# Story 11.6: Console tiles + provenance-tagged CI-failure auto-post to Project room (closed loop)

Status: ready-for-dev (spec) — build gated on Epic-11 build wave (Wave-1 substrate)

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The closed-loop story — sync → dashboard → room. It lights the dashboard PR/CI tiles (8.8)
> from the 11.2/11.3/11.4 mirror and, on a CI failure, auto-posts a provenance-tagged context
> message to the Project discussion room (Epic 10.3).** The tiles are a **read model** over
> `scm_pr_mirror`/`scm_check_run` (no new store, no second GitHub integration — 8.8a discipline),
> degrading per-tile to empty when unsynced. The auto-post is an **observer notification, not a
> coordination path**: it fires on a mirror **state transition** (check → `failure`), posts an
> **UNTRUSTED-EXTERNAL, `external_origin`-tagged** message into the room (10.3) — a *collab surface,
> not a coordination channel* — and **carries no claim/handoff/dispatch capability** (§6 no-P2P;
> Epic 12 observer-not-coordinator discipline). It is **idempotent + echo-safe**: a redelivered
> `failure` (at-least-once) posts **once**, and our own post never re-triggers. A CI-failure that
> **dispatches an agent or writes coord**, an auto-post **missing provenance** or rendered as trusted
> instruction, a **duplicate post** per redelivery, or a dashboard tile backed by a **new rollup
> store** is a **regression**. Read AC2, AC3, AC4 literally. Deps: **11.2 + 11.3 + 11.4 (mirror) +
> 8.8 (dashboard read model) + 10.3 (Project room).**

## Story

As **an operator**,
I want **synced SCM state surfaced in the console** — dashboard PR/CI tiles + a provenance-tagged
CI-failure auto-post to the Project discussion room,
so that **the sync closes the loop into the surfaces I already use — a CI failure reaches the squad's
room as attributable context — without the auto-post ever becoming a coordination path (no
claim/handoff/dispatch), without the tiles adding a new datastore, and without a redelivered webhook
double-posting.**

## Context & prerequisites (read first)

- **PRD / epic:** `docs/bmad/04-epics-and-stories.md` Epic 11 row **11.6** — *synced state surfaced
  in console — dashboard tiles + CI-failure auto-post to the Project room; on a CI failure on a linked
  PR, a **provenance-tagged context message auto-posts to the Project discussion room (Epic 10)** and
  the dashboard PR/CI tiles update.* **Closed loop: sync → dashboard (8.8) → room (10.3).**
- **The mirror this surfaces:** `docs/bmad/stories/11-2-issues-work-items-sync.md`,
  `docs/bmad/stories/11-3-pr-status-run-branch.md`, `docs/bmad/stories/11-4-ci-checks-artifacts-build-browser.md`
  (`scm_pr_mirror` / `scm_check_run` — the CI-failure transition source; all untrusted-external,
  provenanced). The loop is 11.1; the seam is 11.5.
- **The dashboard read model (tiles):** `docs/bmad/04-epics-and-stories.md` **8.8a** (the
  data-aggregation read model — one RBAC-filtered payload composed from `coord` audit + **`scm`
  mirror** + OTel + Run state; **no new aggregation service, no rollup datastore**; **per-tile
  degradation** — unsynced repo → empty PR/CI tile) and **8.8d** (PR mini-board over `scm_pr_mirror`).
  11.6's tiles are a **read model over the mirror**, not a new store — the 8.8a R6/ponytail discipline.
- **The Project room (auto-post target):** Epic 10.3 Project discussion room (ISI-2695). Per
  `[[isi-2182-epic10-discussion-rooms]]`: the **room is a collab-surface, NOT a coordination
  channel** (Postgres-backed, ADR-001; not a CRD). An auto-post is a **message into the room**, not a
  dispatch. Messages carry provenance (author/origin) — the CI-failure post is authored by a **bot/
  system principal** and tagged **untrusted-external** `external_origin`.
- **Observer-not-coordinator (the load-bearing guard):** the auto-post is the SCM analog of the Epic
  12 plugin guard — *observers react outside core; **never** a coordination path* (§6 no-P2P). The
  post **notifies**; it **must not** claim a work item, create a handoff, dispatch an agent, or write
  any coordination custody. See `docs/bmad/03-architecture.md` §6 (no-P2P), §7.5/ADR-023 (event
  fan-out — the auto-post may ride the event seam but stays an observer), §7.3.2 (untrusted-external).
