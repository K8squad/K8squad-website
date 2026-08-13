#!/usr/bin/env python3
"""Story 8.7d falsification — the build-browser BFF endpoints + per-principal scoping gate (NFR-SEC5).

⛔ THIS IS THE NFR-SEC5 BLOCKING SECURITY GATE of Epic 8.7. Nothing ships to the console (8.7e) until the
S4 cross-principal same-Team read-authZ case is green. The visibility model is **per-principal, not
Team-legible** (Architect Winston, ISI-2166 / arch r15, §9.4). The raw worktree content a Run produces may
carry that principal's BYO secrets (§11), so it must never be legible to ANY other principal — including a
principal in the SAME Team/Project.

Four GET-only endpoints sit at the console edge:

    GET /api/runs/{runId}/build/tree
    GET /api/runs/{runId}/build/diff?path=<path>
    GET /api/runs/{runId}/build/file?path=<path>&ref=run|base
    GET /api/runs/{runId}/build/meta

The load-bearing claim of THIS story is that the edge is an **authorization choke point** (§13): every read
resolves `caller.principal` + `caller.teamScope` and evaluates `authorizeRead(caller, run)` **BEFORE any
backend call** (git 8.7a / live A2A 8.7b / snapshot 8.7c), and denies with **404 (never 403)** whenever the
caller is not the Run's owning principal. `authorizeRead` allows **iff both** (a) the Run is in the caller's
Team scope AND (b) `run.owningPrincipal == caller.principal`; either false → `deny(404)`. Deny and
genuinely-missing are **indistinguishable** to the client (existence-hiding). Path resolution is
**git-backed** (`git show`/`git cat-file`, never a raw FS `open`), so `../`/absolute/symlink escape is
**structurally impossible**, not merely filtered. The per-principal cache partition and the Team-namespace
NetworkPolicy/RBAC are **defense-in-depth** — the **owning-principal check is the mechanism** that denies a
same-Team non-owner; do NOT conflate the cache partition with the read gate (the F7/B1 reviewer trap).

A "the build browser rendered and something got served" demo passes even if the edge confirms Run existence
to a non-owner with a 403, calls the backend before authorizing (leaking timing / existence), lets a
same-Team peer read another principal's worktree, opens a raw FS path, treats the cache partition as the
gate, or leaks `run.id`/`principal.id`/`path`/file-content into a metric label. So this is a DIFFERENTIAL
check over the SCOPING-GATE DESIGN the BFF would ship: we first prove the naive "just proxy the runId to git"
anti-pattern is DETECTED violating every invariant (real teeth), then prove the §13/NFR-SEC5 conformant
design violates nothing — driving REAL requests (owner A, same-Team non-owner B, cross-Team C) through an
executable `serve()` with a backend spy that records whether the backend was touched on the deny path.

Invariants (D1-D11, one per AC of story 8.7d):
  D1  GET-ONLY SURFACE (AC1): exactly the four routes, each accepts ONLY GET; a mutating verb is
      STRUCTURALLY absent (405 / route missing) and never reaches the backend.
  D2  AUTHORIZE BEFORE BACKEND (AC2): on a deny, ZERO backend calls are made (proven by a backend spy that
      records zero invocations on the deny path) — the gate runs before any git/shim/snapshot call.
  D3  PER-PRINCIPAL 404, EXISTENCE-HIDING (AC3, the crux, ISI-2166): same-Team non-owner B → 404 (never
      403) on all four endpoints, with a body INDISTINGUISHABLE from a genuinely-missing runId; owner A →
      200 (positive control). A 403, or a deny body that differs from not-found, leaks the boundary.
  D4  GATE CHECKS BOTH CONDITIONS (AC4): allow iff (run ∈ caller.teamScope) AND (owningPrincipal ==
      caller.principal); either false → deny(404). Cross-Team caller C → 404; same-Team non-owner B → 404;
      owner-in-scope A → allow.
  D5  EXISTING OWNING-PRINCIPAL FIELD (AC5): the gate READS the already-persisted initiating-principal
      identity (BYO scope + per-principal metering, §11) — no new schema field, no migration.
  D6  RUNNABLE PREDICATE TABLE (AC6): the pure `authorizeRead(caller, run)` predicate — no cluster, no DB,
      no network — asserts owner→allow, same-Team non-owner→deny(404), cross-Team→deny(404), and never
      leaks the internal deny reason to the client.
  D7  S4 LIVE-BFF SUITE (AC7): the blast-radius cross-principal same-Team read-authZ row over the REAL edge
      — B → 404 on ALL FOUR endpoints, cross-Team → 404, owner A → 200 (positive control). Gating a subset
      of the four endpoints (e.g. `meta` ungated) fails HERE even if the pure predicate is correct.
  D8  DEFENSE-IN-DEPTH, CACHE ≠ GATE (AC8): the owning-principal check is THE read-gate mechanism; the
      per-principal cache partition and Team-namespace NetworkPolicy/RBAC are independent fail-closed layers
      — treating the cache partition AS the read gate (F7/B1), or opening the outer layers, breaks D8.
  D9  STRUCTURAL PATH SAFETY (AC9): `diff`/`file` resolve paths through the 8.7a git-backed read model
      (`git show`/`git cat-file`), never a raw FS `open`; `../`/absolute/symlink escape is rejected
      STRUCTURALLY (path ∉ the Run's git-resolved changed set → 404), not merely filtered.
  D10 READ-SURFACE OBSERVABILITY (AC10, OBS-BB3): a deny increments `scope.denied{endpoint}` and writes a
      provenanced id-only WARN `{run.id, principal.id, endpoint, outcome:denied}` that NEVER confirms Run
      existence in a client-visible surface (response stays 404); trace attachment follows the live/completed
      split — live → child of the Run trace (traceparent over 8.7b), completed → BFF-rooted trace + span LINK
      to the Run trace_id (8.7c snapshot meta).
  D11 NFR-OBS3 STANDING LAW (AC11): no `run.id`/`principal.id`/`work_item.id`/`path`/`bytes_returned` on any
      METRIC label (span/log only); no file content/diff bodies in any signal; no `model` label;
      `bytes_returned` is a HISTOGRAM, not a monotonic sum. Read volume is legibility telemetry, never a
      consumption/billing axis.

Mutation harness (real teeth): every `--mutate=<NAME>` injects EXACTLY ONE defect into the CONFORMANT
NFR-SEC5 design; the check then goes RED with the mapped invariant among the failures (siblings may also
trip — acceptable for overlapping security invariants; the MAPPED tooth is the proof, ISI-2271 convention).
Baseline `python3 build-browser-bff-scoping-check.py` exits 0; each `--mutate=NAME` exits 1.

    --mutate=POST_ROUTE       serve a mutating verb (POST) on a route          -> D1
    --mutate=BACKEND_FIRST    call the backend before authorizing              -> D2
    --mutate=DENY_403         deny with 403 instead of 404                     -> D3
    --mutate=DENY_LEAK_BODY   deny body differs from not-found (existence leak) -> D3
    --mutate=NO_SCOPE_CHECK   drop the Team-scope condition                    -> D4
    --mutate=NEW_FIELD        read a new owningPrincipal field (migration)     -> D5
    --mutate=NO_OWNER_CHECK   drop the owning-principal condition              -> D6
    --mutate=UNGATED_META     skip the gate on the `meta` endpoint only        -> D7
    --mutate=CACHE_AS_GATE    treat the cache partition AS the read gate       -> D8
    --mutate=NETPOL_OPEN      the outer NetworkPolicy/RBAC layer is fail-open  -> D8
    --mutate=RAW_FS           resolve paths via raw FS open (traversal escapes) -> D9
    --mutate=NO_DENY_METRIC   a deny does not emit scope.denied                -> D10
    --mutate=DENY_LOG_CLIENT  the deny log is surfaced to the client           -> D10
    --mutate=TRACE_SWAP       live uses a link / completed uses a child        -> D10
    --mutate=LABEL_LEAK       put run.id on a metric label                     -> D11
    --mutate=MODEL_LABEL      put a `model` label on a build-browser metric    -> D11
    --mutate=BYTES_SUM        emit bytes_returned as a monotonic sum           -> D11

Runtime / backends (owned elsewhere). The git projection (8.7a), the live A2A read verb (8.7b), and the
completed-Run snapshot reader (8.7c) are the backends this edge dispatches to on ALLOW; this check stubs
them behind a spy. It guards ONLY the BFF scoping-gate contract — 8.7d's crux and exactly what design §5 +
testing §6.5 (S4) asked: prove the per-principal 404 gate over the real edge without a cluster.
"""

