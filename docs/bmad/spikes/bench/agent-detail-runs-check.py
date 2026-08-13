#!/usr/bin/env python3
"""Story 8.11 falsification — the Agent detail page with Run history + logs (FR-F9, epic 8.11, arch §13).

Screen: the agent-detail page (UX 10-agent-detail-runs, 11th screen, ISI-2162). Reached by click-through
from the team-org diagram (8.10) or the squad overview (8.1). It shows a **Run list** with status / duration /
token usage; drilling into a Run opens **tabbed logs** — task/work-item (coordination record, Epic 2),
tool-call, LLM (prompt/response + token counts), build output (**links to the build browser 8.7**), and error
traces — all sourced from `run_events` streamed by the shim over A2A (§7.1/§5.2); an **active Run gets a live
SSE log tail** (§4.4, same BFF proxy as the Run stream 8.2); and **each Run links to its OTel trace** (§17.2
per-Run durable traceparent, ISI-2133 / story 13.1).

Six properties are load-bearing and non-negotiable (epic 8.11, arch §13/§17.2, §12.3 r20/r21, OQ14):
  (1) the Run list + tabbed logs are a **read-only projection of existing sources** — Run CRDs (§5.2) for the
      list, `run_events` (§7.1) + the coordination record (Epic 2) for the tabs — GET-only, NO new backend /
      store; every tab is provenanced to a real existing source, never a fabricated one;
  (2) it is served through the **SAME deny-by-default RBAC wall** every other read model uses, scoped — a
      caller with no membership gets the not-found/deny shape (existence-hiding), never a partial Run list;
      there is **no agent-detail-specific authz path**;
  (3) **token counts are runtime-reported / best-effort legibility, NOT the billing authority** (OQ14, §11,
      arch §17.2): every token figure is provenance `runtime_reported` + authority `best_effort` (never
      `billing`/`authoritative`); a Run whose runtime reported nothing degrades to run-minutes with NO
      fabricated count — the authoritative consumption axis stays the dashboard 8.8 / OTel metering spine;
  (4) it is a **read + navigate surface** (R6 scope guard, no-P2P on the console) — NO mutate/claim/retry/
      dispatch/edit affordance anywhere;
  (5) the **active Run's log tail rides the EXISTING SSE bus** (same EventSource + BFF proxy as the Run stream
      8.2) — NO polling loop, NO new transport; a completed Run has NO live tail (it renders from the durable
      `run_events`);
  (6) each Run's **OTel-trace link and the build-output tab are DEEP-LINKS** (URL navigations) to the existing
      trace store (§17.2 / 13.1) and the build browser (8.7) — NOT a new in-console trace/build store; and
      telemetry adds **no new domain metric** and keeps per-item ids (`agent`/`run.id`/`work_item.id`/
      `user.id`/`model`) off every metric label (NFR-OBS3).

This is a MODEL/differential check (a sibling of team-org-diagram-check.py (8.10), dashboard-aggregation-
check.py and live-runs-panel-sse-check.py), stdlib-only, `python3` it directly — no console, no live cluster
(Run CRDs + `run_events` + memberships fed by fixtures). It first proves the anti-pattern — a "billing
console" (its own authz path that leaks to a non-member, a fabricated non-`run_events` log store, token counts
presented as the authoritative billing axis with a fabricated count where the runtime reported none, a retry/
dispatch button hung on every Run, a polling loop that even tails a completed Run, an in-console reimplemented
trace/build store instead of a deep-link, and per-Run metric labels) — is DETECTED as violating every
invariant (real teeth), then proves the read-model agent-detail page violates nothing and actually returns the
member a scoped, `run_events`-sourced Run history with best-effort tokens, denying the non-member, exposing no
mutate affordance, tailing the active Run over the existing SSE bus, and deep-linking (not reimplementing) the
trace + build browser, with per-item ids off every metric label.

Invariants (C1-C7, each mapped to an AC of story 8.11):
  C1  READ-ONLY PROJECTION (AC1): the Run list (status/duration/tokens) projects Run CRDs (§5.2); the tabbed
      logs (task/work-item, tool-call, LLM, build output, error trace) project `run_events` (§7.1) + the
      coordination record (Epic 2). GET-only (every mutating verb structurally absent); every tab provenanced
      to a real existing source; NO new backend / store.
  C2  THE ONE DENY-BY-DEFAULT RBAC WALL, SCOPED (AC2, security crux): served through the SAME shared
      deny-by-default middleware every read model uses — NO agent-detail-specific authz path. A caller with no
      membership gets the not-found/deny shape (existence-hiding), NEVER a partial Run list; a member gets the
      scoped Run history.
  C3  TOKENS ARE BEST-EFFORT LEGIBILITY, NOT BILLING (AC3, OQ14): every token figure is runtime-reported +
      best-effort (never billing/authoritative); a Run whose runtime reported nothing degrades to run-minutes
      with NO fabricated count. The authoritative consumption axis stays the dashboard (8.8) / metering spine.
  C4  READ + NAVIGATE ONLY (AC4, no-P2P + R6): NO mutate/claim/retry/dispatch/edit affordance anywhere — this
      is a legibility surface, not a coordination path (kill stays 8.4, compose stays 8.5).
  C5  LIVE TAIL OVER THE EXISTING SSE BUS (AC5): the active Run's log tail rides the existing SSE progress bus
      (same EventSource + BFF proxy as the Run stream 8.2) — NO new transport, NO polling loop. A completed Run
      has NO live tail (renders from the durable `run_events`).
  C6  TRACE + BUILD ARE DEEP-LINKS, NOT REIMPLEMENTATIONS (AC6): each Run's OTel-trace link and the
      build-output tab are URL navigations to the existing trace store (§17.2 / 13.1 durable traceparent) and
      the build browser (8.7) — NOT a new in-console trace/build store.
  C7  CARDINALITY FIREWALL + NO NEW METRIC (AC7, NFR-OBS3): the page emits NO new domain metric; per-item ids
      (`agent`/`run.id`/`work_item.id`/`user.id`) are NEVER metric labels and there is NO `model` label.

Mutation-proof harness (no vacuous guard — the ISI-2346-F1 class is excluded by construction). Each
`--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT read model; the check then goes RED with the
mapped invariant failing:
  --mutate=FABRICATED_LOG_SOURCE  source a log tab from a fabricated (non-run_events) store   -> C1 RED
  --mutate=BESPOKE_AUTHZ          an agent-detail-specific authz path that leaks a non-member -> C2 RED
  --mutate=TOKENS_AS_BILLING      present tokens as the authoritative billing axis            -> C3 RED
  --mutate=MUTATE_AFFORDANCE      hang a retry/dispatch button on every Run                   -> C4 RED
  --mutate=POLL_TAIL              drive the active-Run tail with a polling loop, not the bus  -> C5 RED
  --mutate=REIMPL_TRACE          reimplement the trace/build in-console instead of deep-link -> C6 RED
  --mutate=PERITEM_LABEL          put `run.id` on an agent-detail metric label                -> C7 RED

Baseline `python3 agent-detail-runs-check.py` exits 0; each `--mutate=NAME` exits 1 with the mapped violation.
The check exits non-zero if the billing-console model STOPS violating (teeth lost), if the read-model
agent-detail page EVER violates an invariant, or if it fails to actually return the member a scoped,
run_events-sourced Run history with best-effort tokens while denying the non-member.

Runtime proof (owned elsewhere). The real Run-CRD + `run_events` read projection through the BFF, the live
per-membership scoped RBAC on the Go apiserver, the SSE active-Run log tail, and the OTel-trace / build-browser
deep-links are exercised by the console E2E and the apiserver read-model tests. This model check guards the
CONSTRUCTION-TIME contract — 8.11's crux and exactly what FR-F9 + the epic asked: one scoped, run_events-
sourced, best-effort-token, read + navigate agent-detail page over existing seams, deep-linking the trace + the
build browser, tailing the active Run over the existing SSE bus.
"""
import sys

