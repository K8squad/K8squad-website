# Story 8.1: Squad overview screen (Teams → Projects → Run status, no `kubectl`)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **This is the operator's first legibility surface: "what squads exist, what are they working on, and what
> is running right now" — answered without `kubectl` (S2).** It is a **pure read model, coordination-free by
> construction** (R6): it composes the Team → Project → Run-status hierarchy from the **apiserver
> informer/lister cache** (CRD-backed `Team`/`Project`/`Agent`, §5.1) + **Run/claim state** (§6/§8) and
> streams live status over the **existing SSE progress bus** — it adds **no new store, no aggregation
> service, and no mutation** (ADR-020, ADR-013). Read every AC literally: an overview payload that returns a
> Team/Project/Run the caller is **not** scoped to (leaked existence), or any affordance that lets the
> browser reach kube/Postgres directly, is a **security/tenancy regression** against §12.3/§13, not a
> cosmetic bug.

## Story

As an **operator opening the console**,
I want a **squad overview** that shows **all my Teams, each Team's Projects, and the live Run status under them** — a three-level read-only hierarchy assembled by the control plane and delivered through the Next.js BFF,
so that **I can see what every squad is working on and what is running right now at a glance, without `kubectl` (S2)** — a legibility surface, never a coordination or edit path.

## Context & prerequisites (read first)

- **Architecture:** `docs/bmad/03-architecture.md` **§13** (console — the "Screens (FR-F1…F6): squad overview (Teams→Projects→Run status)" bullet; the **BFF choke point** rule — browser never touches Postgres/kube; the **Live Run progress via SSE** bullet — `EventSource` over the apiserver progress bus fed by shim A2A-SSE); **§13 console read models** are the same **deny-by-default middleware** wall (r21, "one enforcement point, every surface" — console read models pass the *same* §12.3 check, no per-surface authz path); the **informer/lister cache** read pattern for CRD-backed entities (§ around the search-source description: "`Agent`/`Team`/`Role`/`Project` … live in etcd, not Postgres — searched via the apiserver's informer/lister cache (name + labels + spec summary), near-real-time, no projection table"). **§12.1** tenancy (Team → namespace 1:1; `project_id`/`team_id` scoping) and **§12.3** RBAC (caller → `auth.project_memberships` → allowed `project_id` set; `global_role=admin` fleet bypass; `viewer`/`contributor`/`maintainer` all *read* within a Project — visibility scopes on **membership**, not grade). **§6/§8** for Run/claim state (the `state`/`phase` + `Paused` condition the status chips derive from). **§4.4** SSE progress bus. **ADR-013** (Next.js BFF vs SPA-direct-to-kube), **ADR-020** (dashboard/read-model composition — no aggregation service, no rollup DB, per-tile/per-source graceful degradation).
- **Nav IA (CEO 2026-08-12):** the console is a **Project-rooted hierarchy**; **"Overview (squad)" and "Dashboard (fleet)" are the two GLOBAL, non-project-scoped nav items** (story 8.13). This story is the **Overview** surface. It is **not** the fleet Dashboard (8.8 — KPI cards / consumption / pending-approvals / live-run map) and **not** the Team org diagram (8.10 — `Team → Agent → Role` org chart). Scope-guarded against both below.
- **Testing:** `docs/bmad/05-testing-strategy.md` **§3.2/§3.3 Epic 8** (console read models pass the **BFF authZ choke point**, §6.7.2) and **§6.7** (RBAC matrix — per-project isolation, existence-hiding for out-of-scope entities, adaptive-nav for non-admins). **§3.5/§6.7.8** responsive + RBAC×breakpoint (the overview reflows in the one responsive tree, ADR-038).
- **Epics:** `docs/bmad/04-epics-and-stories.md` — Epic 8 header + the **8.1** row (`UX 01-squad-overview`, FR-F1) and the nav-IA note (8.13: Dashboard + Overview stay global).
- **UX mock:** `docs/bmad/ux/images/01-squad-overview.*` (dark + light — the Team → Project → Run-status tree). Dark+light is a v1 requirement (story 8.9); responsive across desktop/tablet/mobile (§13.1/ADR-038).
- **Depends on:** the **apiserver** (Epics 2/3 — informer/lister cache over the CRDs + the Run/claim/coord state) and the **SSE progress bus** (§4.4, the same one 8.2 consumes). RBAC scoping uses the **§12.3 deny-by-default middleware** (Epic 15.4). If the identity middleware is not yet mergeable, wire the read model behind its interface and gate the RBAC integration test with `TODO(15.4)` — but the **scoped-assembly core (Task 1) does not depend on it** and must be fully implemented and tested with an injected caller-scope.
- **Blocks / feeds:** the nav shell (8.13) mounts this as the global **Overview** route; the org diagram (8.10) and per-Project dashboard (8.8) are siblings that reuse the same informer-cache + SSE read pattern.

