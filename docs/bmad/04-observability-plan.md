---
stepsCompleted: [context, taxonomy, tracing, metrics, logging, semconv, collector, alerting, handoff, complete]
inputDocuments:
  - docs/bmad/02-prd.md              # NFR-OBS1/2, S9, NFR-PERF1, NFR-SEC1..6, NFR-REL1..3
  - docs/bmad/03-architecture.md     # component map, Run reconcile (§5), coordination spine (§6), shim/A2A (§7), memory (§8), tenancy/egress (§9), credentials (§10)
  - ISI-1406                          # Sympozium observable-llm — 7-signal taxonomy (reason-labeled runs, handoff latency, memory r/w, access decisions, traceparent chain)
  - Sympozium PR #11 / PR #18         # OTel instrumentation (traces+metrics+logs; traceparent on AgentRun CR; noop-on-unset; slog+otelslog; HTTP-transport auto-trace)
  - ISI-1918                          # MemOS memory-semconv v0.1.0 (memory.tier/operation/cube.id; memory_operations_total, memory_operation_duration_ms, memory_result_count)
  - ISI-2303                          # RBAC arch (identity provider, RBAC middleware, Users/ProjectMemberships/Roles data model, Runs carry initiatedByUserId, CRD createdBy/ownedBy) — the identity model this revision instruments
  - ISI-2302                          # RBAC PRD FR-AUTH1..5 (login, admin user CRUD, project-scoped visibility, caller-identity propagation, adaptive UI)
  - ISI-2304                          # RBAC epics — Epic 13 "user-scoped telemetry dimensions" is the story this plan specs
  - ISI-2327                          # Responsive console — arch §13.1 + ADR-038 (CSS-first single SSR tree; canonical breakpoints; commit b2c01e4, branch arch/isi-2327-responsive-console). This revision instruments the breakpoint usage the decision makes observable
  - ISI-2333                          # This revision: viewport/device-class dimension on console RUM (the observability deliverable of ISI-2327)
