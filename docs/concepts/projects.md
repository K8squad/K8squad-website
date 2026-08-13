---
title: Projects (Project)
description: A Project is a repo plus a workspace the squad works against — with source-control sync, an egress policy, and shared goals.
sidebar_position: 5
---

# Projects

**CRD:** `Project` (`ksquad.io/v1alpha1`)

A **Project** is a **repo plus a workspace** that a squad works against. It's the unit that connects a
squad to real source code, and it's also the **authorization boundary** for human access (users are
granted access *per Project*).

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Project
metadata:
  name: payments-api
  namespace: ksquad-system
spec:
  repo:
    url: https://github.com/acme/payments-api.git
    ref: main
    sync:
      provider: github
      webhookSecretRef: payments-webhook
      reflectOutbound: true       # mirror KSquad-produced issues/PRs back to the provider
  workspacePVC:
    size: 20Gi
    storageClassName: fast-ssd
  egressPolicyRef: payments-egress
  goals: "Ship the open backlog; keep CI green; no breaking API changes without an ADR."
  contextBudget: 200000            # token budget folded into agent context
```

## What a Project carries

- **`repo`** — the Git repository (URL, ref, and auth), plus a **`sync`** block that configures
  source-control integration: which provider, the webhook secret, and whether KSquad reflects its own
  outputs (issues, PRs) back to the provider.
- **`workspacePVC`** — the persistent workspace (size and storage class). KSquad **never assumes the
  cluster default StorageClass**; you name it explicitly.
- **`egressPolicyRef`** — the NetworkPolicy governing what the project's Runs may reach.
- **`goals`** — free-form intent that's folded into agent context so agents understand what "done"
  means for this project.
- **`contextBudget`** — a token budget for the context envelope handed to agents.

## What reconciliation does

The **Project reconciler** provisions the workspace PVC, bootstraps repo sync, and applies the
project's NetworkPolicy. A separate **repo-sync reconciler** mirrors source-control state (issues, PRs,
check runs) so the squad works against a live view of the repo.

## Source-control sync

KSquad integrates with your source-control provider through a **provider seam** — GitHub is the v1
provider; others drop in behind the same interface. Sync is bidirectional in spirit: KSquad reads the
repo's issues and PRs into its coordination view, and (when `reflectOutbound` is on) reflects the
work it produces back to the provider.

## Workspaces and concurrency

Each project has a workspace PVC (`RWO` by default, `RWX` optional). Runs get isolated, per-principal
working directories within it, so concurrent Runs don't clobber each other. Storage-class-dependent
behaviors (RWX, expansion, snapshots) are documented so you can pre-flight your class.

## Human access is per-Project

A user's access level (`viewer`, `contributor`, `maintainer`) is held **per Project membership**. The
same person can be a `maintainer` on one project and a `viewer` on another. See
[RBAC & access levels](../operator-guide/rbac).

## Related

- [Squads](./squads) — a squad owns one or more projects.
- [Runs](./runs) — a Run targets a project.
- [RBAC & access levels](../operator-guide/rbac) — project-scoped authorization.
