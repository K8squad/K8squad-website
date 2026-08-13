#!/usr/bin/env python3
"""Story 8.8b falsification — KPI card row + Recent Tickets + quick-access links (FR-I7/I8, FR-I3).

The KPI card row shows four cards (tickets-by-status, tokens-consumed, PRs-by-status, live Runs), a Recent
Tickets list with status badges and a "View all" link, and quick-access links to the Project's primary
surfaces (Issues/Tickets, File Explorer/build browser, Board, Discussion). Every value comes from the **8.8a
composed payload** — this story is a RENDERING story, not a data story: it does NOT re-query coord/scm/
metrics/Run-state directly (that is 8.8a's job). Two properties are load-bearing: (1) every KPI figure and
every Recent-Tickets row reads from the 8.8a sub-payload (pre-scoped by the single deny-by-default RBAC wall
in 8.8a — no second authz path here); (2) a card whose backing source is degraded (8.8a returned
`{available:false}`) renders an EXPLICIT empty/not-configured state, NEVER a fabricated number or a
misleading zero (FR-I3 provenance crux). Live counters ride the EXISTING SSE progress bus (same as the Run
stream — no polling, no new transport). No new domain metric.

Invariants (C1-C7, each mapped to an AC of story 8.8b):
  C1  FROM 8.8A, NOT RE-QUERIED (AC1): the four KPI cards (ticketsByStatus/tokenConsumption/prBoard/
      liveRuns) read from the 8.8a sub-payloads; this story issues NO direct coord/scm/metrics/Run-state
      query. The single source of truth (and the single RBAC wall) is 8.8a.
  C2  STATUS BADGES + VIEW-ALL (AC2): the Recent Tickets list renders from the `recentTickets` sub-payload
      with a status badge per row (work_item.state values: Backlog/Todo/In Progress/In Review/Done + Blocked
      overlay per §13 r25) and a "View all" link into Project → Tickets. No placeholder rows.
  C3  PROJECT-ROOTED QUICK-ACCESS (AC3, FR-I8): quick-access links navigate to the Project's primary
      surfaces (Issues/Tickets, File Explorer/build browser, Board, Discussion) rooted in the selected
      Project — they navigate WITHIN the Project context, not to a flat/global URL.
  C4  REAL SOURCE, EXPLICIT EMPTY ON DEGRADE (AC4, FR-I3 crux): every KPI figure and Recent-Tickets row
      comes from a real 8.8a source. A card whose backing source is degraded (8.8a `{available:false}`)
      renders an EXPLICIT empty/not-configured state — NEVER a fabricated number, a hard-coded figure, or
      a zero that reads as real.
  C5  RBAC THROUGH 8.8A ONLY (AC5): the payload was already server-filtered by 8.8a's deny-by-default wall
      (§12.3). This story adds NO client-side authz predicate and NO dashboard-specific authz code path;
      it renders the pre-scoped payload as-is.
  C6  LIVE VIA EXISTING SSE BUS (AC6): tickets-by-status counters + Recent Tickets live updates come from
      SSE deltas over the EXISTING progress bus (the 8.8a delta contract, §4.4/§13). NO polling loop, NO
      new transport; a delta patches in place without a full refetch.
  C7  NO NEW DOMAIN METRIC (AC8, NFR-OBS3): this story emits only ordinary console/BFF request telemetry.
      No new metric instrument; no per-item ids (work_item.id/run.id/user.id) as metric labels; no model
      label; the token signal is 8.8e, the approval-queue signals are 8.8c/2.12.

Mutation-proof harness. Each `--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT rendering:
  --mutate=DIRECT_QUERY     re-query coord directly instead of reading 8.8a           -> C1 RED
  --mutate=NO_STATUS_BADGE  render Recent Tickets without status badges                -> C2 RED
  --mutate=GLOBAL_LINK      quick-access link not rooted in the Project context        -> C3 RED
  --mutate=FAKE_ZERO        render a fabricated zero for a degraded card               -> C4 RED
  --mutate=CLIENT_AUTHZ     add a client-side authz predicate on the payload           -> C5 RED
  --mutate=POLL_LIVE        drive live counter updates with a polling loop             -> C6 RED
  --mutate=PERITEM_LABEL    put work_item.id on a metric label                         -> C7 RED

Baseline exits 0; each --mutate exits 1 with the mapped invariant RED.
"""
import sys

TICKET_STATES = {"Backlog", "Todo", "In Progress", "In Review", "Done", "Blocked"}
QUICK_ACCESS_TARGETS = {"issues_tickets", "file_explorer", "board", "discussion"}

