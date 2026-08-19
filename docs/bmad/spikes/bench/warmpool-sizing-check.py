#!/usr/bin/env python3
"""
Story 3.5 (ISI-2205) falsification — Warm-pool sizing AS POLICY [GATE: ISI-2113].

Differential falsification, same shape as warmpool-claim-check.py (3.4) / run-retry-backoff-check.py
(3.2). Story 3.4 built the CONTROLLER MECHANISM (bind + scale-up trigger + replenish-to-target),
treating the target N as an opaque static input. THIS story owns the one place N is DERIVED: the
sizing POLICY that answers "how big should the warm buffer be, and how does it flex with load?"

The policy is exactly the arch §9.2 / ISI-2113 sentence:
  * target ready-buffer = base-stock level  N = ceil(λR + z·sqrt(λR))  (pool_sizing.recommend_buffer,
    the ISI-2113 reference impl — CONSUMED here, not reinvented: ponytail rung "integrate not invent"),
  * λ is the LIVE claim-pressure signal (obs §5.3 `warmpool.claim.pressure`) — the policy AUTOSCALES
    the target as λ moves, it is not a fixed constant (FR-C4),
  * bounded by [min, max] so idle cost is bounded (NFR-SCALE2); interactive floor min≥1 (a "warm" pool
    with 0 Ready pods is cold by definition); batch/non-interactive class → target=0 (zero idle cost,
    §9.2 hybrid regime),
  * sized PER (RuntimeClass × AgentRuntime image) key by THAT key's own measured replenish time R —
    Kata's ~4× R forces a ~2–2.6× larger target than gVisor for the same warm-hit SLA (§9.2),
  * scale-DOWN is damped (stabilization band) so a transient pressure dip does not thrash the pool
    (tearing down warm pods you immediately re-need = boots + reintroduced cold misses).

Curve pinned against ISI-2113 MEASURED results (`pool_sizing.py` __main__: gVisor repl_p95=1.716s,
runc=3.560s, per ISI-2294 on cluster `observable-agentsandbox`). "Ship policy against defaults; final
curve pinned when spike lands" (issue) — the spike landed with real R, so `test_pinned_curve` locks
the shipped gVisor defaults as a regression fence.

Mutation contract (the headline invariants must be falsifiable — re-run after any edit):
  * (P1) in SizingPolicy.base_stock, swap recommend_buffer(...) for the MEAN-ONLY ceil(λ·R)
         (drop the z·sqrt(λR) safety stock)                                        -> RED.
  * (P2) in SizingPolicy.target, ignore `observed_lambda` and size from a constant  -> RED.
  * (P3) in SizingPolicy.target, drop the `min(base, self.max_ready)` idle-cost cap -> RED.
  * (P4) in SizingPolicy.__init__, size every key from ONE shared R (ignore per-key) -> RED.

stdlib only. `python3 warmpool-sizing-check.py`. Exits non-zero on any falsification.
No wall-clock, no RNG: λ is a supplied logical pressure signal; R values are the pinned measurements.
"""
import math
import os
import sys

# Consume the ISI-2113 reference sizing impl (same dir). This is the point: 3.5 wires in the
# base-stock formula pool_sizing.py already self-tests; it does NOT re-derive the math.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pool_sizing import recommend_buffer  # noqa: E402

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)

# Pool keys = (RuntimeClass × AgentRuntime image), the one-dimensional §9.2 key.
GVISOR = ("gvisor", "runtime:v1")
KATA   = ("kata",   "runtime:v1")

# v1 MEASURED replenish_s per key (pool_sizing.py __main__ — ISI-2294; gVisor beats runc, Kata is the
# spike's conservative placeholder pending a nested-virt measurement). Sizing is per-key by design.
REPLENISH_S = {GVISOR: 1.716, KATA: 15.0}

# gVisor v1 defaults (arch §9.2): interactive min=2, max=10, 95% warm-hit; batch target=0.
MIN_READY, MAX_READY, SERVICE_LEVEL = 2, 10, 0.95


