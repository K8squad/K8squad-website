#!/usr/bin/env python3
"""Story 8.10 falsification — the Team-organization diagram (live squad org chart, FR-F8, arch §13 r10).

Screen: the Team org diagram (UX 09-team-org-diagram). A squad org-chart view that renders the
`Team -> Agent -> Role` hierarchy read-only from the `Team`/`Agent`/`Role` CRDs (§5.1), shows each Agent's
live status (idle / running / blocked / paused) + runtime type + role badges, streams status over the
EXISTING SSE bus, and click-through deep-links to the agent detail page (8.11).

Five properties are load-bearing and non-negotiable (arch §13 r10, §12.3 r20/r21, FR-F8):
  (1) the hierarchy is a **read-only projection of the CRDs** — GET-only, no new CRD / data source /
      backend; runtime + role badges come from real CRD fields, never a fabricated node;
  (2) it is served through the **SAME deny-by-default RBAC wall** every other read model uses, **`Team`-
      scoped** — a caller with no membership gets the not-found/deny shape (existence-hiding), never a
      partial org chart; there is **no org-diagram-specific authz path**;
  (3) each Agent's status is **DERIVED** from Run/claim state — its current `Run.status.phase` (§5.2) + the
      `Paused` condition (Epic 7.4) — **not** a stored status column and **not** an agent self-reported value;
  (4) it is **coordination-free** — no mutate/claim/reassign/transition affordance anywhere (no-P2P applied
      to the console; R6: this is a legibility surface, NOT the compose/edit view 8.5), and node click-through
      is a **navigation** (a URL to the agent-detail route), never a coordination/dispatch action;
  (5) status updates ride the **EXISTING SSE bus** (same EventSource + BFF proxy as the Run stream 8.2) as
      per-Agent deltas — no polling loop, no new transport; and telemetry adds **no new domain metric** and
      keeps per-item ids (`agent`/`run.id`/`user.id`/`work_item.id`/`model`) off every metric label (NFR-OBS3).

This is a MODEL/differential check (a sibling of dashboard-aggregation-check.py and live-runs-panel-sse-
check.py), stdlib-only, `python3` it directly — no console, no live cluster (CRDs + memberships + Run state
fed by fixtures). It first proves the anti-pattern — an "editable org console" (its own authz path that
leaks to a non-member, a fabricated non-CRD node source, status read from a stored/self-reported field,
a claim/reassign button hung on every node, a click that dispatches a Run instead of navigating, a polling
loop instead of the SSE bus, and per-Agent metric labels) — is DETECTED as violating every invariant (real
teeth), then proves the §13 r10 read-model org diagram violates nothing and actually returns the member a
`Team`-scoped, CRD-sourced hierarchy with derived per-Agent status, denying the non-member, exposing no
mutate affordance, navigating (not dispatching) on click, over the existing SSE bus, with per-item ids off
every metric label.

Invariants (C1-C7, each mapped to an AC of story 8.10):
  C1  READ-ONLY CRD PROJECTION (AC1): the `Team->Agent->Role` hierarchy + runtime type + role badges are a
      read-only projection of the `Team`/`Agent`/`Role` CRDs (§5.1). GET-only (every mutating verb
      structurally absent); node data provenanced to the real CRD source; NO new CRD / data source / backend.
  C2  THE ONE DENY-BY-DEFAULT RBAC WALL, TEAM-SCOPED (AC2, the security crux): served through the SAME shared
      deny-by-default middleware every read model uses — NO org-diagram-specific authz path. A caller with no
      Team membership gets the not-found/deny shape (existence-hiding), NEVER a partial org chart; a member
      gets the scoped hierarchy.
  C3  STATUS IS DERIVED, NOT STORED (AC3, FR-I3 provenance): each Agent's status in {idle,running,blocked,
      paused} is DERIVED from its `Run.status.phase` (§5.2) + `Paused` condition (7.4) — a projection of
      Run/claim state, NOT a stored status column and NOT an agent self-report. No active Run -> `idle`.
  C4  COORDINATION-FREE (AC4, no-P2P + R6): NO mutate/claim/reassign/transition affordance anywhere — read +
      navigate only (the §13 r10 org-diagram precedent). It is NOT the compose/edit view (that stays 8.5).
  C5  DEEP-LINK IS NAVIGATION, NOT DISPATCH (AC5): a node click deep-links to the agent detail page (8.11) via
      a URL navigation — it does NOT claim, dispatch, reassign, or transition anything.
  C6  LIVE OVER THE EXISTING SSE BUS (AC6): status updates ride the existing SSE progress bus (same
      EventSource + BFF proxy as the Run stream 8.2) as per-Agent DELTAS — NO new transport, NO polling loop,
      NO new backend. A delta names the changed Agent so the client patches that node without a full refetch.
  C7  CARDINALITY FIREWALL + NO NEW METRIC (AC7, NFR-OBS3): the diagram emits NO new domain metric; per-item
      ids (`agent`/`run.id`/`work_item.id`/`user.id`) are NEVER metric labels and there is NO `model` label.
      The org chart is legibility, never a consumption axis.

Mutation-proof harness (no vacuous guard — the ISI-2346-F1 class is excluded by construction). Each
`--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT read model; the check then goes RED with the
mapped invariant failing:
  --mutate=FAKE_HIERARCHY    source a node from a fabricated (non-CRD) source        -> C1 RED
  --mutate=BESPOKE_AUTHZ     an org-diagram-specific authz path that leaks non-member -> C2 RED
  --mutate=STORED_STATUS     read status from a stored/self-reported field, not Run    -> C3 RED
  --mutate=CLAIM_AFFORDANCE  hang a claim/reassign button on every node                -> C4 RED
  --mutate=MUTATE_DEEPLINK   node click dispatches a Run instead of navigating         -> C5 RED
  --mutate=POLL_TRANSPORT    drive status with a polling loop, not the SSE bus         -> C6 RED
  --mutate=PERITEM_LABEL     put `agent` on an org-diagram metric label                -> C7 RED

Baseline `python3 team-org-diagram-check.py` exits 0; each `--mutate=NAME` exits 1 with the mapped violation.
The check exits non-zero if the editable-org-console model STOPS violating (teeth lost), if the read-model
org diagram EVER violates an invariant, or if it fails to actually return the member a Team-scoped CRD-sourced
hierarchy with derived status while denying the non-member.

Runtime proof (owned elsewhere). The real CRD read projection through the BFF, the live per-membership
`Team`-scoped RBAC on the Go apiserver, the SSE per-Agent delta stream, and the derived-status computation
over the actual Run/claim + `Paused` state are exercised by the console E2E and the apiserver read-model
tests. This model check guards the CONSTRUCTION-TIME contract — 8.10's crux and exactly what FR-F8 + §13 r10
asked: one `Team`-scoped, CRD-sourced, derived-status, coordination-free, navigate-only, existing-SSE org
diagram.
"""
import sys

