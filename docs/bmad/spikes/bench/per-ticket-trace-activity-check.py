#!/usr/bin/env python3
"""Story 13.5 falsification — per-Run / per-ticket trace activity in the console (obs-plan §3, §5.2, epic 13.5).

This is the OBSERVABILITY half of the trace drill-down. Its sibling 8.11 (done, agent-detail-runs-check.py)
built the console read model — the agent-detail page that deep-links each Run to its OTel trace. THIS story
pins the observability contract that surface consumes and adds the one thing 8.11 does not: the **per-ticket
activity reconstruction**. obs-plan §3 states it literally: *a work item (ticket) can span MULTIPLE Runs —
retries, crash-reclaims, resume-after-pause — so the per-ticket perspective is a JOIN QUERY on `work_item.id`,
not a new signal.* The timeline for a ticket is assembled by joining traces + correlated logs + `run_events`
on `ksquad.work_item.id` across EVERY Run the ticket touched, in causal order — and `work_item.id` stays a
trace/log/exemplar dimension, NEVER a metric label (§1.2/§5.6 cardinality law).

Six properties are load-bearing and non-negotiable (obs-plan §3, §5.2, §4.1, §1.2/§5.6; arch §4.4, §17.2, §12.3):
  (1) each Run **deep-links to its one OTel trace** via the DURABLE `Run.status` annotation
      `ksquad.io/traceparent` (13.1 §C — survives a controller restart, resolves even for a completed Run whose
      trace is closed); the trace shows the state-machine phase-duration spans (§5.2); a URL to the existing
      trace store (§17.2), NOT an in-console reimplementation;
  (2) a ticket's activity is reconstructable across **ALL** its Runs by joining traces + logs + `run_events`
      on `work_item.id`, in causal order — the full attempt history (each Run's claim/phases/terminal), NOT
      just the latest Run;
  (3) the per-ticket / per-Run view is a **QUERY over the id dimensions**, never a new metric label —
      `work_item.id` / `run.id` are span/log/exemplar only, and NO `per_ticket_activity{work_item_id=…}` series
      exists (§1.2/§5.6, the exact regression 13.6's cardinality lint fails on);
  (4) an **active** Run shows live span/log activity over the EXISTING SSE bus (same EventSource + BFF proxy as
      the Run stream 8.2, §4.4) — NO new transport, NO polling loop; a completed Run has NO live activity (it
      renders from the durable `run_events` + the closed trace via the deep-link);
  (5) served through the **ONE shared deny-by-default RBAC wall**, scoped — a non-member gets the not-found/deny
      shape (existence-hiding), never a partial ticket timeline; reads ONLY existing sources (trace store /
      logs / `run_events`); NO new backend/store;
  (6) the join is **stable across the P0->P1 phasing seam** (§4.1) — it reconstructs the ticket at P0 (log +
      `run_events` correlation, no cross-sandbox stitching) and merely DEEPENS the per-Run trace at P1; it must
      not false-start on P1 stitching that has not landed.

This is a MODEL/differential check (a sibling of agent-detail-runs-check.py (8.11) and
run-trace-correlation-check.py (13.1)), stdlib-only, `python3` it directly — no console, no live cluster (the
ticket's Runs + their durable annotations + `run_events` fed by fixtures). It first proves the anti-pattern —
a "per-ticket metrics dashboard" (resolves the trace link from a request-time value that dies on a completed
Run, shows only the LATEST Run of a ticket, materializes a `per_ticket_activity{work_item_id=…}` METRIC,
polls a completed Run, runs its own authz path that leaks a partial timeline to a non-member from a fabricated
activity store, and REQUIRES P1 stitching so it reconstructs nothing at P0) — is DETECTED as violating every
invariant (real teeth), then proves the join-query model violates nothing and actually reconstructs the
three-Run ticket as one causal timeline, deep-linking each Run's trace from its durable annotation, with
`work_item.id` off every metric label, live activity only for the active Run over the existing SSE bus, a
non-member denied, and the join truthful at P0.

Invariants (C1-C6, each mapped to an AC of story 13.5):
  C1  DURABLE TRACE DEEP-LINK (AC1): each Run's trace link resolves the `trace_id` from the durable
      `Run.status` `ksquad.io/traceparent` (13.1 §C) — resolves even for a completed Run — and is a URL to the
      existing trace store (§17.2), never an in-console store.
  C2  PER-TICKET SPANS ALL RUNS, CAUSAL ORDER (AC2, the crux): the ticket timeline joins traces + logs +
      `run_events` on `work_item.id` across EVERY Run the ticket spanned (retry/reclaim/resume), in causal
      order — the full attempt history, NOT just the latest Run.
  C3  A QUERY, NOT A METRIC LABEL (AC3, cardinality crux): the view is a join over the `work_item.id`/`run.id`
      DIMENSIONS; NO metric series is keyed on `work_item.id`/`run.id` and NO new instrument is emitted.
  C4  ACTIVE=LIVE OVER THE EXISTING SSE BUS, COMPLETED=DURABLE-ONLY (AC4): the active Run's activity rides the
      existing EventSource + BFF proxy (run.id+span_id on events); a completed Run has NO live activity — no
      polling loop, no tailing a completed Run.
  C5  ONE RBAC WALL, SCOPED, NO NEW STORE (AC5): served through the shared deny-by-default middleware; a
      non-member gets the not-found/deny shape (never a partial timeline); reads only existing sources.
  C6  JOIN STABLE ACROSS THE P0->P1 SEAM (AC6): the same `work_item.id`/`run.id` join reconstructs the ticket
      at P0 (no stitching) and only deepens at P1; it must not require P1 stitching to work at all.

Mutation-proof harness (no vacuous guard). Each `--mutate=<NAME>` injects exactly ONE defect into the
CONFORMANT join-query model; the check then goes RED with the mapped invariant failing:
  --mutate=REQUEST_TIME_LINK  resolve the trace link from a request-time value (dies for a completed Run) -> C1 RED
  --mutate=LATEST_RUN_ONLY    reconstruct the ticket from only its latest Run                             -> C2 RED
  --mutate=WORKITEM_LABEL     materialize a per_ticket_activity{work_item_id=…} metric series             -> C3 RED
  --mutate=POLL_ACTIVITY      drive live activity with a polling loop AND tail a completed Run            -> C4 RED
  --mutate=BESPOKE_AUTHZ      an agent-detail-specific authz path that leaks a partial timeline           -> C5 RED
  --mutate=REQUIRE_P1         require P1 stitching so the join reconstructs NOTHING at P0                 -> C6 RED

Baseline `python3 per-ticket-trace-activity-check.py` exits 0; each `--mutate=NAME` exits 1 with the mapped
violation. The check exits non-zero if the metrics-dashboard model STOPS violating (teeth lost), if the
join-query model EVER violates an invariant, or if it fails to actually reconstruct the three-Run ticket at P0
with per-item ids off every metric label.

Runtime proof (owned elsewhere). The real trace-store deep-link, the live per-membership scoped RBAC on the Go
apiserver, the SSE active-Run activity stream, and the actual trace + log + `run_events` join are exercised by
the console E2E and the apiserver read-model tests. This model check guards the CONSTRUCTION-TIME contract —
13.5's crux and exactly what obs-plan §3 asked: per-Run trace = a durable deep-link; per-ticket = a
`work_item.id` join across ALL of a ticket's Runs, in causal order, a query never a metric label.
"""
import sys

