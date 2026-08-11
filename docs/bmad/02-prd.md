---
stepsCompleted: [discovery, vision, executive-summary, success, journeys, domain, innovation, project-type, scoping, functional, nonfunctional, polish, challenger-integration, ceo-requirements-r3]
inputDocuments:
  - docs/bmad/00-kickoff-brief.md   # CEO scope + LOCKED decisions (commit 90747e3)
  - docs/bmad/01-brainstorming.md   # Phase 1 synthesis, Alfred-approved 2026-08-10 (commit f7c151e)
  - ISI-2111                         # Design doc: Squad architecture v0.1 (seed, partially superseded)
  - ISI-2112                         # Spike: claude setup-token longevity (credential evidence — in flight)
  - ISI-2113                         # Spike: warm-pool claim latency (arch evidence — in flight)
  - ISI-2114                         # Spec: agent shim interface (arch evidence — in flight)
  - ISI-2121                         # Challenger independent review — CONDITIONAL PASS; findings F1–F20 folded in via ISI-2125
  - ISI-2145                         # CEO r3: Source-control sync (GitHub-first) → Theme H
  - ISI-2146                         # CEO r3: Dashboard / cost + throughput metering → Theme I
  - ISI-2147                         # CEO r3: Per-Project discussion room (collaboration, NOT coordination) → Theme J
  - ISI-2148                         # CEO r3: Build browser (per-Run files/diffs/code view) → Theme K
  - ISI-2149                         # CEO r3: Helm install — Gateway API exposure + explicit StorageClass → Theme L
  - ISI-2150                         # CEO r3: Dark + light mode as v1 console requirement → FR-F7
revisions:
  - r1 (2026-08-10, ISI-2118): initial PRD synthesis
  - r2 (2026-08-10, ISI-2125): Challenger findings (ISI-2121) folded in — see §13.2 for the finding→change map
  - r3 (2026-08-11, ISI-2152): six new CEO requirements (ISI-2145..2150) folded in — new Themes H/I/J/K/L, FR-F7, NFR updates, OQ13–OQ17, risks R13–R17; see §13.3 for the requirement→change map. Re-review requested at CEO gate.
workflowType: 'prd'
authoringMode: 'analyst-led autonomous synthesis (same posture as Phase 1); CEO gate is the human review checkpoint'
project_name: 'KSquad'
gate: 'CEO (BigBoss) — required before Phase 3 (Architecture)'
source_ticket: 'ISI-2118'
parent: 'ISI-2116'
program: 'ISI-2115'
---

# Product Requirements Document — KSquad

**Author:** John (Product Manager)
**Date:** 2026-08-10 · **Revised:** 2026-08-11 (r3 — CEO requirements ISI-2145..2150)
**Phase:** BMAD Phase 2 — PRD
**Gate:** CEO (BigBoss) approval required before Phase 3 (Architecture) · **r3 re-review requested (§14)**
**Source ticket:** ISI-2118 (r1/r2) · ISI-2152 (r3) · **Parent:** ISI-2116 · **Program:** ISI-2115

> **Scope discipline.** This PRD builds on the seven LOCKED decisions in the kickoff brief
> (`00-kickoff-brief.md`, commit 90747e3) and the six themes + two-records principle in the
> approved brainstorming synthesis (`01-brainstorming.md`, commit f7c151e). It **does not reopen**
> locked decisions. Anything that would touch one is filed as an **⚠ ESCALATION** (§13), not a
> requirement. Open questions that Architecture (Phase 3) owns are routed explicitly (§12), not
> resolved here.

---

## 1. Executive Summary

**KSquad is a Kubernetes-native, agent-agnostic control plane for running a *squad* of AI agents
against a shared backlog** — treating "a crew of agents working a project" as a first-class,
reconciled workload the way Kubernetes already treats Deployments and Jobs.

Teams today face a false choice: hand a hosted SaaS platform their credentials and source code and
accept single-vendor lock-in, or hand-wire `claude`, `opencode`, and homegrown bots with no
isolation, no shared state, and no operator surface. KSquad is the missing layer: a fresh Go
operator + Node console (not a Paperclip fork) that reconciles `Team`/`Agent`/`Role`/`Skill`/
`Project`/`Run` CRDs, coordinates agents through **durable shared work items** (never P2P chat),
persists squad knowledge in a **first-class memory server**, and runs untrusted agent code in
**warm-pool sandboxes** under Kubernetes RBAC/NetworkPolicy isolation. Agents from any runtime plug
in through a documented **shim contract** (A2A southbound, MCP for tools); each agent runs on its
own user's **BYO subscription** — KSquad never holds a shared master credential.

The product's defining bet, confirmed by the Phase 1 Challenger pass (ISI-2121, CONDITIONAL PASS):
the locked decisions are *mutually reinforcing* — **be the durable, legible, vendor-neutral
substrate, not the agent.** The MVP's job is to prove that bet end-to-end with one real squad on one
real repo, safely installable by a platform engineer in an afternoon.

> **Differentiation is exactly three deltas** (Challenger F1–F5). KSquad's moat is (1)
> **agent-runtime-agnostic shims** — orchestrate, don't implement the agent; (2) a **reconcile
> control plane** — Runs as reconciled workloads, not heartbeat glue; and (3) **native durable work
> items** — coordination as first-class, crash-safe state. **First-class memory is *parity*, not a
> moat**: the closest comparator, Sympozium, already ships it. We invest in memory to reach parity
> and to make the compounding-knowledge story real (S7) — but the PRD deliberately does **not**
> position memory as the differentiator, and neither should downstream messaging.
>
> **The r3 additions are adoption/legibility/integration surface, not new moats.** The six CEO
> requirements folded in as r3 — source-control sync (H), operational dashboard (I), the discussion
> room (J), the build browser (K), install/exposure hardening (L), and console theming (FR-F7) — make
> KSquad **usable and legible** in a real platform team's world. They strengthen S1–S3 adoption; none
> of them is a differentiator, and downstream positioning should keep weighting the three deltas (§8).
> One of them (J, the discussion room) sits close to a **locked decision** and is fenced accordingly
> in §6.1.

---

## 2. Product Vision

**For** platform engineering teams and tech leads **who** want to run multiple heterogeneous AI
agents as a coordinated crew, **KSquad is** a Kubernetes-native orchestration control plane **that**
makes squads a reconciled, isolated, legible, vendor-neutral workload. **Unlike** hosted "AI
teammate" SaaS (single-vendor, credential-custody, closed runtime) **or** DIY glue (no isolation, no
shared state, no operator surface), **KSquad** keeps the coordination record and the knowledge
record as two distinct durable substrates, orchestrates rather than implements the agent, and
distributes as CRDs + operator + Helm — the AAIF-candidate posture of a substrate, not a product
silo.

---

## 3. Project Classification

| Dimension | Classification |
|-----------|----------------|
| Product type | Infrastructure / platform: Kubernetes operator (Go) + web operator console (Node.js) + first-class memory service |
| Domain | Developer / platform infrastructure; AI agent orchestration. **Domain complexity: High** (untrusted-code isolation, multi-tenancy, credential lifecycle, protocol seams) |
| Project context | **Greenfield** — fresh codebase; ISI-2111 v0.1 design absorbed as input, not extended |
| Distribution | Open-source; potential AAIF (AI Agent Infrastructure Foundation) candidate |
| Primary interfaces | `kubectl`/CRDs, Helm, operator console (browser), A2A (southbound), MCP (tools) |

---

## 4. Success Criteria

Success is defined against the four audiences (§5). Metrics are targets for **v1 / first light**, to
be confirmed with the named design partner (§11, resolves OQ8).

### 4.1 User / operator success
- **S1 — Day-one install.** A platform engineer installs KSquad (Helm + CRDs) on a conformant
  cluster and runs a first squad **in under one afternoon (≤ 4 hours)**, following docs alone.
  *This is the acceptance test that closes OQ8.*
- **S2 — Legibility.** From the console, an operator can, without `kubectl`, answer "what squads
  exist, what is each Run doing right now, and what did it produce" — and **kill a runaway Run in
  ≤ 2 clicks**.
- **S3 — Authoring without glue.** A tech lead composes a working "review + fix + test" squad on a
  real repo **without writing orchestration code** — only CRDs (via console or YAML).
- **S4 — Blast radius is bounded.** An agent executing arbitrary code cannot reach another squad's
  workspace, secrets, or namespace; a deliberately hostile test Run is contained (verified by an
  isolation test, not just asserted).

### 4.2 Business / ecosystem success
- **S5 — Vendor self-onboarding.** An agent-runtime integrator ships a conformant shim for a new
  runtime **in days, not weeks**, passing the shim conformance suite (owned by ISI-2114) with **zero
  core code changes**.
- **S6 — Two runtimes at launch.** **OpenClaw and Hermes** both run real Runs inside the same squad
  at v1, proving agent-agnosticism is real and not single-vendor-with-extra-steps.
- **S7 — Compounding knowledge.** A squad's second Run measurably benefits from the first via the
  memory server (e.g. it recalls a prior decision/fact rather than re-deriving it) — the
  differentiator over stateless orchestration is demonstrable, not theoretical.

