#!/usr/bin/env python3
"""
Story 3.3 (ISI-2203) falsification — kill a Run in <=2 clicks (operator-initiated terminate edge).

Differential crash/liveness falsification, same shape as run-reconcile-check.py (3.1), the Story-2.4
reclaim check, and run-retry-backoff-check.py (3.2). It reuses 3.2's fenced-DB primitives (this edge
invokes the SAME Story-2.4 / section-6.3 reclaim), and proves the KILL edge has teeth by contrasting a
NAIVE kill that releases the checkout BEFORE tearing the sandbox down (and double-writes when the old
sandbox keeps working) against the section-6.3 FENCE-FIRST kill that does not.

Scope reminder: Story 2.4 owns the fence-first reclaim primitive; Story 3.2 owns the *involuntary* death
edge (detect + retry with backoff); Story 3.1 owns the phase spine + the Failed->Claiming retry lap.
THIS check stacks the *operator-kill* teeth on top: fence-first ordering (release AFTER teardown), the
confirmation gate, the ABSORBING-terminal `Cancelled` (kill outranks a concurrent retry; no backoff clock),
crash-idempotent completion, and the idempotent double-click intent.

Mutation contract (the headline invariants must be falsifiable -- re-run these after any edit):
  * swap to release-before-fence / delete the step-1 db.fence_resource barrier advance -> (F-ORDER) RED.
  * delete the confirmation gate in kill_fence_first (release unconditionally) -> (F-CONFIRM) RED.
  * make the retry lap ignore a pending kill (requeue unconditionally) -> (F-ABSORB) RED.

stdlib only. `python3 run-cancel-kill-check.py`. Exits non-zero on any falsification.
No wall-clock, no RNG: 'now' is an injected logical clock; there is no jitter on this edge (kill is
terminal, not retried), so the whole check is deterministic across processes.
"""
import sys

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)

# ---------------------------------------------------------------------------
# Simulated durable Postgres: claim rows + run rows. The ONLY recovery state.
# A "pod" is an in-memory liveness token that a killed/partitioned sandbox
# loses control of; the whole point is that recovery never reads it.
# (Faithful copy of the run-retry-backoff-check.py DB -- same section-6.3 primitives.)
# ---------------------------------------------------------------------------
class DB:
    def __init__(self):
        self.claims = {}          # work_item_id -> {holder, run_id, fence, lease_expires_at}
        self.runs = {}            # run_id -> durable recovery state (teardown_fenced_at, phase, ...)
        self.writes = []          # log of (holder, fence) writes ACCEPTED at the resource layer
        self.max_fence_seen = {}  # RESOURCE-layer highest fence accepted/been-fenced-to (section-6.3)

    # ---- section-6.2 claim acquire/renew/release (conditional UPDATEs) ----
    def acquire(self, wid, holder, run_id, now, lease):
        c = self.claims.get(wid)
        if c is None or c["lease_expires_at"] < now:
            new_fence = (c["fence"] + 1) if c else 1
            self.claims[wid] = {"holder": holder, "run_id": run_id,
                                "fence": new_fence, "lease_expires_at": now + lease}
            return new_fence
        return None  # someone holds a live lease

    def write_item(self, wid, holder, fence):
        """Resource-layer fenced write (section-6.3): the PVC/item rejects any fence below the highest
        it has accepted/been-fenced-to. Holder identity is NOT the gate -- the fence token is."""
        seen = self.max_fence_seen.get(wid, 0)
        if fence >= seen:
            self.max_fence_seen[wid] = fence
            self.writes.append((holder, fence))
            return True
        return False  # fenced out -- stale-token write rejected

    def fence_resource(self, wid, fence):
        """section-6.3 step 1, fence-FIRST: advance the resource barrier to `fence` BEFORE releasing the
        checkout -- independent of any new holder's write. Models the terminate + egress-deny + fence
        marker: a late-waking sandbox carrying the old token is rejected in the window AFTER release but
        BEFORE any new holder has written. Removing / reordering this is the F-ORDER mutation."""
        if fence > self.max_fence_seen.get(wid, 0):
            self.max_fence_seen[wid] = fence

    def release_and_bump(self, wid):
        """section-6.3 step 3: release + monotonic fence bump on the claim row."""
        c = self.claims[wid]
        c["fence"] += 1
        c["holder"] = None
        c["lease_expires_at"] = -1
        return c["fence"]


