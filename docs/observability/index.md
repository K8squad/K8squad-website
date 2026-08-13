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
  fallback signals, and consumption metering (below).
- **Logs** — structured logs from every component.
- **Live progress (SSE)** — separate from OTLP export, the console streams live Run progress over
  Server-Sent Events. (SSE is for the operator watching now; OTLP is for your telemetry backend.)

## Opt-in export with `OTelConfig`

**By default, telemetry stays in-cluster** — nothing is shipped externally until you create an
`OTelConfig`. This is a deliberate privacy-safe default: KSquad won't egress your telemetry unless you
ask it to.

`OTelConfig` supports **per-signal routing** — send each signal to a different backend:

```yaml
apiVersion: ksquad.io/v1alpha1
kind: OTelConfig
metadata:
  name: default
  namespace: ksquad-system
spec:
  exporters:
    traces:
      endpoint: https://otlp.dynatrace.example/api/v2/otlp
      protocol: http                 # grpc | http
      authSecretRef: dynatrace-token # exporter credential is ALWAYS a Secret ref, never inline
    metrics:
      endpoint: http://prometheus.monitoring:4317
      protocol: grpc
    logs:
      endpoint: http://loki.monitoring:4317
      protocol: grpc
  resourceAttributes:
    deployment.environment: production
    service.namespace: ksquad
  sampling:
    ratio: 0.25
```

- **Per-signal fan-out** — traces to one backend, metrics to another, logs to a third.
- **Secret-ref credentials only** — the exporter token is a Kubernetes Secret ref (`authSecretRef`),
  never inline, and never logged.
- **Live reconfiguration** — the OTelConfig reconciler applies changes without a restart.
- **Edit from the console** — Settings → Observability writes it through the apiserver; no direct kube
  access needed. See [Settings](../operator-guide/settings#telemetry-export-otelconfig).

## Consumption metering

KSquad meters model/run consumption along four axes — **`{user/principal, agent, run, project}`** — and
emits it as OTel metrics labeled `{team, project, run, agent, principal, model}`. This feeds the
console's per-project consumption dashboard.

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

The Run [rate-limit recovery](../concepts/runs#rate-limit-recovery) hierarchy emits named metrics,
dimensioned per project / agent / role (plus provider/model):

| Metric | Type | Meaning |
|--------|------|---------|
| `ksquad.ratelimit.hits` | counter | rate-limit events, `{project, agent, role, provider, model}` |
| `ksquad.ratelimit.duration_seconds` | histogram | time Runs spent `Paused(rate_limited)` |
| `ksquad.fallback.activations` | counter | mid-Run fallback-model switches |
| `ksquad.fallback.duration_seconds` | histogram | time spent on the fallback model |

These ride the same `OTelConfig` export path and feed the dashboard's per-project/agent/role panels;
their transitions also publish events plugins can alert on.

## Platform health metrics

The plugin event seam is itself observable: outbox depth, unflushed-event lag, NATS publish failures,
and JetStream consumer lag are all OTel metrics — so you can see whether events are flowing to your
plugins.

## Dashboards

The console's per-project [dashboard](../console-guide#project-dashboard) aggregates these signals —
tickets by status, consumption and its trend, PR status, live Runs — through a pluggable
metrics-backend query seam, so it works with the metrics backend you already run.

## The audit trail

Separate from OTLP metrics, the coordination record (`coord`) is a durable **audit trail** — every
claim, comment, and artifact, with provenance. Between the audit trail (what happened) and OTel traces
(how it flowed), you have full accountability for every unit of work.
