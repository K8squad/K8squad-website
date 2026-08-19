# Story 3.5: Warm-pool sizing as policy [GATE: ISI-2113 tuning]

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE ONE PLACE THE WARM-POOL TARGET `N` IS DERIVED (arch §9.2 "policy-driven, not fixed",
> FR-C4, NFR-SCALE2).** Story 3.4 built the `WarmPool` controller **mechanism** — bind a pooled pod at
> `claiming_sandbox`, trigger scale-up on a miss, replenish-and-teardown *toward a target* — and it
> deliberately treats that target `N` as an **opaque static input**. This story is the **policy** that
> computes `N`: the target ready-buffer is a **base-stock level** `N = ceil(λ·R + z·√(λ·R))` that
> **autoscales on the live claim-pressure signal** (`warmpool.claim.pressure`, obs §5.3), bounded by
> `[min, max]` so **idle cost is bounded**, sized **per (RuntimeClass × AgentRuntime image) key** by that
> key's own measured replenish time `R`, with **batch/non-interactive → `target=0`** (zero idle cost).
> The load-bearing properties are *correctness/cost* properties, not tuning knobs: **(1) the target carries
> the `z·√(λR)` safety stock** — drop it and the pool under-provisions and misses the warm-hit SLA under a
> claim burst; **(2) the target autoscales on the live pressure signal** — freeze it to a constant and it
> over-provisions idle pods at low load or misses at high load; **(3) idle cost is bounded** — the `max`
> cap stops a pressure spike from spawning runaway idle pods, the `min` floor keeps interactive warm, and
> `batch→0` pays nothing when nothing is interactive. A design that skips any of the three is a
> cost/correctness failure, not a tuning ticket.

## ⚠️ Gate status — ISI-2113 has LANDED with MEASURED numbers (read first)

The issue title carries `[GATE: ISI-2113 tuning]` and the description says *"Curve tuned against ISI-2113
results before v1 sign-off. Ship policy against defaults; final curve pinned when spike lands."* **The
spike has landed.** `docs/bmad/spikes/isi-2113-warm-pool-sandbox-latency.md` delivered the sizing model
(the base-stock formula) and `bench/pool_sizing.py` (the reference impl + self-test), and the
follow-up harness run (**ISI-2292/ISI-2294**, cluster `observable-agentsandbox`, k8s v1.35.3, gVisor
`runsc` sentry-verified) filled in the **measured `replenish_s`**:

| Runtime | measured `repl_p95` | source |
|---|---|---|
| **gVisor** (default) | **1.716 s** — *beats runc; no pool-size tax; warm-claim p50 0.110s / p95 0.135s clears NFR-PERF1 by ~15–37×* | ISI-2294 (`pool_sizing.py` __main__) |
| runc (trusted-dev only) | 3.560 s | ISI-2294 |
| Kata (opt-in) | 15.0 s — **placeholder**, handler not installed on the bench cluster; re-measure before any Kata-on-nested-virt default | spike §6 |

So this story does **both** halves the issue asks for: it **ships the policy against defaults** (the
base-stock + autoscale mechanism, runtime-agnostic behind the key) **and pins the final gVisor curve** to
the measured `R`. The one thing still empirical is **Kata `R`** (a placeholder pending a nested-virt
cluster); the policy is correct for Kata the moment that number lands — only the pinned Kata cells move.

## ⚠️ Scope reconciliation — 3.5 vs 3.4 (ISI-2204), they split the pool cleanly

| Concern | Owned by | This story adds |
|---|---|---|
| The **bind at `claiming_sandbox`** (atomic CAS, idempotent per `run_id`, key-matched) + **scale-up trigger** on a miss + **teardown-and-replace** replenish *toward a target* | **Story 3.4** (ISI-2204) | — (the mechanism; consumed) |
| **Deriving the target `N`** — base-stock `N=ceil(λR+z√(λR))`, **autoscale on `claim.pressure`**, `[min,max]` idle-cost bound, per-key `R`, batch→0 | **THIS STORY (3.5)** | the sizing policy (§A) + the pinned v1 curve (§B) |
| The **measured `R`/λ constants** + the **RuntimeClass default** (gVisor) | **ISI-2113 spike** / **ISI-2294** / **Story 4.2** | — (consumed as inputs) |
| The **`warmpool.claim.pressure` / `pool_hit` SLIs** + the **exhaustion alert** | **Epic 13** (13.7, obs §5.3) | this story *reads* `claim.pressure` as its autoscale input; it does not build the SLI pipeline or the alert |

