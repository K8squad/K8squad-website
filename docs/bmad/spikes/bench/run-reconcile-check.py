#!/usr/bin/env python3
"""ISI-2201 (Story 3.1) — crash-safe reconcile falsification for the §8 Run state machine.

The correctness claim of I1 (arch §8, §6.4, ADR-005) is: a Run controller can crash
or fail over at ANY phase boundary, and the failover leader re-reads DURABLE Postgres
state and continues — with each phase's external side effect happening AT MOST ONCE:

  * bind      — sandbox provision keyed by run_id                 → never double-provisions
  * dispatch  — deterministic a2a_task_id = run_id + shim dedup  → never two agent runs
  * collect   — content-addressed artifact upsert                → never a duplicate
  * transition— conditional UPDATE ... WHERE reconcile_step=:exp  → never a double-advance
  * fencing   — a bumped-fence zombie loses the equality guard    → safety for reclaim zombie
  * step-CAS  — an equal-fence competitor loses the step guard    → safety for split-brain

Two split-brain shapes, two DIFFERENT safety mechanisms (AC4): a leader whose fence was bumped
out from under it by a §6.3 reclaim loses the fence-equality guard (fencing = safety); two leaders
that share the SAME fence (claim never reclaimed) are serialized by the step-CAS instead, because
fencing cannot tell equal-fence writers apart. The retry lap (Failed→Claiming, §8/FR-A5) re-runs
claiming_sandbox after a fence-first reclaim and must reattach the run_id-keyed sandbox bind.

This is a *differential* falsification, not a happy-path demo. It runs the same
crash-injection scenario two ways and asserts:

  (A) a NAIVE reconciler that keeps phase progress in CONTROLLER MEMORY and resumes
      from that memory DOES, when the process is replaced (failover), lose progress
      and/or double-dispatch a second agent execution  → proves the harness is
      actually powerful enough to catch a double-drive; and

  (B) the §6.4 DURABLE reconciler (reconcile_step in a simulated Postgres,
      deterministic task id + dedup, content-addressed artifact upsert, fenced
      conditional step-advance) produces EXACTLY ONE agent execution, EXACTLY ONE
      artifact set, EXACTLY ONE terminal transition, and ZERO lost progress — for a
      crash injected at EVERY phase boundary, plus a zombie-leader stale-fence write.

If (A) ever passes (no double-drive seen) the check fails LOUD, because that means
the test lost its detecting power and (B) proves nothing.

No deps: an in-process model of the reconcile loop + a simulated durable store, with
crash injected deterministically at each boundary (no randomness needed — we enumerate
every crash point). The real-Postgres wiring is the Story 3.1 integration test /
Epic-2 coord schema; the logic proven here (idempotency + fencing) is the crux.
"""
import sys

# The pinned phase progression (arch §8 coarse enum → fine-grained durable steps, r28).
STEPS = ["pending", "claiming_sandbox", "dispatching", "running", "collecting", "succeeded"]
TERMINAL = {"succeeded", "failed", "cancelled"}


class World:
    """The observable, side-effecting outside world — the things that must happen once."""
    def __init__(self):
        self.agent_executions = []   # one entry per REAL agent run started (dispatch effect)
        self.artifacts = {}          # content-addressed: key -> content (collect effect)
        self.terminal_transitions = []  # one entry per terminal advance
        self.sandbox_binds = []      # one entry per sandbox PROVISIONED (claiming_sandbox effect)

    # --- dispatch: the shim. Deterministic id + dedup is what makes it once-only. ---
    def shim_submit(self, task_id, dedup):
        if dedup and task_id in {t for t in self.agent_executions}:
            return  # shim reattaches to the in-flight task; NO second execution
        self.agent_executions.append(task_id)

    # --- claiming_sandbox: warm-pool bind (Story 3.2). Keyed by run_id = once-only. ---
    def bind_sandbox(self, run_id, keyed):
        # DURABLE (keyed): a re-entry (crash mid-bind, OR a Failed→Claiming retry lap) reattaches
        # to the sandbox already provisioned for this run_id — never double-provisions (story:122-125).
        # NAIVE (not keyed): every re-entry provisions a fresh sandbox → duplicate binds.
        if keyed and run_id in self.sandbox_binds:
            return  # reattach to the existing sandbox; NO second provision
        self.sandbox_binds.append(run_id)

    # --- collect: artifact registration. Upsert on a content-addressed key = once-only. ---
    def register_artifact(self, key, content, upsert):
        if upsert:
            self.artifacts[key] = content            # idempotent republish
        else:
            self.artifacts.setdefault(f"{key}#{len(self.artifacts)}", content)  # naive: appends dupes

    def terminal(self, phase):
        self.terminal_transitions.append(phase)


