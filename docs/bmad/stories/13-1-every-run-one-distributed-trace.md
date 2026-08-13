# Story 13.1: Every Run = one distributed trace — the durable-correlation spine

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE OTel SPINE FOUNDATION (obs-plan §3 "the unit of correlation: the Run trace", §6
> "logging", OBS-1 + OBS-6).** Every other observability story projects off this one: 13.2's coordination
> metrics carry exemplars *to these spans*, 13.4's token metering rolls up on `ksquad.run.id` / `work_item.id`
> *joined through this trace*, 13.5's console drill-down *links to this trace*, 13.10's user-scoped
> telemetry *rides `ksquad.user.id` on these spans/logs*. The deliverable is a single, standing law made
> real: **one Run is one trace, and all three pillars (traces, logs, metric exemplars) join on the Run.**
> The load-bearing invariant is **"trace context is durable state on the `Run` CR, not in-memory reconciler
> continuity"**: a level-triggered, idempotent reconcile loop (§12 arch) that keeps the trace root only in
> `context.Context` restarts a Run into a **second, disconnected trace** the moment the operator fails over —
> silently fragmenting the very correlation the story exists to guarantee. That is a **correctness failure of
> the observability contract, not a cosmetic gap.** Read AC2 and AC3 literally.

## ⚠️ Scope & phasing — honor the arch's P0/P1 split (read first)

The obs-plan (§4.1) and arch (§4.6/§13.5) **phase** distributed tracing deliberately: in-service spans +
`run.id`-on-every-log are **P0 (MVP)**; full cross-sandbox `traceparent` stitching is a **defined P1
fast-follow**. This story ships **both halves of the epic-13.1 AC**, split along that seam so nothing
false-starts and nothing is a surprise later:

| Concern | Phase | This story delivers |
|---|---|---|
| OTel SDK + `slog`/`otelslog` (Go) + `pino` (BFF) wired into every service with **noop-on-unset** | **P0** | §A wiring + §D the four-field log-correlation contract |
| In-service spans (reconcile phases, claim, dispatch, memory op) with `ksquad.run.id` stamped on every span/log/exemplar | **P0** | §B in-service span tree + the correlation-key contract |
| **Durable** trace-context on the `Run` CR (`ksquad.io/traceparent` status annotation) so the trace **survives a controller restart** | **P0** | §C — the crux invariant (AC2/AC3). *Durable state, not in-memory continuity.* |
| Full `traceparent` **propagation across the seam crossings** (operator → shim → agent → memory) so a Run is **one connected trace end-to-end** | **P1** | §E the §3 propagation contract + **reserving the A2A / MCP / SSE metadata fields NOW** (retrofitting propagation later is the expensive path OBS-6 exists to avoid) |
| Metrics instruments, cardinality CI gate, collector/redaction pipeline, per-Run console drill-down | **elsewhere** | 13.2/13.3/13.4 (metrics), 13.6 (cardinality lint), 13.7 (collector+redaction), 13.5/8.11 (console) — **consumed/observed, not built here** |

**⚠️ Scope pin (this story instruments, it does not decide).** This story adds **zero** new architectural
decisions and **zero** new CRD fields for shape — it reads `ksquad.run.id` / `work_item.id` /
`initiatedByUserId` that Stories 1.2 / 1.6 / 2.1 already put on the Run and the coordination record, and it
writes exactly **one** new piece of durable state: the `ksquad.io/traceparent` **status** annotation on the
`Run` CR (a status write, not a spec field — the operator owns it, §5.2). The **cardinality law** (`run.id`
is a trace/log/exemplar dimension, **never** a metric label) is *enforced* by 13.6's CI gate; this story
merely *obeys* it. The **redaction backstop** (secrets/PII stripped before export) is *built* by 13.7's
collector; this story's obligation is the **service-side** half — never span-attribute or log a secret or raw
agent content in the first place (§1.4, AC5).

**One-line boundary:** this story makes the Run the join key for all three pillars and makes that join
**survive a restart and a service-boundary crossing** — it delivers the correlated trace/log spine; the
metrics, the CI cardinality gate, the collector redaction, and the console drill-down are the stories that
ride on top of it.

