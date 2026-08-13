---
title: Compose CRDs
description: Author KSquad building blocks — Roles, Skills, Agents, Teams, Projects, and Runs — with a worked end-to-end example and composition patterns.
sidebar_position: 1
---

# Compose CRDs

This page walks through composing a squad from the reusable pieces up, with a complete worked example.
For field-by-field detail on any object, see the [Core Concepts](../concepts) pages and the
[API Reference](../api-reference).

## 1. Author a Role

A [Role](../concepts/roles) is a reusable behavior profile — keep it about *behavior*, not runtime.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Role
metadata: { name: backend-engineer, namespace: ksquad-system }
spec:
  promptRef: prompts/backend-engineer
  defaultSkills: [git, run-tests]
  runtimeClassHint: gvisor
```

**Pattern:** author a small set of roles that match how your team actually divides work
(`backend-engineer`, `code-reviewer`, `docs-writer`) and reuse them across agents and squads.

## 2. Author Skills

A [Skill](../concepts/skills) grants capability and declares its own requirements.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Skill
metadata: { name: run-tests, namespace: ksquad-system }
spec:
  source: inline
  mcpToolRefs: [shell, file-read, file-write]
  permissions: [workspace-write]
  requires:
    toolchains: [go@1.23]
```

**Pattern — least privilege.** Grant the narrowest permission that gets the job done. A reviewer that
only needs to read gets a read-only skill; only give `workspace-write` where writing is the point.

**Pattern — Git-sourced skills for sharing.** Keep reusable skills in a repo and pin them by commit
SHA. Remember the trust boundary: the repo supplies *behavior*, but the **capability envelope is
authorized by the CRD**, never widened by repo content.

## 3. Author Agents

An [Agent](../concepts/agents) combines runtime + role + skills + credential.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata: { name: dev-1, namespace: ksquad-system }
spec:
  runtimeRef: claude-code
  roleRef: backend-engineer
  skillRefs: [git, run-tests]
  credentialSecretRef: claude-oauth
  model: claude-opus-4-8
  fallbackModel: claude-sonnet-5   # optional — keep working through rate limits
```

**Pattern — one credential, many agents.** Multiple agents can reference the same per-user Secret;
concurrent Runs on one subscription work (the credential controller keeps the token fresh).

## 4. Author a Project

A [Project](../concepts/projects) is the repo + workspace.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Project
metadata: { name: payments-api, namespace: ksquad-system }
spec:
  repo:
    url: https://github.com/acme/payments-api.git
    ref: main
    sync: { provider: github, webhookSecretRef: payments-webhook, reflectOutbound: true }
  workspacePVC: { size: 20Gi, storageClassName: fast-ssd }
  goals: "Ship the open backlog; keep CI green."
```

**Pattern — write clear goals.** `spec.goals` is folded into agent context. A specific, testable goal
("keep CI green; no breaking API changes without an ADR") produces better work than a vague one.

## 5. Form a Team (Squad)

A [Team](../concepts/squads) groups agents and projects into a squad.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Team
metadata: { name: payments-squad, namespace: ksquad-system }
spec:
  projects: [payments-api]
  agents: [dev-1, dev-2, reviewer-1]
```

The operator reconciles the squad's namespace, RBAC, NetworkPolicy, and quota.

## 6. Start a Run

A [Run](../concepts/runs) is a unit of work.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Run
metadata: { name: backlog-sweep-1, namespace: ksquad-system }
spec:
  teamRef: payments-squad
  projectRef: payments-api
  agents: [dev-1]
  inputs:
    task: "Pick up the next ready issue and open a PR."
  retryPolicy: { maxRetries: 2 }
```

Apply it and watch progress stream in the console, or:

```bash
kubectl apply -f run.yaml
kubectl get run backlog-sweep-1 -n ksquad-system -w
```

## Validation and failing closed

KSquad validates as you compose and **fails closed**:

- an `Agent` whose credential Secret can't be resolved is **rejected**, not silently broken;
- two skills pinning conflicting toolchain versions (`go@1.22` vs `go@1.23`) is a **validation error**;
- a capability a runtime disables (e.g. real Docker on a gVisor-only runtime with no supported
  mechanism) is **rejected**.

So a squad that admits is a squad that can actually run.

## GitOps

Because every object is a CRD, you can keep your whole squad definition in Git and apply it with your
existing GitOps tooling. Pin runtime CLI versions and Git-sourced skills by SHA for fully reproducible
squads.
