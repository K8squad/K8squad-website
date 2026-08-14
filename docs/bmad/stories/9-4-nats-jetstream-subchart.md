# Story 9.4: NATS/JetStream event bus + apiserver outbox relay (chart dependency #2)

Status: in_review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The chart brings up the event bus, and the bus can never block the core.** One
> `helm install` yields Postgres (CNPG) + **NATS/JetStream** + operator + apiserver +
> memory + console. NATS is **stateful dependency #2** (CEO 2026-08-11: *"data in
> Postgres, events on NATS"*, §16/§17.4/ADR-023) — **single-replica default with a
> JetStream file-store PVC** whose StorageClass is `storage.nats.storageClassName`
> (parameterized exactly like Story 9.2, **never** the cluster default), **HA via a
> values toggle** (same shape as CNPG). The apiserver's **outbox relay publishes
> events to JetStream subjects** `ksquad.{entity}.{project}.{squad}.{event_type}`
> (Epic 12.1). The relay is **decoupled from the write path**: it tails the durable
> Postgres outbox out-of-band, republishes unflushed rows at-least-once, and is
> **never** a health gate — so **NATS being unavailable (or `nats.enabled=false`)
> never blocks a Run, a claim, or a memory write**. A JetStream-less NATS, a
> cluster-default JetStream PVC, a relay wired into apiserver readiness, a bus whose
> absence fails the core install, or NATS holding state of record is a **regression**.
> Read AC3 and AC5 literally.

## Story

As a **platform engineer installing KSquad on my own cluster**,
I want **the chart to bring up NATS with JetStream enabled as the plugin event bus —
single-replica by default with a JetStream PVC whose StorageClass I set (never the
cluster default), HA behind one values toggle — and the apiserver outbox relay wired
to publish events to it in a way that can never block a Run/claim/write**,
so that **one `helm install` yields the whole stack (Postgres + NATS + control plane),
plugins have a bus to subscribe to (Epic 12), and the core's install and liveness never
hard-depend on NATS.**

## Context & prerequisites (read first)

- **Epics:** `docs/bmad/04-epics-and-stories.md` Story **9.4** (Epic 9 install) — the
  chart brings up NATS/JetStream; the outbox **relay** publishes to it (Epic 12.1);
  **NATS unavailable never blocks a Run/claim/write** — the outbox buffers. Siblings:
  9.1 Gateway+HTTPRoute ([[isi-2250-story91-gateway-httproute]]), 9.2 StorageClass,
  9.5 auth-in-chart.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§16** (Deployment & install, S1 ≤4h) — *"one `helm install` brings up …
    **NATS/JetStream** (Helm dependency; JetStream enabled, **single-replica default
    with a JetStream PVC**, HA via values toggle — same packaging pattern as CNPG)."*
    NATS is event-flow-only; no state of record lives there.
  - **§17.4 / ADR-023** (Plugin Architecture & Event Seam — *Postgres stores, NATS
    flows, plugins observe*). Domain events append to a **transactional Postgres
    outbox in the same txn** as the state change (durability, at-least-once). A
    **relay worker** tails the outbox (`LISTEN/NOTIFY` + poll), **publishes each event
    to a NATS JetStream subject**, and stamps `published_at`, **republishing unflushed
    rows** on failure/restart. The relay runs **outside** the reconcile/coordination
    transaction, so *"a slow, failing, or absent plugin — or an unavailable NATS —
    can never block a Run, a claim, or a memory write."* Subject taxonomy
    `ksquad.{entity}.{project}.{squad}.{event_type}` (§10.2 versioned catalog).
  - **§16.2 / Story 9.2** (explicit StorageClass) — every PVC's `storageClassName`
    comes from values; the cluster default is a **misconfiguration that fails fast**.
    The JetStream PVC is one such PVC.
  - **§4** — Postgres is the **sole source of truth** (ADR-001); the single-dependency
    principle is **relaxed for the plugin event seam only** (CEO-named trade). NATS
    holds only in-flight/replayable event copies (JetStream retention = catch-up
    buffer, not a store of record).
