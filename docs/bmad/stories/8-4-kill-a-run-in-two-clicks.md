# Story 8.4: Kill a Run in ≤2 clicks (the console kill affordance — FR-F4/A6, S2)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE UI HALF OF THE KILL EDGE — and the FIRST WRITE AFFORDANCE in Epic 8.** Story 3.3
> (ISI-2203, **DONE**) built the *control-plane* half: an operator records a durable cancel intent on a
> `Running` Run and the reconciler runs the fence-first teardown-then-release to the absorbing terminal
> `Cancelled` (no retry, kill-outranks-retry, crash-safe). **This story is the console button that calls
> that edge in ≤2 clicks.** Every prior Epic-8 console story — 8.1 (overview), 8.2 (run-stream), 8.7
> (build-browser) — is **read-only, no-P2P**, and kill was explicitly held **out** of the 8.2 stream as
> *"a separate authorized control-plane action, not a stream verb"* (8.2 S6). So 8.4's entire job is to
> introduce **exactly one gated mutation, correctly** — and the load-bearing property is not "the button
> renders" but that the kill is a **declarative intent** (not a client-side teardown), routed through the
> **BFF choke point** (never browser→kube), gated by the **same deny-by-default RBAC wall** as every other
> surface with the kill **affordance absent from the DOM** for those who cannot act, **idempotent**, and
> surfaced **never-opaquely** over the **existing** SSE bus, distinct from `Failed`. A kill button that
> talks to kube directly, tears the sandbox down in the browser, is shown to viewers, or lets a contributor
> kill someone else's Run is a **security/correctness regression against §13/§12.3/ADR-002**, not a cosmetic
> bug. Read AC3 (declarative-not-imperative) and AC4 (RBAC mutate-gate) literally.

## ⚠️ Scope reconciliation — 8.4 (UI) vs 3.3 (control plane) vs 8.2/8.1 (the surfaces it lives on)

The originating issue (ISI-2267) says *"Given a Running Run, When I click kill (≤2 clicks), Then console
calls apiserver → Run Canceling (Epic 3.3)."* Story 3.3 already built the whole terminate edge. That is not
duplication — the two stories own **different halves of FR-F4/A6**:

| Concern | Owned by | This story adds |
|---|---|---|
| The **fence-first teardown-then-release** on the kill edge → absorbing terminal `Cancelled` (SIGTERM→SIGKILL, egress-deny, confirm-then-release + `fence_token` bump, no retry, crash-safe, `Cancelling` condition) | **Story 3.3** (ISI-2203, DONE) | — (called, not re-built) |
| The **durable cancel-intent** record on the Run (a single declarative `spec`/annotation write, stamped principal §12.4) that the reconciler observes | **Story 3.3 §A** | — (the console *records* this intent; it does not invent a new mechanism) |
| The **live SSE progress bus** that carries the `Cancelling`→`Cancelled` transition to the browser | **Story 8.2** (ISI-2265, DONE) | — (consumed, not re-built — kill feedback rides the ONE existing `EventSource`) |
| The surfaces a Running Run is **visible** on (overview tree, run-stream top bar) | **Stories 8.1 / 8.2** | the kill **affordance** placed on both, ≤2 clicks |
| The **console kill affordance**: a ≤2-click, RBAC-gated, affordance-hidden, idempotent button that records the declarative cancel intent **through the BFF**, and reflects the reconciler-driven transition never-opaquely | **THIS STORY (8.4)** | the whole UI edge (§A/§B/§C below) |

**One-line boundary:** 3.3 answered *"how does the reconciler stop a live Run and drive it to the absorbing
`Cancelled` safely?"* This story answers *"how does an operator **fire** that stop from the console in ≤2
clicks — a declarative intent through the BFF, gated by the same RBAC wall with the affordance hidden from
those who cannot act, idempotent, and legible as it happens — **without** the browser ever tearing anything
down itself or touching kube?"* The console **records intent and observes**; the control plane does the work.

