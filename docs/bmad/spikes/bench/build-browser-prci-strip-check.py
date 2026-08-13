#!/usr/bin/env python3
"""Story 8.7g falsification — the PR/CI header strip in the build browser (with Epic 11).

Epic 8.7 CLOSED at 8.7e (the three-pane console). 8.7g is a flagged fast-follow that adds exactly ONE
thing on top of the 8.7e composition: a **PR/CI header strip**. Given a Run whose PR/CI state has been
mirrored into `coord`/`meta` by SCM sync (Epic 11.4, design §5.4), when the operator opens the build
browser, `meta.prUrl` / `meta.ciStatus` render as a header strip above the three panes — and the CI
artifacts that SCM sync published link into the browser. Absent that mirror, the strip is simply not
there.

The load-bearing claim of THIS story — the one a "I opened a Run that had a PR and saw a link" demo does
NOT prove — is that the build browser **does not hard-depend on Epic 11 to ship**: it **degrades to
git-only**. A Run with no mirrored PR/CI (Epic 11 not landed yet, or SCM sync simply hasn't run for this
Run) MUST render the same three-pane browser it always did, with **no strip, no error, no perpetual
"loading PR…" state** — the strip's absence is the normal, non-degraded git-only view, not a failure.
And the strip is a **pure additive read** over the SAME 8.7d `meta` endpoint: it reads `prUrl`/`ciStatus`
from the gated `meta` payload, it does **not** open a second, ungated channel to GitHub / the CI provider
(that would be an existence-leaking side-channel *around* the per-principal 404 gate, and a new external
dependency the browser must not grow), and it stays **read-only (R6)** — no "merge PR", no "re-run CI",
no "approve" button; `prUrl` is an external link to the SCM, `ciStatus` is a faithful badge of whatever
was mirrored, never a fabricated "passing".

This is a DIFFERENTIAL check over the strip composition the surface would ship. It first proves the naive
"call GitHub directly, slap a merge button on, and hard-fail when there's no PR" anti-pattern is DETECTED
violating EVERY invariant G1–G7 (real teeth), then proves the §5.4/§6/R6 conformant strip violates
nothing — driving REAL renders (PR+CI mirrored, git-only / no mirror, PR-without-status partial mirror,
CI-artifacts published, per-principal deny, missing Run; light + dark) through an executable `render()`
with a spy that records the transport + verb of every backend fetch.

Invariants (G1–G7, one family per AC of story 8.7g):
  G1  STRIP WHEN MIRRORED (AC1, §5.4/§6): a Run whose `meta` carries `prUrl`/`ciStatus` renders a header
      strip whose PR link and CI badge are EXACTLY the mirrored `meta` values (not a live-fetched or
      invented value).
  G2  DEGRADE TO GIT-ONLY (AC2 — THE CRUX): a Run with NO mirrored `prUrl`/`ciStatus` renders the
      unchanged three-pane browser with NO strip and NO error / NO perpetual "loading PR" state — the
      build browser does NOT hard-depend on Epic 11; the strip's absence is the normal git-only view.
  G3  ADDITIVE READ-ONLY OVER meta ONLY (AC3, §13/R6): the strip reads `prUrl`/`ciStatus`/CI-artifacts
      ONLY from the gated 8.7d `meta` payload — never a direct GitHub/CI-provider call, never a second
      ungated channel — and exposes NO mutating affordance (merge-pr / rerun-ci / approve) and issues
      ONLY `GET`.
  G4  FAITHFUL BADGE, NEVER FABRICATED (AC4): `ciStatus` renders the mirrored value verbatim; a partial
      mirror (PR present, status absent) shows the PR link WITHOUT inventing a status — the strip never
      defaults an unknown CI outcome to "success"/"passing".
  G5  PUBLISHED CI ARTIFACTS LINK IN, NOT REBUILT (AC5): CI artifacts that SCM sync published are LINKED
      into the browser from the mirror (`meta.artifacts`), never re-fetched from the CI provider or
      rebuilt by the browser — and never silently dropped.
  G6  STRIP INHERITS THE PER-PRINCIPAL GATE (AC6, §5/NFR-SEC5): the strip rides the SAME gated `meta`
      read, so a per-principal deny / genuinely-missing Run renders "no build view" with NO strip and
      LEAKS NO `prUrl` — the strip is never a side-channel that reveals a Run (or its PR) the caller may
      not even learn exists.
  G7  LIGHT + DARK PARITY (AC7, FR-F7): the strip is present/absent identically in both themes and its
      control set is the same; the CI badge hue is theme-invariant (like the status dots, ISI-2279).

Mutation harness (real teeth): every `--mutate=<NAME>` injects EXACTLY ONE defect into the CONFORMANT
strip composition; the check then goes RED with the mapped invariant among the failures (siblings may
also trip — acceptable for overlapping composition invariants; the MAPPED tooth is the proof, ISI-2271
convention). Baseline `python3 build-browser-prci-strip-check.py` exits 0; each `--mutate=NAME` exits 1.

    --mutate=STRIP_SUPPRESSED   never render the strip even when meta carries it   -> G1
    --mutate=STRIP_HARD_DEP     no mirrored PR/CI -> error/blank, not git-only      -> G2
    --mutate=SCM_DIRECT         read prUrl/ciStatus from GitHub directly, not meta  -> G3
    --mutate=STRIP_MUTATES      ship a merge-pr / rerun-ci control (or non-GET)     -> G3
    --mutate=FABRICATE_STATUS   invent a CI status when the mirror had none         -> G4
    --mutate=ARTIFACTS_REBUILT  re-fetch CI artifacts from the provider, not link   -> G5
    --mutate=ARTIFACTS_DROPPED  drop the published CI-artifact links                -> G5
    --mutate=STRIP_LEAKS_DENY   render a strip (prUrl) on a deny/missing Run        -> G6
    --mutate=THEME_ASYMMETRY    strip present in light, absent in dark              -> G7

Backends (owned elsewhere). The git projection (8.7a), live/completed backends (8.7b/8.7c), the BFF
endpoints + per-principal gate (8.7d), the three-pane composition (8.7e), and the SCM-sync mirror that
populates `meta.prUrl`/`meta.ciStatus`/published artifacts (Epic 11.4) are all backends this strip
consumes; this check stubs `meta` behind a spy. It guards ONLY the 8.7g strip contract — exactly what
design §5.4 (SCM sync) + §6 (console PR/CI linkage) + R6 (read-only) + FR-F7 (mock 06 light+dark) asked:
prove the additive, git-only-degrading, gate-inheriting, read-only strip without a browser or a cluster.
"""

