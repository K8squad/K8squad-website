# Story 8.5: Compose CRDs — Team/Agent/Role/Skill/Project (the console compose surface — FR-F5, R6)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE COMPOSE (AUTHORING) SURFACE — and the SECOND write affordance in Epic 8.** Story 8.4
> (ISI-2267, **DONE**) introduced the first gated mutation — *one* declarative cancel intent through the BFF.
> 8.5 introduces the richest write in the console: a **stepper compose surface** for the five core kinds
> `{Team, Agent, Role, Skill, Project}` (create + edit) whose output is **valid CRs applied via the
> apiserver**. Every read surface (8.1 overview, 8.2 run-stream, 8.7 build-browser) is read-only; 8.4 added
> one gated mutation; **8.5 adds a gated *authoring* surface**. The load-bearing property is **not** "the form
> renders and a CR gets created" but that the form is a **thin producer of declarative CRs**: the apply is
> routed through the **BFF choke point** (never browser→kube), re-validated by the **same Story-1.3 server
> wall** as a raw `kubectl apply` (the console is not a second, looser validator), **gated by the same
> deny-by-default RBAC wall** as every other surface — a **write-tier** affordance (arch §12.3: `maintainer`,
> `admin`, **and** `contributor` compose CRDs in scope; only `viewer` is read-only) — with the credential
> bound as a **Secret ref, never an
> inline value**, and the console kept firmly **on the declarative side of R6**: a **CRD composer, not an IDE
> / code editor / dashboard**. A compose screen that ships its own validation the server never re-runs, POSTs
> straight at the apiserver, inlines the credential value, lets a `viewer` compose, drifts the
> YAML mirror from the applied CR, becomes a free-form code editor, or accepts arbitrary CRD kinds is a
> **security/correctness/scope regression against §13/§12.3/R6/Story 1.3**, not a cosmetic bug. Read AC3
> (declarative-not-an-IDE, R6), AC4 (RBAC write-tier gate) and AC5 (credential Secret-ref) literally.

## ⚠️ Scope reconciliation — 8.5 (the compose surface) vs 1.2/1.3 (CRD types + validation) vs 7.x (creds)

The originating issue (ISI-2268) says *"Given the compose screen, When I create/edit core CRDs, Then valid
CRs are applied via apiserver; And the console is NOT an IDE/code editor/dashboard (scope guard, R6)."* The
CRD *types*, their *validation*, and the *credential model* already exist — 8.5 does **not** re-invent them:

| Concern | Owned by | This story adds |
|---|---|---|
| The **six v1alpha1 CRD types** (`Team`/`Agent`/`Role`/`Skill`/`Project` + `AgentRuntime`) — schema, fields, `modelEndpointRef` | **Story 1.2** (ISI-2188, DONE) | — (composed, not re-defined) |
| The **CEL + ValidatingAdmissionWebhook validation** (same-object CEL, cross-object webhook, `failurePolicy: Fail`, open-ended runtime enum) | **Story 1.3** (ISI-2189, DONE) | — (the apiserver **re-runs** this on every compose apply; the console does **not** re-implement or weaken it) |
| The **per-user Secret-ref credential model** (`oauth`/`apiKey`/`byoEndpoint`, `secret://user/name`, no shared master) | **Epic 7** (7.1–7.5, DONE) + **Story 5.4 injection** (ISI-2216) | — (compose **binds a ref**; the value never enters the console) |
| The **BFF choke point** (browser→BFF→apiserver, never browser→kube) + **§12.3 deny-by-default RBAC** | **§13/ADR-013** + **8.4** (first mutating use) | the **compose** mutating verb behind the **same** wall, at the **write tier** (§12.3: maintainer/admin/contributor compose; viewer read-only) |
| The **compose (authoring) surface**: a ≤N-step stepper form + live read-only YAML mirror that produces valid CRs for the five core kinds, RBAC-gated, credential-ref-bound, applied through the BFF | **THIS STORY (8.5)** | the whole UI compose edge (§A/§B/§C below) |

**One-line boundary:** 1.2 answered *"what are the CRD shapes?"*, 1.3 answered *"how does the apiserver
reject an invalid CR?"*, Epic 7 answered *"how is a credential referenced without a shared master?"* This
story answers *"how does a squad author **compose** those CRs from the console — a declarative form whose
output is a valid CR applied through the BFF, gated by the same RBAC wall at the write tier (§12.3), with the
credential bound as a ref not a value — **without** the console becoming an IDE, re-validating in a looser
client path, or ever holding the secret value?"* The console **authors declarative intent**; the apiserver
validates and the reconciler acts.

