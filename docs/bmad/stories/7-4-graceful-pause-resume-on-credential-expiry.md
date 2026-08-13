# Story 7.4: Graceful pause/resume on credential expiry/rotation

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔑 THIS IS THE SHARED PAUSE/RESUME STATE MACHINE — the one piece of machinery all three credential
> stories plug into (§7.2, §11, FR-G3, S10).** Stories 7.2 and 7.3 each pin ONE credential *lifecycle* —
> *when and why* a credential goes bad: 7.2 (Claude, `oauth-refresh`) pauses `Paused(cred_expired)` at the
> ~9-day re-login lapse; 7.3 (second runtime, `static-key`) pauses `Paused(cred_invalid)` on a provider
> auth-failure; and 7.5 (BYO Ollama, the endpoint model) contributes a third family whose fault is the
> model endpoint going unreachable. **This story owns none of those lifecycles — it owns the ONE thing they
> all plug into: the Run `Running → Paused → Running` transition machinery.** The load-bearing crux is that
> the machinery is **uniform and legible**: a single reducer reacts to a *normalized* credential-state
> signal, so every family — including a runtime added later — gets pause/resume **for free**, and a
> credential fault is **NEVER** allowed to surface opaquely (as a `Failed`, a terminal state, or a silently
> hung Run). Read AC1–AC6 literally: a design that special-cases the pause path per vendor, lets a fault
> bubble up as a generic Run failure, tears the Run down on pause, resumes on a **blind timer** while the
> credential is still bad, pauses silently, or leaks the credential material has committed the **FR-G3
> defect** ("never fails opaquely"), not shipped the feature.

## Gate status (read first)

This story carries **no spike gate**. It is pure control-plane machinery: given a normalized
credential-state signal (produced by the 7.2/7.3/7.5 lifecycles and the shim's runtime auth-failure
detection), drive the Run condition. Architecture **§11 — "Graceful pause/resume (both models)"** already
records the decision — *"Resume triggers on the referenced Secret updating (operator rotates the token)…
This holds for both OAuth-refresh (Claude) and static-key (second runtime) models"* — and **FR-G3** extends
"never fails opaquely" across **all** credential families the platform ships, the Ollama-endpoint model
(§10.3/7.5) included. This story **applies** that settled decision as the concrete state machine and pins
it with a runnable falsification; it does not reopen it.

## Story

As **an operator running a squad whose Runs depend on a credential that can expire, be rotated, or (for a
BYO endpoint) briefly go away**,
I want **any credential fault mid-Run to move that Run into a clearly-labelled `Paused` condition with an
operator signal that names exactly what to do, and to have the Run resume itself the moment I fix the
credential — with the SAME behaviour whether the credential is a Claude OAuth login, a second-runtime API
key, or an Ollama endpoint**,
so that **a credential problem never surfaces as an opaque crash, a silent hang, or a torn-down Run; I
always know a Run is *waiting on me* rather than *broken*, my in-flight work is preserved across the pause,
and the moment I re-login / rotate the Secret / bring the endpoint back the Run picks up where it left off —
FR-G3's "never fails opaquely," uniformly, for every credential model.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **§9.7 FR-G3** (graceful pause/resume on credential expiry/rotation;
  never fail opaquely — the requirement this story implements), **FR-G1/FR-G2** (per-user Secret refs;
  credential *type + lifecycle* as capability metadata — the signal source this reducer consumes),
  **NFR-SEC3** (creds never logged/echoed/exposed cross-squad), **S10** (graceful credential pause/resume as
  a v1 success criterion). The three lifecycle families this must hold for are **OAuth-refresh** (7.2),
  **static-key** (7.3), and **Ollama-endpoint** (7.5).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§11 — Graceful pause/resume (both models).** *"Resume triggers on the referenced Secret updating
    (operator rotates the token)… This holds for both OAuth-refresh (Claude) and static-key (second runtime)
    models."* This story generalises that one reducer to **every** family FR-G3 names, the Ollama endpoint
    included, and makes "never fails opaquely" a construction invariant.
  - **§7.2 — Run lifecycle / conditions.** `Paused` is a **first-class, non-terminal** Run condition,
    distinct from `Failed`: it is **reversible**, and the Run's progress/lease is preserved so it **resumes**
    (does not restart) when the credential recovers. The reducer transitions `Running → Paused(reason) →
    Running`; it does not tear the Run down.
  - **§10 — runtime/dispatch seam.** The pause/resume reducer is **runtime-neutral**: it dispatches on the
    normalized credential-state signal, not on the vendor/runtime family, mirroring the §10.1 zero-lateral-
    branch discipline (the same crux 7.3's AC5 pins). This is precisely what lets a runtime added later
    (Ollama-endpoint) inherit pause/resume **for free**.
  - **§8 — condition/reason surfacing.** Every pause emits an **operator-legible** condition reason + event
    that names the actionable fix (re-login / rotate Secret / restore endpoint) — no silent pause.
  - **§13 — screen 05 Credentials + Run detail.** The operator sees the `Paused` reason and the "what to do"
    prompt; the resume is automatic on the recovery signal. Health states *connected / rotating / invalid*
    (8.6) drive the signal; the operator never sees the credential material.
  - **§17.1 / NFR-SEC3** — the pause signal (condition, event, NATS) carries **reason metadata only**, never
    the credential string.
- **ADR:** No new ADR — this story **applies** §11's already-recorded pause/resume decision (the shared
  machinery for both models) and extends it across every FR-G3 family. **ADR-010** (per-user Secret ref,
  the resume trigger's subject) and **ADR-026** (the Ollama model-endpoint seam, the third family's fault
  source) are **not reopened**.
