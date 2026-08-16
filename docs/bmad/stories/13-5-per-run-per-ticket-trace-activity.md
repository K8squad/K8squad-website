# Story 13.5: Per-Run / per-ticket trace activity in the console — the `work_item.id` join, not a new signal

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE OBSERVABILITY HALF OF THE TRACE DRILL-DOWN (obs-plan §3 "the unit of correlation: the
> Run trace" — the *per-ticket activity view*, §5.2 Run state-machine phase spans).** Its sibling **8.11
> (done)** built the *console read model* — the agent-detail page that deep-links each Run to its OTel trace.
> **This story pins the observability contract that surface consumes and adds the one thing 8.11 does not: the
> *per-ticket activity reconstruction*.** The load-bearing insight is the one obs-plan §3 states literally: **a
> work item (ticket) can span *multiple* Runs — retries, crash-reclaims, resume-after-pause — so the per-ticket
> perspective is a JOIN QUERY on `work_item.id`, not a new signal.** The activity timeline for a ticket is
> assembled by joining **traces + correlated logs + `run_events`** on `ksquad.work_item.id` across *every* Run
> the ticket touched, in causal order — and `work_item.id` stays a **trace/log/exemplar dimension, NEVER a
> metric label** (§1.2/§5.6 cardinality law). The regression this story exists to prevent is materializing a
> `per_ticket_activity{work_item_id=…}` **metric** (unbounded label → cardinality explosion), or showing only
> the **latest** Run of a ticket (silently dropping the retry/reclaim history that is the whole point of the
> per-ticket view). Read AC1, AC2, and AC3 literally.

## ⚠️ Scope & boundary vs 8.11 (read first)

8.11 and this story are **two halves of one FR** and must not overlap or contradict:

| Concern | Owner | This story delivers |
|---|---|---|
| The agent-detail **page** (Run list, tabbed logs, live tail, per-Run trace deep-link) — the console read model | **8.11 (done)** | *consumed, not rebuilt* |
| The **per-Run OTel-trace deep-link contract** — what URL, what target, what durable key (`ksquad.io/traceparent`), phase-duration spans (§5.2) | **this story** pins it; 8.11/13.1 realize it | §A the deep-link contract |
| The **per-ticket activity reconstruction** — a ticket spans *many* Runs; join traces + logs + `run_events` on `work_item.id` across all of them, in causal order | **this story** (8.11 is per-Agent/per-Run, not per-ticket) | §B the join contract + AC2 |
| **Active-Run live span/log activity** over the *existing* SSE bus (no new transport) | **this story** pins the contract; 8.11/8.2 carry the transport | §C the live-activity contract + AC4 |
| The durable `ksquad.io/traceparent` spine, in-service span tree, four-field log correlation | **13.1 (ready-for-dev)** | *depended on, not rebuilt* |
| The metric instruments, the cardinality CI lint, the collector redaction | 13.2/13.3/13.4 · 13.6 · 13.7 | *obeyed, not built* |

**One-line boundary:** 8.11 is *where you look*; this story is *what the trace/per-ticket view is guaranteed to
join on and how it stays a query, not a new signal*. This story adds **zero** new CRD fields, **zero** new
metric instruments, and **zero** new backend store — it defines the **query/join contract** over the
`work_item.id`/`run.id` dimensions 13.1 already stamps on every span/log/exemplar and the `run_events` Epic 2
already writes work-item-scoped.

## Story

As **an operator triaging a ticket or a Run**,
I want **each Run in the console to deep-link to its one OTel trace (phase-duration spans, §5.2) via the
durable `ksquad.io/traceparent`, and a work item's *entire* activity — across every Run it spanned (retry,
crash-reclaim, resume-after-pause) — reconstructable as one causal timeline by joining traces + correlated
logs + `run_events` on `ksquad.work_item.id`, with an active Run showing live span/log activity over the
existing SSE bus**,
so that **I can follow a single Run end-to-end in its trace and see a Paperclip-style per-ticket activity
timeline that survives across all the Runs a ticket took — without a new metric label (`work_item.id` stays
off metric labels, §1.2/§5.6), a new trace/log store (deep-links to 13.1's spine, not a reimplementation), a
polling loop (the live tail rides the one SSE bus), or the latest-Run-only view that silently drops the
retry/reclaim history the per-ticket perspective exists to show.**

## Context & prerequisites (read first)

- **Observability plan:** `docs/bmad/04-observability-plan.md`
  - **§3 "The unit of correlation: the Run trace"** — the authoritative shape. Two paragraphs are this
    story's whole spec:
    - *The trace tree* (Run root → reconcile phases → claim → a2a.submit → shim.execute → agent turns →
      memory ops → SSE progress) and the **propagation contract table** (the seam crossings, their carriers
      and owners) — the per-Run trace this story deep-links to.
    - **"Per-ticket activity view (Paperclip-style)"** — the load-bearing sentence: *"A work item (ticket)
      can span multiple Runs — retries, crash-reclaims, resume-after-pause — so the per-ticket perspective is
      a query pattern, not a new signal: every span, log line, and metric exemplar emitted by a Run carries
      `ksquad.work_item.id` alongside `ksquad.run.id`, and the `run_events` audit rows are work-item-scoped.
      The console/backend renders a Paperclip-style per-ticket activity timeline by joining traces +
      correlated logs + `run_events` on `work_item.id`: claims, Runs, phase transitions, SSE progress,
      artifact appends, terminal reasons, in causal order. This costs nothing at the metrics layer —
      `work_item.id` stays forbidden as a metric label (§1.2/§5.6) and lives exactly where unbounded IDs
      belong."* **This story IS that paragraph made a construction-time contract.**
  - **§1.1** — three pillars correlate or they are noise; the join key is the Run. Per-ticket is the Run join
    lifted one level: **the ticket is the join key across the *set* of Runs it spanned.**
  - **§1.2 / §5.6 cardinality law** — `run.id`, `work_item.id`, `user.id` are **trace/log/exemplar
    dimensions, NEVER metric labels** (unbounded per-actor). The per-ticket view **must** be a JOIN over these
    dimensions, not a metric series keyed on them. 13.6's CI lint *enforces* this; this story *obeys* it.
  - **§4.3 span attributes** — `ksquad.work_item.id` is standard on every span; **§7 semconv** registers it as
    "per-ticket correlation (Paperclip-style activity view, §3); span/log/exemplar only — never a metric label."
  - **§4.1 phasing** — P0: per-ticket reconstruction works over **`run.id`/`work_item.id` log + `run_events`
    audit correlation** (ships without cross-sandbox stitching). P1: the §3 propagation upgrade turns each Run
    into one connected cross-boundary trace, deepening the per-Run trace link (more child spans) **without
    changing the join key**. This story's join contract is stable across the P0→P1 seam.
  - **§6 logging** — every Run log line carries `trace_id`/`span_id`/`ksquad.run.id`/`service.name` (§D of
    13.1); the per-ticket join reads `ksquad.work_item.id` off logs the same way it reads it off spans.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§5.2 Run reconcile** — the **phase-duration spans** the per-Run trace link shows (Pending →
    ClaimingSandbox → Dispatching → Running → Collecting → terminal); the operator owns `Run.status` (so the
    durable `ksquad.io/traceparent` link target is an operator-written status annotation, 13.1 §C).
  - **§7.1 `run_events` shim seam** — the work-item-scoped causal rows (claims, phase transitions, SSE
    progress, artifact appends, tool-call / LLM / error events, terminal reasons) that the per-ticket timeline
    joins alongside traces + logs.
  - **§4.4 SSE hub** — the **one** EventSource + BFF proxy the active-Run live span/log activity rides (same
    as the Run stream 8.2 and the dashboard live tiles) — no new transport, no polling.
  - **§17.2** — the per-Run OTel-trace / metering spine (§13.1 durable traceparent) the deep-link targets.
  - **§12.3 r20/r21** — the one deny-by-default RBAC wall; the per-ticket view is served through it, scoped;
    existence-hiding for non-members (no partial ticket timeline leaks).
- **Depends on:**
  - **Story 13.1** (ISI-2233 — the durable `ksquad.io/traceparent` spine + in-service span tree +
    `work_item.id` stamped on every span/log/exemplar + four-field log correlation). *This story's deep-link
    target and join dimensions are 13.1's outputs.* If 13.1's cross-boundary stitching (P1) has not landed, the
    per-Run trace shows the P0 in-service subtrees and the per-ticket join still works over log + `run_events`
    correlation (§4.1) — the join key is unchanged.
  - **Story 2.1** (ISI-2191 — the coordination schema; `run_events` is work-item-scoped and carries
    `work_item.id` on every row, the audit spine the timeline joins).
  - **Story 8.11** (ISI-2281 — done; the agent-detail page that hosts the per-Run trace deep-link and the
    tabbed logs — the console surface that *consumes* this contract).
  - **Story 8.2** (ISI-2265 — the one EventSource + BFF SSE proxy the live activity rides).
  - *Soft dep:* **Story 1.6** (`Run.spec.initiatedByUserId`) — if landed, the same join mechanism yields the
    per-user timeline (§3, 13.10); this story does **not** require it — per-ticket reconstruction is truthful
    without the user dimension.
- **Is consumed by / pairs with:** **8.11** (agent-detail page — hosts the per-Run trace link + tabbed logs),
  the **Project dashboard** (§17 — the per-ticket / per-user rollups ride the same join), **13.10** (per-user
  activity — the same join re-keyed on `user.id`).

## The per-Run trace deep-link contract (authoritative — §A, obs-plan §3 / arch §5.2 / §17.2)

Each Run in the console deep-links to **exactly one OTel trace** — the trace rooted at the Run's durable
`ksquad.io/traceparent` (13.1 §C). The link is a **navigation (a URL) to the existing trace store** (§17.2),
**never** an in-console reimplementation of a trace view:

- **Target = the durable root.** The link resolves the Run's `trace_id` from the **`Run.status` annotation
  `ksquad.io/traceparent`** (durable state, survives a controller restart — 13.1 §C), not from a request-time
  value. A completed Run's trace is closed at teardown; the link still resolves (the annotation is durable).
- **Shows the phase-duration spans (§5.2).** The trace the operator lands on is the Run state-machine tree:
  reconcile phase spans (Pending→ClaimingSandbox→Dispatching→Running→Collecting→terminal), the
  `sandbox.claim` span (with the `ksquad.sandbox.claim.duration` exemplar), `a2a.task.submit`, and — where P1
  stitching has landed — the in-sandbox `shim.task.execute` / `agent.turn.*` / `mcp.memory.*` subtrees.
- **Deep-link, not a store.** The console **never** materializes a second trace store. This is the same
  discipline 8.11 AC6 states: the trace link is a URL to the existing surface; re-implementing the trace view
  in-console is a second source of truth the architecture forbids.

## The per-ticket activity join contract (authoritative — §B, obs-plan §3 "per-ticket activity view")

**A ticket is not a Run.** A work item spans **multiple** Runs — a retry mints a new Run, a crash-reclaim
fences and re-dispatches, a resume-after-pause continues — all carrying the **same `ksquad.work_item.id`**.
The per-ticket activity timeline is the **join of all three pillars on `work_item.id`, across every Run the
ticket spanned**, assembled in causal order:

- **The join key is `ksquad.work_item.id`, spanning Runs.** The timeline for ticket `W` gathers **every** Run
  whose `work_item.id = W` (not just the latest), then merges, on the `work_item.id` axis:
  - **traces** — the per-Run trace roots (13.1), one per Run of the ticket;
  - **correlated logs** — the four-field log lines (§6/§D) whose `work_item.id = W`;
  - **`run_events`** — the work-item-scoped audit rows (§7.1): claims, Runs, phase transitions, SSE progress,
    artifact appends, tool-call/LLM/error events, terminal reasons.
- **Causal order across Runs.** The merged timeline is ordered causally (claim → dispatch → phase advances →
  terminal, then the *next* Run's claim on retry/reclaim/resume) — so an operator reading ticket `W` sees the
  **full attempt history**, not a single Run's slice. Showing only the latest Run (dropping the prior
  attempts' claims, failures, and reclaim events) is the regression AC2 forbids.
- **It is a QUERY, not a signal (the cardinality crux).** This join **costs nothing at the metrics layer**:
  `work_item.id` stays a **span/log/exemplar dimension** and is **never** a metric label. Materializing a
  `per_ticket_activity{work_item_id=…}` (or `run.id`-keyed) **metric series** to power this view is a
  cardinality-law violation (§1.2/§5.6, unbounded per-ticket) and the exact regression 13.6's CI lint catches
  — the per-ticket view is assembled by **querying/joining the trace + log + audit stores on the id dimension**,
  where unbounded ids belong.
- **P0-truthful, P1-deepened.** At P0 the join works over `run.id`/`work_item.id` log + `run_events`
  correlation (no cross-sandbox trace stitching required, §4.1); at P1 each Run's trace becomes one connected
  cross-boundary trace, so the per-Run trace link deepens — **the join key and the timeline shape are
  unchanged**. The contract is stable across the phasing seam.

## The active-Run live activity contract (authoritative — §C, arch §4.4 / obs-plan §6)

An **active** Run shows **live span/log activity** — new spans opening and new correlated log lines arriving —
over the **existing** SSE progress bus:

- **Rides the ONE bus.** Live activity streams over the **same EventSource + BFF proxy** as the Run progress
  stream (8.2) and the dashboard live tiles (§4.4 r24) — **no new transport, no polling loop, no second SSE
  client**. SSE events carry `run.id` + `span_id` (§3 propagation table, shim → apiserver SSE hub) so live
  activity stitches back into the Run's trace at the apiserver hub.
- **Live only while active.** A **completed** Run has **no live activity** — its trace is closed at teardown
  and it renders from the **durable** `run_events` + the closed trace (via the §A deep-link). Live-tailing a
  completed Run, or driving live activity with a polling loop, is a regression (mirrors 8.11 AC5).
- **The live per-ticket view = live Run activity + the durable prior-Run timeline.** For a ticket whose
  *current* Run is active, the per-ticket timeline is the **durable** history of the ticket's prior Runs (§B
  join over `run_events` + closed traces) **plus** the current Run's **live** activity over the SSE bus — one
  timeline, two provenance classes, no polling.

## Acceptance Criteria

**AC1 — each Run deep-links to its one OTel trace via the durable `ksquad.io/traceparent`; phase-duration spans; a URL, not a store.**
Given a Run, When the operator opens its trace link in the console, Then the link is a **navigation (a URL) to
the existing trace store** (§17.2) resolving the Run's `trace_id` from the **durable `Run.status` annotation
`ksquad.io/traceparent`** (13.1 §C — survives a controller restart, resolves even for a completed Run whose
trace is closed); And the trace it lands on is the Run **state-machine tree** — reconcile phase-duration spans
(§5.2), `sandbox.claim` (+ its exemplar), `a2a.task.submit`, and (where P1 stitching landed) the in-sandbox
subtree; And the console **never reimplements** the trace view in a new in-console store (deep-link only, 8.11
AC6). A trace link resolved from a request-time value instead of the durable annotation, or an in-console
trace store, is a regression.

**AC2 — a ticket's activity is reconstructable across ALL its Runs by joining on `work_item.id`, in causal order (the per-ticket crux).**
Given a work item that spanned **multiple** Runs (retry / crash-reclaim / resume-after-pause), When the
operator opens its per-ticket activity view, Then the timeline is the **join of traces + correlated logs +
`run_events` on `ksquad.work_item.id` across EVERY Run the ticket spanned** (not just the latest), assembled
in **causal order** (each Run's claim → phase advances → terminal, then the next Run's claim); And it surfaces
the full attempt history — claims, Runs, phase transitions, SSE progress, artifact appends, terminal reasons —
so a retry's prior failure and a crash-reclaim's fence are **visible, not dropped**. A view that shows only the
**latest** Run (silently discarding the ticket's prior attempts) is a correctness regression of the per-ticket
contract, not a cosmetic gap.

**AC3 — the per-ticket / per-Run view is a QUERY over id dimensions, NOT a new metric label (the cardinality crux).**
Given the per-ticket (or per-Run) activity view, When it is assembled, Then it is a **join/query over the
`work_item.id` / `run.id` dimensions on the trace + log + `run_events` stores** — and `work_item.id` and
`run.id` remain **trace/log/exemplar dimensions, NEVER metric labels** (§1.2/§5.6). This surface introduces
**no** new metric instrument and **no** `per_ticket_activity{work_item_id=…}` / `{run_id=…}` series; a metric
keyed on `work_item.id` or `run.id` to power this view is an unbounded-cardinality violation and the exact
regression 13.6's CI lint fails the build on. The per-ticket rollup lives **exactly where unbounded ids
belong** — the query layer, not the label set.

**AC4 — active Run shows live span/log activity over the EXISTING SSE bus; completed Run is durable-only (no polling).**
Given an **active** Run, When new spans open and new correlated log lines arrive, Then its live span/log
activity streams over the **same EventSource + BFF proxy** as the Run progress stream (8.2, §4.4) — **no new
transport, no polling loop, no second SSE client** — and SSE events carry `run.id` + `span_id` to stitch back
into the trace; And a **completed** Run has **no live activity** (its trace is closed at teardown; it renders
from the **durable** `run_events` + closed trace via the AC1 deep-link). For a ticket whose current Run is
active, the per-ticket timeline is the **durable prior-Run history + the live current-Run activity** — one
timeline, no polling. Live-tailing a completed Run, or a polling loop, is a regression.

**AC5 — served through the ONE deny-by-default RBAC wall, scoped; existence-hiding; no new backend/store.**
Given the per-ticket / per-Run trace view, When it renders, Then it is served through the **SAME shared
deny-by-default RBAC middleware** every console read model uses (§12.3 r20/r21) — **no view-specific authz
path** — and it is **scoped**: a caller with no membership gets the **not-found/deny** shape
(existence-hiding), **never** a partial ticket timeline. It reads **only** existing sources — the trace store
(§17.2 / 13.1), the correlated logs (§6), and `run_events` (§7.1) — and adds **no new CRD, no new metric, no
new backend, no new store**. A second authz path, a fabricated non-`run_events` activity store, or a partial
timeline leak to a non-member is a regression.

**AC6 — the join is stable across the P0→P1 phasing seam (no false-start).**
Given the §4.1 phasing (P0 = `run.id`/`work_item.id` log + `run_events` correlation, no cross-sandbox
stitching; P1 = full `traceparent` propagation), When P1 stitching lands, Then the per-Run trace **deepens**
(the in-sandbox `shim`/`agent`/`memory` subtrees join the Run's trace) **without changing the join key or the
per-ticket timeline shape** — the view is built on `work_item.id`/`run.id`, which are present and durable at
**both** phases. The per-ticket reconstruction is **truthful at P0** and simply gains connected cross-boundary
traces at P1; it does **not** false-start on P1 stitching that has not landed.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/per-ticket-trace-activity-check.py` — stdlib-only, `python3` it directly. A
**differential** falsification (same shape as the 13.1 / 13.2 / 8.11 checks), not a happy-path demo. It
contrasts a **"per-ticket metrics dashboard" anti-pattern** — which materializes `work_item.id` as a metric
label, shows only the latest Run of a ticket, reimplements an in-console trace store, resolves the trace link
from a request-time value, polls a completed Run, and runs its own authz path — against the **join-query**
model this story specifies, and proves each invariant has teeth by mutation:

- **(C1) per-Run trace deep-link resolves from the durable annotation (AC1).** The link resolves the Run's
  `trace_id` from the durable `Run.status` `ksquad.io/traceparent`; it resolves for a **completed** Run (trace
  closed, annotation durable). *Mutation-proven:* resolving from a request-time value (dropped on a controller
  restart / for a completed Run) turns the check **RED**.
- **(C2) per-ticket reconstruction spans ALL Runs of the ticket, in causal order (AC2 — the crux).** A ticket
  with three Runs (initial-fail → reclaim → resume-succeed) is reconstructed as one causal timeline joining
  traces + logs + `run_events` on `work_item.id`; the timeline contains **all three** Runs' claims / phases /
  terminals. *Mutation-proven:* the anti-pattern's **latest-Run-only** view (drops Runs 1 and 2) turns the
  check **RED** — the "spans multiple Runs" invariant has teeth.
- **(C3) it is a QUERY, not a metric label (AC3 — the cardinality crux).** The view is assembled by joining on
  the `work_item.id`/`run.id` **dimensions**; the check asserts **no** metric series is keyed on `work_item.id`
  or `run.id` (§1.2/§5.6). *Mutation-proven:* materializing a `per_ticket_activity{work_item_id=…}` metric
  turns the check **RED** (unbounded-cardinality violation — the same one 13.6's lint fails on).
- **(C4) active = live over the existing SSE bus; completed = durable-only (AC4).** An active Run's activity
  rides the **existing** EventSource + BFF proxy (run.id+span_id on events); a completed Run has **no** live
  tail and renders from durable `run_events` + closed trace. *Mutation-proven:* a **polling loop** (or
  live-tailing a completed Run) turns the check **RED**.
- **(C5) one RBAC wall, scoped, existence-hiding; no new store (AC5).** The view is served through the shared
  deny-by-default middleware; a non-member gets the not-found/deny shape (not a partial timeline); it reads
  only existing sources (trace store + logs + `run_events`). *Mutation-proven:* a bespoke authz path that
  leaks a partial ticket timeline to a non-member, or a fabricated activity store, turns the check **RED**.
- **(C6) join stable across the P0→P1 seam (AC6).** The same `work_item.id`/`run.id` join reconstructs the
  ticket at **both** P0 (log + `run_events` correlation) and P1 (stitched cross-boundary traces); P1 only
  **deepens** the per-Run trace. *Mutation-proven:* a view that **requires** P1 stitching to reconstruct the
  ticket (false-starts, empty at P0) turns the check **RED**.

Exits non-zero if the trace link resolves from a non-durable value, a ticket is reconstructed from only its
latest Run, a metric is keyed on `work_item.id`/`run.id`, the live path polls (or tails a completed Run), a
non-member sees a partial timeline, or the join requires P1 stitching to work at all. **The headline invariant
is mutation-checked:** the latest-Run-only mutation (C2) and the `work_item.id`-as-label mutation (C3) both
turn the check **RED** — the "per-ticket = a `work_item.id` join across all Runs, never a metric label"
contract is falsifiable, not decorative.

## Out of scope (owned elsewhere)

- **The agent-detail page itself** (Run list, tabbed logs, live tail UI, per-Run trace-link affordance) —
  **Story 8.11 (done)**. This story pins the **observability contract** that page consumes; it does not
  rebuild the page.
- **The durable `ksquad.io/traceparent` spine, the in-service span tree, the four-field log correlation, and
  the P1 cross-boundary `traceparent` stitching** — **Story 13.1** (this story **deep-links to** the trace and
  **joins on** the dimensions 13.1 produces; it does not build the spine).
- **The metric instruments** (`ksquad.coord.*`, `ksquad.run.*`, `ksquad.agent.tokens`, …) and their exemplars
  — **Stories 13.2/13.3/13.4** (this story's join reads the exemplar → trace link; it emits **no** metric).
- **The cardinality CI lint** (`work_item.id`/`run.id` ≠ metric label) — **Story 13.6** (this story **obeys**
  the law; 13.6 **enforces** it — and its lint is exactly what fails on the C3 mutation).
- **The collector pipeline + PII/secret redaction** — **Story 13.7** (the export backstop for the signals this
  view queries).
- **The SSE bus transport** (EventSource + BFF proxy) — **Story 8.2** (this story's live activity **rides** it;
  it adds no transport).
- **The per-user activity timeline** (`user.id` join) and per-project usage breakdown — **Story 13.10 / §17**
  (the same join re-keyed on `user.id`; soft-dep on 1.6).

This story ships the **per-Run OTel-trace deep-link contract (durable `ksquad.io/traceparent`, phase-duration
spans, URL-not-store), the per-ticket activity reconstruction join contract (`work_item.id` across all of a
ticket's Runs, in causal order, a query never a metric label), the active-Run live-activity-over-the-existing-
SSE-bus contract, the one-RBAC-wall scoping, the P0→P1 join stability, and the differential falsification** —
the observability half of the trace/per-ticket drill-down that 8.11's console surface consumes.

## References

- [Source: docs/bmad/04-observability-plan.md#3] — "The unit of correlation: the Run trace" + the **per-ticket
  activity view (Paperclip-style)**: a ticket spans multiple Runs, so per-ticket is a **query pattern joining
  traces + logs + `run_events` on `work_item.id`**, not a new signal; `work_item.id` stays off metric labels.
- [Source: docs/bmad/04-observability-plan.md#5.2] — the Run state-machine phase-duration spans the per-Run
  trace link shows.
- [Source: docs/bmad/04-observability-plan.md#1.2 / #5.6] — the cardinality law: `run.id`/`work_item.id`/
  `user.id` are trace/log/exemplar dimensions, **never** metric labels (13.6 enforces; this story obeys).
- [Source: docs/bmad/04-observability-plan.md#4.1] — the P0/P1 phasing the join is stable across.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 13 row 13.5] (Obs-plan §3, §5.2; pairs with console 8.11).
- [Source: docs/bmad/stories/13-1-every-run-one-distributed-trace.md] — the durable `ksquad.io/traceparent`
  spine + `work_item.id`-on-every-span/log/exemplar this story deep-links to and joins on.
- [Source: docs/bmad/stories/8-11-agent-detail-runs.md] — the console read model (done) that consumes this
  contract (per-Run trace deep-link + tabbed logs).
- [Source: docs/bmad/stories/8-2-live-run-progress-via-sse.md] — the one EventSource + BFF SSE proxy the
  active-Run live activity rides.
- [Source: docs/bmad/03-architecture.md#4.4 / #7.1 / #17.2 / #12.3] — SSE hub, `run_events` shim seam, per-Run
  metering spine, and the one deny-by-default RBAC wall.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, Observability Agent) — construction-time contract via runnable differential
falsification (`per-ticket-trace-activity-check.py`, the Epic-13 / 8.11 model-check pattern).

### Debug Log References

- `python3 per-ticket-trace-activity-check.py` → exit 0 (the "per-ticket metrics-dashboard" anti-pattern trips
  all six C1-C6; the join-query model holds C1-C6 and reconstructs ticket W-500 across all three Runs
  fail→reclaim→resume as one causal timeline).
- `--mutate={REQUEST_TIME_LINK,LATEST_RUN_ONLY,WORKITEM_LABEL,POLL_ACTIVITY,BESPOKE_AUTHZ,REQUIRE_P1}` → each
  exits 1 with the mapped invariant RED; no vacuous survivors (REQUIRE_P1 also trips C2 — acceptable, C6 is the
  mapped tooth).

### Completion Notes List

- Authored the observability-side contract for Story 13.5 as the **complement** of the done 8.11 console read
  model: 8.11 is *where you look* (the agent-detail page + per-Run trace-link affordance); 13.5 is *what the
  trace/per-ticket view is guaranteed to join on and how it stays a query, not a new signal*. No scope overlap:
  the boundary table (§ "Scope & boundary vs 8.11") pins each half.
- **Load-bearing cruxes proven with teeth:** (C1) each Run's trace link resolves from the **durable
  `ksquad.io/traceparent`** (resolves even for a completed Run whose trace is closed) — a URL to the existing
  trace store, not an in-console reimplementation; (C2, the crux) a ticket's activity reconstructs across
  **ALL** its Runs by joining traces + logs + `run_events` on `work_item.id`, in causal order — the
  latest-Run-only mutation (dropping the retry/reclaim attempts) turns the check RED; (C3, the cardinality
  crux) the view is a **query over the id dimensions**, and materializing a `per_ticket_activity{work_item_id=…}`
  metric turns it RED — the exact regression 13.6's lint fails on; (C4) active = live over the existing SSE
  bus, completed = durable-only (no polling); (C5) one shared deny-by-default RBAC wall, scoped,
  existence-hiding, no new store; (C6) the join is stable across the P0→P1 seam — P1 only deepens the per-Run
  trace, it does not change the join key or the set of Runs the ticket spans.
- Runtime proof (the real trace-store deep-link, the live per-membership scoped RBAC on the Go apiserver, the
  SSE active-Run activity stream, and the actual trace + log + `run_events` join) is owned by the console E2E +
  apiserver read-model tests on the actual stores. This check guards the construction-time contract obs-plan §3
  + the epic asked for.

### File List

- `docs/bmad/stories/13-5-per-run-per-ticket-trace-activity.md` (new) — this story.
- `docs/bmad/spikes/bench/per-ticket-trace-activity-check.py` (new) — C1-C6 runnable differential falsification.
