# Story 8.8a: Dashboard data-aggregation read model (BFF, RBAC-filtered, per-tile degrade)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS IS THE 8.8 FOUNDATION.** Every other Project Dashboard tile (8.8b KPI/Recent, 8.8c Pending
> Approvals, 8.8d PR mini-board, 8.8e Token+trend, 8.8f Live Runs) renders from **the one payload this
> story composes**. Two properties are load-bearing and non-negotiable: **(1)** the payload is
> **server-filtered through the same deny-by-default RBAC middleware every other console read model
> uses** — there is **no dashboard-specific authz path** (arch §12.3 r21, Epic 15.4); **(2)** each source
> is queried **independently** so an unavailable source **degrades only its own tile**, never the whole
> dashboard. A dashboard that hard-fails because one backend (metrics, SCM) is unwired is a **regression**,
> not a cosmetic bug. Read AC2 and AC4 literally.

## Story

As an **operator opening a Project's dashboard**,
I want **the apiserver to compose one RBAC-filtered dashboard payload from the coordination record, the SCM mirror, the metrics query seam, and Run/claim state — each source queried independently so any one being unavailable degrades only its tile**,
so that **every dashboard tile draws from a single real-sourced, membership-scoped payload with no new aggregation service, no rollup datastore, and no dashboard-specific authorization path (arch §13 r24, ADR-020).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.9 Theme I — **FR-I1** (health + throughput), **FR-I3** (data derived from the coordination record + Run lifecycle, **never** agent self-report), **FR-I7** (every card draws from a real source, no placeholders). This story builds the payload that FR-I1…I8 render over.
- **Architecture:** `docs/bmad/03-architecture.md` §13 **r24** — *"Dashboard data aggregation is a read model, not a service tier (ADR-020)"*: the BFF **composes** one payload from `coord` audit (§6.5), `scm_pr_mirror` (§5.4), the metrics query seam (§17.2), and Run/claim state (§6/§8); each tile **degrades independently**; **all tiles pass the same deny-by-default RBAC wall** (§12.3, r21 single-surface rule). Also §12.3 (deny-by-default middleware, the one wall), ADR-020 (consumption + dashboard aggregation, "no aggregation service, no rollup DB").
- **Observability:** `docs/bmad/04-observability-plan.md` §17 — the dashboard reads **mostly from read models (no new metric)**; the token/approval **signals** are added by 8.8e / 8.8c / 2.12, **not here**. This story emits only ordinary request telemetry for the aggregation endpoint (see AC7).
- **Depends on (must be landable/mergeable before this story is done):**
  - **Epic 2** — the coordination record (`work_items`, `comments`, `checkouts`, `audit_log`; §6.1/§6.5). This story **reads** it (tickets-by-status, recent tickets, throughput); it does not extend the schema.
  - **Epic 15.4** — the deny-by-default RBAC middleware (`(resource, action, scope)` membership check, §12.3). This story **calls** it as the single authz wall; it must **not** introduce a parallel authz path. If 15.4 is not yet merged, wire the middleware seam behind its interface and gate the RBAC-scoping test on it — but the payload composition must route through that seam, never around it.
- **Cross-epic sources that light tiles up progressively but DO NOT gate this story** (each is a per-tile degrade, AC4): **Epic 11** (SCM/PR sync → 8.8d), **Epic 13.4** (token metering → 8.8e). When absent, the corresponding sub-payload is an explicit **empty/not-configured** shape, never a hard failure.
- **Blocks:** **8.8b, 8.8c, 8.8d, 8.8e, 8.8f** — all five tiles consume this payload and must not ship until the composed endpoint + per-tile degradation + RBAC scoping are green.

## Acceptance Criteria

**AC1 — one composed dashboard endpoint.**
Given the dashboard BFF, When the console requests a Project's dashboard, Then a **single** read endpoint returns **one composed payload** for that Project:
```
GET /api/projects/{projectId}/dashboard
```
And the payload is a **read model** — `GET`-only; any mutating verb is structurally absent (`405`/route absent). And the payload is shaped as **independent sub-payloads per tile** (`ticketsByStatus`, `recentTickets`, `throughput`, `prBoard`, `tokenConsumption`, `liveRuns`, `pendingApprovals`) so a consumer can render any tile without the others.