import argparse
import sys

# affordances that would make the strip an SCM control panel, not a read-only link strip (R6).
MUTATING_STRIP_AFFORDANCES = {"merge-pr", "rerun-ci", "approve-pr", "close-pr", "dispatch-ci"}
# read-only strip controls: an external PR link, the CI badge, and links to published CI artifacts.
READONLY_STRIP_AFFORDANCES = {"open-pr-link", "view-ci-status", "open-ci-artifact"}

NO_BUILD_VIEW = "No build view"     # the ONE neutral label for deny AND genuinely-missing (inherited G6).


# ---- the meta the SCM-sync mirror (Epic 11.4) serves through the 8.7d /meta endpoint ----------------
# `prUrl`/`ciStatus` are present ONLY when SCM sync has mirrored them; `ci-published` artifacts likewise.
RUN_DB = {
    # PR + CI both mirrored -> full strip.
    "run-pr-ci": {
        "status": 200, "live": True, "prUrl": "https://github.com/o/r/pull/7", "ciStatus": "success",
        "artifacts": [{"kind": "build-snapshot"},
                      {"kind": "ci-published", "name": "coverage.html", "uri": "s3://ci/cov-7.html"}],
    },
    # NO mirror (Epic 11 not landed, or SCM sync hasn't run) -> git-only, no strip, NO error.
    "run-git-only": {
        "status": 200, "live": False, "prUrl": None, "ciStatus": None,
        "artifacts": [{"kind": "build-snapshot"}],
    },
    # partial mirror: PR opened, CI not reported yet -> PR link, NO fabricated status.
    "run-pr-nostatus": {
        "status": 200, "live": True, "prUrl": "https://github.com/o/r/pull/8", "ciStatus": None,
        "artifacts": [{"kind": "build-snapshot"}],
    },
    # PR + failing CI + a published CI artifact -> strip links the artifact from the mirror.
    "run-ci-artifacts": {
        "status": 200, "live": False, "prUrl": "https://github.com/o/r/pull/9", "ciStatus": "failure",
        "artifacts": [{"kind": "build-snapshot"},
                      {"kind": "ci-published", "name": "junit.xml", "uri": "s3://ci/junit-9.xml"}],
    },
    # per-principal deny -> 404; the leaked prUrl models what an UNGATED side-channel would expose.
    "run-deny": {
        "status": 404, "_leaked_prurl": "https://github.com/o/r/pull/99",
        "_audit": {"level": "WARN", "run.id": "run-deny", "outcome": "denied"},
    },
    # "run-missing" is intentionally absent -> bare 404, indistinguishable from a deny (G6).
}
# what the CI provider would return if the browser called it DIRECTLY (SCM_DIRECT / ARTIFACTS_REBUILT):
# a LIVE value that DIVERGES from the mirror — proving the strip must reflect the mirror, not a re-fetch.
SCM_LIVE = {
    "run-pr-ci":        {"prUrl": "https://github.com/o/r/pull/7?live=1", "ciStatus": "running",
                         "artifacts": [{"kind": "ci-published", "name": "cov-live.html", "uri": "live"}]},
    "run-git-only":     {"prUrl": "https://github.com/o/r/pull/NEW", "ciStatus": "queued", "artifacts": []},
    "run-pr-nostatus":  {"prUrl": "https://github.com/o/r/pull/8", "ciStatus": "success", "artifacts": []},
    "run-ci-artifacts": {"prUrl": "https://github.com/o/r/pull/9", "ciStatus": "success",
                         "artifacts": [{"kind": "ci-published", "name": "junit-live.xml", "uri": "live"}]},
    "run-deny":         {"prUrl": "https://github.com/o/r/pull/99", "ciStatus": "success", "artifacts": []},
}


