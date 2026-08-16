# Story 12.1: Domain event seam (transactional Postgres outbox + NATS relay, at-least-once)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The FIRST Epic-12 story — the event seam every plugin (12.2 subscribe, 12.3 GRAIL,
> 12.4 guardrail) rides.** CEO decision 2026-08-11 (**overrides ADR-023 r6**): *"store the
> data in Postgres, flow the events on NATS."* Postgres stays the **sole source of truth**
> (ADR-001); event **delivery** moves to a NATS/JetStream bus. The mechanism is a
> **transactional outbox**: when a Run / work item / memory record / sync result changes
> state, an **append-only event row is written in the SAME Postgres transaction** as the
> state change — atomic, so there is **no dual-write hole** (never state-without-event,
> never event-without-state). A **decoupled relay worker** tails the outbox out-of-band
> (`LISTEN/NOTIFY` + poll), publishes each unflushed row to a JetStream subject
> `ksquad.{entity}.{project}.{squad}.{event_type}`, and **stamps `published_at`**,
> **republishing unflushed rows on failure/restart** — so delivery is **at-least-once even
> if NATS is down**. The relay is **never in the write path or the apiserver's readiness**,
> so **NATS being unavailable never blocks a Run, a claim, a memory write, or a sync** — the
> outbox is the durable retry buffer. The seam is **observable via the §17.2 OTel pipeline**
> (outbox depth, unflushed lag, publish failures, JetStream consumer lag). A dual-write
> (event in a separate txn), a subject that drops the taxonomy, a relay that stamps
> `published_at` without a successful publish (or drops the row on failure), a state change
> that commits without an event, a mutated/deleted committed event row, a relay wired into
> the write path or readiness, or a missing OTel signal is a **regression**. Read AC1, AC3,
> and AC5 literally.

## Story

As **the system**,
I want a **domain event seam** — every state change on a Run, work item, memory record, or
sync result appends an event in the **same transaction** as the change (transactional
outbox, durability), and a **decoupled relay worker** publishes it to a NATS JetStream
subject `ksquad.{entity}.{project}.{squad}.{event_type}` (stamping `published_at`,
republishing unflushed rows on failure) so delivery is **at-least-once even when NATS is
down** and the relay can **never block the core** —
so that **plugins have a durable, ordered, replayable event stream to subscribe to (Epic 12)
without any plugin ever building an outbox consumer, without a dual-write divergence, and
without NATS liveness ever gating a Run/claim/write.**

## Context & prerequisites (read first)

- **PRD / epic:** `docs/bmad/04-epics-and-stories.md` Epic 12 row **12.1** — a domain event
  seam, *"Postgres for durability, NATS for event flow (CEO 2026-08-11)"*: an append-only
  event row in the **same transaction** as the state change; a **relay worker** publishes
  it to `ksquad.{entity}.{project}.{squad}.{event_type}` and stamps `published_at`,
  **republishing unflushed rows** on failure/restart → **at-least-once even if NATS is
  down** (outbox = durable retry buffer, no dual-write divergence); observable via §17.2
  OTel (outbox depth, unflushed lag, publish failures, consumer lag). **[CEO decision
  overrides ADR-023.]** Subjects are part of the versioned event catalog (§10.2).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§17.4 / ADR-023 (r13)** — Plugin Architecture & Event Seam (the load-bearing
    section, read it whole). *Postgres stores, NATS flows, plugins observe.* Domain events
    append to a **transactional Postgres outbox in the same txn** as the state change; a
    **relay worker** tails the outbox, **publishes each event to a JetStream subject** and
    stamps `published_at`, **republishing unflushed rows** on failure/restart — so a slow,
    failing, or absent plugin, or an unavailable NATS, **can never block a Run, a claim, or
    a memory write.**
  - **§6.6** — coordination events: every §6 state transition is **emit-only downstream**
    (the transition flows on the event bus as a **non-custodial projection** — never a
    capability; §6 fenced claim / no-P2P is untouched, see 12.4).
  - **§4** — Postgres is the **sole source of truth** (ADR-001); the single-stateful-
    dependency principle is **relaxed for the plugin event seam only** (CEO-named trade).
    NATS/JetStream holds only in-flight/replayable event copies (retention = a catch-up
    buffer, **not** a store of record).
  - **§17.2** — the OTel pipeline the seam's four signals ride (opt-in export, ADR-029).
  - **§10.2** — versioned event catalog / subject-taxonomy spec-drift discipline.
