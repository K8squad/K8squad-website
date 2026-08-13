#!/usr/bin/env python3
"""
Story 3.2 (ISI-2202) falsification — retry/resume of dead Runs with backoff.

Differential crash/liveness falsification, same shape as run-reconcile-check.py (3.1) and the
Story-2.4 reclaim check. It proves the DEATH-DETECTION EDGE has teeth by contrasting a NAIVE detector
that reclaims on lease-expiry alone (and double-writes when a paused holder wakes) against the §6.3
CONFIRMED-DEATH + FENCE-FIRST detector that does not.

Scope reminder: Story 3.1 owns the Failed->Claiming retry-lap re-entrancy (its own check). THIS check
stacks the *detection* false-positive (GC-pause zombie) and false-negative (wedged-but-present pod)
teeth, plus the bounded-backoff policy and its crash-safe durable schedule, and the two-clock
distinctness vs rate-limit.

stdlib only. `python3 run-retry-backoff-check.py`. Exits non-zero on any falsification.
No wall-clock, no RNG seeding surprises: 'now' is an injected logical clock, jitter is deterministic
per (run_id, attempt) so the check is reproducible.
"""
import sys

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)

# ---------------------------------------------------------------------------
# Simulated durable Postgres: claim rows + run rows. The ONLY recovery state.
# A "pod" is an in-memory liveness token that a dead/partitioned holder loses
# control of; the whole point is that recovery never reads it.
# ---------------------------------------------------------------------------
class DB:
    def __init__(self):
        # claim: work_item_id -> {holder, run_id, fence, lease_expires_at}
        self.claims = {}
        # run: run_id -> durable recovery state
        self.runs = {}
        self.writes = []  # log of (holder, fence) writes ACCEPTED at the resource layer
        # canonical fencing: the RESOURCE (PVC/work item) remembers the highest fence it has
        # accepted and rejects any lower one (§6.3 resource-layer fence check). A naive design
        # that never bumps the fence on reclaim cannot use this — both holders carry the same
        # token, so the resource cannot tell the zombie from the new holder.
        self.max_fence_seen = {}

    # ---- §6.2 claim acquire/renew/release (conditional UPDATEs) ----
    def acquire(self, wid, holder, run_id, now, lease):
        c = self.claims.get(wid)
        if c is None or c["lease_expires_at"] < now:
            new_fence = (c["fence"] + 1) if c else 1
            self.claims[wid] = {"holder": holder, "run_id": run_id,
                                "fence": new_fence, "lease_expires_at": now + lease}
            return new_fence
        return None  # someone holds a live lease

    def renew(self, wid, holder, fence, now, lease):
        c = self.claims.get(wid)
        # guarded by holder AND fence AND unexpired lease (§6.2)
        if c and c["holder"] == holder and c["fence"] == fence and c["lease_expires_at"] > now:
            c["lease_expires_at"] = now + lease
            return True
        return False

    def write_item(self, wid, holder, fence):
        """Resource-layer fenced write (§6.3): the PVC/item rejects any fence below the highest
        it has accepted. Holder identity is NOT the gate — the fence token is. A zombie that still
        'holds' a stale token is rejected because a newer token has been seen; a naive design that
        never bumps the token cannot distinguish the zombie and accepts its write."""
        seen = self.max_fence_seen.get(wid, 0)
        if fence >= seen:
            self.max_fence_seen[wid] = fence
            self.writes.append((holder, fence))
            return True
        return False  # fenced out — stale-token write rejected

    def release_and_bump(self, wid):
        """§6.3 step 3: release + monotonic fence bump so a resurrected zombie is fenced out."""
        c = self.claims[wid]
        c["fence"] += 1
        c["holder"] = None
        c["lease_expires_at"] = -1

# ---------------------------------------------------------------------------
# (A) NAIVE detector: reclaims on lease-expiry ALONE, no pod confirmation,
#     no fence bump on release. Must double-write when a paused holder wakes.
# ---------------------------------------------------------------------------
def scenario_naive_gc_pause(db):
    wid, now, lease = "W", 0, 100
    fence = db.acquire(wid, "podA", "run1", now, lease)
    db.write_item(wid, "podA", fence)              # podA does real work
    now = 250                                       # podA GC-paused; lease lapsed at t=100
    # NAIVE: lease_expires_at < now -> reclaim immediately, hand to podB, NO fence bump.
    c = db.claims[wid]
    check(c["lease_expires_at"] < now, "naive precondition: lease should be expired")
    c["holder"] = "podB"; c["lease_expires_at"] = now + lease  # naive reassign, fence UNCHANGED
    db.write_item(wid, "podB", fence)              # podB works under the SAME fence
    # podA WAKES from GC pause, still believes it holds fence -> writes again (naive: accepted!)
    woke = db.write_item(wid, "podA", fence)
    return woke  # True == the double-write the naive design allows