# ---------------------------------------------------------------------------
# THE SIZING POLICY (arch §9.2, ISI-2113). Pure arithmetic over the live pressure
# signal — no cluster, no clock. This is the ONE place the target N is derived.
# ---------------------------------------------------------------------------
class SizingPolicy:
    def __init__(self, replenish_s_by_key, min_ready, max_ready, service_level):
        self.replenish_s_by_key = replenish_s_by_key   # P4: per-(RuntimeClass×image) key R
        self.min_ready = min_ready
        self.max_ready = max_ready
        self.service_level = service_level

    def base_stock(self, key, observed_lambda):
        """Base-stock target for one key at the observed claim rate — the ISI-2113 formula, with
        its z·sqrt(λR) safety stock (P1). Consumes pool_sizing.recommend_buffer, does not reinvent."""
        R = self.replenish_s_by_key[key]               # P4: THIS key's own measured replenish time
        return recommend_buffer(observed_lambda, R, self.service_level)

    def target(self, key, observed_lambda, run_class):
        """The policy target for a (key, live-pressure, run-class). AUTOSCALES on observed_lambda
        (P2); clamps to [min, max] so idle cost is bounded (P3); batch → 0 (§9.2 hybrid)."""
        if run_class == "batch":
            return 0                                   # zero idle cost — batch cold-starts (§9.2)
        base = self.base_stock(key, observed_lambda)   # P2: derived from the LIVE pressure signal
        # P3 idle-cost cap + interactive warm floor. Bound BOTH ends: never below min (a warm pool
        # with 0 Ready is cold), never above max (runaway idle pods under a pressure spike).
        return max(self.min_ready, min(base, self.max_ready))


# ---------------------------------------------------------------------------
# THE AUTOSCALER — drives the §9.2 min/target/max reconcile off the live
# `warmpool.claim.pressure` signal, with a scale-DOWN stabilization band (P5)
# so a transient dip does not thrash the pool (HPA-style stabilization window).
# ---------------------------------------------------------------------------
class PoolAutoscaler:
    def __init__(self, policy, stabilization_ticks=3):
        self.policy = policy
        self.stab = stabilization_ticks
        self.current = {}     # key -> current target ready-count
        self._low = {}        # key -> consecutive ticks the desired target sat below current

    def reconcile(self, key, observed_lambda, run_class="interactive"):
        desired = self.policy.target(key, observed_lambda, run_class)
        cur = self.current.get(key, desired)
        if desired > cur:
            self._low[key] = 0
            cur = desired                              # scale UP immediately — never starve a burst
        elif desired < cur:
            self._low[key] = self._low.get(key, 0) + 1
            if self._low[key] >= self.stab:            # scale DOWN only after SUSTAINED low pressure
                cur = desired
                self._low[key] = 0
        else:
            self._low[key] = 0
        self.current[key] = cur
        return cur


def _mean_only(observed_lambda, R):
    """The naive under-provisioner: cycle demand λR with NO safety stock (P1 differential twin)."""
    return max(1, math.ceil(observed_lambda * R))


# ===========================================================================
# SCENARIOS
# ===========================================================================

# (P1) safety stock — base-stock carries the z·sqrt(λR) burst buffer above bare cycle demand.
def scenario_safety_stock():
    pol = SizingPolicy(REPLENISH_S, MIN_READY, MAX_READY, SERVICE_LEVEL)
    # heavy load on gVisor: cycle demand λR=0.858 -> mean-only ceil = 1; base-stock = 3 (safety=+2).
    base = pol.base_stock(GVISOR, 0.5)
    naive = _mean_only(0.5, REPLENISH_S[GVISOR])
    return base, naive

