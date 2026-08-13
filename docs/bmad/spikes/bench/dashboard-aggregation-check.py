#!/usr/bin/env python3
"""Story 8.8a falsification — the Per-Project dashboard data-aggregation read model (FR-I1/I3/I7, ADR-020).

Screen: the Project Dashboard. This story composes **the ONE payload** every dashboard tile renders from —
8.8b (KPI/recent tickets), 8.8c (pending approvals), 8.8d (PR mini-board), 8.8e (token+trend), 8.8f (live
Runs) are all "render sub-payload X" over this single composed endpoint:

    GET /api/projects/{projectId}/dashboard

Two properties are load-bearing and non-negotiable (arch §13 r24 / §12.3 r21, ADR-020):
  (1) the payload is **server-filtered through the SAME deny-by-default RBAC wall** every other console read
      model (discussion room, build browser, org diagram) uses — there is **no dashboard-specific authz
      path**, and a caller with no membership gets the Project-not-found/deny shape, never a partial payload;
  (2) each source is queried **independently** so an unavailable source **degrades only its own tile** to an
      explicit `{available:false, reason}` marker — the endpoint returns `200` with a partial-but-honest
      payload, **never** a `5xx` because one backend (metrics, SCM) is unwired. A dashboard that hard-fails
      because one source is down is a **regression**, not a cosmetic bug.
And ADR-020 forbids the tempting anti-pattern outright: **no aggregation service, no rollup datastore, no
billing store** — the BFF composes one payload per request over the stores that already exist (`coord`,
`scm_pr_mirror`, the metrics query seam, Run/claim state); the compose path is a **read** (zero writes); and
it emits **no new domain metric** (dashboard read volume is legibility telemetry, never a consumption axis,
and per-item ids never become metric labels — NFR-OBS3).

This is a MODEL/differential check (a sibling of credential-auth-state-check.py and live-run-sse-check.py),
stdlib-only, `python3` it directly — **no console, no live cluster** (sources + memberships fed by fixtures).
It first proves the ADR-020 **anti-pattern** — a "dashboard rollup service" (its own bespoke authz path,
pre-aggregates into a rollup table it writes, hard-fails the whole dashboard `5xx` when one source is down,
fills tiles from agent self-reported numbers, drives updates with a new polling loop, and emits per-Run token
counters with `run.id`/`model` metric labels) — is **DETECTED as violating every invariant** (real teeth),
then proves the §13/ADR-020 read-model composition violates nothing and **actually returns the owner a
partial-but-honest `200` payload — one degraded tile, every other tile fully populated — server-filtered to
their memberships, denying the non-member, writing nothing, over the existing SSE bus, with per-item ids off
every metric label.**

Invariants (C1-C7, each mapped to an AC of story 8.8a):
  C1  ONE COMPOSED, GET-ONLY READ MODEL (AC1): a single endpoint returns one composed payload shaped as
      INDEPENDENT per-tile sub-payloads (ticketsByStatus, recentTickets, throughput, prBoard,
      tokenConsumption, liveRuns, pendingApprovals), each in its own `{available, reason?, data}` envelope so
      a consumer renders any tile alone. GET-only; every mutating verb is structurally absent (405/route
      absent).
  C2  THE ONE DENY-BY-DEFAULT RBAC WALL (AC2, the security crux): the payload is server-filtered through the
      SAME shared deny-by-default middleware every other read model uses — NO dashboard-specific authz path.
      A caller with no membership gets the Project-not-found/deny shape (existence-hiding), NEVER a
      partially-populated payload; a member gets the scoped read payload.
  C3  EVERY SOURCE IS A REAL SOURCE (AC3, FR-I3): each sub-payload is derived from the real source named for
      it (coord audit / scm_pr_mirror / metrics seam / Run-claim state) — NO placeholder, NO hard-coded
      figure, NO agent-self-reported number. A tile with no wired source returns an explicit empty/
      not-configured marker (C4), never a fabricated value.
  C4  PER-TILE INDEPENDENT DEGRADATION (AC4, the availability crux): when one source is unavailable, ONLY
      that tile degrades to `{available:false, reason}` — every OTHER tile is composed and returned normally,
      and the endpoint returns HTTP 200 (a partial-but-honest payload), NEVER 5xx because one source is down.
  C5  READ MODEL, NOT A SERVICE TIER (AC5, ADR-020 / R6): composed in the request path over existing stores —
      NO new aggregation microservice, NO materialized rollup table, NO billing/usage datastore; and the
      compose path is a READ — zero INSERT/UPDATE/DELETE against any store.
  C6  LIVE OVER THE EXISTING SSE BUS (AC6): the endpoint returns the initial snapshot and expresses live
      updates as DELTAS over the existing SSE progress bus (the same EventSource + BFF proxy as the Run
      stream) — NO new transport, NO polling loop. Each delta names {tile, patch} consistent with the
      snapshot so a client applies it without a full refetch.
  C7  CARDINALITY FIREWALL (AC7/AC8, NFR-OBS3): telemetry is span-only + bounded — `project.id` is the only
      scope label; `run.id`/`work_item.id`/`user.id`/`model` are NEVER metric labels; and this story emits NO
      new domain metric (the token signal is 8.8e, the approval-queue signals are 8.8c/2.12). Dashboard read
      volume is legibility telemetry, never a consumption/billing axis.

Mutation-proof harness (no vacuous guard — the ISI-2346-F1 class is excluded by construction). Each
`--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT read model; the check then goes RED with the
mapped invariant failing:
  --mutate=MUTATING_VERB   hang a mutating verb on the dashboard endpoint       -> C1 RED
  --mutate=BESPOKE_AUTHZ   a dashboard-specific authz path that leaks non-member -> C2 RED
  --mutate=FABRICATED_TILE fill a tile from an agent self-reported number        -> C3 RED
  --mutate=WHOLE_FAIL      one source down -> whole dashboard 5xx (not per-tile)  -> C4 RED
  --mutate=ROLLUP_STORE    pre-aggregate into a new rollup table it writes        -> C5 RED
  --mutate=POLL_TRANSPORT  drive live tiles with a new polling loop, not SSE      -> C6 RED
  --mutate=PERITEM_LABEL   put run.id on a dashboard metric label                 -> C7 RED

Baseline `python3 dashboard-aggregation-check.py` exits 0; each `--mutate=NAME` exits 1 with the mapped
violation. The check exits non-zero if the rollup-service model STOPS violating (teeth lost), if the
read-model composition EVER violates an invariant, or if it fails to actually return the member a
partial-but-honest 200 payload (one tile degraded, the rest populated) while denying the non-member.

Runtime proof (owned elsewhere). The real GET-through-BFF, the live per-membership RBAC scoping on the Go
apiserver, and the SSE delta stream are exercised by the console E2E and the apiserver `dashboard`-package
tests (Task 4 degradation + Task 2 RBAC scoping) on the actual coord/scm/metrics/Run stores. This model check
guards the **construction-time contract** — 8.8a's crux and exactly what FR-I1/I3/I7 + ADR-020 asked: one
RBAC-filtered, per-tile-degrading, write-free, no-new-store composed payload the five tile stories render.
"""
import sys

