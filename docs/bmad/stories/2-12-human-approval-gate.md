# Story 2.12: Human-approval gate + approve/reject coordination action

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **⛔ THIS IS A NO-P2P GUARDRAIL STORY (FR-B3, R13).** The approval gate is **human-in-the-loop**, not
> an agent-to-agent channel. An agent may **raise** a gate and **read** its state; an agent may **never**
> approve or reject on a human's behalf. Approve/reject is written **by an authorized human principal**
> through the apiserver — a **write-level** membership on the Project. A path that lets an agent resolve
> its own gate, or that brokers the decision agent↔agent, is a **coordination back-channel** and a
> locked-decision violation, not a feature. Read AC3, AC4, and AC6 literally.

## Story

As an **agent that has reached a point on a work item where a human must decide before work continues**,
I want **to raise a durable, provenanced human-approval gate that blocks the item and releases my fenced checkout — resolvable only by an authorized human's provenanced approve or reject**,
so that **work needing human sign-off blocks safely in the coordination record until a person acts, surfaced on the dashboard Pending Approvals queue (8.8c), with the decision always written by a human — never brokered agent↔agent (FR-B3, no-P2P).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.9 **FR-I5** — the Pending Approvals requirement: an agent MAY raise a human-approval gate (a first-class, durable state in the coordination record §6.1); the gated item **blocks** until an **authorized** human (write-level on that Project) **approves or rejects**; the decision is a **provenanced, append-only** record; **scope guard:** human-in-the-loop, never brokered agent↔agent (§6.1 no-P2P, R13).
- **Architecture:** `docs/bmad/03-architecture.md` §13 **r24** ("Pending Approvals — a human-in-the-loop work-item gate, coordination-free by construction") — `blocked_reason=needs_approval` on the **existing** §6 work-item `blocked` state (**not** a new machine, **not** a Run `Paused`; the Run **releases its fenced checkout** §6.3 and completes); durable provenanced row in `coord` (§6.1/§6.5); an authorized human (write-level §12.3) approves → item returns to `open`/re-dispatch, rejects → resolves with provenanced rationale; **never brokered agent↔agent**. Also §6 (coordination record + `blocked_reason`), §6.2/§6.3 (claim/lease/fence — release path), §8 (blocked machinery), §12.3 (RBAC write-gate).
- **Observability:** `docs/bmad/04-observability-plan.md` §17.2 — two cheap bounded signals this story emits: `ksquad.approval.pending` (gauge, label `project`) on gate raise/resolve, and `ksquad.approval.decisions.total` (counter, labels `project`, `outcome ∈ approve|reject`) on each human decision. `user.id`/`work_item.id`/`run.id` stay **exemplars, never labels**. The **authoritative** who-approved-what is the coordination record + §16.4 security audit log (`initiated_by_user_id`); these metrics are **aggregate legibility only**.
- **Depends on (must be landable/mergeable before this story is done):**
  - **Epic 2 core** — the coordination record (`work_items` with the `blocked` state + `blocked_reason`, `comments` append-only, `checkouts` with fenced release; §6.1/§6.2/§6.3). This story **adds a `blocked_reason` value + an approve/reject action**, reusing the existing block + fenced-release machinery — **not** a new state machine.
  - **Epic 15.4 / §12.3** — the deny-by-default RBAC middleware, so approve/reject is gated on **write-level** (contributor/maintainer) membership and a **viewer** is `403`'d. If 15.4 is not yet merged, wire the write-gate behind its interface and mark the live RBAC test `skip` with `TODO(15.4)` — but the gate must route through that check, never a bespoke one.
- **Backs:** **8.8c** (the Pending Approvals widget) — 8.8c is the **console surface** of the queue this story makes durable; the **gate mechanism + approve/reject action are this story**. 8.8c must not ship its approve/reject affordance until this story's action + RBAC write-gate are green.

## Acceptance Criteria

**AC1 — raise the gate: `blocked_reason=needs_approval` on the existing block (no new machine).**
Given a work item an agent decides needs human sign-off, When the agent **raises** the gate, Then the item enters the **existing `blocked` state** with **`blocked_reason=needs_approval`** — a **new reason value on the already-present §6 work-item block**, **not** a new state machine and **not** a Run-level `Paused`. And `needs_approval` is a durable enum value on the coordination record's `blocked_reason` — no new table, no new machine.

