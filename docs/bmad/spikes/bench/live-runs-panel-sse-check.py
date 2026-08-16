#!/usr/bin/env python3
"""Story 8.8f falsification — Live Runs panel with SSE (FR-I4, no-P2P, rate-limit/fallback, AC5 resume_at).

The Live Runs panel shows the agent↔task↔Project mapping (who is running what) SSE-updated in real time,
with rate-limit/fallback indicators and a `resume_at` countdown for `Paused(rate_limited)` Runs (2.11).
Three properties are load-bearing and non-negotiable:

  (1) SSE over the EXISTING progress bus (same EventSource + BFF proxy as the Run stream and org diagram,
      §4.4/§13) — NO polling loop, NO new transport. This panel OWNS the live-Run deltas that 8.8b (KPI
      counters) and 8.8c (approval count) consume.
  (2) READ + NAVIGATE ONLY — NO mutate/claim/transition affordance on the panel (no-P2P on the console,
      §13 r10 org-diagram precedent). A claim button here would reintroduce a console-side coordination
      affordance the architecture forbids.
  (3) The `resume_at` countdown is derived from the REAL, DURABLE `resume_at` in the coordination record
      (2.11 — `now + Retry-After`, crash-safe) — it is NOT a client-invented timer. It reflects an early
      resume (fallback switch, 5.11) or a re-derived `resume_at` after a controller restart. Showing a
      resume the record does not carry misleads the operator.

Invariants (C1-C7, mapped to ACs of story 8.8f):
  C1  LIVE AGENT↔TASK↔PROJECT MAP FROM liveRuns (AC1): the panel renders the agent↔task↔Project mapping
      for each active Run from the 8.8a `liveRuns` sub-payload (Run/claim state). Empty/degraded state
      ("No active Runs") when the sub-payload is empty or `{available:false}`. No placeholder rows.
  C2  SSE OVER EXISTING BUS; NO POLLING (AC2, transport crux): updates arrive via SSE deltas over the
      EXISTING EventSource + BFF proxy (§4.4/§13, same bus as the Run stream / org diagram / 8.8a). NO
      polling loop, NO new transport. Deltas are consistent with the 8.8a snapshot+delta contract (name
      the changed Run so the client patches in place). This panel OWNS the live-Run delta stream that
      8.8b/8.8c consume.
  C3  READ + NAVIGATE ONLY; NO CLAIM AFFORDANCE (AC3, no-P2P crux): the panel has NO mutate/claim/
      transition affordance. Click-through to the Run (8.2), work item (8.14), agent — no claim, reassign,
      or drive-agent control. Mirrors the org-diagram read model precedent (§13 r10).
  C4  RATE-LIMIT/FALLBACK INDICATORS SSE-UPDATED + GRACEFUL DEGRADE (AC4): throttled agents, active
      fallback models, and the `resume_at` countdown for `Paused(rate_limited)` Runs are SSE-updated (same
      bus, AC2) and degrade gracefully — where 2.11/3.7/5.11/13.9 are absent, the panel shows the live map
      without the indicators.
  C5  resume_at FROM REAL COORD RECORD; NOT A CLIENT-INVENTED TIMER (AC5): the countdown is derived from
      the real `resume_at` in the coordination record (2.11); it counts to that timestamp and reflects an
      early resume (fallback switch, 5.11) or re-derived `resume_at` after a controller restart. It NEVER
      shows a resume the record does not carry.
  C6  RBAC THROUGH 8.8A; REAL ROWS ONLY (AC6): the `liveRuns` sub-payload is already server-filtered by
      8.8a's deny-by-default RBAC wall (§12.3); this story adds NO client-side authz. Every row is a real
      in-flight Run (Run/claim state) — no placeholder.
  C7  NO NEW DOMAIN METRIC (AC7, NFR-OBS3): ordinary console/BFF stream telemetry only; rate-limit/fallback
      figures come from 13.9's metrics, not this panel. No per-item ids (`run.id`/`work_item.id`/`agent`/
      `user.id`) as metric labels; no `model` label; live map is legibility, never a consumption axis.

Mutation-proof harness:
  --mutate=POLL_TRANSPORT           drive live updates with a polling loop, not SSE                 -> C2 RED
  --mutate=CLAIM_BUTTON             add a claim/assign affordance to the panel                      -> C3 RED
  --mutate=MISSING_RATELIMIT_INDICATOR omit the throttle/fallback indicators entirely               -> C4 RED
  --mutate=STALE_THROTTLE_INDICATOR render the indicators from a stale snapshot, not the SSE bus     -> C4 RED
  --mutate=CLIENT_TIMER             use a client-invented timer for resume_at instead of the record  -> C5 RED
  --mutate=FAKE_ROWS                render placeholder rows when liveRuns is empty/degraded          -> C1 RED
  --mutate=CLIENT_AUTHZ             add a client-side authz predicate                                -> C6 RED
  --mutate=PERITEM_LABEL            put run.id on a metric label                                     -> C7 RED
  --mutate=HARD_FAIL_DEGRADE        hard-fail when liveRuns source is unavailable (5xx / throw)     -> C1 RED

Baseline exits 0; each --mutate exits 1.
"""
import sys