- **Idempotency + echo-safety:** the auto-post fires on a **mirror state transition** to
  `conclusion=failure` (not on every webhook). Because webhooks are at-least-once (11.1), the post is
  **idempotent per `(check_external_id, head_sha, conclusion)`** — a redelivered failure posts
  **once**; and the post is **origin-marked** so it never re-enters the mirror as inbound (11.1
  echo-suppression carries).
- **Scope guard:** 11.6 is **tiles (read model) + CI-failure auto-post only.** The mirror data comes
  from 11.2/11.3/11.4; the room from 10.3; the dashboard aggregation from 8.8a. This story adds **no
  coordination path** and **no new datastore**. **Runtime Go/UI deferred to the Epic-11 build wave.**

## Acceptance Criteria

**AC1 — dashboard PR/CI tiles are a read model over the mirror, degrading per-tile (the read-model crux).**
Given a Project whose repo is synced, When I open the dashboard, Then the **PR/CI tiles** render from
the **`scm_pr_mirror` / `scm_check_run` read model** through the **8.8a composed payload** (RBAC-
filtered, §12.3) — **no new aggregation service, no rollup datastore**; when the repo is **unsynced**,
the tiles **degrade to empty** (per-tile, never a whole-dashboard failure). A tile backed by a **new
rollup store**, or one that **hard-fails the dashboard** when unsynced, is a **regression**.

**AC2 — a CI failure auto-posts a provenance-tagged message to the Project room (the closed-loop crux).**
Given a CI **failure** on a linked PR, When the reconciler records the `scm_check_run` transition to
`conclusion=failure`, Then a **context message auto-posts to the Project discussion room (10.3)**,
authored by a **system/bot principal**, tagged **untrusted-external** with **`external_origin`**
(provider, repo, PR/check, actor) and a link to the failing check/PR + correlated Run (11.3/11.4).
The message renders as *external, attributable context* — **never** as a trusted instruction to the
room's agents. A post **missing provenance**, or rendered/consumed as **trusted control input**, is a
**regression**.

**AC3 — the auto-post is an observer, never a coordination path (the no-P2P crux, §6).**
Given the CI-failure auto-post fires, When it posts, Then it **only writes a room message** — it
**does not** claim a work item, create a handoff, dispatch an agent, or write any coordination custody
(claim/lease/fence). It is the SCM analog of the Epic 12 **observer-not-coordinator** guard. An
auto-post that **dispatches an agent**, **transitions a work item**, or **writes custody** is a
**regression** (a coordination path smuggled through a notification).

**AC4 — idempotent + echo-safe: a redelivered failure posts once, our post never re-triggers (the convergence crux).**
Given at-least-once webhook delivery, When a `failure` is **redelivered**, Then the auto-post is
**idempotent** per `(check_external_id, head_sha, conclusion)` — it posts **exactly once**, no
duplicate room message; and the auto-post is **origin-marked** so it **never** re-enters the mirror as
a fresh inbound change (11.1 echo-suppression). A **duplicate post** per redelivery, or an auto-post
that **re-triggers itself**, is a **regression**.

## Tasks / Subtasks

- [ ] **(Epic 11 build)** Dashboard PR/CI tiles as a read model over `scm_pr_mirror`/`scm_check_run`
  through the **8.8a composed payload** (RBAC-filtered); per-tile degrade-to-empty when unsynced. **No
  new store, no new service.**
- [ ] **(Epic 11 build)** CI-failure auto-post: on `scm_check_run` transition → `failure`, post a
  provenance-tagged, `external_origin`-tagged context message to the Project room (10.3) via the
  room's message-append path, authored by a system/bot principal; link failing check/PR + correlated
  Run.
- [ ] **(Epic 11 build)** Idempotency guard keyed `(check_external_id, head_sha, conclusion)` (post
  once per transition); origin-marking so the post is echo-suppressed on the inbound side.
- [ ] **(Epic 11 build)** Observer guard: the auto-post path has **no** access to claim/handoff/
  dispatch/custody APIs (structural — it can only append a room message).
- [ ] **Pin the construction-time contract** as a runnable falsification check
  (`docs/bmad/spikes/bench/scm-ci-autopost-check.py`) in 11.1's model-check style: model the
  read-model tiles, the failure→room auto-post, the observer-not-coordinator boundary, and the
  idempotent/echo-safe post.
