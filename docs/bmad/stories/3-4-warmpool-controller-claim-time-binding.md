# Story 3.4: WarmPool controller — claim-time sandbox binding

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE WARM-PATH START-LATENCY GUARANTEE (arch §9.2 "Warm pool", FR-C1, S9/NFR-PERF1).**
> Story 3.1 built the Run reconcile machine; its **`claiming_sandbox`** step "requests a warm sandbox
> from `SandboxPool`" (§5.3.4) — but *what answers that request* is this controller. This story is the
> `SandboxPool`/`WarmPool` side of that seam: it keeps N pre-warmed pods `Ready` per **(RuntimeClass ×
> AgentRuntime image)** key so that when a Run reaches `ClaimingSandbox` the sandbox is a **grab of an
> already-`Ready` pod (claim-time), not a cold boot** — and if the pool is empty it **triggers scale-up
> and still serves the Run**, never wedges it. The load-bearing invariants are **three**, and each is a
> *correctness* property, not a tuning knob: **(1) the pooled pod is grabbed ATOMICALLY** — one warm pod
> is never handed to two Runs (a shared sandbox = cross-Run contamination, §9.3); **(2) the bind is
> IDEMPOTENT per `run_id`** — a retry lap re-entering `claiming_sandbox` reattaches to the pod it already
> bound, it does not leak a second warm pod (§6.4 re-entrancy, the ISI-2346-F1 class); **(3) a used pod is
> NEVER reused** — on Run completion/death it is **destroyed and a fresh pod replenishes** (§9.3
> teardown-and-replace, "a sandbox is never reused across Runs or principals"). A design that skips any of
> the three is a correctness failure, not a bug ticket.

## ⚠️ Section-number reconciliation (read first)

The originating issue (ISI-2204) cites **"Arch §5.4"** and the epic header lists **"§5.4 (warm pool)"** —
but in the current architecture revision **§5.4 is *Source-Control Sync*** and the **warm pool lives at
§9.2** (with §9.3 hygiene, §5.3.4 pod assembly, §5.2/§5.3 the Claiming step). This is section-renumbering
drift, not a scope change. **This story is authored against the live sections: §9.2 (warm pool sizing +
key), §9.3 (teardown-and-replace hygiene), §5.3.4 / §5.3 "Claiming" (the bind point), §6.4 (re-entrancy
spine).** The FR is unchanged: **FR-C1** (warm-pool claim-time binding).

Also reconcile the phase wording: the issue says *"When a Run reaches `ClaimingSandbox`."* Per r28 (the
pinned CEL `status.phase` enum) and Story 3.1's decision, **`ClaimingSandbox` is a durable
`reconcile_step` *within* the `Claiming` phase (§6.4), not a `status.phase` value.** The bind this story
performs happens at the `claiming_sandbox` reconcile step; it writes **no new phase**.

## ⚠️ Scope reconciliation — 3.4 vs 3.5 (ISI-2205), they split the pool cleanly

| Concern | Owned by | This story adds |
|---|---|---|
| The **bind at `claiming_sandbox`**: grab a pooled pod (claim-time), atomically, idempotently, key-matched | **THIS STORY (3.4)** | the controller bind path (§A) |
| **Scale-up trigger** on a miss + **teardown-and-replace** replenish toward a target N | **THIS STORY (3.4)** | the miss/replenish mechanism (§B) |
| **Deriving the target N** — the base-stock level `N=ceil(λR+z·√(λR))` + **autoscale on claim pressure** | **Story 3.5** (ISI-2205, GATE ISI-2113) | — (consumed as a static policy input; NOT re-derived) |
| The **RuntimeClass default** (gVisor) + the empirical R/λ constants | **ISI-2113 spike** + **Story 4.2** | — (consumed; this story is runtime-agnostic behind the key) |
| The **warm-pool exhaustion alert** + the `pool_hit`/`claim.pressure` SLIs | **Epic 13** (13.7) | this story *emits* `pool_hit=warm\|cold`; it does not build the alert |