class DurableStore:
    """Simulated Postgres coord: the reconcile_step + fence are the source of truth."""
    def __init__(self):
        self.reconcile_step = "pending"
        self.fence = 1
        self.audit_log = []   # §6.5 coord.audit_log rows, one per COMMITTED transition (AC6)
        self.outbox = []      # §6.6 transactional-outbox events, co-committed with the transition

    def reclaim(self, new_fence):
        # §6.3 fence-first reclaim: fence the dead pod (bump the token) BEFORE releasing the
        # claim / re-entering Claiming. Monotonic — a reclaim only ever raises the fence. This is
        # what makes an OLD leader's later write stale (its token no longer equals current, below).
        if new_fence > self.fence:
            self.fence = new_fence
            return True
        return False

    def advance(self, expected, new_step, fence):
        # Conditional UPDATE ... WHERE reconcile_step=:expected AND fence_token=:fence (§6.4).
        # Two INDEPENDENT guards, each covering a different split-brain shape (AC3/AC4):
        #   * fence_token = :fence  — EQUALITY (arch §6.3:711); a zombie whose fence was bumped
        #     out from under it by a reclaim (§6.3) no longer matches → loses. Fencing = safety
        #     for the RECLAIM (bumped-fence) zombie.
        #   * reconcile_step = :expected — the step-CAS; on a PURE split-brain (claim NOT reclaimed,
        #     both leaders share the SAME fence) fencing can't tell them apart, so THIS is what
        #     serializes two equal-fence writers. Step-CAS = safety for the SAME-fence competitor.
        # fence=None models the NAIVE reconciler, which takes no fence guard at all.
        if self.reconcile_step == expected and (fence is None or fence == self.fence):
            self.reconcile_step = new_step
            # AC6: the audit row (§6.5) + outbox event (§6.6) are written in the SAME
            # transaction as the step advance. A pass that LOSES the conditional UPDATE
            # (stale/zombie, below) reaches neither line — no phantom event, no orphaned
            # transition. This is why they live inside the committed branch.
            self.audit_log.append((expected, new_step, fence))
            self.outbox.append(new_step)
            return True
        return False  # stale pass / zombie leader loses — writes NO audit row, NO event


class Crash(Exception):
    pass


def run_phase(step, world, store, fence, durable, crash_after_effect=None, lap=None, fail_at=None):
    """Do one phase's external effect + advance the durable step. §6.4 idempotency.

    `crash_after_effect` injects a crash at the §6.4 CRUX window: the external effect
    has fired but the durable step-advance transaction has NOT committed. This is the
    only crash point where re-entry re-drives an *already-performed* effect, so it is
    the only one that actually exercises the deterministic-id dedup / content-addressed
    upsert. A crash at a phase *boundary* (see `crash_before`) resumes trivially and
    proves nothing about idempotency — the effect had already committed cleanly.

    `lap` disambiguates the dispatch task id ACROSS retry attempts: the id is
    deterministic *within* a lap (so a crash re-drive within one attempt dedups), but a
    Failed→Claiming retry is a NEW attempt and gets a fresh execution (`run_id#lap<n>`).
    `fail_at` drives that step to the terminal `failed` (models an agent attempt failing).
    """
    idx = STEPS.index(step)
    if step == "claiming_sandbox":
        # §6.2/§9 warm-pool bind, keyed by run_id — re-entry (crash OR retry lap) reattaches.
        world.bind_sandbox("run-1", keyed=durable)
    elif step == "dispatching":
        # DURABLE: deterministic id = run_id (per lap), shim dedups. NAIVE: fresh id each attempt.
        if durable:
            task_id = "run-1" if lap is None else f"run-1#lap{lap}"
        else:
            task_id = f"run-1-attempt-{len(world.agent_executions)}"
        world.shim_submit(task_id, dedup=durable)
    elif step == "collecting":
        world.register_artifact("run-1/patch", "diff-bytes", upsert=durable)
    if step == crash_after_effect:
        raise Crash(step)  # effect applied, step NOT yet advanced — re-entry must be idempotent
    if idx + 1 < len(STEPS):
        nxt = "failed" if step == fail_at else STEPS[idx + 1]  # fail_at diverts to the Failed edge
        store.advance(step, nxt, fence)
        if nxt in TERMINAL:
            world.terminal(nxt)


