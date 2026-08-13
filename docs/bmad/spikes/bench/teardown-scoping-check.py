#!/usr/bin/env python3
"""
Story 4.5 falsification — teardown-and-replace + per-principal PVC/cache scoping
(arch §9.3 teardown-and-replace / ADR-006, §9.4 per-principal scoping F6/D7, §12.1; NFR-SEC5).

Differential check over the *hygiene + workspace-mount decisions* a Run reconciler / pool
manager would make across a sequence of completed Runs on ONE Project by DIFFERENT principals.
It proves the harness has TEETH by first showing a NAIVE hygiene+scoping policy (in-place
reset + reuse pod across Runs, one shared per-Project cache subpath) leaks residue and one
principal's data into another principal's Run, then showing the §9.3/§9.4 policy
(teardown-and-replace + per-principal subpath) holds. stdlib-only; `python3 <file>`.

Two DISTINCT leak vectors, two distinct defenses (defense-in-depth):
  (1) POD residue — scratch files, in-memory secrets, git worktree state, poisoned build cache
      LIVING IN THE POD. Defended by TEARDOWN-AND-REPLACE (§9.3): the pod is DESTROYED after its
      Run and the pool replenishes a FRESH pod. Proving an in-place scrub left *zero* residue is a
      losing game (ADR-006 rationale) — so a reused/reset pod is modeled as retaining residue.
  (2) PVC residue — source + build cache on the PERSISTENT Project workspace PVC (persists across a
      principal's Runs by design, FR-C2). Defended by PER-PRINCIPAL SUBPATH partition (§9.4 F6/D7):
      a Run mounts ONLY its own principal's subpath, so principal B never reads principal A's cached
      artifacts/secrets even though the PVC is shared per-Project.

Invariants (AC1-AC5):
  AC1  teardown-and-replace is the DEFAULT: a completed Run's pod is destroyed, not reset-in-place;
       a fresh pod is replenished. Warm-pool economics survive (async replenish), reuse does not.
  AC2  a sandbox pod is NEVER reused/bound across two Runs (or two principals) — the §9.3 absolute.
  AC3  no POD residue crosses Runs: a Run's pod carries nothing authored by a prior Run (esp. a
       different principal). Teardown makes this true by construction; reset-in-place cannot prove it.
  AC4  workspace/cache access is PER-PRINCIPAL, not per-Project: a Run reads only its own principal's
       subpath. A shared per-Project subpath that exposes principal A's data to principal B's Run is
       a construction failure (§9.4, §12.1 per-principal Secret isolation).
  AC5  per-principal subpath is deterministic + collision-safe (principal-hash), and a principal's
       OWN cache DOES persist across that principal's Runs (partition scopes cross-principal, it does
       not defeat FR-C2 same-principal reuse).

AC-runtime (the S4 residue/reuse blast-radius case, NFR-SEC5) is PROVEN AT RUNTIME by the Epic X.2
residue test on a real cluster — this model guards the static hygiene+scoping SHAPE, the
construction-time crux; actual zero-residue is a property of pod destruction + subpath isolation,
observed by the runtime test, not decidable here.
"""
import hashlib
import sys


def principal_subpath(project, principal):
    """§9.4/AC5: deterministic, collision-safe per-principal partition key. A short stable hash of
    the principal id disambiguates (no cross-principal collision, principal-rename doesn't strand)."""
    h = hashlib.sha256(principal.encode()).hexdigest()[:12]
    return f"{project}/cache/{principal}-{h}"


# ---------------------------------------------------------------------------
# Models. A "pod" carries residue: a list of (author_run, author_principal).
# The Project workspace PVC is a dict subpath -> list of (author_run, author_principal),
# persisting across the whole sequence (it is the durable workspace, FR-C2).
# ---------------------------------------------------------------------------
def new_pod(pid):
    return {"id": pid, "residue": []}


