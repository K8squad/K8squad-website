# Story 8.18: Global cross-entity search API — apiserver `pkg/search`, RBAC-in-query (FR-SEARCH1/3/4/5, NFR-PERF3/SEC10)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **⛔ THIS STORY CARRIES A BLOCKING SECURITY GATE.** The **cross-project search-scope leak** case
> (05-testing §6.7.3 **I4**) is a **required security assertion** (S4 / NFR-SEC10 family). Epic 8 search
> stories — this one **and** 8.19 — **cannot close** until I4 and its **determinism guard** are green. The
> RBAC scope predicate (`project_id = ANY(allowed)`) must be applied **inside the query, before rank/LIMIT**;
> an out-of-scope entity that appears in results **or previews or a group `count`** is a **security
> regression** (existence-hiding, same rule as the build browser §8.7d), not a cosmetic bug. Building the
> `tsquery` from a raw user string, or post-filtering a broad result set by RBAC in app code, are both
> **prohibited** — read every acceptance criterion literally.

## Story

As the **operator console's edge (BFF)**,
I want **a single RBAC-scoped `GET /api/v1/search` endpoint on the apiserver that finds work items/tickets, Runs, files/artifacts, agents, and Projects for a query — grouped by entity type, relevance-ranked, with the caller's allowed-`project_id` set applied *in the query* so out-of-scope entities never enter results, previews, or counts, and with the free-text query built injection-safely via `websearch_to_tsquery` + parameterized binds**,
so that **the top-bar search bar (8.19) has one backend to call that is a pure derived read-model — no new store of record, no coordination path, no side door around the §12.3 RBAC wall — surfacing only what the caller could already reach (S2 legibility, R6 scope guard).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.16 Theme P — **FR-SEARCH1** (cross-entity), **FR-SEARCH3** (server-side RBAC scope, existence-hiding), **FR-SEARCH4** (contextual `projectId`/type filters narrow, never widen), **FR-SEARCH5** (graceful empty/no-match/special-char, no injection); **NFR-PERF3** (interactive, RBAC-in-query, off the correctness-critical path); **NFR-SEC10** (server-side authZ, never UI-only). *(FR-SEARCH2 — debounce/keyboard nav/dropdown — is console-side, story 8.19.)*
- **Architecture:** `docs/bmad/03-architecture.md` **§17.5** (the design of record for `pkg/search`) + **ADR-039** (Postgres FTS in-apiserver vs dedicated search cluster). Also §12.3 (deny-by-default RBAC middleware / `auth.project_memberships`), §8.7d (existence-hiding rule this reuses), §4/ADR-001 (one Postgres), §5.4 (scm source), §6.1 (coord source), §8.7c (build-snapshot paths), §13 (BFF proxy).
- **Epics:** `docs/bmad/04-epics-and-stories.md` — Epic 8 row **8.18** (epic-level AC + deps).
- **Testing:** `docs/bmad/05-testing-strategy.md` **§3.4** (backend L1 dimensions: relevance/grouping, RBAC-filter + determinism guard, empty/no-match, special chars) + **§6.7.3 I4** (the cross-project search-scope leak — the required security gate).
- **Depends on (must be resolvable before this story is done):**
  - **Epic 2** (coordination record) — provides `coord.work_item` / `coord.comment` / `coord.artifact` this searches. If a source table is not yet present, search that source behind the same result-merge interface and mark its sub-query test `skip` with a `TODO(epic-2)` — but the **RBAC-in-query gate and the I4 case do not depend on any one source and must be fully implemented and tested** against whatever seedable corpus exists.
  - **Epic 15.4** (identity/membership resolution) — provides the caller → `auth.project_memberships` → allowed-`project_id` resolution the scope predicate binds. This is the **load-bearing dependency**: the gate cannot be certified without it. If 15.4's resolver is not yet landable, implement the gate against the resolver **interface** and seed memberships directly in the L1 test fixture — do **not** stub the predicate to `allow`, and do **not** skip the I4 leak test.
- **Blocks:** **8.19** (top-bar search bar) consumes this API. 8.19 cannot close until this story's I4 gate is green.
- **Not a blocker:** relevance weighting / index-freshness **tuning** and the dedicated-index upgrade trigger are **Architecture-owned (OQ21)** — assert ordering *invariants*, not numeric scores; do not block on OQ21.

