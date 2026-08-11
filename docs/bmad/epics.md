# Epics & Stories — KSquad (architecture-enriched)

> **Status:** Phase-4 **prep**. This is the epic/story backbone with Phase-3 architecture context
> threaded into every story. **CEO Gate 2 (BigBoss, routed by Alfred) must pass before Phase 4
> formally starts** — no implementation begins until then (03-architecture §15).
>
> **CEO directive 2026-08-11 (Henrik):** the Helm chart must not assume cluster defaults — it
> **creates** the `Gateway` + `HTTPRoute` resources (console + apiserver SSE; `gatewayClassName` a
> required values input, TLS/listeners via values) and **parameterizes `storageClassName`** on all
> PVCs (CNPG + Project workspaces; RWO default, RWX optional per §9.4). Threaded into **Epic 9**
> below and part of the **Gate 2 review scope** (03-architecture §16, §22).
>
> **CEO product inputs 2026-08-11 (Henrik, 4× board comments):** (a) **build-output visibility** —
> per-Run build browser (file tree, diffs, code view) extending FR-F3 → **Epic 8.7**;
> (b) **per-Project discussion room** — persistent, agents+humans, Postgres (ADR-001),
> provenance-tagged, memory-queryable, **not** a coordination channel → **Epic 10**;
> (c) **dashboard layer** — project health / work-item throughput / consumption (tokens + cost per
> agent/Run/Project, sandbox resources) riding the OTel pipeline (§17.2) → **Epic 8.8**;
> (d) **source-control sync (GitHub first)** — issues ⇄ work items, PR + CI status, artifacts →
> **Epic 11**; (e) console **dark AND light mode** (theme toggle is v1) + **v2 logo** once
> ISI-2137 assets land → **Epic 8.9**; (f) **plugin architecture** — the platform emits domain
> events that plugins register to (observers, **not** a coordination path); the Dynatrace GRAIL
> memory backend (ISI-2142) is reframed as a **memory SDK/plugin**, first consumer of the seam →
> **Epic 12**; (g) **Ollama model backend + free CI lane** — Agents point at a **BYO Ollama
> endpoint** (endpoint via Secret ref, model name per Agent) as a **third model-backend / credential
> shape** beside Claude-OAuth and second-runtime API-key. **Architecturally this is the §10.3
> model-endpoint seam — `Agent.spec.modelEndpointRef` → per-user Secret + per-Agent `Agent.spec.model`,
> negotiated by a `byoModelEndpoint` capability (§10.1) — orthogonal to `AgentRuntime.type`, NOT a new
> runtime flavor (ADR-026):** a runtime rides the OpenAI-compatible wire to the endpoint — **zero new
> image, zero core change**. **CEO 2026-08-11 follow-up: Ollama is covered through the `opencode` runtime**
> (SST/opencode — natively Ollama-compatible; `ollama launch opencode`), **pulled from Phase 2 into the
> v1 shim set** (story 5.8) as the reference Ollama runtime. The same lane doubles as the **$0
> release-testing path** (in-cluster Ollama / self-hosted GPU runner) for smoke + e2e squad scenarios in
> CI (**ISI-2157**) — no paid API credits. Threaded into **Epic 5** (5.7 model-endpoint + 5.8 opencode
> shim + 5.6 conformance Ollama lane, ISI-2114), **Epic 7** (endpoint-ref credential shape, 7.5), and the
> **Epic X / CI free lane**. Items (a)–(d), (f) and (g)
> are **new scope vs the PRD** — Gate 2 must ratify them as a PRD addendum (see FR coverage check).
>
> **Sources:** PRD `02-prd.md` (FR/NFR contract, §9/§10), Architecture `03-architecture.md`
> (decisions AD-1..AD-10, §4–§11), UX `docs/bmad/ux` (console screens). Traceability: PRD → Arch in
> `03-architecture.md` Appendix B.
>
> **How to read a story:** each carries `Arch:` (architecture section), `FR:` (PRD requirement),
> `Deps:` (cross-story / spike-gate dependencies). Acceptance criteria use Given/When/Then/And.
> Stories are written for the Developer agent and are read **in order**; the Developer opens a
> dedicated per-story file (via `bmad-create-story`) that expands the story selected here.

---

## Epic ordering & rationale

Epic order follows the architecture implementation sequence (03-architecture §4.7), with the
**coordination spine sequenced first among the hard work** (§6, R10) because it is the single most
correctness-critical piece of v1 and everything downstream records state through it.

| # | Epic | Primary decision(s) | FR coverage | Spike gate | Sequence note |
|---|------|--------------------|-------------|-----------|---------------|
| 1 | CRD Foundation & API scaffolding | AD-2 | FR-A1–A3 (types) | — | First — everything depends on the types |
| 2 | **Coordination Spine** (checkout/claim/lease) | AD-1 | FR-B1–B4 | — | **First hard track (R10); dedicated concurrency/chaos suite** |
| 3 | Run reconcile & warm-pool claim | AD-2, AD-3 | FR-A4–A6, FR-C1/C4 | **ISI-2113** (pool sizing) | Needs spine (Epic 2) to record Run state |
| 4 | Sandbox runtime, isolation & workspace | AD-3, AD-5, AD-7, AD-8 | FR-C2/C3/C5/C6 | **ISI-2113** (RuntimeClass) | Needs tenancy (namespaces) + claim path |
| 5 | Agent shims, A2A & conformance | AD-4 | FR-D1–D5 | **ISI-2114** (conformance/shim spec) | Needs reconcile to dispatch tasks |
| 6 | Memory service (knowledge record) | AD-6 | FR-E1–E7 | — | Parallelizable; needs tenancy for scoping |
| 7 | Credential plumbing & pause/resume | AD-9 | FR-G1–G3 | **ISI-2112** (OAuth refresh UX) | Needs shim cred-injection + reconcile Paused |
| 8 | Operator console | AD-10 | FR-F1–F6 + build browser (8.7) + dashboard (8.8) + theming (8.9) | — | Consumes apiserver + SSE; last |
| 9 | **Install, exposure & storage** (Helm hardening) | §16, CEO directive 2026-08-11 | S1, NFR-USE1 | — | After the services it exposes exist (Epics 2/3/8); before design-partner install |
| 10 | **Discussion rooms** (per-Project) | ADR-001 (Postgres), CEO input 2026-08-11 | New scope (Gate 2 PRD addendum) | — | Needs Epic 2 patterns + Epic 6 memory + console (8) |
| 11 | **Source-control sync** (GitHub first) | CEO input 2026-08-11, §5.1 `Project.repo` | New scope (Gate 2 PRD addendum) | — | Needs Project CRD (1), work items (2), console (8), rooms (10), ingress (9) |
| 12 | **Plugin architecture** (event seam + SDK) | CEO input 2026-08-11, ADR-001 | New scope (Gate 2 PRD addendum) | — | Needs events from Epics 2/6/11; plugins are observers, never coordination |
| X | **Isolation test suite** (cross-cutting) | §4.3 | NFR-SEC1/5/6 | ISI-2113 (runtime pick) | First-class CI artifact, not a checkbox |

**Spike-gate posture (03-architecture §14, §21 in the issue framing):** ISI-2112 / ISI-2113 / ISI-2114
are **still `backlog`** and run **in parallel with the foundational track** (Epics 1–2, which depend
on none of them). Stories that consume their *defaults* carry them as **explicit blocking or tuning
dependencies** below — a story may start against the provisional default but cannot **close** until the
gate result confirms/refutes it where marked `[GATE-BLOCKING]`.