class Spy:
    """Records every backend read: transport ('meta' = the gated 8.7d /meta; 'scm-api' = a direct call
    to GitHub/the CI provider) + verb. Reading through 'meta' inherits the per-principal gate for free;
    a 'scm-api' call is an ungated side-channel the strip must never open."""

    def __init__(self):
        self.calls = []

    def meta(self, run_id, verb="GET"):
        self.calls.append({"transport": "meta", "verb": verb, "run_id": run_id})
        return RUN_DB.get(run_id, {"status": 404})

    def scm_api(self, run_id, verb="GET"):
        self.calls.append({"transport": "scm-api", "verb": verb, "run_id": run_id})
        return SCM_LIVE.get(run_id, {})


class ViewModel:
    def __init__(self):
        self.panes = ["tree", "diff", "code"]   # the 8.7e three-pane browser is ALWAYS the base.
        self.strip = None                        # None => no strip (git-only or empty state)
        self.strip_state = None                  # "rendered" | "git-only" | "error"
        self.strip_affordances = set()
        self.empty_state = None
        self.theme_strip_present = None


def _fetch_prci(cfg, spy, run_id, meta):
    """Source the strip fields. Conformant: read them from the already-fetched gated `meta`. Defect
    (SCM_DIRECT / ARTIFACTS_REBUILT): open an ungated `scm-api` channel whose LIVE values diverge from
    the mirror."""
    if cfg["strip_source"] == "scm-direct":
        live = spy.scm_api(run_id)                                  # DEFECT: ungated direct call
        return live.get("prUrl"), live.get("ciStatus"), \
            [a for a in live.get("artifacts", []) if a["kind"] == "ci-published"]
    pr = meta.get("prUrl")
    ci = meta.get("ciStatus")
    if cfg["artifacts_source"] == "rebuilt":
        live = spy.scm_api(run_id)                                  # DEFECT: re-fetch artifacts live
        arts = [a for a in live.get("artifacts", []) if a["kind"] == "ci-published"]
    else:
        arts = [a for a in meta.get("artifacts", []) if a["kind"] == "ci-published"]
    return pr, ci, arts


