---
title: Projects (Project)
description: A Project is a repo plus a workspace the squad works against — with source-control sync, an egress policy, and shared goals.
sidebar:
  order: 9
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
    auth:
      credentialSecretRef: payments-gh-token   # BYO Secret for private-repo clone/sync
    sync:
      provider: github
      webhookSecretRef: payments-webhook
      reflectOutbound: true       # mirror KSquad-produced issues/PRs back to the provider
      pollIntervalSeconds: 300    # fallback poll when webhooks aren't reachable
    automation:
      issueTriage:                  # auto-triage newly opened issues (dispatch a triage agent)
        enabled: true
        triageAgentId: triage-1
      ciFailure:                    # mint a triage ticket on failed CI check runs
        enabled: true
        agentId: ci-triage-1
    reviewAutomation:               # auto-review PRs
      enabled: true
      reviewerAgentId: reviewer-1
      scope: team_authored          # team_authored | all
      trigger: on_new_commits       # on_open | on_new_commits
  workspacePVC:
    size: 20Gi
    storageClassName: fast-ssd
  egressPolicyRef: payments-egress
  goals: "Ship the open backlog; keep CI green; no breaking API changes without an ADR."
  contextBudget: 200000            # token budget folded into agent context
```

## What a Project carries

- **`repo`** — the Git repository: `url` and `ref` (required: `url`), **`auth`**
  (`credentialSecretRef` — the BYO Secret used to clone/sync a private repo), and a **`sync`** block
  that configures source-control integration: `provider`, `webhookSecretRef`, `reflectOutbound`
  (whether KSquad reflects its own outputs back to the provider), plus `issueSync` and `mirror`
  (which mirror surfaces are on: `issues`, `pullRequests`, `checkRuns`, …) and
  `pollIntervalSeconds` as a fallback poll when webhooks aren't reachable.
- **`repo.automation`** — human-enabled, system-executed automations: `issueTriage` (mint an internal
  ticket and dispatch a configured triage agent for each newly opened issue the mirror captures) and
  `ciFailure` (mint a triage ticket and dispatch a configured agent when a mirrored CI check run
  finishes with a configured conclusion on an in-scope ref). A human enabling the policy is the
  authorizing act; disabled/absent means today's manual behavior.
- **`repo.reviewAutomation`** — automatic PR review: `enabled`, `reviewerAgentId`, `scope`
  (`team_authored` — only PRs opened by team agents, the default — or `all`), and `trigger`
  (`on_open` or `on_new_commits`, the latter re-reviewing when the mirrored head SHA changes).
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
[RBAC & access levels](/docs/operator-guide/rbac/).

## Related

- [Squads](/docs/concepts/squads/) — a squad owns one or more projects.
- [Runs](/docs/concepts/runs/) — a Run targets a project.
- [RBAC & access levels](/docs/operator-guide/rbac/) — project-scoped authorization.