**⚠️ Scope pin (the target N is derived in ONE place — 3.5).** This story's controller maintains the pool
*toward* a target `N` and **triggers scale-up when the pool is empty** — but the **value of `N`** (base-stock
math, autoscale on `warmpool.claim.pressure`) is **Story 3.5's** single responsibility. 3.4 treats `N` as an
opaque policy input (a static default is fine for 3.4's acceptance). This keeps the sizing formula out of two
code paths: 3.4 = the *mechanism* (bind + scale-up trigger + replenish-to-target); 3.5 = the *policy* (what
the target is). The falsification (§D) asserts maintain-toward-target + scale-up-on-empty, **not** the sizing
curve (that is `pool_sizing.py` / 3.5's check).

**One-line boundary:** 3.5 answers *"how big should the warm buffer be, and how does it flex with load?"*
This story answers *"given a buffer, how does a Run at `claiming_sandbox` bind a pooled pod at claim-time —
without ever double-binding, leaking on retry, or reusing a pod across principals — and what happens when the
buffer is empty?"*

## Story

As **the `WarmPool`/`SandboxPool` controller (the claim-time-binding half of the Epic-3 Run control plane,
§9.2)**,
I want **to keep N pre-warmed sandbox pods `Ready` per (RuntimeClass × AgentRuntime image) key, and when a
Run reaches its `claiming_sandbox` step bind one of those pooled pods to the Run *atomically*,
*idempotently per `run_id`*, and *only if its key matches* — or, if the pool for that key is empty, trigger
scale-up and serve the Run from a freshly-created pod — then, on the Run's completion or death, destroy the
used pod and replenish a fresh one**,
so that **the warm-path start latency a user feels is claim-time (a grab of an already-`Ready` pod, S9 /
NFR-PERF1 / FR-C1), not a cold boot; one warm pod is never shared by two Runs (no cross-Run contamination,
§9.3); a retry lap never leaks a second warm pod (§6.4); a sandbox is never reused across Runs or principals
(§9.3 teardown-and-replace); and an empty pool degrades to a cold-start that still runs, never a wedged
Run.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-C1** (warm-pool claim-time binding, the direct requirement),
  **FR-C4** (pool sizing as policy — 3.5), **FR-C6 / NFR-SEC5** (sandbox hygiene, no cross-principal
  reuse), **NFR-PERF1 / S9** (warm-claim latency threshold: p50≤2s / p95≤5s), **NFR-SCALE2** (pool scales).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§9.2 "Warm pool (FR-C1/C4, S9, R2)"** — *"`SandboxPool` reconciler keeps **N pre-booted,
    image-pre-pulled** sandbox pods `Ready` per **(RuntimeClass × `AgentRuntime` image)** key so a Run claim
    is grab-time. Warm pods carry only the agent base; skill-specific toolchains attach per-Run via
    node-cached init packs (§5.3.2) — so the pool stays one-dimensional."* **This story implements that
    sentence's controller.** The **one-dimensional key** is load-bearing: the pool is keyed on *(RuntimeClass
    × image)*, not on skill set (toolchains are init-staged at claim time), so a Run never needs a warm pod
    "per skill combination" — but it **does** need one matching its runtime class + base image (§T6 key
    discipline). Hybrid regime: **interactive Runs draw from the pool; batch/non-interactive Runs may
    cold-start** (`target=0`, zero idle cost) — routed by the Run class field.
  - **§9.3 "Hygiene — teardown-and-replace"** — *"After a Run completes, its sandbox pod is **destroyed** and
    the pool replenishes a **fresh** pod from the template … **A sandbox is never reused across Runs or
    principals.**"* **This is AC-hygiene's teeth.** "Warm" is a property of the **pool** (async replenish),
    **not** of an individual reused pod. The controller **must** teardown-and-replace, never return a used pod
    to the `Ready` set.
  - **§5.3.4 / §5.3 "Claiming"** — *"Run reconciler requests a warm sandbox from `SandboxPool` (§9) keyed by
    (RuntimeClass × `AgentRuntime` image), then assembles the pod … **Claim latency, not cold boot**
    (NFR-PERF1/S9)."* This story is the `SandboxPool` responder to that request; the **assembly** (toolchain
    init-staging + sidecars) rides on top of the bound pod and is §5.3.4's concern, not re-specified here.
  - **§6.4 "re-entrancy spine"** — *"deterministic `a2a_task_id = run_id`, **run_id-keyed sandbox bind**,
    content-addressed artifact upsert, conditional step-advance."* **The `run_id`-keyed sandbox bind is this
    story's AC-idempotent.** Story 3.1 built the spine and falsified it (its check E, run_id-keyed
    claiming_sandbox bind); this story provides the bind that spine calls and stacks the *pool-leak*
    false-positive teeth on it. A retry lap re-running `claiming_sandbox` **reattaches** to the pod already
    bound to that `run_id` — it must not grab a second.
  - **§9.1 RuntimeClass** — the pool is **keyed** by RuntimeClass; the *default* (gVisor) and *isolation*
    decision are §9.1 / Story 4.2 / ISI-2113. This story is runtime-agnostic behind the key: it binds a pod
    of the **requested** key and never a mismatched one (binding a `runc` pod to a Run that requires gVisor
    would be the wrong isolation boundary — §T6).
  - **§5.2 leader election** — the pool's **replenish/scale reconcile loop** is **leader-elected** (one owner,
    no racing replenishers). But **Run-reconcile parallelism means concurrent *binds*** can still race for the
    same warm pod, so **leader-election = availability of the replenisher; the atomic CAS bind = safety** —
    the same "leader-elect for availability, fencing/CAS for safety" split as Stories 2.4 / 3.1.
