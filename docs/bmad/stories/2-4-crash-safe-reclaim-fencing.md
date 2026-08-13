# Story 2.4: Crash-safe reclaim + fencing (the §5.3 crash-recovery path)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS IS THE CRASH-RECOVERY HALF OF THE R10 SPINE (PRD FR-B2/NFR-REL1, arch §6.3, §8).** Story 2.2
> guarantees at-most-one-holder *under contention*; this story guarantees at-most-one-holder *across a
> holder crash*. Two properties are non-negotiable: **(1)** a lease expiry returns the item to the pool so
> another Run can claim it — **no operator action, no stuck lease**; **(2)** a resurrected stale holder
> **cannot complete or clobber** the reclaimed item — it is fenced by **holder identity + a monotonic
> fence token**, so every write it attempts is rejected. A design that lets a GC-paused zombie's write land
> after its lease expired is a **silent double-execution — a correctness failure, not a bug ticket**. The
> load-bearing subtlety: **lease expiry means "renewal stopped," NOT "holder is dead"** (arch §6.3) — a
> reclaim that naively flips `state='open'` without fencing the holder first ships exactly that hazard.

## ⚠️ Wording reconciliation (issue text vs. pinned architecture)

The originating issue (ISI-2194) phrases the mechanism as *"`checkouts` row with `lease_expires_at <
now()` … fenced by `holder` identity + monotonic `lease_epoch`"* and *"the item returns to `state='open'`
and is claimable."* Three reconciliations against the **pinned** architecture (arch is authoritative where
they differ, same discipline as Story 2.2's F3 note):

1. **`checkouts` row → `claim` row.** Pinned after F3 (arch §6.1): exactly **one claim row per work item**
   (`claim.work_item_id` PK, table name `claim`), rewritten in place. "checkout" in prose = a row in the
   `claim` table.
2. **`lease_epoch` → `fence_token`.** There is **no separate `lease_epoch` column.** The
   **`fence_token`** on the `claim` row **is** the monotonic lease epoch — it is bumped `+1` on **every**
   acquire and reclaim, **never reset, never reused** across the item's lifetime (arch §6.1/§6.2).
   "Monotonic `lease_epoch`" in the issue text = the pinned monotonic `fence_token`. Fencing is on
   **`(holder_principal, fence_token)`**, not a distinct epoch counter.
3. **"item returns to `state='open'`" is the END STATE, not the mechanism.** Reclaim is **NOT** a naive
   `UPDATE work_item SET state='open'` on lease expiry. Per arch §6.3 it is an **ordered, fence-first,
   crash-safe protocol** (fence the holder → confirm → release the claim). The item *does* end up `open`
   and claimable — but only *after* the holder is fenced. The AC's one-liner elides the ordering that is
   the entire correctness content of this story; **AC2/AC3 below restore it.**

**"This IS the §5.3 crash-recovery path" (issue + epics 04 §Epic-2 row 2.4):** the arch section numbering
drifted — current arch **§5.3 is the AgentRuntime CRD**. The crash-recovery path this story implements is
**§8 "Failure/resume"** (`Failed ──(retryPolicy, backoff)──► Claiming`, which "runs the §6.3 reclaim
protocol — fence the pod first, release the claim second") **+ §6.3** (the reclaim protocol itself). Epic
3.2 (retry/resume) is the direct consumer. Where this story says "§6.3" it means the reclaim protocol;
"§8" means the Run state machine that triggers it.

## Story

As **the coordination spine**,
I want **a crashed or GC-paused holder's work item to be reclaimed back to the pool — after the holder is fenced — so another Run can claim it, and I want the stale holder to be structurally unable to complete or clobber the reclaimed item**,
so that **a Run crash never strands work and never causes a silent double-execution (arch §6.3/§8, FR-B2, NFR-REL1, R10 crash-recovery).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-B2** (at-most-one-holder checkout/claim/lease), **NFR-REL1**
  (crash-safe recovery, nothing lost), **R10** (the coordination spine is the correctness-critical risk;
  concurrency and crash-recovery are *tested, not assumed*).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§6.1** — data model. `claim(work_item_id PK, holder_principal, run_id, fence_token,
    lease_expires_at, acquired_at, renewed_at)`; one active row per item, rewritten in place;
    `fence_token` monotonic for the item's lifetime.
  - **§6.2** — the conditional acquire (reused verbatim here as the reclaim's *release* step — it is the
    same `WHERE (holder_principal IS NULL OR lease_expires_at < now())` guard that makes an expired lease
    re-acquirable) and the fence-guarded renew (`… AND holder AND fence_token AND lease > now()` — a
    zombie's renewal is a no-op).
  - **§6.3** — **the home section. Lease/liveness/fencing + the 3-step reclaim protocol** (below).
  - **§6.4** — reconcile-safe re-entrancy (the reclaim must be safe to re-drive after a reconciler crash
    mid-reclaim — see AC5; `reclaim_fenced_at` durable marker).
  - **§8** — Run state machine; "Failure/resume" is what *triggers* the §6.3 reclaim (lease non-renewal +
    pod status → reclaim → retry with backoff). Kill (FR-A6) also releases claims.
  - **§9.4** — the per-Project workspace PVC a GC-paused zombie can still be mounting (why pod-kill is
    step 1, not an afterthought).
- **Review findings this story must honor (from the ISI-2135/F1–F4 spine remediation):**
  - **F1 (pinned, the crux):** **fence the holder BEFORE releasing the claim.** Lease expiry ≠ holder
    dead. Never treat `lease_expires_at < now()` alone as reclaim permission. See AC2.
  - **F2/F3 (fencing):** the fence-token column and unique-active-claim constraint must exist; every
    state-mutating write is `… AND fence_token = :myFence`. A missing fence column is the "F2 trap"
    (arch §15/epics 14.2) — the chaos gate fails fast if it is absent.
- **Depends on:** **Story 2.1** (the `coord` schema — `claim`/`work_item` tables, `fence_token`,
  `lease_expires_at`) and **Story 2.2** (the §6.2 conditional acquire this story's release step reuses).
  If 2.1/2.2 are not landed, wire against arch §6.1/§6.2 and gate the DB-backed test on them.
- **Blocks / is consumed by:** **3.2** (Run retry/resume — the direct consumer: "releases the work-item
  checkout for reclaim, requeues with backoff"), **2.10** (rate-limit re-route reuses the fenced
  release), **2.12** (approval gate releases the fenced checkout), and **2.7 / Epic 14.2** (the
  concurrency/chaos harness that promotes this story's falsification to a **required real-Postgres CI
  gate** — chaos gates **C3 crash-mid-claim reclaim**, **C4 stale-holder fencing**, **C5
  zombie-writer-vs-PVC**).

## The pinned §6.3 reclaim protocol (authoritative)

Lease expiry means **"renewal stopped," not "holder is dead."** A GC-paused or network-partitioned Run is
alive at the resource layer and keeps mutating the workspace PVC (§9.4), memory (§7), and git. Reclaim is
therefore an **ordered, crash-safe sequence — NOT a state flip**:

```
sweeper / opportunistic claimant finds:  claim.lease_expires_at < now()  AND  work_item.state = 'claimed'
   │
   ├─ 1. FENCE THE HOLDER (before releasing the claim — F1)
   │      • cordon + terminate the holder's sandbox pod (SIGTERM → SIGKILL after a short grace)
   │      • flip its egress NetworkPolicy to deny-all
   │        → pod death revokes the PVC mount (workspace writes stop) and egress (git push/model calls stop)
   │      • write a DURABLE `reclaim_fenced_at` marker on the Run  ← re-entry point on reconciler crash (§6.4)
   │
   ├─ 2. CONFIRM FENCING (never release an unconfirmed-unfenced claim)
   │      • wait for pod deletion, bounded timeout
   │      • on timeout → ESCALATE (node cordon + operator alert), do NOT release
   │
   └─ 3. RELEASE THE CLAIM  ← only now is the row acquirable
          • the §6.2 conditional acquire runs: it matches because `lease_expires_at < now()`,
            and it BUMPS fence_token (+1) → even a holder that somehow survived step 1 is fenced
            at the COORDINATION layer. Item is now claimed by the new holder (or back to `open`
            for the next queue-pull, per the caller).
