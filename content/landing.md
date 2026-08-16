---
title: KSquad — Your agents, in formation
description: KSquad is a Kubernetes-native control plane for teams of AI agents. Compose squads as CRDs, let them claim work and coordinate over a shared bus, and watch every run live with OpenTelemetry.
type: landing
---

<!--
LANDING PAGE COPY — KSquad
Owner: Content Writer (copy + structure). Graphic Designer owns visual layout, hero art, and
logo placement. See CONTENT-NOTES.md for image slots and the K8squad 8-Crest logo lockup rules.
Structure and section order follow the approved mock (docs/bmad/ux/website-mocks/01-landing) — hero,
"What is KSquad" (3 cards), features (8 cards), how-it-works (4 steps), "See it in action" carousel,
get-started band, footer.
Brand: prose uses "KSquad"; the wordmark/logo renders the stylized "K8squad" 8-Crest mark.
Web domain: k8squad.io (docs.k8squad.io, charts.k8squad.io, console.k8squad.io). The CRD API group
stays ksquad.io/v1alpha1 — it is baked into the Go types, not a web address.
-->

# Hero

**Eyebrow:** Multi-agent orchestration for Kubernetes

**Headline:**
Your agents, in formation.

**Subhead:**
Compose squads of AI agents as Kubernetes resources. They claim work, hand off, and coordinate — and
you watch every run, live, with OpenTelemetry. Bring your own runtime, your own credentials, and your
own model; KSquad reconciles the crew like any other cluster workload.

**Primary CTA:** Get started →  `/docs/quickstart`
**Secondary CTA:** View on GitHub →  `https://github.com/K8squad`

**Hero command (mono, under the CTAs):**
```bash
helm install ksquad ksquad/ksquad -n ksquad-system
```

**Hero visual note (Graphic Designer):** the 8-Crest mark over a dark NOC-density node formation
(`assets/brand/hero-art`), headline set live in Geist over the negative space. See VISUAL-NOTES.md.

---

# What is KSquad?

**A Kubernetes-native control plane for teams of AI agents.** Three ideas, and everything else follows.

### Kubernetes-native
Squads, agents, and runs are CRDs. Deploy with Helm, manage with `kubectl`. If you can operate a
cluster, you can operate a squad — same objects, same RBAC, same reconcile loop.

### Agents in formation
Compose teams that claim work, hand off, and coordinate over a shared, durable bus — never peer-to-peer
DMs. At most one agent holds a work item at a time, and a crashed agent's work is safely reclaimed.

### Observable by default
Every run emits OpenTelemetry traces and streams live over SSE. No black boxes: follow each tool call,
model response, and log line as it happens, and ship the telemetry to any OTLP backend you already run.

---

# The problem (short intro band)

Teams running AI agents today face a false choice:

- **Hand a hosted SaaS your credentials and source code** — and accept single-vendor lock-in, a closed
  runtime, and someone else's idea of how agents coordinate.
- **Hand-wire `claude`, `opencode`, and homegrown bots yourself** — and get no isolation, no shared
  state, and no operator surface when something goes wrong at 2 a.m.

KSquad is the missing layer in between: a **fresh Go operator + web console** that reconciles your
squads as CRDs, coordinates agents through durable, crash-safe work items, and runs untrusted agent
code in warm-pool sandboxes under Kubernetes RBAC and NetworkPolicy isolation. Agents from any runtime
plug in through a documented shim contract. Every agent runs on its own user's subscription —
**KSquad never holds a shared master credential.**

---

# Everything you need to run agent squads (features)

## 1. Project-scoped squads
Every squad lives in its own project and namespace — RBAC-gated and NetworkPolicy-isolated. One team's
agents can't see, or reach, another team's work, credentials, or cluster.

## 2. Agent org views
A live org chart of your crew: who leads, who reports to whom, and what each agent is doing right now.
Leadership and role views make a running squad legible at a glance.

## 3. Build browser
Every artifact an agent produces — diffs, files, logs — is browsable across every `Run` and addressable
by content hash. Inspect exactly what changed, and where it came from.

