# Story 8.14a: coord human status-transition endpoint (`PATCH /work-items/{id}/state`)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **This is the ONE new backend mutation the dual-view Tickets screen adds (ADR-037).** Everything else in
> 8.14 reads the existing `coord` path unchanged. Read every AC literally — a `200` where a `409` is
> required (stale drag), or a transition that **acquires the agent's fence/lease**, is a correctness
> regression against the §6 coordination model, not a cosmetic bug.

## Story

As the **operator console's edge (coord)**,
I want a **human status-transition endpoint `PATCH /api/v1/work-items/{id}/state {to, expectedFrom}`** that moves a work item's `state` as a **conditional, audited, RBAC-gated operator override which does not take the work-item fence/lease**,
so that **drag-and-drop (8.14b) and quick-move can advance a ticket's status safely under concurrency with the agent that may be actively working it — a human authority path distinct from the agent claim, never a lost-update and never a fight over the lease (§6.2/§6.4).**

## Context & prerequisites (read first)

- **Architecture:** `docs/bmad/03-architecture.md` §13 "Project → Tickets — dual view" (the DnD → status-update API paragraph), §8.6 (`blocked` refined to an orthogonal condition, **not** a workflow state), §6.1 (`work_item` cardinality + canonical ordered `state` enum), §6.4 (conditional-UPDATE / optimistic-concurrency discipline the agent path already uses), §6.5 (audit + `initiated_by_user_id`), §6.6 (domain event on transition), §12.1/§12.3 (tenancy + per-project RBAC). **ADR-037** (Issues dual-view — board-state derivation + human DnD status transition) and its rejected-alternatives column are the design contract.
- **Testing:** `docs/bmad/05-testing-strategy.md` §3.2(c) "DnD status accuracy" (the server semantics this endpoint must satisfy: one PATCH, 409-on-stale, viewer-denied, **no** claim/lease call) + §6.7 the RBAC matrix this endpoint is a row of.
- **Epics:** `docs/bmad/04-epics-and-stories.md` — the 8.14 umbrella row + the "Epic 8.14 story slicing" subsection (8.14a here).
- **Depends on:** **Epic 2** (the `coord` record, `work_item` table + the canonical `state` enum + the fenced claim/lease rows) and **Epic 15.4** (identity-propagation + deny-by-default RBAC middleware that resolves `{user.id, global_role, project_memberships}`). If 15.4's middleware is not yet mergeable, wire the handler behind the same middleware interface and gate the RBAC integration test with `TODO(15.4)` — but the **conditional-UPDATE core + 409 semantics + no-fence assertion (the deliverables of this story) do not depend on it** and must be fully implemented and tested.
- **Blocks:** **8.14b** (Kanban DnD calls this endpoint). 8.14c (List) and 8.14d (search/filter) do **not** depend on it.

## Acceptance Criteria

**AC1 — the route + shape.**
Given the coord API, When it is deployed, Then exactly one new route exists: `PATCH /api/v1/work-items/{id}/state` accepting a JSON body `{ "to": <state>, "expectedFrom": <state> }`. And no other verb is added to `…/state` (a `GET`/`POST`/`DELETE` on it is `405` or structurally absent). This is the **only** new mutation in the 8.14 epic.

**AC2 — conditional UPDATE, guarded on the shown state (optimistic concurrency).**
Given a work item currently at `state = S`, When `PATCH …/state {to:T, expectedFrom:S}` is applied, Then the store performs a single conditional UPDATE `SET state = :to, updated_at = now(), … WHERE id = :id AND state = :expectedFrom` and, on exactly-one-row-matched, returns **`200`** with the updated `work_item` row (new `state`, new `updated_at`). The update is a single atomic statement — never a read-then-write race.

**AC3 — stale `expectedFrom` → `409`, no lost-update.**
Given a work item whose `state` has already advanced away from `expectedFrom` (e.g. an agent moved it `todo → in_progress` between the board render and the drag), When `PATCH …/state {to:T, expectedFrom:S_old}` is applied, Then zero rows match the `WHERE state = :expectedFrom` guard and the endpoint returns **`409`** carrying the **current** state (so the client can re-sync). And the row is **not** modified. **No last-writer-wins**: the concurrent change is never silently clobbered.