---

## Epic 1 — CRD Foundation & API scaffolding (AD-2)

**Objective:** Establish `ksquad.io/v1alpha1` CRD types and the kubebuilder project so every downstream
controller and service compiles against one API contract. **This is the base of the whole build.**

**Arch:** §5.1 (CRD surface), §11 (project structure), §11.2 (`api/v1alpha1`). **FR:** FR-A1, FR-A2,
FR-A3 (declarative types portion). **Deps:** none — starts immediately, parallel with spikes.

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 1.1 | As a platform engineer, I want the `ksquad.io/v1alpha1` API group scaffolded so all CRDs share one versioned contract. | **Given** a fresh kubebuilder project, **When** `make generate manifests` runs, **Then** the `ksquad.io` group at `v1alpha1` builds with `zz_generated.deepcopy.go` and CRD manifests under `config/crd`. **And** the group is namespaced by default. | Arch §5.1, §11.2. Pins K8s lib versions in `go.mod` (OQ12). |
| 1.2 | As a squad author, I want `Team`, `Agent`, `Role`, `Skill`, `Project`, `Run` CRD types with the spec fields from the architecture. | **Given** the API group, **When** the six types are defined, **Then** each carries the §5.1 spec fields (e.g. `Agent.runtime/roleRef/skillRefs/credentialSecretRef/agentCardOverrides`; `Run.spec.teamRef/workItemRef/inputs/sandboxPolicy` + `Run.status.phase/sandboxRef/claimedAt/conditions/artifactRefs`). **And** `Run.spec.workItemRef` is a **DB row reference, not an owned etcd object** (ADR-001). | Arch §5.1, note under §5.1. Encode `workItemRef` as an opaque ID string, documented as a coordination-DB pointer. |
| 1.3 | As a developer, I want CRD validation + defaulting webhooks (or CEL validation) for the required relationships. | **Given** the types, **When** an invalid CR is applied (e.g. `Agent.runtime` outside the enum, `Team` referencing a missing `Project`), **Then** admission rejects it with a clear message. **And** enum fields (`runtime`, credential type) validate against the known set. | Arch §5.1, §7.2 (credentialType enum). Keep runtime enum open-ended enough for shim vendors (FR-D3). |
| 1.4 | As a platform engineer, I want the Helm chart skeleton + CRD install so `helm install` lands the CRDs. | **Given** `config/helm`, **When** the chart installs on a conformant cluster, **Then** all six CRDs register and the control-plane namespace is created. **And** this is the first step toward the ≤4h install (S1, NFR-USE1). | Arch §4.6, §11.2 (`config/helm`). Full service wiring lands in later epics; this is CRD + namespace scaffolding. |

---

## Epic 2 — Coordination Spine (AD-1) — **the correctness-critical foundational track (R10)**

