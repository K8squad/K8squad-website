#!/usr/bin/env python3
"""
reclaim-fencing-check.py — Story 2.4 falsification (crash-safe reclaim + fencing).

The R10 crash-recovery crux: when a lease expires, the item must be reclaimable by
a fresh holder, AND a resurrected stale holder must NOT be able to complete or clobber
the reclaimed item. Arch §6.3 (reclaim = fence-first, monotonic fence bump) + §6.2
(every state-mutating write is `… AND holder AND fence_token AND unexpired lease`).

This is a *differential* falsification, same discipline as claim-nodouble-check.py:
  1. It first proves a NAIVE reclaim (flip state=open on lease expiry, unguarded
     completion — the exact "just re-claim on timeout" hazard arch §6.3 names) DOES let
     a zombie holder clobber the reclaimed item — so the harness demonstrably has teeth.
  2. Then it proves the §6.3 design (reclaim bumps fence via the §6.2 conditional
     UPDATE; every write is fence-guarded) rejects the zombie write while still letting
     the legitimate reclaimer complete — no clobber, no lost item.

stdlib-only; `python3 reclaim-fencing-check.py`. Exit non-zero if the naive variant
STOPS clobbering (teeth lost) or the §6.3 variant EVER clobbers / loses the item /
lets a stale fence write succeed. Models Postgres row semantics in-process; the
real-Postgres promotion is Story 2.7 → chaos gates C3 (crash-mid-claim reclaim) and
C4 (stale-holder fencing) in Epic 14.2.
"""
import threading

LEASE = 10  # arbitrary lease units


class Coord:
    """In-process model of the `coord.claim` + `work_item` rows and a logical clock."""

    def __init__(self, guarded):
        # guarded=True → §6.3/§6.2 fence discipline; False → naive "flip on timeout".
        self.guarded = guarded
        self.now = 0
        self.lock = threading.Lock()  # models one row's Postgres row-lock serialization
        # one claim row per work item (F3): rewritten in place, fence monotonic
        self.claim = {"holder": None, "fence": 0, "lease_expires_at": 0}
        self.state = "open"
        self.completed_by = None  # who actually got to mark it done

    def tick(self, dt=1):
        with self.lock:
            self.now += dt

    def acquire(self, who):
        """§6.2 conditional fence-bump acquire. Returns fence on success, else None."""
        with self.lock:
            c = self.claim
            free = c["holder"] is None or c["lease_expires_at"] < self.now
            if not (self.state == "open" and free):
                return None
            c["holder"] = who
            c["fence"] = c["fence"] + 1  # monotonic, never reset (both variants bump on acquire)
            c["lease_expires_at"] = self.now + LEASE
            self.state = "claimed"
            return c["fence"]

    def sweep_reclaim(self):
        """Sweeper: lease_expires_at < now() ⇒ reclaim the item back to `open`.

        §6.3 (guarded): the holder is fenced first; releasing to `open` is safe because
        the NEXT acquire bumps the fence, so a surviving zombie is fenced at the coord
        layer. Naive: identical state flip but the completion path (below) is unguarded,
        which is where the clobber leaks in.
        """
        with self.lock:
            if self.claim["lease_expires_at"] < self.now and self.state == "claimed":
                # (guarded) durable reclaim_fenced_at marker would be written here; the
                # coord-layer fence is the fence_token bump on the next acquire.
                self.state = "open"
                self.claim["holder"] = None
                return True
            return False

    def complete(self, who, my_fence):
        """Mark the item done. §6.3: fence-guarded; naive: unguarded (the hazard)."""
        with self.lock:
            if self.guarded:
                # arch §6.3: `… WHERE holder = :me AND fence_token = :myFence AND lease > now()`
                c = self.claim
                if not (c["holder"] == who
                        and c["fence"] == my_fence
                        and c["lease_expires_at"] >= self.now):
                    return False  # stale token / not holder / lapsed → rejected write
            # naive: no guard — last writer wins, a zombie clobbers
            self.state = "done"
            self.completed_by = who
            return True

    def renew(self, who, my_fence):
        """§6.2 fence-guarded renew heartbeat. A stale holder MUST NOT resurrect its
        lease: if this ever succeeded for a zombie, the `lease >= now()` term in
        complete() would then pass and the fence would leak. Naive: unguarded (would
        let the zombie extend its own lease). Returns True iff the lease was extended."""
        with self.lock:
            if self.guarded:
                c = self.claim
                if not (c["holder"] == who
                        and c["fence"] == my_fence
                        and c["lease_expires_at"] > self.now):
                    return False  # zombie renew is a no-op (arch §6.3 renew guard)
            self.claim["lease_expires_at"] = self.now + LEASE
            return True