- **Where this seam is produced vs. consumed:**
  - **9.4** (`docs/bmad/stories/9-4-nats-jetstream-subchart.md`) brings up NATS/JetStream in
    the chart and **wires the relay's URL + subjects + PVC** — the *packaging* of this seam.
    12.1 pins the *seam-logic contract* (same-txn append, at-least-once republish,
    decoupling, observability) that the wired relay must satisfy.
  - **12.2** is the plugin-facing `nats_sub(...)` subscribe API; **12.3** is GRAIL, the
    first consumer; **12.4** proves plugins are **structurally unable** to re-enter
    coordination (the one-way seam guardrail). 12.1 is the **producer half** all three ride.
- **The four entity families (the epic's "Given"):** the seam covers **Runs** (§8
  lifecycle), **work items** (§6 state transitions + 8.14a operator moves), **memory
  records** (§6.x writes, feeding 12.3 GRAIL), and **sync results** (§5.4 repo-sync mirror
  transitions, e.g. the r14 `check_run.failed` event). Every state change across **all
  four** appends exactly one event.
- **Durability model (no dual-write hole):** the event row is committed **in the same
  transaction** as the state change. This is the whole reason for an outbox rather than a
  publish-then-commit or commit-then-publish: a crash in the window between two independent
  writes would leave state advanced with no event (lost) or an event with no state
  (phantom). Same-txn makes it **atomic** — both or neither.
- **Delivery model (at-least-once, NATS-down-safe):** the relay is **out-of-band** — it is
  **not** in the reconcile/coordination transaction and **not** an apiserver readiness gate.
  It scans **unflushed rows** (`published_at IS NULL`, ordered by `seq`), publishes each to
  its subject, and **stamps `published_at` only on a successful publish**. A publish failure
  (including NATS wholly down) **leaves the row unflushed** to be retried on the next
  tick/restart. Consequences: **at-least-once** (never dropped), **no divergence** (Postgres
  is authoritative), and **NATS-down never blocks a write** (the write already committed).
- **Scope guard:** 12.1 is the **producer contract** — same-txn append, relay
  at-least-once + `published_at` + republish, decoupling, and the four OTel signals. The
  **chart bring-up + relay wiring** is 9.4; the **plugin subscribe API** is 12.2; the
  **coordination-path guardrail** (one-way seam, subscribe-only creds, non-custodial
  payloads) is 12.4. This story adds **no coordination path** — §6 fenced claim / no-P2P is
  untouched; events are one-way projections (outbox→NATS→plugins), and nothing a plugin
  publishes re-enters coordination.

## Acceptance Criteria

**AC1 — the event row is appended in the SAME transaction as the state change (the
durability crux, no dual-write hole).**
Given a state change on any entity, When it commits, Then the append-only event row is
written **in the same Postgres transaction** as the state change — **atomic**: both commit
or neither. A crash in the window can never leave **state advanced with no event** (lost) or
an **event with no state** (phantom). A **dual-write** — the event appended in a separate
transaction, or published directly and the state committed after — is a **regression**.

**AC2 — the relay publishes to the full-taxonomy subject and stamps `published_at` exactly
once (the delivery crux).**
Given an unflushed outbox row, When the relay publishes it, Then it publishes to
**`ksquad.{entity}.{project}.{squad}.{event_type}`** (the §10.2 versioned taxonomy, so
plugin wildcard subscriptions match) and **stamps `published_at`** so the row is **not
re-scanned**. A subject that **drops the taxonomy prefix** (plugins miss it) or a relay that
**never stamps `published_at`** (the row redelivers forever, the outbox grows unbounded) is
a **regression**.