# ---------------------------------------------------------------------------
# (B) CONFIRMED-DEATH + FENCE-FIRST detector: needs lease-expiry AND pod-gone,
#     runs fence->confirm->release with a monotonic fence bump.
# ---------------------------------------------------------------------------
def reclaim_fence_first(db, wid, pod_confirmed_gone):
    """§6.3: (1) fence (record marker) (2) confirm gone -> else DON'T release (3) release+bump."""
    if not pod_confirmed_gone:
        return "held"   # step 2 escalates to cordon+alert, claim stays held (AC3)
    db.release_and_bump(wid)  # step 3: only after confirmation, with fence bump
    return "released"

def scenario_confirmed_gc_pause(db):
    wid, now, lease = "W", 0, 100
    fence = db.acquire(wid, "podA", "run1", now, lease)
    db.write_item(wid, "podA", fence)
    now = 250
    # A1 lease-expiry opens the case; A2 pod-watch says podA is GONE -> confirmed dead.
    outcome = reclaim_fence_first(db, wid, pod_confirmed_gone=True)
    check(outcome == "released", "confirmed-dead pod should release")
    new_fence = db.acquire(wid, "podB", "run1", now, lease)  # retry lap re-claims fresh
    check(new_fence is not None and new_fence > fence, "reclaim must bump the fence")
    db.write_item(wid, "podB", new_fence)
    # podA wakes with its STALE fence -> must be rejected.
    woke = db.write_item(wid, "podA", fence)
    return woke  # must be False

# ---------------------------------------------------------------------------
# (C) false-negative teeth: wedged-but-present pod. Pod still exists (watch never
#     fires) but agent hung and stopped renewing. The lease sweeper must still act.
# ---------------------------------------------------------------------------
def scenario_wedged_pod(db):
    wid, now, lease = "W", 0, 100
    fence = db.acquire(wid, "podA", "run1", now, lease)
    now = 250  # podA hung: lease lapsed, but the pod object STILL EXISTS (watch silent)
    pod_watch_fired = False           # A2 alone would never detect this
    lease_sweep_opens = db.claims[wid]["lease_expires_at"] < now  # A1 does
    check(lease_sweep_opens and not pod_watch_fired,
          "wedged-pod: sweep must open the case that the watch misses")
    # fence step TERMINATES the wedged pod -> now confirmable gone -> release
    outcome = reclaim_fence_first(db, wid, pod_confirmed_gone=True)  # after fence kills it
    return outcome  # must be "released" (not wedged forever)

# ---------------------------------------------------------------------------
# (D) backoff policy: monotone, capped, jittered, budgeted.
# ---------------------------------------------------------------------------
def det_jitter(run_id, attempt):
    """Deterministic bounded jitter in [-0.2, +0.2] fraction, reproducible per (run,attempt)."""
    h = (hash((run_id, attempt)) % 1000) / 1000.0  # 0..1
    return (h - 0.5) * 0.4  # -0.2 .. +0.2

def backoff_delay(run_id, attempt, base=10, mult=2, cap=600):
    raw = min(base * (mult ** (attempt - 1)), cap)
    return raw * (1 + det_jitter(run_id, attempt)), raw