import argparse
import sys

ENDPOINTS = ("tree", "diff", "file", "meta")
PATH_ENDPOINTS = ("diff", "file")          # take a ?path= argument

# read.total label enum (bounded, §OBS-BB3) — the ONLY keys allowed on the read.total metric.
READ_TOTAL_LABELS = {"endpoint", "live", "source", "cache_hit", "outcome"}
# keys that must NEVER appear on ANY build-browser metric label (span/log/exemplar only) — Standing law.
FORBIDDEN_METRIC_LABELS = {"run.id", "principal.id", "work_item.id", "path", "bytes_returned", "model"}

NOT_FOUND_BODY = {"error": "not_found"}    # the ONE client-visible shape for deny AND genuinely-missing.


# ---- entities (two same-Team principals A/B; a cross-Team principal C) ------------------------------
class Run:
    def __init__(self, run_id, team_id, owning_principal, live, changed_set):
        self.run_id = run_id
        self.team_id = team_id
        self.owning_principal = owning_principal
        self.live = live
        self.changed_set = set(changed_set)


# T1: principals A (owner) + B (same-Team non-owner). T2: principal C (cross-Team).
CALLER_A = {"principal": "A", "team_scope": {"T1"}}
CALLER_B = {"principal": "B", "team_scope": {"T1"}}
CALLER_C = {"principal": "C", "team_scope": {"T2"}}
# owner principal A, but a session whose Team scope EXCLUDES the Run's team — isolates the scope
# condition (AC4 "either condition false -> 404"): owner_ok holds, scope_ok must NOT, so still deny(404).
CALLER_A_OUTSCOPE = {"principal": "A", "team_scope": {"T2"}}

