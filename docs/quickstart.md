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

- A Kubernetes cluster, **v1.28+**, and `kubectl` configured to reach it.
- **Helm 3.12+**.
- Cluster-admin (KSquad installs CRDs and namespaced RBAC).
- A **StorageClass** you can name (KSquad never assumes the cluster default).
- **~2 vCPU / 4 GiB** free for the control plane, plus headroom for sandboxes.
- A container isolation runtime — **gVisor** is the recommended default. If it isn't installed, KSquad
  falls back to a clearly-flagged runtime; see the [Operator Guide](./operator-guide/install#sandbox-runtime).
- One AI-agent subscription to connect (this guide uses **Claude**).

> **Air-gapped?** KSquad is mirror-friendly — pinned image versions and node pre-pull. See
> [Operator Guide → Air-gapped installs](./operator-guide/install#air-gapped--offline).

## 1. Install the control plane (≈5 min)

Add the chart repository and install into a dedicated namespace. You must name a `storageClassName`
and pick an exposure mode.

```bash
helm repo add ksquad https://k8squad.io/charts
helm repo update

helm install ksquad ksquad/ksquad \
  --namespace ksquad-system --create-namespace \
  --set global.storageClassName=<your-storage-class> \
  --set exposure.mode=clusterip
```

`exposure.mode=clusterip` is the zero-dependency path — it brings the whole stack up and you reach the
console with `kubectl port-forward`. For production you'll switch to `gateway` (Gateway API) or
`ingress`; see [Networking & exposure](./operator-guide/install#networking--exposure).

One install brings up: the **operator**, **apiserver**, **memory service**, **console**, a bundled
**Postgres** (CNPG), and the **NATS/JetStream** event bus.

Wait for the control plane to be ready:

```bash
kubectl -n ksquad-system rollout status deploy/ksquad-operator
kubectl -n ksquad-system rollout status deploy/ksquad-apiserver
kubectl -n ksquad-system get pods
```

## 2. Log in to the console (≈2 min)

KSquad ships **no default password**. On first install the chart generates a random admin password
into a Secret and prints the retrieval command in the install notes. Retrieve it:

```bash
kubectl -n ksquad-system get secret ksquad-bootstrap-admin \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

Port-forward the console and open it:

```bash
kubectl -n ksquad-system port-forward svc/ksquad-console 8443:443
# open https://localhost:8443
```

Log in as `admin` with the retrieved password. You'll be **required to set a new password** before you
can do anything else — the install-time password is a one-time bootstrap value, not a durable
credential.

## 3. Connect a credential (≈3 min)

Agents authenticate with **their own** per-user credential — KSquad never holds a shared master key.

In the console, open **Credentials** and click **Connect Claude**. Complete the browser OAuth flow
once. KSquad stores the resulting tokens in a per-user Kubernetes Secret and a controller keeps the
access token fresh automatically — you won't rotate it by hand.

> Prefer the CLI? Run `ksquad auth login` for the same one-time OAuth flow.

Prefer a local model instead? See [Bring your own model endpoint](./operator-guide/credentials#byo-model-endpoint).

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
    storageClassName: <your-storage-class>
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
- Every step is in the **audit trail** and available as OpenTelemetry.

## Next steps

- [Core Concepts](./concepts) — understand Squads, Agents, Roles, Skills, Projects, and Runs in depth.
- [Author Guide](./author-guide) — compose richer squads and manage work items.
- [Operator Guide](./operator-guide) — production install, RBAC, credentials, and settings.
- [Observability](./observability) — export telemetry with `OTelConfig`.
- [Troubleshooting](./troubleshooting) — if a Run gets stuck or the install fails.
