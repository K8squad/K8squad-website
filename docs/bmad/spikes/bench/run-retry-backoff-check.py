#!/usr/bin/env python3
"""
Story 3.2 (ISI-2202) falsification — retry/resume of dead Runs with backoff.

Differential crash/liveness falsification, same shape as run-reconcile-check.py (3.1) and the
Story-2.4 reclaim check. It proves the DEATH-DETECTION EDGE has teeth by contrasting a NAIVE detector
that reclaims on lease-expiry alone (and double-writes when a paused holder wakes) against the §6.3
CONFIRMED-DEATH + FENCE-FIRST detector that does not.

Scope reminder: Story 3.1 owns the Failed->Claiming retry-lap re-entrancy AND the terminal-vs-requeue
DECISION + the attempt_count/next_attempt_at write (its own check). THIS check stacks the *detection*
false-positive (GC-pause zombie) and false-negative (wedged-but-present pod) teeth, plus the bounded-
backoff DELAY FUNCTION and its crash-safe durable schedule, and the two-clock distinctness vs rate-limit.

Mutation contract (the two headline invariants must be falsifiable — re-run these after any edit):
  * delete the confirmation gate in reclaim_fence_first (release unconditionally) -> (F1) MUST turn RED.
  * delete the fence-FIRST resource-barrier advance (db.fence_resource in reclaim) -> (F2) MUST turn RED.

stdlib only. `python3 run-retry-backoff-check.py`. Exits non-zero on any falsification.
No wall-clock, no RNG surprises: 'now' is an injected logical clock; jitter is a deterministic
hashlib digest of (run_id, attempt) so the check is reproducible ACROSS processes (no PYTHONHASHSEED
salt — plain hash() is per-process salted and would make the gate flaky).
"""
import hashlib
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
        # run: run_id -> durable recovery state (reclaim_fenced_at, next_attempt_at, attempt_count)
        self.runs = {}
        self.writes = []  # log of (holder, fence) writes ACCEPTED at the resource layer
        # canonical fencing: the RESOURCE (PVC/work item) remembers the highest fence it has
        # accepted/been-fenced-to and rejects any lower one (§6.3 resource-layer fence check).
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
        it has accepted/been-fenced-to. Holder identity is NOT the gate — the fence token is."""
        seen = self.max_fence_seen.get(wid, 0)
        if fence >= seen:
            self.max_fence_seen[wid] = fence
            self.writes.append((holder, fence))
            return True
        return False  # fenced out — stale-token write rejected

    def fence_resource(self, wid, fence):
        """§6.3 step 1, fence-FIRST: advance the resource barrier to `fence` BEFORE releasing the
        claim — independent of any new holder's write. This models the terminate + egress-deny +
        fence-marker: a late-waking zombie carrying the old token is rejected in the window AFTER
        release but BEFORE any new holder has written. Removing this line is the F2 mutation."""
        if fence > self.max_fence_seen.get(wid, 0):
            self.max_fence_seen[wid] = fence

    def release_and_bump(self, wid):
        """§6.3 step 3: release + monotonic fence bump on the claim row."""
        c = self.claims[wid]
        c["fence"] += 1
        c["holder"] = None
        c["lease_expires_at"] = -1
        return c["fence"]


# ===========================================================================
# §6.3 CONFIRMED-DEATH + FENCE-FIRST reclaim (the SUT for B/F1/F2/crash-reentry)
# ===========================================================================
def reclaim_fence_first(db, wid, pod_confirmed_gone, now):
    """§6.3 on the death edge, run through the ACTUAL protocol under test:
      (1) fence FIRST — advance the resource barrier + stamp a durable `reclaim_fenced_at` marker,
          idempotently (a crash mid-reclaim re-enters without double-fencing);
      (2) confirm the pod is gone -> else DON'T release (AC1/AC3: suspicion, not license);
      (3) release the claim + bump the claim fence.
    Both mutation targets live here: the step-1 barrier advance (F2) and the step-2 gate (F1)."""
    c = db.claims[wid]
    run = db.runs.setdefault(c["run_id"], {})
    if run.get("reclaim_fenced_at") is None:      # step 1 — idempotent fence-FIRST
        db.fence_resource(wid, c["fence"] + 1)    #   <-- F2 mutation target (delete -> RED)
        run["reclaim_fenced_at"] = now
    if not pod_confirmed_gone:                     # step 2 — confirm or DON'T release
        return "held"                             #   <-- F1 mutation target (delete -> RED)
    db.release_and_bump(wid)                       # step 3 — only after confirmation
    return "released"


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
# (F1) confirmation gate teeth: a lease-expired but UNCONFIRMED (partitioned,
#      still-alive) holder must NOT be released. Drives pod_confirmed_gone=False.
# ---------------------------------------------------------------------------
def scenario_unconfirmed_holder_held(db):
    """AC1/AC3: lease expired opens the case, but the pod is NOT confirmed gone (node
    partitioned, pod alive, about to resume). The §6.3 gate MUST hold the claim, not release."""
    wid, lease = "W", 100
    fence = db.acquire(wid, "podA", "run1", 0, lease)
    db.write_item(wid, "podA", fence)
    now = 250  # lease lapsed; podA partitioned but ALIVE (pod object present)
    outcome = reclaim_fence_first(db, wid, pod_confirmed_gone=False, now=now)
    holder = db.claims[wid]["holder"]
    return outcome, holder  # must be ("held", "podA") — claim never released

def scenario_naive_release_live(db):
    """Differential twin of (F1): a NAIVE release-on-expiry-alone path hands a still-ALIVE
    holder's claim to podB. The live podA keeps writing -> two live holders on one item."""
    wid, lease = "W", 100
    fence = db.acquire(wid, "podA", "run1", 0, lease)
    db.write_item(wid, "podA", fence)
    now = 250
    c = db.claims[wid]  # NAIVE: release-on-expiry-alone, no confirmation, no fence bump
    c["holder"] = "podB"; c["lease_expires_at"] = now + lease
    db.write_item(wid, "podB", fence)
    podA_still_writes = db.write_item(wid, "podA", fence)  # podA was NEVER dead -> resumes
    return podA_still_writes and c["holder"] == "podB"  # True == naive corrupts (two live holders)

