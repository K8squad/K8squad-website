---
stepsCompleted: [context, taxonomy, tracing, metrics, logging, semconv, collector, alerting, handoff, complete]
inputDocuments:
  - docs/bmad/02-prd.md              # NFR-OBS1/2, S9, NFR-PERF1, NFR-SEC1..6, NFR-REL1..3
  - docs/bmad/03-architecture.md     # component map, Run reconcile (§5), coordination spine (§6), shim/A2A (§7), memory (§8), tenancy/egress (§9), credentials (§10)
  - ISI-1406                          # Sympozium observable-llm — 7-signal taxonomy (reason-labeled runs, handoff latency, memory r/w, access decisions, traceparent chain)
  - Sympozium PR #11 / PR #18         # OTel instrumentation (traces+metrics+logs; traceparent on AgentRun CR; noop-on-unset; slog+otelslog; HTTP-transport auto-trace)
  - ISI-1918                          # MemOS memory-semconv v0.1.0 (memory.tier/operation/cube.id; memory_operations_total, memory_operation_duration_ms, memory_result_count)
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
   `run.id`, `work_item.id`, `principal.id`, `sandbox.pod`, `trace_id` are **unbounded** → they live on
   spans, logs, and metric **exemplars**, *never* as Prometheus label values. Metric labels are drawn
   only from the **bounded** enum sets in §5.6. This is the single rule most likely to be violated; it
   is a first-class review gate (§12).
3. **Vendor-neutral at the seam.** Instrumentation is OTel SDK + semantic conventions only. Backend
   choice (Prometheus scrape, Dynatrace OTLP, LGTM) is a **collector exporter** decision, swappable
   without touching a line of service code. Mirrors the architecture's own seam discipline (§7.4).
4. **Secrets and untrusted content never enter telemetry.** NFR-SEC3 (§12 of arch): credentials are
   never logged/echoed/artifacted — and by extension never span-attributed. Agent-authored strings
   (memory content, work-item bodies, model output) are **untrusted input** (§8.4 arch, R9): they are
   PII-scanned and are never emitted verbatim as span/log attributes — only hashes, lengths, kinds,
   and provenance IDs.
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
| operator → apiserver (coordination writes) | gRPC/HTTP OTel propagator (auto) | control plane |
| operator/apiserver → shim | **A2A task metadata** `traceparent` field | `internal/a2a` (§7) |
| controller ↔ `Run` CR (async, cross-restart) | **`Run.status` annotation** `ksquad.io/traceparent` | Run controller (§5.2) |
| shim → agent runtime | env `TRACEPARENT` (Sympozium Job-level pattern) + in-proc | shim |
| agent → ksquad-memory | **MCP request metadata** `traceparent` | `internal/memory` MCP server (§8) |
| shim → apiserver SSE hub | SSE event carries `run.id` + `span_id` for stitching | `internal/sse` (§7) |

The CR-annotation hop is what makes the trace **survive a controller restart** — the reconcile loop is
idempotent and level-triggered (§12 arch), so the trace context must be **durable state**, not in-memory
continuity. This is the KSquad translation of Sympozium's "traceparent annotation on the AgentRun CR."

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