## Acceptance Criteria

**AC1 — the read model: one composed Team → Project → Run-status payload.**
Given the apiserver, When the overview is requested, Then a **single read-model call** returns a **three-level hierarchy** — for each **Team** the caller can see: the Team's identity (name, namespace) and its **Projects**; for each **Project**: its identity (name, repo/ref summary) and the **Runs** under it with their **status** (the Run `phase`/`state` from §6/§8 plus the `Paused` condition/reason where present, §7.4). The payload is **composed from the sources that already exist** — CRD-backed `Team`/`Project`/`Agent` from the **apiserver informer/lister cache**, Run status from **Run/claim state (coord)** — **no new store, no rollup/projection table, no aggregation microservice** (ADR-020). It is assembled by the **control plane, never the browser**.

**AC2 — RBAC/tenancy scoped IN the assembly, never post-filtered (the crux).**
Given the §12.3-resolved caller, When the overview is assembled, Then the caller's **allowed `project_id` set** (from `auth.project_memberships`) and **`team_id` scope** (§12.1) are applied **while composing** the payload — a Team the caller has **no** membership in, a Project outside the allowed set, and any Run under an out-of-scope Project **never enter the payload, its counts, or its structure** (existence-hiding — the caller cannot infer the out-of-scope entity exists, §8.7d/§6.7). An **`admin`** (`global_role=admin`) sees the **fleet-wide** overview (bypass). Scoping is on **membership, not grade** — `viewer`, `contributor`, and `maintainer` all *see* the same Teams/Projects/Runs within their memberships (this screen has no write affordance to gate). **This is a scope-in-the-query property, asserted directly: an out-of-scope Team/Project/Run is structurally absent, not returned-then-hidden.**

**AC3 — strictly read-only, no `kubectl`, no-P2P (S2 + R6 scope guard).**
Given the overview surface, When it is rendered and interacted with, Then it exposes **read only** — **no** create/edit/apply, **no** claim/lease/dispatch/kill affordance, and **no** path by which the browser reaches kube or Postgres directly (every read flows through the apiserver/BFF choke point, §13/ADR-013). The operator gets the full "what squads exist and what is running" picture **without `kubectl`** (S2) and the surface **cannot** be turned into a coordination channel (compose/edit stays 8.5; kill stays 8.4; claim/lease stays server-side §6). No mutating verb exists on the overview route.

**AC4 — live status over the EXISTING SSE bus (no new transport, no polling).**
Given a Running/Paused/finishing Run under a visible Project, When its status changes, Then the overview's Run-status indicators **update live over the existing SSE progress bus** (§4.4, the **same** `EventSource` / BFF proxy as the Run stream 8.2 and the org diagram 8.10) — **no new transport, no bespoke stream, no client polling loop**. The live channel carries **only** entities within the caller's scope (AC2 applies to the stream too — a status event for an out-of-scope Run is never delivered to this client).

**AC5 — per-source graceful degradation (never a whole-screen failure).**
Given the composed read model, When one source is unavailable or empty (e.g. the informer cache is warming, a Team has zero Projects, a Project has zero Runs, or Run-state is momentarily unreadable), Then the affected node degrades to a **legible empty/loading state** (empty Team, "no projects", "no active runs") — the rest of the overview still renders. A partial-source failure **never** collapses the whole screen (ADR-020 per-tile/per-source degradation), and an empty scope (a caller with no memberships) renders an explicit empty state, **not** an error.

**AC6 — control-plane-mediated through the BFF (§13/ADR-013).**
Given the overview read, When the console fetches it, Then it calls **one GET endpoint on the apiserver, proxied by the Next.js BFF** under the same identity-aware choke point as every other read — the browser **never** talks to the Go apiserver, kube, or Postgres directly. The SSE live channel (AC4) rides the **same** BFF proxy. No second authorization path is introduced (r21 single-surface rule — the overview passes the same §12.3 middleware).

**AC7 — dark+light + responsive (v1, not polish).**
Given the overview screen, When it renders, Then it mirrors mock **`01-squad-overview`** in **both dark and light** themes (story 8.9, WCAG AA both modes) and reflows in the **one responsive SSR tree** across desktop/tablet/mobile (§13.1/ADR-038) — the Team→Project→Run tree stays legible down to 360px with no horizontal overflow and touch-parity targets. (Presentation only — identical BFF payload, same §12.3 wall, same one SSE bus at every width.)

