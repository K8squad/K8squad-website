#!/usr/bin/env python3
"""Story 8.8e falsification — token-consumption widget + trend (FR-I2, ADR-020, NFR-OBS3).

The token-consumption widget shows the current total (per user/agent/Run/Project) and a trend over a
selectable window (tokens/day), with an estimated cost where a price table is configured. It extends the
8.8a `tokenConsumption` snapshot sub-payload with a TREND QUERY. Three properties are load-bearing:

  (1) The trend is a QUERY SHAPE over the existing `ksquad.agent.tokens` counter (§5.5) — `rate()`/
      `increase()` over a time window — NOT a new metric instrument and NOT a stored rollup (ADR-020
      "ponytail"). If you find yourself registering a new counter or creating a usage table, stop.
  (2) Per-user/agent/Run DRILL-DOWN is the EXEMPLAR JOIN (§15/§16.5 backend rollup over traces) —
      `user.id`/`run.id`/`work_item.id` stay EXEMPLARS, NEVER metric labels (NFR-OBS3 crux). The KPI total
      + trend federate on BOUNDED `project`/`role` labels only.
  (3) No metrics backend wired (or Epic 13.4 absent) is a NORMAL STATE, not a failure: the widget degrades
      gracefully to "tokens not configured" / throughput-only, NEVER a fabricated number (8.8a per-tile rule).

Invariants (C1-C7, mapped to ACs of story 8.8e):
  C1  CURRENT TOTAL FROM 8.8A + BOUNDED-LABEL BREAKDOWN (AC1): the at-a-glance total reads the 8.8a
      `tokenConsumption` sub-payload; the per-scope breakdown federates on BOUNDED `project`/`role` labels
      from the metrics query seam (§17.2). No direct raw-store query bypassing the seam.
  C2  TREND = RATE()/INCREASE() OVER EXISTING COUNTER (AC2, the ponytail crux): the trend is the SAME
      `ksquad.agent.tokens` series read as a time range — a query shape, NOT a new metric instrument and
      NOT a stored rollup (ADR-020). Re-querying the seam on window change is correct; registering a new
      counter is not.
  C3  ESTIMATED COST VIA PRICE TABLE; DEGRADES TO TOKENS-ONLY (AC3): cost is computed via the §16.5 price
      table over the token series; where no price table is configured, the widget degrades to tokens-only —
      NEVER a fabricated cost.
  C4  DRILL-DOWN IS EXEMPLAR JOIN, NOT A METRIC LABEL (AC5/NFR-OBS3 crux): per-user/agent/Run breakdown
      is served by the §15/§16.5 exemplar/trace rollup — `user.id`/`run.id`/`work_item.id` are EXEMPLARS,
      NEVER metric labels. The KPI total + trend use only BOUNDED scope labels (`project`, `role`).
  C5  GRACEFUL DEGRADE WITH NO METRICS BACKEND (AC6): when 8.8a marks `tokenConsumption` `{available:false}`
      (no backend/Epic 13.4 absent), the widget renders an explicit degraded state (throughput-without-cost
      / "not configured") — NEVER a fabricated number, NEVER a hard failure.
  C6  NO NEW METRIC, NO BILLING STORE (AC7, ADR-020): no new `ksquad.*token*`/`*cost*` counter/gauge is
      registered here; no billing/usage table is introduced. The trend is a query shape over the existing
      instrument. Cost is a price-table computation over the series, never a persisted billing record.
  C7  NFR-OBS3 STANDING LAW (AC8): `user.id`/`agent`/`run.id`/`work_item.id` never a metric label; scope
      labels are BOUNDED (`project`, `role`); NO `model` label on any token instrument; token/cost is
      metering legibility, never a consumption/billing axis; the Epic 14 cardinality gate stays green.

Mutation-proof harness:
  --mutate=NEW_COUNTER      registers a new ksquad.tokens.trend metric instead of querying existing   -> C2 RED
  --mutate=ROLLUP_TABLE     stores trend in a new usage/rollup table                                  -> C6 RED
  --mutate=FAKE_COST        renders a fabricated cost when no price table configured                   -> C3 RED
  --mutate=LABEL_USER_ID    puts user.id on a metric label for the drill-down                         -> C4 RED
  --mutate=FAKE_ON_DEGRADE  renders a fabricated token count when metrics backend absent               -> C5 RED
  --mutate=MODEL_LABEL      adds model label to the token instrument                                   -> C7 RED
  --mutate=DIRECT_RAW_QUERY re-queries the raw metrics store directly, bypassing the query seam        -> C1 RED

Baseline exits 0; each --mutate exits 1.
"""
import sys

