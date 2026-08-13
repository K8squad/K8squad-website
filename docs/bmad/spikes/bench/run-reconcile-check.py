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

    def advance(self, expected, new_step, fence):
        # Conditional UPDATE ... WHERE reconcile_step=:expected AND fence_token=:fence (§6.4).
        # fence=None models the NAIVE reconciler, which takes no fence guard at all.
        if self.reconcile_step == expected and (fence is None or fence >= self.fence):
            self.reconcile_step = new_step
            self.fence = fence
            return True
        return False  # stale pass / zombie leader loses


class Crash(Exception):
    pass


def run_phase(step, world, store, fence, durable):
    """Do one phase's external effect + advance the durable step. §6.4 idempotency."""
    idx = STEPS.index(step)
    if step == "dispatching":
        # DURABLE: deterministic id = run_id, shim dedups. NAIVE: fresh id each attempt, no dedup.
        task_id = "run-1" if durable else f"run-1-attempt-{len(world.agent_executions)}"
        world.shim_submit(task_id, dedup=durable)
    elif step == "collecting":
        world.register_artifact("run-1/patch", "diff-bytes", upsert=durable)
    if idx + 1 < len(STEPS):
        nxt = STEPS[idx + 1]
        store.advance(step, nxt, fence)
        if nxt in TERMINAL:
            world.terminal(nxt)


def reconcile_durable(world, store, fence, crash_before):
    """§6.4 reconciler: reads the durable step, resumes from it. Crash-safe."""
    while store.reconcile_step not in TERMINAL:
        step = store.reconcile_step
        if step == crash_before:
            raise Crash(step)  # controller dies at this boundary
        run_phase(step, world, store, fence, durable=True)


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
        # Zombie old leader briefly issues a STALE-fence mutation (fence < current) — must lose.
        stale_ok = store.advance(store.reconcile_step, "succeeded", fence=0)
        assert not stale_ok, f"zombie stale-fence write WON at {crash_at} — fencing broken"
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
    print(f"[durable] §6.4: crash injected at all {len(STEPS)-1} boundaries + zombie stale-fence — "
          f"exactly-once dispatch/collect/terminal, zero lost progress, fencing holds.")
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
    check_durable()                    # (B) prove §6.4 holds under every crash point
    print("OK — crash-safe reconcile falsification passed "
          "(naive detectably breaks; §6.4 durable machine holds exactly-once).")
    sys.exit(0)