**AC4 — `to` is a valid workflow state; `blocked` is not a state.**
Given the body, When `to` is validated, Then it must be one of the canonical ordered enum `{backlog, todo, in_progress, in_review, done}` — anything else → **`400`**. And **`blocked` is explicitly rejected as a `to`** — it is an **orthogonal condition** (a flag + reason, §8.6), never a workflow state, and is set/cleared through its own condition path, **never** through `/state`. (A blocked item keeps its workflow `state` and shows a badge — five columns, not six.)

**AC5 — RBAC-gated: contributor/maintainer write, viewer read-only.**
Given the Epic 15.4 middleware-resolved caller, When the endpoint is hit, Then it authorizes a **write** only for a caller with **`contributor`** or **`maintainer`** membership on the item's Project; a **`viewer`** → **`403`**; an unauthenticated caller → **`401`**; and a caller with **no membership** on the item's Project, or an `id` outside the caller's tenant scope, → **`404`** (existence-hiding — do not confirm the item exists to an out-of-scope caller, §12.1/§8.7d). The RBAC check is server-side and **not** the UI gate (8.14b's disabled DnD is defense-in-depth only).

**AC6 — audited with the human principal.**
Given a successful transition, When the row is written, Then the `coord` audit records the transition with **`initiated_by_user_id`** = the resolved human caller (§6.5) — distinct from any agent `Run.id` principal — and a domain event is emitted (§6.6, same journal→NATS path §17.4 as the agent transitions). The audit answers "which human moved this, from what, to what, when".

**AC7 — the human transition does NOT take the fence/lease (the crux).**
Given a work item with a **live agent claim** (an active checkout/lease + fencing token, §6.2), When a human `PATCH …/state` succeeds, Then the transition **does not acquire, renew, bump, or release the fence/lease** — the claim/lease row is left **byte-identical** (holder, fence token, lease expiry all unchanged). The human path is an **operator override on `state` only**; the agent's next fenced write still obeys §6.3 (holder AND fence AND unexpired lease). **Assert the claim row is unchanged before/after** in the test — this is the property that keeps the human path from fighting the agent for custody (ADR-037 rejected "DnD acquires the agent's fence/lease").

**AC8 — control-plane-mediated, no-P2P.**
Given the transition, When it is applied, Then it flows through the apiserver/coord service (the §13 BFF choke point) as a control-plane-mediated coord write — never a client-authored state change and never a lateral agent channel. The BFF proxies it; the browser never touches Postgres/kube directly.

**AC9 — runnable store-level test (the concurrency core).**
Given the `pkg/coord` store method behind the handler, When a self-contained Go test exercises it against a test DB (table-driven, no console, no cluster), Then it asserts: (a) `{to:in_progress, expectedFrom:todo}` on a `todo` item → 1 row, `200`, state now `in_progress`; (b) the same call when the item is already `in_progress` → **0 rows → `409`**, state unchanged; (c) `to:blocked` → rejected (`400`); (d) a two-caller race (two conditional UPDATEs with the same `expectedFrom`) → **exactly one wins, the other `409`s** (no double-apply); (e) a live claim row is **unchanged** after a successful transition (AC7). The test lives next to the store implementation and fails if the guard logic breaks.

## Tasks / Subtasks

- [ ] **Task 1 — Store method `TransitionState(ctx, id, to, expectedFrom, initiatedByUserID) (WorkItem, error)` (AC2, AC3, AC4, AC7, AC9).** *Do this first — it is the concurrency core and needs no HTTP/console.*
  - [ ] Implement the single conditional UPDATE `… SET state=:to, updated_at=now() WHERE id=:id AND state=:expectedFrom` returning the updated row; **0 rows matched → typed `ErrStaleTransition`** carrying the current state (a follow-up point-read of `state` for the 409 body).
  - [ ] Validate `to ∈ {backlog,todo,in_progress,in_review,done}`; reject `blocked` and any other value with a typed `ErrInvalidState`.
  - [ ] Write the transition to the audit with `initiated_by_user_id` and enqueue the domain event on the existing outbox/journal (§6.5/§6.6) **in the same transaction** as the state UPDATE (no dual-write hole).
  - [ ] **Do NOT touch the claim/lease row.** No lease renew/acquire/release in this path. Add the table-driven test (AC9) incl. the race case and the **claim-row-unchanged** assertion.
- [ ] **Task 2 — HTTP handler `PATCH /api/v1/work-items/{id}/state` (AC1, AC2, AC3, AC4).**
  - [ ] Parse/validate the body; map `ErrStaleTransition → 409` (current state in body), `ErrInvalidState → 400`, success → `200` with the updated row.
  - [ ] Confirm only `PATCH` is routed on `…/state`; other verbs `405`/absent.