def reconcile_durable(world, store, fence, crash_before, crash_after_effect=None,
                      lap=None, fail_at=None):
    """§6.4 reconciler: reads the durable step, resumes from it. Crash-safe.

    `crash_before` = die at a phase boundary (pre-effect). `crash_after_effect` = die
    mid-phase after the external effect but before the step-advance commits (the §6.4
    crux window that forces an idempotent re-drive on failover). `lap`/`fail_at` drive
    the Failed→Claiming retry lap (see `run_phase`).
    """
    while store.reconcile_step not in TERMINAL:
        step = store.reconcile_step
        if step == crash_before:
            raise Crash(step)  # controller dies at this boundary
        run_phase(step, world, store, fence, durable=True,
                  crash_after_effect=crash_after_effect, lap=lap, fail_at=fail_at)


def reconcile_naive(world, mem_step, crash_before):
    """NAIVE reconciler: continuity lives in `mem_step` (controller memory). Returns final mem_step."""
    store = DurableStore()          # naive still has *a* store but resumes from MEMORY, not it
    store.reconcile_step = mem_step
    while store.reconcile_step not in TERMINAL:
        step = store.reconcile_step
        if step == crash_before:
            return step             # process replaced; in-memory `step` is what a naive resume trusts
        run_phase(step, world, store, None, durable=False)
    return store.reconcile_step


def check_durable():
    """Inject a crash at EVERY phase boundary; assert exactly-once effects after failover."""
    for crash_at in STEPS[:-1]:
        world = World()
        store = DurableStore()
        # First leader runs until it crashes at `crash_at`.
        try:
            reconcile_durable(world, store, fence=1, crash_before=crash_at)
        except Crash:
            pass
        # Zombie old leader briefly issues a STALE-fence mutation (fence < current) — must lose,
        # and (AC6) must write NEITHER an audit row NOR an outbox event (no phantom event).
        audit_before, outbox_before = len(store.audit_log), len(store.outbox)
        stale_ok = store.advance(store.reconcile_step, "succeeded", fence=0)
        assert not stale_ok, f"zombie stale-fence write WON at {crash_at} — fencing broken"
        assert len(store.audit_log) == audit_before and len(store.outbox) == outbox_before, (
            f"crash@{crash_at}: fenced-out zombie pass wrote a phantom audit/event (AC6 broken)")
        # Failover leader takes over: §6.3 fence-first reclaim bumps the token, THEN it re-reads
        # the durable step and continues (its writes now carry the current fence).
        assert store.reclaim(2), f"crash@{crash_at}: failover reclaim failed to bump the fence"
        reconcile_durable(world, store, fence=2, crash_before=None)

        assert store.reconcile_step == "succeeded", f"crash@{crash_at}: not terminal"
        assert world.sandbox_binds == ["run-1"], (
            f"crash@{crash_at}: sandbox provisioned {world.sandbox_binds} (want once) — "
            f"claiming_sandbox bind not run_id-keyed across failover")
        assert len(world.agent_executions) == 1, (
            f"crash@{crash_at}: {len(world.agent_executions)} agent executions (want 1) — "
            f"double-dispatch across failover")
        assert world.artifacts == {"run-1/patch": "diff-bytes"}, (
            f"crash@{crash_at}: duplicate/lost artifact {world.artifacts}")
        assert world.terminal_transitions == ["succeeded"], (
            f"crash@{crash_at}: {world.terminal_transitions} terminal transitions (want 1)")
        # AC6: exactly one audit row + one outbox event per COMMITTED transition — never a
        # double-audit across failover, never a transition with no audit trail / event.
        assert len(store.audit_log) == len(STEPS) - 1 == len(store.outbox), (
            f"crash@{crash_at}: {len(store.audit_log)} audit / {len(store.outbox)} outbox rows "
            f"(want {len(STEPS)-1} each) — audit/event not co-committed 1:1 with transitions")
    print(f"[durable] §6.4: crash injected at all {len(STEPS)-1} boundaries + zombie stale-fence — "
          f"exactly-once dispatch/collect/terminal, zero lost progress, fencing holds; "
          f"audit+outbox co-committed 1:1 per transition, zero phantom on fenced-out pass (AC6).")
    return True