- **Depends on:**
  - **Story 7.2** (the `oauth-refresh` lifecycle — supplies the `cred_expired` fault signal + the
    `secret_updated` recovery for the Claude family). This story consumes that signal; it does not own the
    ~9-day window.
  - **Story 7.3** (the `static-key` lifecycle — supplies the `cred_invalid` fault signal + the
    `secret_updated` recovery for the second runtime). This story consumes it; it does not own the
    auth-failure detection.
  - **Story 7.5** (the BYO-endpoint model — supplies the `endpoint_unreachable` fault + `endpoint_reachable`
    recovery for the Ollama family). This story consumes it; it does not own the endpoint probe.
  - **Story 5.4** (the shim credential-injection contract — surfaces the runtime **auth-failure** that
    normalizes into the `cred_state` signal, and owns the no-log discipline on the *injected value*).
  - **Story 1.2 / 1.3** (the `Run` CRD condition set incl. `Paused`, and the reconciler scaffold that runs
    the transition).
  - **Story 2.x** (the Run reconcile / lease machinery whose progress the pause preserves — Paused must not
    drop the workspace lease).
- **Tightly coupled with / consumed by:**
  - **Stories 7.2 / 7.3 / 7.5** (each names *its* pause reason + *when*; **this** story owns the transition
    they share — §11 confirms 7.4 covers **all** the models).
  - **Story 7.6** (rate-limit pause/resume — a *sibling* pause family, self-recovering and per-credential;
    it reuses this same `Running → Paused → Running` machinery with a different reason and a different
    recovery signal, but is **out of scope** here — this story is the credential-fault pause).
  - **Story 8.6 / §13 screen 05 + Run detail** (the health/`Paused`-reason surface — this story names the
    condition + signal, not the UI).
  - **Story 13.x** (audit/metering — the pause/resume transitions ride the audit trail; not owned here).

## What the graceful pause/resume machinery does (the §7.2/§11 reducer — authoritative)

1. **One uniform, family-neutral reducer (AC1 — the FR-G3 crux).** The reducer dispatches on a **normalized
   credential-state signal** (`fault` / `recovered`) that the 7.2/7.3/7.5 lifecycles + the 5.4 shim emit —
   **not** on the vendor/runtime/model family. Every family routes through the **same** `Running →
   Paused(reason) → Running` transition, so a runtime added later (Ollama-endpoint) gets pause/resume **for
   free**. A per-family branch in the core transition is the §10.1 zero-lateral-branch violation, and it is
   exactly what would leave a new family silently unhandled.

2. **Never opaque: every fault becomes a legible `Paused` (AC2 — what FR-G3 forbids).** A credential fault
   **never** surfaces as `Run.Failed`, a terminal state, or a silently hung `Running` Run. It **always**
   produces the `Paused` condition with an operator-legible reason (`cred_expired` / `cred_invalid` /
   `endpoint_unreachable`). "Never fails opaquely" is the whole point of the story — a fault that bubbles up
   as a generic Run failure has committed the FR-G3 defect.

3. **`Paused` is non-terminal and reversible (AC3).** `Paused` is a first-class Run condition **distinct
   from `Failed`** (§7.2): the Run is **not torn down**, its progress/lease is preserved, and it **resumes**
   (does not restart) when the credential recovers. A model that transitions to a terminal/absorbing state
   on pause, or tears the workspace down, has broken resume-where-you-left-off.