## Story

As **a squad author (Sam, S3) building or editing a squad from the console**,
I want **a compose surface — a stepper form (`Project → Team → Agents → Roles & Skills → Review`) with a
live, read-only, `kubectl`-ready CRD YAML mirror — that lets me create and edit the five core CRDs
(`Team`/`Agent`/`Role`/`Skill`/`Project`) and applies the result as **valid CRs through the Next.js BFF →
apiserver**, where composing an Agent binds runtime + role + skills + a **credential Secret ref** (never an
inline value)**,
so that **I can author a whole squad declaratively without hand-writing YAML or touching `kubectl` — trusting
that the apiserver re-runs the same validation as a raw apply (an invalid CR is rejected by the server, not
just my form), that the form and the YAML are the same resource, and that the credential I bind is a
`secret://` ref KSquad never stores the value of — while a teammate who is only a `viewer`
on that Project never even sees the compose affordance (a `contributor` is write-tier and CAN compose, §12.3),
and the console stays a composition surface, not an IDE (R6).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-F5** (*"The console SHALL let a squad author **compose**
  `Team`/`Agent`/`Role`/`Skill`/`Project` resources (create/edit) — MVP, create/edit of core CRDs"* — the
  direct requirement), **§11.5 / R6 scope guard** (the console *"remains **not an IDE, not a code editor, and
  not a general dashboarding tool**"*), **FR-G1** (BYO per-user credential, never a shared master), **§9.15
  FR-AUTH5 / R19** (the console **adapts to role**: mutate affordances hidden where the user cannot act). The
  persona is **Sam (S3)** composing a squad *"no orchestration code, only CRDs"*.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§13 (console)** — the **BFF choke point** rule (browser never touches Postgres/kube; ADR-013); the
    console is a **legibility + composition** surface, **not an IDE**; console surfaces pass the **same §12.3
    deny-by-default middleware** (r21, *"one enforcement point, every surface"* — the compose mutation passes
    the **same** wall, no console-specific authz path).
  - **§5.1–§5.3 (CRD model) / §10.1 (Agent Card)** — the `Team`/`Agent`/`Role`/`Skill`/`Project` shapes the
    form composes; composing an Agent binds **runtime + role + skills + credential ref** (§10.3 model
    endpoint, §11 credential).
  - **§11 credential model (ADR-010/026/032)** — the credential is a **per-user Secret ref**
    (`secret://user/name`); the **value** is never held by the console, never in the YAML mirror, never in the
    CR spec (NFR-SEC3; Story 5.4 injection places the value at the runtime, out of every sink).
  - **§12.3 RBAC / §12.1 tenancy (per-project roles, ADR-033/035)** — compose is a **write-tier** mutate
    affordance: `maintainer` (per-project), `admin` (global), **and** `contributor` compose CRDs in scope —
    arch §12.3 grants `contributor` *"compose (create/edit CRDs, start/kill Runs)"* (`03-architecture.md:161`,
    `:1485-1487`); the maintainer↔contributor delta is **Project membership/settings administration**, NOT
    CRD composition. Only **`viewer`** is read-only (no compose affordance). The server **re-checks every
    call**. Out-of-scope Projects are **existence-hidden**. *(NB: arch §12.3 is authoritative here. The epics
    prose enumeration "Story 15.3" (`04-epics-and-stories.md:716`) omits contributor-compose and is looser;
    where they conflict §12.3/ADR-035 governs — see remediation ISI-2461. There is no arch §15.3: arch §15 is
    the Coordination-Spine risk section.)*
  - **ADR-002 (desired-state reconciliation)** — compose applies **declarative** CRs the reconciler observes;
    the console never executes/orchestrates. **ADR-013** (Next.js BFF vs SPA-direct-to-kube).
- **CRD validation (Story 1.3, ISI-2189, DONE):** the apiserver enforces **CEL (same-object)** + a
  **`ValidatingAdmissionWebhook` (cross-object existence)** with **`failurePolicy: Fail`** (fail-closed) and
  an **open-ended runtime enum** (FR-D3). The compose apply passes through the **same** admission chain as a
  raw `kubectl apply` — the console re-uses the server's validation, it does **not** re-implement a looser
  one. A client-side check is a **UX affordance** (inline hints), never the enforcement point.
- **Credential model (Epic 7, DONE):** 7.1 per-user Secret refs, 7.2 Claude OAuth, 7.3 second-runtime
  API-key, 7.5 Ollama/BYO endpoint; **Story 5.4 (ISI-2216)** injection — `secretRef` never inline, value in
  **no** sink (NFR-SEC3). Compose **binds the ref**; it never accepts or stores the value.
- **Testing:** `docs/bmad/05-testing-strategy.md` **§3.2/§3.3 Epic 8** (console surfaces behind the BFF authZ
  choke point) and **§6.7** (RBAC matrix — per-project isolation, **mutate-affordance hiding** for
  non-actors, existence-hiding). **§3.5/§6.7.8** responsive + RBAC×breakpoint.
- **UX mock:** `docs/bmad/ux/README.md §3.4` + `docs/bmad/ux/images/04-compose-crd.*` — the stepper
  (`Project → Team → Agents → Roles & Skills → Review`) with a **split view**: a **form** on the left and a
  **live, read-only CRD YAML mirror** on the right (`kubectl`-ready, the just-added Agent highlighted). The
  form and the YAML are declared to be **the same resource**. Credential is a **per-user Secret ref**
  (`secret://sam/hermes-oauth`) with a live-valid dot (FR-G1, BYO). Responsive matrix row: *"Compose CRD
  (8.5): form single-column stack, fields full-width, sticky apply bar; ≥44px inputs/selects; no hover-only
  help text (tap/focus reveals)."* Dark+light (8.9).
- **Depends on:**
  - **Story 1.2** (ISI-2188, DONE) — the CRD types the form composes.
  - **Story 1.3** (ISI-2189, DONE) — the CEL + webhook validation the apiserver re-runs on every compose
    apply. Hard dependency for AC1 ("valid CRs applied via apiserver").
  - **Epic 7** (DONE) + **Story 5.4** (ISI-2216) — the per-user Secret-ref credential model / injection AC5
    binds against.
  - **§12.3 deny-by-default middleware (Epic 15.4)** — resolves the caller → per-project role for the
    maintainer gate. If not yet mergeable, wire the compose handler behind its interface and gate the RBAC
    integration test with `TODO(15.4)`; the **authorization-decision + CR-build/apply core does not depend on
    the console** and must be fully implemented and tested with an injected caller-scope.
  - **8.4** (ISI-2267, DONE) — the **template** for a gated console mutate affordance (BFF choke point,
    affordance-hiding, server re-check). 8.5 follows the same mutate-gate shape at the write tier (§12.3 —
    affordance hidden from `viewer` only; `contributor` composes).
- **Blocks / feeds:** delivers the **FR-F5** console guarantee. It is the compose surface **8.12** (Settings
  → OTelConfig compose) and **8.15** (Users & Roles admin) point back to as *"a compose surface like 8.5"*;
  **8.10** (team-org diagram, read-only) explicitly defers edit to 8.5. Composed CRs feed every downstream
  Run (a composed `Team`/`Agent` is what the reconciler runs).

## The compose surface — declarative CRs through the BFF (authoritative — §A)

**A stepper that produces valid CRs (FR-F5 / UX §3.4).** The author walks
`Project → Team → Agents → Roles & Skills → Review` in a **split view**: a **form** on the left, a **live,
read-only, `kubectl`-ready CRD YAML mirror** on the right. The form and the YAML are **the same resource** —
an author can read either; the YAML is a **legibility mirror**, not a second editable buffer. On **Review →
Apply**, the console fires the apply for each composed CR.

**Valid CRs applied via the apiserver, server-re-validated (FR-F5, Story 1.3).** The apply lands each CR at
the **apiserver**, which re-runs the **same admission chain** (Story 1.3 CEL + `ValidatingAdmissionWebhook`,
`failurePolicy: Fail`) as a raw `kubectl apply`. The console's inline field validation is a **UX affordance**
(fast feedback), **never** the enforcement point: a forged/invalid CR that skips the form check is still
**rejected by the server**. There is **no** second, looser console validation path — the console is a
**producer**, the apiserver is the **validator**.

**Through the BFF, never browser→kube (§13/ADR-013).** The mutating apply terminates at the **Next.js BFF**,
which proxies the Go apiserver under the identity-aware choke point — the **mutating twin** of every read
surface. The browser **never** applies the CR against the Go apiserver, kube, or Postgres directly, and the
compose passes the **same** §12.3 wall as every other surface (r21 — no console-specific authz path).

**Declarative CRs, not an IDE (R6, ADR-002).** The compose surface authors **declarative CRs** and applies
them — the reconciler acts. It does **not** edit orchestration code, **not** execute/run anything, **not**
open a free-form code editor, and **not** become a general dashboard. The console is a **composition surface,
not an IDE** (R6 / PRD §11.5). *"No orchestration code, only CRDs"* (S3).

## The RBAC mutate-gate — the crux (authoritative — §B, arch §12.3/8.16)

Compose is a **write-tier** mutate affordance. Arch §12.3 (ADR-033/035 — the single authoritative
authorization wall, *"one enforcement point, every surface"*, r21) defines the per-project roles:
**`contributor`** is *"project-scoped write … may act and **compose (create/edit CRDs, start/kill Runs)** and
read, but **cannot** administer the Project's membership/settings"* (`03-architecture.md:1485-1487`; `:161`).
The **only** role that cannot compose is **`viewer`** (read-only). The maintainer↔contributor delta is
**membership/settings administration**, NOT CRD composition:

- **`viewer`** (per-project) → **no compose affordance at all**: the compose entry is **absent from the DOM**
  (not `display:none` — trivially re-enabled client-side, §9.15/8.16), **and** the API **denies** a compose
  call if one is forged. `viewer` is the read-only tier (dashboards/Runs/build browser), never a writer.
- **`contributor`**, **`maintainer`** (per-project), and **`admin`** (`global_role=admin` fleet bypass) →
  compose **any** core kind in scope. `contributor` is **write-tier** (§12.3): it composes/edits the five
  core CRDs and starts/kills Runs; it simply cannot administer the Project's membership/settings (that is the
  `maintainer`/`admin` delta, out of 8.5's compose scope).
- **Out-of-scope Projects are existence-hidden** — a Project the caller has no membership in is not visible
  and not composable (the compose decision returns deny **before** revealing existence, §12.3).
- **The server re-checks every call.** The affordance-hiding is a legibility layer **over** the §12.3
  enforcement — the API re-resolves membership on **every** compose call and never trusts a client-asserted
  role (§9.15/8.16). A design that trusts the client's role claim (so hiding the entry is the only guard) is
  the classic broken-access-control regression.

## Credential ref, YAML-mirror fidelity, five kinds (authoritative — §C)

- **Credential is a Secret ref, never an inline value (NFR-SEC3 / §11, Story 5.4).** Composing an Agent binds
  runtime + role + skills + a **per-user Secret ref** (`secret://user/name`, with a live-valid dot, FR-G1).
  The credential **value** is **never** entered into the form, **never** rendered in the YAML mirror, **never**
  written into the CR `spec`, and **never** sent in the apiserver payload — the CR carries a **ref**; Story
  5.4 injects the value at the runtime, out of every sink. An inline credential value in **any** sink is a
  secret-leak regression.
- **Form ≡ YAML mirror (UX §3.4).** The live read-only CRD YAML reflects **exactly** the CR the apply
  produces (`kubectl`-ready) — **no drift** between the form's intent and the applied CR. The mirror is a
  **read-only** legibility view (the author edits the form; the YAML follows), **not** an editable free-form
  code buffer (that would re-open R6).
- **Exactly the five core kinds, create + edit, declarative (FR-F5).** Compose covers **exactly**
  `{Team, Agent, Role, Skill, Project}`, **create + edit** — it is **not** a general editor for arbitrary CRD
  kinds (no `Run`, no `ConfigMap`, no raw-YAML apply of anything typed). **Edit** is a **declarative CR
  revision** applied through the apiserver (a new revision the reconciler observes — Project goal-versioning
  §3.6 / ADR-002), **not** an imperative out-of-band patch.

## Acceptance Criteria

**AC1 — compose produces valid CRs applied via the apiserver, server-re-validated (FR-F5, Story 1.3).**
Given the compose surface, When the author applies a composed `Team`/`Agent`/`Role`/`Skill`/`Project`, Then
the CR is applied at the **apiserver**, which re-runs the **same** Story-1.3 admission chain (CEL +
`ValidatingAdmissionWebhook`, `failurePolicy: Fail`) as a raw `kubectl apply` — an **invalid** CR is
**rejected by the server** (surfaced never-opaquely in the form), not merely by a client-side check. The
console's inline validation is a UX affordance, **not** a second/looser enforcement path (the console is a
producer; the apiserver is the validator).