# ---- the Agent's Runs, each with the Run CRD + run_events state its list row and log tabs project ---------
# The list row (status/duration/tokens) projects the Run CRD (§5.2). `tokens_reported` is the runtime's
# best-effort self-report over A2A (OQ14) — None when the runtime reported nothing (-> degrade to run-minutes,
# NEVER a fabricated count). `active` marks the Run that gets the live SSE log tail; a completed Run has none.
RUNS = {
    "run-142": {"status": "running",   "duration_s": 318, "tokens_reported": 48211,  "active": True},
    "run-141": {"status": "succeeded", "duration_s": 812, "tokens_reported": 120334, "active": False},
    "run-140": {"status": "failed",    "duration_s": 233, "tokens_reported": None,   "active": False},  # no report
    "run-139": {"status": "succeeded", "duration_s": 455, "tokens_reported": 9981,   "active": False},
}
ALL_RUNS = set(RUNS)

# the five tabbed-log surfaces per Run, each provenanced to a REAL existing source (C1) — never a fabricated
# store. task/work-item -> the coordination record (Epic 2); tool-call/LLM/error-trace -> run_events (§7.1);
# build output -> a deep-link to the build browser (8.7), a navigation, not an in-console rebuild.
TABS = {
    "task":         "coord_record",   # Epic 2 coordination record (work item / AC / comments)
    "tool_call":    "run_events",     # §7.1 shim-streamed events over A2A
    "llm":          "run_events",     # prompt / response + best-effort token counts
    "build_output": "deeplink_build", # §13 8.7 build browser — a navigation, not a new store
    "error_trace":  "run_events",     # §7.1 error traces
}
ALL_TABS = set(TABS)
VALID_TAB_SOURCES = {"coord_record", "run_events", "deeplink_build"}

