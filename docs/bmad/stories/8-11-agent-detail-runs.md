# Story 8.11: Agent detail page with Run history + logs

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **A pure read model over the `Run` CRDs + `run_events` — a legibility surface, no new backend.** The
> agent-detail page shows a **Run list** (status / duration / token usage) projected from the `Run` CRDs (§5.2),
> and drilling into a Run opens **tabbed logs** — task/work-item (coordination record, Epic 2), tool-call, LLM
> (prompt/response + token counts), build output (**links to the build browser 8.7**), and error traces — all
> sourced from `run_events` streamed by the shim over A2A (§7.1/§5.2). The **active Run gets a live SSE log
> tail** over the **existing** progress bus (§4.4, same EventSource + BFF proxy as the Run stream 8.2), and
> **each Run deep-links to its OTel trace** (§17.2 per-Run durable traceparent, 13.1/ISI-2133). **Token counts
> are runtime-reported / best-effort legibility (§11 OQ14) — NOT the billing authority** (authoritative
> consumption stays the dashboard 8.8 via the OTel metering spine). It is a **read + navigate surface** (R6
> scope guard, no-P2P on the console): no mutate/claim/retry/dispatch/edit affordance — kill stays 8.4, compose
> stays 8.5. A fabricated non-`run_events` log store, a second authz path, tokens presented as
> billing-authoritative (or fabricated where the runtime reported none), a retry/dispatch button, a polling
> loop instead of the SSE bus, or an in-console reimplementation of the trace/build browser is a **regression**.
> Read AC1, AC3, AC5, and AC6 literally.

## Story

As an **operator reaching an Agent from the org diagram (8.10) or the squad overview (8.1)**,
I want **its detail page showing a Run list with status / duration / token usage, each Run drilling into
tabbed logs (task/work-item, tool-call, LLM prompt/response + tokens, build output linking to the build
browser, error traces) sourced from `run_events`, the active Run tailing live over the existing SSE bus, and
each Run deep-linking to its OTel trace**,
so that **I can see everything an agent has done and drill into any Run — a scoped, `run_events`-sourced read
model over existing seams (FR-F9), with token counts as best-effort legibility (never billing), no new backend,
and no way to drive an agent from the page.**

## Context & prerequisites (read first)

- **PRD / epic:** `docs/bmad/04-epics-and-stories.md` Epic 8 row **8.11** (FR-F9) — the console SHALL provide an
  **agent-detail page with Run history + logs** (Paperclip pattern): a **Run list** with status / duration /
  token usage; per-Run drill-down to **tabbed logs** — task/work-item (coordination record, Epic 2), tool-call,
  LLM (prompt/response + token counts), build output (**links to the build browser 8.7**), and error traces —
  all from `run_events` streamed by the shim over A2A (§7.1/§5.2); an **active Run gets a live SSE log tail**
  (§4.4, same BFF proxy as 8.2); and **each Run links to its OTel trace** (§17.2 per-Run trace, ISI-2133).
- **Architecture:** `docs/bmad/03-architecture.md` §13 (console read models), §7.1 (`run_events` shim seam),
  §5.2 (`Run.status.phase` / Run lifecycle), §4.4 (SSE hub), §17.2 (per-Run OTel trace + metering spine),
  §12.3 r20/r21 (the one deny-by-default RBAC wall), §12.1 (scope). **No new CRD, no new data source.**
- **Token provenance (§11 / §17.2, OQ14 — resolved):** per-call token counts, where a runtime reports them,
  are surfaced by the shim over A2A and attributed to the anchored Run — but they are **runtime-reported and
  therefore best-effort**, explicitly **NOT** the authoritative billing axis. A runtime that reports nothing
  **degrades to run-minutes / resource attribution rather than a fabricated count**. The **authoritative
  consumption axis stays the dashboard (8.8)** via the OTel metering spine (§17.2) — this page is legibility.
