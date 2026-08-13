---
title: KSquad — Run a squad of AI agents as a Kubernetes-native workload
description: KSquad is a Kubernetes-native, agent-agnostic control plane for running a squad of AI agents against a shared backlog — reconciled, isolated, and legible like any other cluster workload.
type: landing
---

<!--
LANDING PAGE COPY — KSquad
Owner: Content Writer (copy + structure). Graphic Designer owns visual layout, hero art, and
logo placement. See CONTENT-NOTES.md for image slots and the K8squad 8-Crest logo lockup rules.
Brand: prose uses "KSquad"; the wordmark/logo renders the stylized "K8squad" 8-Crest mark.
-->

# Hero

**Eyebrow:** Kubernetes-native · Agent-agnostic · Open source

**Headline:**
Run a squad of AI agents like any other Kubernetes workload.

**Subhead:**
KSquad is a Kubernetes-native control plane for running a *squad* of AI agents against a shared
backlog. It treats "a crew of agents working a project" as a first-class, reconciled workload — the
way Kubernetes already treats Deployments and Jobs. You keep your credentials, your source, and your
runtime of choice.

**Primary CTA:** Get started in under 30 minutes →  `/docs/quickstart`
**Secondary CTA:** Read the concepts →  `/docs/concepts`

**Hero visual note (Graphic Designer):** fleet/squad overview console (mock `01-squad-overview`),
or the 8-Crest mark over a dark NOC-density canvas. See CONTENT-NOTES.md.

---

# The problem (short intro band)

Teams running AI agents today face a false choice:

- **Hand a hosted SaaS your credentials and source code** — and accept single-vendor lock-in, a closed
  runtime, and someone else's idea of how agents coordinate.
- **Hand-wire `claude`, `opencode`, and homegrown bots yourself** — and get no isolation, no shared
  state, and no operator surface when something goes wrong at 2 a.m.

KSquad is the missing layer in between: a **fresh Go operator + web console** that reconciles your
squads as CRDs, coordinates agents through durable, crash-safe work items (never peer-to-peer chat),
and runs untrusted agent code in warm-pool sandboxes under Kubernetes RBAC and NetworkPolicy
isolation. Agents from any runtime plug in through a documented shim contract. Every agent runs on its
own user's subscription — **KSquad never holds a shared master credential.**

---

# What makes KSquad different (features)

## 1. Orchestrate the agent — don't reimplement it
KSquad is **agent-runtime-agnostic**. Claude Code, OpenClaw, Hermes, and other coding agents plug in
behind one shim contract (A2A southbound, MCP for tools). Swap or mix runtimes without rewriting your
platform. KSquad orchestrates the crew; it never tries to *be* the agent.

## 2. A reconcile control plane, not heartbeat glue
Every unit of work is a `Run` — a reconciled Kubernetes workload with an explicit, crash-safe state
machine (`Pending → Claiming → Running → Succeeded/Failed/Paused/Cancelled`). A controller restart
never double-drives a Run, and no coordination state is ever trapped inside a dead pod.

## 3. Durable, first-class work items
Coordination is a durable record in Postgres — checkout, claim, lease, fencing, audit — **not** agents
DMing each other. At most one agent holds a work item at a time; a crashed agent's work is safely
reclaimed and re-dispatched. The coordination record *is* the audit trail.

## 4. Bring your own credentials — and your own model
Each agent authenticates with a **per-user Kubernetes Secret** on its own subscription. Connect Claude
once with a single OAuth click and a controller keeps the token fresh for you — zero-touch, no manual
rotation. Prefer a local model? Point an agent at your own Ollama or OpenAI-compatible endpoint.

## 5. Safe by construction
Untrusted agent code runs in **warm-pool sandboxes** (gVisor by default) with per-squad namespaces,
RBAC, NetworkPolicy egress control, and explicit, capability-gated tooling. A compromised agent can't
fabricate a Run, escape its namespace, or reach the network it wasn't granted.

## 6. Legible from install to incident
A web console shows your fleet, live Run streams over SSE, build artifacts, per-project dashboards,
consumption metering, and a full audit trail. Ship telemetry anywhere with an opt-in `OTelConfig`
CRD — traces to one backend, metrics to another, logs to a third.

## 7. One afternoon to first squad
One `helm install` brings up the operator, apiserver, memory service, console, Postgres, and the event
bus. Sane defaults, explicit storage and exposure wiring, and a quickstart that gets you from empty
cluster to first running squad in under an afternoon.

---

# How it works (3–4 steps)

**Step 1 — Install the control plane.**
`helm install` KSquad into your cluster. You get the operator, apiserver, memory service, and console,
with Postgres and the NATS event bus bundled as boring subcharts.

**Step 2 — Connect a credential and define agents.**
Click **Connect Claude** once (or `ksquad auth login`), then declare 2–3 `Agent`s from the bundled
runtimes. Each agent has a `Role` (how it behaves) and `Skill`s (what tools it may use).

**Step 3 — Point at a repo and form a squad.**
Create a `Project` (a repo + a workspace) and group your agents into a `Team`. That's your squad.

**Step 4 — Start a Run.**
Kick off a `Run` from the console or with `kubectl apply`. Watch progress stream live, inspect the
artifacts, and review the durable coordination record. No orchestration code to write.

**How-it-works visual note (Graphic Designer):** a 4-node horizontal flow (Install → Agents → Squad →
Run), or the `08-fleet-dashboard` + `02-run-stream-sse` mocks side by side.

---

# Who it's for

- **Platform engineering teams** who want agent crews to be a governed, isolated, legible cluster
  workload — not a shadow-IT pile of API keys and cron jobs.
- **Tech leads** who need multiple heterogeneous agents working one backlog, with a real operator
  surface, audit trail, and cost visibility.
- **Anyone who refuses the credential-custody / lock-in bargain** of hosted AI-teammate SaaS.

---

# Trust & openness band

- **Vendor-neutral by construction.** BYO runtime, BYO credential, BYO model endpoint. No shared master
  credential, ever.
- **Two durable records, one database.** A coordination record and a knowledge record, both in one
  Postgres — no coordination state hidden in a pod.
- **Open source.** Apache-2.0, CRDs + operator + Helm. A substrate, not a silo.

---

# Final CTA band

**Headline:** Give your agents a control plane.
**Body:** Install KSquad, connect a credential, and run your first squad this afternoon.
**Primary CTA:** Quickstart →  `/docs/quickstart`
**Secondary CTA:** Star us on GitHub →  `https://github.com/K8squad`

---

## Reusable microcopy

- **One-liner (nav / social):** A Kubernetes-native control plane for squads of AI agents.
- **Elevator pitch (60 words):** KSquad runs a squad of AI agents against a shared backlog as a
  first-class, reconciled Kubernetes workload. Agents from any runtime plug in behind one shim
  contract, coordinate through durable crash-safe work items instead of peer-to-peer chat, and run in
  warm-pool sandboxes under RBAC and NetworkPolicy. Every agent uses its own credential — KSquad never
  holds a shared master key.
- **Three-delta tagline:** Orchestrate, don't reimplement. Reconcile, don't glue. Durable work items,
  not DMs.