# ---- the ticket W-500 and the THREE Runs it spanned (retry -> crash-reclaim -> resume) --------------------
# obs-plan §3: a work item spans MULTIPLE Runs. All three carry work_item.id = W-500; each has a DURABLE
# `ksquad.io/traceparent` (its own trace_id, 13.1 §C) and a causal `seq`. Only the current Run is `active`.
TICKET = "W-500"
RUNS = {
    "run-a": {"work_item": "W-500", "seq": 1, "status": "failed",    "trace_id": "t-aaa", "active": False,
              "traceparent": "00-t-aaa-01-01", "events": ["claim", "dispatch", "running", "failed"]},
    "run-b": {"work_item": "W-500", "seq": 2, "status": "reclaimed", "trace_id": "t-bbb", "active": False,
              "traceparent": "00-t-bbb-01-01", "events": ["reclaim.fence", "claim", "dispatch", "reclaimed"]},
    "run-c": {"work_item": "W-500", "seq": 3, "status": "running",   "trace_id": "t-ccc", "active": True,
              "traceparent": "00-t-ccc-01-01", "events": ["resume", "claim", "dispatch", "running"]},
}
# the full causal set of Runs the ticket spanned, in order — what the per-ticket view MUST reconstruct.
TICKET_RUNS_CAUSAL = [r for r, _ in sorted(RUNS.items(), key=lambda kv: kv[1]["seq"])]
ALL_RUNS = set(RUNS)

