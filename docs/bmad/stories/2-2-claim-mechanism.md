# Story 2.2: Claim mechanism (SKIP LOCKED, single-transaction) — the R10 core

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS IS THE SINGLE MOST CORRECTNESS-CRITICAL STORY IN v1 (PRD R10, arch §6, §15).** At-most-one-holder
> under contention is the load-bearing invariant of the entire coordination spine — every other Epic-2/3
> story (claim/renew/reclaim/complete, Run reconcile, warm-pool bind) assumes it. Two properties are
> non-negotiable: **(1)** a claim is **one atomic transaction** — SKIP-LOCKED pop of an open item →
> conditional fence-bump acquire → `state='claimed'` — with **no application-level lock** anywhere;
> **(2)** at-most-one-holder rests on **two independent mechanisms** (the `FOR UPDATE SKIP LOCKED` row
> lock *and* the conditional `WHERE holder IS NULL OR lease_expired` CAS), so a defect in one is still
> caught by the other. A design that double-claims — even once, even under a rare interleaving — is a
> **correctness failure, not a bug ticket**. Read AC1 and AC3 literally.

## ⚠️ Wording reconciliation (issue text vs. pinned architecture)

The originating issue (ISI-2192) phrases the mechanism as *"SELECT FOR UPDATE SKIP LOCKED LIMIT 1 →
**insert checkouts row** → state=claimed"*. That reflects an **earlier draft**. The architecture was
**pinned** after review finding **F3** (arch §6.1, "Cardinality (F3, pinned)"): there is **exactly one
claim row per work item** (`claim.work_item_id` is the **PK**, table name `claim`, not `checkouts`),
the row is **rewritten in place** on every acquire/reclaim, and `fence_token` is **monotonically
increasing across the item's lifetime** (never reset, never reused). There is **no append-only insert**
in the custody path — that was the exact F3 hazard (two live leases via a stale row). This story
implements the **pinned** design; where the issue text and arch §6.1/§6.2 differ, **arch is
authoritative**. The word "checkout" in prose = a row in the `claim` table.

## Story

As an **agent (Run) that needs work**,
I want **to claim an open work item in one atomic transaction so at most one Run ever holds it, even when many Runs claim simultaneously**,
so that **the coordination spine hands each unit of work to exactly one holder with a fresh fencing token — with no double-claim, no stuck item, and no distributed or application-level lock (arch §6.2, R10).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-B2** (at-most-one-holder checkout/claim/lease), **R10** (the
  coordination spine is the correctness-critical risk; concurrency is *tested, not assumed*).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§6.1** — data model. `claim(work_item_id PK, holder_principal, run_id, fence_token, lease_expires_at, acquired_at, renewed_at)`; **one active row per work item**, rewritten in place; `fence_token` monotonic for the item's lifetime. `work_item(id, project_id, team_id, parent_id, title, state, …)`.
  - **§6.2** — the claim SQL (below) and the renew SQL. *"A row returned ⇒ claim acquired with a fresh, monotonically increasing fence token. No row ⇒ someone holds a live lease; the caller backs off. This is atomic in one statement — no double-claim under contention without any distributed lock."*
  - **§6.3** — lease/liveness/fencing (Story 2.4 reclaim; this story just emits the fence token every mutation later checks).
  - **§6.4** — reconcile-safe re-entrancy (Story 2.6; the claim must be safe to re-drive — see AC5).
  - **§6.6** — the acquire also writes a `claim.acquired` domain event to the transactional outbox **in the same transaction** (Story 2.5 owns the outbox relay; this story writes the row).
- **Review findings this story must honor:**
  - **F3 (pinned):** one claim row per item, PK, in-place rewrite, monotonic fence. **No insert-per-claim.** (Reconciliation above.)
  - **F5 (ownership model — resolved here):** §6.2 has *two* claim entry shapes; both funnel into the **same** fence-guarded acquire. See AC2. This story pins which is which so "SKIP-LOCKED returns empty" is never confused with "already claimed."