# 8.8a liveRuns sub-payload — runs active, one is Paused(rate_limited) with a real resume_at and
# throttle/fallback indicators (2.11/3.7/5.11/13.9), one Running on an active fallback model.
SCENARIO_LIVE = {
    "available": True,
    "data": [
        {"run_id": "r-99", "agent": "hermes", "task": "wi-01", "project": "p-alpha",
         "state": "Running", "paused_reason": None, "resume_at": None,
         "throttled": False, "fallback_model": None},
        {"run_id": "r-100", "agent": "openclaw", "task": "wi-02", "project": "p-alpha",
         "state": "Paused", "paused_reason": "rate_limited",
         "resume_at": "2026-08-13T16:45:00Z",  # from the coordination record (2.11)
         "throttled": True, "fallback_model": None},  # throttled agent (13.9)
        {"run_id": "r-101", "agent": "hermes", "task": "wi-05", "project": "p-alpha",
         "state": "Running", "paused_reason": None, "resume_at": None,
         "throttled": False, "fallback_model": "haiku-4-5"},  # active fallback model (5.11)
    ]
}
SCENARIO_EMPTY = {"available": True, "data": []}
SCENARIO_DEGRADED = {"available": False, "reason": "runstate_unavailable"}


def render_panel(design, payload, mut=None):
    """Return (panel, meta) for the Live Runs panel surface."""
    # C2 — transport: existing SSE bus vs polling.
    transport = "polling_loop" if mut == "POLL_TRANSPORT" else design["transport"]

    # C3 — affordances: read+navigate only vs mutate/claim.
    affordances = set(design["affordances"])
    if mut == "CLAIM_BUTTON":
        affordances = affordances | {"claim", "reassign"}

    # C5 — resume_at source: real coordination record vs client-invented timer.
    resume_source = "client_timer" if mut == "CLIENT_TIMER" else design["resume_source"]

    # C6 — client-side authz.
    client_authz = (mut == "CLIENT_AUTHZ") or design.get("client_authz", False)

    # C4 — rate-limit/fallback indicators: present + SSE-updated vs omitted / stale snapshot.
    render_indicators = False if mut == "MISSING_RATELIMIT_INDICATOR" else design.get("render_indicators", True)
    indicator_source = "stale_snapshot" if mut == "STALE_THROTTLE_INDICATOR" else design.get("indicator_source", "sse")

    # C7 — metric labels.
    metric_labels = set(design["metric_labels"])
    if mut == "PERITEM_LABEL":
        metric_labels = metric_labels | {"run.id"}

    fake_rows = (mut == "FAKE_ROWS") or design.get("fake_rows", False)
    hard_fail = (mut == "HARD_FAIL_DEGRADE") or design.get("hard_fail", False)

    if not payload["available"]:
        if hard_fail:
            return None, {"transport": transport, "http": 500, "affordances": affordances,
                          "metric_labels": metric_labels, "client_authz": client_authz}
        if fake_rows:
            rows = [{"run_id": "r-FAKE", "agent": "placeholder", "task": "???",
                     "project": "???", "fabricated": True}]
        else:
            rows = []
        return {"rows": rows, "empty": True, "available": False, "http": 200}, \
               {"transport": transport, "http": 200, "affordances": affordances,
                "metric_labels": metric_labels, "client_authz": client_authz, "resume_source": resume_source}

    rows = []
    for run in payload["data"]:
        countdown = None
        if run["paused_reason"] == "rate_limited" and run["resume_at"]:
            if resume_source == "client_timer":
                countdown = {"source": "client_invented", "value": "T-unknown"}
            else:
                countdown = {"source": "coordination_record", "value": run["resume_at"]}
        # C4 — throttle/fallback indicator, rendered ONLY where the payload carries the signal
        # (graceful degrade: absent where 2.11/3.7/5.11/13.9 are), SSE-updated over the same bus.
        indicator = None
        if render_indicators and (run.get("throttled") or run.get("fallback_model")):
            indicator = {
                "throttled": bool(run.get("throttled")),
                "fallback_model": run.get("fallback_model"),
                "updated_via": indicator_source,
            }
        rows.append({
            "run_id": run["run_id"], "agent": run["agent"], "task": run["task"],
            "project": run["project"], "state": run["state"],
            "paused_reason": run["paused_reason"], "countdown": countdown,
            "indicator": indicator, "fabricated": False,
        })

    return {"rows": rows, "empty": len(rows) == 0, "available": True, "http": 200}, \
           {"transport": transport, "http": 200, "affordances": affordances,
            "metric_labels": metric_labels, "client_authz": client_authz, "resume_source": resume_source}