# the 8.8a tokenConsumption sub-payloads for two scenarios.
SCENARIO_METRICS_WIRED = {"available": True, "data": {"total_tokens": 842_300, "provenance": "metrics"}}
SCENARIO_METRICS_ABSENT = {"available": False, "reason": "metrics_backend_unwired"}


def compute_widget(design, payload, window="7d", price_table=None, mut=None):
    """Return (widget, meta) for the token-consumption widget."""
    # C1 — source: metrics query seam vs raw store direct query.
    source = "raw_metrics_store" if mut == "DIRECT_RAW_QUERY" else design["source"]

    # C2 — trend computation: rate() over existing counter vs new metric instrument.
    trend_instrument = "new_ksquad_tokens_trend" if mut == "NEW_COUNTER" else design["trend_instrument"]

    # C3 — cost computation: price-table vs fabricated cost.
    fake_cost = (mut == "FAKE_COST") or design.get("fake_cost", False)

    # C4 — drill-down: exemplar join vs metric label.
    drilldown_labels = set(design["drilldown_labels"])
    if mut == "LABEL_USER_ID":
        drilldown_labels = drilldown_labels | {"user.id"}

    # C5 — degrade behavior: explicit empty vs fabricated number.
    fake_on_degrade = (mut == "FAKE_ON_DEGRADE") or design.get("fake_on_degrade", False)

    # C6 — new metric / new store.
    new_metric = (mut == "NEW_COUNTER") or design.get("new_metric", False)
    new_store = (mut == "ROLLUP_TABLE") or design.get("new_store", False)

    # C7 — metric labels: bounded scope + no model label.
    metric_labels = set(design["metric_labels"]) | drilldown_labels
    if mut == "MODEL_LABEL":
        metric_labels = metric_labels | {"model"}

    if not payload["available"]:
        if fake_on_degrade:
            total = 0  # reads as real zero — the C5 defect
            available = True
            degraded = False
        else:
            total = None
            available = False
            degraded = True
    else:
        total = payload["data"]["total_tokens"]
        available = True
        degraded = False

    # trend: rate()/increase() over the time window [conformant] vs new counter [defect].
    trend = None if not available else {
        "instrument": trend_instrument, "window": window, "value": 12_000
    }

    # cost: price-table computation or tokens-only [conformant] vs fabricated [defect].
    if available and price_table:
        cost = {"value": total * price_table["per_token"], "currency": "USD", "estimate": True}
    elif available and fake_cost:
        cost = {"value": 9.99, "currency": "USD", "estimate": False, "fabricated": True}
    else:
        cost = None  # tokens-only degrade

    widget = {
        "available": available, "degraded": degraded,
        "total": total, "trend": trend, "cost": cost,
        "drilldown_source": "exemplar_join" if "user.id" not in drilldown_labels else "metric_label",
        "new_store": new_store,
    }
    meta = {
        "source": source, "trend_instrument": trend_instrument, "new_metric": new_metric,
        "new_store": new_store, "metric_labels": metric_labels,
    }
    return widget, meta


