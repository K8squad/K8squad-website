# Story 8.6: Surface credential/auth state (the paused-on-expiry signal, screen 05)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **This is the operator's credential legibility surface: "which of my agents can authenticate right now,
> and which are stuck" — answered on the Settings → Credentials page (screen 05), never by reading a
> Secret.** It is a **pure read model, coordination-free by construction** (R6): per-agent credential health
> — *connected / refreshing / expired·paused* — is **DERIVED** from the **leader-elected credential
> controller's Secret state** (§5.2/§11.1) and the **Run's `Paused` condition** (§7.4); it invents **no new
> credential store and no console-owned health field** (ADR-020). The literal FR-F6 ask is the **clear
> paused-on-expiry signal**: an Agent whose Run is `Paused(cred_expired)` shows an **explicit** paused-on-
> expiry state with its reason and the **one-click re-login remedy** ("Connect Claude" browser-OAuth / `ksquad
> auth login` parity, 7.7) — never a generic error, a blank, or an opaque hang. It is served **through the
> Next.js BFF** (§13/ADR-013), **scoped in the assembly** (a caller sees only their own agents' health;
> `admin` sees the fleet), carries **health/reason metadata only — never the token bytes** (NFR-SEC3), and
> hangs **no token-paste / edit / rotate-in-console field** — the operator **never handles token strings**
> (§11.1 zero-touch). Read every AC literally: surfacing another principal's credential row, echoing the
> Secret value, rendering a `Paused(cred_expired)` Run as a generic error, or exposing a paste-token box is a
> **security / FR-F6 regression**, not a cosmetic bug.

## Story

As an **operator opening Settings → Credentials**,
I want to **see each of my agents' credential/auth health at a glance — connected, refreshing, or expired —
with a clear paused-on-expiry signal and a one-click re-login when a token has lapsed**,
so that **when a Run is `Paused` because its token expired I immediately see *why* and *how to fix it*
without touching `kubectl`, a Secret, or a token string** — a legibility surface, never a coordination or
secret-handling path.

## Context & prerequisites (read first)

