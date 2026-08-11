---
stepsCompleted: [context-analysis, backing-store-decision, crd-surface, agent-runtime-crd, tooling-model, coordination-record, knowledge-record, run-lifecycle, sandbox-runtime, shim-contract, credential-model, tenancy-isolation, console-frontend, sympozium-teardown, spine-risk, install-story, source-control-sync, dashboard-layer, discussion-room, build-browser, exposure-model, console-theming, plugin-architecture, event-bus, memory-backend-pluggability, adr-log, open-questions, traceability, validation]
inputDocuments:
  - docs/bmad/00-kickoff-brief.md   # CEO scope + 7 LOCKED decisions (commit 90747e3)
  - docs/bmad/01-brainstorming.md   # Phase 1 synthesis + Challenger amendments (commit aa1fbb2)
  - docs/bmad/02-prd.md             # CEO-approved PRD r2 (CEO Gate 1 PASSED 2026-08-10, commit 090ce69)
  - ISI-2111                        # Design doc: Squad architecture v0.1 (seed, historical)
  - ISI-2112                        # Spike: setup-token longevity — STATUS: backlog (evidence not yet produced)
  - ISI-2113                        # Spike: warm-pool claim latency — STATUS: backlog (evidence not yet produced)
  - ISI-2114                        # Spec: agent shim interface — STATUS: backlog (evidence not yet produced)
  - ISI-2144                        # AgentRuntime CRD + tooling model (CEO Gate 2 amendment; Henrik+Alfred decided direction 2026-08-11) — folded into §5.3
  - ISI-2145                        # Source-control sync (GitHub): repo-sync reconciler, webhook ingress, issue/PR/CI/artifact mirroring — folded into §5.4
  - ISI-2146                        # Dashboard layer: project health / work items / consumption attribution — folded into §13, §11, §17.2
  - ISI-2147                        # Per-Project discussion room: Postgres-backed, threaded, provenanced, memory-queryable, NOT coordination — folded into §7.5
  - ISI-2148                        # Build browser: per-Run file tree / diff / code view over workspace PVC — folded into §9.4, §13
  - ISI-2149                        # Helm chart: Gateway + HTTPRoute w/ gatewayClassName input; storageClassName for all PVCs — folded into §16.1/§16.2
  - ISI-2150                        # Mocks revision: dark+light theme is a v1 console requirement — folded into §13
  - ISI-2154                        # PM coordination handoff (ISI-2152→2151): PRD r3 FR→arch map + OQ13…OQ17 + new security bar (D8, NFR-SEC7/SEC8/OBS3) — consumed into r4 (this revision)
  - ISI-2142                        # GRAIL — the event-seam's first consumer: memory writes stream to GRAIL (OTLP/SmartScape/DQL); pgvector stays source-of-truth (own Phase 4 story) — folded into §7.6 (r5→r6)
  - ISI-2156                        # Plugin architecture (CEO via ISI-2131 c/1d8db3b3): transactional Postgres outbox event seam + out-of-process plugins + isolation; plugins = read-only observers, not coordination — folded into §17.4/§6.6 (r6)
  - ISI-2134                        # CEO Gate 2 review: BYO-Ollama model-endpoint requirement (Henrik 2026-08-11) — folded into §10.3 (r8)
  - ISI-2157                        # Free CI release-testing lane: in-cluster Ollama / self-hosted GPU runner for zero-credit conformance + smoke/e2e — realized in §10.3 (r8), matrix row in ISI-2114
  - ISI-2157                        # Ollama runtime adapter (CEO): Agent targets BYO Ollama endpoint (Secret-ref endpoint + per-Agent model); doubles as the free credential-less CI/e2e + conformance lane — folded into §10.3/§11 (r8)
  - MemPalace (org shared memory)   # First-hand Sympozium production intel (Ensemble/Agent/Model CRDs, memory sidecar, NATS, PR#45, OTel PRs #11/#18, ISI-1406)
revisions:
  - r1 (2026-08-10, ISI-2119): initial architecture synthesis from CEO-approved PRD r2
  - r2 (2026-08-11, ISI-2144): added §5.3 AgentRuntime CRD + lifecycle-split tooling model (init-staged toolchain packs, Skill.requires, service sidecars, ImageUpdater) per Henrik+Alfred decided direction; ADR-015/016/017; touchpoints §5.1/5.2/8/9.2/10.1/19/21
  - r3 (2026-08-11, ISI-2151): folded six CEO-review requirements (ISI-2145…2150) in behind existing seams — §5.4 source-control sync (repo-sync reconciler + pkg/scm provider seam, GitHub mirror; ADR-018); §7.5 per-Project discussion room (Postgres discussion schema, memory-projected, coordination-free; ADR-019); §11/§13/§17.2 dashboards + consumption attribution (OTel-borne; ADR-020); §9.4/§13 per-Run build browser (git-worktree read model; ADR-021); §16.1/§16.2 Gateway-API + explicit StorageClass exposure (ADR-022); §13 dark+light console theming. No locked decision reopened; touchpoints §1/§5.1/§17.3/§19/§22
  - r4 (2026-08-11, ISI-2154): lockstep with PRD r3. Adopted the PRD's formal numbering (Themes H/I/J/K/L, FR-F7) across §5.4/§7.5/§9.4/§11/§13/§16, and RESOLVED the five Architecture-owned mechanism questions the PRD routed here — OQ13 sync conflict/loop model (§5.4, field-ownership split + origin-tagged echo suppression), OQ14 metering provenance (§11/§17.2, anchored to Run lifecycle + kubelet, not forgeable self-report), OQ15 room storage/distinctness (§7.5), OQ16 Gateway-less fallback (§16.1, degrade to Service/Ingress so ≤4h install holds), OQ17 build-browser source + per-principal scoping (§9.4). Reflected the new security bar: D8 (external integrations untrusted+authenticated), NFR-SEC7 (room scope), NFR-SEC8 (sync auth), NFR-OBS3 (metering provenance). ADR-018/020/022 extended; §19/§22 updated. No locked decision reopened; content unchanged, numbering + two mechanism gaps (OQ13 loop model, OQ16 fallback) filled
  - r5 (2026-08-11, ISI-2151): folded two further CEO-review requirements (comment fad6cf02) in behind existing seams — §17.4 plugin architecture + event bus (internal event bus generalizes the SSE progress bus; in-process plugin subscribers v1, out-of-process delivery seam fast-follow; plugins are observers/integrators, best-effort post-commit, NEVER a coordination path — the §7.3/§7.5 no-P2P argument applied a third time; ADR-023) and §7.6 memory backend pluggability (`MemoryBackend` seam, pgvector default, GRAIL/ISI-2142 as a memory-SDK plugin + its own Phase 4 story; trust model enforced above the backend, backend-independent; ADR-024). Touchpoints §1/§7.1/§17.3/§19/§22. No locked decision reopened; ADR-001 one-Postgres + F16 trust boundary intact
  - r6 (2026-08-11, ISI-2151 / ISI-2156): refined the plugin architecture to the CEO's precise design (ISI-2156). Event seam is now a **transactional Postgres `outbox`** (events append-only in the state-change txn → at-least-once), delivered by **async workers with dead-letter + per-plugin circuit breaker** so a failing plugin can never block reconcile/coordination; plugins are **out-of-process** (sidecar/service) per Project/squad with BYO-Secret outbound creds; **versioned event catalog** under §10.2 drift discipline; **read-only consumption — plugins cannot claim/handoff/mutate**. Reframed GRAIL (§7.6): pgvector is **source-of-truth**, GRAIL is the seam's **first consumer** (memory writes stream via OTLP/SmartScape/DQL), not a backend swap. Rewrote §17.4, §7.6; added §6.6 (coord events); ADR-023/024 revised; §1/§17.3/§19/§20/§22 updated. Internal outbox over external broker per §4 single-stateful-dependency (CEO-named trade). No locked decision reopened
  - r8 (2026-08-11, ISI-2134 / CEO Gate 2, Henrik): folded the CEO BYO-Ollama requirement in behind existing seams — §10.3 model-endpoint seam (`Agent.spec.modelEndpointRef` → Secret, orthogonal to `AgentRuntime.type` so no R×T regression; Ollama rides the OpenAI-compatible wire on existing runtimes with zero new image; local-model gaps declared via §10.1 capability negotiation; in-cluster Ollama = zero-credit CI conformance + smoke/e2e lane for ISI-2157/ISI-2114). Touchpoints §5.1 (`Agent` CRD adds `modelEndpointRef`), §5.3.1, §10.1, §12 egress, §11 credential discipline reused; ADR-026 added; traceability rows added. No locked decision reopened; per-user Secret-ref lock (ADR-010) + R×T-elimination (ADR-015) intact
  - r7 (2026-08-11, ISI-2135): closed the ISI-2132 review's four blocking coordination-spine findings (F1–F4) ahead of the R10 epic — §6.1 cardinality pinned (exactly-one-active claim per work item, monotonic fence, artifact upsert key); §6.2 renewal guard (holder AND fence AND unexpired lease); §6.3 **reclaim protocol: fence the pod (terminate + egress-deny + confirm) BEFORE releasing the claim**, plus resource-layer fence checks (memory write validation, fence-guarded artifact registration, workspace-lease discipline) and the named external-git residual; §6.4 re-entrancy designed for external-effect steps (deterministic `a2a_task_id = run_id` + shim-side dedup + durable dispatch marker; artifact upsert; conditional status UPDATEs); §8 failure path now runs the reclaim protocol; §15 names the zombie-writer-vs-PVC (F1) and double-dispatch (F4) chaos cases as R10 acceptance gates; ADR-025 added. No locked decision reopened; ADR-001/003 intact
  - r8 (2026-08-11, ISI-2151 / ISI-2157): added the **Ollama / BYO model-provider seam** — new §10.3. An `Agent` targets a BYO model endpoint (its own Ollama / any OpenAI-compatible server) via a **Secret-ref endpoint + per-Agent model**, negotiated by a `byoModelEndpoint` capability (§10.1). Kept the honest distinction: Ollama is a **model server, not a coding-agent runtime** (§5.3), so it lands on the model axis and **reinforces the BYO-credential lock** (§11 third story) rather than reopening it. Egress via the model-endpoint allowlist (§12.2). Doubles as the **credential-free CI/e2e + conformance lane** (§10.1, ISI-2114 Ollama lane) for squad smoke/e2e without paid API credits (ISI-2157). ADR-026; §11 heading Two→Three stories; §19/§21/§22 updated. No locked decision reopened
workflowType: 'architecture'
authoringMode: 'analyst-led autonomous synthesis; CEO Gate 2 is the human review checkpoint'
project_name: 'KSquad'
source_ticket: 'ISI-2119'
gate_executor: 'ISI-2127'
parent: 'ISI-2116'
program: 'ISI-2115'
gate: 'CEO (BigBoss) — required before Phase 4 (Epics & Stories)'
locked_decisions_touched: none
---

# Architecture / Solution Design — KSquad

**Author:** Winston (System Architect)
**Date:** 2026-08-10
**Phase:** BMAD Phase 3 — Architecture
**Gate:** CEO (BigBoss) approval required before Phase 4 (Epics & Stories) — hand back to Alfred (CTO)
**Source ticket:** ISI-2119 (executed via ISI-2127) · **Parent:** ISI-2116 · **Program:** ISI-2115

> **Scope discipline.** This document turns the CEO-approved PRD (`02-prd.md` r2) into technology
> decisions. It **builds on** the seven LOCKED decisions (kickoff §2) and **does not reopen** them.
> It resolves the Architecture-owned open questions (OQ2, OQ4, OQ5, OQ7, OQ9, OQ10, OQ11, OQ12) and
> confirms the memory MCP tool surface and the Node frontend approach. Where a decision depends on
> evidence that does not yet exist (the three spikes), it is made **provisionally and behind a
> pluggable seam**, and the spike-gated parameter is named explicitly (§21). Nothing here escalates a
> locked decision; the memory-vs-no-P2P trust boundary (F16) and memory-is-parity framing (F5) were
> ratified at CEO Gate 1 and are implemented here as designed.

---

## 1. Executive Architecture Summary

KSquad is **one Go operator + one Go API/coordination service + one Go memory service + one Node
console + one Postgres**, distributed as CRDs + Helm, that reconciles a *squad of AI agents* as a
first-class Kubernetes workload. The architecture is deliberately **boring where it can be and novel
only where the moat is**:

- **Boring on purpose:** controller-runtime operator, Postgres for durable state, gVisor
  RuntimeClass for sandbox isolation, NetworkPolicy for egress, Next.js for the console, native
  Kubernetes RBAC/Secrets/PVCs for tenancy. No bespoke consensus system, no message bus, no
  home-grown vector database.
- **Novel exactly at the three deltas (PRD §8):** (1) an **agent-runtime-agnostic shim seam**
  (A2A ⇄ native, one sidecar per runtime, capability-negotiated); (2) a **reconcile control plane**
  (a `Run` is a reconciled workload with a crash-safe state machine, not heartbeat glue); (3)
  **native durable work items** (checkout/claim/lease in Postgres transactions — the coordination
  record *is* the audit log).

**The single most important architecture decision (§4):** the **two records live in one Postgres**,
not in etcd/CRDs. CRDs carry *desired state* (Team/Agent/Role/Skill/Project/Run); Postgres carries
*high-churn durable state* (work items, comments, claims, leases, memory). etcd is the wrong store
for contended, queryable, high-write coordination and knowledge data. This one decision de-risks the
coordination spine (F8/R10 — Postgres row locks + fencing instead of a from-scratch distributed
lock) and the memory build-vs-integrate trade (OQ10 — pgvector, not a new vector DB), and it keeps
the install to a **single stateful dependency** so the S1 "≤4h install-to-first-squad" acceptance
test stays reachable.

**Review-cycle surfaces (r3, ISI-2145…2150).** Six requirements raised in CEO review are folded in
**without disturbing the spine**: source-control sync (§5.4), project/work-item/consumption
dashboards (§13/§11/§17.2), a per-Project discussion room (§7.5), a per-Run build browser (§13/§9.4),
explicit Gateway-API + StorageClass exposure (§16.1/§16.2), and dark+light console theming (§13).
Every one **rides an existing decision** rather than adding structure — the new `scm` and `discussion`
records are two more schemas in the *same* one Postgres (ADR-001, no new datastore); dashboards and
consumption ride the *same* OTel pipeline (§17.2, no billing DB); the build browser is the *same*
per-Run git worktree that already exists for concurrency (§9.4); SCM sync reuses the *provider-seam*
discipline that isolates A2A/MCP drift (§10.2); and the discussion room re-applies the *exact* memory
trust boundary (§7.3) so it is legible, provenanced knowledge — **never a coordination back-channel**
(the no-P2P lock stands). No locked decision is reopened.

**Extensibility surfaces (r5→r6, CEO 2026-08-11, ISI-2156).** Two further requirements land the same
way: a **plugin architecture + event seam** (§17.4) and **memory fan-out to GRAIL** (§7.6). The event
seam is a **transactional Postgres `outbox`** — events append-only in the *same transaction* as the
state change (at-least-once), delivered by **async workers with dead-letter + circuit breaker** so a
**failing plugin can never block the reconcile/coordination path**. Plugins are **out-of-process**
(sidecar/service) per Project/squad, and — for the **third** time — the no-P2P discipline is applied by
construction: consumption is **read-only**, the seam has no claim/lease/fence surface, and **plugins
cannot claim, hand off, or mutate state** (the lock stands). GRAIL (ISI-2142) is the seam's **first
consumer** — memory writes stream to it via OTLP/SmartScape/DQL — while **`pgvector` remains
source-of-truth** and the §7.3 trust model is enforced above storage and before fan-out. The outbox is
**one table in the same Postgres, not an external broker** (§4 single-stateful-dependency) — no new
datastore forced, no locked decision reopened.

