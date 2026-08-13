# Story 8.10: Team-organization diagram (live squad org chart)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **A pure read model over the `Team`/`Agent`/`Role` CRDs — coordination-free, `Team`-scoped, no new
> backend.** The org diagram renders the `Team → Agent → Role` hierarchy read-only from the CRDs (§5.1),
> derives each Agent's live status (idle / running / blocked / paused) from **Run/claim state** (§6/§8) over
> the **existing SSE bus** (§4.4, same EventSource + BFF proxy as the Run stream 8.2), and click-through
> **deep-links** to the agent detail page (8.11). It has **no mutate/claim/reassign affordance** — the no-P2P
> lock applied to the console (§13 r10), and the R6 scope guard: this is a **legibility** surface, **not** a
> compose/edit view (that stays 8.5) and **not** a coordination path. A claim button, an editable node, a
> status stored/self-reported (rather than derived), a second transport/polling loop, or a click that
> dispatches instead of navigates is a **regression**. Read AC3, AC4, and AC5 literally.

## Story

As an **operator opening a Team's org diagram**,
I want **the `Team → Agent → Role` hierarchy rendered read-only from the CRDs, each Agent node showing its
real-time status (idle / running / blocked / paused), runtime type, and role badges, status streaming live
over the existing SSE bus, and clicking an Agent deep-linking to its detail page**,
so that **I can see the squad's structure and who is doing what at a glance — a coordination-free, `Team`-scoped
read model over existing CRDs + Run/claim state (FR-F8), no new backend and no way to drive an agent from the
diagram.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.6 **FR-F8** — the console SHALL provide a **team organization diagram**:
  a `Team → Agent → Role` org-chart view with **live per-Agent status** (idle / running / blocked / paused),
  **runtime-type and role badges**, and **click-through to the agent detail page** (FR-F9). A **pure read
  model** sourced from the `Team`/`Agent`/`Role` CRDs with live status derived from Run/claim state over the
  existing SSE bus, **`Team`-scoped**, and **coordination-free** (no mutate/claim affordance — the no-P2P lock
  applied to the console).
- **Architecture:** `docs/bmad/03-architecture.md` §13 **r10** — the org diagram folded into §13 as a squad
  org-chart view (`Team→Agent→Role` hierarchy, live per-Agent status, runtime + role badges, click-through).
  Designed as a **pure read model, coordination-free**: hierarchy from the `Team`/`Agent`/`Role` CRDs
  (read-only) via BFF, live status derived from **Run/claim state** (§6/§8) over the **existing SSE bus**,
  **`Team`-scoped** (§12.1), no mutate/claim affordance (no-P2P applied to the console). **No new CRD, no new
  data source.** Also §12.3 r20/r21 (the one deny-by-default RBAC wall), §5.1 (CRD types), §5.2
  (`Run.status.phase`), §5.3 (`AgentRuntime` runtime type), §4.4 (SSE hub).
- **Status derivation (§5.2 + Epic 7.4):** an Agent's live status is **derived**, not stored — from its
  current **`Run.status.phase`** (§5.2) plus the **`Paused` condition** (Epic 7.4, [[isi-2231-story74-pause-resume]]):
  `running` = an active Run in a running phase; `blocked` = a Run blocked/awaiting; `paused` = the `Paused`
  condition set; `idle` = no active Run. There is **no new status field, no new backend** — the diagram reads
  what Epic 2/3/7 already write.
- **Depends on:** the console read-model conventions established by **8.1** (squad overview: existence-hiding
  scoped read model) and **8.8a** (the one deny-by-default RBAC wall + the existing SSE snapshot/delta bus).
  The status-status derivation rides Epic 2/3 Run/claim state + Epic 7.4 `Paused`.
- **Click-through target:** the **agent detail page (8.11 / FR-F9)** — the deep-link is **navigation only** (a
  URL), never a coordination action. 8.11 is the click-through target (build owned by ISI-2162); until it
  lands, the node still deep-links to the agent-detail route (a real route, not a fabricated action).
- **Scope guard (R6):** this is a **read/legibility** surface. It is **not** the compose/edit view (that
  stays **8.5**) and **not** a coordination path. No mutate/claim/reassign/transition affordance anywhere.
- **Build owned by ISI-2161** (CEO 2026-08-11); UX mock `09-team-org-diagram` (10th screen, ISI-2150,
  `docs/bmad/ux/gen-09-team-org.py`, dark + light). This story pins the **construction-time contract**.