**Objective:** Build the Postgres-backed coordination record — work items, comments, artifacts, and the
checkout/claim/**lease** mechanism — with **provably correct single-claim under contention** and
crash-safe reclaim. **This is a from-scratch distributed-systems build, not a checkbox** (PRD §9.2
build-cost note, R10). It is sequenced first among the hard work and is **tested, not asserted.**

**Arch:** §3 (storage split), §6 (model + consistency), §6.2 (SKIP LOCKED + leases + fencing).
**FR:** FR-B1, FR-B2, FR-B3, FR-B4. **NFR:** NFR-REL1/2, NFR-OBS1 (audit). **Deps:** Epic 1 (Run type
references work items). **No spike-gate dependency** — starts in parallel with ISI-2112/13/14.

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 2.1 | As the system, I want the coordination schema (`work_items`, `comments`, `artifacts`, `checkouts`, `run_events`/`audit_log`) so coordination state is durable and queryable. | **Given** `db/migrations`, **When** migrations apply, **Then** the five tables exist with the §6.1 columns (work_items: id/project_id/title/body/state/created_by/timestamps; comments append-only + provenanced; checkouts: work_item_id/holder/lease_expires_at/lease_epoch). **And** `comments` and `run_events` are append-only (no UPDATE/DELETE path in code). | Arch §6.1. Versioned SQL; forward-only migrations. |
| 2.2 | As an agent (Run), I want to **claim** an open work item so at most one holder ever holds it, even under heavy contention. | **Given** N open items and M concurrent claimers, **When** all claim simultaneously, **Then** each item is held by **exactly one** Run via `SELECT … FOR UPDATE SKIP LOCKED LIMIT 1` → insert `checkouts` row → `state='claimed'` in **one transaction**. **And** no double-claim occurs across the whole run of the concurrency harness. | Arch §6.2 (Claim). **This is the R10 core.** No application-level locks. |
| 2.3 | As the system, I want **lease renewal (heartbeat)** so a live holder keeps its claim. | **Given** a held item, **When** the holder heartbeats, **Then** `lease_expires_at` extends via an UPDATE guarded by `holder = run_id`. **And** a non-holder's renewal is rejected. | Arch §6.2 (Renew). Heartbeat cadence is a controller concern (Epic 3). |
| 2.4 | As the system, I want **crash-safe reclaim** so a dead holder's item returns to the pool. | **Given** a `checkouts` row with `lease_expires_at < now()`, **When** the sweeper (or an opportunistic claimant) runs, **Then** the item returns to `state='open'` and is claimable by another Run. **And** a resurrected stale holder **cannot** complete or clobber the reclaimed item (fenced by `holder` identity + monotonic `lease_epoch`). | Arch §6.2 (Reclaim + Idempotent completion). This **is** the §5.3 crash-recovery path. |
| 2.5 | As an agent, I want to record progress and hand off **only** via work items / comments / artifacts — never direct agent chat. | **Given** the coordination API, **When** an agent hands off work, **Then** the handoff is a comment/state change on a work item; **there is no** agent-to-agent chat channel in the API surface. **And** memory is **not** usable as a handoff channel (enforced in Epic 6, FR-B3 ↔ FR-E). | Arch §6.1, §8.4 (memory ≠ back-channel). FR-B3. |
| 2.6 | As an operator, I want the coordination record queryable as an **audit trail**. | **Given** activity across Runs, **When** I query by work item / actor / time, **Then** every checkout, comment, and artifact is a durable, queryable row (who/what/when/result). | Arch §6.1 (this **is** the audit trail), D4, NFR-OBS1. |
| 2.7 | **[first-class CI artifact]** As the team, I want a **concurrency/chaos test harness** proving the spine's guarantees. | **Given** the spine, **When** the suite runs in CI, **Then** it exercises: (a) **parallel claimers** (no double-claim), (b) **crash-mid-claim** (item reclaimed after lease expiry), (c) **stale-holder completion** (fenced write rejected), (d) **idempotent reconcile** (re-entrant claim/complete is safe). **And** the suite is a **required** CI gate, not optional. | Arch §6.2 (final paragraph), PRD §9.2. **Correctness is tested, not assumed.** This story is non-negotiable for Epic 2 closure. |

---

## Epic 3 — Run reconcile loop & warm-pool claim (AD-2 / AD-3)

**Objective:** Implement the `Run` controller as the reconcile state machine and the `WarmPool`
controller for claim-time sandbox binding. Fail-partway Runs get retry/backoff/resume from the
primitive, not glue.

**Arch:** §5.2 (state machine), §5.3 (failure/retry/resume/kill), §5.4 (warm pool). **FR:** FR-A4,
FR-A5, FR-A6, FR-C1, FR-C4. **NFR:** NFR-REL1/2, NFR-PERF1, NFR-SCALE2. **Deps:** Epic 2 (records Run
state + claims work items), Epic 4 (actual sandbox provisioning — reconcile can stub the sandbox until
Epic 4 lands). **Spike gate:** **ISI-2113** for pool-sizing curve `[GATE-BLOCKING on tuning, not on shipping the policy]`.

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 3.1 | As the system, I want the `Run` reconcile state machine so a Run drives itself to a terminal state. | **Given** a `Run` CR, **When** the controller reconciles, **Then** it advances `Pending → ClaimingSandbox → Dispatching → Running → Collecting → (Succeeded\|Failed\|Canceled)`, writing observed state to `Run.status` and durable rows to Postgres at each phase. **And** each phase is **idempotent** — re-entering after a controller restart reads durable state and continues (no in-memory continuity assumed). | Arch §5.2. The heart of I1. Leader-election so controller death fails over (§5.3). |
| 3.2 | As the system, I want **retry/resume** of a Run whose sandbox or agent dies mid-execution, with backoff, losing no coordination state. | **Given** a Running Run, **When** its sandbox/agent dies (lease expiry or pod disappearance), **Then** the controller releases the work-item checkout for reclaim (Epic 2, §6.2) and requeues the Run with exponential backoff. **And** recovery reads from Postgres — **nothing is lost.** | Arch §5.3. FR-A5, S8. Direct consumer of Epic 2 reclaim. |
| 3.3 | As an operator, I want to **kill** a Run in ≤2 clicks and have its sandbox torn down promptly. | **Given** a Running Run, **When** kill is issued (console → apiserver), **Then** `Run` moves to `Canceling`, the controller tears down the sandbox, and the Run marks `Canceled`. **And** the work-item checkout is released. | Arch §5.3 (Kill), FR-A6/F4, S2. UI half in Epic 8 (FR-F4). |
| 3.4 | As the system, I want a `WarmPool` controller keeping N pre-warmed sandboxes per squad so start latency is claim-time. | **Given** a pool policy, **When** a Run reaches `ClaimingSandbox`, **Then** it **binds a pooled sandbox** (claim-time, not cold-boot) or triggers scale-up if the pool is empty. **And** start latency in the warm path is claim-time (S9, NFR-PERF1). | Arch §5.4. FR-C1. |
| 3.5 | As the system, I want warm-pool **sizing as a policy** (target buffer + autoscale on claim pressure), not a fixed count. | **Given** claim-pressure signal, **When** the pool controller reconciles, **Then** it maintains a target buffer and autoscales, bounding idle cost. **And** the curve is **tuned against ISI-2113** results before v1 sign-off. | Arch §5.4, §14. FR-C4, R2, NFR-SCALE2. **Deps: ISI-2113 `[GATE-BLOCKING on tuning]`** — ship the policy against defaults; final curve pinned when the spike lands. |

---

## Epic 4 — Sandbox runtime, isolation & workspace (AD-3 / AD-5 / AD-7 / AD-8)

**Objective:** Provision isolated sandboxes via `RuntimeClass`, provide per-Project workspaces (PVC)
with per-principal scoping, enforce namespace tenancy + default-deny egress, and teardown-and-replace
between Runs. **Isolation is tested, not asserted** (see Epic X).

**Arch:** §4.3 (isolation/tenancy/credentials/hygiene), §5.4 (teardown-and-replace), §9.1 (namespace
tenancy), §9.2 (egress), §9.3 (workspace + concurrent Runs). **FR:** FR-C2, FR-C3, FR-C5, FR-C6.
**NFR:** NFR-SEC1/4/5, NFR-SCALE1. **Deps:** Epic 1 (types), Epic 3 (claim path). **Spike gate:**
**ISI-2113** for the RuntimeClass pick `[GATE-BLOCKING: hard isolation gate]`.

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 4.1 | As a platform engineer, I want **squad = namespace** tenancy provisioned per `Team`. | **Given** a `Team`, **When** it reconciles, **Then** a dedicated namespace is created with a least-privilege ServiceAccount + Roles, `ResourceQuota` + `LimitRange`, and per-namespace Secrets/PVCs. **And** the control plane runs in a **separate system namespace**. **And** `Team`→namespace is 1:1 (adding squads = adding namespaces, no control-plane redesign). | Arch §9.1, AD-5, D2. NFR-SEC1, NFR-SCALE1. Underlies isolation, egress, credentials, memory scoping. |
| 4.2 | As the system, I want **RuntimeClass-selected sandbox isolation** for every Run. | **Given** a Run claim, **When** the sandbox pod is created, **Then** it uses the selected `RuntimeClass` (**Kata default / gVisor fallback; runc rejected for untrusted code**), and every Run is a distinct sandbox with no shared process/net/fs boundary across squads. | Arch §4.3, §5.4, AD-3. FR-C3, NFR-SEC1. **Deps: ISI-2113 `[GATE-BLOCKING]`** — RuntimeClass pick confirmed by the spike (warm-claim p50 ≤2s/p95 ≤5s; ≤15% overhead; **hostile-Run contained** = hard gate; isolation wins over latency per §1 tiebreaker). RuntimeClass is a **documented cluster prerequisite** (S1). |
| 4.3 | As a squad, I want each `Project` to mount a **persistent workspace** (source + build cache) across Runs. | **Given** a `Project` with a workspace PVC spec, **When** a Run starts, **Then** the PVC mounts source + build cache into the sandbox and persists across Runs. | Arch §9.3. FR-C2. |
| 4.4 | As the system, I want **defined concurrent-Run behavior** on a shared Project workspace. | **Given** concurrent Runs on one Project, **When** they need to write, **Then** a **per-Project write-lease serializes writers** (default); reads are concurrent; the opt-in optimization is a copy-on-write overlay merged back. | Arch §9.3, OQ5. FR-C5. Default = serialize-via-lease (simplest correct). |
| 4.5 | As a security owner, I want **teardown-and-replace + per-principal scoping** so no state bleeds between Runs or principals. | **Given** a completed Run, **When** the pool replenishes, **Then** the sandbox pod is **destroyed and replaced** by default (no reset-in-place unless ISI-2113 shows replace cost prohibitive **and** a residue test passes). **And** PVC access is **scoped per principal**, not merely per Project — a shared workspace cannot expose one user's data to another agent's Run. | Arch §4.3, §5.4, §9.3, AD-3/AD-8, D7. FR-C6, NFR-SEC5. **Security requirement**, not economics. Verified by Epic X residue test. |
| 4.6 | As a security owner, I want **default-deny egress + allowlist** per squad, with an optional egress proxy. | **Given** a squad namespace, **When** NetworkPolicy applies, **Then** egress is **default-deny** with an explicit allowlist to model endpoints + control plane; **And** a `Project.egressPolicyRef` can route via an optional per-squad egress proxy for corporate networks. | Arch §9.2, AD-7, D5. NFR-SEC4. Egress is policy, not hardcode. |

---

## Epic 5 — Agent shims, A2A & conformance (AD-4) — **the moat seam**

**Objective:** Invoke agents southbound over A2A; ship OpenClaw + Hermes shims that both run real Runs
in one squad; express capability gaps as first-class Agent Card flags; pin protocol versions behind the
seam; deliver a runnable conformance suite. **Zero core changes to add a runtime.** The **model backend
an Agent runs against is a separate seam** from the runtime flavor (§10.3, ADR-026): `Agent.spec.model`
+ `Agent.spec.modelEndpointRef` (→Secret) point a runtime at a **BYO Ollama / OpenAI-compatible
endpoint** (story 5.7) — model-endpoint config, **not** a new `AgentRuntime.type` and not a new shim.
**CEO 2026-08-11:** Ollama is covered **through the `opencode` runtime** (SST/opencode — natively
Ollama-compatible via the OpenAI-compatible provider, OSS, no paid credential), so the `opencode` shim
is **pulled from Phase 2 into v1** as the reference Ollama runtime + the $0 CI lane driver (story 5.8).

**Arch:** §7.1 (shim contract), §7.2 (Agent Card + capability + credential metadata), §7.3 (credential
injection), §7.4 (version isolation), §7.5 (launch runtimes + conformance). **FR:** FR-D1–D5. **NFR:**
NFR-EXT1/2. **Deps:** Epic 3 (reconcile dispatches A2A tasks). **Spike gate:** **ISI-2114** owns the
shim spec + reference shim + conformance assertions `[GATE-BLOCKING: conformance suite]`.

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 5.1 | As the core, I want to invoke agents **southbound over A2A** (task lifecycle, artifacts, SSE progress). | **Given** a resolved Agent Card, **When** a Run dispatches, **Then** the core submits an A2A task, streams SSE progress into `run_events`, and collects artifacts — using only A2A + the Agent Card (no other lateral protocol). | Arch §7.1, §5.2, §11.2 (`internal/a2a`). FR-D1, I4/NFR-EXT2. |
| 5.2 | As the system, I want the **Agent Card generated from the `Agent` CRD**, advertising skills, model, capability flags, and credential metadata. | **Given** an `Agent` CR, **When** its card is generated, **Then** it advertises `skills` (from `Skill` refs), `model`, **capability flags** (streaming/tool-calls/interactive as first-class metadata, not failures), and **credential capability metadata** (`credentialType`, `credentialLifecycle`). | Arch §7.2. FR-D4, R3, Challenger F15. Feeds Epic 7 credential handling. |
| 5.3 | As the system, I want **protocol version pinning behind the seam** so upstream A2A/MCP churn never touches core. | **Given** `internal/protocol/versions.go`, **When** an external-spec touchpoint is added, **Then** it sits behind the shim/adapter seam; **And** a version bump changes an adapter, never core. | Arch §7.4, OQ12, R11. `protocol/versions.go`. |
| 5.4 | As a runtime integrator, I want the **credential injection contract** so a shim maps a generic Secret into runtime-native form without logging it. | **Given** a per-user Secret ref on `Agent`, **When** the sandbox is claimed, **Then** the shim receives creds as env/volume and maps them to the runtime's expected form (e.g. `CLAUDE_CODE_OAUTH_TOKEN` vs an API-key env); **And** the shim **never persists or logs** the credential. | Arch §7.3, AD-9. FR-G1, NFR-SEC3. Coupled with Epic 7. |
| 5.5 | As an ecosystem, I want the **OpenClaw and Hermes shims** to ship and both run real Runs in one squad. | **Given** a squad with an OpenClaw agent and a Hermes agent, **When** a Run executes, **Then** both runtimes run real Runs in the **same squad** (S6). | Arch §7.5, §11.2 (`shims/openclaw`, `shims/hermes`). FR-D3. Claude Code is Phase 2; **`opencode` is pulled into v1** (story 5.8, CEO 2026-08-11) as the Ollama/CI runtime. |
| 5.6 | **[GATE-BLOCKING]** As a vendor, I want a **runnable conformance suite** I can execute independently. | **Given** a shim, **When** the conformance suite runs, **Then** it checks Agent Card validity, task-lifecycle conformance, SSE progress, artifact emission, capability-flag honesty, and credential-metadata correctness; **And** passing = "works in any squad, zero core changes." **And** the suite exposes an **Ollama lane** — the same assertions run with the runtime's model resolved to a BYO Ollama endpoint (story 5.7), **driven by the `opencode` runtime (5.8)**, giving vendors a $0 way to prove conformance. | Arch §7.5, §11.2 (`shims/conformance`). FR-D5. **Deps: ISI-2114** — the suite + reference shim are produced there (Ollama lane included); §7 is the architecture-altitude input ISI-2114 formalizes. |
| 5.7 | **[CEO 2026-08-11]** As an operator, I want to point an `Agent` at my **own Ollama endpoint** (BYO local model) so a squad runs on a self-hosted model with **no paid API credits**. | **Given** an `Agent` with `Agent.spec.modelEndpointRef` → a per-user Secret (BYO Ollama / OpenAI-compatible endpoint) and `Agent.spec.model` set, **When** a Run dispatches, **Then** the resolved runtime (**`opencode` by default, story 5.8; any `byoModelEndpoint`-capable runtime**) rides the **OpenAI-compatible wire** to that endpoint through the **existing shim seam — no new `AgentRuntime.type`, no new image, zero core change** — and the Agent Card advertises the `byoModelEndpoint` capability + honest capability flags. **And** the **conformance Ollama lane** (5.6/ISI-2114) proves an Ollama-backed runtime passes task-in → run → artifacts-out. | **Ollama is a model backend (§10.3 model-endpoint seam, ADR-026), not an `AgentRuntime.type`.** Requires the resolved runtime to speak an OpenAI-compatible / Ollama-native wire — the **`byoModelEndpoint` capability (§10.1)**, gated by conformance; a runtime lacking it advertises the gap honestly (weak local models must not fail silently mid-Run). Credential shape = Epic 7.5. Free CI lane = ISI-2157. **Reference runtime = `opencode` (story 5.8)** — natively Ollama-compatible. **Gap flagged:** arch §5.1 now adds `modelEndpointRef` to the `Agent` CRD — **Epic 1 story 1.2 must add that field** (and reconcile the `AgentRuntime` CRD, §5.3/ISI-2144, still absent from 1.2) at Gate 2 before 5.7 builds. |
| 5.8 | **[CEO 2026-08-11]** As the platform, I want the **`opencode` runtime shim in v1** (pulled from Phase 2) so Ollama is covered through a concrete, natively-compatible OSS runtime. | **Given** an `AgentRuntime` of `type: opencode`, **When** its `Agent` sets `modelEndpointRef` → an Ollama endpoint and `model` (e.g. `qwen3`/`llama`/`deepseek`), **Then** the opencode shim runs a real A2A Run against that local model — via opencode's OpenAI-compatible provider (`baseURL …:11434/v1`) — with **zero paid credential** — and **passes the conformance Ollama lane** (5.6). **And** opencode also runs against paid providers unchanged (the endpoint is config, not baked in). | opencode = SST OSS coding agent, native Ollama support (`ollama launch opencode`, 75+ providers). **Pulls opencode forward from Phase 2 (§10.1) into the v1 shim set {OpenClaw, Hermes, opencode}** — **v1-scope change, Gate 2 must ratify.** Justified: cheapest runtime to stand up (OSS + local model + no OAuth) **and** it is the driver for the $0 CI lane (ISI-2157, Epic X). `shims/opencode`. |

---

## Epic 6 — Memory service / knowledge record (AD-6) — **parity, built right**

**Objective:** Ship `ksquad-memory`, a Go service over Postgres + `pgvector`, exposing MCP tools
(semantic search + per-agent diary for MVP), owning the provenance / authorization / per-principal
trust boundary. **Memory is parity, not the moat** — least effort that fully satisfies the FR-E6/E7
trust model. **Memory is a security surface**, and reads are untrusted input.

**Arch:** §8.1–8.4 (posture, build-vs-integrate, MVP tool surface, data model + trust boundary), §9.1
(squad scoping). **FR:** FR-E1–E7. **NFR:** NFR-SEC6. **Deps:** Epic 1 (types), Epic 4.1 (tenancy for
scoping). No spike-gate dependency.

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 6.1 | As the system, I want `ksquad-memory` as a first-class Go service over **Postgres + pgvector** with the `memory_records` schema. | **Given** the service + `db/migrations`, **When** it starts, **Then** `memory_records(id, squad_id, project_id, principal_id, run_id, kind, content, embedding vector, created_at, provenance jsonb)` exists and embeddings/semantic search run on pgvector. **And** we integrate the store — **not** a bespoke vector engine (OQ10). | Arch §8.2, §8.4, §11.2 (`cmd/memory`, `internal/memory`). FR-E1. |
| 6.2 | As an agent, I want MCP tools `memory.write` / `memory.search` / `diary.append` / `diary.read`. | **Given** the memory MCP surface, **When** an agent calls a tool, **Then** the MVP tool set (semantic search + per-agent diary) works per §8.3. **And** `memory.relate` (KG) is **designed for but not shipped** (fast-follow, CEO Gate 1). | Arch §8.3. FR-E2/E4. KG relations = fast-follow, not a v1 blocker. |
| 6.3 | As a security owner, I want **writes authorized + provenanced**. | **Given** a `memory.write`, **When** it is stored, **Then** the record carries author (principal/agent/run) + write time, and unattributed/unauthorized writes are **rejected**. **And** memory is **not** a work-handoff channel — coordination stays in work items (FR-B3). | Arch §8.4, FR-E6, Challenger F7. Structural enforcement of the F16 CEO-gate flag. |
| 6.4 | As a reading agent, I want **reads treated as untrusted input** with provenance surfaced. | **Given** a record written by agent A, **When** agent B reads it via `memory.search`, **Then** provenance is surfaced so B (and its Role/prompt) can weight it — defending against **memory poisoning / prompt-injection-into-a-knowledge-record** (R9). | Arch §8.4, FR-E7, NFR-SEC6. Tested by the poisoning test (Epic X). |
| 6.5 | As a tenant, I want memory **scoped to squad/Project + per-principal**, no cross-tenant leakage. | **Given** records in squad S1, **When** a principal in squad S2 queries, **Then** cross-tenant read/write is **denied by construction** (matches the namespace model, AD-5); **And** one principal cannot write another's diary. | Arch §8.3, §8.4, FR-E5. |

---

## Epic 7 — Credential plumbing & graceful pause/resume (AD-9)

**Objective:** Two concrete, distinct credential stories (Claude-family OAuth + second-runtime API
key), **plus the Ollama BYO-endpoint shape (7.5)**, per-user Secret refs, never a shared master
credential, with graceful pause/resume on expiry/rotation. **Not Claude-shaped.**

**Arch:** §10 (both credential stories + pause/resume), §7.2 (credential metadata), §7.3 (injection).
**FR:** FR-G1, FR-G2, FR-G3. **NFR:** NFR-SEC3. **Deps:** Epic 5 (shim cred injection + card metadata),
Epic 3 (Run `Paused` condition). **Spike gate:** **ISI-2112** for OAuth refresh UX
`[GATE-BLOCKING on the Claude-family refresh path]`.

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 7.1 | As an enterprise, I want each `Agent` to reference credentials via **per-user k8s Secret refs** (BYO), never a shared master. | **Given** an `Agent`, **When** it is composed, **Then** it references a per-user Secret; **And** KSquad stores **no** shared master credential; **And** creds are per-namespace, never cross-squad. | Arch §10, §9.1, AD-9. FR-G1, NFR-SEC3. |
| 7.2 | **[Claude-family credential story]** As an operator, I want the Claude Code OAuth-subscription flow: `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` as a per-user Secret. | **Given** a Claude-family `Agent`, **When** the token is provisioned, **Then** it is held as a per-user Secret ref and injected by the shim (Epic 5.4); **And** the OAuth-subscription lifecycle (refresh/concurrency headless) follows ISI-2112. | Arch §10, FR-G2. **Deps: ISI-2112 `[GATE-BLOCKING]`** — if the spike shows subscription-token lifecycle is unworkable at scale, the BYO-subscription decision triggers a **CEO-gate conversation** (watch item, §10). |
| 7.3 | **[Second-runtime credential story]** As an operator, I want the non-Claude runtime's concrete credential path: long-lived API key / provider token as a per-user Secret (no interactive OAuth). | **Given** an OpenClaw/Hermes `Agent`, **When** the key is provisioned, **Then** it is a per-user Secret; rotation = Secret update; **And** the exact token type/refresh is **pinned per that runtime in this story** (OQ11) so the credential model is vendor-neutral, not Claude-shaped. | Arch §10, FR-G2, Challenger F15/OQ11. **Deps:** pin the second-runtime token model (Epic decision, resolves OQ11). |
| 7.4 | As the system, I want **graceful pause/resume** on credential expiry/rotation mid-Run, for both models. | **Given** a Running Run whose credential expires/rotates, **When** the controller detects it, **Then** the Run moves to a **`Paused`** condition, emits a clear operator signal (Epic 8 / FR-F6), and **resumes on refresh** — never fails opaquely. **And** this holds for the OAuth-refresh, static-key, **and Ollama-endpoint (7.5)** models (shim surfaces `credentialLifecycle`; an unreachable endpoint is a legible `Paused`, not an opaque failure). | Arch §10, §7.2. FR-G3, S10. |
| 7.5 | **[CEO 2026-08-11]** As an operator, I want the **Ollama / BYO-endpoint credential shape** — an endpoint URL (+ optional token) as a per-user Secret ref, model name per Agent, **no paid provider token**. | **Given** an Ollama-backed `Agent` (Epic 5.7), **When** it is composed, **Then** the endpoint is a **per-user Secret ref** (never a shared platform endpoint), the model name is Agent-level config, and the shim injects the endpoint into the runtime's model config; **And** rotation = Secret update; **And** an unreachable endpoint surfaces via pause/resume (7.4), not an opaque failure. | Third credential story (§11 now reads **Two→Three stories**, ADR-026, §10.3) beside Claude-OAuth (7.2) and second-runtime API-key (7.3). Self-hosted endpoint = **also the $0 CI lane** (ISI-2157). **No spike gate** (no OAuth); vendor-neutral by construction (FR-G1/G2), reinforces — never reopens — the per-user Secret-ref lock (ADR-010). |

---

## Epic 8 — Operator console (AD-10)

**Objective:** A Next.js (App Router) + React console — a **legibility + composition** surface (not an
IDE) — that shows squads, streams live Runs over SSE, inspects artifacts, kills Runs, composes CRDs,
and surfaces credential/auth state. Uses the BFF to proxy SSE and hide the Go API.

**Arch:** §4.5 (frontend), §4.4 (SSE hub), §11.2 (`console/`). **UX:** the six screens in
`docs/bmad/ux` (`01-squad-overview` … `05-credential-auth-state`) **plus the 2026-08-11 CEO-added
screens: build browser, project dashboard, discussion room** (mocks in flight; theme toggle
dark+light and the v2 logo are v1 requirements, story 8.9). **FR:** FR-F1–F6. **NFR:** NFR-USE2.
**Deps:** apiserver (Epics 2/3) + SSE hub. Console is sequenced last (§4.7).

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 8.1 | As an operator, I want a **squad overview** (Teams → Projects → Run status) at a glance. | **Given** running squads, **When** I open the console, **Then** I see all Teams, their Projects, and Run status without `kubectl` (S2). | UX `01-squad-overview`. FR-F1. |
| 8.2 | As an operator, I want **live Run progress via SSE**. | **Given** a Running Run, **When** I open its stream, **Then** progress streams live via SSE through the Next.js BFF proxy (hiding the Go API). | Arch §4.4/§4.5. UX `02-run-stream-sse`. FR-F2. |
| 8.3 | As an operator, I want to **inspect a Run's artifacts** and handoff outputs. | **Given** a completed/collecting Run, **When** I open artifacts, **Then** I can inspect artifact blobs + handoff outputs (from the coordination record). | UX `03-artifact-inspection`. FR-F3. |
| 8.4 | As an operator, I want to **kill a Run in ≤2 clicks** from the UI. | **Given** a Running Run, **When** I click kill (≤2 clicks), **Then** the console calls apiserver → Run `Canceling` (Epic 3.3). | UX (on overview + run stream). FR-F4/A6, S2. |
| 8.5 | As a squad author, I want to **compose** `Team`/`Agent`/`Role`/`Skill`/`Project` resources (create/edit). | **Given** the compose screen, **When** I create/edit core CRDs, **Then** valid CRs are applied via apiserver; **And** the console is **not** an IDE/code editor/dashboard (scope guard, R6). | UX `04-compose-crd`. FR-F5. |
| 8.6 | As an operator, I want to **surface credential/auth state**, including a clear paused-on-expiry signal. | **Given** an Agent whose Run is `Paused` on an expired token, **When** I view credential state, **Then** the console shows a clear paused-on-expiry signal (supports S10, Epic 7.4). | UX `05-credential-auth-state`. FR-F6. |
| 8.7 | **[CEO 2026-08-11]** As an operator, I want a **per-Run build browser** so I can see WHAT an agent actually built, not just task status. | **Given** a Run that modified the Project workspace, **When** I open its build browser, **Then** I see the workspace **file tree** scoped to that Run's changes, a **per-file diff view**, and a **code viewer**, all linked to the producing Run (and to its PR/CI state once Epic 11 lands). **And** this extends artifact inspection (8.3) — blobs and handoffs stay reachable from the same surface. | Extends FR-F3. Paperclip gap closed. Diff base = Run's worktree branch vs `Project.repo` default ref (§9.4 worktree model). |
| 8.8 | **[CEO 2026-08-11]** As an operator, I want a **per-Project dashboard layer** — health, work items, consumption — at a glance. | **Given** a Project, **When** I open its dashboard, **Then** I see: (a) **health** — active Runs, squad status, recent activity; (b) **work items** — open/claimed/blocked/done counts + throughput over time (from the Epic 2 coordination record); (c) **consumption** — token usage + cost per agent / per Run / per Project, and sandbox/runtime resource usage. **And** consumption metrics **ride the OTel pipeline** (§17.2 handoff) — no bespoke accounting path — and are **attributed per user/principal**, first-class under the BYO-subscription credential model (locked decision). | Consumption attribution joins §17.2 metrics with Epic 7 credential principal. PR/CI tiles arrive via Epic 11. |
| 8.9 | **[CEO 2026-08-11]** As an operator, I want **dark AND light mode** and the **v2 logo** across the console. | **Given** any console screen, **When** I toggle theme, **Then** all screens render in light mode mirroring the same design tokens (ISI-2126 visual system) — the toggle is **v1, not polish**. **And** all screens + the visual-system header use the **v2 logo** from `assets/logo/` once ISI-2137 lands. **And** light-mode mocks exist for all screens (00 visual system, 01–05, build browser, discussion room, dashboard). | **Deps: ISI-2137** (v2 logo assets — Graphic Designer, pending) + mock revision task (child of ISI-2131). |

---

## Epic 9 — Install, exposure & storage (Helm hardening) — **CEO directive 2026-08-11**

**Objective:** The chart must not assume cluster defaults. It **creates** the cluster-facing
networking (Gateway API) and **parameterizes** all storage, so KSquad installs on any conformant
cluster regardless of its default GatewayClass / StorageClass posture. This epic hardens the
skeleton from story 1.4 into the full install surface (S1).

**Arch:** §16 (amended 2026-08-11), §9.4 (workspace access modes). **FR:** S1, NFR-USE1.
**Deps:** 1.4 (chart skeleton), Epic 3 (apiserver service), Epic 8 (console service), Epic 2
(Postgres/CNPG). **No spike-gate dependency.**

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 9.1 | As a platform engineer, I want the chart to **create the `Gateway` + `HTTPRoute` resources** for the console and apiserver, so exposure works on any Gateway API implementation I choose. | **Given** a cluster with any Gateway API controller (cilium / envoy / istio / traefik), **When** I install with `gateway.className` set, **Then** the chart renders a `Gateway` (listeners + TLS from values: hostnames, cert secret refs, HTTPS redirect) and `HTTPRoute`s binding the console and apiserver services, with the apiserver route preserving **SSE** (no response buffering / default timeouts that kill the stream). **And** install **fails fast with a clear error if `gateway.className` is unset** — the chart never creates a `GatewayClass` and never falls back to a hardcoded or cluster-default class. | Arch §16. SSE is the console's live channel (Epic 8.2); chart docs carry per-implementation notes (e.g. envoy/istio timeout & buffering knobs). |
| 9.2 | As a platform engineer, I want **every PVC to take `storageClassName` from values**, so installs never silently bind the cluster default StorageClass. | **Given** a cluster with an unsuitable (or no) default StorageClass, **When** I install with `storage.postgres.storageClassName` and `storage.workspaces.storageClassName` set, **Then** the CNPG cluster and all per-Project workspace PVCs render with exactly those classes. **And** when either value is unset, `helm template`/install **fails fast naming the missing value** — relying on the cluster default is treated as misconfiguration. | Arch §16, §9.4. Workspace PVCs are provisioned by the operator per `Project` (Epic 4) — the operator reads the class from Helm-provided config, never from cluster defaults. |
| 9.3 | As a platform engineer, I want **access-mode behavior documented per storage-class capability**, so I know what my class supports before install. | **Given** the chart docs, **When** I read the storage section, **Then** it states: `RWO` is the default access mode (worktree-per-Run); `RWX` is optional and only valid when the class supports it (enables true parallel Runs on one Project, §9.4); expansion/snapshot behavior is documented as class-dependent. **And** the values schema validates `accessMode` against an enum and emits a warning when `RWX` is requested (capability can't be introspected — documented pre-flight check). | Arch §9.4. Ties to Epic 4 workspace provisioning; mismatch surfaces at `Project` provision time, not at Run claim time. |

---

## Epic 10 — Discussion rooms (per-Project) — **CEO product input 2026-08-11**

**Objective:** Every `Project` gets a **persistent discussion room** for all team members (agents +
humans): context, Q&A, decisions, announcements. This is a **visibility/collaboration surface — it
is NOT a coordination channel** and does not reopen the locked "coordination via shared work items,
not agent P2P chat" decision: agents still claim/coordinate via work items + fencing (Epic 2); A2A
P2P chat stays out of scope. Missing from Paperclip — a deliberate delta.

**Arch:** ADR-001 (Postgres, NOT a CRD), §6.1 patterns (append-only, provenance), §7 (memory
service query surface). **FR:** new scope — Gate 2 PRD addendum candidate. **Deps:** Epic 2
(coordination schema patterns), Epic 6 (memory indexing), Epic 8 (console surface).

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 10.1 | As the system, I want the **discussion schema + API** (Postgres `coord`-adjacent): rooms, threads, messages. | **Given** a `Project`, **When** it is created, **Then** one persistent room exists (1:1 with Project) with **threaded messages** stored in Postgres — append-only, **provenance-tagged** (author principal, agent-vs-human, Run linkage when posted from a Run). **And** there is no CRD for rooms (ADR-001). | Mirrors §6.1 append-only/provenance discipline. |
| 10.2 | As an agent, I want room content **queryable by the memory service** so decisions/context are recallable. | **Given** room messages, **When** I `memory_search`, **Then** relevant messages surface with provenance and the untrusted-read posture applied (§7.3). **And** room writes carry the same provenance contract as memory writes. | Arch §7. Fast-follow acceptable post-v1 if memory surface slips — flag at Gate 2. |
| 10.3 | As an operator, I want the **room in the console** — read, post, reply-in-thread, agent + human participants side by side. | **Given** a Project room, **When** I open it, **Then** I see threaded history with author/provenance badges (agent/human/Run) and can post/reply; agents post via the apiserver tool surface, humans via console. | Epic 8 surface; mock in flight (story 8.9 theming applies). |
| 10.4 | **[scope guardrail]** As the team, I want the room **structurally unable** to become a coordination back-channel. | **Given** the room API, **When** I inspect it, **Then** there is **no** claim/handoff/state-transition semantics — work claims, checkout, and completion exist only on work items (Epic 2). **And** review-time evidence (F6-style covert-channel test, Epic X) shows coordination state cannot be mutated via the room. | Locked-decision guardrail; pairs with FR-B3 / §8.4 honest framing (F6). |

---

## Epic 11 — Source-control sync (GitHub first) — **CEO product input 2026-08-11**

**Objective:** Sync state from source control INTO the platform so the console reflects reality
without users leaving it: issues ⇄ work items, PR status, CI results, build artifacts — with a
provider seam that doesn't preclude GitLab/Bitbucket later.

**Arch:** §5.1 (`Project.repo` — URL/ref/auth already on the CRD), ADR-001 (synced state in
Postgres, provenance-tagged), §16/Epic 9 (webhook ingress via the Gateway/HTTPRoute surface).
**FR:** new scope — Gate 2 PRD addendum candidate. **Deps:** Epic 1 (`Project` CRD), Epic 2 (work
items), Epic 7 (per-user Secret refs / BYO credentials), Epic 8 (console), Epic 9 (ingress),
Epic 10 (CI auto-post).

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 11.1 | As the system, I want a **repo-sync reconciler** per `Project` — webhook-driven with periodic poll fallback. | **Given** a `Project` with `repo` set, **When** push/PR/check events arrive via webhook ingress (Epic 9 HTTPRoute), **Then** the reconciler updates synced state; **When** webhooks are absent, **Then** a periodic poll keeps state fresh (interval via values). **And** credentials come from the **per-user Secret refs** (BYO model, Epic 7) — never a shared platform token. | Provider seam: reconciler talks to a `SourceProvider` interface; GitHub is the v1 impl. |
| 11.2 | As an operator, I want **GitHub issues ⇄ KSquad work items** synced (status, labels, linkage). | **Given** a linked repo, **When** a GitHub issue changes, **Then** the linked work item reflects status/labels (and vice versa per configured direction); **And** synced state lives in Postgres with **provenance tagging** so the console distinguishes KSquad-native vs GitHub-sourced items. | Arch ADR-001. Conflict policy: last-writer-wins with audit row (§6.5 discipline). |
| 11.3 | As an operator, I want **PR status** — open/merged/closed + review state — linked to the Run/branch that produced it. | **Given** a Run that pushed a branch, **When** a PR exists for it, **Then** the console shows PR state + review status on the Run and in the dashboard (8.8), updated by the reconciler. | Links Epic 3 (Run) ↔ GitHub PR. |
| 11.4 | As an operator, I want **CI check results** per PR and per Run, with **build/CI artifacts linked into the build browser** (8.7). | **Given** CI runs on a linked PR/branch, **When** checks complete, **Then** results surface per PR and per Run; **And** published artifacts are linked into the Run's build browser. | Feeds dashboard PR/CI tiles (8.8). |
| 11.5 | As a platform engineer, I want the **provider seam** explicit so GitLab/Bitbucket can follow without redesign. | **Given** the sync code, **When** reviewed, **Then** all GitHub API access sits behind the provider interface (issues/PRs/checks/artifacts/webhook parsing); adding a provider = new impl + config, no reconciler rewrite. | Same seam discipline as §10 shims. |
| 11.6 | As an operator, I want **synced state surfaced in console** — dashboard tiles + CI-failure auto-post to the Project room. | **Given** a CI failure on a linked PR, **When** the reconciler records it, **Then** a provenance-tagged context message auto-posts to the Project discussion room (Epic 10) and the dashboard PR/CI tiles update. | Closed loop: sync → dashboard (8.8) → room (10.3). |

---

## Epic 12 — Plugin architecture (event seam + SDK) — **CEO product input 2026-08-11**

**Objective:** The platform **emits domain events** (Run lifecycle, work-item transitions, memory
writes, source-control sync results) on an internal **event seam**; **plugins register** to those
events and react outside the core. **Guard (CEO): plugins are observers, not a coordination path**
— no claim/handoff/state-transition capability, ever. The Dynatrace GRAIL memory backend
(ISI-2142) is reframed from a bespoke integration into a **memory SDK/plugin — the seam's first
consumer**.

**Arch:** ADR-001 (event log in Postgres), §6.5 audit patterns (append-only), §7 (memory service),
§17.2 (OTel observability of the seam itself). **FR:** new scope — Gate 2 PRD addendum candidate.
**Deps:** Epic 2 (coordination events), Epic 6 (memory records), Epic 11 (sync/CI events), Epic 7
(BYO credentials for plugin outbound calls).

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| 12.1 | As the system, I want a **domain event seam**: every state transition the platform records is also emitted as an event. | **Given** Runs, work items, memory records, and sync results, **When** their state changes, **Then** an append-only event row is written in the **same transaction** as the state change (Postgres outbox pattern) and published to subscribers at-least-once. **And** the seam is observable via the §17.2 OTel pipeline (emit/deliver lag, failures). | Outbox = no dual-write divergence; same discipline as §6.1 append-only. Event catalog versioned (spec-drift isolation, §10.2). |
| 12.2 | As a plugin author, I want a **plugin SDK + registration contract** so external systems can subscribe without touching core code. | **Given** the SDK, **When** a plugin registers (declared per Project/squad in config), **Then** it receives subscribed event types with delivery receipts + retry/backoff; **And** plugin config + outbound credentials come from **per-user Secret refs** (BYO, Epic 7); **And** a failing/dead plugin **cannot block or slow the core** (isolated delivery workers, dead-letter + circuit breaker). | Plugin runs out-of-process (sidecar/service), never in the reconcile path. Same seam discipline as §10 shims. |
| 12.3 | **[ISI-2142]** As an operator, I want the **Dynatrace GRAIL memory-storage plugin** — memory records stream to GRAIL as the seam's **first consumer**. | **Given** the memory service (Epic 6), **When** memory writes occur, **Then** the GRAIL plugin consumes memory events off the seam and writes them to Dynatrace GRAIL (OTLP logs; SmartScape entity-graph mapping; DQL-queryable) with provenance intact (§7.3). **And** GRAIL unavailability never blocks a memory write — the plugin trails the outbox and catches up. | Reframes ISI-2142 from bespoke integration to **memory SDK/plugin**. Platform memory remains Postgres/pgvector source-of-truth; GRAIL is a downstream replica/analytics sink. |
| 12.4 | **[scope guardrail]** As the team, I want plugins **structurally unable** to become a coordination path. | **Given** the plugin contract, **When** reviewed/tested, **Then** plugins receive events **read-only**; the SDK exposes no claim/handoff/state-mutation surface; and a misbehaving plugin cannot mutate coordination state or satisfy a work-item transition (proven by a test in the Epic X suite). | Same guardrail family as 10.4 (rooms) — observers, not participants. Locked decision holds. |

---

## Epic X — Isolation test suite (cross-cutting, first-class CI artifact)

**Objective:** Prove blast-radius containment and memory-trust enforcement with **adversarial** tests
that are first-class CI artifacts owned here, not asserted claims. **Isolation is tested, not asserted.**

**Arch:** §4.3 (two adversarial tests), §8.4 (poisoning), §11.2 (`test/isolation`). **FR/NFR:** NFR-SEC1,
NFR-SEC5, NFR-SEC6, S4. **Deps:** Epic 4 (isolation), Epic 6 (memory). **Spike gate:** ISI-2113 informs
the RuntimeClass under test.

**CI free-testing lane (CEO 2026-08-11, ISI-2157):** these adversarial tests and the conformance suite
(5.6) run in CI against an **Ollama-backed squad running the `opencode` runtime (Epic 5.8)** (Ollama
service container / self-hosted GPU runner, model resolved per Epic 5.7 / 7.5) so smoke + e2e squad
scenarios execute with **no paid API credits**. `opencode` is the natural driver — OSS + native Ollama +
no OAuth. ISI-2157 owns the CI wiring; this epic and Epic 5 own the scenarios it runs.

| Story | Statement | Key acceptance criteria (GWT) | Notes |
|-------|-----------|-------------------------------|-------|
| X.1 | As a security owner, I want a **hostile-Run blast-radius test**. | **Given** a Run executing arbitrary code, **When** it tries to reach another squad's workspace/network/secrets, **Then** it is **contained** (attempt fails); the test is a required CI artifact. | Arch §4.3, S4, NFR-SEC1. Hard gate on the ISI-2113 RuntimeClass pick (Epic 4.2). |
| X.2 | As a security owner, I want a **residue/reuse test** across Runs and principals. | **Given** a sandbox/PVC reused after a Run, **When** the residue test runs, **Then** no filesystem/in-memory/credential/scratch state bleeds across Runs or principals (teardown-and-replace, per-principal scope). | Arch §4.3, §9.3, FR-C6, NFR-SEC5, R12. Gates the reset-in-place optimization decision. |
| X.3 | As a security owner, I want a **memory-poisoning test**. | **Given** an adversarial record written by agent A, **When** agent B reads it, **Then** provenance is surfaced and the untrusted-read posture holds — B is not silently steered (R9). | Arch §4.3, §8.4, FR-E7, NFR-SEC6. |

---

## Spike-gate dependency summary (explicit, per the issue mandate)

| Spike | Status | Stories that depend on it | Blocking nature |
|-------|--------|---------------------------|-----------------|
| **ISI-2112** (OAuth refresh cadence / subscription-token lifecycle headless) | backlog | 7.2 (Claude-family cred), 7.4 (pause/resume OAuth path) | **GATE-BLOCKING** on the Claude-family refresh path; failure → CEO-gate conversation on BYO-subscription (watch item, Arch §10/§14) |
| **ISI-2113** (RuntimeClass isolation + warm-pool sizing benchmark) | backlog | 3.5 (pool-sizing tuning), 4.2 (RuntimeClass pick), 4.5 (reset-vs-replace), X.1 (hostile-Run) | **GATE-BLOCKING** on the RuntimeClass pick (hostile-Run containment = hard gate; isolation > latency per §1 tiebreaker); tuning-blocking on sizing curve |
| **ISI-2114** (shim spec + reference shim + conformance assertions, **incl. Ollama lane**) | backlog | 5.6 (conformance suite + Ollama lane), 5.7 (Ollama model backend), and shapes 5.1–5.5 | **GATE-BLOCKING** on the conformance suite; §7 is the architecture-altitude input ISI-2114 formalizes |
| **ISI-2157** (CI free-testing lane: Ollama service container / self-hosted GPU runner) | backlog (high) | 5.7, 7.5, Epic X CI lane | **Not a spike** — a CI enabler; not release-blocking, but unblocks $0 smoke + e2e squad testing. Owned by CI/DevEx, not architecture. |

**Parallelization:** Epics 1–2 (CRD foundation + coordination spine) depend on **no** spike and start
immediately, in parallel with ISI-2112/2113/2114. The spikes' results tune AD-3/AD-9/AD-4 **before**
Epics 3/4/5/7 need them — no idle waiting, no fabricated evidence (Arch §14 recommendation).

## FR coverage check

FR-A1–A6 → Epics 1, 3 · FR-B1–B4 → Epic 2 · FR-C1–C6 → Epics 3, 4 · FR-D1–D5 → Epic 5 ·
FR-E1–E7 → Epic 6 · FR-F1–F6 → Epic 8 · FR-G1–G3 → Epic 7 · **S1 / NFR-USE1 (install surface) →
Epics 1.4, 9**. NFR-SEC/REL/PERF/SCALE/OBS threaded into the owning epics; the security NFRs are
additionally **tested** in Epic X.
**CEO 2026-08-11 additions (no PRD FR yet — Gate 2 must ratify as a PRD addendum):** build browser
→ 8.7 (extends FR-F3) · dashboard layer → 8.8 · discussion rooms → Epic 10 · source-control sync →
Epic 11 · theming/logo → 8.9 · plugin architecture (event seam + GRAIL memory plugin) → Epic 12 ·
**Ollama model backend + $0 CI lane → 5.7 + 7.5 (extend FR-D/FR-G via the model/credential seam) +
ISI-2114 Ollama conformance lane + ISI-2157 CI lane**. **No orphan FRs; no orphan stories.**

---

*Prep artifact — awaiting CEO Gate 2. Once Gate 2 passes, per-story files are expanded via
`bmad-create-story` in `docs/bmad/stories/` and executed by the Developer agent in the Epic order above.*