# ---- the Team's agents, each with its real CRD lineage + the Run/claim state its status derives from ----
# hierarchy is a read-only projection of the Team/Agent/Role CRDs (§5.1); status is DERIVED from the Agent's
# current Run.status.phase (§5.2) + Paused condition (7.4). `runstate` is the fixture Run/claim signal, NOT a
# stored field on the Agent — the conformant path derives the status chip from it (C3).
AGENTS = {
    "planner":  {"role": "coordinator", "runtime": "claude",   "runstate": "running"},   # active Run, running
    "builder":  {"role": "engineer",    "runtime": "opencode",  "runstate": "paused"},    # Paused condition set
    "reviewer": {"role": "reviewer",    "runtime": "hermes",    "runstate": "blocked"},   # Run blocked/awaiting
    "scout":    {"role": "researcher",  "runtime": "claude",    "runstate": "none"},      # no active Run -> idle
}
ALL_AGENTS = set(AGENTS)

# the DERIVATION: Run/claim state -> status chip. This is the single source of a node's status (C3). A stored
# status column or an agent self-report is exactly what AC3 forbids.
def derive_status(runstate):
    return {"running": "running", "paused": "paused", "blocked": "blocked", "none": "idle"}[runstate]

VALID_STATUSES = {"idle", "running", "blocked", "paused"}

# agents that changed state while the diagram is open -> the per-Agent SSE delta contract (C6).
LIVE_DELTA_AGENTS = {"planner", "builder", "reviewer"}

# per-item identifiers that must NEVER become a metric label (span/log/exemplar only) — NFR-OBS3 (C7).
FORBIDDEN_METRIC_LABELS = {"agent", "run.id", "work_item.id", "user.id", "principal.id", "model"}

# the Team's members (viewer+). A caller outside this set has NO membership -> the not-found/deny shape.
TEAM_MEMBERS = {"sam", "dana"}


