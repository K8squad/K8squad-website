# Story 3.3: Kill a Run in ≤2 clicks — the operator-initiated terminate edge

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE VOLUNTARY-TERMINATE EDGE (arch §8 "Kill", FR-A6/FR-F4, S2, F4).** Story 3.2 owns the
> *involuntary* death edge — a sandbox that dies silently, detected by lease-non-renewal **+** pod-watch,
> then fenced-reclaimed and **retried** with backoff. This story owns the *voluntary* mirror: **an operator
> says "kill this Run," and the reconciler tears the sandbox down promptly and marks the Run terminally
> `Cancelled` — with the checkout released and NO retry.** The two edges share the **exact §6.3 fence-first
> reclaim primitive** (Story 2.4) but differ in three load-bearing ways: (a) the trigger is a *declarative
> operator intent*, not a detected death — there is nothing to *detect*, so no lease-sweeper / pod-watch
> conjunction here; (b) the terminal disposition is the **absorbing `Cancelled`** state, **not**
> `Failed(reason)` that feeds 3.1's retry lap — a killed Run must **never** be resurrected into `Claiming`;
> (c) the teardown is *active* (we SIGTERM→SIGKILL the pod because we **want** it dead), where 3.2 confirms
> a death that already happened. The load-bearing invariant is the **same fence-first ordering** 3.2/2.4
> enforce: **tear the sandbox down (fence) BEFORE releasing the checkout, never the reverse** — a design
> that releases the work-item checkout first and then kills the pod opens a window where the item is
> re-claimable by a *new* Run while the *old* sandbox is still alive and writing → split-brain double-write
> (§6.3). That is a **correctness failure, not a bug ticket.** Read AC2 and AC4 literally.

## ⚠️ Scope reconciliation — 3.3 vs 3.2 vs 3.1 (read first, they share the reclaim primitive on purpose)

The originating issue (ISI-2203) says "kill → `Canceling` → controller tears down sandbox → `Canceled` →
checkout released." Story 3.2 *already* built a fence-first reclaim (fence the pod, then release the
claim) and Story 2.4 built the §6.3 primitive underneath both. That is not duplication — the three stories
own **different edges of the same reconcile machine**:

| Concern | Owned by | This story adds |
|---|---|---|
| The §6.3 **fence-first reclaim primitive** (fence pod → confirm → release claim + monotonic fence bump) | **Story 2.4** (ISI-2194, §6.3) | — (invoked, not re-built) |
| **Detecting** an *involuntary* silent death (lease non-renewal **+** pod-watch) + **retrying** with backoff | **Story 3.2** (ISI-2202) | — (the *opposite* trigger; no detection here — the operator SAID kill) |
| The `Failed → (retryPolicy, backoff) → Claiming` **retry lap** + `attempt_count` budget | **Story 3.1** (ISI-2201, AC5) | — (a killed Run is terminal — it must **not** enter this lap; AC4) |
| The reconcile machine's **phase-transition + idempotent crash re-entry** spine (durable `reconcile_step`) | **Story 3.1** (its check E) | — (relied on; the teardown re-enters idempotently on the same spine) |
| **Recording a durable operator kill intent** + driving the fence-first teardown-then-release to the **absorbing terminal `Cancelled`** — one declarative signal, reconciler-completes, crash-safe | **THIS STORY (3.3)** | the whole edge (§A/§B/§C below) |

**⚠️ Scope pin (kill is TERMINAL — it does NOT route through the retry lap).** 3.2's death edge writes
`Failed(reason)` and hands it to 3.1's Failed-handler, which *decides* retry-vs-terminate against
`retryPolicy.maxAttempts`. **The kill edge writes the absorbing `Cancelled` directly — it never consults
`retryPolicy`, never writes `next_attempt_at`, never enters 3.1's lap.** `Cancelled` is a sink: no outbound
transition exists (arch §8 diagram). A design that routes a kill through the Failed handler (so a killed
Run gets a backoff and re-`Claiming`) resurrects work the operator explicitly stopped — a correctness
failure (AC4, falsification F-ABSORB). The one place the two edges converge is the §6.3 primitive they both
invoke; everything after the release diverges (kill → `Cancelled` sink; death → `Failed` → 3.1 decides).