## Acceptance Criteria

**AC1 — `Team → Agent → Role` hierarchy is a read-only projection of the CRDs (the read-model crux).**
Given a Team, When the operator opens its org diagram, Then it renders the **`Team → Agent → Role`
hierarchy** from the **`Team`/`Agent`/`Role` CRDs** (§5.1, **read-only**), each Agent node showing its
**runtime type** (`AgentRuntime`, §5.3) and **role badges** — all sourced from real CRD fields (**no new CRD,
no new data source, no fabricated node**). The endpoint is **GET-only**; every mutating verb is structurally
absent (405 / route absent).

**AC2 — `Team`-scoped through the ONE deny-by-default RBAC wall (the security crux).**
Given the diagram, When it renders, Then it is served through the **SAME shared deny-by-default RBAC
middleware** every other console read model uses (§12.3 r20/r21) — **no org-diagram-specific authz path**. It
is **`Team`-scoped** (§12.1): a caller with **no membership** in the Team gets the **not-found/deny shape**
(existence-hiding), **never** a partial org chart; a member gets the scoped hierarchy. This story adds **no**
client-side authz and **no** second authz path.

**AC3 — live per-Agent status is DERIVED from Run/claim state (not stored, not self-reported).**
Given an Agent, When the diagram renders its status, Then the status ∈ **{idle, running, blocked, paused}** is
**derived** from the Agent's current **`Run.status.phase`** (§5.2) + **`Paused` condition** (Epic 7.4) — a
projection of **Run/claim state** (§6/§8, FR-I3 provenance), **not** a stored status column and **not** an
agent self-reported value. An Agent with no active Run renders **`idle`**; the derivation is the single source
of the node's status.

**AC4 — coordination-free: no mutate/claim/reassign affordance (no-P2P on the console, R6).**
Given the diagram, When it renders, Then it has **no mutate / claim / reassign / transition affordance**
anywhere — it is **read + navigate only** (no-P2P applied to the console, §13 r10). It is **not** the
compose/edit view (that stays 8.5) and **not** a coordination path (R6 scope guard). A claim button, an
editable node, or any control that drives/reassigns an agent from the diagram is a regression.

**AC5 — click-through deep-links to the agent detail page — navigation, not dispatch.**
Given an Agent node, When the operator clicks it, Then it **deep-links to the agent detail page** (8.11 /
FR-F9) — a **navigation** (a URL to the agent-detail route), **never** a coordination action (it does not
claim, dispatch, reassign, or transition anything). The click is a read-path navigation only.

**AC6 — status updates live over the EXISTING SSE bus (no new transport, no polling).**
Given the diagram open, When an Agent's Run/claim state changes (a Run starts, claims, blocks, pauses,
completes), Then the node's status **updates live via SSE over the existing progress bus** — the **same
EventSource + BFF proxy** as the Run stream (8.2) and the dashboard live tiles (§4.4/§13, same as 8.2) —
**no polling loop, no new transport, no new backend**. Updates arrive as **deltas** (a delta names the
changed Agent so the client patches that node in place without a full refetch).

**AC7 — observability: consumes existing seams; adds no new domain metric; cardinality firewall.**
Given the diagram, When it renders/streams, Then it emits **only** ordinary console/BFF request+stream
telemetry — it introduces **no new domain metric**, **no new CRD, no new data source, no new backend**.
NFR-OBS3 standing law holds: per-item ids (`agent`/`run.id`/`work_item.id`/`user.id`) are **never** metric
labels, and there is **no** `model` label; the org chart is legibility, never a consumption axis.

## Tasks / Subtasks

- [ ] **Task 1 — Render the `Team → Agent → Role` hierarchy from the CRDs (AC1, AC2).**
  - [ ] Compose the read model from the `Team`/`Agent`/`Role` CRDs (read-only, §5.1) via the BFF; render
        each Agent node with its **runtime type** (`AgentRuntime`, §5.3) + **role badges** from CRD fields.
  - [ ] GET-only; no mutating verb on the surface. No new CRD / data source.
- [ ] **Task 2 — Serve through the one deny-by-default RBAC wall, `Team`-scoped (AC2).**
  - [ ] Route through the SAME shared deny-by-default middleware (§12.3); a non-member of the Team gets the
        not-found/deny shape (existence-hiding); a member gets the scoped hierarchy. No org-specific authz path.
