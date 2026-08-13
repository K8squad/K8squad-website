---
title: Settings
description: Manage KSquad from the console Settings screen — telemetry export via OTelConfig, plugins, and project configuration — all through the apiserver, no direct kube access.
sidebar_position: 5
---

# Settings

Most day-to-day configuration lives in the console **Settings** screen, which edits KSquad through the
apiserver — you don't need direct `kubectl` access to run the platform.

## Telemetry export (OTelConfig)

By default, KSquad telemetry **stays in-cluster** — nothing is shipped to an external endpoint until
you opt in. To export, create an **`OTelConfig`** from **Settings → Observability** (or with
`kubectl`). It supports **per-signal routing** — send traces to one backend, metrics to another, logs
to a third:

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
      protocol: http
      authSecretRef: dynatrace-token
    metrics:
      endpoint: http://prometheus.monitoring:4317
      protocol: grpc
    logs:
      endpoint: http://loki.monitoring:4317
      protocol: grpc
  resourceAttributes:
    deployment.environment: production
  sampling:
    ratio: 0.25
```

- **The exporter credential is always a Secret ref (`authSecretRef`), never inline** — consistent with
  KSquad's BYO-Secret discipline, and never logged.
- A change re-reconciles **live** — the OTelConfig reconciler reconfigures every component's OTLP
  exporter without a restart.
- The default is **no exporter** — a privacy-safe default (don't egress telemetry unless asked).

Full detail in [Observability](../observability).

## Plugins

Register and configure **plugins** per project/squad from Settings. Plugins are **out-of-process,
read-only observers** of the event stream — a failing plugin can never block a Run, a claim, or a
memory write. See the [Plugin SDK](../plugin-sdk) for building one, and configure outbound plugin
credentials as BYO per-user Secrets (never a shared master credential).

## Project configuration

Per-project settings — repo sync, workspace, egress policy, goals, and context budget — are edited on
the project itself. See [Projects](../concepts/projects) and the [Author Guide](../author-guide).

## Who can change what

Settings visibility and edit rights follow the [RBAC model](./rbac):

- **`admin`** — global settings (telemetry, plugins, users, credentials).
- **`maintainer`** — a project's own settings and membership.
- **`contributor`** — compose and act, but not administer settings.
- **`viewer`** — read-only.
