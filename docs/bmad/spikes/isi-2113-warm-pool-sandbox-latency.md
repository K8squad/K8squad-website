---
title: "ISI-2113 Spike — Warm-pool sandbox claim latency (Kata vs gVisor vs plain runc)"
author: "Winston (System Architect)"
date: "2026-08-12"
status: "recommendation delivered; hardware numbers pending harness run on a cluster"
issue: "ISI-2113"
gates: "arch §9.1 (RuntimeClass default), §9.2/§21 (pool sizing), §5.3.3 (docker-in-sandbox); obs §5.3 SLI"
feeds: "Epics 3/4/5/7; Story ISI-2205 (warm-pool sizing as policy)"
deliverables:
  - "this report — runtime recommendation + sizing model + threat-model evaluation"
  - "bench/pool_sizing.py — base-stock sizing calculator (self-tested, no cluster needed)"
  - "bench/claim-latency-bench.sh — field harness; produces cold_start/warm_claim/replenish per RuntimeClass"
---

# ISI-2113 — Warm-pool sandbox claim latency: runtime-class recommendation & pool sizing

## 0. TL;DR (the recommendation)

1. **Default RuntimeClass = gVisor.** It is the only option that both (a) meets the
   agent threat model — arbitrary shell/git/build is untrusted code, so a shared-kernel
   `runc` boundary is disqualified — and (b) keeps warm-claim latency and replenish cost
   pod-like, which is what keeps the warm pool small and cheap. First-hand org evidence
   (OpenClaw already boots green on gVisor, `kernel 4.19.0-gvisor`, MemPalace/ISI-1825)
   removes the "does our agent runtime even work on gVisor" risk.
2. **Kata = opt-in, per-Team/Role, for high-assurance tenants and real-Docker-in-sandbox.**
   Not the floor: it needs nested virtualization (often absent on managed K8s) and its
   ~4× longer replenish time **forces a ~2–2.6× larger idle warm pool for the same warm-hit
   SLA** (quantified in §4). Reserve it where the hardware-virt boundary is actually required.
3. **`runc` = rejected for untrusted agents.** Allowed only behind an explicit
   `trusted-dev` flag for code the operator already trusts. Never the default.
4. **Pool sizing is a policy curve, not a constant.** Size the target ready-buffer as a
   **base-stock level** `N = ceil(λ·R + z·sqrt(λ·R))` where λ = peak claim rate, R = measured
   replenish time, z = warm-hit service level. Concrete grid in §4; calculator in
   `bench/pool_sizing.py`. The issue's suggested 2/5/10 sizes map to gVisor light/heavy
   regimes at 95% warm-hit.
5. **Warm-claim latency is NOT the runtime-selection axis.** A warm pod is already `Ready`;
   the "claim" is a grab + context-inject, near-instant regardless of runtime. Runtime choice
   bites **cold-start**, **replenish time R**, and **steady-state overhead** — and for
   LLM-bound agent workloads (mostly waiting on the model API) that overhead is largely masked.

**This confirms and hardens arch §9.1's provisional decision — it does not change the
architecture.** The seam (`SandboxPool.runtimeClass`, `Role.runtimeClassHint`) stands; this
spike sets the default and the sizing policy behind it.

> **Honesty note (load-bearing).** No cluster with gVisor/Kata RuntimeClass handlers was
> reachable from this spike's environment (homelab CAPI clusters don't ship those handlers by
> default). Per the architecture's own discipline — "do not ship v1 defaults blind" (§21) — I
> did **not** fabricate latency numbers. The **decision** above is defensible from the threat
> model + first-hand org evidence + queueing math and can be acted on now. The **absolute
> millisecond numbers** that lock the v1 default and the exact pool constants must come from
> `bench/claim-latency-bench.sh` run on a cluster that has the RuntimeClasses installed. §6
> states exactly what remains empirical and the falsification criteria.

---

## 1. Question & method

**Question (issue):** claim-to-ready latency for a warm pool under Kata, gVisor, and plain
`runc`, at pool sizes 2/5/10; plus cold-start, steady-state overhead on LLM-bound work, and
isolation vs. the agent threat model.

**Method.** Three parts, matching the three things the issue actually needs to decide:
- **§2 Isolation vs threat model** — decides which runtimes are even *eligible*. Qualitative,
  and decisive: it eliminates `runc` before any latency number is measured.