### 4.3 Technical success
- **S8 — Reconciliation is the control plane.** A `Run` whose sandbox/agent dies mid-execution is
  retried/resumed by the controller with backoff; **no work item is lost** (durability of the
  coordination record).
- **S9 — Warm-pool latency budget.** Median `Run` start latency is **claim-time, not cold-boot-time**
  — target confirmed against the ISI-2113 benchmark before v1 commits a pool-sizing policy.
- **S10 — Credential resilience.** When a BYO subscription token expires/rotates mid-Run, the Run
  **pauses gracefully with a clear operator signal** and resumes on refresh — never fails opaquely
  (design gated on ISI-2112 evidence; see R1/§12 OQ1).

---

## 5. Personas & User Journeys

KSquad has **four audiences** that pull in different directions (from brainstorming §1.4). Keeping
all four satisfied simultaneously is the product's central design tension.

> **Tiebreaker when audiences collide (Challenger F20).** When **operator-safety (Priya)** and
> **author-expressiveness (Sam)** conflict — e.g. a compose feature that would widen blast radius,
> or an authoring convenience that would weaken isolation — **operator-safety wins.** Isolation,
> bounded blast radius, and least privilege (§7 D1–D2, NFR-SEC*) are non-negotiable; expressiveness
> yields to them. This is the standing rule Architecture and Epics apply when a design forces the
> choice, so the trade is decided once here rather than re-litigated per feature.

| Persona | Role | Core need | Success signal |
|---------|------|-----------|----------------|
| **Priya — Platform Engineer** (primary operator) | Owns the cluster + internal dev platform; rolls KSquad out | Native install, CRDs, RBAC/NetworkPolicy isolation, an operator console showing squads/runs/live progress/artifacts | Installs in an afternoon; blast radius bounded; can see & kill a runaway Run |
| **Sam — Squad Author / Tech Lead** (primary user) | Defines a squad against a repo | Declarative CRDs + a compose UI + live Run stream + artifact inspection | Spins up "review + fix + test" without glue code |
| **Dana — Agent-runtime vendor / OSS integrator** (ecosystem) | Wants their runtime to run inside KSquad | A documented shim contract + conformance tests | Ships a shim in days; it appears in squads unchanged |
| **Morgan — the agent itself** (coordination-surface user) | Executes work, checks out items, files comments/artifacts | Shared-work-item API + memory server + MCP tools — **not** a P2P chat channel | Coordinates through durable state; a crash loses nothing |

### 5.1 Journey — Priya installs and gains legibility (S1, S2, S4)
Priya has a conformant cluster and a mandate to let three teams run agent crews without giving a SaaS
vendor her repos. She `helm install`s KSquad; CRDs register and the operator console comes up. She
opens the console: empty but self-explanatory — "create a Project, bind a repo, compose a Team." She
hands the console URL to two tech leads. A week later a Run spikes CPU; she opens the console, sees
the offending Run streaming live, inspects its artifacts, and **kills it in two clicks** — the
sandbox is torn down and the namespace is untouched elsewhere. *New reality: she offers "squads as a
service" internally with bounded blast radius and full legibility.*

### 5.2 Journey — Sam authors a squad (S3, S6, S7)
Sam wants automated review-and-fix on `payments-service`. In the console he creates a `Project`
(repo + workspace), defines three `Agent`s bound to `Role`s (Reviewer, Fixer, Tester) drawn from two
runtimes (**OpenClaw** and **Hermes**), assigns `Skill`s, and groups them into a `Team`. He starts a
`Run` against an open backlog item. He watches the **live SSE stream**: the Reviewer checks out the
item, files findings as comments, the Fixer claims the follow-up and produces a diff artifact, the
Tester validates. On the *next* Run, the squad recalls the earlier architectural decision from the
**memory server** instead of re-litigating it. *New reality: a working crew, composed declaratively,
that gets smarter across runs.*

### 5.3 Journey — Dana onboards a runtime (S5)
Dana maintains an OSS agent runtime and wants it usable in KSquad. She reads the **shim contract**
(A2A Agent Card in, native invocation out), implements a thin translator, and runs the
**conformance suite**. Capability gaps (e.g. no interactive-prompt support) surface as **capability
flags on the Agent Card**, not as failures. She publishes the shim; a squad author adds her runtime
to a `Team` with no KSquad code change. *New reality: her runtime is a first-class citizen of every
squad.*

### 5.4 Journey — Morgan (agent) coordinates durably (S8)
Morgan is an agent executing a Run. It **checks out** a work item (claim semantics prevent two
agents grabbing the same item), does work, files a comment + artifact, and writes a learned fact to
the **memory server** via an MCP tool. Its sandbox is OOM-killed mid-task. The controller reconciles:
the checkout is released/retried, and a fresh sandbox resumes from durable state — **nothing is
lost**, because coordination lives in work items and knowledge lives in memory, never in ephemeral
chat. *New reality: crash-safe coordination is a property of the substrate, not the agent.*

---

## 6. The Two Records (organizing principle)

KSquad maintains **two distinct durable records**, and keeping them distinct is a hard product
principle (brainstorming §4), not an implementation detail:

1. **The coordination record** — work items, comments, checkout/claim. Answers *"what is being done,
   by whom, right now."* Source of truth for reconciliation.
2. **The knowledge record** — the memory server. Answers *"what do we know, and what did we decide
   before."* Source of truth for agent context.

A2A (southbound) and MCP (tools) are the **transport**; these two records are the **state**. Blurring
them — agents chatting P2P, or knowledge buried in comment threads — is the anti-pattern the locked
decisions exist to prevent. Every functional requirement below respects this separation.

**Memory is a knowledge record, not a back-channel (Challenger F16 — flagged for CEO gate).** The
first-class memory server and the no-P2P-chat decision are in tension: a shared read/write knowledge
store *can* be abused as an indirect agent-to-agent messaging channel (agent A writes a "fact," agent
B reads it — de facto coordination outside the work-item record). The PRD defines the **read/write
trust boundary** explicitly so memory does not become covert P2P:

- **Writes are provenanced and authorized.** Every memory record carries its author (principal / agent
  / Run) and is written only by an authorized principal (FR-E6). Memory is **not** a place to hand off
  work — coordination stays in work items (FR-B3); knowledge (durable facts/decisions) goes to memory.
- **Reads treat stored knowledge as untrusted input.** A record written by one agent and read by
  another is potentially adversarial content, not trusted context — see the memory-poisoning threat
  (D6, FR-E7, NFR-SEC6).
- **Scope is the tenancy boundary.** Records are squad/`Project`-scoped and per-principal-attributed
  (FR-E5, NFR-SEC5); cross-tenant read/write is denied by construction.

This tension (memory-as-first-class vs no-P2P) is one of two items **flagged for the CEO gate** (with
F5, the memory-is-parity framing); the Challenger will raise both with BigBoss when this revision
lands. Neither reopens a locked decision — they sharpen the trust boundary and the investment framing.

### 6.1 The discussion room is a *third surface* — collaboration, not a coordination record (ISI-2147)

The r3 discussion room (Theme J, FR-J*) adds a **per-Project room where humans and agents talk**. This
brushes directly against the two most load-bearing locked decisions — **no A2A P2P chat for
coordination** and **two-records discipline** — so the CEO framing is explicit and reproduced here:
**the discussion room is a collaboration surface, NOT a coordination surface. The locked decision is
unchanged.** To make that hold structurally rather than by good intentions, the PRD defines a **third,
distinct surface** with a hard boundary:

- **Coordination stays in work items (unchanged).** Agents SHALL continue to coordinate — check out
  work, hand off, record progress — **exclusively via work items, comments, and artifacts** (FR-B1/B3).
  The discussion room is **not** a place agents claim work, hand off work, or drive a Run. Nothing in
  Theme J relaxes FR-B3. An agent handoff attempted through the room is a **misuse**, not a supported
  path, and the room SHALL NOT carry checkout/claim semantics.
- **The room is human-in-the-loop, not agent-to-agent glue.** Its purpose is **humans collaborating
  with the squad**: an operator or author asks a question, steers priorities, or gets a plain-language
  status; an agent surfaces a question *to a human* or explains a decision. Agent participation is for
  *human* collaboration, not a lateral channel for agents to coordinate with each other outside the
  work-item record. Two agents SHALL NOT use the room to sequence their own work.
- **The room is not the knowledge record either.** Durable facts and decisions still go to the memory
  server (FR-E*); the room is conversational and **not** a source of truth agents mine as trusted
  context. If a room discussion produces a durable decision, that decision is written to a work item
  (coordination) or memory (knowledge) by an authorized principal — the room itself is not authoritative.
- **Provenance and scope, like the other surfaces.** Room messages are attributed to their author
  (human principal or agent/Run), `Project`-scoped, and do not cross tenancy boundaries (NFR-SEC7).

So KSquad now has **two durable *records*** (coordination, knowledge) plus **one collaboration
*surface*** (the room). Records are authoritative and machine-driven; the surface is conversational and
human-anchored. This distinction is what lets us add a discussion room **without** reintroducing the P2P
coordination anti-pattern the locked decisions exist to prevent. It is added as a **CEO-gate ratification
item** (§13) so BigBoss confirms the fence explicitly.

