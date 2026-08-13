# Story 3.2: Retry/resume of dead Runs (backoff) — the liveness-failure detection edge

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE DEATH-DETECTION EDGE FEEDING THE Story-3.1 RETRY LAP (arch §8 "Failure/resume",
> FR-A5, ADR-025).** Story 3.1 built the reconcile machine and its `Failed → (retryPolicy, backoff) →
> Claiming` transition — *but only once a Run has reached `Failed`*. A sandbox that OOM-kills or a node
> that vanishes does **not** politely transition the Run to `Failed`: it goes **silent**. The Run row
> still reads `Running`, the pod is gone, and **no reconcile is queued** because nothing changed on the
> `Run` CR. This story is the missing edge: **how a silently-dead `Running` Run is detected, its
> work-item checkout reclaimed (fence-first), and the Run requeued with bounded exponential backoff —
> reading recovery state from Postgres so nothing is lost.** The load-bearing invariant is **"lease
> expiry is a *suspicion* of death, never a *license* to reclaim"**: a design that treats
> `lease_expires_at < now()` alone as permission to release-and-retry resurrects a slow-but-alive holder
> (the GC-pause zombie, §6.3) — a **correctness failure, not a bug ticket**. Read AC1 and AC3 literally.

## ⚠️ Scope reconciliation — 3.2 vs 3.1 (read first, they overlap on purpose)

The originating issue (ISI-2202) says "requeues Run with exponential backoff," and Story 3.1's machine
*already* re-enters `Claiming` on `Failed` with backoff (3.1 AC5, check (E)). That is not duplication —
the two stories own **different halves of the same edge**:

| Concern | Owned by | This story adds |
|---|---|---|
| The `Failed → Claiming` transition + retry-lap re-entrancy (sandbox bind reattaches, dispatch dedups) | **Story 3.1** (AC5, check E) | — (consumed, not re-specified) |
| **Detecting** that a `Running` Run died *without* transitioning (lease non-renewal + pod disappearance) | **THIS STORY (3.2)** | the two independent detectors (§A) |
| **Confirming** death before reclaim (slow-holder vs dead-holder; the §6.3 GC-pause teeth) | **THIS STORY (3.2)** | the fence-first-with-confirmation reclaim on the death edge (§B) |
| The concrete **exponential-backoff DELAY FUNCTION** (base·multiplier^n + jitter, cap) + its durable crash-safe schedule | **THIS STORY (3.2)** | the delay function + `next_attempt_at`/`attempt_count` durability (§C) |
| The **terminal-vs-requeue DECISION** on the `retryPolicy.maxAttempts` budget (`attempt_count >= maxAttempts → terminal Failed(RetryBudgetExhausted)`) | **Story 3.1** (AC5) | — (consumed, not re-specified — see the scope pin below) |
| Distinguishing **failure backoff (FR-A5)** from **rate-limit `resume_at`** (§8 tier-2, ADR-031) | **THIS STORY (3.2)** | the two are separate clocks on the same Run (§C) |

**⚠️ Scope pin (the budget decision lives in ONE place — 3.1).** The death edge this story owns
transitions `Running → Failed(reason ∈ {SandboxDied, LeaseExpired, PodDisappeared})` after the fence-first
reclaim. It does **not** itself evaluate the attempt budget or decide requeue-vs-terminate. **Story 3.1's
single `Failed → (retryPolicy, backoff) → Claiming` lap (AC5, its check E) owns that decision and is the
sole writer of `attempt_count`/`next_attempt_at`** — consulting `retryPolicy` exactly once, using **this
story's §C delay function** to compute the delay. This keeps the budget check out of two divergent code
paths: 3.2 = detection + fence-first reclaim + the delay-function *spec* + the two-clock distinctness;
3.1 = the terminal-vs-requeue decision + the durable write. (Falsification (D) asserts the budget
*invariant* 3.1 must uphold when it consumes §C, not a second implementation of it.)