- **Architecture:** `docs/bmad/03-architecture.md` **§13** (console — screen **05 Credentials** page; the
  **BFF choke point** rule: browser never touches Postgres/kube; console read models pass the **same
  deny-by-default §12.3 middleware**, r21 "one enforcement point, every surface"); **§11 / §11.1** (per-user
  Secret refs, ADR-010; the **zero-touch credential lifecycle** — the user connects once and never handles
  token strings; health derives from the **leader-elected credential controller's Secret state**); **§5.2**
  (the leader-elected credential controller — one owner refreshes the ~8h token, no per-pod refresh race);
  **§7.2/§7.4** (`credentialLifecycle` metadata; the `Running → Paused → Running` machine and the
  `Paused(cred_expired)` / `Paused(cred_invalid)` / `Paused(endpoint_unreachable)` reasons this surface
  renders). **ADR-013** (Next.js BFF vs SPA-direct-to-kube), **ADR-020** (read-model composition — no new
  store, per-source graceful degradation), **ADR-032** (zero-touch Claude OAuth supersedes the 8h manual
  `setup-token`).
- **Depends on (state this SURFACES, does not own):** **7.4** (`docs/bmad/stories/7-4-graceful-pause-resume-
  on-credential-expiry.md`) owns the family-neutral pause/resume state machine and the `Paused(reason)`
  conditions; **7.2/7.3/7.5** own the three credential *lifecycles* (Claude-OAuth refresh, second-runtime
  static-key, BYO Ollama endpoint); **7.7** owns the leader-elected controller + the one-click "Connect
  Claude" OAuth login. This story is the **console read model** over that state — it renders health, it does
  not compute expiry, refresh a token, or drive pause/resume.
- **Nav IA (CEO 2026-08-12):** this is the **Settings → Credentials** surface in the Project-rooted nav
  (story 8.13). It is **not** the Configuration page (8.12) and **not** the fleet Dashboard's token-
  consumption widget (8.8e — that is *spend*, this is *auth health*). Scope-guarded against both below.
- **Testing:** `docs/bmad/05-testing-strategy.md` **§3.2/§3.3 Epic 8** (console read models behind the BFF
  authZ choke point, §6.7.2) and **§6.7** (RBAC matrix — per-project isolation, existence-hiding for
  out-of-scope entities). **§3.5/§6.7.8** responsive + RBAC×breakpoint.
- **Epics:** `docs/bmad/04-epics-and-stories.md` — Epic 8 header + the **8.6** row (`UX 05-credential-auth-
  state`, FR-F6; the CEO 2026-08-12 addendum: "Connect Claude" one-click OAuth + per-agent health
  *connected / refreshing / expired*, expired offers one-click re-login) and the **7.7** row (zero-touch
  lifecycle; health on console 8.6).
- **UX mock:** `docs/bmad/ux/images/05-credential-auth-state.*` (dark + light) — the per-agent table
  (**AGENT · RUNTIME · CREDENTIAL (Secret ref) · TOKEN · EXPIRES · STATUS · RUNS**), the
  "**Run #139 paused — token expired**" banner, the **Refresh token** (re-login) action, and the status
  chips **Valid / Expiring soon / Expired · paused**. Dark+light is a v1 requirement (story 8.9); responsive
  (§13.1/ADR-038).
- **Blocks / feeds:** consumed by the nav shell (8.13, Settings → Credentials route); shares the derived-
  health read pattern with the per-agent detail (8.11) and the rate-limit pause attribution (7.6, which adds
  a `Paused(rate_limited)` reason into the SAME surface).

## Acceptance Criteria

**AC1 — health is DERIVED from controller state + Run condition, never a console-owned store (C1).**
Given the credential controller's per-user Secret state (§5.2/§11.1) and the Run's condition (§7.4), When the
Credentials page is requested, Then each agent's health (*connected / refreshing / expired·paused*) is
**derived** from those existing sources — the controller's Secret expiry/validity + the `Paused` condition —
**not** a new "credential health" table, a duplicated status field the console writes, or a rollup job
(ADR-020). The console **shows** status; the controller **owns** refresh. A design that persists a second
copy of health that can drift from the controller has committed the defect.

**AC2 — the paused-on-expiry signal is explicit and actionable (the FR-F6 crux, C2).**
Given an Agent whose Run is `Paused(cred_expired)`, When the operator views credential state, Then the
console shows a **clear paused-on-expiry signal** — an explicit *expired · paused* status, the **reason**
(`cred_expired`), and the **one-click re-login remedy** ("Connect Claude" browser-OAuth / `ksquad auth login`
parity, 7.7) — mirroring mock `05` ("Run #139 paused — token expired" + **Refresh token**). It is **never**
rendered as a generic error, a blank cell, a silently-stuck Running, or an opaque failure. This is the read-
side mirror of 7.4's "never opaque" (P2): the same rule applies to `Paused(cred_invalid)` (7.3) and
`Paused(endpoint_unreachable)` (7.5), each with its own actionable remedy.

**AC3 — control-plane-mediated through the BFF (C3, §13/ADR-013).**
Given the credential read, When the console fetches it, Then it calls **one GET endpoint on the apiserver,
proxied by the Next.js BFF** under the same identity-aware choke point as every other read — the browser
**never** talks to the Go apiserver, kube, or Postgres directly, and holds no apiserver URL/credential. No
second authorization path is introduced (r21 single-surface rule — this surface passes the same §12.3
middleware).

**AC4 — scoped IN the assembly, existence-hiding (C4, the tenancy crux).**
Given the §12.3-resolved caller, When the credential view is assembled, Then the caller sees **only the
agents within their membership** — an out-of-scope principal's credential row (its agent, Secret ref,
expiry, status) **never enters the payload, its counts, or its structure** (existence-hiding; credentials
are **per-user** Secret refs, §11/ADR-010). An **`admin`** (`global_role=admin`) sees the fleet **"All
agents / ns: all"** view (bypass, as in mock `05`). Scoping is applied **while composing**, not post-
filtered.

**AC5 — health/reason METADATA only, never the credential material (C5, NFR-SEC3).**
Given the projection, When any field or observability span is produced, Then it carries the **Secret *ref***
(`secret://sam/hermes-oauth`), the **token *type*** (OAuth / API key / endpoint), the **expiry**, the
**status/reason**, and the **remedy** — the **token/secret *bytes* appear on NO field and NO span**
(NFR-SEC3/§17.1). Rendering health never requires reading the material.

