---
title: Install & exposure
description: Install KSquad with Helm, wire networking with Gateway API, name your StorageClass, choose a sandbox runtime, and support air-gapped clusters.
sidebar_position: 1
---

# Install & exposure

KSquad installs with a **single `helm install`**. This page covers what that brings up, the two
decisions the chart won't guess for you (exposure and storage), the sandbox runtime, and air-gapped
installs.

## What one install brings up

One `helm install` deploys `ksquad-system`:

- **CRDs** and the **operator** (controllers for every CRD)
- the **apiserver** (coordination record, audit, SSE, source-control webhooks, and the built-in auth +
  RBAC middleware)
- the **memory service** (the knowledge record)
- the **console**
- **Postgres** (bundled via CNPG — the sole store of record)
- **NATS/JetStream** (the plugin event bus — event flow only, no state of record)

Postgres and NATS are the only two stateful dependencies, both boring Helm subcharts with
single-replica defaults and HA behind a values toggle. Everything else is stateless.

## Prerequisites

- Kubernetes **v1.28+**, `kubectl`, and **Helm 3.12+**
- Cluster-admin for the install (CRDs + namespaced RBAC)
- A named **StorageClass**
- An isolation runtime (**gVisor** recommended)

## Install

```bash
helm repo add ksquad https://charts.ksquad.io
helm repo update

helm install ksquad ksquad/ksquad \
  --namespace ksquad-system --create-namespace \
  --set global.storageClassName=fast-ssd \
  --set exposure.mode=gateway \
  --set exposure.gateway.gatewayClassName=cilium \
  --set exposure.gateway.hostname=ksquad.example.com
```

Then confirm the control plane is healthy:

```bash
kubectl -n ksquad-system get pods
kubectl -n ksquad-system rollout status deploy/ksquad-apiserver
```

## Networking & exposure

**The chart creates exposure; it does not assume it.** Pick a mode with `exposure.mode`:

| Mode | What it renders | When to use |
|------|-----------------|-------------|
| `gateway` | `Gateway` + `HTTPRoute` | **Preferred production path.** Full control over the SSE stream timeout. Requires a `gatewayClassName`. |
| `ingress` | A plain `Ingress` with SSE-safe annotations | A graceful degrade for clusters that have an Ingress controller but no Gateway API. |
| `clusterip` | `Service` only (reach via `port-forward`) | The zero-dependency path — always brings the stack up, even on a bare cluster. |

Key rules:

- **`gatewayClassName` is required in `gateway` mode and is never hardcoded.** cilium, envoy, istio,
  and traefik are all valid. The chart *references* an operator-provided `GatewayClass`; it never
  creates one.
- **The apiserver route must preserve the SSE stream** — no response buffering and no idle timeout that
  would kill a long-lived progress stream. Gateway API is the primitive because its `HTTPRoute` timeout
  semantics express this portably. `ingress` and `clusterip` do **not** give the same portable
  SSE-timeout guarantee — an honest trade, surfaced here, not hidden.
- **The chart pre-flights the selected mode.** A `gateway` install with no matching `GatewayClass`
  **fails fast with a clear message**, not a dangling route.

Listener hostnames, TLS cert secret refs, and HTTPS-redirect are all exposed as values, so you wire
your own DNS and cert story without editing templates.

## Storage

**Every PVC the install renders takes its `storageClassName` from values** — the bundled Postgres and
every per-project workspace PVC. Relying on the cluster-default StorageClass is treated as a
**misconfiguration that fails the install fast**, not a silent fallback.

- Access mode is **`RWO` by default**, with **`RWX` optional** for workspaces that need it.
- Storage-class-dependent behaviors (RWX, volume expansion, snapshots) are documented so you can
  pre-flight your class before install.

```bash
--set global.storageClassName=fast-ssd
--set postgres.storageClassName=fast-ssd      # override per-component if needed
```

## Sandbox runtime

Agent code runs in sandboxes under a **RuntimeClass**. gVisor is the recommended default:

- If **gVisor** is present, KSquad uses it by default.
- If it isn't, KSquad falls back to a **clearly-flagged** runtime so you always know what isolation
  you're getting.
- Some capabilities (for example, running a live Docker daemon inside a sandbox) may require a **Kata**
  RuntimeClass; KSquad validates these requirements and fails closed rather than silently
  under-isolating.

See [Configuration → warm pool](./configuration#warm-pool) for pre-warming and sizing.

## Air-gapped / offline

KSquad is **mirror-friendly by design**: image versions are pinned and pre-pulled onto nodes. For an
air-gapped install:

- mirror the `ghcr.io/ksquad/*` images (the project registry is public) into your internal registry;
- point the chart at your registry via image-override values;
- the local auth store means the **≤4h install has no hard dependency on an external IdP** — you can
  bring up the full stack, including login, entirely offline.

## First-run admin

The chart ships **no baked-in default password**. On install it generates a random admin password into
the `ksquad-bootstrap-admin` Secret and prints the retrieval command in `NOTES.txt`. You log in once
and are **forced to rotate** before doing anything else. Full detail in [RBAC → first-run admin](./rbac#first-run-admin-bootstrap).

## Uninstall

```bash
helm uninstall ksquad -n ksquad-system
```

CRDs and PVCs are retained by default so you don't lose the coordination and knowledge records. Remove
them explicitly if you intend a full teardown.