workflowType: 'observability-plan'
authoringMode: 'O11y-engineer-led synthesis over the CEO-approved PRD + Architect Gate-2 architecture; reuses org OTel prior art'
project_name: 'KSquad'
author: 'O11y Engineer (Observability Agent)'
date: '2026-08-10'
phase: 'BMAD cross-cutting — spans Phase 3 (Solutioning) → Phase 4 (Implementation)'
source_ticket: 'ISI-2133'
parent: 'ISI-2116'
program: 'ISI-2115'
depends_on_architecture: 'ISI-2119 (docs/bmad/03-architecture.md, commit 7b91079)'
honors: [operator-safety-over-expressiveness, two-records-principle, secrets-never-leave-the-seam, vendor-neutral-otel, cardinality-discipline]
revisions:
  - r1 (2026-08-12, ISI-2306 / KSquad RBAC series): added user-scoped telemetry & audit. Threads the human-user identity dimension (`ksquad.user.id` = Run `initiatedByUserId`, from ISI-2303) through every span/log/exemplar (§3), forbids it as a raw metric label (§1.2/§5.6 — it is unbounded per-actor, rolled up in the backend like §15's per-ticket cost), adds the security audit log class (§6) + auth/authz/admin metrics + RBAC security signals (new §16), alerts (§9), semconv attrs (§7), and the user-activity / per-project dashboard. Depends on ISI-2303 landing the identity model to be truthful (flagged §16.7). No cardinality-law exception introduced; no new architectural decision — instruments the RBAC decisions made in ISI-2303.
  - r2 (2026-08-12, ISI-2325 / CEO-validated Project Dashboard): added the **Project Dashboard signal feed** (new §17 + Appendix A row). The dashboard reads mostly from the coordination record / `scm` mirror (read models, no metric); this plan feeds the **one** metrics panel — **token consumption + trend** (§17.1: the existing `ksquad.agent.tokens` §5.5 read *as a time range*, `rate()`/`increase()` — a query shape, **not** a new instrument; per-user/agent/Run stay exemplar rollups §16.5; estimated cost = §16.5 price table, degrades to tokens-only) — plus two cheap bounded **approval-queue** signals (§17.2: `ksquad.approval.pending` gauge + `ksquad.approval.decisions.total{project,outcome}` for the KPI count / stale-approval alert / trend; authoritative who-approved-what stays coord + §16.4 audit log; `user.id`/`work_item.id`/`run.id` exemplar-only). No cardinality-law exception; no new architectural decision — legibility over signals the metering spine + coordination record already carry.
  - r3 (2026-08-12, ISI-2333 / ISI-2327 responsive console — arch §13.1 + ADR-038): added the **console RUM viewport / device-class dimension** (new **§18** + Appendix A row + §5.6/§7/§11 threading). Tags console page-view / interaction / web-vital signals with the active **breakpoint bucket** (`mobile`\|`tablet`\|`desktop`), a **bucketed** viewport-width band, and **orientation** so real breakpoint usage is observable and responsive regressions (layout shift / errors concentrated at one width) surface. **Cardinality-safe:** breakpoint/orientation/width-bucket/route-class are bounded enums → allowed labels (§5.6); **raw pixel width, UA strings, device model are never emitted** (privacy-light — bucketed, not fingerprinting; aligns ADR-038's *never user-agent sniffing*). **Opt-in-consistent:** rides the existing OTelConfig export path (ADR-029, D8 default = no exporter) via a same-origin BFF ingest → collector, no new browser→vendor egress. No cardinality-law exception; no new architectural decision — instruments the CSS-first responsive tree ADR-038 already locked.
depends_on_rbac_architecture: 'ISI-2303 (Users/ProjectMemberships/Roles + auth service + initiatedByUserId + createdBy/ownedBy) — user-scoped telemetry is truthful only once this lands; see §16.7'
---

# Observability Plan — KSquad

**Author:** O11y Engineer (Observability Agent)
**Date:** 2026-08-10
**Phase:** BMAD cross-cutting (Phase 3 → Phase 4)
**Source ticket:** ISI-2133 · **Parent:** ISI-2116 · **Program:** ISI-2115
**Architecture input:** `docs/bmad/03-architecture.md` (ISI-2119, commit 7b91079)

> **Scope discipline.** This plan designs the metrics / logging / tracing / alerting strategy for the
> Gate-2 architecture. It is **vendor-neutral OpenTelemetry at the instrumentation layer** (instrument
> once, export anywhere — Prometheus, Dynatrace, or any OTLP backend) and it **reuses the org's
> Sympozium OTel taxonomy** (ISI-1406, PR #11/#18) where the concepts map. It honors the architecture's
> stated **phasing**: §4.6/§13.5 make Prometheus metrics + structured logs + the `run_events` audit
> stream the **MVP (P0)**, and full cross-service distributed tracing a **defined fast-follow (P1)** —
> this document specs P1 now so it is not a surprise, but does not move it into the MVP critical path.
> It adds **zero** new architectural decisions; it instruments the ones already made.

---

## 1. Design principles (the standing law for every signal)

1. **Three pillars correlate or they are noise.** Every metric data point carries an exemplar to a
   trace; every log line carries `trace_id`/`span_id`; every span carries the same `ksquad.run.id`.
   The join key across all three pillars is the **Run**.
2. **Cardinality is the enemy — the Run is a trace/log dimension, never a metric label.**
   `run.id`, `work_item.id`, `principal.id`, **`user.id` (= `initiatedByUserId`, §16)**, `sandbox.pod`,
   `trace_id` are **unbounded** → they live on spans, logs, and metric **exemplars**, *never* as
   Prometheus label values. Metric labels are drawn only from the **bounded** enum sets in §5.6. This is
   the single rule most likely to be violated; it is a first-class review gate (§12). *Corollary for the
   RBAC revision:* "every metric carries user identity" (ISI-2306) is satisfied by the **exemplar** — the
   §1.1 correlation link, not a label — so per-user drill-down is a trace/audit join, never a per-series
   explosion (§16.2). Bounded scope dimensions (`project`, `role`) stay as labels/resource attrs for the
   cheap aggregations.
3. **Vendor-neutral at the seam.** Instrumentation is OTel SDK + semantic conventions only. Backend
   choice (Prometheus scrape, Dynatrace OTLP, LGTM) is a **collector exporter** decision, swappable
   without touching a line of service code. Mirrors the architecture's own seam discipline (§7.4).
4. **Secrets and untrusted content never enter telemetry.** NFR-SEC3 (§12 of arch): credentials are
   never logged/echoed/artifacted — and by extension never span-attributed. Agent-authored strings
   (memory content, work-item bodies, model output) are **untrusted input** (§8.4 arch, R9): they are
   PII-scanned and are never emitted verbatim as span/log attributes — only hashes, lengths, kinds,
   and provenance IDs. **User PII is the same class (RBAC revision):** the only user identifier that ever
   enters telemetry is the **opaque `ksquad.user.id` (UUID)**; usernames, emails, passwords, and session
   tokens are **never** emitted as attributes, log bodies, or audit fields — the redaction processor (§6)
   backstops it and the security audit log stores actor identity as the opaque id only (§16.4).
5. **Instrument once, phase the export.** SDK is wired into every service from day one with a
   **noop-on-unset** fallback (Sympozium pattern: providers are noop when `OTEL_EXPORTER_OTLP_ENDPOINT`
   is empty — zero overhead, zero risk). Turning observability on is an operator config, not a redeploy.
6. **Observability as code, validated before deploy.** Semconv registry (Weaver), collector config,
   dashboards, and alert rules are version-controlled in-repo and validated in CI (§11) — the same
   discipline the architecture applies to protocol versions and migrations.

---

## 2. Reuse map — Sympozium taxonomy → KSquad (ISI-1406, PR #11/#18)

The org has a battle-tested agent-observability taxonomy from Sympozium (`observable-llm`) and the
MemOS memory-semconv work. We **reuse the concept and the label shape** and re-root the namespace under
`ksquad.*`. This is deliberate: it keeps operators fluent across both products and lets us inherit
proven cardinality choices.

| Sympozium signal (prior art) | KSquad equivalent | Maps to arch section |
|------------------------------|-------------------|----------------------|
| `agent.runs{reason}` (reason-labeled runs) | `ksquad.run.completed{outcome, terminal_reason, runtime}` | Run reconcile §5.2/§5.3 |
| `handoff.latency_ms` | `ksquad.run.dispatch.duration` (control-plane → shim A2A handoff) + `ksquad.sandbox.claim.duration` | §5.2, §5.4 |
| `memory.read` / `memory.write` | `ksquad.memory.operations{operation, kind, result}` + `ksquad.memory.operation.duration` | Memory §8 |
| `access.decisions{decision=allowed}` | `ksquad.authz.decisions{surface, decision}` (memory write authz, claim authz, egress) | §8.4, §6.2, §9.2 |
| `agent.context.input_tokens` | `ksquad.agent.tokens{direction, runtime}` (shim-surfaced, best-effort) | Shim §7 |
| `traceparent.chain` (traceparent annotation on `AgentRun` CR + NATS header prop) | **`ksquad.run.id` + W3C `traceparent`** propagated via `Run` CR status annotation → A2A task metadata → MCP call metadata | §5.2, §7, §8 |
| noop-on-unset providers; `slog`+`otelslog`; HTTP-transport auto-instrumentation | **kept verbatim** as implementation patterns | §12 arch patterns |
| MemOS memory-semconv v0.1.0 (`memory.operation`, `memory.tier`, `item.count`, `latency.ms`) | folded into the `ksquad.memory.*` semconv (§7 here) | §8.3 memory MCP surface |

**What does *not* carry over:** Sympozium propagates context over **NATS headers**; KSquad has no NATS
— the southbound bus is **A2A**, so `traceparent` rides **A2A task metadata** and the **`Run` CR status
annotation** (the CRD analogue of Sympozium's `AgentRun` annotation). Memory context rides **MCP request
metadata**. There is structurally no lateral P2P channel to instrument (§3 arch), which is a feature: the
trace graph is a tree rooted at the Run, never a mesh.

---

## 3. The unit of correlation: the Run trace

Everything hangs off one identifier. A **Run** (§5 arch) is the root span and the correlation key for
all three pillars.

```
TRACE ROOT: Run <ksquad.run.id>                                     (operator, Run controller)
├─ span: reconcile.Pending→ClaimingSandbox                          (operator)
│   └─ span: sandbox.claim            [ksquad.sandbox.claim.duration, exemplar]   (warm-pool ctrl §5.4)
├─ span: reconcile.Dispatching
│   └─ span: a2a.task.submit          [ksquad.run.dispatch.duration]              (a2a client §7)
│       └─ span: shim.task.execute    ─ traceparent crosses the sandbox boundary ─ (shim, in-sandbox)
│           ├─ span: agent.turn.*     [ksquad.agent.tokens, best-effort]          (agent runtime)
│           ├─ span: mcp.memory.search / memory.write                             (agent → ksquad-memory)
│           │   └─ span: memory.op    [ksquad.memory.operation.duration]          (ksquad-memory §8)
│           └─ span: a2a.sse.progress (streamed events → apiserver SSE hub)       (shim → apiserver §7)
├─ span: reconcile.Collecting         (artifacts → object store, indexed)         (operator §5.2)
└─ Run terminal: Succeeded|Failed|Canceled|Paused  → run_events + ksquad.run.completed
```

**Propagation contract (the seam crossings that must carry `traceparent`):**

| Boundary | Carrier | Owner |
|----------|---------|-------|
| console/CLI → apiserver (request) | **authenticated session → `ksquad.user.id`** (= `initiatedByUserId`) on the request context; RBAC middleware (ISI-2303) resolves it before any span opens | auth/BFF middleware (ISI-2303) |
| apiserver → `Run` CR (create) | **`Run.spec.initiatedByUserId`** — durable identity of the human who triggered the Run; the operator stamps `ksquad.user.id` on the Run root span/logs from it | apiserver + Run controller (§5.2) |
| operator → apiserver (coordination writes) | gRPC/HTTP OTel propagator (auto) | control plane |
| operator/apiserver → shim | **A2A task metadata** `traceparent` field | `internal/a2a` (§7) |
| controller ↔ `Run` CR (async, cross-restart) | **`Run.status` annotation** `ksquad.io/traceparent` | Run controller (§5.2) |
| shim → agent runtime | env `TRACEPARENT` (Sympozium Job-level pattern) + in-proc | shim |
| agent → ksquad-memory | **MCP request metadata** `traceparent` | `internal/memory` MCP server (§8) |
| shim → apiserver SSE hub | SSE event carries `run.id` + `span_id` for stitching | `internal/sse` (§7) |

The CR-annotation hop is what makes the trace **survive a controller restart** — the reconcile loop is
idempotent and level-triggered (§12 arch), so the trace context must be **durable state**, not in-memory
continuity. This is the KSquad translation of Sympozium's "traceparent annotation on the AgentRun CR."

**Per-ticket activity view (Paperclip-style).** A work item (ticket) can span multiple Runs — retries,
crash-reclaims, resume-after-pause — so the per-ticket perspective is a **query pattern**, not a new
signal: every span, log line, and metric exemplar emitted by a Run carries `ksquad.work_item.id`
alongside `ksquad.run.id`, and the `run_events` audit rows are work-item-scoped. The console/backend
renders a **Paperclip-style per-ticket activity timeline** by joining traces + correlated logs +
`run_events` on `work_item.id`: claims, Runs, phase transitions, SSE progress, artifact appends,
terminal reasons, in causal order. This costs nothing at the metrics layer — `work_item.id` stays
forbidden as a metric label (§1.2/§5.6) and lives exactly where unbounded IDs belong.

**Per-user activity view (RBAC revision, ISI-2306).** Every span, log line, and metric exemplar a Run
emits also carries **`ksquad.user.id`** (the `initiatedByUserId` the Run was created with, §5.2), so the
same join mechanism yields a **per-user activity timeline** ("who triggered which Runs, on which
projects") and, scoped by the bounded `project` dimension, the **per-project usage breakdown** the
dashboard needs (§16.6). Identity is *durable state on the `Run` CR*, not request-time context — so the
attribution survives a controller restart exactly as the `traceparent` annotation does. `user.id` obeys
the cardinality law identically to `work_item.id`: exemplar/trace/log only, never a metric label (§16.2).

---

## 4. Tracing strategy

### 4.1 Phasing (honors arch §4.6 / §13.5)

- **P0 (MVP):** in-service spans within each control-plane service (operator, apiserver, memory), plus
  the `run_events` stream as the operator-facing causal record. `run.id` stamped on every log/metric
  exemplar. **No cross-sandbox trace stitching required to ship.**
- **P1 (fast-follow, specced here):** full `traceparent` propagation across the operator → shim → agent
  → memory boundary per §3, so a single Run is one connected trace end-to-end. This is the arch's named
  fast-follow; the propagation contract (§3) is defined now so the shim (§7 arch) and the MCP server
  (§8 arch) reserve the metadata fields from day one — retrofitting propagation later is the expensive
  path we avoid.

### 4.2 Sampling

- **Control-plane spans:** **tail-based sampling** in the collector — keep 100% of Runs that end
  `Failed`/`Canceled`/`Paused` or breach the claim-latency SLO (§9); head-sample the rest at a tunable
  rate (default 100% at MVP volume, dial down as squads scale). Rationale: Run volume is operator-scale
  (tens–hundreds concurrent per §5.4), not web-scale — errors are rare and precious, so we bias
  retention toward the pathological Run. *Sampling is a strategy, not a failure — but at this volume the
  right strategy is "keep the interesting ones, always."*
- **Agent-internal spans** (turn/token detail from the shim): head-sampled independently and can be
  dropped without losing the Run-level trace — the shim marks them a distinct scope so tail-sampling
  policy treats them separately.

### 4.3 Span attributes (bounded, PII-safe)

Standard on every span: `ksquad.run.id`, **`ksquad.user.id`** (the initiating human, §16), `ksquad.team`
(squad namespace), `ksquad.project`, `ksquad.runtime`, `service.name`, plus OTel resource
(`k8s.namespace.name`, `k8s.pod.name`,
`k8s.node.name` — injected by the collector's `k8sattributes` processor, **not** hand-set). Content
attributes are **hash/length/kind only**, never raw text (§1.4).

---

## 5. Metrics strategy

All metrics are OTel instruments exported via the collector to Prometheus (scrape) and/or OTLP
(Dynatrace). Names below are the **semconv** names (§7); Prometheus renders them with unit suffixes.

### 5.1 Coordination record — the audit spine (arch §6)

The coordination record **is** the audit trail (§6.1); these metrics are the quantitative projection of
it. Every event here is *also* a durable `audit_log`/`run_events` row — metrics are for rate/latency/SLO,
rows are for forensic query. Do not duplicate the audit *content* into metric labels.

| Instrument | Type | Labels (bounded) | Why |
|------------|------|------------------|-----|
| `ksquad.coord.claim.total` | counter | `result` (acquired\|contended\|empty) | claim throughput & contention on SKIP LOCKED (§6.2) |
| `ksquad.coord.claim.duration` | histogram | `result` | claim path latency; contention pressure signal |
| `ksquad.coord.lease.renew.total` | counter | `result` (ok\|stale_holder) | heartbeat health; `stale_holder` is a fencing signal |
| `ksquad.coord.lease.reclaim.total` | counter | `trigger` (expiry\|sweeper) | **crash-reclaim rate** — the NFR-REL correctness signal (§6.2) |
| `ksquad.coord.fence.epoch.increments` | counter | — | fence-token (`lease_epoch`) increments; a spike = churn/thrash |
| `ksquad.coord.workitem.state` | up/down gauge | `state` (open\|claimed\|done\|failed) | backlog depth by state (bounded enum) |
| `ksquad.coord.workitem.blocked` | up/down gauge | `error_code` (curated enum: `needs_approval`\|`blocked_by_dep`\|`awaiting_credential`\|`awaiting_input`\|`awaiting_review`\|`budget_exhausted`\|`upstream_failed`\|`other`, §5.6/§15) | **tasks currently blocked, labeled by the blocking reason** — up on enter-blocked, down on clear; uncurated reason → `other`. Projection of the coord `blocked_reason` condition (arch r24/r25); the Paperclip "blocked-by" analogue (§15). **Story 13.3 / ISI-2235.** |
| `ksquad.coord.append.total` | counter | `kind` (comment\|artifact) | audit append rate |
| `ksquad.coord.claim.contention.depth` | gauge | — | concurrent claimers losing the SKIP-LOCKED race |

**Fencing observability is a correctness gate, not a nicety.** `stale_holder` renewals and `reclaim`
counts are exactly the signals that prove the §6.2 consistency model holds in production; they feed the
concurrency alert (§9) and are asserted by the Testing Architect's concurrency harness (§10).

### 5.2 Run state machine (arch §5.2/§5.3)

| Instrument | Type | Labels (bounded) | Why |
|------------|------|------------------|-----|
| `ksquad.run.phase.transitions` | counter | `from`, `to` (phase enum §5.2) | state-machine flow; stuck-phase detection |
| `ksquad.run.phase.duration` | histogram | `phase` | per-phase latency (ClaimingSandbox, Dispatching, Running, Collecting) |
| `ksquad.run.completed` | counter | `outcome` (succeeded\|failed\|canceled), `terminal_reason`, `runtime` | **the reason-labeled run counter** (Sympozium `agent.runs{reason}`) |
| `ksquad.run.active` | up/down gauge | `phase` | concurrent Runs by phase (feeds pool sizing §5.4) |
| `ksquad.run.retry.total` | counter | `reason` (sandbox_death\|lease_lost\|controller_failover) | retry/backoff visibility (§5.3) |
| `ksquad.run.paused.total` | counter | `cause` (cred_expiry\|cred_rotation) | **pause-on-auth** signal (§10, FR-G3) |
| `ksquad.run.paused.active` | gauge | `cause` | Runs currently Paused awaiting credential refresh |
| `ksquad.reconcile.duration` | histogram | `controller`, `result` | controller-runtime reconcile latency (NFR-OBS) |
| `ksquad.reconcile.errors` | counter | `controller`, `error_type` | typed reconcile errors → backoff |

`terminal_reason` is a **curated bounded enum** (e.g. `ok`, `agent_error`, `sandbox_lost`,
`timeout`, `killed`, `cred_unrefreshable`) — *not* a free-text passthrough of agent output. Enforcing
that enum is the cardinality gate for this counter.

### 5.3 Sandbox / warm pool (arch §5.4 — S9 / NFR-PERF1)

The **claim-latency SLI is the headline performance number** the architecture gates AD-3 on (§14
threshold: warm-claim p50 ≤ 2s / p95 ≤ 5s). Instrument it precisely.

| Instrument | Type | Labels (bounded) | Why |
|------------|------|------------------|-----|
| `ksquad.sandbox.claim.duration` | histogram | `runtime_class` (kata\|gvisor), `pool_hit` (warm\|cold) | **the S9/NFR-PERF1 SLI**; `pool_hit=cold` = pool exhaustion |
| `ksquad.warmpool.ready` | gauge | `runtime_class` | pool ready-count (target-buffer health §5.4) |
| `ksquad.warmpool.replenish.duration` | histogram | `runtime_class` | teardown→ready cost; the cost the sizing policy trades against |
| `ksquad.warmpool.teardown.total` | counter | `reason` (post_run\|residue_fail\|scale_down) | teardown-and-replace hygiene (AD-3/D7) |
| `ksquad.warmpool.claim.pressure` | gauge | `runtime_class` | claims-waiting vs ready; autoscale trigger (§5.4) |
| `ksquad.warmpool.scale.events` | counter | `direction` (up\|down) | autoscale activity vs idle-cost budget (R2) |

`pool_hit=cold` on `claim.duration` is the single most operationally important label: it separates
"pool sized right, latency is runtime overhead" from "pool starved, latency is cold-boot" — the two have
opposite remediations and both feed the ISI-2113 evidence gate (§14 arch).

### 5.4 Memory service (arch §8) — reuse MemOS semconv (ISI-1918)

Directly inherits the memory-semconv v0.1.0 shape validated in ISI-1918.

| Instrument | Type | Labels (bounded) | Why |
|------------|------|------------------|-----|
| `ksquad.memory.operations` | counter | `operation` (write\|search\|diary_append\|diary_read), `result` (ok\|denied\|empty) | memory r/w counters (Sympozium `memory.read/write`) |
| `ksquad.memory.operation.duration` | histogram | `operation` | latency incl. pgvector search |
| `ksquad.memory.search.result_count` | histogram | — | recall breadth (MemOS `memory_result_count`) |
| `ksquad.memory.write.denied` | counter | `reason` (unauthorized\|unattributed\|cross_tenant) | **provenance/authz enforcement** (FR-E6, §8.4) |
| `ksquad.memory.read.provenance_surfaced` | counter | `provenance_class` (same_principal\|other_principal\|system) | untrusted-read accounting (FR-E7) |
| `ksquad.memory.poisoning.candidates` | counter | `signal` (see §8) | **poisoning-signal candidates** (R9, §8.4) |

Scope labels (`squad`, `project`) ride as **resource attributes**, not per-series labels where they'd
multiply cardinality; `principal_id` is an **exemplar/log** dimension only (§1.2). Provenance and scope
are *enforced in the service* (§8.4 arch) — these metrics **observe** the enforcement, they do not
implement it.

### 5.5 Shim / A2A (arch §7)

| Instrument | Type | Labels (bounded) | Why |
|------------|------|------------------|-----|
| `ksquad.a2a.task.total` | counter | `runtime`, `final_state` (completed\|failed\|canceled\|input_required) | A2A task lifecycle (§7.1) |
| `ksquad.a2a.dispatch.duration` | histogram | `runtime` | **handoff latency** (Sympozium `handoff.latency_ms`) |
| `ksquad.a2a.sse.events` | counter | `runtime`, `type` (progress\|artifact\|status) | SSE progress throughput → console (FR-F2) |
| `ksquad.a2a.sse.stream.active` | gauge | — | live SSE streams (drives the console "live" pulse) |
| `ksquad.shim.capability.negotiated` | counter | `runtime`, `capability` (streaming\|tool_calls\|interactive), `supported` (bool) | **capability negotiation** honesty (FR-D4, §7.2) |
| `ksquad.shim.conformance.result` | gauge | `runtime`, `check` | **conformance-suite** pass/fail per check (§7.5) — CI-emitted |
| `ksquad.agent.tokens` | counter | `runtime`, `direction` (input\|output) | token accounting (Sympozium `agent.context.input_tokens`), best-effort per shim; **per-ticket** rollups aggregate on `work_item.id` and **per-user cost** rollups aggregate on `user.id` — both via exemplars/traces (§15/§16.5), never as a label |

`capability` and `check` are bounded by the conformance suite's fixed check list (§7.5 arch) — a vendor
adding a runtime cannot inflate cardinality because the check set is fixed by the suite, not the runtime.

### 5.6 Cardinality budget (the enforced label allowlist)

**Bounded label domains (allowed as metric labels):** `outcome`, `terminal_reason` (curated enum),
`phase`, `from`/`to` (phase enum), `runtime` (openclaw\|hermes\|…, finite), `runtime_class`
(kata\|gvisor), `operation`, `result`, `state`, `kind`, `trigger`, `reason` (curated enums),
`decision`, `surface`, `capability`, `check`, `direction`, `pool_hit`, `cause`, `error_code`,
`provenance_class`, `signal`, `endpoint`, `source`, `cache_hit`, `live` (build browser, ISI-2165),
**`role`** (curated RBAC enum — `admin`\|`project_user`\|…, §16.2), **`auth_result`**
(success\|failure\|locked), **`target_kind`** (user\|role\|membership\|team\|agent\|skill\|project\|config),
**`action`** (create\|update\|delete\|grant\|revoke\|login\|logout\|refresh) — the RBAC additions (§16),
**`breakpoint`** (mobile\|tablet\|desktop), **`viewport_bucket`** (curated width band, 5 values),
**`orientation`** (portrait\|landscape), **`route_class`** (curated screen enum), **`interaction_kind`**
(curated touch/pointer enum), **`web_vital`** (LCP\|INP\|CLS) — the console-RUM additions (§18).
Total series per instrument stays in the low hundreds.

**Forbidden as metric labels (trace/log/exemplar only):** `run.id`, `work_item.id`, `principal.id`,
**`user.id` (= `initiatedByUserId`)**, `sandbox.pod`, `trace_id`, `team`/`project` names, **usernames /
emails / session tokens (never emitted at all — PII/secret, §1.4)**, **raw viewport pixel width, User-Agent
strings, and any device-model/fingerprint (never emitted at all — privacy, §18: bucketed not fingerprinted)**.
Scope names (`team`, `project`) ride
as **resource attributes** (Prometheus federates them without per-series explosion) or as exemplars;
`user.id` rides as an exemplar/span/log dimension and is rolled up per-user in the backend (§16.2/§16.5).
A CI check (§11) greps the instrumentation for label keys outside the allowlist and fails the build —
`user.id` (and any username/email key) as a label is an explicit build failure. Cardinality discipline is
tested, not hoped for.

---

## 6. Logging strategy

- **Structured, correlated:** Go services use `slog` + `otelslog` bridge (Sympozium pattern) so every
  line auto-carries `trace_id`, `span_id`, `ksquad.run.id`, `service.name`. Console (Node) uses `pino`
  with the same fields injected server-side in the BFF. JSON out; the collector adds k8s resource attrs.
- **Three log classes, kept distinct:**
  1. **Run/coordination audit = the `run_events`/`audit_log` rows in Postgres** (§6.1 arch) — the durable,
     queryable operator-facing record (D4, NFR-OBS1). This is *authoritative* and is **not** replaced by
     stdout logs. Observability *exports a projection* of it (metrics §5.1, and optionally a log-pipeline
     mirror for the vendor backend) but never treats stdout as the audit source of truth.
  2. **Security audit log (RBAC revision, ISI-2306)** — a durable, queryable Postgres audit stream for
     **identity and administrative events**: authentication (login success/failure/lockout, logout, token
     refresh), authorization denials, and **admin/config mutations** (user CRUD, role assignment, project
     membership grant/revoke, and every config change — Team/Agent/Role/Skill/Project/OTelConfig CRD edits
     and Settings changes). Every row carries **actor `user.id`**, `action`, `target_kind` + opaque
     target id, timestamp, source (IP/session), and a **before/after summary or hash** (never raw secret
     values). This is the "**who triggered what Run, who changed what config**" record the ticket asks for;
     it is *authoritative and append-only*, distinct from `run_events` (which is Run-scoped) and from
     stdout. Retention/immutability follows the same policy as `audit_log`. Full spec: §16.4.
  3. **Application/diagnostic logs** — stdout JSON, sampled/leveled, for debugging. Ephemeral by
     comparison.
- **PII & secret redaction (mandatory, NFR-SEC3 + R9):** a collector `transform`/`redaction` processor
  runs a PII+secret scan on all log bodies and attributes before export: credential patterns
  (`CLAUDE_CODE_OAUTH_TOKEN`, bearer/API-key shapes), **passwords and session/auth tokens (RBAC),
  usernames and emails (RBAC PII, §1.4)**, and known secret-ref keys are dropped/hashed — only the opaque
  `user.id` survives. Agent-authored content (memory bodies, work-item text, model output) is treated as
  **untrusted** and is never logged verbatim — only IDs, kinds, lengths, hashes. This scan is
  double-guarded: services must not log secrets in the first place (arch §12), and the collector is the
  backstop. **The security audit log itself is written already-clean** (opaque ids only) — the redaction
  processor is defense-in-depth, not the primary control, on that path.
- **Log levels as policy:** `INFO` for state transitions and audit-relevant events, `WARN` for
  retryable/backoff, `ERROR` for terminal-failure conditions. Reconcile loops log at `DEBUG` per
  iteration (level-triggered loops are chatty) — sampled at the collector.

---

## 7. Semantic conventions (`ksquad.*` registry — Weaver-managed)

Semantic conventions are contracts (persona principle). KSquad ships a **Weaver semconv registry** in
`docs/observability/semconv/` (schema-versioned), so instrumentation code is generated type-safe from
the schema and telemetry is validated against it in CI.

**Attribute registry (core):**

| Attribute | Type | Domain / example | Notes |
|-----------|------|------------------|-------|
| `ksquad.run.id` | string | UUID | root correlation key; span/log/exemplar only |
| `ksquad.work_item.id` | string | UUID | per-ticket correlation (Paperclip-style activity view, §3); span/log/exemplar only — never a metric label |
| `ksquad.team` | string | squad namespace | resource attr (scope), not metric label |
| `ksquad.project` | string | project name | resource attr |
| `ksquad.runtime` | string | `openclaw`\|`hermes` | finite enum → allowed metric label |
| `ksquad.run.phase` | string | phase enum (§5.2) | |
| `ksquad.run.terminal_reason` | string | curated enum (§5.2) | **enum-enforced** |
| `ksquad.runtime_class` | string | `kata`\|`gvisor` | |
| `ksquad.memory.operation` | string | `write`\|`search`\|`diary_append`\|`diary_read` | reuses MemOS v0.1.0 |
| `ksquad.memory.kind` | string | fact\|decision\|… | from `memory_records.kind` |
| `ksquad.memory.provenance_class` | string | same_principal\|other_principal\|system | untrusted-read weighting (FR-E7) |
| `ksquad.authz.decision` | string | `allowed`\|`denied` | Sympozium `access.decisions` shape |
| `ksquad.authz.surface` | string | memory\|claim\|egress\|**project_membership**\|**admin**\|**api** | RBAC surfaces added (§16) |
| `ksquad.user.id` | string | UUID (= Run `initiatedByUserId`, ISI-2303) | **initiating human**; span/log/exemplar only — never a metric label (§16.2). Usernames/emails are **not** registered (PII, never emitted) |
| `ksquad.user.role` | string | curated enum `admin`\|`project_user`\|… | bounded → allowed metric label (§5.6); the caller's effective role |
| `ksquad.auth.event` | string | login\|logout\|token_refresh\|password_change\|lockout | authentication event kind (§16.4) |
| `ksquad.auth.result` | string | success\|failure\|locked | bounded label for `ksquad.auth.login.total` (§16.3) |
| `ksquad.admin.target_kind` | string | user\|role\|membership\|team\|agent\|skill\|project\|config | what an admin mutation touched (§16.4) |
| `ksquad.admin.action` | string | create\|update\|delete\|grant\|revoke | admin mutation verb (§16.4) |
| `ksquad.fence.epoch` | int | monotonic | lease-epoch/fence token (§6.2) |
| `ksquad.console.breakpoint` | string | `mobile`\|`tablet`\|`desktop` | active responsive breakpoint bucket (arch §13.1/ADR-038 canonical tokens: `<768`\|`768–1024`\|`>1024`); bounded (3) → allowed metric label (§18) |
| `ksquad.console.viewport_bucket` | string | `w360`\|`w768`\|`w1024`\|`w1440`\|`w1440p` | **bucketed** viewport-width band (matches the §05 test matrix 360/768/1024/1440), finer than breakpoint but still bounded → allowed label. **Raw pixel width is never emitted** (privacy/cardinality, §18) |
| `ksquad.console.orientation` | string | `portrait`\|`landscape` | viewport orientation where the browser exposes it; bounded (2) → allowed label |
| `ksquad.console.route_class` | string | curated screen enum (`dashboard`\|`list`\|`detail`\|`settings`\|`search`\|`build_browser`\|`discussion`\|`agents`) | the **screen class**, never the raw URL/path (which is unbounded + can carry ids) — bounded → allowed label (§18) |
| `ksquad.console.interaction_kind` | string | `tap`\|`click`\|`nav`\|`pull_refresh`\|`pinch_zoom`\|`drawer_toggle`\|`row_expand` | touch/pointer interaction class — observes the §13.1 touch-parity bar; bounded → allowed label (§18) |

**Reuse & alignment:** OTel resource semconv for `k8s.*`, `service.*`; OTel `gen_ai.*` where the shim can
surface model/token data (aligns `ksquad.agent.tokens` to `gen_ai.usage.*`); MemOS memory-semconv v0.1.0
for the `ksquad.memory.*` block. **Deviations are documented in the registry**, not silently invented —
`validate-telemetry-data` runs actual emitted telemetry against the schema before any vendor sign-off.

---

## 8. Security & poisoning signals (R9, NFR-SEC6, §8.4 arch)

Memory reads are untrusted; a hostile write by agent A must never reach agent B as trusted context. We
**observe** the defense (the enforcement lives in the memory service per §8.4). Candidate poisoning
signals (`ksquad.memory.poisoning.candidates{signal}`), bounded enum:

- `cross_principal_high_recall` — a record authored by principal X surfaces in Y's top-k unusually often.
- `injection_pattern_match` — stored content matches prompt-injection heuristics (imperative
  "ignore previous", tool-invocation strings, role-escape markers) at write or read time.
- `provenance_mismatch` — claimed author ≠ authenticated writer (should be rejected upstream; a count
  here is a defense-in-depth tripwire).
- `write_rate_anomaly` — a principal's write rate spikes beyond baseline (flooding the knowledge record).

These feed a **security alert** (§9) and are asserted by the **memory-poisoning isolation test** the
architecture already mandates (§4.3 arch) — observability makes that test's outcome a continuous
production signal, not just a CI gate. **Never** emit the offending content itself; the signal carries
the record ID + hash + provenance only.

Parallel `ksquad.authz.decisions{surface, decision}` covers the authz surfaces (memory write, work-item
claim, egress, **and the RBAC surfaces `project_membership` / `admin` / `api`** added in the RBAC
revision) — a rising `denied` rate is either an attack or a misconfiguration, both of which the operator
must see.

**RBAC / authentication security signals (ISI-2306).** The RBAC layer (ISI-2303) is a new attack surface;
it gets its own bounded security signals (full metric list §16.3):

- **`ksquad.auth.login.total{auth_result}`** — a sustained spike in `failure` per user/IP (the identity
  rides the **exemplar**, not a label) is **brute-force / credential-stuffing**; `locked` counts account
  for lockout policy firing. Alerts §9.
- **Privilege-escalation tripwire** — an `admin` change that grants the `admin` role or adds membership to
  a sensitive project (`ksquad.admin.change.total{target_kind=role|membership, action=grant|update}`) is a
  high-value audit event; anomalous timing/actor feeds a **security ticket** (§9). The authoritative
  record is the security audit log (§16.4) — the metric is the rate/alert projection.
- **`ksquad.authz.decisions{surface=project_membership, decision=denied}`** rising — a user probing
  projects they are not a member of (FR-AUTH3). Never emit the target project *name*; the record id +
  actor `user.id` ride the exemplar.

As with poisoning signals, **never emit credentials or the offending payload** — auth signals carry the
opaque `user.id`, the `auth_result`/`action`/`target_kind` enums, and a source hash only.

---

## 9. Alerting & SLOs

SLOs derive directly from the PRD NFRs and the architecture's evidence-gate thresholds (§14 arch). Each
SLI is one of the metrics above; each alert is actionable and maps to an operator runbook.

| SLO / SLI | Target (source) | Alert condition | Severity |
|-----------|-----------------|-----------------|----------|
| **Warm-claim latency** `sandbox.claim.duration{pool_hit=warm}` | p50 ≤ 2s, p95 ≤ 5s (NFR-PERF1 / §14 AD-3) | p95 > 5s for 10m **or** `pool_hit=cold` rate > 5% | **page** |
| **Pool readiness** `warmpool.ready` | ≥ target buffer (§5.4 policy) | ready = 0 with active claim pressure | **page** |
| **Crash-reclaim health** `coord.lease.reclaim.total` | reclaim = correct recovery, but bounded | reclaim rate 3× baseline (thrash) **or** `stale_holder` renewals > 0 sustained | **page** (correctness) |
| **Run failure rate** `run.completed{outcome=failed}` | < baseline (NFR-REL) | failure ratio > 20% over 15m, excluding `killed` | **ticket** |
| **Runs stuck** `run.phase.duration{phase}` | phase-appropriate | any Run in a non-terminal phase > SLO (e.g. Dispatching > 60s) | **ticket** |
| **Paused-on-auth backlog** `run.paused.active` | transient | Runs Paused > 30m (refresh not happening — §10 watch item) | **ticket** |
| **Memory authz denials** `memory.write.denied` | ≈ 0 legitimate | denial rate spike | **ticket** (security) |
| **Poisoning candidates** `memory.poisoning.candidates` | 0 | any sustained non-zero | **page** (security) |
| **Reconcile health** `reconcile.errors` | low | error rate spike per controller | **ticket** |
| **Shim conformance** `shim.conformance.result` | all pass | any check regresses to fail (CI + runtime) | **block release** |
| **Brute-force login** `auth.login.total{auth_result=failure}` (RBAC) | ≈ baseline | failure spike concentrated on a user/IP (via exemplar) **or** lockout rate > 0 sustained | **ticket** (security) |
| **Privilege escalation** `admin.change.total{target_kind=role\|membership, action=grant}` (RBAC) | rare, expected | any `admin`-role grant, or membership change outside a change window / by an unexpected actor | **ticket** (security) |
| **RBAC access probing** `authz.decisions{surface=project_membership, decision=denied}` (RBAC) | ≈ 0 legitimate | denial-rate spike (FR-AUTH3) | **ticket** (security) |

**SLO philosophy:** the two **page**-grade correctness SLOs (claim latency, crash-reclaim health) are
the ones the architecture stakes its differentiators on (§1: operator-safety, the coordination spine).
Everything else is ticket-grade. Alert fatigue is a cardinality problem in disguise — we keep the page
set small and correctness-focused.

---

## 10. Collector pipeline design

KSquad is Kubernetes-native and ships a Helm chart (§4.6 arch). Observability adds an **OpenTelemetry
Collector** to the chart as a values-toggled component (on-by-default, `endpoint`-gated per §1.5).
Topology: a **Deployment collector** (gateway) in the system namespace + an optional **DaemonSet**
(node-level, for host/k8s log tailing). Squad-namespace shim/agent telemetry is OTLP-pushed to the
gateway service.

**Gateway pipeline (order is a hard rule of this plan):**

```
receivers:  [otlp (grpc/http), prometheus (scrape control-plane /metrics)]
processors: [memory_limiter,            # MUST be first — backpressure before OOM
             k8sattributes,             # K8s-only (KSquad is k8s-native) — enrich k8s.* resource attrs
             resource,                  # set service.namespace, deployment env
             transform/redaction,       # PII + secret scan (§6) — drop/hash before export
             tail_sampling,             # keep failed/paused/SLO-breach Runs 100% (§4.2)
             batch]                     # MUST be last — batch after all mutation
exporters:  [prometheus (or prometheusremotewrite), otlp/dynatrace, debug (dev only)]
```

**Non-negotiables (persona critical rules, applied):**
- `memory_limiter` **first**, `batch` **last** — always.
- `k8sattributes` is used **because KSquad is Kubernetes** (never `resourcedetection`, which is for
  VM/bare-metal — not applicable here).
- The **redaction/transform** processor sits **before any exporter** so no secret/PII ever leaves the
  cluster boundary — the collector is the backstop to service-side discipline (§6).
- `tail_sampling` sits **after** enrichment/redaction (needs the attributes to make keep/drop decisions)
  and **before** `batch`.

**Egress interaction (critical, ties to arch §9.2):** the per-squad **default-deny egress
NetworkPolicy** must **allowlist the in-cluster collector gateway** so shim/agent OTLP can reach it;
sandboxes do **not** get direct egress to the vendor backend — only the gateway does. This keeps the
telemetry path inside the tenancy model: the sandbox talks to the collector, the collector (system
namespace, governed egress) talks to Dynatrace/Prometheus. Observability must not punch a hole in the
isolation model — it routes *through* it. This is an explicit input to the `internal/tenancy`
NetworkPolicy templates (§11.1 arch).

**Custom collector (OCB) — deferred, flagged:** the default build uses the OTel Contrib distro. If the
Dynatrace exporter or a specific processor isn't in Contrib, an **OCB custom build** (persona OCB
capability) is the path — noted as a fast-follow, not an MVP need.

---

## 11. Instrumentation scope & CI validation (Phase-4 build guidance)

| Component | SDK / approach | Priority |
|-----------|----------------|----------|
| `ksquad-operator` (controllers) | OTel Go SDK; controller-runtime metrics already Prometheus-native → bridge; reconcile spans | P0 |
| `ksquad-apiserver` (coordination) | OTel Go SDK; HTTP-transport auto-instrumentation (Sympozium pattern); explicit spans on claim/lease/reclaim | P0 |
| `ksquad-memory` | OTel Go SDK; MCP-server span per tool call; MemOS semconv | P0 |
| `shims/openclaw`, `shims/hermes` | OTel Go SDK in-sandbox; A2A `traceparent` propagation; token surfacing | P0 metrics / **P1 cross-boundary trace** |
| `console` (Node BFF) | `@opentelemetry/sdk-node` + `pino`; propagate `run.id` into SSE proxy | P1 |
| `console` (browser RUM) | `@opentelemetry/sdk-web` + `web-vitals`; page-view / interaction / web-vital events tagged with the §18 breakpoint/viewport/orientation dimension; posts OTLP/HTTP to a **same-origin BFF ingest** (`/v1/rum`) → collector — **no direct browser→vendor egress**, export gated by OTelConfig (ADR-029, default none) | P1 (§18) |
| Collector + semconv registry + dashboards + alerts | in-repo config, Weaver registry | P0 |

**CI gates (observability-as-code):**
1. **Cardinality lint** — grep instrumentation for metric label keys outside the §5.6 allowlist → fail.
   Explicitly fails on `user.id`/`initiatedByUserId`/username/email as a metric label (RBAC, §16.2 — OBS-9),
   and on **raw viewport width / User-Agent / device-fingerprint** as a console-RUM label or attribute
   (§18 — OBS-11): only the bucketed `breakpoint`/`viewport_bucket`/`orientation` may be emitted.
2. **Semconv validation** — Weaver validates the registry; `validate-telemetry-data` runs emitted
   telemetry from an envtest/e2e Run against the schema.
3. **Secret-leak scan** — the isolation suite (§4.3 arch) asserts no credential appears in any span/log
   in a real Run; the collector redaction processor is unit-tested against known secret shapes.
4. **Conformance metric** — `shim.conformance.result` is emitted by the conformance suite (§7.5 arch);
   a regression blocks release.

---

## 12. Handoffs

### → Developer (Amelia) — implementation stories (Phase 4 epics)
1. **OBS-1 (P0):** Wire OTel Go SDK + `slog`/`otelslog` + noop-on-unset into all three Go services and
   both shims; stamp `ksquad.run.id` on every log/span/exemplar. *(pairs with the coordination-spine and
   reconcile epics — instrument as those are built, not after.)*
2. **OBS-2 (P0):** Implement the §5.1 coordination metrics (claim/lease/renew/reclaim/fence) — **couple
   to the §6.2 spine epic**; these are the correctness SLIs.
3. **OBS-3 (P0):** Implement §5.2/§5.3/§5.4 Run + warm-pool metrics; the `sandbox.claim.duration` SLI is
   the ISI-2113 evidence-gate instrument — must exist before that spike can produce numbers.
4. **OBS-4 (P0):** Implement §5.4 memory metrics + poisoning-candidate signals (couple to §8 memory epic).
5. **OBS-5 (P0):** Ship the collector Helm sub-chart (§10) with the fixed processor order + redaction +
   the egress-allowlist entry into `internal/tenancy` NetworkPolicy templates.
6. **OBS-6 (P1):** Cross-boundary `traceparent` propagation (§3 contract) through A2A metadata, `Run` CR
   status annotation, and MCP metadata — reserve the metadata fields **now** even though stitching is P1.
7. **OBS-7 (P0):** Weaver semconv registry + the four CI gates (§11).

### → Testing Architect — validation KPIs
- The **crash-reclaim / stale-holder** metrics (§5.1) are the observable assertions for the concurrency
  harness (parallel claimers, crash-mid-claim, stale-holder completion) already required by §6.2 arch.
- The **secret-leak scan** and **memory-poisoning candidate** metrics (§8) are the continuous-production
  form of the isolation/residue/poisoning suites (§4.3 arch) — the tests assert them in CI; the alerts
  watch them in prod.
- **Claim-latency SLI** (§5.3) is the KPI the ISI-2113 spike measures against the §14 threshold — the
  test harness consumes `sandbox.claim.duration` histograms directly.

### → Architect (Winston) / Alfred (CTO)
- No architectural change requested. One **input** for the tenancy epic: the egress NetworkPolicy
  templates (§9.2 arch) must allowlist the collector gateway (§10 here). One **confirmation** for Gate 2
  posture: this plan keeps distributed tracing as the arch's stated P1 fast-follow — flagging it so the
  phasing is explicit at the gate, not assumed.

---

## 13. Alignment with evidence gates (arch §14)

| Arch gate | Observability dependency |
|-----------|--------------------------|
| **AD-3 runtime class / claim latency** (ISI-2113) | `ksquad.sandbox.claim.duration{runtime_class, pool_hit}` (§5.3) is the exact instrument the p50≤2s/p95≤5s threshold is measured on. Build it first. |
| **Warm-pool sizing** (ISI-2113) | `warmpool.ready` / `claim.pressure` / `replenish.duration` (§5.3) are the idle-cost-vs-latency tradeoff signals the policy curve is tuned against. |
| **AD-9 OAuth refresh UX** (ISI-2112) | `run.paused.total{cause}` / `run.paused.active` (§5.2) make the pause/resume behavior observable — directly informs the §10 watch item (is subscription-token lifecycle workable headless?). |
| **AD-4 shim conformance** (ISI-2114) | `shim.conformance.result` + `shim.capability.negotiated` (§5.5) are emitted by the conformance suite; observability turns the suite into a continuous signal. |

Observability **produces the evidence** these gates need — so the P0 instrumentation should land in
parallel with (not after) the foundational epic, exactly as §14 arch schedules the spikes.

---

## 14. Traceability (PRD/Arch → this plan)

| PRD / Arch item | This plan |
|-----------------|-----------|
| NFR-OBS1/2 (structured logs, metrics, audit stream) | §5, §6 (audit = `run_events`, projected not replaced) |
| S9 / NFR-PERF1 (claim-time start) | §5.3 claim-latency SLI + §9 page SLO |
| NFR-REL1..3 (durable, resumable, crash-safe) | §5.1 reclaim/fence metrics + §9 crash-reclaim SLO |
| NFR-SEC3 (secrets never logged) | §1.4, §6 redaction, §11 secret-leak CI gate |
| NFR-SEC6 / R9 (memory poisoning) | §8 poisoning signals + §9 security alert |
| Arch §6 coordination spine | §5.1 (the audit spine's quantitative projection) |
| Arch §5 Run reconcile | §3 trace root + §5.2 state-machine metrics |
| Arch §5.4 warm pool | §5.3 |
| Arch §7 shim/A2A | §5.5 + §3 propagation contract |
| Arch §8 memory | §5.4 + §7 semconv (MemOS reuse) + §8 poisoning |
| Arch §9.2 egress | §10 collector egress-allowlist (tenancy input) |
| Arch §4.6/§13.5 (OTel tracing = fast-follow) | §4.1 P0/P1 phasing (honored, not overridden) |
| Sympozium ISI-1406 / PR #11/#18; MemOS ISI-1918 | §2 reuse map + §7 semconv |
| **FR-AUTH1** (login) / **FR-AUTH4** (Runs carry caller identity) — ISI-2302 | §16.1 `ksquad.user.id`=`initiatedByUserId` on every span/log/exemplar; §16.3 `auth.login.total`; §16.4 auth audit |
| **FR-AUTH2** (admin user/membership CRUD) — ISI-2302 | §16.3 `admin.change.total`; §16.4 admin/config-change audit; §16.6 admin dashboards |
| **FR-AUTH3** (project-scoped visibility) — ISI-2302 | §16.6 user-scoped dashboards (BFF-enforced); §8/§16.3 `authz.decisions{surface=project_membership}` probing signal |
| **FR-AUTH5** (adaptive UI) — ISI-2302 | §16.6 dashboards gated admin vs project-user |
| ISI-2306 ticket: user cost / security events / dashboard | §16.5 per-user cost; §16.4 security audit log; §16.6 dashboards |

---

## 15. Review addendum — CEO requirements (2026-08-11)

During review, two observability requirements were added on the ticket by the CEO. Verification of this
plan against them:

| CEO requirement | Verdict | Where / action taken |
|-----------------|---------|----------------------|
| **Token consumption** | ✅ already covered | `ksquad.agent.tokens{runtime, direction}` (§5.5), aligned to OTel `gen_ai.usage.*` (§7). Clarified: **per-ticket token rollups** are derived in the backend by aggregating on `work_item.id` via exemplars/traces — deliberately *not* a metric label (cardinality law §1.2). A cost/pricing rollup would be a backend computation over this signal; flag if a cost model is wanted. |
| **Tasks blocked by (error code)** | ✅ **taxonomy landed (Story 13.3 / ISI-2235)** | `ksquad.coord.workitem.blocked{error_code}` **up/down gauge** (§5.1); `error_code` is a bounded curated enum on the §5.6 allowlist. **Gate closed:** the blocked *condition* now exists in the architecture (arch **r25** refined `blocked` from a lifecycle state to an orthogonal *condition* carrying a `blocked_reason`; **r24** landed the first reason `needs_approval`), and **Story 13.3 lands the curated `error_code` taxonomy** — `needs_approval` \| `blocked_by_dep` \| `awaiting_credential` \| `awaiting_input` \| `awaiting_review` \| `budget_exhausted` \| `upstream_failed` \| `other`. Any uncurated `blocked_reason` **collapses to `other`** (never leaks a free-form string as a label — the cardinality safety valve). The instrumentation is now truthful; the gauge is a pure observe-only projection of the coord condition (blocked/claimable identical with the gauge on/off). |
| **Per-ticket activity on the trace perspective (Paperclip-style)** | ✅ spec added | §3 per-ticket activity view: `ksquad.work_item.id` (now registered in §7) on every span/log/exemplar + work-item-scoped `run_events` → the console joins traces + logs + audit rows on `work_item.id` for a Paperclip-style ticket timeline. P0 supports it via `run.id`/`work_item.id` log+audit correlation; P1 stitching (§4.1) upgrades it to one connected cross-boundary trace. |

One architectural decision now landed (Story 13.3 / ISI-2235): the curated `error_code` (blocked-reason)
taxonomy above. It rides the existing coord `blocked_reason` condition (arch r24/r25) — no new work-item
state, no new subsystem; the gauge observes the condition, it does not create it.

---

## 16. User-scoped telemetry & audit (RBAC series — ISI-2306)

The KSquad RBAC series (ISI-2302 PRD FR-AUTH1..5 · ISI-2303 architecture · ISI-2304 epics) adds a
**human-user identity layer**: an auth service + user store, RBAC middleware on the apiserver BFF, a
`Users`/`ProjectMemberships`/`Roles` data model, and — the load-bearing hook for observability — **every
`Run` carries `initiatedByUserId`** and CRDs carry `createdBy`/`ownedBy`. This section specs the telemetry
and audit that makes that layer *observable*. It instruments the RBAC decisions made in ISI-2303; it adds
**no new architectural decision** and — critically — **no exception to the cardinality law (§1.2)**.

> **This is the observability half of Epic 13 ("user-scoped telemetry dimensions", ISI-2304).** The
> enforcement (who *may* do what) lives in the RBAC middleware and auth service (ISI-2303); this plan
> **observes** that enforcement, exactly as §8 observes the memory-poisoning defense it does not implement.

### 16.1 The dimension: `ksquad.user.id`

One new correlation dimension, `ksquad.user.id`, an **opaque UUID equal to the Run's `initiatedByUserId`**
(ISI-2303 data model). It is stamped on **every span, log line, and metric exemplar** a Run emits
(propagated per §3: authenticated session → `Run.spec.initiatedByUserId` → root span/logs → children).
For **non-Run** work it is the acting user directly (an admin editing config, a user logging in). It joins
against the `Users` table for display; **only the opaque id ever enters telemetry** — usernames and emails
are PII and are never emitted (§1.4, §6 redaction backstop).

### 16.2 The cardinality decision (the one call that matters)

The ticket says *"every trace/span/metric carries user identity."* `user.id` is **unbounded per-actor**
(grows with adoption), so making it a raw Prometheus label would violate the plan's #1 law and reintroduce
exactly the series-explosion §1.2 exists to prevent. The resolution — consistent with the §15 per-ticket
cost precedent, **no new latitude invented**:

| Where user identity lives | Mechanism | Satisfies |
|---------------------------|-----------|-----------|
| **Traces / spans** | `ksquad.user.id` span attribute (§4.3) | "every trace carries user identity" — literally |
| **Logs / audit** | `ksquad.user.id` field on every line + the security audit log (§16.4) | "every log carries user identity" — literally |
| **Metrics** | `ksquad.user.id` on the **exemplar** (the §1.1 metric→trace link), **never a label** | "every metric carries user identity" — via the exemplar, the plan's own correlation model |
| **Per-user aggregation** (cost, activity) | **backend rollup** over exemplars/traces/audit rows on `user.id` | dashboard drill-down without per-series explosion (§16.5/§16.6) |
| **Cheap bounded breakdowns** | `role` (curated enum label) and `project` (resource attr) *are* metric labels | per-project / per-role dashboards at label speed |

So "every metric carries user identity" is **true via the exemplar**, and per-user numbers are a
trace/audit join — the same mechanism KSquad already uses for per-ticket token cost. **A CI gate (§11)
fails the build if `user.id` (or any username/email key) appears as a metric label.** This is the honest
trade-off: label-speed aggregation is available for the *bounded* dimensions the product actually slices
on at scale (project, role); *identity-precise* drill-down is a join, which at KSquad's operator scale
(tens–hundreds of users, human-slow query volume) is the correct cost to pay, not a compromise.

### 16.3 Metrics — authentication, authorization & admin (bounded labels only)

New instruments, all labels drawn from the §5.6 allowlist; `user.id` rides exemplars only.

| Instrument | Type | Labels (bounded) | Why |
|------------|------|------------------|-----|
| `ksquad.auth.login.total` | counter | `auth_result` (success\|failure\|locked) | login throughput; `failure`/`locked` spikes = brute-force (§8, §9) |
| `ksquad.auth.session.active` | up/down gauge | — | concurrent authenticated sessions |
| `ksquad.auth.token.refresh.total` | counter | `result` (ok\|expired\|revoked) | session-token lifecycle health (session strategy, ISI-2303 ADR) |
| `ksquad.authz.decisions` | counter | `surface` (…\|project_membership\|admin\|api), `decision` (allowed\|denied) | **the RBAC enforcement projection** — reuses the §8 instrument, `surface` enum extended |
| `ksquad.admin.change.total` | counter | `target_kind` (user\|role\|membership\|team\|agent\|skill\|project\|config), `action` (create\|update\|delete\|grant\|revoke) | **"who changed what config"** — rate/alert projection of the §16.4 audit rows |
| `ksquad.run.by_role.total` | counter | `role` (curated), `runtime` | per-role Run volume (bounded — feeds the dashboard without user-cardinality) |

`role` and the `*_kind`/`action`/`auth_result` enums are the only new labels; all are curated finite sets
(a user cannot inflate cardinality — the role set is admin-provisioned, ISI-2303). This mirrors the arch
§17.2 rate-limit metrics that already dimension per **project/agent/role**.

### 16.4 The security audit log — the authoritative "who did what"

Log class #2 from §6. A durable, append-only Postgres stream (extends `audit_log`) that is the
**authoritative record** the ticket's *audit-trail* and *security-event-logging* bullets ask for. It is
distinct from `run_events` (Run-scoped) and is never sourced from stdout.

**Event families & row shape** (every row: `ts`, actor `user.id`, `source` (IP/session hash), `action`,
`target_kind`, opaque `target_id`, `result`, `detail` = before/after **summary or hash**, never raw
secret/PII):

- **Authentication** (`auth.event` ∈ login\|logout\|token_refresh\|password_change\|lockout) — login
  attempts (success **and** failure), logout, refresh, lockout. *Failed* logins are recorded with the
  attempted-username **hash** and source, never the password.
- **Authorization denials** — every RBAC-middleware `denied` (surface + target id), so probing is
  forensically reconstructable, not just a counter.
- **Admin / config mutations** — user CRUD, **role change**, **project-membership grant/revoke**, and
  **every config change**: Team/Agent/Role/Skill/Project **and** OTelConfig CRD edits (via `createdBy`/
  `ownedBy` + the change) and console Settings changes. This is the *"who changed what config"* record.
- **Run attribution** — the *"who triggered what Run"* fact is already durable as `Run.initiatedByUserId`
  + the `run_events` rows (§5.1) carrying `user.id`; the security audit log **cross-links** it, it does not
  duplicate the Run lifecycle.

**Guarantees:** append-only, same retention/immutability policy as `audit_log`; written already-clean
(opaque ids only); queryable by actor, target, time (powers the §16.6 dashboard and any compliance export).

### 16.5 Per-user cost attribution (extends existing cost metering)

The existing cost signal is `ksquad.agent.tokens{runtime, direction}` (§5.5), and §15 already established
that per-X cost rollups are a **backend computation over exemplars/traces**, not a metric label. Per-user
cost is the identical mechanism with **zero new metric**: `user.id` is already on every `agent.tokens`
exemplar (§16.1), so the backend rolls tokens up by `user.id` (and by `user.id × project` using the bounded
`project` scope) and applies the pricing model to produce **per-user / per-project cost**. If a first-class
cost *unit* is later wanted (currency, not tokens), that is the same backend rollup with a price table — a
computation over this signal, not a new label. Flagged for the FinOps/console owner as the natural home.

### 16.6 Dashboard — user activity & per-project usage

The ticket's dashboard is two panels, each built on a mechanism already specced — no new signal required:

1. **User activity** — a per-user timeline (logins, Runs triggered, admin changes, cost) built by the
   backend joining the **security audit log** (§16.4) + **traces/logs** on `user.id` (§16.1). This is the
   §3 per-ticket-activity join, re-keyed on the user. Admin-only surface (FR-AUTH2/5).
2. **Per-project usage breakdown** — Runs, tokens/cost, active users, failure rate **by `project`**, which
   is a **bounded scope dimension** (resource attr / label), so this panel is label-speed metrics
   (`ksquad.run.completed`, `ksquad.run.by_role.total`, `agent.tokens` federated by `project`) — no
   per-user cardinality needed for the aggregate view; drill-down to a specific user is the §16.5 join.

Both are **observability-as-code** (§1.6): the dashboards ship version-controlled in-repo like the rest.
The console renders them via the BFF, **user-scoped** — a project user sees only their authorized projects
(FR-AUTH3); the cross-user/all-project view is admin-gated (FR-AUTH2/5) and enforced in the BFF, not the
dashboard.

### 16.7 Dependency & disposition — truthful only once ISI-2303 lands

**Honest gate (same posture as §15's work-item `blocked` deferral):** this instrumentation is *truthful*
only once **ISI-2303** lands the identity model it reads —
`Users`/`ProjectMemberships`/`Roles`, the auth service, RBAC middleware, `Run.initiatedByUserId`, and
CRD `createdBy`/`ownedBy`. Until those exist there is no `user.id` to stamp. This plan **reserves the
semconv and the audit schema now** (so the emitting services are built identity-aware from day one, not
retrofitted — the expensive path §4.1 warns against), and depends on ISI-2303 for the model to be real.

**Handoffs:**
- **→ Architect (ISI-2303):** confirm the field name (`initiatedByUserId`), the `Role` enum surface
  (`admin`\|`project_user`\|…), and that the **security audit log** is a first-class table in the RBAC data
  model (the auth service must *write* it — observability projects/alerts on it, but the auth service owns
  the source of truth). If ISI-2303 names the actor field differently, this plan follows it.
- **→ Developer (Amelia), Epic 13 (ISI-2304):** **OBS-8 (P0)** — propagate `ksquad.user.id` from the RBAC
  middleware onto every span/log/exemplar (§16.1) and emit the §16.3 auth/admin metrics + write the §16.4
  security audit log; **OBS-9 (P0)** — extend the §11 cardinality CI gate to fail on `user.id`/username/
  email as a metric label; **OBS-10 (P1)** — the §16.6 user-activity + per-project dashboards.
- **→ Testing Architect (ISI-2305):** the security audit log completeness (every login/role-change/
  membership-change produces exactly one authoritative row) and the **`user.id`-never-a-label** CI gate are
  assertable KPIs — they belong in the auth/RBAC test suite alongside FR-AUTH enforcement tests.

**Disposition:** revision **r1 (ISI-2306)** complete. Adds the user identity dimension, security audit log,
auth/admin metrics + signals + alerts, per-user cost rollup, and the user-activity/per-project dashboards —
all honoring the cardinality law with **no exception** and **no new architectural decision**. Blocked on
nothing to *author*; **flagged** as truthful-once-ISI-2303-lands.

---

## 17. Project Dashboard signal feed (ISI-2325 — CEO-validated dashboard)

The CEO-validated Project Dashboard (arch §13 r24, PRD Theme I FR-I1…I8, epics 8.8a–f) reads **mostly
from the coordination record** (tickets-by-status, Recent Tickets, Pending Approvals, live Runs) and the
**`scm` mirror** (PR mini-board) — those are **read models, not metrics**, so they need **no new signal**
here. The **one** panel this plan feeds is **token consumption with a trend**, plus two cheap, bounded
approval-queue signals for alerting. **No cardinality-law exception; no new architectural decision.**

### 17.1 Token consumption + trend (FR-I2, story 8.8e)

The signal already exists — `ksquad.agent.tokens{runtime, direction}` (§5.5), aligned to `gen_ai.usage.*`
(§7). The dashboard's **"tokens consumed (with trend)"** KPI is served by:
- **Current total + per-scope breakdown** — the metrics query seam (arch §17.2) reads `agent.tokens`
  federated by the **bounded** scope labels (`project`, `role` — §16.2) for the at-a-glance number.
- **Trend** — the **identical series read as a time range** (tokens/day over a selectable window). A trend
  is a **query shape over the existing counter, not a new instrument** (ponytail) — Prometheus/OTLP
  `rate()`/`increase()` over the window, no stored rollup.
- **Per-user / per-agent / per-Run drill-down** — the §15/§16.5 **backend rollup over exemplars/traces**
  on `work_item.id` / `user.id` / `run.id`; those stay **exemplars, never labels** (§1.2/§5.6). The KPI
  and trend are label-speed; the drill-down is the exemplar join.
- **Estimated cost** — the §16.5 price-table computation over the same series; renders where a price table
  is configured, **degrades to tokens-only** otherwise (matches the 8.8a per-tile degradation rule).

**No new metric, no billing store** (ADR-020) — the widget is a query over the metering spine the dashboard
already rides.

### 17.2 Pending-approvals signals (FR-I5, stories 8.8c / 2.12)

The Pending Approvals **queue itself** is a `coord` read model (`blocked_reason=needs_approval`, arch §6) —
rendered from the DB, no metric required. For **alerting and trend** (a growing/stale approval backlog is
an operational signal), two cheap bounded signals — both label-safe (`project` is a bounded scope dim,
`outcome` is a 2-value enum):

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `ksquad.approval.pending` | gauge (up/down) | `project` | work items currently in `blocked(needs_approval)` — feeds the KPI count + a **stale-approval** alert (§9) when it stays > 0 past an SLO age |
| `ksquad.approval.decisions.total` | counter | `project`, `outcome` (approve\|reject) | human approve/reject volume — approval throughput, drives the dashboard trend and an audit cross-check against the §16.4 security audit log |

**Provenance:** the *authoritative* record of who approved/rejected what is the **coordination record +
security audit log** (§16.4, `initiated_by_user_id`) — these metrics are **aggregate legibility**, never
the record of decision. `run.id` / `work_item.id` / `user.id` stay **exemplars** on the counter, not labels
(§1.2). Alert on `ksquad.approval.pending` age, not on per-item labels.

**Handoff → Developer (Epic 13 / with 8.8c + 2.12):** emit `ksquad.approval.pending` from the coordination
reconciler on gate raise/resolve and `ksquad.approval.decisions.total` on each human decision; extend the
§11 cardinality CI gate to keep `work_item.id`/`user.id`/`run.id` **off** these two instruments' labels.

---

## 18. Console RUM — viewport / device-class dimension (ISI-2333 ← ISI-2327, arch §13.1 / ADR-038)

**Decision instrumented, not made.** ADR-038 makes the console **one responsive SSR tree** — layout keys
off **viewport / container width** via Tailwind breakpoints + container queries, **never user-agent
sniffing**, same BFF payloads, same RBAC wall (§12.3), one SSE bus (arch §13.1). That decision is invisible
in production unless we can *see which breakpoints operators actually use* and *catch regressions that
concentrate at one width*. This section adds a **viewport / device-class dimension** to the console RUM so
the responsive tree is observable. It adds **no new architectural decision and no data/authz path** — it is
a presentation-layer signal riding the existing OTel export seam.

### 18.1 The dimension (bounded, privacy-light, aligned to the design tokens)

Every console **page-view**, **interaction**, and **web-vital** sample is tagged with:

| Dimension | Domain | Source | Why bounded / privacy-safe |
|-----------|--------|--------|-----------------------------|
| `ksquad.console.breakpoint` | `mobile`\|`tablet`\|`desktop` | the **same CSS breakpoint token** that drives layout (`<768`\|`768–1024`\|`>1024`, arch §13.1) — read from the active container query, **not** from the UA | 3 values — the canonical shared tokens; a label, not a fingerprint |
| `ksquad.console.viewport_bucket` | `w360`\|`w768`\|`w1024`\|`w1440`\|`w1440p` | `innerWidth` **bucketed** into the §05-testing viewport bands (360/768/1024/1440) at the SDK before emit | 5 fixed bands; **raw pixel width is dropped at source** — bucketing is the privacy control, not the backend |
| `ksquad.console.orientation` | `portrait`\|`landscape` | `matchMedia('(orientation: …)')` where exposed | 2 values |
| `ksquad.console.route_class` | curated screen enum (§7) | the **route template**, resolved client-side to a screen class (never the raw path — paths carry ids/PII) | ~8 screens; matches the per-screen reflow table in arch §13.1 |

**Device-class is derived from viewport width, never sniffed.** We do **not** parse the User-Agent for a
device model, and we do **not** collect screen DPI, GPU, font list, or any high-entropy client signal — that
would be fingerprinting and it would also contradict ADR-038 (layout is width-driven, so width is the only
honest signal). Combined only with the opaque `ksquad.user.id` (exemplar-only, §16.1), the dimension stays
**privacy-light**: bucketed, low-entropy, and non-identifying.

### 18.2 Signals

Three cheap instruments — all labels drawn from the §18.1 bounded domains (`breakpoint × orientation ×
viewport_bucket × route_class × interaction_kind ≈` low hundreds of series, well inside the §5.6 budget):

| Metric | Type | Labels (bounded) | Why |
|--------|------|------------------|-----|
| `ksquad.console.page_view.total` | counter | `breakpoint`, `viewport_bucket`, `orientation`, `route_class` | **which breakpoints operators actually use, per screen** — the primary question ISI-2327 asks; drives a usage heatmap (breakpoint × screen) |
| `ksquad.console.interaction.total` | counter | `breakpoint`, `route_class`, `interaction_kind` | **touch-parity in the wild** — confirms `pull_refresh`/`pinch_zoom`/`drawer_toggle` are actually exercised on `mobile`/`tablet` (the §13.1 v1 touch bar), not just shipped |
| `ksquad.console.web_vital` | histogram | `breakpoint`, `route_class`, `web_vital` (LCP\|INP\|CLS) | **responsive-regression detector** — **CLS bucketed by `breakpoint`** is the exact "layout errors concentrated at one width" signal the ticket names; INP/LCP by breakpoint catch a slow reflow on one device class |

`web_vital` is the standard Core Web Vitals triad via the `web-vitals` lib; **CLS split by breakpoint** is
the load-bearing series — a layout shift that spikes only at `mobile` is a responsive bug the desktop-only
view never shows. `run.id`/`work_item.id`/`user.id` stay **exemplars** on these instruments, never labels
(§1.2/§5.6) — the aggregate is label-speed, the drill-down is the exemplar join.

**No client-error firehose.** Uncaught client errors ride the existing diagnostic log class (§6.3), tagged
with the same `breakpoint`/`route_class` attributes so an error cluster at one width is queryable — we do
**not** add a per-error metric label (unbounded error strings would breach §5.6).

### 18.3 Export posture — opt-in-consistent (D8 / ADR-029)

The browser SDK emits to a **same-origin BFF ingest endpoint** (`/v1/rum`, served by the console Node BFF
that already fronts every read model) which forwards to the collector. This keeps three invariants intact:

1. **No new egress path.** The browser never talks to a vendor directly — RUM routes **through** the same
   collector pipeline (§10) as every other signal, so the redaction/PII processor and the OTelConfig export
   gate apply unchanged. **Default = no exporter (D8): with no `OTelConfig` exporter configured, RUM is
   collected and dropped at the collector, never egressed** — identical to the rest of the plan's posture.
2. **Same RBAC wall.** `/v1/rum` sits behind the §12.3 deny-by-default middleware like every BFF route — an
   unauthenticated browser cannot post RUM; `user.id` is stamped server-side from the session, never sent by
   the client (so the client can't forge identity, and the session token never rides the RUM payload).
3. **No responsive data/authz path.** Consistent with ADR-038 — this is presentation telemetry, not a
   viewport-conditioned API. The server still sends one SSR tree to every device.

### 18.4 Handoffs

**→ Developer (Amelia) — Epic 8 (console), pairs with the responsive-console stories (ISI-2327):**
- **OBS-11 (P1):** Add `@opentelemetry/sdk-web` + `web-vitals` to the console client; a small
  `breakpoint`-resolver reads the **active CSS breakpoint token** (shared with the Tailwind config — single
  source of truth, no duplicated thresholds) and buckets `innerWidth`/orientation **at the SDK before
  emit** (raw width never leaves the browser). Tag `page_view`/`interaction`/`web_vital` per §18.2.
- **OBS-12 (P1):** Add the `/v1/rum` BFF ingest route behind the §12.3 middleware; stamp `user.id`
  server-side; forward OTLP/HTTP to the collector. **Reuse** the existing collector — no new receiver
  topology beyond an OTLP/HTTP path.
- **CI (extends OBS-7):** the §11 cardinality lint gains the **OBS-11 rule** — fail the build if raw
  viewport width, a User-Agent string, or any device-fingerprint key appears as a RUM label **or**
  attribute; only the bucketed `breakpoint`/`viewport_bucket`/`orientation` are permitted.

**→ Testing Architect — validation KPIs (lockstep with the §05 viewport matrix):**
- The **viewport test matrix** (360/768/1024/1440 × iOS Safari / Android Chrome / desktop Chrome+Firefox,
  a v1 gate in 05-testing-strategy) and this RUM dimension **share the same bucket boundaries** — an e2e
  run at each matrix width should emit exactly one `viewport_bucket`/`breakpoint` pair; the test asserts the
  tag, closing the loop between the synthetic matrix and real-user telemetry.
- **`ksquad.console.web_vital{web_vital="CLS"}` by breakpoint** is the responsive-regression KPI: a CI/prod
  guard can flag a CLS regression isolated to one `breakpoint` — the "layout error at one width" case.

**→ Architect (Winston) / Alfred (CTO):** No architectural change requested. Confirmation only that this
honors ADR-038 (width-driven, no UA sniffing) and the D8 no-exporter-by-default posture — the dimension is
bounded, privacy-light, and rides the existing OTelConfig seam.

---

## Appendix A — Signal-to-component matrix (the §17.2 coverage the ticket asked for)

| Architecture component | Metrics | Traces | Logs / Audit | Alert |
|------------------------|---------|--------|--------------|-------|
| Coordination record (§6) — claim/lease/renew/reclaim, fence, appends | §5.1 | claim/lease spans | `audit_log`/`run_events` (authoritative) | crash-reclaim page |
| Run state machine (§5) — transitions, retry/backoff, pause-on-auth | §5.2 | **Run trace root (§3)** | phase-transition INFO logs | stuck-Run, paused-backlog |
| Sandbox / warm pool (§5.4) — claim latency, ready-count, teardown | §5.3 | sandbox.claim span | teardown/replenish logs | claim-latency + readiness page |
| Memory service (§8) — r/w counters w/ provenance+scope, poisoning | §5.4 | memory.op span | denied-write logs (provenanced) | poisoning page, authz ticket |
| Shim / A2A (§7) — SSE progress, capability negotiation, conformance | §5.5 | shim.execute span + traceparent | A2A lifecycle logs | conformance-regression block |
| Build browser (design §9.4/ADR-021, ISI-2165) — reads, snapshot emit, RO-reader cost | `ksquad.buildbrowser.*` (component plan) | `buildbrowser.*` span (child live / **linked** completed) | scope-denial + emit-failure + reader logs | "no build view" coverage, RO-reader cost, scope-denial — **all ticket-grade** | see `design/build-browser-observability-plan.md` |
| **Identity / RBAC (ISI-2303, §16)** — login, authz decisions, admin/config change, user cost | §16.3 `auth.*`/`authz.decisions`/`admin.change.*`/`run.by_role.*` (labels bounded; `user.id` on exemplars) | `ksquad.user.id` on **every** span (§16.1) | **security audit log** (§16.4, authoritative) + `user.id` on all logs | brute-force / privilege-escalation / access-probing — **security-grade** (§9) |
| **Project Dashboard feed (ISI-2325, §17)** — token consumption+trend, pending-approvals queue | §17.1 `agent.tokens` (query as trend); §17.2 `approval.pending` gauge + `approval.decisions.total` (labels `project`/`outcome` bounded; `user.id`/`work_item.id` on exemplars) | token exemplars on the Run trace (§3); approval decision joins `initiated_by_user_id` | approve/reject in **coord + security audit log** (§16.4, authoritative) | stale-approval backlog (`approval.pending` age past SLO) |
| **Console RUM viewport/device-class (ISI-2333 ← ISI-2327, §18, arch §13.1/ADR-038)** — breakpoint usage, touch-parity, responsive regressions | §18.2 `console.page_view.total` + `console.interaction.total` + `console.web_vital` (labels `breakpoint`/`viewport_bucket`/`orientation`/`route_class`/`interaction_kind`/`web_vital` **all bounded**; raw width/UA/fingerprint **never emitted**; `user.id`/`run.id` on exemplars) | client errors on the diagnostic log class (§6.3) tagged `breakpoint`/`route_class` | **CLS-by-breakpoint** responsive-regression guard (layout error at one width); shares boundaries with the §05 viewport test matrix | opt-in via OTelConfig (D8 default none), same-origin BFF ingest — no browser→vendor egress |

**Disposition:** this plan is the observability design for the Gate-2 architecture, ready to feed Phase-4
epics (OBS-1..7, plus OBS-8..10 for the RBAC user-scoped layer, §16.7). It adds no architectural
decisions, honors the arch's tracing phasing, and reuses the org's Sympozium/MemOS OTel taxonomy. **RBAC
revision r1 (ISI-2306)** layers user-scoped telemetry & audit (§16) with **no cardinality-law exception** —
`user.id` on spans/logs/exemplars, per-user rollups in the backend, bounded `role`/`project` labels for the
dashboards, and an authoritative security audit log — flagged truthful-once-ISI-2303-lands. **Revision r3
(ISI-2333 ← ISI-2327)** adds the **console RUM viewport / device-class dimension** (§18) so ADR-038's
responsive tree is observable — bounded breakpoint/viewport-bucket/orientation/route-class labels,
**privacy-light** (bucketed width, no UA sniffing or fingerprint), opt-in via the OTelConfig seam (D8
default none), CLS-by-breakpoint as the responsive-regression guard — again **no cardinality-law exception,
no new architectural decision**. Ready for Architect/CTO review alongside the architecture at Gate 2.