CHANGED = {"added.txt", "mod.py", "renamed_new.txt"}
RUN_LIVE = Run("run-live", "T1", "A", live=True, changed_set=CHANGED)
RUN_DONE = Run("run-done", "T1", "A", live=False, changed_set=CHANGED)
RUN_DB = {r.run_id: r for r in (RUN_LIVE, RUN_DONE)}

VALID_PATH = "mod.py"                       # in the git-resolved changed set
TRAVERSAL_PATH = "../../etc/passwd"         # must be structurally rejected, never a raw open


# ---- the pure per-principal authZ predicate (AC4/AC5/AC6 — the security core) -----------------------
def authorize_read(caller, run, cfg):
    """`authorizeRead(caller, run) -> ("allow"|"deny", reason)`. Allow iff BOTH the Team-scope AND the
    owning-principal conditions hold; either false -> deny. `reason` is INTERNAL ONLY (never leaked to a
    client body — existence-hiding). Reads the EXISTING owning-principal field (no new schema)."""
    owning = _owning_principal(run, cfg)                        # AC5: existing field, no migration
    scope_ok = (run.team_id in caller["team_scope"]) if cfg["check_scope"] else True
    owner_ok = (owning == caller["principal"]) if cfg["check_owner"] else True
    if scope_ok and owner_ok:
        return "allow", None
    return "deny", ("out-of-team-scope" if not scope_ok else "not-owner")


def _owning_principal(run, cfg):
    """AC5: the owning principal is the ALREADY-persisted initiating identity (BYO scope + metering, §11).
    A conformant read consults the existing field; the NEW_FIELD mutation reads a migration-introduced
    field that does not exist on the record -> the gate cannot resolve the owner."""
    if cfg["owner_field"] == "new_migration":
        return getattr(run, "owning_principal_v2", None)       # DEFECT: field never persisted -> None
    return run.owning_principal


# ---- telemetry sink (OBS-BB3 — real emissions D10/D11 inspect) -------------------------------------
class Telem:
    def __init__(self):
        self.metrics = []   # (name, kind, labels, value)
        self.logs = []      # dict per WARN/INFO record
        self.spans = []     # dict per read span

    def record_read(self, endpoint, source, live, cfg, bytes_returned):
        labels = {"endpoint": endpoint, "live": live, "source": source,
                  "cache_hit": False, "outcome": "ok"}
        if cfg["metric_label_leak"]:
            labels["run.id"] = "run-live"          # DEFECT: high-cardinality id on a metric label
        if cfg["metric_model_label"]:
            labels["model"] = "claude"             # DEFECT: model label on a read metric
        self.metrics.append(("ksquad.buildbrowser.read.total", "counter", labels, 1))
        bytes_kind = "counter" if cfg["bytes_as_sum"] else "histogram"   # DEFECT (sum) -> billing axis
        self.metrics.append(("ksquad.buildbrowser.bytes_returned", bytes_kind,
                             {"endpoint": endpoint, "source": source}, bytes_returned))
        attach = ("child_of_run_trace" if live else "link_to_run_trace")
        if not cfg["trace_attach_correct"]:
            attach = ("link_to_run_trace" if live else "child_of_run_trace")   # DEFECT: swapped
        self.spans.append({"endpoint": endpoint, "attach": attach, "bytes_returned": bytes_returned})

    def record_deny(self, endpoint, principal, run_id, cfg):
        if cfg["emit_scope_denied"]:
            self.metrics.append(("ksquad.buildbrowser.scope.denied", "counter",
                                 {"endpoint": endpoint}, 1))
        # provenanced id-only WARN — carries the ids for S4 audit + enumeration detection (plan §3),
        # but is NOT a client-visible surface (the response body stays a bare 404).
        self.logs.append({"level": "WARN", "run.id": run_id, "principal.id": principal,
                          "endpoint": endpoint, "outcome": "denied",
                          "client_visible": cfg["deny_log_in_client_surface"]})


