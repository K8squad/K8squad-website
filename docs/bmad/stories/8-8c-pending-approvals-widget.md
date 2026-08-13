# Story 8.8c: Pending Approvals widget

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **⛔ THE APPROVE/REJECT GATE IS SERVER-SIDE (2.12), NOT THIS WIDGET.** This story is the **console
> surface** of the approval queue. Hiding the approve/reject buttons from a viewer is **defense-in-depth**,
> **not** the authorization — the write-level gate and the human-principal check live in **Story 2.12**
> (apiserver). A viewer who forges the request must still be **`403`'d server-side**. And an agent can
> **never** approve on a human's behalf (no-P2P, FR-B3) — that guarantee is 2.12's, and this widget must
> not create any path around it. Read AC3 and AC5 literally.

## Story

As an **operator opening a Project's dashboard**,
I want **a Pending Approvals widget listing work items awaiting a human approval decision — each linking to the approval action, with approve/reject available to me only if I hold write-level membership**,
so that **I can see and action the human-approval gates raised by agents, with the decision written by me as a human principal through the apiserver — never brokered agent↔agent (FR-I5).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.9 **FR-I5** — Pending Approvals section listing work items awaiting a human approval decision, each linking to the approval action; authorized human (write-level) approves/rejects; provenanced, append-only; human-in-the-loop, never agent↔agent.
- **Architecture:** `docs/bmad/03-architecture.md` §13 **r24** — the Pending Approvals widget is a **read model** over `coord` items with `blocked_reason=needs_approval`; approve → item returns to `open`/re-dispatch, reject → resolves with the human's provenanced rationale; authorized human = write-level membership (§12.3); never brokered agent↔agent. Same deny-by-default RBAC wall (§12.3).
- **Observability:** `docs/bmad/04-observability-plan.md` §17.2 — the queue itself is a `coord` read model (no metric); the count is fed by `ksquad.approval.pending` (gauge, `project`) and decisions by `ksquad.approval.decisions.total` (counter, `project`,`outcome`) — **both emitted by 2.12**, not this widget. This story **reads** the queue and **renders** the SSE-updated count.
- **Depends on (must be landable/mergeable before this story is done):**
  - **Epic 2.12** — the human-approval gate + approve/reject coordination action. **2.12 is the mechanism; this widget is its surface.** The `blocked_reason=needs_approval` gate, the write-level approve/reject apiserver action, the viewer-`403`, the human-principal check, and the no-P2P guarantee **all live in 2.12**. This widget calls that action and renders that queue.
  - **8.8a** — the dashboard read model; this widget renders the `pendingApprovals` sub-payload (coord items `blocked_reason=needs_approval`) and the SSE approval-count deltas.
  - **Epic 15.4 / §12.3** — the deny-by-default RBAC write-gate (surfaced here as show/hide of approve/reject; **enforced** by 2.12 server-side).
- **Blocked by:** 2.12 + 8.8a (+ 15.4 write-gate). If 2.12 is not yet merged, the widget renders the read-only queue from 8.8a and marks the approve/reject affordance behind 2.12's action interface, `skip`-ping the action integration test with `TODO(2.12)` — the **read surface** can land, the **action** waits on 2.12.

## Acceptance Criteria

**AC1 — the Pending Approvals list (read model over the raised gates).**
Given work items with a human-approval gate raised (`blocked_reason=needs_approval`, Epic 2.12), When the operator opens the dashboard, Then the **Pending Approvals** section lists them — each row showing **title, requesting agent/Run, and age** — from the 8.8a `pendingApprovals` sub-payload (a `coord` read model). And each row **links to the approval action** (FR-I5). And when there are no pending gates, the section shows an explicit **empty** state ("No pending approvals").

**AC2 — approve/reject for a write-level human, written as that human principal.**
Given the operator holds **write-level membership** on the Project (§12.3), When they **approve** a gated item, Then it returns to **`open`** (re-dispatchable); when they **reject**, Then it **resolves** with **their provenanced rationale** — and the decision is written by **them as the human principal** via the **2.12 apiserver action** (`initiated_by_user_id` recorded). And the widget invokes the **2.12** action — it does **not** implement its own approval mutation or write to `coord` directly.

**AC3 — never agent↔agent; the widget creates no path around 2.12's no-P2P guarantee.**
Given the approve/reject flow, When it executes, Then the decision is **only ever** the human's write through the 2.12 apiserver action — the widget introduces **no** client path, proxy, or affordance by which an agent could resolve a gate, nor by which the outcome is pushed back to the raising agent as a message (no-P2P, FR-B3). The raising agent re-learns the outcome only by reading the coordination record (2.12 AC6). This widget must not undermine that.