# per-item identifiers that must NEVER become a metric label (span/log/exemplar only) — NFR-OBS3 (C7).
FORBIDDEN_METRIC_LABELS = {"agent", "run.id", "work_item.id", "user.id", "principal.id", "model"}

# the Agent's Team members (viewer+). A caller outside this set has NO membership -> the not-found/deny shape.
TEAM_MEMBERS = {"sam", "dana"}


# ---- the token derivation: runtime self-report -> a best-effort, non-billing legibility figure (C3) -------
# This is the OQ14 precision bound: tokens are runtime-reported and best-effort, explicitly NOT the
# authoritative billing axis (that stays the dashboard 8.8 / §17.2 metering spine). A runtime that reports
# nothing degrades to run-minutes with NO fabricated count.
def derive_tokens(reported, mut, run):
    if mut == "TOKENS_AS_BILLING":
        # present tokens as the authoritative billing axis, fabricating a count where the runtime reported none
        value = reported if reported is not None else 99999
        return {"value": value, "provenance": "billing_authority", "authority": "billing", "degraded": None}
    if reported is None:
        return {"value": None, "provenance": "runtime_reported", "authority": "best_effort",
                "degraded": "run_minutes"}
    return {"value": reported, "provenance": "runtime_reported", "authority": "best_effort", "degraded": None}


# ---- the composition: BFF projects the agent-detail page per request over Run CRDs + run_events -----------
#
# `compose(design, caller, mut)` -> (view, meta). `view` is None (deny shape) for a non-member; otherwise a
# dict of run -> row `{status, duration_s, tokens, tabs, trace_link, live_tail}`. `meta` carries the
# structural facts the invariants assert over (verbs, rbac wall, affordances, transport, telemetry). `mut`
# names the single injected defect.
def compose(design, caller, mut=None):
    is_member = caller in TEAM_MEMBERS

    # C2 — the ONE deny-by-default wall, scoped. Conformant: the shared middleware denies a non-member
    # (existence-hiding). BESPOKE_AUTHZ swaps in an agent-detail-only path that fails OPEN and leaks the list.
    wall = "bespoke_agentdetail" if mut == "BESPOKE_AUTHZ" else design["rbac_wall"]
    leaks_nonmember = (mut == "BESPOKE_AUTHZ") or design.get("authz_fail_open")
    admit = is_member or leaks_nonmember
    if not admit:
        return None, _meta(design, mut, http=404, admitted=False, wall=wall)

    view = {}
    for run, crd in RUNS.items():
        # C1 — read-only projection. Each tab provenanced to a real existing source. FABRICATED_LOG_SOURCE
        # sources the LLM tab from a fabricated (non-run_events) store; the billing-console design fabricates
        # every log tab from its own store.
        tabs = {}
        for tab, src in TABS.items():
            if design.get("log_source") == "fabricated_store":
                src = "fabricated"
            elif mut == "FABRICATED_LOG_SOURCE" and tab == "llm":
                src = "fabricated"
            tabs[tab] = src

        # C3 — tokens best-effort legibility, never the billing axis; None -> degrade, never fabricate.
        source = "billing_store" if design.get("token_source") == "billing_store" else None
        if source == "billing_store":
            tokens = {"value": crd["tokens_reported"] if crd["tokens_reported"] is not None else 99999,
                      "provenance": "billing_authority", "authority": "billing", "degraded": None}
        else:
            tokens = derive_tokens(crd["tokens_reported"], mut, run)

        # C5 — live tail over the existing SSE bus for the ACTIVE run; a completed run has NO tail.
        # POLL_TAIL drives the tail with a polling loop AND even tails a completed run.
        if mut == "POLL_TAIL" or design.get("tail_transport") == "new_polling_loop":
            live_tail = {"transport": "new_polling_loop"}  # every run gets a polling tail — wrong on two counts
        elif crd["active"]:
            live_tail = {"transport": "sse_existing"}
        else:
            live_tail = None

        # C6 — the OTel-trace link is a URL navigation to the existing trace store (§17.2 / 13.1), NOT a new
        # in-console store. REIMPL_TRACE reimplements it (and the build tab) as an in-console store.
        if mut == "REIMPL_TRACE" or design.get("trace_kind") == "inconsole_store":
            trace_link = {"kind": "inconsole_store", "target": f"/console/traces/{run}"}
            if tabs.get("build_output") in ("deeplink_build", "fabricated"):
                tabs["build_output"] = "inconsole_build"   # build tab reimplemented too
        else:
            trace_link = {"kind": "deeplink_external", "target": f"/o11y/trace/{run}"}

        view[run] = {
            "status": crd["status"], "duration_s": crd["duration_s"],
            "tokens": tokens, "tabs": tabs, "trace_link": trace_link, "live_tail": live_tail,
        }

    return view, _meta(design, mut, http=200, admitted=True, wall=wall)