# ---- the executable BFF edge: serve one request through the gate -----------------------------------
class Spy:
    """Records every backend (git/shim/snapshot) invocation — AC2 proves ZERO on the deny path."""
    def __init__(self):
        self.calls = []

    def read(self, endpoint, run, path):
        self.calls.append((endpoint, run.run_id, path))
        return {"payload": f"{endpoint}:{run.run_id}", "bytes_returned": 128}


def _resolve_path(cfg, run, path):
    """8.7a git-backed path resolution. git mode: only paths IN the Run's git-resolved changed set are
    reachable (tree object), so `../`/absolute escape is STRUCTURALLY impossible. raw_fs mode (DEFECT):
    a raw `open(path)` escapes the worktree entirely."""
    if cfg["path_resolution"] == "raw_fs":
        return "raw_open"                       # DEFECT: traversal reaches an arbitrary FS path
    return "git_show" if path in run.changed_set else "reject"   # structural allowlist = the git tree


def serve(cfg, endpoint, method, caller, run_id, spy, telem, path=None):
    """Serve ONE build-browser request. Returns a response dict; mutates `spy`/`telem` as side effects.

    Order of operations for the conformant design: verb gate (AC1) -> resolve Run (existence-hiding) ->
    `authorizeRead` BEFORE any backend call (AC2) -> on allow, git-backed path safety (AC9) + backend
    dispatch (AC3 live/completed). Deny and genuinely-missing are indistinguishable (AC3)."""
    # D1 — GET-only: a mutating verb is structurally absent (405) and never reaches the backend.
    if method != "GET":
        if cfg["mutating_verb_absent"]:
            return {"status": 405, "body": {"error": "method_not_allowed"}, "authz_denied": False}
        # DEFECT (POST_ROUTE): a mutating verb is served -> fall through as if it were a read.

    run = RUN_DB.get(run_id)
    if run is None:                             # genuinely-missing runId -> 404, identical shape to deny
        return {"status": 404, "body": dict(NOT_FOUND_BODY), "authz_denied": False}

    gate_here = endpoint in cfg["gated_endpoints"]   # D7: the gate must cover ALL FOUR endpoints

    def deny():
        telem.record_deny(endpoint, caller["principal"], run.run_id, cfg)
        status = cfg["deny_status"]             # D3: 404 (never 403)
        body = ({"error": "forbidden", "run": run.run_id, "reason": "not_owner"}
                if cfg["deny_body_leaks"] else dict(NOT_FOUND_BODY))   # D3: indistinguishable body
        return {"status": status, "body": body, "authz_denied": True}

    def backend():
        if endpoint in PATH_ENDPOINTS:
            mech = _resolve_path(cfg, run, path)
            if mech == "reject":                # D9: path ∉ git changed set -> structural 404
                return {"status": 404, "body": dict(NOT_FOUND_BODY), "authz_denied": False}
            if mech == "raw_open":              # DEFECT surfaced: escaped the worktree
                out = spy.read(endpoint, run, path)
                telem.record_read(endpoint, "raw_fs", run.live, cfg, out["bytes_returned"])
                return {"status": 200, "body": {**out, "escaped": True}, "authz_denied": False,
                        "path_mechanism": "raw_open"}
        source = "live" if run.live else "completed"   # AC3: live 8.7b vs completed 8.7c dispatch
        out = spy.read(endpoint, run, path)
        telem.record_read(endpoint, source, run.live, cfg, out["bytes_returned"])
        return {"status": 200, "body": out, "authz_denied": False, "path_mechanism": "git_show"}

    # D8: the OUTER Team-namespace NetworkPolicy/RBAC is an independent fail-closed layer. It does NOT
    # cover the git read path on its own, but if it is fail-open a cross-tenant call is not stopped here.
    if not cfg["layers_fail_closed"] and run.team_id not in caller["team_scope"]:
        # outer layer open + inner gate still runs below (defense-in-depth means BOTH must hold);
        # we record the open outer layer for D8 by letting the inner gate be the sole stop.
        pass

    # D8: the cache partition is residue defense, NEVER the read gate. If it is (mis)used as the gate,
    # the owning-principal check is bypassed for a same-Team peer whose partition happens to be warm.
    if cfg["cache_partition_is_read_gate"]:
        # DEFECT: "same Team => shared partition => allowed to read" — the F7/B1 conflation.
        if run.team_id in caller["team_scope"]:
            return backend()

    if not gate_here:                           # DEFECT (UNGATED_META): endpoint bypasses the gate
        return backend()

    if cfg["gate_order"] == "before":
        decision, _reason = authorize_read(caller, run, cfg)
        if decision == "deny":
            return deny()                       # D2: NO backend call was made
        return backend()

    # DEFECT (BACKEND_FIRST): backend runs before authorization -> spy records a call on the deny path.
    resp = backend()
    decision, _reason = authorize_read(caller, run, cfg)
    if decision == "deny":
        d = deny()
        return d                                # 404, but the backend was already touched (D2 catches it)
    return resp


