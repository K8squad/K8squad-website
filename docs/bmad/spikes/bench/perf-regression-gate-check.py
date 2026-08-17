#!/usr/bin/env python3
"""
Story 14.3 (ISI-2700) falsification — L3 performance regression GATE, P1-P4 relative SLIs.

Same differential shape as claim-nodouble-check.py (2.2) / chaos-harness.py (2.7 -> 14.2) /
warmpool-claim-check.py (3.4): it proves the perf GATE has TEETH by contrasting the arch-correct
RELATIVE-threshold gate (05-testing §5, "regression vs a pinned baseline, not brittle absolutes")
against the naive absolute/no-baseline/tolerate-drops gates the story rejects.

The thing under test is NOT a latency number — final numeric curves are spike-gated (ISI-2113).
The thing under test is the GATE LOGIC: given (baseline-on-main, candidate-on-branch) measured on the
SAME runner in the SAME job, does the comparator fail the build on a real regression and stay green
on hardware noise? Four sub-gates, each a §5 row:

  * P1 claim latency (S9/NFR-PERF1)   -> RELATIVE p95 vs main; RED if p95 drift > tolerance.
  * P2 warm-pool ready-count (FR-C1)  -> interactive Runs draw WARM; RED if interactive cold-start
                                         rate rises above the policy floor (batch may cold-start).
  * P3 SSE throughput (progress bus)  -> emit->deliver p95 RELATIVE + a ZERO-tolerance dropped-event
                                         count (dropped>0 at target concurrency is always RED).
  * P4 outbox delivery lag (§17.4)    -> write-path latency INDEPENDENT of plugin health: RED if the
                                         write p95 under a sick/slow plugin inflates past a small
                                         factor of the healthy write p95 (backpressure leaked in).

Why RELATIVE, not absolute (the headline design): a perf lane re-measures BOTH main and the branch on
the SAME hosted runner in the SAME job. If the runner is a slow draw that day, both scale together and
the RATIO is ~1 -> green. A brittle ABSOLUTE gate (`candidate.p95 < FIXED_MS`) would false-RED the
whole fleet on a slow-runner morning while STILL missing a regression measured on a fast draw. The
`uniform_hw_slowdown` scenario proves the relative gate rides through it AND still catches a genuine
slowdown layered on top.

Mutation contract (each headline tooth must be falsifiable — re-run after any edit):
  * M1  widen P1_TOL to 10.0 (any drift passes)                 -> `p1_real_regression` goes GREEN -> RED here.
  * M2  delete the missing-baseline fail-fast in require_baseline -> `p1_missing_baseline` GREEN -> RED here.
  * M3  make p3_gate tolerate dropped>0 (drop the ==0 check)     -> `p3_dropped_events` GREEN -> RED here.
  * M4  gate P4 on absolute outbox DEPTH not write-path ratio    -> `p4_isolation_break` GREEN -> RED here.

stdlib only. `python3 perf-regression-gate-check.py`. Exits non-zero on any falsification.
No wall-clock, no RNG: samples are fixed vectors; a "slow runner" is a deterministic scalar multiply.
"""
import sys

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)