- **Depends on:** the console read-model conventions from **8.1** (existence-hiding scoped read model), **8.8a**
  (the one deny-by-default RBAC wall + the existing SSE snapshot/delta bus), **8.2** (the one EventSource + BFF
  proxy the live log tail rides), the **build browser 8.7** (the build-output tab deep-links here), and the
  per-Run **durable trace** from **13.1 / ISI-2133** (each Run's OTel-trace deep-link target). The Run list +
  tabbed logs project the `Run` CRDs (§5.2) + `run_events` (§7.1) Epic 2/3 already write.
- **Reached from:** the **team-org diagram (8.10)** click-through (ISI-2161) and the **squad overview (8.1)** /
  Agents rail — both are **navigations** (URLs) to this route, never coordination actions.
- **Scope guard (R6):** this is a **read/legibility** surface. It is **not** a coordination path — **kill**
  stays **8.4**, **compose** stays **8.5**. No mutate/claim/retry/dispatch/edit affordance anywhere.
- **Build owned by ISI-2162** (CEO 2026-08-11); UX mock `10-agent-detail-runs` (11th screen, ISI-2150,
  `docs/bmad/ux/gen-10-agent-runs.py`, dark + light). This story pins the **construction-time contract**.

## Acceptance Criteria

**AC1 — Run list + tabbed logs are a read-only projection of existing sources (the read-model crux).**
Given an Agent, When the operator opens its detail page, Then the **Run list** (status / duration / token
usage) is a read-only projection of the **`Run` CRDs** (§5.2), and each Run's **tabbed logs** — **task/work-item**
(coordination record, Epic 2), **tool-call**, **LLM** (prompt/response + token counts), **build output**
(deep-link to the build browser 8.7), and **error trace** — project **`run_events`** streamed by the shim over
A2A (§7.1/§5.2). Every tab is provenanced to a **real existing source** (`run_events` / coordination record /
build-browser deep-link) — **no new backend, no new store, no fabricated log source**. The endpoint is
**GET-only**; every mutating verb is structurally absent (405 / route absent).

**AC2 — served through the ONE deny-by-default RBAC wall, scoped (the security crux).**
Given the page, When it renders, Then it is served through the **SAME shared deny-by-default RBAC middleware**
every other console read model uses (§12.3 r20/r21) — **no agent-detail-specific authz path**. It is **scoped**
(§12.1): a caller with **no membership** gets the **not-found/deny shape** (existence-hiding), **never** a
partial Run list; a member gets the scoped Run history. This story adds **no** client-side authz and **no**
second authz path.

**AC3 — token counts are best-effort legibility, NOT the billing authority (the OQ14 crux).**
Given a Run's token usage, When it renders in the Run list or the LLM tab, Then it is **runtime-reported and
best-effort** (§11 / §17.2, OQ14) — surfaced as legibility, **NOT** the authoritative consumption/billing axis
(that stays the dashboard **8.8** via the OTel metering spine). A Run whose runtime **reported nothing**
**degrades to run-minutes** with **NO fabricated count**. This surface must **never** present tokens as
billing-authoritative, and must **never** invent a count where the runtime supplied none.

**AC4 — read + navigate surface: no mutate/coordination affordance (R6, no-P2P on the console).**
Given the page, When it renders, Then it has **no mutate / claim / retry / dispatch / edit affordance**
anywhere — it is **read + navigate only** (no-P2P applied to the console, R6 scope guard). It is **not** a
coordination path: **kill** stays **8.4**, **compose** stays **8.5**. A retry button, a dispatch/reassign
control, or an editable Run is a regression.

**AC5 — the active Run gets a live SSE log tail over the EXISTING bus (no new transport, no polling).**
Given an **active** Run open, When new `run_events` arrive, Then its log tail **updates live via SSE over the
existing progress bus** — the **same EventSource + BFF proxy** as the Run stream (8.2) — **no polling loop, no
new transport, no new backend**. A **completed** Run has **no live tail**; it renders from the **durable
`run_events`**. Live-tailing a completed Run, or driving the tail with a polling loop, is a regression.

**AC6 — each Run deep-links to its OTel trace + the build browser — navigation, not a new store.**
Given a Run, When the operator opens its OTel-trace link or its build-output tab, Then each is a **navigation
(a URL)** — the trace link to the **existing trace store** (§17.2 per-Run durable traceparent, 13.1/ISI-2133),
the build-output tab to the **build browser (8.7)**. Neither **reimplements** the trace or the build view in a
**new in-console store**; both are deep-links to existing surfaces.

**AC7 — observability: consumes existing seams; adds no new domain metric; cardinality firewall.**
Given the page, When it renders/streams, Then it emits **only** ordinary console/BFF request+stream telemetry —
it introduces **no new domain metric**, **no new CRD, no new data source, no new backend**. NFR-OBS3 standing
law holds: per-item ids (`agent`/`run.id`/`work_item.id`/`user.id`) are **never** metric labels, and there is
**no** `model` label; the Run history + token figures are legibility, never a consumption axis (that is the
dashboard 8.8 / §17.2 spine).

## Tasks / Subtasks

- [ ] **Task 1 — Project the Run list + tabbed logs from Run CRDs + `run_events` (AC1, AC2).**
  - [ ] Compose the Run list (status/duration/tokens) from the `Run` CRDs (§5.2) via the BFF; compose each
        Run's tabs from `run_events` (§7.1) + the coordination record (Epic 2). GET-only; no new store.
  - [ ] Provenance every tab to its real source; build-output is a deep-link to the build browser (8.7).
- [ ] **Task 2 — Serve through the one deny-by-default RBAC wall, scoped (AC2).**
  - [ ] Route through the SAME shared deny-by-default middleware (§12.3); a non-member gets the not-found/deny
        shape (existence-hiding); a member gets the scoped Run history. No agent-detail-specific authz path.
- [ ] **Task 3 — Surface tokens as best-effort legibility, never billing (AC3).**
  - [ ] Mark every token figure runtime-reported / best-effort (OQ14); a Run with no runtime report degrades to
        run-minutes with NO fabricated count. The authoritative axis stays the dashboard (8.8) / §17.2 spine.
- [ ] **Task 4 — Read + navigate only (AC4).**
  - [ ] No mutate/claim/retry/dispatch/edit affordance anywhere (no-P2P, R6). Kill stays 8.4, compose stays 8.5.
- [ ] **Task 5 — Live-tail the active Run over the existing SSE bus (AC5).**
  - [ ] Tail the active Run's `run_events` over the **existing** progress bus (EventSource + BFF proxy, §4.4,
        same as 8.2); a completed Run renders from the durable `run_events` with no tail. No polling, no new transport.