- **Depends on:** **Story 2.1** (the `coord` schema + `work_item`/`claim` tables and the eager-or-lazy `claim` row must exist). If 2.1 is not yet landed, wire against the schema in `docs/bmad/03-architecture.md` §6.1 and gate the DB-backed test on it.
- **Blocks / is consumed by:** **2.3** (renew), **2.4** (reclaim — reuses the exact §6.2 `WHERE` guard), **2.5** (outbox), **2.6** (reconcile-safe), **2.7** (the concurrency/chaos CI harness that promotes this story's model check to a required real-Postgres gate), **Epic 3** Run reconcile (`ClaimingSandbox`).

## The pinned §6.2 claim (authoritative)

A claim is **one transaction** with three effects, in order:

```sql
-- ONE transaction. No application-level lock. No distributed lock.
BEGIN;

-- (1) Work-pull: pop ONE open item, hold its row lock to COMMIT, skip contended rows.
--     FOR UPDATE SKIP LOCKED is what makes N concurrent claimers dequeue DISTINCT items
--     without blocking each other (throughput + distinctness).
WITH picked AS (
  SELECT id FROM work_item
   WHERE project_id = :proj AND state = 'open'
   ORDER BY created_at            -- FIFO; swap for a priority/order key as needed
   FOR UPDATE SKIP LOCKED
   LIMIT 1
),
-- (2) Conditional fence-bump acquire: the CAS guard. Even on the reclaim/lease-expiry
--     path (Story 2.4) this rejects a second acquirer. Belt-and-suspenders to (1).
acq AS (
  UPDATE claim
     SET holder_principal = :me, run_id = :run,
         fence_token      = fence_token + 1,           -- monotonic, never reset
         lease_expires_at = now() + :lease,
         acquired_at = now(), renewed_at = now()
   WHERE work_item_id IN (SELECT id FROM picked)
     AND (holder_principal IS NULL OR lease_expires_at < now())
  RETURNING work_item_id, fence_token
),
-- (3) Transition the item.
done AS (
  UPDATE work_item SET state = 'claimed'
   WHERE id IN (SELECT work_item_id FROM acq)
)
SELECT work_item_id, fence_token FROM acq;   -- 1 row ⇒ claimed(fence); 0 rows ⇒ nothing to claim

COMMIT;
```

**Row returned ⇒ this Run holds `work_item_id` with fence `fence_token`.** Zero rows ⇒ no open,
unlocked, acquirable item was available this pass; the caller checks whether any `open` items remain
(none → backlog drained; some → all momentarily locked → retry). **No row is ever double-returned to two
transactions**, because the `FOR UPDATE SKIP LOCKED` row lock on the picked `work_item` is held until
`COMMIT` and the conditional `UPDATE claim` rejects any acquire of a live-leased row.

**Claim-row lifecycle (F3):** the `claim` row exists **one-per-work-item**. Two equivalent
implementations — pick the idempotent one:
- **eager:** create `claim(work_item_id, holder=NULL, fence_token=0)` in the same txn that inserts the
  `work_item` (Story 2.1). The acquire is then a pure `UPDATE` (above).
- **lazy (recommended):** collapse create-or-acquire into `INSERT INTO claim(work_item_id, …) VALUES (…)
  ON CONFLICT (work_item_id) DO UPDATE SET … WHERE claim.holder_principal IS NULL OR
  claim.lease_expires_at < now()`. Idempotent, re-entrant (§6.4), and keeps `work_item` creation
  decoupled from claim creation. Either way the row is **rewritten in place**, never appended.

## Acceptance Criteria

**AC1 — one atomic transaction, no application-level lock.**
Given an open work item, When a Run claims it, Then the SKIP-LOCKED pop, the conditional fence-bump
acquire, and the `state='claimed'` transition all commit in **one** database transaction (the §6.2
statement above). And the acquire takes **no** application-level lock, no advisory lock, and no
distributed lock — the only lock is Postgres's own row lock from `FOR UPDATE SKIP LOCKED`, released at
commit. And a returned row carries a **fresh, monotonically increasing `fence_token`** for that item.

**AC2 — the two claim entry shapes, both fence-guarded (F5 resolved).**
Given the two ways a Run reaches a claim, When either is used, Then both funnel through the identical
conditional acquire (2) + transition (3), and are distinguishable by intent, not by safety:
- **Queue-pull (backlog, the AC of this story):** `… WHERE state='open' … FOR UPDATE SKIP LOCKED LIMIT 1`
  — N claimers dequeue **distinct** items. **Empty result ⇒ "nothing available/all locked"**, not an error.
- **Targeted (scheduler assigned `Run.spec.workItemRef`, §5.2):** `… WHERE id = :ref AND state='open'
  FOR UPDATE` (**no** `SKIP LOCKED`; serialize on that one row). **Empty result ⇒ "that specific item is
  no longer open (already claimed / gone)"** — a first-class, distinct outcome the caller must handle
  (not retried as if skipped). This is the F5 disambiguation: queue-empty ≠ target-taken.

**AC3 — no double-claim across the whole concurrency harness (the R10 crux).**
Given N open items and M concurrent claimers, When all claim simultaneously, Then **every item is held
by exactly one Run** and **no item is double-claimed anywhere across the entire run of the harness**. And
every open item is eventually claimed (**no lost work** — SKIP LOCKED skips *contended* rows, never
*loses* them). And each claimed item's returned fence tokens are unique (no two Runs receive the same
`(work_item_id, fence_token)`). **Verified by `docs/bmad/spikes/bench/claim-nodouble-check.py`** (see
"Runnable check" below), which is a *differential* test: it first proves a naive check-then-act claim
(no row lock, no CAS) **does** double-claim — so the harness demonstrably has the power to detect one —
then proves the §6.2 design does **not**. Story 2.7 promotes this to a **required CI gate** run against a
**real Postgres** (`DATABASE_URL`), not the in-process model.

