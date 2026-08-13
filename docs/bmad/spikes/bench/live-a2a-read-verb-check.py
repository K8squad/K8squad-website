#!/usr/bin/env python3
"""Story 8.7b (ISI-2272) falsification — the live A2A build-read verb on the Run shim.

Epic 8.7 build browser has two read paths (design §4): a **live** path (this story) and a
**completed** snapshot path (8.7c). For a *Running* Run the pod still has the git worktree mounted, so
the BFF serves tree/diff/file by issuing a **read-only query over A2A** to the Run's shim, which runs the
**8.7a** read-model in-worktree and returns payloads flagged `live:true`. This reuses the existing shim
channel (design §4.1, §10) — **no new mount, no new transport.**

The load-bearing claim of THIS story is that the live read is a *pure read projection bolted onto the
shim without opening a coordination edge*: the read verb is **distinct from task dispatch** (it is NOT
`SubmitTask`, starts NO agent execution), it is exposed **read-only** (a §10.1 / ISI-2114 conformance
requirement), it **never touches claim/lease/fence** state, and **no mutating verb exists on the query
path**. It **calls** the 8.7a projection — it does not rebuild it (the ADR-021 "do not rebuild" law
propagates up: every higher layer CALLS `pkg/buildbrowser`). And per OBS-BB3 it emits an inner
`buildbrowser.read.source` span that is a **true child of the live Run trace** (W3C `traceparent`
propagated over the read verb), with the Standing law holding on every span attribute.

A shim that answered the read by routing through `SubmitTask` (a second execution), that bumped the fence
or renewed the lease on a read, that exposed a mutating op on the query verb, that dropped the `live`
flag, that hand-rolled a *worse* git projection instead of calling 8.7a, or that opened a fresh root
trace (severing the read span from the Run trace) has NOT shipped the 8.7b contract — it has turned a
read surface into a coordination/exfil edge.

This is a REAL runnable check (same discipline as git-read-model-check.py, §8.6): it imports the **actual
8.7a projection functions** (`project_tree` / `project_diff` / `project_file`) and drives the shim over a
THROWAWAY git repo — so "the shim calls 8.7a, byte-for-byte" is *proven by construction*, not asserted.
git + stdlib only, no cluster / auth / network.

Invariants (L1-L6, each mapped to an 8.7b acceptance criterion):
  L1  DISTINCT-FROM-DISPATCH: the build-read verb is NOT the task-dispatch verb — a read starts ZERO
      agent executions (it never routes through SubmitTask). Reads and dispatch are separate verbs.
  L2  READ-ONLY COORDINATION STATE: a read NEVER mutates claim/lease/fence — fence token, lease holder,
      renewal count, and claim count are byte-identical before and after every read.
  L3  NO MUTATING VERB ON THE QUERY PATH: the read verb's op set is closed to {tree, diff, file}; a
      mutating op is rejected (unknown-op), and the worktree HEAD is byte-identical before/after — no
      read leaves a mutation. A mutating verb is structurally ABSENT, not merely guarded.
  L4  LIVE FLAG: every live read payload carries `live:true` (distinguishing it from the 8.7c completed
      snapshot path, which serves `live:false`).
  L5  CALLS 8.7a, DOES NOT REBUILD: the shim's tree/diff/file payloads are IDENTICAL to the 8.7a
      projection functions run directly (and byte-for-byte to raw git) — the shim delegates to
      pkg/buildbrowser, it does not reimplement a worse git (ADR-021 "do not rebuild").
  L6  OBS-BB3 + Standing law: the read emits a `buildbrowser.read.source` span that is a TRUE CHILD of
      the live Run trace (its trace_id == the incoming W3C `traceparent` trace_id; parent == the
      incoming span_id), and every span attribute is magnitude/status ONLY — never file content, a
      diff body, a `path` metric label, or a `model` label (Standing law #1-#4).

Mutation-proof harness (no vacuous guard — the ISI-2346-F1 class is excluded by construction). Each
`--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT shim; the check then goes RED with
EXACTLY the mapped invariant failing (no guard shadows another):
  --mutate=DISPATCH   answer the read through SubmitTask (a real execution)   -> L1 RED
  --mutate=FENCE      bump the fence token on a read                          -> L2 RED
  --mutate=RENEW      renew the lease on a read                               -> L2 RED
  --mutate=MUTVERB    expose a mutating op ("apply") on the read verb         -> L3 RED
  --mutate=LIVEFLAG   drop the live flag (serve live:false)                   -> L4 RED
  --mutate=REBUILD    hand-roll a worse git projection instead of 8.7a        -> L5 RED
  --mutate=NOTRACE    open a fresh root trace (sever the read span)           -> L6 RED
  --mutate=LEAK       put file content into a read-span attribute             -> L6 RED

Baseline `python3 live-a2a-read-verb-check.py` exits 0; each `--mutate=NAME` exits 1 with the single
violation.

Higher layers (owned elsewhere). The BFF GET endpoints + per-principal 404 scoping gate (8.7d,
NFR-SEC5) and the completed snapshot path (8.7c) build ON this live verb; this check guards ONLY the
live-read-verb contract — 8.7b's crux and exactly what design §4.1/§10 asked.
"""
import hashlib
import importlib.util
import os
import sys