CONFORMANT = {
    "source": "metrics_query_seam",              # C1 — reads via the pluggable seam, not raw store
    "trend_instrument": "ksquad.agent.tokens",   # C2 — rate()/increase() over the EXISTING counter
    "fake_cost": False,                           # C3 — tokens-only when no price table
    "drilldown_labels": set(),                   # C4 — drill-down is exemplar join, no user.id label
    "fake_on_degrade": False,                     # C5 — explicit degraded state when backend absent
    "new_metric": False,                          # C6 — no new metric instrument
    "new_store": False,                           # C6 — no new rollup/billing store
    "metric_labels": {"project", "role"},         # C7 — bounded scope labels ONLY
}
BILLING_DASH = {
    "source": "raw_metrics_store",               # C1 fail — direct raw store query
    "trend_instrument": "new_ksquad_tokens_trend",  # C2 fail — new metric instrument
    "fake_cost": True,                            # C3 fail — fabricated cost
    "drilldown_labels": {"user.id", "run.id"},   # C4 fail — per-item ids as metric labels
    "fake_on_degrade": True,                      # C5 fail — fake zero when backend absent
    "new_metric": True,                           # C6 fail — new metric registered
    "new_store": True,                            # C6 fail — new billing/rollup store
    "metric_labels": {"project", "user.id", "run.id", "model"},  # C7 fail — per-item + model labels
}


def evaluate(design, mut):
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    # Scenario A: metrics backend wired, no price table.
    widget_ok, meta_ok = compute_widget(design, SCENARIO_METRICS_WIRED, price_table=None, mut=mut)
    # Scenario B: metrics backend absent.
    widget_deg, meta_deg = compute_widget(design, SCENARIO_METRICS_ABSENT, price_table=None, mut=mut)
    # Scenario C: metrics wired + price table configured.
    widget_cost, _ = compute_widget(design, SCENARIO_METRICS_WIRED,
                                    price_table={"per_token": 0.000002}, mut=mut)

    # C1 — breakdown via the metrics query seam, not a raw store direct query.
    check("C1", meta_ok["source"] == "metrics_query_seam",
          f"widget reads from {meta_ok['source']!r} — the token breakdown must go through the pluggable "
          f"metrics query seam (§17.2); no direct raw-store query bypassing the seam (AC1)")

    # C2 — trend = rate()/increase() over the EXISTING `ksquad.agent.tokens` counter.
    check("C2", meta_ok["trend_instrument"] == "ksquad.agent.tokens",
          f"trend uses instrument {meta_ok['trend_instrument']!r} — the trend is rate()/increase() over "
          f"the EXISTING `ksquad.agent.tokens` series (a query shape, §17.1); NOT a new counter or a "
          f"stored rollup (ADR-020 ponytail; AC2)")
    check("C2", not meta_ok["new_metric"],
          "this story registers a new metric instrument for the trend — it must NOT; the trend is a query "
          "shape over `ksquad.agent.tokens`, not a new counter/gauge (ADR-020 ponytail; AC2/AC7)")

    # C3 — cost via price table; degrades to tokens-only without a price table (never fabricated).
    check("C3", widget_ok["cost"] is None,
          f"widget shows cost={widget_ok['cost']} with no price table — it must degrade to tokens-only "
          f"when no price table is configured; NEVER a fabricated cost (AC3)")
    if widget_cost["cost"] is not None:
        check("C3", not widget_cost["cost"].get("fabricated"),
              f"estimated cost is flagged as fabricated: {widget_cost['cost']} — cost must be the price-"
              f"table computation over the token series, never a hard-coded or fabricated value (AC3)")

    # C4 — per-user/agent/Run drill-down is exemplar join, NOT a metric label.
    FORBIDDEN_DRILLDOWN = {"user.id", "run.id", "work_item.id", "agent"}
    bad_labels = sorted(meta_ok["metric_labels"] & FORBIDDEN_DRILLDOWN)
    check("C4", not bad_labels,
          f"metric label(s) {bad_labels} are per-item/agent identifiers used for the drill-down — the "
          f"breakdown must be the §15/§16.5 exemplar/trace rollup; these ids are EXEMPLARS, NEVER metric "
          f"labels (NFR-OBS3 cardinality firewall; AC5/AC8)")

    # C5 — metrics backend absent → explicit degraded state; NEVER a fabricated token count.
    check("C5", not widget_deg["available"] or widget_deg.get("degraded"),
          f"widget shows available={widget_deg['available']}, degraded={widget_deg.get('degraded')} when "
          f"the metrics backend is absent — must render an explicit degraded/not-configured state, NEVER a "
          f"fabricated token count or a zero that reads as real (8.8a per-tile degrade; AC6)")
    # positive control: when metrics backend IS wired, available=True with a real value.
    check("C5", widget_ok["available"] and widget_ok["total"] is not None,
          f"widget shows available={widget_ok['available']}, total={widget_ok['total']} when metrics ARE "
          f"wired — must render the real total (non-vacuous; not an over-broad degraded state, AC6)")

    # C6 — no new metric, no new billing/rollup store.
    check("C6", not meta_ok["new_store"],
          "this story introduces a new billing/rollup/usage datastore — ADR-020 forbids a rollup DB or "
          "billing store; the trend is a time-range query over the existing metering spine (AC7)")

    # C7 — bounded scope labels only; no model label; no per-item labels.
    FORBIDDEN_C7 = {"model", "user.id", "run.id", "work_item.id", "agent"}
    banned_c7 = sorted(meta_ok["metric_labels"] & FORBIDDEN_C7)
    check("C7", not banned_c7,
          f"metric label(s) {banned_c7} violate the cardinality firewall — `model` and per-item ids MUST "
          f"NOT be metric labels on any token instrument (obs §5.6/§17.1; NFR-OBS3; AC8)")
    # positive control: bounded scope labels ARE present.
    check("C7", {"project", "role"} <= meta_ok["metric_labels"],
          f"bounded scope labels (project, role) absent from metric_labels {meta_ok['metric_labels']} — "
          f"the at-a-glance total and trend must federate on bounded scope labels (non-vacuous; §16.2)")

    return fails