# ---- the seven per-tile sub-payloads and their real source-of-record (AC3) -------------------------
# ticketsByStatus/recentTickets/throughput/pendingApprovals <- coord audit (§6.5/§6.1); prBoard <-
# scm_pr_mirror (§5.4); tokenConsumption <- metrics query seam (§17.2); liveRuns <- Run/claim state (§6/§8).
TILE_SOURCE = {
    "ticketsByStatus": "coord",
    "recentTickets": "coord",
    "throughput": "coord",
    "pendingApprovals": "coord",
    "prBoard": "scm",
    "tokenConsumption": "metrics",
    "liveRuns": "runstate",
}
ALL_TILES = set(TILE_SOURCE)

# the tiles that update live (KPI counters, live Runs, approval count) — they carry an SSE delta contract
# consistent with the snapshot (8.8f/8.8c fill the stream; 8.8a pins the contract). AC6.
LIVE_TILES = {"ticketsByStatus", "liveRuns", "pendingApprovals"}

# per-item identifiers that must NEVER become a metric label (span/log/exemplar only) — NFR-OBS3. AC8.
FORBIDDEN_METRIC_LABELS = {"run.id", "work_item.id", "user.id", "principal.id", "model"}

# the Project's members (viewer+). A caller outside this set has NO membership -> the deny/not-found shape.
PROJECT_MEMBERS = {"sam", "dana"}

