---
title: Roles (Role)
description: A Role is a reusable behavior profile — the prompt and default skills that define how an agent thinks and acts — kept separate from which runtime executes it.
sidebar_position: 3
---

# Roles

**CRD:** `Role` (`ksquad.io/v1alpha1`)

A **Role** is a reusable **behavior profile**: it defines *how* an agent thinks and acts, independent
of *which* runtime executes it. Roles let you standardize behavior across a squad — a
`software-engineer`, a `code-reviewer`, a `docs-writer` — and reuse those profiles across many agents.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Role
metadata:
  name: code-reviewer
  namespace: ksquad-system
spec:
  promptRef: prompts/code-reviewer          # the behavior prompt
  defaultSkills: [git, read-only-fs]        # skills applied unless the Agent overrides
  runtimeClassHint: gvisor                   # a hint for sandbox isolation selection
```

## What a Role carries

- **`promptRef`** — the behavior prompt that shapes how the agent works (its instructions, review
  standards, coding conventions, and so on).
- **`defaultSkills`** — skills automatically granted to any agent using this role, unless the agent
  narrows or overrides them.
- **`runtimeClassHint`** — a hint the operator uses when selecting sandbox isolation for the Run.

## Behavior is decoupled from runtime

A crucial separation: a `Role` describes **behavior**, while an [`AgentRuntime`](./agents#agentruntime--the-pluggable-coding-agent-flavor)
describes **which coding CLI runs**. Earlier designs conflated the two ("the reviewer image"); KSquad
keeps them apart so you can:

- run the *same* `code-reviewer` role on different runtimes;
- upgrade a runtime CLI without touching behavior;
- reason about behavior and execution independently.

## Roles are data

The `Role` reconciler **validates** a role but doesn't run anything by itself — a role only comes to
life when an `Agent` references it and a `Run` executes that agent. This makes roles safe to author,
review, and share as versioned building blocks.

## Related

- [Agents](./agents) — reference a role via `roleRef`.
- [Skills](./skills) — what `defaultSkills` grant.
- [Author Guide → Compose CRDs](../author-guide/compose-crds) — authoring reusable roles.
