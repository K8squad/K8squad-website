---
title: Squads (Team)
description: A Squad is the tenancy boundary in KSquad — a crew of agents and the projects they own, mapped to a Kubernetes namespace.
sidebar_position: 1
---

# Squads

**CRD:** `Team` (`ksquad.io/v1alpha1`)

A **Squad** is a crew of agents working a shared backlog. It is the top-level unit you organize work
around, and it is KSquad's **tenancy boundary**: each squad maps to a Kubernetes namespace with its
own RBAC, NetworkPolicy, and resource quota. Work, isolation, and access control all resolve at the
squad level.

> **Naming.** In the console and docs we say "Squad" for the human concept; the underlying CRD is
> `Team`. They are the same thing.

## What a Squad owns

A `Team` groups two things:

- **Agents** — the members of the crew (`spec.agents`).
- **Projects** — the repos and workspaces the crew works against (`spec.projects`).

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Team
metadata:
  name: payments-squad
  namespace: ksquad-system
spec:
  projects: [payments-api, payments-web]
  agents: [dev-1, dev-2, reviewer-1]
```

## What reconciliation does

When you create or change a `Team`, the **Team reconciler** ensures the squad's runtime footprint:

- a **namespace** for the squad (the tenancy boundary);
- **RBAC** scoping what runs inside it;
- a **NetworkPolicy** governing egress;
- a **resource quota** so one squad can't starve the cluster.

Because a squad *is* a namespace, isolation between squads is enforced by Kubernetes itself — not by
application-level checks that could be bypassed.

## Why the tenancy boundary matters

Agents run untrusted code. Anchoring the boundary to a namespace means:

- one squad's sandboxes **cannot reach** another squad's workloads or secrets;
- egress is controlled per squad, so a compromised agent can't phone home to an endpoint it wasn't
  granted;
- resource pressure and blast radius are contained.

## Human access to a Squad

Access is granted **per Project**, not per Squad — a user can be a `viewer` on one project and a
`maintainer` on another. See [RBAC & access levels](../operator-guide/rbac) for the full model. The
squad is the *operational* boundary; the project is the *authorization* boundary.

## Related

- [Agents](./agents) — the members of a squad.
- [Projects](./projects) — what a squad works against.
- [Runs](./runs) — how a squad does work.
