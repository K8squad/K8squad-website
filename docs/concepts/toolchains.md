---
title: Toolchains (Toolchain)
description: A Toolchain is a versioned, digest-pinned CLI/tool pack staged into Run sandboxes as init containers — and, in the cluster catalog, the only place Kubernetes RBAC authority originates.
sidebar:
  order: 6
---

# Toolchains

**CRD:** `Toolchain` (`ksquad.io/v1alpha1`)

A **Toolchain** is a versioned pack of tools — `gh`, `kubectl`, `go`, `node`, `dtctl`, `helm`, or
your own long-tail binaries — that [Skills](./skills) can require via `requires.toolchains` entries
like `gh@2.62`. At Run time the operator stages each resolved pack as an **init container** onto a
shared volume mounted read-only, with `PATH` pointing at it: the binary is present *before* the agent
runtime starts, and it costs nothing once the Run is running (languages are files).

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Toolchain
metadata:
  name: kubectl
  namespace: ksquad-system        # cluster catalog; a team namespace = override
spec:
  versions:
    - version: "1.31"             # exact; skills pin name@version
      image: ghcr.io/k8squad/toolchains/kubectl:1.31@sha256:…
      provides: [kubectl]         # tool names staged onto PATH
  rbac:
    scope: namespace              # namespace (default) | cluster
    rules:                        # standard rbacv1.PolicyRule list
      - apiGroups: [""]
        resources: ["pods", "services", "configmaps", "events"]
        verbs: ["get", "list", "watch"]
```

Every version's image is **digest-pinned** — `tag@sha256:…` is enforced at admission (the tag is for
humans; only the digest is used for pulling). Toolchain images are one-tool-per-image and
distroless-style, staged read-only onto a pod-local volume under the Run's sandbox runtime class.

## The cluster catalog

Toolchains live either in the **cluster catalog** (`ksquad-system`, admin-authored) or in a team
namespace as an **override**. The Helm chart ships a curated seven-tool catalog — `kubectl`, `git`,
`gh`, `go`, `node`, `dtctl`, `helm` — rendered as catalog `Toolchain` objects when you enable it:

```bash
helm install ksquad ksquad/ksquad \
  --namespace ksquad-system --create-namespace \
  --set tools.defaultCatalog.enabled=true
```

Without the catalog (or your own `Toolchain` objects), Runs whose skills require `gh@2.62`,
`dtctl@1.0`, or `node@22` **fail admission** with an actionable message naming the demanding skill
and what the catalog actually carries — nothing stages silently.

## The RBAC trust boundary

The rule that makes the catalog safe:

> **Kubernetes RBAC authority originates only from cluster-catalog Toolchains.**

Concretely:

- A team-namespace Toolchain **without** an `rbac` block is admitted freely — the BYO long-tail path
  (`jq`, custom CLIs). It stages a binary and grants **no** Kubernetes permissions at all.
- A team-namespace Toolchain **with** an `rbac` block is admitted only as a *narrowing override* of
  the same-named catalog entry: every rule must be a subset and the scope must stay `namespace`.
  Widening is rejected with a diff-style message. A team namespace can never be the *origin* of
  Kubernetes authority.
- `scope: cluster` is admitted only from the catalog **and** only when the operator Helm value
  `tools.rbac.clusterScopeEnabled=true` is set.

## What a Run actually gets

At assembly, the operator resolves each skill's `name@version` refs (team-ns override first, then the
catalog), **unions** the honored RBAC rules across all resolved toolchains, and renders **one per-Run
`Role`** (`ksquad-run-<run-name>`) bound to the squad's service account — owner-referenced to the Run
so it is garbage-collected when the Run completes. Two consequences worth internalizing:

- `kubectl auth can-i --as=system:serviceaccount:<team>:ksquad-agent` returns permissions **only
  while a Run requiring the toolchain is live**. The baseline team Role stays empty.
- The union is recorded verbatim in the Run's
  [capability manifest](./runs#the-capability-manifest), so "which Run got which permissions through
  which toolchain" is answerable after the fact.

Version conflicts fail closed up front: two skills pinning `node@22` and `node@20` in one Run is an
admission rejection, not a silent latest-wins.

## Related

- [Skills](./skills) — `requires.toolchains` is how a skill demands a pack.
- [MCP Servers](./mcp-servers) — the other half of the capability plane.
- [Runs](./runs) — assembly, the per-Run Role, and the capability manifest.