**AC6 — read-only + the sanctioned OAuth re-login is the ONLY write (C6, §11.1 zero-touch).**
Given the credential surface, When it is rendered and interacted with, Then the **only** mutating affordance
is the **sanctioned browser-OAuth re-login handoff** ("Connect Claude" / one-click **Refresh token** on the
expired row) — there is **no** paste-token box, **no** edit/apply of a Secret in the console, **no** in-
console rotate. The operator **never types a token string** (§11.1/7.7). Everything else is read/navigate.
No claim/lease/kill/compose affordance exists here (those live in 8.2/8.4/8.5).

**AC7 — family-neutral health across all three credential families (C7, mirrors 7.4-P1).**
Given agents backed by the Claude-OAuth, second-runtime static-key, and BYO-Ollama-endpoint families
(§11/7.2/7.3/7.5), When the surface renders, Then it shows a **legible health state uniformly** for every
family — it does **not** special-case one vendor or leave a non-Claude agent with no status. The *refreshing*
state derives from the **leader-elected controller** (§5.2), not the console; a later-added runtime gets
health rendering "for free", exactly as it gets pause/resume for free in 7.4.

**AC8 — dark+light + responsive (v1, not polish).**
Given the Credentials screen, When it renders, Then it mirrors mock **`05-credential-auth-state`** in **both
dark and light** themes (story 8.9, WCAG AA both modes) and reflows in the **one responsive SSR tree**
across desktop/tablet/mobile (§13.1/ADR-038) — the per-agent table stays legible down to 360px with no
horizontal overflow (the STATUS chip + re-login action stay reachable). Presentation only — identical BFF
payload, same §12.3 wall at every width.

**AC9 — runnable falsification check (the scoping + derivation + no-leak core).**
Given the credential-state read model, When the self-contained check
`docs/bmad/spikes/bench/credential-auth-state-check.py` runs (stdlib-only, `python3` it directly, **no
console, no live cluster** — controller state + Run conditions fed by fixtures), Then it asserts C1-C7 with
teeth: it first proves the **FR-F6 anti-pattern** — a "raw-secrets admin panel" (reads a bespoke health
field, points the browser at the Go apiserver, shows every principal's row, prints the token bytes, hangs a
paste-token box, renders the expired Run as a generic error, only knows the Claude family) — is **DETECTED
as violating every invariant**, then proves the §11.1/§13 derived read model **violates nothing and actually
renders the owner an explicit paused-on-expiry signal with the re-login remedy while hiding the Secret
material + every out-of-scope principal's row, uniformly across all three families**. Baseline exits 0; each
`--mutate=<SHADOW_STORE|OPAQUE_EXPIRY|DIRECT_API|CROSS_PRIN|LEAK_MATERIAL|TOKEN_PASTE|FAMILY_SPECIAL>` flips
exactly the mapped invariant RED (exit 1) — the check fails if the anti-pattern stops violating (teeth lost)
or the conformant model ever violates an invariant.

## Tasks / Subtasks

- [x] **Task 0 — the runnable falsification check (AC9).** *Landed first — it is the executable contract the
  read model + console must match, no HTTP/console needed.* `docs/bmad/spikes/bench/credential-auth-state-
  check.py`: NAIVE raw-secrets-panel trips C1-C7 (teeth); CONFORMANT derived read model holds C1-C7; a
  mutation harness maps one defect → one invariant RED. Baseline exit 0; 7 mutants RED.
- [ ] **Task 1 — Credential-health read model `CredentialState(ctx, callerScope) (View, error)` (AC1, AC4,
  AC5, AC7).** *Do this next — the derivation/scoping/no-leak core, no HTTP/console.*
  - [ ] Derive per-agent health from the **controller Secret state** (§5.2/§11.1) + the **Run condition**
    (§7.4): `Paused(cred_expired|cred_invalid|endpoint_unreachable)` or an expired/invalid/unreachable
    controller state → *expired·paused* with the reason + remedy; controller mid-refresh → *refreshing*;
    else *connected*. **No new store, no console-owned health field** (ADR-020).
  - [ ] Apply the caller's **membership scope IN the assembly** (§12.1/§12.3): out-of-scope principals'
    rows never enter the result or its counts; `global_role=admin` → fleet bypass. Per-user Secret ref, §11.
  - [ ] Emit **the Secret ref + metadata only** — never the token bytes on any field or span (NFR-SEC3).
  - [ ] Render **every family** (claude-oauth/static-key/ollama-endpoint) uniformly over
    {connected, refreshing, expired-paused}.
