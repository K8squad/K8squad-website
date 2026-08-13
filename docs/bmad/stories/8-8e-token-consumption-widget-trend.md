# Story 8.8e: Token-consumption widget + trend

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The trend is a QUERY SHAPE over the existing counter — not a new instrument, not a rollup store
> (ADR-020, ponytail).** The signal already exists: `ksquad.agent.tokens` (§5.5). "Tokens consumed (with
> trend)" is that **same series read as a time range** (`rate()`/`increase()`), with per-user/agent/Run
> as **exemplar drill-downs, never labels** (NFR-OBS3). Do not add a new metric, and do not stand up a
> billing/usage datastore. Read AC2, AC5, and AC7 literally.

## Story

As a **finance/ops owner opening a Project's dashboard**,
I want **a token-consumption widget showing the current total (per user/agent/Run/Project) and a trend over a selectable window (tokens/day), with an estimated cost where a price table is configured**,
so that **I see current usage and its direction from the existing metering spine — no new store, degrading gracefully to tokens-only (or throughput-only) when a metrics backend or price table is absent (FR-I2).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.9 **FR-I2** — token/cost consumption attributable **per user, per agent, per Run, per Project**, presented **both as a current total and as a trend over a selectable window** (e.g. tokens/day); surfaces sandbox resource usage for in-flight/recent Runs; **FR-I3** — derived from the coordination record + Run lifecycle, never agent self-report; cost precision bounded by runtime (OQ14).
- **Architecture:** `docs/bmad/03-architecture.md` §13 **r24** + ADR-020 — token/cost rides the **OTel metrics pipeline** (§17.2), read through a **pluggable metrics-backend query seam** that **degrades gracefully** when no backend is wired — never a hard dep, never a new billing datastore; attribution is **per-principal by construction** (BYO creds, §11); the **trend** is a **time-series query** over that same seam (tokens/day over a window), **not** a new store. ADR-020: no aggregation service, no rollup DB, estimate via configurable price table.
- **Observability:** `docs/bmad/04-observability-plan.md` **§17.1** — the signal already exists: `ksquad.agent.tokens{runtime, direction}` (§5.5), aligned to `gen_ai.usage.*` (§7). Current total + per-scope breakdown = the query seam reading `agent.tokens` federated by **bounded** scope labels (`project`, `role`, §16.2). **Trend** = the **identical series read as a time range** (`rate()`/`increase()`), a query shape, not a new instrument. Per-user/per-agent/per-Run drill-down = §15/§16.5 **backend rollup over exemplars/traces** (`work_item.id`/`user.id`/`run.id` stay **exemplars, never labels**). Estimated cost = §16.5 price table, degrades to tokens-only. **No new metric, no billing store.**
- **Depends on (must be landable/mergeable before this story is done):**
  - **8.8a** — the dashboard read model; this story renders + extends the `tokenConsumption` sub-payload (8.8a exposes the snapshot total; this story adds the **trend query** + drill-down + cost).
  - **Epic 13.4** — token metering (emits `ksquad.agent.tokens`, §5.5). **Progressive dep, not a gate:** until 13.4 lands or a metrics backend is wired, the widget **degrades gracefully** (throughput without cost; tokens-only without a price table) per the 8.8a per-tile rule. The widget's query shape + rendering land now.
- **Blocked by:** 8.8a. **Progressive:** Epic 13.4 (token metering) + a wired metrics backend + a configured price table (each degrades independently).

## Acceptance Criteria

**AC1 — current total + per-scope breakdown (from the metrics query seam).**
Given the metrics query seam (Epic 13.4, §17.2), When the operator opens the dashboard, Then the widget shows the **current total** token consumption for the Project, with a **per-scope breakdown** along the **per user / per agent / per Run / per Project** axes (FR-I2). And the at-a-glance total + the label-speed breakdown read `ksquad.agent.tokens` federated by the **bounded** scope labels (`project`, `role`, §16.2); the finer per-user/agent/Run breakdown is the exemplar drill-down (AC5).

**AC2 — trend over a selectable window (a query shape, not a new instrument).**
Given the same `ksquad.agent.tokens` series, When the operator selects a **time window**, Then the widget shows a **trend** (tokens/day over the window) computed as the **identical series read as a time range** — `rate()`/`increase()` over the window (obs §17.1). And this is **a query over the existing counter, not a new metric** and **not** a stored rollup (ADR-020 ponytail). The window is selectable (e.g. 24h / 7d / 30d) and re-queries the same seam.

**AC3 — estimated cost via the configurable price table, degrades to tokens-only.**
Given a **configured price table** (§16.5), When the widget renders, Then it shows an **estimated cost** computed over the same token series. And where **no price table is configured**, the widget **degrades to tokens-only** (no fabricated cost) — matching the 8.8a per-tile degradation rule. Cost is an **estimate**, explicitly not billing (OQ14), and never read from a provider billing API.

**AC4 — sandbox resource usage for in-flight/recent Runs (FR-I2).**
Given in-flight/recent Runs, When the widget renders, Then it surfaces **sandbox resource usage** for those Runs (from the metering spine / Run lifecycle, §17.2) alongside token consumption — legibility of runtime resource use, degrading gracefully where the metrics backend does not report it.

