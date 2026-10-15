---
title: Quickstart
description: Go from an empty Kubernetes cluster to your first running squad in under 30 minutes.
sidebar_position: 1
---

# Quickstart

This guide takes you from an empty cluster to a running squad in **under 30 minutes**. You'll install
KSquad, connect a credential, define a couple of agents, point them at a repo, and start your first
`Run`.

> **What you'll end up with:** a KSquad control plane in your cluster, one `Project` tracking a Git
> repo, a `Team` of two agents, and a completed `Run` you can inspect in the console.

## Prerequisites

- A Kubernetes cluster, **v1.29+** (the chart enforces `kubeVersion >= 1.29.0`), and `kubectl` configured to reach it.
- **Helm 3.12+**.
- Cluster-admin (KSquad installs CRDs and namespaced RBAC).
- A **StorageClass** you can name (KSquad never assumes the cluster default).
- A **Postgres** database KSquad can reach — it is the single store of record and is **not** bundled
  with the chart; you supply the DSN (see step 1).
- **~2 vCPU / 4 GiB** free for the control plane, plus headroom for sandboxes.
- A container isolation runtime — **gVisor** is the recommended default. If it isn't installed, KSquad
  falls back to a clearly-flagged runtime; see the [Operator Guide](/docs/operator-guide/install/#sandbox-runtime).
- One AI-agent subscription to connect (this guide uses **Claude**).

> **Air-gapped?** KSquad is mirror-friendly — pinned image versions and node pre-pull. See
> [Operator Guide → Air-gapped installs](/docs/operator-guide/install/#air-gapped--offline).

## 1. Install the control plane (≈5 min)

Add the chart repository. KSquad installs as **two charts**: the standalone `k8squad-crds` chart owns
the `ksquad.io` CRDs and must go on first; the `k8squad` chart brings the control plane. The install
additionally **requires** a system default model, a Postgres DSN Secret, and the NATS StorageClass —
the chart fails fast when any of them is missing.

```bash
helm repo add ksquad https://charts.k8squad.io
helm repo update

# 1a. CRDs first (cluster-scoped; kept on a separate release so it upgrades independently)
helm upgrade --install k8squad-crds ksquad/k8squad-crds \
  --namespace k8squad-crds --create-namespace --wait

# 1b. Secrets the control plane needs
kubectl create namespace ksquad-system
kubectl -n ksquad-system create secret generic ksquad-database \
  --from-literal=dsn='postgres://user:password@your-postgres:5432/ksquad'
kubectl -n ksquad-system create secret generic ksquad-bootstrap-admin \
  --from-literal=password='<choose-a-one-time-bootstrap-password>'

# 1c. Control plane
helm upgrade --install ksquad ksquad/k8squad \
  --namespace ksquad-system \
  --set modelConfig.default.model=claude-sonnet-4 \
  --set controlPlane.enabled=true \
  --set controlPlane.database.existingSecret=ksquad-database \
  --set controlPlane.nats.persistence.storageClassName=<your-storage-class> \
  --set controlPlane.apiserver.bootstrapAdmin.enabled=true \
  --set controlPlane.apiserver.bootstrapAdmin.username=admin \
  --set controlPlane.apiserver.bootstrapAdmin.existingSecret=ksquad-bootstrap-admin \
  --set tools.defaultCatalog.enabled=true \
  --wait
```

`modelConfig.default.model` is the **required** system default model — `helm install`/`upgrade` aborts
with a clear error when it is unset. `controlPlane.database.existingSecret` points at the Secret
holding your Postgres DSN (an inline dev DSN via `controlPlane.database.dsn` also exists but is
dev-only). `controlPlane.nats.persistence.storageClassName` names the StorageClass for the JetStream
PVC — KSquad never binds a PVC to the cluster-default class silently, so this key is required whenever
the bundled NATS is enabled.

With the Gateway exposure off (the default), every service is ClusterIP-only — the zero-dependency
path, and you reach the console with `kubectl port-forward`. For production you'll enable the
Gateway (Gateway API); see [Networking & exposure](/docs/operator-guide/install/#networking--exposure).

`tools.defaultCatalog.enabled=true` renders the curated [Toolchain](/docs/concepts/toolchains/) catalog
(`kubectl`, `git`, `gh`, `go`, `node`, `dtctl`, `helm`) that skills with `requires.toolchains` resolve
against — leave it off and Runs demanding a toolchain fail admission with an actionable message.

One install brings up: the **operator**, **apiserver**, **memory service**, **console**, and the
**NATS/JetStream** event bus. Postgres is **not** bundled — point the DSN at one you run (any
standard Postgres works; it is the sole store of record).

Wait for the control plane to be ready:

```bash
kubectl -n ksquad-system rollout status deploy/ksquad-operator
kubectl -n ksquad-system rollout status deploy/ksquad-apiserver
kubectl -n ksquad-system get pods
```

## 2. Log in to the console (≈2 min)

KSquad ships **no default password**. The bootstrap admin you configured in step 1 seeds exactly one
`admin` user from the Secret you created — the chart never generates or inlines a password. Retrieve
it:

```bash
kubectl -n ksquad-system get secret ksquad-bootstrap-admin \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

Port-forward the console and open it (the service listens on plain HTTP, port 80):

```bash
kubectl -n ksquad-system port-forward svc/ksquad-console 8080:80
# open http://localhost:8080
```

Log in as `admin` with that password. The bootstrap seed is a one-time value — after first login,
turn it off so it can't re-seed on upgrade:

```bash
helm upgrade ksquad ksquad/ksquad --namespace ksquad-system \
  --reuse-values \
  --set controlPlane.apiserver.bootstrapAdmin.enabled=false
```

## 3. Connect a credential (≈3 min)

Agents authenticate with **their own** per-user credential — KSquad never holds a shared master key.

In the console, open **Credentials** and click **Connect Claude**. Complete the browser OAuth flow
once. KSquad stores the resulting tokens in a per-user Kubernetes Secret and a controller keeps the
access token fresh automatically — you won't rotate it by hand.

Prefer a local model instead? See [Bring your own model endpoint](/docs/operator-guide/credentials/#byo-model-endpoint).

## 4. Create a Project (≈3 min)

A `Project` is a repo plus a workspace. Apply one with `kubectl`, or use the console's **New Project**
form.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Project
metadata:
  name: demo-app
  namespace: ksquad-system
spec:
  repo:
    url: https://github.com/your-org/demo-app.git
    ref: main
  workspacePVC:
    size: 10Gi
    class: <your-storage-class>
  goals: "Keep the test suite green and address the open backlog."
```

```bash
kubectl apply -f project.yaml
kubectl get project demo-app -n ksquad-system
```

## 5. Define agents and form a squad (≈8 min)

Each agent references a **runtime** (which coding CLI runs the work), a **role** (how it behaves), and
zero or more **skills** (what tools it may use). KSquad ships two runtimes and starter roles out of the
box.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata:
  name: dev-1
  namespace: ksquad-system
spec:
  runtimeRef: claude-code          # a bundled AgentRuntime
  roleRef: software-engineer       # a bundled Role
  skillRefs: [git, run-tests]
  credentialSecretRef: claude-oauth # the Secret created in step 3
  model: claude-opus-4-8
---
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata:
  name: reviewer-1
  namespace: ksquad-system
spec:
  runtimeRef: claude-code
  roleRef: code-reviewer
  skillRefs: [git]
  credentialSecretRef: claude-oauth
  model: claude-opus-4-8
```

Group them into a `Team` (your squad) that owns the project:

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Team
metadata:
  name: demo-squad
  namespace: ksquad-system
spec:
  projects: [demo-app]
  agents: [dev-1, reviewer-1]
```

```bash
kubectl apply -f agents.yaml -f team.yaml
```

The operator reconciles the `Team`: it ensures the squad's namespace, RBAC, NetworkPolicy, and quota,
validates each agent's credential and runtime, and publishes each agent's card.

## 6. Start your first Run (≈3 min)

A `Run` is a unit of squad work. Start one from the console's **Start Run** button, or apply:

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Run
metadata:
  name: green-tests-1
  namespace: ksquad-system
spec:
  teamRef: demo-squad
  projectRef: demo-app
  agents: [dev-1]
  inputs:
    task: "Run the test suite and fix the first failing test."
```

```bash
kubectl apply -f run.yaml
kubectl get run green-tests-1 -n ksquad-system -w
```

Watch the `phase` move `Pending → Claiming → Running`. In the console, open the run to see progress
**stream live** over SSE, then inspect the produced artifacts (diffs, logs, build output).

When it reaches `Succeeded`, you've run your first squad. 🎉

## What just happened

- The operator turned your CRDs into a reconciled, isolated workload.
- The `Run` **claimed a durable work item**, got a warm sandbox, and drove `dev-1` to completion — all
  crash-safe, because the coordination state lives in Postgres, not the pod.
- The Run's skills resolved against the **capability plane**: required [toolchains](/docs/concepts/toolchains/)
  staged as init containers, and any [MCP servers](/docs/concepts/mcp-servers/) wired into the runtime —
  with the resolved envelope recorded as the Run's capability manifest.
- Every step is in the **audit trail** and available as OpenTelemetry.

## Next steps

- [Core Concepts](/docs/concepts/) — Squads, Agents, Roles, Skills, MCP Servers, Toolchains, Projects, Runs.
- **Want a full 13-role squad instead of hand-rolled agents?** The repo ships a `kubectl apply`-able
  [BMAD example squad](https://github.com/K8squad/K8squad/blob/main/docs/getting-started-bmad.md) —
  CEO → PM/Architect/UX hierarchy, four default Skills, two MCP servers, in about ten minutes.
- [Author Guide](/docs/author-guide/) — compose richer squads and manage work items.
- [Operator Guide](/docs/operator-guide/) — production install, RBAC, credentials, and settings.
- [Observability](/docs/observability/) — export telemetry with `OTelConfig`.
- [Troubleshooting](/docs/troubleshooting/) — if a Run gets stuck or the install fails.