CONFORMANT = {
    "transport": "sse_existing",                    # C2 — existing EventSource + BFF proxy
    "affordances": {"view", "navigate"},             # C3 — read + navigate only; no claim
    "render_indicators": True,                       # C4 — throttle/fallback indicators present
    "indicator_source": "sse",                       # C4 — indicators SSE-updated over the same bus
    "resume_source": "coordination_record",          # C5 — real resume_at from coord record (2.11)
    "client_authz": False,                           # C6 — no client-side authz
    "metric_labels": set(),                         # C7 — no per-item ids as metric labels
    "fake_rows": False, "hard_fail": False,
}
POLLING_CLAIM = {
    "transport": "polling_loop",                    # C2 fail — polling, not SSE
    "affordances": {"view", "navigate", "claim", "reassign"},  # C3 fail — mutate/claim affordance
    "render_indicators": False,                     # C4 fail — no throttle/fallback indicators
    "indicator_source": "stale_snapshot",           # C4 fail — indicators not off the SSE bus
    "resume_source": "client_timer",                # C5 fail — client-invented timer
    "client_authz": True,                           # C6 fail — client-side authz
    "metric_labels": {"run.id", "agent", "user.id"},  # C7 fail — per-item ids as labels
    "fake_rows": True,                              # C1 fail — placeholder rows when degraded
    "hard_fail": True,                              # C1 fail — 5xx on unavailable
}