**AC2 — the Run releases its fenced checkout on raise (nothing runs against the item until resolved).**
Given the agent raises the gate from within a Run holding the item's checkout, When the gate is raised, Then the Run **releases its fenced checkout** (§6.3) and completes — the item's lease is freed, so **nothing runs against the item** until a human resolves the gate. And the release is the **existing fenced release path** (§6.2/§6.3) — a resurrected stale holder is fenced out by `holder` identity + monotonic `lease_epoch` and **cannot** resume-clobber the gated item (same discipline as reclaim, story 2.4). The gate does **not** hold a lease open or park a Run in `Paused`.

**AC3 — the gate is a durable, provenanced, append-only row in the coordination record.**
Given the raised gate, When it is recorded, Then it is a **durable, provenanced row** in the `coord` record (§6.1/§6.5) carrying **who raised it** (the raising agent/Run provenance), **when**, and the **work item**. And the raise and every subsequent decision are **append-only** (no UPDATE/DELETE of the audit rows — consistent with §6.1 append-only `comments`/`audit_log`). The gate's provenance chain (raised-by → decided-by) is queryable as part of the audit trail (story 2.6).

**AC4 — approve/reject is written by an authorized HUMAN principal (the no-P2P crux).**
Given a gated item, When it is resolved, Then the resolution is written **by a human principal** with **write-level membership** on the Project (§12.3/Epic 15.4) via the apiserver — **approve** → item returns to **`open`** (re-dispatchable through the normal open-item → fenced-claim path, 2.2), **reject** → item resolves with the **human's provenanced rationale**. And the decision row records `initiated_by_user_id` (§6.5) — the concrete human actor. And an **agent can never write the decision**: the approve/reject action **rejects any non-human / agent-asserted principal** — an agent may `raise` (AC1) and `read` (AC5) the gate but has **no** approve/reject capability (FR-B3, no-P2P). Verify with a test that an agent-authenticated call to approve/reject is denied irrespective of Project membership.

**AC5 — a viewer is 403'd; the gate is readable but not resolvable without write.**
Given the approve/reject action, When a caller with **viewer** (read-only) membership attempts it, Then the apiserver returns **`403`** (server-side authz, the deny-by-default wall §12.3) — the viewer may **read** the pending queue but cannot resolve a gate. And the write-gate is enforced **server-side**; hiding the affordance in the UI (8.8c) is defense-in-depth, **not** the gate. Positive control: a **write-level** (contributor/maintainer) human resolves successfully.

**AC6 — the whole loop rides shared work items + comments; no agent-to-agent channel (FR-B3).**
Given the raise → block → human-decision → re-dispatch loop, When it runs end-to-end, Then **every** step is a coordination-record operation on **shared work items + comments** (§6.1) — there is **no** agent-to-agent message, no lateral transport, no back-channel by which the raising agent is *told* the outcome. The raising agent (or any agent) learns the resolution **only** by **reading the coordination record** (the item returned to `open` and re-dispatched, or resolved) — the same read-of-record discipline as the coordinator feedback loop (2.9). A review-time covert-channel check (Epic 14 L4) must not find a path where the decision drives an agent directly.

**AC7 — approve → re-dispatchable; reject → resolved-with-rationale (state transitions).**
Given a resolved gate, When **approve**, Then the item leaves `blocked(needs_approval)` and returns to **`open`** — claimable again through the normal fenced-claim path (2.2), custody never handed to anyone (open-item → claim, not a P2P transfer). When **reject**, Then the item transitions to a **resolved** disposition carrying the human's **rationale** (a provenanced comment/field), and does **not** silently re-dispatch. And both transitions clear `blocked_reason=needs_approval` and are recorded append-only (AC3).

**AC8 — approval-queue observability (obs §17.2).**
Given gate raise/resolve and human decisions, When they occur, Then the coordination reconciler emits:
- `ksquad.approval.pending` — a **gauge** (up on raise, down on resolve), label **`project`** only — the count of items currently in `blocked(needs_approval)`; feeds the 8.8c KPI count + a **stale-approval** alert (obs §9) when it stays > 0 past an SLO age;
- `ksquad.approval.decisions.total` — a **counter**, labels **`project`** + **`outcome ∈ {approve, reject}`** (2-value enum) — human decision volume, driving the dashboard trend and an audit cross-check.
And `work_item.id` / `user.id` / `run.id` are **exemplars on the counter, never labels** (obs §1.2/§17.2). And the **authoritative** record of who-approved-what stays the **coordination record + §16.4 security audit log** (`initiated_by_user_id`) — these two metrics are **aggregate legibility, never the record of decision**.

