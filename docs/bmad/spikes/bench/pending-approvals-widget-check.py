#!/usr/bin/env python3
"""Story 8.8c falsification — Pending Approvals widget (FR-I5, no-P2P, 2.12 gate).

The Pending Approvals widget lists work items with `blocked_reason=needs_approval` (a read model over the
`coord` record via 8.8a's `pendingApprovals` sub-payload), lets a write-level human approve/reject through
the 2.12 apiserver action, and SSE-updates the count. Three properties are load-bearing and non-negotiable:

  (1) The approve/reject action is OWNED BY 2.12 — the widget CALLS that action, it does NOT write to
      `coord` directly or implement its own approval mutation. The gate raise, write-level check,
      human-principal check, and viewer-403 ALL live in 2.12.
  (2) NO client path around the no-P2P guarantee (FR-B3, §13 r10): an agent can NEVER approve on a human's
      behalf; the widget must not create any path (endpoint, proxy, affordance) by which that could happen.
  (3) UI hide ≠ authorization: hiding approve/reject from a viewer is defense-in-depth, NOT the gate — the
      2.12 apiserver action MUST return 403 to a viewer even if the request is forged. Test the server, not
      just the button visibility.

Invariants (C1-C7, mapped to ACs of story 8.8c):
  C1  READ FROM 8.8A `pendingApprovals` (AC1): the widget renders the `pendingApprovals` sub-payload from
      8.8a (coord items `blocked_reason=needs_approval`). Empty state ("No pending approvals") when none;
      degraded state when 8.8a marks the sub-payload unavailable — NEVER a fabricated queue.
  C2  APPROVE/REJECT VIA 2.12 ONLY (AC2): the widget calls the 2.12 apiserver action for approve/reject;
      it does NOT write to `coord` directly or implement its own approval mutation. The decision is written
      as the human principal, provenance recorded by 2.12.
  C3  NO PATH AROUND no-P2P (AC3, FR-B3 crux): the widget introduces NO client path, proxy, or affordance
      by which an agent could resolve a gate; no outcome is pushed back to the raising agent as a message.
      The raising agent learns the outcome ONLY by reading the coordination record (2.12 AC6).
  C4  SSE-UPDATED COUNT, NO POLLING (AC4): the approval count (and the 8.8b KPI count) is SSE-updated over
      the EXISTING progress bus (8.8a/8.8f delta contract, §4.4/§13); NO polling loop.
  C5  VIEWER SEES QUEUE READ-ONLY; 403 SERVER-SIDE (AC5, defense-in-depth): a viewer sees the queue but
      the approve/reject affordance is HIDDEN (defense-in-depth — NOT the gate). The 2.12 apiserver action
      MUST return 403 to a viewer even when the affordance is bypassed. A write-level human sees and can use
      approve/reject.
  C6  REAL ROWS ONLY (AC6, FR-I3): every row is a real coord item with `blocked_reason=needs_approval`
      (via 8.8a). A degraded `pendingApprovals` sub-payload → explicit degraded/empty state, NEVER a
      fabricated queue.
  C7  NO NEW METRIC; APPROVAL METRICS ARE 2.12'S (AC7, NFR-OBS3): the widget emits only ordinary
      console/BFF request telemetry; `ksquad.approval.pending` and `ksquad.approval.decisions.total` are
      emitted by 2.12's coordination reconciler (obs §17.2), NOT here. No per-item ids as metric labels.

Mutation-proof harness:
  --mutate=DIRECT_COORD_WRITE   widget writes to coord directly, bypassing 2.12      -> C2 RED
  --mutate=AGENT_APPROVE_PATH   creates a client path an agent could invoke           -> C3 RED
  --mutate=POLL_COUNT           drives approval count via polling, not SSE            -> C4 RED
  --mutate=NO_SERVER_403        viewer approve → UI-hidden but no 403 server-side     -> C5 RED
  --mutate=FABRICATED_ROWS      fills queue with placeholder rows when source degraded -> C6 RED
  --mutate=EMIT_APPROVAL_METRIC emits ksquad.approval.pending here instead of 2.12   -> C7 RED
  --mutate=FABRICATED_QUEUE     renders queue when 8.8a marks pendingApprovals unavailable -> C1 RED

Baseline exits 0; each --mutate exits 1.
"""
import sys

