---
title: Add a toolchain
description: A task walkthrough — make a new CLI tool available to your squads by defining a Toolchain, pinning name@version in a skill, and confirming it stages at Run time.
sidebar_position: 3
---

# Add a toolchain

You need a tool your squads don't have yet — a different `kubectl` version, a
CLI the default catalog doesn't ship, or your own internal binary. This page
walks you through making it available end to end.

For the *what* and *why* behind toolchains — staging, the RBAC trust boundary,
the per-Run Role — read the [Toolchains concept page](/docs/concepts/toolchains/).
This is the *how-do-I* task.

## Before you start

Check whether you actually need a new toolchain. When
`tools.defaultCatalog.enabled=true`, the chart already ships a curated set:

`kubectl` · `git` · `gh` · `go` · `node` · `dtctl` · `helm` · `python` ·
`docker-cli` · `uv` · `jq` · `yq` · `curl` · `make`

If your tool is in that list, just pin it in your skill's `requires.toolchains`
(jump to [step 3](#3-let-a-skill-require-it)) — there's nothing to add.

## 1. Decide where it lives

| You want to… | Add it as… | Where |
|---|---|---|
| Make a tool available cluster-wide, or grant it Kubernetes RBAC | a **cluster-catalog** Toolchain | admin action — a value in the operator's Helm `tools.defaultCatalog.entries` (or a `Toolchain` in `ksquad-system`) |
| Give *your team* a tool, or pin a version the catalog lacks | a **team BYO** Toolchain | a `Toolchain` object in your team namespace |

The distinction is a **trust boundary**, not just tidiness: Kubernetes RBAC
authority can originate *only* from the cluster catalog. A team-namespace
Toolchain may grant no new API access — it can only stage a binary, or *narrow*
an existing catalog entry of the same name. See
[The RBAC trust boundary](/docs/concepts/toolchains/#the-rbac-trust-boundary).

Most BYO tools (a linter, a custom CLI) need no Kubernetes access at all, so the
team path is self-service and unblocked.

## 2. Write the Toolchain

The common case — a tool staged onto `PATH` with no Kubernetes grants:

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Toolchain
metadata:
  name: kustomize                      # the "name" half of name@version
  namespace: bmad-squad                # your team namespace
spec:
  versions:
    - version: "5.4"                   # the "version" half — skills pin this exactly
      image: ghcr.io/acme/toolchains/kustomize@sha256:<digest>
      provides: [kustomize]            # binaries staged onto PATH
```

Two things the platform enforces at admission:

- **`image` must be digest-pinned** (`@sha256:…`). A moving tag is rejected — a
  Run records the resolved digest so an image can never change under a live Run.
- **`spec.versions` needs at least one entry**, each with a non-empty `version`
  and `image`; versions must be unique within the toolchain.

**Only if the tool calls the Kubernetes API** (like `kubectl`) add an `rbac`
block — and only in the cluster catalog. Keep it least-privilege; wildcards
(`"*"`) are rejected:

```yaml
  rbac:
    scope: namespace                   # namespace (default) | cluster
    rules:
      - apiGroups: [""]
        resources: [pods, services, configmaps, events]
        verbs: [get, list, watch]
```

`scope: cluster` is admitted only from the catalog and only when the operator
has `tools.rbac.clusterScopeEnabled=true` — otherwise it's rejected, fail-closed.

Apply it:

```bash
kubectl apply -f kustomize-toolchain.yaml -n bmad-squad
kubectl get toolchains -n bmad-squad          # shortName: tc
```

## 3. Let a skill require it

A toolchain does nothing until a skill asks for it. Add the exact `name@version`
to the skill's `requires.toolchains`:

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Skill
metadata:
  name: render-manifests
  namespace: bmad-squad
spec:
  # …
  requires:
    toolchains: [kustomize@5.4]        # must match the Toolchain exactly
```

The `name@version` string must match a `Toolchain`'s `metadata.name` and one of
its `spec.versions[].version` **exactly**. A typo, a missing version, or two
skills in one Run asking for two different versions of the same tool → the Run
is **rejected at admission** with a message naming the demanding skill and what
the catalog carries. Nothing stages silently.

## 4. Confirm it works

Run a squad whose skill requires the toolchain, then check:

- **The Run is admitted** — resolution succeeded and the image staged onto
  `PATH`. The Run's [capability manifest](/docs/concepts/runs/#the-capability-manifest)
  records the resolved image and any granted RBAC.
- **If you declared RBAC**, the intended API calls succeed inside the Run and
  nothing broader does. Permissions exist *only while the Run is live*:

  ```bash
  kubectl auth can-i list pods \
    --as=system:serviceaccount:bmad-squad:ksquad-agent -n bmad-squad
  ```

- **The failure path is honest** — point a skill at `kustomize@9.9` (a version
  you never defined) and confirm the Run is rejected up front, not mid-flight.

## 5. Promote it (optional)

If a BYO tool proves broadly useful, ask a platform admin to promote it into the
**cluster catalog** — a change to the operator's Helm
`tools.defaultCatalog.entries`. Contributors adding a toolchain to the shared
catalog should follow the
[contributor guide](https://github.com/K8squad/k8squad-skills/blob/main/docs/adding-a-toolchain.md)
in the skills repo, including the PR checklist (digest pinning, SHA-pinned git
refs, least-privilege RBAC, CI gates).

## Related

- [Toolchains concept](/docs/concepts/toolchains/) — staging, catalog, RBAC boundary
- [Skills concept](/docs/concepts/skills/) — `requires.toolchains`
- [Compose CRDs](/docs/author-guide/compose-crds/) — the full composition order
