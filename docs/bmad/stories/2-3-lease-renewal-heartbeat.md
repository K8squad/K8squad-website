# Story 2.3: Lease renewal (heartbeat) — extend, never resurrect, never borrow

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **This story owns one guarded UPDATE and the three terms that guard it.** A held item's lease is
> extended by its holder's heartbeat via a conditional `UPDATE claim … WHERE holder AND fence AND
> lease > now()` (arch §6.2). Renewal is a **lease extension, not a custody event**: it never bumps the
> fence, never changes the holder, never touches `work_item.state`. The load-bearing property is what
> renewal **refuses**: a non-holder cannot borrow a live lease, a stale-fence zombie cannot extend the
> live holder's lease, and a holder whose lease **already lapsed cannot self-resurrect it**. That last
> refusal is the interlock that makes Story 2.4's fence-first reclaim safe — drop it and a GC-paused
> holder races the sweeper and revives a lease the reclaimer is about to take.

## ⚠️ Wording reconciliation (issue text vs. pinned architecture)

The originating issue (ISI-2193) phrases the guard as a **single term**: *"UPDATE guarded by `holder =
run_id`. Non-holder renewal rejected."* That is **necessary but not sufficient.** The architecture was
**pinned** (arch §6.2 renew, and review finding **F3** folded at arch r7, ISI-2135) to a **three-term**
guard:

```sql
… WHERE work_item_id = :wi
  AND holder_principal = :me        -- (a) holder identity — the issue's one term
  AND fence_token      = :myFence   -- (b) the current fence — closes the same-principal zombie
  AND lease_expires_at > now();     -- (c) the lease is still live — no self-resurrection
```

Where the issue text and arch §6.2 differ, **arch is authoritative**. The single `holder = run_id` term
alone leaks **two** distinct hazards this story must close (each is a teeth arm in the falsification):
- **(b) stale fence:** §8 `Failed ──(retryPolicy)──► Claiming` can re-dispatch after a reclaim so the
  **holder principal matches** but the fence has moved on. Holder-only would let the stale run extend the
  **live** holder's lease. The monotonic `fence_token` is the unforgeable discriminator (mirrors Story
  2.4's same-principal reclaim arm — fence is the sole decider when holder is equal).
- **(c) lapsed lease:** a holder-only guard lets a paused holder that woke **after** its lease expired
  push `lease_expires_at` back into the future — resurrecting a lease the sweeper (Story 2.4/§6.3) is
  about to reclaim. `AND lease_expires_at > now()` makes an expired lease **unrenewable**; the only path
  back is a fresh §6.2 acquire (a fence bump), never a renew.

## Story

As **the agent (Run) that currently holds a work item**,
I want **to extend my lease with a heartbeat that succeeds only while I am still the live, current-fence
holder**,
so that **long work keeps its claim without ever letting a non-holder, a stale-fence zombie, or my own
lapsed self borrow or resurrect a lease — renewal extends custody, it never grants or revives it (arch
§6.2/§6.3, R10).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-B2** (at-most-one-holder checkout/claim/**lease**), **R10** (the
  coordination spine is the correctness-critical risk; concurrency is *tested, not assumed*).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§6.1** — `claim(work_item_id PK, holder_principal, run_id, fence_token, lease_expires_at,
    acquired_at, renewed_at)`; **one active row per work item**, rewritten in place; `fence_token`
    monotonic for the item's lifetime. Renewal moves `lease_expires_at`/`renewed_at` **only**.
  - **§6.2** — the **renew SQL is authoritative** (quoted above). *"A holder can renew only its own live
    claim with its own current fence… Renewal is therefore authority-unambiguous — the F3 ambiguity
    (stale-row renewal succeeding under a newer claim) cannot occur."*
  - **§6.3** — lease/liveness/fencing. Lease TTL is a **tunable** (default **60s renew / 180s expiry**) —
    a knob, not a structural choice. Reclaim treats `lease_expires_at < now()` as "renewal stopped," not
    "holder dead" — which is exactly why **(c)** must forbid self-resurrection (Story 2.4 owns reclaim).
  - **§6.5 / §6.6** — a successful `claim.renewed` is a low-volume audit event (ADR-040) + an outbox
    domain event, written **in the same UPDATE transaction**; a **rejected** renew writes **zero** (no
    phantom-heartbeat trail).
- **Review findings this story must honor:**
  - **F3 (pinned, arch r7):** the renewal guard is `holder AND fence AND unexpired lease`. A stale-row /
    stale-fence renewal must be a **no-op**. This story's falsification proves each of the three terms is
    independently load-bearing.
- **Depends on:** **Story 2.1** (the `coord.claim` row + `coord.audit_log`/`outbox` tables) and **Story
  2.2** (the acquire that mints the `fence_token` a renew re-presents). If 2.1/2.2 are not yet landed,
  wire against §6.1/§6.2; the DB-backed test is gated on them via Story 2.7.
- **Blocks / is consumed by:** **Story 2.4** (reclaim relies on (c): an expired lease is unrenewable, so
  fence-first reclaim never races a self-renew), **Epic 3** Run reconcile (the reconciler owns the
  heartbeat **cadence** — *when* to call renew; this story owns *what one renew does*), **Story 2.7** (the
  concurrency/chaos CI harness promotes this model check to a required real-Postgres gate).

## The pinned §6.2 renew (authoritative)

Renewal is **one guarded UPDATE** — no SELECT-then-write, no application lock, no fence bump:

```sql
-- renew: guarded by holder AND fence AND unexpired lease — a zombie's renewal is a no-op (F3).
-- Extends the lease in place; fence_token, holder_principal, run_id, work_item.state UNCHANGED.
UPDATE claim
   SET lease_expires_at = now() + :lease,   -- push the lease out; the ONLY custody-adjacent field moved
       renewed_at       = now()             -- heartbeat timestamp (telemetry / last-seen)
 WHERE work_item_id     = :wi
   AND holder_principal = :me               -- (a) I am the holder            → non-holder rejected
   AND fence_token      = :myFence          -- (b) with the CURRENT fence     → stale-fence zombie rejected
   AND lease_expires_at > now()             -- (c) and the lease is STILL live → no self-resurrection
