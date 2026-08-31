---
title: Skills (Skill)
description: A Skill is a granted capability — the tools, permissions, toolchains, and sidecars an agent may use. K8squad ships a predefined catalog of Skills and a ready-to-run BMAD squad; skills can be defined inline or loaded from a pinned Git commit.
sidebar_position: 4
---

# Skills

**CRD:** `Skill` (`ksquad.io/v1alpha1`)

A **Skill** is a granted **capability** — it declares *what an agent may do*: which tools it can call,
what permissions it holds, and what toolchains or services its work requires. Skills are how KSquad
grants capability **explicitly and least-privilege**, instead of hoping the right binary happened to be
in an image.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Skill
metadata:
  name: run-tests
  namespace: ksquad-system
spec:
  source: inline
  mcpToolRefs: [shell, file-read, file-write]
  permissions: [workspace-write]
  requires:
    toolchains: [go@1.23, node@22]   # staged as init containers at Run time
    sidecars: []                      # long-running services, e.g. dockerd
```

## What a Skill grants

- **`mcpToolRefs`** — the [MCPServer](./mcp-servers) objects whose tools the skill exposes to the
  agent. Every ref must resolve to an existing `MCPServer` at admission — a dangling ref rejects the
  skill. And the skill may only **narrow** the server's `toolFilter`, never widen it (below).
- **`permissions`** — the permission envelope (for example, workspace write vs. read-only).
- **`requires.toolchains`** — language/CLI packs (`gh@2.62`, `go@1.23`, `node@22`, …), resolved as
  `name@version` against the [Toolchain](./toolchains) catalog. At Run time the operator stages each
  resolved pack as an **init container** into a shared volume — languages are *files*, so they cost
  nothing once the Run is running. An unknown name/version fails Run admission with an actionable
  message.
- **`requires.sidecars`** — genuine long-running services (rootless `dockerd`, a headless browser, an
  ephemeral DB). These become **sidecar** containers, and they're **capability-gated**: a sidecar whose
  capability the agent's runtime disables is rejected. stdio [MCP servers](./mcp-servers) with an
  `image` ride the same mechanism.

## Self-describing skills, operator-assembled pods

Because each skill declares its *own* requirements, the operator can assemble the exact pod a Run
needs by taking the **union** of every skill's `requires`. Version conflicts fail closed — two skills
pinning `go@1.22` and `go@1.23` is a validation error, not a silent pick. The result: **no more "the
image happened to have Go" surprises**, and the warm pool stays small because toolchains attach
per-Run rather than needing a warm pod per skill combination.

## Inline or Git-sourced

A skill's definition can live **inline** in the CRD, or be **loaded from a Git repo**:

```yaml
spec:
  source:
    git:
      repoRef: github.com/acme/squad-skills
      ref: 3f2a9c1                 # PINNED to a commit SHA, never a floating branch
      path: skills/pg-migrate
      credentialSecretRef: acme-skills-ro   # optional, for private repos
```

Git-sourced skills are **pinned to a commit SHA** so a repo force-push can't silently change in-flight
behavior — the same reproducibility discipline as pinned CLI versions. Always pin an immutable SHA,
never a floating branch.

## The trust boundary (important)

Git-sourced skill content is treated as **untrusted input**. A skill grants tools and permissions, so
if a repo could self-declare its own capability envelope, a malicious repo would be a privilege
escalation. KSquad prevents this:

> **The `permissions` and `mcpToolRefs` capability envelope is authorized by the `Skill` CRD — the
> operator/admin who registers the source — never by the fetched repo content.** The repo supplies
> *behavior* (prompts, instructions, scripts) inside that envelope; it can never widen it.

The same one-way rule governs MCP tools: a skill selecting an
[MCPServer](./mcp-servers) via `mcpToolRefs` may only **narrow** the server's `toolFilter` —
intersect it, subtract from it — never widen it. At Run assembly the effective tool set is computed
server-side (`server.allow ∩ skill narrowing − deny`) and a narrowing that references a tool the
server has never observed, or that leaves the effective set empty, **fails Run admission closed**.

Fetched content is validated before staging, runs inside the same sandbox isolation and egress policy
as any Run, and private sources use a **BYO read-only Secret** — never a shared KSquad token.

## Skills are data

Like roles, the `Skill` reconciler validates a skill but doesn't execute it. A skill only takes effect
when an agent uses it in a Run.

## The predefined catalog — you don't start from an empty cluster

You don't have to author every skill yourself. K8squad ships a **canonical catalog of predefined
Skills**, a **curated default toolchain set**, and a **ready-to-run BMAD squad** — so a fresh cluster
comes with capabilities and a team already wired together. Each pillar has its own detail page:

<div class="ksq-cards">
  <a class="ksq-card" href="./skills-catalog"><span class="ksq-card__title">Predefined skills catalog</span><span class="ksq-card__desc">15 ready-made Skills in K8squad/k8squad-skills — 5 default + 10 dev/debug — versioned, SHA-pinned, apply with one kubectl command.</span></a>
  <a class="ksq-card" href="./toolchains"><span class="ksq-card__title">Predefined tooling</span><span class="ksq-card__desc">The curated default Toolchain catalog (gh, kubectl, go, node, dtctl, helm, docker-cli …) and how to build your own one-tool image.</span></a>
  <a class="ksq-card" href="./bmad-squad"><span class="ksq-card__title">Predefined BMAD squad</span><span class="ksq-card__desc">A 13-role CEO → PM / Architect / UX team, pre-wired to the default skills, as a single kubectl apply-able bundle.</span></a>
</div>

Each predefined skill lives in its own `skills/<name>/` directory in
**[`K8squad/k8squad-skills`](https://github.com/K8squad/k8squad-skills)** (a pinned `skill.yaml` CR plus
a `README.md`), so the whole set is versioned and reusable across squads. Add it all with Kustomize —
no clone needed:

```bash
# Add every predefined Skill (targets the bmad-squad namespace by default)
kubectl apply -k github.com/K8squad/k8squad-skills
```

> Skills require the K8squad CRDs to be installed first (`helm install ksquad ksquad/k8squad …`).
> See the **[predefined skills catalog](./skills-catalog)** for every skill and its permissions.

## Related

- [Agents](./agents) — reference skills via `skillRefs`.
- [Roles](./roles) — `defaultSkills` grant skills by default.
- [MCP Servers](./mcp-servers) — what `mcpToolRefs` resolves against; skills only narrow.
- [Toolchains](./toolchains) — what `requires.toolchains` resolves against.
- [Runs](./runs) — how skill requirements assemble a sandbox.