### 6.2 Source-control sync feeds the coordination record — it does not create a parallel one (ISI-2145)

GitHub-first source-control sync (Theme H, FR-H*) maps **external issues ⇄ KSquad work items** and
surfaces PR status, CI results, and artifacts. This is consistent with the two-records discipline, and
the mapping is deliberate: **a synced GitHub issue becomes a first-class work item in the coordination
record** — it does not create a second, competing coordination store. GitHub is an *edge* the
coordination record syncs with, the same way a person filing an issue is. Two constraints keep this
clean: (1) inbound GitHub content (issue bodies, comments, PR text) is **untrusted input** (D8), treated
like any other external text an agent may read; (2) the sync is **provenanced** — a work item created
from GitHub records its external origin, and status/PR/CI signals mirrored back are attributed to the
sync connector, not to an agent. Bidirectionality, conflict resolution, and loop-prevention are an
Architecture concern (OQ13), not resolved here.

---

## 7. Domain Requirements (high-complexity constraints)

Because agents execute **arbitrary, untrusted code** in a **multi-tenant** cluster on **users' own
credentials**, the following are first-class domain constraints, not optional NFRs:

- **D1 — Untrusted-code isolation is mandatory.** Every agent Run executes inside a sandbox with
  enforced isolation (runtime under evaluation: Kata vs gVisor vs runc — ISI-2113). No Run shares a
  process/network/filesystem boundary with another squad.
- **D2 — Least privilege by construction.** RBAC, NetworkPolicy, Secrets, and PVCs scope every
  squad. An agent gets exactly the access its `Role`/`Project` grants — nothing cluster-wide.
- **D3 — Credential custody stays with the principal.** KSquad never holds a shared master
  credential; each agent runs on a per-user Secret ref (BYO subscription). Token *lifecycle* is a
  design constraint (S10, R1, OQ1).
- **D4 — Auditability.** The coordination record *is* the audit log: who checked out what, when, and
  what artifact resulted must be inspectable after the fact.
- **D5 — Egress is controlled.** Corporate networks may block/proxy model endpoints; the squad's
  outbound network path is a policy surface (per-squad NetworkPolicy and/or egress proxy — OQ4,
  Architecture).
- **D6 — The knowledge record is a security surface, not just a feature (Challenger F7).** Stored
  memory is written by untrusted agents and later read as context by other agents — so
  **memory poisoning / prompt-injection-into-a-knowledge-record is a first-class threat**, on par with
  untrusted-code execution. Memory writes SHALL be authorized and provenanced; memory reads SHALL be
  treated as untrusted input; per-agent trust boundaries SHALL bound what any one principal can write
  or read (FR-E6/E7, NFR-SEC6).
- **D7 — Warm-pool and workspace reuse must not bleed state (Challenger F6).** Because sandboxes are
  drawn from a **warm pool** and workspaces persist across Runs, reuse is a **security** surface, not
  only an economics one: a reused sandbox or shared PVC could carry one principal's source, secrets,
  or scratch state into another's Run. Between Runs a reused sandbox SHALL be reset-or-torn-down, and
  PVC/workspace access SHALL be scoped per principal (FR-C6, NFR-SEC5).
- **D8 — External integration surfaces are untrusted and must be authenticated (r3, ISI-2145).**
  Source-control sync ingests external content (GitHub issue/PR/comment bodies, CI output) and accepts
  inbound webhooks. Ingested content SHALL be treated as **untrusted input** to any agent that reads it
  (same posture as D6 memory reads); inbound webhooks SHALL be **authenticated/verified** (signature
  check) before they mutate any KSquad state; and the sync connector's credentials SHALL follow the BYO
  Secret-ref model (D3, FR-G1) — no shared master token to GitHub. (FR-H4, NFR-SEC8.)

---

## 8. Innovation Patterns (what makes KSquad different)

- **I1 — Reconciliation as the agent control plane.** Long-lived, fail-partway agent Runs map
  naturally onto the operator/reconcile loop — a deliberate departure from Paperclip's
  heartbeat-adapter model. Retry/backoff/resume come from the primitive, not bespoke glue.
- **I2 — Agent-agnosticism via a stable shim seam.** The moat is that KSquad *orchestrates* and does
  not *implement* the agent. All per-runtime variation is confined to one shim contract with a
  conformance suite and capability flags.
- **I3 — First-class, compounding memory (parity, not moat — Challenger F5).** Memory is a supported
  KSquad component (KG + semantic search + per-agent diary — MemPalace as reference model), not a BYO
  vector-DB bolt-on, and squads that persist knowledge across runs compound in value. But this is
  **competitive parity**: Sympozium already ships first-class memory. Treat I3 as table-stakes we must
  match and make real (S7), **not** as the differentiator — the moat is I1, I2, and I4's durable work
  items. Invest in memory accordingly (reach parity, defend it — §10.1 NFR-SEC6), and do not oversell
  it in positioning.
- **I4 — Two-records discipline enforced structurally.** No lateral A2A channel *exists*; the memory
  server is the *only* knowledge sink, and **native durable work items** are the *only* coordination
  substrate — a genuine differentiator (Challenger F1–F4), not glue. The anti-pattern is designed out,
  not merely discouraged.

> **The three deltas, stated once (Challenger F1–F5).** KSquad's defensible differentiation is exactly:
> **(1) agent-runtime-agnostic shims (I2), (2) the reconcile control plane (I1), (3) native durable
> work items (I4/FR-B*).** Everything else — memory, console, credential model — is parity or
> enabling infrastructure. Downstream artifacts (positioning, Architecture emphasis, Epics
> sequencing) should weight effort toward these three.

---

## 9. Functional Requirements (the capability contract)

> These FRs are the capability contract for UX, Architecture, and Epics. They state **WHO** and
> **WHAT**, not **HOW** (no UI details, no perf numbers, no technology choices — those live in NFRs
> §10 and Architecture). Anything not listed here will not exist in v1. MVP/phase is marked per FR
> (§11).

### 9.1 Squad model & reconciliation (Theme A — P0 spine)
- **FR-A1** The system SHALL provide `Team`, `Agent`, `Role`, `Skill`, `Project`, and `Run` as
  first-class declarative resources (CRDs). *(MVP)*
- **FR-A2** A `Project` SHALL bind a workspace (persistent storage) and a source repository. *(MVP)*
- **FR-A3** A `Team` SHALL group `Agent`s bound to `Role`s and `Skill`s, scoped to one or more
  `Project`s. *(MVP)*
- **FR-A4** A controller SHALL reconcile a `Run` from desired to observed state: claim a sandbox,
  invoke the agent(s), collect artifacts, and drive the Run to a terminal state. *(MVP)*
- **FR-A5** The controller SHALL retry/resume a `Run` whose sandbox or agent fails mid-execution,
  with backoff, without losing coordination state. *(MVP)*
- **FR-A6** An operator SHALL be able to cancel/kill a `Run` and have its sandbox torn down
  promptly. *(MVP)*

### 9.2 Coordination record — shared work items (Theme B — P0 spine, LOCKED)
- **FR-B1** The system SHALL provide durable **work items** (issues) with **comments** as the sole
  coordination channel between agents. *(MVP)*
- **FR-B2** The system SHALL provide **checkout/claim** semantics so that at most one agent holds a
  work item at a time; a crashed holder's claim SHALL be releasable/reclaimable via a **lease with a
  bounded expiry** (a claim not renewed within its lease is automatically reclaimable). *(MVP)*
- **FR-B3** Agents SHALL record progress and hand off work exclusively via work items, comments, and
  artifacts — **never** via direct agent-to-agent chat. *(MVP)*
- **FR-B4** The coordination record SHALL be queryable as an audit trail (who did what, when, with
  what result). *(MVP)*

> **Build-cost honesty (Challenger F8).** FR-B2's checkout/claim/**lease** semantics plus safe
> **concurrency** (no double-claim under contention, correct reclaim after crash, idempotent
> reconcile) is a **from-scratch distributed-systems build in Go — a major work item, not a given.**
> It is the single most correctness-critical piece of the P0 spine. Scope, sequence, and staff it as
> a first-class engineering track in Architecture (mechanism/consistency model = Architecture, new
> OQ9) and Epics (it is a foundational epic, not a checkbox), and reflect its weight in v1 estimates
> (risk R10).

### 9.3 Knowledge record — first-class memory server (Theme E — P0 differentiator, LOCKED)
- **FR-E1** The system SHALL provide a first-class **memory service** as a supported KSquad component
  (not an external dependency). *(MVP)*
- **FR-E2** Agents SHALL read and write squad knowledge via **MCP tools** exposed by the memory
  service. *(MVP)*
- **FR-E3** The memory service SHALL persist knowledge across Runs so a later Run can retrieve facts
  and prior decisions from an earlier Run. *(MVP)*
- **FR-E4** The memory service SHALL support, at minimum, the MVP subset defined in §11.2 (semantic
  search + per-agent diary), with knowledge-graph relations as a fast-follow. *(MVP subset; see
  OQ6.)*
- **FR-E5** The memory record SHALL be scoped to its squad/`Project` and SHALL NOT leak across
  tenancy boundaries. *(MVP)*