**AC3 — at-least-once even if NATS is down; unflushed rows are republished (the resilience
crux).**
Given NATS is unavailable when a state change commits, When the relay runs (and on every
later tick/restart), Then the write **still committed**, the event sits **unflushed**
(`published_at IS NULL`), and on NATS recovery it is **published and stamped — delivered
at-least-once, never dropped**. A relay that **stamps `published_at` without a successful
publish** (at-most-once — the event is lost) or that **never re-scans unflushed rows** after
a restart (a once-failed row is never retried) is a **regression**.

**AC4 — every one of the four families emits; the outbox is append-only (the completeness
crux).**
Given a state change on a **Run, work item, memory record, or sync result**, When it
commits, Then **each** family appends **exactly one** event row, and a committed outbox row
is **immutable** (append-only — never updated except the `published_at` stamp, never
deleted by the write path). A family whose state change **commits without an event**, or a
committed event row that is later **mutated or deleted**, is a **regression**.

**AC5 — the relay never blocks the core (the isolation crux, NATS-down-safe).**
Given NATS is down (or the relay is failing/absent), When a Run/claim/memory/sync write
occurs, Then the write **commits regardless** and the **apiserver stays ready** — the relay
is **out-of-band**, **not** in the write transaction and **not** a readiness gate. A relay
**wired into the write path** (a publish failure rolls back the state change) or into
**apiserver readiness** (NATS-down → core unready) is a **regression**.

**AC6 — the seam is observable via the §17.2 OTel pipeline (the operability crux).**
Given the seam is running, When metrics are scraped, Then it emits **all four** §17.2
signals — **outbox depth**, **unflushed lag**, **NATS publish failures**, and **JetStream
consumer lag** — so an operator can see a growing backlog or a stalled relay. A **missing
signal** (the operator flies blind on backlog/lag) is a **regression**.

## Tasks / Subtasks

- [x] **Pin the construction-time contract** as a runnable falsification check
  (`docs/bmad/spikes/bench/event-seam-outbox-check.py`) — a faithful executable model of the
  §17.4 seam: a `Store` with real transactions (state + append-only outbox), a NATS stub
  that can be "down", the decoupled relay worker (scan-unflushed → publish → stamp), the four
  entity emitters, and the OTel probe.
- [x] **Six checks C1–C6 ↔ AC1–AC6**, GREEN on the §17.4/ADR-023-conformant baseline.
- [x] **9-mutation battery**, each flipping its designated check RED — DUAL-WRITE,
  WRONG-SUBJECT, NO-STAMP, AT-MOST-ONCE, NO-REPUBLISH, INCOMPLETE-COVERAGE, MUTABLE-OUTBOX,
  RELAY-BLOCKS-CORE, UNOBSERVABLE. Every check is both satisfiable (baseline GREEN) and
  falsifiable (a dedicated killing mutation); genuine coupling (e.g. relay-in-write-path
  breaks both at-least-once and readiness) is reported, not hidden.
- [x] `python3 event-seam-outbox-check.py` → **exit 0**.
- [ ] **(Epic 12 build, later)** the real Postgres `outbox` table + same-txn emit helper
  wired into the §6/§8 mutation paths (Runs, work items, memory, sync), the apiserver relay
  worker (`LISTEN/NOTIFY` + poll, JetStream publish, `published_at` stamp, republish), and
  the §17.2 OTel instruments — proven against a live Postgres + NATS by the apiserver
  integration suite. **12.1 pins the contract those satisfy; 9.4 wires the deployment.**

## Dev Notes

- **Why a model check, not Go:** k8squad ships the API-group scaffold + `pkg/coord` spine;
  there is **no Epic-12 relay artifact to ground against yet**. Per the Epic-8/9/11 pattern
  (e.g. `nats-jetstream-check.py`, `plugin-coordination-guardrail-check.py`,
  `repo-sync-reconciler-check.py`), this story pins the **construction-time contract** as a
  runnable falsification harness so the acceptance is **falsifiable now** and the build
  (owned by the Epic 12 implementation ticket) has a red/green target. When the real relay +
  `outbox` table land, a file-grounded Layer B (snapshot + text-mutation flip, as in the 9.x
  checks) is the natural follow-on.