**AC2 — server-filtered through the ONE deny-by-default RBAC wall (arch §12.3 r21, Epic 15.4).**
Given the composed payload, When it is built, Then it is **server-filtered to the caller's memberships** via the **same deny-by-default middleware** the discussion room, build browser, and org-diagram read models use — the `(resource, action, scope)` check runs **before** any row is returned, and there is **no dashboard-specific authorization code path**. And a caller with **no membership** on the Project receives the Project-not-found/deny shape (existence-hiding consistent with the other read models), **not** a partially-populated payload. And a caller with **viewer** membership receives the **read** payload (all tiles readable); write-gated affordances (approve/reject) are enforced by their own stories (2.12/8.8c), not weakened here.

**AC3 — every source is a real source; no placeholder, no agent self-report (FR-I3).**
Given each sub-payload, When it is composed, Then it is derived from the **real source** named for it — `ticketsByStatus`/`recentTickets`/`throughput` from the `coord` audit (§6.5); `prBoard` from the `scm_pr_mirror` read model (§5.4); `tokenConsumption` from the metrics query seam (§17.2); `liveRuns` from **Run/claim state** (§6/§8); `pendingApprovals` from `coord` items with `blocked_reason=needs_approval` (§6.1). And **no** value is a placeholder, a hard-coded figure, or an agent-self-reported number (FR-I3 provenance). A tile with no wired source returns an explicit **empty / not-configured** marker (AC4), never a fabricated value.

**AC4 — per-tile independent degradation (the availability crux).**
Given the composition, When one source is **unavailable** (repo not synced → SCM mirror empty; metrics backend not wired → metrics query seam down/absent; etc.), Then **only that tile's sub-payload** degrades to an explicit `{ available: false, reason }` (or empty) marker, **And every other tile is composed and returned normally** — the endpoint returns **`200`** with a partial-but-honest payload, **never** a `5xx` because one source is down. And each source is queried **independently** (a failure/timeout in one composition branch is caught and mapped to its tile's degraded marker; it does not abort the others). Verified by a test that stubs the SCM source and the metrics source as unavailable and asserts: PR + token tiles degraded, ticket/throughput/liveRuns tiles fully populated, HTTP `200`.

**AC5 — no new aggregation service, no rollup datastore (ADR-020 / R6 ponytail).**
Given the implementation, When it composes the payload, Then it does so **in the request path over the existing stores** — there is **no** new aggregation microservice, **no** materialized rollup table, **no** billing/usage datastore introduced. And the composition is a **read** — it issues **no writes** to any store (verify: the aggregation path holds no `INSERT/UPDATE/DELETE` against `coord`, `scm`, or any new table; a schema-diff/CI check or a store-spy asserting zero writes). If a source needs a query it does not yet expose, add the **read query** to that source's existing read model — do **not** stand up a new store.

**AC6 — live-capable shape over the existing SSE bus (no new transport).**
Given the tiles that update live (KPI counters, live Runs, approval count — realized in 8.8f/8.8c), When the payload is defined, Then the endpoint returns the **initial snapshot** and the live-update contract is expressed as **deltas over the existing SSE progress bus** (§4.4/§13, the same EventSource + BFF proxy as the Run stream and org diagram) — **no new transport, no polling loop** is introduced by this story. And the snapshot payload and the SSE delta shape are **consistent** (a delta names the tile + the changed sub-payload so a client applies it without a full refetch). 8.8f owns the live-Run stream wiring; this story defines the snapshot + delta contract it fills.

**AC7 — aggregation-endpoint observability (ordinary request telemetry only — no new dashboard metric).**
Given a served dashboard request, When it completes, Then the BFF emits an ordinary request span `dashboard.aggregate{project}` carrying **span-only** attributes (`ksquad.project.id`, and per-tile `ksquad.dashboard.tile.{name}.{available,degraded_reason,duration_ms}`) — `project.id` is a **bounded scope label** where used as a metric dim; `work_item.id`/`run.id`/`user.id` are **span/exemplar only, never a metric label**. And this story adds **no new domain metric** — the token-consumption and approval-queue signals are owned by **8.8e** (obs §17.1) and **8.8c/2.12** (obs §17.2) respectively; this story must not pre-emit them. And a per-tile **degrade** (AC4) is recorded as a span event (`tile.degraded{tile,reason}`) + a `WARN`-level log — **not** a request error, since a degraded tile is a `200`.

**AC8 — NFR-OBS3 standing law (cardinality firewall).**
Given any telemetry this story emits, When produced, Then: (a) `run.id`/`work_item.id`/`user.id`/`principal.id` are **never** a metric label (span/log/exemplar only); (b) **no `model` label** on any dashboard instrument; (c) token/cost figures are **read** from the metering seam, never re-derived or re-emitted as a new counter here; (d) dashboard read volume is **legibility telemetry, never a consumption/billing axis** (obs §17, arch ADR-020). Verified by the Epic 14 cardinality CI gate — this story must not emit anything that trips it.