- [ ] **Task 3 — RBAC + tenancy gate (AC5, AC8).**
  - [ ] Behind the Epic 15.4 middleware: resolve the caller; require `contributor|maintainer` on the item's Project for the write; `viewer → 403`, unauthenticated → `401`, out-of-scope/no-membership → `404` (existence-hiding).
  - [ ] Ensure the item's `project_id` is resolved and tenancy-scoped (§12.1) **before** the transition — never leak existence via a distinguishable 403/404. If 15.4 is not yet mergeable, wire behind its interface and `skip` the RBAC integration test with `TODO(15.4)`; the core (Tasks 1–2) does not depend on it.
- [ ] **Task 4 — BFF proxy shape (AC8).**
  - [ ] Expose the endpoint through the apiserver BFF so the console (8.14b) calls it, never Postgres/kube directly. If the Next.js BFF is not yet scaffolded, a thin proxy stub with a `TODO` is acceptable — the authoritative Go coord handler + AC9 store test are the non-negotiable deliverables here.

## Dev Notes

- **Repo shape (current).** k8squad is the Go code repo; `pkg/auth/` already exists (the auth-session work, ISI-2311). Create this under **`pkg/coord/`** following the `pkg/auth` package conventions (`store.go` / `handler.go` / `*_test.go`, lowercase package, table-driven `_test.go`, the standard `testing` package). Do **not** introduce a new test framework.
- **`expectedFrom` is the whole point.** ADR-037 rejected last-writer-wins precisely because an agent can advance an item between the board render and the human drag. The `WHERE state = :expectedFrom` guard + `409` is the cheap, correct fix — the same optimistic-concurrency discipline the agent path uses at §6.4. Do not "fix" a 409 by retrying server-side; the client (8.14b) re-syncs and the human re-drags if they still want to.
- **No fence, ever.** A human moving `state` is **not** competing for the work-item claim. Taking the lease would fight the live agent and violate the per-item custody model (§6.2/§6.3). The human path writes `state` + audit + event and nothing else on the coordination row. If you find yourself calling a claim/lease helper here, stop — that is the ADR-037 rejected design.
- **`blocked` is not on this axis.** `/state` moves the workflow lane only. `blocked` is a separate condition (flag + reason) with its own set/clear path (agent-set at §8.6, or a human via the approval/block gate — out of scope for this story). Rejecting `to:blocked` here is a guard, not a TODO.
- **404 vs 403.** A `viewer` who *can* see the Project gets `403` on the write (they legitimately see the item, just can't move it). A caller with **no** membership / cross-tenant gets `404` (existence-hiding). Keep these distinct-by-design and test both.

### Project Structure Notes

- **Go:** `pkg/coord/` — `store.go` (the `TransitionState` conditional UPDATE + audit/event in one tx), `handler.go` (the PATCH route + status mapping), `store_test.go` (AC9 table + race + claim-unchanged), `handler_test.go` (status codes / RBAC). Mirror `pkg/auth` naming.
- **Migration:** none required — `state` and the claim/lease rows already exist (Epic 2, §6.1). This story is a new **write path** over existing schema, not a schema change.
- **BFF:** the Next.js console app may not yet be in the repo; the Go coord handler + store test land here regardless (see Task 4).

### References

- [Source: docs/bmad/03-architecture.md#13 Project → Tickets — dual view] — DnD → status-update API: `PATCH …/state {to, expectedFrom}`, conditional UPDATE, 409-resync, no fence/lease, `initiated_by_user_id`, contributor/maintainer write.
- [Source: docs/bmad/03-architecture.md#8.6] — `blocked` refined to an orthogonal condition (flag + reason), not a workflow state.
- [Source: docs/bmad/03-architecture.md#6.4] — conditional-UPDATE / optimistic-concurrency discipline (the agent path this mirrors); §6.5 audit + `initiated_by_user_id`; §6.6 domain event.
- [Source: docs/bmad/03-architecture.md#18 ADR-037] — dual-view board-state derivation + human DnD status transition; rejected alternatives (stored `board_column`, 6th column for blocked, DnD-acquires-lease, last-writer-wins, client-authored state).
- [Source: docs/bmad/05-testing-strategy.md#3.2 Dual-view Tickets (c)] — DnD status accuracy: one PATCH, 409-on-stale-resync, viewer-disabled, no claim/lease call.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.14 story slicing, 8.14a] — epic-level AC + deps.

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
