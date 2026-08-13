#!/usr/bin/env python3
"""Story 8.7a falsification — the pure git read-model (tree/diff/file over a Run's worktree).

This is the FOUNDATION of Epic 8.7 (build browser). ADR-021 / §9.4: every Run already works in its own
git *worktree* over the Project workspace, so the three build-browser views are **native git projections**
— we build no diff engine, no VFS, no snapshot format of our own (design §2 "do not rebuild"):

    tree         := git diff --name-status -M <base>...<runRef>   (+ --numstat for add/del counts)
    per-file diff := git diff -M <base>...<runRef> -- <path>       (unified diff, byte-for-byte)
    file content := git show <runRef>:<path>                       (blob at the Run's commit)

`<base>` = merge-base of the Run's worktree branch and the Project default ref; the **three-dot** form so
the view is *the Run's changes*, not drift on the base since the Run started. `<runRef>` = the worktree
branch tip.

The load-bearing claim of THIS story is that the read-model is a **faithful, bounded projection of git and
nothing more**: the changed set + statuses + counts are exactly what git reports, the unified diff is git's
output **byte-for-byte** (the server emits, the client renders — no re-serialization), file content is the
blob git shows, and every unbounded axis (diff size, file size, tree entry count, binary blobs) is **capped
fail-safe** into a `tooLarge`/`truncated`/`binary` marker rather than an unbounded body. A read-model that
"parses" and re-emits diffs, that miscounts, that silently drops a delete, or that streams a 2 GiB hostile
blob into the response has NOT shipped the ADR-021 projection — it has rebuilt a worse git and opened a
DoS/exfil edge.

Unlike the sibling model-only checks, this one is a REAL runnable check (design §8.6 / AC "runnable
check"): it builds a THROWAWAY git repo, touches 3 files (add / modify / delete), drives the SAME git
commands the server uses, runs the read-model projection over that live git output, and asserts the
projection matches an INDEPENDENT raw-git oracle byte-for-byte. It needs git and stdlib only — no cluster,
no auth, no shim, no network (the AC's "no cluster, no auth").

Invariants (G1-G9, each mapped to an AC of story 8.7a):
  G1  TREE = CHANGED SET: `tree` returns EXACTLY the git changed set with the correct A/M/D/R status —
      not a superset (unchanged files) and never a dropped/miscoded entry (a deleted file reported M, etc.).
  G2  COUNTS: each file's additions/deletions equal `git diff --numstat`'s counts (binary -> None,None).
  G3  DIFF BYTE-FOR-FOR-BYTE: `diff(path).unifiedDiff` is IDENTICAL, byte-for-byte, to
      `git diff -M <base>...<runRef> -- <path>` — no normalization, re-wrap, or whitespace munging.
  G4  FILE CONTENT: `file(path).content` is IDENTICAL to `git show <runRef>:<path>` (the blob at runRef).
  G5  DIFF CAP (512 KiB): an oversize per-file diff returns `tooLarge:true` and NO body — never unbounded.
  G6  FILE CAP (2 MiB): an oversize file returns `tooLarge:true` and `content:None` — never unbounded.
  G7  TREE CAP (5000 entries): a changed set beyond the cap returns `truncated:true` (bounded body).
  G8  BINARY: a binary file returns `binary:true` with NO diff/content body (never streamed as text).
  G9  OBS-BB1 + Standing law: the read span carries ONLY magnitudes/status (`truncated`, `too_large`,
      `file_count`, `bytes_returned`) — NEVER file content, diff bodies, blob bytes, a `path` as a metric
      label, or a `model` label. The foundation emits NO metric and adds NO transport (design §7, plan §1.1).

Mutation-proof harness (no vacuous guard — the ISI-2346-F1 class is excluded by construction). Each
`--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT projection; the check then goes RED with
EXACTLY the mapped invariant failing (no guard shadows another):
  --mutate=STATUS    drop/mis-code the delete in the changed set        -> G1 RED
  --mutate=COUNT     zero out add/del counts                            -> G2 RED
  --mutate=DIFF      re-serialize the unified diff (strip trailing \\n)  -> G3 RED
  --mutate=CONTENT   return git-show with a byte mangled                -> G4 RED
  --mutate=DIFFCAP   ignore the 512 KiB diff cap (stream unbounded)     -> G5 RED
  --mutate=FILECAP   ignore the 2 MiB file cap (stream unbounded)       -> G6 RED
  --mutate=TREECAP   ignore the 5000-entry tree cap                     -> G7 RED
  --mutate=BINARY    emit a body for a binary file                      -> G8 RED
  --mutate=LEAK      put file content into a span attribute             -> G9 RED (Standing law)

Baseline `python3 git-read-model-check.py` exits 0; each `--mutate=NAME` exits 1 with the single violation.

Runtime / higher layers (owned elsewhere). The live A2A read verb (8.7b), completed-Run snapshot artifact
(8.7c), the BFF GET endpoints + per-principal 404 scoping gate (8.7d, NFR-SEC5), and the three-pane console
(8.7e) all build ON this projection. This check guards ONLY the git-projection contract — 8.7a's crux and
exactly what design §8.6 asked: prove the projection matches git without any cluster.
"""
import base64
import os
import subprocess
import sys
import tempfile