# ===========================================================================
# section-6.3 FENCE-FIRST kill (the SUT for A/B/F-ORDER/F-CONFIRM/F-IDEM/...)
# ===========================================================================
def kill_fence_first(db, wid, run_id, pod_confirmed_gone, now):
    """The operator-kill edge run through the ACTUAL section-6.3 protocol under test:
      (1) fence + tear down FIRST -- advance the resource barrier + stamp a durable `teardown_fenced_at`
          marker, idempotently (a crash mid-teardown re-enters without double-fencing);
      (2) confirm the pod is gone/terminal -> else DON'T release, DON'T mark Cancelled (escalate);
      (3) release the checkout + bump the claim fence;
      (4) mark terminal `Cancelled` (absorbing -- no retry, no next_attempt_at).
    Returns "held" (unconfirmed -> escalated) or "cancelled" (terminal).
    Mutation targets: the step-1 barrier advance (F-ORDER) and the step-2 gate (F-CONFIRM)."""
    c = db.claims[wid]
    run = db.runs.setdefault(run_id, {})
    if run.get("teardown_fenced_at") is None:      # step 1 -- idempotent fence-FIRST + teardown
        db.fence_resource(wid, c["fence"] + 1)     #   <-- F-ORDER mutation target (delete/reorder -> RED)
        run["teardown_fenced_at"] = now
        run["condition"] = "Cancelling"            #   surfaced in-progress state (AC6), not a phase
    if not pod_confirmed_gone:                     # step 2 -- confirm or DON'T release
        return "held"                              #   <-- F-CONFIRM mutation target (delete -> RED)
    if run.get("released") is None:                # step 3 -- release EXACTLY ONCE (idempotent re-entry)
        db.release_and_bump(wid)
        run["released"] = True
    run["phase"] = "Cancelled"                     # step 4 -- absorbing terminal; NO retry clock set
    run["condition"] = None
    return "cancelled"


# ---------------------------------------------------------------------------
# (A) NAIVE kill: releases the checkout the instant kill is issued, THEN tears
#     the pod down. Must double-write when the still-alive sandbox keeps working.
# ---------------------------------------------------------------------------
def scenario_naive_release_before_teardown(db):
    wid, now, lease = "W", 0, 100
    fence = db.acquire(wid, "podA", "run1", now, lease)
    db.write_item(wid, "podA", fence)              # podA is doing real work
    # NAIVE kill: release the checkout FIRST (no fence bump, pod not yet torn down)...
    c = db.claims[wid]
    c["holder"] = "podB"; c["lease_expires_at"] = now + lease   # item handed to a new Run, fence UNCHANGED
    db.write_item(wid, "podB", fence)              # podB works under the SAME fence
    # ...and only now SIGKILL podA -- but podA writes once more before the signal lands:
    still_writes = db.write_item(wid, "podA", fence)
    return still_writes  # True == the double-write the naive (release-first) kill allows

# ---------------------------------------------------------------------------
# (F-CONFIRM) confirmation gate teeth: a killed but NETWORK-PARTITIONED (still-alive)
#     sandbox must NOT have its checkout released. Drives pod_confirmed_gone=False.
# ---------------------------------------------------------------------------
def scenario_unconfirmed_kill_held(db):
    """AC2/AC3: kill issued, but the pod is NOT confirmed gone (node partitioned, pod alive). The
    section-6.3 gate MUST hold -- checkout not released, phase not Cancelled (escalate)."""
    wid, lease = "W", 100
    fence = db.acquire(wid, "podA", "run1", 0, lease)
    db.write_item(wid, "podA", fence)
    outcome = kill_fence_first(db, wid, "run1", pod_confirmed_gone=False, now=250)
    holder = db.claims[wid]["holder"]
    phase = db.runs["run1"].get("phase")
    return outcome, holder, phase  # must be ("held", "podA", None) -- checkout never released

