---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - docs/bmad/00-kickoff-brief.md   # CEO scope + LOCKED decisions (commit 90747e3)
  - ISI-2111                         # Design doc: Squad architecture v0.1 (seed, superseded in part — see §7)
session_topic: 'KSquad — Kubernetes-native, agent-agnostic AI agent orchestration'
session_goals: 'Frame the problem, converge the idea space, surface risks/alternatives, and hand a decision-ready brief to Phase 2 (PRD)'
selected_approach: 'Analyst-led synthesis (autonomous) with an embedded Challenger pass'
techniques_used:
  - Problem framing / First Principles
  - Persona Journey (operator + squad-author + agent-vendor)
  - Idea divergence → thematic convergence
  - Assumption Reversal (Challenger)
  - Pre-Mortem (Challenger)
  - Alternatives-considered-and-rejected (Challenger)
ideas_generated: []   # captured inline as themes below rather than a flat list
session_active: false
workflow_completed: true
context_file: 'docs/bmad/00-kickoff-brief.md'
---

# Brainstorming Session Results — KSquad

**Facilitator:** Mary (Business Analyst & Brainstormer)
**Challenge pass:** embedded here; independent adversarial review delegated to Challenger (see §9)
**Date:** 2026-08-10
**Phase:** BMAD Phase 1 — Brainstorming synthesis
**Gate:** Alfred (CTO) reviews before Phase 2 (PRD) begins
**Source ticket:** ISI-2117 · **Parent:** ISI-2116 · **Program:** ISI-2115

> **Amendment note (2026-08-10, ISI-2124).** This revision incorporates the independent Challenger
> review (ISI-2121, verdict **CONDITIONAL PASS**). The Phase-1 gate already passed; these are
> **amendments, not a reopen**. Changes are surgical and localized to §6.1 (new risks R9–R12,
> severity recalibration, named decision-owners), §6.2 (corrected Sympozium competitive read),
> §8 (softened escalation posture + one locked-vs-locked tension surfaced for CEO decision), and
> minor notes in §1.4, §5, and the open questions. The core synthesis is unchanged.

> **Scope discipline.** The CEO kickoff brief (`00-kickoff-brief.md`, commit 90747e3) locks seven
> decisions (frontend Node, backend Go, first-class memory server, shared-work-item coordination,
> A2A southbound, MCP tools, BYO-subscription credentials). This document **builds on** those; it
> does not reopen them. Anything that would touch a locked decision is filed as an **⚠ ESCALATION**
> (§8), not a proposal.

---

## 1. Problem Framing

### 1.1 The core problem

Teams that want to run **multiple AI coding/ops agents as a coordinated crew** today face a false
choice:

- **SaaS orchestration platforms** (hosted "AI teammate" products) — polished, but they own your
  runtime, force a single agent vendor, and require you to hand them credentials and source code.
- **DIY glue** — scripts and queues wiring `claude`, `opencode`, and homegrown bots together, with
  no isolation model, no shared state, no reconciliation, and no operator surface.

There is no **Kubernetes-native, agent-agnostic control plane** that treats "a squad of agents
working a backlog" as a first-class, reconciled workload — the way K8s already treats Deployments,
Jobs, and CRDs. KSquad is that missing layer.

### 1.2 Why Kubernetes-native (first principles)

- **The reconciliation loop is the right primitive.** "Desired: this Run should complete against
  that Project. Observed: no sandbox is claimed." → a controller closes the gap. Agent runs are
  long-lived, fail partway, and need retry/backoff — exactly what operators are good at. This is a
  deliberate departure from Paperclip's heartbeat-adapter model (ISI-2111 §Control plane).
- **Isolation and least privilege are solved primitives.** Namespaces, RBAC, NetworkPolicy, Secrets,
  and PVCs already exist. An agent that can run arbitrary code **must** be sandboxed; K8s gives us
  the substrate instead of inventing one.
- **Multi-tenancy and scale for free.** Squads map to namespaces; scheduling, quotas, and
  horizontal scale are the cluster's job, not ours.
- **The ecosystem is the distribution channel.** CRDs + operator + Helm is how platform teams expect
  to adopt infra. This is also the AAIF-candidate posture: be a *substrate*, not a product silo.

### 1.3 Why agent-agnostic