- [ ] **Four checks C1–C4 ↔ AC1–AC4**, GREEN on the 8.8a/§6/§7.3.2-conformant baseline.
- [ ] **Mutation battery** (≥10), each flipping its designated check RED, no vacuous survivors:
  tile-backed-by-rollup-store / tile-hard-fails-dashboard → C1 RED; auto-post-missing-provenance /
  rendered-as-trusted → C2 RED; auto-post-dispatches-agent / transitions-work-item / writes-custody →
  C3 RED; duplicate-post-per-redelivery / post-re-enters-as-inbound → C4 RED.
- [ ] `python3 scm-ci-autopost-check.py` → **exit 0** (baseline GREEN; all mutations CAUGHT).

## Dev Notes

- **Observer-not-coordinator is the whole story's spine.** A CI-failure notification that "kicks off a
  fix Run" is the seductive regression: it turns untrusted-external CI state into a dispatch — exactly
  the §6 no-P2P line and the Epic 12 plugin guard. 11.6 **notifies the room**; a human (or a
  separately-authorized policy) decides what to do. The check makes the boundary structural: the
  auto-post path can **only** append a room message.
- **Tiles are a read model, not a store (8.8a R6/ponytail):** the PR/CI tiles compose from the mirror
  through the existing 8.8a payload — no rollup table, no aggregation service, no second GitHub
  integration. Per-tile degradation means an unsynced repo yields empty PR/CI tiles while the rest of
  the dashboard renders. This is the same discipline 8.8a/8.8d already carry; 11.6 supplies the tile
  content from 11.2/11.3/11.4.
- **Provenance is the trust boundary into the room (D8/§7.3.2):** the room is a collab surface shared
  by agents; an un-tagged CI-failure message read as a native instruction is the F16 failure. The post
  is authored by a bot/system principal and tagged untrusted-external `external_origin` — the room
  renders it as external, attributable context, and agents consume it through the same untrusted-
  provenance envelope as memory/discussion.
- **Idempotency on the transition, not the webhook:** posting per webhook double-posts under
  at-least-once delivery. Posting per `(check_external_id, head_sha, conclusion)` transition posts
  once; a `failure` → `failure` redelivery is a no-op. Origin-marking closes the echo (our post can't
  re-enter as inbound) — the same convergence discipline as 11.1's C2/C6 and 11.2's C4.
- **Closed loop, one direction:** sync (11.1–11.4) → dashboard tiles (8.8) → room (10.3). The loop
  ends at the room as **information**; it does not curl back into coordination. That one-directional
  boundary is what keeps the SCM sync a mirror, not an authority.

## Testing

- **Runnable check:** `python3 docs/bmad/spikes/bench/scm-ci-autopost-check.py` → **exit 0** —
  baseline GREEN on C1–C4; mutation battery all CAUGHT, no vacuous survivors.
- **Deferred to Epic 11 build (integration):** the real read-model tiles (over 8.8a) + the CI-failure
  auto-post into the 10.3 room, proven by the operator/apiserver + console integration suite (CI fails
  → tile updates + one provenance-tagged room message; redelivery → still one message; no coord
  mutation, no dispatch).

## References

- [Source: docs/bmad/04-epics-and-stories.md] — Epic 11 row 11.6 (console tiles + CI-failure
  auto-post; closed loop sync→dashboard→room); 8.8a (read-model / no-rollup / per-tile degrade); 8.8d
  (PR mini-board).
- [Source: docs/bmad/stories/11-2-issues-work-items-sync.md] / 11-3 / 11-4 — the mirror this surfaces
  (`scm_pr_mirror` / `scm_check_run`, the CI-failure transition source).
- [Source: docs/bmad/stories/11-1-repo-sync-reconciler.md] — the loop + echo-suppression the auto-post
  inherits.
- [Source: docs/bmad/03-architecture.md] — §6 (no-P2P / observer-not-coordinator), §7.5 + ADR-023
  (event fan-out — auto-post rides the seam as an observer), §7.3.2 (untrusted-external), §12.3
  (RBAC-filtered dashboard payload). ADR-001, ADR-018.
- [Source: Epic 10.3 Project discussion room (ISI-2695)] — the room is a collab-surface, not a
  coordination channel (Postgres, ADR-001); the auto-post target.

## Dev Agent Record

_(empty — spec authored by the Story Writer; the build wave fills this in.)_
