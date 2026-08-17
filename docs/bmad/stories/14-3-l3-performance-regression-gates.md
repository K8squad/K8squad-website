# Story 14.3: L3 performance regression gates [P1–P4 relative SLIs]

Status: ready-for-dev

<!-- ISI-2700. Epic 14, Wave-2 (E14.3–14.8). Authored by the Testing Architect.
     Falsification anchor: docs/bmad/spikes/bench/perf-regression-gate-check.py (green; M1–M4 red).
     Source-signal benches already landed: claim-latency-bench.sh, warmpool-claim/sizing-check.py,
     live-run-sse-check.py, live-runs-panel-sse-check.py, event-seam-outbox-check.py. -->

> **📉 THIS IS THE PERFORMANCE REGRESSION GATE — RELATIVE, NOT BRITTLE-ABSOLUTE.** A dedicated
> **`perf.yml`** lane (nightly + release + manual dispatch — **not** every PR) re-measures the four
> headline SLIs on **both `main` and the branch, in the same job on the same runner**, and asserts
> each SLI's **regression vs its pinned baseline** stays within tolerance. It **fails the build** on a
> real regression; it **rides through** a slow-runner morning because the ratio-to-main, not an
> absolute millisecond number, is what is gated. Final numeric curves (P1/P2 sizing) are spike-gated
> (**ISI-2113**) and land as tolerances tighten — the **gate mechanism ships now against defaults**,
> exactly as Story 3.5 shipped the warm-pool policy against defaults.

## Story

As **the platform maintainer defending the headline performance guarantees against silent drift**,
I want **an L3 perf lane that measures P1 claim latency, P2 warm-pool ready-count, P3 SSE throughput,
and P4 outbox delivery lag on both `main` and the branch in one job, and fails the build when a SLI
regresses beyond a relative tolerance vs its pinned baseline**,
so that **NFR-PERF1 "grab-time" claim latency, warm-pool warmth, live-progress throughput, and
write-path/plugin isolation are proven not to rot on every nightly and release — measured against
main, not asserted in a doc, and not brittle to CI-runner noise (PRD NFR-PERF1, S9, §17.4).**

## Context & prerequisites

- **PRD / NFRs:** `docs/bmad/02-prd.md` — **NFR-PERF1** (claim is "grab-time" under the warm pool),
  **S9** (warm-pool claim latency scenario), **FR-C1/C4** (warm-pool ready-count / sizing-as-policy),
  **NFR-USE** (live progress without lag).
- **Testing strategy:** `docs/bmad/05-testing-strategy.md` — **§5** the L3 table (the four P-rows this
  story implements — verbatim source-of-truth for the gate semantics), **§5 note** "relative
  thresholds, not brittle absolute numbers, since numeric tuning is spike-gated (ISI-2113)",
  **§8** (Go perf: `go test -bench` micro + SSE load driver macro), **§10** the `perf.yml` lane
  placement (nightly + release + on-demand, **not** a per-PR gate), **§12** traceability rows
  (L3 P1 §9.2 / P2 §9.2 / P3 §3.1+§17.2 / P4 §17.4).
- **Architecture:** `docs/bmad/03-architecture.md` — **§6.2** claim SQL (the P1 span under test),
  **§9.2** warm-pool ready-count & the (RuntimeClass × AgentRuntime) key (P2), **§9.3**
  teardown-and-replace / replenish (P2 cold-start), **§13/§4.4** the SSE progress bus (P3),
  **§17.4** the outbox delivery-worker isolation the write path must be independent of (P4).
- **Observability plan:** `docs/bmad/04-observability-plan.md` — **§17.2** the OTel span/metric
  taxonomy the perf tests read (claim span duration, `pool_hit`, SSE emit→deliver, outbox depth/lag);
  the metric names the tests assert on **must match** what Story 13.x emits — coordinate with the
  Observability Agent (13.1 run-trace, 13.2 coord metrics, 13.4 token metering) before pinning.

## Absorption / dependency ledger

This story **owns the gate comparator + `perf.yml` lane**. It **consumes** already-landed source-signal
benches rather than re-inventing measurement:

- **P1** claim latency ← `spikes/bench/claim-latency-bench.sh` (ISI-2113 field harness; p50/p95 per
  RuntimeClass), OTel claim-span duration (13.2).
