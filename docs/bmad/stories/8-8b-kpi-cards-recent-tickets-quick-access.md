# Story 8.8b: KPI card row + Recent Tickets + quick-access links

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **Real sources only — no placeholders (FR-I3).** Every KPI figure and every Recent-Tickets row comes
> from the **8.8a payload**, which draws from real sources (coordination record, SCM mirror, metrics seam,
> Run/claim state). A card whose backing source is unwired renders an **explicit empty / "not configured"**
> state — **never** a fabricated or agent-self-reported number. A placeholder figure on this surface is a
> provenance regression, not a cosmetic stand-in.

## Story

As an **operator opening a Project's dashboard**,
I want **a KPI card row (tickets-by-status, tokens-with-trend, PRs-by-status, live Runs), a Recent Tickets list with status badges and a "View all" link, and quick-access links to the Project's primary surfaces**,
so that **I get the Project at a glance from real sources and can jump into any surface — the dashboard is my entry point into the Project (FR-I7/I8).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.9 — **FR-I7** (KPI card row: tickets-by-status, tokens+trend, PRs-by-status, live Runs; Recent Tickets with status badges + "View all"; every card from a real source, no placeholders — FR-I3) and **FR-I8** (quick-access links to Issues/Tickets, File Explorer (build browser), Board, Discussion — honors the Project-rooted IA).
- **Architecture:** `docs/bmad/03-architecture.md` §13 **r24** — KPI cards + Recent Tickets + tickets-by-status come from the `coord` audit (§6.5) via the 8.8a read model; all tiles pass the same deny-by-default RBAC wall (§12.3); per-tile degradation.
- **Depends on (must be landable/mergeable before this story is done):**
  - **8.8a** — the dashboard data-aggregation read model. This story **renders** the `ticketsByStatus`, `recentTickets`, and the KPI sub-payloads from 8.8a; it does **not** re-query raw stores. The **token** KPI value is 8.8e's `tokenConsumption` sub-payload, the **PR** KPI is 8.8d's `prBoard`, the **live Runs** KPI is 8.8f's `liveRuns` — this story renders whatever 8.8a returns for each, including their **degraded** markers.
- **Cross-epic (progressive, do NOT gate this story):** the Tokens / PRs / Live-Runs KPI cards show 8.8e/8.8d/8.8f data when those tiles are wired; until then they render 8.8a's per-tile **empty/not-configured** state (never a fake number). This story ships useful with tickets-by-status + Recent Tickets from the coordination record alone.
- **Blocked by:** 8.8a. **Sibling surfaces it links into:** Project → Tickets (8.14), build browser (8.7), Discussion room (10.3).

## Acceptance Criteria

**AC1 — KPI card row, four cards, from the 8.8a payload.**
Given the dashboard (8.8a payload), When it renders, Then a **KPI card row** shows four cards: **Tickets by status**, **Tokens consumed (with trend — 8.8e)**, **PRs by status (8.8d)**, **Live agent Runs (8.8f)**. And each card reads its value from the corresponding **8.8a sub-payload** (`ticketsByStatus`, `tokenConsumption`, `prBoard`, `liveRuns`) — this story does **not** re-query `coord`/`scm`/metrics/Run-state directly.

**AC2 — Recent Tickets list with status badges + "View all".**
Given the `recentTickets` sub-payload, When it renders, Then a **Recent Tickets** list shows recent work items each with a **status badge** (the `work_item.state` value — Backlog/Todo/In Progress/In Review/Done, with a **Blocked** badge overlay where blocked, per arch §13 r25) and a **"View all"** link that navigates into **Project → Tickets (8.14)**. And ticket rows and badges come from the `coord` record (via 8.8a) — no placeholder rows.

