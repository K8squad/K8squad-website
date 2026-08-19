# Story 8.14c: List (sortable table) view

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **This view is READ-ONLY.** It does not mutate coord state — the only Tickets write is the 8.14a
> status-transition, driven from the Kanban card (8.14b). Because it is read-only it has **no dependency on
> 8.14a** and can be built **in parallel** with 8.14b.

## Story

As an **operator**,
I want a **List view of the Project's tickets as a sortable table**,
so that **I can scan and sort ticket detail — ID, Title, Status, Priority, Assignee, Labels, Updated — and drill into the sub-ticket tree without leaving the console, alongside the Kanban view I toggle to for flow triage.**

## Context & prerequisites (read first)

- **Architecture:** `docs/bmad/03-architecture.md` §13 "Project → Tickets — dual view" (the List table: sortable on ID·Title·Status·Priority·Assignee·Labels·Updated, `updated_at` the recency sort key; all columns are `work_item` §6.1 fields), §5.4 (SCM provenance badge), §13 BFF rule + R6 scope guard.
- **Depends on (must be landable before this story is done):**
  - **8.17** — the reusable sub-ticket tree component (caret + child-count badge + indented children). A parent row uses it; do **not** reimplement.
  - **8.13** — the nav shell + Project context selector (this view mounts under Project → Tickets).
  - **8.9** — the dark+light theme token system.
  - It does **NOT** depend on 8.14a (no mutation here).
- **Testing:** `docs/bmad/05-testing-strategy.md` §3.2 "Dual-view Tickets" (d) List sort (all seven columns incl. Updated).
- **Sibling slices:** **8.14b** (Kanban — parallel) and **8.14d** (shared search/filter + view-toggle — depends on this + 8.14b). Search/filter and the toggle are wired in 8.14d, not here.

## Acceptance Criteria

**AC1 — the seven columns.**
Given the Tickets screen in List view for a selected Project, When it renders, Then a table shows the columns **ID · Title · Status · Priority · Assignee · Labels · Updated**, each populated from the corresponding `work_item` field (§6.1). `Status` shows the workflow `state` (and a Blocked badge if the `blocked` condition is set, §8.6 — mirrors the Kanban badge, not a separate row/column).

**AC2 — every column sorts, both directions.**
Given the table, When the operator clicks a column header, Then the rows sort by that column **ascending**, and clicking again **descending** (a visible sort indicator shows the active column + direction). This holds for all seven columns. **Updated** sorts by `updated_at` (recency) — the default sort is **Updated desc** ("recently touched" first) unless a persisted/URL sort says otherwise.

**AC3 — sub-ticket tree (8.17) on parent rows.**
Given a parent row (a work item with children), When it renders, Then it carries the **8.17 disclosure caret + child-count badge**; expanding reveals its children **indented one level** (recursively, to the indent cap with the "continue in child" affordance); collapsing hides them. A **leaf** row shows no caret. Expansion is **client-only view state** (no mutation). An **orphan child** (parent closed/deleted, §6.1 dangling-tolerant) **renders as a root row**, never hidden.

**AC4 — SCM provenance badge.**
Given a work item synced from source control (Epic 11 / §5.4), When its row renders, Then it shows its **provenance badge** so operators can tell SCM-mirrored tickets from natively-authored ones.

**AC5 — read-only (R6 scope guard).**
Given the List view, When the operator interacts with it, Then **no coordination mutation** is issued from the table — no status change, no claim, no compose/edit (that is 8.5). Status transitions live only on the Kanban card (8.14b). Sorting and tree-expansion are the only interactions and both are client-only view state.

**AC6 — Project-scoped, tenancy-safe read.**
Given the mounted view, When it loads rows, Then it reads the work items for the **selected Project only** (8.13 context) through the BFF's tenancy-scoped read (§12.1) — no cross-Project bleed; it renders only what the API returned.

**AC7 — theme + accessibility.**
Given the table, When it renders in either theme, Then it is **theme-correct** (dark+light, 8.9) at WCAG-AA contrast; headers are real interactive controls (keyboard-sortable, `aria-sort`), the tree carets are real `button`/`aria-expanded` (via 8.17), and the table is navigable by keyboard.

## Tasks / Subtasks

- [ ] **Task 1 — Table + columns (AC1, AC6).**
  - [ ] Render the seven columns from `work_item` fields, Project-scoped via the BFF read; Status column shows `state` + Blocked badge for `blocked` items.
- [ ] **Task 2 — Sorting (AC2).**
  - [ ] Header-click sort asc/desc on every column with an active-sort indicator; default **Updated desc**. Vitest units: each column sorts correctly both directions, incl. `Updated` (recency) — parse/compare types correctly (string vs date vs enum priority order).
- [ ] **Task 3 — Sub-ticket tree (AC3).**
  - [ ] Compose the **8.17** component for parent rows (caret + count + indented children, orphan-as-root, indent cap). Assert expansion is client-only (no coord write). Playwright: expand → children render indented; orphan renders as root.
- [ ] **Task 4 — Provenance badge + read-only guard (AC4, AC5).**
  - [ ] Render the §5.4 provenance badge for SCM-synced rows; assert the table issues no mutation on any interaction.
- [ ] **Task 5 — Theme + a11y (AC7).**
  - [ ] Dark+light token correctness (8.9); `aria-sort` on headers, keyboard sort, keyboard tree nav (via 8.17).

## Dev Notes

- **Framework: detect, don't impose.** Vitest + ESLint (units: sort correctness, badge, tree), Playwright (expand/sort E2E), per 05-testing §3.2. Use whatever table primitive the console scaffolding lands with; do not add a new grid library unless the repo already chose one.
- **Sort types matter.** `Updated` is a timestamp (recency), `Priority` is an ordered enum (not lexicographic), `ID`/`Title`/`Assignee`/`Labels` are strings. Sort each by its natural order — a naive string sort on Updated or Priority is a bug the §3.2(d) test should catch.
- **Read-only is the point.** This slice is deliberately mutation-free — it is the "scan/sort detail" half of the dual view. All writing is the Kanban card's DnD (8.14b) → 8.14a endpoint. Keep the List free of any status/claim/compose affordance (R6).
- **Reuse 8.17.** The tree behavior (lazy-load per parent, orphan-as-root, indent cap, keyboard) is the shared 8.17 component's contract — compose it, don't fork it. If 8.17 is not yet merged, integrate behind its interface and `skip` the tree E2E with `TODO(8.17)`; the flat table + sort deliverables do not depend on it.

### Project Structure Notes

- Console app (Next.js/TS, §13), mounted at the Project → Tickets route (8.13). Component/sort units in Vitest; expand/sort flows in Playwright with semantic locators.

### References

- [Source: docs/bmad/03-architecture.md#13 Project → Tickets — dual view] — List = sortable table on the seven columns; `updated_at` recency; SCM provenance badge; R6 read-only.
- [Source: docs/bmad/03-architecture.md#8.6] — Blocked badge (Status column) mirrors the Kanban badge; not a separate row.
- [Source: docs/bmad/05-testing-strategy.md#3.2 Dual-view Tickets (d)] — List sort on all seven columns incl. Updated.
- [Source: docs/bmad/stories/8-17-*.md (sub-ticket tree component)] — the shared tree contract this view composes (if the file is not yet cut, see epics 8.17).
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.14 story slicing, 8.14c] — epic-level AC + deps (8.17, 8.13, 8.9; parallel to 8.14b).

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