The agent-runtime market is fragmenting fast (OpenClaw, Hermes, Claude Code, OpenCode, and more
arriving). Betting the platform on one runtime is the single biggest strategic risk. Agent-agnosticism
is the moat: **KSquad orchestrates; it does not implement the agent.** The seam is a per-runtime
**shim** translating A2A ⇄ agent-native invocation (locked: A2A southbound, MCP for tools).

### 1.4 Who the operator/user is (personas)

| Persona | Who | What they need from KSquad | Success signal |
|---------|-----|----------------------------|----------------|
| **Priya — Platform Engineer** (primary operator) | Owns the cluster and the internal dev platform. Rolls KSquad out for her org. | `kubectl`/Helm install, CRDs that feel native, RBAC/NetworkPolicy isolation, an operator console showing squads, runs, live progress, artifacts. | Installs in an afternoon; agent blast radius is bounded; she can see and kill a runaway run. |
| **Sam — Squad Author / Tech Lead** (primary user) | Defines a squad: which agents, which roles/skills, against which repo. | Declarative `Team`/`Agent`/`Role`/`Skill`/`Project` CRDs; a UI to compose them; a way to watch a Run stream and inspect handoff artifacts. | Spins up a "review + fix + test" squad on a repo without writing glue code. |
| **Dana — Agent-runtime vendor / OSS integrator** (ecosystem) | Wants their runtime to run inside KSquad. | A documented **shim contract** (A2A Agent Card in, agent-native invocation out) + conformance tests. | Ships a shim for their runtime in days; it appears in squads unchanged. |
| **Morgan — the agent itself** ("user" of the coordination surface) | Executes work, checks out items, files comments/artifacts. | A shared-work-item API (issues/comments/checkout) + memory server + MCP tools. **Not** a P2P chat channel. | Coordinates through durable state, so a crashed agent loses nothing. |

**Framing insight:** KSquad has *four* audiences, and they pull in different directions —
the operator wants **safety and legibility**, the squad author wants **expressiveness**, the vendor
wants a **stable seam**, and the agent wants **durable shared state**. The product's job is to keep
all four satisfied simultaneously; every major design tension below is a collision between two of them.

> **Amendment (F18 — the agent is also an adversarial principal).** Morgan is not only a *user* of
> the coordination surface; because agents run untrusted code, Morgan is also a **potential
> adversary**. A compromised, hallucinating, or buggy agent can poison shared memory (R10),
> contaminate a warm sandbox (R9), or abuse checkout/lease semantics (R11). Every trust boundary
> must model the agent-as-principal on both sides: trusted enough to coordinate, untrusted enough to
> sandbox and audit. Least-privilege and provenance are not optional.
>
> **Amendment (F20 — the explicit tie-breaker).** "Keep all four satisfied simultaneously" is the
> goal, but the collisions are real and need a *declared winner* so design isn't ad hoc. When
> **operator-safety (Priya)** and **author-expressiveness (Sam)** collide, **operator-safety wins** —
> it is the enterprise-adoption gate and the blast-radius constraint, and an unsafe-but-expressive
> platform is a non-starter for the primary operator. Expressiveness is maximized *within* the safety
> envelope, never at its expense. (The vendor-seam and agent-state audiences rarely collide head-on
> with safety; when they do, the same rule applies — safety first.)

---

## 2. Idea Space Explored

Ideas were generated across four orthogonal domains (technical / operator-UX / ecosystem /
failure-modes) to resist semantic clustering, then converged into the themes in §3. Highlights of
the divergent pass:

- **Squads as namespaces vs. squads as label selectors vs. squads as a `Team` CRD** → converged on
  `Team` CRD (legible, RBAC-anchorable). (Theme A)
- Coordination substrate: shared work items vs. message bus vs. blackboard/tuple-space vs. A2A P2P
  chat → **shared work items** (locked). (Theme B)
- Sandbox lifecycle: cold-start per run vs. **warm pool** vs. persistent per-squad pods → warm pool
  with per-project PVC (locked-adjacent, from ISI-2111). (Theme C)
- Shim packaging: sidecar vs. init-translate vs. standalone Deployment vs. WASM plugin → sidecar/
  Deployment per runtime, thin A2A translator. (Theme D)
- Memory server shape: vector store vs. knowledge-graph + diary vs. shared work-item log vs. all
  three → **first-class multi-modal memory service** (locked as first-class; shape is open). (Theme E)
- Operator console: read-only dashboard vs. full CRUD vs. "IDE for squads" → polished console with
  live SSE run streams + artifact inspection (per kickoff UX note). (Theme F)