def _meta(design, mut, http, admitted, wall):
    # C1 — GET-only read projection; NO new backend / store.
    verbs = set(design["verbs"])
    new_backend = design.get("new_backend", False)

    # C4 — read + navigate only. MUTATE_AFFORDANCE hangs a retry/dispatch button on every Run.
    affordances = set(design["affordances"])
    if mut == "MUTATE_AFFORDANCE":
        affordances = affordances | {"retry", "dispatch"}

    # C5 — transport summary for the surface (the per-run tail is asserted on the view).
    transport = "new_polling_loop" if (mut == "POLL_TAIL" or design.get("tail_transport") ==
                                       "new_polling_loop") else design["tail_transport"]

    # C7 — cardinality firewall. PERITEM_LABEL puts `run.id` on a metric label; the billing console also emits
    # a NEW per-Run token counter as a domain metric.
    metric_labels = set(design["metric_labels"])
    if mut == "PERITEM_LABEL":
        metric_labels = metric_labels | {"run.id"}
    new_domain_metric = design.get("new_domain_metric", False)

    return {
        "http": http, "admitted": admitted, "wall": wall, "verbs": verbs,
        "new_backend": new_backend, "affordances": affordances,
        "transport": transport, "metric_labels": metric_labels, "new_domain_metric": new_domain_metric,
    }