- [ ] **Task 3 — Derive live status from Run/claim state (AC3).**
  - [ ] Derive each node's status ∈ {idle, running, blocked, paused} from `Run.status.phase` (§5.2) +
        `Paused` condition (Epic 7.4). No stored status column, no agent self-report. `idle` when no active Run.
- [ ] **Task 4 — Coordination-free; read + navigate only (AC4, AC5).**
  - [ ] No mutate/claim/reassign/transition affordance anywhere (no-P2P, R6). Node click deep-links to the
        agent detail page (8.11) — navigation (URL) only, never a dispatch/coordination action.
- [ ] **Task 5 — Stream status over the existing SSE bus (AC6).**
  - [ ] Subscribe to the **existing** progress bus (EventSource + BFF proxy, §4.4/§13, same as 8.2); apply
        Run-start/claim/block/pause/complete **deltas** to the named Agent node in place. No polling, no new transport.
- [ ] **Task 6 — Observability self-check (AC7).**
  - [ ] Confirm no new domain metric, no new backend; only ordinary request/stream telemetry. NFR-OBS3: no
        per-item ids on labels, no `model` label.

## Dev Notes

- **Pure read model over existing CRDs — no new backend.** The hierarchy is a read-only projection of the
  `Team`/`Agent`/`Role` CRDs (§5.1); the status is a projection of Run/claim state (§6/§8) + the `Paused`
  condition (7.4). There is **no new CRD, no new data source, no aggregation tier** — the diagram reads what
  Epic 1/2/3/7 already write. This is the §13 r10 discipline: the org diagram rides existing seams and does
  **not** reopen the passed CEO Gate 2.
- **Status is derived, never stored.** The single most tempting regression is to add a `status` field to the
  `Agent` CRD and write to it. Don't. The status is **derived** at read/stream time from `Run.status.phase`
  (§5.2) + `Paused` (7.4). A stored status column is a second source of truth that will drift from the Run
  state — and it is exactly what AC3 forbids.
- **Coordination-free — the org-diagram precedent (§13 r10).** The diagram shows who is doing what and lets
  you navigate to detail; it never lets you claim, reassign, or drive an agent. A claim/reassign button here
  would reintroduce a console-side coordination affordance (no-P2P §6) that the architecture forbids and that
  the R6 scope guard rules out (this is not the compose/edit view — that stays 8.5).
- **One SSE bus.** Status streams over the **same** EventSource + BFF proxy as the Run stream (8.2) and the
  dashboard live tiles (§13 r24). Do not stand up a second EventSource client or a polling loop — that is the
  exact anti-pattern §13 rules out. Deltas name the changed Agent so the client patches the node in place.
- **The deep-link is a URL, not an action.** Clicking a node navigates to the agent detail page (8.11) — a
  read-path navigation. It must not dispatch, claim, or transition anything; a click that mutates is a
  coordination affordance in disguise (AC5).

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield console surface — the org diagram lands under `console/`
  and consumes the BFF read model + the existing SSE bus. It adds **no** apiserver code beyond the read
  projection over existing CRDs / Run state, and **no** new store. Reuse the **existing** EventSource client
  (shared with the Run stream / dashboard live tiles) — do not add a second SSE client. Reuse the shared
  deny-by-default RBAC middleware (§12.3) — do not add an org-specific authz path.
- **UX:** `docs/bmad/ux/gen-09-team-org.py` (screen 09, dark + light) is the visual contract — the
  `Team → Agent → Role` lineage tree, status chip hues (running/paused/blocked/idle), runtime + role badges,
  click-through agent-detail panel.

### References