def render(cfg, spy, run_id, theme="light"):
    """Compose the build browser + (when mirrored) the PR/CI header strip for one Run."""
    v = ViewModel()
    meta = spy.meta(run_id)

    if meta.get("status") == 404:
        # deny OR genuinely-missing -> identical neutral empty state (inherited existence-hiding, G6).
        v.empty_state = NO_BUILD_VIEW
        if cfg["render_strip_on_deny"]:
            # DEFECT: fall back to an ungated/leaked prUrl and paint a strip on a Run we can't even see.
            leaked = spy.scm_api(run_id).get("prUrl") or meta.get("_leaked_prurl")
            v.strip = {"prUrl": leaked, "ciStatus": None, "artifacts": []}
            v.strip_state = "rendered"
        return v

    pr, ci, arts = _fetch_prci(cfg, spy, run_id, meta)

    mirrored = bool(pr or ci)
    if not mirrored:
        # NO mirrored PR/CI -> git-only. Conformant: absence is the normal view. Defect: hard-fail.
        if cfg["hard_dep"]:
            v.strip_state = "error"                                 # DEFECT: Epic-11 hard dependency
            v.empty_state = "PR/CI unavailable"
            v.panes = []                                            # browser broke without a PR
        else:
            v.strip_state = "git-only"                             # the strip is simply not there
        v.theme_strip_present = False
        return v

    if not cfg["strip_rendered"]:
        v.strip_state = "git-only"                                 # DEFECT (STRIP_SUPPRESSED): never shown
        v.theme_strip_present = False
        return v

    if cfg["theme_asymmetry"] and theme == "dark":
        v.strip_state = "git-only"                                 # DEFECT: strip vanishes in dark mode
        v.theme_strip_present = False
        return v

    if ci is None and cfg["fabricate_status"]:
        ci = "success"                                             # DEFECT (FABRICATE_STATUS)
    if cfg["artifacts_dropped"]:
        arts = []                                                  # DEFECT (ARTIFACTS_DROPPED)

    v.strip = {"prUrl": pr, "ciStatus": ci, "artifacts": arts}
    v.strip_state = "rendered"
    v.theme_strip_present = True
    v.strip_affordances = set(cfg["strip_affordances"])
    if arts:
        v.strip_affordances.add("open-ci-artifact")
    return v


def _render(cfg, run_id, theme="light"):
    spy = Spy()
    return render(cfg, spy, run_id, theme=theme), spy