- Credentials: shared service account vs. **BYO-subscription per-user Secret refs** → BYO (locked). (Theme G)
- Egress: open vs. per-squad NetworkPolicy allowlist vs. egress proxy → policy + proxy (open Q). (Theme C/H)
- Provocations parked for later phases: "squads that hire squads" (nested Teams), "a Run marketplace,"
  "self-scoring squads" (quality gates), "replay a Run deterministically from the memory log."

---

## 3. Ideas Converged — The Six Themes

### Theme A — Squads as first-class, reconciled teams
A **`Team` CRD** groups `Agent`s bound to `Role`s and `Skill`s, scoped to one or more `Project`s
(workspace PVC + GitHub repo). A `Run` is the unit of work a squad executes; a controller reconciles
`Run` → sandbox claim → agent invocation → artifacts. This is the spine of the product and the
direct descendant of ISI-2111's CRD model (`Team, Agent, Role, Skill, Project, Run`).
**Why it wins:** everything else (RBAC, UI, quotas, audit) hangs off legible CRDs.

### Theme B — Shared work items as the *only* coordination channel *(builds on LOCKED)*
Agents coordinate exclusively through **durable shared work items** — issues, comments, checkout/
claim semantics — never through direct A2A P2P chat. This is Paperclip's proven coordination model
(and the reason KSquad is "inspired by, not a fork of" Paperclip).
**Why it wins:** durability (a crashed agent resumes from state), auditability (the work log *is* the
record), and testability (coordination is inspectable data, not ephemeral messages). A2A is used
**southbound** (control-plane → agent) for the task lifecycle, *not* agent-to-agent laterally.

### Theme C — Warm-pool sandboxes with per-project workspace PVCs
An **AgentSandbox-style warm pool** keeps pre-initialized sandboxes ready so `Run` start latency is
claim-time, not cold-boot-time. Each `Project` gets a workspace **PVC** mounted into the sandbox
(source + build cache persist across runs). Runtime isolation (**Kata vs gVisor**) is under evaluation
— seed spike **ISI-2113** owns the claim-latency benchmark that decides this; this doc does not
pre-empt it.
**Why it wins:** agents run untrusted code; warm pools make strong isolation affordable on the
latency budget.

### Theme D — Agent shims: OpenClaw + Hermes first
One **shim per runtime** translates A2A (Agent Card capability discovery, task lifecycle, artifacts,
SSE progress) ⇄ the runtime's native invocation. **OpenClaw and Hermes ship first** (per kickoff +
ISI-2111), then Claude Code and OpenCode. The shim contract is the ecosystem seam — spec'd by seed
ticket **ISI-2114**.
**Why it wins:** agent-agnosticism (§1.3) is realized entirely at this seam; a stable shim contract
is what lets vendors self-onboard.