- **P2** warm-pool ready-count ← `spikes/bench/warmpool-claim-check.py` (3.4) + `warmpool-sizing-check.py`
  (3.5); `pool_hit=warm|cold` gauge / cold-start rate.
- **P3** SSE throughput ← `spikes/bench/live-run-sse-check.py` (8.2) + `live-runs-panel-sse-check.py`
  (8.8f); emit→deliver latency + dropped-event count.
- **P4** outbox delivery lag ← `spikes/bench/event-seam-outbox-check.py` (12.1); outbox depth, delivery
  lag, dead-letter, circuit state — the §17.4 write-path-independence proof.

**Depends on:** Epic 3 (warm-pool controller, for P1/P2 signals), Epic 8.2 (SSE bus, P3), Epic 12.1
(outbox, P4), Epic 13.x (the OTel signal names). **Spike gate:** **ISI-2113** — ship relative gates
against default tolerances; tighten the numeric curves when the spike lands (mirrors 3.5).

## The P1–P4 cases ↔ signal ↔ gate ↔ spec

| Case | Signal (source bench / OTel) | Gate (relative unless noted) | Arch / §5 |
|------|------------------------------|------------------------------|-----------|
| **P1 · claim latency** (S9/NFR-PERF1) | claim span duration p50/p95 | p95 drift vs `main` ≤ `P1_TOL` (default +20%); **fails fast if no baseline** | §6.2 / §9.2 |
| **P2 · warm-pool ready-count** (FR-C1) | `pool_hit=warm\|cold`, cold-start rate per (RuntimeClass×AgentRuntime) | **interactive** cold-start rate ≤ floor (≈0); **batch exempt** | §9.2/§9.3 |
| **P3 · SSE throughput** (NFR-USE) | emit→deliver p95, dropped-event count at target concurrency | p95 drift ≤ `P3_LAT_TOL` **AND** dropped events **== 0** (zero-tolerance) | §3.1/§13/§17.2 |
| **P4 · outbox delivery lag** (§17.4) | write p95 healthy-plugin vs sick-plugin; outbox depth/lag/dead-letter | write p95 sick/healthy ≤ `P4_ISO_FACTOR` (default 1.5×) — **isolation, branch-internal** | §17.4 |

## Acceptance criteria

- **AC1 — Relative, not absolute.** The gate re-measures each SLI on **both `main` and the branch in
  the same job on the same runner** and asserts the **ratio-to-main** against a tolerance. A uniform
  CI-runner slowdown (both scale together) is **GREEN**; a real regression layered on a slow runner is
  **still RED**. No absolute millisecond threshold gates a merge (numeric curves land post-ISI-2113).
- **AC2 — P1 claim latency.** claim-span p95 drift vs `main` beyond `P1_TOL` **fails the build**; an
  improvement never gates. **Missing baseline → build FAILURE** (fail-fast, never silent-green — the
  F2-trap analogue of 14.2).
- **AC3 — P2 warm-pool.** An **interactive** tier whose cold-start rate rises above the policy floor
  **fails**; a **batch** tier that cold-starts is **exempt** (expected). Keyed per (RuntimeClass ×
  AgentRuntime).
- **AC4 — P3 SSE.** emit→deliver p95 drift beyond `P3_LAT_TOL` **fails**; **any** dropped event at
  target concurrency **fails** (zero-tolerance, not a relative budget).
- **AC5 — P4 outbox isolation.** write-path p95 under a **deliberately slow/failing plugin** must stay
  within `P4_ISO_FACTOR` of the healthy-plugin write p95 (proves §17.4 — a sick plugin never leaks
  backpressure onto the write path). Measured **branch-internal**, not vs main.
- **AC6 — Lane placement & artifacts.** Runs on **`perf.yml`** on **nightly + release + manual
  dispatch**, **not** on every PR (heavier; needs kind + Postgres + the SSE driver). Each run
  **publishes results as artifacts** (per-SLI ratio table) and — later — feeds the consumption/OTel
  dashboards the Observability Agent owns. **Not** a per-PR required check (§10.4 lists it lane-only).
- **AC7 — Skip-with-reason, never silent.** Any SLI whose source signal has not yet landed (e.g. P4
  before 12.1 merges) **skips with a printed reason**, never a silent pass — same discipline as 14.1/14.7.