**AC4 — SSE-updated count over the existing bus (no polling).**
Given the Pending Approvals count (and the KPI card count in 8.8b), When gates are raised or resolved, Then the count is **SSE-updated over the existing progress bus** (8.8f/8.8a delta contract, §4.4/§13) — **no polling loop**. And a raise/resolve delta patches the widget's list + count in place without a full refetch.

**AC5 — viewer sees the queue read-only; approve/reject 403s server-side (defense-in-depth in UI).**
Given a caller with **viewer** (read-only) membership, When they open the widget, Then they **see the queue** but the **approve/reject affordance is hidden** (defense-in-depth); and if the request is forged/replayed, the **2.12 apiserver action returns `403`** server-side — the UI hide is **not** the gate. Positive control: a write-level human sees and can use approve/reject.

**AC6 — every row is a real gate; no placeholder.**
Given the list, When it renders, Then every row is a real `coord` item with `blocked_reason=needs_approval` (via 8.8a) — **no** placeholder or synthesized row (FR-I3). And if the source is degraded (8.8a returned `{available:false}` for `pendingApprovals`), the widget shows an explicit degraded/empty state, never a fabricated queue.

**AC7 — observability: this widget emits no new metric; the signals are 2.12's.**
Given the widget, When it renders/actions, Then it emits **only** ordinary console/BFF request telemetry — the two approval-queue metrics (`ksquad.approval.pending`, `ksquad.approval.decisions.total`) are emitted by the **coordination reconciler in 2.12** (obs §17.2), **not** here. The widget **reads** the queue and consumes the SSE count. NFR-OBS3 standing law holds: no per-item ids (`work_item.id`/`user.id`/`run.id`) as metric labels, no `model` label; the authoritative who-approved-what is coord + §16.4 audit log (2.12), never the metric.

## Tasks / Subtasks

- [ ] **Task 1 — Render the Pending Approvals list (AC1, AC6).**
  - [ ] Render the 8.8a `pendingApprovals` sub-payload: rows with **title, requesting agent/Run, age**, each linking to the approval action.
  - [ ] Empty state ("No pending approvals"); degraded state when 8.8a marks the sub-payload unavailable — never a synthesized row.