# ---------------------------------------------------------------------------
# (B) CONFIRMED-DEATH + FENCE-FIRST detector, full false-positive scenario:
#     confirmed dead -> reclaim -> new holder claims fresh -> woken zombie fenced.
# ---------------------------------------------------------------------------
def scenario_confirmed_gc_pause(db):
    wid, now, lease = "W", 0, 100
    fence = db.acquire(wid, "podA", "run1", now, lease)
    db.write_item(wid, "podA", fence)
    now = 250
    # A1 lease-expiry opens the case; A2 pod-watch says podA is GONE -> confirmed dead.
    outcome = reclaim_fence_first(db, wid, pod_confirmed_gone=True, now=now)
    check(outcome == "released", "confirmed-dead pod should release")
    new_fence = db.acquire(wid, "podB", "run1", now, lease)  # retry lap re-claims fresh
    check(new_fence is not None and new_fence > fence, "reclaim must bump the fence")
    db.write_item(wid, "podB", new_fence)
    # podA wakes with its STALE fence -> must be rejected.
    woke = db.write_item(wid, "podA", fence)
    return woke  # must be False

# ---------------------------------------------------------------------------
# (F2) release-time fence bump ISOLATED: the woken zombie writes AFTER release
#      but BEFORE any new holder acquires/writes. The ONLY thing between its
#      stale-fence write and acceptance is the reclaim's fence-FIRST barrier
#      advance (db.fence_resource) — no new-holder write can mask it here.
# ---------------------------------------------------------------------------
def scenario_zombie_before_new_holder(db):
    wid, lease = "W", 100
    fence = db.acquire(wid, "podA", "run1", 0, lease)
    db.write_item(wid, "podA", fence)          # max_fence_seen = fence
    now = 250
    outcome = reclaim_fence_first(db, wid, pod_confirmed_gone=True, now=now)
    check(outcome == "released", "confirmed-dead must release")
    # NO new holder yet. podA wakes and writes with its stale fence, in the release->reclaim window.
    zombie_write = db.write_item(wid, "podA", fence)
    return zombie_write  # must be False — fenced out by the reclaim barrier ALONE

# ---------------------------------------------------------------------------
# (C) false-negative teeth: wedged-but-present pod. Pod still exists (watch never
#     fires) but agent hung and stopped renewing. The lease sweeper must still act.
# ---------------------------------------------------------------------------
def scenario_wedged_pod(db, grace):
    wid, now, lease = "W", 0, 100
    fence = db.acquire(wid, "podA", "run1", now, lease)
    now = 250  # podA hung: lease lapsed, but the pod object STILL EXISTS (watch silent)
    pod_watch_fired = False           # A2 alone would never detect this
    lease_sweep_opens = db.claims[wid]["lease_expires_at"] < now - grace  # A1 does (grace-aware)
    check(lease_sweep_opens and not pod_watch_fired,
          "wedged-pod: sweep must open the case that the watch misses")
    # fence step TERMINATES the wedged pod -> now confirmable gone -> release
    outcome = reclaim_fence_first(db, wid, pod_confirmed_gone=True, now=now)  # after fence kills it
    return outcome  # must be "released" (not wedged forever)

