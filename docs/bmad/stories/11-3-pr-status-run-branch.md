# Story 11.3: PR status ↔ Run/branch (open/merged/closed + review_state, `head_sha → run.commit_sha`)

Status: ready-for-dev (spec) — build gated on Epic-11 build wave (Wave-1 substrate)

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The PR-mirror story — it fills `scm_pr_mirror` (state + `review_state`) on the 11.1 loop and
> correlates each PR to the Run/branch that produced it via `head_sha → run.commit_sha`, so PR
> state surfaces on the Run and on the dashboard (8.8d).** It elaborates the `scm_pr_mirror`
> row + the Run correlation 11.1 explicitly deferred to this story, through the frozen
> `SourceControlProvider.PullRequests` seam (11.5). The mirror is **UNTRUSTED-EXTERNAL,
> provenanced** — external-owned fields (`state ∈ {open, merged, closed}`, `review_state`,
> `head_sha`, title) written **only** by the inbound reconciler; the **Run correlation is a
> read-side JOIN** (`scm_pr_mirror.head_sha = run.commit_sha`), **never** a mirror write into the
> Run and **never** custody. A correlation that **mutates the Run** (writes PR state onto the Run
> CRD/coord record as authoritative), a mirror **missing `external_origin`**, a **non-idempotent**
> PR upsert, or a Run linked by anything **other than the commit-sha correlation** (e.g. by PR
> title guesswork) is a **regression**. Read AC1, AC2, AC4 literally. Deps: **11.1 loop + 11.5
> seam + Epic 3 Run (`commit_sha`).**

## Story

As **an operator**,
I want **PR status** — open/merged/closed + review state — mirrored on the repo-sync loop and
**correlated to the Run/branch that produced it** (`head_sha → run.commit_sha`),
so that **the console shows real PR + review state on the originating Run and in the dashboard
(8.8d) without leaving KSquad, without the PR mirror ever becoming authoritative over the Run, and
without custody crossing the seam.**

## Context & prerequisites (read first)

- **PRD / epic:** `docs/bmad/04-epics-and-stories.md` Epic 11 row **11.3** — *PR status
  (open/merged/closed + review state) linked to the Run/branch that produced it; a Run that pushed a
  branch with a PR shows PR state + review status on the Run and in the dashboard (8.8), updated by
  the reconciler.* **Links Epic 3 (Run) ↔ GitHub PR.**
