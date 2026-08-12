# Story 8.19: Always-visible top-bar global search bar — debounced grouped dropdown + keyboard nav (FR-SEARCH1/2/4/5, NFR-USE2)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **⛔ SERVER IS THE AUTHORITY — THE UI NEVER WIDENS SCOPE (R6, NFR-SEC10).** This bar renders **only what the
> 8.18 API returned** and calls it **through the BFF proxy** (§13) — **never** Postgres/kube directly, and
> **never** a client-side filter that could reveal an entity the server withheld. UI role/scope adaptation is a
> **usability affordance, not a security boundary** (FR-AUTH5). The RBAC existence-hiding gate lives in 8.18
> (§6.7.3 I4); this story must not add a code path that could re-widen a scoped result set.

## Story

As an **operator**,
I want **an always-visible global search bar in the top bar with a debounced result dropdown grouped by entity type, full keyboard navigation, contextual per-Project scope + entity-type filters, and graceful empty/no-match/special-character states**,
so that **I can jump to any ticket / file / agent / Run / project from anywhere in the console — through one persistent entry point that surfaces only what I'm authorized to see (the 8.18 API is the authority; the UI never widens scope, R6).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.16 Theme P — **FR-SEARCH1** (top-bar, always visible, cross-entity), **FR-SEARCH2** (debounced, grouped dropdown, click-through, full keyboard nav), **FR-SEARCH4** (contextual per-Project scope + entity-type filters — narrow, never widen), **FR-SEARCH5** (graceful empty/no-match/special-char). NFR-USE2 (usability).
- **Architecture:** `docs/bmad/03-architecture.md` **§17.5** (search shape — note: *"debounce + keyboard nav + the grouped dropdown are console concerns"*; the API is stateless), **§13** (Next.js BFF proxy → apiserver, the browser never touches Postgres/kube), §17.3 (layout — top-bar placement), §12.3 (RBAC choke point — enforced server-side, UI is not the boundary).
- **Epics:** `docs/bmad/04-epics-and-stories.md` — Epic 8 row **8.19** (epic-level AC + deps); the nav IA context in the Epic 8 header (Project-rooted hierarchy, app shell = 8.13).
- **Testing:** `docs/bmad/05-testing-strategy.md` **§3.4** (frontend: Vitest unit — debounce/grouping/empty-state/no-client-widening; Playwright E2E — bar-on-every-screen, keyboard-only flow, contextual scope + widen affordance, entity-type filters, light+dark) + §3.2 idiom.
- **UX:** new screen **`12-global-search`** — the 13th console screen (new **Designer ticket**, ISI-2150 mock set). If the mock is not yet delivered when this story starts, build to the FR-SEARCH2/4/5 behavior contract and align visual details to the mock when it lands (see Open questions).
- **Depends on (must be landable before this story is done):**
  - **8.18** (global search API) — the single backend this bar calls (via BFF). **Hard dependency**: the bar cannot render real results without it. If 8.18 is not yet merged, wire the fetch behind the BFF proxy interface and drive the component tests against a mocked API response shape (`{ groups: [{ type, results:[{id,label,deepLink}] }] }`), but the **keyboard-nav, debounce, grouping, and empty-state behaviors are fully testable now** and must land here.
  - **8.13** (app shell / nav shell) — provides the persistent top bar this bar lives in. If the shell top-bar slot is not yet present, add the bar in the shell's top-bar region and coordinate placement with 8.13 (do not fork a second top bar).
  - **8.9** (theming) — dark + light tokens. The bar and dropdown must be theme-correct in both.
- **Blocked by the 8.18 gate:** this story **cannot close** until 8.18's §6.7.3 I4 RBAC-leak gate + determinism guard are green (the bar must not ship over an unscoped backend).

## Acceptance Criteria

**AC1 — always-visible top-bar bar, present on every screen (FR-SEARCH1).**
Given any console screen, When it loads, Then the **global search bar is present in the app-shell top bar** (8.13), persistent across navigation — it does **not** disappear on any screen. And it searches across all first-class entity types (tickets, files/artifacts, agents, Runs, projects) via one query.

**AC2 — debounced query → BFF proxy → 8.18 API (FR-SEARCH2, §13).**
Given the caller types in the bar, When keystrokes arrive, Then the input is **debounced** (rapid keystrokes coalesce into the trailing call — no request-per-keystroke) and the query is sent **through the BFF proxy** to the 8.18 `GET /api/v1/search` endpoint — **never** to Postgres/kube directly (§13). And the loading state is distinct from the empty/neutral state (no ambiguous blank).