# the 8.8a scenario: coord + Run-state wired; metrics and SCM are NOT yet wired (normal state).
SCENARIO_88A = {
    "ticketsByStatus": {"available": True, "data": {"open": 3, "in_progress": 2, "done": 14}},
    "recentTickets": {"available": True, "data": [
        {"id": "wi-01", "title": "Wire SSE delta", "state": "In Progress", "blocked": False},
        {"id": "wi-02", "title": "Add coord schema", "state": "Done", "blocked": False},
        {"id": "wi-03", "title": "Approval gate raise", "state": "In Review", "blocked": True},
    ]},
    "tokenConsumption": {"available": False, "reason": "metrics_backend_unwired"},
    "prBoard": {"available": False, "reason": "scm_not_synced"},
    "liveRuns": {"available": True, "data": [{"runId": "r-99", "agent": "hermes", "task": "wi-01"}]},
}


def render(design, payload_88a, mut=None):
    """Return (rendered, meta) where rendered is the surface shape and meta holds structural facts."""
    # C1 — source: 8.8a payload vs direct store query.
    source = "coord_direct" if mut == "DIRECT_QUERY" else design["source"]

    # C4 — degrade behavior: explicit empty vs fabricated zero.
    fake_degrade = (mut == "FAKE_ZERO") or design.get("fake_degrade", False)

    # C5 — client-side authz predicate.
    client_authz = (mut == "CLIENT_AUTHZ") or design.get("client_authz", False)

    # C6 — live update mechanism.
    live_transport = "polling" if mut == "POLL_LIVE" else design["live_transport"]

    # C7 — metric labels.
    metric_labels = set(design["metric_labels"])
    if mut == "PERITEM_LABEL":
        metric_labels = metric_labels | {"work_item.id"}

    # build KPI cards from the 8.8a payload
    kpi_cards = {}
    for tile in ("ticketsByStatus", "tokenConsumption", "prBoard", "liveRuns"):
        sp = payload_88a.get(tile, {"available": False, "reason": "missing"})
        if sp["available"]:
            kpi_cards[tile] = {"value": sp["data"], "empty": False, "fabricated": False}
        else:
            if fake_degrade:
                kpi_cards[tile] = {"value": 0, "empty": False, "fabricated": True}
            else:
                kpi_cards[tile] = {"value": None, "empty": True, "fabricated": False}

    # build Recent Tickets from `recentTickets` sub-payload
    rt_sp = payload_88a.get("recentTickets", {"available": False})
    if rt_sp["available"]:
        tickets = [
            {"id": t["id"], "title": t["title"],
             "badge": t["state"] if (mut != "NO_STATUS_BADGE" and not design.get("no_badges")) else None,
             "blocked_overlay": t["blocked"] if (mut != "NO_STATUS_BADGE" and not design.get("no_badges")) else None}
            for t in rt_sp["data"]
        ]
        view_all = design["view_all_link"]
    else:
        tickets, view_all = [], None

    # quick-access links: Project-rooted vs global.
    link_rooting = "global" if mut == "GLOBAL_LINK" else design["link_rooting"]
    quick_links = {t: f"/{link_rooting}/{t}" for t in QUICK_ACCESS_TARGETS}

    meta = {
        "source": source, "live_transport": live_transport,
        "metric_labels": metric_labels, "client_authz": client_authz,
        "link_rooting": link_rooting,
    }
    rendered = {
        "kpi_cards": kpi_cards, "tickets": tickets, "view_all": view_all, "quick_links": quick_links,
    }
    return rendered, meta


# ---- the two designs -------------------------------------------------------------------------------
CONFORMANT = {
    "source": "88a_payload",                    # C1 — reads from 8.8a, not direct coord
    "no_badges": False,                          # C2 — status badges rendered
    "view_all_link": "/project/{id}/tickets",   # C2 — View all link present
    "link_rooting": "project/{id}",             # C3 — Project-rooted quick-access
    "fake_degrade": False,                       # C4 — degraded → explicit empty
    "client_authz": False,                       # C5 — no client-side authz
    "live_transport": "sse_existing",            # C6 — existing SSE bus
    "metric_labels": set(),                      # C7 — no per-item ids as labels
}
NAIVE = {
    "source": "coord_direct",                   # C1 fail — re-queries coord directly
    "no_badges": True,                           # C2 fail — no status badges
    "view_all_link": None,                       # C2 fail — no View all link
    "link_rooting": "global",                   # C3 fail — global URLs, not Project-rooted
    "fake_degrade": True,                        # C4 fail — fabricates a zero for degraded cards
    "client_authz": True,                        # C5 fail — client-side authz predicate
    "live_transport": "polling",                 # C6 fail — polling loop
    "metric_labels": {"work_item.id", "run.id"}, # C7 fail — per-item ids on metric labels
}