- **FR-E6** Every memory write SHALL be **authorized and provenanced**: only an authorized principal
  may write, and each record SHALL carry the identity of its author (principal / agent / Run) and
  write time. Unattributed or unauthorized writes SHALL be rejected. *(MVP — Challenger F7.)*
- **FR-E7** The memory service SHALL enforce **per-agent/per-principal trust boundaries** on reads and
  writes and SHALL treat stored knowledge as **untrusted input** to the reading agent (defending
  against **memory poisoning / prompt-injection-into-a-knowledge-record**). At minimum for MVP:
  provenance is surfaced to readers, writes are scoped to the writer's authorization, and a
  record cannot silently impersonate another principal. *(MVP — Challenger F7; see NFR-SEC6.)*

> **Open trade — build vs integrate (Challenger F13, OQ10).** That memory is **first-class is LOCKED**;
> **how it is built is open** (per OQ6, the *shape* is open). Building a memory store in-house vs
> wrapping a proven one (e.g. `pgvector`, `sqlite-vss`) is a genuine trade — in-house = full control
> over the FR-E6/E7 trust model; integrate = faster, battle-tested storage but a dependency to bend to
> the provenance/authorization requirements. Carried as an open question (§12 OQ10) for Architecture;
> not resolved here and **not** a reopening of the locked first-class-memory decision.

### 9.4 Sandbox & workspace (Theme C — P1 first light)
- **FR-C1** The system SHALL run each agent Run in an isolated sandbox drawn from a **warm pool** so
  start latency is claim-time. *(MVP)*
- **FR-C2** Each `Project` SHALL mount a persistent workspace (source + build cache) into its
  sandboxes, persisting across Runs. *(MVP)*
- **FR-C3** Sandbox isolation SHALL be enforced (runtime chosen per ISI-2113 evidence). *(MVP)*
- **FR-C4** The warm pool SHALL be sized by an **autoscale/sizing policy**, not a fixed count, to
  balance latency against idle cost. *(MVP policy defined; tuning post-ISI-2113.)*
- **FR-C5** Concurrent Runs on the same `Project` workspace SHALL have a defined share/lock behavior
  (mechanism = Architecture, OQ5). *(MVP)*
- **FR-C6** A warm-pool sandbox reused across Runs SHALL be **reset to a clean state or torn down and
  replaced** between Runs so that no filesystem, in-memory, credential, or scratch state bleeds from
  one Run — or one principal — into the next. Workspace/PVC access SHALL be **scoped per principal**,
  not merely per `Project`, so a shared workspace cannot expose one user's data to another agent's
  Run. This is a **security** requirement (D7, NFR-SEC5), not only warm-pool economics. *(MVP —
  Challenger F6.)*

### 9.5 Agent shims & A2A (Theme D — P1 ecosystem)
- **FR-D1** The system SHALL invoke agents **southbound over A2A** (Agent Card capability discovery,
  task lifecycle, artifacts, SSE progress). *(MVP)*
- **FR-D2** Each runtime SHALL integrate via a **shim** translating A2A ⇄ native invocation, one shim
  per runtime. *(MVP)*
- **FR-D3** **OpenClaw and Hermes** shims SHALL ship at v1; Claude Code and OpenCode SHALL follow.
  *(MVP: OpenClaw + Hermes; Phase 2 roadmap: Claude Code, OpenCode.)*
- **FR-D4** Runtime capability gaps (streaming, tool-calls, interactive prompts) SHALL be expressed
  as **capability flags on the Agent Card**, and the core SHALL treat them as first-class — not
  special-cased hacks. *(MVP)*
- **FR-D5** The shim contract SHALL be accompanied by a **conformance test suite** a vendor can run
  independently (suite owned by ISI-2114). *(MVP)*

### 9.6 Operator console (Theme F — P1 adoption, UX mandate)
- **FR-F1** The console SHALL show all squads at a glance (Teams, their Projects, and Run status).
  *(MVP)*
- **FR-F2** The console SHALL stream **live Run progress via SSE**. *(MVP)*
- **FR-F3** The console SHALL let an operator inspect a Run's **artifacts** and handoff outputs.
  *(MVP)*
- **FR-F4** The console SHALL let an operator **cancel/kill** a Run (satisfying FR-A6 from the UI).
  *(MVP)*
- **FR-F5** The console SHALL let a squad author **compose** `Team`/`Agent`/`Role`/`Skill`/`Project`
  resources (create/edit). *(MVP — create/edit of core CRDs.)*
- **FR-F6** The console SHALL surface **credential/auth state** for agents, including a clear signal
  when a Run is paused on an expired token (supports S10). *(MVP)*
- **FR-F7** The console SHALL support both **dark and light modes** as a v1 requirement, with a
  coherent visual system across both and respect for the operator's OS/browser preference. *(MVP —
  ISI-2150; visual direction delegated to the Graphic Designer, §11.4.)*
- **Scope guard (revised r3):** the console is a **legibility + composition + operational-visibility**
  surface. The r3 additions stay inside that boundary: the dashboard (Theme I) is an **operational
  dashboard** (health, throughput, cost), **not** a general BI / custom-query tool; the build browser
  (Theme K) is a **read-only** file/diff/code *viewer*, **not** an IDE or code editor. The console
  remains **not an IDE, not a code editor, and not a general dashboarding tool** (guards R6, R15).

### 9.7 Credential model (Theme G — P1 enterprise unlock, LOCKED)
- **FR-G1** Each `Agent` SHALL reference credentials via **per-user Kubernetes Secret refs**
  (BYO subscription); KSquad SHALL NOT store a shared master credential. *(MVP)*
- **FR-G2** The system SHALL support token acquisition **per runtime**, and the credential model SHALL
  be runtime-neutral by construction — **not Claude-shaped** (Challenger F15). At least **two concrete,
  distinct credential stories SHALL ship at v1**, one per launch runtime (S6):
  - **Claude-family runtime:** `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`, held as a per-user
    Secret ref (subscription-OAuth lifecycle, gated on ISI-2112).
  - **Second launch runtime (OpenClaw or Hermes — a non-Claude runtime):** its own concrete
    acquisition path — the default vendor-neutral pattern is a **long-lived API key / provider token
    supplied as a per-user Kubernetes Secret ref** (no interactive OAuth setup step), with the exact
    token type and any refresh semantics pinned per that runtime's auth model (OQ11).
  The shim contract (FR-D*) SHALL expose credential *type* and *lifecycle* as capability metadata so the
  core never hard-codes one vendor's auth flow. *(MVP — Challenger F15, coherence with the
  vendor-neutral moat.)*
- **FR-G3** On credential expiry/rotation mid-Run, the system SHALL **pause the Run gracefully**,
  signal the operator (FR-F6), and resume on refresh — never fail opaquely. This SHALL hold for both
  OAuth-refresh (Claude-family) and static/API-key (second-runtime) credential models. *(MVP; refresh
  UX for the OAuth case gated on ISI-2112, R1/OQ1.)*

### 9.8 Source-control sync — GitHub-first (Theme H — r3, ISI-2145)
> Syncs an external source-control system into KSquad. **GitHub is the v1 target**; the connector is
> written against a **provider seam** so a second provider (GitLab/Gitea) is a fast-follow, not a
> rewrite. This feeds the coordination record (§6.2) — it does not create a parallel one.
- **FR-H1** The system SHALL sync **external issues ⇄ work items**: a GitHub issue can create/update a
  KSquad work item, and a work-item state change can be reflected back to the linked GitHub issue.
  *(MVP — GitHub.)*
- **FR-H2** The system SHALL surface, per linked item/Run, **PR status, CI results, and produced
  artifacts** from the source-control provider, visible in the console (Theme F / build browser Theme
  K). *(MVP — GitHub.)*
- **FR-H3** The sync SHALL operate by **webhook (push) with polling as a fallback/reconciliation
  path**, so it is correct even when a webhook is missed. *(MVP.)*
- **FR-H4** The connector SHALL authenticate to the provider using **per-project/per-user BYO
  credentials via Kubernetes Secret refs** (consistent with FR-G1); KSquad SHALL NOT hold a shared
  master source-control token. Inbound webhooks SHALL be **signature-verified** before mutating state
  (D8). *(MVP.)*
- **FR-H5** Content ingested from the provider (issue/PR/comment bodies, CI output) SHALL be treated as
  **untrusted input** when read by an agent (D8, NFR-SEC8), and each synced work item SHALL carry its
  **external provenance** (origin repo/issue, sync connector identity). *(MVP.)*
- **Scope guard:** v1 is **GitHub** and the issue⇄work-item + PR/CI/artifact-status surface.
  Bidirectional conflict-resolution semantics and loop-prevention are Architecture (OQ13); multi-provider
  and deep two-way field mapping are Phase 2.

### 9.9 Operational dashboard & cost/throughput metering (Theme I — r3, ISI-2146)
> A **scoped operational dashboard**, not a BI tool (see the revised console scope guard, R15).
- **FR-I1** The console SHALL provide a **dashboard** showing **project/squad health** and **work-item
  throughput** (e.g. items opened/claimed/closed, Runs in flight / succeeded / failed) over time.
  *(MVP.)*