def check_durable_intraphase():
    """The §6.4 CRUX: crash AFTER an effectful phase fires but BEFORE its step commits.

    This is the only crash window that re-drives an already-performed external effect on
    failover, so it is the only one that actually exercises the dedup / upsert mechanisms
    (a boundary crash resumes from a cleanly-committed step and never re-runs the effect).
    Neutering dedup or upsert MUST make this check fail — that is what gives it teeth.
    """
    for crash_at in ("claiming_sandbox", "dispatching", "collecting"):
        world = World()
        store = DurableStore()
        # Leader 1 runs until the effect at `crash_at` has fired, then dies before commit.
        try:
            reconcile_durable(world, store, fence=1, crash_before=None, crash_after_effect=crash_at)
        except Crash:
            pass
        # The durable step is still the SAME phase — the effect happened, the advance did not.
        assert store.reconcile_step == crash_at, (
            f"intraphase@{crash_at}: step advanced to {store.reconcile_step} before commit — "
            f"effect and step-advance were not atomic")
        # Failover leader re-enters the SAME phase and MUST re-drive it idempotently.
        assert store.reclaim(2), f"intraphase@{crash_at}: failover reclaim failed to bump the fence"
        reconcile_durable(world, store, fence=2, crash_before=None)
        assert store.reconcile_step == "succeeded", f"intraphase@{crash_at}: not terminal"
        assert world.sandbox_binds == ["run-1"], (
            f"intraphase@{crash_at}: sandbox provisioned {world.sandbox_binds} (want once) — "
            f"run_id-keyed bind did not reattach on the mid-phase re-drive")
        assert len(world.agent_executions) == 1, (
            f"intraphase@{crash_at}: {len(world.agent_executions)} agent executions (want 1) — "
            f"dedup did not suppress the re-driven dispatch")
        assert world.artifacts == {"run-1/patch": "diff-bytes"}, (
            f"intraphase@{crash_at}: duplicate/lost artifact {world.artifacts} — upsert not idempotent")
        assert world.terminal_transitions == ["succeeded"], (
            f"intraphase@{crash_at}: {world.terminal_transitions} terminal transitions (want 1)")
    print("[durable] §6.4 crux: crash AFTER effect / BEFORE commit at claiming_sandbox+dispatching+"
          "collecting — re-driven effect suppressed by run_id-keyed bind / dedup / upsert "
          "(idempotency mechanisms exercised).")
    return True