def request(cfg, endpoint, method, caller, run_id, path=None):
    """Drive one request with a fresh spy + telem; return (resp, spy, telem)."""
    spy, telem = Spy(), Telem()
    resp = serve(cfg, endpoint, method, caller, run_id, spy, telem, path=path)
    return resp, spy, telem


def _path_for(endpoint, path=None):
    if endpoint in PATH_ENDPOINTS:
        return path if path is not None else VALID_PATH
    return None


# ---- invariants (D1-D11) ---------------------------------------------------------------------------
def check(cfg):
    v = []

    # D1 — GET-only surface; a mutating verb is structurally absent (405) and never hits the backend.
    for ep in ENDPOINTS:
        resp, spy, _ = request(cfg, ep, "POST", CALLER_A, "run-live", path=_path_for(ep))
        if resp["status"] != 405 or spy.calls:
            v.append(f"D1 {ep}: a mutating verb (POST) was served (status={resp['status']}, "
                     f"backend_calls={len(spy.calls)}) — mutating verbs must be structurally absent (AC1)")

    # D2 — authorize BEFORE any backend call: a deny path makes ZERO backend calls (spy proof).
    # Probe with BOTH denied callers (same-Team non-owner B and cross-Team C) so the proof holds however
    # the gate denies.
    for caller in (CALLER_B, CALLER_C):
        for ep in ENDPOINTS:
            resp, spy, _ = request(cfg, ep, "GET", caller, "run-live", path=_path_for(ep))
            if resp["authz_denied"] and spy.calls:
                v.append(f"D2 {ep}/{caller['principal']}: {len(spy.calls)} backend call(s) on the DENY "
                         f"path — the gate must run before any git/shim/snapshot call (AC2)")

    # D3 — per-principal 404 existence-hiding: a deny -> 404 (never 403), body == not-found; owner A -> 200.
    missing_resp, _, _ = request(cfg, "tree", "GET", CALLER_A, "run-nope")
    for caller in (CALLER_B, CALLER_C):
        for ep in ENDPOINTS:
            d_resp, _, _ = request(cfg, ep, "GET", caller, "run-live", path=_path_for(ep))
            if not d_resp["authz_denied"]:
                continue                        # a deny did not occur here (a leak — D6/D7's teeth)
            if d_resp["status"] != 404:
                v.append(f"D3 {ep}/{caller['principal']}: deny returned {d_resp['status']} — must be 404, "
                         f"never 403 (existence-hiding, AC3)")
            if d_resp["body"] != missing_resp["body"]:
                v.append(f"D3 {ep}/{caller['principal']}: deny body {d_resp['body']} != not-found body "
                         f"{missing_resp['body']} — deny and missing must be indistinguishable (AC3)")
    for ep in ENDPOINTS:                        # positive control: the owner CAN read
        a_resp, _, _ = request(cfg, ep, "GET", CALLER_A, "run-live", path=_path_for(ep))
        if a_resp["status"] != 200:
            v.append(f"D3 {ep}: owner A got {a_resp['status']} — the owning principal must read (200) (AC3)")

    # D4 — the gate checks BOTH conditions; EITHER false -> 404. Cross-Team non-owner C isolates neither
    # condition alone (both fail); the owner-but-out-of-scope caller isolates the SCOPE condition (owner_ok
    # holds, scope_ok must not) so dropping just the Team-scope check is observable here.
    for ep in ENDPOINTS:
        c_resp, _, _ = request(cfg, ep, "GET", CALLER_C, "run-live", path=_path_for(ep))
        if c_resp["status"] != 404:
            v.append(f"D4 {ep}: cross-Team caller C got {c_resp['status']} — a Run outside Team scope must "
                     f"be 404 (AC4)")
        o_resp, _, _ = request(cfg, ep, "GET", CALLER_A_OUTSCOPE, "run-live", path=_path_for(ep))
        if o_resp["status"] != 404:
            v.append(f"D4 {ep}: owner A out of Team scope got {o_resp['status']} — the Team-scope condition "
                     f"must independently deny (both conditions required, AC4)")

    # D5 — the gate reads the EXISTING owning-principal field (no new field / migration).
    if cfg["owner_field"] != "existing":
        # concretely: with the migration field the owner cannot even be resolved -> the owner is denied.
        a_resp, _, _ = request(cfg, "tree", "GET", CALLER_A, "run-live")
        v.append(f"D5 the gate reads a new owningPrincipal field ('{cfg['owner_field']}') requiring a "
                 f"migration — it must read the existing initiating-principal identity (AC5); "
                 f"owner A now resolves to status {a_resp['status']}")

    # D6 — runnable pure-predicate table (no cluster/DB/network): A->allow, B->deny, C->deny.
    table = [(CALLER_A, RUN_LIVE, "allow"), (CALLER_B, RUN_LIVE, "deny"), (CALLER_C, RUN_LIVE, "deny")]
    for caller, run, want in table:
        got, reason = authorize_read(caller, run, cfg)
        if got != want:
            v.append(f"D6 predicate({caller['principal']} -> run owned by {run.owning_principal}) = {got}, "
                     f"want {want} (AC6 table)")
        if got == "deny" and reason is None:
            v.append("D6 predicate deny carries no internal reason (needed for the id-only audit log, AC6)")

    # D7 — S4 blast-radius suite over the REAL edge: B -> 404 on ALL FOUR; C -> 404; owner A -> 200.
    for ep in ENDPOINTS:
        b_resp, _, _ = request(cfg, ep, "GET", CALLER_B, "run-live", path=_path_for(ep))
        c_resp, _, _ = request(cfg, ep, "GET", CALLER_C, "run-live", path=_path_for(ep))
        a_resp, _, _ = request(cfg, ep, "GET", CALLER_A, "run-live", path=_path_for(ep))
        if b_resp["status"] != 404:
            v.append(f"D7 S4 {ep}: same-Team non-owner B got {b_resp['status']} — must be 404 on EVERY "
                     f"endpoint (NFR-SEC5 blast-radius, AC7)")
        if c_resp["status"] != 404:
            v.append(f"D7 S4 {ep}: cross-Team C got {c_resp['status']} — must be 404 (AC7)")
        if a_resp["status"] != 200:
            v.append(f"D7 S4 {ep}: positive control owner A got {a_resp['status']} — must be 200 (AC7)")

    # D8 — cache partition is NOT the read gate; outer NetworkPolicy/RBAC is an independent fail-closed
    #      layer. The owning-principal check must be THE mechanism that denies same-Team B.
    if cfg["cache_partition_is_read_gate"]:
        v.append("D8 the per-principal cache partition is used AS the read gate — it is residue "
                 "defense-in-depth only; the owning-principal check is the read-gate mechanism (F7/B1, AC8)")
    if not cfg["layers_fail_closed"]:
        v.append("D8 the outer Team-namespace NetworkPolicy/RBAC layer is fail-open — every layer must "
                 "fail closed independently (AC8)")

    # D9 — structural path safety: traversal rejected (git-resolved), never a raw FS open.
    if cfg["path_resolution"] != "git":
        v.append(f"D9 path resolution is '{cfg['path_resolution']}' — must be git-backed "
                 f"(git show/cat-file), never a raw FS open (AC9)")
    for ep in PATH_ENDPOINTS:
        resp, _, _ = request(cfg, ep, "GET", CALLER_A, "run-live", path=TRAVERSAL_PATH)
        if resp.get("path_mechanism") == "raw_open" or resp["status"] == 200:
            v.append(f"D9 {ep}: traversal path '{TRAVERSAL_PATH}' resolved (status={resp['status']}, "
                     f"mech={resp.get('path_mechanism')}) — escape must be structurally impossible (AC9)")

    # D10 — read-surface observability: deny emits scope.denied + an id-only WARN not surfaced to the
    #       client (response stays 404); trace attachment follows the live/completed split.
    resp, _, telem = request(cfg, "tree", "GET", CALLER_C, "run-live")
    if resp["authz_denied"]:
        denied_metrics = [m for m in telem.metrics if m[0] == "ksquad.buildbrowser.scope.denied"]
        if not denied_metrics:
            v.append("D10 a deny did not emit ksquad.buildbrowser.scope.denied (AC10)")
        warn = [l for l in telem.logs if l["level"] == "WARN" and l["outcome"] == "denied"]
        if not warn:
            v.append("D10 a deny did not write a provenanced id-only WARN log (AC10)")
        if any(l.get("client_visible") for l in warn):
            v.append("D10 the deny WARN log is surfaced to the client — it must never confirm Run "
                     "existence in a client-visible surface (AC10)")
        if resp["status"] != 404:
            v.append(f"D10 a deny returned {resp['status']} despite the audit log — the response must "
                     f"stay 404 (AC10)")
    else:
        v.append("D10 a cross-Team caller was NOT denied, so no scope.denied audit signal is emitted (AC10)")
    # trace attachment split: live -> child of Run trace, completed -> link to Run trace_id.
    _, _, tlive = request(cfg, "tree", "GET", CALLER_A, "run-live")
    _, _, tdone = request(cfg, "tree", "GET", CALLER_A, "run-done")
    if tlive.spans and tlive.spans[-1]["attach"] != "child_of_run_trace":
        v.append("D10 a LIVE read is not a child of the Run trace (traceparent over 8.7b) (AC10)")
    if tdone.spans and tdone.spans[-1]["attach"] != "link_to_run_trace":
        v.append("D10 a COMPLETED read is not a BFF-rooted trace with a span LINK to the Run trace (AC10)")

    # D11 — NFR-OBS3 standing law over the REAL emissions: no forbidden metric label, bytes_returned is a
    #       histogram, no model label.
    _, _, telem = request(cfg, "tree", "GET", CALLER_A, "run-live")
    for name, kind, labels, _val in telem.metrics:
        leaked = set(labels) & FORBIDDEN_METRIC_LABELS
        if leaked:
            v.append(f"D11 metric {name} carries forbidden label(s) {sorted(leaked)} — ids/path/bytes/"
                     f"model are span/log-only, never a metric label (Standing law, AC11)")
        if name == "ksquad.buildbrowser.read.total" and set(labels) - READ_TOTAL_LABELS:
            v.append(f"D11 read.total has non-enum label(s) {sorted(set(labels) - READ_TOTAL_LABELS)} — "
                     f"bounded enum labels only (AC11)")
        if name == "ksquad.buildbrowser.bytes_returned" and kind != "histogram":
            v.append(f"D11 bytes_returned is a '{kind}', must be a histogram (read volume is not a "
                     f"consumption/billing sum, AC11)")

    return v