# ---- the two designs -------------------------------------------------------------------------------------
CONFORMANT = {
    "verbs": {"GET"},                       # C1 — GET-only read projection
    "new_backend": False,                   # C1 — no new store; Run CRDs + run_events + coord record
    "rbac_wall": "deny_by_default_shared",  # C2 — the ONE shared wall, scoped, no agent-detail-specific path
    "affordances": {"navigate"},            # C4 — read + navigate only; no mutate/retry/dispatch
    "tail_transport": "sse_existing",       # C5 — active-Run tail over the existing SSE bus
    "metric_labels": {"team.id"},           # C7 — one bounded scope label
    "new_domain_metric": False,             # C7 — no new domain metric (legibility, not a consumption axis)
}
BILLING_CONSOLE = {
    "verbs": {"GET", "POST", "PATCH"},      # C1 fail — mutating verbs on the surface
    "new_backend": True,                    # C1 fail — a new agent-detail/log backend + store
    "log_source": "fabricated_store",       # C1 fail — log tabs from a fabricated (non-run_events) store
    "rbac_wall": "bespoke_agentdetail",     # C2 fail — its own authz path...
    "authz_fail_open": True,                # C2 fail — ...that leaks the Run list to a non-member
    "token_source": "billing_store",        # C3 fail — tokens presented as the authoritative billing axis
    "affordances": {"navigate", "retry", "dispatch", "kill"},  # C4 fail — mutate/coordination affordances
    "tail_transport": "new_polling_loop",   # C5 fail — a polling loop, not the SSE bus
    "trace_kind": "inconsole_store",        # C6 fail — a reimplemented in-console trace/build store
    "metric_labels": {"team.id", "run.id", "model"},  # C7 fail — per-item + model metric labels
    "new_domain_metric": True,              # C7 fail — a new per-Run token counter
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

    # C1 — read-only projection; GET-only; no new backend; every tab provenanced to a real existing source.
    check("C1", meta["verbs"] == {"GET"},
          f"agent-detail endpoint exposes {sorted(meta['verbs'])} — it is a read projection of Run CRDs + "
          f"run_events; every mutating verb must be structurally absent (GET-only, AC1)")
    check("C1", not meta["new_backend"],
          "agent detail stands up a new backend / store — the epic forbids it: the Run list projects Run CRDs "
          "(§5.2) and the tabs project run_events (§7.1) + the coordination record (Epic 2) (AC1)")
    check("C1", view is not None and ALL_RUNS <= set(view),
          f"projected view is missing Run(s) {sorted(ALL_RUNS - set(view or {}))} — it must render the whole "
          f"Run history for the Agent (AC1)")
    if view is not None:
        for run, row in view.items():
            missing_tabs = sorted(ALL_TABS - set(row["tabs"]))
            check("C1", not missing_tabs,
                  f"Run {run} is missing log tab(s) {missing_tabs} — every Run must expose task/work-item, "
                  f"tool-call, LLM, build output, and error-trace tabs (AC1)")
            faked = sorted(t for t, s in row["tabs"].items() if s not in VALID_TAB_SOURCES)
            check("C1", not faked,
                  f"Run {run} log tab(s) {faked} are sourced from a fabricated store — every tab must project "
                  f"a real existing source (run_events §7.1, coord record Epic 2, or a build-browser deep-link) "
                  f"(AC1)")

    # C2 — the ONE shared deny-by-default wall; scoped; non-member denied, member admitted.
    check("C2", meta["wall"] == "deny_by_default_shared",
          f"page built through a {meta['wall']!r} authz path — it must route through the SAME shared "
          f"deny-by-default middleware every read model uses; no agent-detail-specific authz path (AC2/§12.3)")
    deny_view, deny_meta = compose(design, NONMEMBER, mut=mut)
    check("C2", deny_view is None and deny_meta["http"] == 404,
          f"non-member {NONMEMBER!r} received {'a populated Run list' if deny_view else 'no view'} "
          f"(http {deny_meta['http']}) — a caller with no membership must get the not-found/deny shape, never "
          f"a partial Run list (AC2 existence-hiding)")
    # positive control (non-vacuous): the MEMBER is admitted with a real scoped Run history, not denied to nothing.
    check("C2", view is not None and meta["admitted"],
          f"member {MEMBER!r} was denied — the shared wall must ADMIT a member's scoped Run history "
          f"(non-vacuous; not an over-broad deny)")

    # C3 — tokens best-effort legibility, never the billing axis; None -> degrade, never fabricate.
    if view is not None:
        billing = sorted(r for r, row in view.items()
                         if row["tokens"]["authority"] != "best_effort"
                         or row["tokens"]["provenance"] != "runtime_reported")
        check("C3", not billing,
              f"Run(s) {billing} present tokens as authoritative/billing — token counts are runtime-reported "
              f"and best-effort (OQ14, §17.2); the authoritative consumption axis stays the dashboard 8.8, "
              f"never this legibility surface (AC3)")
        # a runtime that reported nothing must degrade to run-minutes with NO fabricated count.
        fabricated = sorted(r for r, row in view.items()
                            if RUNS[r]["tokens_reported"] is None
                            and (row["tokens"]["value"] is not None or row["tokens"]["degraded"] != "run_minutes"))
        check("C3", not fabricated,
              f"Run(s) {fabricated} show a fabricated token count where the runtime reported none — a Run with "
              f"no runtime report must degrade to run-minutes with NO fabricated count (AC3/OQ14)")
        # non-vacuous positive control: a Run that DID report tokens surfaces its real best-effort count.
        reported = "run-141"
        check("C3", view[reported]["tokens"]["value"] == RUNS[reported]["tokens_reported"],
              f"Run {reported} does not surface its runtime-reported token count "
              f"{RUNS[reported]['tokens_reported']} — best-effort tokens must still be shown when reported "
              f"(non-vacuous; the surface is legibility, it just is not billing) (AC3)")

    # C4 — read + navigate only; no mutate/claim/retry/dispatch/edit affordance.
    illegal_aff = sorted(meta["affordances"] & {"retry", "dispatch", "claim", "reassign", "kill", "edit"})
    check("C4", not illegal_aff,
          f"the page exposes coordination affordance(s) {illegal_aff} — it must be read + navigate ONLY "
          f"(no-P2P on the console, R6); kill stays 8.4, compose stays 8.5 (AC4)")

    # C5 — the active Run's tail rides the existing SSE bus; a completed Run has NO tail; no polling loop.
    if view is not None:
        active_run = next(r for r, c in RUNS.items() if c["active"])
        tail = view[active_run]["live_tail"]
        check("C5", tail is not None and tail["transport"] == "sse_existing",
              f"the active Run {active_run} log tail uses "
              f"{tail['transport'] if tail else 'no'} transport — it must ride the existing SSE progress bus "
              f"(same EventSource + BFF proxy as the Run stream 8.2); no new transport, no polling loop (AC5)")
        # a completed Run must NOT be live-tailed — it renders from the durable run_events.
        bad_tail = sorted(r for r, row in view.items() if not RUNS[r]["active"] and row["live_tail"] is not None)
        check("C5", not bad_tail,
              f"completed Run(s) {bad_tail} carry a live tail — only the active Run gets an SSE tail; a "
              f"completed Run renders from the durable run_events (AC5)")

    # C6 — the trace link + build-output tab are deep-links to existing surfaces, not a reimplemented store.
    if view is not None:
        reimpl_trace = sorted(r for r, row in view.items() if row["trace_link"]["kind"] != "deeplink_external")
        check("C6", not reimpl_trace,
              f"Run(s) {reimpl_trace} reimplement the OTel trace in-console — each Run's trace link must be a "
              f"URL navigation to the existing trace store (§17.2 / 13.1 durable traceparent), never a new "
              f"in-console trace store (AC6)")
        reimpl_build = sorted(r for r, row in view.items() if row["tabs"].get("build_output") != "deeplink_build")
        check("C6", not reimpl_build,
              f"Run(s) {reimpl_build} reimplement the build output in-console — the build-output tab must "
              f"deep-link to the build browser (8.7), never rebuild it in the agent-detail page (AC6)")

    # C7 — cardinality firewall: bounded metric labels only; no per-item id label; no new domain metric.
    banned = sorted(meta["metric_labels"] & FORBIDDEN_METRIC_LABELS)
    check("C7", not banned,
          f"metric label(s) {banned} are per-item/model identifiers — they are span/exemplar only, never a "
          f"metric label (NFR-OBS3 cardinality firewall, AC7)")
    check("C7", not meta["new_domain_metric"],
          "the agent-detail page emits a new domain metric — it must not: the Run history + token figures are "
          "legibility telemetry, never a consumption axis (that is the dashboard 8.8 / §17.2 spine) (AC7)")

    return fails


def run(mut=None):
    bill_fails = evaluate(BILLING_CONSOLE, None)           # teeth
    bill_hit = {inv for inv, _ in bill_fails}
    conf_fails = evaluate(CONFORMANT, mut)                 # baseline or single injected defect
    return bill_fails, bill_hit, conf_fails


MUTANTS = {
    "FABRICATED_LOG_SOURCE": "C1", "BESPOKE_AUTHZ": "C2", "TOKENS_AS_BILLING": "C3",
    "MUTATE_AFFORDANCE": "C4", "POLL_TAIL": "C5", "REIMPL_TRACE": "C6", "PERITEM_LABEL": "C7",
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

    bill_fails, bill_hit, conf_fails = run(mut=mut)

    # teeth gate: the billing-console model must trip every invariant, always.
    missing_teeth = [inv for inv in ALL_INV if inv not in bill_hit]
    if missing_teeth:
        print(f"[agent-detail] TEETH LOST — the billing-console model no longer trips {missing_teeth}:")
        for inv, d in bill_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[agent-detail] FAIL — the read-model agent-detail page violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] billing-console model        : {len(bill_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(bill_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] read-model agent-detail page  : 0 violation(s); "
              "GET-only run_events-projection, one-shared-wall scoped, best-effort-tokens, read+navigate, "
              "sse-tail-on-active, deep-linked trace+build, bounded-cardinality")
        print("[agent-detail] PASS — the billing-console model detectably breaks every invariant; the\n"
              "      read-model agent-detail page holds C1-C7 ... and actually returns the member a scoped,\n"
              "      run_events-sourced Run history with best-effort tokens, denying the non-member, exposing\n"
              "      no mutate affordance, tailing the active Run over the existing SSE bus, and deep-linking\n"
              "      (not reimplementing) the OTel trace + the build browser, with per-item ids off every\n"
              "      metric label.")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)} — acceptable, {expected} is the mapped tooth)" if others else ""
        print(f"[agent-detail] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[agent-detail] SURVIVED — --mutate={mut} did NOT trip {expected} (VACUOUS GUARD); "
          f"tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