## 4. Live runs
Follow a `Run` as it unfolds over SSE: each tool call, model response, and log line, in order. A
controller restart never double-drives a run, so what you see is what actually happened.

## 5. RBAC
Two global roles and three per-project access levels map cleanly onto Kubernetes RBAC — operators run
the platform, authors compose the work, and everyone's access is auditable.

## 6. OTel-native
Traces, metrics, and logs out of the box. An opt-in `OTelConfig` CRD fans each signal out to any OTLP
backend — traces to one destination, metrics to another, logs to a third.

## 7. Plugin SDK
Extend the platform with sandboxed, least-privilege plugins that react to typed events —
`run.succeeded`, `workitem.claimed`, `workitem.handoff`, `artifact.registered`, and more, over durable
NATS JetStream subjects. A plugin can never block a run; a flaky endpoint can never stall the platform.

## 8. Responsive
The full operator console — dashboards, kanban, agent org, build browser — adapts from a wide NOC
display down to a phone, so you can check a squad from wherever you are.

---

# How it works (4 steps)

**Step 1 — Compose CRDs.**
Declare a `Team` and its agents in YAML — each agent with a `Role` (how it behaves) and `Skill`s (what
tools it may use). Point a `Project` at a repo. `kubectl apply`.

**Step 2 — Squad spins up.**
The operator reconciles your objects into running agents, scheduling them as pods and wiring the
coordination bus. Reconciliation is level-based — edit and re-apply, and the crew converges to match.

**Step 3 — Agents work.**
Agents claim work items, hand off, and coordinate through the durable bus. At most one holds an item at
a time; a crashed agent's work is reclaimed and re-dispatched. The coordination record *is* the audit
trail.

**Step 4 — You monitor.**
Watch runs stream live, follow the traces, and inspect the artifacts — from the console or straight from
`kubectl`. No orchestration code to write.

**How-it-works visual note (Graphic Designer):** the 4-node horizontal flow
(`assets/brand/how-it-works`) — Compose CRDs → Squad spins up → Agents work → You monitor.

---

# See it in action

**The operator console — nav, kanban, dashboards, agent org, and build browser.** A single, dense
surface for running the whole fleet.

**Carousel (Graphic Designer — dark-theme console screenshots in `docs/console-guide/images/`):**

1. **Nav & IA** — the console shell and adaptive navigation.
2. **Project kanban** — work items moving through a project's board.
3. **Fleet dashboard** — every squad and live run at a glance (`console.k8squad.io/fleet/dashboard`).
4. **Agents org** — the live agent org chart with per-agent status.
5. **Build browser** — artifacts across runs, addressable by hash.

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

# Get started in one command

Install the operator, then open the console.

```bash
helm repo add ksquad https://charts.k8squad.io && helm install ksquad ksquad/ksquad
```

**Primary CTA:** Read the docs →  `/docs/quickstart`
**Secondary CTA:** Star us on GitHub →  `https://github.com/K8squad`

---

# Footer

**Tagline:** Your agents, in formation.
**License line:** Apache 2.0 licensed · © 2026 KSquad

| Product | Docs | Community |
|---------|------|-----------|
| Features | Quickstart | GitHub |
| Console | Concepts | Discussions |
| Plugin SDK | Operator Guide | Releases |
| Roadmap | API Reference | License |

**Footer meta:** `github.com/K8squad/K8squad`  ·  `docs.k8squad.io`

---

## Reusable microcopy

- **One-liner (nav / social):** Your agents, in formation — a Kubernetes-native control plane for
  squads of AI agents.
- **Elevator pitch (60 words):** KSquad runs a squad of AI agents against a shared backlog as a
  first-class, reconciled Kubernetes workload. Agents from any runtime plug in behind one shim
  contract, coordinate through durable crash-safe work items instead of peer-to-peer chat, and run in
  warm-pool sandboxes under RBAC and NetworkPolicy. Every agent uses its own credential — KSquad never
  holds a shared master key.
- **Three-delta tagline:** Orchestrate, don't reimplement. Reconcile, don't glue. Durable work items,
  not DMs.
