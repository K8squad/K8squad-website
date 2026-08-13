---
title: Skills (Skill)
description: A Skill is a granted capability — the tools, permissions, toolchains, and sidecars an agent may use. Skills can be defined inline or loaded from a pinned Git commit.
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

- **`mcpToolRefs`** — the MCP tools the skill exposes to the agent.
- **`permissions`** — the permission envelope (for example, workspace write vs. read-only).
- **`requires.toolchains`** — language/CLI packs (`go@1.23`, `node@22`, `python@3.13`, …). At Run time
  the operator stages each required pack as an **init container** into a shared volume — languages are
  *files*, so they cost nothing once the Run is running.
- **`requires.sidecars`** — genuine long-running services (rootless `dockerd`, a headless browser, an
  ephemeral DB). These become **sidecar** containers, and they're **capability-gated**: a sidecar whose
  capability the agent's runtime disables is rejected.

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
behavior — the same reproducibility discipline as pinned CLI versions.

## The trust boundary (important)

Git-sourced skill content is treated as **untrusted input**. A skill grants tools and permissions, so
if a repo could self-declare its own capability envelope, a malicious repo would be a privilege
escalation. KSquad prevents this:

> **The `permissions` and `mcpToolRefs` capability envelope is authorized by the `Skill` CRD — the
> operator/admin who registers the source — never by the fetched repo content.** The repo supplies
> *behavior* (prompts, instructions, scripts) inside that envelope; it can never widen it.

Fetched content is validated before staging, runs inside the same sandbox isolation and egress policy
as any Run, and private sources use a **BYO read-only Secret** — never a shared KSquad token.

## Skills are data

Like roles, the `Skill` reconciler validates a skill but doesn't execute it. A skill only takes effect
when an agent uses it in a Run.

## Related

- [Agents](./agents) — reference skills via `skillRefs`.
- [Roles](./roles) — `defaultSkills` grant skills by default.
- [Runs](./runs) — how skill requirements assemble a sandbox.
