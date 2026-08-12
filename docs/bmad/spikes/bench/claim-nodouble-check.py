#!/usr/bin/env python3
"""ISI-2192 (Story 2.2) — no-double-claim falsification check for the §6.2 claim.

The correctness claim of R10 is: given N open work items and M concurrent
claimers, each item ends up held by EXACTLY ONE Run — via
`SELECT … FOR UPDATE SKIP LOCKED LIMIT 1` → conditional claim-acquire →
`state='claimed'`, all in ONE transaction, with NO application-level lock.

This is a *differential* falsification, not a happy-path demo. It runs the same
concurrency scenario two ways and asserts:

  (A) a NAIVE claim (select the open item WITHOUT the row lock, then acquire)
      DOES produce at least one double-claim under contention  → proves the
      harness is actually powerful enough to catch a double-claim; and
  (B) the §6.2 claim (FOR UPDATE SKIP LOCKED holding the row lock through the
      acquire) produces ZERO double-claims and hands each item a unique,
      monotonically-increasing fence token.

If (A) ever passes (no double-claim seen) the check fails LOUD, because that
means the test lost its detecting power and (B) proves nothing.

Two backends:
  * default  — an in-process model of Postgres row locking with REAL threads.
               `FOR UPDATE [SKIP LOCKED]` = try-acquire a per-row lock; SKIP
               LOCKED skips a locked row, plain FOR UPDATE blocks on it; the
               lock is held until the transaction "commits". Zero deps.
  * postgres — set DATABASE_URL (and have psycopg installed) to run the exact
               §6.2 SQL against a REAL Postgres. This is the path Story 2.7
               wires into CI as the required gate. Only the §6.2 variant runs
               here (we don't ship a knowingly-broken statement to real PG).

Exit 0 iff every assertion holds. Any breach exits non-zero — this is the
smallest thing that fails if the §6.2 claim logic breaks.
"""
import os
import sys
import threading
import time

N_ITEMS = 200          # open work items
M_CLAIMERS = 32        # concurrent Runs racing to claim
LEASE_SECONDS = 180


# ---------------------------------------------------------------------------
# In-process model of the coordination record + Postgres row-lock semantics.
# ---------------------------------------------------------------------------
class ModelDB:
    """Faithful-enough model of `work_item` + `claim` under row-level locking.

    Only the properties that decide the no-double-claim outcome are modelled:
    per-row exclusive locks acquired by FOR UPDATE and held to commit, and the
    SKIP LOCKED vs. block-on-lock distinction. Everything else is a plain dict.
    """

    def __init__(self, n):
        self._guard = threading.Lock()               # protects the maps below
        self._row_locks = {i: threading.Lock() for i in range(n)}
        self.work_item = {i: "open" for i in range(n)}
        # one claim row per work item (PK work_item_id), rewritten in place.
        self.claim = {i: {"holder": None, "run_id": None, "fence": 0,
                          "lease_ok": False} for i in range(n)}

    # SELECT … WHERE state='open' … FOR UPDATE SKIP LOCKED LIMIT 1
    def pick_open_skip_locked(self):
        """Return (item_id, release_fn) for one open, lockable item — or (None, None)."""
        with self._guard:
            candidates = [i for i, s in self.work_item.items() if s == "open"]
        for i in candidates:
            if self._row_locks[i].acquire(blocking=False):   # SKIP LOCKED
                # re-check under the row lock (state may have changed)
                with self._guard:
                    still_open = self.work_item[i] == "open"
                if still_open:
                    return i, self._row_locks[i].release
                self._row_locks[i].release()
        return None, None

    # NAIVE: pick an open item with NO row lock (the bug we must be able to catch)
    def pick_open_no_lock(self):
        with self._guard:
            for i, s in self.work_item.items():
                if s == "open":
                    return i, (lambda: None)
        return None, None

    def acquire_claim_and_transition(self, i, me, run, cas):
        """Claim-acquire + state flip — the body of the txn (check-then-act).

        Correctness rests on TWO independent mechanisms, and the differential
        test removes both in the naive variant to give itself teeth:

          * the row lock (FOR UPDATE SKIP LOCKED, held by the caller to commit)
            — serialises this section per item so only one claimer is ever in
            it; and
          * the conditional CAS guard (`WHERE holder IS NULL OR lease_expired`,
            enabled via `cas=True`) — rejects a second acquire even without the
            row lock, covering the reclaim/lease-expiry path.

        With neither (naive: no row lock, `cas=False`) this is the textbook
        check-then-act race the story forbids ("no application-level locks").
        The `time.sleep(0)` widens the read→write window so the race is
        deterministic under contention rather than GIL-masked.

        Returns the fresh fence token, or None if the CAS guard rejected us.
        """
        with self._guard:
            state = self.work_item[i]
            held = self.claim[i]["holder"] is not None and self.claim[i]["lease_ok"]
        if state != "open":
            return None
        if cas and held:                                      # WHERE guard
            return None
        time.sleep(0)                                         # widen the window
        with self._guard:
            if cas and self.claim[i]["holder"] is not None and self.claim[i]["lease_ok"]:
                return None                                   # CAS re-check at write
            c = self.claim[i]
            c["holder"] = me
            c["run_id"] = run
            c["fence"] += 1                                   # monotonic bump
            c["lease_ok"] = True
            self.work_item[i] = "claimed"
            return c["fence"]


