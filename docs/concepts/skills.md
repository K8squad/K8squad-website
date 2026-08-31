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
Skills** in the dedicated repo
**[`K8squad/k8squad-skills`](https://github.com/K8squad/k8squad-skills)**. Each skill lives in its own
`skills/<name>/` directory (a pinned `skill.yaml` CR plus a `README.md` documenting its purpose,
permissions, and role wiring), so the whole set is versioned, SHA-pinned, and reusable across squads.
Apply the catalog with Kustomize straight from the repo — no clone needed:

```bash
# Add every predefined Skill (targets the bmad-squad namespace by default)
kubectl apply -k github.com/K8squad/k8squad-skills

# …or add a single skill
kubectl apply -f https://raw.githubusercontent.com/K8squad/k8squad-skills/main/skills/kubectl-debug/skill.yaml
```

> Skills require the K8squad CRDs to be installed first (`helm install ksquad ksquad/k8squad …`).

### Default skills

These are the broadly useful capabilities most squads want out of the box. The [predefined BMAD
squad](#the-predefined-bmad-squad) ships the first four wired to roles for you.

| Skill | What it grants |
|-------|----------------|
| [`bmad`](https://github.com/K8squad/k8squad-skills/tree/main/skills/bmad) | The shared BMAD phased-workflow method (inline) — granted to every role. |
| [`github`](https://github.com/K8squad/k8squad-skills/tree/main/skills/github) | Remote git / PR / issue operations via the GitHub CLI (`gh`). |
| [`dynatrace`](https://github.com/K8squad/k8squad-skills/tree/main/skills/dynatrace) | Dynatrace control-plane (`dtctl`) for observability queries and dashboards. |
| [`dt-dql-essentials`](https://github.com/K8squad/k8squad-skills/tree/main/skills/dt-dql-essentials) | DQL syntax, pitfalls, and query optimization for observability work. |
| [`graphical`](https://github.com/K8squad/k8squad-skills/tree/main/skills/graphical) | Diagram / SVG asset rendering. |

### Dev / debug skills

Layer these on for hands-on engineering. Every introspection skill is **least-privilege** —
`kubectl-debug`, `otel-observability-query`, and `psql-inspect` carry **no write / apply / delete**
verbs.

| Skill | What it grants |
|-------|----------------|
| [`code-search`](https://github.com/K8squad/k8squad-skills/tree/main/skills/code-search) | Semantic + structural (AST) code navigation. |
| [`kubectl-debug`](https://github.com/K8squad/k8squad-skills/tree/main/skills/kubectl-debug) | Read-only cluster introspection + ephemeral debug containers. |
| [`go-build-test`](https://github.com/K8squad/k8squad-skills/tree/main/skills/go-build-test) | `go build` / `vet` / `test` (`-run`, `-race`) with a dockerd sidecar. |
| [`git-workflow`](https://github.com/K8squad/k8squad-skills/tree/main/skills/git-workflow) | Local git operations, including `git bisect`. |
| [`golangci-lint`](https://github.com/K8squad/k8squad-skills/tree/main/skills/golangci-lint) | Run the repo's lint gate locally. |
| [`otel-observability-query`](https://github.com/K8squad/k8squad-skills/tree/main/skills/otel-observability-query) | Read-only trace / log / span query (Dynatrace DQL). |
| [`container-build`](https://github.com/K8squad/k8squad-skills/tree/main/skills/container-build) | docker / buildkit build / run / inspect. |
| [`delve-pprof`](https://github.com/K8squad/k8squad-skills/tree/main/skills/delve-pprof) | Live-process debugging (`dlv`) + profiling (`pprof`). |
| [`psql-inspect`](https://github.com/K8squad/k8squad-skills/tree/main/skills/psql-inspect) | Read-only `psql` into the coordination / run-source DB. |
| [`http-grpc-probe`](https://github.com/K8squad/k8squad-skills/tree/main/skills/http-grpc-probe) _(optional)_ | `curl` / `grpcurl` probing of live endpoints. |

See the [catalog README](https://github.com/K8squad/k8squad-skills#readme) for each skill's exact
permissions and the recommended role → skill matrix.

### Predefined tooling

Most catalog skills grant their capability through a **[Toolchain](./toolchains)** — a versioned,
digest-pinned CLI pack (`gh`, `kubectl`, `go`, `node`, `dtctl`, `helm`, `docker-cli`, …) staged as an
init container at Run time. K8squad ships a **curated default catalog** of these toolchains, enabled
with one Helm flag:

```bash
helm install ksquad ksquad/k8squad --set tools.defaultCatalog.enabled=true …
```

The predefined Skills pin against this catalog, so `github` gets a tested `gh`, `go-build-test` gets a
tested `go`, and version conflicts across a Run's skills **fail closed** rather than silently picking a
"latest". Long-tail binaries a skill needs (`ripgrep`, `ast-grep`, `delve`, `grpcurl`, …) are supplied
by team-namespace Toolchains you define. See [Toolchains](./toolchains) for the full curated set.

## The predefined BMAD squad

To go from an empty cluster to a working team without hand-authoring a dozen roles, K8squad ships a
**predefined BMAD squad** — 13 roles in a proven CEO → PM / Architect / UX hierarchy, pre-wired with
the default Skills above — as a single `kubectl apply`-able bundle in
[`examples/bmad-team/`](https://github.com/K8squad/K8squad/tree/main/examples/bmad-team).

- **CEO** at the top, owning the outcome.
- **Product Manager**, **Architect**, and **UX Designer** reporting to the CEO.
- Under the PM: **Brainstormer**, **Challenger**, **Content Writer**.
- Under the Architect: **Code Reviewer**, **Test Architect**, **Coder**, **DevOps Engineer**,
  **Observability Engineer**.
- Under the UX Designer: **Graphical Designer**.

```bash
# 1. Install the operator (once per cluster)
helm repo add ksquad https://charts.k8squad.io
helm install ksquad ksquad/k8squad --namespace k8squad-system --create-namespace

# 2. Apply the BMAD squad — Team, Roles, Agents, Project + the default Skills
kubectl apply -f https://raw.githubusercontent.com/K8squad/K8squad/main/examples/bmad-team/

# 3. Drop in your model token
kubectl -n bmad-squad edit secret model-credentials   # replace REPLACE_ME
```

Everything lands in a dedicated **`bmad-squad`** namespace. Skills attach at two levels — grant
broad-value skills as **role defaults** (`Role.spec.defaultSkills`) and specialist ones **per agent**
(`Agent.spec.skillRefs`, which override the role's defaults):

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

## Related

- [Agents](./agents) — reference skills via `skillRefs`.
- [Roles](./roles) — `defaultSkills` grant skills by default.
- [MCP Servers](./mcp-servers) — what `mcpToolRefs` resolves against; skills only narrow.
- [Toolchains](./toolchains) — what `requires.toolchains` resolves against.
- [Runs](./runs) — how skill requirements assemble a sandbox.