### Theme E — Memory server as a first-class component *(LOCKED)*
Not an external dependency — a **first-class KSquad component**. It is the squad's shared long-term
brain, complementary to (not a replacement for) the shared work-item log: work items are the
*coordination* record; memory is the *knowledge* record (facts, prior decisions, per-agent diary).
**Open shape (for PRD/arch):** knowledge-graph + semantic search + per-agent diary (the MemPalace
pattern already used across the org is a strong reference model), exposed to agents via **MCP tools**.
**Why it wins:** squads that persist knowledge across runs compound in value; it is table-stakes
over *stateless* orchestration. **Caveat (F1):** it is **not** a differentiator versus memory-equipped
prior art — Sympozium already ships a first-class memory server (§6.2). Memory is a P0 *capability we
must have*, not a moat; the moat is elsewhere (§6.2's three deltas).

### Theme F — A polished operator console
The Node frontend targets **polished UI/UX** (kickoff UX note): squads at a glance, live **SSE**
run progress, artifact inspection, and squad composition. This is the operator's legibility surface
(Priya) and the squad author's authoring surface (Sam).
**Why it wins:** legibility is the operator's #1 need; a K8s CRD platform with no good console loses
to a worse platform that has one.

### Theme G — BYO-subscription credential model *(LOCKED)*
Per-user **Secret refs on the `Agent` CRD**. `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`;
GLM/other tokens via k8s Secrets. KSquad never holds a shared master credential; each agent runs on
its principal's own subscription.
**Why it wins:** the enterprise adoption unlock — no "hand us your API keys." Token *lifecycle at
scale* is the hard part (seed spike **ISI-2112**).

---

## 4. Cross-Cutting Insight — The Two Records

The sharpest convergence of the session: KSquad maintains **two distinct durable records**, and
keeping them distinct is an architectural principle, not an accident.

1. **The coordination record** (Theme B) — work items, comments, checkout. Answers *"what is being
   done and by whom, right now."* Source of truth for reconciliation.
2. **The knowledge record** (Theme E) — the memory server. Answers *"what do we know, and what did
   we decide before."* Source of truth for agent context.

A2A (southbound) and MCP (tools) are the *transport*; these two records are the *state*. Blurring
them (e.g. letting agents chat P2P, or stuffing knowledge into comment threads) is exactly the
anti-pattern the locked decisions guard against.

> **Caveat (F16).** This clean separation has a seam: the knowledge record is *writable by agents*, so
> it is **functionally a lateral channel** — one agent can influence another by writing memory the
> other later reads, which is in tension with the no-P2P spirit of the coordination record. §8 surfaces
> this as an explicit Alfred/CEO decision (governed channel vs constrained), with write-authorization
> and provenance (R10) as the mechanism. Do not treat "two records" as having fully resolved it.

---

## 5. Prioritization (what Phase 2 should anchor on)

| Priority | Item | Rationale |
|----------|------|-----------|
| **P0 — spine** | `Team/Agent/Role/Skill/Project/Run` CRDs + reconcile loop (Theme A) | Nothing exists without it. |
| **P0 — spine** | Shared work-item coordination surface (Theme B) | The coordination record; locked. |
| **P0 — capability** | First-class memory server (Theme E) | Locked and P0, but **MVP shape is undefined** (F19): the KG/semantic-search/diary subset, the MCP tool surface, and the write-authorization/provenance model (R10) are all open (→OQ6). Not a differentiator (F1) — table-stakes vs memory-equipped prior art (§6.2). PRD must pin the MVP shape *and* the write model before build. |
| **P1 — first light** | Warm-pool sandbox + per-project PVC (Theme C) | Needed to run *anything* safely; gated on ISI-2113. |
| **P1 — ecosystem** | Shim contract + OpenClaw/Hermes shims (Theme D) | Realizes agent-agnosticism; spec'd by ISI-2114. |
| **P1 — adoption** | Polished operator console w/ live SSE (Theme F) | Operator legibility; kickoff UX mandate. |
| **P1 — enterprise unlock** | BYO-subscription credentials (Theme G) | Locked; lifecycle risk owned by ISI-2112. |
| **P2 — later** | Nested squads, Run replay from memory log, self-scoring quality gates, Run marketplace | Parked provocations; revisit post-v1. |

---

## 6. Challenger Pass — Risks, Alternatives Rejected, Open Questions

*(Embedded adversarial pass; an independent Challenger review is delegated in §9.)*

### 6.1 Top risks (pre-mortem: "KSquad failed in 18 months — why?")

| # | Risk | Severity | Mitigation / owner |
|---|------|----------|--------------------|
| R1 | **Subscription-token lifecycle breaks at scale.** OAuth tokens from `claude setup-token` expire/rotate; refreshing per-user tokens for many agents is unproven. If tokens silently die mid-run, squads fail opaquely. This is load-bearing for the entire BYO-subscription bet (G) — if it doesn't hold, a locked decision reopens. | **Critical** | Seed spike **ISI-2112** must produce longevity evidence *before* the PRD commits to the cred UX. Design for refresh + graceful run-pause on auth failure. **Decision-owner: Alfred (CTO)** — if ISI-2112 is negative, Alfred takes the BYO-vs-fallback call to the CEO gate. |
| R2 | **Warm-pool economics.** Idle warm sandboxes cost money; too few → cold-start latency returns; too many → burn. Kata vs gVisor claim latency is unmeasured. | **High** | Seed spike **ISI-2113** benchmarks claim latency; PRD needs a pool-sizing/autoscale policy, not a fixed pool. |
| R3 | **Agent-agnosticism is a leaky abstraction.** A2A + a shim contract may not cleanly cover every runtime's quirks (streaming, tool-calls, interactive prompts). The seam could leak per-runtime special cases into the core. | **High** | ISI-2114 shim spec must define a *conformance test suite*; core must treat shim gaps as first-class (capability flags on the Agent Card), not hacks. |
| R4 | **We rebuild Paperclip and call it new.** The coordination model is Paperclip's; risk of importing its complexity or, worse, its assumptions (heartbeat adapter) into a supposedly operator-native design. | **Med** | Explicit reconciliation vs ISI-2111 (§7): control plane is **operator/reconcile**, not heartbeat-adapter. Keep the coordination *contract*, drop the runtime. |
| R5 | **Two-records discipline erodes.** Under delivery pressure, teams will be tempted to let agents chat P2P or bury knowledge in comment threads — collapsing §4. | **Med** | Make it structurally hard: no lateral A2A channel exists; memory server is the only knowledge sink. Enforce in the shim contract. |
| R6 | **Operator console scope creep.** "Polished UI/UX" + "IDE for squads" ambition can swallow the roadmap. | **Med** | PRD must scope the console to legibility (view squads/runs/artifacts + compose CRDs), not become an IDE. |
| R7 | **Egress/enterprise networking.** Corporate networks block or proxy Anthropic/model endpoints; per-squad egress policy is unspecified. | **Med** | Open question OQ4; needs an egress-proxy story in arch. |
| R8 | **No design partner / adoption vacuum.** AAIF-candidate posture assumes an ecosystem shows up. If no real operator deploys it, it's a demo. | **Med** | Recommend naming ≥1 design-partner persona/team in the PRD and a "day-one install" acceptance test. **Decision-owner: John (PM).** |
| R9 | **Warm-pool + persistent-PVC cross-run contamination (F6).** A warm sandbox reused across runs — or a per-project PVC that persists between runs — can carry state forward: in-memory secrets, scratch files, git worktree residue, a poisoned build cache. One run's leftovers silently corrupt or leak into the next (cross-run, and across tenants if pooling isn't tenant-scoped). "Warm" is in direct tension with "clean." | **High** | Make **reset/teardown-between-runs a first-class requirement**, not an afterthought: define the sandbox hygiene contract (what is wiped, what legitimately persists in the PVC, how the PVC is scrubbed/namespaced). Owner: **Winston (Architect)** — folded into ISI-2113 scope + a PRD acceptance test. **Decision-owner: Alfred** on the warm-vs-clean tradeoff. |
| R10 | **Shared memory-server poisoning / write-authorization (F7).** A first-class shared memory server that *any* agent can write to is a poisoning surface: a compromised, buggy, or hallucinating agent writes false "knowledge" that later agents read and trust. No write-authorization model, no provenance/attribution, no invalidation path is defined. Compounds R9 and F18 (agent-as-adversary). | **High** | Memory writes require **authorization + provenance** (which agent/run/role asserted this fact, when) + an **invalidation** path; consider read-mostly or per-agent-partitioned defaults. Owner: **John (PM)** scopes the MVP write model (→OQ6); **Winston** designs it. See also the locked-vs-locked tension in §8 (F16). |
| R11 | **Under-building the coordination spine from scratch in Go (F8).** Checkout/lease/claim, concurrency control, and exactly-once-ish work-item semantics are **hard distributed-systems problems**. "Paperclip already does this" does **not** mean they're solved here: Paperclip is heartbeat-driven, KSquad is reconcile-driven, and the leasing/liveness semantics differ materially. Underestimating this ships a coordination layer with silent double-claims or stuck leases. | **High** | Treat lease/checkout/concurrency as a **named design workstream with its own spike and test suite**, not an assumed-solved import from Paperclip. Model liveness explicitly (lease TTL, fencing, reconcile-safe claims). Owner: **Winston (Architect)**, Phase 3 — flag for a dedicated spike if arch surfaces unknowns. |
| R12 | **External-spec churn — A2A / MCP drift (F9).** The southbound A2A contract and the MCP tool surface are **external, still-evolving specs**. Version drift upstream can break shims, the tool surface, and the conformance suite out from under us. | **Med** | **Pin** spec revisions; capability-negotiate rather than assume; have the ISI-2114 conformance suite assert against a *pinned* A2A/MCP rev and gate upgrades. Owner: **Winston** via ISI-2114. |