# per-item identifiers that must NEVER become a metric label (span/log/exemplar only) — §1.2/§5.6 (C3).
FORBIDDEN_METRIC_LABELS = {"work_item.id", "run.id", "user.id", "principal.id", "agent", "model"}

# the Team members who can see the ticket. A caller outside this set has NO membership -> not-found/deny shape.
TEAM_MEMBERS = {"sam", "dana"}


# ---- reconstruct the per-ticket timeline by joining on work_item.id across ALL the ticket's Runs ----------
# Returns (included_run_ids, timeline_events, per_run) where per_run maps run -> its trace-link + live state.
# `stitching_landed` models the §4.1 phase: False = P0 (log + run_events correlation, no cross-sandbox
# stitching), True = P1 (connected cross-boundary trace). The conformant join works at BOTH.
def reconstruct(design, caller, mut, stitching_landed):
    is_member = caller in TEAM_MEMBERS

    # C5 — the ONE deny-by-default wall, scoped. Conformant: the shared middleware denies a non-member.
    # BESPOKE_AUTHZ swaps in a view-specific path that fails OPEN and leaks a partial timeline.
    wall = "bespoke_perticket" if mut == "BESPOKE_AUTHZ" else design["rbac_wall"]
    leaks_nonmember = (mut == "BESPOKE_AUTHZ") or design.get("authz_fail_open")
    if not (is_member or leaks_nonmember):
        return None, None, None, None, {"http": 404, "admitted": False, "wall": wall}

    # `render_runs` = the ticket's Runs the view surfaces per-Run rows for (C1 trace link / C4 live state);
    # `included` = the Runs whose events are JOINED into the per-ticket activity timeline (C2/C6). They are the
    # same for a conformant view; the metrics-dashboard renders every Run but only timelines the latest, so the
    # per-Run C1/C4 teeth stay observable even when its timeline is incomplete.
    #
    # C6 — P0->P1 join stability. The conformant join reconstructs the ticket at P0 from work_item.id log +
    # run_events correlation. REQUIRE_P1 requires stitching -> empty timeline at P0 (false-start); the
    # metrics-dashboard shows the FULL history only once P1 lands (partial at P0) — both make P0 != P1.
    requires_p1 = (mut == "REQUIRE_P1") or design.get("requires_p1_stitching")
    latest_only = (mut == "LATEST_RUN_ONLY") or design.get("latest_run_only")
    full_only_at_p1 = design.get("full_only_at_p1")

    render_runs = [] if (requires_p1 and not stitching_landed) else list(TICKET_RUNS_CAUSAL)
    if requires_p1 and not stitching_landed:
        included = []                      # false-start: nothing reconstructs until P1 lands
    elif latest_only or (full_only_at_p1 and not stitching_landed):
        included = [TICKET_RUNS_CAUSAL[-1]]   # only the latest Run — drops the retry/reclaim attempts
    else:
        included = list(TICKET_RUNS_CAUSAL)

    timeline = [(r, ev) for r in included for ev in RUNS[r]["events"]]  # joined events, causal order

    per_run = {}
    for r in render_runs:
        crd = RUNS[r]
        # C1 — the trace deep-link resolves from the DURABLE annotation and resolves for a completed Run.
        # REQUEST_TIME_LINK resolves from a request-time value that is absent once the Run/trace is closed.
        if mut == "REQUEST_TIME_LINK" or design.get("link_source") == "request_time":
            # a request-time value is only present while the Run is live; None for a completed Run.
            resolved = crd["trace_id"] if crd["active"] else None
            link = {"kind": "deeplink_external", "resolved_from": "request_time", "trace_id": resolved}
        elif design.get("trace_kind") == "inconsole_store":
            link = {"kind": "inconsole_store", "resolved_from": "durable_annotation", "trace_id": crd["trace_id"]}
        else:
            # durable: resolve trace_id from `ksquad.io/traceparent` — present for live AND completed Runs.
            tid = crd["traceparent"].split("-")[1]
            link = {"kind": "deeplink_external", "resolved_from": "durable_annotation", "trace_id": tid}

        # C4 — live activity over the existing SSE bus for the ACTIVE Run only; a completed Run has none.
        # POLL_ACTIVITY drives a polling loop AND tails completed Runs.
        if mut == "POLL_ACTIVITY" or design.get("activity_transport") == "new_polling_loop":
            live = {"transport": "new_polling_loop"}      # every Run polled — wrong on two counts
        elif crd["active"]:
            live = {"transport": "sse_existing", "carries": {"run.id", "span_id"}}
        else:
            live = None
        per_run[r] = {"trace_link": link, "live": live}

    meta = {"http": 200, "admitted": True, "wall": wall,
            "new_backend": design.get("new_backend", False),
            "reads_only_existing": design.get("activity_store", "existing") == "existing"}

    # C3 — metric labels. WORKITEM_LABEL materializes a per_ticket_activity series keyed on work_item.id.
    metric_labels = set(design["metric_labels"])
    new_domain_metric = design.get("new_domain_metric", False)
    if mut == "WORKITEM_LABEL":
        metric_labels = metric_labels | {"work_item.id"}
        new_domain_metric = True
    meta["metric_labels"] = metric_labels
    meta["new_domain_metric"] = new_domain_metric
    return render_runs, included, timeline, per_run, meta