# the standard scenario: coord/scm/Run-state wired; the metrics backend (Epic 13.4) NOT yet wired. This is a
# NORMAL operating state, not a failure — it is exactly what AC4 exists to handle (tokenConsumption degrades,
# every other tile populates, HTTP 200).
SCENARIO = {"coord": True, "scm": True, "runstate": True, "metrics": False}


# ---- the composition: BFF composes one payload per request over the existing stores (the executable spec) -
#
# `compose(design, caller, sources, mut)` -> (payload, meta). `payload` is None (deny shape) for a non-member;
# otherwise a dict of tile -> `{available, reason?, data}`. `meta` carries the structural facts the invariants
# assert over (verbs, rbac wall, tier, writes, transport, telemetry). `mut` names the single injected defect.
def compose(design, caller, sources, mut=None):
    is_member = caller in PROJECT_MEMBERS

    # C2 — the ONE deny-by-default wall. The conformant path routes every source query through the SAME
    # shared middleware; a non-member is denied (existence-hiding). BESPOKE_AUTHZ swaps in a dashboard-only
    # authz path that fails OPEN — it leaks the payload to a non-member.
    wall = "bespoke_dashboard" if mut == "BESPOKE_AUTHZ" else design["rbac_wall"]
    leaks_nonmember = (mut == "BESPOKE_AUTHZ") or design.get("authz_fail_open")
    admit = is_member or leaks_nonmember
    if not admit:
        return None, _meta(design, mut, http=404, admitted=False, wall=wall)

    # C4 — degradation mode. Conformant: each source queried independently, a down source degrades ONLY its
    # tile, HTTP 200. WHOLE_FAIL: any source down takes the whole dashboard 5xx.
    degrade = "whole" if mut == "WHOLE_FAIL" else design["degrade"]
    any_down = not all(sources.get(TILE_SOURCE[t], True) for t in ALL_TILES)
    whole_failed = degrade == "whole" and any_down
    http = 500 if whole_failed else 200

    payload = {}
    for tile, src in TILE_SOURCE.items():
        available = sources.get(src, True)
        if whole_failed:
            # the anti-pattern: one source down -> the WHOLE dashboard is unavailable.
            payload[tile] = {"available": False, "reason": "dashboard_unavailable"}
            continue
        if not available:
            # C4 conformant degrade: an explicit, honest per-tile marker — never a fabricated value (C3).
            payload[tile] = {"available": False, "reason": f"{src}_unavailable"}
            continue
        # C3 — real provenance. FABRICATED_TILE stamps one tile with an agent self-reported number.
        prov = "agent_self_report" if (mut == "FABRICATED_TILE" and tile == "throughput") else src
        payload[tile] = {"available": True, "data": {"provenance": prov}}

    return payload, _meta(design, mut, http=http, admitted=True, wall=wall)