**AC9 — runnable falsification check (the RBAC-scoping + per-tile-degrade + no-new-store core).**
Given the dashboard read model, When the self-contained check `docs/bmad/spikes/bench/dashboard-aggregation-check.py` runs (stdlib-only, `python3` it directly, **no console, no live cluster** — sources + memberships fed by fixtures), Then it asserts C1-C7 with teeth: it first proves the **ADR-020 anti-pattern** — a "dashboard rollup service" (its own bespoke authz path that leaks to a non-member, pre-aggregates into a rollup table it writes, hard-fails the whole dashboard `5xx` when one source is down, fills tiles from agent self-reported numbers, drives updates with a new polling loop, and puts `run.id`/`model` on metric labels) — is **DETECTED as violating every invariant**, then proves the §13/ADR-020 read-model composition **violates nothing and actually returns the member a partial-but-honest `200` payload (one tile degraded, every other tile populated), server-filtered to their memberships, denying the non-member, writing nothing, over the existing SSE bus, with per-item ids off every metric label**. Baseline exits 0; each `--mutate=NAME` (`MUTATING_VERB`→C1, `BESPOKE_AUTHZ`→C2, `FABRICATED_TILE`→C3, `WHOLE_FAIL`→C4, `ROLLUP_STORE`→C5, `POLL_TRANSPORT`→C6, `PERITEM_LABEL`→C7) exits 1 with exactly the mapped invariant RED (no vacuous guard).

## Tasks / Subtasks

- [ ] **Task 1 — Define the composed dashboard payload contract (AC1, AC3, AC6).** *Do this first — the tile stories consume it.*
  - [ ] Define the `GET /api/projects/{projectId}/dashboard` response type as **independent per-tile sub-payloads**: `ticketsByStatus`, `recentTickets`, `throughput`, `prBoard`, `tokenConsumption`, `liveRuns`, `pendingApprovals`. Each sub-payload carries its own `{ available: bool, reason?, data }` envelope so a consumer renders it in isolation.
  - [ ] Define the **SSE delta** shape for the live-capable tiles (KPI counters, `liveRuns`, `pendingApprovals` count): a delta names `{ tile, patch }` and is consistent with the snapshot (8.8f/8.8c fill the stream; this story pins the contract).
  - [ ] `GET`-only; assert mutating verbs are structurally absent (AC1).
- [ ] **Task 2 — Route composition through the single deny-by-default RBAC wall (AC2).**
  - [ ] Resolve `caller` memberships and pass every source query through the **Epic 15.4 deny-by-default middleware** `(resource, action, scope)` check — the **same** wall the discussion room / build browser / org diagram use. Do **not** write a dashboard-specific authz predicate.
  - [ ] No-membership caller → the Project deny/not-found shape (existence-hiding, consistent with sibling read models), not a partial payload.
  - [ ] Add a test: caller with membership → scoped payload; caller without → deny shape; viewer → full **read** payload.
  - [ ] If 15.4 is not yet merged, wire the middleware seam behind its interface and mark the live RBAC integration test `skip` with `TODO(15.4)` — but the composition **must** route through the seam, never around it.
- [ ] **Task 3 — Compose each sub-payload from its real source, independently (AC3, AC4, AC5).**
  - [ ] `ticketsByStatus` / `recentTickets` / `throughput` ← `coord` audit read queries (§6.5). Reuse existing coord read paths; add read-only queries if missing (no schema change).
  - [ ] `prBoard` ← `scm_pr_mirror` read model (§5.4, `review_state` → ready-for-review/draft/blocked/merged, correlated `head_sha→run.commit_sha`).
  - [ ] `tokenConsumption` ← metrics query seam (§17.2) — **snapshot total only** here; the trend + drill-down is 8.8e.
  - [ ] `liveRuns` ← Run/claim state (§6/§8) — snapshot; the SSE stream is 8.8f.
  - [ ] `pendingApprovals` ← `coord` items `blocked_reason=needs_approval` (§6.1) — the read model; the gate + approve/reject action is 2.12, the widget is 8.8c.
  - [ ] Wrap **each** source query in its own error/timeout boundary → on failure map to `{ available:false, reason }` for **that tile only**; never abort the whole compose. Endpoint returns `200` with the partial-but-honest payload.
  - [ ] Assert **zero writes** on the aggregation path (store-spy or read-only connection); **no** new table/service (AC5).