**AC2 — the compose apply goes through the Next.js BFF, never browser→kube (§13/ADR-013).**
Given Review → Apply, When the console applies the CRs, Then each apply is a mutating call to the **Next.js
BFF**, which proxies the Go apiserver under the same identity-aware choke point as every other surface — the
browser **never** calls the Go apiserver, kube, or Postgres directly (the mutating twin of the read surfaces).
No second/console-specific authorization path is introduced (r21 — compose passes the same §12.3 wall).

**AC3 — the console composes DECLARATIVE CRs and is NOT an IDE/code editor/dashboard (R6, ADR-002).**
Given the compose surface, When the author works, Then it composes **declarative CRs** and applies them (the
reconciler acts, ADR-002) — it does **not** edit orchestration code, **not** execute/run anything, and **not**
present a free-form code editor or a general dashboard. The console stays a **composition surface, not an
IDE** (R6 / PRD §11.5). *"No orchestration code, only CRDs."*

**AC4 — compose is a WRITE-tier mutate affordance, affordance-hidden from viewer, server-enforced (the crux, arch §12.3/8.16).**
Given the §12.3-resolved caller, When the console renders and a compose is fired, Then: a **`viewer`** sees
**no** compose affordance (**absent from the DOM**, not `display:none`) **and** the API **denies** a forged
compose (viewer is read-only); a **`contributor`**, a **`maintainer`**, and an **`admin`** (fleet bypass) can
compose **any** core kind in scope (arch §12.3 grants `contributor` *"compose (create/edit CRDs, start/kill
Runs)"* — the maintainer↔contributor delta is membership/settings admin, not composition); an **out-of-scope**
Project is **existence-hidden** (not visible, not composable). The **server re-checks membership on every
call** and never trusts a client-asserted role — the affordance-hiding is a legibility layer **over** the
§12.3 enforcement (§9.15/8.16).