def run(mut=None):
    naive_fails = evaluate(BILLING_DASH, None)
    naive_hit = {inv for inv, _ in naive_fails}
    conf_fails = evaluate(CONFORMANT, mut)
    return naive_fails, naive_hit, conf_fails


MUTANTS = {
    "DIRECT_RAW_QUERY": "C1", "NEW_COUNTER": "C2", "FAKE_COST": "C3", "LABEL_USER_ID": "C4",
    "FAKE_ON_DEGRADE": "C5", "ROLLUP_TABLE": "C6", "MODEL_LABEL": "C7",
}
ALL_INV = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]


def main(argv):
    mut = None
    for a in argv[1:]:
        if a.startswith("--mutate="):
            mut = a.split("=", 1)[1].strip().upper()
    if mut and mut not in MUTANTS:
        print(f"unknown mutant {mut!r}; choose from {', '.join(MUTANTS)}", file=sys.stderr)
        return 2

    naive_fails, naive_hit, conf_fails = run(mut=mut)
    missing_teeth = [inv for inv in ALL_INV if inv not in naive_hit]
    if missing_teeth:
        print(f"[tok] TEETH LOST — billing-dashboard model no longer trips {missing_teeth}:")
        for inv, d in naive_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[tok] FAIL — §8.8e token-consumption widget violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] billing-dashboard anti-pattern  : {len(naive_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(naive_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] §8.8e conformant token widget   : 0 violation(s); "
              "seam-sourced, rate-over-existing-counter, tokens-only-degrade, "
              "exemplar-drilldown, explicit-empty-on-no-backend, no-new-metric/store, bounded-cardinality")
        print("[tok] PASS")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)})" if others else ""
        print(f"[tok] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[tok] SURVIVED — --mutate={mut} did NOT trip {expected}; tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
