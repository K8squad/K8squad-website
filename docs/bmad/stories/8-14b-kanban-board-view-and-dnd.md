# Story 8.14b: Kanban board view + drag-and-drop status wiring

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The board is a PURE PROJECTION of `work_item.state` (ADR-037).** There is no stored "column" field to
> read or write. A drag calls the 8.14a status-transition endpoint; the board never authors state
> client-side. Read AC2 and AC4 literally — consulting or persisting a separate column field, or letting
> the UI keep a card in the target column after a `409`, is an ADR-037 regression.

## Story

As an **operator**,
I want a **Kanban board view of the Project's tickets with drag-and-drop status transitions**,
so that **I can triage flow at a glance and move a ticket across `Backlog · Todo · In Progress · In Review · Done` by dragging its card — a control-plane-mediated, RBAC-gated, concurrency-safe human override, not a client-side state change.**

## Context & prerequisites (read first)

- **Architecture:** `docs/bmad/03-architecture.md` §13 "Project → Tickets — dual view" (board-state derivation, the five columns, `blocked`-as-badge, DnD → status-update API, viewer read-only), §8.6 (`blocked` is a condition, not a column), §13 BFF rule (browser never touches Postgres/kube directly).
- **Depends on (must be landable before this story is done):**
  - **8.14a** — `PATCH /work-items/{id}/state {to, expectedFrom}` (the mutation this view drives). If not yet merged, stub the call behind the same interface and mark the DnD integration test `skip` with `TODO(8.14a)` — but the **board projection + blocked-badge + RBAC-disabled DnD render (this story's non-DnD deliverables) do not depend on it.**
  - **8.17** — the reusable sub-ticket tree component (caret + count badge + in-place expansion). A card with children uses it; do **not** reimplement.
  - **8.13** — the nav shell + Project context selector (this view mounts under Project → Tickets, Project-scoped).
  - **8.9** — the dark+light theme token system.
- **Testing:** `docs/bmad/05-testing-strategy.md` §3.2 "Dual-view Tickets" (a) board-state derivation, (b) blocked-as-condition, (c) DnD status accuracy + 409-resync + viewer-disabled + no-claim-call.
- **Sibling slices:** **8.14c** (List view — parallel, read-only) and **8.14d** (shared search/filter + view-toggle — depends on this + 8.14c). Search/filter and the view toggle are **not** in this story; the board just consumes the shared filter set 8.14d wires.

## Acceptance Criteria

**AC1 — five columns, canonical order.**
Given the Tickets screen in Kanban view for a selected Project, When it renders, Then it shows exactly five columns in canonical order — **Backlog · Todo · In Progress · In Review · Done** — matching the ordered `work_item.state` enum. There is **no** "Blocked" column.

**AC2 — board is a pure projection of `state` (no stored column).**
Given a set of work items, When the board renders, Then each item is placed in the single column equal to its `work_item.state` and nowhere else; every one of the five states maps to exactly one column. And changing **only** an item's `state` in a fixture moves the card to the new column — the placement reads `state` and **no separate "column"/"board_column" field** (assert the projection: there is no stored column consulted).

**AC3 — card content + sub-ticket tree.**
Given a card, When it renders, Then it shows **ID, title, assignee, priority**. And a card **with children** shows the **8.17 caret + child-count badge** and **expands in place within its own lane** (children are not scattered across status columns; each child still shows its own status chip). A leaf card shows no caret.

**AC4 — `blocked` is a badge in its lane, never a column.**
Given a work item whose `blocked` condition is set (§8.6), When it renders, Then it appears **in the column of its workflow `state`** (e.g. In Progress) with a **Blocked badge overlay** — never in a separate/6th column and never moved out of its lane. Clearing `blocked` removes the badge without moving the card.

**AC5 — DnD issues exactly one status transition (8.14a).**
Given a **contributor/maintainer**, When they drag a card from column *X* to column *Y*, Then exactly one `PATCH …/work-items/{id}/state {to:Y_state, expectedFrom:X_state}` is issued **through the BFF** (never Postgres/kube directly, §13); on **`200`** the card settles in column *Y*. And the drag issues **no claim/lease/checkout call** (distinct authority path, §6.2) — assert no claim endpoint is called.

**AC6 — stale drag → `409` → board re-syncs (no lost-update).**
Given a card the UI shows in column *X* but whose server `state` has already advanced (e.g. an agent moved it), When the operator drags it and the `PATCH` returns **`409`** with the current server state, Then the board **re-syncs the card to server truth** (moves it to the server's current column and clears the optimistic move) — it does **not** leave the card in the dragged-to column and does **not** author state client-side. A brief non-blocking notice ("board updated") is acceptable; a silent wrong-position is not.

**AC7 — viewer is read-only (UI RBAC gate, defense-in-depth).**
Given a **viewer** membership, When the board renders, Then **drag-and-drop is disabled** (cards are not draggable) and no `PATCH …/state` is issuable from the UI. This mirrors — and never replaces — the 8.14a server RBAC wall (a forged PATCH still `403`s server-side, §12.3/§6.7.2). The role is read from the BFF session, never a client store.

**AC8 — theme + accessibility.**
Given the board, When it renders in either theme, Then it is **theme-correct** (dark+light, 8.9) at WCAG-AA contrast, and DnD has a **keyboard-accessible** equivalent (a quick-move affordance / keyboard drag per the `@dnd-kit`-class library the console scaffolding lands with) so status moves are not mouse-only.

**AC9 — Project-scoped, tenancy-safe read.**
Given the mounted view, When it loads cards, Then it reads the work items for the **selected Project only** (8.13 context), through the BFF's tenancy-scoped read (§12.1) — no cross-Project bleed, and it renders only what the API returned (server is the authority, R6).

## Tasks / Subtasks

- [ ] **Task 1 — Board projection + columns (AC1, AC2, AC9).**
  - [ ] Render five fixed columns from the `state` enum in canonical order; place each item by `state` (pure projection — no stored column). Load items Project-scoped through the BFF read.
  - [ ] Vitest unit: five-state→five-column mapping; a `state`-only fixture change moves the card; assert no separate column field is read.
- [ ] **Task 2 — Card + sub-ticket tree (AC3).**
  - [ ] Card shows ID/title/assignee/priority; a parent card composes the **8.17** caret+badge and expands in-place within its lane. Leaf = no caret.
- [ ] **Task 3 — Blocked badge (AC4).**
  - [ ] Render a Blocked badge overlay for `blocked` items in their `state` lane; never a 6th column. Vitest unit: blocked item stays in its lane with a badge; clearing moves nothing.
- [ ] **Task 4 — DnD → 8.14a wiring (AC5, AC6).**
  - [ ] On drop, issue one `PATCH …/state {to, expectedFrom}` via the BFF with `expectedFrom` = the state the card was shown in. On `200` settle in target; on `409` **re-sync to the server's current state** and clear the optimistic move; assert **no** claim/lease call fires.
  - [ ] If 8.14a is not yet merged, stub behind the interface and `skip` the DnD integration test with `TODO(8.14a)`.
  - [ ] Playwright E2E: drag Todo→In Progress fires exactly one correct PATCH and lands the card; a stale-state drag gets 409 and the board re-syncs to server truth (no lost-update).
- [ ] **Task 5 — RBAC-disabled DnD for viewer (AC7).**
  - [ ] Read role from the BFF session; disable drag + hide/disable move affordances for `viewer`; assert no PATCH is issuable. Vitest unit + Playwright (viewer sees no draggable cards).
- [ ] **Task 6 — Theme + a11y (AC8).**
  - [ ] Dark+light token correctness (8.9), WCAG-AA contrast; a keyboard-accessible quick-move/keyboard-drag equivalent to mouse DnD.

## Dev Notes

- **Framework: detect, don't impose.** Use whatever the console scaffolding lands with (Vitest + ESLint per 05-testing §3.2; Playwright for E2E). The DnD library is expected to be `@dnd-kit`-class or native drag — follow the repo's choice; do not add a new one.
- **Pure projection — say it in code.** The column a card sits in is `columnFor(item.state)`, a total function over the five-value enum. There is no `item.column`. This is ADR-037's single-source-of-truth: the board renders `state`; the DnD writes `state`; nothing stores a column.
- **Optimistic move + 409 rollback.** It is fine to move the card optimistically on drop for responsiveness — but the `409` path **must** roll the card back to the server's current column (from the 409 body), not leave the optimistic position. The server is the authority; the human re-drags if they still want the move.
- **No claim, no fence.** The drag is a status override, not a checkout. It must never call the claim/lease/checkout path — that is the agent's custody model (§6.2). Assert zero claim calls in the DnD test.
- **UI RBAC is legibility, not the wall.** Disabling DnD for viewers is defense-in-depth over the 8.14a server `403`. Never rely on the disabled UI as the boundary — the server re-checks (8.14a AC5).

### Project Structure Notes

- Console app (Next.js/TS, §13). If not yet scaffolded when this story starts, coordinate with 8.13 (nav shell) — this view mounts at the Project → Tickets route. Component units in Vitest; DnD/409 flows in Playwright with semantic locators (`aria`-based), per 05-testing §3.2.

### References

- [Source: docs/bmad/03-architecture.md#13 Project → Tickets — dual view] — five columns, pure `state` projection, blocked-as-badge, DnD → `PATCH …/state`, 409-resync, viewer read-only, BFF choke point.
- [Source: docs/bmad/03-architecture.md#8.6] — `blocked` is an orthogonal condition (badge), not a column.
- [Source: docs/bmad/03-architecture.md#18 ADR-037] — board-state derivation + human DnD transition; rejected: stored column, 6th column, DnD-acquires-lease, last-writer-wins, client-authored state.
- [Source: docs/bmad/05-testing-strategy.md#3.2 Dual-view Tickets (a)(b)(c)] — board derivation, blocked-as-condition, DnD accuracy + 409-resync + viewer-disabled + no-claim-call.
- [Source: docs/bmad/stories/8-14a-coord-status-transition-endpoint.md] — the endpoint this view drives (shape, 409, RBAC, no-fence).
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.14 story slicing, 8.14b] — epic-level AC + deps (8.14a, 8.17, 8.13, 8.9).

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
