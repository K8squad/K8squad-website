---
title: Core Concepts
description: The building blocks of KSquad — Squads, Agents, Roles, Skills, Projects, and Runs — and how they fit together.
sidebar_position: 2
---

# Core Concepts

KSquad models everything as Kubernetes objects under the API group **`ksquad.io/v1alpha1`**. Six
concepts do most of the work. Read them in order the first time; they build on each other.

| Concept | CRD | One-line definition |
|---------|-----|---------------------|
| [Squad](./squads) | `Team` | The tenancy boundary — a crew of agents and the projects they own. |
| [Agent](./agents) | `Agent` (+ `AgentRuntime`) | One agent instance: a runtime + a role + skills + a credential. |
| [Role](./roles) | `Role` | A reusable behavior profile — how an agent thinks and acts. |
| [Skill](./skills) | `Skill` | A granted capability — what tools an agent may use. |
| [Project](./projects) | `Project` | A repo plus a workspace the squad works against. |
| [Run](./runs) | `Run` | A unit of squad work — a reconciled, crash-safe workload. |

## How they fit together

![The ksquad.io/v1alpha1 object model: a Squad (Team) owns a Project and has Agents; each Agent uses a Role and Skills, runs on an AgentRuntime, and authenticates with a Secret; an Agent drives a Run, which claims a durable Work Item and executes in an isolated Sandbox.](./images/concept-model.svg)

A **Squad** (`Team`) owns one or more **Projects** and has **Agents**. Each Agent composes a **Role**
(behavior) with **Skills** (tools and permissions), runs on an **AgentRuntime** (which coding CLI), and
authenticates with its own **Secret**. An Agent drives a **Run**, which claims a durable **Work Item**
(a Postgres row, not a CRD) and executes in an isolated **Sandbox**.

## Two records, one database

Two distinct kinds of durable state underpin every concept, and both live in **one Postgres**:

- **The coordination record** — work items, claims, leases, comments, and artifacts. This is how
  agents coordinate *without ever talking to each other directly*, and it doubles as the audit trail.
- **The knowledge record** — the squad's memory, served by a first-class memory service so knowledge
  compounds across runs.

Keeping these two records separate and durable is a deliberate design choice: **coordination state is
never trapped inside a pod**, and knowledge outlives any single Run.

## Desired state vs. durable state

- **Desired state** — `Team`, `Agent`, `AgentRuntime`, `Role`, `Skill`, `Project`, `Run`,
  `OTelConfig` — is expressed as **CRDs** and reconciled by the operator.
- **Durable, high-churn app state** — work items, comments, claims, artifacts, memory, users — lives
  in **Postgres**, behind the apiserver and memory APIs. These are *not* CRDs.

Knowing which side of this line a thing lives on tells you how to interact with it: `kubectl` /
console-compose for desired state; the console and APIs for the durable record.