# ---- the two designs -------------------------------------------------------------------------------------
CONFORMANT = {
    "rbac_wall": "deny_by_default_shared",   # C5 — the ONE shared wall, scoped
    "link_source": "durable_annotation",     # C1 — trace link resolves from the durable ksquad.io/traceparent
    "trace_kind": "deeplink_external",       # C1 — a URL to the existing trace store, not an in-console store
    "latest_run_only": False,                # C2 — reconstruct across ALL the ticket's Runs
    "requires_p1_stitching": False,          # C6 — join truthful at P0 (no cross-sandbox stitching required)
    "activity_transport": "sse_existing",    # C4 — active-Run activity over the existing SSE bus
    "activity_store": "existing",            # C5 — reads only trace store / logs / run_events
    "new_backend": False,                    # C5 — no new backend/store
    "metric_labels": {"team.id"},            # C3 — one bounded scope label
    "new_domain_metric": False,              # C3 — no new instrument (it is a query, not a signal)
}
METRICS_DASHBOARD = {
    "rbac_wall": "bespoke_perticket",        # C5 fail — its own authz path...
    "authz_fail_open": True,                 # C5 fail — ...that leaks a partial timeline to a non-member
    "activity_store": "fabricated",          # C5 fail — a fabricated non-run_events activity store
    "new_backend": True,                     # C5 fail — a new per-ticket backend/store
    "link_source": "request_time",           # C1 fail — trace link resolved from a request-time value
    "full_only_at_p1": True,                 # C2+C6 fail — partial (latest-Run-only) at P0, full only once P1 lands
    "activity_transport": "new_polling_loop",# C4 fail — a polling loop, tailing completed Runs too
    "metric_labels": {"team.id", "work_item.id", "run.id"},  # C3 fail — per-item id metric labels
    "new_domain_metric": True,               # C3 fail — a new per_ticket_activity metric series
}