## Story

As **the KSquad control plane (operator, apiserver, memory service) and the console BFF**,
I want **every Run to open exactly one distributed trace rooted at `ksquad.run.id`, to carry that trace
context as durable state on the `Run` CR (so it survives a controller failover) and across every
service-boundary crossing (so the operator → apiserver → shim → agent → memory hops are one connected trace,
not a forest of orphans), and to have `slog`+`otelslog` (Go) / `pino` (BFF) auto-stamp
`trace_id`/`span_id`/`ksquad.run.id`/`service.name` on every log line**,
so that **an operator can follow one Run end-to-end across all three pillars from a single correlation key,
the correlation is not silently broken by a controller restart (durable, not in-memory) or a service
boundary (propagated, not dropped), turning observability on is an operator config and never a redeploy or a
change in Run behavior (noop-on-unset), and no secret or untrusted agent content ever leaks into a span or a
log line — closing the NFR-OBS1/2 correlation half of the observability spine that every downstream Epic-13
story assumes but does not itself establish.**

## Context & prerequisites (read first)

- **Observability plan:** `docs/bmad/04-observability-plan.md`
  - **§3 "The unit of correlation: the Run trace"** — the authoritative trace shape (root = Run; the span
    tree: reconcile phases → claim → A2A dispatch → shim execute → agent turns → memory ops → SSE progress)
    **and the propagation contract table** (the seam crossings that must carry `traceparent`, and their
    owners). *This story's whole spec is the elaboration of §3.* Note the load-bearing sentence: **"The
    CR-annotation hop is what makes the trace survive a controller restart — the reconcile loop is
    idempotent and level-triggered, so the trace context must be durable state, not in-memory continuity."**
  - **§1.1** — the standing law: *"Three pillars correlate or they are noise. Every metric data point
    carries an exemplar to a trace; every log line carries `trace_id`/`span_id`; every span carries the same
    `ksquad.run.id`. The join key across all three pillars is the Run."* This story **is** that law made real.
  - **§1.4 / §6 redaction** — secrets and untrusted agent content never enter telemetry: only the opaque
    `ksquad.user.id` (UUID), hashes, lengths, kinds, and provenance IDs — never credentials, usernames,
    emails, session tokens, or raw memory/work-item/model text (AC5, service-side half; 13.7 is the backstop).
  - **§1.5 "Instrument once, phase the export" (noop-on-unset)** — the SDK is wired into every service from
    day one; providers are **noop when `OTEL_EXPORTER_OTLP_ENDPOINT` is empty** — zero overhead, zero risk.
    Turning observability on is an **operator config, not a redeploy** (AC4).
  - **§4.1 phasing** — P0 = in-service spans + `run.id` on every log/exemplar (ships **without** cross-sandbox
    stitching); P1 = full `traceparent` propagation across operator → shim → agent → memory (specced here,
    metadata fields reserved now). This story honors that split (see the scope table above).
  - **§6 logging** — `slog`+`otelslog` (Go) auto-carry `trace_id`/`span_id`/`ksquad.run.id`/`service.name`;
    console (Node) uses `pino` with the same fields injected server-side in the BFF; JSON out; the collector
    adds k8s resource attrs. Three log classes kept distinct (`run_events` audit is authoritative, **not**
    replaced by stdout).
  - **§2 reuse map** — kept-verbatim implementation patterns from Sympozium (ISI-1406, PR #11/#18):
    **noop-on-unset providers; `slog`+`otelslog`; HTTP-transport auto-instrumentation;** the traceparent
    annotation on the CR is the KSquad translation of Sympozium's "traceparent annotation on the AgentRun CR".
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§5.2 Run reconcile** — the phases this story spans (Pending → ClaimingSandbox → Dispatching → Running
    → Collecting → terminal); the operator owns the `Run.status` writes (so the `ksquad.io/traceparent`
    status annotation is an operator write, in the **same commit** as the phase/step advance — §6.4 idempotency).
  - **§7 shim / A2A** — the southbound bus is **A2A** (no NATS for the Run path); `traceparent` rides **A2A
    task metadata** (the metadata field this story reserves for P1), and SSE progress events carry `run.id` +
    `span_id` for stitching back into the trace at the apiserver hub.
  - **§8 memory** — agent → ksquad-memory is **MCP**; `traceparent` rides **MCP request metadata** (reserved).
  - **§12 arch patterns** — the reconcile loop is **level-triggered and idempotent**; a Run that dies silently
    or an operator that fails over re-enters reconcile with **no in-memory continuity** — which is exactly why
    the trace root must be **durable on the CR** (§C, the crux). This is the same durability argument Story
    3.2 makes for `next_attempt_at` (the backoff clock survives a restart because it is in Postgres, not RAM);
    here the *trace context* survives a restart because it is on the CR, not in `context.Context`.
- **Depends on:**
  - **Story 1.2** (ISI-2188 — the six v1alpha1 CRD types; `Run.status` is the surface the `traceparent`
    annotation is written to; no new field, a status annotation).
  - **Story 2.1** (ISI-2191 — the coordination schema; `work_item.id` correlation and the `run_events`/audit
    spine that logs project off, §6 log class 1).
  - **Story 3.1** (ISI-2201 — the reconcile state machine + durable `reconcile_step`; the spans this story
    opens are the phase transitions 3.1 defines, and the `traceparent` annotation is written in the same
    §6.4 transaction as the `reconcile_step` advance).
  - **Story 1.6** (ISI-2304 — `Run.spec.initiatedByUserId`; the operator stamps `ksquad.user.id` on the Run
    root span/logs from it, §3 propagation table row 2). *Soft dep:* if 1.6 has not landed, the trace is
    truthful without the user dimension; 13.10 threads it (flagged, not blocking).
- **Blocks / is consumed by:** **13.2** (coordination metrics — exemplars link to these spans), **13.4**
  (token metering — rolls up on `run.id`/`work_item.id` joined through this trace), **13.5 / 8.11** (console
  per-Run trace drill-down — deep-links to this trace), **13.6** (cardinality lint — enforces the `run.id`≠label
  law this story obeys), **13.7** (collector + redaction — the export backstop for these signals),
  **13.10** (user-scoped telemetry — rides `ksquad.user.id` on these spans/logs).

## The correlation model (authoritative — §A/§B, obs-plan §3)

**§A — the SDK wiring (P0, every service, noop-on-unset).** Each Go service (`ksquad-operator`,
`ksquad-apiserver`, `ksquad-memory`) and both shims wire the OTel Go SDK + the `slog`→`otelslog` bridge; the
console BFF wires `@opentelemetry/sdk-node` + `pino`. **Providers are noop when the OTLP endpoint is unset**
(Sympozium pattern): with no endpoint, the tracer yields non-recording spans, **zero spans are exported, and
the service's behavior is byte-for-byte identical** to the exporter-configured path — the only difference is
whether telemetry leaves the process (AC4). This is what makes "turn observability on" an operator config,
not a redeploy or a risk.

**§B — the in-service span tree (P0), rooted at the Run.** The Run is the **root span** and the correlation
key. Each service opens spans for its own work, all carrying `ksquad.run.id` (+ `ksquad.work_item.id`,
`ksquad.user.id`, `ksquad.team`, `ksquad.project`, `service.name`, per §4.3):

```
TRACE ROOT: Run <ksquad.run.id>                          (operator, Run controller — §5.2)
├─ reconcile.Pending→ClaimingSandbox → span: sandbox.claim         (warm-pool ctrl §5.4)
├─ reconcile.Dispatching             → span: a2a.task.submit  ── traceparent crosses to shim (P1, §E) ──▶
├─ reconcile.Collecting              (artifacts → object store)     (operator §5.2)
└─ Run terminal: Succeeded|Failed|Canceled|Paused → run_events + (13.2) ksquad.run.completed
```

At P0 the operator/apiserver/memory subtrees are each internally connected; the **cross-sandbox** hop
(`a2a.task.submit` → `shim.task.execute`) is stitched at **P1** (§E). Even at P0, **every log line the Run
emits in any service carries `ksquad.run.id`** (from the durable CR field, not the tracer), so per-Run log
correlation works **before** cross-boundary stitching lands — the two are independent (that independence is
AC4's noop teeth and AC1's log contract).

## The durable trace-context crux (authoritative — §C, the load-bearing invariant)

A Run's trace root is minted when the operator first reconciles it out of `Pending`. The reconcile loop is
**level-triggered and idempotent** (§12 arch): on an operator restart / leader failover, the **new** leader
re-reads the `Run` CR and re-enters reconcile with **no in-memory continuity** — the `context.Context` that
held the trace root is gone. If the trace root lives only in that context, the resumed reconcile **mints a
fresh trace_id**, and the Run's post-restart spans hang off a **second, disconnected trace** — the operator
looking at "the trace for Run X" sees only half of it, and the two halves never join. **This silently
violates "one Run = one trace."**

**The fix (mirrors Story 3.2's durable `next_attempt_at`):** the operator writes the W3C `traceparent` of
the Run root span to a **durable `Run.status` annotation `ksquad.io/traceparent`**, in the **same commit** as
the reconcile-step/phase advance (§6.4 transaction). On **any** re-entry — normal reconcile, crash mid-Run,
leader failover — the reconciler **reads the annotation first and re-parents its spans off the durable root**,
never mints a second root for a Run that already has one. The trace context is **durable state on the CR**,
exactly as the backoff clock is durable state in Postgres (3.2) — recovery reads the record, not RAM.

- **First reconcile** (no annotation): mint root, **write `ksquad.io/traceparent`** in the step-advance commit.
- **Re-entry** (annotation present): **read it, continue the same trace** — child spans link to the durable
  root; the trace_id is stable across the restart.
- **Idempotent:** writing the annotation is a no-op if it already matches; a crash between minting the root
  and committing the annotation re-enters as "first reconcile" (re-mints — acceptable, the pre-crash root
  exported nothing durable) — but once the annotation is committed, the root is **pinned** for the Run's life.

This is the KSquad translation of Sympozium's "traceparent annotation on the `AgentRun` CR" (obs-plan §2),
and it is **why the CR-annotation hop is in the §3 propagation contract at all**: it is the hop that crosses
**time** (a restart), the sibling of the hops that cross **service boundaries** (§E).

## The log-correlation contract (authoritative — §D, obs-plan §6)

Every log line a service emits **inside a Run's execution** auto-carries **four fields**:
`trace_id`, `span_id`, `ksquad.run.id`, `service.name`. This is **not** hand-threaded per call site — it is
structural:

- **Go:** `slog` with the **`otelslog` bridge** pulls `trace_id`/`span_id` from the active span in
  `context.Context`, and `ksquad.run.id`/`service.name` from a logger bound to the Run at reconcile entry.
  A log call that **bypasses the bridge** (a raw `log.Printf`, or a `slog` logger constructed without the
  handler) emits a line with **none** of the four fields — an **un-joinable** line that breaks §1.1. The
  contract is: **all Run-scoped logging goes through the bridged logger**; the falsification (F2) proves a
  bypassed line is detectable and forbidden.
- **BFF (Node):** `pino` with a server-side child logger bound per request, injecting the same four fields
  from the propagated context; the BFF **never** trusts a client-supplied `trace_id` (it derives it from the
  server span).
- **`ksquad.run.id` is available even when the tracer is noop** (AC4): it comes from the **durable Run field**
  bound to the logger, not from the span — so with the exporter unset, log lines still carry `run.id`
  (per-Run log correlation survives), they simply lack a `trace_id` (no recording span). Turning the exporter
  on adds `trace_id`/`span_id`; it never changes whether `run.id` is present.

**Three log classes stay distinct (§6):** the `run_events`/`audit_log` Postgres rows are the **authoritative**
operator-facing record and are **not** replaced by stdout; this story's stdout/structured logs are the
**diagnostic** class, correlated to the same Run but never the source of truth for the audit. Observability
*projects* the audit spine; it does not become it.

## The propagation contract (authoritative — §E, P1, obs-plan §3 table)

For a Run to be **one connected trace end-to-end**, `traceparent` must cross **every** service boundary. Drop
it at any one hop and the trace **fragments into a forest**: the operator's subtree, the shim's subtree, and
the memory subtree become three unrelated traces with no common root — the operator can no longer follow one
Run across services (the exact failure this story exists to prevent). The seam crossings and their owners:

| Boundary | Carrier | Owner | Phase |
|----------|---------|-------|-------|
| console/CLI → apiserver (request) | authenticated session → `ksquad.user.id` on request context (RBAC middleware, ISI-2303) resolves before any span opens | auth/BFF middleware | P0 (identity) |
| apiserver → `Run` CR (create) | `Run.spec.initiatedByUserId` → operator stamps `ksquad.user.id` on the root span/logs | apiserver + Run controller (§5.2) | P0 |
| operator → apiserver (coordination writes) | gRPC/HTTP OTel propagator (auto, HTTP-transport instrumentation) | control plane | P0 |
| **controller ↔ `Run` CR (async, cross-restart)** | **`Run.status` annotation `ksquad.io/traceparent`** — the durable §C hop that crosses *time* | Run controller (§5.2) | **P0 (§C)** |
| operator/apiserver → shim | **A2A task metadata** `traceparent` field | `internal/a2a` (§7) | **P1** — reserve field now |
| shim → agent runtime | env `TRACEPARENT` (Sympozium Job-level pattern) + in-proc | shim | P1 |
| agent → ksquad-memory | **MCP request metadata** `traceparent` | `internal/memory` MCP server (§8) | P1 — reserve field now |
| shim → apiserver SSE hub | SSE event carries `run.id` + `span_id` for stitching | `internal/sse` (§7) | P1 |

**Reserve the metadata fields at P0 even though stitching is P1 (OBS-6).** The A2A task-metadata
`traceparent` field, the MCP request-metadata field, and the SSE `run.id`+`span_id` fields are **defined in
the wire contract now**, populated with the durable root's context, and simply **not yet consumed** into a
single stitched trace until P1 — because **retrofitting propagation onto a shipped wire protocol is the
expensive path**. A P0 shim writes the field; a P1 collector/consumer stitches it. This is the one forward
obligation this story places on the shim (§7) and MCP server (§8) epics.

## Acceptance Criteria

**AC1 — one Run opens exactly one trace rooted at `ksquad.run.id`; every span and log line joins on it.**
Given a Run that executes, When any service (operator, apiserver, memory, BFF) emits a span or a log line for
it, Then the span carries `ksquad.run.id` (+ `service.name`, `work_item.id`, and — where 1.6 has landed —
`ksquad.user.id`) and the log line auto-carries **all four** of `trace_id`/`span_id`/`ksquad.run.id`/`service.name`
via `otelslog` (Go) / `pino` (BFF); And the Run's spans across a single service form **one** connected
subtree rooted at the Run (no orphan roots within a service); And **per-Run log correlation works at P0**
(every log line carries `run.id`) **independently of** cross-boundary span stitching (which is P1, §E).

**AC2 — trace context is DURABLE state on the `Run` CR and SURVIVES a controller restart/failover (the crux).**
Given a Run whose root span was minted on first reconcile, When the operator writes the reconcile-step
advance, Then it writes the W3C `traceparent` to the durable **`Run.status` annotation `ksquad.io/traceparent`**
in the **same commit** (§6.4 transaction); And on **any re-entry** — normal reconcile, crash mid-Run, or a
**leader failover to a fresh process with no in-memory continuity** — the reconciler **reads the annotation
first and re-parents its spans off the durable root**, so the Run remains **exactly one trace (one stable
`trace_id`) across the restart**; And a design that keeps the trace root only in `context.Context`, minting a
fresh root on the resumed reconcile, produces **two disconnected traces for one Run** — a correctness failure
of the correlation contract, not a cosmetic gap.

**AC3 — annotation writes are idempotent; a crash before the annotation commits re-mints, after it commits pins.**
Given a Run being reconciled, When the reconciler writes `ksquad.io/traceparent`, Then the write is a **no-op
if the annotation already matches** (re-reconcile does not thrash the root); And a crash **between** minting
the root and committing the annotation re-enters as "first reconcile" and **re-mints** (acceptable — the
pre-commit root exported nothing durable), while a crash **after** the annotation commits **re-parents off the
pinned root** (never re-mints) — so once pinned, the root is stable for the Run's life, exactly as
`reconcile_step` (3.1) and `next_attempt_at` (3.2) are durable-once-committed.

**AC4 — noop-on-unset: observability on/off is config, never a redeploy and never a change in Run behavior.**
Given the OTLP endpoint is **unset**, When a Run executes, Then the tracer yields **non-recording spans**,
**zero spans are exported**, and the Run's phase outcome and coordination writes are **byte-for-byte identical**
to the exporter-configured path; And **`ksquad.run.id` is still stamped on every log line** (it comes from the
durable Run field, not the span), so per-Run log correlation survives with the exporter off — the only
difference the exporter makes is whether `trace_id`/`span_id` are present and whether telemetry leaves the
process. Turning observability on is an **operator config (set the endpoint), not a redeploy**.

**AC5 — no secret and no untrusted agent content ever enters a span attribute or a log line (service-side half).**
Given any span or log line this story emits, When it is constructed, Then it carries **only** bounded/opaque
values — `ksquad.run.id`/`work_item.id`/`user.id` (UUIDs), `service.name`, phase/enum values, and content
**hashes/lengths/kinds** — and **never** a credential (`CLAUDE_CODE_OAUTH_TOKEN`, bearer/API-key shapes), a
username/email/session token, or **raw** agent-authored content (memory bodies, work-item text, model output);
And this is the **service-side** discipline (never log/attribute a secret in the first place, §1.4) — the
collector redaction processor (13.7) is the **defense-in-depth backstop**, not the primary control, on this path.

**AC6 — the P1 propagation fields are RESERVED in the wire contracts now, even though stitching is P1.**
Given the A2A task-metadata, MCP request-metadata, and SSE-event wire contracts, When a P0 shim/apiserver
dispatches/streams, Then it **populates** the `traceparent` field (A2A metadata, MCP metadata) and the
`run.id`+`span_id` fields (SSE) with the durable root's context — **the fields exist and are filled from day
one** — even though a **single stitched cross-service trace is consumed at P1**; And every §E boundary is
accounted for, so no boundary silently drops `traceparent` (which would fragment the trace into a forest).
This is the forward obligation on the shim (§7) and MCP (§8) epics — reserve now, stitch at P1; **do not** ship
the wire protocol without the field and pay the retrofit cost later.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/run-trace-correlation-check.py` — stdlib-only, `python3` it directly. A
**differential** falsification (same shape as the Story 2.4 / 3.1 / 3.2 checks), not a happy-path demo. It
proves the durable-correlation contract has teeth by contrasting a **NAIVE in-memory-context** design (that
fragments a Run into two traces on restart) against the **durable `ksquad.io/traceparent`** design that does
not, and it stacks the seam-propagation, log-correlation, noop, and redaction teeth on top:

- **(A) NAIVE in-memory trace context — root lives only in `context.Context`.** The operator mints a root,
  reconciles a phase, then the process **restarts** (fresh reconciler, no in-memory continuity). The naive
  resume mints a **fresh** trace_id → the Run's spans split across **two** trace_ids. The check asserts the
  naive design **detectably fragments** (a Run maps to >1 trace root). If (A) ever stops fragmenting, the
  check fails **loud** — the harness lost its detecting power.
- **(B) DURABLE traceparent annotation — the §C crux.** The operator writes `ksquad.io/traceparent` to the
  `Run.status` in the **same commit** as the step advance; on restart the fresh reconciler **re-reads it and
  re-parents**, so the Run is **exactly one trace_id** across the restart. Asserts one-Run-one-trace survives
  a failover. *Mutation-proven:* deleting the annotation **write** (collapsing B to A) turns the check **RED**
  — the load-bearing "durable, not in-memory" invariant now has teeth.
- **(F1) seam-propagation teeth (AC6/§E).** The operator → shim hop injects `traceparent` into the A2A task
  metadata; the shim opens its `shim.task.execute` span as a **child of the dispatch span** (same trace). The
  check asserts the shim subtree shares the Run's trace root. *Mutation-proven:* deleting the A2A-metadata
  `traceparent` inject makes the shim mint a **new root** → the trace fragments into a forest (operator
  subtree + orphan shim subtree) → the check turns **RED**.
- **(F2) log-correlation teeth (AC1/§D).** Every log line emitted inside a Run's span must carry **all four**
  of `trace_id`/`span_id`/`ksquad.run.id`/`service.name`. The check routes Run logging through the
  `otelslog`-bridged logger and asserts the four fields on every line, then drives a **bypass** (a raw logger
  with none of the fields) and asserts it is **detectably un-joinable**. *Mutation-proven:* routing one Run
  log call through the raw (unbridged) logger turns the check **RED**.
- **(F3) noop-on-unset teeth (AC4).** With the exporter endpoint **unset**, the check asserts: **zero spans
  exported**, the Run's phase outcome **identical** to the exporter-on path (behavior-neutral), **and**
  `ksquad.run.id` **still present on every log line** (from the durable Run field) while `trace_id` is absent
  (non-recording span). Turning observability on/off never changes Run behavior or drops `run.id`.
- **(F4) redaction teeth (AC5).** The check scans every emitted span attribute and log body for credential
  shapes (`CLAUDE_CODE_OAUTH_TOKEN`, bearer/API-key), usernames/emails/session tokens, and raw
  agent-content markers, and asserts **none appear** — only UUIDs, enums, hashes, lengths, kinds.
  *Mutation-proven:* span-attributing a token (or logging raw agent text) turns the check **RED**.
- **(F5) idempotent annotation write (AC3).** A re-reconcile with the annotation already present asserts the
  write is a **no-op** (root not re-minted); a crash **before** the annotation commit re-mints (acceptable),
  a crash **after** it re-parents off the pinned root (never re-mints).

Exits non-zero if a Run fragments into >1 trace across a restart, a seam drops `traceparent` (forest), a Run
log line is missing any of the four correlation fields, the noop path changes Run behavior or drops `run.id`,
a secret/PII/raw-content value reaches a span or log, or the annotation write re-mints a pinned root. **The
headline invariant is mutation-checked:** deleting the durable-annotation write (B→A) turns the check **RED**
— the "durable trace context, not in-memory continuity" contract is falsifiable, not decorative.

## Out of scope (owned elsewhere)

- **The metric instruments themselves** (`ksquad.coord.*`, `ksquad.run.*`, `ksquad.agent.tokens`, …) — Stories
  **13.2/13.3/13.4/13.9** (this story provides the **spans+exemplar target** they link to, not the metrics).
- **The cardinality CI lint** (grep metric labels vs the §5.6 allowlist; `run.id`≠label) — **Story 13.6**
  (this story **obeys** the law; 13.6 **enforces** it).
- **The collector pipeline + mandatory PII/secret redaction processor + SLO alerts** — **Story 13.7** (this
  story does the **service-side** never-log-a-secret half, AC5; 13.7 is the export backstop).
- **The `OTelConfig` CRD + reconciler that configures exporters** — Stories **1.5 / 13.8** (this story is
  noop-until-an-endpoint-exists; 13.8 is how the endpoint gets set declaratively).
- **The per-Run / per-ticket console trace drill-down** — Stories **13.5 / 8.11** (deep-links to the trace
  this story produces).
- **User-scoped telemetry dimensions** (`ksquad.user.id`/`user.role` on auth+RBAC signals) — **Story 13.10**
  (rides on the spans/logs this story establishes; soft-dep on 1.6/Epic 15).
- **The actual P1 cross-service stitching consumer** — the tail-sampling/stitching in the collector (§4.2/§10)
  consumes the reserved fields (AC6); this story **reserves and populates** the fields, it does not build the
  stitching backend.

This story ships the **OTel SDK wiring (noop-on-unset), the in-service span tree rooted at the Run, the
durable `ksquad.io/traceparent` annotation that survives a controller restart, the four-field
`slog`/`otelslog`+`pino` log-correlation contract, the reserved P1 propagation fields, the service-side
secret/PII discipline, and the differential falsification** — the correlated trace/log spine that every
downstream Epic-13 story rides on.