# ---- invariants (G1-G7) ----------------------------------------------------------------------------
def check(cfg):
    v = []

    # G1 — a mirrored Run renders a strip whose PR link + CI badge are EXACTLY the meta values.
    vpc, _ = _render(cfg, "run-pr-ci")
    meta = RUN_DB["run-pr-ci"]
    if vpc.strip is None or vpc.strip_state != "rendered":
        v.append("G1 a Run with mirrored prUrl/ciStatus rendered no header strip — SCM-synced PR/CI must "
                 "render as a strip above the three panes (AC1, §5.4/§6)")
    else:
        if vpc.strip["prUrl"] != meta["prUrl"]:
            v.append(f"G1 the strip PR link '{vpc.strip['prUrl']}' != the mirrored meta.prUrl "
                     f"'{meta['prUrl']}' — the strip must reflect the mirror, not a live/invented value (AC1)")
        if vpc.strip["ciStatus"] != meta["ciStatus"]:
            v.append(f"G1 the strip CI badge '{vpc.strip['ciStatus']}' != the mirrored meta.ciStatus "
                     f"'{meta['ciStatus']}' (AC1)")

    # G2 — no mirror -> the unchanged three-pane browser, no strip, NO error/blank (THE crux).
    vgo, _ = _render(cfg, "run-git-only")
    if vgo.strip is not None or vgo.strip_state != "git-only":
        v.append(f"G2 a Run with no mirrored PR/CI has strip_state='{vgo.strip_state}' — with no mirror "
                 f"there must be NO strip (git-only), not a strip (AC2)")
    if vgo.empty_state is not None:
        v.append(f"G2 a Run with no mirrored PR/CI rendered '{vgo.empty_state}' — the build browser must "
                 f"NOT hard-depend on Epic 11; it degrades to git-only, never an error/blank (AC2)")
    if list(vgo.panes) != ["tree", "diff", "code"]:
        v.append(f"G2 a Run with no mirrored PR/CI lost its three panes ({vgo.panes}) — the git-only "
                 f"browser must render unchanged when the strip is absent (AC2)")

    # G3 — additive read over the gated meta ONLY; no SCM-direct call, no mutating affordance, only GET.
    vp3, spy3 = _render(cfg, "run-pr-ci")
    off = sorted({c["transport"] for c in spy3.calls if c["transport"] != "meta"})
    if off:
        v.append(f"G3 the strip read via transport(s) {off} — prUrl/ciStatus/CI-artifacts must come ONLY "
                 f"from the gated 8.7d meta, never a direct GitHub/CI-provider call (§13, AC3)")
    bad_aff = sorted(vp3.strip_affordances & MUTATING_STRIP_AFFORDANCES)
    if bad_aff:
        v.append(f"G3 mutating strip affordance(s) {bad_aff} present — the strip is read-only (R6): an "
                 f"external PR link + CI badge, never a merge/re-run/approve control (AC3)")
    bad_verbs = sorted({c["verb"] for c in spy3.calls if c["verb"] != "GET"})
    if bad_verbs:
        v.append(f"G3 non-GET verb(s) {bad_verbs} issued from the strip — a mutating verb must be "
                 f"structurally absent (AC3)")

    # G4 — a partial mirror (PR, no status) shows the PR link but NEVER a fabricated status.
    vns, _ = _render(cfg, "run-pr-nostatus")
    if vns.strip is None:
        v.append("G4 a partial mirror (PR opened, CI not reported) rendered no strip — the PR link must "
                 "still show (AC4)")
    else:
        if vns.strip["prUrl"] != RUN_DB["run-pr-nostatus"]["prUrl"]:
            v.append("G4 a partial mirror dropped the PR link (AC4)")
        if vns.strip["ciStatus"] is not None:
            v.append(f"G4 a partial mirror invented a CI status '{vns.strip['ciStatus']}' — an unknown CI "
                     f"outcome must stay absent, never default to 'success'/'passing' (AC4)")

    # G5 — published CI artifacts are LINKED from the mirror, never rebuilt/re-fetched, never dropped.
    vca, spyca = _render(cfg, "run-ci-artifacts")
    published = [a for a in RUN_DB["run-ci-artifacts"]["artifacts"] if a["kind"] == "ci-published"]
    if vca.strip is None or not vca.strip["artifacts"]:
        v.append("G5 a Run with published CI artifacts linked none into the browser — SCM-synced CI "
                 "artifacts must link in from the mirror (AC5)")
    elif {a["uri"] for a in vca.strip["artifacts"]} != {a["uri"] for a in published}:
        v.append(f"G5 the linked CI artifacts {sorted(a['uri'] for a in vca.strip['artifacts'])} != the "
                 f"mirrored set {sorted(a['uri'] for a in published)} — link the mirror, don't re-fetch (AC5)")
    if any(c["transport"] == "scm-api" for c in spyca.calls):
        v.append("G5 CI artifacts were re-fetched from the CI provider — the browser LINKS what SCM sync "
                 "published (meta.artifacts), it does not rebuild/re-fetch them (AC5)")

    # G6 — the strip inherits the gate: a deny / missing Run shows no strip and leaks no prUrl.
    for rid in ("run-deny", "run-missing"):
        vd, _ = _render(cfg, rid)
        if vd.empty_state != NO_BUILD_VIEW:
            v.append(f"G6 {rid} did not render the neutral '{NO_BUILD_VIEW}' (AC6)")
        if vd.strip is not None:
            v.append(f"G6 {rid} rendered a strip ({vd.strip!r}) — a deny/missing Run must show NO strip "
                     f"and LEAK NO prUrl; the strip must ride the same gated meta read, never an ungated "
                     f"side-channel (existence-hiding, §5/NFR-SEC5, AC6)")

    # G7 — light + dark parity: strip present/absent identically, same control set (FR-F7).
    vl, _ = _render(cfg, "run-pr-ci", theme="light")
    vk, _ = _render(cfg, "run-pr-ci", theme="dark")
    if vl.theme_strip_present != vk.theme_strip_present:
        v.append(f"G7 the strip is present in light={vl.theme_strip_present} but dark="
                 f"{vk.theme_strip_present} — it must render identically in both themes (mock 06, AC7)")
    if vl.strip_affordances != vk.strip_affordances:
        v.append(f"G7 the strip control set differs between themes (light-only="
                 f"{sorted(vl.strip_affordances - vk.strip_affordances)}, dark-only="
                 f"{sorted(vk.strip_affordances - vl.strip_affordances)}) (AC7)")

    return v


