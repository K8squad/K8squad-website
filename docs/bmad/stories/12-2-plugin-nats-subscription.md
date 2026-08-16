# Story 12.2: Plugin NATS subscription (`nats_sub`, wildcard subjects, JetStream replay/catch-up)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The consumer half of the event seam — the plugin-facing API is `nats_sub`, not a bespoke
> SDK.** 12.1 pinned the **producer** (same-txn Postgres outbox → relay → JetStream,
> at-least-once even if NATS is down). 12.2 pins how a **plugin subscribes**: given the NATS
> connection + the `ksquad.{entity}.{project}.{squad}.{event_type}` subject taxonomy, a plugin
> author writes `nats_sub("ksquad.run.*.*.completed")` and **receives event JSON with NATS
> wildcard flexibility** (`*` one token, `>` tail) and **JetStream replay/catch-up** for events
> it missed while offline (durable consumer — core NATS is fire-and-forget). Its **config +
> outbound credentials come from per-user Secret refs** (BYO, Epic 7 §11) declared **per
> Project/squad** — never a shared master credential, never inline. The plugin runs
> **out-of-process, never in the reconcile path**, its NATS creds are **subscribe-only** (no
> PUB onto coord subjects) and the events are **non-custodial** projections — so a
> **failing/dead/absent plugin, or NATS being wholly down, can never block or slow a Run, a
> claim, or a memory write** (the relay is decoupled; the outbox buffers). A subscribe API that
> forces exact subjects or a bespoke outbox-consumer contract, a core-NATS/ephemeral binding
> that drops offline events, a shared/inline credential, a PUB grant on coord subjects, a
> custodial payload, or a subscribe path wired into the write path / apiserver liveness is a
> **regression**. Read AC1, AC2, and AC5 literally.

## Story

As a **plugin author**,
I want to **subscribe to NATS subjects** — `nats_sub("ksquad.run.*.*.completed")` — with
**wildcard flexibility** and **JetStream replay/catch-up** for events I missed while offline,
with my **config + outbound credentials from per-user Secret refs** (BYO, Epic 7) declared per
Project/squad, and with my plugin running **out-of-process** so that a failing/dead/absent
plugin — or NATS being down — **can never block or slow the core** —
so that **I can react to platform events in a few lines without touching core code, without
building an outbox consumer (poll/dedup/cursors), and without ever becoming a coordination
path or a dependency the core's liveness rests on.**

## Context & prerequisites (read first)

- **PRD / epic:** `docs/bmad/04-epics-and-stories.md` Epic 12 row **12.2** — *"As a plugin
  author, I want to subscribe to NATS subjects — `nats_sub("ksquad.run.*.*.completed")` — so I
  can react to platform events in a few lines … **Given** NATS connection details + subject
  taxonomy, **When** a plugin subscribes (declared per Project/squad in config), **Then** it
  receives event JSON on its subjects with **NATS wildcard** flexibility and **JetStream
  replay/catch-up** for events missed while offline; **And** plugin config + outbound
  credentials come from **per-user Secret refs** (BYO, Epic 7); **And** a failing/dead/absent
  plugin — or NATS being down — **cannot block or slow the core** …"* Plugin runs
  out-of-process, never in the reconcile path. **Plugin-facing API is NATS subscribe, not a
  bespoke SDK/outbox contract** (CEO plugin-simplicity goal).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§17.4 / ADR-023 (r13)** — Plugin Architecture & Event Seam (read whole). *Postgres
    stores, NATS flows, plugins observe.* **Subject taxonomy**
    `ksquad.{entity}.{project}.{squad}.{event_type}` lets plugins subscribe with NATS wildcards
    (e.g. `ksquad.run.*.*.completed`, `ksquad.*.projectX.>`). Plugins **subscribe to NATS
    subjects**; **JetStream retains events so a plugin can replay/catch up** on what it missed
    (core NATS for fire-and-forget). **Plugin model — out-of-process, per Project/squad**;
    outbound credentials use **BYO per-user Secret refs (§11)**, never a shared master
    credential. **Guard 1–3:** the plugin contract is **read-only event consumption** — no
    claim/lease/fence/handoff/mutate surface; nothing a plugin publishes re-enters coordination
    (12.4 owns the full guardrail).
  - **§10.2** — versioned event catalog / subject-taxonomy drift discipline: a consumer **pins
    an event-schema rev** (`pkg/events@rev`); producer changes are additive-or-gated so a
    third-party plugin survives platform evolution.
  - **§4 / §16** — NATS/JetStream is **stateful dependency #2**, event-flow-only (JetStream
    retention = catch-up buffer, not a store of record); Postgres stays sole source of truth
    (ADR-001).