def run_zombie_scenario(guarded):
    """
    Forced adversarial interleaving (the zombie window §6.3 exists to close):
      1. A claims the item        (fence=1)
      2. A is GC-paused; lease expires
      3. sweeper reclaims → open; B claims (fence=2 under §6.3)
      4. B does its work
      5. A resurrects and tries to complete with its STALE fence=1
    Correct outcome: the item is completed by B, and A's stale completion is rejected.
    """
    co = Coord(guarded=guarded)
    fa = co.acquire("A")
    assert fa == 1, "A should get fence 1"

    # A goes to sleep; time passes past the lease
    for _ in range(LEASE + 2):
        co.tick()

    reclaimed = co.sweep_reclaim()
    assert reclaimed, "sweeper must reclaim an expired lease"

    fb = co.acquire("B")  # legitimate reclaimer

    # B completes its (correct) run
    b_ok = co.complete("B", fb)

    # A wakes up as a zombie and tries to complete with its stale fence
    a_ok = co.complete("A", fa)

    return {
        "fence_A": fa, "fence_B": fb,
        "B_completed": b_ok, "A_zombie_completed": a_ok,
        "completed_by": co.completed_by, "final_state": co.state,
    }


def run_same_holder_reclaim(guarded):
    """
    The interleaving the A≠B scenario MASKS: §8 `Failed ──(retryPolicy)──► Claiming`
    re-dispatches the SAME agent principal. So the reclaimer's holder identity EQUALS
    the zombie's — `holder == who` is TRUE for both, and the ONLY thing separating the
    stale run from the live one is the monotonic `fence_token` (AC4). This forces the
    fence term to be the deciding guard, not the holder term.

      1. A claims        (fence=1)
      2. A is GC-paused; lease expires
      3. sweeper reclaims → A is re-dispatched and RE-acquires as the same principal (fence=2)
      4. the stale A@fence1 tries to renew (resurrect its lease), then to complete
    Correct outcome: both stale-fence writes are rejected BY THE FENCE TERM (holder
    matches); the live A@fence2 completes exactly once.
    """
    co = Coord(guarded=guarded)
    f_stale = co.acquire("A")
    for _ in range(LEASE + 2):
        co.tick()
    co.sweep_reclaim()
    f_live = co.acquire("A")  # same principal, higher fence (retry-to-same-agent)

    stale_renew = co.renew("A", f_stale)      # zombie tries to extend its own lease
    stale_done = co.complete("A", f_stale)    # zombie tries to complete on stale fence
    live_done = co.complete("A", f_live)      # the live re-dispatch completes
    return {
        "fence_stale": f_stale, "fence_live": f_live,
        "stale_renew_ok": stale_renew, "stale_completed": stale_done,
        "live_completed": live_done, "completed_by": co.completed_by,
        "final_state": co.state,
    }