def scenario_naive_release_live(db):
    """Differential twin of F-CONFIRM: a NAIVE kill releases an unconfirmed (still-ALIVE) sandbox's
    checkout to podB. The live podA keeps writing -> two live holders on one item."""
    wid, lease = "W", 100
    fence = db.acquire(wid, "podA", "run1", 0, lease)
    db.write_item(wid, "podA", fence)
    now = 250
    c = db.claims[wid]  # NAIVE: release-on-kill, no confirmation, no fence bump
    c["holder"] = "podB"; c["lease_expires_at"] = now + lease
    db.write_item(wid, "podB", fence)
    podA_still_writes = db.write_item(wid, "podA", fence)  # podA was NEVER gone -> keeps writing
    return podA_still_writes and c["holder"] == "podB"     # True == naive corrupts (two live holders)

# ---------------------------------------------------------------------------
# (B) FENCE-FIRST kill, full wake-after-kill scenario: confirmed gone -> teardown
#     -> release -> new holder claims fresh -> woken (partitioned) sandbox fenced.
# ---------------------------------------------------------------------------
def scenario_confirmed_kill(db):
    wid, now, lease = "W", 0, 100
    fence = db.acquire(wid, "podA", "run1", now, lease)
    db.write_item(wid, "podA", fence)
    outcome = kill_fence_first(db, wid, "run1", pod_confirmed_gone=True, now=250)
    check(outcome == "cancelled", "confirmed kill should terminate Cancelled")
    check(db.runs["run1"]["phase"] == "Cancelled", "kill must mark terminal Cancelled")
    new_fence = db.acquire(wid, "podB", "run1b", 250, lease)  # item reclaimable for other work
    check(new_fence is not None and new_fence > fence, "kill release must bump the fence")
    db.write_item(wid, "podB", new_fence)
    woke = db.write_item(wid, "podA", fence)   # partitioned podA wakes with STALE fence -> rejected
    return woke  # must be False

# ---------------------------------------------------------------------------
# (F-ORDER) release-time fence bump ISOLATED: a woken sandbox writes AFTER release
#     but BEFORE any new holder acquires/writes. The ONLY thing between its stale-fence
#     write and acceptance is the kill's fence-FIRST barrier advance (db.fence_resource).
# ---------------------------------------------------------------------------
def scenario_zombie_before_new_holder(db):
    wid, lease = "W", 100
    fence = db.acquire(wid, "podA", "run1", 0, lease)
    db.write_item(wid, "podA", fence)          # max_fence_seen = fence
    outcome = kill_fence_first(db, wid, "run1", pod_confirmed_gone=True, now=250)
    check(outcome == "cancelled", "confirmed kill must terminate")
    # NO new holder yet. podA wakes and writes with its stale fence, in the release->reclaim window.
    zombie_write = db.write_item(wid, "podA", fence)
    return zombie_write  # must be False -- fenced out by the kill barrier ALONE

# ---------------------------------------------------------------------------
# (F-ABSORB) kill outranks a concurrent retry -- `Cancelled` is absorbing.
#     A kill lands while a retry is in flight (Failed written, 3.1 lap about to
#     re-Claiming). The reconciler must check the kill BEFORE requeue.
# ---------------------------------------------------------------------------
def retry_lap(db, run_id, wid, now, lease, ignore_kill=False):
    """3.1's Failed->Claiming lap. It MUST NOT resurrect a Run that carries a pending kill / is
    terminally Cancelled. Setting ignore_kill=True is the F-ABSORB mutation."""
    run = db.runs.get(run_id, {})
    if not ignore_kill and (run.get("cancel_requested") or run.get("phase") == "Cancelled"):
        return "no-op"   # kill outranks retry -- do NOT re-claim
    db.acquire(wid, "podRetry", run_id, now, lease)
    run["phase"] = "Claiming"
    return "reclaimed"

def scenario_kill_outranks_retry(db, ignore_kill=False):
    wid, lease = "W", 100
    db.acquire(wid, "podA", "run1", 0, lease)
    run = db.runs.setdefault("run1", {})
    run["phase"] = "Failed"; run["reason"] = "SandboxDied"   # 3.2 death edge wrote Failed
    # operator kill lands WHILE the retry is in flight:
    run["cancel_requested"] = True
    kill_fence_first(db, wid, "run1", pod_confirmed_gone=True, now=250)   # kill drives to Cancelled
    # now 3.1's retry lap fires (the race):
    lap = retry_lap(db, "run1", wid, 260, lease, ignore_kill=ignore_kill)
    return db.runs["run1"]["phase"], lap