**AC5 — per-user/agent/Run drill-down is the exemplar join, NOT a label (NFR-OBS3 crux).**
Given the drill-down along per-user / per-agent / per-Run, When it renders, Then it is served by the **§15/§16.5 backend rollup over exemplars/traces** on `work_item.id` / `user.id` / `run.id` — those identifiers stay **exemplars, never metric labels** (obs §1.2/§5.6). The KPI total + trend are **label-speed** (bounded `project`/`role`); the drill-down is the **exemplar join**. This story must **not** add `user.id`/`agent`/`run.id`/`work_item.id` as a metric label to satisfy the drill-down.

**AC6 — degrades gracefully with no metrics backend (the availability crux).**
Given **no metrics backend wired** (or Epic 13.4 not yet landed), When the operator opens the dashboard, Then the widget **degrades gracefully** — it shows **throughput without cost** (or an explicit "token metering not configured" state), **never a hard failure** and **never a fabricated number** (8.8a `{available:false}` for `tokenConsumption` → explicit degraded state). And a degraded token widget does not take down the rest of the dashboard.

**AC7 — no new metric, no billing store (ADR-020).**
Given the implementation, When it queries token/cost, Then it introduces **no new metric instrument** (it queries the existing `ksquad.agent.tokens`) and **no billing/usage datastore** (the trend is a query over the metering spine, not a stored rollup). And the estimated cost is a **price-table computation over the series** (§16.5), not a persisted cost record. Verify: no new counter/gauge named `ksquad.*token*`/`ksquad.*cost*` is registered by this story; no new table for usage/billing.

**AC8 — NFR-OBS3 standing law (cardinality firewall).**
Given any telemetry touched, When produced, Then: (a) `user.id`/`agent`/`run.id`/`work_item.id` are **never** a metric label (exemplar-only, AC5); (b) scope labels stay **bounded** (`project`, `role`); (c) **no `model` label** on any token instrument (obs §5.6/§17.1); (d) token/cost is **metering legibility** — the per-principal authoritative attribution is §11, the figures are best-effort/runtime-reported (OQ14). Verified by the Epic 14 cardinality CI gate.

## Tasks / Subtasks

- [ ] **Task 1 — Current total + per-scope breakdown (AC1).**
  - [ ] Render the `tokenConsumption` current total from 8.8a; extend with the per-scope breakdown querying `ksquad.agent.tokens` federated by **bounded** `project`/`role` labels via the metrics query seam (§17.2).
- [ ] **Task 2 — Trend over a selectable window (AC2).**
  - [ ] Add a **window selector** (e.g. 24h/7d/30d); compute the trend as `rate()`/`increase()` over the **same** `agent.tokens` series — a **query shape**, no new instrument, no stored rollup.
  - [ ] Re-query the seam on window change; render the tokens/day series.
- [ ] **Task 3 — Estimated cost + sandbox usage (AC3, AC4).**
  - [ ] Compute estimated cost via the §16.5 price table over the token series where configured; **degrade to tokens-only** when no price table — never fabricate cost.
  - [ ] Surface sandbox resource usage for in-flight/recent Runs from the metering spine (§17.2); degrade gracefully where unreported.
- [ ] **Task 4 — Per-user/agent/Run drill-down as the exemplar join (AC5, AC8).**
  - [ ] Serve the finer drill-down from the §15/§16.5 backend rollup over exemplars/traces (`work_item.id`/`user.id`/`run.id` exemplar-only). **Do not** add any of these as a metric label.
- [ ] **Task 5 — Graceful degradation (AC6, AC7).**
  - [ ] When 8.8a marks `tokenConsumption` `{available:false}` (no metrics backend / Epic 13.4 absent), render the explicit degraded state (throughput-without-cost / "not configured") — never a hard failure or fake number.
  - [ ] Assert **no new metric** and **no billing store** is introduced (AC7): no new `ksquad.*token*`/`*cost*` instrument registered here, no usage/billing table.
- [ ] **Task 6 — Standing-law self-check (AC8).**
  - [ ] Confirm no per-item ids as metric labels, bounded scope labels only, **no `model` label**; the Epic 14 cardinality gate stays green.

## Dev Notes