- [ ] **Task 6 — Deep-link the OTel trace + the build browser (AC6).**
  - [ ] Each Run links to its OTel trace (§17.2 / 13.1 durable traceparent); the build-output tab deep-links to
        the build browser (8.7). Both are URL navigations — never a reimplemented in-console store.
- [ ] **Task 7 — Observability self-check (AC7).**
  - [ ] Confirm no new domain metric, no new backend; only ordinary request/stream telemetry. NFR-OBS3: no
        per-item ids on labels, no `model` label.

## Dev Notes

- **Pure read model over existing seams — no new backend.** The Run list projects the `Run` CRDs (§5.2); the
  tabs project `run_events` (§7.1) + the coordination record (Epic 2). There is **no new CRD, no new data
  source, no log-store tier** — the page reads what Epic 2/3 + the shim already write. This is the §13
  discipline: the agent-detail page rides existing seams and does **not** reopen the passed CEO Gate 2.
- **Tokens are legibility, never billing — the OQ14 crux.** The single most tempting regression is to present
  the runtime-reported token count as an authoritative consumption/billing figure, or to fabricate a count when
  the runtime reports none. Don't. Tokens here are **runtime-reported and best-effort** (§17.2/OQ14); a Run
  with no report **degrades to run-minutes** with no invented number. The **authoritative** consumption axis is
  the dashboard **8.8** via the OTel metering spine — this page never claims to be it.