# ---------------------------------------------------------------------------
# (F-NORETRY) kill never writes the failure/backoff clock (AC4).
# ---------------------------------------------------------------------------
def scenario_kill_no_backoff_clock(db):
    wid, lease = "W", 100
    db.acquire(wid, "podA", "run1", 0, lease)
    kill_fence_first(db, wid, "run1", pod_confirmed_gone=True, now=250)
    run = db.runs["run1"]
    # a killed Run carries NONE of the 3.2 backoff-clock state
    return ("next_attempt_at" not in run and "attempt_count" not in run
            and run["phase"] == "Cancelled")

# ---------------------------------------------------------------------------
# (F-IDEM) crash mid-teardown re-enters idempotently (AC5): crash BETWEEN the
#     teardown marker (step 1) and the release (step 3); re-entry must not
#     double-advance the fence nor double-release.
# ---------------------------------------------------------------------------
def scenario_crash_mid_teardown(db):
    wid, lease = "W", 100
    fence = db.acquire(wid, "podA", "run1", 0, lease)
    db.write_item(wid, "podA", fence)
    # First pass: pod NOT yet confirmed gone -> step 1 stamps teardown_fenced_at + fences, then holds.
    kill_fence_first(db, wid, "run1", pod_confirmed_gone=False, now=250)
    marker_before = db.runs["run1"]["teardown_fenced_at"]   # original stamp (250), held path -> no release
    claim_fence_before = db.claims[wid]["fence"]             # unchanged on the held path
    # ---- CRASH ----  failover leader re-reconciles; pod now confirmed gone.
    kill_fence_first(db, wid, "run1", pod_confirmed_gone=True, now=300)
    # Re-READ the marker AFTER re-entry (do NOT trust the pre-crash capture): the step-1
    # `teardown_fenced_at is None` idempotency guard must make step 1 a no-op on re-entry, so the
    # marker stays the ORIGINAL 250 -- it must NOT be re-stamped to 300. (Capturing the marker
    # before re-entry would hide a re-stamp -- the ISI-2346-F1 teeth gap this hardens; delete the
    # guard and marker_after flips 250->300, turning this RED.)
    marker_after = db.runs["run1"]["teardown_fenced_at"]
    claim_fence_after = db.claims[wid]["fence"]
    released_holder = db.claims[wid]["holder"]
    phase = db.runs["run1"]["phase"]
    # marker stable across re-entry (stamped exactly once), the claim fence bumped EXACTLY once by the
    # single release, release happened exactly once (holder None), terminal Cancelled.
    return (marker_before == 250 and marker_after == 250
            and claim_fence_after == claim_fence_before + 1
            and released_holder is None and phase == "Cancelled")

# ---------------------------------------------------------------------------
# (F-DOUBLECLICK) idempotent intent (AC1): the SAME kill applied twice yields ONE
#     teardown, ONE release, ONE terminal Cancelled -- the second is a no-op.
# ---------------------------------------------------------------------------
def scenario_double_click(db):
    wid, lease = "W", 100
    fence = db.acquire(wid, "podA", "run1", 0, lease)
    kill_fence_first(db, wid, "run1", pod_confirmed_gone=True, now=250)
    fence_after_first = db.claims[wid]["fence"]
    # operator double-clicks / client retries the SAME kill:
    kill_fence_first(db, wid, "run1", pod_confirmed_gone=True, now=251)
    fence_after_second = db.claims[wid]["fence"]
    return fence_after_first == fence_after_second and db.runs["run1"]["phase"] == "Cancelled"

# ---------------------------------------------------------------------------
# (F-PARTIAL) no half-done terminal (AC5): there is no terminal outcome where the
#     pod is torn down but the checkout is still held, or released but not Cancelled.
# ---------------------------------------------------------------------------
def scenario_no_half_terminal(db):
    wid, lease = "W", 100
    db.acquire(wid, "podA", "run1", 0, lease)
    # unconfirmed -> the ONLY non-terminal outcome is "held" (case open), never a half terminal:
    kill_fence_first(db, wid, "run1", pod_confirmed_gone=False, now=250)
    held = db.runs["run1"].get("phase") is None and db.claims[wid]["holder"] == "podA"
    # confirmed -> BOTH release AND Cancelled, together:
    kill_fence_first(db, wid, "run1", pod_confirmed_gone=True, now=300)
    both = db.claims[wid]["holder"] is None and db.runs["run1"]["phase"] == "Cancelled"
    return held and both