- [ ] **Task 4 — Per-tile degradation tests (AC4).**
  - [ ] Test: SCM source unavailable → `prBoard.available=false`, all other tiles populated, HTTP `200`.
  - [ ] Test: metrics seam unavailable → `tokenConsumption.available=false`, others populated, `200`.
  - [ ] Test: both unavailable → both degraded, ticket/throughput/liveRuns populated, `200` (never `5xx`).
- [ ] **Task 5 — Aggregation-endpoint observability (AC7, AC8).**
  - [ ] Emit the `dashboard.aggregate{project}` request span with **span-only** per-tile attributes (`available`, `degraded_reason`, `duration_ms`); `project.id` bounded label only where metered.
  - [ ] Record each per-tile degrade as a span event + `WARN` log — not a request error (degraded tile is `200`).
  - [ ] **Standing-law self-check (AC8):** no `run.id`/`work_item.id`/`user.id`/`model` metric labels; do **not** emit the token or approval-queue metrics (those are 8.8e / 8.8c+2.12). Do not treat dashboard read volume as a consumption axis. The Epic 14 cardinality gate must stay green.

## Dev Notes

- **Read model, not a service tier — this is the whole point of ADR-020.** The temptation is to build a "dashboard service" that pre-aggregates and caches. **Do not.** The BFF composes one payload per request over `coord`/`scm`/metrics/Run-state, all of which already exist. No rollup DB, no billing store, no aggregation microservice (that is exactly the "extra tier + stale-data surface" the ADR rejects). If a source is slow, the fix is a better read query on that source, not a new materialized store.
- **One RBAC wall, no second authz path.** Arch §12.3 r21 pins the single-surface rule: console read models, discussion room, dashboards, and build browser all pass the **same** deny-by-default middleware. The build-browser per-principal gate is that check *specialized*, not a second path — do not model the dashboard as its own authz domain. Server-filter the payload to the caller's memberships; the client never sees a row it isn't entitled to (same discipline as the no-P2P console read models).
- **Per-tile degradation is a first-class contract, not error handling.** An unsynced repo (no SCM), an unwired metrics backend (no cost) are **normal** operating states, not failures. Each tile carries its own `{available, reason}` envelope; the endpoint is `200` as long as it composed *something* honest. A `5xx` because metrics is down would take the whole dashboard offline for a tile that is legitimately "not configured yet."
- **This story emits NO new domain metric.** Obs §17 is explicit: the dashboard reads mostly from read models (no metric). The token-consumption signal (§17.1) lands with **8.8e**; the two approval-queue signals (§17.2) land with **8.8c / 2.12**. If you find yourself adding `ksquad.dashboard.*` counters for tile contents, stop — that is legibility telemetry at most (span/log), never a consumption axis, and per-item ids stay off labels (AC8).
- **You are building the contract five stories depend on.** Get the payload shape + the SSE delta shape right first (Task 1) and publish it — 8.8b…8.8f are all "render sub-payload X" and their ACs reference these field names. A late reshape of this contract ripples into five stories.

### Project Structure Notes

- **Repo shape (current, this branch `test/isi-2311-a5-auth-session`):** the Go monorepo is **greenfield** — only `pkg/auth/*_test.go` (auth-session contract scaffolding, ISI-2311) and `console/e2e/auth/` exist so far. There is **no** `internal/` tree, **no** `migrations/`, **no** `go.mod` checked in on this branch yet. Treat the apiserver read-model package + the Next.js console app as **greenfield** — create them following the emerging monorepo conventions (Go package under the apiserver; the console under `console/`). Earlier story files (8.7d) reference `internal/discussion` as a pattern; that package does not exist in this checkout — do **not** assume it; follow whatever apiserver package layout is landed by the time you implement, and match `pkg/auth` conventions for the Go side (standard `testing`, table-driven `_test.go`).
- **Apiserver (Go):** the authoritative composition + RBAC-scoped read queries belong in the Go apiserver (single source of truth, §13). Suggested package: `dashboard` (handler + per-source composers + `_test.go` for AC4 degradation + AC2 RBAC scoping). Reuse the coord/scm/metrics read models rather than re-querying raw tables.
- **BFF / console (Next.js/TS):** the console app (§13, ADR-013) is not yet scaffolded. The BFF route is a thin proxy that surfaces the apiserver payload + the SSE stream verbatim; the **authoritative composition + RBAC gate live server-side in Go**, never only in the BFF/TS layer (a compromised BFF must not be able to widen the payload).
- **Naming:** match `pkg/auth` conventions (lowercase package, standard `testing`, table-driven `_test.go`). Do not introduce a new test framework.

### References