def pctl(xs, q):
    """Nearest-rank percentile (q in 0..100). Deterministic; no interpolation, no numpy."""
    if not xs:
        raise ValueError("percentile of empty sample")
    s = sorted(xs)
    # nearest-rank: ceil(q/100 * N), 1-indexed
    k = max(1, -(-q * len(s) // 100))
    return s[k - 1]


# ---------------------------------------------------------------------------
# Relative-gate knobs. These are TOLERANCES on the ratio-to-main, NOT absolute
# SLO numbers (those land after ISI-2113). They are the only thing the gate
# hard-codes; everything else is measured head-vs-main in the same job.
# ---------------------------------------------------------------------------
P1_TOL = 0.20            # claim-latency p95 may drift +20% vs main before RED
P2_COLDRATE_FLOOR = 0.02 # interactive cold-start rate must stay ~0 (allow 2% jitter)
P3_LAT_TOL = 0.20        # SSE emit->deliver p95 may drift +20% vs main before RED
P4_ISO_FACTOR = 1.50     # write p95 under a sick plugin must stay within 1.5x of healthy write p95


class MissingBaseline(Exception):
    """A perf run with no pinned main baseline must FAIL THE BUILD, never silent-green."""


def require_baseline(baseline, name):
    # M2 tooth: deleting this guard lets a baseline-less run pass -> silent green.
    if baseline is None or (isinstance(baseline, (list, tuple)) and len(baseline) == 0):
        raise MissingBaseline(name)


def rel_regression(main_v, branch_v):
    """Signed fractional change vs main. >0 == slower/worse."""
    return (branch_v - main_v) / main_v


# ---------------------------------------------------------------------------
# The four sub-gates. Each returns (passed: bool, detail: str).
# A gate that RAISES MissingBaseline is a build FAILURE (caught by the driver).
# ---------------------------------------------------------------------------
def p1_gate(main_samples, branch_samples):
    require_baseline(main_samples, "P1 claim-latency baseline")
    reg = rel_regression(pctl(main_samples, 95), pctl(branch_samples, 95))
    return reg <= P1_TOL, f"p95 drift {reg:+.1%} (tol +{P1_TOL:.0%})"


def p2_gate(interactive_cold_rate, tier):
    # Batch Runs are ALLOWED to cold-start (expected, §5 P2 row); only interactive must draw warm.
    if tier == "batch":
        return True, "batch tier exempt (cold-start expected)"
    passed = interactive_cold_rate <= P2_COLDRATE_FLOOR
    return passed, f"interactive cold-start rate {interactive_cold_rate:.1%} (floor {P2_COLDRATE_FLOOR:.0%})"


def p3_gate(main_samples, branch_samples, dropped_events):
    require_baseline(main_samples, "P3 SSE-latency baseline")
    # M3 tooth: dropped events at target concurrency are ZERO-tolerance, never a relative budget.
    if dropped_events != 0:
        return False, f"{dropped_events} dropped event(s) at target concurrency (zero-tolerance)"
    reg = rel_regression(pctl(main_samples, 95), pctl(branch_samples, 95))
    return reg <= P3_LAT_TOL, f"emit->deliver p95 drift {reg:+.1%}, 0 dropped"


def p4_gate(write_p95_healthy, write_p95_sick):
    # The invariant is ISOLATION, proved WITHIN the candidate: a slow/failing plugin must not push
    # backpressure onto the write path. Compared branch-internal, not vs main (§17.4).
    # M4 tooth: gating on absolute outbox depth instead of this ratio misses the leak entirely.
    ratio = write_p95_sick / write_p95_healthy
    return ratio <= P4_ISO_FACTOR, f"write p95 sick/healthy = {ratio:.2f}x (max {P4_ISO_FACTOR:.2f}x)"


# ---------------------------------------------------------------------------
# Scenarios. Each pins the EXPECTED verdict; the check asserts the gate agrees.
# GREEN == gate passes (merge allowed); RED == gate fails the build.
# ---------------------------------------------------------------------------
# A representative claim-latency sample vector (ms) measured on `main`, p95 ~ 42.
MAIN_P1 = [12, 14, 15, 16, 18, 19, 20, 22, 24, 26, 28, 31, 34, 38, 42]


def scale(xs, k):
    return [x * k for x in xs]


def run_scenarios():
    # -- P1: no change (noise within tol) -> GREEN (positive control) --
    ok, d = p1_gate(MAIN_P1, [x + 1 for x in MAIN_P1])
    check(ok, f"[p1_no_change] expected GREEN, gate said RED: {d}")

    # -- P1: a genuine +50% p95 regression -> RED (the teeth; M1 kills this) --
    ok, d = p1_gate(MAIN_P1, scale(MAIN_P1, 1.5))
    check(not ok, f"[p1_real_regression] expected RED, gate said GREEN: {d}")

    # -- P1: whole runner 1.6x slower, main re-measured same job -> ratio ~1 -> GREEN.
    #        A brittle ABSOLUTE gate would false-RED here; the relative gate rides through. --
    slow_main = scale(MAIN_P1, 1.6)
    slow_branch = scale(MAIN_P1, 1.6)
    ok, d = p1_gate(slow_main, slow_branch)
    check(ok, f"[p1_uniform_hw_slowdown] expected GREEN (relative), gate said RED: {d}")
    #   ...and a real regression LAYERED ON the slow runner is still caught -> RED.
    ok, d = p1_gate(slow_main, scale(slow_branch, 1.5))
    check(not ok, f"[p1_regression_on_slow_hw] expected RED, gate said GREEN: {d}")

    # -- P1: an improvement (faster) is never gated -> GREEN --
    ok, d = p1_gate(MAIN_P1, scale(MAIN_P1, 0.7))
    check(ok, f"[p1_improvement] expected GREEN, gate said RED: {d}")

    # -- P1: missing baseline -> build FAILURE (M2 kills this) --
    raised = False
    try:
        p1_gate(None, MAIN_P1)
    except MissingBaseline:
        raised = True
    check(raised, "[p1_missing_baseline] expected fail-fast MissingBaseline, gate silently passed")

    # -- P2: interactive draws warm -> GREEN --
    ok, d = p2_gate(0.0, "interactive")
    check(ok, f"[p2_interactive_warm] expected GREEN, gate said RED: {d}")
    # -- P2: a regression makes interactive Runs cold-start (18%) -> RED --
    ok, d = p2_gate(0.18, "interactive")
    check(not ok, f"[p2_interactive_coldstart_regression] expected RED, gate said GREEN: {d}")
    # -- P2: batch tier cold-starts -> GREEN (expected, exempt) --
    ok, d = p2_gate(0.40, "batch")
    check(ok, f"[p2_batch_coldstart_exempt] expected GREEN, gate said RED: {d}")

    # -- P3: bounded latency, zero drops -> GREEN --
    ok, d = p3_gate(MAIN_P1, [x + 2 for x in MAIN_P1], dropped_events=0)
    check(ok, f"[p3_clean] expected GREEN, gate said RED: {d}")
    # -- P3: one dropped event at target concurrency -> RED (zero-tolerance; M3 kills this) --
    ok, d = p3_gate(MAIN_P1, MAIN_P1, dropped_events=1)
    check(not ok, f"[p3_dropped_events] expected RED, gate said GREEN: {d}")
    # -- P3: latency p95 blows out +60% even with zero drops -> RED --
    ok, d = p3_gate(MAIN_P1, scale(MAIN_P1, 1.6), dropped_events=0)
    check(not ok, f"[p3_latency_regression] expected RED, gate said GREEN: {d}")

    # -- P4: sick plugin, write path unaffected (1.1x) -> GREEN (isolation holds) --
    ok, d = p4_gate(write_p95_healthy=20.0, write_p95_sick=22.0)
    check(ok, f"[p4_isolation_holds] expected GREEN, gate said RED: {d}")
    # -- P4: sick plugin leaks backpressure, write p95 3x -> RED (isolation broken; M4 kills this) --
    ok, d = p4_gate(write_p95_healthy=20.0, write_p95_sick=60.0)
    check(not ok, f"[p4_isolation_break] expected RED, gate said GREEN: {d}")


def main():
    run_scenarios()
    if FAIL:
        print("PERF-GATE FALSIFIED — the L3 regression gate does not hold:")
        for m in FAIL:
            print("  FAIL:", m)
        print(f"\n{len(FAIL)} falsification(s). The gate is NOT safe to merge behind.")
        sys.exit(1)
    print("PERF-GATE OK — P1-P4 relative regression gates have teeth:")
    print("  P1 claim latency   : relative p95 vs main; real regression RED, hw-noise GREEN, no-baseline fails fast")
    print("  P2 warm-pool ready : interactive cold-start regression RED; batch cold-start exempt")
    print("  P3 SSE throughput  : latency relative + dropped-events ZERO-tolerance")
    print("  P4 outbox lag      : write-path p95 independent of plugin health (§17.4 isolation)")
    print("\nAll expected GREEN/RED verdicts matched. Mutations M1-M4 each re-RED this check.")


if __name__ == "__main__":
    main()