# ===========================================================================
# Run every scenario; each asserts the section-6.3 kill edge's teeth.
# ===========================================================================
def main():
    # (A) NAIVE release-before-teardown MUST double-write (harness keeps its detecting power).
    check(scenario_naive_release_before_teardown(DB()) is True,
          "(A) naive release-before-teardown should double-write (harness lost its teeth)")

    # (F-CONFIRM) unconfirmed kill holds the checkout; naive twin corrupts.
    outcome, holder, phase = scenario_unconfirmed_kill_held(DB())
    check(outcome == "held", "(F-CONFIRM) unconfirmed kill must NOT release (return held)")
    check(holder == "podA", "(F-CONFIRM) unconfirmed kill must leave podA holding the checkout")
    check(phase is None, "(F-CONFIRM) unconfirmed kill must NOT mark Cancelled")
    check(scenario_naive_release_live(DB()) is True,
          "(F-CONFIRM twin) naive release of a live sandbox should create two live holders")

    # (B) fence-first kill: woken partitioned sandbox is fenced out.
    check(scenario_confirmed_kill(DB()) is False,
          "(B) woken sandbox after fence-first kill must be REJECTED (stale fence)")

    # (F-ORDER) release-window zombie fenced by the barrier ALONE.
    check(scenario_zombie_before_new_holder(DB()) is False,
          "(F-ORDER) zombie write in the release window must be fenced by the kill barrier")

    # (F-ABSORB) kill outranks retry; the ignore-kill mutation resurrects (must differ).
    phase_ok, lap_ok = scenario_kill_outranks_retry(DB(), ignore_kill=False)
    check(phase_ok == "Cancelled" and lap_ok == "no-op",
          "(F-ABSORB) kill must outrank the retry lap -> terminal Cancelled, lap no-op")
    phase_bad, _ = scenario_kill_outranks_retry(DB(), ignore_kill=True)
    check(phase_bad == "Claiming",
          "(F-ABSORB mutation) a retry lap that ignores the kill DOES resurrect (differential proof)")

    # (F-NORETRY) no backoff clock on a kill.
    check(scenario_kill_no_backoff_clock(DB()) is True,
          "(F-NORETRY) a killed Run must carry no next_attempt_at / attempt_count")

    # (F-IDEM) crash mid-teardown re-enters idempotently.
    check(scenario_crash_mid_teardown(DB()) is True,
          "(F-IDEM) crash mid-teardown must re-enter without double-release / double-fence")

    # (F-DOUBLECLICK) idempotent intent.
    check(scenario_double_click(DB()) is True,
          "(F-DOUBLECLICK) the same kill twice must be a no-op the second time")

    # (F-PARTIAL) no half-done terminal.
    check(scenario_no_half_terminal(DB()) is True,
          "(F-PARTIAL) no terminal state with pod torn down but checkout held (or vice versa)")

    if FAIL:
        print("FALSIFIED — Story 3.3 kill edge has a hole:")
        for m in FAIL:
            print("  -", m)
        sys.exit(1)
    print("OK — Story 3.3 kill edge holds:")
    print("  (A) naive release-before-teardown double-writes (harness has teeth)")
    print("  (F-CONFIRM) unconfirmed kill holds the checkout; naive twin makes two live holders")
    print("  (B) fence-first kill fences a woken partitioned sandbox")
    print("  (F-ORDER) release-window zombie fenced by the kill barrier alone")
    print("  (F-ABSORB) kill outranks the retry lap (Cancelled absorbing); ignore-kill mutation resurrects")
    print("  (F-NORETRY) a killed Run carries no backoff clock")
    print("  (F-IDEM) crash mid-teardown re-enters without double-release / double-fence")
    print("  (F-DOUBLECLICK) the same kill twice is idempotent")
    print("  (F-PARTIAL) no half-done terminal")
    sys.exit(0)


if __name__ == "__main__":
    main()
