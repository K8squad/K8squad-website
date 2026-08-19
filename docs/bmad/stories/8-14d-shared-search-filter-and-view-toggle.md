# Story 8.14d: shared search/filter + view-toggle persistence

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **Filters are SERVER-SIDE query params on the same BFF read, applied identically to both views; the view
> toggle is a per-user READ PREFERENCE (localStorage + `?view=`), never coord state.** This slice cross-cuts
> 8.14b (Kanban) and 8.14c (List) — both must exist to share the filter set and the toggle.

## Story

As an **operator**,
I want a **global search bar + contextual filters that apply to both Tickets views, and a view toggle whose choice persists**,
so that **I can narrow tickets by priority/assignee/label (or search title/ID) and have that set survive when I flip Kanban↔List, and reopen the console in whichever view I last chose (or the one a shared `?view=` link specifies).**

## Context & prerequisites (read first)

- **Architecture:** `docs/bmad/03-architecture.md` §13 "Project → Tickets — dual view" (view toggle persisted per user via localStorage + `?view=` URL param; global search bar title/ID + contextual filters priority/assignee/label as **server-side, tenancy-scoped query params** on the same BFF read, indexed `state`/`assignee`/`labels` predicates, applied identically to both views so toggling preserves the active filter set — a read/organization preference, never coord state), §12.1 (tenancy scope), R6 scope guard.
- **Depends on:** **8.14b** (Kanban) **+ 8.14c** (List) — both views must exist to wire the shared filter/search state and the toggle across them. Also **8.13** (nav shell / Project scope) + **8.9** (theme).
- **Testing:** `docs/bmad/05-testing-strategy.md` §3.2 "Dual-view Tickets" (e) view-toggle persistence (reload / `?view=` restores the view; filters survive the toggle) and (f) search + filters narrow both views via server-side query params, tenancy-scoped.
- **Scope boundary — NOT the global search:** this is the **screen-local** Tickets search/filter over the `coord` read for the selected Project. The **always-visible top-bar cross-entity global search** (tickets/files/agents/Runs/projects) is the separate **8.18 (API) + 8.19 (top-bar UI)** track. Do not conflate them.

## Acceptance Criteria

**AC1 — filters are server-side query params on the shared read.**
Given the Tickets read, When the operator sets a **priority**, **assignee**, or **label** filter, or types in the **global search** box (matches title / ID), Then each is sent as a **query param on the BFF read** (e.g. `?priority=&assignee=&label=&q=`) and the server narrows the result set with **indexed, tenancy-scoped predicates** (§12.1) — filtering is **not** done client-side over a full unscoped fetch (an out-of-scope item never arrives to be filtered out).

**AC2 — filters apply identically to both views.**
Given an active filter/search set, When the view is **Kanban**, Then the board shows only matching cards (in their `state` columns); When the view is **List**, Then the table shows the same matching rows. The **same query params** back both views — there is no per-view filter divergence.

**AC3 — the filter set survives the view toggle.**
Given an active filter/search set in one view, When the operator toggles Kanban↔List, Then the **active filters and search text are preserved** (carried in the shared query state / URL, not reset) and the other view renders the same narrowed set.

**AC4 — view toggle persists per user (localStorage + `?view=`).**
Given the view toggle, When the operator selects **Kanban** or **List**, Then the choice is written to **localStorage** (per user) **and** reflected in the **`?view=kanban|list` URL param**; When the screen is **reloaded** or reached via navigation, Then it **restores the last-chosen view**; When a **shared link with `?view=`** is opened, Then it **opens in that view** (the URL param wins for a deep link). The toggle is a **read preference — never a coordination mutation** (no coord write on toggle).

**AC5 — empty query / no-match are clean states.**
Given the search/filter, When the query is **empty**, Then the view shows the full (Project-scoped) set — a neutral state, not an error; When it **matches nothing**, Then the view shows a clear **empty state** (not a blank pane, spinner, or error). Special characters in the search box are handled safely by the server read (parameterized), never surfaced as an error.

