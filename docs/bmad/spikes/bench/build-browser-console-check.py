#!/usr/bin/env python3
"""Story 8.7e falsification — the console three-pane build browser (tree -> diff -> code).

This is the LAST slice of Epic 8.7 (deps 8.7a -> {8.7b,8.7c} -> 8.7d -> 8.7e). 8.7a-c own the git
projection + live/completed backends; 8.7d owns the BFF endpoints + the blocking NFR-SEC5 per-principal
scoping gate. 8.7e owns exactly ONE thing the others do not: the **console composition** — a strictly
read-only three-pane surface (changed-file tree LEFT -> per-file diff CENTER -> code-view toggle) that
mirrors mock `06-build-browser` (light + dark, FR-F7), reachable from BOTH the Run detail (Epic 8.11
"build output" tab) and artifact inspection (Epic 8.3), that reads the Run's build view ONLY through the
four 8.7d endpoints:

    GET /api/runs/{runId}/build/tree            (changed-file set; polled while live)
    GET /api/runs/{runId}/build/diff?path=<p>   (per-file unified diff; PULL on demand)
    GET /api/runs/{runId}/build/file?path=<p>&ref=run|base   (code view; PULL on demand)
    GET /api/runs/{runId}/build/meta            (live flag + snapshot presence; polled while live)

The load-bearing claim of THIS story is that the console is a **legibility surface, not an IDE (scope
guard R6)** and a **pure consumer of the 8.7d edge**: it never touches git / the Go apiserver / kube
directly (§13 one choke point), so it inherits the per-principal 404 gate for free — a `404` from the
gate renders as a neutral "no build view" that is INDISTINGUISHABLE from a genuinely-missing Run, and
the gate's id-only WARN audit log is NEVER surfaced to the operator. A live Run POLLS tree/meta on the
existing cadence and PULLS diffs/files on demand (no bespoke SSE channel — diffs are pull); a completed
Run renders statically from the 8.7c snapshot with NO live pod. Caps (`truncated`/`tooLarge`/`binary`)
render as explicit markers, never as an unbounded body and never silently dropped. The surface exposes
NO edit / apply / commit / save / run / terminal affordance and issues ONLY `GET` — the compose/write
surface (FR-F5, story 8.5) is a DIFFERENT screen.

A "the build browser rendered and I saw a diff" demo passes even if the console reads git directly
(bypassing the gate, leaking a same-Team peer's worktree), ships an "edit" button, streams diffs it
should pull, requires a live pod for a completed Run, renders a `tooLarge` blob raw, distinguishes a
per-principal deny from a missing Run (leaking existence), surfaces the audit log, or drops a pane in
dark mode. So this is a DIFFERENTIAL check over the CONSOLE COMPOSITION the surface would ship: we first
prove the naive "just render whatever git returns, add an edit button" anti-pattern is DETECTED
violating every invariant (real teeth), then prove the §6/R6 conformant composition violates nothing —
driving REAL renders (live Run, completed Run, no-snapshot Run, per-principal deny, missing Run; light
+ dark; select-file + code-view-toggle interactions) through an executable `render()` with a BFF spy
that records the transport + verb of every backend fetch.

Invariants (E1-E9, one family per AC of story 8.7e):
  E1  THREE-PANE COMPOSITION (AC1, mock 06): exactly three panes in reading order — changed-file tree
      (left) -> per-file diff (center) -> code-view (toggle) — and selecting a changed file in the tree
      DRIVES the diff pane (the panes are wired, not three independent widgets).
  E2  THROUGH THE 8.7d BFF ONLY (AC2, §13): every pane fetch uses the BFF transport — never git-direct,
      never apiserver-direct, never kube. Because the read rides the gate, a per-principal deny Run
      yields "no build view" and NEVER leaks worktree content (bypassing the BFF leaks it).
  E3  STRICTLY READ-ONLY, R6 (AC3): the surface exposes NO mutating affordance (edit/apply/commit/save/
      run/delete/terminal) and issues ONLY `GET` — a mutating verb is STRUCTURALLY absent from the
      component (the compose/write surface, story 8.5, is a different screen).
  E4  LIVE POLL / DIFF PULL; COMPLETED STATIC (AC4, §6): a live Run POLLS exactly {tree,meta} on the
      existing cadence and PULLS diffs/files on demand (no bespoke SSE; diff/file are never polled); a
      completed Run renders statically from the 8.7c snapshot with NO live pod.
  E5  TWO ENTRY POINTS, ONE COMPONENT (AC5): reachable from BOTH Run detail (8.11) and artifact
      inspection (8.3) — both routes land on the SAME component bound to the SAME runId, not two
      divergent implementations.
  E6  CAPS SURFACED, NEVER UNBOUNDED (AC6): a `tooLarge` diff / `binary` file / `truncated` tree renders
      the explicit marker — never an unbounded body, never a silently-dropped signal (passes the 8.7a
      caps through; does not re-cap).
  E7  DEGRADE LEGIBLY, EXISTENCE-HIDING (AC7): a gate `404` (per-principal deny) and a genuinely-missing
      Run render an IDENTICAL neutral "no build view" (the console never distinguishes them), the gate's
      id-only WARN audit log is NEVER surfaced to the operator, and a completed Run whose snapshot failed
      to emit renders an EXPLICIT "no build view" — surfaced, not a silent blank / silent 404.
  E8  CODE-VIEW TOGGLE = REF SWITCH (AC8): the code-view toggle reads `file?path=&ref=run|base` — a `ref`
      param on the SAME read endpoint via `GET`, never a new/mutating call; the default ref is `run`
      (the Run's own commit).
  E9  LIGHT + DARK PARITY (AC9, FR-F7): the surface renders identically in both themes — the pane
      structure and the control set are the same; no pane/affordance present in one theme and absent in
      the other.

Mutation harness (real teeth): every `--mutate=<NAME>` injects EXACTLY ONE defect into the CONFORMANT
console composition; the check then goes RED with the mapped invariant among the failures (siblings may
also trip — acceptable for overlapping composition invariants; the MAPPED tooth is the proof, ISI-2271
convention). Baseline `python3 build-browser-console-check.py` exits 0; each `--mutate=NAME` exits 1.

    --mutate=PANE_SWAP         reorder the panes (diff before tree)              -> E1
    --mutate=TREE_NOT_WIRED    selecting a tree file does not drive the diff     -> E1
    --mutate=GIT_DIRECT        read git directly, bypassing the BFF gate         -> E2
    --mutate=EDIT_AFFORDANCE   ship an edit/apply/commit control                 -> E3
    --mutate=MUTATING_VERB     issue a non-GET verb on the surface               -> E3
    --mutate=STREAM_DIFFS      poll/stream diffs instead of pulling on demand    -> E4
    --mutate=COMPLETED_NEEDS_POD a completed Run requires a live pod             -> E4
    --mutate=DIVERGENT_ENTRY   the two entry points bind different components    -> E5
    --mutate=UNBOUNDED_RENDER  render a tooLarge/binary body raw (no marker)     -> E6
    --mutate=DROP_MARKER       silently drop the cap marker                      -> E6
    --mutate=DENY_DISTINGUISH  render a deny differently from a missing Run      -> E7
    --mutate=SILENT_NOSNAP     a no-snapshot completed Run renders a silent blank -> E7
    --mutate=AUDIT_SURFACED    surface the gate's id-only WARN to the operator   -> E7
    --mutate=TOGGLE_MUTATES    the code-view toggle issues a mutating call       -> E8
    --mutate=DEFAULT_REF_BASE  default the code view to base, not the Run commit -> E8
    --mutate=THEME_ASYMMETRY   a control present in light is absent in dark      -> E9

Backends (owned elsewhere). The git projection (8.7a), the live A2A read verb (8.7b), the completed-Run
snapshot (8.7c), and the BFF endpoints + per-principal gate (8.7d) are the backends this console
consumes; this check stubs them behind a BFF spy. It guards ONLY the 8.7e console-composition contract
— exactly what design §6 (console surface) + R6 (read-only scope guard) + FR-F7 (mock 06 light+dark)
asked: prove the three-pane, gate-inheriting, read-only surface without a browser or a cluster.
"""