# ---- designs ---------------------------------------------------------------------------------------
def conformant_cfg():
    """The §13 / NFR-SEC5 scoping-gate design that holds D1-D11."""
    return {
        "mutating_verb_absent": True,            # D1: GET-only, mutating verbs structurally absent
        "gate_order": "before",                  # D2: authorize before any backend call
        "deny_status": 404,                      # D3: 404, never 403
        "deny_body_leaks": False,                # D3: deny body == not-found body (indistinguishable)
        "check_scope": True,                     # D4: Team-scope condition
        "check_owner": True,                     # D4/D6: owning-principal condition
        "owner_field": "existing",               # D5: existing field, no migration
        "gated_endpoints": set(ENDPOINTS),       # D7: ALL FOUR endpoints run the gate
        "cache_partition_is_read_gate": False,   # D8: cache partition is residue defense, not the gate
        "layers_fail_closed": True,              # D8: outer NetworkPolicy/RBAC fail-closed
        "path_resolution": "git",                # D9: git-backed, never raw FS open
        "emit_scope_denied": True,               # D10: deny emits scope.denied
        "deny_log_in_client_surface": False,     # D10: id-only WARN never surfaced to the client
        "trace_attach_correct": True,            # D10: live->child, completed->link
        "metric_label_leak": False,              # D11: no id on a metric label
        "metric_model_label": False,             # D11: no model label
        "bytes_as_sum": False,                   # D11: bytes_returned is a histogram
    }