**AC5 — the credential is bound as a Secret ref, never an inline value (NFR-SEC3 / §11, Story 5.4).**
Given the author composes an Agent, When they bind its credential, Then the Agent CR references a **per-user
Secret ref** (`secret://user/name`, live-valid dot, FR-G1) — the credential **value** is **never** entered
into the form, **never** shown in the YAML mirror, **never** written into the CR `spec`, and **never** placed
in the apiserver payload. The console holds a **ref**; the value stays out of every sink (Story 5.4 injects
it at the runtime). An inline credential value anywhere is a secret-leak regression.

**AC6 — the form and the live YAML mirror are the SAME resource; the mirror is read-only (UX §3.4).**
Given the split view, When the author edits the form, Then the live **`kubectl`-ready CRD YAML mirror**
reflects **exactly** the CR the apply produces — **no drift** between form intent and applied CR — and the
mirror is a **read-only** legibility view (the author edits the form; the YAML follows), **not** an editable
free-form code buffer. Two representations, one CR.

**AC7 — exactly the five core kinds, create + edit, declarative (FR-F5 scope).**
Given the compose surface, When the author composes, Then it covers **exactly**
`{Team, Agent, Role, Skill, Project}`, **create + edit** — it is **not** a general editor for arbitrary CRD
kinds (no `Run`, no `ConfigMap`, no raw typed-YAML apply), and **edit** is a **declarative CR revision**
applied through the apiserver (reconciler-observed — §3.6 goal-versioning / ADR-002), not an imperative
out-of-band patch.