**AC3 — quick-access links to the Project's primary surfaces (FR-I8).**
Given the dashboard, When it renders, Then **quick-access links** navigate to the Project's primary surfaces: **Issues/Tickets (8.14)**, **File Explorer / build browser (8.7)**, **Board**, and **Discussion (10.3)**. And the links honor the **Project-rooted IA** (§9.6) — they route within the selected Project's context, so the dashboard is the operator's entry point into the Project.

**AC4 — every figure is a real source; no placeholder, no self-report (FR-I3).**
Given any KPI figure or Recent-Tickets row, When rendered, Then it comes from the **8.8a real sources** — **no** placeholder value, **no** hard-coded figure, **no** agent-self-reported number. And a card whose backing source is **unwired/degraded** (8.8a returned `{available:false}` for it — e.g. Tokens with no metrics backend, PRs with no synced repo) renders an **explicit empty / "not configured"** state, **never** a fabricated number or a zero that reads as real.

**AC5 — RBAC-scoped through 8.8a (no second authz path).**
Given the rendered cards and lists, When they display, Then every figure and row reflects only what the caller is entitled to see — the payload was **already server-filtered** to the caller's memberships by 8.8a's deny-by-default RBAC wall (§12.3). This story adds **no** client-side authz and **no** dashboard-specific authz path; it renders the pre-scoped payload. A viewer sees the same read cards; write-gated affordances are not on this surface.

**AC6 — live-updating KPI counters over the existing SSE bus (no polling).**
Given the KPI counters and Recent Tickets, When underlying state changes, Then the affected cards/rows update from **SSE deltas over the existing progress bus** (the 8.8a snapshot + delta contract, §4.4/§13) — **no polling loop, no new transport**. And a delta names its tile + changed sub-payload so the client patches in place without a full refetch (8.8a AC6). The live-Runs and approval counters are streamed by 8.8f / 8.8c; this story consumes the deltas for the cards it owns (tickets-by-status count, Recent Tickets).

**AC7 — empty/degraded states are explicit and honest (per-tile degrade).**
Given any card or the Recent-Tickets list with **no data** or a **degraded** source, When it renders, Then it shows an explicit empty state ("No tickets yet", "Tokens — not configured", "No repo synced") — distinguishable from a real zero and from a loading state. And a degraded card **does not** take down the row — the other cards render normally (8.8a per-tile independence surfaced in the UI).

**AC8 — observability: this story adds no new metric.**
Given rendering, When it occurs, Then this story emits **only** ordinary console/BFF request telemetry (it consumes the 8.8a payload + SSE) — it introduces **no new domain metric**. The token signal is 8.8e (obs §17.1); the approval-queue signals are 8.8c/2.12 (obs §17.2). NFR-OBS3 standing law holds: no per-item ids (`work_item.id`/`run.id`/`user.id`) as metric labels, no `model` label, read volume is not a consumption axis.

## Tasks / Subtasks

- [ ] **Task 1 — KPI card row (AC1, AC4, AC7).**
  - [ ] Render four cards bound to the 8.8a sub-payloads: `ticketsByStatus`, `tokenConsumption`, `prBoard`, `liveRuns`. Each card reads its **8.8a** value — no direct store query.
  - [ ] For each card, honor the sub-payload's `{available, reason}` envelope: available → the figure; unavailable → an explicit "not configured"/empty state (never a fake number or a misleading zero).
- [ ] **Task 2 — Recent Tickets list (AC2, AC4, AC7).**
  - [ ] Render `recentTickets` with **status badges** (`work_item.state`; Blocked overlay per §13 r25) and a **"View all"** link into Project → Tickets (8.14).
  - [ ] Empty state: "No tickets yet" — distinct from loading and from a real empty result.
- [ ] **Task 3 — Quick-access links (AC3).**
  - [ ] Render links to Issues/Tickets (8.14), File Explorer/build browser (8.7), Board, Discussion (10.3), routed within the selected Project (Project-rooted IA, §9.6).