**AC8 — runnable read-model test (the scoping + composition core).**
Given the overview read-model function behind the endpoint, When a self-contained Go test exercises it (table-driven, **no console, no live cluster** — informer/lister and Run-state fed by fakes/fixtures), Then it asserts: (a) a caller with membership in Teams {A,B} but not C gets a payload containing **A and B only** — **C, its Projects, and its Runs are structurally absent** (AC2 existence-hiding), including from any count; (b) each returned Project carries its Runs with the correct **status** derived from Run/claim state, incl. a **`Paused`** Run showing its reason (§7.4); (c) an **`admin`** caller gets **all** Teams (fleet bypass); (d) a caller with **no** memberships gets an **empty** payload, not an error (AC5); (e) an unavailable/empty source degrades **that node only** (empty Projects/Runs) without failing the whole assembly (AC5). The test lives next to the read-model implementation and fails if the scoping or composition logic breaks.

## Tasks / Subtasks

- [ ] **Task 1 — Overview read model `SquadOverview(ctx, callerScope) (Overview, error)` (AC1, AC2, AC5, AC8).** *Do this first — it is the scoping/composition core and needs no HTTP/console.*
  - [ ] Compose the Team → Project → Run-status tree: read CRD-backed `Team`/`Project` (and `Agent` where the mock shows squad membership) from the **apiserver informer/lister cache** (§13 read-model pattern — no projection table); read Run status from **Run/claim state** (§6/§8), including the `Paused` reason (§7.4).
  - [ ] Apply the caller's **allowed `project_id` set + `team_id` scope IN the assembly** (§12.1/§12.3) — out-of-scope Teams/Projects/Runs never enter the result or its counts; `global_role=admin` → fleet bypass. **Scope-in-the-composition, not post-filter.**
  - [ ] Degrade per-source: a warming cache / empty Team / empty Project / unreadable Run-state yields an empty node, never a whole-assembly error (ADR-020). Empty scope → empty payload.
  - [ ] Add the table-driven test (AC8) incl. the **out-of-scope-Team-absent** case (a→C absent), the `Paused`-status case, the admin-bypass case, the empty-scope case, and the per-source-degradation case.
- [ ] **Task 2 — GET endpoint `GET /api/v1/overview` (AC1, AC3, AC6).**
  - [ ] Expose the read model on the apiserver as a **GET-only** route; confirm **no mutating verb** is routed on it (`POST`/`PATCH`/`DELETE` → `405`/absent). Return the composed payload; empty scope → `200` with an empty payload (not `403`/`404`).
- [ ] **Task 3 — RBAC + tenancy gate (AC2, AC6).**
  - [ ] Behind the Epic 15.4 **deny-by-default middleware**: resolve the caller → memberships/`global_role`, hand the resolved **scope** to Task 1 (never let the handler post-filter). Unauthenticated → `401`. The overview is read-visible to any authenticated caller *within their scope* (no grade gate — AC2). If 15.4 is not yet mergeable, wire behind its interface and `skip` the RBAC integration test with `TODO(15.4)`; the Task-1 core does not depend on it.
- [ ] **Task 4 — Live status over SSE (AC4, AC6).**
  - [ ] Subscribe the overview's Run-status indicators to the **existing SSE progress bus** (§4.4) via the **same BFF proxy** as 8.2 — status transitions update in place; the stream is **scope-filtered** (an out-of-scope Run event is never delivered). No new transport, no polling.
- [ ] **Task 5 — Console screen + BFF proxy (AC1, AC3, AC6, AC7).** *If the Next.js console is not yet scaffolded, a thin BFF proxy stub + a `TODO` is acceptable — the authoritative deliverables are the Go read model + AC8 test.*
  - [ ] Render the three-level **Team → Project → Run-status** tree mirroring mock `01-squad-overview`, **read-only** (no compose/claim/kill affordance — those live in 8.5/8.4), consuming the GET endpoint via the Next.js BFF and the SSE bus for live status.
  - [ ] Dark + light (8.9) + responsive reflow to 360px (§13.1/ADR-038). Empty/loading states per AC5.

## Dev Notes