def run_reclaim_race(guarded, claimers=16):
    """Reclaim idempotency / no-lost-work: after an expiry, exactly one of N racing
    claimers wins the reclaim, the item is never lost, and fences stay unique+monotonic."""
    co = Coord(guarded=guarded)
    co.acquire("A")
    for _ in range(LEASE + 2):
        co.tick()

    fences, won = [], []
    barrier = threading.Barrier(claimers)

    def claim(name):
        barrier.wait()
        co.sweep_reclaim()  # opportunistic-claimant path (AC1): sweeper == any claimant
        f = co.acquire(name)
        if f is not None:
            fences.append(f)
            won.append(name)

    ts = [threading.Thread(target=claim, args=(f"C{i}",)) for i in range(claimers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return {"winners": len(won), "fences": sorted(fences), "state": co.state}


def main():
    print("[model] Story 2.4 crash-safe reclaim + fencing — zombie-writer falsification\n")

    naive = run_zombie_scenario(guarded=False)
    print(f"[model] NAIVE  (flip-on-timeout, unguarded complete): {naive}")
    # teeth check: the naive design MUST let the zombie clobber, else the test is toothless
    assert naive["A_zombie_completed"] is True, \
        "TEETH LOST: naive variant should let the zombie clobber — falsification is meaningless"
    assert naive["completed_by"] == "A", \
        "TEETH LOST: naive zombie should have clobbered B's completion"
    print("[model]        → zombie A clobbered B's reclaimed item (as expected; hazard is real)\n")

    guarded = run_zombie_scenario(guarded=True)
    print(f"[model] §6.3   (fence-first reclaim, guarded complete): {guarded}")
    assert guarded["fence_B"] > guarded["fence_A"], "reclaim must bump the fence (monotonic)"
    assert guarded["B_completed"] is True, "the legitimate reclaimer B must be able to complete"
    assert guarded["A_zombie_completed"] is False, \
        "FENCING BROKEN: zombie A with a stale fence must NOT be able to complete"
    assert guarded["completed_by"] == "B", "the item must be completed by its live holder, not the zombie"
    assert guarded["final_state"] == "done", "item must reach done via the live holder"
    print("[model]        → zombie A's stale-fence write REJECTED; B completed cleanly\n")

    # Same-principal reclaim: forces the FENCE term (not the holder term) to be the
    # decider — the A≠B scenario above rejects the zombie on holder mismatch, so it
    # would still pass even if the fence_token guard were absent. This arm does not.
    same = run_same_holder_reclaim(guarded=True)
    print(f"[model] §6.3   (same-principal retry, fence is the only discriminator): {same}")
    assert same["fence_live"] > same["fence_stale"], "reclaim must bump the fence (monotonic, AC4)"
    assert same["stale_renew_ok"] is False, \
        "FENCING BROKEN: a stale-fence renew must be a no-op (else it resurrects the lease)"
    assert same["stale_completed"] is False, \
        "FENCING BROKEN: same-principal stale fence must be rejected BY THE FENCE TERM"
    assert same["live_completed"] is True, "the live re-dispatch (fresh fence) must complete"
    assert same["completed_by"] == "A" and same["final_state"] == "done", \
        "item completed exactly once by the live re-dispatch"
    # teeth: prove the fence term is load-bearing here — with holder equal, dropping the
    # fence guard WOULD let the stale write land. (Guarded here mirrors the naive gap.)
    leak = run_same_holder_reclaim(guarded=False)
    assert leak["stale_completed"] is True, \
        "TEETH LOST: without the fence guard, a same-principal stale write must clobber"
    print("[model]        → same-principal stale renew+complete REJECTED by the fence term; "
          "naive leaks it (teeth)\n")

    race = run_reclaim_race(guarded=True)
    print(f"[model] reclaim race (16 claimants after expiry): {race}")
    assert race["winners"] == 1, "exactly one claimant may win the reclaim (no double-claim)"
    assert race["state"] == "claimed", "the item must be re-held, never lost"
    assert len(set(race["fences"])) == len(race["fences"]), "fences must be unique"
    print("[model]        → single winner, item re-held, fences unique\n")

    print("[model] PASS — naive detectably clobbers; §6.3 reclaim+fencing holds "
          "(no clobber, no lost item, unique monotonic fence).")


if __name__ == "__main__":
    main()