Standard on every span: `ksquad.run.id`, `ksquad.team` (squad namespace), `ksquad.project`,
`ksquad.runtime`, `service.name`, plus OTel resource (`k8s.namespace.name`, `k8s.pod.name`,
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
| `ksquad.agent.tokens` | counter | `runtime`, `direction` (input\|output) | token accounting (Sympozium `agent.context.input_tokens`), best-effort per shim |

`capability` and `check` are bounded by the conformance suite's fixed check list (§7.5 arch) — a vendor
adding a runtime cannot inflate cardinality because the check set is fixed by the suite, not the runtime.

### 5.6 Cardinality budget (the enforced label allowlist)

**Bounded label domains (allowed as metric labels):** `outcome`, `terminal_reason` (curated enum),
`phase`, `from`/`to` (phase enum), `runtime` (openclaw\|hermes\|…, finite), `runtime_class`
(kata\|gvisor), `operation`, `result`, `state`, `kind`, `trigger`, `reason` (curated enums),
`decision`, `surface`, `capability`, `check`, `direction`, `pool_hit`, `cause`, `provenance_class`,
`signal`. Total series per instrument stays in the low hundreds.

**Forbidden as metric labels (trace/log/exemplar only):** `run.id`, `work_item.id`, `principal.id`,
`sandbox.pod`, `trace_id`, `team`/`project` names (these ride as **resource attributes** for scoping,
which Prometheus federates without per-series explosion, or as exemplars). A CI check (§11) greps the
instrumentation for label keys outside the allowlist and fails the build — cardinality discipline is
tested, not hoped for.

---

## 6. Logging strategy

- **Structured, correlated:** Go services use `slog` + `otelslog` bridge (Sympozium pattern) so every
  line auto-carries `trace_id`, `span_id`, `ksquad.run.id`, `service.name`. Console (Node) uses `pino`
  with the same fields injected server-side in the BFF. JSON out; the collector adds k8s resource attrs.
- **Two log classes, kept distinct:**
  1. **Audit log = the `run_events`/`audit_log` rows in Postgres** (§6.1 arch) — the durable,
     queryable operator-facing record (D4, NFR-OBS1). This is *authoritative* and is **not** replaced by
     stdout logs. Observability *exports a projection* of it (metrics §5.1, and optionally a log-pipeline
     mirror for the vendor backend) but never treats stdout as the audit source of truth.
  2. **Application/diagnostic logs** — stdout JSON, sampled/leveled, for debugging. Ephemeral by
     comparison.
- **PII & secret redaction (mandatory, NFR-SEC3 + R9):** a collector `transform`/`redaction` processor
  runs a PII+secret scan on all log bodies and attributes before export: credential patterns
  (`CLAUDE_CODE_OAUTH_TOKEN`, bearer/API-key shapes), emails, tokens, and known secret-ref keys are
  dropped/hashed. Agent-authored content (memory bodies, work-item text, model output) is treated as
  **untrusted** and is never logged verbatim — only IDs, kinds, lengths, hashes. This scan is
  double-guarded: services must not log secrets in the first place (arch §12), and the collector is the
  backstop.
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
| `ksquad.authz.surface` | string | memory\|claim\|egress | |
| `ksquad.fence.epoch` | int | monotonic | lease-epoch/fence token (§6.2) |

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

Parallel `ksquad.authz.decisions{surface, decision}` covers the three authz surfaces (memory write,
work-item claim, egress) — a rising `denied` rate is either an attack or a misconfiguration, both of
which the operator must see.

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
| Collector + semconv registry + dashboards + alerts | in-repo config, Weaver registry | P0 |

**CI gates (observability-as-code):**
1. **Cardinality lint** — grep instrumentation for metric label keys outside the §5.6 allowlist → fail.
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

---

## Appendix A — Signal-to-component matrix (the §17.2 coverage the ticket asked for)

| Architecture component | Metrics | Traces | Logs / Audit | Alert |
|------------------------|---------|--------|--------------|-------|
| Coordination record (§6) — claim/lease/renew/reclaim, fence, appends | §5.1 | claim/lease spans | `audit_log`/`run_events` (authoritative) | crash-reclaim page |
| Run state machine (§5) — transitions, retry/backoff, pause-on-auth | §5.2 | **Run trace root (§3)** | phase-transition INFO logs | stuck-Run, paused-backlog |
| Sandbox / warm pool (§5.4) — claim latency, ready-count, teardown | §5.3 | sandbox.claim span | teardown/replenish logs | claim-latency + readiness page |
| Memory service (§8) — r/w counters w/ provenance+scope, poisoning | §5.4 | memory.op span | denied-write logs (provenanced) | poisoning page, authz ticket |
| Shim / A2A (§7) — SSE progress, capability negotiation, conformance | §5.5 | shim.execute span + traceparent | A2A lifecycle logs | conformance-regression block |

**Disposition:** this plan is the observability design for the Gate-2 architecture, ready to feed Phase-4
epics (OBS-1..7). It adds no architectural decisions, honors the arch's tracing phasing, and reuses the
org's Sympozium/MemOS OTel taxonomy. Ready for Architect/CTO review alongside the architecture at Gate 2.