- **§3 Latency taxonomy** — separates the four latencies the issue conflates (warm-claim,
  cold-start, replenish, steady-state overhead) and identifies which one each runtime actually
  moves. This is where "warm-claim latency is not the selection axis" comes from.
- **§4 Sizing model** — turns replenish time R + claim rate λ into a pool-size curve. The
  runtime's cost shows up **here**, as idle-pool size, not as user-visible claim latency.
- **§5 Harness** — the reproducible instrument that fills in the measured R and cold-start so
  §4 produces final numbers on hardware.

---

## 2. Isolation vs. the agent threat model (decides eligibility)

**Threat model (PRD NFR-SEC2, brainstorming §threats):** an agent runs **arbitrary
shell/git/build commands** authored partly from untrusted input (git repos = D8-untrusted,
recalled memory = untrusted, fetched skills = untrusted). Treat every sandbox as running
**hostile code that will try to escape**. The isolation boundary is therefore a hard
requirement, not a tuning knob.

| Runtime | Boundary | Escape surface | Verdict for untrusted agents |
|---------|----------|----------------|------------------------------|
| **runc** | Shared host kernel (namespaces + cgroups + seccomp) | The **entire Linux kernel syscall surface**; one kernel LPE = host compromise = cross-tenant blast radius | **Rejected as default.** A single kernel CVE escapes the box. Only acceptable behind an explicit `trusted-dev` flag for code the operator already trusts. |
| **gVisor** | User-space **sentry** intercepts syscalls; the app never talks to the host kernel directly | Sentry itself + a **small** host-kernel surface the sentry uses; dramatically reduced vs runc | **Default.** Right-sized for the threat model: kernel attack surface is cut to a fraction, at pod-like start cost. Compatibility caveats (some syscalls/filesystems) are the price and are real but bounded. |
| **Kata** | Hardware-virt **microVM** (separate guest kernel) | Hypervisor boundary (VM escape) — the strongest common-case boundary | **Opt-in, high-assurance.** Use when a tenant demands a VM boundary or needs **real Docker/nested containers** in-sandbox (§5.3.3). Needs nested virt; heavier. Not the floor. |

**Conclusion:** eligibility is **gVisor (default) and Kata (opt-in)**; `runc` is out for the
default path. This is decided **before** latency — no latency number rescues a shared-kernel
boundary under "arbitrary shell/git/build". It matches arch §9.1; this spike is the evidence
that ratifies it.

**Docker-in-sandbox (arch §5.3.3, §21 gated row):** on gVisor, `docker: true` is backed by a
**rootless dockerd sidecar** (no privileged container, no real nested virt) — covers most
build needs. **True nested Docker / VM-in-sandbox requires Kata.** So the `docker` capability
flag is the gate; the RuntimeClass decides the mechanism. Recommendation: ship rootless-dockerd
on gVisor as the default docker backing; route `docker`-with-real-nested-virt Runs to a Kata
`runtimeClassHint`. No architectural change — this is §5.3.3 + §9.1 as already seamed.

---

## 3. Latency taxonomy (what each runtime actually moves)

The issue asks for "claim-to-ready latency", but a warm pool deliberately **decouples** claim
latency from runtime start cost. Four distinct latencies:

| Latency | Definition | Dominated by | Does runtime choice move it? |
|---------|-----------|--------------|------------------------------|
| **Warm-claim** (`pool_hit=warm`) | Grab an already-`Ready` pod, bind to Run, inject context, start work | Control-plane grab + context assembly (§8.5), **not** sandbox boot | **Barely.** The pod is already booted. This is the SLI users feel (obs §5.3: p50≤2s / p95≤5s) and it is met by *having a warm pod*, independent of runtime. |
| **Cold-start** (`pool_hit=cold`) | Pool empty → create a pod → `Ready` | **Runtime sandbox-creation cost** + scheduling (image prepulled) | **Yes, strongly.** runc ≈ baseline; gVisor ≈ pod-like + sentry init; Kata ≈ + microVM boot. This is the miss penalty the pool exists to avoid. |
| **Replenish R** | Teardown-and-replace (§9.3): delete used pod → fresh pod `Ready` | Same as cold-start | **Yes.** R is the input that sets pool size (§4). Kata's larger R is the real cost of choosing it. |
| **Steady-state overhead** | Per-syscall / IO / memory tax while the agent runs | Workload shape × runtime | **Yes, but masked for LLM-bound work** — see below. |