- **Where this sits in the seam:**
  - **12.1** (`stories/12-1-domain-event-seam.md`, done) is the **producer** — same-txn outbox
    append → relay → `published_at` → at-least-once. 12.2 is the **consumer** the epic's
    "Given NATS + taxonomy, When a plugin subscribes" clause names.
  - **9.4** (`stories/9-4-nats-jetstream-subchart.md`, in_review) brings up NATS/JetStream in
    the chart and hands the apiserver the relay config (subject prefix, decoupling flags). Its
    shipped `event-relay.yaml` ConfigMap is the **producer contract the subscribe side mirrors**
    (same subject taxonomy prefix; same "never blocks the write path" isolation).
  - **12.3** GRAIL is the **first real consumer** (`nats_sub` on memory subjects → OTLP/GRAIL);
    **12.4** proves plugins are **structurally unable** to re-enter coordination (subscribe-only
    creds, one-way seam, non-custodial payloads). 12.2 introduces the subscribe API those ride;
    it adds **no publish/mutate affordance** (that discipline is 12.4's to enforce end-to-end).
- **Why `nats_sub`, not an SDK (the CEO plugin-simplicity goal):** the pure-outbox-exposed-to-
  plugins option is rejected in §17.4 precisely because *"every plugin dev would have to build
  an outbox consumer — polling, dedup, cursors."* 12.2's contract is that the plugin-facing API
  is **plain NATS subscribe** — the platform's outbox/relay is hidden behind the bus.
- **Scope guard:** 12.2 is the **subscribe contract** — `nats_sub` + wildcard, durable
  JetStream replay/catch-up, per-user-Secret config/creds per Project/squad, out-of-process
  isolation, and the subscribe-only / non-custodial property of the API it introduces. The
  **producer** (outbox→relay) is 12.1; the **chart bring-up + relay wiring** is 9.4; the
  **first consumer** is 12.3; the **end-to-end one-way guardrail** (a HostilePlugin cannot
  coordinate no matter what it publishes/replays) is 12.4. This story adds **no coordination
  path**.

## Acceptance Criteria

**AC1 — `nats_sub` with NATS wildcard flexibility (the ergonomics crux).**
Given the NATS connection + the `ksquad.{entity}.{project}.{squad}.{event_type}` taxonomy, When
a plugin calls `nats_sub("ksquad.run.*.*.completed")`, Then it **receives the event JSON** on
matching subjects with NATS **wildcard** semantics (`*` matches exactly one token; `>` matches
one-or-more trailing tokens) and a **non-matching** subject is **not** delivered. The
plugin-facing API is **`nats_sub`**, not a bespoke outbox-consumer SDK. An API that forces
**exact subjects** (no wildcard) or that replaces `nats_sub` with an **outbox-consumer
framework** the plugin must implement is a **regression**. *(Bench: C1; M1/M2.)*

**AC2 — JetStream replay/catch-up for events missed offline (the resilience crux).**
Given a plugin was **offline** while events were published on its subjects, When it reconnects
with its **durable JetStream consumer**, Then it **replays and catches up** on the missed events
from its last position — not just live fire-and-forget. A subscription bound to **core-NATS
fire-and-forget** (offline events lost) or an **ephemeral** consumer with **no durable cursor**
(a restart re-reads from "now") is a **regression**. *(Bench: C2; M3.)*

**AC3 — config + outbound credentials from per-user Secret refs, per Project/squad (the BYO
crux).**
Given a plugin is registered, When its subscribe config (subjects, durable name) and outbound
credentials (NATS account + any external creds) are resolved, Then they come from **per-user
Secret refs** (BYO, Epic 7 §11) **declared per Project/squad** — never a **shared master
credential**, never an **inline** literal, never a global/unscoped config. A shared/master
credential, an inline secret, or an unscoped config is a **regression**. *(Bench: C3; M4/M5/M6.
Ties to Story 7.1 per-user Secret refs.)*

**AC4 — subscribe-only creds + non-custodial payloads (the read-only crux).**
Given the subscribe API this story introduces, When a plugin's NATS credentials and the
delivered event payload are inspected, Then the creds are **subscribe-only** — **no PUB grant
on coord subjects** (`ksquad.>` / any `ksquad.workitem.*.*.claimed`-shaped subject) — and the
event JSON is a **non-custodial projection** carrying **no live fence/claim/lease token** a
plugin could replay for custody. A **PUB grant** on coord subjects or a **custodial payload** is
a **regression**. *(Bench: C4; M7/M8. The full end-to-end guardrail — a HostilePlugin cannot
coordinate no matter what — is Story 12.4; 12.2 pins that the subscribe API adds no such
affordance.)*

**AC5 — a failing/dead/absent plugin — or NATS down — never blocks or slows the core (the
isolation crux).**
Given a plugin that is slow, crashed, absent, or a NATS that is **wholly down**, When a
Run/claim/memory write occurs, Then the write **commits regardless** and the **apiserver stays
ready** — the plugin runs **out-of-process**, **not** in the reconcile/write path, the relay is
**decoupled**, and apiserver liveness **never references** NATS or a plugin. A subscribe path
that lets a **stuck/absent consumer apply backpressure** to the relay/write path, that runs the
plugin **in-process** in the reconcile path, or that **gates apiserver liveness on NATS** is a
**regression**. *(Bench: C5; M9/M10/M11.)*

## Falsification bench

`docs/bmad/spikes/bench/plugin-nats-subscription-check.py` (stdlib only,
`python3 …/plugin-nats-subscription-check.py` → **exit 0**):

- **Layer A — model-based mutation battery.** A faithful model of the subscribe seam: a
  `JetStream` with retained messages + per-durable cursors + NATS **wildcard matching**
  (`nats_match`), the `nats_sub` API, the plugin credential/config source, the creds
  permission-set + event payload shape, and the out-of-process isolation of a core write. Five
  checks **C1–C5 ↔ AC1–AC5**; the §17.4-conformant baseline is **GREEN** on all five. An
  **11-mutation battery**, each flipping its designated check RED — NO-WILDCARD, BESPOKE-SDK,
  CORE-NATS/EPHEMERAL, SHARED-CRED, INLINE-SECRET, GLOBAL-SCOPE, PUB-GRANT, CUSTODIAL-PAYLOAD,
  IN-WRITE-PATH, IN-PROCESS, LIVENESS-GATE. A **vacuity guard** proves every check is both
  satisfiable (baseline GREEN) and falsifiable (a dedicated killing mutation).
- **Layer B — file-grounded pass** over pinned real artifacts: the shipped relay ConfigMap
  (`helm-chart-isi2149/templates/event-relay.yaml`, k8squad@`598f3f5`) whose **subject taxonomy
  prefix + decoupling flags** are the producer contract the subscribe side mirrors, and the
  normative **subscribe text-of-record in §17.4** (`nats_sub`, wildcard subjects, JetStream
  replay/catch-up, per-user Secret refs, out-of-process, read-only). Five detectors (FG1–FG5),
  each **passes on shipped text and flips on mutation** — teeth on the real artifacts.

Mutation → caught-by map:

| Mutation | Break | Caught by |
|---|---|---|
| M1 NO-WILDCARD (exact subjects only) | plugins can't `run.*.*.completed` | C1 |
| M2 BESPOKE-OUTBOX-SDK (not `nats_sub`) | plugin must build a consumer | C1 |
| M3 CORE-NATS / EPHEMERAL | offline events lost, no catch-up | C2 |
| M4 SHARED-MASTER-CRED | credential lock broken | C3 |
| M5 INLINE-SECRET | secret not a Secret ref | C3 |
| M6 GLOBAL-CONFIG-SCOPE | not per Project/squad | C3 |
| M7 PUB-GRANT on coord subjects | creds not subscribe-only | C4 |
| M8 CUSTODIAL-PAYLOAD | replayable fence token in event | C4 |
| M9 IN-RECONCILE-PATH | NATS/plugin-down blocks the write | C5 |
| M10 IN-PROCESS | plugin in the reconcile path | C5 |
| M11 NATS-GATES-LIVENESS | NATS-down → apiserver unready | C5 |

## Tasks / Subtasks

- [x] **Pin the construction-time contract** as a runnable falsification check
  (`docs/bmad/spikes/bench/plugin-nats-subscription-check.py`) — a faithful executable model of
  the §17.4 subscribe seam: JetStream retention + durable cursors + NATS wildcard matching, the
  `nats_sub` API, the credential/config source, the subscribe-only creds + non-custodial
  payload, and the out-of-process isolation of a core write.
- [x] **Five checks C1–C5 ↔ AC1–AC5**, GREEN on the §17.4/ADR-023-conformant baseline.
- [x] **11-mutation battery**, each flipping its designated check RED; a **vacuity guard**
  proves every check is both satisfiable and falsifiable (no vacuous survivor).
- [x] **Layer B file-grounded pass** — 5 detectors over the shipped relay ConfigMap
  (k8squad@`598f3f5`) + the §17.4 subscribe text-of-record; each passes on shipped text and
  flips on mutation.
- [x] `python3 plugin-nats-subscription-check.py` → **exit 0**.
- [ ] **(Epic 12 build, later)** the real plugin subscribe surface — a thin `nats_sub(subject,
  durable)` helper over the JetStream client (`pkg/events/jetstream`, landed with 12.1/ISI-2663)
  binding a **durable consumer** per plugin, the **per-Project/squad plugin config** (subjects +
  durable name) and **BYO per-user Secret** NATS account (subscribe-only), and an **event-schema
  rev pin** (§10.2) — proven end-to-end against a live NATS/JetStream by the plugin integration
  suite (a plugin subscribes, goes offline across N events, reconnects, replays all N). **12.2
  pins the contract that build satisfies; 9.4 wires the bus; 12.3 is the first consumer; 12.4
  proves the guardrail.**

## Dev Notes

- **Why a model check, not Go (same rationale as 12.1):** the producer half (`pkg/events` +
  `pkg/events/jetstream`) landed with ISI-2663/PR #51; the **plugin-facing subscribe helper +
  per-plugin config/creds** is the Epic-12 build ticket's to write. Per the Epic-8/9/11/12.1
  pattern, this story pins the **construction-time subscribe contract** as a runnable
  falsification harness so the acceptance is **falsifiable now** and the build has a red/green
  target. When the real `nats_sub` helper + plugin config land, a file-grounded Layer B over
  that artifact (as in 9.4) is the natural follow-on.
- **`nats_sub` is the whole API (AC1):** the CEO plugin-simplicity goal is that a plugin dev
  writes `nats_sub("ksquad.run.*.*.completed")` and nothing more — no poll loop, no cursor
  bookkeeping. NO-WILDCARD (exact subjects) defeats the ergonomics; BESPOKE-SDK re-imposes the
  outbox-consumer §17.4 explicitly rejects. Both trip C1.
- **Durable is the catch-up ledger (AC2):** JetStream retains events; a **durable** consumer's
  cursor is exactly "what this plugin has acked." CORE-NATS/EPHEMERAL drops the cursor, so an
  offline window is lost forever — C2 RED. This is the "replay/catch-up for events missed while
  offline" clause made falsifiable.
- **Subscribe-only + non-custodial bridges to 12.4 (AC4):** 12.2 introduces the subscribe API;
  it must not smuggle a publish/mutate affordance. The PUB-GRANT and CUSTODIAL-PAYLOAD mutations
  are the two ways the *subscribe surface itself* could reopen coordination — 12.4 then proves
  the property holds end-to-end against a HostilePlugin (every attack fails). The two stories
  are complementary, not redundant: 12.2 = "the API adds no affordance"; 12.4 = "no affordance
  exists anywhere, no matter what."
- **Isolation is structural (AC5):** the plugin is out-of-process and the relay reads the outbox
  out-of-band; a stuck/absent consumer cannot backpressure the producer, and liveness never
  references NATS. IN-WRITE-PATH / IN-PROCESS / LIVENESS-GATE each re-couple the core to the
  plugin/bus and trip C5 — the §17.4 "a failing/absent plugin, or NATS down, can never block a
  Run/claim/write" isolation made greppable. Mirrors 9.4's `relay.blocksWritePath: "false"` /
  `relay.natsHealthGatesApiserver: "false"` on the producer side.
- **No-P2P preserved:** the seam stays one-way (outbox→NATS→plugins); §6 fenced claim / no-P2P
  is untouched. 12.2 only guarantees the *consume* side is ergonomic, resilient, BYO-scoped, and
  read-only; 12.4 owns the end-to-end guardrail.

## Testing

- **Runnable check:** `python3 docs/bmad/spikes/bench/plugin-nats-subscription-check.py` →
  **exit 0** — baseline GREEN on C1–C5; all 11 mutations flip their target RED; the vacuity
  guard shows every check satisfiable AND falsifiable; 5 file-grounded detectors pass with teeth.
- **Deferred to Epic 12 build (integration):** the real `nats_sub(subject, durable)` helper
  over `pkg/events/jetstream` binding a durable consumer, per-Project/squad plugin config +
  BYO per-user Secret NATS account (subscribe-only), and the §10.2 event-schema rev pin —
  proven against a live NATS/JetStream by the plugin integration suite (subscribe → offline
  across N events → reconnect → replay all N). **9.4** wires the bus; **12.3** is the first
  consumer; **12.4** proves the one-way guardrail.

## References

- [Source: docs/bmad/04-epics-and-stories.md] — Epic 12 row 12.2 (plugin `nats_sub`; wildcard;
  JetStream replay/catch-up; per-user Secret refs; failing/absent plugin or NATS-down cannot
  block/slow the core; plugin-facing API is NATS subscribe, not a bespoke SDK).
- [Source: docs/bmad/03-architecture.md#17.4] — Subject taxonomy (`ksquad.{entity}.{project}.
  {squad}.{event_type}`, wildcards), Plugin subscribe (`nats_sub`, JetStream replay/catch-up),
  Plugin model (out-of-process, per Project/squad, BYO per-user Secret refs), Guard 1–3
  (read-only, no coordination re-entry); §10.2 (versioned event catalog / rev pin); §4/§16
  (NATS = stateful dep #2, event-flow-only).
- [Source: docs/bmad/stories/12-1-domain-event-seam.md] — the producer half (same-txn outbox →
  relay → at-least-once) this subscribe contract consumes.
- [Source: docs/bmad/stories/9-4-nats-jetstream-subchart.md] — the chart that brings up
  NATS/JetStream and ships the relay ConfigMap (subject prefix + decoupling flags Layer B reads).
- [Source: docs/bmad/spikes/bench/plugin-coordination-guardrail-check.py] — Story 12.4, the
  end-to-end one-way-seam / subscribe-only-creds / non-custodial-payload guardrail this
  subscribe API feeds (no-P2P intact).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, Architect / agent 216ef42c) — construction-time subscribe
contract via runnable falsification check (`plugin-nats-subscription-check.py`, Epic-8/9/11/12.1
model-check pattern).

### Debug Log References

- `python3 plugin-nats-subscription-check.py` → **exit 0**. Baseline GREEN on C1–C5; the
  11-mutation battery all flipped their target check RED; vacuity guard: every check satisfiable
  AND falsifiable; 5 file-grounded detectors (FG1–FG5) pass on shipped text and flip on mutation.

### Completion Notes List

- Modeled and falsified the §17.4 **plugin subscribe** contract with teeth. **Load-bearing
  cruxes proven:** (C1) the plugin-facing API is **`nats_sub` with NATS wildcard flexibility** —
  a plugin subscribes `ksquad.run.*.*.completed`, receives the matching event JSON, and a
  non-matching subject is not delivered; forcing exact subjects or a bespoke outbox SDK trips C1;
  (C2) **JetStream replay/catch-up** — a durable consumer replays events published while the
  plugin was offline; core-NATS/ephemeral loses them → C2 RED; (C3) config + creds from
  **per-user Secret refs per Project/squad** — shared master, inline, or global scope trips C3;
  (C4) the subscribe API is **subscribe-only + non-custodial** — a PUB grant on coord subjects or
  a replayable token in the payload trips C4 (12.4 owns the end-to-end guardrail); (C5) a
  **failing/dead/absent plugin or NATS-down never blocks/slows the core** — out-of-process,
  decoupled, liveness never references NATS; wiring the subscribe path into the write path /
  in-process / apiserver liveness trips C5.
- **`nats_sub`, not an SDK, is the through-line:** the platform's outbox/relay stays hidden
  behind the bus; a plugin author writes a one-line subscribe and gets wildcards + replay for
  free. The seam is **one-way** — §6 fenced claim / no-P2P is untouched (12.4 owns that
  guardrail; 12.3 is the first real consumer).
- **Runtime proof deferred to the Epic 12 build ticket** — the real `nats_sub(subject, durable)`
  helper over `pkg/events/jetstream`, per-Project/squad plugin config + BYO per-user Secret NATS
  account (subscribe-only), and the §10.2 event-schema rev pin — proven against a live
  NATS/JetStream by the plugin integration suite. This check guards the construction-time
  contract and is the red/green target that build lands against.

### File List

- `docs/bmad/spikes/bench/plugin-nats-subscription-check.py` (new) — C1–C5 runnable
  falsification check, 11-mutation battery + vacuity guard, 5 file-grounded detectors.
- `docs/bmad/stories/12-2-plugin-nats-subscription.md` (this file) — the Epic-12 subscribe story.