RETURNING fence_token;                       -- 1 row ⇒ renewed (fence UNCHANGED); 0 rows ⇒ rejected, back off
```

**One row returned ⇒ the lease was extended and `fence_token` is returned *unchanged*** (a renew must
never change it — that is the claim/reclaim path, §6.2 acquire / Story 2.2/2.4). **Zero rows ⇒ the renew
was rejected** by at least one guard term; the caller must treat this as **"I no longer hold this item"**
(a non-holder, a superseded fence, or a lapsed lease) and stop — it must **not** retry the renew as if it
were a transient miss, and it must **not** fall back to re-acquiring without going through the §6.2 claim
(which is the only path that legitimately bumps the fence).

**Renew is not claim (the invariant that keeps the two paths from blurring):**

| | acquire (§6.2, Story 2.2) | reclaim (§6.3, Story 2.4) | **renew (this story)** |
|---|---|---|---|
| `fence_token` | **+1** (monotonic) | **+1** (monotonic) | **unchanged** |
| `holder_principal`/`run_id` | set to acquirer | set to reclaimer | **unchanged** |
| `work_item.state` | → `claimed` | (reclaim → open → re-claim) | **unchanged** |
| guard | `holder IS NULL OR lease < now()` | same (post-fence) | `holder = :me AND fence = :myFence AND lease > now()` |
| on an **expired** lease | **acquirable** | reclaimable | **rejected** (no resurrection) |

## Acceptance Criteria

**AC1 — a live holder's heartbeat extends the lease, in one guarded UPDATE, with no fence bump.**
Given a work item held by Run *me* at fence *f* with a lease that has not yet expired, When *me* renews
with `(:me, :myFence=f)`, Then the single §6.2 `UPDATE claim … RETURNING fence_token` commits, `lease_expires_at`
is pushed to `now() + :lease`, `renewed_at` is updated, and the returned `fence_token` is **still `f`**
(renewal never bumps the fence). And `holder_principal`, `run_id`, and `work_item.state` are **unchanged**.
No application-level, advisory, or distributed lock is taken.

**AC2 — a non-holder renewal is rejected (the issue's explicit AC; guard term (a)).**
Given an item held by Run *A* at fence *f*, When a different principal *B* (or *A*'s superseded run) calls
renew, Then the `holder_principal = :me` term fails, **zero rows** are returned, *A*'s lease is **unchanged**,
and *B* learns it does not hold the item. *B* cannot extend, shorten, or observe *A*'s lease via renew.

**AC3 — a stale-fence renewal is rejected even when the principal matches (guard term (b)).**
Given *A* re-dispatched after a reclaim so the **live** holder is *A* at fence *f₂* while a paused zombie
still carries *A*'s **stale** fence *f₁* (`f₁ < f₂`), When the zombie renews with `(:A, :myFence=f₁)`, Then
the `fence_token = :myFence` term fails and the renew is a **no-op** — the zombie cannot extend the **live**
holder's lease. The monotonic fence is the sole discriminator here (holder is equal), exactly as in Story
2.4's same-principal reclaim arm. And the live *A@f₂* renews normally.

**AC4 — a lapsed-lease self-renewal is rejected: an expired lease is unrenewable (guard term (c), the
Story-2.4 interlock).**
Given *A* holds the item at fence *f* but its lease has already expired (`lease_expires_at < now()`) and it
has **not yet been reclaimed**, When *A* wakes and renews with its **own current** `(:A, :myFence=f)`, Then
the `lease_expires_at > now()` term fails and the renew is a **no-op** — *A* cannot resurrect its own expired
lease. The only path back to holding the item is a fresh §6.2 **acquire** (which bumps the fence). This is
what lets §6.3 fence-first reclaim treat expiry as reclaimable without racing a self-renew.

**AC5 — renew is not a claim: idempotent, re-entrant, and a clean no-op on an item it no longer holds.**
Given a controller that re-drives a heartbeat, When it renews an item it **still** holds, Then repeated
renews are idempotent — each only pushes `lease_expires_at`/`renewed_at`, never the fence, holder, or state
(N renews ⇒ same fence as after the acquire). And When it renews an item that has since been **reclaimed**
by another holder (or itself at a higher fence), Then the renew returns zero rows and mutates **nothing** —
a re-drive on a lost item is a safe no-op, never a partial resurrection.

**AC6 — audit/outbox on success only; a rejected heartbeat leaves no trail (§6.5/§6.6, ADR-040).**
Given a **successful** renew, When it commits, Then a `claim.renewed` row is appended to `coord.audit_log`
(low-volume coordination audit — principal + fence + timestamp, ADR-040) **and** a `claim.renewed` outbox
event is written **in the same UPDATE transaction** (§6.6). Given a **rejected** renew (AC2/AC3/AC4), When
it returns zero rows, Then **zero** audit and **zero** outbox rows are written — a heartbeat that did not
land leaves no phantom trail (the reject path must be audit-silent, mirroring the SELECT-FROM-acq pattern
in Story 2.2). *(The outbox relay is Story 2.5; this story writes the row on the success branch only.)*

**AC7 — heartbeat cadence is out of scope (a controller concern, Epic 3).**
Given this story specifies **the effect of one renewal**, When cadence is discussed, Then *how often* to
renew, *when* to start/stop, backoff, and the renew/expiry TTLs (default 60s/180s, §6.3) are **owned by the
Run reconciler (Epic 3)** and are **not** in scope here. This story guarantees only that **one** renew, given
`(:me, :myFence)`, has exactly the guarded effect above.

## Runnable check (the falsification, already green)

`docs/bmad/spikes/bench/renew-heartbeat-check.py` — stdlib-only, `python3` it directly:

```
[model] Story 2.3 lease renewal (heartbeat) — three-guard falsification