**AC8 — dark+light + responsive (v1, not polish).**
Given the compose surface, When it renders, Then it mirrors the mock (`04-compose-crd`) in **both dark and
light** (story 8.9, WCAG AA both modes) and reflows per the responsive matrix (**form single-column stack,
fields full-width, sticky apply bar**; **≥44px** inputs/selects; **no hover-only** help text — tap/focus
reveals) in the one responsive SSR tree (§13.1/ADR-038) — no width at which the compose form overflows or a
control drops below the touch target.

**AC9 — runnable falsification (the compose-design core).**
Given the compose-CRD design, When `docs/bmad/spikes/bench/run-compose-crd-check.py` runs (stdlib-only, no
console, no cluster), Then it asserts **C1–C7** (valid CRs server-validated · BFF choke point · declarative
CRs not an IDE · RBAC write-tier gate [contributor composes, viewer read-only] · credential Secret-ref not
inline · form≡YAML mirror · five core kinds) over the design a console would ship: the **naive
raw-compose-editor** anti-pattern is **DETECTED** violating every invariant (real teeth), the **§13/FR-F5**
design violates none, and each **named guard** is **independently mutation-proven** — `--mutate=<SERVER_SKIP_
VALIDATION|CLIENT_ONLY_VALIDATION|DIRECT_API|CODE_EDITOR|EXECUTES|VIEWER_AFFORDANCE|NO_RECHECK|INLINE_SECRET|
YAML_DRIFT|EDITABLE_YAML|ARBITRARY_KIND|IMPERATIVE_EDIT>` flips the check **RED with exactly one violation**
(one arm per sub-guard — two arms each on C1/C4/C6/C7 — so no guard shadows another and the ISI-2346-F1
vacuous-tooth class is excluded by construction). Baseline exits 0; each of the 12 mutations exits 1.