**AC4 — empty-result semantics are explicit, never a silent stall.**
Given a claim attempt that returns zero rows, When the caller handles it, Then it distinguishes
"backlog drained" (no `open` items remain for the scope) from "all open items momentarily locked by
peers" (retry with jitter) from "targeted item no longer open" (AC2). And a claimer loop **terminates**
when the backlog is drained rather than spinning forever (bounded retry / drained check).

**AC5 — the acquire is reconcile-safe (re-entrant, §6.4).**
Given a controller that crashes and re-drives a claim, When it re-enters, Then re-reading `claim`
(holder + fence) tells it whether **it already holds the item with a current fence** — in which case it
does **not** re-acquire or bump the fence again. A Run only ever holds one live fence per item; a
re-drive is a no-op on an item it already holds. (Full re-entrancy across dispatch is Story 2.6; this
story must not make the acquire *un*-re-entrant.)

**AC6 — the acquire writes its audit + domain-event rows in the same transaction (§6.5/§6.6).**
Given a successful acquire, When it commits, Then the coordination audit row (principal + timestamp,
§6.5) and the `claim.acquired` outbox row (§6.6) are written **in the same transaction** as effects
(1)–(3) — so a claim is atomically observable, and a crash can never leave a claimed item with no audit
trail or a phantom event with no claim. (The outbox **relay** is Story 2.5; this story writes the row.)

## Runnable check (the falsification, already green)

`docs/bmad/spikes/bench/claim-nodouble-check.py` — stdlib-only, `python3` it directly:

```
[model] N=200 items, M=32 claimers, real threads
[model] NAIVE (no row lock, no CAS): 200 item(s) double-claimed
[model] §6.2  (FOR UPDATE SKIP LOCKED): 0 double-claimed, 200/200 items claimed
[model] PASS — naive detectably breaks; §6.2 holds no-double-claim.
```

- **Default (no deps):** an in-process model of Postgres row locking driven by **real threads**. It
  removes both protections in the naive variant to keep its detecting power honest, then proves the
  §6.2 variant (SKIP-LOCKED row lock held to commit **+** conditional CAS) holds no-double-claim and
  claims all 200 items. Exits non-zero if the naive variant *stops* double-claiming (teeth lost) or the
  §6.2 variant *ever* double-claims / loses an item / returns a non-positive fence.
- **Real Postgres (Story 2.7 CI path):** set `DATABASE_URL` and install `psycopg`; the harness runs the
  **exact §6.2 SQL** (the CTE above) across M connection-backed claimers and asserts the same
  invariants against a live server. This is the authoritative gate; the model check guards the *logic*.
- **Why differential:** a happy-path "it claimed each item once" demo can pass with a broken design
  under a lucky interleaving. Proving the harness *catches* a real double-claim first is what makes the
  §6.2 PASS meaningful.

## Out of scope (owned elsewhere)

- **Renew** (2.3), **reclaim + pod-fencing** (2.4, §6.3), **outbox relay** (2.5), **cross-dispatch
  reconcile-safety** (2.6), the **CI concurrency/chaos gate** (2.7). This story ships the claim acquire,
  its two entry shapes, and the falsification that no interleaving double-claims.