> **Honesty note carried throughout.** ISI-2112 (setup-token longevity), ISI-2113 (sandbox claim
> latency), and ISI-2114 (shim contract) are **still `backlog` and unassigned** as of this writing —
> the "evidence" the wake asked me to consume **does not exist yet**. This architecture is therefore
> designed so those spikes tune *parameters behind seams* (which RuntimeClass, what pool size, exact
> OAuth refresh cadence, pinned A2A rev) and **cannot invalidate the structure**. The spikes must
> still run before v1 commits the gated defaults; §21 names each gated parameter and §22 flags the
> spikes as required follow-ups.

---

## 2. Architecture Context & Method

| Input | What it fixes | Where it lands |
|-------|---------------|----------------|
| Kickoff §2 (7 LOCKED) | Node FE, Go BE, first-class memory, work-item coordination, A2A south, MCP tools, BYO creds | Assumed, not re-argued |
| PRD §9 FR-A…G | Capability contract (WHO/WHAT) | §5–§13 map each FR to a mechanism |
| PRD §10 NFR | Security, reliability, latency, tenancy | §12, §17, §9 |
| PRD §6 two-records + F16 trust boundary | Coordination vs knowledge separation | §4, §6, §7 |
| PRD Challenger F6/F7/F8/F9/F16 | Warm-pool hygiene, memory poisoning, spine cost, spec drift, memory trust | §9.3, §7.3, §6/§15, §10.3 |
| MemPalace first-hand Sympozium intel | Honest competitive teardown | §14 |
| ISI-2112/2113/2114 | Credential/runtime/shim evidence — **not yet produced** | Designed behind seams; §21 gates |

**Method:** decision-first. Each section states the decision, the trade considered, the mechanism,
and the FR/NFR it satisfies. Alternatives seriously considered are recorded in the ADR log (§18) so
Epics and Code Review inherit the *reasoning*, not just the outcome.

---

## 3. System Overview

### 3.1 Component map

```
                            ┌───────────────────────────────────────────────┐
  Operator (Priya) ───────► │  ksquad-console (Node / Next.js)               │
  Author  (Sam)   ───────►  │  polished UI + BFF; SSE fan-out; no direct kube│
                            └───────────────┬───────────────────────────────┘
                                            │ REST + SSE (HTTPS)
                            ┌───────────────▼───────────────────────────────┐
   kubectl / CRDs ─────────►│  ksquad-apiserver (Go)                        │
                            │   • coordination record: work items / comments │
                            │     / checkout / lease / artifacts (Postgres)  │
                            │   • audit query API   • SSE progress bus        │
                            └───┬───────────────┬───────────────┬────────────┘
                                │               │               │
        ┌───────────────────────▼──┐   ┌────────▼─────────┐   ┌─▼───────────────────┐
        │ ksquad-operator (Go)     │   │ ksquad-memory (Go)│   │ Postgres (single    │
        │  controller-runtime      │   │  MCP server       │   │ stateful dependency)│
        │  reconcilers:            │   │  pgvector + diary │   │  • coord schema     │
        │  Team/Agent/Project/Run  │   │  + KG (fast-follow)│  │  • memory schema    │
        │  + SandboxPool           │   └────────┬──────────┘   │  (logically split,  │
        └───────────┬──────────────┘            │              │  distinct trust)    │
                    │ creates/tears down         │ MCP tools    └─────────────────────┘
        ┌───────────▼───────────────────────────▼───────────────────────────┐
        │  Team namespace  (tenancy boundary — RBAC / NetworkPolicy / quota) │
        │   ┌──────────────────────────────────────────────────────────┐    │
        │   │ Sandbox Pod (warm-pool, gVisor RuntimeClass)              │    │
        │   │   ┌────────────────┐   ┌─────────────────────────────┐    │    │
        │   │   │ shim sidecar   │◄──┤ agent runtime (OpenClaw /   │    │    │
        │   │   │ (A2A ⇄ native) │   │ Hermes / Claude Code / …)   │    │    │
        │   │   └────────────────┘   └─────────────────────────────┘    │    │
        │   │   Project workspace PVC (per-principal-scoped, worktree)  │    │
        │   └──────────────────────────────────────────────────────────┘    │
        └────────────────────────────────────────────────────────────────────┘
```

### 3.2 Plane split

- **Control plane** (namespace `ksquad-system`): operator, apiserver, memory service, console,
  Postgres. Stateful, cluster-privileged (scoped), one install.
- **Data plane** (per-`Team` namespace): sandbox pods, shims, agent runtimes, workspace PVCs, the
  Team's Secrets. Untrusted, least-privilege, blast-radius-bounded.

The control plane is trusted; **everything in the data plane is treated as hostile** (agents run
arbitrary code — PRD D1, F18). This split is the spine of the security model (§12, §17).

---

## 4. Foundational Decision — One Postgres, Two Records (ADR-001)

**Decision.** Durable non-declarative state lives in **PostgreSQL**, shipped with KSquad. The
**coordination record** and the **knowledge record** (PRD §6) are two **logically separate schemas**
in that one database with **different trust semantics**, not two datastores. CRDs remain the
*desired-state* API and live in etcd via the Kubernetes API as normal.

**Why not CRDs/etcd for work items and memory.** etcd is a strongly-consistent config store, not a
work queue or a knowledge base. Work items are high-churn (comments, claim/renew, status), demand
transactional claim semantics under contention, and must be *richly queryable* as an audit trail
(PRD FR-B4/NFR-OBS1); memory needs vector similarity search (FR-E4). etcd gives none of these well —
object-size limits, watch-storm amplification, no joins, no vector index. Forcing them into CRDs
would be the classic operator anti-pattern.

**Why one database, not two.** S1 (≤4h install) punishes every added stateful dependency. One
Postgres with two schemas gives logical separation and independent trust boundaries without a second
operational surface. It also lets `pgvector` (memory) and transactional row-locks (coordination)
come from the same proven engine.

**Why this de-risks the two hardest bets:**
- **Coordination spine (F8/R10):** checkout/claim/lease becomes a **conditional `UPDATE` inside a
  transaction with a fencing token**, not a bespoke distributed lock. Postgres' MVCC + `SELECT … FOR
  UPDATE SKIP LOCKED` is battle-tested; we are not writing Raft. (§6)
- **Memory build-vs-integrate (OQ10/F13):** integrate `pgvector` for semantic search; keep full
  control of the FR-E6/E7 provenance/trust model in our own schema and service layer. Best of both.
  (§7)

**Operational shape.** Ship Postgres via the **CloudNativePG (CNPG) operator** as a Helm dependency
(HA, backups, failover as boring config), with a single-instance default profile for the S1 quick
install. Consumers: apiserver (coord schema, read-write), memory service (memory schema, read-write);
no other component touches the DB directly.

*Satisfies:* FR-B1…B4, FR-E1…E7, NFR-REL1/REL3, NFR-OBS1. *Trade recorded:* ADR-001.

---

## 5. CRD Surface & Operator Design

### 5.1 CRDs (`ksquad.io/v1alpha1`)

| CRD | Purpose | Key spec | Reconciled by |
|-----|---------|----------|---------------|
| `Team` | Squad = tenancy boundary | `projects[]`, `agents[]` (refs), `namespaceStrategy` | Team reconciler → ensures namespace, RBAC, NetworkPolicy, quota |
| `Agent` | One agent instance in a squad | `runtimeRef` (→`AgentRuntime`), `credentialSecretRef`, `capabilityOverrides`, `model`, `modelEndpointRef` (→Secret, BYO model endpoint — §10.3) | Agent reconciler → validates Secret + runtime, publishes Agent Card |
| `AgentRuntime` | Pluggable coding-agent flavor + CLI version policy | `type`, `image`, `cliVersion`, `capabilities{docker,github,packageInstall}` | AgentRuntime reconciler + `ImageUpdater` (§5.3) |
| `Role` | Reusable behavior profile | `promptRef`, `defaultSkills[]`, `runtimeClassHint` | (data only; validated) |
| `Skill` | Granted tool/capability | `mcpToolRefs[]`, `permissions`, `requires{toolchains[],sidecars[]}` | (data only; validated → drives §5.3.4 pod assembly) |
| `Project` | Repo + workspace | `repo` (URL/ref/auth, `sync{provider,webhookSecretRef,mirror{},reflectOutbound}` §5.4), `workspacePVC` (size/class), `egressPolicyRef` | Project reconciler → PVC, repo-sync bootstrap, NetworkPolicy; **repo-sync reconciler** (§5.4) mirrors SCM |
| `Run` | Unit of squad work | `teamRef`, `projectRef`, `workItemSelector`, `agents[]`, `retryPolicy` | **Run reconciler (the core state machine, §8)** |
| `SandboxPool` (internal) | Warm-pool sizing | `runtimeClass`, `size`/`policy`, `template` | SandboxPool reconciler (§9) |

> Work items, comments, claims, artifacts, and memory records are **not CRDs** — they are Postgres
> rows behind the apiserver/memory APIs (§4). The `Run` CRD *references* work items via
> `workItemSelector`; it does not embed them.

### 5.2 Operator

- **controller-runtime / Kubebuilder**, one manager, one reconciler per CRD, leader-elected. The
  `AgentRuntime` reconciler validates the runtime + owns the `ImageUpdater` control loop (§5.3.5); the
  Run reconciler runs the pod-assembly algorithm (§5.3.4) at `Claiming`.
- Reconcilers are **idempotent and level-triggered**; each writes `status.observedGeneration` and
  conditions. Run reconciler additionally coordinates with the apiserver's claim service via fencing
  tokens (§6.3, §8) so a controller restart never double-drives a Run.
- CRD validation via CEL/webhooks (e.g. an `Agent` must resolve a credential Secret before it is
  admitted — fail closed, PRD NFR-SEC*).

*Satisfies:* FR-A1…A3, FR-A6. *Trade recorded:* ADR-002 (Postgres for coordination, CRDs for
desired state).

### 5.3 `AgentRuntime` CRD, Toolchains & Pod Composition (ISI-2144, CEO Gate 2 amendment)

> **Decided direction (Henrik + Alfred, 2026-08-11):** tooling is **split by lifecycle, not
> one-size-fits-all**. Languages/CLIs are *files* → staged by init containers. Stateful services are
> *processes* → sidecars. Skills declare what they need; the operator assembles the pod. This
> eliminates the combinatorial runtime-image matrix and kills "works on my image".

#### 5.3.1 `AgentRuntime` CRD — the coding-agent flavor + CLI version policy

The **agent flavor** (which coding CLI runs the work) is now a first-class, referenceable object
instead of an implicit property of a hand-built image. `Agent.spec.runtimeRef` points at an
`AgentRuntime`; the `Role` no longer conflates behavior profile with runtime image.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: AgentRuntime
metadata:
  name: claude-code
spec:
  type: claude-code            # claude-code | kimi-code | opencode | codex | openclaw | hermes
  image: ghcr.io/ksquad/runtime-claude-code   # base + the agent CLI + the shim (§10)
  cliVersion: "1.2.3"          # PINNED by default; latest only in dev (see 5.3.5 lifecycle)
  capabilities:               # capability flags gate pod assembly (fail-closed, NFR-SEC*)
    docker: false              # → rootless dockerd sidecar (5.3.3); Kata-gated for real docker
    github: true               # → gh CLI + git credential mount from Secret (BYO token)
    packageInstall: true       # → rootless OS-package install inside the sandbox
  credentialSecretRef: claude-oauth   # per-user Secret (defers to §11 credential model, unchanged)
```

- **What the image ships:** a minimal base + the **coding-agent CLI** (version governed by
  `cliVersion`) + the **A2A⇄native shim** (§10). It ships *no* language toolchains — those are
  decoupled (5.3.2). Result: the image count is **R (one base per agent flavor)**, not **R×T**
  (flavor × toolchain combinations). This is the matrix-elimination the amendment targets.
- **Capabilities are declared, not ambient** (consistent with the FR-D4/R3 capability-flag model on
  the Agent Card, §10.1): `docker`/`github`/`packageInstall` are flags the operator reads to decide
  what to mount/inject — and CEL/webhook validation fails closed (e.g. `docker: true` on a gVisor-only
  RuntimeClass is rejected unless a rootless-dockerd sidecar or a Kata RuntimeClass is available, §9.1).
- **`type` drives conformance:** every `AgentRuntime.type` must pass the shim conformance suite
  (ISI-2114) — "A2A task in → run → artifacts out". The CRD and the shim spec are two halves of one
  seam (§10.1). A `type` that has not passed conformance is admitted only behind an explicit
  `experimental` flag.

#### 5.3.2 Toolchain packs via init containers (languages/CLIs are *files*)

Each language/utility toolchain is a **versioned OCI image** (e.g. `ksquad/toolchain-go:1.23`,
`toolchain-node:22`, `toolchain-python:3.13`). At pod assembly the operator adds one **init container
per required pack**; each init container **stages its toolchain into a shared volume** (an `emptyDir`
staging mount overlaid on `PATH`) before the agent container starts.

- **Why init, not sidecar:** languages are files, not long-running processes. A sidecar would burn
  pod CPU/memory for the whole Run and force fragile PATH/volume hacks. An init container stages files
  and exits — **zero steady-state overhead**.
- **Composable + version-pinnable + node-cacheable:** `go@1.23`, `node@22` are independent, pinned
  refs; the packs are ordinary images pre-pulled onto nodes (warm-pool image-prepull, §9.2), so
  staging is a fast local copy, not a network pull.
- **Install rights (issue §3):** `packageInstall: true` runtimes get **rootless** package install
  inside the sandbox (user-mode `mise`/`devbox`/`apt`), scoped to the workspace — no root, no host
  mutation. Packs cover the common case; rootless install covers the long tail.

#### 5.3.3 Service sidecars (stateful processes only)

Sidecars are reserved for **genuine long-running services** the agent reaches over `localhost`:
rootless `dockerd` (the `docker` capability), headless browsers, ephemeral local DBs. These are
processes, not files — a sidecar is the correct primitive and the resource cost is justified by a
real running service.

- **Docker capability (issue §3, OQ2 interaction):** on **gVisor** (default, §9.1) the `docker`
  capability is served by a **rootless `dockerd` / kaniko / buildah** sidecar (no host Docker socket,
  no privileged container). Real nested Docker requires a **Kata** RuntimeClass; the operator refuses
  `docker: true` on a runtime pinned to gVisor-only unless the rootless path is selected. The flag is
  the gate; the RuntimeClass decides which mechanism backs it — spike-tunable (§9.1), not structural.

#### 5.3.4 `Skill.requires` — self-describing skills + operator pod assembly

The `Skill` CRD (§5.1) gains a `requires` block so a skill declares *its own* toolchain packs and
service sidecars. The operator merges the union of a Run's skills' requirements into the Run pod spec.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Skill
spec:
  mcpToolRefs: [...]          # (unchanged)
  permissions: [...]         # (unchanged)
  requires:
    toolchains: [go@1.23, node@22]   # → init containers (5.3.2)
    sidecars: [dockerd]               # → service sidecars (5.3.3), capability-gated