- [Source: docs/bmad/02-prd.md#9.6 FR-F8] — team organization diagram: `Team→Agent→Role` read model over the
  CRDs, live per-Agent status (idle/running/blocked/paused), runtime-type + role badges, click-through to the
  agent detail page (FR-F9); `Team`-scoped, coordination-free (no-P2P on the console).
- [Source: docs/bmad/03-architecture.md#13 (r10) — org-diagram read model] — pure read model over Run/claim
  state, `Team`-scoped (§12.1), no mutate/claim affordance (no-P2P on the console); no new CRD / data source.
- [Source: docs/bmad/03-architecture.md#13 (r24) — Live tiles are SSE, one bus] — the existing SSE progress
  bus (same BFF proxy as the org diagram + Run stream); no new transport, no polling.
- [Source: docs/bmad/03-architecture.md#12.3 (r20/r21)] — the one deny-by-default RBAC wall; no per-surface
  authz path; existence-hiding for non-members.
- [Source: docs/bmad/03-architecture.md#5.2 / Epic 7.4] — `Run.status.phase` + the `Paused` condition; the
  Run/claim state the per-Agent status is derived from.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8 row 8.10] — epic-level AC; read/legibility surface
  (not compose/edit 8.5, not a coordination path, R6); status derives from `Run.status.phase` + `Paused`; no
  new backend; deep-links to 8.11; build owned by ISI-2161.
- [Source: docs/bmad/stories/8-8a-dashboard-data-aggregation-read-model.md] — the shared deny-by-default RBAC
  wall + existing SSE snapshot/delta bus this diagram reuses.
- [Source: docs/bmad/stories/8-1-squad-overview-screen.md] — the existence-hiding scoped-read-model precedent.
- [Source: docs/bmad/ux/gen-09-team-org.py] — screen 09 org-diagram mock (dark + light).

### Open questions (route via ISI-2161; do not block the read model)

1. **`blocked` derivation source (Architect / Winston).** AC3 lists `blocked` among the statuses. Confirm the
   exact Run/claim signal for `blocked` (a Run condition awaiting a dependency vs a work-item `blocked` state)
   so the derivation stays a projection of existing state (never a new field). *Does not block rendering
   idle/running/paused from `Run.status.phase` + `Paused`.*
2. **Cross-Project Agents in a `Team`-scoped diagram (Architect).** FR-F8 is `Team`-scoped; an Agent may run
   Runs across multiple Projects of the squad. Confirm the diagram shows the Team's Agents with their current
   status regardless of which Project the active Run sits in (status is Agent-level). *Does not block the
   Team-scoped hierarchy render.*

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, agent 2230b001) — construction-time contract via runnable falsification check
(`team-org-diagram-check.py`, Epic-8 model-check pattern).

### Debug Log References

- `python3 team-org-diagram-check.py` → exit 0 (the editable-org-console anti-pattern trips all 7; the
  §13 r10 conformant org-diagram read model holds C1-C7).
- `--mutate={FAKE_HIERARCHY,BESPOKE_AUTHZ,STORED_STATUS,CLAIM_AFFORDANCE,MUTATE_DEEPLINK,POLL_TRANSPORT,PERITEM_LABEL}`
  → each exit 1 with the mapped invariant RED; no vacuous survivors.

### Completion Notes List

- Implemented C1-C7 falsification check with teeth via an "editable org console" anti-pattern (mutating verbs
  on the surface, its own authz path that leaks to a non-member, status read from a stored/self-reported field,
  a claim/reassign button on each node, a click that dispatches instead of navigates, a polling loop instead of
  the SSE bus, and per-Agent metric labels).
- **Load-bearing cruxes proven:** (C1) hierarchy is a **read-only projection of the `Team`/`Agent`/`Role`
  CRDs** — GET-only, no new CRD/data source, runtime + role badges from real CRD fields; (C2) served through
  the **ONE shared deny-by-default RBAC wall**, `Team`-scoped, existence-hiding for non-members — no
  org-specific authz path; (C3) status is **DERIVED** from `Run.status.phase` (§5.2) + `Paused` (7.4), never a
  stored column or self-report; (C4) **coordination-free** — no mutate/claim/reassign affordance (no-P2P,
  §13 r10, R6 not-a-compose-view); (C5) click-through is a **navigation (URL)** to the agent detail page
  (8.11), never a dispatch; (C6) status streams over the **EXISTING** SSE bus (same EventSource + BFF proxy as
  8.2), delta-per-Agent, no polling/new transport.
- Runtime proof (real CRD read projection, live per-membership `Team`-scoped RBAC on the Go apiserver, SSE
  delta wire-up, and the derived-status stream) owned by console E2E + apiserver read-model tests on the actual
  CRD + Run/claim stores. This check guards the construction-time contract FR-F8 + §13 r10 asked for.

### File List

- `docs/bmad/spikes/bench/team-org-diagram-check.py` (new) — C1-C7 runnable falsification check.
- `docs/bmad/stories/8-10-team-org-diagram.md` (this file) — status→done + Dev Agent Record.
</content>
</invoke>
