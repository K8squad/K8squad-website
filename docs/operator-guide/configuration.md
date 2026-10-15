---
title: Configuration
description: Configure KSquad through Helm values and CRDs — high-availability toggles, warm-pool policy, egress defaults, and runtime image lifecycle.
sidebar_position: 2
---

# Configuration

KSquad is configured on two levels:

- **Install-time / infrastructure** — Helm values (dependencies, HA, exposure, storage, warm pool).
- **Runtime / behavior** — CRDs (`AgentRuntime`, `Role`, `Skill`, `Project`, `OTelConfig`) and the
  console **Settings** page.

This page covers the infrastructure level. For behavior, see the [Author Guide](/docs/author-guide/) and
[Settings](/docs/operator-guide/settings/).

## Helm values overview

| Area | Key values | Notes |
|------|-----------|-------|
| Default model | `modelConfig.default.model` | **Required** — install aborts without it. |
| Event bus storage | `controlPlane.nats.persistence.storageClassName`, `.size` | Required when NATS is enabled (default); no cluster-default fallback. HA: `controlPlane.nats.ha.enabled` / `.replicas` (odd, ≥3). |
| Exposure | `exposure.gateway.enabled`, `exposure.gateway.gatewayClassName`, `exposure.gateway.hostnames.console` / `.apiserver` | See [Install & exposure](/docs/operator-guide/install/#networking--exposure). |
| Postgres | `controlPlane.database.existingSecret` (or dev-only `.dsn`) | Bring your own — HA/sizing live with your Postgres, not the chart. |
| Workspace volumes | `workspacePVC.defaultClass`, `.defaultSize`, `.defaultAccessModes` | Operator defaults for per-Run workspace PVCs; per-Project override via `spec.workspacePVC`. |
| Auth | `controlPlane.auth.jwtSigningKey.existingSecret` | JWT signing key from an existing Secret. |
| Images | `controlPlane.image.registry`, `.tag`, `.tagOverrides` | Per-component tag overrides for mixed-sha clusters. |
| Observability | `controlPlane.otel.endpoint`, `observability.otel.*` | OTLP wiring + the rendered `OTelConfig` CR. |

> The exact value paths track the chart version you install — always check `helm show values ksquad/ksquad`
> for the authoritative list.

## High availability

The bundled NATS defaults to a single JetStream replica; cluster it with a values toggle (replicas
must be odd and ≥3 for a RAFT quorum):

```bash
--set controlPlane.nats.ha.enabled=true --set controlPlane.nats.ha.replicas=3
```

Postgres HA is yours to run — it is not part of the chart, so size and replicate it where it lives.

The stateless components (operator, apiserver, memory, console) scale horizontally; the operator is
**leader-elected**, so running multiple replicas gives you failover without double-driving reconciles.

## Warm pool

Sandboxes come from a **warm pool** so Run claim latency stays low. Warm pods are keyed by
**(RuntimeClass × AgentRuntime image)** — *not* by skill set, because skill toolchains are staged
per-Run from node-cached packs. That keeps the pool small (one dimension, the agent base) while
skill-specific toolchains attach at claim time.

Tune size and policy per runtime:

```yaml
sandbox:
  warmPool:
    default:
      size: 2            # warm pods held ready per key
      maxIdle: 30m
    claude-code:
      size: 4
```

When a runtime image is updated (see below), KSquad **drains and re-warms** the affected key so cold
starts don't balloon.

## Runtime images & the update lifecycle

`AgentRuntime.cliVersion` is **pinned by default** for reproducibility. To keep runtimes fresh without
CI thrash or blind cold-start pulls, KSquad runs an internal **ImageUpdater** controller that:

1. watches upstream CLI release feeds on a schedule;
2. proposes a `cliVersion` bump;
3. **canaries exactly one sandbox** against the shim conformance suite before rolling the bump;
4. triggers a warm-pool refresh so warm pods and node pre-pull stay current.

You keep control: pin `cliVersion` explicitly to freeze a runtime, or opt a runtime into faster updates
in non-production. A bad upstream release can't silently poison in-flight Runs because everything is
pinned and canaried first.

## Toolchains and sidecars

Language toolchains (`go@1.23`, `node@22`, `python@3.13`, …) are **versioned OCI images** staged as
init containers at Run time; long-running services (rootless `dockerd`, headless browsers) are
**sidecars**, capability-gated. You don't pre-build a combinatorial image matrix — skills declare what
they need and the operator assembles the pod. See [Skills](/docs/concepts/skills/).

Pre-pull toolchain and runtime images onto nodes for fast warm starts (this is also what makes
air-gapped installs practical).

## Egress defaults

Each squad gets a default NetworkPolicy. Author an `EgressPolicy` CR and point projects at it with
`Project.spec.egressPolicyRef`:

Egress control is part of the safety model — a compromised agent can only reach endpoints it was
explicitly granted. See [Multi-tenancy & isolation](/docs/concepts/squads/#why-the-tenancy-boundary-matters).