4. **Resume is driven by the recovery signal, fail-closed (AC4).** The Run resumes on the **observed
   recovery signal** — `secret_updated` (7.2 re-login / 7.3 rotation, both an in-place per-user Secret
   update) or `endpoint_reachable` (7.5 endpoint restored) — and **never on a blind retry timer while the
   credential is still bad**. Resume is fail-closed: no recovery signal, no resume. *(Non-vacuous: the model
   must both* stay paused *until recovery* and *actually resume* each family when its recovery signal
   arrives.)*

5. **A clear operator signal on every pause (AC5).** Each pause emits an **operator-legible** signal — the
   condition reason **plus** an event (screen 05 / Run detail / NATS §17.4) that names the actionable fix
   ("re-login", "rotate the Secret", "restore the endpoint"). There is **no silent pause**: a Run that
   pauses without telling the operator what to do has failed "never fails opaquely" just as badly as a
   crash.

6. **The signal carries metadata, never material (AC6).** The condition, event, and NATS message carry
   **reason metadata only** (which family, which fault, what to do) — **never** the credential string
   (NFR-SEC3, §17.1). The pause path neither logs nor echoes the OAuth token, API key, or endpoint token.

## Acceptance Criteria

**AC1 — one uniform, family-neutral pause/resume reducer (the FR-G3 crux).** Given credential faults from
the OAuth-refresh, static-key, and Ollama-endpoint families, When the controller reduces each to a Run
transition, Then it dispatches on a **normalized credential-state signal**, identically for every family —
it does **not** branch on the vendor/runtime/model family. All three families route through the **same**
`Running → Paused → Running` machinery, so a runtime added later inherits pause/resume for free. A per-family
special-case in the core transition is a construction failure (the §10.1 zero-lateral-branch / FR-G3 defect
that would leave a new family unhandled).

**AC2 — never opaque: every credential fault becomes a legible `Paused` condition.** Given a Running Run
whose credential expires, is rotated/revoked, or whose endpoint goes unreachable, When the controller
detects it, Then the Run moves to the **`Paused`** condition with an operator-legible reason
(`cred_expired` / `cred_invalid` / `endpoint_unreachable`) — **never** `Run.Failed`, a terminal state, or a
silently hung `Running` Run. A credential fault that surfaces opaquely (as a generic failure or crash-loop)
is the exact FR-G3 defect this story forbids.

**AC3 — `Paused` is non-terminal and reversible; work is preserved.** Given a Run in `Paused` on a
credential fault, When the fault is later resolved, Then the Run **resumes** (does not restart) with its
progress/lease intact — `Paused` is a first-class condition **distinct from `Failed`** (§7.2), the Run is
**not torn down**, and the workspace lease is not dropped. A pause modeled as a terminal/absorbing state, or
one that tears the Run down, has broken resume-where-you-left-off.

**AC4 — resume is driven by the recovery signal, fail-closed.** Given a `Paused` Run, When the referenced
credential recovers (the per-user Secret is updated — 7.2 re-login / 7.3 rotation — or the endpoint becomes
reachable again — 7.5), Then the Run resumes on that **observed recovery signal** and **only** then. It does
**not** resume on a blind retry timer while the credential is still invalid. *(Non-vacuous: the model must
stay paused through the fault* and *actually resume each family — `secret_updated` for OAuth/static-key,
`endpoint_reachable` for Ollama — when recovery arrives.)*

**AC5 — a clear operator signal is emitted on every pause.** Given a Run entering `Paused` on a credential
fault, When the pause is recorded, Then a **clear operator signal** is emitted — the condition reason plus
an event (screen 05 / Run detail / NATS §17.4) that **names the actionable fix** for that family
("re-login" / "rotate the Secret" / "restore the endpoint"). There is **no silent pause**: a pause with no
operator signal is as opaque as a crash and fails FR-G3.

**AC6 — the pause signal carries metadata, never material.** Given a paused/resuming Run, When its pause
signal is observed (condition, event, NATS, logs), Then only **reason metadata** (family, fault reason,
remedy) appears — **never** the credential string (OAuth token, API key, or endpoint token) (NFR-SEC3,
§17.1). The pause path neither logs nor echoes the credential material.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/pause-resume-credential-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check over the **Run-condition transitions a controller reducer would produce** for a
credential fault→recovery on each of the three families (OAuth-refresh, static-key, Ollama-endpoint). It
first proves the **FR-G3 anti-pattern** — the "opaque failure" reducer, where a credential fault surfaces as
a terminal `Run.Failed` with no operator signal and no resume — is **DETECTED as violating the pause/resume
model on every family** (so the harness has real teeth), then proves the **§7.2/§11 graceful reducer**
violates nothing and **actually resumes all three families** on their own recovery signal.

