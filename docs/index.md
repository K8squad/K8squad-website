---
title: KSquad Documentation
description: Install, operate, and extend KSquad — the Kubernetes-native control plane for squads of AI agents.
sidebar_position: 0
---

# KSquad Documentation

**KSquad is a Kubernetes-native, agent-agnostic control plane for running a *squad* of AI agents
against a shared backlog.** It reconciles your squads as CRDs, coordinates agents through durable
work items, and runs untrusted agent code in isolated sandboxes — so a crew of agents becomes a
first-class, legible cluster workload instead of a pile of scripts and API keys.

New here? Read the [one-paragraph overview of how the pieces fit together](#the-model-in-one-paragraph),
then jump into the [Quickstart](./quickstart).

## Start here

| If you want to… | Go to |
|-----------------|-------|
| Get from empty cluster to first running squad | [Quickstart](./quickstart) |
| Understand the building blocks | [Core Concepts](./concepts) |
| Install and run KSquad for a team | [Operator Guide](./operator-guide) |
| Compose agents, squads, and work items | [Author Guide](./author-guide) |
| Learn the console screen by screen | [Console Guide](./console-guide) |
| Look up CRD fields and API objects | [API Reference](./api-reference) |
| Ship traces, metrics, and logs | [Observability](./observability) |
| Diagnose a stuck Run or a failed install | [Troubleshooting](./troubleshooting) |
| Build an integration that reacts to events | [Plugin SDK](./plugin-sdk) |

## The model in one paragraph

You define a **Squad** (a `Team`) that owns one or more **Projects** (a repo + a workspace). A squad is
made of **Agents**, each of which has a **Role** (how it behaves) and **Skills** (what tools it may
use), and authenticates with its own per-user credential. When there's work to do, you start a
**Run** — a reconciled workload that claims a durable **work item**, spins up an isolated sandbox, and
drives an agent to completion. Agents never talk to each other directly; they coordinate through the
durable work-item record. Everything is observable in the console and exportable as OpenTelemetry.

## Core principles

- **Orchestrate the agent, don't reimplement it.** Any compliant runtime plugs in behind one shim
  contract. KSquad coordinates the crew; it is not itself an agent.
- **Reconcile, don't glue.** Runs are level-triggered Kubernetes workloads with a crash-safe state
  machine. No heartbeat scripts, no lost state in dead pods.
- **Coordinate through durable work items, never peer-to-peer chat.** At most one agent holds a work
  item at a time; the record is the audit trail.
- **Bring your own credential.** Per-user Kubernetes Secrets; KSquad holds no shared master credential.
- **Safe by construction.** Warm-pool sandboxes, per-squad namespaces, RBAC, NetworkPolicy egress
  control, and capability-gated tooling.
- **One database, two records.** A coordination record and a knowledge record both live in one
  Postgres — nothing critical is hidden in a pod.

## Versioning

KSquad ships its CRDs under the API group **`ksquad.io/v1alpha1`**. This documentation tracks the
current release; where behavior is version-dependent it is called out inline.