**One-line boundary:** 3.1 answered *"once a Run is Failed, how does it retry safely?"* This story answers
*"how does a Run that died silently ever become Failed-and-retried in the first place, without a
false-positive reclaim of a live holder, and with a backoff that survives an operator restart?"* — it
delivers the death to 3.1's doorstep as `Failed(reason)` and hands it the delay function; 3.1 decides.

## Story

As **the Run reconciler + the lease-sweeper (§6.2/§6.3, the liveness layer of the I1 control plane)**,
I want **to detect a `Running` Run whose sandbox or agent has died — by lease non-renewal *and* pod
disappearance, never by lease expiry alone — then fence-and-confirm the dead holder, release its
work-item checkout for reclaim, and requeue the Run into `Claiming` with bounded exponential backoff
whose schedule is durable in Postgres**,
so that **a crashed sandbox or a vanished node never leaves a Run wedged in `Running` forever, never
loses committed coordination progress (it is in Postgres, not the pod), never releases a claim out from
under a holder that is merely slow (the GC-pause zombie), and never storms a broken dependency with
unbounded retries — closing the FR-A5 / NFR-REL1/REL2 half of R4 that Story 3.1 assumed but did not
detect.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-A5** (failure/retry with backoff, the direct requirement),
  **FR-A4** (Run reconcile lifecycle, 3.1), **FR-B2** (lease/liveness reclaim), **NFR-REL1** (no
  coordination state lost on crash), **NFR-REL2** (failover continues), **S8** (the scenario:
  sandbox/agent dies mid-Run → recover, lose nothing).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§8 "Failure/resume (FR-A5, NFR-REL1/REL2)"** — *"a dead sandbox/agent is detected (lease
    non-renewal **+ pod status**); the reconciler runs the §6.3 reclaim protocol — fence the pod first,
    release the claim second — and retries with backoff. No coordination state is lost because it is in
    Postgres, not the pod."* **This story's whole spec is the elaboration of that one sentence.** Note
    the **`+`**: lease non-renewal AND pod status, not OR — that conjunction is AC1's teeth.
  - **§6.2** — the fenced claim renewal `UPDATE … WHERE work_item_id AND holder AND fence AND
    lease_expires_at > now()`. A dead holder stops renewing; the row becomes *reclaimable-in-principle*
    once `lease_expires_at < now()`, **but §6.3 forbids acting on that alone.**
  - **§6.3 "Lease, liveness, fencing (crash-reclaim)"** — the **authoritative reclaim protocol** this
    story drives on the death edge: **(1) fence the holder** — terminate the pod, deny egress
    (git push / model calls stop), record a durable `reclaim_fenced_at` marker on the Run so a
    reconciler crash mid-reclaim re-enters idempotently; **(2) confirm** the pod is gone (or escalate to
    cordon + operator alert — *never release an unconfirmed-unfenced claim*); **(3) release the claim** —
    only now is the row acquirable via the §6.2 conditional UPDATE, and the monotonic `fence_token` bump
    means a resurrected zombie's writes lose the equality guard. *"the reconciler never treats
    `lease_expires_at < now()` alone as reclaim permission."*
  - **§8 rate-limit tier-2 (ADR-031) — the sibling clock to NOT conflate.** `Paused(rate_limited)`
    carries a **`resume_at`** wake for a *deliberate, provider-signalled* wait; this story's backoff is
    the **`next_attempt_at`** for an *involuntary death*. Same "durable timestamp + `RequeueAfter`, not a
    poll loop, crash-safe by re-reading the row" *mechanism* (reuse it), different *cause and budget*
    (retryPolicy attempts vs Retry-After). Do not route a dead-sandbox retry through `Paused`.
  - **§5.1 `Run`** (r28) — `spec.retryPolicy` (the attempt budget + backoff params this story reads);
    `status.phase` (the pinned CEL enum — a requeue writes `Claiming`, **never a new phase**);
    `status.conditions` (this story surfaces the death `reason=SandboxDied|LeaseExpired|PodDisappeared`
    and the `Failed` transition; `attempt_count`/`next_attempt_at` are written by **3.1's lap**, not here —
    see the scope pin). This story **writes** detection/reason status; it does not add CRD fields (Story 1.2
    owns shape) and does not write the retry-budget fields (3.1 does).
  - **§6.4** — the re-entrancy spine (deterministic `a2a_task_id = run_id`, run_id-keyed sandbox bind,
    content-addressed artifact upsert, conditional step-advance). **This story relies on it**: a retry
    lap re-runs `claiming_sandbox`/`dispatching` and must not double-provision or double-dispatch. Story
    3.1 built and falsified it (its check E). This story's falsification stacks the *detection*
    false-positive/false-negative teeth on top.