> **Severity band (F11).** Severities are deliberately spread, not compressed to High/Med: **R1 is
> Critical** (it can reopen a locked decision), R2/R3/R9/R10/R11 are High, the rest Med. If a later
> pass finds everything reading "High," that's a calibration smell — re-rank.
>
> **Decision-owners (F12).** Spike tickets produce *evidence*; they do not *decide*. Each load-bearing
> risk names a **human/agent decision-owner** who takes the call when evidence lands: **Alfred (CTO)**
> owns the locked-decision gates (R1, R9, and the §8 memory tension), **John (PM)** owns product-scope
> calls (R8, R10 MVP shape), **Winston (Architect)** owns the technical design calls (R3, R9, R11, R12).

### 6.2 Alternatives considered and **rejected** (with reasons)

| Alternative | Why it was tempting | Why rejected |
|-------------|--------------------|--------------|
| **A2A P2P agent chat for coordination** | Natural "agents talking to each other"; A2A supports it. | **Rejected (LOCKED).** Ephemeral, non-durable, non-auditable, untestable; loses the crashed-agent-resumes property. Shared work items win. |
| **Fork Paperclip** | Fastest path; coordination model already works. | **Rejected (kickoff).** Paperclip is heartbeat-adapter + company/agents/issues, not operator-native; wrong control-plane primitive for K8s. Fresh Go codebase instead. |
| **Message bus / blackboard / tuple-space coordination** | Classic multi-agent substrate; decoupled. | Rejected: reintroduces the non-durable, hard-to-audit problems of P2P without the legibility of work items. |
| **Single-vendor (Claude-only) platform** | Simpler; deepest integration; ship faster. | Rejected: the runtime market is fragmenting (§1.3); single-vendor lock is the #1 strategic risk. Agent-agnosticism via shims is the moat. |
| **Cold-start sandbox per run (no warm pool)** | Zero idle cost; simpler. | Rejected for interactive runs: cold-boot latency kills the operator/author experience. Warm pool (Theme C), sized by ISI-2113 evidence. |
| **Memory as an external dependency** (bring-your-own vector DB) | Less to build/own. | **Rejected (LOCKED).** Memory is first-class — it's the compounding-value differentiator and must be a supported, coherent surface, not a BYO bolt-on. |
| **Shared service-account credentials** | Simplest cred model; one token to manage. | **Rejected (LOCKED).** Kills enterprise adoption ("hand us your keys") and blast-radius containment. BYO-subscription per-user Secret refs instead. |
| **Prior art: Sympozium** (k8s-native multi-agent orchestration, "every agent is an ephemeral Pod; every skill an isolated sidecar," by the k8sgpt author) | Validates the *category* (k8s-native agentic orchestration is real and being built), and the isolated-sidecar-per-skill pattern is worth studying for Theme D shims. | **Corrected competitive read (F1–F5) — this is first-hand intel, not a spec skim.** The org has **hands-on production experience** with Sympozium: we deploy BMAD ensembles on it and have contributed OTel PRs upstream. That obligates us to be honest about the overlap, and the earlier draft got several facts wrong. See the corrected read directly below. |