- **The trend is not a new thing to build — it's how you read the thing that exists.** `ksquad.agent.tokens` (§5.5) already carries the data. The "with trend" requirement is satisfied by reading that series as a time range (`rate()`/`increase()`), not by emitting a new counter or persisting a rollup. This is the single most-repeated point in obs §17.1 and ADR-020 (ponytail): **query shape, not new instrument, not billing store.** If you're registering a metric or creating a usage table in this story, you've taken the wrong path.
- **Labels are bounded; drill-down is exemplars.** The at-a-glance total + trend federate on **bounded** `project`/`role` labels (§16.2). The per-user/per-agent/per-Run breakdown FR-I2 asks for is the **exemplar/trace rollup** (§15/§16.5) — `user.id`/`run.id`/`work_item.id` are **exemplars, never labels** (NFR-OBS3). The temptation to "just add a `user` label so the breakdown is easy" is exactly the cardinality violation the Epic 14 gate fails. KPI = label-speed; drill-down = exemplar join.
- **Cost is an estimate, not billing (OQ14).** Estimated cost is a price-table computation (§16.5) over best-effort/runtime-reported tokens; it degrades to tokens-only with no price table. It is never read from a provider billing API (BYO creds, §11 — no shared billing visibility) and never persisted as a billing record. Attribution is per-principal by construction (BYO), so no shared-credential disambiguation is needed.
- **Progressive dep, graceful degrade.** Epic 13.4 emits the token metric; a metrics backend must be wired to query it; a price table must be configured for cost. Each is independent (8.8a per-tile rule): no backend → throughput-only; backend but no price table → tokens-only. None of these is a failure — they are honest degraded states.

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield — only `pkg/auth/*_test.go` + `console/e2e/auth/`. The metrics query seam (§17.2) + `ksquad.agent.tokens` (§5.5, Epic 13) are not yet in this checkout. This story's UI lands under `console/` in the dashboard surface; the **query seam** is server-side (apiserver/BFF reads the metrics backend). This story adds the trend query shape + rendering — **no new metric instrument, no new store**.
- **Match conventions:** reuse the metrics query seam 8.8a uses for the snapshot; extend it with the time-range query — do not add a second metrics client.

### References

- [Source: docs/bmad/02-prd.md#9.9 FR-I2] — token/cost per user/agent/Run/Project; current total + trend over a selectable window (tokens/day); sandbox resource usage; cost precision bounded by runtime (OQ14).
- [Source: docs/bmad/03-architecture.md#13 (r24) + ADR-020] — token/cost rides the OTel metrics pipeline (§17.2) via a pluggable query seam that degrades gracefully; per-principal by construction (BYO §11); trend = time-series query over the same seam, not a new store; estimate via configurable price table; no aggregation service, no rollup/billing DB.
- [Source: docs/bmad/04-observability-plan.md#17.1 — Token consumption + trend] — `ksquad.agent.tokens` (§5.5); current total federated by bounded `project`/`role`; trend = same series as a time range (`rate()`/`increase()`), a query shape not a new instrument; per-user/agent/Run drill-down = exemplar/trace rollup (§15/§16.5), ids exemplar-only; estimated cost = §16.5 price table, degrades to tokens-only; no new metric, no billing store.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.8 row 8.8e] — epic-level AC; **deps 8.8a + Epic 13.4**; trend = time-series over `ksquad.agent.tokens` (obs §5.5/§16.5).
- [Source: docs/bmad/stories/8-8a-dashboard-data-aggregation-read-model.md] — the `tokenConsumption` snapshot sub-payload + per-tile degradation this story extends.

### Open questions (route via ISI-2325; do not block the query shape)

1. **Window options (PM / Designer).** Confirm the selectable trend windows (24h / 7d / 30d?) the CEO-validated mock pins — the query shape is window-agnostic, but the UI selector set should match the mock.
2. **Sandbox-usage source granularity (Architect / Epic 13 owner).** Confirm which sandbox resource signals (CPU/mem/wall) are available from the metering spine for the in-flight/recent-Run view (FR-I2), and their degrade behavior when a runtime does not report them (OQ14). *Does not block the token widget.*

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, agent 2230b001) — construction-time contract via runnable falsification check (`token-consumption-widget-check.py`, Epic-8 model-check pattern).

### Debug Log References

- `python3 token-consumption-widget-check.py` → exit 0 (billing-dashboard anti-pattern trips all 7; §8.8e conformant token widget holds C1-C7).
- `--mutate={DIRECT_RAW_QUERY,NEW_COUNTER,FAKE_COST,LABEL_USER_ID,FAKE_ON_DEGRADE,ROLLUP_TABLE,MODEL_LABEL}` → each exit 1 with the mapped invariant RED; no vacuous survivors.

### Completion Notes List

- Implemented C1-C7 falsification check with teeth via a "billing dashboard" anti-pattern (raw store query, new metric instrument, fabricated cost, user.id as metric label, fake zero on degrade, rollup table, model label).
- **Load-bearing cruxes proven mechanically:** (C2) the ADR-020 ponytail crux — trend = rate()/increase() over the EXISTING `ksquad.agent.tokens` counter (a query SHAPE, not a new instrument, not a stored rollup); (C4) NFR-OBS3 crux — per-user/agent/Run drill-down is the §15/§16.5 EXEMPLAR JOIN, never a metric label; (C5) no metrics backend → explicit "not configured" state, never a fabricated token count; (C6) no new metric instrument, no billing/rollup datastore.
- Runtime proof (real metrics-seam query, trend window selector, exemplar drill-down, price-table cost) owned by console E2E + apiserver dashboard-package tests.

### File List

- `docs/bmad/spikes/bench/token-consumption-widget-check.py` (new) — C1-C7 runnable falsification check.
- `docs/bmad/stories/8-8e-token-consumption-widget-trend.md` (this file) — status→done + Dev Agent Record.