## Story

As **an operator watching a runaway or unwanted `Running` Run in the console**,
I want **a kill affordance reachable in ≤2 clicks — on both the squad overview and the run-stream — that
records a single declarative cancel intent on the Run (stamped with me as the initiating principal) through
the Next.js BFF, and then reflects the reconciler-driven `Cancelling`→`Cancelled` transition live over the
same SSE stream I am already watching**,
so that **I can stop the Run in two clicks without `kubectl` (FR-A6/S2), trust that I fired one declarative
signal (not a half-done client-side teardown — the reconciler completes the fence-first teardown of Story
3.3), and see the kill actually take effect and land on the terminal `Cancelled` (distinct from `Failed`) —
while a teammate who is only a `viewer` on that Project never even sees the button, a `contributor` can kill
only their own Runs, and a double-click never fires two kills.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-F4** (*"The console SHALL let an operator cancel/kill a Run
  (satisfying FR-A6 from the UI)"* — the direct requirement), **FR-A6** (the control-plane guarantee Story
  3.3 delivers, called from here), **S2** (legibility — the operator acts from the console, **without
  `kubectl`**), **§9.15 FR-AUTH5 / R19** (the console **adapts to role**: non-admins see read-only surfaces,
  mutate affordances like start/kill are **hidden** where the user cannot act), **FR-G3** (never-opaque —
  the kill is legible, not a bare spinner). The persona motivation is Priya's *"see & kill a runaway Run"*
  and the narrative *"kills it in two clicks"* (§ around the platform-engineer walkthrough).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§13 (console)** — the **BFF choke point** rule (browser never touches Postgres/kube; ADR-013); the
    **Live Run progress via SSE** bullet (the ONE `EventSource` the kill feedback rides); console surfaces
    pass the **same §12.3 deny-by-default middleware** (r21, *"one enforcement point, every surface"* — the
    kill mutation passes the **same** wall, no console-specific authz path).
  - **§8 "Kill (FR-A6/F4)"** + the **§8 lifecycle diagram** (`Running ─► Cancelled`, `Cancelled` absorbing)
    — the edge this button calls; the transient teardown is surfaced as a **`Cancelling` condition**
    (reason=`OperatorKill`), not a new phase (Story 3.3's phase-name reconciliation).
  - **§12.3 RBAC / §12.1 tenancy / §15.3 per-project roles** — kill is a **mutate affordance**: `admin`
    (global) and `maintainer` kill **any** Run in scope; `contributor` kills **own** Runs only; `viewer` has
    **no** kill affordance. The server **re-checks every call** (the console is never the sole enforcement
    point — §9.15/8.16). Out-of-scope Runs are **existence-hidden** (not killable, not visible).
  - **§12.4 principal stamping** — the cancel intent records **who** issued the kill (surfaced in the
    `Cancelling` condition + audit 2.6).
  - **ADR-002 (desired-state reconciliation)** — kill is a **declarative** intent the reconciler observes,
    **not** an imperative RPC/teardown from the client. **ADR-013** (Next.js BFF vs SPA-direct-to-kube).
  - **§4.4 SSE progress bus** — the existing bus (8.2) that carries the `Cancelling`→`Cancelled` transition.
- **Nav IA / role-adaptive console (8.16, ISI-2304):** the kill button is one of the **mutate affordances**
  8.16 governs — **absent from the DOM** (not `display:none`) for a role that cannot act, layered **over**
  the server-side §12.3 enforcement (the console degrades gracefully if the API rejects an unauthorized
  call). This story places the kill affordance; 8.16 is the general adaptive-nav mechanism it conforms to.
- **Testing:** `docs/bmad/05-testing-strategy.md` **§3.2/§3.3 Epic 8** (console surfaces behind the BFF
  authZ choke point) and **§6.7** (RBAC matrix — per-project isolation, **mutate-affordance hiding** for
  non-actors, existence-hiding for out-of-scope entities). **§3.5/§6.7.8** responsive + RBAC×breakpoint (the
  kill target stays ≥44px touch-parity at every width).
- **UX mock:** `docs/bmad/ux/images/02-run-stream-sse.*` (the run-stream top bar — *"kill stays ≤2 clicks
  (button ≥44px)"*, per the responsive matrix row) and `01-squad-overview.*` (the overview Run-status row,
  where the kill affordance also lives). Dark+light (8.9), responsive (§13.1/ADR-038).
- **Depends on:**
  - **Story 3.3** (ISI-2203, **DONE**) — the control-plane kill edge this button calls (records intent →
    reconciler drives fence-first teardown → `Cancelled`). Hard dependency; this story is its UI half.
  - **Story 8.2** (ISI-2265, **DONE**) — the SSE progress bus + BFF proxy the kill feedback rides; the
    run-stream surface the button sits on.
  - **Story 8.1** (ISI-2264, DONE) — the overview surface the button also sits on.
  - **§12.3 deny-by-default middleware (Epic 15.4)** — resolves the caller → per-project role for the mutate
    gate. If not yet mergeable, wire the kill handler behind its interface and gate the RBAC integration
    test with `TODO(15.4)`; the **authorization-decision + intent-recording core does not depend on the
    console** and must be fully implemented and tested with an injected caller-scope.
- **Blocks / feeds:** completes the **FR-F4** console guarantee (the UI half of FR-A6). The `trigger=cancel`
  reclaim metric (Epic 13.2) *observes* the resulting reconcile. This is the **template for every future
  console mutate affordance** (8.5 compose, start-Run, approvals) — the first place Epic 8 crosses from
  read-only to a gated write.

## The kill affordance — one declarative intent through the BFF (authoritative — §A)

**≤2 clicks (FR-A6/S2).** On a **killable** (non-terminal) Run, the operator reaches kill in **≤2 clicks**:
**click Kill → confirm** (a single confirm step guards against an accidental fire; that is the second and
final click). The affordance is present on **both** surfaces a Running Run appears on — the **squad overview**
Run-status row (8.1) and the **run-stream** top bar (8.2, ≥44px) — so the operator never has to hunt for it
and **never falls back to `kubectl`** (S2). More than two clicks, or a `kubectl`/CLI escape hatch, fails
FR-A6.

**The click records a declarative cancel intent — it does NOT tear anything down (ADR-002, Story 3.3 §A).**
The confirm fires **one** mutating call: the console → **Next.js BFF** → apiserver records the **durable
cancel intent** on the Run (the `spec`-level cancel field / `ksquad.io/cancel-requested` annotation Story
3.3 defined), **stamped with the initiating principal** (§12.4). That is the whole client action. The
console does **not** SIGTERM/SIGKILL the pod, does **not** release the checkout, does **not** set
`status.phase` — the **reconciler** observes the intent and completes the fence-first teardown-then-release
(Story 3.3 §B). A console that performs the teardown itself has taken over a control-plane responsibility and
broken desired-state reconciliation (AC3).

**Through the BFF, never browser→kube (§13/ADR-013).** The mutating call terminates at the **Next.js BFF**,
which proxies the Go apiserver under the identity-aware choke point. The browser **never** issues the kill
against the Go apiserver, kube, or Postgres directly — the **mutating twin** of 8.2's read-side S2. The kill
passes the **same** §12.3 deny-by-default wall as every read surface; there is **no** second/console-specific
authorization path (r21).

## The RBAC mutate-gate — the crux (authoritative — §B, §12.3/§15.3/8.16)

Kill is the **first mutate affordance** in Epic 8, so the load-bearing new property is that a *write* passes
the same wall the reads do, **affordance-hidden** from those who cannot act:

- **`viewer`** (per-project) → **no kill affordance at all**: the button is **absent from the DOM** (not
  `display:none` — a `display:none` button is trivially re-enabled client-side, §9.15/8.16), **and** the API
  **denies** a kill call if one is forged. Visibility is affordance-hiding; the API is the real enforcement.
- **`contributor`** → kills **own** Runs only: the affordance renders on Runs the caller started; a kill
  against **another** member's Run is **denied** by the server (§15.3: *"contributor = can create tickets,
  view all, kill own Runs"*).
- **`maintainer`** (per-project) and **`admin`** (`global_role=admin` fleet bypass) → kill **any** Run in
  scope (§15.3: *"maintainer = full control … kill Runs"*).
- **Out-of-scope Runs are existence-hidden** — a Run under a Project the caller has no membership in is not
  visible and not killable (the kill decision returns deny **before** revealing existence, §12.3).
- **The server re-checks every call.** The console affordance-hiding is a legibility layer **over** the
  §12.3 enforcement — the API re-resolves membership on **every** kill call and never trusts a client-asserted
  role (§9.15/8.16 *"the server re-checks every API call"*). A design that trusts the client's role claim
  (so hiding the button is the only guard) is the classic broken-access-control regression.

## Idempotent, never-opaque, only-killable (authoritative — §C)

- **Idempotent intent (the double-click guard, Story 3.3 F-DOUBLECLICK).** The same kill fired twice — a
  double-click, a client retry, a re-render — is a **no-op the second time**: one kill → one teardown → one
  release → one terminal `Cancelled`, regardless of how many times the signal arrives. The button reflects
  the in-flight `Cancelling` state (disabled/"Cancelling…") after the first fire, and the durable
  `cancel_requested_at` marker (Story 3.3) makes a repeated intent inert. A design that re-fires the teardown
  per click is not idempotent.
- **Never-opaque, over the EXISTING SSE bus, distinct from `Failed` (FR-G3, Story 3.3 AC6, 8.2 §4.4).** After
  the fire, the Run reflects the **`Cancelling` condition** (reason=`OperatorKill`, **by whom** §12.4) then
  the terminal **`Cancelled`** — streamed live over the **same** `EventSource`/BFF proxy the operator is
  already watching (8.2), **no new transport, no polling loop**. The terminal state is **visibly distinct
  from `Failed`** (an operator kill is never conflated with a died-and-exhausted Run). An opaque spinner, a
  new poll, or a "Failed"-colored terminal breaks legibility.
- **Only killable (non-terminal) Runs (Story 3.3 AC4 — `Cancelled` absorbing).** The kill affordance is
  offered **only** on a non-terminal Run (`Pending`/`Claiming`/`Running`/`Paused`). A `Succeeded`/`Failed`/
  `Cancelled` Run shows **no** kill affordance, and a kill call against an already-terminal Run is **rejected/
  no-op** — you cannot cancel a done Run (`Cancelled` is a sink). A `Paused` Run (§7.4) is still live and
  **is** killable.

## Acceptance Criteria

**AC1 — kill in ≤2 clicks, on both surfaces, no `kubectl` (FR-A6/S2).**
Given a **killable** (non-terminal) Run visible in the console, When the operator kills it, Then the
affordance is reachable in **≤2 clicks** (**Kill → confirm**), present on **both** the squad-overview
Run-status row (8.1) and the run-stream top bar (8.2, target ≥44px), and there is **no** `kubectl`/CLI
fallback path — the operator stops the Run entirely from the console (**S2**). The confirm is the second and
final click (an accidental-fire guard, not extra friction).

**AC2 — the kill call goes through the Next.js BFF, never browser→kube (§13/ADR-013).**
Given the confirm, When the console fires the kill, Then it issues **one** mutating call to the **Next.js
BFF**, which proxies the Go apiserver under the same identity-aware choke point as every other surface — the
browser **never** calls the Go apiserver, kube, or Postgres directly (the mutating twin of 8.2's S2). No
second/console-specific authorization path is introduced (r21 — the kill passes the same §12.3 wall).

**AC3 — the console records a DECLARATIVE cancel intent, not an imperative teardown (ADR-002, Story 3.3 §A).**
Given the kill fire, When the mutating call lands, Then it records the **durable cancel intent** on the Run
(the Story 3.3 `spec`/annotation signal), **stamped with the initiating principal** (§12.4) — **a single
declarative write**. The console does **not** SIGTERM/SIGKILL the pod, **not** release the work-item
checkout, and **not** set `status.phase`: the **reconciler** observes the intent and completes the fence-first
teardown-then-release (Story 3.3). Deleting the Run CR is **not** the kill mechanism. A console that performs
the teardown client-side is a correctness regression (desired-state reconciliation broken).

**AC4 — kill is a role-gated mutate affordance, affordance-hidden, server-enforced (the crux, §12.3/§15.3/8.16).**
Given the §12.3-resolved caller, When the console renders and the kill is fired, Then: a **`viewer`** sees
**no** kill affordance (**absent from the DOM**, not `display:none`) **and** the API **denies** a forged
kill; a **`contributor`** can kill **own** Runs only (a kill against another member's Run is **server-denied**);
a **`maintainer`** and an **`admin`** (fleet bypass) can kill **any** Run in scope; an **out-of-scope** Run is
**existence-hidden** (not visible, not killable). The **server re-checks membership on every call** and never
trusts a client-asserted role — the affordance-hiding is a legibility layer **over** the §12.3 enforcement,
not a substitute for it (§9.15/8.16).

**AC5 — the kill intent is idempotent (the double-click guard, Story 3.3 F-DOUBLECLICK).**
Given a kill already fired, When the same kill is fired again (double-click, retry, re-render), Then it is a
**no-op the second time** — **one** kill → **one** teardown → **one** release → **one** terminal `Cancelled`,
regardless of how many times the signal arrives. The affordance reflects the in-flight `Cancelling` state
(disabled/"Cancelling…") after the first fire; a repeated intent neither re-fires the teardown nor errors.

**AC6 — the transition is never-opaque, live over the EXISTING SSE bus, distinct from `Failed` (FR-G3, 3.3 AC6).**
Given a fired kill, When the reconciler drives the teardown, Then the console surfaces the **`Cancelling`
condition** (reason=`OperatorKill`, **by whom** §12.4) then the terminal **`Cancelled`** — streamed live over
the **same** `EventSource`/BFF SSE proxy the operator is already watching (8.2 §4.4), with **no new transport
and no polling loop** — and the terminal state is **visibly distinct from `Failed`**. The kill is never an
opaque spinner and an operator-cancelled Run is never conflated with a died-and-exhausted one.

**AC7 — the kill affordance is offered only on a killable Run (Story 3.3 AC4 — `Cancelled` absorbing).**
Given a Run's state, When the console renders, Then the kill affordance is offered **only** on a **non-terminal**
Run (`Pending`/`Claiming`/`Running`/`Paused` — a `Paused` Run is still live and killable); a `Succeeded`/
`Failed`/`Cancelled` Run shows **no** kill affordance, and a kill call against an already-terminal Run is
**rejected/no-op** (you cannot cancel a done Run — `Cancelled` is a sink).

**AC8 — dark+light + responsive (v1, not polish).**
Given the kill affordance, When it renders, Then it mirrors the mocks (`02-run-stream-sse` top bar,
`01-squad-overview` Run-status row) in **both dark and light** (story 8.9, WCAG AA both modes) and stays
reachable in **≤2 clicks** with a **≥44px** touch target across desktop/tablet/mobile in the one responsive
SSR tree (§13.1/ADR-038) — no width at which kill needs >2 clicks or overflows.

**AC9 — runnable falsification (the affordance-design core).**
Given the kill-affordance design, When `docs/bmad/spikes/bench/run-kill-twoclicks-check.py` runs (stdlib-only,
no console, no cluster), Then it asserts **K1–K7** (≤2 clicks/no-kubectl · BFF choke point · declarative
intent not imperative teardown · RBAC mutate-gate · idempotent · never-opaque over the existing SSE bus ·
only-killable-Runs) over the design a console would ship: the **naive raw-kill-button** anti-pattern is
**DETECTED** violating every invariant (real teeth), the **§13/FR-F4** design violates none, and each guard is
**independently mutation-proven** — `--mutate=<CLICKS|DIRECT_API|IMPERATIVE|UNSTAMPED|VIEWER_AFFORDANCE|
CONTRIB_ANY|NO_RECHECK|NONIDEMPOTENT|OPAQUE|KILL_TERMINAL>` flips the check **RED with exactly one violation**
(no guard shadows another; the ISI-2346-F1 vacuous-tooth class excluded). Baseline exits 0; each mutation
exits 1.

## Tasks / Subtasks

- [ ] **Task 1 — Kill authorization + intent-recording core (AC2, AC3, AC4, AC5, AC7).** *Do this first — it
  is the mutate-gate + declarative-intent core and needs no console.*
  - [ ] `AuthorizeKill(ctx, callerScope, run) (bool, reason)`: resolve the caller → per-project role (§12.3/
    §15.3); `admin`/`maintainer` → any in scope, `contributor` → own-only, `viewer` → deny; out-of-scope →
    deny (existence-hidden); terminal Run → deny (AC7). **Re-checked server-side on every call**, never
    client-trusted (8.16).
  - [ ] `RecordCancelIntent(ctx, callerScope, runRef)`: on authorize, record the **Story 3.3 durable cancel
    intent** on the Run (`spec`/annotation), **stamped with the principal** (§12.4) — a single declarative
    write. Do **not** tear down / release / set phase (ADR-002 — the reconciler owns that, Story 3.3). The
    write is **idempotent** (repeated intent = no-op via the `cancel_requested_at` marker, AC5).
  - [ ] Table-driven test: viewer-deny, contributor-own-allow / contributor-other-deny, maintainer-any-allow,
    admin-bypass, out-of-scope-deny, terminal-Run-deny, idempotent-double-fire (one intent). Fails if any
    decision or the idempotency breaks.
- [ ] **Task 2 — Kill mutating endpoint on the apiserver (AC2, AC3, AC4, AC7).**
  - [ ] Expose the kill as an authorized mutating verb (e.g. `POST /api/v1/runs/{id}/cancel`) that calls
    `AuthorizeKill` then `RecordCancelIntent`. Unauthorized → `403`; unauthenticated → `401`; terminal Run →
    `409`/`422` (not killable); out-of-scope → `404` (existence-hiding). **Idempotent**: a repeated cancel
    on an already-cancelling/cancelled Run → `200`/`204` no-op, not a second teardown.
- [ ] **Task 3 — RBAC mutate gate behind the §12.3 middleware (AC4).**
  - [ ] Route the endpoint behind the Epic 15.4 **deny-by-default middleware**; the handler receives the
    **resolved** caller-scope and never post-authorizes on a client claim. If 15.4 is not yet mergeable, wire
    behind its interface and `skip` the integration test with `TODO(15.4)`; the Task-1 core does not depend
    on the console.
- [ ] **Task 4 — Console kill affordance + BFF proxy (AC1, AC2, AC6, AC8).** *If the Next.js console is not
  yet scaffolded, a thin BFF proxy stub + a `TODO` is acceptable — the authoritative deliverables are the Go
  core (Task 1) + the AC9 check.*
  - [ ] Place the kill affordance on **both** surfaces — the overview Run-status row (8.1) and the run-stream
    top bar (8.2, ≥44px) — reachable in **≤2 clicks** (Kill → confirm), **no kubectl fallback**.
  - [ ] Fire **one** call through the **Next.js BFF** (never browser→apiserver/kube). Reflect the
    `Cancelling`→`Cancelled` transition live over the **existing** SSE bus (8.2) — never-opaque
    (`OperatorKill` + by-whom), distinct from `Failed` (AC6). Disable/"Cancelling…" after the first fire (AC5).
  - [ ] **Affordance-hide by role** (AC4): the kill button is **absent from the DOM** for a `viewer` and for
    a `contributor` on another member's Run (8.16 — not `display:none`). Offer kill **only** on non-terminal
    Runs (AC7).
  - [ ] Dark + light (8.9) + responsive ≥44px target to 360px (§13.1/ADR-038).
- [ ] **Task 5 — Runnable falsification (AC9).** *(Already authored — keep green.)*
  - [ ] `docs/bmad/spikes/bench/run-kill-twoclicks-check.py` — baseline exits 0; each `--mutate=NAME` exits 1
    with exactly one violation (10 mutations, K1–K7). Wire into the bench matrix.

## Dev Notes

- **Repo shape (current).** k8squad is the Go code repo; `pkg/auth/`, `pkg/coord/`, and the Story 3.3 kill
  edge already exist. Put the kill authorization + intent-recording next to the other apiserver write paths /
  the Run reconcile package (following `pkg/coord`/`pkg/auth` conventions — lowercase package, `*_test.go`,
  standard `testing`). Do **not** introduce a new binary or a new kill mechanism — this story **calls** the
  Story 3.3 declarative intent, it does not re-implement the teardown.
- **The crux is the mutate-gate, not the button (AC4).** This is the **first write affordance** in Epic 8.
  The load-bearing property is that a *write* passes the **same** §12.3 deny-by-default wall as the reads,
  with the affordance **absent from the DOM** for non-actors and the **server re-checking every call**
  (§9.15/8.16). Mirror the read-side rule (8.1/8.2): the authz decision is made **server-side** on the
  resolved caller-scope; the client hiding the button is legibility, not enforcement. A `viewer` who forges a
  kill call must be **denied by the API**, and a `contributor` must not be able to kill another's Run — those
  are the mutation-proven teeth (`VIEWER_AFFORDANCE`, `CONTRIB_ANY`, `NO_RECHECK`).
- **Declarative, not imperative (AC3).** The console records **intent** and **observes** — it never tears the
  sandbox down, releases the checkout, or sets the phase (ADR-002 / Story 3.3 §A). The whole client action is
  **one declarative write** stamped with the principal (§12.4). A console that does the teardown has taken
  over the reconciler's job — the `IMPERATIVE` mutation is exactly that regression.
- **Reuse, don't rebuild (AC6).** Kill feedback rides the **existing** SSE bus (8.2, §4.4) — the `Cancelling`
  condition + terminal `Cancelled` arrive on the **same** `EventSource` the operator is already watching. Do
  **not** stand up a new stream or a polling loop for kill status (the `OPAQUE` mutation covers the
  poll/spinner regression). The `Cancelling` reason (`OperatorKill`, by-whom) is what makes it never-opaque
  (FR-G3) and distinct from `Failed` (Story 3.3 AC6).
- **≤2 clicks means a confirm, not a naked one-click (AC1).** FR-A6's *"≤2 clicks"* is satisfied by **Kill →
  confirm** — the confirm is an accidental-fire guard (killing a Run is destructive), still within the
  budget. Do **not** interpret "2 clicks" as forbidding the confirm; interpret ">2 clicks or a kubectl
  fallback" as the S2 regression (the `CLICKS` mutation).
- **Kill ≠ compose ≠ start (scope guard).** This story ships **only** the kill affordance. It is **not** the
  compose screen (8.5 — create/edit CRDs) and **not** start-a-Run. If you find yourself adding a create/edit
  form, stop — that is 8.5. Kill is one gated mutation: record the cancel intent, observe the terminal.

### Project Structure Notes

- **Go (apiserver):** kill authorization + intent recording next to the Run reconcile / apiserver write
  paths — `AuthorizeKill` (the per-project role gate, server-re-checked) + `RecordCancelIntent` (the Story
  3.3 declarative intent, principal-stamped, idempotent) + `handler.go` (the mutating verb + status codes) +
  `*_test.go` (the AC-driven table). Mirror `pkg/coord`/`pkg/auth` naming and the standard `testing` idiom.
- **No new teardown.** The fence-first teardown-then-release + absorbing `Cancelled` already exist (Story
  3.3). This story records the intent the reconciler observes and reflects the transition — **no** new
  reconcile logic, **no** new store, **no** CRD-shape change.
- **BFF/console:** the Next.js console may not yet be scaffolded; the Go core + AC9 check land here
  regardless (Task 4 note). The console fires one call through the BFF proxy and consumes the existing SSE
  bus for the transition.
- **Runnable check:** `docs/bmad/spikes/bench/run-kill-twoclicks-check.py` (authored) — stdlib-only,
  differential over the kill-affordance design, 10 mutations covering K1–K7.

### References

- [Source: docs/bmad/02-prd.md — FR-F4 / FR-A6 / S2 / §9.15 FR-AUTH5 / FR-G3] — console cancel/kill from the
  UI (satisfying FR-A6); operator acts without `kubectl`; role-adaptive console hides mutate affordances for
  non-actors; never-opaque.
- [Source: docs/bmad/03-architecture.md#13] — BFF choke point (browser never touches apiserver/kube/Postgres,
  ADR-013); Live Run progress via SSE (the ONE `EventSource`); console surfaces pass the same §12.3
  deny-by-default middleware (r21 "one enforcement point, every surface").
- [Source: docs/bmad/03-architecture.md#8 + lifecycle diagram] — Kill (FR-A6/F4): `Running ─► Cancelled`
  (absorbing); the transient teardown surfaced as a `Cancelling` condition (reason=OperatorKill).
- [Source: docs/bmad/03-architecture.md#12.3/#12.1/#15.3] — per-project roles: maintainer/admin kill any,
  contributor kills own, viewer none; server re-checks every call; out-of-scope existence-hidden.
- [Source: docs/bmad/03-architecture.md#12.4] — the cancel intent stamps the initiating principal (who
  issued the kill; audit 2.6).
- [Source: docs/bmad/03-architecture.md ADR-002 / ADR-013] — desired-state reconciliation (declarative
  intent, not imperative RPC); Next.js BFF vs SPA-direct-to-kube.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8, story 8.4 + the responsive matrix "Run stream / SSE
  (8.2): kill stays ≤2 clicks (button ≥44px)"] — FR-F4/A6, S2; kill on overview + run stream.
- [Source: docs/bmad/stories/3-3-kill-a-run-in-two-clicks.md] — the control-plane kill edge this button
  calls (durable cancel intent → fence-first teardown-then-release → absorbing `Cancelled`; `Cancelling`
  condition; idempotent F-DOUBLECLICK; AC4 absorbing).
- [Source: docs/bmad/stories/8-2-live-run-progress-via-sse.md] — the SSE bus + BFF proxy the kill feedback
  rides; kill held out of the stream as "a separate authorized control-plane action" (S6).
- [Source: docs/bmad/ux/images/02-run-stream-sse, 01-squad-overview] — the run-stream top bar (kill ≤2
  clicks, ≥44px) and the overview Run-status row (dark + light).

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

- `docs/bmad/spikes/bench/run-kill-twoclicks-check.py` — baseline exits 0; `--mutate=<CLICKS|DIRECT_API|
  IMPERATIVE|UNSTAMPED|VIEWER_AFFORDANCE|CONTRIB_ANY|NO_RECHECK|NONIDEMPOTENT|OPAQUE|KILL_TERMINAL>` each
  exits 1 with exactly one violation (K1–K7).

### Completion Notes List

### File List

- `docs/bmad/stories/8-4-kill-a-run-in-two-clicks.md` (this story)
- `docs/bmad/spikes/bench/run-kill-twoclicks-check.py` (runnable falsification, AC9)