**One-line boundary:** 3.2 answered *"how does a Run that died silently get detected, reclaimed, and
retried?"* This story answers *"how does an operator stop a live Run in one declarative action — tearing
its sandbox down promptly and releasing its checkout — such that the kill completes exactly once even
across a controller restart, never releases the checkout before the sandbox is confirmed gone, and never
gets undone by a concurrent retry?"* Same reclaim primitive, opposite trigger, terminal (not retried) sink.

## Story

As **the Run reconciler (the I1 control plane, §8) responding to a declarative operator kill intent**,
I want **to record a durable cancel intent on a `Running` Run, tear its sandbox pod down promptly
(SIGTERM→SIGKILL, §9.3 disposable) with a fence-first barrier, confirm the pod is gone before releasing
the work-item checkout, then mark the Run terminally `Cancelled` — all driven idempotently from one
declarative signal so a controller restart mid-teardown completes the kill exactly once**,
so that **an operator can stop a runaway or unwanted Run in ≤2 clicks (FR-A6/FR-F4, S2) and trust that the
sandbox is actually gone, the checkout is actually released for other work, the kill cannot be half-done
(no terminal state where the pod is torn down but the checkout is still held, or vice versa), a still-alive
sandbox can never keep writing after its item is handed to a new holder (fence-first + fence bump, §6.3),
and a killed Run is never silently resurrected by the retry lap (`Cancelled` is absorbing) — delivering
the FR-A6 terminate guarantee the console's kill button (Epic 8.4) calls.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-A6** (*"An operator SHALL be able to cancel/kill a `Run` and have
  its sandbox torn down promptly"* — the direct requirement), **FR-F4** (the console kill button that calls
  this edge — UI half, Epic 8), **S2** (legibility — an operator acts from the console without `kubectl`),
  **F4** (the differentiator: a killed Run is *promptly* and *cleanly* terminated, not left orphaned).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§8 "Kill (FR-A6/F4)"** — *"operator cancels → reconciler tears down the sandbox pod
    (SIGTERM→SIGKILL), releases claims, marks `Cancelled`. Sandbox teardown is prompt because the pod is
    disposable (§9.3)."* **This story is the elaboration of that one sentence** — with the crash-safety and
    fence-first ordering made explicit.
  - **§8 lifecycle diagram** — `Running ─► Cancelled (operator kill, FR-A6/F4)`. **`Cancelled` is an
    absorbing sink**: the diagram shows **no outbound edge** from it (unlike `Failed`, which loops back to
    `Claiming` via retry/backoff). That asymmetry is AC4's teeth.
  - **§6.3 "Lease, liveness, fencing (crash-reclaim)"** — the **authoritative reclaim protocol** this story
    invokes on the *kill* edge exactly as 3.2 invokes it on the *death* edge: **(1) fence** — terminate the
    pod + egress-deny + record a durable teardown marker in the same transaction (idempotent re-entry);
    **(2) confirm** the pod is gone/terminal (or escalate to cordon+operator-alert — **never release an
    unconfirmed claim**); **(3) release** the checkout via the §6.2 conditional UPDATE with a **monotonic
    `fence_token` bump** so a partitioned-but-alive sandbox that wakes after teardown loses the
    `fence_token = :myFence` equality guard. *"the reconciler never releases before the holder is fenced."*
  - **§6.2** — the fenced claim `release` (conditional UPDATE) the kill edge calls at step 3, and the
    `fence_token` bump that fences a woken zombie.
  - **§9.3 "Hygiene — reset-or-teardown … teardown-and-replace"** — the sandbox pod is **disposable**; the
    kill teardown is *prompt* because there is no in-place reset to negotiate — SIGTERM→SIGKILL and the pod
    is gone. The per-Run credential Secret and workspace are revoked at teardown (§11/§9.4).
  - **§5.1 `Run`** (r28) — `status.phase` (the CEL-validated enum `Pending|Claiming|Running|Paused|
    Succeeded|Failed|Cancelled` — this story's terminal write is **`Cancelled`**; see the **⚠️ phase-name
    reconciliation** note below), `status.conditions` (this story surfaces the in-progress teardown as a
    `Cancelling` condition and the terminal reason), `spec.retryPolicy` (**not read** on this edge — kill is
    terminal). This story **writes** cancel-intent + teardown-marker + terminal status; it does **not** add
    CRD fields (Story 1.2 owns shape — see the reconciliation note for the one field it flags).
  - **§6.4** — the re-entrancy spine (durable step markers, conditional advance). **This story relies on
    it**: the teardown re-enters idempotently on the same spine 3.1 built (its check E) — a crash between
    teardown (step 1/2) and release (step 3) re-enters at the durable marker, never re-fires the terminate
    from scratch and never double-releases.