- [ ] **Task 4 — RBAC-scoped rendering + live updates (AC5, AC6).**
  - [ ] Render only the pre-scoped 8.8a payload; add no client-side authz.
  - [ ] Subscribe to the 8.8a SSE delta stream; patch the tickets-by-status count + Recent Tickets in place on delta; no polling. Consume (do not originate) the live-Runs / approval-count deltas.
- [ ] **Task 5 — Observability self-check (AC8).**
  - [ ] Confirm no new domain metric is emitted here; only ordinary request telemetry. NFR-OBS3: no per-item ids on labels, no `model` label.

## Dev Notes

- **This is a rendering story over 8.8a — do not re-query the sources.** Every value flows from the 8.8a composed payload; if you find yourself opening a `coord`/`scm`/metrics/Run-state query in this story, stop — that belongs in 8.8a (single source of truth, ADR-020). This keeps the RBAC wall (§12.3) and per-tile degradation in one place.
- **Placeholders are a provenance bug (FR-I3).** The CEO-validated surface exists because operators must trust the numbers. A "0" that actually means "no source wired" is worse than an honest "not configured." Render the 8.8a `{available:false}` markers as explicit empty states; never paper over a degraded tile with a real-looking figure.
- **Cross-tile values render even before their epics land.** The Tokens/PRs/Live-Runs cards will show 8.8e/8.8d/8.8f data eventually; until those tiles are wired they show 8.8a's degraded marker. That is by design (per-tile progressive fill) — this story is done when tickets-by-status + Recent Tickets are real and the other three cards honestly reflect 8.8a's per-tile state.
- **SSE, one bus.** Live counters ride the same EventSource + BFF proxy as the Run stream and org diagram (§4.4/§13). No polling, no second transport.

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield — only `pkg/auth/*_test.go` + `console/e2e/auth/`. The Next.js console app (§13, ADR-013) is not yet scaffolded; this story's UI lands in the console app under `console/` following whatever app-router layout is established. The dashboard data all comes through the 8.8a BFF endpoint + SSE stream; this story adds **no** apiserver code.
- **Match conventions:** follow the console app's component/route conventions once scaffolded; use the existing SSE client the Run stream / org diagram use (do not add a second EventSource client).

### References

- [Source: docs/bmad/02-prd.md#9.9 FR-I7] — KPI card row (tickets-by-status, tokens+trend, PRs-by-status, live Runs); Recent Tickets with status badges + "View all"; every card from a real source, no placeholders (FR-I3).
- [Source: docs/bmad/02-prd.md#9.9 FR-I8] — quick-access links to Issues/Tickets, File Explorer (build browser), Board, Discussion; Project-rooted IA.
- [Source: docs/bmad/03-architecture.md#13 (r24) — dashboard read model] — KPI cards + Recent Tickets + tickets-by-status from the `coord` audit via 8.8a; same deny-by-default RBAC wall; per-tile degradation; SSE one bus.
- [Source: docs/bmad/03-architecture.md#13 (r25) — board-state derivation] — `work_item.state` values (Backlog·Todo·In Progress·In Review·Done) + Blocked as a badge overlay condition (status badges).
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.8 row 8.8b] — epic-level AC; deps 8.8a; mock = CEO-validated Project Dashboard (ISI-2325).
- [Source: docs/bmad/stories/8-8a-dashboard-data-aggregation-read-model.md] — the payload sub-payload shape + SSE delta contract this story renders.

### Open questions (route via ISI-2325; do not block rendering)

1. **KPI card set finality (PM / Designer).** The CEO-validated mock pins four KPI cards (tickets/tokens/PRs/live-Runs). Confirm no additional KPI card (e.g. throughput-over-time) belongs in the row vs the body tiles. *Does not block the four validated cards.*
2. **"Board" quick-access target (Designer / Architect).** FR-I8 lists "Board" alongside Issues/Tickets — confirm whether "Board" is the Kanban view of Tickets (8.14 Kanban) or a distinct surface, so the link routes correctly.

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