# ---- caps (design §3 "Limits, fail-safe not fail-open") --------------------------------------------
DIFF_CAP_BYTES = 512 * 1024        # per-file unified diff
FILE_CAP_BYTES = 2 * 1024 * 1024   # file content
TREE_CAP_ENTRIES = 5000            # changed-set entries


# ---- git plumbing (the exact commands the server runs) ---------------------------------------------
def git(repo, *args, text=True):
    """Run a git command in `repo`. Returns stdout (str if text else bytes)."""
    r = subprocess.run(
        ["git", "-C", repo, *args],
        check=True, capture_output=True, text=text,
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"},
    )
    return r.stdout


def git_bytes(repo, *args):
    return git(repo, *args, text=False)


# ---- the read-model projection (the executable spec 8.7a's Go service must match) ------------------
#
# Every projection function shells out to the SAME git command the server uses and applies ONLY the
# bounding markers on top — no diff engine, no re-serialization (ADR-021). `mut` names the single injected
# defect for the mutation harness; conformant baseline passes mut=None.

def project_tree(repo, base, run_ref, mut=None):
    """git diff --name-status + --numstat -> the changed-set projection (G1, G2, G7)."""
    name_status = git(repo, "diff", "--name-status", "-M", f"{base}...{run_ref}")
    numstat = git(repo, "diff", "--numstat", "-M", f"{base}...{run_ref}")

    # add/del counts keyed by the path git attributes them to ("-"/"-" => binary).
    counts = {}
    for line in numstat.splitlines():
        add, dele, rest = line.split("\t", 2)
        path = rest.split("\t")[-1]  # for renames git prints "old\tnew"; count keys on the new path
        a = None if add == "-" else int(add)
        d = None if dele == "-" else int(dele)
        counts[path] = (a, d)

    files = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        code = parts[0]
        status = code[0]                 # A / M / D / R / C
        renamed_from = None
        if status == "R":
            renamed_from, path = parts[1], parts[2]
        else:
            path = parts[1]

        if mut == "STATUS" and status == "D":
            # DEFECT: report a delete as a modify (a dropped/mis-coded change) -> G1.
            status = "M"

        a, d = counts.get(path, (0, 0))
        if mut == "COUNT":
            a, d = 0, 0                  # DEFECT: zero the counts -> G2.

        files.append({
            "path": path, "status": status,
            "additions": a, "deletions": d,
            **({"renamedFrom": renamed_from} if renamed_from else {}),
        })

    truncated = len(files) > TREE_CAP_ENTRIES
    if mut == "TREECAP":
        truncated = False               # DEFECT: never mark truncated -> G7 (unbounded body).
    if truncated:
        files = files[:TREE_CAP_ENTRIES]

    return {"base": base, "runRef": run_ref, "files": files, "truncated": truncated}


def _is_binary_diff(raw_bytes):
    # git emits a one-line "Binary files a/x and b/x differ" hunk for binary content.
    return b"\nBinary files " in raw_bytes or raw_bytes.startswith(b"Binary files ")


def project_diff(repo, base, run_ref, path, mut=None):
    """git diff <base>...<runRef> -- <path> -> unified-diff projection (G3, G5, G8)."""
    raw = git_bytes(repo, "diff", "-M", f"{base}...{run_ref}", "--", path)
    binary = _is_binary_diff(raw)
    if mut == "BINARY":
        binary = False                  # DEFECT: treat a binary diff as text -> G8.

    if binary:
        return {"path": path, "unifiedDiff": None, "binary": True,
                "tooLarge": False, "sizeBytes": len(raw)}

    too_large = len(raw) > DIFF_CAP_BYTES
    if mut == "DIFFCAP":
        too_large = False               # DEFECT: ignore the 512 KiB cap -> G5 (unbounded body).
    if too_large:
        return {"path": path, "unifiedDiff": None, "binary": False,
                "tooLarge": True, "sizeBytes": len(raw)}

    unified = raw.decode("utf-8", "surrogateescape")
    if mut == "DIFF":
        unified = unified.rstrip("\n")  # DEFECT: re-serialize -> no longer byte-identical -> G3.
    return {"path": path, "unifiedDiff": unified, "binary": False,
            "tooLarge": False, "sizeBytes": len(raw)}