- **Depends on:**
  - **Story 3.1** (ISI-2201 — the reconcile machine + durable `reconcile_step` + the `Failed → Claiming`
    retry transition this story *triggers*). Hard dependency: 3.2 is the detector that feeds 3.1's lap.
  - **Story 2.4** (ISI-2194 — reclaim + fencing, the §6.3 fence-first protocol this story invokes on the
    death edge) and **Story 2.2** (ISI-2192 — the fenced claim being released). 3.2 is *"the direct
    consumer of Epic 2 reclaim"* (epics row 3.2).
  - **Story 2.1** (coord schema — `claim.lease_expires_at`, `fence_token`; the Run recovery state
    `reconcile_step`, `reclaim_fenced_at`, `next_attempt_at`, `attempt_count`).
  - **§5.2 leader election** — the lease-sweeper is a **leader-elected** reconcile loop (one owner, no
    racing sweepers); availability mechanism, with fencing as the safety mechanism underneath.
- **Blocks / is consumed by:** **3.3** (kill/cancel — reuses the same reclaim, but operator-initiated,
  not death-triggered), **3.7** (rate-limit auto-pause — the sibling `resume_at` clock this story keeps
  *distinct*), **Epic 13.2** (the `lease.reclaim.total{trigger}` + `stale_holder` metrics that *observe*
  this story's reclaims — the concurrency alert), **Epic 8.8f** (Live Runs surfaces the retry/backoff
  state).

## The two detectors (authoritative — §A)