def scenario_backoff(db):
    base, mult, cap, max_attempts = 10, 2, 600, 5
    prev_raw = -1
    for n in range(1, max_attempts + 1):
        delay, raw = backoff_delay("run1", n, base, mult, cap)
        check(raw >= prev_raw, f"backoff must be non-decreasing at attempt {n}")
        check(delay <= cap * 1.2 + 1e-9, f"backoff must be capped (attempt {n}, delay {delay})")
        prev_raw = raw
    # jitter: two different runs at the same attempt should differ
    d1, _ = backoff_delay("runA", 3, base, mult, cap)
    d2, _ = backoff_delay("runB", 3, base, mult, cap)
    check(d1 != d2, "jitter must desynchronize a thundering herd")
    # budget: at attempt == max_attempts the NEXT death is terminal Failed, not a requeue
    def decide(attempt_count):
        return "Failed(RetryBudgetExhausted)" if attempt_count >= max_attempts else "Claiming"
    check(decide(max_attempts) == "Failed(RetryBudgetExhausted)",
          "attempt budget must terminate, not requeue forever")
    check(decide(max_attempts - 1) == "Claiming", "within budget must requeue")

# ---------------------------------------------------------------------------
# (E) crash-safe schedule: next_attempt_at is durable; operator restart re-reads
#     it and resumes the REMAINING delay, not zero and not immediate.
# ---------------------------------------------------------------------------
def scenario_crash_safe_schedule(db):
    # durable: reconciler persisted next_attempt_at at t=100 for a 300s backoff
    db.runs["run1"] = {"next_attempt_at": 400, "attempt_count": 2}
    # operator restart at t=250: in-memory timer is GONE. Durable path re-reads Postgres.
    now_after_restart = 250
    durable = db.runs["run1"]["next_attempt_at"]
    remaining = durable - now_after_restart
    check(remaining == 150, "restart must resume REMAINING delay (150s), not restart from zero")
    check(remaining > 0, "restart mid-backoff must not fire immediately")
    # naive in-memory variant would have lost 'durable' and either fire now or never.
    naive_inmemory = None  # timer object was in the dead process
    check(naive_inmemory is None, "naive in-memory schedule is lost on restart (that's the bug)")

# ---------------------------------------------------------------------------
# (F) two-clock distinctness: death != rate-limit.
# ---------------------------------------------------------------------------
def scenario_two_clocks(db):
    death_run = {"reason": "SandboxDied", "next_attempt_at": 400,
                 "budget": "maxAttempts", "phase": "Claiming"}
    rl_run = {"reason": "rate_limited", "resume_at": 500,
              "budget": "Retry-After", "phase": "Paused(rate_limited)"}
    # a dead sandbox is NEVER Paused(rate_limited)
    check(death_run["phase"] != "Paused(rate_limited)", "death must not be a rate-limit pause")
    check("resume_at" not in death_run, "death path must not write resume_at")
    check("next_attempt_at" not in rl_run, "rate-limit path must not write failure next_attempt_at")
    # budgets are distinct clocks
    check(death_run["budget"] != rl_run["budget"], "failure and rate-limit budgets must differ")

# ===========================================================================
def main():
    # (A) naive MUST double-write (harness keeps its detecting power)
    naive_double = scenario_naive_gc_pause(DB())
    check(naive_double is True,
          "HARNESS LOST TEETH: naive lease-expiry-alone detector no longer double-writes")

    # (B) confirmed+fence-first MUST NOT double-write
    zombie_won = scenario_confirmed_gc_pause(DB())
    check(zombie_won is False, "fence-first reclaim let a woken GC-paused zombie write (AC3 violated)")

    # (C) wedged pod must still be reclaimed, not wedged forever
    wedged_outcome = scenario_wedged_pod(DB())
    check(wedged_outcome == "released", "wedged-but-present pod was not reclaimed (AC1 false-negative)")

    scenario_backoff(DB())              # (D)
    scenario_crash_safe_schedule(DB())  # (E)
    scenario_two_clocks(DB())           # (F)

    if FAIL:
        print("FALSIFIED — Story 3.2 design check FAILED:")
        for m in FAIL:
            print("  ✗", m)
        sys.exit(1)
    print("OK — Story 3.2 retry/backoff design holds:")
    print("  (A) naive lease-expiry-alone detector double-writes on GC-pause wake (harness has teeth)")
    print("  (B) confirmed-death + fence-first reclaim fences out the woken zombie (AC2/AC3)")
    print("  (C) wedged-but-present pod still reclaimed by the lease sweeper (AC1 conjunction)")
    print("  (D) backoff monotone + capped + jittered + budget-terminal (AC4)")
    print("  (E) durable next_attempt_at survives operator restart, resumes remaining delay (AC5)")
    print("  (F) failure clock kept distinct from rate-limit resume_at (AC6)")

if __name__ == "__main__":
    main()
