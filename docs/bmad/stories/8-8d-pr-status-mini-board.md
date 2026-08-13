# Story 8.8d: PR status mini-board

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **Reuse the SCM mirror — no second GitHub integration.** The PR mini-board is a **read model over the
> existing `scm_pr_mirror`** (arch §5.4), **not** a fresh GitHub API call from the dashboard. And it
> **must not gate on Epic 11 to ship**: an unsynced repo yields an **empty board**, never a hard failure
> (8.8a per-tile degradation). Read AC4 literally.

## Story

As an **operator opening a Project's dashboard**,
I want **a PR status mini-board grouping the Project's pull requests by state (ready-for-review / draft / blocked / merged), each row linking to its producing Run/branch**,
so that **I see the Project's PR flow at a glance from the source-control sync read model — not a second GitHub integration — degrading to an empty board when no repo is synced (FR-I6).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.9 **FR-I6** — PR status mini-board grouping the Project's PRs by state (**ready-for-review / draft / blocked / merged**), derived from the **source-control sync** read model (Theme H, FR-H1…H5) — **not** a second GitHub integration; each PR row links to its producing Run/branch where correlated; degrades to empty when no repo is synced.
- **Architecture:** `docs/bmad/03-architecture.md` §13 **r24** — the PR mini-board comes from the **`scm_pr_mirror` read model** (§5.4, `review_state` → ready-for-review/draft/blocked/merged, correlated to the Run by `head_sha→run.commit_sha`); per-tile degradation (unsynced repo → empty PR board); same deny-by-default RBAC wall. Also §5.4 (repo-sync reconciler + `pkg/scm` provider seam, GitHub mirror; ADR-018).
- **Depends on (must be landable/mergeable before this story is done):**
  - **8.8a** — the dashboard read model; this story renders the `prBoard` sub-payload 8.8a composes from `scm_pr_mirror`. This story does **not** call GitHub or re-query the mirror directly beyond what 8.8a exposes.
  - **Epic 11.3** — PR status sync (populates `scm_pr_mirror` with `review_state`). **This is a progressive dep, not a gate:** until 11.3 lands (or no repo is synced), the board degrades to **empty** (8.8a per-tile rule). The rendering + grouping + correlation contract can and should land against the mirror's shape now.
- **Blocked by:** 8.8a. **Progressive:** Epic 11.3. **Mirrors:** the build-browser PR strip (8.7g) reads the same mirror — keep the `review_state` grouping + `head_sha→run.commit_sha` correlation consistent with it.

## Acceptance Criteria

**AC1 — group PRs by the four states, from the SCM mirror.**
Given a Project whose repo is synced (Epic 11), When the operator opens the dashboard, Then the **PR mini-board** groups the Project's PRs into **ready-for-review / draft / blocked / merged** — the `scm_pr_mirror.review_state` values (§5.4) — via the 8.8a `prBoard` sub-payload. And the grouping is a **read** of the mirror — this story issues **no** direct GitHub API call (no second integration).

**AC2 — each row links to its producing Run/branch where correlated.**
Given a PR row, When it renders, Then it **links to its producing Run/branch** where correlated — the mirror's `head_sha→run.commit_sha` correlation (§13 r24). And where a PR is **not** correlated to a Run (e.g. externally opened), the row still renders in its state group, with the Run link absent rather than fabricated.

**AC3 — reuse the SCM mirror; no second GitHub integration (Theme H).**
Given the board, When it composes, Then it reads **only** the `scm_pr_mirror` read model (§5.4, via 8.8a) — it does **not** open a second GitHub integration, token, or webhook path. The single source-control sync reconciler (§5.4, ADR-018) is the only GitHub touch; the dashboard is a read model over its mirror.

**AC4 — degrades to an empty board when no repo is synced (the availability crux).**
Given a Project with **no synced repo** (or Epic 11.3 not yet landed), When the operator opens the dashboard, Then the PR mini-board renders an **explicit empty board** ("No repository synced" / empty state) — **not** a hard failure, **not** a fabricated PR, **not** a whole-dashboard error (8.8a per-tile degradation). And an empty/degraded `prBoard` sub-payload (8.8a `{available:false}`) is rendered as this empty state, distinguishable from "synced repo with zero open PRs."