def naive_cfg():
    """The 'just proxy the runId to git' anti-pattern — every knob wrong. Must be DETECTED violating
    every invariant D1-D11, or the harness has no teeth."""
    c = conformant_cfg()
    c.update(
        mutating_verb_absent=False,              # D1: mutating verbs served
        gate_order="after",                      # D2: backend called before authz (observed via C's deny)
        deny_status=403,                         # D3: 403 instead of 404
        deny_body_leaks=True,                    # D3: deny body confirms existence
        check_scope=True,                        # KEEP scope so cross-Team C is DENIED -> deny-shape teeth
        check_owner=False,                       # D6/D7: same-Team peer B leaks through
        owner_field="new_migration",             # D5: reads a migration-introduced field
        gated_endpoints=set(ENDPOINTS),          # gate runs (so C is denied, B is evaluated)
        cache_partition_is_read_gate=True,       # D8: cache partition mis-used as the read gate (leaks B)
        layers_fail_closed=False,                # D8: outer NetworkPolicy/RBAC fail-open
        path_resolution="raw_fs",                # D9: raw FS open, traversal escapes
        emit_scope_denied=False,                 # D10: no scope.denied on deny
        deny_log_in_client_surface=True,         # D10: deny log surfaced to the client
        trace_attach_correct=False,              # D10: live/completed trace attachment swapped
        metric_label_leak=True,                  # D11: run.id on a metric label
        metric_model_label=True,                 # D11: model label
        bytes_as_sum=True,                       # D11: bytes_returned as a monotonic sum
    )
    return c