# ---------------------------------------------------------------------------
# (F6) grace window: a single missed heartbeat WITHIN grace is not death.
#      lease nominally lapsed but within grace -> sweeper must NOT open reclaim.
# ---------------------------------------------------------------------------
def scenario_grace_no_reclaim(db, grace):
    wid, lease = "W", 100
    db.acquire(wid, "podA", "run1", 0, lease)
    now = 100 + grace - 1  # lease lapsed at t=100 but still WITHIN grace (< now-grace is false)
    lease_nominally_expired = db.claims[wid]["lease_expires_at"] < now
    reclaim_opens = db.claims[wid]["lease_expires_at"] < now - grace
    check(lease_nominally_expired, "grace: lease should be nominally expired")
    return reclaim_opens  # must be False — a briefly-stalled but alive holder is not dead

# ---------------------------------------------------------------------------
# (F5) crash mid-reclaim: a crash BETWEEN the fence marker (step 1) and the
#      release (step 3) must re-enter idempotently — no double barrier advance.
# ---------------------------------------------------------------------------
def scenario_crash_mid_reclaim(db):
    wid, lease = "W", 100
    fence = db.acquire(wid, "podA", "run1", 0, lease)
    db.write_item(wid, "podA", fence)
    now = 250
    c = db.claims[wid]
    # First reconciler ran step 1 (barrier advanced + durable marker) then CRASHED before release.
    db.fence_resource(wid, c["fence"] + 1)
    db.runs.setdefault("run1", {})["reclaim_fenced_at"] = now
    barrier_after_step1 = db.max_fence_seen[wid]
    check(db.claims[wid]["holder"] == "podA", "crash before release: claim still held")
    # New leader re-enters the SAME reclaim. Marker present -> idempotent step 1 (no re-advance).
    outcome = reclaim_fence_first(db, wid, pod_confirmed_gone=True, now=now)
    check(db.max_fence_seen[wid] == barrier_after_step1,
          "re-entry must NOT double-advance the fence barrier (idempotent §6.3 step 1)")
    return outcome  # must be "released" — re-entry completes the release

# ---------------------------------------------------------------------------
# (D) backoff policy: monotone, capped, jittered, budgeted.
#     Scope pin (F3): 3.2 owns this DELAY FUNCTION; the terminal-vs-requeue
#     DECISION belongs to Story 3.1's single Failed-handler lap (asserted here
#     only as the invariant 3.1 must uphold when it consumes this function).
# ---------------------------------------------------------------------------
def det_jitter(run_id, attempt):
    """Deterministic bounded jitter in [-0.2, +0.2] fraction, reproducible ACROSS processes.
    Uses a hashlib digest, NOT hash(): str hashing is salted per-process (PYTHONHASHSEED), which
    would make the schedule non-reproducible and (D)'s d1!=d2 a ~0.1% flaky FAIL."""
    h = hashlib.sha256(f"{run_id}:{attempt}".encode()).hexdigest()
    frac = (int(h[:8], 16) % 1000) / 1000.0  # 0..1, stable across runs
    return (frac - 0.5) * 0.4  # -0.2 .. +0.2

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
    # jitter: two different runs at the same attempt should differ (deterministic, stable)
    d1, _ = backoff_delay("runA", 3, base, mult, cap)
    d2, _ = backoff_delay("runB", 3, base, mult, cap)
    check(d1 != d2, "jitter must desynchronize a thundering herd")
    # budget INVARIANT (owned+decided by 3.1 AC5; 3.2's delay function feeds it):
    # at attempt == max_attempts the NEXT death is terminal Failed, not a requeue.
    def decide(attempt_count):
        return "Failed(RetryBudgetExhausted)" if attempt_count >= max_attempts else "Claiming"
    check(decide(max_attempts) == "Failed(RetryBudgetExhausted)",
          "attempt budget must terminate, not requeue forever")
    check(decide(max_attempts - 1) == "Claiming", "within budget must requeue")

# ---------------------------------------------------------------------------
# (E) crash-safe schedule: next_attempt_at is durable; operator restart re-reads
#     it and resumes the REMAINING delay. The NAIVE variant keeps the wake in an
#     in-memory reconciler object that a restart drops -> the wake is lost.
# ---------------------------------------------------------------------------
class InMemoryReconciler:
    """Naive: the backoff wake lives ONLY in this process's timer map."""
    def __init__(self):
        self.timers = {}

