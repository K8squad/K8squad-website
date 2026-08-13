#!/usr/bin/env python3
"""Story 8.8d falsification — PR status mini-board (FR-I6, scm_pr_mirror, no second GitHub integration).

The PR mini-board groups the Project's pull requests by state (ready-for-review/draft/blocked/merged) from
the 8.8a `prBoard` sub-payload, which reads the `scm_pr_mirror` (§5.4, ADR-018) — the SINGLE source-control
sync read model. Two properties are load-bearing and non-negotiable:

  (1) This story issues NO direct GitHub API call and introduces NO second GitHub integration, token, or
      webhook path. The repo-sync reconciler (§5.4, ADR-018) is the only thing that talks to GitHub; the
      dashboard is a read model over its mirror (via 8.8a). One GitHub integration, ever.
  (2) An unsynced repo (or Epic 11.3 not yet landed) is a NORMAL OPERATING STATE, not a failure: the board
      degrades to an explicit empty state ("No repository synced"), never a hard failure or a whole-dashboard
      error (8.8a per-tile degrade). Read AC4 literally.

Invariants (C1-C7, mapped to ACs of story 8.8d):
  C1  GROUPED BY FOUR STATES FROM SCM MIRROR (AC1): the board groups PRs into ready-for-review/draft/
      blocked/merged (scm_pr_mirror.review_state) via the 8.8a `prBoard` sub-payload. No direct GitHub
      call; no direct re-query of the mirror beyond what 8.8a exposes.
  C2  ROW LINKS VIA sha-CORRELATION; UNCORRELATED ROWS RENDER WITHOUT LINK (AC2): each row links to its
      producing Run/branch through the mirror's `head_sha→run.commit_sha` correlation (§13 r24). Where a PR
      is NOT correlated to a Run, the row renders in its state group WITHOUT a Run link — the link is NEVER
      fabricated.
  C3  ONE SCM MIRROR, NO SECOND GITHUB INTEGRATION (AC3, Theme H crux): the board reads exclusively from
      `scm_pr_mirror` via 8.8a — it does NOT open a second GitHub integration, token, or webhook. The single
      repo-sync reconciler (§5.4, ADR-018) is the only GitHub touch; the dashboard is a read model over that
      mirror.
  C4  DEGRADES TO EXPLICIT EMPTY ON NO REPO SYNCED (AC4, availability crux): when `prBoard` is
      `{available:false}` (no repo synced / Epic 11.3 absent), the board renders an EXPLICIT empty state
      ("No repository synced"), NOT a hard failure, NOT a fabricated PR, NOT a whole-dashboard error.
      Distinguishable from "synced repo with zero open PRs."
  C5  RBAC THROUGH 8.8A; NO SECOND AUTHZ (AC5): the `prBoard` sub-payload was already server-filtered by
      8.8a's deny-by-default wall. This story adds NO client-side authz predicate.
  C6  REAL ROWS ONLY (AC6, FR-I3): every row is a real `scm_pr_mirror` PR (via 8.8a). No placeholder or
      synthesized PR; a degraded source → empty state (AC4).
  C7  NO NEW DOMAIN METRIC (AC7, NFR-OBS3): ordinary console/BFF request telemetry only; no new PR metric;
      no per-item ids (pr.id/run.id) as metric labels; sync telemetry belongs to Epic 11 / §5.4.

Mutation-proof harness:
  --mutate=GITHUB_DIRECT    call GitHub API directly instead of reading 8.8a/scm_mirror -> C3 RED
  --mutate=FAKE_SHA_LINK    fabricate a Run link for an uncorrelated PR                 -> C2 RED
  --mutate=HARD_FAIL        return 5xx / throw when prBoard is unavailable              -> C4 RED
  --mutate=FAKE_PR          render a synthesized PR row when source is degraded         -> C6 RED
  --mutate=CLIENT_AUTHZ     add a client-side authz predicate                           -> C5 RED
  --mutate=WRONG_GROUPS     group by something other than review_state four values      -> C1 RED
  --mutate=PERITEM_LABEL    put pr.id on a metric label                                 -> C7 RED

Baseline exits 0; each --mutate exits 1.
"""
import sys