## Tasks / Subtasks

- [ ] **Task 1 — Compose authorization + CR-build/apply core (AC1, AC2, AC4, AC5, AC7).** *Do this first — it
  is the mutate-gate + CR-producer core and needs no console.*
  - [ ] `AuthorizeCompose(ctx, callerScope, projectRef, kind) (bool, reason)`: resolve the caller →
    per-project role (arch §12.3); `maintainer`/`admin`/`contributor` (write-tier) → any core kind in scope,
    `viewer` → **deny** (read-only); out-of-scope → deny (existence-hidden); non-core kind → deny (AC7).
    **Re-checked server-side on every call**, never client-trusted (8.16). *(Compose is write-tier, not
    maintainer-only: §12.3 grants `contributor` compose; the maintainer delta is membership/settings admin.)*
  - [ ] `BuildCR(kind, formModel) (unstructured, error)`: build a **declarative** CR for one of the five core
    kinds from the composed form model. For an Agent, bind runtime + role + skills + **credential
    `secretRef`** — **never** an inline value (NFR-SEC3; reject/panic if a raw value is ever set). The built
    CR is byte-identical to the YAML mirror the console shows (AC6).
  - [ ] `ApplyCR(ctx, callerScope, cr)`: apply through the apiserver so the **Story-1.3 admission chain**
    runs (CEL + webhook, `failurePolicy: Fail`); **surface the server's rejection** verbatim (AC1). Do **not**
    re-implement/weaken validation client-side. **Edit** = a declarative revision apply (AC7), not an
    imperative patch.
  - [ ] Table-driven test: viewer-deny, contributor-any-allow, maintainer-any-allow, admin-bypass,
    out-of-scope-deny, non-core-kind-deny; invalid CR → server-rejected (not client-swallowed);
    credential-ref-only (a raw value in the model is rejected, never applied).
- [ ] **Task 2 — Compose mutating endpoint on the apiserver (AC1, AC2, AC4, AC7).**
  - [ ] Expose the compose as an authorized mutating verb (e.g. `POST /api/v1/projects/{p}/compose` or a
    kind-scoped apply) that calls `AuthorizeCompose` → `BuildCR` → `ApplyCR`. Unauthorized → `403`;
    unauthenticated → `401`; invalid CR → `422` **from the admission chain** (Story 1.3), not a bespoke
    console check; out-of-scope → `404` (existence-hiding); non-core kind → `400`/`422`.
- [ ] **Task 3 — RBAC mutate gate behind the §12.3 middleware (AC4).**
  - [ ] Route the endpoint behind the Epic 15.4 **deny-by-default middleware**; the handler receives the
    **resolved** caller-scope and never post-authorizes on a client claim. If 15.4 is not yet mergeable, wire
    behind its interface and `skip` the integration test with `TODO(15.4)`; the Task-1 core does not depend on
    the console.
- [ ] **Task 4 — Console compose surface + BFF proxy (AC1, AC2, AC3, AC5, AC6, AC8).** *If the Next.js
  console is not yet scaffolded, a thin BFF proxy stub + a `TODO` is acceptable — the authoritative
  deliverables are the Go core (Task 1) + the AC9 check.*
  - [ ] Build the stepper (`Project → Team → Agents → Roles & Skills → Review`) split view: **form** + **live
    read-only `kubectl`-ready YAML mirror** that is byte-identical to the applied CR (AC6). The mirror is
    **not** an editable code buffer; the surface is **not** an IDE/executor (AC3/R6).
  - [ ] Fire the apply through the **Next.js BFF** (never browser→apiserver/kube). Surface a server admission
    **rejection** verbatim in the form (AC1, never-opaque).
  - [ ] Bind the Agent credential as a **Secret ref** (`secret://user/name`, live-valid dot) — the value is
    **never** entered/shown/stored (AC5).
  - [ ] **Affordance-hide by role** (AC4): the compose entry is **absent from the DOM** for a `viewer`
    (8.16 — not `display:none`); a `contributor` is write-tier and **sees** the compose affordance (§12.3).
  - [ ] Dark + light (8.9) + responsive (single-column stack, sticky apply bar, ≥44px, no hover-only) to
    360px (§13.1/ADR-038).