- **AC8 — Falsification anchor is green and has teeth.** `perf-regression-gate-check.py` exits 0, and
  the documented mutations **M1–M4** each re-RED it (verified below). The Go perf lane is a faithful
  **1:1 translation** of this anchor's verdict table (as `TestSpine` is of `chaos-harness.py`).

## Falsification anchor (language-neutral, runnable now)

`docs/bmad/spikes/bench/perf-regression-gate-check.py` — stdlib-only differential, no wall-clock, no
RNG. It contrasts the arch-correct **relative** gate against the naive absolute / no-baseline /
tolerate-drops gates §5 rejects, and pins an **expected GREEN/RED verdict per scenario**; the check
asserts the gate agrees. Scenarios: `p1_no_change` (GREEN control), `p1_real_regression` (RED),
`p1_uniform_hw_slowdown` (GREEN — relative rides through), `p1_regression_on_slow_hw` (RED — still
caught), `p1_improvement` (GREEN), `p1_missing_baseline` (build FAILURE), `p2_interactive_warm`
(GREEN), `p2_interactive_coldstart_regression` (RED), `p2_batch_coldstart_exempt` (GREEN),
`p3_clean` (GREEN), `p3_dropped_events` (RED), `p3_latency_regression` (RED), `p4_isolation_holds`
(GREEN), `p4_isolation_break` (RED).

**Mutation contract (each headline tooth is falsifiable — verified 2026-08-17):**

| Mutation | Edit | Effect |
|----------|------|--------|
| **M1** | widen `P1_TOL` to 10.0 | `p1_real_regression` silently GREEN → check RED (exit 1) |
| **M2** | delete the `require_baseline` raise | `p1_missing_baseline` silently GREEN → check RED |
| **M3** | make `p3_gate` tolerate `dropped>0` | `p3_dropped_events` silently GREEN → check RED |
| **M4** | loosen `P4_ISO_FACTOR` to 99.0 | `p4_isolation_break` silently GREEN → check RED |

```
$ python3 docs/bmad/spikes/bench/perf-regression-gate-check.py   # exit 0
PERF-GATE OK — P1–P4 relative regression gates have teeth
$ # M1–M4 each -> exit 1 (verified)
```

## Implementation notes (for the Developer, in the k8squad Go repo)

- **`perf.yml`** workflow: `on: [schedule (nightly cron), release, workflow_dispatch]`; jobs:
  `p1-claim-latency`, `p2-warmpool`, `p3-sse-throughput`, `p4-outbox-lag`. Node 24-compatible action
  pins (`actions/checkout@v5`, `actions/setup-go@v6`, `actions/upload-artifact@v5`) per §10.3.
- **Baseline strategy:** check out `main` and the branch **in the same job**; run each bench against
  both; compute ratio. (No cross-run baseline store needed initially — same-job re-measure is the
  runner-noise defense of AC1. A pinned artifact store can follow once curves stabilize post-2113.)
- **P1/P2** ride `claim-latency-bench.sh` + the warm-pool checks against a **kind** cluster (reuse the
  `spine-chaos.yml` runner class, `ubuntu-latest-4-core`). **P3** uses a k6/vegeta-style SSE fan-out
  driver (§8 macro). **P4** drives `event-seam-outbox-check.py`'s slow-plugin arm against a real outbox.
- **Tolerances** (`P1_TOL`, `P3_LAT_TOL`, `P2_COLDRATE_FLOOR`, `P4_ISO_FACTOR`) live in one config;
  ISI-2113 tightens them. Assert against OTel metric **names** owned by Epic 13 — coordinate before pinning.
- **Not a PR gate.** Wire into branch protection as a **lane-only** check (§10.4 leaves perf off the
  per-PR required set); a red nightly opens a tracking issue, it does not block unrelated merges.

## Handoff

- **← Story Writer / Epics:** the 14.3 row (`docs/bmad/04-epics-and-stories.md`) + §5 L3 table.
- **→ Developer (k8squad):** implement `perf.yml` + the four Go bench jobs as a 1:1 translation of the
  falsification anchor's verdict table. Child dev issue carries the Go build + workflow work.
- **↔ Observability Agent:** align the OTel span/metric names P1–P4 assert on (claim span, `pool_hit`,
  SSE emit→deliver, outbox depth/lag) with 13.1/13.2 emission — tests and dashboards must agree.
- **↔ Code Reviewer (Amelia):** review the gate comparator for the relative-not-absolute invariant and
  the zero-tolerance P3 drop check.