- **The active Run rides the ONE SSE bus.** The live log tail streams over the **same** EventSource + BFF proxy
  as the Run stream (8.2) and the dashboard live tiles (§13 r24). Do not stand up a second EventSource client
  or a polling loop — that is the exact anti-pattern §13 rules out. A completed Run has no tail; it renders from
  the durable `run_events`.
- **Trace + build are deep-links, not reimplementations.** Each Run's OTel-trace link navigates to the existing
  trace store (§17.2 / 13.1 durable traceparent); the build-output tab deep-links to the build browser (8.7).
  Re-implementing either in a new in-console store is a second source of truth the architecture forbids (AC6).
- **Read + navigate only — the §13 legibility precedent (R6).** The page shows what an agent has done and lets
  you navigate to detail; it never lets you retry, dispatch, or drive a Run. A retry/dispatch button here would
  reintroduce a console-side coordination affordance (no-P2P §6). Kill stays **8.4**; compose stays **8.5**.

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield console surface — the agent-detail page lands under
  `console/` and consumes the BFF read model (Run CRDs + `run_events` + coordination record) + the existing SSE
  bus. It adds **no** apiserver code beyond the read projection over existing Run state / `run_events`, and
  **no** new store. Reuse the **existing** EventSource client (shared with the Run stream / dashboard live
  tiles) — do not add a second SSE client. Reuse the shared deny-by-default RBAC middleware (§12.3) — do not add
  an agent-detail-specific authz path. The build-output tab and the OTel-trace link are **deep-links** to the
  build browser (8.7) and the trace store (§17.2 / 13.1) — never reimplemented in-console.
- **UX:** `docs/bmad/ux/gen-10-agent-runs.py` (screen 10, dark + light) is the visual contract — the identity
  card, the Run list (status / duration / tokens), the tabbed log drill-down (task/work-item · tool-call · LLM ·
  build output · error trace), the active-Run live tail, and the per-Run OTel-trace link.

### References

- [Source: docs/bmad/04-epics-and-stories.md — Epic 8 row 8.11] (FR-F9) — agent-detail page: Run list
  (status/duration/tokens), tabbed logs from `run_events` (task/work-item · tool-call · LLM · build output →
  8.7 · error trace), active-Run live SSE log tail (same BFF proxy as 8.2), per-Run OTel-trace link (§17.2,
  ISI-2133); token counts runtime-reported/best-effort (OQ14) — legibility, NOT billing (authoritative = 8.8);
  read surface (R6), no new backend; build owned by ISI-2162.