- [ ] **Task 5 — Runnable falsification (AC9).** *(Already authored — keep green.)*
  - [ ] `docs/bmad/spikes/bench/run-compose-crd-check.py` — baseline exits 0; each `--mutate=NAME` exits 1
    with exactly one violation (12 mutations, C1–C7; one arm per sub-guard).

## Dev Notes

- **Repo shape (current).** k8squad is the Go code repo; `pkg/auth/`, `pkg/coord/`, and the CRD types
  (Story 1.2) + validation webhooks (Story 1.3) already exist. Put the compose authorization + CR-build/apply
  next to the other apiserver write paths (following `pkg/coord`/`pkg/auth` conventions — lowercase package,
  `*_test.go`, standard `testing`). Do **not** re-define the CRD types, re-implement the validation, or invent
  a new credential model — this story **composes** the existing types, **re-uses** the Story-1.3 admission
  chain, and **binds** the Epic-7 Secret-ref.
- **The crux is the write-tier gate, not the form (AC4).** Compose is the **second write affordance** in Epic
  8. Per arch §12.3 (ADR-033/035, the authoritative wall) a `contributor` is **project-scoped write** and
  **can** compose CRDs (as it can kill Runs); the **only** role denied compose is `viewer` (read-only). The
  maintainer↔contributor delta is **membership/settings administration**, not composition — so 8.5's gate
  hides the affordance from **`viewer` only**. Mirror the 8.4 mutate-gate shape (BFF choke point,
  affordance-hidden from viewer, server re-checks every call). A `viewer` who forges a compose call must be
  **denied by the API** — that is the `VIEWER_AFFORDANCE`/`NO_RECHECK` mutation-proven tooth. *(Do NOT gate
  compose to maintainer-only: that inverts §12.3 and 403s a legitimately write-authorized `contributor` — the
  ISI-2461 regression. The looser epics-Story-15.3 prose is not authoritative; a genuine maintainer-only
  policy would be a §12.3/ADR-035 change requiring Architect/CEO sign-off, not a story-level assertion.)*
- **Valid CRs = the server's job, not the form's (AC1).** The apiserver re-runs the **same** Story-1.3
  admission chain as a raw `kubectl apply`. The console's inline validation is a UX nicety for fast feedback;
  it is **never** the enforcement point (a forged/invalid CR that skips it is still server-rejected). Do
  **not** ship a bespoke, drift-prone client validator that the server never re-runs (the
  `CLIENT_ONLY_VALIDATION` mutation covers that regression).
- **Declarative, not an IDE (AC3 / R6).** The whole action is *compose a declarative CR → apply → the
  reconciler acts*. The console never edits code, executes, or becomes a dashboard. If you find yourself
  building a free-form code editor or a "run this squad now" button, stop — that is the R6 scope creep the
  `CODE_EDITOR`/`EXECUTES` mutations detect. The YAML mirror is **read-only** (AC6).
- **The credential value never enters the console (AC5).** Compose binds a **Secret ref**; Story 5.4 places
  the value at the runtime, out of every sink. The value must never be in the form state, the YAML mirror,
  the CR spec, or the apiserver payload (the `INLINE_SECRET` mutation is exactly that leak).
- **Compose ≠ kill ≠ act (scope guard).** This story ships **only** the compose (authoring) surface for the
  five core kinds. It is **not** the kill affordance (8.4) and **not** a coordination/claim path (R6 — that
  stays server-side). Settings→OTelConfig (8.12) and Users&Roles (8.15) are **separate** compose/admin
  surfaces that reuse this pattern, not part of 8.5.

### Project Structure Notes

- **Go (apiserver):** compose authorization + CR build/apply next to the apiserver write paths —
  `AuthorizeCompose` (the per-project **maintainer** gate, server-re-checked) + `BuildCR` (the declarative CR
  producer, credential-ref-only) + `ApplyCR` (apply through the Story-1.3 admission chain) + `handler.go`
  (the mutating verb + status codes) + `*_test.go` (the AC-driven table). Mirror `pkg/coord`/`pkg/auth`
  naming and the standard `testing` idiom.
- **No new CRD, no new validator, no new credential model.** The five core CRD types (1.2), the CEL+webhook
  validation (1.3), and the per-user Secret-ref model (Epic 7 / 5.4) already exist. This story composes,
  re-validates through the server, and binds the ref — **no** new store, **no** CRD-shape change, **no**
  console-side validation authority.