- **The loop + seam + the row this elaborates:** `docs/bmad/stories/11-1-repo-sync-reconciler.md` —
  the mirror-shape note states explicitly: *"`scm_pr_mirror.review_state` and the `head_sha →
  run.commit_sha` Run/branch correlation are **elaborated by 11.3**."* Plus **11.5**
  (`SourceControlProvider.PullRequests` capability: `state`, `review_state`, `head_sha`).
- **Architecture:** `docs/bmad/03-architecture.md` **§5.4** (reconciler & mirror — read whole),
  **§7.3.2** (untrusted-external provenance), **§9.4** (worktree model — a Run pushes its worktree
  branch; `run.commit_sha` is the head it pushed), **§6** (fenced claim / no-P2P — custody never
  crosses the seam), **§8** (Run state machine — the Run the PR correlates to). **ADR-001** (`scm`
  schema), **ADR-018** (field-ownership + echo-suppression).
- **Mirror schema (11.1 pinned the table; 11.3 fills `state`/`review_state`/`head_sha` + correlation):**
  `scm_pr_mirror` — external-owned **`external_id`, `number`, `title`, `state ∈ {open, merged,
  closed}`, `review_state ∈ {pending, approved, changes_requested, review_required, dismissed}`,
  `head_sha`, `base_ref`, `actor`, `external_origin{...}`, `synced_at`**. Upsert key = `(project_id,
  provider, external_id)`; idempotent (redelivered `pull_request` webhook = no-op).
- **Run correlation (the crux, read-side):** the link is **`scm_pr_mirror.head_sha =
  run.commit_sha`** — a **JOIN at read time**, not a write into the Run. Epic 3's `Run` records the
  `commit_sha` it pushed (§9.4 worktree model); the reconciler mirrors the PR's `head_sha`; the
  console/dashboard **correlate** them. A PR with no matching Run renders un-correlated; a Run with
  no PR renders PR-less. **Neither side is mutated by the correlation.**
- **Provenance / trust (D8, §7.3.2):** every `scm_pr_mirror` row is **untrusted-external** with
  `external_origin`; PR/review state renders as *external, attributable*, never as trusted control
  input, never as an authoritative Run status.
- **Downstream consumers:** the **8.8d PR status mini-board** reads `scm_pr_mirror` grouped by
  `review_state` (ready-for-review / draft / blocked / merged) with each row linking to its
  correlated Run; the **8.7g build-browser PR/CI header strip** reads the same. Both **degrade to
  empty** when no repo is synced — 11.3 does not block them shipping.
- **Scope guard:** 11.3 is **PR + review state + Run correlation only.** CI checks/artifacts are 11.4
  (11.4 depends on 11.3), console tiles + CI-failure auto-post are 11.6. No coordination path; no
  mirror write into the Run or coord custody. **Runtime Go deferred to the Epic-11 build wave.**

## Acceptance Criteria

**AC1 — PR + review state reconcile through the seam into a provenanced mirror (the mirror crux).**
Given a linked repo with a PR, When the PR changes (webhook `pull_request` / poll), Then the
reconciler **idempotent-upserts** `scm_pr_mirror` keyed by `(project_id, provider, external_id)` via
**`SourceControlProvider.PullRequests`** (11.5) — `state ∈ {open, merged, closed}`, `review_state`,
`head_sha`, `base_ref` — and the row is **untrusted-external** with **`external_origin`**. A
redelivered webhook is a **no-op**. A row **missing `review_state`/`head_sha`**, **missing
`external_origin`**, or reached by a **direct GitHub call** outside the seam, is a **regression**.

**AC2 — Run correlation is a read-side `head_sha → run.commit_sha` JOIN, never a Run mutation (the correlation crux).**
Given a mirrored PR and a Run that pushed its branch, When the console/dashboard correlates them,
Then the link is computed **`scm_pr_mirror.head_sha = run.commit_sha`** at read time — the reconciler
**does not write PR state onto the Run CRD or the coordination record** as authoritative, and the Run
is **never mutated** by the mirror. A PR with no matching Run renders **un-correlated**; a Run with no
PR renders **PR-less**. Correlating by anything **other than the commit sha** (title/branch-name
guesswork), or a correlation that **mutates the Run**, is a **regression**.

**AC3 — PR state surfaces on the Run and on the dashboard, updated by the reconciler (the surface crux).**
Given a correlated PR, When I open the Run (8.11) or the dashboard PR mini-board (8.8d), Then I see
**PR state + review state**, refreshed as the reconciler updates the mirror; when no repo is synced,
both surfaces **degrade to empty** (never error). A surface that **hard-depends** on Epic 11 to
render (rather than degrading), or one that shows **stale** state the reconciler has already updated,
is a **regression**.

**AC4 — the PR mirror never writes custody; correlation stays no-P2P (the custody crux, §6).**
Given the reconciler upserts a PR row and the console correlates it to a Run, When it writes, Then it
writes **only external-owned PR fields** — **never** claim/lease/fence, **never** the Run's
authoritative state. The PR mirror is *reflected external state*; the Run's state stays owned by the
Run reconciler (§6/§8). A PR mirror write that touches custody or overwrites Run state is a
**regression** (custody crossing the seam breaks no-P2P).

## Tasks / Subtasks

- [ ] **(Epic 11 build)** `scm_pr_mirror` migration completing `state`/`review_state`/`head_sha`/
  `base_ref` (over 11.1's pinned table); idempotent upsert keyed `(project_id, provider,
  external_id)`.
- [ ] **(Epic 11 build)** Inbound PR reconcile off 11.1's loop via `SourceControlProvider.PullRequests`
  (11.5), subscribing `pull_request` webhook + poll fallback.
- [ ] **(Epic 11 build)** Read-side correlation view/query `scm_pr_mirror.head_sha = run.commit_sha`
  (indexed both sides); expose on Run detail (8.11) + dashboard PR mini-board (8.8d) + build-browser
  strip (8.7g). **No write into the Run.**
- [ ] **Pin the construction-time contract** as a runnable falsification check
  (`docs/bmad/spikes/bench/scm-pr-mirror-check.py`) in 11.1's model-check style: model the PR upsert,
  the read-side sha correlation, and the no-custody/no-Run-mutation invariant.
- [ ] **Four checks C1–C4 ↔ AC1–AC4**, GREEN on the §5.4/§7.3.2/§6-conformant baseline.
- [ ] **Mutation battery** (≥10), each flipping its designated check RED, no vacuous survivors:
  drop-provenance / non-idempotent PR upsert → C1 RED; correlate-by-title / correlation-mutates-Run →
  C2 RED; surface-hard-depends-on-sync (no degrade) / stale-after-update → C3 RED; PR-mirror-writes-
  custody / overwrites-Run-state → C4 RED.
- [ ] `python3 scm-pr-mirror-check.py` → **exit 0** (baseline GREEN; all mutations CAUGHT).

## Dev Notes

- **Correlation is a JOIN, not a write — this is the whole story's spine.** The temptation is to
  "stamp the PR onto the Run" so the Run detail can read it locally. That makes the mirror authoritative
  over the Run and crosses the seam. Instead the Run records the `commit_sha` **it** pushed (§9.4,
  owned by Epic 3), the mirror records the PR's `head_sha` (owned by the reconciler), and the surface
  **joins** them. Two independent owners, one read-time correlation — no custody crosses.
- **Why `head_sha`, not branch name:** branch names are reused/force-pushed; the commit sha the Run
  pushed is the stable, unforgeable correlation key. It also degrades honestly — a force-push that
  moves the PR head to a sha no Run produced simply un-correlates, which is correct.
- **Degrade-to-empty is a first-class requirement (8.8a per-tile degradation):** the PR mini-board and
  the build-browser strip must render empty when no repo is synced, never error. 11.3 provides the
  data; the surfaces already handle absence (8.8d/8.7g say so explicitly) — the check guards that the
  reconciler side never makes them hard-depend.
- **review_state vocabulary is normalized (11.5 AC4):** `{pending, approved, changes_requested,
  review_required, dismissed}` is provider-neutral; the GitHub adapter maps GitHub's review states
  onto it, a GitLab adapter maps MR approval states onto it — the mini-board's grouping
  (ready-for-review/draft/blocked/merged) is derived from this normalized vocabulary, not raw GitHub.

## Testing

- **Runnable check:** `python3 docs/bmad/spikes/bench/scm-pr-mirror-check.py` → **exit 0** — baseline
  GREEN on C1–C4; mutation battery all CAUGHT, no vacuous survivors.
- **Deferred to Epic 11 build (integration):** the real `scm_pr_mirror` upsert + the
  `head_sha=commit_sha` correlation query, proven against a live GitHub + real Runs by the operator/
  apiserver integration suite (Run pushes branch → PR opens → mirror row → correlated on Run + 8.8d;
  merge/close → surfaces update; no PR → surfaces degrade to empty).

## References

- [Source: docs/bmad/04-epics-and-stories.md] — Epic 11 row 11.3 (PR status ↔ Run/branch).
- [Source: docs/bmad/stories/11-1-repo-sync-reconciler.md] — the loop + the explicit note that
  `scm_pr_mirror.review_state` + `head_sha→run.commit_sha` are elaborated here.
- [Source: docs/bmad/stories/11-5-provider-seam-explicit.md] — `SourceControlProvider.PullRequests`
  seam + normalized `review_state`.
- [Source: docs/bmad/03-architecture.md#5.4] — reconciler & mirror; §7.3.2 (untrusted-external), §9.4
  (worktree/`commit_sha`), §6 (no-P2P), §8 (Run state). ADR-001, ADR-018.
- [Source: docs/bmad/04-epics-and-stories.md] — 8.8d (PR mini-board, `scm_pr_mirror` consumer) + 8.7g
  (build-browser PR/CI strip) — both degrade to empty without sync.

## Dev Agent Record

_(empty — spec authored by the Story Writer; the build wave fills this in.)_