REVIEW_STATES = {"ready-for-review", "draft", "blocked", "merged"}

# 8.8a prBoard sub-payload — repo synced, mix of correlated and uncorrelated PRs.
SCENARIO_SYNCED = {
    "available": True,
    "data": [
        {"pr_id": "pr-1", "title": "Add SSE hub", "review_state": "ready-for-review",
         "head_sha": "abc123", "run_commit_sha": "abc123", "correlated_run": "r-21"},
        {"pr_id": "pr-2", "title": "WIP: rate-limit", "review_state": "draft",
         "head_sha": "def456", "run_commit_sha": None, "correlated_run": None},  # uncorrelated
        {"pr_id": "pr-3", "title": "Hotfix auth", "review_state": "blocked",
         "head_sha": "ghi789", "run_commit_sha": "ghi789", "correlated_run": "r-22"},
        {"pr_id": "pr-4", "title": "Epic 11.1 scm", "review_state": "merged",
         "head_sha": "jkl012", "run_commit_sha": "jkl012", "correlated_run": "r-20"},
    ]
}
# 8.8a prBoard sub-payload — no repo synced (Epic 11.3 absent).
SCENARIO_UNSYNCED = {"available": False, "reason": "scm_not_synced"}


def render_board(design, payload, mut=None):
    """Return (board, meta) representing the rendered PR mini-board surface."""
    # C3 — data source: scm_mirror via 8.8a vs direct GitHub API.
    source = "github_direct_api" if mut == "GITHUB_DIRECT" else design["source"]

    # C1 — grouping axis.
    group_by = "custom" if mut == "WRONG_GROUPS" else design["group_by"]

    # C4 — degradation: explicit empty vs hard failure vs fake PR.
    fake_pr_on_degrade = (mut == "FAKE_PR") or design.get("fake_pr_on_degrade", False)
    hard_fail = (mut == "HARD_FAIL") or design.get("hard_fail", False)

    # C5 — client-side authz.
    client_authz = (mut == "CLIENT_AUTHZ") or design.get("client_authz", False)

    # C7 — metric labels.
    metric_labels = set(design["metric_labels"])
    if mut == "PERITEM_LABEL":
        metric_labels = metric_labels | {"pr.id"}

    if not payload["available"]:
        if hard_fail:
            return None, {"source": source, "http": 500, "metric_labels": metric_labels,
                          "client_authz": client_authz, "group_by": group_by}
        if fake_pr_on_degrade:
            rows = [{"pr_id": "pr-FAKE", "title": "Placeholder PR", "review_state": "draft",
                     "run_link": None, "fabricated": True}]
        else:
            rows = []
        return {"groups": {}, "rows": rows, "empty": True, "empty_reason": "no_repo_synced",
                "fabricated": fake_pr_on_degrade}, \
               {"source": source, "http": 200, "metric_labels": metric_labels,
                "client_authz": client_authz, "group_by": group_by}

    rows = []
    for pr in payload["data"]:
        correlated = (pr["run_commit_sha"] is not None and
                      pr["head_sha"] == pr["run_commit_sha"])
        if correlated:
            run_link = pr["correlated_run"]
        elif mut == "FAKE_SHA_LINK" or design.get("fake_sha_link", False):
            run_link = "r-FAKE"  # fabricated correlation
        else:
            run_link = None  # honest: no correlation, no link

        state = pr["review_state"] if group_by == "review_state" else "custom_group"
        rows.append({
            "pr_id": pr["pr_id"], "title": pr["title"],
            "review_state": state, "run_link": run_link,
            "correlated": correlated, "fabricated_link": (not correlated and run_link is not None),
        })

    groups = {}
    for r in rows:
        groups.setdefault(r["review_state"], []).append(r["pr_id"])

    return {"groups": groups, "rows": rows, "empty": False, "fabricated": False}, \
           {"source": source, "http": 200, "metric_labels": metric_labels,
            "client_authz": client_authz, "group_by": group_by}


