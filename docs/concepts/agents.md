---
title: Agents (Agent & AgentRuntime)
description: An Agent is one member of a squad — a runtime plus a role, skills, and a per-user credential. AgentRuntime selects which coding CLI runs the work.
sidebar_position: 2
---

# Agents

**CRDs:** `Agent`, `AgentRuntime` (`ksquad.io/v1alpha1`)

An **Agent** is a single member of a squad. It composes four things:

- a **runtime** (`runtimeRef`) — *which coding agent CLI* runs the work;
- a **role** (`roleRef`) — *how it behaves*;
- **skills** (`skillRefs`) — *what tools it may use*;
- a **credential** (`credentialSecretRef`) — *whose subscription it runs on*.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata:
  name: dev-1
  namespace: ksquad-system
spec:
  runtimeRef: claude-code          # → AgentRuntime
  roleRef: software-engineer       # → Role
  skillRefs: [git, run-tests]      # → Skill[]
  credentialSecretRef: claude-oauth
  model: claude-opus-4-8
  # optional:
  # modelEndpointRef: my-ollama    # BYO model endpoint (see Credentials)
  # fallbackModel: claude-sonnet-5 # used if the primary model is rate-limited
  # capabilityOverrides: { ... }   # narrow the agent's advertised capabilities
```

When you create an `Agent`, the **Agent reconciler** validates that the credential Secret and runtime
resolve, then publishes the agent's **card** — the capability envelope other parts of KSquad negotiate
against. An agent whose credential can't be resolved is **rejected**, not silently broken.

## AgentRuntime — the pluggable coding-agent flavor

`AgentRuntime` makes *which coding CLI runs* a first-class, referenceable object instead of an implicit
property of a hand-built image. This is what lets KSquad be **agent-runtime-agnostic**: Claude Code,
OpenClaw, Hermes, and others plug in behind the same shim contract.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: AgentRuntime
metadata:
  name: claude-code
spec:
  type: claude-code                # claude-code | kimi-code | opencode | codex | openclaw | hermes
  image: ghcr.io/ksquad/runtime-claude-code
  cliVersion: "1.2.3"              # pinned by default for reproducibility
  capabilities:
    docker: false
    github: true
    packageInstall: true
  credentialSecretRef: claude-oauth
```

Key ideas:

- **The image ships a minimal base + the coding CLI + the KSquad shim** — and *no* language
  toolchains. Toolchains (Go, Node, Python, …) are staged per-Run from what a Run's skills declare, so
  there's no combinatorial "flavor × toolchain" image matrix.
- **`cliVersion` is pinned by default.** A Run is reproducible, and a bad upstream CLI release can't
  silently poison in-flight work. KSquad canaries version bumps against a conformance suite before
  rolling them out.
- **Capabilities are declared, not ambient.** `docker`, `github`, and `packageInstall` are flags the
  operator reads to decide what to mount or inject — and validation fails closed (for example, asking
  for real Docker on a gVisor-only runtime is rejected unless a supported mechanism is available).
- **`type` must pass conformance.** Every runtime type passes a shim conformance suite — "A2A task in →
  run → artifacts out" — before it's trusted. Unproven types are admitted only behind an explicit
  experimental flag.

## The shim contract

Every runtime speaks to KSquad through a **shim**: A2A southbound (KSquad hands the agent a task and
receives artifacts) and MCP for tool access. Because the shim is the only seam, you can **swap or mix
runtimes** without changing your platform — the moat is orchestration, not any one agent.

## Credentials — bring your own

An agent authenticates with a **per-user Kubernetes Secret** referenced by `credentialSecretRef`.
KSquad holds **no shared master credential**. Three credential shapes ship at v1:

- **Claude-family** — one-time OAuth, then zero-touch auto-refresh.
- **Non-Claude runtimes** — a long-lived API key or provider token.
- **BYO model endpoint** — your own Ollama or OpenAI-compatible server URL.

See [Credentials](../operator-guide/credentials) for the full lifecycle.

## Model selection and fallback

`spec.model` picks the model; `spec.modelEndpointRef` (optional) points at a BYO endpoint; and
`spec.fallbackModel` (optional) lets a Run switch models mid-flight if the primary is rate-limited,
instead of pausing. See [Runs → rate-limit recovery](./runs#rate-limit-recovery).

## Related

- [Roles](./roles) — behavior profiles.
- [Skills](./skills) — granted capabilities.
- [Runs](./runs) — how agents get work.
- [Credentials](../operator-guide/credentials) — the credential lifecycle.