- [ ] **Task 2 — GET endpoint `GET /api/v1/credentials` (AC1, AC3).**
  - [ ] Expose the read model as a **GET-only** route on the apiserver; confirm **no mutating verb** is
    routed on it (`POST`/`PATCH`/`DELETE` → `405`/absent). Empty scope → `200` with an empty payload.
- [ ] **Task 3 — RBAC + tenancy gate (AC4, AC3).**
  - [ ] Behind the §12.3 deny-by-default middleware: resolve caller → memberships/`global_role`, hand the
    resolved **scope** to Task 1 (handler never post-filters). Unauthenticated → `401`. If 15.4 is not yet
    mergeable, wire behind its interface and `skip` the RBAC integration test with `TODO(15.4)`; the Task-1
    core does not depend on it.
- [ ] **Task 4 — the sanctioned re-login handoff (AC2, AC6).**
  - [ ] Wire the expired row's **one-click "Connect Claude" / Refresh token** action to the **browser-OAuth
    login** owned by 7.7 (`ksquad auth login` CLI parity) — a redirect/handoff, **not** a token field. The
    surface exposes **no** paste-token/edit/rotate affordance.
- [ ] **Task 5 — Console screen + BFF proxy (AC2, AC6, AC8).** *If the Next.js console is not yet scaffolded,
  a thin BFF proxy stub + `TODO` is acceptable — the authoritative deliverables are the check (Task 0) + the
  Go read model + tests.*
  - [ ] Render the per-agent table mirroring mock `05`, the **paused-on-expiry banner + Refresh-token
    action** on a `Paused(cred_expired)` row, **read-only** otherwise, consuming the GET endpoint via the
    BFF.
  - [ ] Dark + light (8.9) + responsive reflow to 360px (§13.1/ADR-038). Empty/loading states per ADR-020.

## Dev Notes

- **Repo shape (current).** k8squad is the Go code repo; `pkg/auth/` and `pkg/coord/` already exist. Put the
  read model with the other **apiserver read models** — a small `pkg/credstate` (or fold into the existing
  apiserver read package) following the `pkg/overview`/`pkg/coord` conventions (`credstate.go` /
  `handler.go` / `*_test.go`, lowercase package, table-driven `_test.go`, standard `testing`). Do **not**
  introduce a new store or binary — this is a **library read model in the existing apiserver**, exactly like
  the squad overview (8.1) and the dashboard read model (8.8a/ADR-020).
- **Derive, do not duplicate (AC1, the crux).** Health is a **function of** the controller's Secret state
  (§5.2/§11.1) and the Run condition (§7.4). The rejected shape is a second "credential health" table the
  console keeps in sync — it will drift, and a drifted *connected* over a truly-expired token is precisely
  the FR-F6 failure (the operator thinks they're fine while the Run is wedged). Same rejection as the
  dashboard aggregation service (ADR-020).
- **The paused-on-expiry signal is the whole point (AC2).** FR-F6's literal ask is that a `Paused(cred_
  expired)` Run is **legible** on this screen — status + reason + the one-click fix. This is the read-side
  twin of 7.4's "never opaque". If you find the expired state rendering as a generic error or a blank, the
  story has failed regardless of how pretty the table is.
- **Never the material (AC5).** Per-user Secret refs (§11/ADR-010) mean the *ref* is safe to show
  (`secret://sam/hermes-oauth`) but the *value* is not — health legibility never needs the token bytes.
  This is the same NFR-SEC3 wall as credential injection (5.4) and the pause signal (7.4-P6).
- **Zero-touch: no token typing (AC6).** §11.1/7.7 is emphatic — the operator connects once via browser
  OAuth and **never handles token strings**. So the console's only write is the OAuth re-login handoff; a
  paste-token/edit/rotate box would reintroduce exactly the manual-token toil ADR-032 removed. Read-only +
  one sanctioned OAuth handoff.
- **Credentials ≠ Configuration ≠ consumption (scope guard).** This is **Settings → Credentials** (auth
  *health*). It is **not** Configuration (8.12) and **not** the token-*consumption*/spend widget (8.8e). If
  you find yourself adding cost/spend or config editing here, stop — that is 8.8e / 8.12.
- **7.6 forward-compat.** The rate-limit pause (7.6) adds a `Paused(rate_limited)` reason with per-credential
  attribution into this SAME surface. Keep the reason→signal mapping family/reason-driven (as the check
  models it) so 7.6 slots in without a per-reason special-case.