> **Corrected Sympozium read (F1–F5, replaces the prior row's claims).**
> Grounded in the org's hands-on production use (BMAD ensembles deployed on Sympozium; OTel PRs
> contributed upstream), the earlier draft's competitive claims were wrong on four counts and must be
> struck:
>
> - **F1 — "first-class memory" is NOT a KSquad differentiator.** Sympozium **already ships a
>   first-class memory server**: a SQLite sidecar backing `Team.Knowledge` + per-agent seeds, exposed
>   to agents as an **injected MCP tool**, with **semantic search in flight upstream (PR #45)**. Delete
>   any claim that memory differentiates us — it's convergent prior art (see the Theme E caveat).
> - **F2 — it is multi-model-flexible, not "single-model-flexible."** Strike the single-model claim.
> - **F3 — it *has* a coordination model.** Sympozium coordinates via **Ensemble edges**,
>   **NATS result-passing**, and **Channels**. "No coordination model" is false; ours differs in
>   *kind* (durable work items vs message/result passing), not in *presence*.
> - **F4 — CRD overlap is near-direct.** Sympozium's **`Ensemble` CRD ≈ our `Team` CRD**. Name the
>   overlap honestly rather than implying the CRD framing is novel.
> - **F5 — the honest differentiation narrows to exactly three deltas.** After the corrections above,
>   KSquad's defensible differentiation versus Sympozium is **only these three**:
>     1. **Agent-runtime-agnostic shims** — a vendor-neutral A2A⇄native shim seam (Theme D). Sympozium
>        is not architected around swappable third-party agent runtimes behind a stable shim contract.
>     2. **A reconcile control plane** — desired/observed reconciliation (Theme A), versus Sympozium's
>        **delegation + NATS-result-passing** model. Different control primitive, not a UI skin.
>     3. **Native durable work items** as *the* coordination record (Theme B / §4) — versus
>        message/channel/result passing. Durability + auditability + crash-resume is the delta.
>
>   Everything else (k8s-native CRDs, isolated pods/sidecars, first-class memory, multi-model) is
>   **convergent prior art, not moat**. Do not oversell. Architect (**Winston**) owes a full,
>   evidence-based competitive teardown in Phase 3 that starts from these three deltas.

### 6.3 Open questions (for PRD / Architecture)

- **OQ1 (→ISI-2112, PRD):** What is the real longevity of `claude setup-token` OAuth tokens, and what
  is the refresh UX when one expires mid-run?
- **OQ2 (→ISI-2113, arch):** Kata vs gVisor vs runc — claim latency and isolation strength tradeoff?
  What warm-pool sizing/autoscale policy falls out of the numbers?
- **OQ3 (→ISI-2114, arch):** What is the exact shim contract, and what does its conformance suite
  assert (streaming, tool-calls, interactive prompts, capability flags)?
- **OQ4 (arch):** Egress model — per-squad NetworkPolicy allowlist, egress proxy, or both — for
  corporate networks that block model endpoints?
- **OQ5 (arch):** Workspace persistence — per-project PVC vs. artifact-sync — and how do concurrent
  runs on the same Project share/lock the workspace?
- **OQ6 (PRD):** Memory server shape — KG + semantic search + per-agent diary? What's the MVP subset,
  and what is its MCP tool surface?
- **OQ7 (PRD):** Multi-tenancy boundary — is a squad a namespace, and how do RBAC/quotas map to
  `Team`?
- **OQ8 (PRD):** Who is the named design partner, and what is the "day-one install" acceptance test?
- **OQ9 (→ISI-2113, arch — F14):** Should the sandbox model be **hybrid warm/cold**? Warm pools pay
  their keep for *interactive* runs where claim latency is felt; **batch / non-interactive** work
  (scheduled squads, bulk backlog burndown) may be better on **cold-start** sandboxes that cost
  nothing idle and sidestep the R9 contamination risk (fresh boot every time). ISI-2113 should size
  *both* regimes and define the routing rule (which run class gets warm vs cold).

---

## 7. Reconciliation with Seed Ticket ISI-2111 (Squad architecture v0.1)

This document **absorbs and partially supersedes** ISI-2111 (cited, not restated). Reconciliation:

- **Carried forward unchanged:** the CRD model (`Team/Agent/Role/Skill/Project/Run`); warm-pool
  sandbox with per-project PVC; A2A southbound + MCP tools; shim-per-runtime with **OpenClaw + Hermes
  first**; BYO-subscription credentials; shared-work-items (not P2P) coordination; **operator/
  reconcile control plane (not heartbeat-adapter)**. These are consistent with the kickoff's locked
  decisions.
- **Elevated to first-class:** the **memory server**. ISI-2111 did not treat memory as a named
  component; the kickoff locks it as first-class, and this doc makes it Theme E — a co-equal of the
  coordination surface (the "two records," §4).
- **Made explicit:** the **four-persona framing** (§1.4) and the operator-console UX mandate (Theme F),
  which ISI-2111 left implicit.
- **Deferred to spikes, not decided here:** ISI-2111's "Known hard problems" (token lifecycle,
  workspace persistence, egress, Run→sandbox scheduling) are mapped to seed spikes ISI-2112/2113/2114
  and open questions OQ1–OQ5 rather than resolved in Phase 1.