- **BFF/console:** the Next.js console may not yet be scaffolded; the Go core + AC9 check land here
  regardless (Task 4 note). The console fires the apply through the BFF proxy and renders the read-only YAML
  mirror byte-identical to the applied CR.
- **Runnable check:** `docs/bmad/spikes/bench/run-compose-crd-check.py` (authored) — stdlib-only, differential
  over the compose-CRD design, 10 mutations covering C1–C7.

### References

- [Source: docs/bmad/02-prd.md — FR-F5 / §11.5 R6 / FR-G1 / §9.15 FR-AUTH5] — console composes
  `Team`/`Agent`/`Role`/`Skill`/`Project` (create/edit of core CRDs); console remains **not an IDE/code
  editor/dashboard** (R6); BYO per-user credential; role-adaptive console hides mutate affordances.
- [Source: docs/bmad/03-architecture.md#13] — BFF choke point (browser never touches apiserver/kube/Postgres,
  ADR-013); console is a legibility + **composition** surface, not an IDE; same §12.3 deny-by-default
  middleware (r21 "one enforcement point, every surface").
- [Source: docs/bmad/03-architecture.md#5.1–5.3 / #10.1 / #10.3 / #11] — the CRD model the form composes;
  Agent binds runtime + role + skills + credential ref; per-user Secret-ref credential model (ADR-010/026/032).
- [Source: docs/bmad/03-architecture.md#12.3/#12.1 (ADR-033/035), lines 161 + 1483-1490] — per-project roles:
  maintainer/admin/**contributor** (write-tier) compose any core kind in scope — §12.3 grants `contributor`
  *"compose (create/edit CRDs, start/kill Runs)"*; only **viewer** is read-only; server re-checks every call;
  out-of-scope existence-hidden. The maintainer↔contributor delta is membership/settings admin, not
  composition. *(There is no arch §15.3; the epics prose "Story 15.3" (`04-epics-and-stories.md:716`) is
  looser and non-authoritative where it conflicts — ISI-2461.)*
- [Source: docs/bmad/03-architecture.md ADR-002 / ADR-013] — desired-state reconciliation (declarative CRs,
  not imperative execution); Next.js BFF vs SPA-direct-to-kube.
- [Source: docs/bmad/stories/1-3-crd-validation-defaulting-webhooks.md] — the CEL (same-object) + webhook
  (cross-object) validation with `failurePolicy: Fail` that the apiserver re-runs on every compose apply.
- [Source: docs/bmad/stories/5-4-*credential-injection* / Epic 7 stories] — per-user Secret-ref, value in no
  sink (NFR-SEC3); compose binds the ref, never the value.
- [Source: docs/bmad/stories/8-4-kill-a-run-in-two-clicks.md] — the template for a gated console mutate
  affordance (BFF choke point, affordance-hidden, server re-checks every call); compose follows it at the
  write tier (§12.3 — affordance hidden from `viewer` only; `contributor` composes).
- [Source: docs/bmad/ux/README.md §3.4 + images/04-compose-crd] — the stepper + split-view form/YAML mirror
  (same resource, kubectl-ready), credential as `secret://` ref; responsive matrix "Compose CRD (8.5)".
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8, story 8.5 + the responsive matrix "Compose CRD (8.5):
  form single-column stack … sticky apply bar; ≥44px inputs/selects; no hover-only help text"] — FR-F5; R6
  scope guard.

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

- `docs/bmad/spikes/bench/run-compose-crd-check.py` — baseline exits 0; `--mutate=<SERVER_SKIP_VALIDATION|
  CLIENT_ONLY_VALIDATION|DIRECT_API|CODE_EDITOR|EXECUTES|VIEWER_AFFORDANCE|NO_RECHECK|INLINE_SECRET|YAML_DRIFT|
  EDITABLE_YAML|ARBITRARY_KIND|IMPERATIVE_EDIT>` each exits 1 with exactly one violation (C1–C7; one arm per
  sub-guard — ISI-2461 remediation: dropped `CONTRIB_COMPOSE` [not a defect], re-pointed `CLIENT_ONLY_
  VALIDATION`→client-only guard, added `SERVER_SKIP_VALIDATION`/`EDITABLE_YAML`/`IMPERATIVE_EDIT`).

### Completion Notes List

### File List

- `docs/bmad/stories/8-5-compose-crds.md` (this story)
- `docs/bmad/spikes/bench/run-compose-crd-check.py` (runnable falsification, AC9)