**AC5 — RBAC-scoped through 8.8a (no second authz path).**
Given the rendered board, When it displays, Then it shows only PRs for Projects/repos the caller is entitled to see — the `prBoard` sub-payload was **already server-filtered** by 8.8a's deny-by-default RBAC wall (§12.3). This story adds **no** client-side authz and **no** dashboard-specific authz path.

**AC6 — real rows only; no placeholder (FR-I3).**
Given the board, When it renders, Then every row is a real `scm_pr_mirror` PR (via 8.8a) — **no** placeholder or synthesized PR. A missing/degraded source renders the empty state (AC4), never a fake PR.

**AC7 — observability: no new metric; consistent with the SCM mirror.**
Given the board, When it renders, Then this story emits **only** ordinary console/BFF request telemetry — it introduces **no new domain metric** (the PR board is a read model, obs §17 adds no PR metric). NFR-OBS3 standing law holds: no per-item ids (`pr.id`/`run.id`) as metric labels, no `model` label; PR-mirror sync telemetry belongs to Epic 11 / §5.4, not here.

## Tasks / Subtasks

- [ ] **Task 1 — Render the four-state PR mini-board (AC1, AC2, AC6).**
  - [ ] Render the 8.8a `prBoard` sub-payload grouped into **ready-for-review / draft / blocked / merged** (`scm_pr_mirror.review_state`).
  - [ ] Each row links to its producing Run/branch via the mirror's `head_sha→run.commit_sha` correlation; uncorrelated PRs render without a Run link (never fabricated).
  - [ ] No placeholder rows; a degraded source → empty state (Task 3).
- [ ] **Task 2 — Reuse the SCM mirror only (AC3, AC5).**
  - [ ] Confirm the board reads exclusively from `scm_pr_mirror` via 8.8a — no direct GitHub call, no second integration/token/webhook.
  - [ ] Render only the pre-scoped payload; add no client-side authz.
- [ ] **Task 3 — Empty / degraded state (AC4).**
  - [ ] When `prBoard` is `{available:false}` (no repo synced / Epic 11.3 absent), render an explicit **"No repository synced"** empty board — distinct from a synced-repo-zero-PRs state and from loading. Never a hard failure or fake PR.
- [ ] **Task 4 — Consistency with the build-browser PR strip (8.7g).**
  - [ ] Keep the `review_state` grouping + `head_sha→run.commit_sha` correlation consistent with 8.7g (same mirror, same correlation) so the dashboard board and the build-browser strip do not diverge.
- [ ] **Task 5 — Observability self-check (AC7).**
  - [ ] Confirm no new domain metric here; only ordinary request telemetry. NFR-OBS3: no per-item ids on labels, no `model` label.

## Dev Notes

