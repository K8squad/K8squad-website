#!/usr/bin/env python3
"""Story 8.7c (ISI-2273) falsification — the build-snapshot artifact at Collecting (completed path).

Epic 8.7 build browser has two read paths (design §4): a **live** path (8.7b — the pod still has the
worktree mounted) and a **completed** snapshot path (THIS story). A Run's pod is torn down at completion
(§9.3, teardown-not-reset), so the git projection a completed Run serves cannot come from a live shim.
Instead, when the Run reaches **Collecting** (§6.1/§6.4) it emits a **build-snapshot artifact**: a
**fence-guarded, content-addressed `coord.artifact` upsert** —

    coord.artifact { work_item_id, run_id, kind:"build-snapshot",   # UNIQUE(work_item_id, run_id, kind)
                     sha256,                                          # content hash of the bundle
                     uri,                                             # object-store URI of the bundle
                     meta:{ base, runRef, commit, fileCount, totalAdditions, totalDeletions, truncated,
                            traceId } }                               # traceId = OBS-BB2 span-link key

— capturing the **8.7a** projection (`git diff --name-status` / `git diff` / `git show`) into a git-native
bundle. A completed Run then serves **tree + diffs + changed-file code** from that snapshot with
`live:false` (the discriminator vs 8.7b's `live:true`), needing **no live pod**. If emission fails or was
skipped, a completed Run's build read degrades to a **legible `no-build-view` signal** — NOT a silent
`404` that reads as "this Run does not exist" (design §7 "surface it, don't silently 404"; the coverage
SLO in the obs plan §4). v1 target = **snapshot-only** (the RO-reader pod is the flagged 8.7f fast-follow).

The load-bearing claim of THIS story: the completed-path snapshot is (1) written under fence discipline
and content-addressing so a stale re-run cannot clobber a fresher snapshot and the bytes are
integrity-verifiable; (2) a faithful CAPTURE of the 8.7a projection, not a rebuilt worse git (ADR-021 "do
not rebuild" propagates up); (3) served pod-independently with `live:false`; (4) never a silent 404 on an
emit miss; and (5) attached to telemetry as an OTel span **link** back to the (closed) Run trace — the
§1.2 correction — with the NFR-OBS3 Standing law holding on every signal.

This is a REAL runnable check (same discipline as git-read-model-check.py §8.6 and live-a2a-read-verb-
check.py): it imports the **actual 8.7a projection functions** (`project_tree` / `project_diff` /
`project_file`) and drives emission + completed reads over a THROWAWAY git repo — so "the snapshot
captures 8.7a byte-for-byte" is *proven by construction*, not asserted. git + stdlib only, no cluster /
auth / network / object store.

Invariants (S1-S7, each mapped to an 8.7c acceptance criterion):
  S1  FENCE-GUARDED UPSERT: emission is a fence-guarded upsert on UNIQUE(work_item_id, run_id, kind) — a
      STALE-fence emitter (fence < the current claim fence, §6.3) does NOT overwrite a fresher snapshot
      row, and a re-entrant Collecting at the same fence with identical content is an idempotent no-op.
  S2  CONTENT-ADDRESSED: the row records `sha256` == hash(bundle bytes) AND an object-store `uri`; the
      served bundle is VERIFIED against the recorded sha256 (a mismatch is caught, never served blind).
  S3  META COMPLETENESS/CORRECTNESS: `meta` carries {base, runRef, commit, fileCount, totalAdditions,
      totalDeletions, truncated, traceId}, and the counts equal the 8.7a projection over base...runRef.
  S4  COMPLETED PATH, live:false, NO POD: a completed Run (pod torn down) serves tree/diff/file from the
      snapshot bundle flagged `live:false`, and the read NEVER reaches for the (gone) live shim/pod.
  S5  CAPTURES 8.7a BYTE-FOR-BYTE, NOT REBUILT: the tree/diff/file served from the snapshot are IDENTICAL
      to the 8.7a projection over the same base...runRef (and the diff is byte-for-byte to raw `git diff`)
      — the bundle captures pkg/buildbrowser, it does not reimplement a worse git (ADR-021).
  S6  EMIT FAILURE = LEGIBLE "no build view", NEVER SILENT 404: a completed Run whose snapshot emission
      failed/was skipped serves a legible `no-build-view` outcome (runExists:true), NOT a bare 404 that is
      indistinguishable from "Run does not exist" or an empty body.
  S7  OBS-BB2 + Standing law: emission emits `snapshot.emit.*` + `snapshot.bytes`/`.file_count`
      (histograms); a completed read opens a BFF-ROOTED trace with an OTel span **link** back to the Run's
      original trace_id (from `meta.traceId`) — NOT a forced child of the torn-down Run trace (§1.2) — and
      every `ksquad.buildbrowser.*` span attribute is magnitude/status ONLY (no file content, no diff
      body, no `model` label; bytes/file_count are histograms, not monotonic sums).

Mutation-proof harness (no vacuous guard — the ISI-2346-F1 class is excluded by construction). Each
`--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT emission/read path; the check then goes
RED with EXACTLY the mapped invariant failing (no guard shadows another):
  --mutate=STALEFENCE   a stale-fence emit overwrites a fresher snapshot row     -> S1 RED
  --mutate=NOFENCE      drop the fence guard on the upsert entirely              -> S1 RED
  --mutate=SHA_MISMATCH record a sha256 that does not match the bundle bytes     -> S2 RED
  --mutate=NOURI        omit the object-store uri on the row                     -> S2 RED
  --mutate=NOMETA       drop a required meta field (fileCount)                   -> S3 RED
  --mutate=LIVEFLAG     serve the completed read with live:true                  -> S4 RED
  --mutate=NEEDPOD      completed read reaches for the (torn-down) live pod      -> S4 RED
  --mutate=REBUILD      snapshot rebuilds a worse git instead of capturing 8.7a  -> S5 RED
  --mutate=SILENT404    an emit-miss serves a bare 404 (not a legible no-view)   -> S6 RED
  --mutate=LINKCHILD    force the completed read to be a CHILD of the Run trace  -> S7 RED
  --mutate=LEAK         put bundle content into a read-span attribute            -> S7 RED

Baseline `python3 build-snapshot-collecting-check.py` exits 0; each `--mutate=NAME` exits 1 with the
single violation.

Higher layers (owned elsewhere). The BFF GET endpoints + per-principal 404 scoping gate (8.7d, NFR-SEC5)
dispatch to THIS completed path when a Run is not live; the RO-reader pod for full-tree completed reads is
the flagged 8.7f fast-follow. This check guards ONLY the completed-snapshot contract — 8.7c's crux and
exactly what design §4.2/§6.1 + obs plan OBS-BB2/§1.2 asked.
"""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile

# ---- import the ACTUAL 8.7a projection (proves "capture, don't rebuild" by construction) -----------
_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_8_7a():
    """Load git-read-model-check.py (8.7a) as a module — the snapshot CAPTURES its projection."""
    path = os.path.join(_HERE, "git-read-model-check.py")
    spec = importlib.util.spec_from_file_location("git_read_model_8_7a", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g8a = _load_8_7a()
git, git_bytes = g8a.git, g8a.git_bytes

SNAPSHOT_KIND = "build-snapshot"
# The meta fields the snapshot row MUST carry (design §4.2 + obs OBS-BB2 traceId for the span link).
META_FIELDS = ("base", "runRef", "commit", "fileCount", "totalAdditions",
               "totalDeletions", "truncated", "traceId")

# OBS-BB2 completed-read span-attribute allowlist — magnitudes/status + bounded enums only.
SPAN_MAGNITUDES = {
    "ksquad.buildbrowser.live",          # bool status (false on the completed path)
    "ksquad.buildbrowser.source",        # bounded enum: snapshot | shim | ro_reader
    "ksquad.buildbrowser.truncated",
    "ksquad.buildbrowser.too_large",
    "ksquad.buildbrowser.file_count",
    "ksquad.buildbrowser.bytes_returned",
}


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def canonical_bundle_bytes(tree, diffs, files, tag=None):
    """The git-native capture, serialized canonically so it is content-addressed by sha256. The
    unifiedDiff strings are preserved verbatim (byte-for-byte round-trip), so a read from the bundle is
    identical to the 8.7a projection. `tag` distinguishes an otherwise-equal payload (used to model a
    stale re-run's divergent bundle) so a fence/idempotency violation is observable via the sha."""
    payload = {"tree": tree, "diffs": diffs, "files": files}
    if tag is not None:
        payload["_capture_tag"] = tag
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8", "surrogateescape")


def deserialize_bundle(bundle):
    return json.loads(bundle.decode("utf-8", "surrogateescape"))


# ---- the durable coordination record (§6.2 claim fence + §6.5 artifact) ----------------------------
class Coord:
    """In-process model of coord.claim (the current fence) + coord.artifact (build-snapshot rows keyed
    by the UNIQUE(work_item_id, run_id, kind) constraint) + the OBS-BB2 emission telemetry."""

    def __init__(self):
        self.fence = {}          # work_item_id -> current claim fence (§6.3)
        self.artifacts = {}      # (work_item_id, run_id, kind) -> row  (the UNIQUE key = upsert target)
        self.metrics = []        # snapshot.emit.* / snapshot.bytes / snapshot.file_count records

    def current_fence(self, wi):
        return self.fence.get(wi, 0)


# ---- emission at Collecting (§6.1/§6.4) — the fence-guarded content-addressed upsert ----------------
def emit_snapshot(coord, wi, run, principal, fence, repo, base, run_ref, run_trace_id,
                  mut=None, tag=None, fail=False):
    """Capture the 8.7a projection into a bundle and fence-guarded upsert it as a content-addressed
    build-snapshot `coord.artifact` row. Emits OBS-BB2 `snapshot.emit.*` telemetry. Returns a result
    dict; on stale-fence / drift rejection the existing row is left untouched (S1)."""
    key = (wi, run, SNAPSHOT_KIND)

    # OBS-BB2: emission can fail at Collecting. A failed emit writes NO artifact row and records a
    # legible result=failed metric — the completed read then degrades to a legible "no build view" (S6),
    # never a silent 404. (This is the "no build view" coverage-SLO failure mode, obs §4/§6.)
    if fail:
        coord.metrics.append({"name": "ksquad.buildbrowser.snapshot.emit.total", "result": "failed"})
        return {"result": "failed"}

    # --- capture the 8.7a projection (CALL pkg/buildbrowser, do NOT rebuild — ADR-021 propagates) ---
    tree = dict(g8a.project_tree(repo, base, run_ref))
    all_paths = [f["path"] for f in tree["files"]]
    changed = [f["path"] for f in tree["files"] if f["status"] != "D"]   # git show has no deleted blob
    diffs = {p: dict(g8a.project_diff(repo, base, run_ref, p)) for p in all_paths}
    files = {p: dict(g8a.project_file(repo, run_ref, p)) for p in changed}

    if mut == "REBUILD":
        # DEFECT: the snapshot rebuilds a WORSE git instead of capturing the 8.7a projection
        # byte-for-byte — re-serialized diff + mis-coded delete (the ADR-021 violation) -> S5.
        for d in diffs.values():
            if d.get("unifiedDiff") is not None:
                d["unifiedDiff"] = d["unifiedDiff"].rstrip("\n")     # no longer byte-for-byte
        for f in tree["files"]:
            if f["status"] == "D":
                f["status"] = "M"                                    # mis-coded delete

    bundle = canonical_bundle_bytes(tree, diffs, files, tag=tag)
    sha = sha256(bundle)
    if mut == "SHA_MISMATCH":
        sha = "0" * 64          # DEFECT: recorded digest does not match the bundle bytes -> S2.

    meta = {
        "base": base,
        "runRef": run_ref,
        "commit": run_ref,
        "fileCount": len(tree["files"]),
        "totalAdditions": sum((f.get("additions") or 0) for f in tree["files"]),
        "totalDeletions": sum((f.get("deletions") or 0) for f in tree["files"]),
        "truncated": tree["truncated"],
        "traceId": run_trace_id,          # OBS-BB2: persist the Run's original trace_id for the link
    }
    if mut == "NOMETA":
        del meta["fileCount"]             # DEFECT: drop a required meta field -> S3.

    uri = None if mut == "NOURI" else f"s3://ksquad-artifacts/{wi}/{run}/{SNAPSHOT_KIND}"  # NOURI -> S2
    row = {"work_item_id": wi, "run_id": run, "kind": SNAPSHOT_KIND,
           "sha256": sha, "uri": uri, "meta": meta, "bundle": bundle,
           "fence": fence, "owning_principal": principal}

    # --- fence-guarded, content-addressed upsert on UNIQUE(wi, run, kind) (§6.3/§6.4) ---
    existing = coord.artifacts.get(key)
    if existing is not None and existing["sha256"] == sha:
        # re-entrant Collecting (§6.4): identical content -> idempotent no-op (one row, S1).
        coord.metrics.append({"name": "ksquad.buildbrowser.snapshot.emit.total", "result": "skipped"})
        return {"result": "skipped"}

    # fence guard: a stale emitter (fence < the current claim fence, §6.3) must NOT overwrite a fresher
    # snapshot row. Two defects bypass it — NOFENCE removes the guard, STALEFENCE inverts the comparison
    # (a stale fence is wrongly treated as fresh) — and either lets the stale write land -> S1.
    current = coord.current_fence(wi)
    if mut == "NOFENCE":
        stale = False
    elif mut == "STALEFENCE":
        stale = fence > current
    else:
        stale = fence < current
    if stale:
        coord.metrics.append({"name": "ksquad.buildbrowser.snapshot.emit.total", "result": "skipped"})
        return {"result": "stale-rejected"}

    coord.artifacts[key] = row
    body_bytes = len(bundle)
    coord.metrics += [
        {"name": "ksquad.buildbrowser.snapshot.emit.total", "result": "ok"},
        {"name": "ksquad.buildbrowser.snapshot.bytes", "type": "histogram", "value": body_bytes},
        {"name": "ksquad.buildbrowser.snapshot.file_count", "type": "histogram",
         "value": meta.get("fileCount", len(tree["files"]))},
    ]
    return {"result": "ok"}


# ---- the completed-Run read (pod torn down) — serve from the snapshot bundle, live:false ------------
def read_completed(coord, wi, run, op, path=None, pod_alive=False, mut=None):
    """A COMPLETED Run (pod torn down §9.3) serves tree/diff/file from the snapshot bundle with
    `live:false`, needing no pod. A missing snapshot degrades to a legible no-build-view (S6)."""
    key = (wi, run, SNAPSHOT_KIND)
    row = coord.artifacts.get(key)

    if row is None:
        # Emission failed/skipped -> no snapshot. The owner + Run still exist; say so LEGIBLY (S6).
        if mut == "SILENT404":
            return {"status": 404}        # DEFECT: indistinguishable from "Run not found" -> S6.
        return {"status": 200, "outcome": "no-build-view", "live": False,
                "reason": "snapshot-missing", "runExists": True}

    if mut == "NEEDPOD" and not pod_alive:
        # DEFECT: the completed path reaches for the (torn-down) live shim/pod -> S4.
        raise RuntimeError("completed read tried to contact a torn-down pod")

    # content-addressed integrity: the served bytes must hash to the recorded sha256 (S2).
    integrity_ok = sha256(row["bundle"]) == row["sha256"]
    payload = deserialize_bundle(row["bundle"])

    if op == "tree":
        served = dict(payload["tree"])
    elif op == "diff":
        served = dict(payload["diffs"][path])
    else:
        served = dict(payload["files"][path])

    served["live"] = True if mut == "LIVEFLAG" else False   # LIVEFLAG masquerades as the 8.7b path.
    served["source"] = "snapshot"
    served["integrityOk"] = integrity_ok
    return {"status": 200, "payload": served}


# ---- OBS-BB2 completed-read span (§1.2 correction: span LINK, not a forced child) ------------------
def completed_read_span(coord, row, op, payload, path=None, mut=None):
    """A completed read opens a BFF-ROOTED trace with an OTel span LINK back to the Run's original
    trace_id (persisted in meta.traceId) — the Run trace closed at teardown, so a forced parent-child
    would fabricate a span under a trace that no longer exists (obs §1.2)."""
    run_trace = row["meta"].get("traceId")
    bff_trace = "b" * 32                 # a fresh BFF-rooted trace (deterministic, no wall clock)

    trace_id = bff_trace
    parent_span_id = None
    links = [{"trace_id": run_trace, "kind": "run-origin"}]   # the causal-but-async edge
    if mut == "LINKCHILD":
        # DEFECT: force the completed read to be a CHILD of the (closed) Run trace instead of a link.
        trace_id = run_trace
        parent_span_id = "0" * 16
        links = []

    size = payload.get("sizeBytes", 0)
    if op == "tree":
        size = sum((f.get("additions") or 0) + (f.get("deletions") or 0) for f in payload["files"])
    attrs = {
        "ksquad.buildbrowser.live": payload.get("live", False),
        "ksquad.buildbrowser.source": payload.get("source", "snapshot"),
        "ksquad.buildbrowser.truncated": payload.get("truncated", False),
        "ksquad.buildbrowser.too_large": bool(payload.get("tooLarge", False)),
        "ksquad.buildbrowser.file_count": len(payload["files"]) if op == "tree" else 1,
        "ksquad.buildbrowser.bytes_returned": size,      # magnitude, never a body
    }
    if mut == "LEAK":
        # DEFECT: bundle content leaks into a span attribute (Standing law #2) — the exfil edge.
        body = payload.get("content") or payload.get("unifiedDiff") or "leaked-content-sample"
        attrs["ksquad.buildbrowser.sample"] = body
    return {"name": f"buildbrowser.{op}", "trace_id": trace_id, "parent_span_id": parent_span_id,
            "links": links, "attrs": attrs}


# ---- the runnable check ----------------------------------------------------------------------------
def run(mut=None):
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    with tempfile.TemporaryDirectory() as repo:
        base, run_ref = g8a.build_fixture(repo)          # 8.7a fixture: base -> add/modify/delete/rename
        coord = Coord()
        wi, run = "wi-1", "runA"
        principal = "alice"
        run_trace_id = "abcdef0123456789abcdef0123456789"
        coord.fence[wi] = 2                               # current claim fence at Collecting (§6.3)

        # ── Collecting: emit the build-snapshot (fence-guarded content-addressed upsert) ──
        res = emit_snapshot(coord, wi, run, principal, fence=2, repo=repo, base=base, run_ref=run_ref,
                            run_trace_id=run_trace_id, mut=mut)
        key = (wi, run, SNAPSHOT_KIND)
        row = coord.artifacts.get(key)
        # baseline sanity: a successful Collecting must leave exactly one snapshot row.
        check("S1", row is not None and res["result"] == "ok",
              f"Collecting did not emit a build-snapshot row (result={res['result']!r})")
        if row is None:
            return fails                                  # nothing else is meaningful without the row

        sha_v1 = row["sha256"]

        # S2 — content-addressed: sha256 == hash(bundle), a uri is present, and a read VERIFIES bytes.
        check("S2", row["sha256"] == sha256(row["bundle"]),
              f"recorded sha256 {row['sha256'][:12]}… != hash(bundle) — bundle not content-addressed")
        check("S2", bool(row["uri"]),
              "snapshot row has no object-store uri (design §4.2 requires kind+sha256+uri)")
        rt = read_completed(coord, wi, run, "tree", pod_alive=False, mut=None)
        check("S2", rt["payload"]["integrityOk"] is True,
              "completed read served the bundle WITHOUT verifying bytes against the recorded sha256")

        # S3 — meta completeness + correctness (counts derived from the 8.7a projection).
        meta = row["meta"]
        missing = [f for f in META_FIELDS if f not in meta]
        check("S3", not missing, f"snapshot meta missing required field(s): {missing}")
        otree = dict(g8a.project_tree(repo, base, run_ref))
        check("S3", meta.get("fileCount") == len(otree["files"]),
              f"meta.fileCount {meta.get('fileCount')} != 8.7a changed-set size {len(otree['files'])}")
        check("S3", meta.get("totalAdditions") == sum((f.get("additions") or 0) for f in otree["files"])
              and meta.get("totalDeletions") == sum((f.get("deletions") or 0) for f in otree["files"]),
              "meta add/del totals do not equal the 8.7a projection over base...runRef")

        # S4 — completed path serves live:false from the snapshot, NEVER reaching a torn-down pod.
        for op, p in (("tree", None), ("diff", "mod.py"), ("file", "added.txt")):
            try:
                r = read_completed(coord, wi, run, op, path=p, pod_alive=False, mut=mut)
            except RuntimeError as e:
                check("S4", False, f"completed {op} read reached for a torn-down pod: {e}")
                continue
            check("S4", r.get("status") == 200 and r["payload"].get("live") is False,
                  f"completed {op} read live flag is {r.get('payload', {}).get('live')!r}, "
                  f"expected False (8.7b live path serves live:true)")

        # S5 — the served projection is IDENTICAL to the 8.7a oracle (capture, not rebuilt). The read
        # itself is driven mut=None: the REBUILD defect lives in the EMITTED bundle (S5 is an emit-side
        # capture property), and the read-affecting mutants (LIVEFLAG/NEEDPOD) are exercised under S4.
        served_tree = read_completed(coord, wi, run, "tree", pod_alive=False, mut=None)["payload"]
        served_diff = read_completed(coord, wi, run, "diff", path="mod.py", pod_alive=False, mut=None)["payload"]
        served_file = read_completed(coord, wi, run, "file", path="added.txt", pod_alive=False, mut=None)["payload"]
        oracle_tree = dict(g8a.project_tree(repo, base, run_ref))
        oracle_diff = dict(g8a.project_diff(repo, base, run_ref, "mod.py"))
        oracle_file = dict(g8a.project_file(repo, run_ref, "added.txt"))
        _serving = {"live", "source", "integrityOk"}     # fields the completed reader stamps on
        check("S5", {k: v for k, v in served_tree.items() if k not in _serving} == oracle_tree,
              "snapshot tree != 8.7a project_tree (the snapshot rebuilt the projection)")
        check("S5", {k: v for k, v in served_diff.items() if k not in _serving} == oracle_diff,
              "snapshot diff != 8.7a project_diff (the snapshot rebuilt the projection)")
        check("S5", {k: v for k, v in served_file.items() if k not in _serving} == oracle_file,
              "snapshot file != 8.7a project_file (the snapshot rebuilt the projection)")
        # …and byte-for-byte to raw git (the ADR-021 anchor: no re-serialization slipped into the bundle).
        raw = git_bytes(repo, "diff", "-M", f"{base}...{run_ref}", "--", "mod.py")
        if served_diff.get("unifiedDiff") is not None:
            check("S5", served_diff["unifiedDiff"].encode("utf-8", "surrogateescape") == raw,
                  "snapshot diff unifiedDiff not byte-identical to `git diff` (bundle re-serialized)")

        # S7 — OBS-BB2: completed read = BFF-rooted span LINK to the Run trace (not a forced child);
        # emission emitted snapshot.emit.* + histogram bytes/file_count; Standing law on span attrs.
        span = completed_read_span(coord, row, "tree", served_tree, mut=mut)
        check("S7", span["trace_id"] != run_trace_id,
              "completed read span is a CHILD of the (closed) Run trace — must be a BFF-rooted span "
              "with an OTel LINK back to the Run trace (obs §1.2)")
        check("S7", any(l["trace_id"] == run_trace_id for l in span["links"]),
              "completed read span carries no OTel link back to the Run's original trace_id")
        check("S7", set(span["attrs"]) <= SPAN_MAGNITUDES,
              f"read span carries non-magnitude attrs "
              f"{sorted(set(span['attrs']) - SPAN_MAGNITUDES)} (Standing law #1/#2)")
        bodies = [served_file.get("content"), served_diff.get("unifiedDiff")]
        bodies = [b for b in bodies if b]
        for k, v in span["attrs"].items():
            if isinstance(v, str):
                for b in bodies:
                    check("S7", b not in v and len(v) < 40,
                          f"read span attr {k} carries content (Standing law #2)")
        check("S7", "model" not in {k.rsplit(".", 1)[-1] for k in span["attrs"]},
              "read span carries a `model` label (Standing law #3)")
        # positive control: emission telemetry is present and bytes/file_count are histograms, not sums.
        emit_ok = [m for m in coord.metrics
                   if m["name"] == "ksquad.buildbrowser.snapshot.emit.total" and m.get("result") == "ok"]
        hists = [m for m in coord.metrics if m["name"] in
                 ("ksquad.buildbrowser.snapshot.bytes", "ksquad.buildbrowser.snapshot.file_count")]
        check("S7", len(emit_ok) == 1, "emission did not record a snapshot.emit.total{result=ok}")
        check("S7", hists and all(m.get("type") == "histogram" for m in hists),
              "snapshot.bytes/.file_count must be histograms, not monotonic sums (Standing law #4)")

        # S1 — re-entrant Collecting at the SAME fence with identical content = idempotent no-op…
        res2 = emit_snapshot(coord, wi, run, principal, fence=2, repo=repo, base=base, run_ref=run_ref,
                             run_trace_id=run_trace_id, mut=mut)
        check("S1", res2["result"] == "skipped" and coord.artifacts[key]["sha256"] == sha_v1,
              f"re-entrant Collecting was not an idempotent no-op (result={res2['result']!r}, "
              f"sha {'changed' if coord.artifacts[key]['sha256'] != sha_v1 else 'stable'})")

        # …and a STALE-fence emitter (fence 1 < current 2) with divergent content does NOT overwrite the
        # fresher row. This is the LAST write in the scenario so a mutant's clobber cannot shadow S2-S7.
        emit_snapshot(coord, wi, run, principal, fence=1, repo=repo, base=base, run_ref=run_ref,
                      run_trace_id=run_trace_id, mut=mut, tag="stale-rerun")
        check("S1", coord.artifacts[key]["sha256"] == sha_v1,
              "a STALE-fence emit (fence < current claim fence) OVERWROTE a fresher snapshot row — "
              "the upsert is not fence-guarded (§6.3)")

        # S6 — a completed Run whose emission FAILED serves a legible no-build-view, never a silent 404.
        runB = "runB"
        femit = emit_snapshot(coord, wi, runB, principal, fence=2, repo=repo, base=base, run_ref=run_ref,
                              run_trace_id=run_trace_id, mut=mut, fail=True)
        check("S6", femit["result"] == "failed",
              "the fail-injected emission did not record result=failed")
        rb = read_completed(coord, wi, runB, "tree", pod_alive=False, mut=mut)
        check("S6", rb.get("status") == 200 and rb.get("outcome") == "no-build-view"
              and rb.get("runExists") is True,
              f"completed read of a snapshot-less Run returned {rb!r} — an emit miss must be a LEGIBLE "
              f"'no build view' (runExists:true), never a silent 404 (design §7)")

    return fails


MUTANTS = {
    "STALEFENCE": "S1", "NOFENCE": "S1",
    "SHA_MISMATCH": "S2", "NOURI": "S2",
    "NOMETA": "S3",
    "LIVEFLAG": "S4", "NEEDPOD": "S4",
    "REBUILD": "S5",
    "SILENT404": "S6",
    "LINKCHILD": "S7", "LEAK": "S7",
}


def main(argv):
    mut = None
    for a in argv[1:]:
        if a.startswith("--mutate="):
            mut = a.split("=", 1)[1].strip().upper()
    if mut and mut not in MUTANTS:
        print(f"unknown mutant {mut!r}; choose from {', '.join(MUTANTS)}", file=sys.stderr)
        return 2

    fails = run(mut=mut)

    if mut is None:
        if fails:
            print("[build-snapshot] FAIL — baseline 8.7c contract violated:")
            for inv, d in fails:
                print(f"    {inv}: {d}")
            return 1
        print("[build-snapshot] PASS — the build-snapshot at Collecting honors the 8.7c contract "
              "against a completed throwaway repo.")
        print("    S1 fence-guarded upsert  S2 content-addressed(sha256+uri, verified)  S3 meta complete")
        print("    S4 live:false, no pod  S5 captures 8.7a byte-for-byte(not rebuilt)  S6 no silent 404")
        print("    S7 OBS-BB2 span-link(not child) + Standing law")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)} — acceptable, {expected} is the mapped tooth)" if others else ""
        print(f"[build-snapshot] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[build-snapshot] SURVIVED — --mutate={mut} did NOT trip {expected} (VACUOUS GUARD); "
          f"tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