# (P2) autoscale — the target TRACKS the live claim-pressure signal, up and down, within bounds.
def scenario_autoscale_tracks_pressure():
    pol = SizingPolicy(REPLENISH_S, MIN_READY, MAX_READY, SERVICE_LEVEL)
    # sweep observed λ low -> high; interactive target must be monotonic non-decreasing in λ.
    lambdas = [0.05, 0.2, 0.5, 1.0, 3.0]
    targets = [pol.target(GVISOR, lam, "interactive") for lam in lambdas]
    monotonic = all(targets[i] <= targets[i + 1] for i in range(len(targets) - 1))
    # and it genuinely MOVES with pressure (a constant policy would be flat): low != high.
    moves = targets[0] != targets[-1]
    return targets, monotonic, moves

# (P3) idle-cost bound — no pressure spike drives the target past max; interactive floor holds at min.
def scenario_idle_cost_bounded():
    pol = SizingPolicy(REPLENISH_S, MIN_READY, MAX_READY, SERVICE_LEVEL)
    spike = pol.target(GVISOR, 50.0, "interactive")     # absurd pressure — unclamped would explode
    trickle = pol.target(GVISOR, 0.0001, "interactive") # near-zero pressure — floor must hold
    raw_at_spike = pol.base_stock(GVISOR, 50.0)         # what the base-stock alone would demand
    return spike, trickle, raw_at_spike

# (P3b) batch/non-interactive is target=0 — zero idle cost (§9.2 hybrid), regardless of pressure.
def scenario_batch_zero_idle():
    pol = SizingPolicy(REPLENISH_S, MIN_READY, MAX_READY, SERVICE_LEVEL)
    return [pol.target(GVISOR, lam, "batch") for lam in (0.0, 0.5, 50.0)]

# (P4) per-key R — Kata's ~4× replenish forces a larger target than gVisor at the SAME λ (§9.2).
def scenario_per_key_replenish():
    pol = SizingPolicy(REPLENISH_S, MIN_READY, MAX_READY, SERVICE_LEVEL)
    gv = pol.base_stock(GVISOR, 0.2)     # R=1.716 -> 2
    ka = pol.base_stock(KATA,   0.2)     # R=15.0  -> 6  (the 2–2.6×+ pool multiplier)
    return gv, ka

# (P5) scale-down hysteresis — a single-tick pressure dip does NOT tear the pool down (no thrash).
def scenario_hysteresis_no_thrash():
    pol = SizingPolicy(REPLENISH_S, MIN_READY, MAX_READY, SERVICE_LEVEL)
    az = PoolAutoscaler(pol, stabilization_ticks=3)
    # steady heavy pressure establishes a target, then ONE tick of low pressure, then heavy resumes.
    seq = [0.5, 0.5, 0.5, 0.05, 0.5, 0.5]
    hyst = [az.reconcile(GVISOR, lam) for lam in seq]
    # naive (no stabilization) re-evaluates raw every tick — it flaps down on the single dip.
    naive = [pol.target(GVISOR, lam, "interactive") for lam in seq]
    return hyst, naive

# (Pin) the shipped v1 gVisor curve at MEASURED R (ISI-2294). Regression fence on the defaults.
def scenario_pinned_curve():
    pol = SizingPolicy(REPLENISH_S, MIN_READY, MAX_READY, SERVICE_LEVEL)
    inter = {name: pol.target(GVISOR, lam, "interactive")
             for name, lam in (("light", 0.05), ("medium", 0.2), ("heavy", 0.5))}
    batch = pol.target(GVISOR, 0.5, "batch")
    return inter, batch