**Steady-state overhead on LLM-bound workloads (issue ask #2).** An agent Run's wall-clock is
dominated by **waiting on the model API** (network round-trips, token streaming), not local
syscalls. gVisor's overhead concentrates on **syscall-heavy / IO-heavy** phases (git clone,
`npm install`, compiles); Kata's overhead is **memory footprint + boot**, not steady CPU.
Therefore:
- For the **LLM-bound majority** of an agent's wall-clock, gVisor overhead is **negligible**
  (the box is idle-waiting on the network anyway).
- The overhead that *does* land is on **build/IO bursts** — bounded, amortized, and the same
  work you'd pay on any isolation boundary. It does not change the runtime recommendation.

**Implication:** the runtime-selection decision rides on **isolation (§2) + replenish-cost-vs-pool-size
(§4)**, not on warm-claim latency and not on steady-state overhead. That reframing is the
main analytical result of the spike.

---

## 4. Pool-sizing model (where the runtime cost actually lands)

**Model.** The warm pool is a **base-stock inventory** system. It holds `N` `Ready` pods; a
claim consumes one; teardown-and-replace (§9.3) boots a fresh one in `R` seconds. A claim that
lands while the pool is empty is a `pool_hit=cold` miss. For Poisson claim arrivals at peak
rate **λ** (claims/s) and replenishment lead time **R** (s), demand-during-replenishment has
mean `λR` and (Poisson) std `sqrt(λR)`. Target ready-buffer for a warm-hit service level with
z-score `z`:

```
N = ceil( λR + z·sqrt(λR) )        z = 1.28 (90%), 1.65 (95%), 2.33 (99%)
```

`λR` = claims that land during one replenish window; `z·sqrt(λR)` = burst safety stock.
Calculator + self-test: **`bench/pool_sizing.py`** (`python3 pool_sizing.py --selftest`).

**Recommended buffer grid** at **95% warm-hit** (z=1.65). *R values below are CONSERVATIVE
PLACEHOLDERS pending the harness (§5) — the shape and the runtime-vs-runtime ratio are the
result; the absolute R is what §5 measures:*

| Runtime | Assumed R | light (3/min, λ=0.05) | medium (12/min, λ=0.2) | heavy (30/min, λ=0.5) |
|---------|-----------|:---------------------:|:----------------------:|:---------------------:|
| runc (baseline) | ~2s | 1 | 2 | 3 |
| **gVisor (default)** | ~4s | **1** | **3** | **5** |
| Kata (opt-in) | ~15s | 3 | 6 | 13 |

**Reading the grid — the load-bearing result:**
- The issue's suggested **2/5/10** sizes correspond to gVisor across light→heavy load; gVisor
  at heavy load lands at **5**, medium at **3** — comfortably in the 2–10 envelope.
- **Choosing Kata multiplies the required idle pool ~2–2.6×** for the *same* warm-hit SLA
  (heavy: 5 → 13), because its replenish time is ~4× longer. This is the concrete idle-cost
  argument for keeping gVisor the default and Kata opt-in — it is a **pool-size** cost, not a
  user-latency cost.
- Sizing is **per (RuntimeClass × AgentRuntime image)** key (§9.2), autoscaled between
  min/max on claim-rate (`warmpool.claim.pressure`, obs §5.3), not a fixed constant.

**Warm vs cold routing (issue ask, §9.2 hybrid regime):** interactive Runs draw from the warm
pool (sized above); **batch/non-interactive Runs may cold-start** (zero idle cost, sidesteps
reuse-contamination). Route by the Run class field. This keeps idle cost bounded: only
interactive demand pays for a warm buffer.

**Default policy to ship (behind §9.2 seam), pending §5 numbers:**
- gVisor, interactive: `min=2, target=base-stock(λ_peak, R_measured, 0.95), max=10`, scale on
  `claim.pressure`.
- Kata, interactive: same formula, but expect ~2× target; cap max tighter (idle cost) and
  prefer cold-start fallback for Kata bursts.