- **Status:** ISI-2111 remains a valid v0.1 design input; where this synthesis and the forthcoming
  PRD/architecture disagree with it, **the BMAD artifacts win** and ISI-2111 should be treated as
  historical context.

---

## 8. ⚠ Escalations (touching LOCKED decisions)

Per the kickoff gate rule, anything that would alter a locked decision is escalated to the CEO
(via Alfred), **not** proposed here. As of this synthesis:

- **No escalation warranted *yet* — but "yet," not "never" (F17).** Every theme builds *on* the
  locked decisions, and the Challenger pass (§6.2) tested each adversarially (P2P chat, single-vendor,
  shared-service-account creds, external memory). Each held up **on the evidence available now** —
  which is *not* the same as "confirmed on the merits." The token-lifecycle (G), warm-pool (C), and
  shim-contract (D) decisions are only **provisionally validated, pending spikes ISI-2112 / ISI-2113 /
  ISI-2114**. If any spike returns disqualifying evidence, the corresponding locked decision goes to a
  CEO gate (R1 is the sharpest such trigger). **Merits-confirmation is deferred, not granted.**
- **⚠ Decision for Alfred / CEO — a locked-vs-locked tension, surfaced not silently resolved (F16).**
  Two locked decisions are in tension:
  - **E — "first-class shared memory server"** (any agent reads/writes the squad's knowledge record), and
  - **B / §4 — "no P2P, no lateral agent-to-agent channel"** (coordination only through durable work items).
  A shared memory server that agents both read and write is **functionally a lateral information
  channel**: agent X can influence agent Y by writing memory that Y later reads. That is
  coordination-by-side-channel — precisely what the no-P2P rule exists to prevent. It doesn't violate
  the *letter* of "no A2A P2P chat," but it's in tension with its *spirit*, and the §4 "two records"
  principle papers over it. **This is an explicit decision for Alfred/CEO, not something Phase 1
  resolves:** is memory an *accepted, governed* lateral channel (write-authorization + provenance per
  R10), or must it be *constrained* (read-mostly, provenance-gated, per-agent-partitioned)? Flagged
  now so it's a deliberate architectural choice in Phase 2/3, not an accident discovered in build.
- **Watch item (not an escalation):** if ISI-2112 shows subscription-token lifecycle is unworkable at
  scale, the **BYO-subscription** decision (G) could come under pressure. That would be a CEO-gate
  conversation for Phase 2, flagged here pre-emptively so it isn't a surprise (see R1, now Critical).

---

## 9. Handoff & Next Steps

**Disposition of ISI-2117:** artifact delivered and committed. Two parallel next steps:

1. **Independent Challenger review — DONE (ISI-2121, verdict CONDITIONAL PASS).** The embedded §6 pass
   is Brainstormer-authored; the independent adversarial review by **Challenger** completed and its
   findings (F1–F20) are incorporated in this revision (ISI-2124): corrected Sympozium read (§6.2),
   new risks R9–R12 and severity recalibration (§6.1), softened escalation posture + the surfaced
   locked-vs-locked memory tension (§8), and minor notes (§1.4/§5/OQ9). No reopen — amendments only.
2. **Alfred (CTO) gate.** Phase 1's gate owner reviews this synthesis (with the Challenger's notes)
   and, on approval, unblocks **Phase 2 — PRD** (owner: John / Product Manager), whose CEO gate is the
   next hard checkpoint.