def main():
    # (P1) base-stock carries safety stock above bare cycle demand.
    base, naive = scenario_safety_stock()
    check(base > naive and base == 3 and naive == 1,
          "P1 safety-stock FAILED: the target dropped its z·sqrt(λR) burst buffer (mean-only sizing) "
          "-> the pool under-provisions and misses warm-hit SLA under a claim burst "
          "(swap recommend_buffer for mean-only ceil(λR) in base_stock to see this go RED)")

    # (P2) target autoscales on the live claim-pressure signal — monotonic in λ and genuinely moving.
    targets, monotonic, moves = scenario_autoscale_tracks_pressure()
    check(monotonic and moves,
          "P2 autoscale FAILED: the target does not track the live claim-pressure signal "
          "(a fixed constant ignores λ — over-provisions idle at low load, misses at high load; "
          "ignore `observed_lambda` in target() to see this go RED). targets=%r" % (targets,))

    # (P3) idle cost is bounded: max caps a pressure spike; the interactive floor holds at min.
    spike, trickle, raw_at_spike = scenario_idle_cost_bounded()
    check(spike == MAX_READY and raw_at_spike > MAX_READY and trickle == MIN_READY,
          "P3 idle-cost-bound FAILED: an unclamped target ran past max under a pressure spike "
          "(runaway idle pods) or fell below the interactive min floor "
          "(drop the min(base, self.max_ready) cap in target() to see this go RED). "
          "spike=%r raw=%r trickle=%r" % (spike, raw_at_spike, trickle))
    check(scenario_batch_zero_idle() == [0, 0, 0],
          "P3b batch-zero-idle FAILED: a batch/non-interactive class did not size to 0 "
          "(§9.2 hybrid: batch cold-starts, zero idle cost)")

    # (P4) each key is sized by ITS OWN replenish time — Kata's longer R => a larger pool.
    gv, ka = scenario_per_key_replenish()
    check(gv == 2 and ka == 6 and ka >= 2 * gv,
          "P4 per-key-R FAILED: Kata (R=15s) was not sized larger than gVisor (R=1.716s) at equal λ "
          "(sizing every key from one shared R under-sizes Kata / over-sizes gVisor — §9.2 multiplier; "
          "collapse replenish_s_by_key to a single R to see this go RED). gv=%r ka=%r" % (gv, ka))

    # (P5) scale-down hysteresis absorbs a transient dip; the naive re-eval thrashes on it.
    hyst, naive = scenario_hysteresis_no_thrash()
    check(min(hyst) == max(hyst) and min(naive) < max(naive),
          "P5 hysteresis FAILED: a single-tick pressure dip thrashed the pool (tore down warm pods "
          "it immediately re-needs = wasted boots + reintroduced cold misses). "
          "hyst=%r naive=%r" % (hyst, naive))

    # (Pin) the shipped v1 gVisor defaults at MEASURED R — a regression fence on the curve.
    inter, batch = scenario_pinned_curve()
    check(inter == {"light": 2, "medium": 2, "heavy": 3} and batch == 0,
          "PIN curve DRIFTED: the shipped v1 gVisor interactive curve at measured R=1.716s "
          "(ISI-2294) is {light:2, medium:2, heavy:3}, batch:0. A change here means the R/λ "
          "constants or the min/max envelope moved — re-pin deliberately. got=%r batch=%r"
          % (inter, batch))

    if FAIL:
        print("FALSIFIED — Story 3.5 warm-pool sizing-policy check FAILED:")
        for m in FAIL:
            print("  ✗", m)
        sys.exit(1)
    print("OK — Story 3.5 warm-pool sizing-as-policy design holds:")
    print("  (P1) target = base-stock ceil(λR + z·sqrt(λR)) — carries safety stock; mean-only under-provisions")
    print("  (P2) target autoscales on the live claim.pressure signal (monotonic in λ); a constant ignores load")
    print("  (P3) idle cost bounded: max caps a spike, min floors interactive, batch=0 (§9.2 hybrid)")
    print("  (P4) each (RuntimeClass×image) key sized by its OWN R — Kata's longer R forces a larger pool")
    print("  (P5) scale-down hysteresis absorbs a transient dip — no pool thrash (naive re-eval flaps)")
    print("  (PIN) shipped v1 gVisor curve at MEASURED R=1.716s (ISI-2294): light=2 medium=2 heavy=3, batch=0")


if __name__ == "__main__":
    main()
