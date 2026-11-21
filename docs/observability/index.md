---
title: Observability
description: KSquad's telemetry — OpenTelemetry traces, metrics, and logs; opt-in per-signal export via the OTelConfig CRD; consumption metering; and dashboards.
sidebar_position: 7
---

# Observability

KSquad is built to be legible. Every component — the operator, apiserver, memory service, console, and
the agent shims — emits **OpenTelemetry**. Where that telemetry goes is **your choice and opt-in**,
configured by a CRD rather than hardcoded.

## What KSquad emits

- **Traces** — per-Run traces correlate a Run across the operator's reconcile, the apiserver's
  coordination calls, memory reads/writes, and the agent shim, so you can follow one unit of work end
  to end.
- **Metrics** — Run lifecycle counters, claim/lease metrics, memory read/write counters, rate-limit and
  fallback signals, tool and skill usage (below), and consumption metering.
- **Logs** — structured logs from every component.
- **Live progress (SSE)** — separate from OTLP export, the console streams live Run progress over
  Server-Sent Events. (SSE is for the operator watching now; OTLP is for your telemetry backend.)

## Tool and skill usage telemetry

The capability plane is instrumented end to end. Every tool call, skill load, and MCP call emits
spans following the **OpenTelemetry GenAI semantic conventions**, plus bounded-cardinality metrics:

| Signal | Name | Labels / attributes |
|--------|------|---------------------|
| Span | `gen_ai.tool.call` | `gen_ai.tool.name`, hashed arguments (raw arguments never travel), outcome, duration |
| Span | `skill.load` | skill name, pinned source SHA |
| Span | `mcp.call` | MCP server, `gen_ai.tool.name`, outcome, duration |
| Counter | `ksquad_tool_calls_total` | `{tool, agent, skill}` |
| Counter | `ksquad_skill_loads_total` | `{skill, agent}` |
| Histogram | `ksquad_mcp_call_duration_seconds` | `{server, tool}` |