- **Same-txn is the whole point (AC1):** the model commits state and event as one atomic
  unit; the DUAL-WRITE mutation splits them into two commits and injects a crash in the
  window, leaving state advanced with no event → C1 RED. This is why an outbox beats a
  publish-then-commit: there is no window to lose an event in.
- **`published_at` is the at-least-once ledger (AC2/AC3):** the relay stamps it **only** on
  a successful publish, so the set `{published_at IS NULL}` is exactly "still owed." NO-STAMP
  redelivers forever (C2 RED) and NO-REPUBLISH / AT-MOST-ONCE lose the guarantee (C3 RED) —
  and NO-STAMP also trips C3 and AT-MOST-ONCE couples with C2 because the stamp is the shared
  ledger both lean on; the bench reports that coupling rather than hiding it.
- **Decoupling is structural, not best-effort discipline (AC5):** the relay reads the outbox
  out-of-band; it is not in the write txn and readiness never references NATS. The
  RELAY-BLOCKS-CORE mutation publishes synchronously in the write path and gates readiness on
  the bus — with NATS down the state change rolls back and the apiserver goes unready (C5 RED,
  and correctly C3 too: coupling the relay in also kills at-least-once). This is the §17.4
  "NATS-down never blocks the core" isolation made falsifiable.
- **No-P2P preserved:** the seam is one-way (outbox→NATS→plugins); §6 fenced claim / no-P2P
  and the coordination custody path are untouched. 12.4 proves nothing a plugin publishes
  re-enters coordination; 12.1 only guarantees the *forward* emission is durable and honest.

## Testing

- **Runnable check:** `python3 docs/bmad/spikes/bench/event-seam-outbox-check.py` → **exit 0**
  — baseline GREEN on C1–C6; all 9 mutations flip their target RED; every check is both
  satisfiable and falsifiable, no vacuous survivor.
- **Deferred to Epic 12 build (integration):** the real `outbox` table + same-txn emit helper
  on the §6/§8 mutation paths, the apiserver relay worker (`LISTEN/NOTIFY` + poll → JetStream
  publish → `published_at` stamp → republish-unflushed), and the four §17.2 OTel instruments
  — proven against a live Postgres + NATS by the apiserver integration suite. **9.4** proves
  the chart bring-up + relay wiring; **12.4** proves the one-way guardrail.

## References

- [Source: docs/bmad/04-epics-and-stories.md] — Epic 12 row 12.1 (domain event seam;
  same-txn outbox + relay + `published_at` + republish → at-least-once even if NATS down;
  §17.2 observability). CEO decision overrides ADR-023.
- [Source: docs/bmad/03-architecture.md#17.4] — Plugin Architecture & Event Seam (the
  load-bearing spec, ADR-023 r13); §6.6 (coordination events, emit-only downstream), §4
  (single-source-of-truth + the NATS trade), §17.2 (OTel pipeline), §10.2 (versioned event
  catalog / subject taxonomy).
- [Source: docs/bmad/stories/9-4-nats-jetstream-subchart.md] — the chart that brings up
  NATS/JetStream and wires this relay's URL + subjects + JetStream PVC (the deployment half).
- [Source: docs/bmad/spikes/bench/plugin-coordination-guardrail-check.py] — Story 12.4, the
  one-way-seam / non-custodial-payload guardrail this producer seam feeds (no-P2P intact).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, Architect / agent 216ef42c) — construction-time contract via
runnable falsification check (`event-seam-outbox-check.py`, Epic-8/9/11 model-check pattern).

### Debug Log References

- `python3 event-seam-outbox-check.py` → **exit 0**. Baseline GREEN on C1–C6; the 9-mutation
  battery all flipped their target check RED. Reported (not hidden) coupling: NO-STAMP↔C3,
  NO-REPUBLISH↔C2, RELAY-BLOCKS-CORE↔C3 — each a genuine seam property (the `published_at`
  ledger and the write-path decoupling are load-bearing across more than one AC).

### Completion Notes List