**AC9 — NFR-OBS3 standing law (cardinality firewall).**
Given the two approval instruments, When telemetry is produced, Then: (a) `work_item.id`/`user.id`/`run.id` are **never** a metric label (exemplar-only); (b) `outcome` is a **bounded 2-value enum**, `project` is a **bounded scope dim** — no unbounded label; (c) **no `model` label**; (d) the metrics are **legibility**, never a consumption/billing axis. Verified by the Epic 14 cardinality CI gate (extend it to keep `work_item.id`/`user.id`/`run.id` off these two instruments' labels, obs §17.2 handoff).

## Tasks / Subtasks

- [ ] **Task 1 — Add the `needs_approval` gate on the existing block (AC1, AC2, AC3).** *Reuse §6 block + §6.3 fenced release — do not build a new machine.*
  - [ ] Add `needs_approval` as a value of the existing `blocked_reason` enum on the coordination record (§6.1) — no new table, no new state machine, no migration beyond the enum value.
  - [ ] Implement **raise-gate**: from a Run holding the item's checkout, set the item `blocked(needs_approval)` and **release the fenced checkout** (§6.3, the existing release path) in one transaction — the Run then completes; the item's lease is freed. Assert a stale holder is fenced out by `holder` + `lease_epoch` (reuse 2.4 fencing; add a fenced-clobber test).
  - [ ] Record the raise as a **durable, provenanced, append-only** row (who/when/work-item, §6.5).
- [ ] **Task 2 — The human approve/reject coordination action (AC4, AC5, AC7).**
  - [ ] Add the apiserver action (e.g. `POST /api/work-items/{id}/approval {decision: approve|reject, rationale?}`) — **GET-free** mutation gated by the deny-by-default RBAC middleware at **write-level** (contributor/maintainer, §12.3/Epic 15.4).
  - [ ] **Reject any non-human / agent-asserted principal** — only a human principal may write the decision (AC4 no-P2P crux). Agent-authenticated call → denied regardless of membership.
  - [ ] **Viewer → `403`** server-side (AC5). Write-level human → success (positive control).
  - [ ] On **approve**: clear `blocked_reason`, transition item → `open` (re-dispatchable via 2.2 fenced claim — custody via open-item→claim, never P2P transfer). On **reject**: transition → resolved with the human's **provenanced rationale** (append-only comment/field). Record `initiated_by_user_id` (§6.5) on both.
  - [ ] If Epic 15.4 not yet merged, wire the write-gate behind its interface; `skip` the live RBAC test with `TODO(15.4)` — the gate still routes through the middleware seam.
- [ ] **Task 3 — No-P2P end-to-end proof (AC6).**
  - [ ] Add a test exercising raise → block → human decision → read-of-record: the raising agent learns the outcome **only** by reading the coordination record (item `open`+re-dispatched, or resolved) — **no** message delivered agent↔agent.
  - [ ] Assert the API surface has **no** agent-to-agent approval channel and an agent cannot resolve its own (or any) gate.
  - [ ] Tag the case so the Epic 14 L4 covert-channel review tracks it (no back-channel drives an agent from the decision).
- [ ] **Task 4 — Approval-queue observability (AC8, AC9).**
  - [ ] Emit `ksquad.approval.pending` (gauge, label `project`) from the coordination reconciler on gate **raise** (+1) and **resolve** (−1).
  - [ ] Emit `ksquad.approval.decisions.total` (counter, labels `project`, `outcome`) on each human decision; attach `work_item.id`/`user.id`/`run.id` as **exemplars**, never labels.
  - [ ] Ensure the **authoritative** decision record is the coordination record + §16.4 security audit log (`initiated_by_user_id`) — the metrics are aggregate only.
  - [ ] **Standing-law self-check (AC9):** no per-item ids as labels, `outcome` bounded 2-value, no `model` label; extend the Epic 14 cardinality gate to keep `work_item.id`/`user.id`/`run.id` off these two instruments.
- [ ] **Task 5 — Audit-trail integration (AC3, AC7).**
  - [ ] Confirm the raise + both decisions appear in the queryable audit trail (story 2.6) as append-only rows, joinable by work item / actor / time, carrying the raised-by → decided-by provenance chain.

## Dev Notes

- **This is a `blocked_reason`, not a new state machine.** Arch §13 r24 is emphatic: `needs_approval` is a **new reason on the existing §6 work-item block**, **not** a new machine and **not** a Run `Paused`. The Run does **not** park in `Paused` holding a lease — it **releases the fenced checkout** (§6.3) and completes, exactly like any other block. Reuse the block + fenced-release + reclaim machinery from Epic 2 (2.2–2.4); do not invent a parallel approval state.
- **The no-P2P line is the reason this story exists as a guardrail (R13, FR-B3).** An agent raising a gate and then being *told* "approved" by another party would be an agent-to-agent coordination channel — forbidden. The only legitimate loop is **agent raises (write to record) → item blocks → human decides (write to record) → agent re-learns by reading the record**. Approve/reject is written by a **human principal**; the action must reject an agent-asserted principal even with Project membership. If you find yourself delivering the outcome to the raising agent, you've reintroduced the back-channel — stop.
- **404 vs 403, and existence.** Unlike the build-browser per-principal gate (which hides existence with `404`), the approval write-gate is a **capability** gate on a Project the caller can already see: a viewer who can read the queue gets a **`403`** on approve/reject (they know the item exists; they lack write). Do not conflate this with the build-browser existence-hiding — different surface, different rule (§12.3 deny-by-default returns the shape appropriate to the resource's visibility).
- **Custody is never transferred.** Approve returns the item to `open`; the next holder **claims** it through the normal fenced path (2.2). The human does not hand custody to an agent, and no agent hands custody to another. Same discipline as reclaim (2.4) and handoff (2.8): open-item → fenced claim, never a lease handoff.
- **Metrics are legibility, not the record.** The authoritative who-approved-what is the coordination record + the §16.4 security audit log (`initiated_by_user_id`). `ksquad.approval.pending` / `.decisions.total` exist for the KPI count, the stale-approval alert, and the trend — they carry `project`/`outcome` labels and per-item ids **only as exemplars**. Never alert on per-item labels; alert on `approval.pending` age.

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield Go monorepo — only `pkg/auth/*_test.go` + `console/e2e/auth/` exist; no `internal/`, no `migrations/`, no `go.mod` checked in on this branch. The coordination record (Epic 2, §6.1) is where this story lives — implement the `blocked_reason` value + approve/reject action in the coordination package alongside the existing claim/lease/block code, following `pkg/auth` conventions (lowercase package, standard `testing`, table-driven `_test.go`). Do **not** assume an `internal/discussion` tree (referenced by older story files) exists — it does not in this checkout.
- **Migration:** adding the `needs_approval` enum value is a **forward-only** SQL migration on the existing `work_items.blocked_reason` (versioned, per story 2.1 discipline) — one enum value, no new table.
- **Apiserver (Go):** the approve/reject action is an authoritative apiserver mutation behind the deny-by-default RBAC middleware; the console (8.8c) is a thin surface over it. The human-principal check + write-level gate live server-side, never only in the BFF.

### References

- [Source: docs/bmad/02-prd.md#9.9 FR-I5] — human-approval gate; durable first-class state in coordination record; authorized human (write-level) approves/rejects; provenanced append-only; human-in-the-loop, never agent↔agent (§6.1 no-P2P, R13).
- [Source: docs/bmad/03-architecture.md#13 (r24) — Pending Approvals, a human-in-the-loop work-item gate] — `blocked_reason=needs_approval` on the existing block (not a new machine, not a Run `Paused`); Run releases fenced checkout §6.3; durable provenanced row; write-level human approve→open/reject→resolved; never brokered agent↔agent.
- [Source: docs/bmad/03-architecture.md#6.2/#6.3 — claim/lease/fence + fenced release] — the release + fencing machinery this story reuses (stale holder fenced out by holder + lease_epoch).
- [Source: docs/bmad/03-architecture.md#12.3 — deny-by-default RBAC, write-level membership] — the write-gate; viewer 403; server-side enforcement.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 2 row 2.12] — epic-level AC (raise gate, release checkout, provenanced row, write-level approve/reject, viewer 403, no agent↔agent channel); backs the 8.8c widget.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 2 rows 2.5/2.8/2.9] — FR-B3 no-P2P discipline; read-of-record, never P2P; the coordinator feedback-loop precedent (2.9).
- [Source: docs/bmad/04-observability-plan.md#17.2 — Pending-approvals signals] — `ksquad.approval.pending` gauge (`project`), `ksquad.approval.decisions.total` counter (`project`,`outcome`); per-item ids exemplar-only; authoritative record = coord + §16.4 audit log; stale-approval alert.

### Open questions (route to the named owner via ISI-2325; do not block the guardrail on these)

1. **Re-dispatch target on approve (Architect / Winston).** On approve → `open`, does the item re-enter the general open-item pool (any eligible Run claims, 2.2) or does it return to a designated Run/agent? This story assumes the **general open-item → fenced-claim** path (no custody transfer). Confirm no directed re-dispatch is expected. *Does not block the gate or the no-P2P proof.*
2. **Rejection terminal state (PM / Architect).** Is a **rejected** item terminal (resolved/closed) or reopenable by a human later? This story treats reject as a resolved disposition with rationale; confirm whether a human may subsequently reopen it (a normal state transition, not a new gate).

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