def evaluate(design, mut):
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    # Scenario A: runs active
    panel_live, meta_live = render_panel(design, SCENARIO_LIVE, mut=mut)
    # Scenario B: no active runs
    panel_empty, meta_empty = render_panel(design, SCENARIO_EMPTY, mut=mut)
    # Scenario C: source degraded
    panel_deg, meta_deg = render_panel(design, SCENARIO_DEGRADED, mut=mut)

    # C1 — live map from `liveRuns`; empty/degraded → explicit "No active Runs", never placeholder.
    if panel_live is not None:
        faked = [r["run_id"] for r in panel_live["rows"] if r.get("fabricated")]
        check("C1", not faked,
              f"panel contains fabricated row(s) {faked} — every row must be a real in-flight Run from "
              f"the 8.8a `liveRuns` sub-payload (Run/claim state); no placeholder (AC1/FR-I3)")
        check("C1", len(panel_live["rows"]) == len(SCENARIO_LIVE["data"]),
              f"panel has {len(panel_live['rows'])} rows for {len(SCENARIO_LIVE['data'])} live Runs — "
              f"all live Runs must render (non-vacuous; AC1)")

    check("C1", meta_deg.get("http") == 200,
          f"panel returned HTTP {meta_deg.get('http')} with source unavailable — must return 200 with an "
          f"explicit empty/degraded state (8.8a per-tile degrade; AC1)")
    if panel_deg is not None:
        faked_deg = [r["run_id"] for r in panel_deg.get("rows", []) if r.get("fabricated")]
        check("C1", not faked_deg,
              f"degraded panel contains fabricated row(s) {faked_deg} — must show an explicit 'No active "
              f"Runs' state when the source is unavailable (AC1)")

    # C2 — SSE over existing bus; no polling; delta contract.
    check("C2", meta_live["transport"] == "sse_existing",
          f"panel uses {meta_live['transport']!r} for live updates — must use the EXISTING SSE progress "
          f"bus (EventSource + BFF proxy, §4.4/§13, same as the Run stream / org diagram / 8.8a); "
          f"NO polling loop, NO new transport (AC2)")

    # C3 — read + navigate only; no claim/reassign/transition affordance.
    ALLOWED_AFFORDANCES = {"view", "navigate"}
    bad_affordances = sorted(meta_live["affordances"] - ALLOWED_AFFORDANCES)
    check("C3", not bad_affordances,
          f"panel exposes mutate/claim affordance(s) {bad_affordances} — the panel is READ + NAVIGATE "
          f"ONLY; no claim, reassign, or drive-agent control (no-P2P on the console, §13 r10 "
          f"org-diagram precedent; AC3)")
    check("C3", "navigate" in meta_live["affordances"],
          "navigate affordance absent — the panel must allow click-through to Run/work item/agent "
          "(non-vacuous; AC3)")

    # C4 — rate-limit/fallback indicators present AND SSE-updated; degrade gracefully.
    # The figures come from 13.9/2.11/5.11; this panel SSE-consumes and renders them per-Run.
    if panel_live is not None:
        signal_ids = {run["run_id"] for run in SCENARIO_LIVE["data"]
                      if run.get("throttled") or run.get("fallback_model")}
        indicated = [r for r in panel_live["rows"]
                     if r["run_id"] in signal_ids and r.get("indicator")]
        # present half — every throttled/fallback Run must carry an indicator (the untoothed gap, F1).
        check("C4", len(indicated) == len(signal_ids),
              f"{len(indicated)}/{len(signal_ids)} throttled/fallback Runs render an indicator — the "
              f"rate-limit/fallback indicators (throttled agent, active fallback model) MUST be present "
              f"for every Run the `liveRuns` payload marks throttled/fallback; omitting them entirely "
              f"leaves the 'indicators present' half of AC4 untoothed (AC4)")
        # SSE-updated half — indicators ride the SAME existing bus (AC2), not a stale snapshot.
        for r in indicated:
            check("C4", r["indicator"]["updated_via"] == "sse",
                  f"Run {r['run_id']}: indicator updated_via={r['indicator']['updated_via']!r} — the "
                  f"throttle/fallback indicators MUST be SSE-updated over the EXISTING bus (AC2), not a "
                  f"stale snapshot or a separate poll (AC4)")
        # graceful-degrade half — NO indicator fabricated where the payload carries no throttle/fallback
        # signal (where 2.11/3.7/5.11/13.9 are absent, the panel shows the live map without indicators).
        fabricated_ind = [r["run_id"] for r in panel_live["rows"]
                          if r["run_id"] not in signal_ids and r.get("indicator")]
        check("C4", not fabricated_ind,
              f"Run(s) {fabricated_ind} render a rate-limit/fallback indicator without the payload marking "
              f"them throttled/fallback — indicators degrade gracefully and appear ONLY where the signal is "
              f"carried; no fabricated indicators (AC4 graceful-degrade half)")

    # C5 — resume_at from the real coordination record (2.11); never a client-invented timer.
    rate_limited_rows = [r for r in (panel_live or {}).get("rows", [])
                         if r.get("paused_reason") == "rate_limited"]
    for r in rate_limited_rows:
        cd = r.get("countdown")
        if cd is not None:
            check("C5", cd["source"] == "coordination_record",
                  f"Run {r['run_id']}: countdown source={cd['source']!r} — the resume_at countdown MUST "
                  f"be derived from the real `resume_at` in the coordination record (2.11, crash-safe); "
                  f"NOT a client-invented timer (AC5)")
    # positive control: Paused(rate_limited) Run WITH a real resume_at renders a countdown.
    rl_with_resume = [r for r in rate_limited_rows if r.get("countdown")]
    check("C5", bool(rl_with_resume),
          f"no countdown rendered for Paused(rate_limited) Runs with a real resume_at — the countdown "
          f"must appear and be derived from the coord record (non-vacuous; AC5)")

    # C6 — no client-side authz; pre-scoped by 8.8a.
    check("C6", not meta_live["client_authz"],
          "panel adds a client-side authz predicate — the `liveRuns` sub-payload is already server-"
          "filtered by 8.8a's deny-by-default RBAC wall (§12.3); no second filter here (AC6)")

    # C7 — no per-item ids as metric labels; no model label.
    FORBIDDEN = {"run.id", "work_item.id", "agent", "user.id", "model"}
    banned = sorted(meta_live["metric_labels"] & FORBIDDEN)
    check("C7", not banned,
          f"metric label(s) {banned} are per-item/agent/model identifiers — span/exemplar only, never "
          f"metric labels (NFR-OBS3 cardinality firewall; live map is legibility, not a consumption axis; "
          f"rate-limit/fallback figures come from 13.9's metrics, not here; AC7)")

    return fails