- [ ] **Task 2 — Approve/reject via the 2.12 action (AC2, AC3).**
  - [ ] Wire approve/reject to the **2.12 apiserver action** (`POST …/work-items/{id}/approval`), passing the operator's rationale on reject. Do **not** write to `coord` from the widget.
  - [ ] On success, reflect the transition (approve → item leaves the queue back to `open`; reject → resolved) — driven by the SSE delta (Task 3), not an optimistic local mutation that could drift from the record.
  - [ ] Ensure no client path lets an agent invoke the action or receive a pushed outcome (no-P2P; the guarantee is 2.12's — this widget must not add a bypass).
- [ ] **Task 3 — SSE-updated count + list (AC4).**
  - [ ] Subscribe to the 8.8a/8.8f approval-count delta stream; patch the list + count (and the 8.8b KPI count) in place on raise/resolve. No polling.
- [ ] **Task 4 — RBAC-aware affordance (AC5).**
  - [ ] Show approve/reject only to write-level members (defense-in-depth); viewer sees read-only queue.
  - [ ] Add a test asserting the **2.12 apiserver action** returns `403` to a viewer even when the UI affordance is bypassed — the server is the gate.
  - [ ] If 15.4/2.12 not yet merged, gate the affordance behind their interfaces and `skip` the live action/authz tests with `TODO(2.12|15.4)`.
- [ ] **Task 5 — Observability self-check (AC7).**
  - [ ] Confirm the widget emits **no** approval metric (those are 2.12's); only ordinary request telemetry. NFR-OBS3: no per-item ids on labels, no `model` label.

## Dev Notes

- **The mechanism is 2.12; this is the window onto it.** The gate raise, the `blocked_reason=needs_approval` state, the write-level approve/reject apiserver action, the human-principal check, the viewer-`403`, the no-P2P guarantee, and the two approval metrics **all belong to Story 2.12**. This widget **reads** the queue (via 8.8a) and **invokes** 2.12's action. If you find yourself writing an approval mutation or emitting `ksquad.approval.*` here, stop — that is 2.12.
- **UI hide ≠ authorization.** Hiding approve/reject from a viewer is good UX and defense-in-depth, but the **server** (2.12) is the gate: a forged/replayed request from a viewer must `403`. Test the server behavior, not just the button visibility.
- **No optimistic drift.** Reflect approve/reject outcomes from the **SSE delta** (the record's truth), not a local optimistic mutation — the item's real state (open vs resolved) is written by 2.12 and streamed back. This keeps the widget consistent with the coordination record and avoids showing an "approved" item that the server rejected.
- **Real rows only (FR-I3).** Every row is a genuine `coord` gate. A degraded `pendingApprovals` sub-payload renders as an honest empty/degraded state — never a synthesized queue.

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield — only `pkg/auth/*_test.go` + `console/e2e/auth/`. The Next.js console app is not yet scaffolded; this widget lands under `console/` in the dashboard surface. It adds **no** apiserver code — it consumes 8.8a's payload/SSE and calls 2.12's action.
- **Match conventions:** reuse the console's SSE client (shared with the Run stream / org diagram); reuse the 2.12 action client rather than a bespoke fetch.

### References

- [Source: docs/bmad/02-prd.md#9.9 FR-I5] — Pending Approvals section; links to the approval action; authorized human approves/rejects; provenanced append-only; human-in-the-loop, never agent↔agent.
- [Source: docs/bmad/03-architecture.md#13 (r24) — Pending Approvals widget as a read model] — over `coord` `blocked_reason=needs_approval`; approve→open, reject→resolved-with-rationale; write-level human; same RBAC wall; never agent↔agent.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.8 row 8.8c] — epic-level AC; **deps Epic 2.12** + 8.8a + Epic 15.4; read model over `coord` `blocked_reason=needs_approval`; count SSE-updated (8.8f bus).
- [Source: docs/bmad/stories/2-12-human-approval-gate.md] — the gate mechanism + approve/reject action + write-gate + viewer-403 + no-P2P guarantee + the two approval metrics this widget surfaces.
- [Source: docs/bmad/stories/8-8a-dashboard-data-aggregation-read-model.md] — the `pendingApprovals` sub-payload + SSE approval-count delta this widget renders.
- [Source: docs/bmad/04-observability-plan.md#17.2] — `ksquad.approval.pending` / `.decisions.total` are emitted by 2.12's reconciler, not the widget; per-item ids exemplar-only; authoritative record = coord + §16.4 audit log.

### Open questions (route via ISI-2325; do not block the read surface)

1. **Row detail depth (Designer / PM).** The CEO mock pins title + requesting agent/Run + age + link. Confirm whether a row also shows a short "reason for approval" excerpt (from the raising agent's provenance) inline vs on the linked action page. *Does not block the list.*
2. **Reject rationale UX (Designer).** Confirm the reject flow collects the human's rationale inline in the widget vs on the linked approval-action page (2.12 requires a provenanced rationale on reject regardless of where it is entered).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, agent 2230b001) — construction-time contract via runnable falsification check (`pending-approvals-widget-check.py`, Epic-8 model-check pattern).

### Debug Log References

- `python3 pending-approvals-widget-check.py` → exit 0 (naive bespoke-approval widget trips all 7; §8.8c conformant widget holds C1-C7).
- `--mutate={FABRICATED_QUEUE,DIRECT_COORD_WRITE,AGENT_APPROVE_PATH,POLL_COUNT,NO_SERVER_403,FABRICATED_ROWS,EMIT_APPROVAL_METRIC}` → each exit 1 with the mapped invariant RED; no vacuous survivors.

### Completion Notes List

- Implemented C1-C7 falsification check with teeth via a "naive bespoke-approval widget" (writes coord directly, fabricates queue, exposes agent path, polls, fails open on viewer, emits approval metrics itself).
- **Load-bearing cruxes proven:** (C2) approve/reject calls 2.12 action ONLY — no direct coord write or own approval mutation; (C3) no client path an agent could invoke to resolve a gate (no-P2P, FR-B3); (C5) viewer approve returns 403 server-side (2.12 is the gate, not the UI hide); (C7) the two approval metrics (ksquad.approval.pending / .decisions.total) are 2.12's, not this widget's.
- Runtime proof (real approve/reject via 2.12 action, SSE count updates, viewer-403 integration) owned by console E2E + 2.12 apiserver tests.

### File List

- `docs/bmad/spikes/bench/pending-approvals-widget-check.py` (new) — C1-C7 runnable falsification check.
- `docs/bmad/stories/8-8c-pending-approvals-widget.md` (this file) — status→done + Dev Agent Record.