- **Repo shape (current).** k8squad is the Go code repo; `pkg/auth/` and `pkg/coord/` already exist (ISI-2311 / Epic 2). Put the read model with the other **apiserver read models** — a small `pkg/overview` (or fold into the existing apiserver read package) following the `pkg/coord`/`pkg/auth` conventions (`overview.go` / `handler.go` / `*_test.go`, lowercase package, table-driven `_test.go`, standard `testing`). Do **not** introduce a new test framework or a new binary — the overview is a **library read model in the existing apiserver**, exactly like `pkg/search` (§17.5) and the dashboard read model (8.8a/ADR-020).
- **Informer cache, not a projection table.** `Team`/`Project`/`Agent` are CRDs in **etcd** — read them through the apiserver's **informer/lister cache** (near-real-time, low cardinality), **not** a Postgres projection. Run status comes from **Run/claim state (coord + Run CRD `status.phase`)**. This composition is the whole story — **do not** build a new "overview" datastore or a rollup job (ponytail/ADR-020; the same rejection as the dashboard aggregation service).
- **Scope in the assembly is the crux (AC2/AC8).** The load-bearing property is **existence-hiding**: an out-of-scope Team/Project/Run must be **structurally absent** from the payload, counts included — never returned-then-hidden by the UI. This is the **same deny-by-default wall** as every other console read model (r21 "one enforcement point, every surface"); there is **no** overview-specific authz path. Mirror the `pkg/search` rule — scope predicate injected **before** results are built, not a post-filter (which would leak existence via counts/latency).
- **Overview ≠ Dashboard ≠ org diagram (scope guard).** This is the **squad Overview** (Team → **Project** → Run-status, the *work* dimension, global). It is **not** the fleet **Dashboard** (8.8 — KPI cards, consumption/cost, pending-approvals, live-run map) and **not** the **org diagram** (8.10 — Team → **Agent** → Role org chart with per-agent status badges). If you find yourself adding KPI tiles/cost or an agent-role org chart here, stop — that is 8.8 / 8.10. Overview answers "which squads, working on which projects, with what running".
- **No `kubectl`, no side door (AC3/AC6).** The entire value (S2) is that the operator never touches `kubectl`. Correspondingly the browser never touches kube/Postgres — one GET through the BFF choke point (§13/ADR-013), SSE over the same proxy. Read-only, no-P2P: this surface can never become a coordination channel (compose=8.5, kill=8.4, claim/lease=server-side §6).
- **SSE reuse (AC4).** Live status rides the **existing** progress bus (§4.4) the Run stream (8.2) and org diagram (8.10) already use — a single `EventSource`, scope-filtered. Do **not** stand up a new stream or a polling loop.

### Project Structure Notes

- **Go (apiserver):** `pkg/overview/` — `overview.go` (the `SquadOverview` composition over the informer/lister cache + Run/claim state, scoped in-assembly), `handler.go` (the GET route + `405` on other verbs), `overview_test.go` (AC8 table: out-of-scope-absent, Paused-status, admin-bypass, empty-scope, per-source-degradation). Mirror `pkg/coord`/`pkg/search` naming and the standard `testing` idiom.
- **No migration.** CRDs (`Team`/`Project`/`Agent`) live in etcd (informer cache); Run/claim/coord state already exists (Epic 2/3). This story is a **new read path over existing state**, not a schema change — no new table, no new store.
- **BFF/console:** the Next.js console app may not yet be in the repo; the Go read model + AC8 test land here regardless (see Task 5). The console screen consumes the GET endpoint + SSE via the BFF proxy.

### References

- [Source: docs/bmad/03-architecture.md#13 console] — "Screens (FR-F1…F6): squad overview (Teams→Projects→Run status)"; BFF choke point (browser never touches Postgres/kube, ADR-013); Live Run progress via SSE (`EventSource` over the apiserver progress bus fed by shim A2A-SSE); console read models pass the same §12.3 deny-by-default middleware (r21 "one enforcement point, every surface").
- [Source: docs/bmad/03-architecture.md#13/§17.5 informer cache] — CRD-backed `Agent`/`Team`/`Role`/`Project` live in etcd, read via the apiserver informer/lister cache (near-real-time, no projection table); RBAC scope applied **in the query** (allowed `project_id` set + `team_id` scope), existence-hiding for out-of-scope entities (§8.7d).
- [Source: docs/bmad/03-architecture.md#12.1/#12.3] — Team→namespace tenancy; caller → `auth.project_memberships` → allowed `project_id` set; `global_role=admin` fleet bypass; membership (not grade) governs visibility.
- [Source: docs/bmad/03-architecture.md#4.4] — SSE progress bus (the single `EventSource` the console consumes).
- [Source: docs/bmad/03-architecture.md#18 ADR-013/ADR-020] — Next.js BFF vs SPA-direct-to-kube; read-model composition (no aggregation service, no rollup DB, per-source graceful degradation).
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8, story 8.1 + nav-IA note (8.13: Dashboard + Overview stay global)] — UX `01-squad-overview`, FR-F1.
- [Source: docs/bmad/05-testing-strategy.md#3.2/#3.3/#6.7] — console read models behind the BFF authZ choke point; per-project isolation + existence-hiding RBAC matrix; §3.5/§6.7.8 responsive + RBAC×breakpoint.
- [Source: docs/bmad/ux/images/01-squad-overview] — the Team → Project → Run-status tree mock (dark + light).

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