**Feeds forward into:**
- **Phase 2 (PRD):** personas §1.4, priorities §5, open questions OQ1/OQ6/OQ7/OQ8, UX mandate (Theme F).
- **Phase 3 (Architecture):** themes A–G, open questions OQ2–OQ5, seed spikes ISI-2112/2113/2114, and a
  proper Sympozium competitive teardown.

---

## Session Summary & Insights

**Key achievements:**
- Framed KSquad's problem around a real gap (no k8s-native, agent-agnostic squad control plane) and
  identified its **four audiences** and their competing needs.
- Converged the idea space into **six themes** plus one organizing principle (the **two records**:
  coordination vs. knowledge).
- Ran a full Challenger pass — embedded, then hardened by the independent Challenger review (ISI-2121,
  CONDITIONAL PASS): **12 risks** (R1 Critical; R9–R12 added), **7 rejected alternatives** with a
  **corrected, first-hand Sympozium read** (memory is convergent prior art, not a moat — the
  differentiation narrows to three deltas), and **9 open questions** routed to the right phase/spike.
- Reconciled and partially superseded ISI-2111; **no escalations *yet*** — but merits-confirmation is
  contingent on spikes ISI-2112/2113/2114, and **one locked-vs-locked tension** (shared memory as a
  lateral channel vs no-P2P) is surfaced as an explicit Alfred/CEO decision, not silently resolved.

**Session reflection:** the strongest signal is that the locked decisions are *mutually reinforcing* —
shared work items + first-class memory + BYO credentials + agent-agnostic shims aren't seven separate
choices, they're one coherent bet: **be the durable, legible, vendor-neutral substrate, not the
agent.** Phase 2 should protect that coherence above feature breadth.