- Modeled and falsified the §17.4/ADR-023 (r13) event seam with teeth via a 9-mutation
  broken-seam battery. **Load-bearing cruxes proven:** (C1) the event row is appended **in
  the same transaction** as the state change — a DUAL-WRITE (separate txn + crash in the
  window) leaves state without an event → C1 RED (no dual-write hole); (C2) the relay
  publishes to the **full `ksquad.{entity}.{project}.{squad}.{event_type}` taxonomy** and
  **stamps `published_at` exactly once** — a dropped-taxonomy subject or an unstamped row
  (redelivers forever) trips C2 RED; (C3) delivery is **at-least-once even if NATS is down**
  — the write commits, the row buffers unflushed, recovery delivers it once; stamping without
  a good publish (at-most-once) or never re-scanning unflushed rows trips C3 RED; (C4) **all
  four families** (Run/work-item/memory/sync) emit **exactly one** append-only row — a
  skipped family or a mutated committed row trips C4 RED; (C5) the relay **never blocks the
  core** — with NATS down the write commits and the apiserver stays ready; wiring the relay
  into the write path or readiness trips C5 RED (and, correctly, C3); (C6) the seam is
  **observable via all four §17.2 signals** (outbox depth, unflushed lag, publish failures,
  consumer lag) — dropping one trips C6 RED.
- **Postgres-authoritative, NATS-flow-only is the through-line:** Postgres stays the source
  of truth (ADR-001); NATS carries only replayable copies; the relay decouples them so
  NATS-down never blocks a Run/claim/memory/sync write. The seam is **one-way** — §6 fenced
  claim / no-P2P is untouched (12.4 owns that guardrail).
- **Runtime proof deferred to the Epic 12 build ticket** — the real `outbox` table + same-txn
  emit helper on the §6/§8 mutation paths, the apiserver relay worker, and the §17.2 OTel
  instruments — proven against a live Postgres + NATS by the apiserver integration suite.
  This check guards the construction-time contract the epic asked for, and is the red/green
  target that build (and 9.4's wiring) lands against.

### File List

- `docs/bmad/spikes/bench/event-seam-outbox-check.py` (new) — C1–C6 runnable falsification
  check, 9-mutation broken-seam battery.
- `docs/bmad/stories/12-1-domain-event-seam.md` (this file) — the first Epic-12 story.

### Dev build delivered (ISI-2663, 2026-08-16) — PR #51 (K8squad/K8squad)

The "runtime proof deferred to the Epic 12 build ticket" above is now built and pushed as
**PR #51** (branch `feature/isi-2663-events-relay`, stacked on #49 `coord.outbox` substrate;
retargets to `main` when #49 merges). It lands the C1–C6 red/green target above against real
code:

- **`pkg/events`** — `Capture` / `CaptureForWorkItem` (same-txn append, AC-a/C1), the
  `Relay` worker (LISTEN/NOTIFY on `coord_outbox` + poll fallback → publish
  `ksquad.{entity}.{project}.{squad}.{event_type}` composed from columns → set-once
  `published_at` → at-least-once even if NATS down, AC-b/C2/C3/C5), the four §17.2 OTel
  signals (AC-c/C6), and `PgWaker`/`SQLStore` bindings. The nats.go JetStream client is
  isolated in **`pkg/events/jetstream`** so `pkg/events`/`pkg/coord` build without NATS.
- **Capture wiring** — the production §6.2 claim (`coord.ProdClaimer`) co-commits one
  `work_item`/`claimed` outbox event via `WithOutboxCapture()` (opt-in; on in the apiserver
  run-loop, off for the 0001-only spine chaos gate).
- **`cmd/event-relay`** — standalone worker driven by the Story 9.4 `event-relay` ConfigMap.
- **Tests** — 15 pure-Go unit tests prove C1–C6 with in-memory fakes (default lane, green);
  `-tags=integration` (DATABASE_URL) proves same-txn atomicity + set-once/append-only schema
  guards on real Postgres; `-tags=chaos` `TestSpineProdOutbox` (0001+0003) proves the wired
  claim co-commits one event 1:1 with the §6.5 audit row; `-tags=integration` (NATS_URL)
  proves end-to-end JetStream publish + set-once.