def run(mut=None):
    naive_fails = evaluate(POLLING_CLAIM, None)
    naive_hit = {inv for inv, _ in naive_fails}
    conf_fails = evaluate(CONFORMANT, mut)
    return naive_fails, naive_hit, conf_fails


MUTANTS = {
    "FAKE_ROWS": "C1", "POLL_TRANSPORT": "C2", "CLAIM_BUTTON": "C3",
    "MISSING_RATELIMIT_INDICATOR": "C4", "STALE_THROTTLE_INDICATOR": "C4",
    "CLIENT_TIMER": "C5", "CLIENT_AUTHZ": "C6", "PERITEM_LABEL": "C7",
    "HARD_FAIL_DEGRADE": "C1",
}
ALL_INV = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]


def main(argv):
    mut = None
    for a in argv[1:]:
        if a.startswith("--mutate="):
            mut = a.split("=", 1)[1].strip().upper()
    if mut and mut not in MUTANTS:
        print(f"unknown mutant {mut!r}; choose from {', '.join(sorted(MUTANTS))}", file=sys.stderr)
        return 2

    naive_fails, naive_hit, conf_fails = run(mut=mut)
    missing_teeth = [inv for inv in ALL_INV if inv not in naive_hit]
    if missing_teeth:
        print(f"[runs] TEETH LOST — polling-claim panel no longer trips {missing_teeth}:")
        for inv, d in naive_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[runs] FAIL — §8.8f Live Runs panel violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] polling-claim-panel anti-pattern : {len(naive_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(naive_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] §8.8f conformant Live Runs panel  : 0 violation(s); "
              "sse-existing-bus, read+navigate-only, sse-throttle/fallback-indicators, "
              "coord-record-resume_at, real-rows-only, no-second-authz, bounded-cardinality")
        print("[runs] PASS")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)})" if others else ""
        print(f"[runs] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[runs] SURVIVED — --mutate={mut} did NOT trip {expected}; tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