## Acceptance Criteria

**AC1 — one GET endpoint, grouped relevance-ranked response.**
Given an authenticated caller and a query `q`, When `GET /api/v1/search?q=&projectId=&types=` is called, Then it returns results **grouped by entity type** — `tickets` (work items), `files` (artifacts/build-snapshot paths), `agents` (`Agent`/`Team`/`Role`), `runs`, `projects` — each group **relevance-ranked**, and each result carries `{ type, id, label, deepLink }` (deep-link target to that entity's detail surface). And the endpoint is **`GET`-only** (a mutating verb is structurally absent / `405`) — search is a read-only derived read-model (R6), never a claim/mutate path.

**AC2 — RBAC scope applied *in the query*, before rank/LIMIT (the security crux; FR-SEARCH3, NFR-SEC10).**
Given any request, When `pkg/search` builds each source sub-query, Then it first resolves `caller → auth.project_memberships → allowed project_id set` (§12.3) and injects `WHERE project_id = ANY($allowed)` (plus the `global_role=admin` fleet-wide bypass) into **every** sub-query **before** any `ts_rank`/ordering/`LIMIT`. And the RBAC predicate is **never** applied by post-filtering a broader result set in app code (that would leak existence via counts/latency — prohibited by NFR-PERF3 + §17.5).

**AC3 — existence-hiding: out-of-scope entities absent from results, previews, AND counts.**
Given caller **A** a member of Project **P1** only and an entity that matches `q` in Project **P2** (which A is not a member of), When A searches, Then the P2 entity is **absent** from A's results, from any preview, **and from the group `count`** — A **cannot infer** the P2 entity exists (existence-hiding, same rule as §8.7d / I1). **Positive controls:** A **does** get its own P1 matches (not a blanket-empty bug); a caller with `global_role=admin` gets the **fleet-wide** match (bypass).

**AC4 — determinism guard: removing the scope predicate fails the build.**
Given the L1 RBAC-filter suite, When a red-team variant **removes** the `project_id = ANY(...)` predicate so a cross-project row leaks, Then the build **fails fast** (proves the scope is *in the query*, not app-layer post-filtering). This guard is the mechanism that certifies AC2/AC3 stay true under refactor (matches §4.1/§6.7.0 determinism-guard idiom).

**AC5 — injection-safe query construction (FR-SEARCH5, NFR-SEC10).**
Given free-text `q`, When the query is built, Then user input is turned into a query via **`websearch_to_tsquery`** (or `plainto_tsquery`) with **parameterized binds** — it is **never** concatenated into SQL or a `tsquery`. And inputs containing `:`, `*`, quotes, path separators, FTS operators, and **injection-shaped strings** (`'; DROP …`, `%`, `_`, `") OR 1=1 --`) are treated as **literal search terms**: they return sensible/empty results, **never error**, and **never execute as SQL/FTS syntax**. A query that would delete or leak rows if interpolated **must** return a benign empty/no-match and leave the corpus intact.

**AC6 — empty and no-match states (FR-SEARCH5).**
Given the endpoint, When `q` is **empty**, Then it short-circuits **server-side** to a neutral/recent state (**no** wildcard full-table scan, no error); When `q` **matches nothing** the caller can see, Then it returns **empty groups with `200`** — never a `500`, error, or endless spinner. (These are the states 8.19 renders as FR-SEARCH5's empty UI.)

**AC7 — `projectId`/`types` narrow within the RBAC floor, never widen (FR-SEARCH4).**
Given the optional `projectId` and `types[]` params, When they are supplied, Then they **shrink** the result set **within** the AC2 authorization floor — `projectId` restricts to that one Project **only if** it is already in the caller's allowed set (a `projectId` outside the allowed set yields **empty**, not an error, and never widens), and `types` restricts to the named entity types. They can only narrow, never widen, what the caller may see.

**AC8 — sources searched / explicitly not searched (§17.5 trust boundary).**
Given the corpus, When search runs, Then it covers **record-backed** sources via Postgres FTS live at query time — `coord.work_item` (title/body), `coord.comment` (body), `coord.artifact` + **build-snapshot `meta` paths/filenames** (§8.7c — *paths, not file contents*), `scm` mirror titles (§5.4), `Run` metadata — **and** **CRD-backed** entities (`Agent`/`Team`/`Role`/`Project`) via the apiserver **informer/lister cache** (name + labels + spec summary), filtered by the same allowed-`Project` set (and `Team`-scope for agents, §12.1). And it **explicitly does NOT** search **memory-record *content*** (FR-E7 trust boundary — untrusted, provenance-gated; surfaced only via the memory MCP path) **or raw file/blob bodies** (build browser stays the contents surface) — these are Phase-2, not v1 scope.

**AC9 — Postgres FTS mechanism, no new deployment/dependency (ADR-039, ADR-001).**
Given the implementation, When it ships, Then it rides **PostgreSQL FTS** (`tsvector`/`tsquery` + a **GIN** index; `pg_trgm` for prefix/typo-tolerant **name** matching) over tables KSquad already owns, as a **library package `pkg/search` inside the existing apiserver** — **no** dedicated search cluster, **no** new Go binary, **no** reindex/dual-write pipeline, **no** new store of record (records are searchable live at query time). The only backend delta is the **GIN index migration** + the `pkg/search` package (ADR-001 "one Postgres" intact).

**AC10 — ranking invariants (relevance; OQ21 tuning excluded).**
Given a fixed seeded corpus, When results are ranked, Then a **title/name match outranks an incidental body match**, a **prefix/partial name** (`pg_trgm`) matches an agent/project, and ordering is **stable/deterministic** for that fixed corpus. Assert the ordering **invariants** — **not** brittle numeric scores (exact relevance weighting = field boosts / recency decay is **OQ21**, Architecture-owned, tuned post-first-corpus).

**AC11 — off the correctness-critical path (NFR-PERF3).**
Given search load, When queries run, Then the GIN index keeps interactive latency low and the RBAC predicate bounds every scan, and search **never** degrades the coordination/reconcile (claim/lease) path — it is a read through the §12.3 wall, not a write and not on the correctness-critical spine. (Numeric latency target = OQ21; assert the *shape*: indexed, RBAC-bounded, read-only.)

## Tasks / Subtasks

- [ ] **Task 1 — RBAC scope resolution + in-query predicate (AC2, AC3, AC4).** *Do this first — it is the security core.*
  - [ ] Resolve `caller → auth.project_memberships → allowed project_id set` via the §12.3 middleware / Epic 15.4 resolver **interface** (do not re-implement membership; do not trust a client-asserted set). Include the `global_role=admin` fleet-wide bypass.
  - [ ] Thread the allowed set into **every** source sub-query as a parameterized `WHERE project_id = ANY($allowed)` **before** ranking/`LIMIT`. Never post-filter in app code.
  - [ ] Write the **determinism guard** (AC4): a red-team test variant that drops the predicate and leaks a cross-project row **fails the build**. Co-locate it with the query builder so a refactor that removes the predicate trips it.
- [ ] **Task 2 — Injection-safe query builder (AC5).**
  - [ ] Build the FTS query with `websearch_to_tsquery`/`plainto_tsquery` + **parameterized binds** — never string-concatenate user input into SQL or a `tsquery`.
  - [ ] Short-circuit **empty `q`** server-side to the neutral/recent state (no wildcard scan); return **empty groups `200`** on no-match (AC6).
  - [ ] Add the special-char / injection-shaped negative tests (`:`, `*`, quotes, path seps, `'; DROP …`, `%`, `_`, `") OR 1=1 --`) → literal terms, benign result, corpus intact (AC5).
- [ ] **Task 3 — Record-backed sources over Postgres FTS + GIN migration (AC8, AC9, AC10).**
  - [ ] Add the **GIN index migration** over the searched columns (`coord.work_item` title/body, `coord.comment` body, `coord.artifact`/build-snapshot `meta` paths, `scm` mirror titles, `Run` metadata). `pg_trgm` for name columns.
  - [ ] Implement each source sub-query with `ts_rank` scoring; **paths/filenames only** for artifacts — never file contents (AC8 trust boundary).
  - [ ] Confirm **no** new deployment/dependency/reindex pipeline — `pkg/search` is a library in the apiserver (AC9).
- [ ] **Task 4 — CRD-backed sources via informer cache (AC8).**
  - [ ] Search `Agent`/`Team`/`Role`/`Project` via the apiserver informer/lister cache (name + labels + spec summary), `pg_trgm`-style in-process match.
  - [ ] Apply the **same** allowed-`Project` set (and `Team`-scope for agents, §12.1) to the cache results — the CRD path is **not** a bypass around AC2.
- [ ] **Task 5 — Rank-merge + group + response shape (AC1, AC10).**
  - [ ] Normalize per-source scores (`ts_rank` / trigram similarity + recency boost + small entity-type weight) into one ranked list, then **group by entity type** for the response.
  - [ ] Emit the `{ type, id, label, deepLink }` shape per result; assert deterministic ordering for a fixed corpus (AC10).
  - [ ] Honor `projectId`/`types` as **narrowing-only** filters within the RBAC floor (AC7).
- [ ] **Task 6 — Wire the `GET /api/v1/search` endpoint, GET-only (AC1, AC11).**
  - [ ] Expose the endpoint on the apiserver behind the §12.3 identity-aware middleware (same choke point as every other read); assert mutating verbs are structurally absent / `405`.
  - [ ] Confirm the read is off the correctness-critical path (no claim/lease/reconcile interaction) — AC11.
- [ ] **Task 7 — §3.4 backend L1 suite + §6.7.3 I4 security gate (AC2–AC6, AC10; the ⛔ gate).**
  - [ ] Relevance & grouping (AC10); RBAC filtering with A/B/admin + **determinism guard** (AC2–AC4); empty & no-match (AC6); special/injection chars (AC5). Go L1, `testing`+`testify`, Postgres container (§3.1 idiom).
  - [ ] Add the **§6.7.3 I4** case: A-scoped principal queries a term matching entities in **both** Project A and Project B → **only A-scoped results**; a B entity is **absent from results, previews, and the group `count`**; the predicate is **in the query**; **positive controls** A-gets-own + admin-fleet-wide. Tag it `NFR-SEC10`/S4 so the L4 gate tracks it.

## Dev Notes

- **RBAC-in-query is the load-bearing rule.** Search must be **just another read through the §12.3 wall** — it opens no side door around it. The scope predicate lives *in* every sub-query (`project_id = ANY($allowed)`) **before** rank/LIMIT; app-layer post-filtering leaks existence via counts/latency and is explicitly prohibited (§17.5, NFR-PERF3). The `viewer`/`contributor`/`maintainer` grade does **not** change visibility (all three read within a Project) — search scopes on **membership**, not grade.
- **Existence-hiding, same as §8.7d.** An out-of-scope entity is **absent**, never a `403` and never a `count` of `1` — a non-member must not be able to infer a P2 entity exists. This is the I4 assertion and the required security gate.
- **Injection-safe by construction.** `websearch_to_tsquery` + parameterized binds means special/reserved chars are **literal terms**, never operator/SQL injection. Never build a `tsquery` from a raw user string (the ADR-039 anti-pattern).
- **No new store of record, no coordination path.** Search is a **derived read-model** — records are searched **live at query time** over tables KSquad already owns. The two-records invariant (§4/§6, ADR-001) is untouched; there is no projection/reindex table and no NATS/coordination interaction (R6 holds).
- **Trust boundary.** Memory-record **content** (FR-E7/§7.3) and raw file/blob **bodies** are **out of scope in v1** — only artifact **paths/filenames** (§8.7c) and the record/CRD metadata above are searched. Do not widen the corpus into contents.
- **OQ21 is not a blocker.** Relevance *tuning* (field boosts, recency decay), CRD-cache match strategy at scale, and the numeric latency target are Architecture-owned, post-first-corpus. Assert ordering **invariants**, not scores. The dedicated search index (OpenSearch/ES) is the **named upgrade path**, not built until a measured miss triggers it — do not build it here.

### Project Structure Notes

- **Placement:** `pkg/search` **inside the existing apiserver** (Arch §17.5 / ADR-039) — a library package, **not** a new binary or deployment. Follow the repo's Go package conventions (handler / store / `*_test.go` split; table-driven `_test.go` with `testify`). The apiserver already holds the `coord`/`scm`/`auth` schemas and the §12.3 deny-by-default RBAC middleware — reuse them; do not add a fourth Go binary or a new signing key/network hop.
- **Repo shape (current, branch-dependent):** the working tree is early/greenfield — `pkg/auth/` currently holds the A5 auth-session test scaffolding (ISI-2311) and `console/e2e/` the console E2E harness; the coord/scm stores and apiserver wiring land with Epic 2 / their own stories. If a searched source table or the apiserver mux is not yet present when this story starts, implement `pkg/search` against the **store/resolver interfaces** and seed fixtures in the L1 Postgres-container test — the **GIN migration, the injection-safe builder, the RBAC-in-query predicate, and the I4 gate are the non-negotiable deliverables** and must land here regardless of which sources are wired.
- **Migration:** add the **GIN index** (and `pg_trgm` extension enable, if not already) as a `migrations/` step; do not create a `search` projection/materialized table (ADR-039 — FTS reads live).
- **Naming/tests:** match the existing Go test idiom; Postgres-container L1 per §3.1. Do not introduce a new test framework.

### References

- [Source: docs/bmad/03-architecture.md#17.5 Global Cross-Entity Search] — `pkg/search` in-apiserver, Postgres FTS (`tsvector`/GIN + `pg_trgm`), sources searched/not-searched, RBAC-in-query (allowed-`project_id`, existence-hiding), injection-safe `websearch_to_tsquery`, ranking, OQ21.
- [Source: docs/bmad/03-architecture.md ADR-039] — Postgres FTS in-apiserver vs dedicated search cluster; dedicated index = named upgrade path; the prohibited alternatives (post-filtering RBAC, raw-string `tsquery`, projection table, memory-content search).
- [Source: docs/bmad/03-architecture.md#8.7d] — existence-hiding rule (out-of-scope → absent, not `403`) reused here.
- [Source: docs/bmad/03-architecture.md#12.3] — deny-by-default RBAC middleware, `auth.project_memberships`, the one choke point.
- [Source: docs/bmad/02-prd.md#9.16 Theme P] — FR-SEARCH1/3/4/5 + scope guard (read-only cross-entity finder, not a doc search engine / BI surface / mutate path).
- [Source: docs/bmad/02-prd.md#10.3 NFR-PERF3] — interactive, RBAC-in-query (not post-filter), off the correctness-critical path.
- [Source: docs/bmad/02-prd.md#10.1 NFR-SEC10] — server-side authZ, per-Project membership+role checked before returning data, deny-by-construction.
- [Source: docs/bmad/05-testing-strategy.md#3.4 Global cross-entity search] — backend L1 dimensions: relevance/grouping, RBAC-filter + determinism guard, empty/no-match, special/injection chars; positive controls.
- [Source: docs/bmad/05-testing-strategy.md#6.7.3 I4] — cross-project search-scope leak: only A-scoped results, B absent from results/previews/`count`, predicate-in-query, determinism guard fails build, positive controls (A-own + admin-fleet). Required security gate.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8 row 8.18] — epic-level AC + deps (Epic 2 coord, Epic 15.4 identity/membership); backend delta = GIN migration + `pkg/search`, no new deployment.

### Open questions (for the dev agent to resolve with the named owner — do not block the security core)

1. **Membership resolver contract (Architect / Epic 15.4 owner).** Confirm the exact `caller → allowed project_id set` resolver signature and the `admin` fleet-bypass shape exposed by Epic 15.4 identity middleware, so `pkg/search` binds the authoritative set (not a re-derived one). *This does not block Task 1's predicate or the I4 test — seed memberships in the fixture and implement against the interface.*
2. **CRD-cache scope join (Architect / Winston).** Confirm how the informer-cache CRD results (`Agent`/`Team`/`Role`/`Project`) join to the allowed-`Project` set (and `Team`-scope for agents, §12.1) — a `Project` CRD's own visibility vs an `Agent`'s Team-scope — so the CRD path applies AC2 identically and is not a bypass.
3. **Relevance weighting seed (Architect / OQ21).** OQ21 owns tuning; confirm only the *invariants* (title>body, prefix-name match, stable order) are asserted at L1 now, with numeric weights deferred — so this story does not hard-code targets that OQ21 will move.

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
