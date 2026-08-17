# Story 11.2: GitHub issues ⇄ KSquad work items (status/labels/linkage, provenance, last-writer-wins + audit)

Status: ready-for-dev (spec) — build gated on Epic-11 build wave (Wave-1 substrate)

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The first mirror-content story on the 11.1 loop — it maps a linked repo's issues to KSquad
> work items (status/labels/linkage), provenance-tagged so the console distinguishes KSquad-native
> from GitHub-sourced.** It reconciles issues through the **frozen `SourceControlProvider` seam
> (11.5)** into the **`scm_issue_mirror`** row 11.1 pinned, **linked** to the Epic-2 work item.
> The mirror is **UNTRUSTED-EXTERNAL, provenanced (`external_origin`)** — a *mirror, not the source
> of truth*: external-owned fields (title/body/state/labels) are written **only** by the inbound
> reconciler; the **KSquad-owned link (`work_item_id`) and all coord custody (claim/lease/fence)
> are never written by the mirror** (§6 field-ownership split). Optional **outbound** reflection
> (work-item state → GitHub issue) is **direction-gated** (config), **echo-suppressed** (our own
> write is origin-marked and dropped on the way back in), and off unless `reflectOutbound`. Conflict
> is **last-writer-wins + an audit row** (§6.5). A mirror row treated as **trusted control input**,
> a **missing `external_origin`**, a mirror that **writes `work_item_id` or custody**, a **missing
> echo-suppression** that ping-pongs, or a conflict resolved **without an audit row** is a
> **regression**. Read AC1, AC3, AC4, AC5 literally. Deps: **11.1 loop + 11.5 seam + Epic 2 work
> items.**

## Story

As **an operator**,
I want **GitHub issues ⇄ KSquad work items** synced (status, labels, linkage) through the repo-sync
loop — provenance-tagged in Postgres so the console distinguishes KSquad-native from GitHub-sourced,
with conflicts resolved last-writer-wins + audit,
so that **I see and manage real issue state inside the console without the mirror ever becoming the
source of truth, without custody crossing the seam (§6 no-P2P), and without a reflected write
ping-ponging back as a fresh inbound change.**

## Context & prerequisites (read first)

- **PRD / epic:** `docs/bmad/04-epics-and-stories.md` Epic 11 row **11.2** — *GitHub issues ⇄
  KSquad work items (status/labels/linkage); a GitHub issue change reflects on the linked work item
  (and vice versa per configured direction); synced state lives in Postgres with **provenance
  tagging** so the console distinguishes KSquad-native vs GitHub-sourced. **Conflict policy:
  last-writer-wins with audit row (§6.5).*** ADR-001.
- **The loop + seam this rides:** `docs/bmad/stories/11-1-repo-sync-reconciler.md` (level-triggered
  idempotent upsert keyed by external id, HMAC-before-parse webhook + poll fallback, BYO token,
  untrusted-external provenance, echo-suppression) and **11.5** (`docs/bmad/stories/11-5-provider-seam-explicit.md`
  — the frozen `SourceControlProvider.Issues` capability). 11.2 adds **no new loop machinery** — it
  fills the `scm_issue_mirror` row and the work-item link on top of 11.1's contract.
- **Architecture:** `docs/bmad/03-architecture.md` **§5.4** (repo-sync reconciler & mirror — read
  whole), **§7.3.2** (untrusted-external provenance envelope — same envelope as memory/discussion),
  **§6.1** (`work_item` shape + state), **§6.5** (audit-row discipline — every mutation co-commits an
  immutable audit row same-txn), **§6** (fenced claim / no-P2P — custody never crosses the seam),
  **§5.1** (`Project.repo.sync.mirror{issues}` + `reflectOutbound` direction gate). **ADR-001** (one
  Postgres — `scm` schema), **ADR-018** (field-ownership + echo-suppression).