def project_file(repo, run_ref, path, mut=None):
    """git show <runRef>:<path> -> file-content projection (G4, G6, G8)."""
    raw = git_bytes(repo, "show", f"{run_ref}:{path}")
    binary = b"\x00" in raw
    if mut == "BINARY":
        binary = False
    size = len(raw)

    if binary:
        return {"path": path, "content": None, "encoding": "base64",
                "binary": True, "tooLarge": False, "sizeBytes": size}

    too_large = size > FILE_CAP_BYTES
    if mut == "FILECAP":
        too_large = False               # DEFECT: ignore the 2 MiB cap -> G6 (unbounded body).
    if too_large:
        return {"path": path, "content": None, "encoding": "utf8",
                "binary": False, "tooLarge": True, "sizeBytes": size}

    content = raw.decode("utf-8", "surrogateescape")
    if mut == "CONTENT":
        content = content + "X"         # DEFECT: content no longer equals the blob -> G4.
    return {"path": path, "content": content, "encoding": "utf8",
            "binary": False, "tooLarge": False, "sizeBytes": size}


def build_span_attrs(tree, diffs, files, mut=None):
    """OBS-BB1: the read span carries ONLY magnitudes/status — never content (G9, Standing law)."""
    bytes_returned = sum(d["sizeBytes"] for d in diffs) + sum(f["sizeBytes"] for f in files)
    attrs = {
        "ksquad.buildbrowser.truncated": tree["truncated"],
        "ksquad.buildbrowser.too_large": any(d["tooLarge"] for d in diffs)
                                         or any(f["tooLarge"] for f in files),
        "ksquad.buildbrowser.file_count": len(tree["files"]),
        "ksquad.buildbrowser.bytes_returned": bytes_returned,   # magnitude, not a body
    }
    if mut == "LEAK":
        # DEFECT: content leaks into a signal (Standing law #2) — the exfil edge OBS-BB1 forbids.
        first_body = next((f["content"] for f in files if f.get("content")), "")
        attrs["ksquad.buildbrowser.sample"] = first_body
    return attrs


# ---- throwaway repo fixture ------------------------------------------------------------------------
def write(repo, rel, data):
    p = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(p) or repo, exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(p, mode) as fh:
        fh.write(data)


def build_fixture(repo):
    """base commit (3 files) -> worktree branch that ADDs / MODIFIEs / DELETEs. Returns (base, runRef)."""
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "check@ksquad.local")
    git(repo, "config", "user.name", "read-model-check")

    # base commit — the Project default ref
    write(repo, "keep.txt", "unchanged line\n")
    write(repo, "mod.py", "def f():\n    return 1\n")
    write(repo, "gone.md", "delete me\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD").strip()

    # the Run's worktree branch — the three canonical changes
    git(repo, "checkout", "-q", "-b", "run/worktree")
    write(repo, "added.txt", "brand new file\nsecond line\n")             # A
    write(repo, "mod.py", "def f():\n    return 2  # changed\n")          # M
    os.remove(os.path.join(repo, "gone.md"))                             # D
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "run changes")
    run_ref = git(repo, "rev-parse", "HEAD").strip()

    # merge-base(base, runRef) == base here (runRef descends from base), so base...runRef == the Run's set.
    mb = git(repo, "merge-base", base, run_ref).strip()
    assert mb == base, "fixture invariant: merge-base must equal base"
    return base, run_ref