- **ISI-2113 spike** (`docs/bmad/spikes/isi-2113-warm-pool-sandbox-latency.md`) — ratifies **gVisor default**
  and gives the **sizing model** (`bench/pool_sizing.py`) 3.5 consumes. Its load-bearing framing for *this*
  story: **"warm-claim latency is NOT the runtime-selection axis — a warm pod is already `Ready`, so the
  claim is a grab + context-inject, near-instant regardless of runtime."** That is exactly the property AC1
  guarantees: the *pool having a Ready pod* is what makes the claim grab-time; runtime choice moves
  cold-start/replenish (pool size, §9.2), which is 3.5's cost, not the warm-claim latency this story owns.
- **Depends on:**
  - **Story 3.1** (ISI-2201 — the reconcile machine whose `claiming_sandbox` step invokes this bind, and the
    §6.4 re-entrancy spine — run_id-keyed bind — this story's idempotency plugs into). Hard dependency.
  - **Story 1.2** (ISI-2188 — the `Run` / `SandboxPool` CRD shapes: `SandboxPool.runtimeClass`, `size`/`policy`,
    `template`, §5.1; `Run` class/runtime key). This story does **not** add CRD fields.
  - **Story 4.2** (ISI-2208 — RuntimeClass selection contract §9.1) + **ISI-2113** (default + sizing). Consumed
    as the key/runtime inputs; not built here.
- **Blocks / is consumed by:** **Story 3.5** (ISI-2205 — sizing-as-policy sits *on top of* this controller's
  maintain-toward-target + scale-up mechanism), the **Epic-3/4/5 Go Run reconciler** (calls this bind at
  `claiming_sandbox`), **Epic 13.7** (the warm-pool-exhaustion `pool_hit=cold` alert observes this story's
  `pool_hit` emission), **Epic 14.3** (the **P2 warm-pool ready-count** perf gate).

## The bind at `claiming_sandbox` (authoritative — §A)

When a Run reaches its `claiming_sandbox` reconcile step (§6.4), the controller binds a sandbox in this
exact order:

1. **Idempotent reattach (§6.4, run_id-keyed — AC-idempotent).** *First*, look up whether a pod is **already
   bound to this `run_id`** (a prior lap bound it, then the reconciler crashed/requeued). If so, **reattach to
   that pod and return** — no new grab, **zero** inventory change. This is the §6.4 discipline: the bind is a
   deterministic function of `run_id`, so re-running the step is a no-op, not a second provision. Skipping this
   is the ISI-2346-F1 class of bug (the falsification never exercises the re-entry → a naive "grab fresh every
   lap" leaks a warm pod per retry).

2. **Warm grab (claim-time — AC-atomic + AC-claim-time + AC-key).** Otherwise, among the pods that are `Ready`
   **and match the Run's (RuntimeClass × image) key**, grab one **atomically**: a **K8s-native
   optimistic-concurrency compare-and-swap** on the pod object (`resourceVersion` — the same "native
   concurrency, not invented locking" discipline as the §6.2 conditional `UPDATE`, on the pod instead of the
   claim row). The winner flips the pod `Ready → Bound(run_id)`; a racer whose `resourceVersion` is stale gets
   a **409 Conflict** and **retries against another `Ready` pod** (or falls to step 3). **This is a grab of an
   already-`Ready` pod — no pod is created on the warm path**, so the start latency is claim-time
   (`pool_hit=warm`, WARM_GRAB « COLD_BOOT). After a successful grab, the controller **triggers replenish
   toward the target** (§B) — asynchronously, off the claim path.

3. **Miss path — scale-up, then serve (AC-scaleup, never wedge).** If **no `Ready` pod matches the key** the
   pool is empty for that key: **trigger scale-up** (create a pod / grow toward the target). An **interactive**
   Run then binds the freshly-`Ready` pod (`pool_hit=cold`, the miss penalty the pool exists to avoid); a
   **batch/non-interactive** Run cold-starts directly (`target=0`, §9.2 hybrid). Either way the Run is
   **served** — the empty pool degrades to a cold-start, it **never wedges the Run**. The scale-up trigger is
   what feeds the §9.2 `claim.pressure` autoscale signal (3.5) and the 13.7 exhaustion alert.

## The pool lifecycle — teardown-and-replace (authoritative — §B, drives §9.3)

- **Maintain-toward-target.** The (leader-elected) replenish loop keeps `Ready`-count == target `N` per key,
  creating fresh pods from the `SandboxPool.template`. **The value of `N` is Story 3.5's** (base-stock +
  pressure autoscale); this story maintains *toward* whatever `N` policy provides and defaults to a static
  target when 3.5 is not yet wired.
- **Teardown-and-replace on release (AC-hygiene, §9.3).** When a Run **completes, is cancelled, or dies**
  (the Story 3.2 death edge / 3.3 kill both end here), its bound pod is **destroyed** — `Bound → Torn`, never
  back to `Ready` — and the replenish loop boots a **fresh** pod from the template. **A used pod is never
  returned to the pool and never bound by a second Run/principal.** This is the security property behind
  NFR-SEC5: proving an in-place scrub left zero residue (scratch files, in-memory secrets, poisoned build
  cache) is a losing game (ADR-006); a destroyed pod is provably clean, and warm-pool economics survive
  because "warm" is a property of the **pool's async replenish**, not of a reused pod.
- **One-dimensional key.** Pods are keyed **(RuntimeClass × AgentRuntime image)** only — **not** per skill
  set (§9.2). Skill toolchains attach per-Run via node-cached init packs (§5.3.2) at assembly (§5.3.4), so the
  pool stays small (one dimension: the agent base). An `ImageUpdater` bump (§5.3.5) drains and re-warms the
  affected key — that drain/re-warm rides the same teardown-and-replace mechanism (not re-specified here).

## Acceptance Criteria

**AC1 — a Run at `claiming_sandbox` binds a POOLED pod at claim-time (a grab, not a cold boot) whenever a
matching `Ready` pod exists.**
Given a `Run` reaching its `claiming_sandbox` step (§6.4) and a warm pool holding at least one `Ready` pod
whose **(RuntimeClass × AgentRuntime image)** key matches the Run, When the controller binds, Then it
**grabs the already-`Ready` pod** (`pool_hit=warm`) — it does **not** create a pod on the claim path — so the
warm-path start latency is **claim-time** (the §5.3.4 grab + context-inject, meeting S9/NFR-PERF1 p50≤2s /
p95≤5s independent of RuntimeClass, per ISI-2113). The bound pod leaves the `Ready` set; the controller
triggers replenish toward the target **off the claim path** (§B).

**AC2 — the pooled-pod grab is ATOMIC: one warm pod is never handed to two Runs.**
Given two Runs reaching `claiming_sandbox` concurrently and a pool with a single matching `Ready` pod, When
both attempt to bind it, Then the grab is a **K8s optimistic-concurrency CAS on the pod (`resourceVersion`)**:
**exactly one** Run wins (`Ready → Bound(run_id)`), the other gets a **409 Conflict** and retries against
another `Ready` pod or triggers scale-up (AC5). **No warm pod is ever bound to two Runs** — a shared sandbox
would be a cross-Run contamination (§9.3). A design that "picks the first `Ready` pod" without an atomic guard
double-binds and is a correctness failure.

**AC3 — the bind is IDEMPOTENT per `run_id`: a retry lap reattaches, it does not leak a second pod (§6.4).**
Given a Run whose `claiming_sandbox` step already bound a pod, When the step **re-runs** (reconciler
crash/requeue, the §6.4 re-entrancy case), Then the controller **reattaches to the pod already bound to that
`run_id`** and returns — **no new grab, no inventory change, exactly one `Bound` pod for the Run**. A design
that grabs a fresh `Ready` pod on every lap **leaks** a warm pod per retry (and orphans the first) — the
ISI-2346-F1 re-entrancy class. The bind is a deterministic function of `run_id`, matching the §6.4 spine 3.1
falsified.

**AC4 — a used pod is DESTROYED and replaced with a fresh one; it is NEVER reused across Runs/principals
(§9.3).**
Given a Run that completes, is cancelled, or dies, When its sandbox is released, Then the bound pod is
**torn down (destroyed), never returned to the `Ready` pool**, and the replenish loop boots a **fresh** pod
from the `SandboxPool.template`. **No physical pod is ever bound by a second Run or a second principal** —
teardown-and-replace (ADR-006), the NFR-SEC5 no-residue guarantee. "Warm" is a property of the pool's async
replenish, not of a reused pod.

**AC5 — an empty pool TRIGGERS SCALE-UP and still serves the Run; it never wedges it.**
Given a Run at `claiming_sandbox` and **no `Ready` pod matching its key**, When the controller binds, Then it
**triggers scale-up** (grow toward the target / create a pod — feeding the §9.2 `claim.pressure` signal and
the 13.7 exhaustion alert) and **serves the Run**: an **interactive** Run binds the freshly-`Ready` pod
(`pool_hit=cold`, the miss penalty); a **batch/non-interactive** Run cold-starts directly (`target=0`,
§9.2 hybrid). The empty pool degrades to a **cold-start that still runs** — the Run is **never left wedged**
waiting for a pod that is never requested.

**AC6 — the bind respects the (RuntimeClass × image) key; a wrong-key pod is never bound.**
Given a Run requiring key `(gVisor × imageA)` and a pool holding only `(Kata × imageA)` or `(gVisor × imageB)`
`Ready` pods, When the controller binds, Then it **binds only a pod whose key matches** — it treats the
mismatched warm pods as ineligible (they are untouched) and falls to the scale-up/cold path (AC5) for the
correct key. Binding a wrong-**RuntimeClass** pod would place the Run behind the **wrong isolation boundary**
(§9.1 — a correctness/security failure); binding a wrong-**image** pod would give it the wrong agent base. The
pool is one-dimensional but the dimension is **exact**.

**AC7 — the controller emits truthful `pool_hit=warm|cold` accounting.**
Given each bind, When it completes, Then the controller records **`pool_hit=warm`** iff it grabbed an
existing `Ready` pod and **`pool_hit=cold`** iff it scaled-up/booted on the claim path — matching the §9.2 /
obs §5.3 `ksquad.sandbox.claim.duration{runtime_class, pool_hit}` SLI so the **13.7 warm-pool-exhaustion
alert** and the **14.3 P2 ready-count** gate observe reality, not a misreport.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/warmpool-claim-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same shape as the 2.2 / 2.4 / 3.1 / 3.2 checks), not a happy-path demo. It contrasts NAIVE
controllers against the §9.2/§9.3/§6.4 controller and **mutation-checks the three headline invariants**:

- **(M1) atomic bind — the `resourceVersion` CAS (AC2).** Two Runs race for the single warm pod: the correct
  CAS lets **exactly one** win (the other's stale `resourceVersion` → 409). A differential twin shows the
  **naive pick-a-`Ready`-pod (no atomicity) hands the SAME physical pod to both Runs** (a shared sandbox). The
  CAS is deliberately the **sole gate** (no redundant live `state==Ready` re-check that would mask a missing
  guard). *Mutation-proven:* deleting the `if p.rv != expected_rv` CAS guard in `cas_bind` turns the check
  **RED** — both binders succeed, double-binding one pod.
- **(M2) idempotent `run_id` rebind (AC3, §6.4).** A retry lap for the same `run_id` **reattaches** — the
  check asserts the pool inventory is **unchanged** and there is **exactly one `Bound` pod** for the Run. A
  differential twin shows the **naive grab-fresh-every-lap leaks a second pod** (two `Bound` pods for one
  Run). *Mutation-proven:* deleting the `run_id` reattach lookup in `bind_claim_time` turns the check **RED**.
- **(M3) never-reuse — teardown-and-replace (AC4, §9.3).** Two sequential Runs by **different principals**
  bind **distinct physical pods** (the first is torn down, a fresh one replenishes) — no physical pod ever
  ran two principals. A differential twin shows the **naive return-to-pool reuses one pod across two
  principals** (cross-principal contamination). *Mutation-proven:* making `release()` set `state="Ready"`
  instead of `"Torn"` turns the check **RED**.
- **(T2) claim-time on the warm path (AC1/FR-C1/S9).** A warm hit against a pool held **above** target
  asserts **zero pod creations on the claim path** and latency == the grab cost (WARM_GRAB « COLD_BOOT) — a
  cold-boot-on-warm-hit fails loud. (The scenario seeds above target so the legitimate async replenish does
  not confound the claim-path boot count.)
- **(T5) empty-pool scale-up, no wedge (AC5).** An empty pool asserts the bind **triggers a pod create** AND
  the Run is **served** (`pool_hit=cold`, non-null pod) — never wedged.
- **(T6) key discipline (AC6).** A Run needing `(gVisor × v1)` against a pool of only `(Kata × v1)` and
  `(gVisor × v2)` pods asserts it binds a **matching-key** pod (via cold path) and **never disturbs the
  mismatched warm pods** — no wrong-isolation-boundary bind.
- **(T7) truthful `pool_hit` accounting (AC7).** Asserts `warm` iff grabbed-from-pool and `cold` iff
  scaled-up, so the §9.2 SLI / 13.7 alert observe reality.

Exits non-zero if a warm pod is double-bound, a retry lap leaks or double-binds a pod, a used pod is reused
across principals, a warm hit cold-boots, an empty pool wedges the Run, a wrong-key pod is bound, or the
`pool_hit` accounting lies. **The three headline invariants are mutation-checked:** deleting the CAS guard
(M1), the `run_id` reattach (M2), or the teardown (M3) each turns the check **RED**.

## Out of scope (owned elsewhere)

- **The target-N SIZING policy** — base-stock `N=ceil(λR+z·√(λR))` + autoscale on `claim.pressure` (**Story
  3.5 / ISI-2205**, gate ISI-2113; `pool_sizing.py` is its reference; this story consumes `N` as a static
  input and only maintains-toward-target + scale-up-on-empty). **The RuntimeClass default + isolation
  decision** (§9.1 / **Story 4.2** / **ISI-2113** — this story is key-agnostic). **Pod assembly** — toolchain
  init-staging + capability-gated sidecars on top of the bound pod (§5.3.4, **Story 3.x**). **The Run reconcile
  machine + `claiming_sandbox` step orchestration** (**Story 3.1** — this story is the `SandboxPool` responder
  it calls). **The death/kill edges that trigger release** (**Stories 3.2 / 3.3** — they end in this story's
  teardown, not re-specified). **`ImageUpdater` drain/re-warm** (§5.3.5). **The warm-pool-exhaustion alert +
  `pool_hit`/`claim.pressure` SLIs** (**Epic 13.7**, obs §5.3 — this story *emits* `pool_hit`; it does not
  build the alert). **The P2 ready-count perf gate** (**Epic 14.3**). This story ships **the claim-time bind
  (atomic, idempotent, key-matched), the empty-pool scale-up-and-serve, the teardown-and-replace lifecycle,
  the `pool_hit` accounting, and the differential falsification** — the FR-C1 warm-path start-latency
  guarantee itself.