- **FR-I2** The dashboard SHALL show **token/cost consumption**, attributable at least along the axes
  **per user, per agent, per Run, and per Project**. *(MVP — attribution axes are the requirement;
  cost precision is bounded by what each runtime reports, OQ14.)*
- **FR-I3** Consumption/throughput data SHALL be derived from the coordination record and Run lifecycle
  signals (NFR-OBS2/OBS3), **not** from a separate agent self-report an agent could forge. *(MVP —
  provenance of metering.)*
- **Scope guard:** operational visibility over KSquad's own entities (Projects, Runs, work items,
  agents, cost). **Not** a general/custom-query analytics product, **not** external-metrics ingestion.

### 9.10 Per-Project discussion room (Theme J — r3, ISI-2147) — collaboration surface, NOT coordination
> **LOCKED-DECISION-ADJACENT.** Read §6.1 first: this is a *third surface* (collaboration), fenced off
> from the two coordination/knowledge *records*. The locked no-P2P-coordination decision is **unchanged**.
- **FR-J1** Each `Project` SHALL provide a **discussion room** where **humans and agents** can post
  messages, scoped to that `Project`. *(MVP.)*
- **FR-J2** The room SHALL be a **collaboration surface for human-in-the-loop interaction** (humans
  steering/asking the squad; agents surfacing questions or explanations to humans). It SHALL NOT carry
  **checkout/claim/handoff** semantics and SHALL NOT be a coordination channel between agents — agent
  coordination stays in work items (FR-B1/B3, §6.1). *(MVP — hard boundary.)*
- **FR-J3** Room messages SHALL be **attributed** to their author (human principal or agent/Run) and
  SHALL NOT be treated by agents as an authoritative source of truth; durable decisions produced in the
  room are written to a work item or memory by an authorized principal (§6.1). *(MVP.)*
- **FR-J4** The room SHALL be `Project`-scoped and SHALL NOT leak across tenancy boundaries (NFR-SEC7).
  *(MVP.)*
- **Scope guard:** the room is conversational and human-anchored. It is explicitly **not** the coordination
  record and **not** the knowledge record. Anti-pattern designed out, not merely discouraged (R13).

### 9.11 Build browser (Theme K — r3, ISI-2148)
- **FR-K1** The console SHALL provide a **build browser** that, per `Run`, lets an operator view the
  **files** the Run touched/produced, **diffs**, and a **read-only code view**. *(MVP.)*
- **FR-K2** The build browser SHALL source its content from the Run's workspace/artifacts and (where
  linked) the source-control PR/diff (Theme H), attributed to the Run that produced it. *(MVP.)*
- **Scope guard:** **read-only** viewing (files, diffs, code). It is **not** an editor and **not** an
  IDE — no in-console editing, no execution (guards R15).

### 9.12 Install & cluster exposure (Theme L — r3, ISI-2149)
> Makes the S1 "install in an afternoon" acceptance test concrete and testable at the cluster edge.
- **FR-L1** The Helm install SHALL expose the operator console (and any required ingress endpoints) via
  the **Kubernetes Gateway API**, with sane, documented defaults. *(MVP — replaces ad-hoc Ingress
  assumptions; exact GatewayClass/TLS = Architecture, OQ16.)*
- **FR-L2** The Helm install SHALL require an **explicit StorageClass** for persistent workspaces/PVCs
  (FR-A2/C2) — configurable, with the requirement surfaced clearly at install time rather than relying
  on an implicit cluster default. *(MVP.)*
- **FR-L3** These install requirements SHALL be part of the **S1 day-one install acceptance test**: a
  platform engineer following docs alone provisions Gateway API exposure and a named StorageClass and
  reaches a first running squad in ≤ 4h. *(MVP — extends S1, NFR-USE1.)*

---

## 10. Non-Functional Requirements

Only NFRs that matter for KSquad are listed (selective by design).

### 10.1 Security & isolation (highest priority)
- **NFR-SEC1** Cross-squad isolation SHALL be enforced by Kubernetes primitives (namespaces, RBAC,
  NetworkPolicy, Secrets, PVCs); a Run SHALL NOT access another squad's workspace, secrets, or
  network. Verified by an explicit isolation/blast-radius test (S4).
- **NFR-SEC2** Agent code runs untrusted; the sandbox runtime SHALL provide strong isolation
  (Kata/gVisor decision per ISI-2113); `runc`-only is acceptable **only** if the benchmark shows it
  meets the isolation bar.
- **NFR-SEC3** Credentials SHALL never be logged, echoed into artifacts, or exposed cross-squad.
- **NFR-SEC4** Egress SHALL be governable per squad (NetworkPolicy allowlist and/or egress proxy —
  OQ4).