**AC3 — result dropdown grouped by entity type, click-through (FR-SEARCH2).**
Given a query returns results, When the dropdown renders, Then results are **grouped by entity type** (tickets, files, agents, Runs, projects) in the order/shape the API returned, and each result is **click-through** to its detail surface (via the API's `deepLink`). And the UI renders **only** what the API returned — it does **not** re-rank, re-filter to widen, or synthesize results the server withheld.

**AC4 — full keyboard navigation, WCAG-AA (FR-SEARCH2, NFR-USE2).**
Given the search bar, When the caller uses only the keyboard, Then: a **shortcut focuses** the bar, **arrow keys** move through results (across groups), **Enter opens** the highlighted result, **Esc dismisses** the dropdown — the entire flow works **without a mouse**. And it meets **WCAG-AA** (focus visible, roles/labels correct, `aria-expanded`/active-descendant on the combobox/listbox pattern).

**AC5 — theme-correct in dark + light (8.9).**
Given the bar and dropdown, When the theme toggles, Then both render correctly in **dark and light** using the story-8.9 design tokens (no hard-coded colors, no unreadable contrast in either theme).

**AC6 — contextual per-Project scope + widen affordance (FR-SEARCH4).**
Given the caller is on a **Project screen**, When they search, Then the bar offers a **contextual scope to the current Project** (passing `projectId` to 8.18), with an explicit **widen-to-all-authorized** affordance that restores the full authorized set. And this scoping is **convenience over** the authorization floor — it **narrows, never widens** (the server enforces the floor; the UI cannot widen past it).

**AC7 — entity-type filters (FR-SEARCH4).**
Given the dropdown, When the caller applies an **entity-type filter** (e.g. tickets-only, files-only), Then results narrow to those types (passing `types[]` to 8.18) — the filter narrows correctly and never widens beyond the API result set.

**AC8 — empty, no-match, and special-character states are graceful (FR-SEARCH5).**
Given edge inputs, When the caller: (a) has an **empty query** → the bar shows a **neutral/recent state** (no error, no spinner-forever); (b) types a **no-match** query → a clear **empty state** renders (distinct from the neutral pre-query state **and** the loading state — not a blank or a permanent spinner); (c) types **special/reserved characters** (`:`, `*`, quotes, path separators, injection-shaped input) → they are passed as literal text to 8.18 and the UI shows the API's benign/empty result — **never** a client error. The UI never treats these as an error condition.

**AC9 — the UI is not the security boundary (FR-AUTH5, R6, NFR-SEC10).**
Given results, When they render, Then the bar surfaces **only** the entities the 8.18 API returned (which are already RBAC-scoped server-side, existence-hiding) — there is **no** client-side path that could reveal an entity the server withheld, and **no** client store used as the source of scope. The bar degrades gracefully if the API rejects/withholds — it never re-derives authorization client-side.

## Tasks / Subtasks

- [ ] **Task 1 — Top-bar search bar component in the app shell (AC1, AC5).**
  - [ ] Add the bar to the **8.13 app-shell top bar** region (single top bar — do not fork a second one); confirm it is present on **every** screen.
  - [ ] Theme it with the 8.9 tokens (dark + light); no hard-coded colors.
- [ ] **Task 2 — Debounced fetch through the BFF proxy (AC2, §13).**
  - [ ] Debounce input (trailing-edge; rapid keystrokes → one call). Call the **BFF proxy** route that forwards to 8.18 `GET /api/v1/search?q=&projectId=&types=` — never Postgres/kube directly.
  - [ ] Model distinct states: neutral/recent (empty), loading, results, empty (no-match). No ambiguous blank.
- [ ] **Task 3 — Grouped result dropdown + click-through (AC3, AC9).**
  - [ ] Render groups by entity type in API order; each result deep-links via the API `deepLink`.
  - [ ] Render **only** API-returned results — no client re-rank/re-filter-to-widen, no synthesized results (AC9).
- [ ] **Task 4 — Full keyboard navigation + WCAG-AA (AC4).**
  - [ ] Shortcut focuses the bar; arrow keys traverse results across groups; Enter opens; Esc dismisses. Implement the combobox/listbox a11y pattern (`role`, `aria-expanded`, active-descendant); visible focus.
  - [ ] Verify the full flow is mouse-free.
- [ ] **Task 5 — Contextual scope + entity-type filters (AC6, AC7).**
  - [ ] On a Project screen, default the contextual `projectId` scope with a **widen-to-all** affordance; pass `types[]` for entity-type filters. Both **narrow only**.
- [ ] **Task 6 — Empty / no-match / special-char states (AC8).**
  - [ ] Empty `q` → neutral/recent; no-match → distinct empty state (not blank/spinner); special/injection chars → passed literally, benign UI result, never a client error.
- [ ] **Task 7 — §3.4 frontend suite (AC1–AC8; §3.2 idiom).**
  - [ ] **Vitest unit:** debounce coalesces rapid keystrokes into the trailing call; results render **grouped by type**; the **empty state** renders on no-match (distinct from neutral + loading); the UI renders **only** API-returned results (no client-side widening) — AC9.
  - [ ] **Playwright E2E (semantic locators):** the bar is **present on every screen** (app-shell top bar); **keyboard-only** flow (shortcut → arrow → Enter opens → Esc dismisses); **contextual scope** on a Project screen narrows + the **widen-to-all** affordance restores; entity-type filters narrow correctly; run in **light and dark** (8.9).

## Dev Notes

- **The API is the authority; the UI never widens (R6, FR-AUTH5).** 8.18 applies RBAC **in the query** (existence-hiding) — the bar renders only what it returns and adds no path that could reveal a withheld entity. UI scope adaptation is convenience, not a security boundary. Never use a client store as the scope source; never re-rank/re-filter to surface more than the API returned.
- **BFF proxy only (§13).** The browser never touches Postgres/kube. All search traffic flows through the BFF's identity-aware proxy to 8.18 — the same choke point as every other console read.
- **Debounce + keyboard nav + grouped dropdown are console concerns (§17.5).** The API is stateless; interactivity is entirely this story's job. Debounce is trailing-edge (coalesce to one call), not throttle-per-keystroke.
- **Empty vs no-match vs loading are three distinct states.** Empty `q` → neutral/recent; in-flight → loading; matched-nothing → empty state. Never collapse them into a blank or a permanent spinner (FR-SEARCH5 / §3.4).
- **Special/injection chars are the server's problem, handled safely.** The bar passes them **literally** to 8.18 (which uses `websearch_to_tsquery` + parameterized binds) — the UI must not pre-validate/reject them or treat them as an error; it just renders the benign/empty API result.
- **Blocked on the 8.18 gate.** Do not close this story until 8.18's §6.7.3 I4 RBAC-leak gate + determinism guard are green — shipping the bar over an unscoped backend would leak existence.

### Project Structure Notes

- **Repo shape (current, branch-dependent):** the console front end is early — `console/e2e/` holds the Playwright E2E harness (incl. `console/e2e/auth/`) on the current branch; the app-shell / top-bar (8.13) and theme tokens (8.9) land with their own stories. The bar lives in the **console app-shell top-bar** region; add it there rather than creating a standalone widget outside the shell.
- **BFF route:** add/extend the Next.js BFF proxy route that forwards to apiserver `GET /api/v1/search` under the §13 identity-aware layer — the bar calls the BFF route, never the apiserver/Postgres directly.
- **Tests:** Vitest units next to the component; Playwright E2E in `console/e2e/` (semantic locators, light+dark), matching the §3.2 console idiom. Do not introduce a new test framework.
- **If 8.18 / 8.13 / 8.9 are not yet merged when you start:** build the bar against the BFF-proxy + API response-shape **interface** and a mocked API; the keyboard-nav, debounce, grouping, and empty-state behaviors are fully testable now and are the deliverable. Coordinate the top-bar slot with 8.13 and tokens with 8.9 rather than forking either.

### References

- [Source: docs/bmad/02-prd.md#9.16 Theme P] — FR-SEARCH1 (top-bar, always visible), FR-SEARCH2 (debounced, grouped dropdown, click-through, full keyboard nav), FR-SEARCH4 (contextual per-Project scope + entity-type filters, narrow-never-widen), FR-SEARCH5 (graceful empty/no-match/special-char).
- [Source: docs/bmad/03-architecture.md#17.5 Global Cross-Entity Search] — "debounce + keyboard nav + grouped dropdown are console concerns"; stateless API; `projectId`/`types` narrow within the RBAC floor.
- [Source: docs/bmad/03-architecture.md#13] — Next.js BFF proxy → apiserver; browser never touches Postgres/kube; one identity-aware choke point.
- [Source: docs/bmad/05-testing-strategy.md#3.4 Global cross-entity search — Frontend] — Vitest (debounce, grouping, empty-state, no client-widening); Playwright (bar-on-every-screen, keyboard-only, contextual scope + widen, entity-type filters, light+dark).
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8 row 8.19] — epic-level AC + deps (8.18 API, 8.13 app shell, 8.9 theme); UX `12-global-search` (new Designer ticket).
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8 header, nav IA] — Project-rooted hierarchy; app shell = 8.13; global search context.

### Open questions (for the dev agent to resolve with the named owner — do not block the build)

1. **UX mock delivery (Designer / ISI-2150 set).** The `12-global-search` mock is a new Designer ticket. Confirm whether it is delivered when this story starts; if not, build to the FR-SEARCH2/4/5 behavior contract and reconcile visual details (grouping layout, filter chip placement, empty-state copy) to the mock when it lands.
2. **Focus shortcut key (Designer / PM).** Confirm the keyboard shortcut that focuses the bar (e.g. `/` or `Cmd/Ctrl-K`) and any platform conventions, so it doesn't collide with existing app-shell shortcuts (8.13).
3. **App-shell top-bar slot (8.13 owner).** Confirm the exact top-bar slot/region the bar occupies and the responsive behavior (§17.3: full-width mobile / icon-triggered tablet / inline desktop) so the bar composes with the 8.13 shell rather than forking a second top bar.

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
