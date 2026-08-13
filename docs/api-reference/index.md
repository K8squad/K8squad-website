---
title: API Reference
description: KSquad's API surface — the ksquad.io/v1alpha1 CRDs (auto-generated from Go types) and the apiserver's coordination, memory, and admin REST APIs.
sidebar_position: 6
---

# API Reference

KSquad exposes two API surfaces:

1. **CRDs** — the desired-state objects under **`ksquad.io/v1alpha1`**, reconciled by the operator.
2. **The apiserver REST/BFF APIs** — the durable coordination record, memory, source-control mirror,
   dashboards, search, and auth/admin.

> **Auto-generated.** The per-field CRD reference below is **generated from the Go API types** (the
> canonical source of truth). This page describes the *structure* of that reference and the stable
> object catalog; the field-level tables are produced by the docs build from the CRD OpenAPI schemas so
> they never drift from the code.

## CRD reference (`ksquad.io/v1alpha1`)

Each CRD's reference page is generated from its Go type and lists every spec/status field, its type,
whether it's required, defaults, and validation. The object catalog:

| Kind | Scope | Purpose | Concept page |
|------|-------|---------|--------------|
| `Team` | Namespaced | Squad = tenancy boundary (`projects[]`, `agents[]`, `namespaceStrategy`) | [Squads](../concepts/squads) |
| `Agent` | Namespaced | One agent (`runtimeRef`, `roleRef`, `skillRefs[]`, `credentialSecretRef`, `model`, `modelEndpointRef?`, `fallbackModel?`, `capabilityOverrides?`) | [Agents](../concepts/agents) |
| `AgentRuntime` | Namespaced | Coding-agent flavor + CLI version policy (`type`, `image`, `cliVersion`, `capabilities{docker,github,packageInstall}`) | [Agents](../concepts/agents#agentruntime--the-pluggable-coding-agent-flavor) |
| `Role` | Namespaced | Behavior profile (`promptRef`, `defaultSkills[]`, `runtimeClassHint`) | [Roles](../concepts/roles) |
| `Skill` | Namespaced | Granted capability (`source{inline\|git}`, `mcpToolRefs[]`, `permissions`, `requires{toolchains[],sidecars[]}`) | [Skills](../concepts/skills) |
| `Project` | Namespaced | Repo + workspace (`repo{url,ref,sync}`, `workspacePVC`, `egressPolicyRef`, `goals`, `contextBudget`) | [Projects](../concepts/projects) |
| `Run` | Namespaced | Unit of work — **spec:** `teamRef`, `projectRef`, `workItemRef`, `inputs`, `sandboxPolicy`, `agents[]`, `retryPolicy`; **status:** `phase`, `sandboxRef`, `claimedAt`, `conditions`, `artifactRefs` | [Runs](../concepts/runs) |
| `OTelConfig` | Namespaced | OTLP export config (per-signal `exporters{traces,metrics,logs}`) | [Observability](../observability) |

### Common metadata

- **`metadata.annotations[ksquad.io/created-by]`** — set by the apiserver at create time to the
  originating user; **immutable**, so a CRD's origin is always auditable.
- **Runs** additionally carry **`metadata.annotations[ksquad.io/initiated-by]`** — the human who
  triggered the Run (or a `system` sentinel for auto-retry/scheduled Runs).
- **`status.conditions`** and **`status.observedGeneration`** — every reconciled object reports these.

### What is *not* a CRD

Work items, comments, claims, artifacts, memory records, and users/memberships are **not CRDs** — they
are durable rows in Postgres behind the apiserver APIs. The `Run` CRD *references* a work item via
`workItemRef`; it never embeds it. See [The coordination record](../author-guide/work-items).

## Apiserver REST / BFF APIs

The apiserver exposes the durable record and platform operations. These are the surfaces the console
(and your integrations) use:

| Area | What it covers |
|------|----------------|
| **Coordination** | Work items, claims/leases, comments, artifacts, audit trail |
| **Runs & SSE** | Run control and the live progress stream (Server-Sent Events) |
| **Memory** | The knowledge record (served via an MCP server + pgvector) |
| **Source-control mirror** | Synced issues, PRs, and check runs |
| **Dashboards & search** | Per-project dashboards, consumption metering, RBAC-scoped global search |
| **Auth & admin** | Login/session, users, per-project memberships, settings |

> The concrete endpoint paths, request/response schemas, and the OpenAPI/Swagger document are
> generated and published alongside this reference. Authentication uses the session tokens issued at
> login; all endpoints enforce the [RBAC model](../operator-guide/rbac) server-side.

## Events

Domain events (Run lifecycle, work-item transitions, artifacts, memory writes, sync results, credential
refresh) are published on a **versioned event catalog** and delivered to plugins over NATS. See the
[Plugin SDK → Event reference](../plugin-sdk/event-reference) for the subject taxonomy and event
schemas.

## Stability

`v1alpha1` signals that the API may evolve. Changes to the event catalog and CRD schemas follow a
**pinned-adapter discipline** — additive or gated, never ambient breakage — so integrations that pin a
schema revision survive platform evolution.
