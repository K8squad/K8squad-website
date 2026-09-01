---
title: Install & exposure
description: Install KSquad with Helm, wire networking with Gateway API, name your StorageClass, choose a sandbox runtime, and support air-gapped clusters.
sidebar_position: 1
---

# Install & exposure

KSquad installs with **two Helm charts**: a small `k8squad-crds` chart that owns the `ksquad.io`
CRDs, installed first, then the control-plane chart. This page covers what they bring up, the CRD
lifecycle, the two decisions the chart won't guess for you (exposure and storage), the sandbox
runtime, and air-gapped installs.

## What an install brings up

Two charts deploy into `ksquad-system`:

- **`k8squad-crds`** — the eleven `ksquad.io` CRDs, in their own chart so they can be upgraded
  independently of the control plane and are never removed by a control-plane uninstall (see
  [CRD lifecycle & upgrades](#crd-lifecycle--upgrades)).
- **`ksquad`** — the control plane:
  - the **operator** (controllers for every CRD)
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

Install the CRD chart first, then the control plane, into the same namespace.

```bash
helm repo add ksquad https://charts.k8squad.io
helm repo update

# 1. CRDs (their own chart, installed first)
helm install k8squad-crds ksquad/k8squad-crds \
  --namespace ksquad-system --create-namespace --wait

# 2. Control plane
helm install ksquad ksquad/k8squad \
  --namespace ksquad-system \
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

## CRD lifecycle & upgrades

KSquad delivers its `ksquad.io` CRDs in a **dedicated `k8squad-crds` chart**, separate from the
control-plane chart. This is deliberate: Helm's control-plane release owns **zero** CRDs, so the CRD
schema has its own upgrade lifecycle and can never be dropped by a control-plane uninstall.

**Why a separate chart**

- **Upgrades actually propagate.** Because the CRDs are ordinary templated resources in the
  `k8squad-crds` release, `helm upgrade k8squad-crds` reconciles their schema (new fields, versions,
  validation rules) via Helm's three-way merge — no hand-run `kubectl apply`.
- **Your resources survive uninstall.** Each CRD carries `helm.sh/resource-policy: keep`, so a
  `helm uninstall` (of either chart) never deletes the CRDs or the `Project`/`Team`/`Run`/… custom
  resources you created.

**Upgrade order — CRDs first, always**

```bash
helm repo update
helm upgrade k8squad-crds ksquad/k8squad-crds --wait   # 1. CRD schema first
helm upgrade ksquad       ksquad/k8squad                # 2. then the control plane
```

The control-plane chart declares the minimum CRD schema it needs via the
`k8squad.io/min-crds-version` annotation. **Always move the CRD chart to a version ≥ that minimum
before upgrading the control plane.** A newer `k8squad-crds` chart is always safe ahead of the control
plane — CRD changes within a major version are additive-only (see the versioning policy below).

**Breaking CRD changes**

Within the pre-1.0 `v1alpha1` API, CRD changes are **additive-only** and need no migration. A genuinely
breaking change ships a **new served API version** alongside the old one with a conversion path, and a
per-release migration notice — never an in-place schema shrink that would reject your existing
resources. Full policy and the per-release notice template:
[CRD upgrade & migration guide](https://github.com/K8squad/k8squad/blob/main/docs/crd-upgrade-migration.md).

**Migrating an existing single-chart install**

Earlier KSquad releases bundled the CRDs inside the control-plane chart. Because those CRDs were already
annotated to be retained, adopting the separate chart is data-safe: install `k8squad-crds` (it adopts
the existing CRDs in place), then continue upgrading both charts as above. Your custom resources are
untouched throughout. The exact adopt-in one-liner ships in the `k8squad-crds` chart notes.

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

Uninstall the control plane; the CRD chart is a separate release:

```bash
helm uninstall ksquad -n ksquad-system
# CRDs are a separate release — removing them is a deliberate, separate step:
# helm uninstall k8squad-crds -n ksquad-system
```

CRDs, your custom resources, and PVCs are **retained by default** so you don't lose the coordination and
knowledge records — the CRDs via `helm.sh/resource-policy: keep`, so even
`helm uninstall k8squad-crds` leaves the `Project`/`Team`/`Run`/… objects in place. Delete the CRDs and
PVCs explicitly only if you intend a full teardown (removing a CRD cascades a delete of every custom
resource of that kind cluster-wide).