**AC6 — server is the authority (R6), tenancy-scoped.**
Given any filter/search, When results render, Then the UI renders **only what the API returned** and **never widens** the Project/tenant scope client-side; the Project context (8.13) + the §12.1 tenancy predicate bound every read. No filter combination can reveal a ticket outside the caller's scope.

**AC7 — theme + accessibility.**
Given the search bar, filter controls, and view toggle, When they render in either theme, Then they are **theme-correct** (dark+light, 8.9), WCAG-AA, keyboard-operable (focusable controls, a keyboard shortcut to focus search is welcome), with clear labels and `aria` state on the active view + active filters.

## Tasks / Subtasks

- [ ] **Task 1 — Shared filter/search query state (AC1, AC2, AC6).**
  - [ ] Hold priority/assignee/label + `q` as a **single shared query state** (URL-backed) that both views read; send them as BFF query params on the tenancy-scoped read. Assert the BFF request carries the params (not client-side post-filtering).
  - [ ] Vitest units: setting each filter narrows both view models to the expected set; the request carries the param.
- [ ] **Task 2 — Filters survive the toggle (AC3).**
  - [ ] Ensure the shared query state is not reset on view change; the other view renders the same narrowed set. Playwright: filter in Kanban → toggle to List → same rows.
- [ ] **Task 3 — View-toggle persistence (AC4).**
  - [ ] Write the chosen view to localStorage + `?view=`; restore on reload/navigation; a `?view=` deep-link wins on first load. Assert **no coord write** on toggle. Vitest unit (persistence resolution: URL > localStorage > default) + Playwright (`?view=` deep-link opens the right view; reload restores).
- [ ] **Task 4 — Empty / no-match / special-char states (AC5).**
  - [ ] Empty query → full Project-scoped set (neutral); no-match → explicit empty state; special chars handled by the parameterized server read (no error). Vitest units + a Playwright no-match case.
- [ ] **Task 5 — Theme + a11y (AC7).**
  - [ ] Dark+light correctness (8.9); keyboard-operable controls; `aria` on active view + filters; optional focus-search shortcut.

## Dev Notes

- **Server-side filtering is a correctness property, not a perf nicety.** Filtering on the server with the tenancy predicate means an out-of-scope ticket is never fetched to the client at all (§12.1, R6). Client-side filtering over a broad fetch would both break scope-hiding and diverge the two views. Keep filters as query params on the one BFF read that both views share.
- **URL is the source of truth for view + filters; localStorage is the fallback.** For a deep link (`?view=list&priority=high`) the URL wins so a shared link reproduces the sender's view. localStorage remembers the user's last choice when no `?view=` is present. Resolution order: **URL param > localStorage > default (per the validated mock)**.
- **Toggle/filter never touch coord.** These are read/organization preferences. No mutation, no fence, no claim — the only Tickets write in the whole 8.14 epic is the 8.14a status transition (driven by 8.14b). Assert zero coord writes on toggle/filter.
- **Not the top-bar global search.** 8.18/8.19 is the cross-entity, cross-Project top-bar search with its own RBAC-in-query backend. This story is the local Tickets narrow. Reuse the shared filter/search UI primitives if the console scaffolding offers them, but the backend here is the existing `coord` read with query params, not `pkg/search`.

### Project Structure Notes

- Console app (Next.js/TS, §13), on the Project → Tickets route (8.13), composing 8.14b + 8.14c. URL/query-state management follows the App Router conventions the console scaffolding lands with. Units in Vitest; toggle/filter flows in Playwright with semantic locators.

### References

- [Source: docs/bmad/03-architecture.md#13 Project → Tickets — dual view] — view toggle (localStorage + `?view=`), server-side search/filters applied to both views, filter survives toggle, read preference never coord state.
- [Source: docs/bmad/05-testing-strategy.md#3.2 Dual-view Tickets (e)(f)] — view-toggle persistence (`?view=` deep-link, filters survive toggle) + search/filter narrowing both views via tenancy-scoped query params.
- [Source: docs/bmad/stories/8-14b-kanban-board-view-and-dnd.md] + [8-14c-list-sortable-table-view.md] — the two views this slice shares filters + the toggle across.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.14 story slicing, 8.14d] — epic-level AC + deps (8.14b + 8.14c); note the 8.18/8.19 boundary.

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
