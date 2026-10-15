---
title: Install & exposure
description: Install KSquad with Helm, wire networking with Gateway API, name your StorageClass, choose a sandbox runtime, and support air-gapped clusters.
sidebar_position: 1
---

# Install & exposure

KSquad installs with **Helm** — two charts: the standalone `k8squad-crds` chart owns the `ksquad.io`
CRDs and goes on **first**, then the `k8squad` control-plane chart. This page covers what that brings
up, the decisions the chart won't guess for you (exposure and storage), the sandbox runtime, and
air-gapped installs.

## What one install brings up

The `k8squad` chart with `controlPlane.enabled=true` deploys into `ksquad-system`:

- the **operator** (controllers for every CRD)
- the **apiserver** (coordination record, audit, SSE, source-control webhooks, and the built-in auth +
  RBAC middleware)
- the **memory service** (the knowledge record)
- the **console**
- **NATS/JetStream** (the plugin event bus — event flow only, no state of record)

The `ksquad.io` **CRDs** themselves are owned by the separate `k8squad-crds` chart, installed before
the control plane and upgraded on its own cadence — CRDs and the control-plane schema roll
independently.

**Postgres is not bundled.** It is the sole store of record and you point the chart at one you run
(`controlPlane.database.existingSecret`, or a dev-only inline DSN). NATS is the only bundled stateful
component: single-replica by default, HA behind a values toggle.

## Prerequisites

- Kubernetes **v1.29+** (the chart enforces `kubeVersion >= 1.29.0`), `kubectl`, and **Helm 3.12+**
- Cluster-admin for the install (CRDs + namespaced RBAC)
- A named **StorageClass** for the JetStream PVC
- A **Postgres** database (the store of record — not bundled)
- A **system default model** (`modelConfig.default.model` — install aborts without it)
- An isolation runtime (**gVisor** recommended)

## Install

```bash
helm repo add ksquad https://charts.k8squad.io
helm repo update

# CRDs first — the standalone k8squad-crds chart
helm upgrade --install k8squad-crds ksquad/k8squad-crds \
  --namespace k8squad-crds --create-namespace --wait

# Secrets: Postgres DSN + one-time bootstrap admin (password never inline in values)
kubectl create namespace ksquad-system
kubectl -n ksquad-system create secret generic ksquad-database \
  --from-literal=dsn='postgres://user:password@your-postgres:5432/ksquad'
kubectl -n ksquad-system create secret generic ksquad-bootstrap-admin \
  --from-literal=password='<choose-a-one-time-bootstrap-password>'

# Control plane
helm upgrade --install ksquad ksquad/k8squad \
  --namespace ksquad-system \
  --set modelConfig.default.model=claude-sonnet-4 \
  --set controlPlane.enabled=true \
  --set controlPlane.database.existingSecret=ksquad-database \
  --set controlPlane.nats.persistence.storageClassName=fast-ssd \
  --set exposure.gateway.enabled=true \
  --set exposure.gateway.gatewayClassName=cilium \
  --set exposure.gateway.hostnames.console=ksquad.example.com \
  --wait
```

Omit the three `exposure.*` flags for a ClusterIP-only install (reach the console via
`kubectl -n ksquad-system port-forward svc/ksquad-console 8080:80`).

Then confirm the control plane is healthy:

```bash
kubectl -n ksquad-system get pods
kubectl -n ksquad-system rollout status deploy/ksquad-apiserver
```

## Networking & exposure

**The chart creates exposure; it does not assume it.** There is one knob:
`exposure.gateway.enabled`.

| Setting | What it renders | When to use |
|------|-----------------|-------------|
| `exposure.gateway.enabled=false` (default) | `Service` only (reach via `port-forward`) | The zero-dependency path — always brings the stack up, even on a bare cluster. |
| `exposure.gateway.enabled=true` | `Gateway` + `HTTPRoute` | **Preferred production path.** Full control over the SSE stream timeout. Requires `exposure.gateway.gatewayClassName`. |

Key rules:

- **`gatewayClassName` is required when the Gateway is enabled and is never hardcoded.** cilium,
  envoy, istio, and traefik are all valid. The chart *references* an operator-provided `GatewayClass`;
  it never creates one.
- **The apiserver route must preserve the SSE stream** — no response buffering and no idle timeout that
  would kill a long-lived progress stream. Gateway API is the primitive because its `HTTPRoute` timeout
  semantics express this portably. ClusterIP-only installs do **not** give the same portable
  SSE-timeout guarantee — an honest trade, surfaced here, not hidden.
- **The chart pre-flights the Gateway install.** An enabled Gateway with no matching `GatewayClass`
  **fails fast with a clear message**, not a dangling route.

Listener hostnames (`hostnames.console`, `hostnames.apiserver`), TLS cert secret refs, and
HTTPS-redirect are all exposed as values, so you wire your own DNS and cert story without editing
templates. Leave both hostnames empty to expose by IP — the console answers at `/` and the apiserver
SSE endpoint under `/api`.

## Storage

**No PVC ever silently binds to the cluster-default StorageClass** — that is treated as a
**misconfiguration that fails fast**, not a silent fallback:

- The bundled NATS/JetStream PVC requires `controlPlane.nats.persistence.storageClassName` whenever
  NATS is enabled (the default) — the install aborts without it.
- Per-project workspace PVCs take their class from each Project's `spec.workspacePVC.class` and their
  size from `spec.workspacePVC.size`.
- Postgres storage is your concern — you run it, so you size it.

- Access mode is **`RWO` by default**, with **`RWX` optional** for workspaces that need it.
- Storage-class-dependent behaviors (RWX, volume expansion, snapshots) are documented so you can
  pre-flight your class before install.

## Sandbox runtime

Agent code runs in sandboxes under a **RuntimeClass**. gVisor is the recommended default:

- If **gVisor** is present, KSquad uses it by default.
- If it isn't, KSquad falls back to a **clearly-flagged** runtime so you always know what isolation
  you're getting.
- Some capabilities (for example, running a live Docker daemon inside a sandbox) may require a **Kata**
  RuntimeClass; KSquad validates these requirements and fails closed rather than silently
  under-isolating.

See [Configuration → warm pool](/docs/operator-guide/configuration/#warm-pool) for pre-warming and sizing.

## Air-gapped / offline

KSquad is **mirror-friendly by design**: image versions are pinned and pre-pulled onto nodes. For an
air-gapped install:

- mirror the `ghcr.io/ksquad/*` images (the project registry is public) into your internal registry;
- point the chart at your registry via image-override values;
- the local auth store means the **≤4h install has no hard dependency on an external IdP** — you can
  bring up the full stack, including login, entirely offline.

## First-run admin

The chart ships **no baked-in default password** and never generates one. Seeding the first admin is
opt-in: create a Secret holding a password of your choice and enable
`controlPlane.apiserver.bootstrapAdmin` (`username` + `existingSecret`) — the apiserver seeds that one
user once. Disable the seed after first login so it can't re-seed on upgrade. Full detail in
[RBAC → first-run admin](/docs/operator-guide/rbac/#first-run-admin-bootstrap).

## Uninstall

```bash
helm uninstall ksquad -n ksquad-system
```

CRDs live in the separate `k8squad-crds` release (with a resource policy that keeps CRs alive through
control-plane uninstalls) and PVCs are retained — you don't lose the coordination and knowledge
records. Remove the CRD release explicitly (`helm uninstall k8squad-crds -n k8squad-crds`) only if you
intend a full teardown.
