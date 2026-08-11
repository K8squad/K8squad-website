# KSquad — BMAD Kickoff Brief (CEO)

**Owner:** BigBoss (CEO) · **BMAD Orchestrator:** Alfred (CTO)
**Source ticket:** ISI-2115 · **Date:** 2026-08-10 · **Status:** kickoff → in execution

This brief is the CEO scope + decision boundary for the BMAD flow. It is authored by the
CEO to anchor delegation. The actual BMAD artifacts (brainstorming, PRD, architecture,
epics/stories) are produced by the CTO's team and land in this folder.

---

## 1. Product vision

**KSquad** = a **Kubernetes-native, agent-agnostic AI agent orchestration platform**. Agents
are organized into **squads** (virtual teams) that coordinate on shared work items. New OSS
project, **potential AAIF (AI Agent Infrastructure Foundation) candidate**. Conceptually
inspired by Paperclip's company/agents/issues coordination model, but a **fresh, operator-based
codebase** — not a fork.

## 2. LOCKED decisions (Henrik, 2026-08-10 — do not re-litigate)

| Area | Decision |
|------|----------|
| Frontend | **Node.js** — target a polished UI/UX |
| Backend | **Go** |
| Memory server | **First-class component of the project** (not an external dependency) |
| Coordination model | Shared work items (issues / comments / checkout), **NOT** agent P2P chat |
| Southbound protocol | **A2A** (Agent Cards, task lifecycle, artifacts, SSE progress) |
| Tools protocol | **MCP** |
| A2A P2P chat | **Out of scope** for coordination |
| Credentials | **BYO-subscription** — per-user Secret refs on the Agent CRD |

These are inputs, not open questions. BMAD should build on them, not reopen them. Anything a
phase wants to change here escalates to the CEO before proceeding.

## 3. Architecture inputs (seed for PRD + architecture phases)

- **CRD surface:** `Team`, `Agent`, `Role`, `Skill`, `Project` (workspace PVC + GitHub repo), `Run`.
- **Sandbox runtime:** AgentSandbox-style **warm pool** (Kata vs gVisor under evaluation),
  per-project workspace PVC.
- **A2A usage:** Agent Cards for capability discovery; task lifecycle for runs; artifacts for
  handoffs; SSE for progress.
- **Agent shims** for heterogeneous runtimes: **OpenClaw + Hermes first**, then Claude Code, OpenCode.
- **Credential model:** `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`; GLM tokens via k8s
  Secrets; per-user Secret refs on the `Agent` CRD.

## 4. BMAD flow — phases, owners, gates

Sequential with CEO review gates. Alfred fans each phase out to the right specialist on his team.

| # | Phase | Suggested owner (Alfred's team) | Output | Gate |
|---|-------|-------------------------------|--------|------|
| 1 | Brainstorming synthesis | Brainstormer + Challenger | `docs/bmad/01-brainstorming.md` | Alfred review |
| 2 | PRD | Product Manager | `docs/bmad/02-prd.md` | **CEO gate (BigBoss)** |
| 3 | Architecture / solution design | Architect | `docs/bmad/03-architecture.md` | **CEO gate (BigBoss)** |
| 4 | Epics & stories | Story Writer / PM | `docs/bmad/04-epics-and-stories.md` | Alfred review → CEO sign-off |

**Gate rule:** Do not start phase N+1 until phase N's artifact exists and its gate owner has
approved. The two CEO gates (post-PRD, post-architecture) are where BigBoss confirms the product
and technical direction before deeper investment.

**UX note:** the Node frontend targets *polished UI/UX*. The PRD must carry explicit UX goals
(operator console: squads, runs, live SSE progress, artifacts), and the architecture must name
the frontend approach. Pull in the Graphic Designer for UX/visual direction as needed.

## 5. Seed tickets to absorb / refine (do not duplicate — reconcile into BMAD artifacts)

- **ISI-2111** — Design doc: Squad architecture v0.1 → feeds phases 1 & 3
- **ISI-2112** — Spike: `claude setup-token` longevity + headless Claude Code → feeds credential model (PRD/arch)
- **ISI-2113** — Spike: warm-pool sandbox claim latency (Kata vs gVisor vs runc) → feeds sandbox runtime (arch)
- **ISI-2114** — Spec: Agent shim interface (OpenClaw + Hermes first) → feeds shim design (arch)

Each spike/spec produces evidence the BMAD artifacts should cite, not restate. Where a BMAD
phase supersedes a seed ticket, note the reconciliation in the artifact.

## 6. Workspace conventions

- Repo: `/mnt/nas/project/ksquad` (git initialized).
- BMAD artifacts: `docs/bmad/NN-<phase>.md` (numbered, one per phase).
- Fresh codebase — no Paperclip fork. Go backend, Node frontend, first-class memory server.
- Commit each artifact as it lands; reference the ISI number in the message.

## 7. Definition of done for ISI-2115

All four BMAD artifacts exist in `docs/bmad/`, both CEO gates passed, and an epics/stories list
ready to spawn implementation issues. At that point ISI-2115 closes `done` and implementation
epics become their own tracked issues.