```
[model] FR-G3 opaque-failure reducer : 6 violation(s) -> DETECTED
[model]   - [claude-oauth] credential fault surfaced as Run.Failed (reason='Error') — FR-G3 forbids failing opaquely ...
[model]   - [claude-oauth] Paused modeled as terminal/torn-down (terminal=True, torn_down=True) — Paused must be reversible ...
[model]   - [static-key] credential fault surfaced as Run.Failed ...
[model]   - [ollama-endpoint] credential fault surfaced as Run.Failed ...
[model] §7.2/§11 graceful pause/resume: 0 violation(s); conditions={'claude-oauth': 'Paused', 'static-key': 'Paused', 'ollama-endpoint': 'Paused'}; resumes={... 'ollama-endpoint': 'endpoint_reachable'}
[model] PASS — the opaque-failure reducer detectably breaks the pause/resume model; the §7.2/§11 graceful
        machinery holds P1-P6 ... and resumes all three families on their own recovery signal.
```

It encodes AC1–AC6 as assertions (P1–P6) over the transitions a design would produce: **(P1)** every
transition must dispatch on the normalized `cred_state` signal, never the vendor family — a per-family
branch flips it RED; **(P2)** every fault must become `Paused(reason)`, never `Failed`/terminal/hung;
**(P3)** `Paused` must be non-terminal and not tear the Run down; **(P4)** resume must fire on the observed
recovery signal and never a blind timer (non-vacuous in both directions — it must stay paused *and* actually
resume); **(P5)** every pause must emit an operator signal naming the fix; **(P6)** no observable surface may
carry credential material.

Each guard is **independently load-bearing** — mutation-verified via `--mutate=NAME`, which injects one
single defect into the conformant graceful path (`FAMILY_SPECIAL`, `OPAQUE_FAIL`, `TERMINAL_PAUSE`,
`BLIND_RESUME`, `SILENT_PAUSE`, `LEAK`) and flips the check **RED with exactly one violation** and no guard
shadowing another (the ISI-2346-F1 vacuous-tooth class is excluded by construction). Baseline `python3
pause-resume-credential-check.py` exits 0; each `--mutate=NAME` exits 1 with exactly one violation. The
check exits non-zero if the opaque-failure model *stops* violating (teeth lost), if the graceful model
*ever* violates an invariant, or if it fails to pause every family and resume each on its own recovery
signal.

**Runtime proof (owned by 7.2 + 7.3 + 7.5 + 5.4 + the ISI-2114 conformance lane).** The actual
`Running → Paused(reason) → Running` transition on a real cluster — a real credential fault, the emitted
operator event, and resume-on-refresh — is exercised by each family's story on its own credential plus the
conformance run. The model check guards the **construction-time pause/resume state machine** — 7.4's crux
and the thing FR-G3/S10 asked (graceful, uniform, never opaque).

## Out of scope (owned elsewhere)

- **Each family's credential lifecycle** — *when/why* a credential goes bad: the ~9-day OAuth re-login lapse
  (**7.2**, §11.1), the static-key provider auth-failure (**7.3**, §11), the endpoint-unreachable fault
  (**7.5**, §10.3). This story consumes their normalized fault/recovery signals; it does not own the
  detection.
- **The runtime auth-failure detection + no-log on the injected value** (**5.4**, §7.3, NFR-SEC3) — how the
  shim observes a provider auth-failure and normalizes it into the `cred_state` signal without logging the
  credential. This story owns the *transition*, not the probe.
- **The per-user Secret-ref shape + the operator's Secret update** (**7.1**, §11/§12.1, ADR-010) — the
  subject of the `secret_updated` recovery signal; this story reacts to the update, it does not implement
  the ref.
- **Rate-limit pause/resume** (**7.6**, §11.1) — a *sibling* pause family (self-recovering, per-credential,
  a different reason + recovery signal). It reuses this same `Running → Paused → Running` machinery but is a
  distinct story; this one is the **credential-fault** pause.
- **The console `Paused`-reason surface + Run detail** (**8.6 / §13 screen 05 + Run detail**) — the UI that
  renders the pause reason and the "what to do" prompt; this story names the condition + signal, not the UI.
- **The Run reconcile / lease machinery** (**2.x / 3.x**, §6/§7.2) — the reconcile loop that runs the
  transition and the lease the pause preserves; this story names the `Paused` transition, not the reconcile
  spine.
- **Audit / metering of pause/resume events** (**13.x**, §17) — the transitions ride the audit trail; not
  owned here.