def _meta(design, mut, http, admitted, wall):
    # C1 — GET-only. MUTATING_VERB hangs a mutating verb on the dashboard endpoint.
    verbs = set(design["verbs"])
    if mut == "MUTATING_VERB":
        verbs = verbs | {"POST"}

    # C5 — read model, not a service tier. ROLLUP_STORE stands up a rollup table + writes to it.
    tier = "aggregation_service" if mut == "ROLLUP_STORE" else design["tier"]
    writes = design["writes"] + (3 if mut == "ROLLUP_STORE" else 0)
    new_store = design.get("new_store", False) or mut == "ROLLUP_STORE"

    # C6 — live over the existing SSE bus. POLL_TRANSPORT introduces a polling loop and drops the delta
    # contract; the conformant path names a {tile, patch} delta for every live tile, consistent with the snap.
    if mut == "POLL_TRANSPORT" or design.get("transport") == "new_polling_loop":
        transport, delta_contract = "new_polling_loop", {}
    else:
        transport = design["transport"]
        delta_contract = {t: {"tile": t, "patch": f"{t}.data"} for t in LIVE_TILES}

    # C7 — cardinality firewall. Conformant metric labels are the single bounded scope label. PERITEM_LABEL
    # puts run.id on a metric label; the naive rollup also emits a NEW per-Run token counter.
    metric_labels = set(design["metric_labels"])
    if mut == "PERITEM_LABEL":
        metric_labels = metric_labels | {"run.id"}
    new_domain_metric = design.get("new_domain_metric", False)

    return {
        "http": http, "admitted": admitted, "wall": wall, "verbs": verbs,
        "source_kind": design["source_kind"], "tier": tier, "writes": writes, "new_store": new_store,
        "transport": transport, "delta_contract": delta_contract,
        "metric_labels": metric_labels, "new_domain_metric": new_domain_metric,
    }


# ---- the two designs -------------------------------------------------------------------------------
CONFORMANT = {
    "verbs": {"GET"},                       # C1 — GET-only read model
    "rbac_wall": "deny_by_default_shared",  # C2 — the ONE shared wall, no dashboard-specific path
    "source_kind": "real",                  # C3 — every tile from its real source
    "degrade": "per_tile",                  # C4 — one source down degrades only its tile, HTTP 200
    "tier": "read_model_request_path",      # C5 — composed in-request over existing stores
    "writes": 0,                            # C5 — the compose path is a read; zero writes
    "transport": "sse_delta_existing",      # C6 — snapshot + deltas over the existing SSE bus
    "metric_labels": {"project.id"},        # C7 — one bounded scope label
    "new_domain_metric": False,             # C7 — no new domain metric here (token=8.8e, approvals=8.8c/2.12)
}
ROLLUP = {
    "verbs": {"GET", "POST", "DELETE"},     # C1 fail — mutating verbs on the surface
    "rbac_wall": "bespoke_dashboard",       # C2 fail — its own authz path...
    "authz_fail_open": True,                # C2 fail — ...that leaks to a non-member
    "source_kind": "self_report",           # C3 fail — tiles from agent self-reported numbers
    "degrade": "whole",                     # C4 fail — one source down -> whole dashboard 5xx
    "tier": "aggregation_service",          # C5 fail — a new pre-aggregating service tier...
    "writes": 5,                            # C5 fail — ...that writes a rollup table
    "new_store": True,                      # C5 fail — a materialized rollup/billing datastore
    "transport": "new_polling_loop",        # C6 fail — a new polling loop, not the SSE bus
    "metric_labels": {"project.id", "run.id", "model"},  # C7 fail — per-item + model metric labels
    "new_domain_metric": True,              # C7 fail — emits a new per-Run token counter here
}