import argparse
import sys

# the three panes, in reading order: tree (left) -> diff (center) -> code (toggle).
PANES = ("tree", "diff", "code")
# endpoints that are PULLED on demand (never polled). tree/meta are the polled pair while live.
PULL_ENDPOINTS = ("diff", "file")
POLL_WHILE_LIVE = {"tree", "meta"}
# affordances that would make this an IDE, not a legibility surface (R6) — must never appear.
MUTATING_AFFORDANCES = {"edit", "apply", "commit", "save", "run", "delete", "terminal"}
# the two entry points that must land on the SAME component (8.11 Run detail, 8.3 artifact inspection).
ENTRY_POINTS = ("run-detail", "artifact-inspection")
BUILD_BROWSER = "build-browser"      # the one component both entry points bind to.

NO_BUILD_VIEW = "No build view"      # the ONE neutral label for deny AND genuinely-missing (E7).


# ---- the Run fixtures the BFF serves (owner's own reads unless `deny`) ------------------------------
RUN_DB = {
    "run-live":    {"live": True,  "deny": False, "snapshot": None,      "tree_truncated": False},
    "run-done":    {"live": False, "deny": False, "snapshot": "present", "tree_truncated": False},
    "run-nosnap":  {"live": False, "deny": False, "snapshot": "missing", "tree_truncated": False},
    "run-bigtree": {"live": True,  "deny": False, "snapshot": None,      "tree_truncated": True},
    "run-deny":    {"live": True,  "deny": True,  "snapshot": None,      "tree_truncated": False},
    # "run-missing" is intentionally absent -> 404, indistinguishable from a deny (E7).
}
CHANGED_FILES = [
    {"path": "mod.py",    "status": "M", "additions": 4, "deletions": 1},
    {"path": "huge.diff", "status": "M", "additions": 0, "deletions": 0},   # tooLarge diff
    {"path": "logo.png",  "status": "A", "additions": 0, "deletions": 0},   # binary
]


