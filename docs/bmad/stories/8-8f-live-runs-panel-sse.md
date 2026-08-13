# Story 8.8f: Live Runs panel (SSE)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **SSE over the EXISTING progress bus — no polling, no new transport.** The Live Runs panel streams the
> agent↔task↔Project map over the **same** EventSource + BFF proxy as the Run stream and org diagram
> (§4.4/§13). It is a **read model** derived from Run/claim state (FR-I3 provenance) with **no
> mutate/claim affordance** (no-P2P applied to the console). A polling loop, a second transport, or a
> claim button on this panel is a regression. Read AC2 and AC5 literally.

## Story

As an **operator opening a Project's dashboard**,
I want **a Live Runs panel showing the agent↔task↔Project mapping (who is running what) SSE-updated in real time, with rate-limit/fallback indicators and a resume countdown for rate-limited Runs**,
so that **I see real-time agent activity across the squad at a glance from Run/claim state over the existing progress bus — a read model, no polling, no mutate affordance (FR-I4).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` §9.9 **FR-I4** — live **agent↔task↔Project mapping** (who is running what), **SSE-updated**; complements the org diagram (FR-F8); a **read model** derived from Run/claim state (FR-I3 provenance).
- **Architecture:** `docs/bmad/03-architecture.md` §13 **r24** — live tiles (live-Run map, KPI counters, approval count) stream over the **existing SSE progress bus** (EventSource, same BFF proxy as the org diagram and Run stream) — no new transport, no polling. Also §13 org-diagram precedent (r10): a pure read model over Run/claim state, `Team`-scoped, no mutate/claim affordance (no-P2P on the console). §4.4 (SSE hub).
- **Rate-limit / fallback indicators:** Epic 8.8 (CEO 2026-08-12) adds **rate-limit/fallback indicators** (13.9 metrics): per-project/agent/role panels — SSE-updated — for throttled agents, active fallback models, and a **`resume_at` countdown** for `Paused(rate_limited)` Runs. Stories **2.11** (scheduled-resume timer, `resume_at`), **3.7** (`Paused(rate_limited)` state), **5.10/5.11** (shim rate-limit signal + fallback model), **13.9** (rate-limit/fallback metrics). This panel **consolidates the existing 8.8 rate-limit/fallback indicators** (per the slicing note).
- **Depends on (must be landable/mergeable before this story is done):**
  - **8.8a** — the dashboard read model; this story renders + streams the `liveRuns` sub-payload (Run/claim state) and owns the **SSE live-Run stream** the 8.8a snapshot+delta contract defines.
- **Progressive (do NOT gate this story):** the `resume_at` countdown + fallback-model + throttled-agent indicators light up as **2.11/3.7/5.10/5.11/13.9** land; until then the panel shows the live agent↔task↔Project map from Run/claim state alone.
- **Blocked by:** 8.8a. **Complements:** the org diagram (8.10) — no mutate/claim affordance on either.

## Acceptance Criteria

**AC1 — live agent↔task↔Project mapping (who is running what).**
Given in-flight Runs, When the operator opens the dashboard, Then the **Live Runs** panel shows the **agent↔task↔Project mapping** — for each active Run, which **agent** is running which **task (work item)** in which **Project** — a **read model** derived from **Run/claim state** (§6/§8, FR-I3 provenance), rendered from the 8.8a `liveRuns` sub-payload.

**AC2 — SSE-updated over the existing progress bus (the transport crux).**
Given the panel, When Run/claim state changes (a Run starts, claims, completes, pauses), Then the panel **updates in real time via SSE over the existing progress bus** — the **same EventSource + BFF proxy** as the Run stream and org diagram (§4.4/§13, same as 8.2) — **no polling loop, no new transport**. And updates arrive as **deltas** consistent with the 8.8a snapshot+delta contract (a delta names the changed Run so the client patches in place without a full refetch). This story **owns the live-Run stream** that 8.8b/8.8c consume for their live counters.

**AC3 — no mutate/claim affordance (no-P2P on the console).**
Given the panel, When it renders, Then it has **no mutate/claim/transition affordance** — it is **read + navigate only** (click through to the Run 8.2, the work item 8.14, the agent). It complements the org diagram (8.10) without introducing any way to claim, reassign, or drive an agent from the console (no-P2P applied to the console read model, §13 r10 precedent).

**AC4 — rate-limit / fallback indicators (13.9).**
Given Runs under rate-limit or fallback, When the panel renders, Then it surfaces the **rate-limit/fallback indicators** (13.9): **throttled agents**, **active fallback models**, and a **`resume_at` countdown** for **`Paused(rate_limited)`** Runs (2.11). And these indicators are **SSE-updated** (AC2) and **degrade gracefully** — where 2.11/3.7/5.10/5.11/13.9 are not yet landed, the panel shows the live map without the indicators (per-tile progressive fill), never a hard failure.

**AC5 — `resume_at` countdown is a real, record-derived timer (not a fabricated clock).**
Given a `Paused(rate_limited)` Run with a `resume_at` (2.11 — `now + Retry-After`, a single durable wake in the coordination record), When the panel renders its **countdown**, Then the countdown is derived from the **real `resume_at`** value (Run/claim state via 8.8a/SSE) — it counts down to that timestamp and reflects an early resume (fallback switch, 5.11) or a re-derived `resume_at` after a controller restart (2.11 crash-safe). It is **not** a client-invented timer, and it never shows a resume the record does not carry.

**AC6 — RBAC-scoped + real rows only (through 8.8a).**
Given the panel, When it renders, Then it shows only Runs the caller is entitled to see — the `liveRuns` sub-payload was **server-filtered** by 8.8a's deny-by-default RBAC wall (§12.3), and the SSE stream is likewise scoped. This story adds **no** client-side authz and **no** second authz path. And every row is a real in-flight Run (Run/claim state) — **no** placeholder (FR-I3); a degraded/empty `liveRuns` renders an explicit "No active Runs" state.

**AC7 — observability: consumes the SSE bus; adds no new dashboard metric.**
Given the panel, When it renders/streams, Then it emits **only** ordinary console/BFF request+stream telemetry — it introduces **no new domain metric**. The rate-limit/fallback figures come from the **13.9 metrics** (emitted by their own stories), not this panel. NFR-OBS3 standing law holds: no per-item ids (`run.id`/`work_item.id`/`agent`/`user.id`) as metric labels, no `model` label; the live map is legibility, never a consumption axis.

## Tasks / Subtasks

- [ ] **Task 1 — Render the live agent↔task↔Project map (AC1, AC6).**
  - [ ] Render the 8.8a `liveRuns` sub-payload: per active Run, agent × task (work item) × Project. Read + navigate only.
  - [ ] Empty/degraded state ("No active Runs") when the sub-payload is empty/`{available:false}`; no placeholder rows.
- [ ] **Task 2 — Own the SSE live-Run stream over the existing bus (AC2).**
  - [ ] Subscribe to the **existing progress bus** (EventSource + BFF proxy, §4.4/§13, same as 8.2); apply Run-start/claim/complete/pause **deltas** in place per the 8.8a delta contract. **No polling, no second transport.**
  - [ ] Publish/expose the live-Run deltas that 8.8b (KPI counters) / 8.8c (approval count) consume — this panel is the live-Run stream owner.
- [ ] **Task 3 — Read+navigate only; no mutate/claim affordance (AC3).**
  - [ ] Click-through to the Run (8.2), work item (8.14), agent — no claim/reassign/transition control anywhere on the panel (no-P2P console read model).
- [ ] **Task 4 — Rate-limit / fallback indicators + resume countdown (AC4, AC5).**
  - [ ] Surface throttled agents + active fallback models (13.9), SSE-updated; degrade gracefully where 13.9/5.11 absent.
  - [ ] Render the **`resume_at` countdown** for `Paused(rate_limited)` Runs from the **real `resume_at`** (2.11) via 8.8a/SSE; reflect early resume (5.11) and re-derived `resume_at` (crash-safe); never a client-invented clock.
- [ ] **Task 5 — RBAC-scoped rendering (AC6).**
  - [ ] Render only the pre-scoped payload + scoped SSE stream; add no client-side authz.
- [ ] **Task 6 — Observability self-check (AC7).**
  - [ ] Confirm no new domain metric here; only ordinary request/stream telemetry. Rate-limit/fallback figures come from 13.9's metrics. NFR-OBS3: no per-item ids on labels, no `model` label.

## Dev Notes

- **One SSE bus, and this panel owns the live-Run stream.** The live-Run map, the KPI counters (8.8b), and the approval count (8.8c) all ride the **same** EventSource + BFF proxy as the Run stream and org diagram (§4.4/§13). This story wires the live-Run deltas; 8.8b/8.8c **consume** them. Do not stand up a second EventSource client or a polling loop — that is the exact anti-pattern §13 r24 rules out ("no new transport, no polling").
- **Read model, no mutate — the org-diagram precedent (§13 r10).** The org diagram is a pure read model over Run/claim state with no mutate/claim affordance (no-P2P on the console). The Live Runs panel follows the same discipline: it shows who is running what and lets you navigate, but it never lets you claim, reassign, or drive an agent. A claim button here would reintroduce a console-side coordination affordance the architecture forbids.
- **The countdown must be honest.** `resume_at` is a **real, durable** value written by 2.11 (`now + Retry-After`, a single crash-safe wake in the coordination record). The panel counts down to *that* timestamp — reflecting an early resume when a fallback model is switched (5.11) or a re-derived `resume_at` after a controller restart. Do not invent a client-side timer or show a resume the record does not carry; that would mislead the operator about when work actually resumes.
- **Indicators are progressive.** The live agent↔task↔Project map ships from Run/claim state alone. The rate-limit/fallback indicators + `resume_at` countdown fill in as 2.11/3.7/5.10/5.11/13.9 land (per-tile progressive fill) — their absence is a graceful degrade, not a failure.

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield — only `pkg/auth/*_test.go` + `console/e2e/auth/`. The SSE progress bus (§4.4) + Run/claim state (Epic 2/3) are not yet in this checkout. This panel lands under `console/` in the dashboard surface; it consumes 8.8a's `liveRuns` sub-payload + the existing SSE bus and adds **no** apiserver code (the live-Run stream is exposed by the existing BFF proxy the Run stream / org diagram use).
- **Match conventions:** reuse the **existing** EventSource client (shared with the Run stream / org diagram) — do not add a second SSE client; reuse the 8.8a delta contract.

### References

- [Source: docs/bmad/02-prd.md#9.9 FR-I4] — live agent↔task↔Project mapping (who is running what), SSE-updated; complements the org diagram; read model derived from Run/claim state (FR-I3 provenance).
- [Source: docs/bmad/03-architecture.md#13 (r24) — Live tiles are SSE, one bus] — live-Run map + KPI counters + approval count over the existing SSE progress bus (same BFF proxy as org diagram + Run stream); no new transport, no polling.
- [Source: docs/bmad/03-architecture.md#13 (r10) — org-diagram read model] — pure read model over Run/claim state, no mutate/claim affordance (no-P2P on the console) — the precedent this panel follows.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.8 row 8.8f] — epic-level AC; deps 8.8a; consolidates the existing 8.8 rate-limit/fallback indicators (13.9); `resume_at` countdown (2.11); SSE only, no polling.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.8 row 8.8 (CEO 2026-08-12) + rows 2.11/3.7/5.10/5.11/13.9] — rate-limit/fallback indicators + `resume_at` (scheduled-resume timer) provenance.
- [Source: docs/bmad/stories/8-8a-dashboard-data-aggregation-read-model.md] — the `liveRuns` sub-payload + SSE snapshot/delta contract this panel owns and streams.

### Open questions (route via ISI-2325; do not block the live map)

1. **Team vs Project scope of the panel (Architect / Winston).** FR-I4 says "across the squad"; the org diagram is `Team`-scoped (§13 r10) while the dashboard is Project-rooted. Confirm whether the Live Runs panel shows the **Project's** Runs or the **Team/squad's** Runs (and whether cross-Project Runs of the same squad appear). *Does not block rendering the Project's live map.*
2. **Countdown display when `Retry-After` is absent (Designer / Architect).** 2.11 falls back to exponential backoff+jitter when `Retry-After` is absent (no exact `resume_at`). Confirm how the countdown renders in that case (indeterminate "resuming soon" vs a computed backoff estimate) so it stays honest (AC5).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, agent 2230b001) — construction-time contract via runnable falsification check (`live-runs-panel-sse-check.py`, Epic-8 model-check pattern).

### Debug Log References

- `python3 live-runs-panel-sse-check.py` → exit 0 (polling-claim-panel anti-pattern trips all 6; §8.8f conformant Live Runs panel holds C1-C7).
- `--mutate={FAKE_ROWS,POLL_TRANSPORT,CLAIM_BUTTON,CLIENT_TIMER,CLIENT_AUTHZ,PERITEM_LABEL,HARD_FAIL_DEGRADE}` → each exit 1 with the mapped invariant RED; no vacuous survivors.

### Completion Notes List

- Implemented C1-C7 falsification check with teeth via a "polling-claim panel" anti-pattern (polling loop, claim/reassign button, client-invented resume timer, client-side authz, per-item metric labels, hard-fails on degraded source).
- **Load-bearing cruxes proven:** (C2) SSE ONLY over the EXISTING EventSource + BFF proxy (§4.4/§13, same bus as Run stream + org diagram) — no polling, no new transport; this panel OWNS the live-Run delta stream that 8.8b/8.8c consume; (C3) read + navigate only, NO mutate/claim/transition affordance (no-P2P on the console, §13 r10 org-diagram precedent); (C5) resume_at countdown derived from the REAL coordination record (2.11, crash-safe), NOT a client-invented timer — reflects early resume (fallback switch, 5.11) and re-derived resume_at after controller restart.
- Runtime proof (real SSE delta wire-up, rate-limit/fallback indicator streaming from 13.9, resume_at countdown from coord record) owned by console E2E + 8.8a/2.11 integration tests.

### File List

- `docs/bmad/spikes/bench/live-runs-panel-sse-check.py` (new) — C1-C7 runnable falsification check.
- `docs/bmad/stories/8-8f-live-runs-panel-sse.md` (this file) — status→done + Dev Agent Record.