[model] happy path (live holder renews):  full → lease extended, fence UNCHANGED (1→1), state=claimed
[model] (a) non-holder renew:   none→LEAK (B extended A's lease)   holder→reject   full→reject
[model] (b) stale-fence renew:  holder→LEAK (zombie extended live) fence→reject    full→reject
[model] (c) lapsed self-renew:  holder_fence→LEAK (self-resurrect) full→reject (expired ⇒ unrenewable)
[model] not-a-claim:  N renews keep fence=1; renew after reclaim = no-op (0 mutations)
[model] audit:  success ⇒ 1 audit + 1 outbox; every rejected renew ⇒ 0 + 0
[model] PASS — each of the three guard terms independently load-bearing; renew extends, never resurrects.
```

- **Default (no deps):** an in-process model of the `coord.claim` row + a logical clock, with the renew
  guard parameterized over four modes so **each guard term is proven load-bearing on its own**:
  - `none` — unguarded (`WHERE work_item_id` only): a non-holder renews → **must LEAK** (proves term (a)).
  - `holder` — the **issue's single term** (`holder = run_id`): a stale-fence zombie extends the live
    holder's lease → **must LEAK** (proves term (b) is needed *beyond* the issue's guard).
  - `holder_fence` — holder + fence, **no `lease > now()`**: a lapsed holder self-resurrects → **must LEAK**
    (proves term (c) is needed beyond even holder+fence).
  - `full` — arch §6.2 three-term guard: **rejects all three** hazards while letting the live current-fence
    holder renew.
  The check exits non-zero if any weaker mode **stops** leaking its hazard (teeth lost) or if `full` **ever**
  leaks, bumps the fence on renew, mutates on a rejected renew, or writes an audit/outbox row on a reject.
- **Why differential (per-term):** a happy-path "the holder renewed and the lease moved" demo passes even
  for a holder-only guard — it never exercises the stale-fence or lapsed-lease hazard. Proving that each
  weaker guard **detectably** leaks its specific hazard, and that only the full three-term guard closes all
  three, is what makes the `full` PASS meaningful. This mirrors the "each mechanism independently" arms in
  `claim-nodouble-check.py` (2.2) and the same-principal teeth arm in `reclaim-fencing-check.py` (2.4).
- **Real Postgres (Story 2.7 CI path):** set `DATABASE_URL`; the harness runs the §6.2 renew UPDATE against
  a live server across the same scenarios and asserts the guard/no-fence-bump/audit-silent-on-reject
  invariants. Promoted to the required gate in Story 2.7 (chaos case alongside C3/C4).

## Out of scope (owned elsewhere)

- **Heartbeat cadence / scheduling** (Epic 3 Run reconciler — AC7), **claim acquire** (2.2), **reclaim +
  pod-fencing** (2.4, §6.3), **outbox relay** (2.5), the **CI concurrency/chaos gate** (2.7). This story
  ships the renew UPDATE, its three-term guard, the not-a-claim invariant, and the falsification that no
  weaker guard survives.