# ---- designs ---------------------------------------------------------------------------------------
def conformant_cfg():
    """The §5.4 / §6 / R6 / FR-F7 PR/CI strip that holds G1-G7."""
    return {
        "strip_rendered": True,          # G1: render the strip when meta carries prUrl/ciStatus
        "strip_source": "meta",          # G3: read prUrl/ciStatus from the gated 8.7d meta
        "hard_dep": False,               # G2: no mirror -> git-only, not an error
        "strip_affordances": {"open-pr-link", "view-ci-status"},   # G3: read-only links only
        "fabricate_status": False,       # G4: never invent a CI status
        "artifacts_source": "mirror",    # G5: link published CI artifacts from meta.artifacts
        "artifacts_dropped": False,      # G5: never drop the artifact links
        "render_strip_on_deny": False,   # G6: a deny/missing Run shows no strip, leaks no prUrl
        "theme_asymmetry": False,        # G7: light/dark parity
    }


def naive_cfg():
    """The 'call GitHub directly, add a merge button, hard-fail when there's no PR' anti-pattern — every
    knob wrong. Must be DETECTED violating every invariant G1-G7, or the harness has no teeth."""
    c = conformant_cfg()
    c.update(
        strip_source="scm-direct",       # G1 (diverges from mirror) + G3 (ungated direct call)
        hard_dep=True,                   # G2: no PR -> error, not git-only
        strip_affordances={"open-pr-link", "merge-pr", "rerun-ci"},   # G3: SCM control panel
        fabricate_status=True,           # G4: invent a status
        artifacts_source="rebuilt",      # G5: re-fetch artifacts live
        artifacts_dropped=True,          # G5: (belt-and-suspenders) also drop them
        render_strip_on_deny=True,       # G6: paint a strip on a Run we can't see
        theme_asymmetry=True,            # G7: strip missing in dark
    )
    return c