```

**Operator pod-assembly algorithm** (Run reconciler, §8 `Claiming`):
1. Resolve `Agent.runtimeRef` → `AgentRuntime` → **agent container** (image + shim + `cliVersion`).
2. Union the `requires.toolchains` of every `Skill` on the Run → dedupe by name, resolve version
   conflicts fail-closed (two skills pinning `go@1.22` vs `go@1.23` is a validation error, not a
   silent pick) → **one init container per pack**.
3. Union the `requires.sidecars`, intersect with `AgentRuntime.capabilities` (a sidecar whose
   capability the runtime disables is rejected) → **service sidecars**.
4. Mount the shared toolchain-staging volume + the Project workspace PVC (§9.4) + credential Secrets
   (§11) + the `gh`/git credential mount when `github: true`.

Net: **no more "the image happened to have Go" surprises.** Requirements are explicit, validated, and
assembled by the operator — the R×T image matrix is gone.

#### 5.3.5 Runtime-image build & update lifecycle (the hard part, issue §2)

CLIs release weekly/daily; the architecture must stay fresh without CI thrash or blind cold-start
pulls. **Decision: hybrid (issue option c) — pinned `cliVersion` in the CRD + an `ImageUpdater`
controller.**

- **Pinned by default:** `AgentRuntime.cliVersion` is an exact version; a Run is reproducible and a
  bad CLI release cannot silently poison in-flight work.
- **`ImageUpdater` controller** (new, operator-internal): watches upstream CLI release feeds
  (npm/GitHub releases) on a schedule, proposes a `cliVersion` bump, **canaries exactly one sandbox**
  against the shim conformance suite (ISI-2114) before rolling the bump to the `AgentRuntime`, then
  triggers a **warm-pool refresh** (§9.2) so warm pods and node image-prepull are updated — otherwise
  a bump balloons cold-start. Rebuild-pipeline (option a) and init-time CLI pull (option b) are
  rejected as the *default*: (a) is CI-heavy and (b) trades reproducibility + cold-start for freshness
  we already get from the scheduled canary.
- **Warm-pool interaction (issue §2, resolved):** warm pods are keyed by **(RuntimeClass ×
  AgentRuntime image)** — *not* by skill set, because toolchains are init-staged at claim time from
  node-cached packs (5.3.2). So the warm pool stays small (one dimension, the agent base) while
  skill-specific toolchains attach per-Run without a warm pod per skill combination. An `ImageUpdater`
  bump drains and re-warms the affected key.

**Open questions escalated to Alfred/CEO (issue §Open questions — not architect-owned):**
1. **Registry:** `ghcr.io/ksquad/*` — are runtime/toolchain images public for the OSS project?
2. **CLI license / redistribution:** which agent CLIs permit redistribution *inside* an image
   (**Claude Code ToS is the live risk**) vs. must be init-time downloaded from the vendor at pod
   start? This can force option (b) *for specific runtimes only* — the CRD's per-runtime `image` +
   `cliVersion` seam already accommodates a mixed model. **Flagged, not silently assumed.**
3. **Air-gapped / corporate installs:** mirror support for CLI + toolchain-pack pulls (offline
   registry). The pinned-version + node-prepull model is mirror-friendly; needs an explicit design
   pass in Epics.

*Satisfies:* FR-D3/D4 (runtime pluggability, capability negotiation), FR-A1…A3 (CRD surface), the
ISI-2144 amendment scope. *Trade recorded:* ADR-015 (AgentRuntime CRD + R-not-R×T image model),
ADR-016 (lifecycle-split tooling: init-staged packs vs service sidecars), ADR-017 (hybrid image
update via ImageUpdater + conformance canary). *Spike-gated:* Docker-in-sandbox mechanism per
RuntimeClass (§9.1/ISI-2113); CLI-redistribution licensing (open question 2, owner Alfred).

### 5.4 Source-Control Sync — repo-sync reconciler & provider seam (Theme H, FR-H1…H5; ISI-2145)

> **Decision (Henrik, CEO review 2026-08-11):** a `Project`'s upstream source host (GitHub first) is
> **mirrored into KSquad**, not made the source of truth. GitHub is an *external, provenanced mirror*;
> the fenced coordination record (§6) stays authoritative. Coordination custody never moves through
> the mirror — the no-P2P/durable-work-item locks are untouched.

**Reconciler + provider seam.** A `repo-sync` control loop (operator-internal, one per `Project` with
`repo.sync` configured) reconciles the linked repo against a `SourceControlProvider` interface
(`pkg/scm`, §17.3). GitHub is the v1 provider; GitLab/Gitea drop in behind the same interface later —
the **same seam discipline** that isolates A2A/MCP spec drift (§10.2), so provider-specific churn never
reaches coord. Level-triggered reconcile is the correctness backstop; the webhook is only a fast path.

**What is mirrored (inbound).** Issues, pull requests, CI **check runs** (status), and release/build
**artifacts** (by URI + sha, reusing the artifact provenance shape §6.1) are ingested into a new
Postgres **`scm` schema** — `scm_repo`, `scm_issue_mirror`, `scm_pr_mirror`, `scm_check_run`,
`scm_artifact_ref` — linked to the `Project` and, where an operator maps them, to `coord` work items
(FR-H1 issues⇄work items; FR-H2 PR/CI/artifact status). This is **one more schema in the same one
Postgres (ADR-001)**, not a new datastore.

**Webhook ingress.** The apiserver exposes an **HMAC-verified** webhook endpoint; the HMAC secret is a
per-`Project` Secret ref (`repo.sync.webhookSecretRef`, same per-user-Secret discipline as §11). It
subscribes to `push` / `pull_request` / `issues` / `check_run` / `release` (FR-H3 webhook + poll
fallback). **Webhooks are lossy and at-least-once**, so a webhook only *triggers* a reconcile; the
periodic provider-list reconcile is what guarantees eventual convergence. The HMAC signature is
**verified before any payload is parsed** (FR-H4, NFR-SEC8, D8) — an unsigned or bad-signature delivery
is dropped, never reconciled. Payloads are treated as **untrusted input** (FR-H5, D8): every synced
work item and mirror row carries `external_origin` provenance (provider, repo, external id, actor) and
is rendered in the console as *external, attributable* data (§17.1), consumed by agents through the same
untrusted-provenance envelope as memory/discussion (§7.3.2) — **never trusted control input**.

**Bidirectionality, conflict resolution & loop-prevention (OQ13 — resolved).** The PRD sets the
direction (mirror, not source of truth) and leaves the mechanism to Architecture; here it is:
- **Field-ownership split (conflict resolution).** Each mirrored row has two field classes with
  **single-writer ownership**, so there is no bidirectional last-writer race: *external-owned* fields
  (issue/PR title, body, external state, CI result) are written **only** by the inbound reconciler from
  the provider; *KSquad-owned* fields (linked `coord` work-item id, claim/lease/custody — §6) are
  written **only** by the coordination record and are **never** pushed to or overwritten by the mirror.
  Custody never crosses the seam (the no-P2P / durable-work-item lock stands). Divergence on an
  external-owned field always resolves to *the provider's value at last successful reconcile* (the
  provider is authoritative for its own content); divergence on a KSquad-owned field is impossible
  because the mirror has no write path to it.
- **Loop-prevention (echo suppression).** Outbound reflection (below) stamps every KSquad-authored
  provider write with an **origin marker** (a bot actor identity + a content marker/`external_origin`
  round-trip id). The inbound reconciler **drops any delivery whose actor/marker is KSquad's own**, so a
  reflected comment/status can never re-enter as a fresh inbound change and ping-pong. Combined with
  level-triggered reconcile (idempotent upsert keyed by external id — a redelivered webhook is a no-op),
  this makes the sync **convergent, not oscillating**.

**Outbound reflection (opt-in, gated).** Posting KSquad Run status/comments back to a PR/issue is a
per-`Project` opt-in provider capability (`reflectOutbound`) and is a **projection of coord state**,
never a second source of truth. Off by default; requires a status-write-scoped token; every write is
origin-marked (loop-prevention, above).

**Authorization (FR-H4, D8, NFR-SEC8).** The provider token is a **per-`Project`/per-user BYO Secret
ref** (never a shared master token to GitHub — same D3/FR-G1 discipline as §11), scoped to
**mirror-read** (+ optional status-write only when `reflectOutbound`) — least privilege, fail-closed.
Sync-connector credentials are **never logged, echoed, or exposed to an agent Run** (NFR-SEC8).

*Satisfies:* Theme H (FR-H1…H5), D8, NFR-SEC8, OQ13 (resolved); reinforces FR-B4 audit (SCM artifacts
join the coord trail). *Trade recorded:* ADR-018 (repo-sync provider seam + mirror-not-authority +
field-ownership/echo-suppression). *Touchpoints:* §5.1 (`Project`), §17.3 (layout, `pkg/scm`), §13
(dashboard project-health source), §19/§22.

---

## 6. Coordination Record — Work Items, Checkout / Claim / Lease (OQ9, F8)

**This is the single most correctness-critical component of v1 (PRD R10). It is a foundational
engineering track, not a spine checkbox.** It is designed here concretely so Epics can staff and
sequence it first.

### 6.1 Data model (Postgres `coord` schema)

`work_item(id, project_id, team_id, title, state, created_by, created_at, …)` ·
`comment(id, work_item_id, author_principal, body, created_at)` ·
`artifact(id, work_item_id, run_id, kind, uri, sha256, created_at, UNIQUE(work_item_id, run_id, kind))` ·
`claim(work_item_id PK, holder_principal, run_id, fence_token, lease_expires_at, acquired_at, renewed_at)`.

**Cardinality (F3, pinned):** exactly **one active claim row per work item** — `work_item_id` is the
PK, the row is rewritten in place on every reclaim, and `fence_token` is **monotonically increasing
across the item's lifetime** (never reset, never reused). There is no append-only claim history in
the custody path (history lives in the audit/outbox, §6.5/§6.6), so two live leases on one item are
structurally impossible.

All coordination — progress, handoff, artifacts — is rows here (FR-B1/B3). **No agent-to-agent
channel exists in the schema**; there is no `message` table and no lateral transport (I4, structural
enforcement of "no P2P").

### 6.2 Checkout / claim (at-most-one-holder, FR-B2)

```sql
-- claim: conditional acquire, atomic, contention-safe
UPDATE claim
   SET holder_principal = :me, run_id = :run, fence_token = fence_token + 1,
       lease_expires_at = now() + :lease, acquired_at = now(), renewed_at = now()
 WHERE work_item_id = :wi
   AND (holder_principal IS NULL OR lease_expires_at < now())
RETURNING fence_token;
```

- A row returned ⇒ claim acquired with a fresh, **monotonically increasing fence token**. No row ⇒
  someone holds a live lease; the caller backs off. This is atomic in one statement — **no
  double-claim under contention** without any distributed lock.
- Work-pull uses `SELECT … FOR UPDATE SKIP LOCKED` so N agents dequeue distinct items without
  blocking each other.

```sql
-- renew: guarded by holder AND fence AND unexpired lease — a zombie's renewal is a no-op (F3)
UPDATE claim
   SET lease_expires_at = now() + :lease, renewed_at = now()
 WHERE work_item_id = :wi
   AND holder_principal = :me
   AND fence_token      = :myFence
   AND lease_expires_at > now();
```

- A holder can renew **only its own live claim with its own current fence**. A paused holder whose
  lease lapsed cannot resurrect it: the `lease_expires_at > now()` term fails, and once the row is
  reclaimed the `holder`/`fence_token` terms fail. Renewal is therefore authority-unambiguous — the
  F3 ambiguity (stale-row renewal succeeding under a newer claim) cannot occur.

### 6.3 Lease, liveness, fencing (crash-reclaim, FR-B2/NFR-REL1)

- A claim carries a **bounded lease** (`lease_expires_at`). The holding agent (via the apiserver)
  **renews** on a heartbeat well inside the lease. A crashed holder stops renewing; once
  `lease_expires_at < now()`, the item is reclaimable by the exact `WHERE` clause above — **no
  operator action, no stuck lease**.
- **Fencing prevents the zombie-writer race:** a slow/paused holder that wakes after its lease
  expired and the item was re-claimed carries a *stale* fence token. Every state-mutating write
  (comment, status, artifact, complete) is `… AND fence_token = :myFence`; a stale token's write is
  rejected. This closes the classic lease+GC-pause hazard that a naive "just re-claim on timeout"
  design would ship as a silent double-execution.
- Lease TTL is a tunable (default 60s renew / 180s expiry) — a knob, not a structural choice.

**Reclaim protocol — fence the holder BEFORE the claim is released (F1).** Lease expiry means
"renewal stopped," **not** "holder is dead": a GC-paused or partitioned Run is alive at the
resource layer and keeps mutating the per-Project workspace PVC (§9.4), memory (§7), and git. The
reconciler never treats `lease_expires_at < now()` alone as reclaim permission. Reclaim is an
ordered, crash-safe sequence:

1. **Fence the holder.** Cordon + terminate the holder's sandbox pod (SIGTERM → SIGKILL after a
   short grace) and flip its egress `NetworkPolicy` to deny-all. Pod death revokes the PVC mount
   (workspace writes stop) and egress (git push / model calls stop). A durable `reclaim_fenced_at`
   marker is recorded on the Run before proceeding, so a reconciler crash mid-reclaim re-enters at
   the right step.
2. **Confirm fencing.** Wait for pod deletion (bounded timeout). On timeout, escalate (node
   cordon + operator alert) — never release an unconfirmed-unfenced claim.
3. **Release the claim.** Only now is the row acquirable via the §6.2 conditional UPDATE, which
   bumps `fence_token` — so even a holder that somehow survived step 1 is fenced at the
   coordination layer.

**Resource-layer fence checks (defense in depth).** The pod-kill ordering is the primary fence;
the state-mutating services additionally reject stale tokens, so a fencing failure degrades to
**rejected writes, never silent corruption**:

- **Memory service (§7):** every write carries the caller's `(work_item_id, fence_token)`; the
  service validates it against `coord.claim` inside the write transaction and rejects stale tokens.
- **Artifact / object store:** artifact registration is a fence-guarded `coord.artifact` row; the
  object URI is durable only once that row commits, so a zombie's orphaned blob is unreferenced and
  garbage-collectable.
- **Workspace lease (§9.4):** exclusive-write operations (dependency install, index rebuild) take
  the Project workspace lease under the same fence discipline.
- **Residual (named, not hidden):** a zombie that survives fencing with valid git credentials could
  still push to the *external* remote — outside the fence perimeter. Mitigation: git credentials
  are per-Run scoped and revoked at sandbox teardown (§11); the R10 epic records this residual in
  its threat model explicitly.

### 6.4 Reconcile-safe integration (re-entrancy for external-effect steps, F4)

The Run reconciler treats the claim service as the source of truth for "who is doing what."
Re-entry re-reads claim + fence and never re-drives an item it does not hold with a current fence.
For steps with **external side effects**, idempotency is designed, not assumed:

- **A2A dispatch (Claiming → Running).** The shim task id is **deterministic** — `a2a_task_id =
  run_id` — and the shim **dedups on task id**: a second submit with an existing id reattaches to
  the in-flight task instead of starting a second agent execution. Before submitting, the
  reconciler writes a durable dispatch marker (`run.dispatched_task_id`, `run.dispatched_at`) in
  the same transaction as the state transition. Both crash windows are then safe: crash **after**
  submit but **before** the marker → re-entry re-submits the same deterministic id and the shim
  dedups; crash **before** submit → re-entry finds no marker and submits once. **No crash window
  produces two agent executions.** Shim-side dedup on the deterministic id is a conformance
  requirement (§10.1, ISI-2114).
- **Collecting / artifact emission.** `coord.artifact` enforces `UNIQUE(work_item_id, run_id,
  kind)` with content `sha256` (§6.1); registration is an upsert, so a re-entered Collecting phase
  republishes the same content-addressed row — never a duplicate artifact.
- **Status transitions** are conditional UPDATEs (`… WHERE status = :expected`), so a stale
  reconcile pass cannot resurrect or double-advance a Run.

This is why coordination lives in Postgres transactions, not controller memory.

### 6.5 Audit (FR-B4/D4/NFR-OBS1)

The `coord` schema *is* the audit log — every checkout, comment, artifact, and completion is an
immutable-append row with principal + timestamp. The apiserver exposes a read-only audit query API;
the console renders it (§13).

### 6.6 Domain events (transactional outbox, §17.4)

Every coordination state change — claim acquired, handoff, comment, completion — **also writes a domain
event to the Postgres `outbox` table in the same transaction** (§17.4). The audit log (§6.5) and the
outbox are complementary: the audit log is the **queryable durable history**; the outbox is the
**at-least-once delivery feed** to out-of-process plugin consumers. Both are Postgres rows written in the
state-change transaction, so neither can diverge from what actually committed. **The outbox is emit-only
and read-only downstream — it grants no custody and exposes no claim/lease/fence surface** (the §17.4
guard); coordination custody remains solely in the fenced `claim` table (§6.2/6.3).

*Satisfies:* FR-B1…B4, NFR-REL1/REL2, NFR-OBS1, D4. *Risk owned:* R10. *Closes review findings
F1–F4 (ISI-2132 review → ISI-2135 design fix).* *Trade recorded:* ADR-003
(Postgres row-lock + fencing vs bespoke lease service / etcd lease / Redis lock), ADR-023 (outbox, §17.4),
ADR-025 (fence-before-release reclaim + deterministic dispatch id, §18).

---

## 7. Knowledge Record — Memory Service (OQ6 confirmed, OQ10, F5, F7/F16)

### 7.1 Shape & build-vs-integrate (OQ10 / F13)

**Decision — integrate, don't invent.** The memory service is a **first-class KSquad Go service**
(FR-E1, LOCKED) that **wraps `pgvector`** in the shared Postgres (ADR-001). We own the API, schema,
provenance, and trust model; we borrow proven vector storage. This mirrors the org's own Sympozium
finding (MemPalace: PR#45 debated sidecar-MCP vs centralized `sqlite-vss`; centralized won) —
KSquad's version is centralized memory over `pgvector`.

**MVP tool surface (confirms CEO Gate 1's OQ6 cut).** Exposed to agents as **MCP tools** (FR-E2):

| MCP tool | v1 | Backing |
|----------|----|---------|
| `memory_search(query, scope)` | ✅ | pgvector cosine over `memory_record.embedding` |
| `memory_write(content, kind, tags)` | ✅ | insert w/ provenance envelope (§7.3) |
| `diary_append(entry)` / `diary_read(agent, last_n)` | ✅ | per-agent diary rows |
| `kg_add` / `kg_query` (relations) | ⛔ fast-follow | Postgres relation table, post-v1 |

Embeddings: a pluggable embedder (default: a small local model served in `ksquad-system`, or an
allowlisted embedding endpoint) — the provider is config, behind a seam, so an air-gapped cluster can
swap it. The **storage/retrieval backend itself is likewise behind a `MemoryBackend` seam (§7.6)**:
`pgvector` is the default and v1 backend; alternative backends (e.g. GRAIL, ISI-2142) plug in as a
memory SDK without changing the MCP tool surface or the §7.3 trust model. KG relations are **explicitly
a fast-follow**, not a v1 blocker (PRD §11.2).

### 7.2 Data model (Postgres `memory` schema)

`memory_record(id, scope_team_id, scope_project_id, kind, content, embedding vector, author_principal,
author_run_id, author_agent_id, written_at, invalidated_at)` ·
`diary_entry(id, agent_id, team_id, entry, created_at)`.

### 7.3 Trust boundary — the F16 resolution, implemented (F7, NFR-SEC6, D6)

CEO Gate 1 ratified: **memory is a provenanced knowledge record, never a coordination back-channel.**
Implemented as three enforced rules — this is the *architectural* resolution of the locked-vs-locked
tension (first-class shared memory vs no-P2P):

1. **Writes are authorized + provenanced (FR-E6).** Every `memory_write` requires an authenticated
   principal; the row records `author_principal / author_run_id / author_agent_id / written_at`.
   Unattributed or unauthorized writes are rejected at the service, not the DB. A principal cannot
   write a record attributed to another principal — impersonation is impossible by construction.
2. **Reads return an untrusted-provenance envelope (FR-E7).** `memory_search`/`diary_read` never
   return bare text; they return `{content, author, written_at, scope, trust: "untrusted"}`. The shim
   surfaces provenance to the agent so stored knowledge is consumed as *cited, attributable input*,
   not as trusted system context. This is the memory-poisoning defense (D6/R9): a hostile write can
   be *seen*, *attributed*, and *distrusted*, never silently injected as authority.
3. **Scope is the tenancy boundary (FR-E5).** Every read/write is filtered by `scope_team_id`
   (+ optional project). Cross-tenant read/write is denied by construction; the service never issues
   an unscoped query. Per-principal partitioning bounds what one compromised agent can influence.

**Why this is not a P2P channel.** Coordination handoffs — "claim this, I'm done, your turn" — have
*no expression* in the memory API; they only exist in the `coord` claim/comment tables (§6), which
are checkout-gated and fenced. Memory holds durable *facts/decisions*, tagged and attributed. Agent A
writing a fact that agent B later reads is **legible, provenanced knowledge sharing**, not covert
coordination: B sees who asserted it, when, and that it is untrusted. The no-P2P *spirit* is honored
because the *coordination act* (transfer of work custody) is structurally confined to the fenced
work-item record.

### 7.4 Durability (NFR-REL3)

Memory writes are ordinary Postgres commits; a crashed agent mid-write either commits or rolls back —
it cannot corrupt the knowledge record. `invalidated_at` gives a soft-retract path (a later authorized
write can supersede a fact) without destroying the audit trail.

### 7.5 Per-Project Discussion Room (Theme J, FR-J1…J4; ISI-2147) — legible talk, **not** coordination

> **Decision (Henrik, CEO review 2026-08-11):** each `Project` gets a Postgres-backed, threaded,
> provenanced discussion room that the memory service can query. It is **conversation, not custody** —
> the locked "no P2P coordination / durable-work-item" decision **stands**, enforced by construction.

**Shape & storage.** A new **`discussion` schema** in the shared Postgres (ADR-001 — a schema, not a
new datastore): `discussion_thread(id, project_id, team_id, title, created_by, created_at)` ·
`discussion_message(id, thread_id, parent_id, author_principal, author_agent_id, body, created_at,
invalidated_at)`. Threaded (`parent_id`), scoped per Project/Team, every message provenanced with an
authenticated principal + timestamp — the **same write-auth + provenance rules as memory** (§7.3.1).
Soft-retract via `invalidated_at` (§7.4), so a superseded message decays without losing the trail.

**Memory-queryable.** The memory service indexes discussion messages in `pgvector` and returns them
through `memory_search` (and a scoped `discussion_search(project)` MCP tool) under the **identical
untrusted-provenance envelope** (§7.3.2): a discussion message handed to an agent is *cited,
attributed, and marked `trust: "untrusted"`* — consumed as knowledge to weigh, never as authority.

**Why this is NOT a coordination channel (the §7.3 argument, applied again — and it must be, because
threaded messaging superficially *looks* like P2P).**
1. **Discussion carries talk, not work custody.** There is no `claim`, `lease`, or `fence_token` in the
   `discussion` schema, and no mapping from a discussion message to a change of work-item holder.
2. **The coordination act has no expression here.** Transfer of custody of a work item exists *only* in
   the fenced `coord` claim/comment tables (§6), checkout-gated and fenced. Agent A asking a question a
   human or agent B answers in a thread moves no item, claims nothing, and is fully attributable.
3. **So the no-P2P *spirit* is honored for the identical reason memory honors it (§7.3):** the
   coordination primitive stays structurally confined to the fenced work-item record; everything else
   is legible, scoped, distrusted talk. Discussion is *how people and agents reason in the open*; the
   `coord` record is *where custody actually moves*.

The room is served by the apiserver and rendered per Project in the console (§13), behind the same BFF
authorization choke point (§13) and the same Team-scope tenancy filter as memory (§7.3.3). It is a
**human-in-the-loop collaboration surface** (FR-J1/J2), messages are **author-attributed** (FR-J3, the
provenance above), and it is **`Project`-scoped and never crosses tenancy boundaries** (FR-J4,
NFR-SEC7) — the same namespace/Team-scope filter that gates memory reads applies unchanged.

**OQ15 (room storage/persistence + structural distinctness) — resolved.** Storage is the Postgres
`discussion` schema above (backing-store question answered — a schema, not a new datastore, ADR-001).
Structural distinctness from the two records is enforced **by construction, not by convention**: the
schema has no `claim`/`lease`/`fence_token` column and no custody-transfer expression (the three-point
argument above), so it *cannot* be a coordination record; and it is provenance-and-trust-marked exactly
like memory (untrusted-read envelope, §7.3.2), so it does not silently become an authoritative knowledge
record either. NB: ISI-2147's "memory-backed" framing is satisfied by the pgvector projection — but the
**fence holds regardless of backing store** (agents never mine the room as trusted context). This fence
is flagged for CEO ratification (PRD §13, R13); the architecture implements it as if ratified and
provides a **read-mostly fallback** (§13 scope guard) if the CEO gate narrows it.

*Satisfies:* Theme J (FR-J1…J4), NFR-SEC7, OQ15 (resolved); consistent with FR-E5…E7 trust semantics,
NFR-SEC6. *Trade recorded:* ADR-019 (discussion-room storage — Postgres `discussion` schema,
memory-projected, coordination-free by construction). *Touchpoints:* §7.3 (trust boundary reused), §13
(surface), §17.3 (layout), §19/§22.

### 7.6 Memory Fan-out & Backend Seam (ISI-2142 / GRAIL) — pgvector is source-of-truth

> **Decision (Henrik, CEO 2026-08-11, refined via ISI-2156):** **Postgres/pgvector remains the memory
> source-of-truth.** GRAIL (ISI-2142) is the **event seam's first consumer** — memory-write events
> **stream to GRAIL** (OTLP / SmartScape / DQL) via the §17.4 plugin outbox, as a downstream
> analytical/observability sink, **not** a backend swap. The trust model and the MCP tool surface do
> not move.

- **GRAIL as the first plugin consumer (ISI-2142).** Memory writes (§7.3) already emit domain events to
  the §17.4 outbox. GRAIL subscribes to those events as an **out-of-process plugin** and streams them to
  Dynatrace GRAIL via OTLP/SmartScape/DQL. This is **read-only fan-out**: GRAIL *observes* memory writes;
  it does not author, gate, or hold memory. **pgvector stays source-of-truth** for
  `memory_search`/provenance/trust (§7.1/§7.3). GRAIL is its own Phase 4 story, never a v1 dependency.
- **Why fan-out, not dual-write or backend-swap.** Streaming from the **transactional outbox** gives
  **atomic capture** (the event exists iff the memory write committed) without coupling the write to
  GRAIL's availability — a synchronous dual-write would make memory writes fail when GRAIL is down. And
  keeping pgvector as source-of-truth preserves the §7.3 trust model and the ADR-001 single-Postgres
  install; GRAIL is an *additive* analytical surface, not a substitute record.
- **Backend seam remains (secondary).** The memory service still speaks an internal `MemoryBackend`
  contract (§7.1) so the *storage* engine is swappable in principle — but v1's decision is explicit:
  **pgvector is the source-of-truth backend; GRAIL is a consumer.** Swapping the source-of-truth backend
  is out of scope for v1.
- **Trust model unchanged.** Write-auth + provenance + untrusted-read + Team-scope (§7.3) are enforced
  **above storage and before fan-out**; GRAIL receives already-provenanced events and gains **no
  authority over agents** — a downstream sink can never become trusted context.

*Satisfies:* new (memory fan-out / GRAIL consumer, ISI-2142 via ISI-2156); preserves FR-E1…E7, the §7.3
trust boundary, ADR-001/004. *Trade recorded:* ADR-024. *Touchpoints:* §17.4 (event seam), §7.1/§7.3,
§17.3 (layout), §19/§22.

*Satisfies:* FR-E1…E7, NFR-SEC6, NFR-REL3, D6. *Positioning:* parity, not moat (F5) — invest to reach
and defend parity (S7), do not oversell. *Trade recorded:* ADR-004, ADR-019 (§7.5), ADR-024 (§7.6).

---

## 8. Run Lifecycle & Reconciliation (I1 — the reconcile control plane)

The `Run` is a reconciled workload with an explicit, crash-safe state machine — the delta vs
heartbeat orchestration (F1–F4, R4).

```
 Pending ─► Claiming ─► Running ─┬─► Succeeded
    ▲          │           │     ├─► Failed ──(retryPolicy, backoff)──► Claiming
    │          │           │     └─► Cancelled (operator kill, FR-A6/F4)
    │          │           ▼
    │          │        Paused ──(credential expiry, §11)──► Running (on Secret refresh)
    └──────────┴── retry/backoff (sandbox or agent failure, FR-A5) ──┘
```

- **Claiming:** Run reconciler requests a warm sandbox from `SandboxPool` (§9) keyed by
  (RuntimeClass × `AgentRuntime` image), then **assembles the pod** (§5.3.4): init-staged toolchain
  packs + capability-gated service sidecars merged from the Run's `Skill.requires`. Claim latency, not
  cold boot (NFR-PERF1/S9), gated on ISI-2113 numbers.
- **Running:** shim invoked over A2A (§10); agent works the item(s) through the coordination record
  (§6) and memory (§7); SSE progress streamed to apiserver → console (FR-F2/NFR-PERF2).
- **Failure/resume (FR-A5, NFR-REL1/REL2):** a dead sandbox/agent is detected (lease non-renewal +
  pod status); the reconciler runs the §6.3 **reclaim protocol — fence the pod first, release the
  claim second** — and retries with backoff. **No coordination state is lost** because it is in
  Postgres, not the pod.
- **Kill (FR-A6/F4):** operator cancels → reconciler tears down the sandbox pod (SIGTERM→SIGKILL),
  releases claims, marks `Cancelled`. Sandbox teardown is prompt because the pod is disposable (§9.3).
- **Pause (§11):** an auth-failure signal from the shim transitions the Run to `Paused` with a clear
  operator condition (FR-F6/S10), resuming on credential refresh — never an opaque failure.

*Satisfies:* FR-A4/A5/A6, NFR-REL1/REL2, S8. *Trade recorded:* ADR-005 (reconcile state machine vs
job/heartbeat).

---

## 9. Sandbox & Warm Pool (OQ2 provisional, OQ5, F6/D7)

### 9.1 Isolation runtime (OQ2 — provisional, spike-gated)

**Provisional decision: gVisor as the default RuntimeClass; Kata opt-in for high-assurance;
`runc` only for explicitly-trusted dev.** Rationale under the agent threat model (arbitrary
shell/git/build — PRD NFR-SEC2):

- **gVisor** — strong syscall-interception isolation with pod-like start latency; runs on managed
  clusters without nested virtualization. **First-hand org evidence (MemPalace / ISI-1825):** OpenClaw
  already runs on gVisor (`kernel 4.19.0-gvisor`, green boot) in the agent-sandbox work — a launch
  runtime is *known to work* on gVisor. This is the pragmatic default.
- **Kata** — stronger (VM) isolation, heavier, frequently needs nested virt unavailable on managed
  K8s. Offer as a per-Team/`runtimeClassHint` opt-in for high-assurance tenants; do not make it the
  floor.
- **`runc`** — rejected as a default for untrusted code; allowed only behind an explicit
  "trusted-dev" flag.

**Structural safety:** RuntimeClass is a **per-Team / per-Project knob** (`SandboxPool.runtimeClass`,
`Role.runtimeClassHint`), not a hardcode. **ISI-2113 has not run** (§21); its claim-latency +
isolation numbers set the *default* and the *pool-sizing policy*, but the architecture stands whatever
it picks. If ISI-2113 shows gVisor's LLM-bound overhead is unacceptable, we flip the default
RuntimeClass — no structural change.

### 9.2 Warm pool (FR-C1/C4, S9, R2)

- `SandboxPool` reconciler keeps **N pre-booted, image-pre-pulled** sandbox pods `Ready` per
  **(RuntimeClass × `AgentRuntime` image)** key so a Run claim is grab-time. Warm pods carry only the
  agent base; **skill-specific toolchains attach per-Run via node-cached init packs** (§5.3.2) — so
  the pool stays one-dimensional (no warm pod per skill combination) while an `ImageUpdater` bump
  (§5.3.5) drains and re-warms the affected key. **Hybrid regime (brainstorming OQ9/F14):** interactive
  Runs draw from the warm pool; **batch/non-interactive Runs may cold-start** (zero idle cost, and
  sidesteps reuse-contamination) — routed by a Run class field. Both regimes sized by ISI-2113.
- Pool size is **policy-driven, not fixed** (FR-C4): a target-ready-count with autoscale bounds
  (min/max, scale-on-claim-rate). Default policy ships; numeric tuning is post-ISI-2113 (NFR-SCALE2).

### 9.3 Hygiene — reset-or-teardown (F6/D7, FR-C6, NFR-SEC5) — **teardown-and-replace**

**Decision: teardown-and-replace, not in-place reset.** After a Run completes, its sandbox pod is
**destroyed** and the pool replenishes a **fresh** pod from the template. Rationale (ponytail:
edge-case-correct over cheaper-but-flimsier): proving an in-place scrub left *zero* residue
(scratch files, in-memory secrets, git worktree state, poisoned build cache) is a losing game;
destroying the pod is provably clean and warm-pool economics survive because "warm" is a property of
the *pool* (async replenish), not of an individual reused pod. **A sandbox is never reused across
Runs or principals.**

### 9.4 Workspace & concurrency (OQ5, FR-C2/C5, per-principal scoping F6/D7)

- Each `Project` has a **workspace PVC** (source + build cache) persisting across Runs (FR-C2).
- **Concurrent Runs on one Project (OQ5):** the workspace is mounted, and each Run operates in its
  own **git worktree** (native git, not invented locking — ponytail rung 4) over the shared checkout,
  so concurrent Runs don't clobber. Operations needing exclusive write (dependency install, index
  rebuild) take a **Project workspace lease** (same lease primitive as §6.3). Default PVC access is
  `RWO` with worktree-per-Run; `RWX` (if the storage class supports it) enables true parallelism.
- **Per-principal scoping (F6/D7):** the **build cache is partitioned per principal** (separate
  subpath/volume), so one user's cached artifacts can't poison or leak into another principal's Run.
  Workspace access is scoped per principal, not merely per Project — a shared Project workspace never
  exposes one user's secrets/source to another agent's Run. Verified by the S4 blast-radius test's
  reuse/residue case (NFR-SEC5).
- **Per-Run build browser read model (Theme K, FR-K1/K2; ISI-2148) — content source & scoping (OQ17
  resolved):** the PRD asks *which* content source (workspace PVC vs git/PR diff vs artifact store) and
  *how* read access is scoped per principal — here it is. **Source = the Run's own workspace worktree,
  not a separate artifact store** (FR-K2): because each Run already works in its **own git worktree**
  over the persistent workspace PVC, the per-Run file tree, diffs, and code view are *already a native
  git projection* — file tree = fs walk / `git ls-tree`, diffs = `git diff` (worktree vs base ref),
  code view = file read. **git is the diff engine; we build none** (ponytail rung 4). A **live** Run is
  read through the shim (its pod has the workspace mounted — a read-only query over A2A); a **completed**
  Run — whose pod is torn down (§9.3) — is read by snapshotting the worktree diff as a `coord`
  **artifact** at completion (§6.1) and/or an **on-demand read-only workspace-reader** pod that mounts
  the Project PVC `RO` at the Run's commit. **Per-principal read scoping (FR-K1, FR-C6, NFR-SEC5):**
  access is gated at the BFF (§13) by the same principal/Team-scope filter as the rest of the console,
  and because the build cache is **partitioned per principal** (above), the browser can only surface the
  requesting principal's own Run/worktree — a shared Project workspace never leaks one user's source or
  build residue to another. Strictly read-only, tenancy-scoped to the Run's Team namespace, never a
  write path. Surfaced in the console (§13) as *legibility, not an editor* (scope guard R6).

*Satisfies:* FR-C1…C6, NFR-SEC2/SEC5, NFR-PERF1, NFR-SCALE2; Theme K (FR-K1/K2), OQ17 (resolved).
*Spike-gated:* RuntimeClass default, pool sizing (ISI-2113). *Trade recorded:* ADR-006
(teardown-vs-reset), ADR-007 (worktree-vs-lock), ADR-021 (build-browser read model, §13/§18).

---

## 10. Agent Shims & A2A (OQ3, OQ12/F9, I2 — the moat seam)

### 10.1 Shim placement & contract (absorbs ISI-2114 intent)

- **One shim per runtime, as a sidecar in the sandbox pod.** The agent runtime runs in the pod with
  the workspace mounted; the shim sidecar terminates **A2A southbound** from the control plane and
  translates to the runtime's native invocation (OpenClaw gateway/sessions API; Hermes native), keeps
  the call **workspace-local**, streams **SSE progress**, and emits **artifacts** to the coordination
  record. (Sidecar over standalone Deployment because the agent needs the local workspace; over
  init-container because it is long-lived per Run.)
- **Shim ↔ AgentRuntime:** the shim is built into (or co-scheduled with) the `AgentRuntime` image
  (§5.3.1); conformance (ISI-2114) is asserted per `AgentRuntime.type`. The two are the two halves of
  one seam.
- **Agent Card generated from the `Agent` CRD + resolved `AgentRuntime`** (skills, model, auth method,
  capability flags including `docker`/`github`/`packageInstall`).
- **Capability flags are first-class (FR-D4, R3):** streaming / tool-calls / interactive-prompt /
  credential-type / **model-endpoint override (`byoModelEndpoint`, §10.3)** are negotiated on the Agent
  Card; the core treats gaps as declared capabilities, never as special-cased hacks. A runtime with no
  interactive-prompt support advertises that; the core routes around it.
- **v1 shims: OpenClaw + Hermes** (FR-D3/S6); Claude Code + OpenCode follow (Phase 2).
- **Conformance suite (FR-D5, owned by ISI-2114):** a vendor runs it independently; passing ⇒ the
  runtime drops into any squad with **zero core changes** (S5/NFR-EXT1). **ISI-2114 has not been
  executed** (§21) — the shim *contract* is designed here; the *reference shim + conformance
  assertions* are the spike's deliverable and must land before S5/S6 can be claimed.

### 10.2 Spec-drift isolation (OQ12 / F9 / R11)

- A2A and MCP wire versions are **pinned** in a single versioned adapter package (`pkg/a2a@rev`,
  `pkg/mcp@rev`). The core speaks an **internal stable interface**; the external spec revs are
  isolated *at the adapter seam only*. Upstream churn stays at the seam, never reaches the Run
  reconciler or the coordination/knowledge services.
- The conformance suite asserts against the **pinned** A2A/MCP rev; spec upgrades are a deliberate,
  gated change (bump rev → re-run conformance → release), not an ambient break. Capability negotiation
  absorbs minor variance.

### 10.3 Model-provider seam — BYO endpoints & Ollama (ISI-2157)

> **Decision (Henrik, CEO 2026-08-11, ISI-2157):** an `Agent` can target a **BYO model endpoint** — its
> own **Ollama** instance (a local model) — via a **Secret-ref endpoint + per-`Agent` model**. This is a
> *model-provider* seam, **distinct from the *agent-runtime* seam** (§5.3/§10.1), and it **reinforces the
> BYO-credential lock** (§11) rather than reopening it.

- **Runtime vs model provider — the honest distinction.** §5.3/§10.1 make the *coding-agent runtime*
  (OpenClaw / Hermes / …) pluggable; the **model** those runtimes call is a *separate axis*. Ollama is
  **not a coding runtime — it is an OpenAI-compatible model server.** So "Ollama runtime adapter" is
  implemented as a **model-endpoint override**: `Agent.spec.model` + an endpoint from a Secret ref,
  consumed by any runtime advertising the `byoModelEndpoint` capability. (Treating Ollama as an
  `AgentRuntime.type` would be a category error — recorded in ADR-026.)
- **Capability-negotiated (FR-D4).** A runtime advertises `byoModelEndpoint` (OpenAI-compatible base-URL
  override) on its Agent Card (§10.1); the core routes the Agent's endpoint + model to it. Runtimes that
  only speak a fixed vendor endpoint simply don't advertise it — no special-casing.
- **Credential shape (§11, third story).** The endpoint URL (+ optional token) is a **per-user Secret
  ref**; the model is `Agent.spec.model`. No interactive OAuth, no shared master credential — the same
  BYO-Secret discipline as the other two stories, so the lock holds.
- **Egress (§12.2).** A BYO Ollama endpoint (in-cluster Service or a LAN/remote host) is an
  **allowlisted egress target** on the Team NetworkPolicy — default-deny still holds; the endpoint joins
  the model-endpoint allowlist like any other provider.
- **Free CI / release-test lane (ISI-2157) — doubles the value.** Because Ollama needs **no paid API
  credits**, an Ollama-served model (a CI **service container** or a **self-hosted GPU runner**) is the
  **credential-free lane for smoke + e2e squad scenarios** and for running the **shim conformance suite**
  (§10.1, the ISI-2114 **Ollama lane**). Squad-level e2e becomes runnable in CI without vendor keys — an
  architecture-enables-testing win, not merely a runtime option.
- **Honesty.** Local models are weaker than frontier APIs; the Ollama lane is for **correctness/plumbing
  e2e + conformance**, not a production quality bar. Model quality is a per-`Agent` choice, never an
  architecture claim.

*Satisfies:* FR-D1…D5, NFR-EXT1/EXT2, R3, R11; Ollama / BYO model endpoint (ISI-2157); reinforces FR-G
(BYO creds) + S6/conformance. *Spike-gated:* reference shim + conformance assertions (ISI-2114, now incl.
the Ollama lane), pinned A2A/MCP rev. *Trade recorded:* ADR-008 (sidecar shim), ADR-009 (pinned adapter
seam), ADR-026 (BYO model-provider seam / Ollama, §10.3).

### 10.3 Model-endpoint seam & BYO Ollama adapter (CEO Gate 2, Henrik 2026-08-11)

**A model endpoint is not a runtime.** The coding-agent flavor (`AgentRuntime.type`, §5.3.1) is *which
CLI runs the work*; the **model endpoint** is *which inference server that CLI talks to*. They are
orthogonal seams — conflating them would re-introduce the R×T matrix ADR-015 just killed, one image
per (flavor × provider). So the endpoint stays **per-Agent configuration**, never baked into the image:

- **`Agent.spec.modelEndpointRef` → Secret** carries the base URL + auth for a BYO inference server;
  `Agent.spec.model` names the model to request. Absent the ref, the runtime uses its built-in
  provider default (Anthropic for `claude-code`, etc.). This is the same per-user Secret-ref discipline
  as credentials (§11, ADR-010) — KSquad holds no shared endpoint, and the Secret is mounted to the
  runtime container only, never logged, never on the Agent Card.
- **Ollama = one instance of the seam, not a special case.** A user points an Agent at their own Ollama
  server (`modelEndpointRef` → `{OLLAMA_HOST, model}`). Ollama's **OpenAI-compatible API** is what makes
  this boring: any runtime whose CLI speaks the OpenAI wire (`opencode`, `codex`) points at it by config
  alone — **zero new image, zero core change** (the S5 promise, applied to the model axis). A runtime
  hardwired to one vendor (`claude-code` → Anthropic) simply does not advertise `modelEndpointRef`
  support; that gap is a **declared capability** (§10.1), not a hack.
- **Local-model capability negotiation is first-class (§10.1, R3).** Local models routinely lack native
  tool-calling / structured-output / long context. The shim negotiates these on the **Agent Card** exactly
  as it does for runtime gaps — the core treats a missing capability as declared and routes around it,
  never assumes parity. This keeps "BYO weak local model" honest instead of silently failing mid-Run.
- **Egress (§12/ADR-012).** An **in-cluster** Ollama (the free-CI shape) is reached by a scoped
  `NetworkPolicy` allow to its Service — no internet egress opened. An **external** Ollama rides the same
  default-deny + allowlist/proxy path as any other endpoint (D8: external endpoint is untrusted transport,
  auth from the Secret). No new egress primitive.
- **Free release-testing lane (ISI-2157 CI, ISI-2114 Ollama conformance lane).** The shim conformance
  suite (§10.1) and the smoke + e2e squad scenarios need a model to run against; on paid APIs that costs
  credits per CI run. An **Ollama service container** (CPU, tiny model — conformance is wire-shape, not
  answer-quality) or a **self-hosted GPU runner** (heavier e2e squads) gives CI a **zero-credit model
  backend**. This makes conformance (the S5/S6 gate) actually runnable on every PR — the seam that was
  "designed but unexecutable without spend" becomes continuously verified. The Ollama lane is an
  **added row in the runtime/conformance matrix (ISI-2114)**, keyed on an OpenAI-compatible runtime +
  `modelEndpointRef` pointing at the CI Ollama.

*Satisfies:* FR-D3/D4 (runtime + capability negotiation, extended to the model axis), FR-G1 (per-user
Secret-ref, no shared endpoint), the CEO BYO-Ollama requirement. *Trade recorded:* ADR-026.
*Spike-gated:* which small model the CI lane pins + whether e2e needs the GPU runner (ISI-2157/ISI-2114,
tuning behind the seam, not structural). *Touchpoints:* §5.1 `Agent` CRD, §5.3.1, §10.1, §12, §11.

---

## 11. Credential Model — Two Concrete Stories (OQ11 / F15, FR-G)

**Vendor-neutral by construction — not Claude-shaped.** Per-user **Kubernetes Secret refs on the
`Agent` CRD** (FR-G1, LOCKED); KSquad never holds a shared master credential. Credential **type +
lifecycle are capability metadata** on the shim/Agent Card (FR-G2), so the core hardcodes no vendor's
auth flow. Two distinct stories ship at v1 (S6):

| Runtime family | Acquisition | Lifecycle | Secret shape |
|----------------|-------------|-----------|--------------|
| **Claude-family** | `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` | subscription-OAuth; refresh + graceful pause | per-user Secret ref (OAuth token) |
| **Second runtime (OpenClaw/Hermes — non-Claude)** | long-lived **API key / provider token** supplied directly | static (no interactive OAuth step); refresh only if the provider rotates | per-user Secret ref (API key) |

**Graceful pause/resume (FR-G3/S10, both models).** The shim detects an auth-failure signal from the
runtime and reports it over A2A; the Run reconciler transitions to `Paused` with an operator-legible
condition (FR-F6), **not** an opaque failure. Resume triggers on the referenced Secret updating
(operator rotates the token) — the operator watches the Secret and re-drives the Run. This holds for
both OAuth-refresh (Claude) and static-key (second runtime) models.

**ISI-2112 has not run** (§21). The *structure* (per-user Secret ref, pause-on-auth-failure, resume-
on-refresh) is spike-independent; ISI-2112's evidence sets the **exact OAuth refresh cadence, token
longevity, and concurrency-on-one-subscription limits**, and — per PRD §13 watch item / R1 — if
setup-token lifecycle proves unworkable at scale, that is a **CEO-gate conversation** owned by Alfred,
not an architecture reopening. OQ11's exact second-runtime token type/refresh is pinned per that
runtime's auth model as the shim lands.

**Consumption attribution & metering provenance (Theme I, FR-I2/I3, NFR-OBS3, OQ14 — resolved).**
Because every credential is a **per-user Secret ref** (FR-G1, LOCKED) and KSquad holds *no* shared
master credential, model/run consumption is **attributable to the owning principal by construction**
along the four axes `{user/principal, agent, run, project}` (FR-I2) — no shared-credential
disambiguation problem. The PRD's hard constraint (FR-I3, NFR-OBS3) is that metering must derive from
the **Run lifecycle / coordination record, not forgeable agent self-report**. The mechanism (OQ14):
- **Non-forgeable spine.** The axes and the *existence and shape* of consumption are anchored to signals
  the **control plane owns, not the agent**: the operator emits Run lifecycle events (start/finish,
  run-minutes) from its own reconcile (§8), and sandbox CPU/mem come from **kubelet/cAdvisor**, not the
  runtime. A compromised agent **cannot fabricate a Run, hide one, or misattribute one to another
  principal** — those axes live outside the sandbox's trust boundary (F18).
- **Best-effort token counts (the OQ14 precision bound).** Per-call token counts, where a runtime
  reports them, are surfaced by the shim over A2A and attributed to the anchored Run — but they are
  **runtime-reported and therefore best-effort**, explicitly *not* the authoritative billing axis. They
  are sanity-bounded against run-minutes/resource (a wildly inconsistent count is flagged, not trusted),
  and a runtime that reports nothing degrades to run-minutes/resource attribution rather than a gap.
- **Emission.** The apiserver/operator emit all of the above as **OTel metrics** labeled
  `{team, project, run, agent, principal, model}` (§17.2), which the console consumption dashboard (§13)
  aggregates. Actual currency cost is provider-side (BYO); KSquad reports an **estimate** via a
  configurable price table and **never claims to be a billing system of record** (FR-I2 cost precision
  best-effort) — an honest limit, not a hidden one.

*Satisfies:* FR-G1…G3, NFR-SEC3, S10; Theme I (FR-I2/I3), NFR-OBS3, OQ14 (resolved). *Spike-gated:*
OAuth refresh cadence/longevity (ISI-2112). *Trade recorded:* ADR-010, ADR-020 (consumption model,
§13/§18).

---

## 12. Multi-Tenancy & Isolation (OQ7, OQ4/F, NFR-SEC1…5)

### 12.1 Tenancy boundary — a squad is a namespace (OQ7)

**Decision: `Team` → one Kubernetes namespace.** The namespace is the RBAC / NetworkPolicy / quota /
Secret boundary (brainstorming §1.2; NFR-SCALE1). A Team's Projects, Runs, sandbox pods, workspace
PVCs, and per-user Secrets live in its namespace. The control plane lives in `ksquad-system`. Adding
squads = adding namespaces — no control-plane redesign (NFR-SCALE1). Within a Team namespace,
**per-principal** isolation of Secrets is enforced by RBAC + the per-principal workspace scoping
(§9.4), so multiple users in one squad don't cross-access credentials.

- Cross-squad isolation (NFR-SEC1/S4): namespace + default-deny NetworkPolicy + scoped RBAC +
  per-namespace PVCs. A Run cannot reach another squad's workspace, Secrets, or network. Verified by
  an explicit **blast-radius / hostile-Run test** (S4) including the §9.3/§9.4 reuse-residue case.
- Least privilege (D2/NFR-SEC*): an agent's ServiceAccount gets exactly its Role/Project grants,
  never cluster-wide.

### 12.2 Egress control (OQ4 / D5 / NFR-SEC4 / R7)

**Decision: default-deny egress NetworkPolicy per Team namespace + a model-endpoint allowlist, with
an optional egress proxy for corporate networks.** Two shipped mechanisms, one default:
- **Default:** per-Team NetworkPolicy allowlisting the required model/tool endpoints (and the control
  plane); everything else denied.
- **Optional (corporate/proxied nets — R7):** a Team-level `egressPolicyRef` injects `HTTPS_PROXY`
  into sandboxes to route model traffic via a forward proxy. Native env + native NetworkPolicy — no
  bespoke egress gateway (ponytail rung 4).

*Satisfies:* NFR-SEC1/SEC3/SEC4, NFR-SCALE1, D2/D5. *Trade recorded:* ADR-011 (namespace-per-Team),
ADR-012 (NetworkPolicy + optional proxy).

---

## 13. Operator Console — Node Frontend Approach (Theme F, NFR-USE2)

**Decision: a Next.js (React + TypeScript) app with a thin server-side BFF.** Names the frontend
approach the kickoff required.

- **Next.js** (app router, SSR) for a polished, accessible, responsive UI (NFR-USE2). Component/design
  system: Tailwind + a headless component kit (e.g. Radix/shadcn) so the Graphic Designer's visual
  direction (PRD §11.4) drops onto a coherent token system.
- **BFF, not direct kube.** The browser never talks to the Kubernetes API or Postgres directly; the
  Next.js server proxies/aggregates the **Go apiserver** (REST + SSE). This keeps one authorization
  choke point and one source of truth.
- **Live Run progress via SSE** (FR-F2/NFR-PERF2): the apiserver publishes an SSE progress bus fed by
  shim A2A-SSE; the console consumes `EventSource` (native — ponytail). Human-imperceptible lag under
  normal load.
- **Screens (FR-F1…F6):** squad overview (Teams→Projects→Run status); live Run stream; artifact/
  handoff inspection; **2-click kill** (S2/FR-F4); compose Team/Agent/Role/Skill/Project (create/edit
  CRDs — FR-F5); credential/auth state incl. paused-on-expiry signal (FR-F6/S10).
- **Dashboards (Theme I, FR-I1…I3; ISI-2146):** project-health / work-items (FR-I1) / consumption
  (FR-I2) views. Health + work-item state
  read from the `coord` audit (§6.5) and the `scm` mirror (§5.4) via the apiserver — **always
  available**. **Consumption** (per-Run/agent/principal token counts, run-minutes, sandbox resource, and
  an *estimated* cost via a configurable price table) rides the **OTel metrics pipeline** (§17.2), read
  through a **pluggable metrics-backend query seam** (Prometheus/OTLP-compatible) that **degrades
  gracefully** when no backend is wired — never a hard dependency, never a new billing datastore
  (ponytail). Attribution is **per-principal by construction** because credentials are BYO per-user
  (§11) — no shared credential to disambiguate.
- **Per-Project discussion room (Theme J, FR-J1…J4; ISI-2147, §7.5):** threaded, provenanced discussion
  rendered per Project; memory-queryable; `Project`-scoped (FR-J4, NFR-SEC7); coordination-free by
  construction.
- **Per-Run build browser (Theme K, FR-K1/K2; ISI-2148, §9.4):** read-only file tree / diff / code view
  over the Run's git worktree, per-principal scoped (FR-K1/NFR-SEC5). Legibility, not an IDE.
- **Dark + light theme is a v1 requirement (FR-F7, NFR-USE2; ISI-2150, mocks revision).** The console ships **both**
  themes at v1, implemented on the design-token system (Tailwind + CSS variables / `next-themes`),
  honoring `prefers-color-scheme` with a user toggle and meeting **WCAG AA contrast in both modes**
  (NFR-USE2 / accessibility) — a v1 acceptance item, not a post-v1 polish.
- **Scope guard (R6):** legibility, composition, discussion, and read-only build inspection — still
  **Not** an IDE, code editor, or general-purpose analytics tool beyond project-health/work-items/
  consumption.

*Satisfies:* FR-F1…F7, NFR-USE1/USE2, S2/S3; Theme I (FR-I1…I3), Theme J (FR-J1…J4), Theme K
(FR-K1/K2). *Trade recorded:* ADR-013 (Next.js BFF vs
SPA-direct-to-kube), ADR-020 (consumption model), ADR-021 (build-browser read model). *Depends on:*
Graphic Designer UX direction (parallel, PRD §11.4) — theme tokens for both modes.

---

## 14. Sympozium Competitive Teardown (evidence-based, first-hand)

Grounded in the org's **hands-on production use** of Sympozium (MemPalace: BMAD ensembles deployed;
OTel PRs #11/#18 and ISI-1406 contributed upstream; tutorial ISI-1384/1387). Not a spec skim.

### 14.1 What Sympozium actually is (from our own deployments)

- **CRDs:** `Ensemble`, `Agent`, `Model` (upstream chart v0.10.x; the older PersonaPack/
  SympoziumInstance era is retired). `Ensemble ≈ our Team`.
- **Coordination:** delegation / sequential / supervision / stimulus **edges**, a **SpawnRouter**
  (`delegate_to_persona → child AgentRun → AwaitingDelegate → NATS result`), **NATS result-passing**,
  and **Channels** with a `channel_router` (allowed/denied). Event/result-driven.
- **Memory:** first-class — a **SQLite sidecar** per agent, `sharedMemory = Team.Knowledge`, memory
  seeds, a `/memory` TUI; **semantic search in flight (PR #45)**, debating sidecar-MCP vs centralized
  `sqlite-vss`.
- **Models:** multi-model via the `Model` CRD + Ollama (e.g. qwen3.6 / qwen3.5:122b).
- **Sandbox:** gVisor RuntimeClass supported (`--with-sandbox`).

### 14.2 Convergent prior art (NOT our moat — say so)

k8s-native CRDs, isolated pods/sidecars, **first-class memory** (F5 — parity), multi-model, gVisor
sandbox. We must not oversell any of these as differentiation.

### 14.3 The three honest deltas (and how the architecture realizes each)

1. **Agent-runtime-agnostic shims (I2, §10).** Sympozium's agents are **native personas** driven by
   its own controller — it is *not* architected around swappable third-party runtimes behind a stable
   A2A⇄native shim contract with a vendor-runnable conformance suite. KSquad's shim seam (a vendor
   ships a conformant shim, zero core change) is the delta. *This is the moat's sharpest edge.*
2. **Reconcile control plane (I1, §8).** Sympozium is **delegation + NATS-result-passing** (SpawnRouter,
   AwaitingDelegate). KSquad is **desired/observed reconciliation** of a `Run` workload with an explicit
   crash-safe state machine, retry/backoff/resume from the primitive. Different control primitive, not
   a UI skin.
3. **Native durable work items (I4, §6).** Sympozium coordinates via **ephemeral NATS messages /
   Channels / result-passing**. KSquad's coordination record is **durable, fenced, auditable work items
   with checkout/lease + crash-resume** in Postgres. Durability + auditability + crash-safe custody
   transfer is the delta.

**Positioning discipline (F5):** lead with these three; treat memory as parity we reach and defend
(S7), never as the headline. Track Sympozium — and the funded entrant + the k8sgpt author (R8) — as
live competitors, not an empty market.

---

## 15. The Coordination Spine as a First-Class Engineering Risk (F8 / R10)

Restated for Epics so it is staffed, not assumed:

- The checkout/claim/**lease** + concurrency work (§6) is a **from-scratch distributed-systems build**
  and the **most correctness-critical piece of v1**. It is a **foundational epic sequenced first**,
  not a spine checkbox.
- **De-risking lever (ADR-001/003):** by putting it on Postgres row-locks + fencing tokens rather
  than a bespoke lock service or etcd leases, we convert an open-ended distributed-systems build into
  a well-understood transactional-database problem. This is the single biggest schedule de-risk in the
  architecture — but it is still a real, test-heavy build (contention, crash-reclaim, zombie-writer
  fencing, idempotent reconcile), and v1 estimates must weight it accordingly.
- **Test obligation:** a dedicated concurrency/chaos test suite — parallel double-claim attempts,
  crash-mid-claim reclaim, GC-pause zombie-writer rejection, idempotent-reconcile re-entry — is a v1
  gate, not a nice-to-have (S8). Two cases are named acceptance gates for the R10 epic (F1/F4,
  ISI-2135):
  - **Zombie-writer-vs-PVC (F1):** freeze a claim holder's sandbox pod past lease expiry (simulated
    GC pause), let the reconciler reclaim to a new Run, then unfreeze the old holder. Assert: the old
    pod was terminated *before* the claim was released (§6.3 ordering), its stale-fence memory and
    artifact writes are rejected, and the shared Project workspace shows no cross-Run interleave.
  - **Double-dispatch (F4):** kill the reconciler between A2A submit and the dispatch-marker write,
    then restart. Assert: exactly one shim task exists for the Run (deterministic `a2a_task_id =
    run_id`, shim dedup) and exactly one agent execution occurred; same for a re-entered Collecting
    phase (artifact upsert, no duplicate rows).

---

## 16. Deployment & Install Story (S1 — ≤4h install-to-first-squad)

The architecture is shaped by the S1 acceptance test (design partner: Paperclip platform team).

- **One `helm install`** brings up `ksquad-system`: CRDs, operator, apiserver, memory service,
  console, and Postgres (CNPG dependency, single-instance default profile; HA is a values toggle).
- **Sane defaults, docs alone:** default RuntimeClass (gVisor if present, else a clearly-flagged
  fallback), default warm-pool policy, default egress NetworkPolicy, bundled OpenClaw + Hermes shims.
- **First-squad quickstart:** create a `Project` (repo + workspace), define 2–3 `Agent`s from the two
  bundled runtimes, group into a `Team`, start a `Run` — from the console or YAML, no orchestration
  code (S3).
- **Single stateful dependency (§4)** is what keeps this a one-afternoon install; every avoided
  datastore is time the platform engineer doesn't spend.

### 16.1 Networking & exposure — Gateway API (Theme L, FR-L1…L3; ISI-2149, CEO directive 2026-08-11)

**The chart creates exposure, it does not assume it.** The chart renders the `Gateway` + `HTTPRoute`
resources for the console and the apiserver (FR-L1) — the apiserver route **must preserve the SSE
stream** (no response buffering, no default idle timeout that kills a long-lived progress stream, §13).
Gateway API (not a legacy `Ingress`) is the primitive because its `HTTPRoute` timeout/backend semantics
express the SSE requirement portably.

- **`gatewayClassName` is a *required* values input** *when Gateway-mode is selected* — never hardcoded,
  never the cluster default. cilium / envoy / istio / traefik are all valid targets; the chart
  **references** the operator-provided `GatewayClass` and **never creates one**.
- **Listener + TLS via values:** hostnames, cert secret refs, HTTPS-redirect are all values-exposed, so
  the platform engineer wires their own DNS/cert story without editing templates.
- **Gateway-less fallback (OQ16 — resolved; keeps the ≤4h install true).** Not every target cluster has
  a Gateway controller installed, and the PRD's S1 ≤4h install (FR-L3, NFR-USE1) cannot depend on the
  operator first installing one. So exposure is a **`values.exposure.mode` switch** with three
  documented, pre-flightable options, defaulting to fail-fast clarity rather than a silent guess:
  `gateway` (renders `Gateway`+`HTTPRoute`, requires `gatewayClassName` — the preferred production
  path, full SSE-timeout control); `ingress` (renders a plain `Ingress` with the SSE-safe annotations
  for the common controllers — a **graceful degrade** for clusters that have an Ingress controller but
  no Gateway API); and `clusterip` (renders `Service` only, console reached via `port-forward` /
  operator's own LB — the zero-dependency path that **always** brings the stack up so first-squad can be
  reached within the window even on a bare cluster). The chart **pre-flights** the selected mode (a
  Gateway-mode install with no matching `GatewayClass` fails the install with a clear message, not a
  dangling route), so the ≤4h acceptance never hinges on a cluster capability the operator didn't
  confirm. `ingress`/`clusterip` are documented as **not** giving the same portable SSE-timeout
  guarantees as Gateway — an honest trade, surfaced, not hidden.

### 16.2 Storage — explicit StorageClass (Theme L, FR-L2; ISI-2149, CEO directive 2026-08-11)

**Every PVC the install renders takes its `storageClassName` from values (FR-L2)** — Postgres (CNPG) and
per-Project workspace PVCs (§9.4). Relying on the cluster-default StorageClass is treated as a
**misconfiguration that fails the install fast**, not a silent fallback. Access mode is `RWO` by
default with `RWX` optional (§9.4); the chart docs state which behaviors are storage-class-capability
dependent (RWX, expansion, snapshots) so the class can be pre-flighted.

*Satisfies:* S1, Theme L (FR-L1…L3), NFR-USE1, OQ16 (resolved). *Trade recorded:* ADR-014 (bundle
Postgres via CNPG vs require external DB), ADR-022 (Gateway-API exposure + explicit StorageClass +
Gateway-less fallback vs Ingress-only / cluster-default).

---

## 17. Cross-Cutting Concerns

### 17.1 Security threat model (agent-as-adversary, F18)

Every data-plane principal is hostile. Layers: gVisor syscall isolation (§9.1) · namespace + RBAC +
NetworkPolicy + per-namespace Secrets (§12) · teardown-and-replace sandboxes + per-principal workspace
scoping (§9.3/9.4) · memory write-auth + provenance + untrusted-read (§7.3) · fenced coordination
(§6.3) · credentials never logged/echoed cross-squad (NFR-SEC3). Verified by the S4 blast-radius test
(hostile Run + reuse-residue + memory-poisoning cases) — **tested, not asserted** (F6/F7).

### 17.2 Observability (NFR-OBS1/OBS2) — hand-off to Observability Agent

The `coord` schema is the audit trail (§6.5). Runs emit OTel traces/metrics/logs; SSE carries live
progress. The org has deep OTel practice (Sympozium PRs, ISI-1406) — the observability *strategy*
(span/metric taxonomy, memory read/write counters, claim/lease metrics, per-Run trace correlation) is
delegated to the Observability Agent (§20 handoff), seeded by that prior art. **Consumption/usage
metrics (ISI-2146)** — per-Run token counts, run-minutes, sandbox resource, and estimated cost, labeled
`{team, project, run, agent, principal, model}` (§11) — are part of this same OTel metric taxonomy and
feed the console consumption dashboard (§13) through the pluggable metrics-backend query seam; they add
no datastore.

### 17.3 Go backend service layout

`ksquad-operator` (controllers, incl. the **repo-sync reconciler** §5.4 and `ImageUpdater` §5.3.5) ·
`ksquad-apiserver` (coordination record + audit + SSE + **SCM webhook ingress** §5.4 + SCM-mirror /
discussion / dashboard read APIs, one binary) · `ksquad-memory` (MCP server + pgvector, indexes the
`discussion` schema §7.5). Shared `pkg/a2a`, `pkg/mcp` (pinned adapter seams, §10.2), `pkg/coord`
(claim/lease/fencing), `pkg/scm` (**source-control provider seam** §5.4, GitHub first), `pkg/events`
(**versioned event catalog + transactional-outbox delivery workers** §17.4), `pkg/apis` (CRD types). The
`ksquad-apiserver` additionally runs the **outbox delivery workers** (§17.4); **out-of-process plugins**
run as sidecars/services registered per Project/squad, with **GRAIL (ISI-2142) the first such consumer**
(§7.6); `ksquad-memory` keeps **pgvector as source-of-truth** behind a `MemoryBackend` seam (§7.1/§7.6).
Postgres remains the **only stateful dependency** — the **append-only `outbox` is one more table in the
same database** (not a new datastore, and pointedly **not an external broker**), alongside the `coord` /
`memory` / `discussion` / `scm` schemas (ADR-001 intact).

### 17.4 Plugin Architecture & Event Seam (ISI-2156, CEO 2026-08-11) — transactional outbox, out-of-process plugins, **observers not coordination**

> **Decision (Henrik, CEO 2026-08-11, ISI-2156):** the platform emits domain events through a
> **transactional Postgres outbox**; **out-of-process plugins** consume them **read-only**. A failing
> plugin can **never** block the reconcile/coordination path. Plugins are **observers, not a
> coordination path** — they cannot claim, hand off, or mutate state. Pairs with the discussion-room
> guardrail (§7.5, F6 family). **Internal outbox, not an external broker**, per the
> single-stateful-dependency principle (§4/§16).

**Event seam — transactional outbox (at-least-once).** Domain events are written **append-only to a
Postgres `outbox` table in the SAME transaction as the state change** that produced them. Because the
outbox row and the state row commit atomically, an event is captured **iff** its state change committed
— no lost events, no phantom events. Covered:
- **Run lifecycle** (§8): Pending/Claiming/Running/Succeeded/Failed/Cancelled/Paused.
- **Work-item transitions** (§6 coord, §6.6): created / claimed / handoff / completed — written in the
  claim/comment transaction.
- **Memory writes** (§7.3): provenanced memory + discussion writes.
- **Sync / CI results** (§5.4 scm): issue / PR / check-run / artifact mirror updates.

This keeps ADR-001 intact: the outbox is **a table in the same Postgres**, not a new datastore and
**not** an external broker (Kafka/NATS) — the CEO-named trade, resolved for the internal outbox on the
single-stateful-dependency principle (§4).

**Delivery — async workers, decoupled from the write path.** Separate **delivery workers** tail the
outbox (`LISTEN/NOTIFY` + polling) and push to registered plugins with **at-least-once** delivery, retry
with backoff, a **dead-letter** queue for poison messages, and a **per-plugin circuit breaker**.
Delivery runs **outside** the reconcile/coordination transaction, so **a slow, failing, or absent plugin
can never block a Run, a claim, or a memory write** (the CEO isolation requirement). Outbox depth,
delivery lag, dead-letter counts, and per-plugin circuit state are OTel metrics (§17.2).

**Versioned event catalog (drift discipline, §10.2).** Each event type has a **versioned schema** in a
catalog governed by the same pinned-adapter discipline as A2A/MCP (`pkg/events@rev`): consumers pin an
event-schema rev; producer changes are additive-or-gated, never ambient breakage. This is how a
third-party plugin survives platform evolution.

**Plugin model — out-of-process, per Project/squad.** Plugins are **out-of-process** (sidecar or
standalone service), registered/configured **per Project/squad**. Outbound credentials use **BYO
per-user Secret refs (§11)** — a plugin calling an external system carries a per-Project/per-user Secret,
never a shared master credential (credential lock upheld). Plugins run least-privilege and are
**untrusted** (D8/§17.1).

**Guard — plugins are observers, NOT a coordination path (CEO; §7.3/§7.5 discipline, applied again).**
The plugin contract is **read-only event consumption**. There is no plugin affordance to claim, lease,
fence, hand off, or otherwise mutate coordination/knowledge state:
1. The outbox is **emit-only downstream**: events flow out; nothing a plugin returns re-enters the
   coord/memory transaction. A plugin **cannot move a work item** by consuming (or attempting to emit) an
   event.
2. Custody transfer stays structurally confined to the fenced `coord` record (§6); the event seam has
   **no claim/lease/fence surface** — the same reason memory (§7.3) and the discussion room (§7.5) are
   not P2P channels, now applied to plugins a **third** time.
3. A plugin that must *act on the world* (e.g. mirror to an external tracker) does so as an ordinary
   **authored, audited API client** subject to D8 — outside the event seam, and still with **no
   coordination primitive**. Read-in via events; write-out (if any) via the same public APIs as any
   principal.

*Satisfies:* new (plugin architecture, ISI-2156); D8 (untrusted + authenticated), NFR-SEC*, NFR-OBS1/2
(outbox metrics), single-stateful-dependency (§4). *Trade recorded:* ADR-023 (transactional outbox vs
external broker; out-of-process isolated plugins; read-only consumer contract). *Touchpoints:* §6.6
(coord events), §7.3/§7.5 (no-P2P discipline), §7.6 (GRAIL first consumer), §10.2 (event-catalog drift),
§17.2 (observed), §17.3 (layout), §19/§22.

---

## 18. ADR Log (decisions & trades)

| ADR | Decision | Chosen | Seriously considered & rejected |
|-----|----------|--------|---------------------------------|
| 001 | Durable-state store | **One Postgres, two schemas** (coord + memory) | etcd/CRDs for work items (wrong store); two separate DBs (S1 cost) |
| 002 | Desired-state API | **CRDs via controller-runtime** | Custom API objects; config in Postgres |
| 003 | Claim/lease mechanism | **Postgres row-lock + fencing token** | Bespoke lease service; etcd leases; Redis lock (added dep, weaker fencing) |
| 004 | Memory build-vs-integrate | **Integrate pgvector; own the trust model** | In-house vector store; external vector DB (BYO — excluded by lock) |
| 005 | Run control | **Reconcile state machine** | K8s Job; heartbeat-adapter (Paperclip model — R4) |
| 006 | Sandbox hygiene | **Teardown-and-replace** | In-place reset (unprovable clean); reuse (state bleed — F6) |
| 007 | Concurrent workspace | **git worktree per Run + workspace lease** | Global Project lock (serializes); artifact-sync (complexity) |
| 008 | Shim placement | **Sidecar in sandbox pod** | Standalone Deployment (loses workspace-local); init-container |
| 009 | Spec drift | **Pinned adapter seam + conformance-gated upgrades** | Track upstream head (ambient breakage — F9) |
| 010 | Credentials | **Per-user Secret ref; two concrete stories; type as capability** | Shared service account (excluded by lock); Claude-only shape (F15) |
| 011 | Tenancy | **namespace-per-Team** | namespace-per-Project; namespace-per-Run; label-selector tenancy |
| 012 | Egress | **default-deny NetworkPolicy + optional proxy** | Open egress; bespoke egress gateway |
| 013 | Console | **Next.js + BFF** | SPA direct-to-kube (auth sprawl); server-rendered-only |
| 014 | DB packaging | **Bundle Postgres via CNPG** | Require external managed DB (breaks S1 one-afternoon install) |
| 015 | Coding-agent flavor | **`AgentRuntime` CRD; image = R-per-flavor (not R×T)** | Baking toolchains into each runtime image (combinatorial matrix); implicit runtime in `Role` |
| 016 | Tooling model | **Lifecycle-split: init-staged toolchain packs + `Skill.requires`; sidecars for stateful services only** | Fat base image (2–3GB, still a matrix); toolchains-as-sidecars (idle CPU/mem, PATH hacks) |
| 017 | Runtime image freshness | **Hybrid: pinned `cliVersion` + `ImageUpdater` + conformance canary + warm-pool refresh** | Auto-rebuild pipeline (CI-heavy); init-time CLI pull as default (cold-start + non-reproducible) |
| 018 | Source-control sync (Theme H, FR-H*; ISI-2145) | **repo-sync reconciler + `pkg/scm` provider seam; GitHub is a mirror, coord stays authoritative; conflict = field-ownership split (external-owned vs KSquad-owned, single writer each); loop-prevention = origin-marked outbound + drop-own-echo inbound (OQ13)** | Bidirectional sync as source of truth (leaks custody into an external, unfenced store); GitHub-only hardcode (no seam); webhook-only ingress (lossy/at-least-once); last-writer-wins across both directions (custody race, no clear owner) |
| 019 | Discussion room (ISI-2147) | **Postgres `discussion` schema, provenanced, memory-projected, coordination-free by construction** | Reuse `coord` tables (conflates talk with custody, breaks no-P2P lock); memory schema only (muddies the trust model); NATS/message bus (added dep, ephemeral, is P2P) |
| 020 | Consumption attribution & metering provenance (Theme I, FR-I2/I3, NFR-OBS3; ISI-2146) | **Axes anchored to Run lifecycle (operator) + kubelet/cAdvisor — non-forgeable; runtime-reported token counts are best-effort, sanity-bounded, not the billing axis (OQ14); OTel metrics labeled per-principal; estimate via price table; no billing DB** | Trust agent self-reported tokens as authoritative (forgeable — NFR-OBS3 forbids); dedicated usage/billing datastore (new stateful dep, breaks S1); read provider billing API (BYO — no shared billing visibility) |
| 021 | Build browser (ISI-2148) | **Read-only git-worktree projection (live via shim; completed via artifact snapshot + on-demand RO reader)** | Long-lived per-Run file service (pods are torn down §9.3); bespoke diff engine (git already diffs); browser writes to workspace (violates read-only/scope guard) |
| 022 | Exposure model (Theme L, FR-L*; ISI-2149) | **Chart creates `Gateway`+`HTTPRoute`; `gatewayClassName` required values input; `values.exposure.mode` = gateway\|ingress\|clusterip with pre-flight so a Gateway-less cluster still installs in ≤4h (OQ16); explicit `storageClassName` for every PVC** | Legacy `Ingress`-only (SSE buffering, weaker timeout control); Gateway-mode as a hard dependency (breaks S1 on Gateway-less clusters); hardcode or cluster-default gatewayClass/storageClass (non-portable, silent misconfig) |
| 023 | Plugin architecture & event seam (ISI-2156, CEO 2026-08-11) | **Transactional Postgres `outbox` (events append-only in the state-change txn → at-least-once); async delivery workers with dead-letter + per-plugin circuit breaker so a failing plugin never blocks reconcile/coordination; out-of-process plugins per Project/squad, BYO-Secret outbound creds; versioned event catalog (§10.2 discipline); read-only consumption — plugins cannot claim/handoff/mutate (observers, not a coordination path)** | External broker (Kafka/NATS — breaks single-stateful-dependency §4/§16); in-process plugins (couple plugin failure to the reconcile path); synchronous delivery inside the write txn (a slow/failing plugin blocks claims/writes); any plugin write-back/coordination affordance (breaks no-P2P lock) |
| 024 | Memory fan-out to GRAIL (ISI-2142 via ISI-2156) | **`pgvector` stays source-of-truth; GRAIL is the event seam's first consumer — memory writes stream via OTLP/SmartScape/DQL from the outbox (read-only fan-out), own Phase 4 story; trust enforced above storage/before fan-out** | Swap pgvector for a GRAIL backend (loses source-of-truth + §7.3 trust control, breaks air-gapped S1); synchronous dual-write to GRAIL from the memory service (non-atomic, couples writes to GRAIL availability); make GRAIL a v1 dependency |
| 025 | Reclaim & dispatch safety (F1/F4, ISI-2132→ISI-2135) | **Fence-the-pod-before-claim-release reclaim protocol (§6.3) + deterministic `a2a_task_id = run_id` with shim-side dedup + artifact upsert keys + conditional status UPDATEs (§6.4)** | Release-on-lease-expiry alone (zombie writer keeps mutating PVC/memory/git — Kleppmann fencing violation); reconciler in-memory dispatch dedup (lost on crash); fresh execution id per attempt (double-dispatch on re-entry) |
| 026 | Model endpoint & BYO Ollama (CEO Gate 2, Henrik 2026-08-11) | **Model endpoint is a per-Agent Secret ref (`Agent.spec.modelEndpointRef`) orthogonal to `AgentRuntime.type` — Ollama rides the OpenAI-compatible wire on existing runtimes (zero new image); local-model gaps declared via §10.1 capability negotiation; in-cluster Ollama doubles as the zero-credit CI conformance + e2e lane (ISI-2157/ISI-2114)** | Bake the provider into each runtime image (re-creates the R×T matrix ADR-015 killed, one image per flavor×provider); a dedicated `OllamaRuntime` CRD (endpoint is config, not a flavor); KSquad-held shared endpoint (breaks the per-user Secret-ref lock, ADR-010); assume model parity instead of negotiating (weak local model fails silently mid-Run); paid-API-only CI (conformance gate unrunnable per-PR without spend) |

---

## 19. Traceability (PRD → Architecture)

| PRD | Architecture |
|-----|--------------|
| FR-A1…A6 | §5 CRDs + operator; §8 Run state machine |
| FR-B1…B4 (LOCKED) | §6 coordination record (Postgres, fenced) |
| FR-E1…E7 (LOCKED) | §7 memory service; §7.3 trust boundary |
| FR-C1…C6 | §9 warm pool, runtime, hygiene, workspace |
| FR-D1…D5 | §10 shim seam + A2A + conformance; §5.3 `AgentRuntime` CRD + tooling model (ISI-2144) |
| FR-F1…F6 | §13 console |
| FR-F7 (dark/light, r3) | §13 dark+light theme (v1, WCAG AA both modes) |
| FR-H1…H5 (SCM sync, r3) | §5.4 repo-sync + `pkg/scm` seam; OQ13 conflict/loop model |
| FR-I1…I3 (dashboard/metering, r3) | §13 dashboards; §11 attribution; §17.2 OTel metering (non-forgeable) |
| FR-J1…J4 (discussion room, r3) | §7.5 Postgres `discussion`, coordination-free; §13 surface |
| FR-K1…K2 (build browser, r3) | §9.4 git-worktree read model, per-principal scoped; §13 surface |
| FR-L1…L3 (install/exposure, r3) | §16.1 Gateway API + Gateway-less fallback; §16.2 explicit StorageClass |
| FR-G1…G3 (LOCKED) | §11 credentials, two stories, pause/resume |
| NFR-SEC1…6 | §12 tenancy/egress; §9.3/9.4 hygiene; §7.3 memory; §17.1 threat model |
| NFR-SEC7 (room scope, r3) | §7.5 `Project`-scoped, attributed, no-coordination-path (FR-J4) |
| NFR-SEC8 (sync auth, r3) | §5.4 HMAC verify + BYO Secret-ref creds, never logged/exposed to Run |
| NFR-OBS3 (metering provenance, r3) | §11/§17.2 anchored to Run lifecycle + kubelet, not agent self-report |
| D8 (external integrations untrusted+authenticated, r3) | §5.4 untrusted-input + signature verify; §17.1 threat model |
| NFR-REL1…3 | §6.3 fencing; §8 resume; §7.4 durability |
| NFR-PERF1/2 | §9.2 warm pool; §13 SSE |
| NFR-SCALE1/2 | §12.1 namespace-per-Team; §9.2 policy pool |
| NFR-USE1/2 | §16 install; §13 console |
| NFR-EXT1/2, OBS1/2 | §10 shims; §6.5 + §17.2 |
| D1…D7 | §9.1, §12, §7.3, §9.3/9.4, §17.1 |
| OQ2/4/5/7/9/10/11/12 | §9.1 / §12.2 / §9.4 / §12.1 / §6 / §7.1 / §11 / §10.2 |
| OQ13/14/15/16/17 (r3, Architecture-owned) | §5.4 conflict+loop / §11+§17.2 metering source / §7.5 room storage+distinctness / §16.1 Gateway-less fallback / §9.4 build-browser source+scoping — **all resolved** |
| §8 three deltas, F5 | §14 teardown (deltas realized in §10/§8/§6) |
| Challenger F6/F7/F8/F9/F16/F18/F20 | §9.3-4 / §7.3 / §6+§15 / §10.2 / §7.3 / §17.1 / (safety-wins, §12 tiebreaker applied) |
| ISI-2145 Source-control sync | §5.4 repo-sync + `pkg/scm` provider seam; §17.3 layout; ADR-018 |
| ISI-2146 Dashboards + consumption | §13 dashboards; §11 attribution; §17.2 metrics; ADR-020 |
| ISI-2147 Discussion room | §7.5 (Postgres `discussion`, memory-projected, coordination-free); §13 surface; ADR-019 |
| ISI-2148 Build browser | §9.4 read model; §13 surface; ADR-021 |
| ISI-2149 Helm exposure | §16.1 Gateway API + §16.2 explicit StorageClass; ADR-022 |
| ISI-2150 Console theming | §13 dark+light theme (v1, WCAG AA both modes) |
| ISI-2156 Plugin architecture + event seam (r6) | §17.4 transactional Postgres outbox + async delivery (dead-letter/circuit-breaker) + out-of-process plugins, read-only (not coordination); §6.6 coord events; §17.3 `pkg/events`; ADR-023 |
| ISI-2142 GRAIL memory fan-out (r6) | §7.6 GRAIL = event-seam first consumer (OTLP/SmartScape/DQL), pgvector source-of-truth; §7.1/§17.4; ADR-024 |
| BYO Ollama model endpoint (CEO Gate 2, Henrik; r8) | §10.3 `Agent.spec.modelEndpointRef` seam (orthogonal to `AgentRuntime.type`), OpenAI-compat runtimes, capability-negotiated; §5.1 CRD; §12 egress; ADR-026 |
| ISI-2157 free CI / ISI-2114 Ollama conformance lane (r8) | §10.3 in-cluster Ollama service container / self-hosted GPU runner = zero-credit conformance + smoke/e2e lane; added row in the ISI-2114 runtime/conformance matrix |

---

## 20. Handoff & Next Steps

- **Gate:** CEO (BigBoss) approval — CEO Gate 2 — routed by Alfred (CTO). **No Phase 4 (Epics) starts**
  until this architecture passes the gate.
- **Downstream delegations (subtasks created under ISI-2119):**
  - **Story Writer** — enrich stories with architecture context (CRD surface, Run state machine,
    coordination-spine epic sequencing, shim contract, memory trust model). **r3 adds:** SCM sync
    (§5.4), discussion room (§7.5), dashboards/consumption (§13/§11), build browser (§9.4/§13), Gateway
    API + StorageClass exposure (§16.1/§16.2), dark+light theme (§13) — new stories / Epic touchpoints.
  - **Code Reviewer** — review architecture for implementation feasibility (fencing correctness, ADR
    trades, spike-gated seams). **r3 adds:** verify the discussion room stays coordination-free (§7.5
    argument), the SCM mirror never becomes a custody store (§5.4), and the build browser stays strictly
    read-only (§9.4).
  - **Observability Agent** — plan observability (coord audit trail, claim/lease + memory metrics,
    per-Run trace correlation), seeded by the org's Sympozium OTel prior art. **r3 adds:** the
    consumption/usage metric taxonomy (§17.2/§13, ISI-2146) and the metrics-backend query seam.
    **r6 adds:** the event seam's outbox (§17.4) is itself instrumented (outbox depth, delivery lag,
    dead-letter, per-plugin circuit state) — fold these into the span/metric taxonomy.
  - **r6 (plugin architecture + GRAIL) — new Phase 4 stories (ISI-2156, ISI-2142):** the **event seam**
    (transactional Postgres `outbox` + versioned catalog + async delivery workers with dead-letter and
    per-plugin circuit breaker, §17.4), the **out-of-process plugin runtime** (registration/config per
    Project/squad, BYO-Secret outbound creds), and the **GRAIL consumer** (§7.6, streams memory writes
    via OTLP/SmartScape/DQL) are each their own Phase 4 story; v1 keeps `pgvector` source-of-truth.
    **Code Reviewer:** verify the outbox commits in the state-change transaction, that delivery failure
    is fully decoupled from reconcile/coordination, and that the plugin contract stays **read-only**
    (no claim/handoff/mutate — §17.4/§6.6 guard).
- **Feeds forward:** Phase 4 (Epics) inherits §5–§13 as the build map, §15 (spine sequenced first),
  §18 ADRs (incl. r3 ADR-018…022, r5/r6 ADR-023/024), and §21 spike gates as explicit dependencies.

---

## 21. Spike-Gated Parameters (evidence not yet produced — do not ship v1 defaults blind)

Every gated item is a **parameter behind a seam**, not a structural risk. But the spikes are
**`backlog`/unassigned** — they must run before v1 commits these defaults:

| Gate | Sets | Spike | Status |
|------|------|-------|--------|
| Sandbox RuntimeClass default + LLM-bound overhead | §9.1 default (gVisor provisional) | **ISI-2113** | ⚠ backlog — not started |
| Warm-pool sizing/autoscale numbers + warm/cold routing | §9.2 policy defaults | **ISI-2113** | ⚠ backlog — not started |
| OAuth token longevity, refresh cadence, concurrency-on-one-subscription | §11 Claude-family lifecycle | **ISI-2112** | ⚠ backlog — not started |
| Reference shim + conformance assertions | §10.1 S5/S6 claimable | **ISI-2114** | ⚠ backlog — not started |
| Pinned A2A/MCP revision | §10.2 adapter seam version | ISI-2114 scope | ⚠ backlog — not started |
| Docker-in-sandbox mechanism (rootless dockerd vs Kata real-docker) | §5.3.3 `docker` capability backing | ISI-2113 (RuntimeClass) | ⚠ backlog — not started |
| CLI redistribution licensing (bake-in vs init-time vendor pull) | §5.3.5 open-Q 2 — Claude Code ToS live risk | **owner: Alfred/CEO** (legal, not a spike) | ⚠ open — escalated |

**Architect recommendation to Alfred/CEO:** schedule and staff ISI-2112/2113/2114 **in parallel with
Phase 4 Epics**. They gate v1 *defaults and the S5/S6 conformance claims*, not the architecture — so
Epics can proceed, but the spikes must land before the corresponding v1 acceptance tests (S6, S9,
S10) can be signed off. If ISI-2112 returns disqualifying evidence on subscription-token lifecycle,
that is the PRD §13 watch-item CEO-gate conversation (R1), owned by Alfred — flagged here so it is not
a surprise.

---

## 22. Validation Checklist (self-review before CEO Gate 2)

- [x] All 7 LOCKED decisions honored, none reopened.
- [x] Every FR (§9) and NFR (§10) mapped to a mechanism (§19).
- [x] Architecture-owned OQs resolved: OQ2 (§9.1), OQ4 (§12.2), OQ5 (§9.4), OQ7 (§12.1), OQ9 (§6),
      OQ10 (§7.1), OQ11 (§11), OQ12 (§10.2); **r3 (ISI-2154): OQ13 sync conflict/loop (§5.4), OQ14
      metering provenance (§11/§17.2), OQ15 room storage/distinctness (§7.5), OQ16 Gateway-less fallback
      (§16.1), OQ17 build-browser source/scoping (§9.4)**.
- [x] Memory MCP tool surface confirmed (§7.1); Node frontend approach named (§13).
- [x] Challenger findings designed in: F5 (§14 positioning), F6 (§9.3/9.4), F7/F16 (§7.3), F8 (§6/§15),
      F9 (§10.2), F18 (§17.1), F20 (§12 safety-wins tiebreaker applied).
- [x] Sympozium teardown from first-hand intel; three deltas realized in-architecture (§14).
- [x] S1 install story preserved by the single-stateful-dependency decision (§4/§16).
- [x] Helm networking & storage wired explicitly (CEO directive 2026-08-11, §16.1/§16.2): chart creates
      `Gateway`/`HTTPRoute` for console + apiserver (SSE) with **required** `gatewayClassName` and
      TLS/listeners via values; all PVCs (CNPG + workspace) take `storageClassName` from values —
      no cluster-default reliance; RWO default / RWX optional documented per storage-class
      capability. ADR-022. Stories: Epic 9 (`epics.md`).
- [x] Spikes' non-existence surfaced honestly; decisions placed behind seams; gates named (§21).
- [x] ADR log records the trades (§18) for downstream inheritance.
- [x] ISI-2144 amendment folded in: `AgentRuntime` CRD + lifecycle-split tooling (§5.3), R-not-R×T
      image model, ImageUpdater lifecycle; warm-pool/§8/§10 reconciled; ADR-015/016/017; CLI-license
      + registry + air-gap open questions escalated to Alfred/CEO (not silently assumed).
- [x] r3 CEO-review requirements folded in (ISI-2145…2150) — each behind an existing seam, no locked
      decision reopened:
      - [x] ISI-2145 source-control sync: repo-sync reconciler + `pkg/scm` provider seam, GitHub mirror
            (coord authoritative), HMAC webhook ingress + reconcile backstop, `scm` schema (§5.4);
            ADR-018.
      - [x] ISI-2146 dashboards + consumption: coord/scm health + OTel-borne consumption, per-principal
            by BYO-cred construction, estimate-not-billing, no new datastore (§11/§13/§17.2); ADR-020.
      - [x] ISI-2147 discussion room: Postgres `discussion` schema, threaded, provenanced,
            memory-queryable, and **coordination-free by construction** — §7.3 no-P2P argument
            re-applied (§7.5); ADR-019.
      - [x] ISI-2148 build browser: read-only per-Run git-worktree projection (live via shim, completed
            via artifact snapshot + RO reader), legibility not IDE (§9.4/§13); ADR-021.
      - [x] ISI-2149 exposure: Gateway API + explicit StorageClass formalized into §16.1/§16.2; ADR-022.
      - [x] ISI-2150 console theming: dark+light as a v1 requirement, token-driven, WCAG AA both modes
            (§13).
      - [x] "One Postgres" (ADR-001) preserved: `scm` + `discussion` are schemas, not new datastores;
            S1 single-stateful-dependency intact.
- [x] r3 lockstep with PRD (ISI-2154): PRD's formal numbering adopted across §5.4/§7.5/§9.4/§11/§13/§16
      (Themes H/I/J/K/L, FR-F7); the five Architecture-owned mechanism OQs (OQ13–OQ17) **resolved**, with
      two genuine gaps closed — OQ13 sync loop-prevention/conflict model (§5.4) and OQ16 Gateway-less
      install fallback (§16.1). New security bar reflected: D8 external-untrusted+authenticated (§5.4/§17.1),
      NFR-SEC7 room scope (§7.5), NFR-SEC8 sync auth (§5.4), NFR-OBS3 non-forgeable metering (§11/§17.2).
      No locked decision reopened.
- [x] r5→r6 plugin architecture folded in (CEO comments fad6cf02 + 7892ec22 / ISI-2156) — behind an
      existing seam, no locked decision reopened:
      - [x] Event seam (§17.4, §6.6): **transactional Postgres `outbox`** — events append-only in the
            state-change transaction (at-least-once); async delivery workers with **dead-letter +
            per-plugin circuit breaker** so a **failing plugin never blocks reconcile/coordination**;
            **versioned event catalog** under §10.2 drift discipline. **Internal outbox, not an external
            broker** (§4 single-stateful-dependency — the CEO-named trade). ADR-023.
      - [x] Plugin model (§17.4): **out-of-process** (sidecar/service) per Project/squad; outbound creds
            via **BYO per-user Secret refs** (§11); least-privilege, untrusted (D8).
      - [x] Guard (CEO): **plugins are observers, NOT a coordination path** — **read-only** consumption,
            no claim/lease/fence surface, cannot hand off or mutate state; §7.3/§7.5 no-P2P argument
            applied a **third** time (pairs with the discussion-room guardrail, F6 family).
      - [x] GRAIL (§7.6, ISI-2142): the seam's **first consumer** — memory writes stream via
            OTLP/SmartScape/DQL; **`pgvector` stays source-of-truth**; read-only fan-out, own Phase 4
            story; trust model enforced above storage/before fan-out. ADR-024.
      - [x] "One Postgres" (ADR-001) + S1 self-contained install preserved: the `outbox` is one more
            **table** in the same Postgres (not a datastore, not a broker); pgvector source-of-truth keeps
            the single stateful dependency.