def check_naive_detectably_breaks():
    """The naive design MUST break under failover, or the harness has no teeth."""
    broke = False
    # Crash AFTER the dispatch effect (which fires advancing dispatching→running), so leader 1 has
    # already started an agent execution when it dies.
    for crash_at in ["running", "collecting"]:
        world = World()
        reconcile_naive(world, "pending", crash_before=crash_at)  # leader 1 dies at crash_at
        # Failover: the naive controller kept continuity in MEMORY, which is now gone — the new
        # process has no durable record, so it restarts from `pending` and re-drives every phase
        # (dispatch with no dedup, collect with no upsert) that leader 1 already performed.
        reconcile_naive(world, "pending", crash_before=None)
        doubled = len(world.agent_executions) > 1 or len(world.artifacts) > 1
        if doubled:
            broke = True
    assert broke, ("NAIVE reconciler did NOT double-drive across failover — the falsification lost "
                   "its detecting power; the durable proof is meaningless. FIX THE HARNESS.")
    print("[naive]  in-memory continuity: double-drives a phase's side effect across failover "
          "(detectably broken — harness has teeth).")
    return True


# --- AC5 terminal-vs-non-terminal classifier (Paused must stay reachable) -----------------
# The non-terminal phases a reconcile loop may resume from. Paused/Paused(rate_limited) (§8) are
# NOT driven by this story, but the machine must not make them unreachable (AC5) — a classifier
# that silently dropped Paused into "unknown" would let a later rate-limit-recovery story wire a
# phase the machine can never re-enter.
NON_TERMINAL_RESUMABLE = {
    "pending", "claiming_sandbox", "dispatching", "running", "collecting",
    "paused", "paused(rate_limited)",
}


def classify(phase):
    """AC5: is a phase terminal (absorbing) or non-terminal (resumable)?"""
    if phase in TERMINAL:
        return "terminal"
    if phase in NON_TERMINAL_RESUMABLE:
        return "resumable"
    return "unknown"  # a phase the machine can neither absorb nor resume — an AC5 gap


def check_paused_classifier():
    """F3(b) / AC5: Paused + Paused(rate_limited) are non-terminal RESUMABLE, not terminal."""
    for p in ("paused", "paused(rate_limited)"):
        assert p not in TERMINAL, f"AC5: {p} classified terminal — it is non-terminal resumable"
        assert classify(p) == "resumable", (
            f"AC5: {p} is {classify(p)} (want resumable) — the machine made Paused unreachable")
    for p in ("succeeded", "cancelled"):
        assert classify(p) == "terminal", f"AC5: {p} must be terminal (absorbing)"
    # `failed` is terminal-absorbing UNLESS retryPolicy re-enters Claiming (see check_retry_lap).
    assert classify("failed") == "terminal", "AC5: failed must be terminal (absorbing) by default"
    print("[durable] AC5 classifier: Paused/Paused(rate_limited) are non-terminal resumable "
          "(reachable for a later rate-limit-recovery story); succeeded/failed/cancelled terminal.")
    return True


def check_same_fence_split_brain():
    """F4 / AC4: on a PURE leader-election split-brain the claim is NOT reclaimed, so the old and
    the failover leader carry the SAME fence — fencing cannot distinguish them. The step-CAS
    (WHERE reconcile_step = :expected, AC3), NOT fencing, is what prevents the double-advance here.
    Two equal-fence leaders race to advance the same step; assert exactly one wins.
    """
    world = World()
    store = DurableStore()
    store.advance("pending", "claiming_sandbox", fence=1)  # reach a mid-machine step at fence 1
    step = store.reconcile_step
    audit_before, outbox_before = len(store.audit_log), len(store.outbox)
    # No reclaim happened → both leaders still hold fence=1. Fencing is a no-op discriminator here.
    a_ok = store.advance(step, "dispatching", fence=1)
    b_ok = store.advance(step, "dispatching", fence=1)  # SAME fence — must lose on the step-CAS
    assert a_ok and not b_ok, (
        f"same-fence split-brain: a_ok={a_ok} b_ok={b_ok} — the step-CAS failed to serialize two "
        f"EQUAL-fence writers; fencing alone cannot (AC3/AC4 broken)")
    assert store.reconcile_step == "dispatching", "same-fence: step did not advance exactly once"
    assert len(store.audit_log) == audit_before + 1 and len(store.outbox) == outbox_before + 1, (
        "same-fence split-brain: a second audit/outbox row leaked past the step-CAS (double-advance)")
    print("[durable] AC4 same-fence split-brain: two EQUAL-fence leaders race; the step-CAS "
          "(WHERE reconcile_step=:expected) serializes them — exactly one advance. Fencing is NOT "
          "load-bearing for this shape; the step-CAS is (credits AC3, not fencing).")
    return True