MUTATIONS = {
    "STRIP_SUPPRESSED":  lambda d: d.update(strip_rendered=False),
    "STRIP_HARD_DEP":    lambda d: d.update(hard_dep=True),
    "SCM_DIRECT":        lambda d: d.update(strip_source="scm-direct"),
    "STRIP_MUTATES":     lambda d: d.update(strip_affordances={"open-pr-link", "merge-pr", "rerun-ci"}),
    "FABRICATE_STATUS":  lambda d: d.update(fabricate_status=True),
    "ARTIFACTS_REBUILT": lambda d: d.update(artifacts_source="rebuilt"),
    "ARTIFACTS_DROPPED": lambda d: d.update(artifacts_dropped=True),
    "STRIP_LEAKS_DENY":  lambda d: d.update(render_strip_on_deny=True),
    "THEME_ASYMMETRY":   lambda d: d.update(theme_asymmetry=True),
}

# the invariant each mutation is PRIMARILY expected to flip RED (siblings may also trip — acceptable).
MUT_INVARIANT = {
    "STRIP_SUPPRESSED": "G1", "STRIP_HARD_DEP": "G2", "SCM_DIRECT": "G3", "STRIP_MUTATES": "G3",
    "FABRICATE_STATUS": "G4", "ARTIFACTS_REBUILT": "G5", "ARTIFACTS_DROPPED": "G5",
    "STRIP_LEAKS_DENY": "G6", "THEME_ASYMMETRY": "G7",
}

ALL_INVARIANTS = [f"G{i}" for i in range(1, 8)]


def main():
    ap = argparse.ArgumentParser(
        description="Story 8.7g PR/CI header-strip falsification (git-only degrade / R6 / §5.4 / FR-F7)")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS),
                    help="inject one defect into the conformant PR/CI strip composition")
    args = ap.parse_args()

    # 1) Teeth: the naive 'call GitHub directly + merge button + hard-fail-without-PR' anti-pattern must
    #    violate EVERY invariant G1-G7.
    naive_v = check(naive_cfg())
    fams = {x.split()[0] for x in naive_v}
    print(f"[bb-prci] NAIVE call-github-directly+merge-button+hard-dep anti-pattern : {len(naive_v)} "
          f"violation(s) across {len(fams)} invariant(s) -> DETECTED")
    missing = [g for g in ALL_INVARIANTS if g not in fams]
    if missing:
        print(f"[bb-prci] FAIL — the naive anti-pattern did NOT trip {missing} (teeth lost)")
        for x in naive_v:
            print(f"[bb-prci]   - {x}")
        return 1

    # 2) The conformant §5.4/§6/R6 strip (optionally mutated).
    cfg = conformant_cfg()
    if args.mutate:
        MUTATIONS[args.mutate](cfg)
    v = check(cfg)

    if args.mutate:
        hit = sorted({x.split()[0] for x in v}, key=lambda s: int(s[1:]))
        expected = MUT_INVARIANT[args.mutate]
        print(f"[bb-prci] conformant + --mutate={args.mutate}: {len(v)} violation(s) {hit}")
        for x in v:
            print(f"[bb-prci]   - {x}")
        if expected in hit:
            others = [g for g in hit if g != expected]
            tag = f" (also tripped {others} — acceptable, {expected} is the mapped tooth)" if others else ""
            print(f"[bb-prci] KILLED — --mutate={args.mutate} -> {expected} RED{tag}.")
            return 1
        print(f"[bb-prci] SURVIVED — --mutate={args.mutate} did NOT trip {expected} (VACUOUS GUARD)")
        return 1

    if v:
        print("[bb-prci] FAIL — the conformant strip composition violated an invariant:")
        for x in v:
            print(f"[bb-prci]   - {x}")
        return 1
    print("[bb-prci] PASS — the naive call-github+merge-button+hard-dep anti-pattern detectably breaks")
    print("        every invariant; the §5.4/§6/R6/FR-F7 PR/CI strip holds G1-G7 (strip when mirrored ·")
    print("        DEGRADE TO GIT-ONLY when absent · additive read-only over the gated meta ONLY · faithful")
    print("        badge never fabricated · published CI artifacts link in not rebuilt · inherits the")
    print("        per-principal gate — no strip/prUrl leak on deny · light+dark parity).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