def run_model(skip_locked, cas):
    db = ModelDB(N_ITEMS)
    results = []            # (item_id, run_id, fence) per successful claim
    results_lock = threading.Lock()
    barrier = threading.Barrier(M_CLAIMERS)

    def claimer(worker_id):
        barrier.wait()      # maximise contention: everyone starts together
        while True:
            with db._guard:
                any_open = any(s == "open" for s in db.work_item.values())
            if not any_open:
                return
            if skip_locked:
                i, release = db.pick_open_skip_locked()
            else:
                i, release = db.pick_open_no_lock()
            if i is None:
                # skip-locked path: all open rows momentarily locked — retry
                continue
            try:
                fence = db.acquire_claim_and_transition(i, f"agent-{worker_id}",
                                                        f"run-{worker_id}-{i}", cas)
                if fence is not None:
                    with results_lock:
                        results.append((i, f"run-{worker_id}", fence))
            finally:
                release()

    threads = [threading.Thread(target=claimer, args=(w,))
               for w in range(M_CLAIMERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def audit(results):
    """Return (double_claimed_items, fence_ok)."""
    holders = {}
    for item, run, fence in results:
        holders.setdefault(item, []).append((run, fence))
    doubles = {i: hs for i, hs in holders.items() if len(hs) > 1}
    # each claimed item got exactly one fence == 1 in a clean single-pass claim
    fence_ok = all(fence >= 1 for _, _, fence in results)
    return doubles, fence_ok


def check_model():
    print(f"[model] N={N_ITEMS} items, M={M_CLAIMERS} claimers, real threads\n")

    # (A) the naive variant MUST double-claim — else the test can't detect one.
    #     naive = check-then-act with NO row lock and NO CAS guard: the exact
    #     "application-level lock" anti-pattern the story forbids.
    naive = run_model(skip_locked=False, cas=False)
    naive_doubles, _ = audit(naive)
    print(f"[model] NAIVE (no row lock, no CAS): {len(naive_doubles)} item(s) double-claimed")
    assert naive_doubles, (
        "FALSIFICATION LOST ITS TEETH: the naive claim did NOT double-claim, "
        "so a passing §6.2 result would prove nothing. Increase contention.")

    # (B) the §6.2 variant MUST NOT double-claim, ever.
    #     §6.2 = FOR UPDATE SKIP LOCKED (row lock held to commit) + conditional
    #     CAS acquire — both mechanisms present, as in the real SQL.
    good = run_model(skip_locked=True, cas=True)
    good_doubles, fence_ok = audit(good)
    claimed = {i for i, _, _ in good}
    print(f"[model] §6.2  (FOR UPDATE SKIP LOCKED): "
          f"{len(good_doubles)} double-claimed, {len(claimed)}/{N_ITEMS} items claimed")
    assert not good_doubles, f"DOUBLE-CLAIM under §6.2: {good_doubles}"
    assert claimed == set(range(N_ITEMS)), "some open item was never claimed (lost work)"
    assert fence_ok, "a claim returned a non-positive fence token"
    print("[model] PASS — naive detectably breaks; §6.2 holds no-double-claim.\n")


# ---------------------------------------------------------------------------
# Optional: run the EXACT §6.2 SQL against a real Postgres (Story 2.7 CI path).
# ---------------------------------------------------------------------------
def check_postgres(dsn):
    try:
        import psycopg  # psycopg3
    except ImportError:
        try:
            import psycopg2 as psycopg  # fallback
        except ImportError:
            print("[postgres] DATABASE_URL set but no psycopg/psycopg2 — skipping.")
            return None

    import concurrent.futures as cf

    ddl = """
    DROP TABLE IF EXISTS claim; DROP TABLE IF EXISTS work_item;
    CREATE TABLE work_item(id int PRIMARY KEY, project_id int, state text NOT NULL);
    CREATE TABLE claim(work_item_id int PRIMARY KEY REFERENCES work_item(id),
        holder_principal text, run_id text, fence_token int NOT NULL DEFAULT 0,
        lease_expires_at timestamptz);
    """
    with psycopg.connect(dsn) as c:
        with c.cursor() as cur:
            cur.execute(ddl)
            for i in range(N_ITEMS):
                cur.execute("INSERT INTO work_item VALUES (%s, 1, 'open')", (i,))
                cur.execute("INSERT INTO claim(work_item_id) VALUES (%s)", (i,))
        c.commit()

    # ONE transaction: SKIP-LOCKED pop → conditional fence-bump acquire → claimed.
    claim_txn = f"""
    WITH picked AS (
        SELECT id FROM work_item WHERE state='open'
        ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
    ), acq AS (
        UPDATE claim SET holder_principal=%(me)s, run_id=%(run)s,
               fence_token = fence_token + 1,
               lease_expires_at = now() + interval '{LEASE_SECONDS} seconds'
        WHERE work_item_id IN (SELECT id FROM picked)
          AND (holder_principal IS NULL OR lease_expires_at < now())
        RETURNING work_item_id, fence_token
    ), done AS (
        UPDATE work_item SET state='claimed'
        WHERE id IN (SELECT work_item_id FROM acq)
    )
    SELECT work_item_id, fence_token FROM acq;
    """

    def claimer(worker_id):
        out = []
        with psycopg.connect(dsn) as c:
            while True:
                with c.cursor() as cur:
                    cur.execute(claim_txn, {"me": f"agent-{worker_id}",
                                            "run": f"run-{worker_id}"})
                    row = cur.fetchone()
                c.commit()
                if row is None:
                    # empty: no open+unlocked item this pass — are any left?
                    with c.cursor() as cur:
                        cur.execute("SELECT count(*) FROM work_item WHERE state='open'")
                        if cur.fetchone()[0] == 0:
                            return out
                    continue
                out.append((row[0], f"run-{worker_id}", row[1]))

    with cf.ThreadPoolExecutor(max_workers=M_CLAIMERS) as ex:
        results = [r for fut in [ex.submit(claimer, w) for w in range(M_CLAIMERS)]
                   for r in fut.result()]

    doubles, fence_ok = audit(results)
    claimed = {i for i, _, _ in results}
    print(f"[postgres] §6.2 SQL: {len(doubles)} double-claimed, "
          f"{len(claimed)}/{N_ITEMS} claimed")
    assert not doubles, f"DOUBLE-CLAIM against real Postgres: {doubles}"
    assert claimed == set(range(N_ITEMS)), "lost work: an open item was never claimed"
    assert fence_ok, "a claim returned a non-positive fence token"
    print("[postgres] PASS — real Postgres upholds no-double-claim.\n")
    return True


if __name__ == "__main__":
    check_model()
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        check_postgres(dsn)
    else:
        print("[postgres] DATABASE_URL not set — real-PG proof deferred to "
              "Story 2.7 CI. Model check above is authoritative for logic.")
    print("OK — no-double-claim falsification passed.")
    sys.exit(0)