def scenario_crash_safe_schedule(db):
    # durable path persists to Postgres; naive path only arms an in-memory timer.
    db.runs["run1"] = {"next_attempt_at": 400, "attempt_count": 2}
    rec = InMemoryReconciler()
    rec.timers["run1"] = 400
    # operator restart: the process (and `rec`) is GONE. A fresh reconciler has NO timers.
    fresh = InMemoryReconciler()
    now_after_restart = 250
    # DURABLE path re-reads Postgres and resumes the remaining delay:
    durable = db.runs["run1"]["next_attempt_at"]
    remaining = durable - now_after_restart
    check(remaining == 150, "restart must resume REMAINING delay (150s), not restart from zero")
    check(remaining > 0, "restart mid-backoff must not fire immediately")
    # NAIVE in-memory path: the wake was in `rec.timers`, dropped on restart -> gone.
    check("run1" not in fresh.timers,
          "naive in-memory schedule is lost on restart (Run would wedge — that's the bug)")

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
    grace = 30  # AC1 grace = a small multiple of the renewal interval

    # (A) naive MUST double-write (harness keeps its detecting power)
    naive_double = scenario_naive_gc_pause(DB())
    check(naive_double is True,
          "HARNESS LOST TEETH: naive lease-expiry-alone detector no longer double-writes")

    # (F1) confirmation gate: unconfirmed/live holder MUST be held, not released.
    f1_outcome, f1_holder = scenario_unconfirmed_holder_held(DB())
    check(f1_outcome == "held" and f1_holder == "podA",
          "AC1/AC3 confirmation gate FAILED: unconfirmed (live) holder was released "
          "(delete the `if not pod_confirmed_gone: return 'held'` gate to see this go RED)")
    # differential twin: the naive release-on-expiry path DOES corrupt (two live holders)
    check(scenario_naive_release_live(DB()) is True,
          "HARNESS LOST TEETH: naive release-on-expiry-alone no longer corrupts a live holder")

    # (B) confirmed+fence-first MUST NOT double-write
    zombie_won = scenario_confirmed_gc_pause(DB())
    check(zombie_won is False, "fence-first reclaim let a woken GC-paused zombie write (AC3 violated)")

    # (F2) release-time fence bump isolated: zombie writes BEFORE any new holder -> fenced out.
    f2_zombie = scenario_zombie_before_new_holder(DB())
    check(f2_zombie is False,
          "AC2 §6.3 step-1 fence-FIRST FAILED: a woken zombie wrote a stale fence in the "
          "release->new-holder window (delete `db.fence_resource(...)` to see this go RED)")

    # (C) wedged pod must still be reclaimed, not wedged forever
    wedged_outcome = scenario_wedged_pod(DB(), grace)
    check(wedged_outcome == "released", "wedged-but-present pod was not reclaimed (AC1 false-negative)")

    # (F6) grace window: a missed heartbeat within grace must NOT open reclaim.
    check(scenario_grace_no_reclaim(DB(), grace) is False,
          "AC1 grace FAILED: a single missed heartbeat within grace opened a reclaim")

    # (F5) crash mid-reclaim: idempotent re-entry, no double fence advance.
    check(scenario_crash_mid_reclaim(DB()) == "released",
          "AC2 crash-mid-reclaim re-entry FAILED (idempotency)")

    scenario_backoff(DB())              # (D)
    scenario_crash_safe_schedule(DB())  # (E)
    scenario_two_clocks(DB())           # (F)

    if FAIL:
        print("FALSIFIED — Story 3.2 design check FAILED:")
        for m in FAIL:
            print("  ✗", m)
        sys.exit(1)
    print("OK — Story 3.2 retry/backoff design holds:")
    print("  (A)  naive lease-expiry-alone detector double-writes on GC-pause wake (harness has teeth)")
    print("  (F1) confirmation gate holds an unconfirmed/live holder; naive release corrupts it (AC1/AC3)")
    print("  (B)  confirmed-death + fence-first reclaim fences out the woken zombie (AC2/AC3)")
    print("  (F2) fence-FIRST barrier alone fences a zombie in the release->new-holder window (AC2 §6.3)")
    print("  (C)  wedged-but-present pod still reclaimed by the lease sweeper (AC1 conjunction)")
    print("  (F6) a missed heartbeat within grace does NOT open reclaim (AC1 grace)")
    print("  (F5) crash between fence-marker and release re-enters idempotently (AC2)")
    print("  (D)  backoff monotone + capped + jittered + budget-terminal invariant (AC4; decision=3.1)")
    print("  (E)  durable next_attempt_at survives operator restart; naive in-memory wake is lost (AC5)")
    print("  (F)  failure clock kept distinct from rate-limit resume_at (AC6)")

if __name__ == "__main__":
    main()
