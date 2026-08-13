#!/usr/bin/env python3
"""ISI-2201 (Story 3.1) — crash-safe reconcile falsification for the §8 Run state machine.

The correctness claim of I1 (arch §8, §6.4, ADR-005) is: a Run controller can crash
or fail over at ANY phase boundary, and the failover leader re-reads DURABLE Postgres
state and continues — with each phase's external side effect happening AT MOST ONCE:

  * dispatch  — deterministic a2a_task_id = run_id + shim dedup  → never two agent runs
  * collect   — content-addressed artifact upsert                → never a duplicate
  * transition— conditional UPDATE ... WHERE reconcile_step=:exp  → never a double-advance
  * fencing   — a stale-fence zombie leader loses every UPDATE    → safety != single-writer

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

    # --- dispatch: the shim. Deterministic id + dedup is what makes it once-only. ---
    def shim_submit(self, task_id, dedup):
        if dedup and task_id in {t for t in self.agent_executions}:
            return  # shim reattaches to the in-flight task; NO second execution
        self.agent_executions.append(task_id)

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

    def advance(self, expected, new_step, fence):
        # Conditional UPDATE ... WHERE reconcile_step=:expected AND fence_token=:fence (§6.4).
        # fence=None models the NAIVE reconciler, which takes no fence guard at all.
        if self.reconcile_step == expected and (fence is None or fence >= self.fence):
            self.reconcile_step = new_step
            self.fence = fence
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


def run_phase(step, world, store, fence, durable, crash_after_effect=None):
    """Do one phase's external effect + advance the durable step. §6.4 idempotency.

    `crash_after_effect` injects a crash at the §6.4 CRUX window: the external effect
    has fired but the durable step-advance transaction has NOT committed. This is the
    only crash point where re-entry re-drives an *already-performed* effect, so it is
    the only one that actually exercises the deterministic-id dedup / content-addressed
    upsert. A crash at a phase *boundary* (see `crash_before`) resumes trivially and
    proves nothing about idempotency — the effect had already committed cleanly.
    """
    idx = STEPS.index(step)
    if step == "dispatching":
        # DURABLE: deterministic id = run_id, shim dedups. NAIVE: fresh id each attempt, no dedup.
        task_id = "run-1" if durable else f"run-1-attempt-{len(world.agent_executions)}"
        world.shim_submit(task_id, dedup=durable)
    elif step == "collecting":
        world.register_artifact("run-1/patch", "diff-bytes", upsert=durable)
    if step == crash_after_effect:
        raise Crash(step)  # effect applied, step NOT yet advanced — re-entry must be idempotent
    if idx + 1 < len(STEPS):
        nxt = STEPS[idx + 1]
        store.advance(step, nxt, fence)
        if nxt in TERMINAL:
            world.terminal(nxt)


def reconcile_durable(world, store, fence, crash_before, crash_after_effect=None):
    """§6.4 reconciler: reads the durable step, resumes from it. Crash-safe.

    `crash_before` = die at a phase boundary (pre-effect). `crash_after_effect` = die
    mid-phase after the external effect but before the step-advance commits (the §6.4
    crux window that forces an idempotent re-drive on failover).
    """
    while store.reconcile_step not in TERMINAL:
        step = store.reconcile_step
        if step == crash_before:
            raise Crash(step)  # controller dies at this boundary
        run_phase(step, world, store, fence, durable=True, crash_after_effect=crash_after_effect)


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
        # Failover leader takes over with a fresh fence, re-reads durable step, continues.
        reconcile_durable(world, store, fence=2, crash_before=None)

        assert store.reconcile_step == "succeeded", f"crash@{crash_at}: not terminal"
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
    for crash_at in ("dispatching", "collecting"):
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
        reconcile_durable(world, store, fence=2, crash_before=None)
        assert store.reconcile_step == "succeeded", f"intraphase@{crash_at}: not terminal"
        assert len(world.agent_executions) == 1, (
            f"intraphase@{crash_at}: {len(world.agent_executions)} agent executions (want 1) — "
            f"dedup did not suppress the re-driven dispatch")
        assert world.artifacts == {"run-1/patch": "diff-bytes"}, (
            f"intraphase@{crash_at}: duplicate/lost artifact {world.artifacts} — upsert not idempotent")
        assert world.terminal_transitions == ["succeeded"], (
            f"intraphase@{crash_at}: {world.terminal_transitions} terminal transitions (want 1)")
    print("[durable] §6.4 crux: crash AFTER effect / BEFORE commit at dispatching+collecting — "
          "re-driven effect suppressed by dedup/upsert (idempotency mechanisms exercised).")
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


if __name__ == "__main__":
    check_naive_detectably_breaks()   # (A) prove the harness can catch a double-drive
    check_durable()                    # (B) prove §6.4 holds under every phase-boundary crash
    check_durable_intraphase()         # (C) prove dedup/upsert hold at the mid-phase crux window
    print("OK — crash-safe reconcile falsification passed "
          "(naive detectably breaks; §6.4 durable machine holds exactly-once at boundary AND "
          "mid-phase crash windows).")
    sys.exit(0)