- **NFR-SEC5** Warm-pool sandboxes and persistent workspaces SHALL NOT leak state across Runs or
  principals: a reused sandbox SHALL be reset/replaced between Runs, and PVC/workspace access SHALL be
  scoped **per principal** (FR-C6, D7). Verified alongside the S4 blast-radius test with a
  reuse/residue case (a second Run on a recycled sandbox cannot read the first Run's residue).
  *(Challenger F6.)*
- **NFR-SEC6** The memory service SHALL defend against **memory poisoning / prompt-injection via
  stored knowledge**: writes are authorized and provenanced (FR-E6), reads are treated as untrusted
  input with provenance surfaced (FR-E7), and per-principal trust boundaries bound cross-agent
  influence. A hostile write by one agent SHALL NOT silently steer another agent as trusted context.
  *(Challenger F7 — a first-class threat, tested, not asserted.)*
- **NFR-SEC7** The per-Project discussion room (Theme J) SHALL be `Project`-scoped, author-attributed,
  and SHALL NOT cross tenancy boundaries; it SHALL carry no checkout/claim semantics and SHALL NOT be a
  path for agent-to-agent coordination (enforces the §6.1 fence). *(r3 — ISI-2147.)*
- **NFR-SEC8** Source-control sync (Theme H) SHALL authenticate the provider connection via BYO Secret
  ref (no shared master token), **verify inbound webhook signatures** before mutating state, and treat
  all ingested external content as untrusted input (D8). Sync-connector credentials SHALL never be
  logged or exposed cross-tenant. *(r3 — ISI-2145.)*

### 10.2 Reliability & recoverability
- **NFR-REL1** No committed coordination state SHALL be lost on sandbox/agent/controller failure
  (durability of the coordination record; S8).
- **NFR-REL2** A `Run` SHALL be resumable/retryable with backoff after transient failure.
- **NFR-REL3** Memory-service writes SHALL be durable; a crashed agent SHALL NOT corrupt the
  knowledge record.

### 10.3 Performance & latency
- **NFR-PERF1** `Run` start latency SHALL be dominated by **claim time**, not sandbox cold-boot
  (numeric target set against ISI-2113; S9).
- **NFR-PERF2** Console live progress (SSE) SHALL reflect Run state changes with low, human-imperceptible
  lag under normal load (target confirmed in Architecture).

### 10.4 Scalability & multi-tenancy
- **NFR-SCALE1** Squads SHALL be independently schedulable; adding squads SHALL NOT require
  control-plane redesign (multi-tenancy boundary per OQ7).
- **NFR-SCALE2** The warm pool SHALL scale by policy (FR-C4) to bound idle cost while protecting
  latency (economics risk R2).

### 10.5 Usability & installability
- **NFR-USE1** Install SHALL be Helm + CRDs with sane defaults; first squad running in ≤ 4h (S1). The
  install SHALL expose the console via the **Gateway API** and require an **explicit StorageClass**
  (FR-L1/L2), both documented and part of the S1 acceptance test. *(r3 — ISI-2149.)*
- **NFR-USE2** The console SHALL target **polished UI/UX** (kickoff mandate): coherent visual system,
  responsive, accessible enough for daily operator use, and SHALL ship **both dark and light modes** at
  v1 (FR-F7) with a coherent system across both. Detailed UX/visual direction is delegated to the
  Graphic Designer (§11.4). *(r3 theming — ISI-2150.)*

### 10.6 Extensibility & interoperability
- **NFR-EXT1** Adding a new runtime SHALL require only a conformant shim, **zero core changes** (S5).
- **NFR-EXT2** Tool access SHALL be via MCP; agent invocation via A2A — no bespoke lateral protocols.

### 10.7 Observability & auditability
- **NFR-OBS1** The coordination record SHALL serve as a queryable audit trail (D4).
- **NFR-OBS2** Runs SHALL emit progress/lifecycle signals consumable by the console (SSE) and by
  operators (logs/metrics; detail in Architecture).
- **NFR-OBS3** The system SHALL emit **cost/token and throughput metering** signals sufficient to
  attribute consumption per user / agent / Run / Project (FR-I2), derived from Run lifecycle and the
  coordination record rather than forgeable agent self-report (FR-I3). Metering accuracy is bounded by
  what each runtime reports (OQ14). *(r3 — ISI-2146.)*

---

## 11. Scope — MVP, Roadmap, and Out-of-Scope

### 11.1 MVP philosophy
**Platform-validation MVP.** The MVP must prove the *coherent bet* end-to-end: one real squad, two
real runtimes, on one real repo, safely isolated, coordinating via work items, compounding via
memory, legible in the console, installable in an afternoon by a design partner. Feature breadth is
subordinate to proving that spine works and holds together.

### 11.2 Phase 1 — MVP / first light (v1)
Anchored on the brainstorming prioritization (§5): the two P0 spines + P0 differentiator + the P1s
required to run *anything* safely and legibly.

- **Spine:** FR-A1…A6 (CRDs + reconcile + kill), FR-B1…B4 (work items + checkout + audit).
  **Cost note (Challenger F8):** the coordination spine's checkout/claim/**lease** + concurrency
  (FR-B2) is a **from-scratch distributed-systems build in Go** and the most correctness-critical MVP
  component — it is a **foundational engineering track**, not a spine checkbox. Sequence it early and
  weight v1 estimates accordingly; it, not memory, is where the hard engineering risk concentrates
  (R10, OQ9).
- **Differentiator:** FR-E1…E5 (first-class memory). **MVP memory subset (resolves OQ6, provisional
  → CEO/Architecture to confirm):** semantic search + per-agent diary exposed via MCP tools;
  knowledge-graph relations are a **fast-follow**, not a v1 blocker.
- **First light:** FR-C1…C5 (warm-pool sandbox + per-project PVC), FR-G1…G3 (BYO credentials).
- **Ecosystem:** FR-D1…D5 with **OpenClaw + Hermes** shims and the conformance suite.
- **Adoption:** FR-F1…F7 (console: view squads/runs, live SSE, artifacts, kill, compose CRDs,
  credential state, **dark/light mode**).
- **r3 — CEO integration/legibility additions (ISI-2145..2150):**
  - **Source-control sync, GitHub-first** — FR-H1…H5 (issues⇄work items, PR/CI/artifact status, webhook
    +poll, BYO-Secret creds).
  - **Operational dashboard + cost/throughput metering** — FR-I1…I3 (health, throughput, cost per
    user/agent/Run/Project).
  - **Per-Project discussion room** — FR-J1…J4 (collaboration surface, fenced from coordination — §6.1).
  - **Build browser** — FR-K1…K2 (read-only per-Run files/diffs/code view).
  - **Install & exposure** — FR-L1…L3 (Gateway API exposure + explicit StorageClass, part of S1).
- **Named design partner + day-one install acceptance test (resolves OQ8):** Paperclip platform team
  (internal, confirmed at CEO Gate 1); S1 now includes the FR-L1/L2 exposure+storage acceptance.

> **Scope-impact honesty (r3).** The six CEO additions are real MVP scope growth on top of an already
> lean platform-validation MVP. Two (**FR-L install/exposure**, **FR-F7 theming**) the CEO scoped as
> v1 explicitly and they are low-risk. The other four are **console/integration surface** that lands
> *around* the spine, not on the correctness-critical path (the R10 coordination-spine build is still
> where the hard engineering risk sits). Recommended v1 cut, **for CEO to confirm at re-review**: ship
> **FR-H (GitHub only)**, **FR-I (the four attribution axes; cost precision best-effort per OQ14)**,
> **FR-J (room with the §6.1 fence)**, and **FR-K (read-only viewer)** as v1, with multi-provider sync,
> deep two-way field mapping, and richer analytics deferred to Phase 2. If v1 timeline pressure forces a
> cut, the honest order to defer is **K → I-depth → H-breadth**; **J's fence and L's install acceptance
> should not be cut** (J because it touches a locked decision and must ship fenced-or-not-at-all; L
> because it gates S1). Flagged for the CEO gate, not silently absorbed.

### 11.3 Phase 2+ — Growth & Vision (post-v1, out of MVP)
- Additional shims: **Claude Code, OpenCode** (then vendor-contributed).
- Memory: knowledge-graph relations promoted to first-class; richer recall/ranking.
- Console growth: deeper artifact diffing, richer composition ergonomics (still not an IDE).
- **Parked provocations (P2, revisit post-v1):** nested squads ("squads that hire squads"),
  deterministic **Run replay from the memory log**, self-scoring quality gates, a Run marketplace.

### 11.4 Operator-console UX direction (delegated)
The Node console's "polished UI/UX" mandate (NFR-USE2) requires dedicated UX/visual direction beyond
the capability contract. **Delegated to the Graphic Designer** as a parallel child issue (see §14) to
produce console UX/visual direction — information architecture, key screens (squad overview, live Run
stream, artifact inspection, compose flow, credential/auth state, **the operational dashboard (I), the
discussion room (J), and the build browser (K)**), a **dark + light visual system** (FR-F7), and a
coherent visual system — feeding Phase 3 (Architecture, frontend approach) and Phase 4 (Epics). This
does **not** block the PRD or the CEO gate; it runs in parallel and lands before/with Architecture.
*(r3 expands this brief to the new console surfaces; a follow-up note goes to the Graphic Designer's
ISI-2126.)*

### 11.5 Explicitly OUT OF SCOPE
- **A2A P2P chat for coordination** — *out of scope by locked decision.* Coordination is shared work
  items only. No lateral agent-to-agent channel exists (structurally enforced — I4).
- **Fork of Paperclip** — KSquad is a fresh Go/Node codebase; ISI-2111 is historical context, not a
  base.
- **KSquad holding shared/master credentials** — excluded by the BYO-subscription decision.
- **Bring-your-own external memory as the primary store** — memory is first-class; external stores are
  not the v1 model.
- **Message bus / blackboard / tuple-space coordination** — rejected in Phase 1 (§6.2); not in scope.
- **The discussion room as a coordination channel** — the room (Theme J) is a human-in-the-loop
  *collaboration* surface only; agent coordination stays in work items. Using it for agent-to-agent
  handoff is out of scope by locked decision (§6.1). *(r3.)*
- **The console as an IDE / code editor** — the build browser (Theme K) is **read-only**; no in-console
  editing or execution. Scope guard on R15. *(r3 — refines R6.)*
- **A general BI / custom-query analytics product** — the dashboard (Theme I) is a scoped operational
  view over KSquad's own entities, not a general dashboarding tool. *(r3 — refines R6.)*
- **Multi-provider source-control sync at v1** — v1 is **GitHub only** (Theme H); GitLab/Gitea and deep
  two-way field mapping are Phase 2. *(r3.)*
- **Single-vendor (Claude-only) platform** — agent-agnosticism is the point; excluded.

---

## 12. Open Questions & Routing

PRD-owned questions are answered above (as noted); Architecture-owned questions are routed, not
resolved here.

| # | Question | Owner | Disposition in this PRD |
|---|----------|-------|-------------------------|
| **OQ1** | `claude setup-token` OAuth longevity + mid-Run refresh UX | **PRD + ISI-2112** | Requirement stated (FR-G3, S10, R1) as *graceful pause + resume on refresh*; **exact refresh UX gated on ISI-2112 evidence** — flagged as a watch item (§13). |
| **OQ6** | Memory server shape + MVP subset + MCP tool surface | **PRD** | Answered provisionally (§11.2): MVP = semantic search + per-agent diary via MCP; KG relations fast-follow. **CEO/Architecture to confirm the cut.** |
| **OQ7** | Multi-tenancy boundary — is a squad a namespace? RBAC/quota → `Team` mapping | **PRD → Architecture** | Direction set: squads are tenancy boundaries enforced by K8s primitives (NFR-SEC1, NFR-SCALE1). **Exact namespace/`Team` mapping = Architecture.** |
| **OQ8** | Named design partner + day-one install acceptance test | **PRD** | Acceptance test defined (S1: ≤4h install-to-first-squad). **Design-partner name to be set at the CEO gate** (§11.5) — the one input this PRD cannot self-supply. |
| OQ2 | Kata vs gVisor vs runc claim latency + pool sizing | ISI-2113 → Architecture | Routed; NFR-SEC2, FR-C3/C4, NFR-PERF1 depend on it. |
| OQ3 | Exact shim contract + conformance assertions | ISI-2114 → Architecture | Routed; FR-D4/D5 depend on it. |
| OQ4 | Egress model (NetworkPolicy vs proxy) | Architecture | Routed; NFR-SEC4, D5. |
| OQ5 | Workspace persistence + concurrent-Run share/lock | Architecture | Routed; FR-C2/C5. |
| OQ9 | Coordination-spine mechanism + consistency model: how checkout/claim/lease + concurrency (FR-B2) is built correctly in Go (double-claim under contention, crash-reclaim, idempotent reconcile) | Architecture → Epics | **New (Challenger F8).** Routed; foundational track, R10. Backing store + concurrency primitive = Architecture. |
| OQ10 | Memory service: build in-house vs integrate a proven store (`pgvector`/`sqlite-vss`) while still satisfying FR-E6/E7 provenance + trust model | Architecture | **New (Challenger F13).** First-class memory is LOCKED; *implementation shape* is open (per OQ6). Routed, not resolved here. |
| OQ11 | Second launch runtime's concrete credential model (token type + refresh semantics for the non-Claude runtime), so the credential story is vendor-neutral, not Claude-shaped | PRD → Architecture | **New (Challenger F15).** Default pattern set (API-key-in-Secret, FR-G2); exact per-runtime token type/refresh pinned in Architecture. |
| OQ12 | A2A / MCP external-spec drift: how the protocol surface is version-pinned and isolated behind the shim/adapter seam so upstream churn does not reach core | Architecture | **New (Challenger F9).** Routed; isolation strategy = Architecture; tracked as risk R11. |
| OQ13 | Source-control sync bidirectionality, conflict resolution, and loop-prevention (issue⇄work-item echo) | Architecture | **New (r3, ISI-2145).** Direction set (§6.2): synced items are coordination-record work items with external provenance; webhook+poll (FR-H3). Exact conflict/loop model = Architecture. |
| OQ14 | Cost/token metering data source across heterogeneous runtimes — how per-user/agent/Run/Project token+cost is measured when each runtime reports differently (or not at all) | PRD → Architecture | **New (r3, ISI-2146).** Requirement is the attribution axes + non-forgeable provenance (FR-I2/I3, NFR-OBS3); precision bound and per-runtime source = Architecture. |
| OQ15 | Discussion-room storage/persistence and how it stays structurally distinct from the coordination and knowledge records | Architecture | **New (r3, ISI-2147).** Boundary set (§6.1): third surface, no checkout/claim, not authoritative. Backing store + enforcement mechanism = Architecture. |
| OQ16 | Gateway API exposure specifics — GatewayClass choice, TLS, and how defaults keep the ≤4h install true across clusters that may not have a Gateway controller | Architecture | **New (r3, ISI-2149).** Requirement set (FR-L1, NFR-USE1); implementation + fallback for Gateway-less clusters = Architecture. |
| OQ17 | Build-browser content source — workspace PVC vs git/PR diff vs artifact store, and read-only access scoping per principal | Architecture | **New (r3, ISI-2148).** Requirement set (FR-K1/K2, read-only). Source + per-principal access model = Architecture (aligns with FR-C6/NFR-SEC5). |

---

## 13. ⚠ Escalations & Watch Items

- **Escalations required: none.** Every requirement builds on the locked decisions; the Phase 1
  Challenger pass tested each locked decision adversarially and each held on the merits.
- **Watch item (not an escalation) — carried from Phase 1:** if **ISI-2112** shows subscription-token
  lifecycle is unworkable at scale, the **BYO-subscription** decision (G) comes under pressure. That
  would be a **CEO-gate conversation** — flagged here pre-emptively so it is not a surprise at Phase 3.
- **Challenger review landed (ISI-2121 → ISI-2125):** the independent adversarial review returned
  **CONDITIONAL PASS**. Its findings (F1–F20) are folded into this **r2 revision** — new/hardened
  requirements (FR-B2 lease, FR-C6, FR-E6/E7, FR-G2 second-runtime), new NFRs (SEC5/SEC6), new domain
  constraints (D6/D7), new risks (R9–R11) and open questions (OQ9–OQ12), and the differentiation
  reframing (§1, §8). See the finding→change map in **§13.2**. This revision does **not** reopen a
  locked decision; it sharpens the security, cost, and positioning framing on top of them.
- **Two items flagged for the CEO gate (Challenger F5, F16):** the Challenger will raise these with
  BigBoss directly. **(F5)** *Memory is parity with Sympozium, not a moat* — a framing/investment call
  the CEO should ratify (reflected in §1, §8 I3). **(F16)** *The memory-vs-no-P2P trust boundary* —
  the read/write boundary is now defined in §6; the CEO should confirm the stance that memory is a
  provenanced knowledge record, never a coordination back-channel. Both are framing/ratification
  items, not blockers to the requirements in this revision.
- **r3 folded in (ISI-2152 ← CEO requirements ISI-2145..2150):** six new requirements added as Themes
  H/I/J/K/L, FR-F7, NFRs SEC7/SEC8/OBS3/USE updates, domain D8, OQ13–OQ17, risks R13–R17. See the
  requirement→change map in **§13.3**. **No locked decision is reopened.** One item is a **CEO-gate
  ratification item** (below).
- **One r3 item flagged for the CEO gate — the discussion room fence (ISI-2147):** the per-Project
  discussion room sits adjacent to the LOCKED *no-P2P-coordination* and *two-records* decisions. The
  PRD fences it as a **third surface — collaboration, not coordination** (§6.1, FR-J2, NFR-SEC7). The
  CEO should **confirm this fence** (agents coordinate only via work items; the room never carries
  checkout/claim/handoff). This is a ratification of an already-locked stance, not a reopening — but
  because a discussion room is *exactly* the shape the locked decisions guard against, it is called out
  explicitly rather than absorbed silently. **Recommendation:** if the fence cannot hold in
  Architecture, ship the room read-mostly (humans post; agents read + reply to humans only) rather than
  weaken FR-B3.
- **Scope-growth watch item (not an escalation):** r3 adds real MVP scope (§11.2 scope-impact note). It
  lands around the spine, not on the R10 correctness-critical path, but the CEO should confirm the v1
  cut (recommended order-to-defer: K → I-depth → H-breadth; J-fence and L-install not cuttable).

### 13.1 Risk register (Phase 1 R1–R7 + Challenger-driven R8 upgrade and R9–R12, mapped to requirements)
| # | Risk | Sev | Mitigation in this PRD |
|---|------|-----|------------------------|
| R1 | Subscription-token lifecycle breaks at scale | High | FR-G3, S10, OQ1, watch item; design for graceful pause/resume; gated on ISI-2112. |
| R2 | Warm-pool economics (idle cost vs cold-start) | High | FR-C4, NFR-SCALE2 (policy-sized pool); tuned by ISI-2113. |
| R3 | Agent-agnosticism is a leaky abstraction | High | FR-D4 capability flags + FR-D5 conformance suite; core treats gaps as first-class. |
| R4 | "We rebuilt Paperclip" | Med | I1 reconcile-not-heartbeat; §11.5 out-of-scope fork. |
| R5 | Two-records discipline erodes | Med | I4 structural enforcement; FR-B3 (no P2P), FR-E1 (only knowledge sink). |
| R6 | Console scope creep → IDE | Med | FR-F scope guard; §11.5 out-of-scope. |
| R7 | Egress/enterprise networking | Med | NFR-SEC4, D5, OQ4 (Architecture). |
| R8 | **Competitive displacement + adoption vacuum** (upgraded — Challenger F10) | **High** | Market is contested, not empty: a **funded entrant** and a credible OSS actor (**the k8sgpt author**) are in/adjacent to this space. Mitigation: lead with the three deltas (§8) not memory-parity; land the internal design partner fast (OQ8 resolved — Paperclip platform team); ship a conformance-suite ecosystem play (S5) to out-open a single-vendor incumbent. Track competitors explicitly in Architecture/GTM. |
| R9 | Memory poisoning / prompt-injection into the knowledge record | High | D6, FR-E6/E7, NFR-SEC6; writes authorized+provenanced, reads treated as untrusted, per-principal trust boundaries; tested, not asserted. (Challenger F7.) |
| R10 | Coordination-spine build cost/correctness (checkout/claim/lease + concurrency in Go, from scratch) | High | FR-B2 lease semantics; foundational engineering track (§11.2), OQ9; sequenced early, weighted in estimates; the real hard-engineering risk, not memory. (Challenger F8.) |
| R11 | External-spec churn (A2A / MCP drift) | Med | Version-pin the protocol surface and isolate it behind the shim/adapter seam so upstream changes stay at the seam, not core (OQ12); capability metadata on the Agent Card absorbs variation. (Challenger F9.) |
| R12 | Warm-pool/PVC state bleed across Runs/principals | Med | D7, FR-C6, NFR-SEC5; reset-or-teardown between Runs, per-principal PVC scoping; reuse/residue case added to the S4 blast-radius test. (Challenger F6.) |
| R13 | **Discussion room erodes the two-records discipline / becomes covert agent-to-agent P2P coordination** (r3, ISI-2147) | **High** | §6.1 fence: third surface, no checkout/claim (FR-J2), not authoritative (FR-J3), scoped+attributed (NFR-SEC7); CEO-gate ratification of the fence (§13); read-mostly fallback if the fence can't hold. Touches a locked decision — treated as first-class. |
| R14 | Source-control sync loop / duplicate work items / external-content injection via synced issues/PRs | Med | §6.2 provenance + D8 untrusted-input; webhook signature verify + poll reconciliation (FR-H3/H4/H5, NFR-SEC8); conflict/loop model routed to Architecture (OQ13). |
| R15 | Console scope creep — build browser → IDE, dashboard → BI tool | Med | Revised console scope guard (§9.6); FR-K read-only, FR-I operational-only scope guards; §11.5 out-of-scope refinements. |
| R16 | Cost/token metering inaccurate or forgeable across heterogeneous runtimes | Med | FR-I3 + NFR-OBS3 derive metering from Run lifecycle/coordination record, not agent self-report; attribution axes are the v1 requirement, precision best-effort per runtime (OQ14). |
| R17 | Gateway API / explicit-StorageClass assumptions break the ≤4h install on clusters lacking a Gateway controller or default storage | Med | FR-L1/L2 documented defaults + surfaced-at-install requirement; S1 acceptance includes it (FR-L3); Gateway-less fallback = Architecture (OQ16). |

### 13.2 Challenger finding → PRD change map (ISI-2121 → r2 via ISI-2125)
| Finding | Gist | Where folded in |
|---------|------|-----------------|
| F1–F4 | Real differentiation = shims + reconcile control plane + native durable work items | §1 (three deltas), §8 I2/I1/I4, §8 callout |
| F5 | Memory-first-class is *parity* with Sympozium, not a moat — invest accordingly | §1, §8 I3; **flagged for CEO gate** (§13) |
| F6 | Warm-pool/PVC hygiene: reset-or-teardown between Runs; PVC per principal — a security req | D7, FR-C6, NFR-SEC5, R12 |
| F7 | Memory: write-auth, provenance, per-agent trust; poisoning/prompt-injection is first-class threat | D6, FR-E6/E7, NFR-SEC6, R9 |
| F8 | Coordination spine (checkout/claim/lease + concurrency in Go) is a major from-scratch build | FR-B2 lease, §9.2 callout, §11.2 cost note, OQ9, R10 |
| F9 | External-spec churn (A2A/MCP drift) as a tracked risk with isolation strategy | OQ12, R11 |
| F10 | Competitive displacement (funded entrant, k8sgpt author) — upgrade R8 | R8 (upgraded to High) |
| F13 | Build-memory-in-house vs integrate proven store is a genuine open trade | §9.3 note, OQ10 |
| F15 | Credential model is Claude-shaped; need the second runtime's credential story concrete | FR-G2/G3, OQ11 |
| F16 | Memory-vs-no-P2P locked-decision tension — define read/write trust boundary explicitly | §6 (trust boundary); **flagged for CEO gate** (§13) |
| F20 | Name which audience wins when operator-safety and author-expressiveness collide | §5 tiebreaker (operator-safety wins) |

*Findings not individually itemized above (e.g. affirmations / already-covered points from the
CONDITIONAL PASS) required no PRD change; the addendum scoped the actionable set to the rows here.*

### 13.3 CEO r3 requirement → PRD change map (ISI-2145..2150 → r3 via ISI-2152)
| Ticket | Requirement | Where folded in |
|--------|-------------|-----------------|
| **ISI-2145** | Source-control sync (GitHub-first): issues⇄work items, PR/CI/artifact status, webhook+poll, BYO Secret creds | §6.2, D8, **Theme H (FR-H1…H5)**, NFR-SEC8, OQ13, R14 |
| **ISI-2146** | Dashboard: project health, work-item throughput, token/cost per user/agent/Run/Project | **Theme I (FR-I1…I3)**, NFR-OBS3, §9.6 scope guard, OQ14, R16 |
| **ISI-2147** | Per-Project discussion room (agents+humans; collaboration, NOT coordination — locked decision unchanged) | §6.1 (the fence), **Theme J (FR-J1…J4)**, NFR-SEC7, §11.5 out-of-scope, OQ15, R13; **CEO-gate ratification (§13)** |
| **ISI-2148** | Build browser: per-Run files, diffs, code view | **Theme K (FR-K1…K2)**, §9.6 scope guard, §11.5, OQ17, R15 |
| **ISI-2149** | Helm install: Gateway API exposure + explicit StorageClass (S1 install-story acceptance) | **Theme L (FR-L1…L3)**, NFR-USE1, S1 update, OQ16, R17 |
| **ISI-2150** | Dark + light mode as v1 console requirement | **FR-F7**, NFR-USE2, §11.4 (Graphic Designer brief) |

**Coordination with Architecture (parallel revision).** The architecture revision runs in parallel; to
keep FR↔architecture references consistent, r3 routes each new mechanism question to Architecture as an
explicit OQ rather than resolving it here: OQ13 (sync conflict/loop), OQ14 (metering source), OQ15
(room storage/distinctness), OQ16 (Gateway API specifics + Gateway-less fallback), OQ17 (build-browser
source + per-principal access). The Architect ticket is notified via the §14 handoff so the two
documents stay in lockstep.

---

## 14. Handoff & Next Steps

- **Gate:** CEO (BigBoss) approval, routed by Alfred (CTO). Per the kickoff, **no architecture work
  starts** until this PRD passes the CEO gate.
- **Parallel delegation (non-blocking):** operator-console UX/visual direction to the **Graphic
  Designer** (§11.4) — feeds Phase 3/4.
- **One input this PRD cannot self-supply:** the **named design partner** (OQ8). Recommend BigBoss
  name it at the gate; the acceptance test (S1) is otherwise fully specified.
- **Feeds forward:** Phase 3 (Architecture) inherits OQ2–OQ7, seed spikes ISI-2112/2113/2114, the
  two-records principle, and the FR/NFR contract. Phase 4 (Epics) inherits §9 as the capability
  contract and §11 as the scope boundary.
- **r2 propagation (post-CEO-gate).** CEO Gate 1 approved r1 and Architecture (ISI-2119) is already
  in flight. The Challenger-driven r2 additions must reach that work: **OQ9** (coordination-spine
  mechanism/consistency), **OQ10** (memory build-vs-integrate), **OQ11** (second-runtime credential
  model), **OQ12** (A2A/MCP drift isolation), plus the new security bar (NFR-SEC5/SEC6, D6/D7,
  FR-C6/E6/E7) and the differentiation weighting (§8 three deltas). A child issue notifies the
  Architect so r2 is consumed rather than missed (§ handoff ticket). The two CEO-gate flags (F5, F16)
  are raised by the Challenger with BigBoss directly.

---

## Appendix A — Traceability (brainstorming → PRD)

| Brainstorming | PRD |
|---------------|-----|
| §1.4 personas | §5 (four audiences + journeys) |
| Theme A | FR-A*, I1 |
| Theme B (LOCKED) | FR-B*, §6, §11.5 out-of-scope P2P |
| Theme C | FR-C*, NFR-SEC2, NFR-PERF1 |
| Theme D | FR-D*, I2, S5/S6 |
| Theme E (LOCKED) | FR-E*, I3, S7, OQ6 |
| Theme F | FR-F*, NFR-USE2, §11.4 |
| Theme G (LOCKED) | FR-G*, S10, OQ1, R1 |
| §4 two records | §6, I4 |
| §5 prioritization | §11 scope/roadmap |
| OQ1/OQ6/OQ7/OQ8 | §12 (answered/routed) |
| §6 risks R1–R8 | §13.1 (R8 upgraded; R9–R12 added from Challenger) |
| §8 zero escalations | §13 (F5/F16 flagged for CEO gate) |
| Challenger ISI-2121 F1–F20 | §13.2 finding→change map (r2 via ISI-2125) |
| CEO r3 ISI-2145 (SCM sync) | §6.2, D8, FR-H*, NFR-SEC8, OQ13, R14 |
| CEO r3 ISI-2146 (dashboard) | FR-I*, NFR-OBS3, OQ14, R16 |
| CEO r3 ISI-2147 (discussion room) | §6.1, FR-J*, NFR-SEC7, OQ15, R13 |
| CEO r3 ISI-2148 (build browser) | FR-K*, OQ17, R15 |
| CEO r3 ISI-2149 (Helm/Gateway/StorageClass) | FR-L*, NFR-USE1, S1, OQ16, R17 |
| CEO r3 ISI-2150 (dark/light mode) | FR-F7, NFR-USE2, §11.4 |
| CEO r3 ISI-2145..2150 | §13.3 requirement→change map (r3 via ISI-2152) |

---

## CEO Gate 1 Decision — 2026-08-10

**Status: APPROVED** by BigBoss (CEO).

**OQ8 resolved — Named design partner:** Paperclip platform team (internal). Acceptance test: S1 = ≤4h install-to-first-squad on a conformant cluster, following docs alone.

**Memory MVP subset (OQ6) confirmed:** semantic search + per-agent diary via MCP tools for v1; KG relations are a fast-follow.

**Next:** Phase 3 Architecture (ISI-2119) is unblocked. Architecture owns OQ2–OQ5, OQ7, the Sympozium teardown, Node frontend approach, and memory MCP tool surface confirmation. CEO gate 2 fires after `03-architecture.md` is delivered and reviewed.

---

## CEO Gate — r3 Re-Review Requested — 2026-08-11

**Status: PENDING CEO (BigBoss) re-review.**

r3 folds the six CEO requirements ISI-2145..2150 into the PRD (see §13.3 map). Requesting BigBoss
re-review of:

1. **The discussion-room fence (ISI-2147, §6.1 / R13) — the one ratification item.** Confirm the room is
   a **collaboration surface, not coordination**: agents coordinate only via work items (FR-B3);
   the room carries no checkout/claim/handoff (FR-J2). No locked decision is reopened; this ratifies the
   stance for a feature shaped exactly like what the locked decisions guard against.
2. **The v1 scope cut (§11.2 scope-impact note).** Confirm all six ship at v1 as folded, or approve the
   recommended defer order (K → I-depth → H-breadth; **J-fence and L-install not cuttable**).
3. **Metering precision expectation (FR-I2/OQ14).** Confirm that v1 delivers the four attribution axes
   with **best-effort** cost precision (bounded by what each runtime reports), not guaranteed exact cost.

**Parallel:** the Architecture revision consumes r3's OQ13–OQ17 and the new security bar
(NFR-SEC7/SEC8, D8) — Architect notified via child issue so the two documents stay in lockstep. **Phase 4
story writing should wait on this r3 re-review** so stories are written against the ratified cut.