# the 8.8a `pendingApprovals` sub-payload (available — there are real gates).
SCENARIO_AVAILABLE = {
    "available": True,
    "data": [
        {"id": "wi-55", "title": "Deploy to staging", "requesting_agent": "hermes", "run": "r-21",
         "age_min": 14, "blocked_reason": "needs_approval"},
        {"id": "wi-61", "title": "Merge hotfix PR", "requesting_agent": "openclaw", "run": "r-22",
         "age_min": 3, "blocked_reason": "needs_approval"},
    ]
}
# the 8.8a `pendingApprovals` sub-payload (degraded — coord not yet wired).
SCENARIO_DEGRADED = {"available": False, "reason": "coord_unavailable"}


def render_widget(design, payload, caller_role, action_target, mut=None):
    """Return (widget, server_response) for the widget + a simulated action call by caller_role."""
    source = "8.8a_payload"
    fabricated_queue = (mut == "FABRICATED_QUEUE") or design.get("fabricate_queue", False)
    fabricated_rows = (mut == "FABRICATED_ROWS") or design.get("fabricate_rows", False)
    agent_path = (mut == "AGENT_APPROVE_PATH") or design.get("agent_path", False)
    live_transport = "polling" if mut == "POLL_COUNT" else design["live_transport"]
    direct_write = (mut == "DIRECT_COORD_WRITE") or design.get("direct_write", False)
    no_server_403 = (mut == "NO_SERVER_403") or design.get("no_server_403", False)
    emit_metric = (mut == "EMIT_APPROVAL_METRIC") or design.get("emit_metric", False)
    metric_labels = set(design["metric_labels"])

    if payload["available"]:
        rows = [dict(r) for r in payload["data"]]
        if fabricated_rows:
            rows.append({"id": "wi-FAKE", "title": "Fabricated gate", "fabricated": True,
                         "blocked_reason": "needs_approval"})
    else:
        if fabricated_queue:
            rows = [{"id": "wi-FAKE2", "title": "Synthesized row", "fabricated": True}]
        else:
            rows = []

    affordance_visible = (caller_role == "write_member")
    action_mutation = "2.12_action" if not direct_write else "coord_direct"

    server_http = None
    if action_target is not None:
        is_human_write_member = caller_role == "write_member"
        if no_server_403:
            server_http = 200 if is_human_write_member else 200  # viewer let through!
        else:
            server_http = 200 if is_human_write_member else 403

    widget = {
        "rows": rows, "available": payload["available"] or fabricated_queue,
        "affordance_visible": affordance_visible, "agent_path": agent_path,
        "action_mutation": action_mutation, "live_transport": live_transport,
        "emit_metric": emit_metric, "metric_labels": metric_labels, "source": source,
    }
    return widget, server_http


CONFORMANT = {
    "fabricate_queue": False, "fabricate_rows": False,
    "direct_write": False, "agent_path": False,
    "live_transport": "sse_existing", "no_server_403": False,
    "emit_metric": False, "metric_labels": set(),
}
NAIVE = {
    "fabricate_queue": True,   # C1 fail — shows queue when sub-payload degraded
    "fabricate_rows": True,    # C6 fail — adds synthesized rows
    "direct_write": True,      # C2 fail — writes coord directly
    "agent_path": True,        # C3 fail — exposes an agent-invocable path
    "live_transport": "polling",  # C4 fail — polling loop
    "no_server_403": True,     # C5 fail — viewer not 403'd server-side
    "emit_metric": True,       # C7 fail — emits the approval metric here
    "metric_labels": {"work_item.id", "user.id"},  # C7 fail — per-item ids as labels
}


