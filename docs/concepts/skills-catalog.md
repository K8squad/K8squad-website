---
title: Predefined skills catalog
description: The skills K8squad ships out of the box — a versioned, SHA-pinned catalog in K8squad/k8squad-skills, split into broadly-useful default skills and hands-on dev/debug skills. Each card links to that skill's own detail page.
sidebar_position: 5
---

# Predefined skills catalog

K8squad publishes a catalog of ready-made **[Skills](/docs/concepts/skills/)** in the dedicated repo
**[`K8squad/k8squad-skills`](https://github.com/K8squad/k8squad-skills)**. Each skill lives in its own
`skills/<name>/` directory — a pinned `skill.yaml` CR plus a `README.md` documenting its purpose,
permissions, and role wiring — so the whole set is versioned, SHA-pinned, and reusable across squads.
**Every card below links to that skill's own detail page** in the catalog.

Apply the catalog with Kustomize straight from the repo — no clone needed:

```bash
# Add every predefined Skill (targets the bmad-squad namespace by default)
kubectl apply -k github.com/K8squad/k8squad-skills

# …or add a single skill
kubectl apply -f https://raw.githubusercontent.com/K8squad/k8squad-skills/main/skills/kubectl-debug/skill.yaml
```

> Skills require the K8squad CRDs to be installed first (`helm install ksquad ksquad/k8squad …`).

## Default skills

The broadly useful capabilities most squads want out of the box. The
[predefined BMAD squad](/docs/concepts/bmad-squad/) ships the first four wired to roles for you.

<div class="ksq-cards">
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/bmad"><span class="ksq-card__title"><code>bmad</code></span><span class="ksq-card__desc">The shared BMAD phased-workflow method (inline) — granted to every role.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/github"><span class="ksq-card__title"><code>github</code></span><span class="ksq-card__desc">Remote git / PR / issue operations via the GitHub CLI (gh).</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/dynatrace"><span class="ksq-card__title"><code>dynatrace</code></span><span class="ksq-card__desc">Dynatrace control-plane (dtctl) for observability queries and dashboards.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/dt-dql-essentials"><span class="ksq-card__title"><code>dt-dql-essentials</code></span><span class="ksq-card__desc">DQL syntax, pitfalls, and query optimization for observability work.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/graphical"><span class="ksq-card__title"><code>graphical</code></span><span class="ksq-card__desc">Diagram / SVG asset rendering.</span></a>
</div>

## Dev / debug skills

Layer these on for hands-on engineering. Every introspection skill is **least-privilege** —
`kubectl-debug`, `otel-observability-query`, and `psql-inspect` carry **no write / apply / delete**
verbs.

<div class="ksq-cards">
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/code-search"><span class="ksq-card__title"><code>code-search</code></span><span class="ksq-card__desc">Semantic + structural (AST) code navigation.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/kubectl-debug"><span class="ksq-card__title"><code>kubectl-debug</code></span><span class="ksq-card__desc">Read-only cluster introspection + ephemeral debug containers.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/go-build-test"><span class="ksq-card__title"><code>go-build-test</code></span><span class="ksq-card__desc">go build / vet / test (-run, -race) with a dockerd sidecar.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/git-workflow"><span class="ksq-card__title"><code>git-workflow</code></span><span class="ksq-card__desc">Local git operations, including git bisect.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/golangci-lint"><span class="ksq-card__title"><code>golangci-lint</code></span><span class="ksq-card__desc">Run the repo's lint gate locally.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/otel-observability-query"><span class="ksq-card__title"><code>otel-observability-query</code></span><span class="ksq-card__desc">Read-only trace / log / span query (Dynatrace DQL).</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/container-build"><span class="ksq-card__title"><code>container-build</code></span><span class="ksq-card__desc">docker / buildkit build / run / inspect.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/delve-pprof"><span class="ksq-card__title"><code>delve-pprof</code></span><span class="ksq-card__desc">Live-process debugging (dlv) + profiling (pprof).</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/psql-inspect"><span class="ksq-card__title"><code>psql-inspect</code></span><span class="ksq-card__desc">Read-only psql into the coordination / run-source DB.</span></a>
  <a class="ksq-card" href="https://github.com/K8squad/k8squad-skills/tree/main/skills/http-grpc-probe"><span class="ksq-card__title"><code>http-grpc-probe</code> <em>(optional)</em></span><span class="ksq-card__desc">curl / grpcurl probing of live endpoints.</span></a>
</div>

See the [catalog README](https://github.com/K8squad/k8squad-skills#readme) for each skill's exact
permissions and the recommended role → skill matrix.

## Related

- [Skills](/docs/concepts/skills/) — the `Skill` CRD these entries are instances of.
- [Toolchains](/docs/concepts/toolchains/) — the tooling most catalog skills grant, and how to build your own.
- [Predefined BMAD squad](/docs/concepts/bmad-squad/) — a ready-made team wired to these skills.