def evaluate(design, mut, payload_88a):
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    rendered, meta = render(design, payload_88a, mut=mut)

    # C1 — KPI cards read from 8.8a payload, not a direct coord/scm/metrics/Run-state query.
    check("C1", meta["source"] == "88a_payload",
          f"KPI cards sourced via {meta['source']!r} — they must read from the 8.8a sub-payloads; this "
          f"story issues NO direct coord/scm/metrics/Run-state query (8.8a is the single source of truth "
          f"and the single RBAC wall; AC1)")
    # positive control: all four KPI tiles are present in the rendered output.
    missing_kpi = sorted(k for k in ("ticketsByStatus", "tokenConsumption", "prBoard", "liveRuns")
                         if k not in rendered["kpi_cards"])
    check("C1", not missing_kpi,
          f"KPI card(s) {missing_kpi} absent from rendered output — all four must render (AC1)")

    # C2 — Recent Tickets: status badge per row + "View all" link.
    check("C2", rendered.get("view_all") is not None,
          "No 'View all' link on the Recent Tickets list — it must link into Project → Tickets (AC2/FR-I7)")
    bad_badges = [t["id"] for t in rendered["tickets"] if t.get("badge") is None]
    check("C2", not bad_badges,
          f"Recent Tickets row(s) {bad_badges} have no status badge — every row needs a work_item.state "
          f"badge (Backlog/Todo/In Progress/In Review/Done + Blocked overlay per §13 r25; AC2)")

    # C3 — quick-access links are Project-rooted (navigate within the selected Project's context).
    check("C3", meta["link_rooting"] != "global",
          f"quick-access links use {meta['link_rooting']!r} rooting — they must be Project-rooted (route "
          f"within the selected Project's context so the dashboard is the operator's entry point, AC3/FR-I8)")
    check("C3", set(rendered["quick_links"]) == QUICK_ACCESS_TARGETS,
          f"quick-access link set {set(rendered['quick_links'])} ≠ required {QUICK_ACCESS_TARGETS} (AC3/FR-I8)")

    # C4 — degraded card → explicit empty state, NEVER fabricated zero.
    faked = sorted(t for t, card in rendered["kpi_cards"].items() if card.get("fabricated"))
    check("C4", not faked,
          f"KPI card(s) {faked} render a fabricated zero for a degraded source — a degraded tile must show "
          f"an explicit 'not configured'/empty state, never a number that reads as real (AC4/FR-I3)")
    # positive control: the available cards do have real values.
    available_no_val = sorted(t for t, card in rendered["kpi_cards"].items()
                              if payload_88a.get(t, {}).get("available") and not card.get("value"))
    check("C4", not available_no_val,
          f"available KPI card(s) {available_no_val} have no rendered value — an available tile must render "
          f"its real data (non-vacuous; not an over-broad empty state, AC4)")

    # C5 — no client-side authz predicate; the payload is pre-scoped by 8.8a.
    check("C5", not meta["client_authz"],
          "this story adds a client-side authz predicate — it must NOT; the payload is already server-"
          "filtered by 8.8a's deny-by-default RBAC wall; adding a second filter risks both double-denial "
          "and a drift gap if the two filters diverge (AC5/§12.3)")

    # C6 — live updates via the existing SSE bus; no polling.
    check("C6", meta["live_transport"] == "sse_existing",
          f"live counter updates use {meta['live_transport']!r} — they must ride the EXISTING SSE progress "
          f"bus (the 8.8a delta contract, §4.4/§13, same as the Run stream); NO polling loop, NO new "
          f"transport (AC6)")

    # C7 — no per-item ids as metric labels; no new domain metric.
    FORBIDDEN = {"work_item.id", "run.id", "user.id", "principal.id", "model"}
    banned = sorted(meta["metric_labels"] & FORBIDDEN)
    check("C7", not banned,
          f"metric label(s) {banned} are per-item/model identifiers — span/exemplar only, never a metric "
          f"label (NFR-OBS3 cardinality firewall, AC8)")

    return fails


def run(mut=None):
    naive_fails = evaluate(NAIVE, None, SCENARIO_88A)
    naive_hit = {inv for inv, _ in naive_fails}
    conf_fails = evaluate(CONFORMANT, mut, SCENARIO_88A)
    return naive_fails, naive_hit, conf_fails


MUTANTS = {
    "DIRECT_QUERY": "C1", "NO_STATUS_BADGE": "C2", "GLOBAL_LINK": "C3", "FAKE_ZERO": "C4",
    "CLIENT_AUTHZ": "C5", "POLL_LIVE": "C6", "PERITEM_LABEL": "C7",
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
        print(f"[kpi] TEETH LOST — the naive panel no longer trips {missing_teeth}:")
        for inv, d in naive_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[kpi] FAIL — the §8.8b KPI/recent/quickaccess rendering violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] naive direct-query panel     : {len(naive_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(naive_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] §8.8b conformant rendering   : 0 violation(s); "
              "88a-sourced, status-badges+view-all, project-rooted-links, "
              "explicit-empty-on-degrade, no-second-authz, sse-live, bounded-cardinality")
        print("[kpi] PASS")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)})" if others else ""
        print(f"[kpi] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[kpi] SURVIVED — --mutate={mut} did NOT trip {expected}; tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