# ---- the composition: BFF projects the org diagram per request over the existing CRDs + Run state ---------
#
# `compose(design, caller, mut)` -> (view, meta). `view` is None (deny shape) for a non-member; otherwise a
# dict of agent -> node `{role, runtime, status, status_source, click}`. `meta` carries the structural facts
# the invariants assert over (verbs, rbac wall, source, affordances, transport, telemetry). `mut` names the
# single injected defect.
def compose(design, caller, mut=None):
    is_member = caller in TEAM_MEMBERS

    # C2 — the ONE deny-by-default wall, Team-scoped. Conformant: the shared middleware denies a non-member
    # (existence-hiding). BESPOKE_AUTHZ swaps in an org-diagram-only path that fails OPEN and leaks the chart.
    wall = "bespoke_orgdiagram" if mut == "BESPOKE_AUTHZ" else design["rbac_wall"]
    leaks_nonmember = (mut == "BESPOKE_AUTHZ") or design.get("authz_fail_open")
    admit = is_member or leaks_nonmember
    if not admit:
        return None, _meta(design, mut, http=404, admitted=False, wall=wall)

    view = {}
    for agent, crd in AGENTS.items():
        # C1 — read-only CRD projection. FAKE_HIERARCHY sources one node from a fabricated (non-CRD) source.
        node_source = "fabricated" if (mut == "FAKE_HIERARCHY" and agent == "scout") else "crd"

        # C3 — status DERIVED from Run/claim state. A stored/self-reported field is the defect: either the
        # design reads status from a stored column (the editable-console anti-pattern) or STORED_STATUS injects
        # one stale stored value into the conformant path.
        if design.get("status_source") == "stored_field" or (mut == "STORED_STATUS" and agent == "builder"):
            status, status_source = "running", "stored_field"   # a stale stored column contradicting the Run
        else:
            status, status_source = derive_status(crd["runstate"]), "runstate_derived"

        # C5 — click-through is a URL navigation to the agent detail page (8.11). The defect DISPATCHES a Run
        # instead: either the design makes every click a dispatch (anti-pattern) or MUTATE_DEEPLINK injects one.
        if design.get("click_kind") == "dispatch_run" or (mut == "MUTATE_DEEPLINK" and agent == "planner"):
            click = {"kind": "dispatch_run", "target": agent}
        else:
            click = {"kind": "navigate", "target": f"/agents/{agent}"}

        view[agent] = {
            "role": crd["role"], "runtime": crd["runtime"],
            "status": status, "status_source": status_source, "node_source": node_source, "click": click,
        }

    return view, _meta(design, mut, http=200, admitted=True, wall=wall)


def _meta(design, mut, http, admitted, wall):
    # C1 — GET-only read projection; NO new CRD / data source / backend.
    verbs = set(design["verbs"])
    if mut == "FAKE_HIERARCHY":
        verbs = verbs  # FAKE_HIERARCHY is a source defect, not a verb defect (kept orthogonal)
    new_backend = design.get("new_backend", False)

    # C4 — coordination-free. CLAIM_AFFORDANCE hangs a claim/reassign button on every node.
    affordances = set(design["affordances"])
    if mut == "CLAIM_AFFORDANCE":
        affordances = affordances | {"claim", "reassign"}

    # C6 — live over the existing SSE bus. POLL_TRANSPORT introduces a polling loop and drops the delta
    # contract; the conformant path names a per-Agent delta consistent with the snapshot.
    if mut == "POLL_TRANSPORT" or design.get("transport") == "new_polling_loop":
        transport, delta_contract = "new_polling_loop", {}
    else:
        transport = design["transport"]
        delta_contract = {a: {"agent": a, "patch": "status"} for a in LIVE_DELTA_AGENTS}

    # C7 — cardinality firewall. PERITEM_LABEL puts `agent` on a metric label; the editable console also
    # emits a NEW per-Agent status counter.
    metric_labels = set(design["metric_labels"])
    if mut == "PERITEM_LABEL":
        metric_labels = metric_labels | {"agent"}
    new_domain_metric = design.get("new_domain_metric", False)

    return {
        "http": http, "admitted": admitted, "wall": wall, "verbs": verbs,
        "new_backend": new_backend, "affordances": affordances,
        "transport": transport, "delta_contract": delta_contract,
        "metric_labels": metric_labels, "new_domain_metric": new_domain_metric,
    }