A `Running` Run that dies silently produces **no CR change**, so a purely CR-triggered reconciler never
wakes. Detection needs **two independent signals**, and the reclaim needs **both to agree** (§8's `+`):

**A1 — Lease-expiry sweeper (the primary detector, leader-elected, §6.2/§6.3).** A periodic reconcile
loop (a `RequeueAfter`-driven sweep, *not* a busy poll) scans `claim` rows where
`lease_expires_at < now() - grace` and the holding Run is `Running`. Grace = a small multiple of the
renewal interval (a single missed heartbeat is not death; the holder may be briefly stalled). An expired
lease makes a Run a **death *suspect*** — it enters reclaim's step (1), it does **not** get its claim
released yet. Mirrors the §6.2 reclaim `WHERE` clause and the r18/Story-2.11 due-item sweeper discipline
(a single scheduled sweep, zero wasted work).

**A2 — Pod-disappearance watch (the confirmation detector).** The Run reconciler watches the sandbox pod
(the pod the Run assembled in `Claiming`, §5.3.4). A pod `Deleted` / `Failed` / `NotReady`-past-grace
event enqueues the owning Run for reconcile *immediately* (no wait for the sweep interval). This is the
**fast path** (pod vanished cleanly) and the **confirmation source** for A1 (is the suspect actually
gone, or just not renewing because its node is network-partitioned but the pod is alive and about to
resume writing?).

**Why both, not either (AC1's teeth):** lease-expiry alone false-positives on a GC-paused-but-alive
holder (releases a live claim → §6.3's exact hazard). Pod-watch alone false-negatives on a wedged pod
that still *exists* (Running, holding the lease, but the agent process is hung and will never renew —
the pod is present so the watch never fires). **The reclaim proceeds to release only when the holder is
*confirmed dead*: pod gone/terminal (A2) OR the lease-expiry sweep escalated a fence that the holder
could not survive (A1 → fence step terminates the pod, then confirms).** Lease-expiry opens the case;
pod-state closes it. Neither signal alone releases a claim.

## The reclaim on the death edge (authoritative — §B, drives §6.3)

On a confirmed-dead `Running` Run, the reconciler runs the **§6.3 reclaim protocol verbatim** — the same
protocol Story 2.4 built for crash-recovery, invoked here from the Run machine:

1. **Fence the holder.** Terminate the sandbox pod (SIGTERM→SIGKILL, §9.3 disposable), apply the
   egress-deny NetworkPolicy so any late-waking process cannot `git push` or call the model, and record
   a durable **`reclaim_fenced_at`** marker on the Run **in the same transaction** as the phase note — so
   a reconciler crash mid-reclaim re-enters at step (2), never re-fires the terminate from scratch and
   never skips ahead to release.
2. **Confirm.** Verify the pod is gone/terminal (A2). If it cannot be confirmed within a bound (node
   unreachable, pod stuck `Terminating`), **escalate to cordon + operator alert — do NOT release.** An
   unconfirmed claim stays held; a false reclaim is worse than a stuck one (releasing a live holder =
   split-brain double-write, §6.3).
3. **Release the claim + bump the fence.** Only now release via the §6.2 conditional UPDATE. The
   **monotonic `fence_token` bump** (§6.1) means that if the "dead" holder was merely partitioned and
   wakes, its next renewal/write carries the **stale** fence and loses the `fence_token = :myFence`
   equality guard — its writes are rejected, not applied. This is why the release is safe even though
   step (2) can never be *perfectly* certain: fencing turns "probably dead" into "cannot corrupt state
   even if wrong."

The released work-item checkout is now reclaimable by Epic 2 (§6.2) — the retry lap (Story 3.1) re-claims
it fresh. **Recovery reads Postgres:** the Run's `reconcile_step`, artifacts, and audit trail are all
durable; the dead pod held **zero** recovery state. The retry re-derives from the committed step (3.1
AC2), so "nothing is lost" is a property of *where the state lives*, not of the retry code.

## The backoff policy (authoritative — §C)

**The function.** On the Nth consecutive death of a Run (attempt counter `attempt_count`, durable):

```
delay = min( base * (multiplier ^ (attempt_count - 1)), cap ) + jitter
next_attempt_at = now() + delay
```

- **`base`, `multiplier`, `cap`** come from `spec.retryPolicy` (§5.1), with operator-tunable defaults
  (e.g. base=10s, multiplier=2, cap=10m). **Bounded** — the cap prevents an unbounded wait; the multiplier
  prevents a retry storm against a broken dependency (a persistently-failing image, a dead node pool).
- **`jitter`** — a bounded random spread (e.g. ±20%) so a fleet of Runs that all died on the same node
  failure do not re-`Claiming` in a synchronized thundering herd against the `SandboxPool`.
- **`retryPolicy.maxAttempts` is the budget — but the *decision* is 3.1's (scope pin).** This story's
  death edge writes `Failed(reason)`; **Story 3.1's single Failed-handler lap (AC5)** is the one place that
  reads `retryPolicy`, and when `attempt_count >= maxAttempts` it keeps the Run terminal **`Failed`** with
  `reason=RetryBudgetExhausted` (its absorbing state) rather than requeuing — otherwise it computes the
  delay via the function above and re-enters `Claiming`. 3.2 defines the delay math; 3.1 owns the budget
  branch and the `attempt_count`/`next_attempt_at` write. Retry is bounded in *count* (3.1) and *delay* (this §C).

**The schedule is durable (the crash-safety crux, mirrors §8 tier-2 `resume_at`).** `next_attempt_at` and
`attempt_count` are persisted on the Run **in the same transaction** as the reclaim/step write. The
reconciler schedules a **single `RequeueAfter(next_attempt_at - now())`** — *not* a poll loop. On an
operator restart the failover leader **re-reads `next_attempt_at` from Postgres and re-schedules**; the
backoff clock is never held only in controller memory. A Run that was 4 minutes into a 10-minute backoff
when the operator restarted resumes with ~6 minutes left, not from zero and not immediately.

**Two clocks, one Run, kept distinct (do not merge with rate-limit).** A Run can carry a failure
`next_attempt_at` (this story, FR-A5, budget = `maxAttempts`) *or* a rate-limit `resume_at` (§8 tier-2,
ADR-031, budget = `Retry-After` window) — they are **different reasons with different budgets** even
though both reuse the durable-timestamp + `RequeueAfter` mechanism. A dead sandbox is **not** a
`Paused(rate_limited)`; conflating them would charge a death against the rate-limit re-route path or make
a rate-limit consume the retry budget. The phase classifier (3.1 AC5) already treats them as distinct
non-terminal resumable states; this story only ever writes the **failure** clock.

## Acceptance Criteria

**AC1 — a `Running` Run whose holder dies is detected by lease-non-renewal AND pod-state, never by lease
expiry alone.**
Given a `Running` Run whose sandbox/agent has died, When the liveness layer observes it, Then it is
detected by **both** the lease-expiry sweeper (A1: `lease_expires_at < now() - grace`, leader-elected,
`RequeueAfter`-driven not a busy poll) **and** the pod-disappearance watch (A2: pod `Deleted`/`Failed`
enqueues the owning Run immediately). And a **single missed heartbeat within grace does not trigger
reclaim** (a briefly-stalled but alive holder is not dead). And **lease expiry alone never releases the
claim** — it opens the reclaim case (step 1), it is not a license to release (AC3).

**AC2 — reclaim on the death edge runs the §6.3 protocol fence-first, and recovery loses nothing.**
Given a confirmed-dead `Running` Run, When the reconciler reclaims, Then it (1) **fences** the holder
(terminate pod + egress-deny) recording a durable `reclaim_fenced_at` in the same transaction, (2)
**confirms** the pod is gone (or escalates to cordon+alert without releasing), (3) **releases** the
work-item checkout via the §6.2 conditional UPDATE with a **monotonic `fence_token` bump** — in that
order, never release-before-fence. And the released checkout is reclaimable by Epic 2 for the retry lap.
And **recovery reads Postgres**: the Run's `reconcile_step`, artifacts, and audit are durable; the retry
re-derives from the committed step (3.1 AC2) — the dead pod held zero recovery state, so **nothing is
lost**.

**AC3 — a slow-but-alive holder (GC-pause zombie) is never falsely reclaimed; fencing makes an uncertain
reclaim safe.**
Given a holder whose lease expired because it was **paused/partitioned, not dead**, When the sweeper
suspects it, Then the reclaim **does not release** until the pod is confirmed gone/terminal (AC1's
conjunction); a still-existing pod holds the case open (escalate, don't release). And if the release does
proceed and the "dead" holder later **wakes**, its stale `fence_token` **loses the `fence_token = :myFence`
equality guard** (§6.3) — its renewal/write is rejected, not applied. So a false-positive reclaim can
**never corrupt state**: fencing turns "probably dead" into "cannot double-write even if wrong." A design
that releases on `lease_expires_at < now()` alone (no pod confirmation, no fence bump) is a correctness
failure.

**AC4 — the death edge produces `Failed(reason)`; requeue uses this story's bounded backoff DELAY
FUNCTION, and the terminal-vs-requeue DECISION is 3.1's single budget check (scope pin).**
Given a Run reclaimed after death, When the death edge completes, Then it transitions
`Running → Failed(reason ∈ {SandboxDied, LeaseExpired, PodDisappeared})` — it does **not** itself evaluate
the attempt budget. And when **Story 3.1's Failed-handler lap** requeues, it re-enters `Claiming` after
`delay = min(base * multiplier^(attempt_count-1), cap) + jitter` (this story's §C function, params from
`spec.retryPolicy`), incrementing the durable `attempt_count` **that 3.1 writes**. And the delay is
**bounded** by `cap` (no unbounded wait), the **multiplier** backs off a persistently-failing dependency
(no retry storm), and **jitter** prevents a synchronized thundering herd after a shared node failure. And
the budget is enforced in exactly one place — **3.1 AC5**: when `attempt_count >= maxAttempts` the Run
stays terminal `Failed(RetryBudgetExhausted)`, never an infinite retry loop. This story does **not** add a
second `retryPolicy` code path (see the scope pin above).

**AC5 — the backoff schedule is durable and crash-safe; it is a single timed wake, not a poll loop.**
Given a Run waiting out its backoff, When the reconciler schedules the retry, Then it persists
`next_attempt_at` + `attempt_count` to Postgres **in the same transaction** as the reclaim/step write and
schedules a **single `RequeueAfter(next_attempt_at - now())`** — **not** a poll loop (zero wasted
reconciles during the wait). And on an **operator/leader restart** the failover leader **re-reads
`next_attempt_at` from Postgres and re-schedules the remaining delay** — the backoff clock is never held
only in controller memory; a restart mid-backoff resumes the remaining time, never restarts from zero and
never fires immediately.

**AC6 — the failure clock is distinct from the rate-limit `resume_at` clock (no cross-contamination).**
Given a Run that dies (this story) versus a Run that is rate-limited (§8 tier-2 / 3.7), When each schedules
its wake, Then the **death** path writes the **failure** `next_attempt_at` with budget `maxAttempts` and
`reason ∈ {SandboxDied, LeaseExpired, PodDisappeared}`, while the **rate-limit** path writes `resume_at`
with a `Retry-After` budget and `phase=Paused(rate_limited)` — **the two are never conflated**: a dead
sandbox never becomes `Paused(rate_limited)`, and a rate-limit pause never consumes the failure retry
budget. Both reuse the durable-timestamp + `RequeueAfter` mechanism (AC5); they differ in cause, phase,
and budget.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/run-retry-backoff-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same shape as the Story 2.4 / 3.1 checks), not a happy-path demo. It stacks the *detection*
teeth (this story) on top of the *retry-lap* re-entrancy (3.1, assumed):

- **(A) NAIVE detector — releases on lease-expiry alone.** Reclaims the moment `lease_expires_at < now()`
  with no pod confirmation and no fence bump. A **GC-paused-but-alive** holder wakes after the reclaim and
  writes → the check asserts the naive design **detectably double-writes** (two live holders on one item).
  If (A) ever stops breaking, the check fails **loud** — the harness lost its detecting power.
- **(F1) confirmation-gate teeth (AC1/AC3).** Drives `pod_confirmed_gone=False` (a lease-expired but
  network-partitioned, still-alive holder) and asserts the §6.3 reclaim returns **`held`** — the claim is
  **not** released — plus a differential twin where a naive release-on-expiry path hands the claim to podB
  while the live podA keeps writing → **two live holders**. *Mutation-proven:* deleting the
  `if not pod_confirmed_gone: return "held"` gate turns the check **RED** (the load-bearing "suspicion, not
  license" invariant now has teeth — the gap ISI-2363 F1 flagged).
- **(B) §6.3 CONFIRMED-DEATH + FENCE-FIRST detector.** Requires **both** lease-expiry (A1) **and** pod
  gone/terminal (A2) before release; runs fence → confirm → release with a monotonic fence bump. The same
  GC-paused zombie wakes → its stale fence **loses the equality guard**; its write is **rejected**. The
  check asserts **exactly-one live holder, zero double-writes** across the false-positive scenario.
- **(F2) release-time fence bump ISOLATED (AC2 §6.3 step 1).** The reclaim advances the resource fence
  barrier **fence-first** (`db.fence_resource`), so a woken zombie that writes **after release but before
  any new holder acquires/writes** is fenced out by the reclaim **alone** — no new-holder write masks it.
  *Mutation-proven:* deleting the barrier advance turns the check **RED** (the gap ISI-2363 F2 flagged: the
  old model let acquire's re-bump mask a deleted release bump).
- **(C) false-negative teeth — wedged-but-present pod.** A pod that still `exists` (Running) but whose
  agent hung and stopped renewing: pod-watch alone never fires; the check asserts the **grace-aware lease
  sweeper** (`lease_expires_at < now - grace`) still opens the case and (after fencing terminates the
  wedged pod) reclaims — the conjunction detector does not silently wedge forever.
- **(F6) grace window (AC1).** A single missed heartbeat **within grace** (`lease` lapsed but
  `!(lease_expires_at < now - grace)`) asserts the sweeper does **not** open a reclaim — the transient-stall
  false-positive guard has teeth.
- **(F5) crash mid-reclaim (AC2 idempotency).** A crash **between** the fence marker (step 1) and the
  release (step 3) re-enters via the durable `reclaim_fenced_at` marker and asserts the fence barrier is
  **not double-advanced** — step 1 is idempotent.
- **(D) backoff monotonicity + cap + budget INVARIANT.** Asserts `delay(n)` is non-decreasing, **capped**
  (never exceeds `cap + jitter`), and **jittered** deterministically (two Runs at the same attempt get
  different delays, reproducible across processes — `hashlib`, not salted `hash()`, the ISI-2363 F4 fix).
  The `attempt_count >= maxAttempts → Failed(RetryBudgetExhausted)` assertion is the **invariant 3.1 must
  uphold** when it consumes this §C function — **not** a second budget implementation here (scope pin).
- **(E) crash-safe backoff schedule (AC5).** Persists `next_attempt_at` to Postgres, simulates an operator
  restart mid-backoff via a **fresh in-memory reconciler with no timers**, and asserts the failover path
  **re-reads durable state and resumes the remaining delay** (150s, not zero, not immediate) while the
  naive in-memory wake is **dropped** on restart.
- **(F) two-clock distinctness (AC6).** Asserts a dead-sandbox Run carries the **failure**
  `next_attempt_at`/`maxAttempts` budget and is **never** classified `Paused(rate_limited)`, and a
  rate-limited Run carries `resume_at`/Retry-After and **never** consumes the failure budget — merging the
  two clocks makes it fail loud.

Exits non-zero if the reclaim releases a live/unconfirmed holder, double-writes, lets a zombie write in the
release window, false-negatives a wedged pod, reclaims within grace, double-advances the fence on re-entry,
exceeds the cap, loses the backoff wake on restart, or conflates the failure and rate-limit clocks. **The
two headline invariants are mutation-checked:** deleting the confirmation gate (F1) or the fence-first
barrier advance (F2) each turns the check **RED** — the ISI-2363 blocking findings are closed.

## Out of scope (owned elsewhere)

- **The `Failed → Claiming` transition + retry-lap re-entrancy** (Story 3.1 AC5, check E — this story
  *triggers* it, does not re-specify it), **the fenced claim/reclaim primitives** (Stories 2.2/2.4, §6.2/6.3
  — invoked, not built here), **operator kill/cancel** (Story 3.3 — same reclaim, but human-initiated),
  **rate-limit `Paused(rate_limited)` + `resume_at`** (Story 3.7 / §8 tier-2 — the sibling clock kept
  *distinct*, AC6, not driven here), **warm-pool sandbox bind internals** (§9.2), **the reclaim/lease
  metrics** (Epic 13.2 `lease.reclaim.total` — observes this story, does not implement it), **the Live-Runs
  retry/backoff UI** (Epic 8.8f). This story ships the **death detection (two detectors + the conjunction),
  the fence-first reclaim on the death edge, the bounded exponential-backoff requeue policy, its durable
  crash-safe schedule, and the differential falsification** — the FR-A5 liveness-recovery guarantee itself.