**One-line boundary:** 3.4 answers *"given a buffer, how does a Run bind a pooled pod without double-binding,
leaking on retry, or reusing across principals — and what happens when it's empty?"* **This story answers
*"how big should the buffer be, and how does it flex with load — while bounding idle cost?"*** 3.4 =
mechanism; 3.5 = policy. The target is derived in **one** place (here); 3.4 consumes it opaquely. This keeps
the sizing formula out of two code paths.

## Story

As **the warm-pool sizing policy (the `SandboxPool` target-`N` controller half of the Epic-3 Run control
plane, §9.2)**,
I want **to compute the target ready-buffer `N` for each (RuntimeClass × AgentRuntime image) key as a
base-stock level `N = ceil(λ·R + z·√(λ·R))` — driven by the live `warmpool.claim.pressure` signal λ and the
key's own measured replenish time `R` — autoscaling `N` between `[min, max]` as pressure moves, damping
scale-down so a transient dip does not thrash the pool, and sizing batch/non-interactive Runs to `target=0`**,
so that **the warm pool holds enough Ready pods to serve the observed claim rate at the warm-hit service
level (95%) — so a Run's start latency stays claim-time (S9/NFR-PERF1) — while idle cost is *bounded* (never
more than `max` pods per key, `min` when quiet, nothing at all for batch), the pool *flexes with real load*
rather than being a fixed guess (FR-C4), and the shipped v1 gVisor curve is *pinned to the measured
ISI-2113/ISI-2294 numbers* (light=2, medium=2, heavy=3) rather than a blind default.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-C4** (pool sizing as policy — the direct requirement),
  **NFR-SCALE2** (the pool scales with load), **NFR-PERF1 / S9** (warm-claim latency threshold the buffer
  exists to protect: p50≤2s / p95≤5s), **FR-C1** (warm-pool claim-time binding — the mechanism this policy
  sizes, owned by 3.4).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§9.2 "Warm pool (FR-C1/C4, S9, R2)"** — *"Pool size is **policy-driven, not fixed** (FR-C4): a
    target-ready-count with autoscale bounds (min/max, scale-on-claim-rate). **Sizing policy (ISI-2113):**
    the target ready-buffer is a **base-stock level** `N = ceil(λ·R + z·√(λ·R))` — λ = peak claim rate, R =
    measured `warmpool.replenish.duration`, z = warm-hit service level (1.65 ≈ 95%). … Default curve (gVisor,
    95%): interactive `min=2, target=base-stock(λ_peak,R), max=10`; batch/non-interactive `target=0`
    (cold-start). Kata's ~4× R ⇒ ~2–2.6× larger target for the same SLA."* **This story implements that
    paragraph.** The **per-(RuntimeClass × image) key** sizing and the **hybrid regime** (interactive draws
    from the pool; batch cold-starts at `target=0`) are load-bearing and are ACs here.
  - **§9.3 "Hygiene — teardown-and-replace"** — the reason `R` (replenish time) is the sizing input at all:
    every claim consumes a pod that is *destroyed and replaced*, so the pool is a base-stock inventory whose
    replenishment lead time is `R`. (Mechanism owned by 3.4; consumed here as the model's `R`.)
  - **§5.2 leader election** — the sizing/replenish reconcile loop is **leader-elected** (one owner, no
    racing resizers). This story computes the target the leader drives toward; the atomic *bind* safety is
    3.4's CAS (the "leader-elect for availability, CAS for safety" split).
  - **§21 (spike-gated params) / traceability §matrix** — the warm-pool sizing row is *"policy delivered
    (base-stock formula §9.2 + `pool_sizing.py`); default curve ships; R/λ constants … from harness."* This
    story consumes the now-**measured** R (ISI-2294) and moves that row from 🟡 to shipped for gVisor.
- **ISI-2113 spike** (`docs/bmad/spikes/isi-2113-warm-pool-sandbox-latency.md`) + **`bench/pool_sizing.py`**
  — the sizing **model** and its **reference implementation** (`recommend_buffer`, self-tested). **This story
  CONSUMES `pool_sizing.recommend_buffer` — it does not re-derive the base-stock math** (ponytail rung
  "integrate, don't reinvent"; the same discipline as 6.1 consuming the memory service). The spike's §6
  falsification criteria (gVisor warm-claim p95 ≤ 5s; gVisor R "pod-like") are **met** by the ISI-2294 run.
- **ISI-2292 / ISI-2294** — the harness run that produced the measured `repl_p95` now pinned in
  `pool_sizing.py` __main__ and in this story's curve. gVisor `R = 1.716s`.
- **Depends on:**
  - **Story 3.4** (ISI-2204 — the `WarmPool` controller **mechanism** that consumes this target: bind +
    scale-up trigger + replenish-to-target). Hard dependency — this policy is meaningless without the
    controller that maintains *toward* the `N` it produces.
  - **ISI-2113 spike** + **ISI-2294** (the model, the reference impl, the measured `R`). Gate — now **cleared**.
  - **Story 1.2** (ISI-2188 — `SandboxPool` CRD: `size`/`policy`/`runtimeClass`/`template`, §5.1). This story
    populates the `policy` (min/max/service-level) and computes the effective `target`; it does **not** add
    CRD fields.
- **Blocks / is consumed by:** the **Epic-3 Go `SandboxPool` reconciler** (drives replenish toward this
  target), **Epic 13.7** (the exhaustion alert fires when observed `pool_hit=cold` rate implies the target is
  too low for actual λ — this policy is what the alert says to raise), **Epic 14.3** (the **P2 warm-pool
  ready-count** perf gate asserts the pool holds ≈ this target).

## The sizing policy (authoritative — §A)

For each **(RuntimeClass × AgentRuntime image) key**, the policy computes the target ready-count from three
inputs: the live claim-pressure signal **λ** (`warmpool.claim.pressure`, obs §5.3), the key's own measured
replenish time **R** (`warmpool.replenish.duration`), and the service-level `z` (1.65 ≈ 95%).

1. **Batch/non-interactive → `target=0` (AC-batch, §9.2 hybrid).** *First*, route by Run class: a
   batch/non-interactive key sizes to **0** — it cold-starts, paying **zero idle cost** and sidestepping
   reuse-contamination. Interactive keys proceed to the base-stock computation.

2. **Base-stock target (AC-basestock).** The interactive target ready-buffer is the base-stock level
   `N = ceil(λ·R + z·√(λ·R))` — `λ·R` = claims that land during one replenish window (cycle demand);
   `z·√(λ·R)` = **safety stock** for burstiness (Poisson σ). This is **`pool_sizing.recommend_buffer(λ, R, sl)`
   consumed directly** — the story does not re-implement it. Dropping the `z·√(λR)` safety term (mean-only
   `ceil(λR)`) under-provisions and misses the warm-hit SLA under a burst — the P1 falsification.

3. **Autoscale on the live pressure signal (AC-autoscale, FR-C4).** λ is **not a fixed constant** — it is the
   live `warmpool.claim.pressure` reading, so the target is **recomputed each reconcile** and **flexes with
   observed load**: rising λ raises `N` (scale up), falling λ lowers it (scale down). A policy that ignores λ
   and returns a constant either over-provisions idle pods at low load (cost) or misses at high load
   (latency) — the P2 falsification.

4. **Idle-cost bound: clamp to `[min, max]` (AC-bound, NFR-SCALE2).** The target is clamped: **never above
   `max`** (a pressure spike cannot spawn runaway idle pods — the idle-cost ceiling), **never below `min`**
   for interactive (`min ≥ 1`: a "warm" pool with 0 Ready pods is cold by definition, so an interactive key
   always keeps a warm floor). Dropping the `max` cap lets an absurd λ explode the pool — the P3 falsification.

5. **Per-key `R` (AC-perkey, §9.2).** Each key is sized by **its own** measured `R`. Kata's ~4× longer
   replenish forces a **~2–2.6× larger** target than gVisor for the *same* λ and SLA — the concrete idle-cost
   argument for capping Kata pools tighter and preferring cold-start for Kata bursts. Sizing every key from
   one shared `R` under-sizes Kata (misses its SLA) or over-sizes gVisor — the P4 falsification.

6. **Scale-down hysteresis (AC-nothrash).** Scale-**up** is immediate (never starve a burst); scale-**down**
   is **damped by a stabilization band** — a *transient* pressure dip does not tear down warm pods the pool
   immediately re-needs (churn = wasted boots + reintroduced cold misses, an HPA-style stabilization window).
   Belt-and-suspenders over the base-stock target; it makes the autoscale non-thrashing, not merely correct.

## The pinned v1 curve (authoritative — §B, gate deliverable)

With the **measured** gVisor `R = 1.716s` (ISI-2294) and the §9.2 gVisor defaults (`min=2, max=10`, 95%),
the shipped v1 interactive curve is:

| Load regime | λ (claims/s) | raw base-stock `ceil(λR+z√(λR))` | **shipped target** (after `min=2`/`max=10`) |
|---|---|---|:---:|
| light (3/min) | 0.05 | 1 | **2** (min floor) |
| medium (12/min) | 0.20 | 2 | **2** |
| heavy (30/min) | 0.50 | 3 | **3** |
| batch / non-interactive | any | — | **0** |

The measured gVisor `R` (1.716s) is *faster* than the spike's 4.0s placeholder, so the pool is even smaller
than the spike grid — the whole gVisor interactive curve sits comfortably in the `[2, 10]` envelope with
large headroom. **Kata** (placeholder `R=15s`): medium → 6, heavy → raw 13 **clamped to `max=10`** — the
clamp visibly *bites* for Kata, which is the intended "cap Kata tighter, prefer cold-start for bursts"
behavior. These constants are **pinned by the falsification** (`test_pinned_curve`) so a future R/λ or
min/max edit cannot silently move the shipped defaults — re-pinning is a deliberate act.

## Acceptance Criteria

**AC1 — the interactive target is the base-stock level `N = ceil(λR + z√(λR))`, safety stock included.**
Given an interactive key with live claim rate λ and measured replenish time R, When the policy computes the
target, Then it returns **`pool_sizing.recommend_buffer(λ, R, 0.95)`** — the base-stock level whose
`z·√(λR)` term is **safety stock** for burstiness — not the bare cycle demand `ceil(λR)`. A design that sizes
to the mean `λR` alone **under-provisions**: it misses the 95% warm-hit SLA the moment a claim burst lands
while a replenish is in flight. The base-stock math is **consumed from the ISI-2113 reference impl**, not
re-derived.

**AC2 — the target AUTOSCALES on the live `warmpool.claim.pressure` signal (it is not a fixed constant).**
Given a key whose observed claim rate λ moves over time, When the policy reconciles, Then the target is
**recomputed from the live λ each reconcile** and is **monotonic non-decreasing in λ**: rising pressure
raises the target (scale up), falling pressure lowers it (scale down). A fixed constant target (ignoring λ)
**over-provisions idle pods at low load** (idle cost) or **misses at high load** (cold hits) — it is a
correctness failure against FR-C4, not a conservative default.

**AC3 — idle cost is BOUNDED: the target is clamped to `[min, max]`; interactive floors at `min≥1`.**
Given any observed λ — including an absurd pressure spike — When the policy computes the target, Then it is
**never above `max`** (the idle-cost ceiling: a spike cannot spawn runaway idle pods) and **never below `min`**
for an interactive key (`min ≥ 1`: an interactive pool always keeps a warm floor — 0 Ready is cold). Dropping
the `max` cap lets the base-stock grow unboundedly with λ — an idle-cost blowout, the NFR-SCALE2 failure.

**AC4 — batch/non-interactive keys size to `target=0` (zero idle cost, §9.2 hybrid).**
Given a batch/non-interactive Run class, When the policy computes the target, Then it returns **0**
regardless of λ — batch cold-starts (paying zero idle cost and sidestepping reuse-contamination), only
interactive demand pays for a warm buffer. This is the §9.2 hybrid regime; it is the reason idle cost is
bounded *by workload class*, not just by the `max` cap.

**AC5 — each (RuntimeClass × image) key is sized by ITS OWN measured replenish time R.**
Given two keys with different R — gVisor (R=1.716s) and Kata (R=15s) — at the **same** λ, When the policy
sizes them, Then Kata's target is **larger** (its ~4× R forces a ~2–2.6×+ larger base-stock for the same
SLA — §9.2). Sizing every key from one shared R **under-sizes Kata** (misses its warm-hit SLA) **or
over-sizes gVisor** (idle cost). The pool is one-dimensional, but each dimension is sized on its own physics.