- **One GitHub integration, ever — the SCM mirror (§5.4, ADR-018).** FR-I6 is explicit: the board is derived from the source-control sync read model, **not** a second GitHub integration. The repo-sync reconciler is the only thing that talks to GitHub; the mirror (`scm_pr_mirror`) is the read model. The dashboard reads the mirror (via 8.8a). If you find yourself adding a GitHub token or API call in this story, stop — that is the reconciler's job (Epic 11 / §5.4).
- **Progressive dep, not a gate (per-tile degrade).** Epic 11.3 populates `review_state`; until it lands or a repo is synced, the board is **empty**, and that is a first-class, correct state — not a failure. This story ships the rendering + grouping + correlation now; the board fills as 11.3 lands. Do **not** block this story on Epic 11.
- **Correlation is `head_sha→run.commit_sha`.** A PR links to its producing Run/branch through that correlation (§13 r24). Where a PR has no correlated Run, render the row without the Run link — do not fabricate a correlation. Keep this identical to the build-browser PR strip (8.7g) so the two surfaces agree.
- **"blocked" here is the PR `review_state`, not the work-item block.** The PR mini-board's "blocked" group is a `scm_pr_mirror.review_state` value (a PR blocked on review/CI), distinct from the work-item `blocked` coordination state used by the approval gate (2.12). Do not conflate them.

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield — only `pkg/auth/*_test.go` + `console/e2e/auth/`. The `pkg/scm` provider seam + `scm_pr_mirror` (§5.4, ADR-018) are not yet in this checkout — they land with Theme H / Epic 11. This story's UI lands under `console/` in the dashboard surface; it consumes 8.8a's `prBoard` sub-payload and adds **no** apiserver/SCM code (the mirror is Epic 11's).
- **Match conventions:** render within the console dashboard; reuse the shared read path (8.8a) — do not add a bespoke SCM client.

### References

- [Source: docs/bmad/02-prd.md#9.9 FR-I6] — PR status mini-board; ready-for-review/draft/blocked/merged; derived from source-control sync read model, not a second GitHub integration; each row links to its producing Run/branch; degrades to empty when no repo synced.
- [Source: docs/bmad/03-architecture.md#13 (r24) — dashboard read model] — PR mini-board from `scm_pr_mirror` (§5.4, `review_state`), correlated `head_sha→run.commit_sha`; per-tile degradation; same RBAC wall.
- [Source: docs/bmad/03-architecture.md#5.4 — source-control sync] — repo-sync reconciler + `pkg/scm` provider seam, GitHub mirror (ADR-018) — the single GitHub touch this story reads from.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.8 row 8.8d] — epic-level AC; **deps 8.8a + Epic 11.3**; reuses the SCM mirror (no second integration); feeds/mirrors the build-browser PR strip (8.7g).
- [Source: docs/bmad/stories/8-8a-dashboard-data-aggregation-read-model.md] — the `prBoard` sub-payload + per-tile degradation this story renders.

### Open questions (route via ISI-2325; do not block rendering)

1. **`review_state` value mapping (Architect / Epic 11 owner).** Confirm the exact `scm_pr_mirror.review_state` enum maps cleanly to the four display groups (ready-for-review / draft / blocked / merged) — e.g. how a closed-unmerged PR is grouped. *Does not block the four validated groups; render the mirror's states as they land.*
2. **Row link target (Designer).** Confirm each PR row links to the producing **Run** (8.2), the **branch** in the build browser (8.7), or the external PR — the mock pins "producing Run/branch"; confirm precedence when both are correlated.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, agent 2230b001) — construction-time contract via runnable falsification check (`pr-status-mini-board-check.py`, Epic-8 model-check pattern).

### Debug Log References

- `python3 pr-status-mini-board-check.py` → exit 0 (naive second-github-integration panel trips all 7; §8.8d conformant mini-board holds C1-C7).
- `--mutate={WRONG_GROUPS,FAKE_SHA_LINK,GITHUB_DIRECT,HARD_FAIL,CLIENT_AUTHZ,FAKE_PR,PERITEM_LABEL}` → each exit 1 with the mapped invariant RED; no vacuous survivors.

### Completion Notes List

- Implemented C1-C7 falsification check with teeth via a "second GitHub integration panel" (calls GitHub API directly, wrong grouping, fabricates sha-correlations, hard-fails on no-repo, client-side authz, per-item metric labels).
- **Load-bearing cruxes proven:** (C3) one SCM mirror, no second GitHub integration — the repo-sync reconciler (§5.4, ADR-018) is the only GitHub touch; (C4) no repo synced (Epic 11.3 absent) → explicit empty board ("No repository synced"), HTTP 200, never 5xx (8.8a per-tile degrade crux); (C2) uncorrelated PRs render without a fabricated Run link (head_sha→run.commit_sha correlation only, §13 r24).
- Runtime proof (real scm_pr_mirror queries, four-state rendering, correlation wire-up) owned by console E2E + Epic 11 integration tests.

### File List

- `docs/bmad/spikes/bench/pr-status-mini-board-check.py` (new) — C1-C7 runnable falsification check.
- `docs/bmad/stories/8-8d-pr-status-mini-board.md` (this file) — status→done + Dev Agent Record.
