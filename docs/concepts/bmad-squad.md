---
title: Predefined BMAD squad
description: A ready-to-run 13-role team in a proven CEO → PM / Architect / UX hierarchy, pre-wired with the default skills, shipped as a single kubectl apply-able bundle in examples/bmad-team/.
sidebar_position: 6
---

# Predefined BMAD squad

To go from an empty cluster to a working team without hand-authoring a dozen roles, K8squad ships a
**predefined BMAD squad** — 13 roles in a proven CEO → PM / Architect / UX hierarchy, pre-wired with
the [default skills](/docs/concepts/skills-catalog/#default-skills) — as a single `kubectl apply`-able bundle in
[`examples/bmad-team/`](https://github.com/K8squad/K8squad/tree/main/examples/bmad-team).

## The org chart

**CEO** owns the outcome; three leads report in, each with their own team.

<div class="ksq-cards">
  <div class="ksq-card"><span class="ksq-card__title">CEO</span><span class="ksq-card__desc">Owns the outcome at the top of the squad.</span></div>
</div>

<div class="ksq-cards">
  <div class="ksq-card"><span class="ksq-card__title">Product Manager</span><span class="ksq-card__desc">Leads product. Team: Brainstormer, Challenger, Content Writer.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">Architect</span><span class="ksq-card__desc">Leads engineering. Team: Code Reviewer, Test Architect, Coder, DevOps Engineer, Observability Engineer.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">UX Designer</span><span class="ksq-card__desc">Leads design. Team: Graphical Designer.</span></div>
</div>

<div class="ksq-cards">
  <div class="ksq-card"><span class="ksq-card__title">Brainstormer</span><span class="ksq-card__desc">Under PM — idea generation.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">Challenger</span><span class="ksq-card__desc">Under PM — adversarial review of proposals.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">Content Writer</span><span class="ksq-card__desc">Under PM — docs and written deliverables.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">Code Reviewer</span><span class="ksq-card__desc">Under Architect — reviews diffs.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">Test Architect</span><span class="ksq-card__desc">Under Architect — test strategy and coverage.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">Coder</span><span class="ksq-card__desc">Under Architect — implementation.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">DevOps Engineer</span><span class="ksq-card__desc">Under Architect — CI/CD and infrastructure.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">Observability Engineer</span><span class="ksq-card__desc">Under Architect — telemetry and SLOs.</span></div>
  <div class="ksq-card"><span class="ksq-card__title">Graphical Designer</span><span class="ksq-card__desc">Under UX — diagrams and visual assets.</span></div>
</div>

## Install it

```bash
# 1. Install the operator (once per cluster)
helm repo add ksquad https://charts.k8squad.io
helm install ksquad ksquad/k8squad --namespace k8squad-system --create-namespace

# 2. Apply the BMAD squad — Team, Roles, Agents, Project + the default Skills
kubectl apply -f https://raw.githubusercontent.com/K8squad/K8squad/main/examples/bmad-team/

# 3. Drop in your model token
kubectl -n bmad-squad edit secret model-credentials   # replace REPLACE_ME
```

Everything lands in a dedicated **`bmad-squad`** namespace.

## Wiring skills to roles and agents

Skills attach at two levels — grant broad-value skills as **role defaults**
(`Role.spec.defaultSkills`) and specialist ones **per agent** (`Agent.spec.skillRefs`, which override
the role's defaults):

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

- [Predefined skills catalog](/docs/concepts/skills-catalog/) — the skills the squad is wired to.
- [Roles](/docs/concepts/roles/) — `defaultSkills` grant skills by default.
- [Agents](/docs/concepts/agents/) — `skillRefs` grant skills per agent.