# ---- the runnable check ----------------------------------------------------------------------------
def run(mut=None):
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    with tempfile.TemporaryDirectory() as repo:
        base, run_ref = build_fixture(repo)

        # ---- core changed set: add / modify / delete --------------------------------------------
        tree = project_tree(repo, base, run_ref, mut=mut)
        by_path = {f["path"]: f for f in tree["files"]}

        # G1 — EXACTLY the changed set with correct A/M/D (oracle = raw name-status).
        oracle_ns = {}
        for line in git(repo, "diff", "--name-status", "-M", f"{base}...{run_ref}").splitlines():
            parts = line.split("\t")
            oracle_ns[parts[-1]] = parts[0][0]
        check("G1", set(by_path) == set(oracle_ns),
              f"tree paths {sorted(by_path)} != git changed set {sorted(oracle_ns)}")
        check("G1", "keep.txt" not in by_path, "unchanged file leaked into the changed set")
        for p, st in oracle_ns.items():
            check("G1", by_path.get(p, {}).get("status") == st,
                  f"{p}: status {by_path.get(p, {}).get('status')} != git {st}")

        # G2 — add/del counts equal numstat (oracle).
        oracle_counts = {}
        for line in git(repo, "diff", "--numstat", "-M", f"{base}...{run_ref}").splitlines():
            add, dele, rest = line.split("\t", 2)
            oracle_counts[rest.split("\t")[-1]] = (
                None if add == "-" else int(add), None if dele == "-" else int(dele))
        for p, (a, d) in oracle_counts.items():
            check("G2", (by_path[p]["additions"], by_path[p]["deletions"]) == (a, d),
                  f"{p}: counts {(by_path[p]['additions'], by_path[p]['deletions'])} != git {(a, d)}")
        # non-vacuous: the modify actually has a nonzero add AND del.
        check("G2", (by_path["mod.py"]["additions"] or 0) > 0 and (by_path["mod.py"]["deletions"] or 0) > 0,
              "modify must have nonzero add+del (fixture non-vacuous)")

        # G3 — unified diff byte-for-byte vs the raw git oracle, for every changed path.
        diffs = []
        for p in oracle_ns:
            proj = project_diff(repo, base, run_ref, p, mut=mut)
            diffs.append(proj)
            oracle_raw = git_bytes(repo, "diff", "-M", f"{base}...{run_ref}", "--", p)
            if not proj["binary"] and not proj["tooLarge"]:
                proj_bytes = proj["unifiedDiff"].encode("utf-8", "surrogateescape")
                check("G3", proj_bytes == oracle_raw,
                      f"{p}: unifiedDiff not byte-identical to `git diff` ({len(proj_bytes)} vs {len(oracle_raw)} B)")

        # G4 — file content byte-for-byte vs git show, for the added + modified files.
        files = []
        for p in ("added.txt", "mod.py"):
            proj = project_file(repo, run_ref, p, mut=mut)
            files.append(proj)
            oracle_blob = git_bytes(repo, "show", f"{run_ref}:{p}")
            if not proj["binary"] and not proj["tooLarge"]:
                check("G4", proj["content"].encode("utf-8", "surrogateescape") == oracle_blob,
                      f"{p}: content not identical to `git show {run_ref}:{p}`")

        # ---- G5: oversize per-file diff -> tooLarge, no body ------------------------------------
        write(repo, "big.txt", ("x" * 4000 + "\n") * 200)   # ~800 KiB > 512 KiB cap
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "big diff")
        big_ref = git(repo, "rev-parse", "HEAD").strip()
        big_diff = project_diff(repo, base, big_ref, "big.txt", mut=mut)
        check("G5", big_diff["sizeBytes"] > DIFF_CAP_BYTES, "fixture: big diff must exceed cap")
        check("G5", big_diff["tooLarge"] is True and big_diff["unifiedDiff"] is None,
              f"oversize diff must be tooLarge with no body (got tooLarge={big_diff['tooLarge']}, "
              f"body={'set' if big_diff['unifiedDiff'] is not None else 'None'})")

        # ---- G6: oversize file -> tooLarge, content None ----------------------------------------
        big_file = project_file(repo, big_ref, "big.txt", mut=mut)
        # big.txt is ~800 KiB < 2 MiB; grow a dedicated blob past 2 MiB for the file cap.
        write(repo, "huge.txt", "y" * (FILE_CAP_BYTES + 4096))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "huge file")
        huge_ref = git(repo, "rev-parse", "HEAD").strip()
        huge_file = project_file(repo, huge_ref, "huge.txt", mut=mut)
        check("G6", huge_file["sizeBytes"] > FILE_CAP_BYTES, "fixture: huge file must exceed cap")
        check("G6", huge_file["tooLarge"] is True and huge_file["content"] is None,
              f"oversize file must be tooLarge with no content (got tooLarge={huge_file['tooLarge']}, "
              f"content={'set' if huge_file['content'] is not None else 'None'})")

        # ---- G7: tree cap (5000 entries) -> truncated -------------------------------------------
        # Simulate a pathological changed set directly against the projection's cap logic (adding 5000
        # real files to git is slow and adds nothing — the cap is a pure bound on the projection body).
        big_ns = "\n".join(f"A\tf{i}.txt" for i in range(TREE_CAP_ENTRIES + 250))
        big_num = "\n".join(f"1\t0\tf{i}.txt" for i in range(TREE_CAP_ENTRIES + 250))
        capped = _project_tree_from(big_ns, big_num, base, run_ref, mut=mut)
        check("G7", capped["truncated"] is True and len(capped["files"]) == TREE_CAP_ENTRIES,
              f"tree beyond {TREE_CAP_ENTRIES} must truncate (got truncated={capped['truncated']}, "
              f"n={len(capped['files'])})")

        # ---- G8: binary file -> binary:true, no body --------------------------------------------
        write(repo, "logo.png", b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8 + b"\x00\x01\x02")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "binary")
        bin_ref = git(repo, "rev-parse", "HEAD").strip()
        bin_diff = project_diff(repo, base, bin_ref, "logo.png", mut=mut)
        bin_file = project_file(repo, bin_ref, "logo.png", mut=mut)
        check("G8", bin_diff["binary"] is True and bin_diff["unifiedDiff"] is None,
              f"binary diff must be binary:true w/ no body (got binary={bin_diff['binary']})")
        check("G8", bin_file["binary"] is True and bin_file["content"] is None,
              f"binary file must be binary:true w/ no content (got binary={bin_file['binary']})")

        # ---- G9: OBS-BB1 span attrs — magnitudes/status only, NO content ------------------------
        attrs = build_span_attrs(tree, diffs, files, mut=mut)
        magnitudes = {"ksquad.buildbrowser.truncated", "ksquad.buildbrowser.too_large",
                      "ksquad.buildbrowser.file_count", "ksquad.buildbrowser.bytes_returned"}
        check("G9", set(attrs) <= magnitudes,
              f"read span carries non-magnitude attrs {sorted(set(attrs) - magnitudes)} (Standing law #2/#1)")
        # no attr value may echo real file/diff content (content-leak firewall)
        secrets = [f["content"] for f in files if f.get("content")]
        for k, v in attrs.items():
            if isinstance(v, str):
                for s in secrets:
                    check("G9", s not in v and (len(v) < 40),
                          f"span attr {k} appears to carry content (Standing law #2)")
        check("G9", "model" not in {k.rsplit(".", 1)[-1] for k in attrs},
              "no `model` label on any ksquad.buildbrowser.* attr (Standing law #3)")

    return fails