# ---- the runnable check ----------------------------------------------------------------------------
def evaluate(design, mut, sources):
    """Return the list of (invariant, detail) violations for `design`, composed for member + non-member."""
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    MEMBER, NONMEMBER = "sam", "mallory"
    payload, meta = compose(design, MEMBER, sources, mut=mut)

    # C1 — one composed, GET-only read model shaped as independent per-tile envelopes.
    check("C1", meta["verbs"] == {"GET"},
          f"dashboard endpoint exposes {sorted(meta['verbs'])} — it is a read model; every mutating verb must "
          f"be structurally absent (GET-only, AC1)")
    check("C1", payload is not None and ALL_TILES <= set(payload),
          f"composed payload is missing tiles {sorted(ALL_TILES - set(payload or {}))} — it must carry all "
          f"seven independent sub-payloads (AC1)")
    if payload is not None:
        bad_env = sorted(t for t, sp in payload.items() if "available" not in sp)
        check("C1", not bad_env,
              f"tile(s) {bad_env} lack an independent {{available, reason?, data}} envelope — each tile must "
              f"render in isolation (AC1)")

    # C2 — the ONE shared deny-by-default wall; non-member denied, member admitted (existence-hiding).
    check("C2", meta["wall"] == "deny_by_default_shared",
          f"payload built through a {meta['wall']!r} authz path — it must route through the SAME shared "
          f"deny-by-default middleware every read model uses; no dashboard-specific authz path (AC2/§12.3 r21)")
    deny_payload, deny_meta = compose(design, NONMEMBER, sources, mut=mut)
    check("C2", deny_payload is None and deny_meta["http"] == 404,
          f"non-member {NONMEMBER!r} received {'a populated payload' if deny_payload else 'no payload'} "
          f"(http {deny_meta['http']}) — a caller with no membership must get the Project-not-found/deny "
          f"shape, never a partial payload (AC2 existence-hiding)")
    # positive control (non-vacuous): the MEMBER is admitted with a real payload, not denied to nothing.
    check("C2", payload is not None and meta["admitted"],
          f"member {MEMBER!r} was denied — the shared wall must ADMIT a member's scoped read payload "
          f"(non-vacuous; not an over-broad deny)")

    # C3 — every available tile derives from its REAL source; no self-report / placeholder.
    check("C3", meta["source_kind"] == "real",
          f"dashboard fills tiles from a {meta['source_kind']!r} source — every card must draw from its real "
          f"source (coord/scm/metrics/Run-state), never a placeholder or agent self-report (AC3/FR-I3)")
    if payload is not None:
        faked = sorted(t for t, sp in payload.items()
                       if sp.get("available") and sp["data"].get("provenance") != TILE_SOURCE[t])
        check("C3", not faked,
              f"tile(s) {faked} carry data not provenanced to their real source "
              f"{[(t, TILE_SOURCE[t]) for t in faked]} — a fabricated/self-reported value (AC3/FR-I3)")

    # C4 — per-tile independent degradation: the metrics tile degrades, EVERY other tile populates, HTTP 200.
    check("C4", meta["http"] == 200,
          f"endpoint returned HTTP {meta['http']} with a source down — one unavailable source must degrade "
          f"only its tile, never take the whole dashboard 5xx (AC4 availability crux)")
    if payload is not None:
        tc = payload.get("tokenConsumption", {})
        check("C4", tc.get("available") is False and tc.get("reason"),
              f"tokenConsumption tile = {tc} with the metrics source unwired — the unavailable source's tile "
              f"must degrade to an explicit {{available:false, reason}} marker (AC4)")
        others = {t: sp for t, sp in payload.items() if t != "tokenConsumption"}
        not_up = sorted(t for t, sp in others.items() if not sp.get("available"))
        check("C4", not not_up,
              f"tile(s) {not_up} failed to compose while only the metrics source was down — every OTHER tile "
              f"must be populated normally (a partial-but-honest 200 payload, AC4)")

    # C5 — read model, not a service tier: no new store, zero writes on the compose path.
    check("C5", meta["tier"] == "read_model_request_path",
          f"composition runs as a {meta['tier']!r} — it must compose in the request path over existing stores; "
          f"no aggregation service tier (AC5/ADR-020)")
    check("C5", not meta["new_store"],
          "composition stands up a new rollup/billing datastore — ADR-020 forbids a rollup DB / aggregation "
          "store; add a read query to an existing source instead (AC5)")
    check("C5", meta["writes"] == 0,
          f"compose path issued {meta['writes']} write(s) — the aggregation path is a READ; it must hold no "
          f"INSERT/UPDATE/DELETE against any store (AC5)")

    # C6 — live over the existing SSE bus: snapshot + a delta contract for every live tile; no polling loop.
    check("C6", meta["transport"] == "sse_delta_existing",
          f"live updates use {meta['transport']!r} — they must ride the existing SSE progress bus (same "
          f"EventSource + BFF proxy as the Run stream); no new transport, no polling loop (AC6)")
    missing_delta = sorted(LIVE_TILES - set(meta["delta_contract"]))
    check("C6", not missing_delta,
          f"live tile(s) {missing_delta} have no SSE delta contract — each live tile needs a {{tile, patch}} "
          f"delta consistent with the snapshot so a client applies it without a full refetch (AC6)")

    # C7 — cardinality firewall: bounded metric labels only; no per-item id label; no new domain metric.
    banned = sorted(meta["metric_labels"] & FORBIDDEN_METRIC_LABELS)
    check("C7", not banned,
          f"metric label(s) {banned} are per-item/model identifiers — they are span/exemplar only, never a "
          f"metric label (NFR-OBS3 cardinality firewall, AC8)")
    check("C7", not meta["new_domain_metric"],
          "this story emits a new domain metric — it must not: the token signal is 8.8e, the approval-queue "
          "signals are 8.8c/2.12; dashboard read volume is legibility telemetry, never a consumption axis "
          "(AC7/AC8/§17)")

    return fails