def check_retry_lap():
    """F3(a)+(c) / AC5 + §8 FR-A5: the Failed → Claiming retry lap — the trickiest re-entry.

    Lap 1 fails; retryPolicy-within-budget does a §6.3 FENCE-FIRST reclaim (fence the dead pod,
    THEN release the claim) and re-enters `claiming_sandbox`. The second lap must re-run
    claiming_sandbox IDEMPOTENTLY: the sandbox bind is keyed by run_id, so the retry REATTACHES to
    the sandbox provisioned on lap 1 — never double-provisions (story:122-125). Each lap IS a
    genuine new agent attempt, though (a retry re-dispatches), so agent_executions grows per lap.
    """
    world = World()
    store = DurableStore()
    # ---- Lap 1: pending → claiming_sandbox (binds) → dispatching (attempt 0) → running → FAILED
    reconcile_durable(world, store, fence=1, crash_before=None, lap=0, fail_at="running")
    assert store.reconcile_step == "failed", f"retry lap 1 did not reach failed: {store.reconcile_step}"
    assert world.sandbox_binds == ["run-1"], f"lap 1 sandbox bind not once: {world.sandbox_binds}"
    assert world.agent_executions == ["run-1#lap0"], f"lap 1 dispatch wrong: {world.agent_executions}"
    # ---- retryPolicy within budget: §6.3 fence-first reclaim, THEN re-enter Claiming ----
    assert store.reclaim(2), "retry: fence-first reclaim did not bump the fence"
    store.reconcile_step = "claiming_sandbox"  # §8 Failed → Claiming (after the reclaim)
    # ---- Lap 2: the retry re-runs claiming_sandbox; the run_id-keyed bind MUST reattach ----
    reconcile_durable(world, store, fence=2, crash_before=None, lap=1)
    assert store.reconcile_step == "succeeded", f"retry lap 2 did not succeed: {store.reconcile_step}"
    # THE load-bearing assertion: claiming_sandbox ran on BOTH laps, but the run_id-keyed bind
    # provisioned the sandbox EXACTLY ONCE — the retry reattached, never double-provisioned.
    assert world.sandbox_binds == ["run-1"], (
        f"retry re-provisioned the sandbox: {world.sandbox_binds} — claiming_sandbox bind is not "
        f"idempotent across the Failed→Claiming lap (story:122-125, AC3)")
    # A retry is a genuine new attempt: one distinct agent execution per lap, no cross-lap dedup.
    assert world.agent_executions == ["run-1#lap0", "run-1#lap1"], (
        f"retry agent attempts wrong: {world.agent_executions} — a retry lap must re-dispatch a "
        f"fresh execution, not dedup onto the failed one")
    print("[durable] §8/AC5 retry lap: Failed→(fence-first reclaim §6.3)→Claiming re-runs "
          "claiming_sandbox; run_id-keyed sandbox bind reattaches (provisioned ONCE across both "
          "laps); each lap is one genuine agent attempt.")
    return True


if __name__ == "__main__":
    check_naive_detectably_breaks()   # (A) prove the harness can catch a double-drive
    check_durable()                    # (B) prove §6.4 holds under every phase-boundary crash
    check_durable_intraphase()         # (C) prove idempotency holds at the mid-phase crux window
    check_same_fence_split_brain()     # (D) F4: step-CAS serializes equal-fence split-brain
    check_retry_lap()                  # (E) F3: Failed→Claiming retry, run_id-keyed bind once
    check_paused_classifier()          # (F) F3/AC5: Paused stays non-terminal resumable
    print("OK — crash-safe reconcile falsification passed "
          "(naive detectably breaks; §6.4 durable machine holds exactly-once at boundary, "
          "mid-phase, retry-lap, and same-fence split-brain windows; Paused stays reachable).")
    sys.exit(0)