# ---- the runnable check ----------------------------------------------------------------------------------
def evaluate(design, mut):
    """Return the list of (invariant, detail) violations for `design`, for member + non-member, at P0."""
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    MEMBER, NONMEMBER = "sam", "mallory"
    # The join is evaluated at P0 (stitching NOT landed) — this is the §4.1 phase that must already work.
    render_runs, included, timeline, per_run, meta = reconstruct(design, MEMBER, mut, stitching_landed=False)

    # positive control (non-vacuous): the member is admitted with a real reconstruction, not denied to nothing.
    check("C5", included is not None and meta["admitted"],
          f"member {MEMBER!r} was denied — the shared wall must ADMIT a member's scoped ticket timeline "
          f"(non-vacuous; not an over-broad deny)")

    if included is not None:
        # C6 — the join must reconstruct the ticket at P0 (no cross-sandbox stitching). Empty here = false-start.
        check("C6", len(included) > 0,
              f"ticket {TICKET} reconstructs NOTHING at P0 — the per-ticket join runs over work_item.id log + "
              f"run_events correlation and must be truthful at P0 (§4.1); requiring P1 stitching to reconstruct "
              f"at all is a false-start (AC6)")

        # C2 — the timeline joins ALL of the ticket's Runs, in causal order — the full attempt history.
        missing = [r for r in TICKET_RUNS_CAUSAL if r not in included]
        check("C2", not missing,
              f"ticket {TICKET} timeline is missing Run(s) {missing} — a ticket spans MULTIPLE Runs "
              f"(retry/reclaim/resume) and the per-ticket view must join traces + logs + run_events on "
              f"work_item.id across EVERY Run it spanned, not just the latest (AC2, the crux)")
        # causal order: the seq of the included Runs must be non-decreasing.
        seqs = [RUNS[r]["seq"] for r in included]
        check("C2", seqs == sorted(seqs),
              f"ticket timeline Runs {included} are not in causal order (seqs {seqs}) — the merged timeline "
              f"must be ordered claim->dispatch->terminal, then the next Run's attempt (AC2)")
        # non-vacuous: the reconstructed timeline actually carries each Run's attempt events (e.g. the reclaim).
        check("C2", ("run-b", "reclaim.fence") in timeline,
              "the reconstructed timeline does not surface Run run-b's crash-reclaim fence event — the "
              "per-ticket view must show the full attempt history (claims, reclaims, terminals), not a summary "
              "(non-vacuous; the prior attempts' events are the point of the per-ticket perspective) (AC2)")

        # C1 — each rendered Run's trace link resolves from the DURABLE annotation and resolves for a completed Run.
        for r in render_runs:
            link = per_run[r]["trace_link"]
            check("C1", link["kind"] == "deeplink_external",
                  f"Run {r} reimplements the trace view in-console ({link['kind']}) — the trace link must be a "
                  f"URL to the existing trace store (§17.2), never a new in-console store (AC1)")
            check("C1", link["resolved_from"] == "durable_annotation",
                  f"Run {r} trace link resolves from {link['resolved_from']!r} — it must resolve the trace_id "
                  f"from the DURABLE Run.status ksquad.io/traceparent (13.1 §C), which survives a restart and "
                  f"resolves for a completed Run (AC1)")
            check("C1", link["trace_id"] is not None,
                  f"Run {r} trace link did not resolve (trace_id None) — a completed Run's trace is closed but "
                  f"the durable annotation must still resolve the link; a request-time value that is gone once "
                  f"the Run closes breaks this (AC1)")

        # C4 — the active Run gets live activity over the EXISTING SSE bus; a completed Run gets none.
        active_runs = [r for r in render_runs if RUNS[r]["active"]]
        for active_run in active_runs:
            live = per_run[active_run]["live"]
            check("C4", live is not None and live["transport"] == "sse_existing",
                  f"the active Run {active_run} activity uses {live['transport'] if live else 'no'} transport — "
                  f"it must ride the existing SSE progress bus (same EventSource + BFF proxy as the Run stream "
                  f"8.2); no new transport, no polling loop (AC4)")
            if live is not None and live.get("carries"):
                check("C4", {"run.id", "span_id"} <= live["carries"],
                      f"the active Run {active_run} SSE events do not carry run.id + span_id — live activity "
                      f"must carry them to stitch back into the Run's trace (§3 SSE hub row) (AC4)")
        bad = [r for r in render_runs if not RUNS[r]["active"] and per_run[r]["live"] is not None]
        check("C4", not bad,
              f"completed Run(s) {bad} carry live activity — only the active Run gets a live SSE stream; a "
              f"completed Run renders from the durable run_events + the closed trace (AC4)")

    # C5 — the ONE shared wall; scoped; a non-member denied; reads only existing sources; no new backend.
    check("C5", meta["wall"] == "deny_by_default_shared",
          f"view built through a {meta['wall']!r} authz path — it must route through the SAME shared "
          f"deny-by-default middleware every read model uses; no view-specific authz path (AC5/§12.3)")
    check("C5", meta.get("reads_only_existing", True),
          "the view reads a fabricated activity store — it must read ONLY existing sources (trace store §17.2, "
          "correlated logs §6, run_events §7.1); no new store (AC5)")
    check("C5", not meta["new_backend"],
          "the view stands up a new backend/store — the per-ticket timeline is a JOIN over existing sources, "
          "not a new store (AC5)")
    _, deny_inc, _, _, deny_meta = reconstruct(design, NONMEMBER, mut, stitching_landed=False)
    check("C5", deny_inc is None and deny_meta["http"] == 404,
          f"non-member {NONMEMBER!r} received {'a partial ticket timeline' if deny_inc else 'no view'} "
          f"(http {deny_meta['http']}) — a caller with no membership must get the not-found/deny shape, never a "
          f"partial timeline (AC5 existence-hiding)")

    # C3 — a query over id dimensions, never a metric label; no new instrument.
    banned = sorted(meta["metric_labels"] & FORBIDDEN_METRIC_LABELS)
    check("C3", not banned,
          f"metric label(s) {banned} are per-item identifiers — the per-ticket view is a JOIN over the "
          f"work_item.id/run.id DIMENSIONS; those are span/log/exemplar only, NEVER metric labels "
          f"(§1.2/§5.6, the exact regression 13.6's cardinality lint fails on) (AC3, the cardinality crux)")
    check("C3", not meta["new_domain_metric"],
          "the view emits a new domain metric (e.g. per_ticket_activity{work_item_id=…}) — the per-ticket "
          "rollup is a QUERY over the trace/log/audit stores, not a new signal; materializing it as a metric "
          "series keyed on an unbounded id is a cardinality-law violation (AC3)")

    # C6 — join stability: the SAME join must ALSO reconstruct the ticket at P1 (stitching landed), unchanged.
    _, p1_inc, _, _, _ = reconstruct(design, MEMBER, mut, stitching_landed=True)
    check("C6", p1_inc is not None and set(p1_inc) == set(included or []),
          f"the ticket reconstruction differs across the P0->P1 seam (P0={sorted(included or [])}, "
          f"P1={sorted(p1_inc or [])}) — P1 must only DEEPEN the per-Run trace, never change the join key or "
          f"the set of Runs the ticket timeline spans (AC6)")

    return fails