CONFORMANT = {
    "source": "8.8a_scm_mirror",          # C1/C3 — reads 8.8a `prBoard`; no direct GitHub call
    "group_by": "review_state",            # C1 — grouped by the four scm_pr_mirror review_state values
    "fake_sha_link": False,                # C2 — uncorrelated PRs render without a link
    "fake_pr_on_degrade": False,           # C4/C6 — degraded → explicit empty, no fake PR
    "hard_fail": False,                    # C4 — no 5xx on no-repo
    "client_authz": False,                 # C5 — no client-side authz
    "metric_labels": set(),               # C7 — no per-item labels
}
NAIVE = {
    "source": "github_direct_api",        # C3 fail — second GitHub integration
    "group_by": "custom",                  # C1 fail — wrong grouping axis
    "fake_sha_link": True,                 # C2 fail — fabricates correlations
    "fake_pr_on_degrade": True,           # C6 fail — synthesizes PR rows on degrade
    "hard_fail": True,                     # C4 fail — 5xx when no repo
    "client_authz": True,                  # C5 fail — client-side authz predicate
    "metric_labels": {"pr.id", "run.id"}, # C7 fail — per-item labels
}


def evaluate(design, mut):
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    # Scenario A: repo synced
    board_ok, meta_ok = render_board(design, SCENARIO_SYNCED, mut=mut)
    # Scenario B: no repo synced
    board_deg, meta_deg = render_board(design, SCENARIO_UNSYNCED, mut=mut)

    # C1 — groups match the four review_state values from the mirror; no custom/wrong grouping.
    check("C1", meta_ok["group_by"] == "review_state",
          f"board groups by {meta_ok['group_by']!r} instead of the scm_pr_mirror `review_state` values "
          f"(ready-for-review/draft/blocked/merged) — must group by the mirror's four states (AC1)")
    if board_ok:
        bad_groups = sorted(g for g in board_ok["groups"] if g not in REVIEW_STATES)
        check("C1", not bad_groups,
              f"board contains group(s) {bad_groups} not in the four review_state values "
              f"{sorted(REVIEW_STATES)} — grouping must match the mirror exactly (AC1)")
        check("C1", len(board_ok["rows"]) == len(SCENARIO_SYNCED["data"]),
              f"board has {len(board_ok['rows'])} rows for {len(SCENARIO_SYNCED['data'])} mirror PRs "
              f"— all mirror rows must render (non-vacuous; AC1)")

    # C2 — uncorrelated PRs render without a fabricated link.
    if board_ok:
        faked_links = [r["pr_id"] for r in board_ok["rows"] if r.get("fabricated_link")]
        check("C2", not faked_links,
              f"PR(s) {faked_links} have a fabricated Run link — uncorrelated PRs must render without a "
              f"Run link; the correlation is head_sha→run.commit_sha only (§13 r24; AC2)")
        # positive control: correlated PRs DO have a link.
        corr = [r for r in board_ok["rows"] if r.get("correlated")]
        no_link = [r["pr_id"] for r in corr if not r.get("run_link")]
        check("C2", not no_link,
              f"correlated PR(s) {no_link} have no Run link — a correlated PR must link to its producing "
              f"Run/branch (non-vacuous, AC2)")

    # C3 — one SCM mirror, no second GitHub integration.
    check("C3", meta_ok["source"] == "8.8a_scm_mirror",
          f"PR board reads from {meta_ok['source']!r} — it must read exclusively from the `scm_pr_mirror` "
          f"via 8.8a; NO direct GitHub API call, NO second integration/token/webhook (AC3/Theme H/ADR-018)")

    # C4 — degraded (no repo synced) → explicit empty board, HTTP 200, never 5xx.
    check("C4", meta_deg.get("http") == 200,
          f"board returned HTTP {meta_deg.get('http')} with no repo synced — must return HTTP 200 with an "
          f"explicit empty board (8.8a per-tile degrade; AC4)")
    if board_deg is not None:
        check("C4", board_deg["empty"] and not board_deg.get("fabricated"),
              f"degraded board: empty={board_deg['empty']}, fabricated={board_deg.get('fabricated')} — "
              f"must be an explicit empty state (not a fabricated PR, not a hard failure; AC4)")

    # C5 — no client-side authz.
    check("C5", not meta_ok["client_authz"],
          "board adds a client-side authz predicate — the `prBoard` sub-payload was already server-filtered "
          "by 8.8a's deny-by-default RBAC wall; no second filter here (AC5/§12.3)")

    # C6 — real rows only; no fabricated row in either the synced or the degraded scenario.
    if board_ok:
        faked_rows = [r["pr_id"] for r in board_ok["rows"] if r.get("fabricated")]
        check("C6", not faked_rows,
              f"board contains fabricated row(s) {faked_rows} in the synced scenario — every row must be a "
              f"real scm_pr_mirror PR (via 8.8a); no placeholder or synthesized PR (AC6/FR-I3)")
    # C6 also tested against the degraded scenario: evaluate SCENARIO_UNSYNCED with an explicit empty board.
    # The NAIVE design sets fake_pr_on_degrade=True — render a separate degraded board for the NAIVE path
    # where hard_fail is bypassed by checking the dedicated degraded render.
    # pass the mut so FAKE_PR is injected, but force hard_fail off so the degrade path is reachable.
    # When mut=HARD_FAIL, the test is whether hard_fail → 5xx; the fake-PR degrade path is separate.
    _safe_mut = None if mut == "HARD_FAIL" else mut
    _board_deg_nofail, _meta_deg_nofail = render_board(
        {**design, "hard_fail": False}, SCENARIO_UNSYNCED, mut=_safe_mut)
    faked_on_deg = [r["pr_id"] for r in (_board_deg_nofail or {}).get("rows", []) if r.get("fabricated")]
    check("C6", not faked_on_deg,
          f"degraded board contains fabricated row(s) {faked_on_deg} — a degraded source renders the "
          f"explicit empty state ('No repository synced'), never a fake PR (AC6/FR-I3)")

    # C7 — no per-item ids as metric labels.
    FORBIDDEN = {"pr.id", "run.id", "user.id", "model"}
    banned = sorted(meta_ok["metric_labels"] & FORBIDDEN)
    check("C7", not banned,
          f"metric label(s) {banned} are per-item/model identifiers — span/exemplar only, never a metric "
          f"label (NFR-OBS3; PR mirror sync telemetry belongs to Epic 11/§5.4, not here; AC7)")

    return fails


def run(mut=None):
    naive_fails = evaluate(NAIVE, None)
    naive_hit = {inv for inv, _ in naive_fails}
    conf_fails = evaluate(CONFORMANT, mut)
    return naive_fails, naive_hit, conf_fails


MUTANTS = {
    "WRONG_GROUPS": "C1", "FAKE_SHA_LINK": "C2", "GITHUB_DIRECT": "C3", "HARD_FAIL": "C4",
    "CLIENT_AUTHZ": "C5", "FAKE_PR": "C6", "PERITEM_LABEL": "C7",
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
        print(f"[pr] TEETH LOST — naive panel no longer trips {missing_teeth}:")
        for inv, d in naive_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[pr] FAIL — §8.8d PR mini-board violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] naive second-github-integration : {len(naive_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(naive_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] §8.8d conformant mini-board     : 0 violation(s); "
              "review_state-grouped, honest-sha-correlation, one-scm-mirror, "
              "explicit-empty-on-no-repo, no-second-authz, real-rows-only, bounded-cardinality")
        print("[pr] PASS")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)})" if others else ""
        print(f"[pr] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[pr] SURVIVED — --mutate={mut} did NOT trip {expected}; tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
