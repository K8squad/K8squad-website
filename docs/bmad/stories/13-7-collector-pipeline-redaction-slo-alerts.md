# Story 13.7: Collector pipeline + mandatory PII/secret redaction + core SLO alerts

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE EXPORT BACKSTOP AND THE ALERT SPINE FOR ALL OF EPIC 13 (obs-plan §10 + §9, §11 gate #3).**
> Every other Epic-13 story *emits* a signal; this story ships the one place all those signals pass through
> on their way out of the cluster — the **OpenTelemetry Collector** — and pins the two things that make that
> passage safe and useful: (1) a **mandatory `transform`/`redaction` processor that strips PII/secrets before
> any exporter**, so no credential, password, session token, username, or email ever crosses the cluster
> boundary (NFR-SEC3, R9); and (2) the **core SLO alert set** (§9) wired onto the instruments the sibling
> stories already emit. The load-bearing subtlety: **redaction is upstream of every export path, not a
> per-exporter opt-in.** The collector is the *backstop* to service-side discipline (arch §12), never the
> primary control — but it is a hard, always-on backstop. The second subtlety: **processor order is a rule,
> not a preference** — `memory_limiter` first, `batch` last, redaction before `tail_sampling` before any
> exporter. Reorder them and you either OOM under backpressure, batch un-redacted data, or sample on
> attributes that redaction was about to change.

## ⚠️ Scope pin — this story ships the pipeline + redaction + alert rules; it does not instrument (read first)

This story adds **zero** new metrics and **zero** application instrumentation. It ships three things: the
**collector Helm sub-chart** (§10 topology + the fixed processor order), the **mandatory redaction
processor** (§6) with its secret-leak falsification bench (§11 gate #3), and the **core SLO alert rules**
(§9) as `PrometheusRule`/OTel alert config. The signals it exports and alerts on are authored by the other
Epic-13 stories (13.1 traces, 13.2 coord metrics, 13.3 blocked-by gauge, 13.4 token metering, 13.5
per-ticket trace) and Epic 12 (outbox/JetStream lag). The one-line boundary: **13.7 makes the signals leave
the cluster safely and page/ticket when they breach SLO; the sibling stories make the signals; 13.8 makes
the exporter *destinations* configurable.**

| Concern | This story | Owned elsewhere |
|---|---|---|
| Collector Helm sub-chart (gateway Deployment + optional node DaemonSet), values-toggled, endpoint-gated per §1.5 | **✅ delivered** | Chart skeleton = 1.4; egress NetPol templates = `internal/tenancy` (arch §9.2/§11.1) — this story adds **one allowlist entry** |
| The fixed processor order (`memory_limiter` → k8sattributes → resource → **transform/redaction** → tail_sampling → `batch`) | **✅ delivered (AC1)** — order is a hard rule | — |
| Mandatory PII/secret redaction processor before **any** exporter (NFR-SEC3, R9, §6) | **✅ the crux (AC2/AC3)** | Service-side "don't log secrets in the first place" = arch §12 (primary control; this is the backstop) |
| Secret-leak falsification bench (planted secret shapes are dropped/hashed; opaque `user.id` survives) | **✅ delivered (AC6)** | The isolation suite that asserts no secret in a **real Run** = §4.3 arch / §11 gate #3 |
| Core SLO **alert rules** (§9): fencing/crash-reclaim, warm-pool exhaustion, pause-on-auth **and** pause-on-rate-limit, outbox/JetStream lag | **✅ delivered (AC4)** — the rules | The **instruments** the rules fire on = 13.2 (coord/fence), 13.3–13.5 (Run/warm-pool/pause), Epic 12 (outbox lag) |
| Egress: sandboxes reach the **in-cluster gateway only**; the gateway (system ns, governed egress) reaches the vendor | **✅ the isolation invariant (AC5)** | The default-deny NetPol itself = arch §9.2 (Story 4.6 / `internal/tenancy`) — this story routes *through* it, never around it |
| Exporter **destinations** (per-signal OTLP routing, Secret-ref auth, sampling) driven by the `OTelConfig` CRD | consumed | **Story 13.8** (`OTelConfig` reconciler, ISI-2151) — redaction (this story) runs **upstream** of whatever 13.8 configures |
| Cardinality lint on metric labels | consumed | **Story 13.6** (ISI-2238) — a different gate on a different axis |
| Weaver semconv registry + semconv CI validation | consumed | **OBS-7** (§11 gate #2) |

## Story

As **an SRE operating the platform**,
I want **the collector pipeline with a mandatory PII/secret redaction processor that strips credentials,
passwords, session tokens, usernames, and emails before any exporter — plus the core SLO alert rules on the
fencing, warm-pool, pause-on-auth/rate-limit, and outbox-lag signals**,
so that **telemetry leaves the cluster legible and metered but never leaking a secret or PII, and the two
correctness SLOs the architecture stakes its differentiators on (claim latency, crash-reclaim health) page
me before an operator notices — while pause backlogs, warm-pool exhaustion, and event-bus lag open tickets.**

## Context & prerequisites (read first)

- **Observability plan:** `docs/bmad/04-observability-plan.md`
  - **§10 "Collector pipeline design"** — the authoritative topology + the **fixed processor order** this
    story mechanizes (`memory_limiter` first, `batch` last; `k8sattributes` because KSquad is k8s-native,
    never `resourcedetection`; redaction before any exporter; `tail_sampling` after enrichment/redaction,
    before batch). Also the **egress interaction** (allowlist the in-cluster gateway; sandboxes never get
    direct vendor egress) — an explicit input to the `internal/tenancy` NetworkPolicy templates.
  - **§6 "Logging strategy → PII & secret redaction (mandatory, NFR-SEC3 + R9)"** — the redaction contract:
    credential patterns (`CLAUDE_CODE_OAUTH_TOKEN`, bearer/API-key shapes), passwords/session/auth tokens,
    usernames/emails (RBAC PII, §1.4), and known secret-ref keys are dropped/hashed; **only the opaque
    `user.id` survives**; agent-authored content (memory bodies, work-item text, model output) is never
    logged verbatim — IDs/kinds/lengths/hashes only. Double-guarded: services don't log secrets (arch §12);
    the collector is the backstop.
  - **§9 "Alerting & SLOs"** — the alert table this story ships as rules. The **two page-grade correctness
    SLOs** (`sandbox.claim.duration{pool_hit=warm}` p95 / `pool_hit=cold` rate; `coord.lease.reclaim` thrash
    + `stale_holder` renewals) and the **ticket-grade** rest (Run failure rate, stuck Runs, paused backlog,
    memory authz denials, poisoning candidates, reconcile errors, shim conformance). Alert-fatigue discipline:
    the page set stays small and correctness-focused.
  - **§8 "Security & poisoning signals"** and **§16.3** (RBAC auth/authz/admin metrics) — the security alert
    inputs (poisoning candidates → page; brute-force login / privilege-escalation / access-probing → ticket).
  - **§11 gate #3 "Secret-leak scan"** — the isolation suite asserts no credential appears in any span/log in
    a real Run; **the collector redaction processor is unit-tested against known secret shapes** (this story's
    bench).
- **Epics:** `docs/bmad/04-epics-and-stories.md` row **13.7** ("collector pipeline with **mandatory**
  PII/secret redaction + core SLO alerts … Redaction is mandatory, not optional"); paired with row **13.8**
  (`OTelConfig` reconciler — "the mandatory redaction pipeline (13.7) runs before any exporter").
- **Architecture:** §17.2 (observability), §9.2 / §11.1 (per-squad default-deny egress NetworkPolicy — the
  allowlist entry for the gateway lands here), §12 (services must not log secrets — the primary control),
  §4.6 (Helm chart / collector as a values-toggled component).
- **Dependencies (instruments the alerts fire on):** 13.2 (ISI-2234 coord/fence metrics — DONE), 13.3
  (ISI-2235 blocked-by gauge — DONE), 13.4 (ISI-2236 token metering — in review), 13.5 (ISI-2237 per-ticket
  trace — DONE), Epic 12 (ISI-2260 event seam — outbox/JetStream lag; DONE). Story 1.4 (Helm chart skeleton —
  DONE) and Story 4.6 (egress NetPol — DONE) are the surfaces this story extends.

## Acceptance criteria

- **AC1 — the collector ships as a values-toggled Helm component with the fixed processor order.** The
  chart adds an **OTel Collector gateway** (Deployment, system namespace) + an **optional node DaemonSet**,
  on-by-default and **endpoint-gated per §1.5** (no configured export endpoint ⇒ signals stay in-cluster).
  The gateway pipeline is **exactly**: `receivers: [otlp (grpc/http), prometheus]` → `processors:
  [memory_limiter, k8sattributes, resource, transform/redaction, tail_sampling, batch]` → `exporters:
  [prometheus|prometheusremotewrite, otlp/<vendor>, debug (dev only)]`. **`memory_limiter` MUST be first,
  `batch` MUST be last**; `k8sattributes` (never `resourcedetection`); `tail_sampling` **after** redaction,
  **before** batch. A config that reorders these fails the chart's config test.
- **AC2 — redaction is mandatory and upstream of every exporter (the crux).** The `transform`/`redaction`
  processor sits **before any exporter** on **all three signal pipelines** (traces, metrics-exemplars, logs)
  and scans bodies + attributes for: credential patterns (`CLAUDE_CODE_OAUTH_TOKEN`, `Authorization: Bearer`,
  API-key shapes), passwords + session/auth tokens, **usernames and emails** (RBAC PII, §1.4), and known
  secret-ref keys — **dropping or hashing** each. Only the **opaque `user.id`** survives. It is **not** a
  per-exporter opt-in: opting into an external endpoint (13.8) never bypasses it. Removing the processor, or
  moving it after an exporter, is a config-test failure.
- **AC3 — agent-authored content is never exported verbatim.** Memory bodies, work-item text, and model
  output are treated as **untrusted** (§6, §7.3 arch): the pipeline exports only their **IDs, kinds, lengths,
  and hashes** — never the raw text. The redaction bench plants a raw model-output body and asserts only the
  hash/length survive.
- **AC4 — the core SLO alert rules exist and match §9.** The chart ships alert rules (`PrometheusRule` /
  OTel alerting config) for, at minimum: **(page)** warm-claim latency (`sandbox.claim.duration{pool_hit=warm}`
  p95 > 5s/10m **or** `pool_hit=cold` rate > 5%), pool readiness (`warmpool.ready` = 0 under claim pressure),
  crash-reclaim health (`coord.lease.reclaim` thrash ≥ 3× baseline **or** sustained `stale_holder` renewals),
  poisoning candidates (any sustained non-zero); **(ticket)** Run failure rate, stuck Runs, **paused-backlog
  covering BOTH reasons** — `run.paused.active{reason}` with `reason ∈ credential|rate_limited` (pause-on-auth
  **and** pause-on-rate-limit, 3.7/7.6) — memory authz denials, reconcile errors, and **outbox/JetStream lag
  (Epic 12)**; **(block release)** shim conformance regression. Each rule names an actionable operator
  runbook. The **page set stays small** (the two correctness SLOs + pool readiness + poisoning) — everything
  else is ticket-grade (alert-fatigue discipline, §9).
- **AC5 — telemetry routes *through* the tenancy model, never around it (isolation invariant).** The
  per-squad **default-deny egress NetworkPolicy** (arch §9.2, Story 4.6) is extended with **exactly one**
  allowlist entry: the in-cluster **collector gateway service**. Sandboxes/shims OTLP-push to the gateway and
  get **no** direct egress to the vendor backend; only the gateway (system namespace, governed egress)
  reaches Dynatrace/Prometheus remote-write. A test asserts a sandbox cannot reach the vendor endpoint
  directly and *can* reach the gateway.
- **AC6 — redaction is tested, not hoped for (falsification bench).** A differential bench feeds the
  redaction processor a fixture stream: a clean baseline exports unchanged, and each planted secret/PII shape
  (OAuth token, bearer header, API key, password field, session token, username, email, a `secretRef` value,
  and a raw agent-content body) is **dropped or hashed** on output while the opaque `user.id` survives.
  Weakening the redaction rules (e.g. narrowing the token regex) flips the bench RED; moving redaction after
  the exporter flips it RED (verified by live mutation).

## Deliverables

- **Collector Helm sub-chart** — gateway Deployment + optional node DaemonSet, values-toggled + endpoint-gated
  (§1.5), with the **fixed processor order** and a **chart config test** that fails on reorder / missing
  redaction (AC1/AC2). Lands under the source-repo chart (`charts/…/collector`); the BMAD spec + reference
  config live at `docs/bmad/spikes/bench/collector-pipeline.yaml`.
- **Redaction processor config** — the `transform`/`redaction` rules covering the §6 secret+PII shapes,
  positioned before every exporter on all three pipelines (AC2/AC3).
- **Core SLO alert rules** — `PrometheusRule` (or OTel alerting config) for the §9 table, page/ticket/block
  severities, each mapped to a runbook (AC4). Reference at `docs/bmad/spikes/bench/slo-alerts.yaml`.
- **Egress-allowlist entry** — one rule added to the `internal/tenancy` default-deny NetworkPolicy template
  admitting the collector gateway service (AC5).
- **Redaction falsification bench** — `docs/bmad/spikes/bench/redaction-leak-check.py`: GREEN baseline + one
  mutation per planted secret/PII/agent-content shape, plus a "redaction-after-export" and a
  "weakened-rule" mutation that both flip RED (AC6, §11 gate #3).

## Verification

```
# Config order + redaction-present gate (fails on reorder / missing redaction)
helm template charts/.../collector | <config-order-check>          # → memory_limiter first, batch last, redaction pre-export
python3 docs/bmad/spikes/bench/redaction-leak-check.py             # → OK (baseline clean; every planted secret dropped/hashed; user.id survives)
# Egress: sandbox → gateway allowed, sandbox → vendor denied
<netpol-test>                                                      # → gateway reachable, vendor endpoint unreachable from sandbox
```

## Handoffs

- **← Instruments (already landed / in flight):** 13.2 (coord/fence, DONE), 13.3 (blocked-by, DONE), 13.4
  (token metering, in review), 13.5 (per-ticket trace, DONE), Epic 12 (outbox/JetStream lag, DONE). This
  story wires **alert rules** onto their signals; it does not emit them.
- **→ Story 13.8 (`OTelConfig` reconciler, ISI-2151):** 13.8 configures the exporter *destinations*
  (per-signal OTLP routing, Secret-ref auth, sampling) from the CRD. **The redaction pipeline this story
  ships runs upstream of whatever 13.8 configures** — opting into an external endpoint never bypasses PII/
  secret stripping. 13.8 must wire its exporters **downstream** of the fixed `transform/redaction` processor.
- **→ Testing Architect / §11 gate #3:** the redaction bench here is the unit-level guard; the real-Run
  secret-leak assertion (no credential in any span/log during an actual Run) rides the §4.3 isolation suite.
- **→ SRE / operator:** each alert rule ships with a runbook pointer; the page set is deliberately the two
  correctness SLOs + pool readiness + poisoning (§9 philosophy) — keep additions ticket-grade.