def evaluate(design, mut, payload, caller_role="write_member"):
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    # Scenario A: payload available
    widget_ok, http_write = render_widget(design, SCENARIO_AVAILABLE, "write_member",
                                          action_target="approve", mut=mut)
    # Scenario B: payload degraded
    widget_deg, _ = render_widget(design, SCENARIO_DEGRADED, "write_member",
                                  action_target=None, mut=mut)
    # Scenario C: viewer tries to approve (should 403 server-side)
    _, http_viewer = render_widget(design, SCENARIO_AVAILABLE, "viewer",
                                   action_target="approve", mut=mut)

    # C1 — reads from 8.8a `pendingApprovals`; degraded sub-payload → explicit empty, no fabricated queue.
    faked_in_deg = [r for r in widget_deg["rows"] if r.get("fabricated")]
    check("C1", not faked_in_deg and (not widget_deg["available"] or not widget_deg["rows"]),
          f"widget renders a queue when 8.8a marks pendingApprovals degraded "
          f"(available={widget_deg['available']}, fabricated_rows={[r['id'] for r in faked_in_deg]}, "
          f"rows={[r['id'] for r in widget_deg['rows']]}) — must show an explicit empty/degraded state, "
          f"NEVER a fabricated queue (AC1)")
    # positive control: with an available payload, real rows ARE rendered.
    check("C1", len(widget_ok["rows"]) == len(SCENARIO_AVAILABLE["data"]),
          f"widget rendered {len(widget_ok['rows'])} rows for {len(SCENARIO_AVAILABLE['data'])} real gates "
          f"— all real gates must appear (non-vacuous; not an over-broad empty, AC1)")

    # C2 — approve/reject calls 2.12 action, NOT a direct coord write.
    check("C2", widget_ok["action_mutation"] == "2.12_action",
          f"approve/reject uses {widget_ok['action_mutation']!r} — it must call the 2.12 apiserver action; "
          f"the widget MUST NOT write to coord directly or implement its own approval mutation (AC2)")
    check("C2", http_write == 200,
          f"write-level human approve returned HTTP {http_write} — must succeed (200) via 2.12 (AC2)")

    # C3 — no client path an agent could invoke to resolve a gate.
    check("C3", not widget_ok["agent_path"],
          "the widget exposes an agent-invocable path — no-P2P (FR-B3): an agent MUST NOT be able to "
          "resolve a gate, and no outcome is pushed back to the raising agent as a message. The raising "
          "agent learns the outcome only by reading the coord record (2.12 AC6); this widget must not "
          "undermine that (AC3)")

    # C4 — SSE-updated count, no polling.
    check("C4", widget_ok["live_transport"] == "sse_existing",
          f"approval count uses {widget_ok['live_transport']!r} for live updates — it must be SSE-updated "
          f"over the EXISTING progress bus (8.8a/8.8f delta contract, §4.4/§13); NO polling loop (AC4)")

    # C5 — viewer: approve/reject hidden in UI; 403 server-side even if forged.
    check("C5", http_viewer == 403,
          f"viewer approve returned HTTP {http_viewer} — 2.12 MUST return 403 server-side even when the "
          f"UI affordance is bypassed (UI hide is defense-in-depth, NOT the gate; AC5)")
    # positive control: write-level human's affordance is visible.
    check("C5", widget_ok["affordance_visible"],
          "approve/reject affordance not shown to write-level member — must be visible for write members "
          "(non-vacuous; not an over-broad hide, AC5)")

    # C6 — real rows only; no fabricated rows appended.
    faked = [r for r in widget_ok["rows"] if r.get("fabricated")]
    check("C6", not faked,
          f"widget contains {len(faked)} fabricated row(s) — every row must be a real coord item with "
          f"blocked_reason=needs_approval (via 8.8a); no placeholder or synthesized row (AC6/FR-I3)")

    # C7 — no approval metric emitted here; NFR-OBS3.
    check("C7", not widget_ok["emit_metric"],
          "the widget emits an approval metric (`ksquad.approval.*`) — those are emitted by 2.12's "
          "coordination reconciler (obs §17.2), NOT this widget; this story emits only ordinary "
          "request telemetry (AC7)")
    FORBIDDEN = {"work_item.id", "run.id", "user.id", "principal.id", "model"}
    banned = sorted(widget_ok["metric_labels"] & FORBIDDEN)
    check("C7", not banned,
          f"metric label(s) {banned} are per-item/model identifiers — span/exemplar only, never a metric "
          f"label (NFR-OBS3 cardinality firewall, AC7)")

    return fails


def run(mut=None):
    naive_fails = evaluate(NAIVE, None, SCENARIO_AVAILABLE)
    naive_hit = {inv for inv, _ in naive_fails}
    conf_fails = evaluate(CONFORMANT, mut, SCENARIO_AVAILABLE)
    return naive_fails, naive_hit, conf_fails


MUTANTS = {
    "FABRICATED_QUEUE": "C1", "DIRECT_COORD_WRITE": "C2", "AGENT_APPROVE_PATH": "C3",
    "POLL_COUNT": "C4", "NO_SERVER_403": "C5", "FABRICATED_ROWS": "C6", "EMIT_APPROVAL_METRIC": "C7",
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
        print(f"[appr] TEETH LOST — naive panel no longer trips {missing_teeth}:")
        for inv, d in naive_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[appr] FAIL — §8.8c Pending Approvals widget violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] naive bespoke-approval widget : {len(naive_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(naive_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] §8.8c conformant widget       : 0 violation(s); "
              "8.8a-sourced, 2.12-action-only, no-agent-path, sse-count, viewer-403-server-side, "
              "real-rows-only, no-approval-metric-here")
        print("[appr] PASS")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)})" if others else ""
        print(f"[appr] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[appr] SURVIVED — --mutate={mut} did NOT trip {expected}; tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
