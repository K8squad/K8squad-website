---
title: The pre-defined BMAD squad
description: A ready-to-run team of 13 BMAD roles and a catalog of Skills — apply one bundle and go from an empty cluster to a working AI squad.
sidebar_position: 2
---

# Onboard in minutes with the pre-defined BMAD squad

Standing up an AI engineering team used to mean hand-authoring a dozen roles,
wiring skills, and hoping every reference resolved. KSquad now ships a
**pre-defined BMAD squad** — 13 roles in a proven CEO → PM / Architect / UX
hierarchy, pre-wired with four default [Skills](./concepts/skills) — as a single
`kubectl apply`-able bundle. Install the operator, apply the squad, drop in your
model token, and you have a working team.

## What's in the box

A complete squad that models the **BMAD** flow:

- **CEO** at the top, arbitrating and owning the outcome.
- **Product Manager**, **Architect**, and **UX Designer** reporting to the CEO.
- Under the PM: **Brainstormer**, **Challenger**, **Content Writer**.
- Under the Architect: **Code Reviewer**, **Test Architect**, **Coder**,
  **DevOps Engineer**, **Observability Engineer**.
- Under the UX Designer: **Graphical Designer**.

Thirteen roles, one flat `Team`, with the reporting hierarchy encoded in each
role's prompt.

## Three commands to a running squad

```bash
# 1. Install the operator (once per cluster)
helm repo add ksquad https://charts.k8squad.io
helm install ksquad ksquad/k8squad --namespace k8squad-system --create-namespace

# 2. Apply the BMAD squad — Team, Roles, Agents, Project + the 4 default Skills
kubectl apply -f examples/bmad-team/

# 3. Add your model token
kubectl -n bmad-squad edit secret model-credentials   # replace REPLACE_ME
```

Everything lands in a dedicated **`bmad-squad`** namespace. Open the console,
create a Run, and watch the CEO fan work out through the hierarchy — the PM
scopes it, the Architect sequences it, the Coder and reviewers execute —
streaming live. The full walkthrough (prerequisites, verification, first Run,
troubleshooting) is in the in-repo
[Getting Started guide](https://github.com/K8squad/K8squad/blob/main/docs/getting-started-bmad.md).

## Default Skills

A [`Skill`](./concepts/skills) is KSquad's **CRD-authorized capability envelope**
— it grants an agent a specific tool or capability, least-privilege, and is never
self-widened by a fetched skill body. The pre-defined Skills are sourced from the
canonical catalog repo
**[`K8squad/k8squad-skills`](https://github.com/K8squad/k8squad-skills)**, so they
can be versioned, pinned, and reused across squads.

The **four defaults** ship inline with the `examples/bmad-team/` bundle (you get
them from step 2 above). A broader **dev/debug set** lives in the same catalog and
is opt-in.

### The four defaults

| Skill | What it does | Attached to |
|-------|--------------|-------------|
| [**`bmad`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/bmad) | The shared BMAD phased-workflow method (inline). | Every role |
| [**`github`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/github) | Remote git / PR / issue ops via the GitHub MCP. | Coder, DevOps Engineer, Code Reviewer |
| [**`dynatrace`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/dynatrace) | Dynatrace control-plane (`dtctl`) for observability queries and dashboards. | Observability Engineer |
| [**`graphical`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/graphical) | Diagram / SVG asset rendering. | Graphical Designer |

### The dev / debug set

Layer these on for hands-on engineering work. All read/introspection skills are
least-privilege — `kubectl-debug`, `otel-observability-query`, and `psql-inspect`
carry **no write/apply/delete** verbs.

| Skill | What it does |
|-------|--------------|
| [**`code-search`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/code-search) | Semantic + structural (AST) code navigation. |
| [**`kubectl-debug`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/kubectl-debug) | Read-only cluster introspection + ephemeral debug containers. |
| [**`go-build-test`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/go-build-test) | `go build` / `vet` / `test` (`-run`, `-race`) with a dockerd sidecar. |
| [**`git-workflow`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/git-workflow) | Local git operations, including `git bisect`. |
| [**`golangci-lint`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/golangci-lint) | Run the repo's lint gate locally. |
| [**`otel-observability-query`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/otel-observability-query) | Read-only trace / log / span query (Dynatrace DQL). |
| [**`container-build`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/container-build) | docker / buildkit build / run / inspect. |
| [**`delve-pprof`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/delve-pprof) | Live-process debugging (`dlv`) + profiling (`pprof`). |
| [**`psql-inspect`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/psql-inspect) | Read-only `psql` into the coordination / run-source DB. |
| [**`http-grpc-probe`**](https://github.com/K8squad/k8squad-skills/tree/main/skills/http-grpc-probe) _(optional)_ | `curl` / `grpcurl` probing of live endpoints. |

### Install the catalog

The four defaults are already present after applying the squad. To add the
dev/debug set, apply the whole catalog with Kustomize — it targets the
`bmad-squad` namespace and re-declares the same four defaults idempotently:

```bash
git clone https://github.com/K8squad/k8squad-skills.git
kubectl apply -k k8squad-skills/
```

Or apply a single skill:

```bash
kubectl apply -f k8squad-skills/skills/kubectl-debug/skill.yaml
```

> Skills require the KSquad CRDs to be installed first (the Helm step above).

### Wire a Skill to a role or an agent

Skills attach at two levels — grant broad-value skills as **role defaults**, and
specialist ones **per agent**. An agent's `skillRefs` override its role's
`defaultSkills`.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Role
metadata: { name: coder, namespace: bmad-squad }
spec:
  defaultSkills:            # granted to every agent assuming this role
    - name: code-search
    - name: go-build-test
    - name: git-workflow
---
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata: { name: coder-01, namespace: bmad-squad }
spec:
  skillRefs:                # granted to this one agent
    - name: delve-pprof
```

See the [catalog README](https://github.com/K8squad/k8squad-skills#readme) for
each skill's permissions and the recommended role → skill matrix.

Bring your own model token; KSquad brings the team.