Tool-call arguments are reduced to a hex SHA-256 before they leave the pod — you can see *that* a
credential-touching tool ran, and correlate it with the Run's
[capability manifest](/docs/concepts/runs/#the-capability-manifest), but secrets and payloads never land
in telemetry.

Two plumbing notes:

- **Where it flows from.** The in-pod shim hook and the operator-side A2A dispatch feed both map into
  the same telemetry pipeline, so events emitted inside sandboxes and events dispatched by the
  operator land in one place — the `ksquad_*` series are also scrapeable on the operator's
  `/metrics` endpoint.
- **The toggle.** The tool-usage pipeline is gated by `OTelConfig.spec.toolUsage.enabled` and defaults
  to enabled; turning it off emits no spans and no metric samples at all (opt-out, not just
  filter-out).

The console's Run view surfaces tool and skill activity alongside the live SSE stream, so an operator
watching a Run sees which capabilities the agent is actually exercising — the same data the exported
metrics carry, without a backend round-trip.

## Opt-in export with `OTelConfig`

**By default, telemetry stays in-cluster** — nothing is shipped externally until you create an
`OTelConfig`. This is a deliberate privacy-safe default: KSquad won't egress your telemetry unless you
ask it to.

`OTelConfig` supports **per-signal routing** — each signal is a top-level key with its own exporter,
send each to a different backend:

```yaml
apiVersion: ksquad.io/v1alpha1
kind: OTelConfig
metadata:
  name: default
  namespace: ksquad-system
spec:
  traces:
    endpoint: https://otlp.dynatrace.example/api/v2/otlp
    protocol: http/protobuf        # grpc | http/protobuf | http/json
    auth:                          # exporter credential is ALWAYS a Secret ref, never inline
      name: dynatrace-token
      key: token
    resourceAttributes:
      deployment.environment: production
    sampling:                      # traces only
      type: probabilistic
      ratio: 0.25
  metrics:
    endpoint: prometheus.monitoring:4317
    protocol: grpc
  logs:
    endpoint: http://loki.monitoring:4317
    protocol: grpc
  toolUsage:                       # opt-out toggle for the tool-usage pipeline (absent = enabled)
    enabled: true
```

- **Per-signal fan-out** — `spec.traces`, `spec.metrics`, `spec.logs` each carry `endpoint` and
  `protocol` (required; `grpc` | `http/protobuf` | `http/json`), plus optional per-signal
  `resourceAttributes` and, for traces, `sampling` (`always_on` | `always_off` | `probabilistic`
  with `ratio`). At least one signal must be configured.
- **Secret-ref credentials only** — the exporter token is a Secret ref (`auth: {name, key}`, with
  optional `namespace`), never inline, and never logged.
- **`toolUsage` toggle** — `spec.toolUsage.enabled` gates the tool-usage pipeline platform-wide;
  absent defaults to enabled (opt-out, not filter-out).
- **Live reconfiguration** — the OTelConfig reconciler applies changes without a restart.
- **Edit from the console** — Settings → Configuration writes it through the apiserver (`/api/otelconfig`);
  no direct kube access needed. See [Settings](/docs/operator-guide/settings/#telemetry-export-otelconfig).

## Consumption metering

KSquad meters model/run consumption along four axes — **`{user/principal, agent, run, project}`** — as
OTel metrics (`ksquad_llm_calls_total{model, agent}`, `ksquad_llm_tokens_total{model, agent, direction}`,
with `ksquad.llm.cost.usd` on the spans), correlated to the run/principal via span attributes
(`ksquad.run.id`, `ksquad.principal.id`, `ksquad.project.name`, `ksquad.team.name`,
`ksquad.agent.name`). This feeds the console's per-project consumption dashboard.

The metering is **non-forgeable by construction**:

- The existence and shape of consumption are anchored to signals the **control plane owns, not the
  agent**: Run lifecycle events come from the operator's own reconcile, and sandbox CPU/memory come
  from kubelet/cAdvisor. A compromised agent **cannot fabricate a Run, hide one, or misattribute one**.
- **Per-call token counts are best-effort** — where a runtime reports them, they're attributed to the
  anchored Run and sanity-bounded against run-minutes and resource usage, but they are explicitly *not*
  the authoritative axis. A runtime that reports nothing degrades gracefully to run-minutes/resource
  attribution.
- Because every credential is a per-user Secret (no shared master credential), consumption is
  **attributable to the owning principal by construction** — there's no shared-credential
  disambiguation problem.

KSquad reports **estimated** cost via a configurable price table and **never claims to be a billing
system of record** — an honest limit, surfaced, not hidden.

## Rate-limit & fallback signals

The Run [rate-limit recovery](/docs/concepts/runs/#rate-limit-recovery) hierarchy emits named metrics,
dimensioned per project / agent / role:

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `ksquad_fallback_activations_total` | counter | `{project, agent, role, primary_model, fallback_model}` | mid-Run fallback-model switches |
| `ksquad_fallback_duration_seconds` | histogram | `{project, agent, role}` | time served from the fallback model |

The rate-limit pair (`ratelimit.hits` / `ratelimit.duration_seconds`) is **planned** — it lands with
the rate-limit metric stories (ISI-2296/2297); until then, `Paused(rate_limited)` time is visible in
traces and the Run's status. The fallback metrics ride the same `OTelConfig` export path and feed the
dashboard's per-project/agent/role panels.

## Platform health metrics

The plugin event seam is itself observable — the event relay exports these metrics (also scrapeable
on the operator's `/metrics` endpoint):

| Metric | Type | Meaning |
|--------|------|---------|
| `ksquad_outbox_depth` | gauge | total rows in `coord.outbox` |
| `ksquad_outbox_unflushed_lag` | gauge | rows not yet published to NATS (relay backlog) |
| `ksquad_outbox_publish_failures_total` | counter | NATS publish failures (at-least-once retry leaves the row unflushed) |
| `ksquad_jetstream_consumer_lag` | gauge | messages pending across JetStream consumers (fan-out lag) |

If your plugin seems to be missing events, check these first.

## Dashboards

The console's per-project [dashboard](/docs/console-guide/#project-dashboard) aggregates these signals —
tickets by status, consumption and its trend, PR status, live Runs — through a pluggable
metrics-backend query seam, so it works with the metrics backend you already run.

## The audit trail

Separate from OTLP metrics, the coordination record (`coord`) is a durable **audit trail** — every
claim, comment, and artifact, with provenance. Between the audit trail (what happened) and OTel traces
(how it flowed), you have full accountability for every unit of work.
