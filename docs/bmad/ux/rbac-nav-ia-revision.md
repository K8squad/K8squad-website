---
title: Console-user RBAC & navigation IA revision — KSquad operator console
author: System Architect (Winston)
date: 2026-08-12
status: proposed — pending CEO/PM scope confirmation
source_ticket: ISI-2307
supersedes_reference: memory/ksquad-nav-ia-revision.md  # referenced by ISI-2307 but absent from repo/mempalace; this doc recreates it
feeds: UX mocks (screens 15–18) · Architecture §12 (tenancy) / §13 (console) · Epics (console auth story)
inputs:
  - docs/bmad/03-architecture.md   # §12 tenancy (Team=namespace, RBAC/NetworkPolicy), §13 console screens, §11 credential model
  - docs/bmad/02-prd.md            # §5 personas (Priya/David), §9.6 FR-F console, D2 least-privilege, NFR-SEC1
non_blocking: false                # introduces new product scope (console auth + human RBAC) not yet in PRD/arch — see §6
---

# Console-user RBAC & Navigation IA Revision

> **Why this doc exists.** ISI-2307 asks for console mocks that assume a **human-user RBAC layer**
> — a login screen, an admin-only *Users & Roles* screen, an *admin vs non-admin* adaptive nav,
> and a project selector that shows *only authorized projects*. **None of that exists in the current
> PRD or architecture.** In the architecture today, `Role` is an **agent behavior profile** (§5.1 CRD)
> and "RBAC" means **Kubernetes tenancy** (§12.1 `Team`→namespace + RBAC/NetworkPolicy). There is no
> concept of a *console user*, no login, no per-human access role. ISI-2307 referenced
> `memory/ksquad-nav-ia-revision.md` for the "updated IA" — that file is absent from the repo and
> mempalace. This document **recreates the missing IA** and defines the model the mocks realize, so
> the mocks are grounded in a coherent architecture rather than invented per-screen. **The model
> below is a proposal pending CEO/PM confirmation (see §6).**

## 1. Model at a glance

Two orthogonal, additive concepts on top of the existing cluster:

1. **Authentication** — *who is this human?* → **OIDC / SSO** (boring, standard for K8s operator
   consoles). No local password store; the console BFF trusts an OIDC IdP and never holds a
   long-lived human secret. Consistent with §11's "console never stores raw credentials" ethos.
2. **Authorization** — *what may this human see/do?* → a small set of **console access roles** plus
   **per-user project membership**, both derived from OIDC group claims and mapped onto the
   **Kubernetes RBAC that already governs the cluster** (D2 least-privilege, NFR-SEC1). The console
   *reflects* existing RBAC; it introduces **no new isolation mechanism**.

> **Naming discipline.** "Console access role" is **not** the `Role` CRD. To avoid the collision,
> the UI labels this axis **"Access level"** (Admin / Operator / Viewer), never bare "Role". The
> `Role` CRD (Reviewer/Fixer/Tester behavior profiles) keeps its meaning everywhere else.

## 2. Console access roles (3 — minimal)

| Access level | Persona | Projects | Fleet Dashboard | Compose/mutate | Settings | Users & Roles |
|---|---|---|---|---|---|---|
| **Admin** | Priya (platform eng) | all | ✓ fleet-wide | ✓ | ✓ read/write | ✓ **manage** |
| **Operator** | David (squad operator) | **authorized only** | membership-scoped | ✓ within authorized projects | read-only | ✗ hidden |
| **Viewer** | stakeholder / auditor | **authorized only** | membership-scoped | ✗ read-only | read-only | ✗ hidden |

The ISI-2307 "admin vs non-admin" split = **Admin** vs **{Operator, Viewer}**. Only Admin sees
*Users & Roles*, the fleet-wide Dashboard, and every project.

## 3. Project membership → authorized-projects selector

A console user is **granted membership** to specific projects (an OIDC group → `Project`/`Team`
mapping). Consequences surfaced in the UI:

- **Project selector lists only authorized projects.** A non-admin never sees projects they cannot
  read. Admins see all projects with an "all" affordance.
- **Everything project-scoped (Build · Tickets · Runs · Discussion) is filtered to authorized
  `project_id`s** — the same `project_id` filter the CRD/BFF read model already applies (§13
  scoping rule), now additionally gated by the caller's membership. Fail-closed: unknown/unauthorized
  project → 404, mirroring the build-browser scoping precedent (ISI-2166, 404-not-403).

## 4. Adaptive navigation

Same locked visual system (dark #0B1220 + azure #3D7DFF; light mirror). The rail **adapts to access
level** — items the user cannot use are **removed, not disabled** (no dead affordances):

```
ADMIN rail                          NON-ADMIN rail (Operator/Viewer)
─────────────────────────           ─────────────────────────────────
GLOBAL                              GLOBAL
  Dashboard  (fleet-wide)            Overview     (own squads)
  Overview                           Agents       (authorized only)
  Agents                           PROJECT
PROJECT                              [selector — authorized projects only]
  [selector — all projects]           Build · Tickets · Runs · Discussion
  Build · Tickets · Runs · Disc.   SETTINGS
SETTINGS                             Configuration  (read-only)
  Configuration                      Credentials    (read-only, own)
  Credentials
  Users & Roles   ← admin only
```

- **Mobile** mirrors the same authorization: role-adaptive **bottom nav** (Admin gets a *Manage*/Users
  tab; non-admin does not) and the same **SSO login flow**.
- The account menu shows the current **access level badge** so the user always knows their scope.

## 5. Screens delivered (mocks, ISI-2307)

| # | Screen | Covers ISI-2307 item |
|---|---|---|
| **15** | **Users & Roles** (admin) — user list, access-level assignment, **project-membership matrix** | 1 |
| **16** | **Adaptive nav** — Admin vs non-admin rail side-by-side + authorized-projects selector | 2, 5 |
| **17** | **Login** (desktop) — SSO/OIDC sign-in | 3 |
| **18** | **Mobile** — SSO login flow + role-adaptive bottom nav | 4 |

## 6. Scope flag (read before building on this)

This introduces **new product scope**: console authentication and a human RBAC layer are **not** in
the current PRD (§9.6 FR-F is about console *function*, not *auth*) or architecture. The model here is
deliberately **thin and RBAC-reflecting** — it adds OIDC login + a group→access-role/membership mapping
and surfaces the K8s RBAC that already exists, rather than inventing a parallel authz system. Before
this graduates from mocks to committed architecture it needs:

- **CEO/PM confirmation** that console auth + human RBAC is in v1 scope, and the 3-role model is right.
- A PRD FR (console auth) + an **ADR** (OIDC + group→role/membership mapping; console reflects RBAC).
- An Epic/story handoff (console BFF authz middleware; IdP integration).

Until then these are **direction mocks**, consistent with the "delegated UX direction" posture of the
rest of the ISI-2150 set (README author = Graphic Designer; non-blocking to the CEO gate).