def run(mut=None):
    rollup_fails = evaluate(ROLLUP, None, SCENARIO)          # teeth
    rollup_hit = {inv for inv, _ in rollup_fails}
    conf_fails = evaluate(CONFORMANT, mut, SCENARIO)          # baseline or single injected defect
    return rollup_fails, rollup_hit, conf_fails


MUTANTS = {
    "MUTATING_VERB": "C1", "BESPOKE_AUTHZ": "C2", "FABRICATED_TILE": "C3", "WHOLE_FAIL": "C4",
    "ROLLUP_STORE": "C5", "POLL_TRANSPORT": "C6", "PERITEM_LABEL": "C7",
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

    rollup_fails, rollup_hit, conf_fails = run(mut=mut)

    # teeth gate: the dashboard-rollup-service model must trip every invariant, always.
    missing_teeth = [inv for inv in ALL_INV if inv not in rollup_hit]
    if missing_teeth:
        print(f"[dash] TEETH LOST — the dashboard-rollup-service model no longer trips {missing_teeth}:")
        for inv, d in rollup_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[dash] FAIL — the §13/ADR-020 dashboard read model violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] ADR-020 dashboard-rollup-service model : {len(rollup_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(rollup_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] §13/ADR-020 dashboard read model        : 0 violation(s); "
              "GET-only, one-shared-wall, real-sourced, per-tile-degrade, no-new-store+read-only, "
              "sse-delta, bounded-cardinality")
        print("[dash] PASS — the dashboard-rollup-service model detectably breaks every invariant; the "
              "§13/ADR-020\n       read model holds C1-C7 ... and actually returns the member a partial-but-"
              "honest 200 payload\n       (tokenConsumption degraded, every other tile populated), server-"
              "filtered to their\n       memberships, denying the non-member, writing nothing, over the "
              "existing SSE bus, with\n       per-item ids off every metric label.")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)} — acceptable, {expected} is the mapped tooth)" if others else ""
        print(f"[dash] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[dash] SURVIVED — --mutate={mut} did NOT trip {expected} (VACUOUS GUARD); "
          f"tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