def simulate(runs, *, teardown, per_principal_subpath):
    """Run the sequence under a hygiene policy (teardown vs in-place reset) and a scoping policy
    (per-principal subpath vs shared per-Project subpath). Returns the trace:
      binds     : run_id -> pod_id it was bound to (AC2 reuse detection)
      pod_reads : list of (run_id, run_principal, author_run, author_principal) POD residue reads
      pvc_reads : list of (run_id, run_principal, author_run, author_principal) PVC residue reads
      replaced  : count of fresh pods replenished after a completed Run (AC1)
    """
    pvc = {}                       # subpath -> [(author_run, author_principal), ...]  (durable)
    warm = new_pod("warm-0")       # the initially-warm pod
    binds, pod_reads, pvc_reads = {}, [], []
    replaced = 0

    for r in runs:
        rid, principal, project = r["id"], r["principal"], r["project"]

        # --- claim a sandbox ---
        pod = warm
        binds[rid] = pod["id"]

        # --- the Run READS what its pod + mounted subpath expose (before writing its own) ---
        for (a_run, a_principal) in pod["residue"]:
            pod_reads.append((rid, principal, a_run, a_principal))

        # which PVC subpath(s) does this Run's mount expose?
        if per_principal_subpath:
            exposed = [principal_subpath(project, principal)]        # ONLY own principal's subpath
        else:
            # naive: one shared per-Project subpath -> every principal's entries are visible
            exposed = [k for k in pvc if k.startswith(f"{project}/cache/")] or [f"{project}/cache/shared"]
        for sp in exposed:
            for (a_run, a_principal) in pvc.get(sp, []):
                pvc_reads.append((rid, principal, a_run, a_principal))

        # --- the Run WRITES its own scratch/secret into pod + workspace cache ---
        pod["residue"].append((rid, principal))
        if per_principal_subpath:
            wsp = principal_subpath(project, principal)
        else:
            wsp = f"{project}/cache/shared"                          # naive: everyone shares one subpath
        pvc.setdefault(wsp, []).append((rid, principal))

        # --- hygiene on completion ---
        if teardown:
            # §9.3: DESTROY the pod (residue dies with it) and replenish a FRESH one for the next Run.
            warm = new_pod(f"warm-{replaced + 1}")
            replaced += 1
        else:
            # naive in-place reset: SAME pod re-used next Run. We cannot prove the scrub cleared
            # every scratch file / in-mem secret / poisoned cache entry (ADR-006) -> residue retained.
            pass

    return {"binds": binds, "pod_reads": pod_reads, "pvc_reads": pvc_reads, "replaced": replaced}


def violations(trace, runs):
    """Invariant assertions over a simulate() trace. A cross-principal read is the crux leak."""
    v = []
    n = len(runs)

    # AC2: no pod bound to more than one Run
    pods_used = {}
    for rid, pod in trace["binds"].items():
        pods_used.setdefault(pod, []).append(rid)
    for pod, rs in pods_used.items():
        if len(rs) > 1:
            v.append(f"pod {pod} reused across Runs {sorted(rs)} [AC2 teardown-and-replace]")

    # AC3: no POD residue authored by a DIFFERENT Run reaches a later Run (cross-principal is worst)
    for (rid, principal, a_run, a_principal) in trace["pod_reads"]:
        if a_run != rid:
            tag = "CROSS-PRINCIPAL" if a_principal != principal else "same-principal"
            v.append(f"{rid}({principal}): read POD residue from {a_run}({a_principal}) [{tag}] [AC3]")

    # AC4: no PVC residue authored by a DIFFERENT PRINCIPAL reaches this Run (same-principal is OK/AC5)
    for (rid, principal, a_run, a_principal) in trace["pvc_reads"]:
        if a_principal != principal:
            v.append(f"{rid}({principal}): read PVC/cache residue from {a_run}({a_principal}) "
                     f"[CROSS-PRINCIPAL leak] [AC4]")

    # AC1: a fresh pod must be replenished after each completed Run (reuse forbidden, warm survives)
    if trace["replaced"] != n:
        v.append(f"only {trace['replaced']}/{n} completed Runs replenished a fresh pod [AC1]")

    return v