# ---- the two designs -------------------------------------------------------------------------------------
CONFORMANT = {
    "verbs": {"GET"},                       # C1 — GET-only read projection
    "new_backend": False,                   # C1 — no new CRD / data source / backend
    "rbac_wall": "deny_by_default_shared",  # C2 — the ONE shared wall, Team-scoped, no org-specific path
    "affordances": {"navigate"},            # C4 — read + navigate only; no mutate/claim/reassign
    "transport": "sse_delta_existing",      # C6 — per-Agent deltas over the existing SSE bus
    "metric_labels": {"team.id"},           # C7 — one bounded scope label
    "new_domain_metric": False,             # C7 — no new domain metric (org chart is legibility)
}
EDITABLE_CONSOLE = {
    "verbs": {"GET", "POST", "PATCH"},      # C1 fail — mutating verbs on the surface
    "new_backend": True,                    # C1 fail — a new org/status backend + store
    "rbac_wall": "bespoke_orgdiagram",      # C2 fail — its own authz path...
    "authz_fail_open": True,                # C2 fail — ...that leaks the chart to a non-member
    "status_source": "stored_field",        # C3 fail — status read from a stored/self-reported column, not Run
    "click_kind": "dispatch_run",           # C5 fail — a node click dispatches a Run instead of navigating
    "affordances": {"navigate", "claim", "reassign", "transition"},  # C4 fail — mutate/claim affordances
    "transport": "new_polling_loop",        # C6 fail — a polling loop, not the SSE bus
    "metric_labels": {"team.id", "agent", "model"},  # C7 fail — per-item + model metric labels
    "new_domain_metric": True,              # C7 fail — a new per-Agent status counter
}


# ---- the runnable check ----------------------------------------------------------------------------------
def evaluate(design, mut):
    """Return the list of (invariant, detail) violations for `design`, composed for member + non-member."""
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    MEMBER, NONMEMBER = "sam", "mallory"
    view, meta = compose(design, MEMBER, mut=mut)

    # C1 — read-only CRD projection; GET-only; no new backend; every node provenanced to the CRD source.
    check("C1", meta["verbs"] == {"GET"},
          f"org-diagram endpoint exposes {sorted(meta['verbs'])} — it is a read projection of the CRDs; every "
          f"mutating verb must be structurally absent (GET-only, AC1)")
    check("C1", not meta["new_backend"],
          "org diagram stands up a new CRD / data source / backend — FR-F8/§13 r10 forbid it: the hierarchy is "
          "a read-only projection of the existing Team/Agent/Role CRDs (AC1)")
    check("C1", view is not None and ALL_AGENTS <= set(view),
          f"projected view is missing agents {sorted(ALL_AGENTS - set(view or {}))} — it must render the whole "
          f"Team->Agent->Role hierarchy from the CRDs (AC1)")
    if view is not None:
        faked = sorted(a for a, n in view.items() if n["node_source"] != "crd")
        check("C1", not faked,
              f"agent node(s) {faked} are sourced from a fabricated (non-CRD) source — every node (hierarchy, "
              f"runtime type, role badge) must project from the real Team/Agent/Role CRDs (AC1)")
        missing_badges = sorted(a for a, n in view.items() if not n.get("role") or not n.get("runtime"))
        check("C1", not missing_badges,
              f"agent node(s) {missing_badges} lack a role and/or runtime badge — each node must carry its CRD "
              f"role badge + runtime type (AgentRuntime §5.3) (AC1)")

    # C2 — the ONE shared deny-by-default wall; Team-scoped; non-member denied, member admitted.
    check("C2", meta["wall"] == "deny_by_default_shared",
          f"diagram built through a {meta['wall']!r} authz path — it must route through the SAME shared "
          f"deny-by-default middleware every read model uses; no org-diagram-specific authz path (AC2/§12.3)")
    deny_view, deny_meta = compose(design, NONMEMBER, mut=mut)
    check("C2", deny_view is None and deny_meta["http"] == 404,
          f"non-member {NONMEMBER!r} received {'a populated org chart' if deny_view else 'no view'} "
          f"(http {deny_meta['http']}) — a caller with no Team membership must get the not-found/deny shape, "
          f"never a partial org chart (AC2 existence-hiding)")
    # positive control (non-vacuous): the MEMBER is admitted with a real Team-scoped view, not denied to nothing.
    check("C2", view is not None and meta["admitted"],
          f"member {MEMBER!r} was denied — the shared wall must ADMIT a member's Team-scoped org chart "
          f"(non-vacuous; not an over-broad deny)")

    # C3 — status DERIVED from Run/claim state; valid status set; no stored/self-reported field.
    if view is not None:
        stored = sorted(a for a, n in view.items() if n["status_source"] != "runstate_derived")
        check("C3", not stored,
              f"agent(s) {stored} have status from a non-derived source (stored column / self-report) — status "
              f"must be DERIVED from Run.status.phase (§5.2) + Paused (7.4), never stored/self-reported (AC3)")
        bad_status = sorted(a for a, n in view.items() if n["status"] not in VALID_STATUSES)
        check("C3", not bad_status,
              f"agent(s) {bad_status} carry a status outside {sorted(VALID_STATUSES)} (AC3)")
        # non-vacuous derivation control: each fixture Run-state derives to the expected chip (idle when no Run).
        wrong = sorted(a for a, n in view.items() if n["status"] != derive_status(AGENTS[a]["runstate"]))
        check("C3", not wrong,
              f"agent(s) {wrong} render a status that does not match the derivation of their Run/claim state "
              f"(e.g. an Agent with no active Run must render `idle`) — status must track the derivation (AC3)")

    # C4 — coordination-free: read + navigate only; no mutate/claim/reassign/transition affordance.
    illegal_aff = sorted(meta["affordances"] & {"claim", "reassign", "transition", "kill", "dispatch"})
    check("C4", not illegal_aff,
          f"the diagram exposes coordination affordance(s) {illegal_aff} — it must be read + navigate ONLY "
          f"(no-P2P on the console, §13 r10); this is a legibility surface, not the compose/edit view 8.5 (AC4)")

    # C5 — click-through is a URL navigation to the agent detail page, never a dispatch/coordination action.
    if view is not None:
        dispatching = sorted(a for a, n in view.items() if n["click"]["kind"] != "navigate")
        check("C5", not dispatching,
              f"agent node(s) {dispatching} click-through DISPATCHES instead of navigating — the click must "
              f"deep-link (a URL) to the agent detail page (8.11), never claim/dispatch/transition (AC5)")

    # C6 — live over the existing SSE bus: per-Agent delta contract; no polling loop / new transport.
    check("C6", meta["transport"] == "sse_delta_existing",
          f"status updates use {meta['transport']!r} — they must ride the existing SSE progress bus (same "
          f"EventSource + BFF proxy as the Run stream 8.2); no new transport, no polling loop (AC6)")
    missing_delta = sorted(LIVE_DELTA_AGENTS - set(meta["delta_contract"]))
    check("C6", not missing_delta,
          f"live agent(s) {missing_delta} have no SSE delta contract — each status change needs a per-Agent "
          f"{{agent, patch}} delta so a client patches the node without a full refetch (AC6)")

    # C7 — cardinality firewall: bounded metric labels only; no per-item id label; no new domain metric.
    banned = sorted(meta["metric_labels"] & FORBIDDEN_METRIC_LABELS)
    check("C7", not banned,
          f"metric label(s) {banned} are per-item/model identifiers — they are span/exemplar only, never a "
          f"metric label (NFR-OBS3 cardinality firewall, AC7)")
    check("C7", not meta["new_domain_metric"],
          "the org diagram emits a new domain metric — it must not: the org chart is legibility telemetry, "
          "never a consumption axis; only ordinary request/stream telemetry (AC7/§17)")

    return fails