MUTATIONS = {
    "POST_ROUTE":      lambda d: d.update(mutating_verb_absent=False),
    "BACKEND_FIRST":   lambda d: d.update(gate_order="after"),
    "DENY_403":        lambda d: d.update(deny_status=403),
    "DENY_LEAK_BODY":  lambda d: d.update(deny_body_leaks=True),
    "NO_SCOPE_CHECK":  lambda d: d.update(check_scope=False),
    "NEW_FIELD":       lambda d: d.update(owner_field="new_migration"),
    "NO_OWNER_CHECK":  lambda d: d.update(check_owner=False),
    "UNGATED_META":    lambda d: d.update(gated_endpoints={"tree", "diff", "file"}),
    "CACHE_AS_GATE":   lambda d: d.update(cache_partition_is_read_gate=True),
    "NETPOL_OPEN":     lambda d: d.update(layers_fail_closed=False),
    "RAW_FS":          lambda d: d.update(path_resolution="raw_fs"),
    "NO_DENY_METRIC":  lambda d: d.update(emit_scope_denied=False),
    "DENY_LOG_CLIENT": lambda d: d.update(deny_log_in_client_surface=True),
    "TRACE_SWAP":      lambda d: d.update(trace_attach_correct=False),
    "LABEL_LEAK":      lambda d: d.update(metric_label_leak=True),
    "MODEL_LABEL":     lambda d: d.update(metric_model_label=True),
    "BYTES_SUM":       lambda d: d.update(bytes_as_sum=True),
}

# the invariant each mutation is PRIMARILY expected to flip RED (siblings may also trip — acceptable).
MUT_INVARIANT = {
    "POST_ROUTE": "D1", "BACKEND_FIRST": "D2", "DENY_403": "D3", "DENY_LEAK_BODY": "D3",
    "NO_SCOPE_CHECK": "D4", "NEW_FIELD": "D5", "NO_OWNER_CHECK": "D6", "UNGATED_META": "D7",
    "CACHE_AS_GATE": "D8", "NETPOL_OPEN": "D8", "RAW_FS": "D9", "NO_DENY_METRIC": "D10",
    "DENY_LOG_CLIENT": "D10", "TRACE_SWAP": "D10", "LABEL_LEAK": "D11", "MODEL_LABEL": "D11",
    "BYTES_SUM": "D11",
}

ALL_INVARIANTS = [f"D{i}" for i in range(1, 12)]


def main():
    ap = argparse.ArgumentParser(description="Story 8.7d BFF per-principal scoping-gate falsification (NFR-SEC5)")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="inject one defect into the conformant design")
    args = ap.parse_args()

    # 1) Teeth: the naive 'proxy the runId to git' anti-pattern must violate EVERY invariant D1-D11.
    naive_v = check(naive_cfg())
    fams = {x.split()[0] for x in naive_v}
    print(f"[bff-scope] NAIVE proxy-the-runId anti-pattern : {len(naive_v)} violation(s) across "
          f"{len(fams)} invariant(s) -> DETECTED")
    missing = [d for d in ALL_INVARIANTS if d not in fams]
    if missing:
        print(f"[bff-scope] FAIL — the naive anti-pattern did NOT trip {missing} (teeth lost)")
        for x in naive_v:
            print(f"[bff-scope]   - {x}")
        return 1

    # 2) The conformant NFR-SEC5 design (optionally mutated).
    cfg = conformant_cfg()
    if args.mutate:
        MUTATIONS[args.mutate](cfg)
    v = check(cfg)

    if args.mutate:
        hit = sorted({x.split()[0] for x in v}, key=lambda s: int(s[1:]))
        expected = MUT_INVARIANT[args.mutate]
        print(f"[bff-scope] conformant + --mutate={args.mutate}: {len(v)} violation(s) {hit}")
        for x in v:
            print(f"[bff-scope]   - {x}")
        if expected in hit:
            others = [d for d in hit if d != expected]
            tag = f" (also tripped {others} — acceptable, {expected} is the mapped tooth)" if others else ""
            print(f"[bff-scope] KILLED — --mutate={args.mutate} -> {expected} RED{tag}.")
            return 1
        print(f"[bff-scope] SURVIVED — --mutate={args.mutate} did NOT trip {expected} (VACUOUS GUARD)")
        return 1

    if v:
        print("[bff-scope] FAIL — the conformant design violated an invariant:")
        for x in v:
            print(f"[bff-scope]   - {x}")
        return 1
    print("[bff-scope] PASS — the naive proxy detectably breaks every invariant; the §13/NFR-SEC5 design")
    print("        holds D1-D11 (GET-only · authorize-before-backend · per-principal 404 existence-hiding ·")
    print("        both-conditions gate · existing owning-principal field · runnable predicate table ·")
    print("        S4 blast-radius over all four endpoints · cache≠gate defense-in-depth · structural path")
    print("        safety · OBS-BB3 deny audit + trace split · NFR-OBS3 standing-law metric labels).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