def run(mut=None):
    dash_fails = evaluate(METRICS_DASHBOARD, None)         # teeth
    dash_hit = {inv for inv, _ in dash_fails}
    conf_fails = evaluate(CONFORMANT, mut)                 # baseline or single injected defect
    return dash_fails, dash_hit, conf_fails


MUTANTS = {
    "REQUEST_TIME_LINK": "C1", "LATEST_RUN_ONLY": "C2", "WORKITEM_LABEL": "C3",
    "POLL_ACTIVITY": "C4", "BESPOKE_AUTHZ": "C5", "REQUIRE_P1": "C6",
}
ALL_INV = ["C1", "C2", "C3", "C4", "C5", "C6"]


def main(argv):
    mut = None
    for a in argv[1:]:
        if a.startswith("--mutate="):
            mut = a.split("=", 1)[1].strip().upper()
    if mut and mut not in MUTANTS:
        print(f"unknown mutant {mut!r}; choose from {', '.join(MUTANTS)}", file=sys.stderr)
        return 2

    dash_fails, dash_hit, conf_fails = run(mut=mut)

    # teeth gate: the metrics-dashboard model must trip every invariant, always.
    missing_teeth = [inv for inv in ALL_INV if inv not in dash_hit]
    if missing_teeth:
        print(f"[per-ticket] TEETH LOST — the metrics-dashboard model no longer trips {missing_teeth}:")
        for inv, d in dash_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[per-ticket] FAIL — the join-query model violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] per-ticket metrics-dashboard : {len(dash_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(dash_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] join-query model             : 0 violation(s); "
              "durable-annotation trace deep-link, all-Runs causal reconstruction, work_item.id off every "
              "metric label, sse-activity-on-active, one-shared-wall scoped, P0->P1 stable")
        print("[per-ticket] PASS — the metrics-dashboard model detectably breaks every invariant; the\n"
              "      join-query model holds C1-C6 ... and actually reconstructs ticket W-500 across all three\n"
              "      Runs (fail -> reclaim -> resume) as one causal timeline, deep-linking each Run's trace\n"
              "      from its durable ksquad.io/traceparent, with work_item.id off every metric label, live\n"
              "      activity only for the active Run over the existing SSE bus, denying the non-member, and\n"
              "      reconstructing truthfully at P0.")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)} — acceptable, {expected} is the mapped tooth)" if others else ""
        print(f"[per-ticket] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[per-ticket] SURVIVED — --mutate={mut} did NOT trip {expected} (VACUOUS GUARD); "
          f"tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