```

**Defense in depth — resource-layer fence checks (arch §6.3).** The pod-kill ordering is the *primary*
fence; the state-mutating services *additionally* reject stale tokens, so a fencing failure degrades to
**rejected writes, never silent corruption**:

- **Renew** (§6.2): `… WHERE holder AND fence_token = :myFence AND lease_expires_at > now()` — a zombie
  cannot resurrect its lease (the `lease > now()` term fails, and once reclaimed the `holder`/`fence`
  terms fail).
- **Complete / status / comment** (§6.5): every state-mutating write carries `(work_item_id, fence_token)`
  and is guarded the same way — a stale token's write is a **no-op, not a clobber**.
- **Memory write** (§7): validated against `coord.claim` inside the write txn; stale token rejected.
- **Artifact registration** (§6.1): a fence-guarded `coord.artifact` upsert; a zombie's orphaned blob is
  unreferenced and GC-able.
- **Residual (named, not hidden):** a zombie that survives fencing with valid git credentials could still
  push to the *external* remote — outside the fence perimeter. Mitigation: per-Run-scoped git credentials
  revoked at sandbox teardown (§11); the R10 threat model records this residual explicitly.

**Reclaim trigger — sweeper OR opportunistic claimant (AC1).** Reclaim is not owned by a single privileged
sweeper. Any claimant that encounters an item whose lease has expired can drive the §6.3 protocol (the
§6.2 conditional acquire *is* the release step, and it self-serializes on the Postgres row lock). A
periodic sweeper is the liveness backstop that guarantees an item with **no** contending claimant is still
eventually reclaimed (so a drained-but-crashed item never sits stuck). Both paths run the **identical**
fence-first sequence — the sweeper has no shortcut that skips step 1.

## Acceptance Criteria

**AC1 — an expired lease is reclaimable, no operator action.**
Given a `claim` row with `lease_expires_at < now()` on a `claimed` work item, When the sweeper (a periodic
liveness backstop) **or** an opportunistic claimant runs, Then the item is reclaimed and becomes claimable
by another Run — **with no operator intervention and no stuck lease**. And the reclaim self-serializes on
the Postgres row lock (the §6.2 conditional acquire is the release step), so a sweeper and a claimant
racing the same expired item produce **exactly one** reclaim, never two.

**AC2 — reclaim is fence-first and ordered (F1 — the crux), never a naive state flip.**
Given a lease expiry, When the item is reclaimed, Then the reconciler **fences the holder before releasing
the claim**: (1) cordon + terminate the holder's sandbox pod and deny-all its egress; (2) confirm pod
deletion within a bounded timeout — on timeout **escalate (node cordon + operator alert), do not release**;
(3) only then run the §6.2 conditional acquire, which **bumps `fence_token`**. And `lease_expires_at <
now()` **alone is never treated as reclaim permission** — the reconciler does not skip to step 3.

**AC3 — a resurrected stale holder cannot complete or clobber (the R10 crash-recovery crux).**
Given a holder A that was GC-paused past its lease and whose item was reclaimed (by B, at a higher
`fence_token`), When A resurrects and attempts to **complete, transition, comment, register an artifact, or
renew**, Then **every one of those writes is rejected** because each is guarded by `… AND holder_principal
= :me AND fence_token = :myFence AND lease_expires_at > now()` and A holds a **stale** fence. And the
legitimate holder B — with the current fence — **can** complete. And the item is completed **exactly once,
by B**, never double-executed by A's stale run. **Verified by
`docs/bmad/spikes/bench/reclaim-fencing-check.py`** (below), a *differential* check: it first proves a
naive flip-on-timeout + unguarded-complete design **does** let the zombie clobber, then proves the §6.3
design does not.

**AC4 — the fence token is monotonic across reclaim (never reset, never reused).**
Given N reclaims of the same work item over its lifetime, When each reclaim's acquire runs, Then
`fence_token` is strictly increasing (`+1` each acquire/reclaim) and **no fence value is ever reused** —
so a token from any prior holder is always strictly less than the current one, which is what makes "stale"
detectable by the `fence_token = :myFence` guard. A reclaim **never** resets the fence to 0.

**AC5 — the reclaim is crash-safe / re-entrant (§6.4).**
Given a reconciler that crashes **mid-reclaim**, When it re-enters, Then the durable `reclaim_fenced_at`
marker on the Run tells it which step it reached — it re-enters at the right step (re-confirm fencing or
proceed to release) rather than restarting from scratch or releasing an unfenced claim. And re-driving a
reclaim on an item that was **already** reclaimed (lease now fresh under a new holder) is a **no-op** — the
§6.2 conditional acquire matches nothing (lease not expired), so the sweeper cannot bump the fence out from
under a live holder or double-reclaim.

**AC6 — no lost work.**
Given an item whose holder crashed with **no** contending claimant, When the periodic sweeper runs, Then
the item is still eventually reclaimed and returns to `open` (or is re-held) — a crashed holder on a
drained backlog never leaves the item permanently stuck. And a reclaim never deletes or orphans the work
item, its comments, or its audit trail (those are append-only, §6.5).

## Runnable check (the falsification, already green)

`docs/bmad/spikes/bench/reclaim-fencing-check.py` — stdlib-only, `python3` it directly:

```
[model] NAIVE  (flip-on-timeout, unguarded complete): … 'A_zombie_completed': True, 'completed_by': 'A' …
[model]        → zombie A clobbered B's reclaimed item (as expected; hazard is real)
[model] §6.3   (fence-first reclaim, guarded complete): … 'A_zombie_completed': False, 'completed_by': 'B' …
[model]        → zombie A's stale-fence write REJECTED; B completed cleanly
[model] reclaim race (16 claimants after expiry): {'winners': 1, 'fences': [2], 'state': 'claimed'}
[model] PASS — naive detectably clobbers; §6.3 reclaim+fencing holds …
```

- **Default (no deps):** an in-process model of the `coord.claim`/`work_item` rows with a logical clock,
  driving the **forced zombie interleaving** the fence exists to close: A claims (fence 1) → A is
  GC-paused past its lease → sweeper reclaims → B claims (fence 2) → A resurrects and tries to complete
  with its **stale** fence 1. It first proves the **naive** design (flip `state='open'` on expiry +
  **unguarded** completion — the exact "just re-claim on timeout" hazard arch §6.3 names) lets A's zombie
  write **clobber** B's completion — so the harness has honest teeth — then proves the **§6.3** design
  (reclaim bumps the fence; every write is `… AND holder AND fence AND lease > now()`) **rejects** A's
  stale write while B completes cleanly. It exits non-zero if the naive variant *stops* clobbering (teeth
  lost) or the §6.3 variant *ever* clobbers / loses the item / lets a stale-fence write land. A 16-claimant
  **reclaim race** asserts exactly one winner (no double-claim on the reclaim path) and unique fences.
- **Real Postgres (Story 2.7 / Epic 14.2 CI path):** the promotion wires this against a live server as
  chaos gates **C3 (crash-mid-claim reclaim)**, **C4 (stale-holder fencing)**, and **C5
  (zombie-writer-vs-PVC)** — the `-race` required status check Epic 2 cannot close without.
  **Coverage note:** the model check guards the *reclaim + fencing logic* (AC1–AC4/AC6), which is the R10
  crash-recovery crux. The **pod-kill/egress-deny ordering (AC2 steps 1–2)** and the **`reclaim_fenced_at`
  re-entry (AC5)** are pinned in prose here and exercised against a real kubelet + reconciler in 14.2
  (C5); the model asserts the coordination-layer consequence (a bumped fence rejects the stale write),
  which holds **regardless** of whether the pod-kill fully succeeded — that is the defense-in-depth point.
- **Why differential:** a happy-path "the sweeper reclaimed it" demo passes even with a broken design that
  never fences the holder — the zombie just never happened to wake in that run. Proving the harness
  *catches* a real clobber first is what makes the §6.3 PASS meaningful.

## Out of scope (owned elsewhere)

- **Claim acquire + its two entry shapes** (2.2), **renew heartbeat** (2.3), **outbox relay** (2.5),
  **cross-dispatch reconcile-safety** (2.6), the **required CI concurrency/chaos gate** (2.7 → Epic 14.2
  C1–C7). This story ships the **reclaim protocol** (fence-first, ordered, crash-safe), the **fencing
  guard** on state-mutating writes, and the falsification that a resurrected stale holder cannot clobber a
  reclaimed item.