def run(mut=None):
    edit_fails = evaluate(EDITABLE_CONSOLE, None)          # teeth
    edit_hit = {inv for inv, _ in edit_fails}
    conf_fails = evaluate(CONFORMANT, mut)                 # baseline or single injected defect
    return edit_fails, edit_hit, conf_fails


MUTANTS = {
    "FAKE_HIERARCHY": "C1", "BESPOKE_AUTHZ": "C2", "STORED_STATUS": "C3", "CLAIM_AFFORDANCE": "C4",
    "MUTATE_DEEPLINK": "C5", "POLL_TRANSPORT": "C6", "PERITEM_LABEL": "C7",
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

    edit_fails, edit_hit, conf_fails = run(mut=mut)

    # teeth gate: the editable-org-console model must trip every invariant, always.
    missing_teeth = [inv for inv in ALL_INV if inv not in edit_hit]
    if missing_teeth:
        print(f"[org] TEETH LOST — the editable-org-console model no longer trips {missing_teeth}:")
        for inv, d in edit_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[org] FAIL — the §13 r10 org-diagram read model violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] editable-org-console model  : {len(edit_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(edit_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] §13 r10 org-diagram read model: 0 violation(s); "
              "GET-only CRD-projection, one-shared-wall Team-scoped, derived-status, coordination-free, "
              "navigate-only, sse-delta, bounded-cardinality")
        print("[org] PASS — the editable-org-console model detectably breaks every invariant; the §13 r10\n"
              "      org diagram holds C1-C7 ... and actually returns the member a Team-scoped CRD-sourced\n"
              "      Team->Agent->Role hierarchy with derived per-Agent status, denying the non-member,\n"
              "      exposing no mutate affordance, navigating (not dispatching) on click, over the existing\n"
              "      SSE bus, with per-item ids off every metric label.")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)} — acceptable, {expected} is the mapped tooth)" if others else ""
        print(f"[org] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[org] SURVIVED — --mutate={mut} did NOT trip {expected} (VACUOUS GUARD); "
          f"tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