# ---- the executable BFF edge (8.7d) the console consumes; the spy records transport + verb ----------
class BFF:
    """Stubs the 8.7d endpoints. The per-principal gate lives HERE (§13). If the console bypasses the
    BFF (`data_source != "bff"`), the gate is NOT applied — a deny Run leaks worktree content."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.calls = []   # {endpoint, verb, transport, run_id, params, pull}

    def get(self, endpoint, run_id, params=None, pull=False, verb="GET"):
        transport = {"git_direct": "git", "apiserver_direct": "apiserver"}.get(
            self.cfg["data_source"], "bff")
        self.calls.append({"endpoint": endpoint, "verb": verb, "transport": transport,
                           "run_id": run_id, "params": dict(params or {}), "pull": pull})
        return self._respond(endpoint, run_id, params or {})

    def _respond(self, endpoint, run_id, params):
        run = RUN_DB.get(run_id)
        if run is None:                                   # genuinely-missing -> bare 404
            return {"status": 404}
        gated = self.cfg["data_source"] == "bff"          # the gate only runs on the BFF path
        if run["deny"] and gated:                         # per-principal deny -> 404 + id-only audit
            return {"status": 404, "deny_reason": "not-owner",
                    "_audit": {"level": "WARN", "run.id": run_id, "outcome": "denied"}}
        # (deny + NOT gated) falls through to a 200 — that IS the git-direct leak E2 detects.
        if endpoint == "meta":
            if run["snapshot"] == "missing":              # completed, snapshot emit failed (8.7c)
                return {"status": 200, "live": False, "build_view": "absent"}
            return {"status": 200, "live": run["live"], "commit": "abc123",
                    "artifacts": [{"kind": "build-snapshot"}]}
        if endpoint == "tree":
            return {"status": 200, "files": list(CHANGED_FILES),
                    "truncated": run["tree_truncated"]}
        if endpoint == "diff":
            p = params.get("path")
            if p == "huge.diff":
                return {"status": 200, "tooLarge": True, "binary": False}      # no body
            if p == "logo.png":
                return {"status": 200, "binary": True}                        # no body
            return {"status": 200, "unifiedDiff": "@@ -1 +1 @@\n-a\n+b",
                    "binary": False, "tooLarge": False}
        if endpoint == "file":
            return {"status": 200, "path": params.get("path"), "ref": params.get("ref", "run"),
                    "content": "print('x')", "binary": False, "tooLarge": False}
        return {"status": 404}


# ---- the console composition (THIS story) ----------------------------------------------------------
class ViewModel:
    def __init__(self):
        self.panes = []
        self.entry_component = None
        self.run_id_binding = None
        self.empty_state = None          # None => a live view is rendered
        self.live = None
        self.poll_targets = set()
        self.pulled = set()
        self.needs_live_pod = False
        self.completed_source = None
        self.tree_files = []
        self.diff_pane_path = None
        self.affordances = []
        self.theme_controls = set()
        self.markers = {}                # path (or "__tree__") -> "truncated"/"tooLarge"/"binary"/"unbounded"/None
        self.toggle = None


def _component_for(cfg, entry):
    if cfg["entry_binding"] == "divergent":
        # DEFECT: only the Run-detail route reaches the real build browser; artifact inspection forks off.
        return BUILD_BROWSER if entry == "run-detail" else "artifact-viewer-legacy"
    return BUILD_BROWSER


def _empty_state(cfg, kind, meta):
    """A gate 404 (deny) and a genuinely-missing Run must be INDISTINGUISHABLE (existence-hiding); the
    gate's id-only WARN audit log is never surfaced to the operator. A no-snapshot completed Run must be
    surfaced explicitly, not rendered as a silent blank."""
    if kind == "not-found":
        es = {"kind": "no-build-view", "label": NO_BUILD_VIEW,
              "distinguishes": False, "audit_surfaced": False}
        if cfg["distinguish_deny"] and meta.get("deny_reason"):
            es["label"] = f"Access denied: {meta['deny_reason']}"   # DEFECT: leaks that the Run exists
            es["distinguishes"] = True
        if cfg["audit_surfaced"] and meta.get("_audit"):
            es["audit_surfaced"] = True                             # DEFECT: audit log shown to operator
            es["audit"] = meta["_audit"]
        return es
    if kind == "snapshot-missing":
        if cfg["silent_nosnap"]:
            return None                                             # DEFECT: silent blank / silent 404
        return {"kind": "no-build-view", "label": f"{NO_BUILD_VIEW} — snapshot unavailable",
                "distinguishes": False, "audit_surfaced": False}
    return None


def _cap_marker(cfg, resp):
    """Surface the 8.7a caps as an explicit marker; never render an unbounded body, never drop the
    signal."""
    capped = resp.get("tooLarge") or resp.get("binary")
    if not capped:
        return None
    if cfg["drop_marker"]:
        return None                                                # DEFECT: signal silently dropped
    if not cfg["caps_surfaced"]:
        return "unbounded"                                         # DEFECT: raw unbounded body rendered
    return "tooLarge" if resp.get("tooLarge") else "binary"


def render(cfg, bff, run_id, entry="run-detail", theme="light", interaction=None):
    """Compose the three-pane build browser for one Run. Returns a ViewModel; every backend read goes
    through `bff` (recorded by the spy). `interaction` optionally carries {"select": path} (drive the
    diff pane) and {"toggle_code": path, "ref": run|base} (drive the code view)."""
    interaction = interaction or {}
    v = ViewModel()
    v.panes = list(cfg["pane_order"])                 # E1: reading order tree -> diff -> code
    v.entry_component = _component_for(cfg, entry)    # E5: both entry points -> same component
    v.run_id_binding = run_id
    v.affordances = list(cfg["affordances"])          # E3: read-only control set

    # meta first — it carries the live flag and whether a build view exists at all.
    meta = bff.get("meta", run_id)
    if meta["status"] == 404:                         # deny OR genuinely-missing -> identical empty state
        v.empty_state = _empty_state(cfg, "not-found", meta)
        v.theme_controls = _theme_controls(cfg, theme, v.affordances)
        return v
    if meta.get("build_view") == "absent":            # completed Run, snapshot emit failed (8.7c)
        v.empty_state = _empty_state(cfg, "snapshot-missing", meta)
        v.theme_controls = _theme_controls(cfg, theme, v.affordances)
        return v

    v.live = meta["live"]
    if v.live:                                        # E4: live -> poll {tree,meta}; diff/file pull
        v.poll_targets = set(cfg["poll_targets"])
        if cfg["stream_diffs"]:
            v.poll_targets.add("diff")                # DEFECT: diffs streamed/polled instead of pulled
    else:                                             # E4: completed -> static from the 8.7c snapshot
        v.poll_targets = set()
        v.needs_live_pod = cfg["completed_needs_pod"]
        v.completed_source = cfg["completed_source"]

    tree = bff.get("tree", run_id)
    v.tree_files = tree["files"]
    if tree.get("truncated"):
        v.markers["__tree__"] = "truncated" if (cfg["caps_surfaced"] and not cfg["drop_marker"]) \
            else ("unbounded" if not cfg["caps_surfaced"] else None)

    # select a changed file -> drive the diff pane (PULL on demand).
    if "select" in interaction:
        path = interaction["select"]
        if cfg["selection_wired"]:                    # E1: the tree drives the diff pane
            v.diff_pane_path = path
            diff = bff.get("diff", run_id, params={"path": path}, pull=True)
            v.pulled.add("diff")
            v.markers[path] = _cap_marker(cfg, diff)
        # else DEFECT (TREE_NOT_WIRED): the panes are independent; selection does nothing.

    # code-view toggle -> read file?path=&ref=run|base (PULL on demand); a ref switch, never a mutation.
    if "toggle_code" in interaction:
        path = interaction["toggle_code"]
        ref = interaction.get("ref", cfg["default_ref"])   # E8: default ref = run (the Run's commit)
        if cfg["toggle_mutates"]:
            bff.get("file", run_id, params={"path": path, "ref": ref}, pull=True, verb="POST")
            v.toggle = {"endpoint": "file", "ref": ref, "read_only": False}   # DEFECT
        else:
            bff.get("file", run_id, params={"path": path, "ref": ref}, pull=True)
            v.pulled.add("file")
            v.toggle = {"endpoint": "file", "ref": ref, "read_only": True}

    if cfg["mutating_verb"]:                           # DEFECT (MUTATING_VERB): a spurious write call
        bff.get("file", run_id, params={"path": "mod.py"}, verb="POST")

    v.theme_controls = _theme_controls(cfg, theme, v.affordances)
    return v


def _theme_controls(cfg, theme, affordances):
    controls = set(affordances)
    if cfg["theme_asymmetry"] and theme == "dark":
        controls.discard("toggle-code-view")           # DEFECT: a control missing in dark mode
    return controls


def _render(cfg, run_id, entry="run-detail", theme="light", interaction=None):
    """Drive one render with a fresh BFF spy; return (view, bff)."""
    bff = BFF(cfg)
    view = render(cfg, bff, run_id, entry=entry, theme=theme, interaction=interaction)
    return view, bff


# ---- invariants (E1-E9) ----------------------------------------------------------------------------
def check(cfg):
    v = []

    # E1 — three-pane composition (mock 06) + the tree drives the diff pane.
    vlive, _ = _render(cfg, "run-live", interaction={"select": "mod.py"})
    if list(vlive.panes) != list(PANES):
        v.append(f"E1 pane order {vlive.panes} != {list(PANES)} — tree(left) -> diff(center) -> "
                 f"code(toggle), mock 06 (AC1)")
    if vlive.diff_pane_path != "mod.py":
        v.append("E1 selecting a changed file in the tree did not drive the diff pane — the panes must "
                 "be wired, not three independent widgets (AC1)")

    # E2 — every pane fetch rides the BFF (never git/apiserver-direct); a deny Run never leaks content.
    vl2, bffl = _render(cfg, "run-live", interaction={"select": "mod.py", "toggle_code": "mod.py"})
    off_bff = sorted({c["transport"] for c in bffl.calls if c["transport"] != "bff"})
    if off_bff:
        v.append(f"E2 pane reads used transport(s) {off_bff} — the console must read ONLY through the "
                 f"8.7d BFF (§13 one choke point), never git/apiserver-direct (AC2)")
    vdeny, bffd = _render(cfg, "run-deny", interaction={"select": "mod.py"})
    if vdeny.empty_state is None or vdeny.tree_files:
        v.append("E2 a per-principal deny Run leaked build content — reading through the BFF gate must "
                 "yield 'no build view' (the git-direct bypass is the leak, AC2)")

    # E3 — strictly read-only, R6: no mutating affordance, and every verb is GET.
    vaff, bffv = _render(cfg, "run-live", interaction={"select": "mod.py", "toggle_code": "mod.py"})
    bad_aff = sorted(set(vaff.affordances) & MUTATING_AFFORDANCES)
    if bad_aff:
        v.append(f"E3 mutating affordance(s) {bad_aff} present — the build browser is read-only (R6); "
                 f"the compose/write surface (story 8.5) is a different screen (AC3)")
    bad_verbs = sorted({c["verb"] for c in bffv.calls if c["verb"] != "GET"})
    if bad_verbs:
        v.append(f"E3 non-GET verb(s) {bad_verbs} issued — a mutating verb must be structurally absent "
                 f"from the surface (AC3)")

    # E4 — live polls {tree,meta} + pulls diffs/files; completed is static from the snapshot, no pod.
    vlp, _ = _render(cfg, "run-live", interaction={"select": "mod.py", "toggle_code": "mod.py"})
    if not POLL_WHILE_LIVE <= vlp.poll_targets:
        v.append(f"E4 a live Run must poll {sorted(POLL_WHILE_LIVE)}; got {sorted(vlp.poll_targets)} (AC4)")
    stray = vlp.poll_targets - POLL_WHILE_LIVE
    if stray:
        v.append(f"E4 endpoint(s) {sorted(stray)} are polled — diffs/files are PULL on demand, never "
                 f"streamed/polled (no bespoke SSE channel, AC4)")
    if "diff" not in vlp.pulled:
        v.append("E4 the diff was not pulled on demand (AC4)")
    vdone, _ = _render(cfg, "run-done")
    if vdone.poll_targets:
        v.append(f"E4 a completed Run polled {sorted(vdone.poll_targets)} — it must render statically (AC4)")
    if vdone.needs_live_pod:
        v.append("E4 a completed Run required a live pod — it must render from the 8.7c snapshot (AC4)")
    if vdone.completed_source != "snapshot":
        v.append(f"E4 a completed Run's source is '{vdone.completed_source}', must be the snapshot (AC4)")

    # E5 — the two entry points land on the SAME component bound to the SAME runId.
    v_rd, _ = _render(cfg, "run-live", entry="run-detail")
    v_ai, _ = _render(cfg, "run-live", entry="artifact-inspection")
    if v_rd.entry_component != v_ai.entry_component or v_rd.entry_component != BUILD_BROWSER:
        v.append(f"E5 entry points bind different components (run-detail={v_rd.entry_component}, "
                 f"artifact-inspection={v_ai.entry_component}) — both must land on '{BUILD_BROWSER}' (AC5)")
    if v_rd.run_id_binding != v_ai.run_id_binding:
        v.append("E5 the two entry points bound different runIds — both open the same Run (AC5)")

    # E6 — caps surfaced as markers, never an unbounded body, never silently dropped.
    vh, _ = _render(cfg, "run-live", interaction={"select": "huge.diff"})
    if vh.markers.get("huge.diff") != "tooLarge":
        v.append(f"E6 a tooLarge diff rendered as '{vh.markers.get('huge.diff')}' — must be the "
                 f"'tooLarge' marker, never an unbounded body or a dropped signal (AC6)")
    vb, _ = _render(cfg, "run-live", interaction={"select": "logo.png"})
    if vb.markers.get("logo.png") != "binary":
        v.append(f"E6 a binary file rendered as '{vb.markers.get('logo.png')}' — must be the 'binary' "
                 f"marker (AC6)")
    vt, _ = _render(cfg, "run-bigtree")
    if vt.markers.get("__tree__") != "truncated":
        v.append(f"E6 a truncated tree rendered as '{vt.markers.get('__tree__')}' — must be the "
                 f"'truncated' marker (AC6)")

    # E7 — deny and missing are indistinguishable; audit not surfaced; no-snapshot surfaced explicitly.
    vden, _ = _render(cfg, "run-deny")
    vmis, _ = _render(cfg, "run-missing")
    if vden.empty_state is None:
        v.append("E7 a per-principal deny did not render an empty state (AC7)")
    elif vmis.empty_state is None:
        v.append("E7 a missing Run did not render an empty state (AC7)")
    else:
        if vden.empty_state["label"] != vmis.empty_state["label"] or vden.empty_state["distinguishes"]:
            v.append(f"E7 deny ('{vden.empty_state['label']}') is distinguishable from missing "
                     f"('{vmis.empty_state['label']}') — existence-hiding: both must read '{NO_BUILD_VIEW}' (AC7)")
        if vden.empty_state["audit_surfaced"]:
            v.append("E7 the gate's id-only WARN audit log was surfaced to the operator — it must never "
                     "reach a client-visible surface (AC7)")
    vns, _ = _render(cfg, "run-nosnap")
    if vns.empty_state is None:
        v.append("E7 a completed Run with no snapshot rendered a silent blank — a no-build-view must be "
                 "surfaced explicitly, not silently 404'd (design §7, AC7)")

    # E8 — the code-view toggle is a ref switch on the file endpoint (GET), default ref = run.
    vtog, bfft = _render(cfg, "run-live", interaction={"toggle_code": "mod.py", "ref": "base"})
    if vtog.toggle is None:
        v.append("E8 the code-view toggle is absent (AC8)")
    elif not vtog.toggle["read_only"]:
        v.append("E8 the code-view toggle issued a mutating call — it must be a `ref` switch on the file "
                 "endpoint (GET file?ref=run|base), never a new/mutating call (AC8)")
    file_calls = [c for c in bfft.calls if c["endpoint"] == "file"]
    if not file_calls:
        v.append("E8 the code-view toggle did not read the file endpoint (AC8)")
    elif any(c["verb"] != "GET" or "ref" not in c["params"] for c in file_calls):
        v.append("E8 the code-view toggle must GET file?path=&ref=run|base — a ref param, read-only (AC8)")
    vdef, bffdef = _render(cfg, "run-live", interaction={"toggle_code": "mod.py"})   # omit ref -> default
    ref_used = next((c["params"].get("ref") for c in bffdef.calls if c["endpoint"] == "file"), None)
    if ref_used != "run":
        v.append(f"E8 the default code-view ref is '{ref_used}' — must default to 'run' (the Run's own "
                 f"commit), not the base (AC8)")

    # E9 — light + dark parity: identical pane structure and control set (FR-F7).
    vlite, _ = _render(cfg, "run-live", theme="light", interaction={"select": "mod.py"})
    vdark, _ = _render(cfg, "run-live", theme="dark", interaction={"select": "mod.py"})
    if vlite.theme_controls != vdark.theme_controls:
        only_l = sorted(vlite.theme_controls - vdark.theme_controls)
        only_d = sorted(vdark.theme_controls - vlite.theme_controls)
        v.append(f"E9 light/dark control sets differ (light-only={only_l}, dark-only={only_d}) — the "
                 f"surface must render identically in both themes (mock 06 light+dark, AC9)")
    if list(vlite.panes) != list(vdark.panes):
        v.append("E9 the pane structure differs between themes (AC9)")

    return v


# ---- designs ---------------------------------------------------------------------------------------
def conformant_cfg():
    """The §6 / R6 / FR-F7 console composition that holds E1-E9."""
    return {
        "pane_order": list(PANES),                       # E1: tree -> diff -> code
        "selection_wired": True,                         # E1: the tree drives the diff pane
        "data_source": "bff",                            # E2: read only through the 8.7d BFF
        "affordances": ["select-file", "toggle-code-view", "copy-path", "theme"],  # E3: read-only
        "mutating_verb": False,                          # E3: only GET
        "poll_targets": {"tree", "meta"},                # E4: live polls tree+meta
        "stream_diffs": False,                           # E4: diffs are pull, never streamed
        "completed_needs_pod": False,                    # E4: completed renders from the snapshot
        "completed_source": "snapshot",                  # E4: the 8.7c build-snapshot artifact
        "entry_binding": "same_component",               # E5: both entries -> build-browser
        "caps_surfaced": True,                           # E6: render tooLarge/binary/truncated markers
        "drop_marker": False,                            # E6: never silently drop the signal
        "distinguish_deny": False,                       # E7: deny == missing (existence-hiding)
        "silent_nosnap": False,                          # E7: no-snapshot surfaced explicitly
        "audit_surfaced": False,                         # E7: id-only WARN never shown to the operator
        "toggle_mutates": False,                         # E8: toggle is a ref switch (GET), never a write
        "default_ref": "run",                            # E8: default to the Run's own commit
        "theme_asymmetry": False,                        # E9: light/dark parity
    }


def naive_cfg():
    """The 'just render whatever git returns, add an edit button' anti-pattern — every knob wrong. Must
    be DETECTED violating every invariant E1-E9, or the harness has no teeth."""
    c = conformant_cfg()
    c.update(
        pane_order=["diff", "tree", "code"],             # E1: panes reordered
        selection_wired=False,                           # E1: panes are independent widgets
        data_source="git_direct",                        # E2: reads git directly, bypassing the gate
        affordances=["select-file", "toggle-code-view", "edit", "apply", "commit"],  # E3: IDE controls
        mutating_verb=True,                              # E3: issues a POST
        stream_diffs=True,                               # E4: diffs streamed
        completed_needs_pod=True,                        # E4: a completed Run needs a live pod
        completed_source="ro-pod",                       # E4: not the snapshot
        entry_binding="divergent",                       # E5: the two entries fork
        caps_surfaced=False,                             # E6: render bodies raw
        drop_marker=True,                                # E6: drop cap markers
        distinguish_deny=True,                           # E7: deny != missing (existence leak)
        silent_nosnap=True,                              # E7: no-snapshot silent blank
        audit_surfaced=True,                             # E7: surface the audit log
        toggle_mutates=True,                             # E8: the toggle writes
        default_ref="base",                              # E8: default to base
        theme_asymmetry=True,                            # E9: a control missing in dark
    )
    return c


MUTATIONS = {
    "PANE_SWAP":           lambda d: d.update(pane_order=["diff", "tree", "code"]),
    "TREE_NOT_WIRED":      lambda d: d.update(selection_wired=False),
    "GIT_DIRECT":          lambda d: d.update(data_source="git_direct"),
    "EDIT_AFFORDANCE":     lambda d: d.update(
        affordances=["select-file", "toggle-code-view", "edit", "apply", "commit"]),
    "MUTATING_VERB":       lambda d: d.update(mutating_verb=True),
    "STREAM_DIFFS":        lambda d: d.update(stream_diffs=True),
    "COMPLETED_NEEDS_POD": lambda d: d.update(completed_needs_pod=True, completed_source="ro-pod"),
    "DIVERGENT_ENTRY":     lambda d: d.update(entry_binding="divergent"),
    "UNBOUNDED_RENDER":    lambda d: d.update(caps_surfaced=False),
    "DROP_MARKER":         lambda d: d.update(drop_marker=True),
    "DENY_DISTINGUISH":    lambda d: d.update(distinguish_deny=True),
    "SILENT_NOSNAP":       lambda d: d.update(silent_nosnap=True),
    "AUDIT_SURFACED":      lambda d: d.update(audit_surfaced=True),
    "TOGGLE_MUTATES":      lambda d: d.update(toggle_mutates=True),
    "DEFAULT_REF_BASE":    lambda d: d.update(default_ref="base"),
    "THEME_ASYMMETRY":     lambda d: d.update(theme_asymmetry=True),
}

# the invariant each mutation is PRIMARILY expected to flip RED (siblings may also trip — acceptable).
MUT_INVARIANT = {
    "PANE_SWAP": "E1", "TREE_NOT_WIRED": "E1", "GIT_DIRECT": "E2", "EDIT_AFFORDANCE": "E3",
    "MUTATING_VERB": "E3", "STREAM_DIFFS": "E4", "COMPLETED_NEEDS_POD": "E4", "DIVERGENT_ENTRY": "E5",
    "UNBOUNDED_RENDER": "E6", "DROP_MARKER": "E6", "DENY_DISTINGUISH": "E7", "SILENT_NOSNAP": "E7",
    "AUDIT_SURFACED": "E7", "TOGGLE_MUTATES": "E8", "DEFAULT_REF_BASE": "E8", "THEME_ASYMMETRY": "E9",
}

ALL_INVARIANTS = [f"E{i}" for i in range(1, 10)]


def main():
    ap = argparse.ArgumentParser(
        description="Story 8.7e console three-pane build-browser composition falsification (R6/FR-F7)")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS),
                    help="inject one defect into the conformant console composition")
    args = ap.parse_args()

    # 1) Teeth: the naive 'render whatever git returns, add an edit button' anti-pattern must violate
    #    EVERY invariant E1-E9.
    naive_v = check(naive_cfg())
    fams = {x.split()[0] for x in naive_v}
    print(f"[bb-console] NAIVE render-git-directly+edit-button anti-pattern : {len(naive_v)} violation(s) "
          f"across {len(fams)} invariant(s) -> DETECTED")
    missing = [e for e in ALL_INVARIANTS if e not in fams]
    if missing:
        print(f"[bb-console] FAIL — the naive anti-pattern did NOT trip {missing} (teeth lost)")
        for x in naive_v:
            print(f"[bb-console]   - {x}")
        return 1

    # 2) The conformant §6/R6 composition (optionally mutated).
    cfg = conformant_cfg()
    if args.mutate:
        MUTATIONS[args.mutate](cfg)
    v = check(cfg)

    if args.mutate:
        hit = sorted({x.split()[0] for x in v}, key=lambda s: int(s[1:]))
        expected = MUT_INVARIANT[args.mutate]
        print(f"[bb-console] conformant + --mutate={args.mutate}: {len(v)} violation(s) {hit}")
        for x in v:
            print(f"[bb-console]   - {x}")
        if expected in hit:
            others = [e for e in hit if e != expected]
            tag = f" (also tripped {others} — acceptable, {expected} is the mapped tooth)" if others else ""
            print(f"[bb-console] KILLED — --mutate={args.mutate} -> {expected} RED{tag}.")
            return 1
        print(f"[bb-console] SURVIVED — --mutate={args.mutate} did NOT trip {expected} (VACUOUS GUARD)")
        return 1

    if v:
        print("[bb-console] FAIL — the conformant composition violated an invariant:")
        for x in v:
            print(f"[bb-console]   - {x}")
        return 1
    print("[bb-console] PASS — the naive render-git+edit-button anti-pattern detectably breaks every")
    print("        invariant; the §6/R6/FR-F7 console composition holds E1-E9 (three-pane tree->diff->code ·")
    print("        through-the-8.7d-BFF-only · strictly read-only R6 · live-poll/diff-pull + completed-static ·")
    print("        two-entry-points-one-component · caps surfaced · deny==missing existence-hiding + no-snapshot")
    print("        surfaced · code-view toggle = ref switch · light+dark parity).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