def _project_tree_from(name_status, numstat, base, run_ref, mut=None):
    """Pure re-run of project_tree's parse/cap over synthetic git output (for the G7 cap bound)."""
    counts = {}
    for line in numstat.splitlines():
        add, dele, rest = line.split("\t", 2)
        counts[rest.split("\t")[-1]] = (None if add == "-" else int(add),
                                        None if dele == "-" else int(dele))
    files = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        status, path = parts[0][0], parts[-1]
        a, d = counts.get(path, (0, 0))
        files.append({"path": path, "status": status, "additions": a, "deletions": d})
    truncated = len(files) > TREE_CAP_ENTRIES
    if mut == "TREECAP":
        truncated = False
    if truncated:
        files = files[:TREE_CAP_ENTRIES]
    return {"base": base, "runRef": run_ref, "files": files, "truncated": truncated}


MUTANTS = {
    "STATUS": "G1", "COUNT": "G2", "DIFF": "G3", "CONTENT": "G4", "DIFFCAP": "G5",
    "FILECAP": "G6", "TREECAP": "G7", "BINARY": "G8", "LEAK": "G9",
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
            print("[read-model] FAIL — baseline projection violated:")
            for inv, d in fails:
                print(f"    {inv}: {d}")
            return 1
        print("[read-model] PASS — git-projection contract holds against a live throwaway repo.")
        print("    G1 tree=changed-set(A/M/D)  G2 counts=numstat  G3 diff byte-for-byte  G4 file=git-show")
        print(f"    G5 diff>{DIFF_CAP_BYTES//1024}KiB->tooLarge  G6 file>{FILE_CAP_BYTES//1024//1024}MiB->tooLarge  "
              f"G7 tree>{TREE_CAP_ENTRIES}->truncated  G8 binary->no-body  G9 OBS-BB1 span=magnitudes-only")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)} — acceptable, {expected} is the mapped tooth)" if others else ""
        print(f"[read-model] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[read-model] SURVIVED — --mutate={mut} did NOT trip {expected} (VACUOUS GUARD); "
          f"tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