- [Source: docs/bmad/03-architecture.md#7.1] — `run_events` shim seam (tool-call / LLM / error events over A2A).
- [Source: docs/bmad/03-architecture.md#5.2] — `Run.status.phase` / Run lifecycle the list row projects.
- [Source: docs/bmad/03-architecture.md#17.2 (metering provenance, OQ14)] — runtime-reported token counts are
  best-effort, explicitly NOT the billing axis; a runtime that reports nothing degrades to run-minutes; the
  authoritative consumption axis is the dashboard (8.8).
- [Source: docs/bmad/03-architecture.md#4.4 / §13 (r24)] — the existing SSE progress bus (same EventSource + BFF
  proxy as the Run stream 8.2); no new transport, no polling.
- [Source: docs/bmad/03-architecture.md#12.3 (r20/r21)] — the one deny-by-default RBAC wall; no per-surface
  authz path; existence-hiding for non-members.
- [Source: docs/bmad/stories/8-2-live-run-progress-via-sse.md] — the one EventSource + BFF proxy the live log
  tail rides.
- [Source: docs/bmad/stories/8-7e-console-three-pane-build-browser.md] — the build browser the build-output tab
  deep-links to.
- [Source: docs/bmad/stories/13-1-run-trace.md] — the per-Run durable `ksquad.io/traceparent` the OTel-trace
  deep-link targets (§17.2 / ISI-2133).
- [Source: docs/bmad/stories/8-10-team-org-diagram.md] — the org-diagram click-through that reaches this page.
- [Source: docs/bmad/ux/gen-10-agent-runs.py] — screen 10 agent-detail mock (dark + light).

### Open questions (route via ISI-2162; do not block the read model)

1. **`run_events` retention window for completed Runs (Architect / Winston).** The tabs render a completed
   Run from the durable `run_events`. Confirm the retention window / archival for `run_events` so a
   long-completed Run still renders its logs (vs. a "logs expired" degrade). *Does not block rendering the Run
   list or an active Run's live tail.*
2. **Cross-Project Run history in a scoped page (Architect).** An Agent may run Runs across multiple Projects of
   the squad. Confirm the detail page shows the Agent's Runs across those Projects (Agent-level history), each
   row still scoped by the shared RBAC wall. *Does not block the scoped Run-list render.*

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, agent 2230b001) — construction-time contract via runnable falsification check
(`agent-detail-runs-check.py`, Epic-8 model-check pattern).

### Debug Log References

- `python3 agent-detail-runs-check.py` → exit 0 (the billing-console anti-pattern trips all 7; the read-model
  agent-detail page holds C1-C7).
- `--mutate={FABRICATED_LOG_SOURCE,BESPOKE_AUTHZ,TOKENS_AS_BILLING,MUTATE_AFFORDANCE,POLL_TAIL,REIMPL_TRACE,PERITEM_LABEL}`
  → each exit 1 with the mapped invariant RED; no vacuous survivors (REIMPL_TRACE also trips C1 — acceptable, C6
  is the mapped tooth).

### Completion Notes List

- Implemented C1-C7 falsification check with teeth via a "billing console" anti-pattern (mutating verbs on the
  surface, a fabricated non-`run_events` log store, its own authz path that leaks to a non-member, token counts
  presented as the authoritative billing axis with a fabricated count where the runtime reported none, a
  retry/dispatch button on every Run, a polling loop that even tails a completed Run, an in-console
  reimplemented trace/build store, and per-Run metric labels).
- **Load-bearing cruxes proven:** (C1) the Run list + tabbed logs are a **read-only projection** of the `Run`
  CRDs (§5.2) + `run_events` (§7.1) + the coordination record (Epic 2) — GET-only, no new backend/store, every
  tab provenanced to a real existing source; (C2) served through the **ONE shared deny-by-default RBAC wall**,
  scoped, existence-hiding for non-members — no agent-detail-specific authz path; (C3) token counts are
  **runtime-reported / best-effort legibility**, never billing-authoritative, degrading to run-minutes with no
  fabricated count when the runtime reports none — the authoritative axis stays the dashboard (8.8); (C4)
  **read + navigate only** — no mutate/claim/retry/dispatch/edit affordance (no-P2P, R6; kill=8.4, compose=8.5);
  (C5) the active Run's log tail rides the **EXISTING** SSE bus (same EventSource + BFF proxy as 8.2), a
  completed Run renders from the durable `run_events` with no tail; (C6) the OTel-trace link + build-output tab
  are **deep-links** to the existing trace store (§17.2 / 13.1) + the build browser (8.7), never reimplemented
  in-console.
- Runtime proof (the real Run-CRD + `run_events` read projection through the BFF, the live per-membership
  scoped RBAC on the Go apiserver, the SSE active-Run log tail, and the OTel-trace / build-browser deep-links)
  owned by console E2E + apiserver read-model tests on the actual Run + `run_events` stores. This check guards
  the construction-time contract FR-F9 + the epic asked for.

### File List

- `docs/bmad/spikes/bench/agent-detail-runs-check.py` (new) — C1-C7 runnable falsification check.
- `docs/bmad/stories/8-11-agent-detail-runs.md` (this file) — status→done + Dev Agent Record.