**AC6 — scale-down is damped so a transient pressure dip does not thrash the pool.**
Given a key at a steady target, When the observed pressure dips for a **single** reconcile tick and then
recovers, Then the policy **does not tear the pool down** on the transient (a stabilization band absorbs it);
scale-up remains immediate. A naive re-evaluate-raw-every-tick **flaps** the pool — tearing down warm pods it
immediately re-needs, wasting boots and reintroducing cold misses on the very next claim.

**AC7 — the shipped v1 gVisor curve is pinned to the measured ISI-2294 numbers.**
Given the measured gVisor `R = 1.716s` and the §9.2 defaults (`min=2, max=10`, 95%), When the interactive
curve is materialized, Then it is **{light: 2, medium: 2, heavy: 3}** and **batch: 0** — the shipped v1
defaults, locked by the falsification as a regression fence so an R/λ or min/max change cannot silently move
them. (Kata cells remain a placeholder pending its measured R; the policy is correct the moment that lands.)

## Runnable check (the falsification)

`docs/bmad/spikes/bench/warmpool-sizing-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same shape as the 3.4 / 3.2 / 2.2 checks), not a happy-path demo. It **consumes
`pool_sizing.recommend_buffer`** (the ISI-2113 reference impl — demonstrating "integrate, don't reinvent")
and mutation-checks the headline policy invariants against naive twins:

- **(P1) safety stock — base-stock, not mean-only (AC1).** The target carries the `z·√(λR)` burst buffer:
  at gVisor heavy load the base-stock is **3** while the mean-only `ceil(λR)` is **1**. *Mutation-proven:*
  swapping `recommend_buffer(...)` for `ceil(λ·R)` in `SizingPolicy.base_stock` turns the check **RED** — the
  pool under-provisions.
- **(P2) autoscale tracks the live pressure signal (AC2).** Sweeping λ low→high, the target is monotonic
  non-decreasing **and genuinely moves** (a constant would be flat). *Mutation-proven:* ignoring
  `observed_lambda` in `SizingPolicy.target` (size from a constant) turns the check **RED**.
- **(P3) idle cost bounded — the `max` cap + interactive floor (AC3).** An absurd λ clamps to `max=10`
  (raw base-stock would exceed it) and a trickle λ floors at `min=2`. *Mutation-proven:* dropping the
  `min(base, self.max_ready)` cap turns the check **RED** — the target runs past max. Plus **(P3b)** batch
  sizes to 0 at every λ (AC4).
- **(P4) per-key R (AC5).** gVisor (R=1.716s) → 2 vs Kata (R=15s) → 6 at the same λ (≥2× — the §9.2
  multiplier). *Mutation-proven:* sizing every key from one shared R turns the check **RED**.
- **(P5) scale-down hysteresis, no thrash (AC6).** A `[heavy, heavy, heavy, dip, heavy, heavy]` pressure
  sequence holds the target flat under the stabilization band, while the naive raw-every-tick twin flaps.
- **(PIN) the shipped v1 gVisor curve (AC7).** Asserts interactive `{light:2, medium:2, heavy:3}` and
  `batch:0` at the measured R=1.716s — a regression fence on the defaults.

Exits non-zero if the target drops its safety stock, stops tracking pressure, blows past the idle-cost cap
or floor, sizes batch above 0, ignores per-key R, thrashes on a transient dip, or drifts the pinned curve.
**The headline invariants are mutation-checked:** P1 (mean-only), P2 (frozen λ), P3 (no max cap), P4 (shared
R) each turn the check **RED** — verified by running the mutations as real source edits.

## Out of scope (owned elsewhere)

- **The `WarmPool` controller mechanism** — the claim-time bind (atomic CAS, idempotent per `run_id`,
  key-matched), the scale-up trigger on a miss, and teardown-and-replace *toward* the target (**Story 3.4 /
  ISI-2204** — this story only *derives* the target it maintains toward). **The measured R/λ constants + the
  RuntimeClass default** (**ISI-2113 spike** / **ISI-2294** / **Story 4.2** — consumed as inputs; the Kata R
  remains a placeholder pending a nested-virt cluster measurement). **The `warmpool.claim.pressure` /
  `pool_hit` / `warmpool.replenish.duration` SLI pipeline** and the **warm-pool-exhaustion alert** (**Epic
  13.7**, obs §5.3 — this story *reads* `claim.pressure` as its autoscale input; it does not build the SLI or
  the alert). **The P2 warm-pool ready-count perf gate** (**Epic 14.3**). **Pod assembly / RuntimeClass
  isolation** (§5.3.4 / §9.1 / Story 4.2). This story ships **the sizing policy (base-stock target, autoscale
  on live pressure, `[min,max]` idle-cost bound, per-key R, batch→0, scale-down hysteresis), the pinned v1
  gVisor curve against the measured ISI-2294 numbers, and the differential falsification** — the FR-C4
  pool-sizing-as-policy guarantee itself.