def check_same_principal_cache_persists():
    """AC5: the per-principal partition must NOT defeat FR-C2 — a principal's OWN cache persists
    across that principal's own Runs (scoping is cross-principal, not a same-principal reset)."""
    runs = [
        {"id": "a1", "principal": "p1", "project": "proj"},
        {"id": "a2", "principal": "p1", "project": "proj"},   # same principal, later Run
    ]
    t = simulate(runs, teardown=True, per_principal_subpath=True)
    # a2 (p1) SHOULD see a1 (p1)'s cache entry — same principal, that's the point of a persistent cache
    saw_own = any(a_run == "a1" and a_principal == "p1"
                  for (rid, principal, a_run, a_principal) in t["pvc_reads"] if rid == "a2")
    assert saw_own, "per-principal subpath wrongly hid a principal's OWN prior cache (breaks FR-C2)"
    # ...and it is NOT a cross-principal leak (same principal), so violations() stays clean
    assert violations(t, runs) == [], "same-principal cache reuse must not be flagged as a leak"
    print("[model] AC5 subpath   : per-principal partition preserves same-principal cache reuse "
          "(FR-C2 intact), collision-safe hash")


def check_subpath_determinism():
    """AC5: subpath is deterministic + collision-safe across distinct principals."""
    a = principal_subpath("proj", "alice")
    b = principal_subpath("proj", "bob")
    assert a == principal_subpath("proj", "alice"), "subpath must be deterministic"
    assert a != b, "distinct principals must not collide on a subpath"
    print(f"[model] AC5 keys      : distinct principals -> distinct subpaths "
          f"({a.split('/')[-1]} != {b.split('/')[-1]}), deterministic")


# --- test sequence: 3 completed Runs on ONE Project by TWO principals, interleaved ---
#   r1(p1) -> r2(p2) -> r3(p1). p2's Run sits between two p1 Runs so a leak in either
#   direction (p1->p2 residue, or p2 reading p1's cache) is exercised.
RUNS = [
    {"id": "r1", "principal": "p1", "project": "proj"},
    {"id": "r2", "principal": "p2", "project": "proj"},
    {"id": "r3", "principal": "p1", "project": "proj"},
]


def main():
    check_subpath_determinism()
    check_same_principal_cache_persists()

    # NAIVE: in-place reset (reuse pod) + shared per-Project cache subpath
    naive = simulate(RUNS, teardown=False, per_principal_subpath=False)
    naive_v = violations(naive, RUNS)
    print(f"[model] naive policy  : {len(naive_v)} residue/scoping violation(s) -> "
          f"{'DETECTED' if naive_v else 'NONE (TEETH LOST!)'}")
    for x in naive_v:
        print(f"          - {x}")

    # §9.3/§9.4: teardown-and-replace + per-principal subpath
    good = simulate(RUNS, teardown=True, per_principal_subpath=True)
    good_v = violations(good, RUNS)
    distinct_pods = len(set(good["binds"].values()))
    print(f"[model] §9.3/§9.4     : {len(good_v)} violations; {len(RUNS)} Runs -> "
          f"{distinct_pods} distinct pods, {good['replaced']} fresh replenishments, "
          f"0 cross-principal reads")
    for x in good_v:
        print(f"          - {x}")

    # teeth: naive must leak (both a cross-principal POD read and a cross-principal PVC read) and
    # reuse a pod; compliant must hold with per-Run distinct pods and full replenishment.
    naive_has_pvc_leak = any("[AC4]" in x for x in naive_v)
    naive_has_pod_leak = any("[AC3]" in x for x in naive_v)
    naive_has_reuse = any("[AC2" in x for x in naive_v)
    ok = (len(naive_v) > 0
          and naive_has_pvc_leak            # cross-principal cache leak detected
          and naive_has_pod_leak            # cross-principal pod residue detected
          and naive_has_reuse               # pod reuse detected
          and len(good_v) == 0              # compliant holds every invariant
          and distinct_pods == len(RUNS)    # every Run got its own fresh pod
          and good["replaced"] == len(RUNS))
    if ok:
        print("[model] PASS — naive detectably leaks residue + crosses principals; "
              "§9.3 teardown + §9.4 per-principal scoping hold AC1-AC5.")
        return 0
    print("[model] FAIL — invariant broken (see above).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