- **Chart implementation:** the chart lives and is CI-tested in the **`k8squad`**
  source repo at `deploy/helm/ksquad/`. This story's chart work ships on
  `feature/isi-2253-nats-jetstream` (**PR #18**, commit `598f3f5`), branched off
  `5e6442d` (`feature/helm-exposure-storage` = 9.1/9.2). `ci/test.sh` lints + renders
  and asserts every guard (needs a `helm` binary). This story (ISI-2253) pins the
  **construction-time contract** those templates must satisfy and adds a `helm`-free
  falsification bench. A read-only snapshot of the shipped chart is re-vendored under
  `docs/bmad/spikes/bench/helm-chart-isi2149/` (see PROVENANCE.md).
- **Design choice — parent-rendered, not an upstream subchart.** The chart renders
  the NATS/JetStream workload **itself** (`templates/nats.yaml`: ConfigMap + headless/
  client Services + StatefulSet with a `volumeClaimTemplate`), **same packaging
  pattern as the CNPG `Cluster` CR** — chosen *specifically* so the JetStream PVC's
  `storageClassName` stays the first-class `storage.nats.storageClassName` knob.
  An upstream NATS subchart cannot template its PVC StorageClass from a parent value,
  which would silently reintroduce the cluster-default fallback that §16.2 forbids.
  "Subchart" in the CEO decision means *the chart bundles NATS*; parent-rendering
  honors that while keeping the storage guarantee. No operator is vendored, so the
  chart renders and lints **offline**.
- **Scope guard:** this story is the **bus + the relay wiring the chart owns**. The
  relay *worker code* and the event catalog are Epic 12.1/12.2; the apiserver
  Deployment is owned elsewhere — the chart hands it the relay config via an
  `*-event-relay` ConfigMap. Exposure is 9.1; StorageClass mechanics are 9.2; auth
  packaging is 9.5.

## Acceptance Criteria

**AC1 — NATS is brought up with JetStream ENABLED.** With `nats.enabled` (default
true), the chart renders a NATS StatefulSet whose config **enables JetStream** with a
file store (`jetstream { store_dir … }`), plus its headless + client Services and
config ConfigMap. A NATS without JetStream (core-NATS only, no replay substrate) is a
regression. *(Bench: C1; FG1.)*

**AC2 — Single-replica default; HA via a values toggle (CNPG pattern).** The default
profile renders **one** replica. Setting `nats.ha.enabled=true` with an odd
`nats.ha.replicas` (≥3) renders a **clustered JetStream RAFT quorum** (cluster routes
in the config, `replicas` honored) — the same toggle *shape* as CNPG
`storage.postgres.instances`. An even or `<3` HA replica count **fails fast** (RAFT
quorum). A hardcoded replica count that ignores the toggle is a regression.
*(Bench: C2 — differential default-vs-HA; C6 quorum fail-fast.)*

**AC3 — JetStream PVC StorageClass is parameterized, never the cluster default
(like 9.2).** The JetStream file-store PVC's `storageClassName` resolves from
`storage.nats.storageClassName` (falling back to the global `storage.storageClassName`)
and is stamped onto the `volumeClaimTemplate`. When neither is set **while
`nats.enabled`**, `helm template`/`install` **fails fast** naming the missing value —
never a silent cluster-default. A per-family override beats the global.
*(Bench: C3 — differential over two classes + fail-fast; FG2.)*

**AC4 — The apiserver outbox relay is wired to publish to NATS (Epic 12.1).** With
`events.relay.enabled` (default true), the chart renders an `*-event-relay` ConfigMap
carrying: the **JetStream bus URL** (`ksquad.nats.url` — release-derived
`nats://<release>-nats.<ns>.svc:4222` unless `events.relay.natsUrl` overrides),
`relay.jetstream: "true"`, and the **subject taxonomy prefix**
(`ksquad.{entity}.{project}.{squad}.{event_type}`). The URL is derived/values-driven,
never a hardcoded literal. *(Bench: C4; FG3.)*

**AC5 — NATS-unavailable NEVER blocks a Run/claim/write (the isolation crux, §17.4).**
The relay is **decoupled** from the write path by construction, and the chart's relay
config makes this explicit and greppable: `relay.decoupled: "true"`,
`relay.blocksWritePath: "false"`, `relay.natsHealthGatesApiserver: "false"`. Flipping
`blocksWritePath` to `"true"`, gating apiserver health on NATS, or placing the NATS
probe in the write path is a regression. Moreover **`nats.enabled=false` still installs
the core** — the relay renders and buffers in the durable Postgres outbox
(`relay.busBundled: "false"`), and the core Services/Postgres/operator config all still
render. NATS-down delays fan-out only. *(Bench: C5 — isolation invariants + bus-off
core-up; FG4.)*

**AC6 — Renders/lints offline; NATS holds no state of record.** The chart renders and
lints with no network and no vendored operator (parent-rendered workload). NATS is
**event-flow-only**: JetStream retention is a catch-up/replay buffer, and Postgres
stays the sole source of truth (ADR-001) — the story and chart docs state this
explicitly so no operator mistakes NATS for durable state. *(Bench: FG5 — no
`kind: Cluster`/CR pretending NATS stores of-record; docs assert event-flow-only.)*

## Falsification bench

`docs/bmad/spikes/bench/nats-jetstream-check.py` (stdlib only, `helm`-free):

- **Layer A — model-based mutation battery.** A faithful mini-renderer of the chart's
  NATS/JetStream workload, the StorageClass resolution + `ksquad.validate` fail-fast,
  and the event-relay ConfigMap. Six checks **C1–C6 ↔ AC1–AC6**; differential checks
  render two distinct value profiles (default single-replica/`std` vs
  HA-3/`nats-class`) and assert the output **tracks the input** — the teeth against
  hardcoding. Each broken-chart mutation is caught by its designated check going RED;
  the §16/§17.4-conformant baseline is GREEN on all six.
- **Layer B — file-grounded pass.** Reads the **pinned real chart snapshot**
  (k8squad@`598f3f5`), asserts the **shipped** templates satisfy each invariant, and
  text-mutates each to prove the detector flips — teeth on the real artifact. 5
  detectors (FG1 JetStream enabled, FG2 PVC class from values, FG3 relay→NATS URL +
  subjects, FG4 relay decoupled / bus-off-core-up, FG5 no state-of-record).

Mutation → caught-by map:

| Mutation | Break | Caught by |
|---|---|---|
| M1 disable JetStream (core-NATS only) | no replay substrate | C1 |
| M2 hardcode replicas, ignore ha toggle | HA toggle inert | C2 |
| M3 accept even HA replicas | no RAFT quorum | C6 |
| M4 accept `<3` HA replicas | no RAFT quorum | C6 |
| M5 JetStream PVC → cluster default | silent default StorageClass | C3 |
| M6 skip NATS StorageClass fail-fast | unset renders anyway | C3 |
| M7 hardcode relay NATS URL | ignores release/values | C4 |
| M8 drop subject taxonomy prefix | no subjects to publish on | C4 |
| M9 relay `blocksWritePath: true` | NATS-down blocks writes | C5 |
| M10 gate apiserver health on NATS | NATS-down blocks liveness | C5 |
| M11 bus-off fails core install | NATS a hard dep | C5 |

Run: `python3 docs/bmad/spikes/bench/nats-jetstream-check.py` (exit 0 = all teeth hold).
Full render/lint gate (needs `helm`): `k8squad` `deploy/helm/ksquad/ci/test.sh` — all
checks pass on `598f3f5` (helm v3.16.3), incl. 13 NATS render assertions + 3 NATS
fail-fast guards.

## Definition of Done

- [x] Construction-time contract (AC1–AC6) pinned against arch §16 / §17.4 / ADR-023 /
      §16.2.
- [x] Chart brings up NATS/JetStream + wires the outbox relay in `k8squad`
      (`deploy/helm/ksquad/`, PR #18 / `598f3f5`); `ci/test.sh` green under real helm.
- [x] Falsification bench green: C1–C6 baseline GREEN, 11 mutations caught, 5
      file-grounded detectors pass with teeth (`nats-jetstream-check.py`, exit 0).
- [x] Chart snapshot re-vendored (full chart @`598f3f5`) + PROVENANCE updated.

## Notes

- **k8squad is source of truth for the chart; ksquad holds the story + bench** — the
  vendored snapshot is a read-only fixture pinned to a commit.
- **NATS-down never blocks is the whole point** (§17.4, CEO isolation requirement).
  The relay is best-effort and out-of-band; the durable outbox is the at-least-once
  buffer. The chart makes the invariant *greppable* (`relay.blocksWritePath: "false"`,
  `relay.natsHealthGatesApiserver: "false"`) so the bench and any reviewer can assert
  it on the real artifact — the apiserver Deployment (owned elsewhere) must honor it.
- **Parent-rendered over subchart** is a deliberate call to preserve the §16.2
  no-cluster-default StorageClass guarantee; recorded in the chart `Chart.yaml` NOTE,
  the README event-bus section, and this story's Context.