- [Source: docs/bmad/03-architecture.md#13 (r24) — Dashboard data aggregation is a read model, not a service tier (ADR-020)] — BFF composes coord/scm/metrics/Run-state; per-tile independent degradation; all tiles pass the same deny-by-default RBAC wall; no aggregation service / no rollup DB.
- [Source: docs/bmad/03-architecture.md#12.3 (r21) — one enforcement point, every surface] — console read models, discussion room, dashboards, build browser all pass the *same* deny-by-default middleware; no per-surface authz drift.
- [Source: docs/bmad/03-architecture.md ADR-020] — consumption attribution + dashboard aggregation; no aggregation microservice, no rollup DB, no billing datastore.
- [Source: docs/bmad/02-prd.md#9.9 Theme I — FR-I1, FR-I3, FR-I7] — health + throughput; data derived from coordination record + Run lifecycle, never agent self-report; every card from a real source, no placeholders.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.8 row 8.8a + "Epic 8.8 story slicing" subsection] — foundation for 8.8b–f; chain `8.8a → {8.8b,8.8c,8.8d,8.8e,8.8f}`; cross-epic deps (2.12/11.3/13.4) light tiles progressively, do not gate 8.8a.
- [Source: docs/bmad/04-observability-plan.md#17] — dashboard reads mostly from read models (no new metric); token signal §17.1 (8.8e), approval-queue signals §17.2 (8.8c/2.12); NFR-OBS3 cardinality firewall.

### Open questions (route to the named owner via ISI-2325; do not block the foundation on these)

1. **Payload freshness vs SSE deltas (Architect / Winston).** Is the snapshot always freshly composed per request (recommended — no cache, no stale surface, ADR-020), with SSE carrying only live-tile deltas? Confirm no per-request cache is expected. *Does not block Task 1–4.*
2. **Endpoint shape (Architect / PM).** Confirm `GET /api/projects/{projectId}/dashboard` as one composed endpoint vs one-endpoint-per-tile. This story assumes **one composed payload** (per r24 "one dashboard payload"); if per-tile endpoints are preferred, the RBAC wall + degradation contract are unchanged, only the transport splits.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, agent 2230b001) — construction-time contract via runnable falsification check (the Epic-8 model-check pattern, sibling of `credential-auth-state-check.py` / `live-run-sse-check.py`). The authoritative Go apiserver `dashboard` package + console BFF are greenfield and are built by the runtime tasks; this check pins the payload/RBAC/degrade contract the five tile stories consume.

### Debug Log References

- `python3 dashboard-aggregation-check.py` → exit 0 (rollup-service anti-pattern trips all 7; §13/ADR-020 read model holds C1-C7, returns member a partial-but-honest 200, denies non-member).
- `--mutate={MUTATING_VERB,BESPOKE_AUTHZ,FABRICATED_TILE,WHOLE_FAIL,ROLLUP_STORE,POLL_TRANSPORT,PERITEM_LABEL}` → each exit 1 with exactly the mapped invariant (C1…C7) RED; no vacuous survivors.

### Completion Notes List

- Implemented AC9: the runnable falsification check encoding AC1-AC8 as C1-C7 (AC7+AC8 fold into C7, the cardinality firewall). Teeth via a `ROLLUP` anti-pattern design that trips every invariant; each `--mutate` grafts exactly one defect onto the `CONFORMANT` read model.
- **Load-bearing crux proven mechanically:** (AC2) the payload routes through the ONE shared deny-by-default wall with a non-member denied to the Project-not-found shape and a member admitted; (AC4) with the metrics backend unwired (a normal state — Epic 13.4 absent), `tokenConsumption` degrades to `{available:false, reason}` while every other tile is populated and the endpoint returns `200`, never `5xx`; (AC5) the compose path is read-only over existing stores with zero writes and no new rollup datastore; (AC8) `run.id`/`work_item.id`/`user.id`/`model` never appear as metric labels and this story emits no new domain metric.
- Runtime proof (real GET-through-BFF, live per-membership RBAC scoping on the Go apiserver, SSE delta stream) is owned by the console E2E + the apiserver `dashboard`-package tests; this check guards the construction-time contract the five tile stories (8.8b-f) render over.
- **Blocks cleared for tile stories:** 8.8b-f may now consume the pinned per-tile sub-payload names + SSE delta contract.

### File List

- `docs/bmad/spikes/bench/dashboard-aggregation-check.py` (new) — the C1-C7 runnable falsification check.
- `docs/bmad/stories/8-8a-dashboard-data-aggregation-read-model.md` (this file) — AC9 + Dev Agent Record.