- **Depends on:**
  - **Story 2.4** (ISI-2194 — the §6.3 fence-first reclaim primitive: fence pod → confirm → release +
    fence bump). Hard dependency: this story *invokes* it on the operator-kill edge.
  - **Story 3.1** (ISI-2201 — the reconcile machine + durable `reconcile_step` + idempotent crash re-entry
    the teardown rides on; and the terminal-state model into which `Cancelled` slots as an absorbing sink).
  - **Story 2.2** (ISI-2192 — the fenced claim being released) and **Story 2.1** (coord schema — the
    `claim` row + `fence_token` the release bumps; the Run recovery state for the durable teardown marker).
  - **§5.2 leader election** — the reconciler is leader-elected (one owner drives the teardown, no racing
    reconcilers double-fire the kill); availability mechanism, fencing is the safety mechanism underneath.
  - **Story 1.2 / 1.3** (CRD shape + validation) — owns the `Run.status.phase` enum and any condition-type
    vocabulary; see the reconciliation note for the one enum question this story surfaces to the Architect.
- **Blocks / is consumed by:** **Epic 8.4** (the console "kill in ≤2 clicks" button — the UI half of
  FR-F4/A6 that calls this control-plane edge; this story is its backend), **Epic 13.2** (the
  `lease.reclaim.total{trigger=cancel}` metric that *observes* this story's reclaims — distinguishing an
  operator kill from a death reclaim by the `trigger` label), **Story 3.6/context assembler** (a cancelled
  Run's snapshot is frozen; no further context assembly).

## ⚠️ Phase-name reconciliation — `Canceling` (epics AC) vs `Cancelled` (arch §5.1 CEL enum) — flagged to the Architect

The epics-and-stories AC (row 3.3) reads *"Run moves to `Canceling` … the Run marks `Canceled`"* — a
transient `Canceling` state followed by terminal `Canceled`. But the **arch §5.1 `Run.status.phase` CEL
enum (r28)** is `Pending|Claiming|Running|Paused|Succeeded|Failed|Cancelled` — it has the terminal
`Cancelled` (double-l) but **no `Canceling` phase**, and the §8 diagram transitions `Running ─► Cancelled`
directly. This story resolves the tension **without unilaterally expanding the CEL enum** (Story 1.2 owns
CRD shape; 3.2 set the precedent of *not* inventing new phases — it writes `Claiming`, never a new phase):

- **The in-progress teardown is surfaced as a `status.conditions` entry** (`type=Cancelling, status=True,
  reason=OperatorKill`), **not** a new phase. This satisfies the AC's *"moves to `Canceling`"* observably
  (the console and `kubectl get` show the Run is cancelling) while `status.phase` stays `Running` until the
  teardown completes, then flips **once** to the terminal `Cancelled` (matching the §8 diagram + the CEL
  enum). The **durable crash-safety marker** is a `cancel_requested_at` / `teardown_fenced_at` pair on the
  Run recovery row (mirroring 3.2's `reclaim_fenced_at`), **not** the phase field — so re-entry does not
  depend on a phase the enum lacks.
- **Flagged to the Architect (spec reconciliation, non-blocking):** if a first-class `Cancelling` phase is
  preferred over a condition (for UI-state clarity), the §5.1 CEL enum must add it and Story 1.2/1.3 must
  land it at Gate 2. This story is written to the **condition** model so it is buildable against the enum
  as it stands today; a later enum addition is a drop-in (the durable marker already carries the state).
  The **spelling** should also be reconciled (`Cancelled`/`Cancelling` double-l per the CEL enum vs the
  epics' single-l `Canceling`/`Canceled`) — this story uses the **CEL enum spelling** (`Cancelled`).

## The kill intent — one declarative signal (authoritative — §A)

**Kill is a *declarative desired-state* intent, not an imperative RPC** (ADR-002: desired-state
reconciliation). The console → apiserver records a **durable cancel intent** on the `Run` (a
`spec`-level cancel field / `ksquad.io/cancel-requested` annotation stamped with the initiating principal,
§12.4) — a single write. The reconciler *observes* it and drives the teardown; the operator does **not**
separately tear down the pod, release the checkout, and set the phase. **"≤2 clicks" (FR-A6/S2) maps to
"one idempotent declarative signal is sufficient; the reconciler completes the rest."** Deleting the Run CR
is **not** the kill mechanism (it would drop status/audit and race the finalizer); the intent is recorded
*on* the Run so the terminal `Cancelled` + its audit trail survive.

**Idempotent intent (the double-click guard).** The same kill signal issued twice (a double-click, a client
retry, a re-reconcile) is a **no-op the second time** — the durable `cancel_requested_at` marker makes the
teardown re-entrant, so a repeated intent neither re-fires the terminate from scratch nor double-releases
the checkout nor errors. One kill, one teardown, one release, one terminal write — regardless of how many
times the signal arrives.

## The teardown-then-release on the kill edge (authoritative — §B, drives §6.3)

On a `Running` Run carrying a cancel intent, the reconciler runs the **§6.3 reclaim protocol** — the same
protocol 3.2 runs on the death edge, invoked here from the *kill* branch:

1. **Fence + tear down the sandbox.** SIGTERM→SIGKILL the pod (§9.3 disposable), apply the egress-deny
   NetworkPolicy so any late-waking process cannot `git push` or call the model, advance the resource fence
   barrier, and record a durable **`teardown_fenced_at`** marker on the Run **in the same transaction** as
   the `Cancelling` condition — so a reconciler crash mid-teardown re-enters at step (2), never re-fires
   the terminate and never skips to release.
2. **Confirm the pod is gone/terminal.** Verify teardown completed (pod deleted/terminal). If it cannot be
   confirmed within a bound (node unreachable, pod stuck `Terminating`), **escalate to cordon + operator
   alert — do NOT release the checkout, do NOT mark `Cancelled`.** An unconfirmed teardown holds the case
   open; releasing a checkout while the old sandbox may still be alive = split-brain double-write (§6.3).
3. **Release the checkout + bump the fence.** Only now release the work-item claim via the §6.2 conditional
   UPDATE with a **monotonic `fence_token` bump**. If the "dead" sandbox was merely partitioned and wakes,
   its next write carries the **stale** fence and loses the `fence_token = :myFence` equality guard — its
   write is **rejected, not applied**. Fencing turns "we SIGKILLed it, it is probably gone" into "cannot
   corrupt state even if it somehow wakes."
4. **Mark terminal `Cancelled`.** Flip `status.phase` `Running → Cancelled` **once** (clearing the
   `Cancelling` condition), in the same transaction as the release. `Cancelled` is **absorbing**: no retry,
   no backoff, no `next_attempt_at`, no re-`Claiming`. The Run is done.

**Fence-first, never release-first (the load-bearing ordering).** Steps 1→2→3 are **ordered**: fence and
confirm the sandbox *before* releasing the checkout. A design that releases the checkout first (so a new
Run can claim the item) and *then* tears the pod down leaves a window where the **old, still-alive sandbox
and the new holder both write the same item** — the split-brain §6.3 exists to prevent. This is the *same*
ordering invariant 3.2/2.4 enforce; this story asserts it on the operator-kill edge (falsification
F-ORDER + F-CONFIRM).

## Kill is terminal — it outranks a concurrent retry (authoritative — §C)

`Cancelled` is an **absorbing terminal state** (§8 diagram: no outbound edge). Two consequences the
falsification pins:

- **The kill edge writes `Cancelled` directly — it never routes through 3.1's Failed handler.** It does not
  read `retryPolicy`, does not compute a backoff, does not write `next_attempt_at`. A dead sandbox
  (§8 death edge) becomes `Failed(reason)` and 3.1 *decides* retry-vs-terminate; a **killed** Run skips
  that decision entirely — the operator already decided (F-NORETRY).
- **A kill outranks an in-flight retry/reconcile (precedence).** If a kill intent lands while the Run is
  mid-reconcile — e.g. 3.2 just wrote `Failed(SandboxDied)` and 3.1's lap is about to re-`Claiming`, or the
  Run is between phases — the **terminal `Cancelled` wins**: once the cancel intent is durable, the retry
  lap must **not** resurrect the Run into `Claiming`. The reconciler checks the cancel intent / terminal
  `Cancelled` **before** any requeue. A design where the retry lap ignores a pending kill and re-claims a
  cancelled Run silently undoes the operator's stop (F-ABSORB — the distinctive teeth of this story vs 3.2).

## Acceptance Criteria

**AC1 — kill is one declarative, idempotent operator intent; the reconciler completes the rest (≤2 clicks).**
Given a `Running` Run, When an operator issues a kill (console → apiserver records a durable cancel intent
on the Run — a single declarative write, stamped with the initiating principal §12.4), Then the reconciler
observes it and drives the teardown to terminal `Cancelled` **without** the operator separately tearing down
the pod / releasing the checkout / setting the phase. And the **same kill issued twice is a no-op the
second time** (idempotent `cancel_requested_at` marker): one kill → one teardown → one release → one
terminal write, regardless of how many times the signal arrives. And **deleting the Run CR is not the kill
mechanism** — the intent is recorded on the Run so `Cancelled` and its audit survive.

**AC2 — teardown runs the §6.3 protocol fence-first: sandbox down BEFORE checkout release, never the reverse.**
Given a Run carrying a cancel intent, When the reconciler reclaims, Then it (1) **fences + tears down** the
sandbox (SIGTERM→SIGKILL + egress-deny + resource-barrier advance) recording a durable `teardown_fenced_at`
in the same transaction, (2) **confirms** the pod is gone/terminal (or escalates to cordon+alert **without
releasing and without marking `Cancelled`**), (3) **releases** the work-item checkout via the §6.2
conditional UPDATE with a **monotonic `fence_token` bump** — **in that order, never release-before-teardown**.
And the released checkout is reclaimable by Epic 2 for other work. A design that releases the checkout before
the sandbox is confirmed torn down is a correctness failure (split-brain double-write, §6.3).

**AC3 — a partitioned-but-alive sandbox that wakes after teardown is fenced out; an unconfirmed teardown holds.**
Given a sandbox that was network-partitioned (not actually dead) when killed, When the teardown proceeds,
Then the reclaim **does not release the checkout until the pod is confirmed gone/terminal** (AC2 step 2 — a
still-present pod escalates, it does not release). And if the release does proceed and the "dead" sandbox
later **wakes**, its stale `fence_token` **loses the `fence_token = :myFence` equality guard** (§6.3) — its
write is **rejected, not applied**. So even a kill against a merely-partitioned sandbox can **never corrupt
state**: fencing turns "we SIGKILLed it" into "cannot double-write even if it wakes."

**AC4 — `Cancelled` is absorbing: a killed Run never retries and is never resurrected by the retry lap.**
Given a killed Run, When the kill edge completes, Then it writes terminal **`Cancelled` directly** — it does
**not** consult `retryPolicy`, does **not** write `next_attempt_at`, does **not** enter 3.1's Failed→Claiming
lap (that lap is for the *death* edge's `Failed(reason)`, not for kill). And when a kill intent lands **while
a retry is in flight** (3.2 wrote `Failed`, 3.1's lap about to re-`Claiming`), the **terminal `Cancelled`
wins**: the reconciler checks the cancel intent **before** any requeue, so the retry lap **never resurrects a
cancelled Run into `Claiming`**. A design where the retry lap ignores a pending kill silently undoes the
operator's stop — a correctness failure.

**AC5 — the teardown is crash-safe and idempotent; the kill completes exactly once across a restart.**
Given a controller crash **between** the teardown (steps 1/2) and the checkout release (step 3), When the
failover leader re-reconciles, Then it re-enters via the durable `teardown_fenced_at` marker and **completes
the kill without re-firing the terminate from scratch and without double-releasing** — the fence barrier is
**not** double-advanced, the checkout is released **exactly once**, and the terminal `Cancelled` is written
**exactly once**. And there is **no observable terminal state where the pod is torn down but the checkout is
still held, or the checkout is released but the phase is not `Cancelled`** — partial completion is not a
terminal state; the reconciler drives to the complete terminal or holds the case open (AC2 escalation).

**AC6 — the in-progress teardown is surfaced legibly (`Cancelling` condition), distinct from `Failed`.**
Given a Run being killed, When the teardown is in progress, Then the reconciler surfaces a
`status.conditions` entry (`type=Cancelling, reason=OperatorKill`) so the console/`kubectl` show *why* and
*by whom* (§12.4 principal) — an operator kill is **never** an opaque `Failed`. And the terminal state is
`Cancelled` (the §5.1 CEL enum value, §8 diagram sink), **distinct** from `Failed(reason)`: a consumer
(Epic 13.2 metric, Epic 8 UI) can tell an operator-cancelled Run from a died-and-exhausted one by the
terminal phase + the `trigger=cancel` reclaim label, never conflating a deliberate stop with a failure.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/run-cancel-kill-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification, same shape as the Story 2.4 / 3.1 / 3.2 checks (it reuses the 3.2 fenced-DB primitives), not
a happy-path demo. It proves the *kill* edge has teeth by contrasting a NAIVE kill that releases the
checkout before tearing the sandbox down (and double-writes when the old sandbox keeps working) against the
§6.3 fence-first kill that does not — plus the terminal/absorbing and crash-idempotency teeth:

- **(A) NAIVE kill — release-before-teardown.** Releases the checkout the instant kill is issued, *then*
  tears the pod down. A **still-alive** sandbox keeps writing after podB claims the freed item → the check
  asserts the naive design **detectably double-writes** (two live holders on one item). If (A) ever stops
  breaking, the check fails **loud** — the harness lost its detecting power.
- **(F-ORDER) fence-first ordering teeth (AC2).** The SUT tears down + advances the resource fence barrier
  **before** releasing the checkout. *Mutation-proven:* swapping to release-before-fence (delete the
  step-1 `db.fence_resource` barrier advance / release first) turns the check **RED** — a woken sandbox that
  writes in the release→teardown window is accepted (the ISI-2363-F2-shaped gap on the kill edge).
- **(F-CONFIRM) confirmation-gate teeth (AC2/AC3).** Drives `pod_confirmed_gone=False` (a killed but
  network-partitioned, still-alive sandbox) and asserts the §6.3 reclaim returns **`held`** — the checkout
  is **not** released and the phase is **not** `Cancelled` (escalate, don't release). *Mutation-proven:*
  deleting the `if not pod_confirmed_gone: return "held"` gate turns the check **RED** (the "we killed it,
  release the checkout" shortcut is exactly the split-brain hazard — the ISI-2363-F1-shaped gap on the kill
  edge). A differential twin releases to podB while the live podA keeps writing → **two live holders**.
- **(B) §6.3 FENCE-FIRST kill.** Tears down → confirms gone → releases with a monotonic fence bump. The
  same partitioned sandbox wakes → its stale fence **loses the equality guard**; its write is **rejected**.
  The check asserts **exactly-one live holder, zero double-writes** across the wake-after-kill scenario.
- **(F-ABSORB) kill outranks retry — `Cancelled` is absorbing (AC4).** A kill intent lands while a retry is
  in flight (`Failed(SandboxDied)` written, 3.1's lap about to re-`Claiming`). The SUT checks the cancel
  intent **before** requeue → the Run terminates `Cancelled`, the retry lap is a no-op. *Mutation-proven:*
  making the retry lap ignore the pending kill (requeue unconditionally) turns the check **RED** — a
  cancelled Run is silently resurrected into `Claiming` (the distinctive kill-vs-death teeth).
- **(F-NORETRY) kill never writes the failure clock (AC4).** Asserts the kill edge writes `Cancelled` with
  **no `next_attempt_at`, no `attempt_count` increment, no `retryPolicy` read** — a killed Run carries none
  of the 3.2 backoff-clock state. Routing kill through the Failed handler (setting `next_attempt_at`) makes
  it fail **loud**.
- **(F-IDEM) crash mid-teardown re-enters idempotently (AC5).** A crash **between** the teardown marker
  (step 1) and the release (step 3) re-enters via the durable `teardown_fenced_at` marker and asserts the
  fence barrier is **not** double-advanced and the checkout is released **exactly once** — step 1 is
  idempotent, exactly like 3.2's `reclaim_fenced_at` re-entry.
- **(F-DOUBLECLICK) idempotent intent (AC1).** The same kill signal applied **twice** yields **one**
  teardown, **one** release, **one** terminal `Cancelled` — the second application is a no-op (no second
  fence bump, no error). A design that re-fires teardown per signal makes it fail loud.
- **(F-PARTIAL) no half-done terminal (AC5).** Asserts there is **no** terminal outcome where the pod is
  torn down but the checkout is still held, or the checkout is released but the phase is not `Cancelled` —
  the reconciler drives to the complete terminal or holds the case open (escalation), never both-half.

Exits non-zero if the kill releases the checkout before the sandbox is fenced/confirmed, double-writes,
lets a woken sandbox write in the release window, resurrects a cancelled Run via the retry lap, writes a
backoff clock on a kill, double-advances the fence on re-entry, re-fires teardown on a repeated signal, or
leaves a half-done terminal. **The two headline invariants are mutation-checked:** deleting the fence-first
barrier advance (F-ORDER) or the confirmation gate (F-CONFIRM) each turns the check **RED**, and making the
retry lap ignore the kill (F-ABSORB) turns it **RED** — the kill edge's correctness core is falsifiable.

## Out of scope (owned elsewhere)

- **The §6.3 fence-first reclaim primitive** (Story 2.4 — invoked, not built here), **the involuntary
  death-detection edge + retry/backoff** (Story 3.2 — the opposite trigger; a kill is *not* a death and
  does *not* retry), **the `Failed → Claiming` retry lap + `attempt_count` budget** (Story 3.1 AC5 — a
  killed Run never enters it, AC4), **the reconcile-machine phase spine + idempotent crash re-entry**
  (Story 3.1 — relied on, not re-built), **the fenced claim/lease primitives** (Stories 2.2/2.1 — the
  release + `fence_token` this story bumps), **the `Run.status.phase` CEL enum + condition vocabulary**
  (Story 1.2/1.3 — this story flags the `Canceling`-vs-`Cancelled` reconciliation to the Architect, it does
  not unilaterally expand the enum), **the console "kill in ≤2 clicks" button + the ≤2-clicks UX**
  (Epic 8.4 / FR-F4 — the UI half; this story is the control-plane edge it calls), **the
  `lease.reclaim.total{trigger=cancel}` metric** (Epic 13.2 — observes this story), **per-Run credential/
  workspace revocation internals at teardown** (§11/§9.4 — invoked at step 1). This story ships the
  **operator-kill intent, the fence-first teardown-then-release on the kill edge, the absorbing-terminal
  `Cancelled` (no retry, kill-outranks-retry), the crash-safe idempotent completion, and the differential
  falsification** — the FR-A6 terminate guarantee itself.
</content>
</invoke>
