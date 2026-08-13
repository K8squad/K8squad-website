---
title: Author Guide
description: Compose squads and manage work — author CRDs (Roles, Skills, Agents, Teams, Projects, Runs) and drive the durable coordination record.
sidebar_position: 4
---

# Author Guide

This guide is for the **squad author** — the person who composes agents, roles, skills, and squads, and
drives work through them. Where the [Operator Guide](../operator-guide) is about running the platform,
this guide is about *using* it to get work done.

You'll compose everything as CRDs (from the console or with `kubectl`) and manage work through the
durable coordination record.

## In this guide

| Page | What it covers |
|------|----------------|
| [Compose CRDs](./compose-crds) | Authoring Roles, Skills, Agents, Teams, Projects, and Runs — the composition order and good patterns |
| [Managing work items](./work-items) | The coordination record — creating, claiming, commenting, artifacts, and approvals |

## The composition order

Build from the reusable pieces up:

1. **Roles** — behavior profiles you'll reuse across agents.
2. **Skills** — capabilities (tools, permissions, toolchains) agents can be granted.
3. **Agents** — combine a runtime + role + skills + credential.
4. **Project** — the repo + workspace to work against.
5. **Team (Squad)** — group agents and projects.
6. **Run** — start work.

You don't have to author everything from scratch — KSquad ships starter runtimes, roles, and skills.
Compose on top of them.

## Console or YAML — your choice

Every concept can be authored two ways:

- **In the console** — guided forms with validation, ideal for exploring and for people who don't live
  in `kubectl`.
- **As YAML** — `kubectl apply`, ideal for GitOps and reproducible squad definitions.

Both go through the same validation and the same apiserver, so they're interchangeable. Many teams
prototype in the console and then export to YAML for version control.
