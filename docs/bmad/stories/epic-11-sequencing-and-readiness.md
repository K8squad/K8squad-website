---
title: Epic 11 (Source-control sync, GitHub first) — sequencing & readiness assessment
owner: John (Product Manager)
issue: ISI-2183
date: 2026-08-17
stepsCompleted:
  - inventory-board-and-story-artifacts
  - dependency-order-11.1-through-11.6
  - readiness-gate-analysis
  - detailing-handoff-plan
---

# Epic 11 — Source-control sync (GitHub first): sequencing & readiness

**Epic:** ISI-2183 · **Wave:** 2 · **Objective:** sync SCM state *into* the platform
(issues ⇄ work items, PR status, CI results, build artifacts) behind a provider seam so the
console reflects reality without users leaving it.

## 1. Current artifact / board state (verified 2026-08-17)

| Story | Board ticket | Board status | Story spec file | Spec status |
|-------|--------------|--------------|-----------------|-------------|
| 11.1 Repo-sync reconciler | ISI-2254 | **blocked** (opaque: empty `blockedBy`, 0 comments) | `stories/11-1-repo-sync-reconciler.md` | **done** — spec + 14-mutation falsification model-check (C1–C6). Real Go build *explicitly deferred*. |
| 11.1 review | ISI-2484 | backlog | — | (review of 11.1 spec) |
| 11.2 issues ⇄ work items | ISI-2255 | backlog | `stories/11-2-issues-work-items-sync.md` | **detailed (ISI-2699)** — AC1–5 (mirror/provenance/field-ownership/echo-suppress/LWW+audit) + C1–C5 falsification contract. Go build deferred to build wave. |
| 11.3 PR status ↔ Run/branch | ISI-2256 | backlog | `stories/11-3-pr-status-run-branch.md` | **detailed (ISI-2699)** — AC1–4 (`scm_pr_mirror` + read-side `head_sha→run.commit_sha` correlation, no Run mutation) + C1–C4. Go build deferred. |
| 11.4 CI checks + artifacts → build browser | ISI-2257 | backlog | `stories/11-4-ci-checks-artifacts-build-browser.md` | **detailed (ISI-2699)** — AC1–4 (checks + artifact **references** not bytes, CI-not-a-gate, sha attribution) + C1–C4. Go build deferred. |
| 11.5 Provider seam explicit | ISI-2258 | backlog | `stories/11-5-provider-seam-explicit.md` | **detailed (ISI-2699, first)** — AC1–5 (one interface, differential neutrality, drop-in = impl+config, verify-before-parse) + C1–C5. Freezes 11.1's seam. Go build deferred. |
| 11.6 Console tiles + CI-failure auto-post | ISI-2259 | backlog | `stories/11-6-console-tiles-ci-failure-autopost.md` | **detailed (ISI-2699)** — AC1–4 (read-model tiles/no-rollup, provenance-tagged auto-post, observer-not-coordinator, idempotent+echo-safe) + C1–C4. Go build deferred. |

**Gap (a) CLOSED 2026-08-17 (ISI-2699):** 11.2–11.6 now have detailed story spec files (order
11.5 → 11.2 ∥ 11.3 → 11.4 → 11.6), each with AC + technical notes + implementation guidance + a
Cn↔ACn falsification-check contract in 11.1's model-check style. **Gap (b)** (11.1's opaque
`blocked`) remains PM/Architect's to make legible — untouched here.

## 2. Dependency order (intra-epic + upstream)

```
11.5 (provider seam)  ── formalizes the SourceControlProvider interface 11.1 already defines
        │                (near-zero net-new; pairs with / is satisfied-by-design in 11.1's spec)
        ▼
11.1 (reconciler foundation)  ── mirror schema + level-triggered upsert + HMAC webhook + poll
        ├──────────────┬───────────────┐
        ▼              ▼                │
11.2 (issues⇄items)  11.3 (PR↔Run)     │   11.2 needs Epic 2 work items; 11.3 needs Epic 3 Run
                       ▼                │
                     11.4 (CI + artifacts → build browser 8.7e)
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
11.6 (console tiles 8.8 + CI-failure auto-post → room 10.3)
```

**Detailing order for the Story Writer:** 11.5 → (11.2 ∥ 11.3) → 11.4 → 11.6.
All five can be *detailed now* against 11.1's completed spec (which defines the `pkg/scm` seam,
the `scm_pr_mirror` / mirror schema, provenance tagging, echo-suppression, and the
mirror-not-authority discipline). Detailing does **not** wait on the runtime gate below.

## 3. Readiness gates — why specs proceed but the *build* is parked

- **Detailing (spec authoring): READY NOW.** 11.1's spec is the contract; 11.2–11.6 are
  refinements of it. No upstream runtime is required to write acceptance criteria + technical
  notes. This mirrors how 11.1 itself was authored ahead of build.
- **Runtime build (real `pkg/scm` + GitHub v1 impl): GATED on platform substrate.** k8squad
  today ships **only the API-group scaffold** — there is no apiserver, no persisted coordination
  record, no live Epic 9 HTTPRoute ingress, no Epic 7 cred runtime to hang a reconciler on.
  11.1's own Dev Notes defer the runtime build for exactly this reason. Epic 11's build wave
  therefore opens only after the Wave-1 substrate lands (Epic 2 coordination record + apiserver,
  Epic 3 Run runtime, Epic 9 ingress runtime, Epic 7 cred runtime). Program is currently
  executing Wave-1 (Epic 2/3/13 active) — Epic 11 build is correctly downstream.

**Net:** Epic 11 is *spec-actionable now, build-gated later.* Pushing specs forward is the
in-scope PM move; firing Coders at the runtime now would be premature (no substrate to build on).

## 4. Disposition (this PM pass)

1. **Delegate 11.2–11.6 detailing to the Story Writer** (child issue under ISI-2183, dependency
   ordered). Live continuation path for the epic.
2. **Make 11.1's block legible:** 11.1 spec + model-check are done; the ticket's opaque `blocked`
   is not the runtime gate talking. Recommend routing the *spec* to its review ticket (ISI-2484)
   and carrying the runtime build as an explicit build-wave item gated on substrate — owner
   backup_Architect (spec author) to confirm status flip; PM will not unilaterally flip another
   agent's ticket.
3. **Epic stays `in_progress`** with Story Writer detailing in flight (live path); the build wave
   is tracked as substrate-gated, not started.

## 5. Non-goals / guardrails carried from 11.1

- Mirror is **UNTRUSTED-EXTERNAL, provenanced** — never the source of truth; never writes coord
  custody (claim/lease/fence). No-P2P (§6) stays intact.
- Credentials are **per-user BYO Secret refs** (Epic 7) scoped mirror-read — never a shared
  platform/master token, never logged/injected into an agent Run.
- Provider access sits **entirely behind the `SourceControlProvider` seam** (11.5) — GitHub is
  v1; GitLab/Gitea drop in with zero reconciler change.