### Project Structure Notes

- **Go (apiserver):** `pkg/credstate/` — `credstate.go` (the `CredentialState` derivation over controller
  Secret state + Run condition, scoped in-assembly, metadata-only), `handler.go` (GET route + `405` on other
  verbs), `credstate_test.go` (C1-C7 table: derived-not-stored, paused-on-expiry-legible, per-principal-
  absent, no-material, family-neutral, admin-bypass). Mirror `pkg/overview`/`pkg/coord` naming.
- **Runnable check:** `docs/bmad/spikes/bench/credential-auth-state-check.py` (Task 0, landed) — the stdlib
  falsification harness; baseline exit 0, 7 mutants RED.
- **No migration.** Controller Secret state (§5.2/§11.1) and Run conditions (§7.4) already exist. This story
  is a **new read path over existing state**, not a schema change — no new table, no new store.

### References

- [Source: docs/bmad/03-architecture.md#13] — screen 05 Credentials page; BFF choke point (browser never
  touches Postgres/kube, ADR-013); console read models pass the same §12.3 deny-by-default middleware (r21).
- [Source: docs/bmad/03-architecture.md#11 / #11.1] — per-user Secret refs (ADR-010); zero-touch credential
  lifecycle (connect once, never handle token strings); health derives from the credential controller's
  Secret state.
- [Source: docs/bmad/03-architecture.md#5.2] — the leader-elected credential controller (single refresher,
  ~8h token refresh, no per-pod race) — the `refreshing` state's source of truth.
- [Source: docs/bmad/03-architecture.md#7.2 / #7.4] — `credentialLifecycle` metadata; `Running → Paused →
  Running` machine; `Paused(cred_expired|cred_invalid|endpoint_unreachable)` reasons this surface renders.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8, story 8.6 + story 7.7] — UX `05-credential-auth-
  state`, FR-F6; "Connect Claude" one-click OAuth + per-agent health (connected/refreshing/expired), expired
  offers one-click re-login; health on console 8.6.
- [Source: docs/bmad/05-testing-strategy.md#3.2/#3.3/#6.7] — console read models behind the BFF authZ choke
  point; per-project isolation + existence-hiding RBAC matrix.
- [Source: docs/bmad/ux/images/05-credential-auth-state] — the per-agent credential table (AGENT · RUNTIME ·
  CREDENTIAL Secret-ref · TOKEN · EXPIRES · STATUS · RUNS), the "Run #139 paused — token expired" banner, the
  Refresh-token re-login action (dark + light).
- [Source: docs/bmad/stories/7-4-graceful-pause-resume-on-credential-expiry.md] — the family-neutral pause/
  resume state machine (P1 uniform, P2 never-opaque) this surface renders read-side.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (ISI-2269, heartbeat 2026-08-13)

### Debug Log References

- `python3 docs/bmad/spikes/bench/credential-auth-state-check.py` → baseline exit 0 (raw-secrets panel trips
  C1-C7; derived read model holds C1-C7).
- `--mutate=SHADOW_STORE` → C1 RED · `--mutate=OPAQUE_EXPIRY` → C2 RED · `--mutate=DIRECT_API` → C3 RED ·
  `--mutate=CROSS_PRIN` → C4 RED · `--mutate=LEAK_MATERIAL` → C5 RED · `--mutate=TOKEN_PASTE` → C6 RED ·
  `--mutate=FAMILY_SPECIAL` → C7 RED. Unknown mutant → exit 2.

### Completion Notes List

- Story authored + the runnable falsification check (Task 0) landed and green. C1-C7 map 1:1 to AC1-AC7;
  each has an independently load-bearing mutant (mutation-proof, ISI-2346-F1 vacuous-tooth class excluded).
- This story SURFACES 7.4's pause/resume state + 7.7's zero-touch controller; it owns no lifecycle, no store,
  no refresh — a derived read model, per ADR-020.
- Go read model (`pkg/credstate`, Tasks 1-3) + console screen (Task 5) remain for the k8squad code repo,
  gated on the same §12.3 middleware as every Epic-8 read surface (behind its interface if 15.4 unmerged).

### File List

- `docs/bmad/stories/8-6-surface-credential-auth-state.md` (new — this story)
- `docs/bmad/spikes/bench/credential-auth-state-check.py` (new — the C1-C7 falsification check, baseline exit
  0 + 7 mutants RED)