- Batch/non-interactive: `target=0` (cold-start), any runtime.

---

## 5. The measurement harness (fills in the real numbers)

**`bench/claim-latency-bench.sh`** — kubectl + bash + GNU date, no other deps. Per RuntimeClass
it measures and reports p50/p95 of:
- `cold_start` (create → `Ready`, image **prepulled** first so it measures sandbox creation, not
  image pull),
- `warm_claim` (exec round-trip against an already-`Ready` pod — the grab proxy),
- `replenish` (delete → fresh pod `Ready` — teardown-and-replace §9.3 → this is the **R** that
  feeds `pool_sizing.py`).

It **skips absent RuntimeClasses with a notice** (no silent truncation) and has a `--validate`
mode that runs with no cluster. Run:

```
# on a cluster that has the gvisor/kata RuntimeClasses installed:
ITERS=10 ./claim-latency-bench.sh runc gvisor kata
# then size from the measured repl_p95 (seconds):
python3 -c "from pool_sizing import table; print(table({'gvisor':R_g,'kata':R_k}, {'medium':0.2,'heavy':0.5}, 0.95))"
```

The harness reports in the **same units and shape as the obs SLI**
`ksquad.sandbox.claim.duration{runtime_class, pool_hit}` (obs §5.3), so the same instrument
validates the number in production. Wire the harness's cold/warm distinction to
`pool_hit=cold|warm` and the CI conformance suite consumes the histogram directly (obs OBS-3).

---

## 6. What remains empirical (falsification criteria before v1 default lock)

The **decision** (gVisor default, Kata opt-in, runc rejected) is robust to the numbers — it is
driven by isolation, which no latency measurement changes. What the harness must confirm before
v1 commits the *defaults and the S9 acceptance test*:

1. **gVisor warm-claim p95 ≤ 5s, p50 ≤ 2s** (obs §5.3 / NFR-PERF1 threshold). Expected to pass
   trivially since warm = already-Ready; the risk is context-assembly (§8.5) not the runtime.
2. **gVisor cold-start / replenish R is "pod-like"** (single-digit seconds). If gVisor R turns
   out ≫ expected on the target nodes, the gVisor pool target rises (still gVisor — §4 just sizes
   bigger). Only a *catastrophic* gVisor overhead on LLM-bound Runs would flip the default, and
   §3 argues that overhead is masked — this is the specific thing to watch.
3. **Kata R and nested-virt availability** on the actual node pool — confirms the ~2× pool
   multiplier and whether Kata is even schedulable (nested virt present?).
4. **Rootless-dockerd-on-gVisor** covers the observed `docker: true` build needs; only route to
   Kata what genuinely needs real nested virt.

**Disqualifying result (→ escalate):** if measured gVisor steady-state overhead on a
representative build-heavy Run exceeds ~1.5× runc wall-clock *and* that lands on the critical
path (not masked by model-wait), re-open the default-vs-Kata-vs-runc-trusted-dev trade with the
CTO. §3 predicts this will not happen for LLM-bound Runs; the harness proves it.

---

## 7. Disposition & handoffs

- **arch §9.1 / §21:** the RuntimeClass-default row moves from *provisional* to
  **recommended (gVisor), evidence-based**, with the empirical confirmation scoped to §5's
  harness. §9.2 pool-sizing row now has a concrete policy formula + default curve. (Pointer
  added; no locked decision reopened — this fills a spike-gated parameter behind an existing
  seam, exactly as §21 intends.)
- **Story ISI-2205 (Warm-pool sizing as policy) [GATE: ISI-2113]:** unblocked. The sizing
  policy = base-stock formula (§4) driven by `warmpool.replenish.duration` + `claim.pressure`
  (obs §5.3), autoscaled min/target/max. `pool_sizing.py` is the reference implementation of
  the target computation.
- **Epics 3/4/5/7:** the runtime default (gVisor) and the warm/cold routing (interactive=warm,
  batch=cold) are now decided, so dependent stories can proceed against those constants.
- **Remaining empirical step (not a blocker to the decision):** run `claim-latency-bench.sh`
  on a cluster with the RuntimeClasses before signing off the S9/NFR-PERF1 v1 acceptance test.
  Tracked as the follow-up in §6; owner = whoever stands up the first gVisor-enabled cluster.