- **Mirror schema (11.1 pinned the table; 11.2 fills it):** `scm_issue_mirror` — external-owned
  fields **`external_id`, `number`, `title`, `body`, `state ∈ {open, closed}`, `labels[]`,
  `actor`, `external_origin{provider,repo,external_id,actor}`, `synced_at`** — plus the **KSquad-owned
  link `work_item_id`** (nullable FK to Epic-2 `work_item`) written **only** by the coordination
  record's link operation, **never** by the inbound mirror upsert. Upsert key = `(project_id,
  provider, external_id)` (idempotent — a redelivered webhook is a no-op).
- **Linkage model:** a work item ↔ issue link is established by **body/title convention or explicit
  operator link** (e.g. `KSquad-<work_item_id>` marker on the issue, or an operator "link" action).
  The link write is a **KSquad-owned-field** write on the coordination side; the mirror only **reads**
  the link to render provenance. **Un-linked** synced issues render as GitHub-sourced with no
  KSquad work item.
- **Provenance / trust (D8, §7.3.2):** every `scm_issue_mirror` row is **untrusted-external** and
  carries `external_origin`; the console renders it as *external, attributable* (a "GitHub-sourced"
  badge distinct from KSquad-native items); agents consume it only through the **same
  untrusted-provenance envelope as memory/discussion** — **never trusted control input**.
- **Outbound (optional, direction-gated):** when `Project.repo.sync.mirror.issues.direction`
  includes outbound **and** `reflectOutbound` is on, a KSquad work-item state/label change reflects
  to the GitHub issue **through the seam**, **origin-marked** (bot actor + marker) so the resulting
  inbound webhook is **echo-suppressed** (dropped, never re-applied). Outbound is **off by default**.
- **Conflict (OQ13 / §6.5):** when both sides changed since last sync, resolution is
  **last-writer-wins by `synced_at`/event timestamp**, and the resolution **co-commits an audit row**
  (`§6.5`) capturing both candidate values, the winner, and `external_origin` — so a clobber is
  **attributable, never silent**.
- **Scope guard:** 11.2 is **issues ⇄ work items only.** PR status is 11.3, checks/artifacts 11.4,
  console tiles + CI-failure auto-post 11.6. This story adds **no coordination path** — the link and
  any work-item state write go through the **existing coord mutation** (Epic 2, RBAC-gated, audited),
  never a mirror-authored custody write. **Runtime Go deferred to the Epic-11 build wave.**

## Acceptance Criteria

**AC1 — issues reconcile through the seam into a provenanced, untrusted-external mirror (the mirror crux).**
Given a linked repo, When an issue changes (webhook-triggered or poll), Then the reconciler
**idempotent-upserts** `scm_issue_mirror` keyed by `(project_id, provider, external_id)` via the
**`SourceControlProvider.Issues`** seam (11.5) — status, labels, title/body — and the row is
**untrusted-external** (§7.3.2) carrying **`external_origin`** (provider, repo, external id, actor).
A redelivered webhook is a **no-op**. A mirror row **missing `external_origin`**, or one reached by a
**direct GitHub call** outside the seam, is a **regression**.

**AC2 — the console distinguishes KSquad-native vs GitHub-sourced (the provenance-render crux).**
Given synced issues, When the console lists work items / issues, Then a **GitHub-sourced** item is
**visibly provenance-badged** (external origin + repo + issue number, linking out) and **distinct**
from a **KSquad-native** work item; an item with **no `external_origin`** never renders as external,
and an external item is **never rendered as trusted/native**. Rendering an external item without its
provenance badge is a **regression**.

**AC3 — external-owned fields only; the mirror never writes the link or custody (the field-ownership crux, §6).**
Given the inbound reconciler upserts a mirror row, When it writes, Then it writes **only
external-owned fields** (title/body/state/labels/actor/origin); the **KSquad-owned `work_item_id`
link is written only by the coordination link operation**, and **claim/lease/fence custody is never
written by the mirror** (§6). A mirror upsert that sets `work_item_id`, or that touches any custody
field, is a **regression** (custody crossing the seam breaks no-P2P).

**AC4 — echo-suppression: a reflected outbound write never re-enters as fresh inbound (the loop crux).**
Given `reflectOutbound` is on and KSquad reflects a work-item change to the GitHub issue, When the
resulting webhook arrives, Then it is **origin-marked** (bot actor + marker) and **dropped** — the
mirror is **unchanged**, no re-apply, no ping-pong. With `reflectOutbound` **off** (default), no
outbound write happens at all. A reflected write that **re-enters** as a fresh inbound change, or an
outbound write firing while `reflectOutbound` is off, is a **regression**.

**AC5 — conflict = last-writer-wins + an audit row (the conflict crux, §6.5).**
Given both the issue and the linked work item changed since the last sync, When the reconciler
resolves, Then it applies **last-writer-wins** (by event/sync timestamp) **and co-commits an audit
row** (§6.5, same-txn) recording **both candidate values, the winner, and `external_origin`** — the
losing value is **attributable, never silently lost**. A conflict resolved **without** an audit row,
or a **non-deterministic** resolution, is a **regression**.

## Tasks / Subtasks

- [ ] **(Epic 11 build)** `scm_issue_mirror` migration (external-owned fields + `external_origin`
  JSON + nullable `work_item_id` FK); idempotent upsert keyed `(project_id, provider, external_id)`.
- [ ] **(Epic 11 build)** Inbound reconcile path off 11.1's loop via `SourceControlProvider.Issues`
  (11.5): map issue → mirror row; resolve/render the work-item link (read-only from the mirror side).
- [ ] **(Epic 11 build)** Last-writer-wins conflict resolver that **co-commits an audit row** (§6.5,
  same-txn) with both candidates + winner + origin.
- [ ] **(Epic 11 build)** Optional outbound reflect (direction-gated by `reflectOutbound`), origin-
  marked for echo-suppression; the inbound path drops origin-marked deliveries.
- [ ] **(Epic 11 build)** Console provenance badge (KSquad-native vs GitHub-sourced) — render-only,
  reuses the untrusted-external envelope; feeds the 8.14 Tickets view provenance badges + 11.6 tiles.
- [ ] **Pin the construction-time contract** as a runnable falsification check
  (`docs/bmad/spikes/bench/scm-issue-mirror-check.py`) in 11.1's model-check style: model the
  inbound upsert, the field-ownership split, echo-suppression, and the LWW+audit conflict resolver.
- [ ] **Five checks C1–C5 ↔ AC1–AC5**, GREEN on the §5.4/§7.3.2/§6.5-conformant baseline.
- [ ] **Mutation battery** (≥12), each flipping its designated check RED, no vacuous survivors:
  drop-provenance → C1/C2 RED; mirror-writes-`work_item_id`/custody → C3 RED; no-echo-suppression
  (reflected write re-enters) / outbound-fires-while-off → C4 RED; conflict-without-audit /
  non-deterministic-resolution → C5 RED; non-idempotent upsert (redelivery duplicates) → C1 RED.
- [ ] `python3 scm-issue-mirror-check.py` → **exit 0** (baseline GREEN; all mutations CAUGHT).

## Dev Notes

- **Mirror-not-authority is the through-line:** the console *shows* issue state; the fenced
  coordination record (§6) stays authoritative for anything KSquad acts on. The link is the only
  bridge, and it is written on the **coord** side (RBAC-gated, audited), never by the mirror. This is
  the exact field-ownership split 11.1's C6 proves — 11.2 instantiates it for issues.
- **Provenance is not decoration — it is the trust boundary (D8):** an un-badged external item read
  by an agent as native instruction is the F16 failure this envelope exists to prevent. The badge is
  the render side of `external_origin`; the agent-facing side is the untrusted-provenance envelope
  (§7.3.2), identical to memory/discussion.
- **Echo-suppression makes outbound safe:** without it, reflecting a work-item change to GitHub fires
  a webhook that the reconciler would re-apply, and the pair oscillates. Origin-marking (bot actor +
  marker) + drop-on-inbound + the idempotent external-id upsert make the sync **convergent, not
  oscillating** — same discipline as 11.1's C2/C6.
- **LWW is deterministic + attributable, not lossy:** last-writer-wins is the resolution, but the
  audit row (§6.5) means the losing value is recoverable and the clobber is attributable. A silent
  LWW (no audit) is the regression the check hunts.
- **Direction gate:** default is **inbound-only** (mirror-read). Outbound is opt-in per Project
  (`reflectOutbound`) and scoped by the BYO token's status-write scope (Epic 7) — never a shared
  token, never logged (11.1 AC5 carries).

## Testing

- **Runnable check:** `python3 docs/bmad/spikes/bench/scm-issue-mirror-check.py` → **exit 0** —
  baseline GREEN on C1–C5; mutation battery all CAUGHT, no vacuous survivors.
- **Deferred to Epic 11 build (integration):** the real `scm_issue_mirror` upsert + link resolution +
  LWW/audit resolver + optional outbound reflect, proven against a live GitHub by the operator/
  apiserver integration suite (issue change → mirror row → console badge; conflict → audit row;
  reflected write → echo-suppressed).

## References

- [Source: docs/bmad/04-epics-and-stories.md] — Epic 11 row 11.2 (issues ⇄ work items; provenance;
  LWW + audit).
- [Source: docs/bmad/stories/11-1-repo-sync-reconciler.md] — the loop (idempotent upsert, provenance,
  echo-suppression, field-ownership) 11.2 rides.
- [Source: docs/bmad/stories/11-5-provider-seam-explicit.md] — the frozen `SourceControlProvider.Issues`
  seam.
- [Source: docs/bmad/03-architecture.md#5.4] — reconciler & mirror; §7.3.2 (untrusted-external), §6.1
  (`work_item`), §6.5 (audit), §6 (no-P2P), §5.1 (`repo.sync.mirror`/`reflectOutbound`). ADR-001,
  ADR-018.
- [Source: docs/bmad/stories/8-14b-kanban-board-view-and-dnd.md] — a downstream consumer (SCM-synced
  tickets show provenance badges).

## Dev Agent Record

_(empty — spec authored by the Story Writer; the build wave fills this in.)_