# ---- import the ACTUAL 8.7a projection (proves "call, don't rebuild" by construction) --------------
_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_8_7a():
    """Load git-read-model-check.py (8.7a) as a module — the shim CALLS its projection functions."""
    path = os.path.join(_HERE, "git-read-model-check.py")
    spec = importlib.util.spec_from_file_location("git_read_model_8_7a", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g8a = _load_8_7a()
git, git_bytes = g8a.git, g8a.git_bytes

# The read verb's op set is CLOSED to these three read projections (design §3/§4.1).
READ_OPS = ("tree", "diff", "file")

# OBS-BB3 span-attribute allowlist — magnitudes/status only (Standing law #1/#2).
SPAN_MAGNITUDES = {
    "ksquad.buildbrowser.live",          # bool status
    "ksquad.buildbrowser.truncated",
    "ksquad.buildbrowser.too_large",
    "ksquad.buildbrowser.file_count",
    "ksquad.buildbrowser.bytes_returned",
}


# ---- W3C traceparent (RFC "00-<trace_id:32hex>-<span_id:16hex>-<flags:2hex>") ----------------------
def parse_traceparent(tp):
    version, trace_id, span_id, flags = tp.split("-")
    return {"version": version, "trace_id": trace_id, "span_id": span_id, "flags": flags}


def child_span_id(trace_id, op, path):
    """Deterministic child span-id (16 hex). No wall clock / randomness — resume-safe."""
    h = hashlib.sha256(f"{trace_id}:{op}:{path}".encode()).hexdigest()
    return h[:16]


# ---- claim/lease/fence — the coordination state the read path must NEVER touch (§6.2/§6.3) ---------
class Lease:
    def __init__(self):
        self.fence = 42          # current fence token (§6.3 — sole write discriminator)
        self.holder = "run-7f3a"  # lease holder identity
        self.renewals = 0        # lease-renewal count (§2.3 heartbeat)
        self.claims = 0          # claim count (§6.2)

    def snapshot(self):
        return (self.fence, self.holder, self.renewals, self.claims)


# ---- the live Run's shim (8.7b): six task verbs + ONE distinct read-only build-query verb ----------
class LiveShim:
    """A Running Run's shim sidecar. Exposes the six A2A task MUST-verbs (dispatch surface) PLUS a
    DISTINCT read-only build-read verb. The read verb runs the 8.7a projection in-worktree and never
    opens a coordination edge. Each mutant flips exactly one 8.7b invariant."""

    def __init__(self, repo, base, run_ref, lease, mut=None):
        self.repo, self.base, self.run_ref = repo, base, run_ref
        self.lease = lease
        self.mut = mut
        self.executions = 0          # agent executions started via SubmitTask (L1)

    # ── task-dispatch surface (V1 SubmitTask) — the verb reads are DISTINCT from ──
    def submit_task(self, task_id):
        # A real dispatch starts an execution and binds the fence (legitimate on this verb).
        self.executions += 1
        return "started"

    # ── the build-read verb (8.7b) — read-only, a distinct A2A verb ──
    def build_read(self, op, path=None, traceparent=None):
        # L1 — a read must NOT route through dispatch. The DISPATCH defect answers it via SubmitTask,
        # starting a spurious execution (a read becoming a coordination action).
        if self.mut == "DISPATCH":
            self.submit_task(task_id=self.lease.holder)

        # L3 — the op set is CLOSED to reads. The MUTVERB defect widens it with a mutating op.
        allowed = set(READ_OPS)
        if self.mut == "MUTVERB":
            allowed = allowed | {"apply"}
        if op not in allowed:
            return {"error": "unknown-op", "op": op}      # mutating verb structurally rejected
        if op == "apply":
            # The mutating op the MUTVERB defect exposed: it writes to the worktree over the read verb.
            g8a.write(self.repo, "injected-by-read.txt", "a read must never write\n")
            git(self.repo, "add", "-A")
            git(self.repo, "commit", "-q", "-m", "read-verb mutation")
            return {"applied": True}

        # L5 — CALL the 8.7a projection in-worktree; do NOT rebuild it. The REBUILD defect swaps in a
        # hand-rolled worse git that diverges from pkg/buildbrowser + raw git.
        payload = self._reimplemented_projection(op, path) if self.mut == "REBUILD" \
            else self._project_8_7a(op, path)

        # L4 — flag the live path. The LIVEFLAG defect serves live:false (masquerading as 8.7c).
        payload["live"] = False if self.mut == "LIVEFLAG" else True

        # L6 — OBS-BB3 read span (attached separately; see read_span()).
        return payload

    # 8.7a delegation (the conformant path) — identical to pkg/buildbrowser by construction.
    def _project_8_7a(self, op, path):
        if op == "tree":
            return dict(g8a.project_tree(self.repo, self.base, self.run_ref))
        if op == "diff":
            return dict(g8a.project_diff(self.repo, self.base, self.run_ref, path))
        return dict(g8a.project_file(self.repo, self.run_ref, path))

    # The REBUILD defect: a shim that reinvents git (re-serializes the diff, drops the trailing newline)
    # — the ADR-021 "do not rebuild" violation. Diverges from the 8.7a oracle byte-for-byte.
    def _reimplemented_projection(self, op, path):
        real = self._project_8_7a(op, path)
        if op == "diff" and real.get("unifiedDiff") is not None:
            real["unifiedDiff"] = real["unifiedDiff"].rstrip("\n")   # re-serialized, not byte-for-byte
        elif op == "tree":
            for f in real["files"]:
                if f["status"] == "D":
                    f["status"] = "M"                                 # mis-coded delete (rebuilt worse)
        elif op == "file" and real.get("content") is not None:
            real["content"] = real["content"] + "X"                   # mangled blob
        return real

    # OBS-BB3 — the inner read span, a TRUE CHILD of the live Run trace (traceparent propagated).
    def read_span(self, op, path, payload, traceparent):
        tp = parse_traceparent(traceparent)
        if self.mut == "NOTRACE":
            # DEFECT: open a fresh ROOT trace — the read span is severed from the live Run trace.
            trace_id = "f" * 32
            parent_span_id = None
        else:
            trace_id = tp["trace_id"]           # SAME trace => true child of the live Run trace
            parent_span_id = tp["span_id"]

        size = payload.get("sizeBytes", 0)
        if op == "tree":
            size = sum((f.get("additions") or 0) + (f.get("deletions") or 0) for f in payload["files"])
        attrs = {
            "ksquad.buildbrowser.live": payload.get("live", True),
            "ksquad.buildbrowser.truncated": payload.get("truncated", False),
            "ksquad.buildbrowser.too_large": bool(payload.get("tooLarge", False)),
            "ksquad.buildbrowser.file_count": len(payload["files"]) if op == "tree" else 1,
            "ksquad.buildbrowser.bytes_returned": size,      # magnitude, never a body
        }
        if self.mut == "LEAK":
            # DEFECT: file content leaks into a span attribute (Standing law #2) — the exfil edge.
            body = payload.get("content") or payload.get("unifiedDiff") or "leaked-content-sample"
            attrs["ksquad.buildbrowser.sample"] = body
        return {
            "name": "buildbrowser.read.source",
            "trace_id": trace_id,
            "parent_span_id": parent_span_id,
            "span_id": child_span_id(trace_id, op, path or ""),
            "attrs": attrs,
        }


# ---- the runnable check ----------------------------------------------------------------------------
def run(mut=None):
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    import tempfile
    with tempfile.TemporaryDirectory() as repo:
        base, run_ref = g8a.build_fixture(repo)          # 8.7a fixture: base -> add/modify/delete
        lease = Lease()
        shim = LiveShim(repo, base, run_ref, lease, mut=mut)

        # The BFF hands the shim the live Run's trace context over the read verb (OBS-BB3).
        run_trace_id = "abcdef0123456789abcdef0123456789"
        run_span_id = "1122334455667788"
        traceparent = f"00-{run_trace_id}-{run_span_id}-01"

        lease_before = lease.snapshot()
        head_before = git(repo, "rev-parse", "HEAD").strip()

        # ── drive the three read ops over the live verb ──
        tree = shim.build_read("tree", traceparent=traceparent)
        diff_paths = [f["path"] for f in tree["files"] if f["status"] != "D"]
        diff = shim.build_read("diff", path="mod.py", traceparent=traceparent)
        filep = shim.build_read("file", path="added.txt", traceparent=traceparent)

        # L1 — a read starts ZERO agent executions (distinct from SubmitTask dispatch).
        check("L1", shim.executions == 0,
              f"live read started {shim.executions} agent execution(s) — read verb is not distinct "
              f"from task dispatch (routed through SubmitTask)")

        # L2 — coordination state (claim/lease/fence) byte-identical before/after reads.
        check("L2", lease.snapshot() == lease_before,
              f"read mutated claim/lease/fence: {lease_before} -> {lease.snapshot()} "
              f"(fence/holder/renewals/claims)")

        # L4 — every live payload flagged live:true.
        for name, p in (("tree", tree), ("diff", diff), ("file", filep)):
            check("L4", p.get("live") is True,
                  f"{name} payload live flag is {p.get('live')!r}, expected True (8.7c serves live:false)")

        # L5 — the shim payloads are IDENTICAL to the 8.7a projection run directly (call, not rebuild)…
        oracle_tree = dict(g8a.project_tree(repo, base, run_ref))
        oracle_diff = dict(g8a.project_diff(repo, base, run_ref, "mod.py"))
        oracle_file = dict(g8a.project_file(repo, run_ref, "added.txt"))
        check("L5", {k: v for k, v in tree.items() if k != "live"} == oracle_tree,
              "tree payload != 8.7a project_tree (shim rebuilt the projection)")
        check("L5", {k: v for k, v in diff.items() if k != "live"} == oracle_diff,
              "diff payload != 8.7a project_diff (shim rebuilt the projection)")
        check("L5", {k: v for k, v in filep.items() if k != "live"} == oracle_file,
              "file payload != 8.7a project_file (shim rebuilt the projection)")
        # …and byte-for-byte to raw git (the ADR-021 anchor: no re-serialization slipped in).
        raw = git_bytes(repo, "diff", "-M", f"{base}...{run_ref}", "--", "mod.py")
        if diff.get("unifiedDiff") is not None:
            check("L5", diff["unifiedDiff"].encode("utf-8", "surrogateescape") == raw,
                  "diff unifiedDiff not byte-identical to `git diff` (read verb re-serialized)")

        # L6 — OBS-BB3 read span is a TRUE CHILD of the live Run trace; Standing law on attrs.
        span = shim.read_span("tree", None, tree, traceparent)
        check("L6", span["trace_id"] == run_trace_id,
              f"read span trace_id {span['trace_id']} != live Run trace {run_trace_id} "
              f"(span is not a child of the Run trace — traceparent not propagated)")
        check("L6", span["parent_span_id"] == run_span_id,
              f"read span parent {span['parent_span_id']} != Run span {run_span_id}")
        check("L6", set(span["attrs"]) <= SPAN_MAGNITUDES,
              f"read span carries non-magnitude attrs {sorted(set(span['attrs']) - SPAN_MAGNITUDES)} "
              f"(Standing law #1/#2)")
        # no attr value may echo real file/diff content (content-leak firewall, Standing law #2)
        bodies = [filep.get("content"), diff.get("unifiedDiff")]
        bodies = [b for b in bodies if b]
        for k, v in span["attrs"].items():
            if isinstance(v, str):
                for b in bodies:
                    check("L6", b not in v and len(v) < 40,
                          f"read span attr {k} carries content (Standing law #2)")
        check("L6", "model" not in {k.rsplit(".", 1)[-1] for k in span["attrs"]},
              "read span carries a `model` label (Standing law #3)")

        # L3 — no mutating verb on the query path: (a) a mutating op is rejected, (b) worktree unchanged.
        apply_res = shim.build_read("apply", path="x", traceparent=traceparent)
        check("L3", apply_res.get("applied") is not True,
              "read verb ACCEPTED a mutating op ('apply') — a mutating verb is not structurally absent")
        head_after = git(repo, "rev-parse", "HEAD").strip()
        check("L3", head_after == head_before,
              f"worktree HEAD changed across reads ({head_before[:8]} -> {head_after[:8]}) — "
              f"a read left a mutation on the query path")
        # positive control: the read op set is exactly the closed read allowlist (non-vacuous).
        check("L3", shim.build_read("nonsense-verb", traceparent=traceparent).get("error") == "unknown-op",
              "read verb did not reject an unknown op (op set is not closed)")

    return fails


MUTANTS = {
    "DISPATCH": "L1", "FENCE": "L2", "RENEW": "L2", "MUTVERB": "L3",
    "LIVEFLAG": "L4", "REBUILD": "L5", "NOTRACE": "L6", "LEAK": "L6",
}


# The FENCE / RENEW defects live on the read handler but touch coordination state; wire them by
# subclassing so the read path itself is the injection point (a read that mutates the lease).
_ORIG_BUILD_READ = LiveShim.build_read


def _build_read_with_coord_defect(self, op, path=None, traceparent=None):
    res = _ORIG_BUILD_READ(self, op, path=path, traceparent=traceparent)
    if op in READ_OPS:
        if self.mut == "FENCE":
            self.lease.fence += 1        # DEFECT: read bumped the fence token (§6.3) -> L2
        if self.mut == "RENEW":
            self.lease.renewals += 1     # DEFECT: read renewed the lease (§2.3 heartbeat) -> L2
    return res


LiveShim.build_read = _build_read_with_coord_defect


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
            print("[live-read-verb] FAIL — baseline 8.7b contract violated:")
            for inv, d in fails:
                print(f"    {inv}: {d}")
            return 1
        print("[live-read-verb] PASS — the live A2A build-read verb honors the 8.7b contract "
              "against a live throwaway repo.")
        print("    L1 read!=dispatch(0 executions)  L2 lease/fence/claim untouched  L3 no mutating verb"
              "  L4 live:true")
        print("    L5 calls 8.7a byte-for-byte (not rebuilt)  L6 OBS-BB3 read span child-of-Run-trace, "
              "magnitudes-only")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)} — acceptable, {expected} is the mapped tooth)" if others else ""
        print(f"[live-read-verb] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[live-read-verb] SURVIVED — --mutate={mut} did NOT trip {expected} (VACUOUS GUARD); "
          f"tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
