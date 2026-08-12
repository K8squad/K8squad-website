#!/usr/bin/env python3
"""
ISI-2113 warm-pool sizing calculator.

The warm pool is a base-stock inventory system: it holds N pre-booted sandbox
pods `Ready`; a Run claim consumes one; teardown-and-replace (arch §9.3) boots a
FRESH pod, which takes `replenish_s` to reach Ready. A claim that arrives while
the pool is empty is a `pool_hit=cold` miss (obs §5.3 SLI) and eats the full
cold-start latency instead of ~grab-time.

Sizing target: keep P(pool_hit=warm) at a service level (e.g. 95%). With Poisson
claim arrivals at rate `lambda_cps` and replenishment lead time L ≈ replenish_s,
demand-during-lead-time has mean μ = λ·L and, for Poisson, σ = sqrt(λ·L). The
base-stock level is:

    N = ceil( μ + z·σ ) = ceil( λL + z·sqrt(λL) )

z is the normal quantile for the target warm-hit service level. λL is the "cycle
demand" (how many claims land during one replenish window); z·sqrt(λL) is safety
stock for burstiness. This is why runtime choice bites POOL SIZE, not warm-claim
latency: gVisor vs Kata barely changes the grab-time of an already-Ready pod, but
Kata's ~4x longer replenish_s inflates λL and therefore N for the same SLA.

This module is pure arithmetic (no cluster needed). Feed it the `replenish_s`
that claim-latency-bench.sh measures per RuntimeClass on real hardware, and the
`lambda_cps` you expect at peak, and it prints the recommended target buffer.
"""
from __future__ import annotations
import math

# Normal quantiles for common warm-hit service levels (one-sided).
Z = {0.90: 1.2816, 0.95: 1.6449, 0.99: 2.3263}


def recommend_buffer(lambda_cps: float, replenish_s: float,
                     service_level: float = 0.95) -> int:
    """Base-stock target ready-count for a warm pool.

    lambda_cps    : peak claim arrival rate (claims/second)
    replenish_s   : teardown-and-replace time to a fresh Ready pod (seconds)
    service_level : target P(pool_hit=warm), one of Z's keys (or any 0<sl<1)
    """
    if lambda_cps < 0 or replenish_s < 0:
        raise ValueError("rates and durations must be non-negative")
    z = Z.get(service_level)
    if z is None:  # linear-interp fallback so arbitrary SLAs still work
        z = _z_from_sl(service_level)
    cycle_demand = lambda_cps * replenish_s          # μ
    safety = z * math.sqrt(cycle_demand)             # z·σ, Poisson σ=sqrt(μ)
    # Floor of 1: a "warm" pool with 0 ready pods is cold by definition.
    return max(1, math.ceil(cycle_demand + safety))


def _z_from_sl(sl: float) -> float:
    """Acklam-style rational approximation of the normal inverse-CDF."""
    if not 0.0 < sl < 1.0:
        raise ValueError("service_level must be in (0,1)")
    # Beasley-Springer/Moro is overkill here; use a compact rational approx.
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if sl < plow:
        q = math.sqrt(-2 * math.log(sl))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if sl <= phigh:
        q = sl - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - sl))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def table(replenish_by_runtime: dict[str, float],
          lambdas: dict[str, float],
          service_level: float = 0.95) -> str:
    """Render a runtime x load-regime recommended-buffer grid."""
    rows = ["runtime      " + "".join(f"{name:>10}" for name in lambdas)]
    for rt, rep in replenish_by_runtime.items():
        cells = "".join(
            f"{recommend_buffer(lam, rep, service_level):>10}"
            for lam in lambdas.values())
        rows.append(f"{rt:<12} (R={rep:>4.1f}s){cells}")
    return "\n".join(rows)


def _selftest() -> None:
    # 1. Monotonic in load: more claims/sec => >= buffer.
    a = recommend_buffer(0.2, 4.0)
    b = recommend_buffer(0.5, 4.0)
    assert b >= a, (a, b)

    # 2. Monotonic in replenish time: slower replenish => >= buffer.
    #    This is the load-bearing claim of the spike (Kata's longer R costs pool).
    gvisor = recommend_buffer(0.2, 4.0)
    kata = recommend_buffer(0.2, 15.0)
    assert kata > gvisor, (gvisor, kata)

    # 3. Higher service level => >= buffer (more safety stock).
    assert recommend_buffer(0.2, 4.0, 0.99) >= recommend_buffer(0.2, 4.0, 0.90)

    # 4. Floor: a warm pool is never sized to 0 even at trickle load.
    assert recommend_buffer(0.0001, 1.0) == 1

    # 5. Worked value pinned in the spike report (gVisor, medium load, 95%):
    #    λL = 0.2*4 = 0.8; N = ceil(0.8 + 1.6449*sqrt(0.8)) = ceil(2.27) = 3.
    assert recommend_buffer(0.2, 4.0, 0.95) == 3, recommend_buffer(0.2, 4.0, 0.95)

    # 6. Kata heavy load pinned value: λL=7.5; N=ceil(7.5+1.6449*sqrt(7.5))=13.
    assert recommend_buffer(0.5, 15.0, 0.95) == 13, recommend_buffer(0.5, 15.0, 0.95)

    # 7. inverse-CDF approx agrees with tabulated z at the standard SLAs.
    assert abs(_z_from_sl(0.95) - 1.6449) < 1e-2, _z_from_sl(0.95)
    print("pool_sizing selftest: OK")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
        sys.exit(0)
    # Default: print the recommendation grid using the spike's CONSERVATIVE
    # placeholder replenish times. Replace these with claim-latency-bench.sh
    # measured p95 replenish_s before locking a v1 default (arch §21).
    REPLENISH_S = {"runc": 2.0, "gvisor": 4.0, "kata": 15.0}  # PLACEHOLDER — measure!
    LAMBDAS = {"light(3/m)": 0.05, "medium(12/m)": 0.2, "heavy(30/m)": 0.5}
    print("Recommended warm-pool target buffer (95% warm-hit) — "
          "R values are PLACEHOLDERS pending hardware measurement:\n")
    print(table(REPLENISH_S, LAMBDAS, 0.95))
    print("\nRun `python3 pool_sizing.py --selftest` to verify the model.")
