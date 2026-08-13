#!/usr/bin/env python3
"""ISI-2197 (Story 2.7) — concurrency/chaos harness for the coordination spine.

REQUIRED CI GATE (not optional) for Epic 2 closure. Exercises the four spine
invariants the PRD R10 / arch §6 rest on, each as a *differential* check (prove
a broken variant breaks first, so a PASS on the real design means something):

  (a) parallel claimers .............. no double-claim under contention  (§6.2, AC3)
      -> delegated to claim-nodouble-check.py (Story 2.2, already green); this
         harness runs it as a subprocess so the gate is one command.
  (b) crash-mid-claim ................ reclaim ONLY after lease expiry     (§6.3)
  (c) stale-holder completion ........ fenced write rejected              (§6.3)
  (d) idempotent reconcile ........... re-entrant claim/complete is a no-op(§6.4)

(b)/(c)/(d) are ordering scenarios, so they run on a deterministic virtual-clock
model of `coord.claim` — chaos here is adversarial *interleaving* (a holder that
pauses past its lease, wakes with a stale fence, re-drives a committed step), not
just parallelism, which (a) already supplies. Deterministic == non-flaky, which a
required gate must be.

Two backends, same as Story 2.2:
  * default   — in-process model, zero deps. Authoritative for the LOGIC.
  * postgres  — set DATABASE_URL (+ psycopg) to run (b)/(c)/(d) as real SQL
                against a live server. Story 2.7's CI job sets this; the
                model path always runs.

Exit 0 iff every assertion in every scenario holds. Any breach exits non-zero.
This is the smallest thing that fails if a spine invariant regresses.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEASE = 180                 # lease seconds (virtual)


# ---------------------------------------------------------------------------
# Virtual-clock model of coord.claim + the §6.2/§6.3/§6.4 guarded statements.
# A single writer per scenario step (we drive the interleaving explicitly), so
# no threads/locks are needed here — the point is guard logic under a hostile
# ORDER of operations and a controllable clock, not raw contention (that's (a)).
# ---------------------------------------------------------------------------
class Clock:
    def __init__(self): self.t = 1000
    def now(self): return self.t
    def advance(self, dt): self.t += dt


class ClaimDB:
    """One claim row per work item (PK), rewritten in place; monotonic fence.

    Models exactly the columns the guards read: holder_principal, fence_token,
    lease_expires_at. work_item.state and a per-Run dispatch marker cover the
    complete/reconcile paths. Every method IS one of the pinned SQL statements.
    """

    def __init__(self, clk, items):
        self.clk = clk
        self.work_item = {i: {"state": "open"} for i in items}
        self.claim = {i: {"holder": None, "run": None, "fence": 0,
                          "lease_expires_at": 0} for i in items}
        self.completed = {}                 # work_item_id -> run that completed it
        self.dispatched = {}                # run -> dispatched_task_id (§6.4 marker)

    # §6.2 conditional fence-bump acquire (queue-pull or reclaim; same guard).
    #   WHERE holder IS NULL OR lease_expires_at < now()
    # fence_guard=False models the F-hazard variant (no lease/holder guard) used
    # to give scenario (b) teeth: it would steal a still-live lease.
    def acquire(self, i, me, run, fence_guard=True):
        if self.work_item[i]["state"] not in ("open", "claimed"):
            return None
        c = self.claim[i]
        live = c["holder"] is not None and c["lease_expires_at"] >= self.clk.now()
        if fence_guard and live:
            return None                      # someone holds a live lease -> back off
        c["holder"], c["run"] = me, run
        c["fence"] += 1                      # monotonic, never reset
        c["lease_expires_at"] = self.clk.now() + LEASE
        self.work_item[i]["state"] = "claimed"
        return c["fence"]

    # §6.2 renew: WHERE holder=:me AND fence=:myFence AND lease_expires_at > now()
    def renew(self, i, me, my_fence):
        c = self.claim[i]
        if c["holder"] == me and c["fence"] == my_fence and c["lease_expires_at"] > self.clk.now():
            c["lease_expires_at"] = self.clk.now() + LEASE
            return True
        return False

    # §6.3 fenced state-mutating write (complete): ... AND fence_token = :myFence.
    # fence_check=False models the zombie-writer hazard (scenario (c) teeth).
    def complete(self, i, me, my_fence, fence_check=True):
        c = self.claim[i]
        if fence_check and c["fence"] != my_fence:
            return False                     # stale fence -> rejected
        if self.work_item[i]["state"] == "done":
            return False                     # §6.4: WHERE status='claimed' — no double-advance
        self.work_item[i]["state"] = "done"
        self.completed[i] = (me, my_fence)
        return True

    # §6.4 reconcile-safe re-drive of a claim: re-read; only (re)acquire if we do
    # NOT already hold it with a current fence. re_entrant=False = the naive
    # re-drive that unconditionally re-acquires (scenario (d) teeth) and so bumps
    # the fence on every reconcile pass.
    def redrive_claim(self, i, me, run, my_fence, re_entrant=True):
        c = self.claim[i]
        already = (c["holder"] == me and c["fence"] == my_fence
                   and c["lease_expires_at"] >= self.clk.now())
        if re_entrant and already:
            return my_fence                  # no-op: already hold with current fence
        return self.acquire(i, me, run)

    # §6.4 idempotent dispatch of an external-effect step: durable marker guards it.
    def dispatch_once(self, run, task_id, idempotent=True):
        if idempotent and run in self.dispatched:
            return self.dispatched[run]      # re-entered: return the recorded id
        self.dispatched[run] = task_id
        return task_id


# --------------------------- scenario (a) ----------------------------------
def scenario_a():
    print("[a] parallel claimers — no double-claim (delegates to Story 2.2 check)")
    r = subprocess.run([sys.executable, os.path.join(HERE, "claim-nodouble-check.py")],
                       env=os.environ.copy())
    assert r.returncode == 0, "claim-nodouble-check.py FAILED — (a) no-double-claim breach"
    print("[a] PASS — no-double-claim holds (see check output above).\n")


# --------------------------- scenario (b) ----------------------------------
def scenario_b():
    """crash-mid-claim: a reclaim succeeds ONLY after the lease expires."""
    print("[b] crash-mid-claim — reclaim after lease expiry (§6.3)")
    clk = Clock()
    db = ClaimDB(clk, [0])

    f1 = db.acquire(0, "H1", "run-H1")            # H1 claims
    assert f1 == 1

    # H1 crashes (stops renewing). BEFORE expiry, H2's reclaim MUST be rejected —
    # a live lease is not reclaimable. Prove the guard actually blocks here.
    clk.advance(LEASE - 1)
    assert db.acquire(0, "H2", "run-H2") is None, \
        "reclaimed a STILL-LIVE lease — §6.3 lease guard is not holding"

    # teeth: a reclaim WITHOUT the lease/holder guard would steal the live lease.
    stolen = db.acquire(0, "H2", "run-H2", fence_guard=False)
    assert stolen is not None, "harness lost teeth: unguarded acquire didn't steal"
    # (that mutated the model; rebuild for the real path)
    clk = Clock(); db = ClaimDB(clk, [0]); f1 = db.acquire(0, "H1", "run-H1")

    # AFTER expiry the same §6.2 conditional UPDATE reclaims, bumping the fence —
    # no operator action, no stuck lease.
    clk.advance(LEASE + 1)
    f2 = db.acquire(0, "H2", "run-H2")
    assert f2 == 2, f"reclaim after expiry should bump fence to 2, got {f2}"
    assert db.claim[0]["holder"] == "H2"
    # exactly one live holder at a time — H1 can no longer renew.
    assert db.renew(0, "H1", f1) is False, "zombie H1 renewed after reclaim"
    print("[b] PASS — live lease not reclaimable; expired lease reclaimed, fence 1->2.\n")
    return clk, db, f1, f2                         # hand state to (c)


# --------------------------- scenario (c) ----------------------------------
def scenario_c(state):
    """stale-holder completion: the fenced write from the old holder is rejected."""
    print("[c] stale-holder completion — fenced write rejected (§6.3)")
    clk, db, f1, f2 = state                        # H1 holds stale fence f1; H2 holds f2

    # H1 wakes after the GC pause and tries to complete with its STALE fence.
    assert db.complete(0, "H1", f1) is False, \
        "ZOMBIE WRITE ACCEPTED — stale fence completion was not rejected (§6.3 breach)"

    # teeth: without the `AND fence_token=:myFence` guard the zombie write lands.
    assert db.complete(0, "H1", f1, fence_check=False) is True, \
        "harness lost teeth: unfenced complete didn't accept the stale write"
    assert db.completed[0] == ("H1", f1)           # confirm it WAS the zombie that landed
    db.work_item[0]["state"] = "claimed"; db.completed.pop(0)   # undo the teeth probe

    # the CURRENT holder H2 completes with its live fence — accepted.
    assert db.complete(0, "H2", f2) is True, "current holder's fenced write was rejected"
    assert db.completed[0] == ("H2", f2)
    print("[c] PASS — stale-fence completion rejected; current-fence completion accepted.\n")


# --------------------------- scenario (d) ----------------------------------
def scenario_d():
    """idempotent reconcile: re-entrant claim + complete + dispatch are no-ops."""
    print("[d] idempotent reconcile — re-entrant claim/complete/dispatch safe (§6.4)")
    clk = Clock()
    db = ClaimDB(clk, [0])
    f = db.acquire(0, "H1", "run-H1")
    assert f == 1

    # re-drive the claim K times (controller crash/re-enter). It already holds the
    # item with a current fence -> every pass is a no-op, fence STAYS 1 (AC5).
    for _ in range(5):
        assert db.redrive_claim(0, "H1", "run-H1", f, re_entrant=True) == f
    assert db.claim[0]["fence"] == 1, "re-entrant re-drive bumped the fence (AC5 breach)"

    # teeth: a naive re-drive that treats every reconcile pass as a fresh reclaim
    # (unconditional acquire, ignoring both the re-read AND the §6.2 lease guard)
    # bumps the fence on every pass. NB: the §6.2 guard alone already blocks a
    # re-acquire of one's OWN live lease (acquire() returns None), so re-entrancy
    # is belt-and-suspenders on top of the guard — the AC5 re-read makes it a
    # no-op even for a re-drive that forgot the guard.
    before = db.claim[0]["fence"]
    db.acquire(0, "H1", "run-H1", fence_guard=False)
    assert db.claim[0]["fence"] == before + 1, "harness lost teeth: unguarded re-acquire didn't bump"
    db.claim[0]["fence"] = before                  # undo the teeth probe

    # re-drive complete K times -> exactly one advance (WHERE status='claimed').
    assert db.complete(0, "H1", db.claim[0]["fence"]) is True
    for _ in range(5):
        assert db.complete(0, "H1", db.claim[0]["fence"]) is False, "double-advanced a done item"

    # re-drive an external-effect dispatch K times -> one task id (durable marker).
    tid = db.dispatch_once("run-H1", "task-abc")
    for _ in range(5):
        assert db.dispatch_once("run-H1", "task-def") == tid, "re-dispatched an external effect"
    print("[d] PASS — claim/complete/dispatch are re-entrant no-ops; fence stable at 1.\n")


# ---------------------------------------------------------------------------
# Optional real-Postgres path for (b)/(c)/(d) — Story 2.7 CI job sets DATABASE_URL.
# ---------------------------------------------------------------------------
def check_postgres(dsn):
    try:
        import psycopg
    except ImportError:
        try:
            import psycopg2 as psycopg
        except ImportError:
            print("[postgres] DATABASE_URL set but no psycopg — skipping real-PG chaos.")
            return None

    ddl = """
    DROP TABLE IF EXISTS claim; DROP TABLE IF EXISTS work_item;
    CREATE TABLE work_item(id int PRIMARY KEY, state text NOT NULL);
    CREATE TABLE claim(work_item_id int PRIMARY KEY REFERENCES work_item(id),
        holder_principal text, run_id text, fence_token int NOT NULL DEFAULT 0,
        lease_expires_at timestamptz);
    INSERT INTO work_item VALUES (0,'open'); INSERT INTO claim(work_item_id) VALUES (0);
    """
    # A tiny lease so we can let it expire in real time without a long CI wait.
    acquire = """
    WITH acq AS (
      UPDATE claim SET holder_principal=%(me)s, run_id=%(run)s,
             fence_token = fence_token + 1,
             lease_expires_at = now() + interval '1 second'
       WHERE work_item_id=0
         AND (holder_principal IS NULL OR lease_expires_at < now())
      RETURNING fence_token
    ) UPDATE work_item SET state='claimed'
        WHERE id IN (SELECT 0 FROM acq) RETURNING (SELECT fence_token FROM acq);
    """
    complete = """
    UPDATE work_item SET state='done'
     WHERE id=0 AND state='claimed'
       AND %(fence)s = (SELECT fence_token FROM claim WHERE work_item_id=0)
    RETURNING id;
    """
    import time
    with psycopg.connect(dsn, autocommit=True) as c, c.cursor() as cur:
        cur.execute(ddl)

        # (b) crash-mid-claim: H1 claims; before expiry H2 is rejected; after, reclaims.
        cur.execute(acquire, {"me": "H1", "run": "run-H1"}); f1 = cur.fetchone()[0]
        assert f1 == 1
        cur.execute(acquire, {"me": "H2", "run": "run-H2"})
        # A rejected acquire updates zero rows -> RETURNING yields NO row, so
        # fetchone() is None (not a (None,) tuple). `[0]` here would TypeError on
        # the very case this asserts. Match scenario (c)'s `is None` pattern.
        assert cur.fetchone() is None, "[pg-b] reclaimed a live lease"
        time.sleep(1.2)                              # let the 1s lease expire
        cur.execute(acquire, {"me": "H2", "run": "run-H2"}); f2 = cur.fetchone()[0]
        assert f2 == 2, f"[pg-b] reclaim should bump fence to 2, got {f2}"
        print("[postgres] (b) PASS — live lease not reclaimable; expired reclaimed 1->2.")

        # (c) stale-holder completion: H1's fence f1 write rejected; H2's f2 accepted.
        cur.execute(complete, {"fence": f1}); assert cur.fetchone() is None, "[pg-c] zombie write landed"
        cur.execute(complete, {"fence": f2}); assert cur.fetchone() is not None, "[pg-c] live write rejected"
        print("[postgres] (c) PASS — stale-fence completion rejected; current accepted.")

        # (d) idempotent reconcile: re-drive complete on a done item is a no-op.
        for _ in range(3):
            cur.execute(complete, {"fence": f2})
            assert cur.fetchone() is None, "[pg-d] double-advanced a done item"
        print("[postgres] (d) PASS — re-driven complete is a no-op (WHERE state='claimed').\n")
    return True


if __name__ == "__main__":
    scenario_a()
    scenario_b_state = scenario_b()
    scenario_c(scenario_b_state)
    scenario_d()
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        check_postgres(dsn)
    else:
        print("[postgres] DATABASE_URL not set — real-PG chaos deferred to CI job.")
    print("OK — concurrency/chaos harness passed (a,b,c,d).")
    sys.exit(0)
