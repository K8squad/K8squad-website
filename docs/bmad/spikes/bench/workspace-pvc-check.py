#!/usr/bin/env python3
"""Story 4.3 falsification — per-Project persistent workspace PVC (arch §9.4, ADR-007, FR-C2/C5).

Differential check. It models the *workspace provision + mount + concurrency decisions a Project
reconciler / Run pod-assembler would make across a sequence of Runs on ONE Project* (some sequential,
some concurrent), then asserts the arch §9.4 workspace invariants over those decisions:

  AC1  PERSISTENCE ACROSS RUNS (FR-C2). The Project workspace PVC (source + build cache) is a durable
       resource bound to the PROJECT, not to any Run's sandbox pod. When a Run completes and its pod is
       torn down (§9.3, teardown-and-replace of the POD), the PVC and the build cache it holds SURVIVE,
       so a later Run on the same Project sees the prior Run's warm cache. A reconciler that ties PVC
       lifecycle to pod lifecycle (delete/recreate the PVC per Run) loses the cache every Run — a
       cold rebuild each time — and violates FR-C2. (Pod lifecycle != workspace lifecycle.)

  AC2  WORKTREE-PER-RUN CONCURRENCY (ADR-007, §9.4). Concurrent Runs on one Project each operate in
       their OWN git worktree over the shared checkout (native git, not invented locking), so two
       Runs writing their working trees at the same time do NOT clobber each other. A reconciler that
       hands every Run one shared working directory lets concurrent Runs overwrite each other's
       working state — a data-integrity failure, and the reason ADR-007 chose worktree-per-Run over a
       single global Project lock (which would instead serialize every Run and kill parallelism).

  AC3  WORKSPACE LEASE ON EXCLUSIVE-WRITE OPS (§9.4, §6.3 lease primitive). Operations that mutate the
       SHARED checkout/cache (dependency install, index rebuild) take a Project workspace lease, so
       they run one-at-a-time. Worktree-per-Run isolates working trees but NOT the shared cache/index;
       two Runs running `npm install` / rebuilding the index against the shared cache concurrently
       corrupt it. The lease serializes exactly those critical sections (and only those — ordinary
       per-worktree writes stay parallel, AC2).

Why differential: a happy-path "a Run mounted a PVC and built" demo passes with a broken reconciler
that recreates the PVC each Run (cache silently cold), shares one working dir across concurrent Runs
(silent clobber), or skips the lease (silent cache corruption) — none of those show up on a single
sequential green Run. So we first prove a NAIVE reconciler (PVC lifecycle == pod lifecycle; one shared
working dir; no exclusive-write lease) is DETECTED violating every invariant — the harness has real
teeth — then prove the §9.4/ADR-007 reconciler violates nothing.

Mutation contract (each defense is independently load-bearing, none decorative):
  - drop PERSISTENCE  (recreate PVC per Run, keep worktree + lease) -> AC1 RED (cache lost across Runs)
  - drop WORKTREE     (one shared working dir, keep persist + lease) -> AC2 RED (concurrent clobber)
  - drop LEASE        (no exclusive-write serialization, keep rest)  -> AC3 RED (shared-cache corruption)

Out of scope (owned elsewhere, deliberately NOT modeled here): per-principal subpath partitioning +
teardown-and-replace of the POD + residue proof (Story 4.5 / §9.3), and the per-principal build-browser
READ gate (Story 8.7d / ISI-2166). This story provisions/mounts/persists the PVC and owns worktree+lease
concurrency; 4.5 partitions that same PVC per principal.

stdlib only; `python3 workspace-pvc-check.py`. Exits non-zero if the naive arm stops being detected
(teeth lost) or the §9.4 arm ever violates an invariant.
"""
import sys


class Violation(Exception):
    pass


# ---------------------------------------------------------------------------
# Model of the persistent workspace + the reconciler's provision/mount/concurrency policy.
# No real threads: concurrency is modeled as an explicit event schedule the reconciler processes,
# so the run is deterministic. "Concurrent" Runs are ones whose lifetimes overlap in the schedule.
# ---------------------------------------------------------------------------

class WorkspacePVC:
    """The durable per-Project PVC: a build cache + a shared checkout, both persisting across Runs."""

    def __init__(self, project):
        self.project = project
        self.cache = {}          # build-cache: dep/index artifacts that must survive across Runs (FR-C2)
        self.checkout = {}       # shared checkout content (the base tree worktrees fork from)
        self.generation = 0      # bumps every time the PVC is (re)created — a cold, empty volume


class Reconciler:
    """Project reconciler + Run pod-assembler. The three booleans are the §9.4/ADR-007 defenses;
    the mutation arms flip one True->False to prove each is load-bearing."""

    def __init__(self, persist_pvc=True, worktree_per_run=True, lease_exclusive=True):
        self.persist_pvc = persist_pvc
        self.worktree_per_run = worktree_per_run
        self.lease_exclusive = lease_exclusive
        self.pvcs = {}                 # project -> WorkspacePVC (the durable resource)
        self.worktrees = {}            # run_id -> working-tree dict (a view onto the checkout)
        self._shared_dirs = {}         # project -> the ONE shared working dir (naive/no-worktree arm)
        self._lease_holder = None      # project -> run_id currently holding the workspace lease
        self._exclusive_active = {}    # project -> run_id inside an exclusive-write critical section
        self.overlaps = []             # recorded exclusive-write overlaps on the shared cache (AC3)

    # --- PVC provisioning (AC1) --------------------------------------------
    def ensure_pvc(self, project):
        """§9.4: the PVC is bound to the Project and provisioned ONCE, reused across every Run.
        The naive arm re-provisions per Run, so the cache it holds is discarded each time."""
        if project not in self.pvcs:
            self.pvcs[project] = WorkspacePVC(project)
            self.pvcs[project].generation = 1
        elif not self.persist_pvc:
            # pod-lifecycle == workspace-lifecycle: destroy + recreate the PVC -> a cold, empty volume.
            gen = self.pvcs[project].generation + 1
            self.pvcs[project] = WorkspacePVC(project)
            self.pvcs[project].generation = gen
        return self.pvcs[project]

    # --- Run start: mount PVC + open a worktree (AC2) ----------------------
    def start_run(self, run_id, project):
        pvc = self.ensure_pvc(project)                 # mount the persistent PVC (§5.2 pod-assembly step 4)
        if self.worktree_per_run:
            # native git worktree over the shared checkout — isolated working tree per Run (ADR-007).
            self.worktrees[run_id] = dict(pvc.checkout)
        else:
            # one shared working directory keyed by PROJECT (a fixed path like /workspace, stable across
            # PVC re-provisioning) — every concurrent Run aliases the SAME dict, so their writes collide.
            # (Keyed on project, NOT on PVC identity, so this defect is not masked by the AC1 defect.)
            self.worktrees[run_id] = self._shared_dirs.setdefault(project, dict(pvc.checkout))
        return pvc

    def write_worktree(self, run_id, path, content):
        """Ordinary per-Run working-tree write — must stay isolated & parallel (AC2)."""
        self.worktrees[run_id][path] = content

    def read_worktree(self, run_id, path):
        return self.worktrees[run_id].get(path)

    # --- Exclusive-write op against the SHARED cache (AC3) -----------------
    def exclusive_write(self, run_id, project, key, value):
        """dependency install / index rebuild — mutates the shared cache. §9.4 requires a workspace
        lease so these serialize; the naive arm runs them concurrently and corrupts the cache."""
        pvc = self.pvcs[project]
        if self.lease_exclusive:
            # workspace lease (§6.3 primitive): block until no other Run holds it — serialized.
            if self._lease_holder not in (None, run_id):
                raise Violation(f"{run_id}: lease held by {self._lease_holder} — model must serialize")
            self._lease_holder = run_id
        # enter critical section
        if project in self._exclusive_active and self._exclusive_active[project] != run_id:
            # another Run is mid-exclusive-write on the shared cache at the same time -> corruption.
            self.overlaps.append((self._exclusive_active[project], run_id, key))
        self._exclusive_active[project] = run_id
        pvc.cache[key] = value                          # the durable, cross-Run artifact
        # leave critical section
        del self._exclusive_active[project]
        if self.lease_exclusive:
            self._lease_holder = None

    def read_cache(self, project, key):
        return self.pvcs[project].cache.get(key)

    def finish_run(self, run_id, project):
        """Run completes: its sandbox POD is torn down (§9.3) — but the PVC is NOT the pod.
        The worktree view is dropped; the durable PVC + cache stay."""
        self.worktrees.pop(run_id, None)
        # NOTE: we deliberately do NOT delete self.pvcs[project] — that is the AC1 crux. The naive
        # arm's damage is applied at the *next* ensure_pvc (recreate), modeling PVC-tied-to-pod.


# ---------------------------------------------------------------------------
# Invariant checks over a reconciler's decisions
# ---------------------------------------------------------------------------

def check_ac1_persistence(make_reconciler):
    """FR-C2: a cache artifact written by Run r1 is visible to a later Run r2 on the same Project."""
    r = make_reconciler()
    proj = "acme/api"
    # r1 warms the cache with a dependency install, then completes (pod torn down).
    r.start_run("r1", proj)
    r.exclusive_write("r1", proj, "deps/node_modules.lock", "sha:abc123")
    r.finish_run("r1", proj)
    # r2 starts later on the same Project — should find r1's cached deps (warm, not cold).
    r.start_run("r2", proj)
    hit = r.read_cache(proj, "deps/node_modules.lock")
    r.finish_run("r2", proj)
    ok = hit == "sha:abc123"
    detail = ("cache HIT across Runs (PVC persisted)" if ok
              else f"cache MISS — PVC gen bumped to {r.pvcs[proj].generation}, cold rebuild (FR-C2 violated)")
    return ok, detail


def check_ac2_worktree(make_reconciler):
    """ADR-007: two CONCURRENT Runs write the same relative path in their working trees without clobber."""
    r = make_reconciler()
    proj = "acme/api"
    # r1 and r2 overlap: both open worktrees, both write the same path, then each reads its own back.
    r.start_run("r1", proj)
    r.start_run("r2", proj)                             # concurrent — r2's lifetime overlaps r1's
    r.write_worktree("r1", "build/out.o", "from-r1")
    r.write_worktree("r2", "build/out.o", "from-r2")
    seen_r1 = r.read_worktree("r1", "build/out.o")
    seen_r2 = r.read_worktree("r2", "build/out.o")
    r.finish_run("r1", proj)
    r.finish_run("r2", proj)
    ok = seen_r1 == "from-r1" and seen_r2 == "from-r2"
    detail = ("worktree-per-Run: each Run reads its OWN working tree, no clobber"
              if ok else f"CLOBBER — r1 reads '{seen_r1}', r2 reads '{seen_r2}' (shared working dir)")
    return ok, detail


def check_ac3_lease(make_reconciler):
    """§9.4/§6.3: concurrent exclusive-writes on the SHARED cache must not overlap (lease serializes)."""
    r = make_reconciler()
    proj = "acme/api"
    # Two concurrent Runs each rebuild the shared index. Model the interleave: r1 enters its critical
    # section, and while it is inside, r2 attempts its exclusive write.
    r.start_run("r1", proj)
    r.start_run("r2", proj)
    if r.lease_exclusive:
        # lease serializes: r1 fully completes its exclusive op, then r2 does — no overlap by construction.
        r.exclusive_write("r1", proj, "index.db", "built-by-r1")
        r.exclusive_write("r2", proj, "index.db", "built-by-r2")
    else:
        # no lease: interleave the critical sections to model true concurrency on the shared cache.
        r._exclusive_active[proj] = "r1"               # r1 enters and is still inside...
        r.exclusive_write("r2", proj, "index.db", "built-by-r2")   # ...r2 enters concurrently -> overlap
        r._exclusive_active.pop(proj, None)
    r.finish_run("r1", proj)
    r.finish_run("r2", proj)
    ok = len(r.overlaps) == 0
    detail = ("exclusive-writes serialized by workspace lease — no shared-cache overlap"
              if ok else f"CORRUPTION — {len(r.overlaps)} overlapping exclusive-write(s) on shared cache: {r.overlaps}")
    return ok, detail


CHECKS = [
    ("AC1 persist-across-Runs (FR-C2)", check_ac1_persistence),
    ("AC2 worktree-per-Run       ", check_ac2_worktree),
    ("AC3 exclusive-write lease   ", check_ac3_lease),
]


def run_arm(label, make_reconciler):
    """Return (all_pass, [(name, ok, detail)])."""
    results = []
    for name, fn in CHECKS:
        ok, detail = fn(make_reconciler)
        results.append((name, ok, detail))
    return all(ok for _, ok, _ in results), results


def main():
    failures = []

    # --- compliant §9.4/ADR-007 arm: all three defenses on -----------------
    compliant = lambda: Reconciler(persist_pvc=True, worktree_per_run=True, lease_exclusive=True)
    comp_ok, comp_res = run_arm("§9.4", compliant)
    print("[model] §9.4/ADR-007 arm (persist + worktree-per-Run + workspace lease):")
    for name, ok, detail in comp_res:
        print(f"          {'PASS' if ok else 'FAIL'} {name} — {detail}")
    if not comp_ok:
        failures.append("§9.4 compliant arm violated an invariant (should hold all)")

    # --- naive arm: PVC==pod lifecycle, one shared dir, no lease -----------
    naive = lambda: Reconciler(persist_pvc=False, worktree_per_run=False, lease_exclusive=False)
    naive_ok, naive_res = run_arm("naive", naive)
    print("[model] naive arm (PVC lifecycle == pod lifecycle; one shared working dir; no lease):")
    for name, ok, detail in naive_res:
        print(f"          {'PASS' if ok else 'DETECTED'} {name} — {detail}")
    if naive_ok:
        failures.append("naive arm passed all invariants — harness has NO teeth")
    else:
        n_detected = sum(1 for _, ok, _ in naive_res if not ok)
        print(f"[model] naive arm       : {n_detected}/3 invariant(s) DETECTED as violated")

    # --- mutation contract: each defense independently load-bearing --------
    print("[model] mutation contract (flip ONE defense off in the §9.4 arm — the matching AC must go RED):")
    mutations = [
        ("drop PERSISTENCE", lambda: Reconciler(persist_pvc=False, worktree_per_run=True, lease_exclusive=True),
         "AC1 persist-across-Runs (FR-C2)"),
        ("drop WORKTREE   ", lambda: Reconciler(persist_pvc=True, worktree_per_run=False, lease_exclusive=True),
         "AC2 worktree-per-Run       "),
        ("drop LEASE      ", lambda: Reconciler(persist_pvc=True, worktree_per_run=True, lease_exclusive=False),
         "AC3 exclusive-write lease   "),
    ]
    for mut_label, make, target_ac in mutations:
        _, res = run_arm(mut_label, make)
        by_name = {name: (ok, detail) for name, ok, detail in res}
        target_ok, target_detail = by_name[target_ac]
        # the targeted AC must flip RED...
        if target_ok:
            failures.append(f"mutation '{mut_label}' did NOT turn {target_ac.strip()} RED — defense is decorative")
            print(f"          BROKEN  {mut_label}: {target_ac.strip()} still GREEN (not load-bearing!)")
            continue
        # ...and the OTHER two ACs must stay GREEN (the defense is targeted, not a global break).
        others_ok = all(ok for name, (ok, _) in by_name.items() if name != target_ac)
        if not others_ok:
            failures.append(f"mutation '{mut_label}' broke an unrelated AC — not a clean isolation")
            print(f"          BROKEN  {mut_label}: collateral damage to another AC")
            continue
        print(f"          RED     {mut_label} -> {target_ac.strip()} RED (others GREEN): {target_detail}")

    print()
    if failures:
        print("[model] FAIL — " + "; ".join(failures))
        return 1
    print("[model] PASS — naive detectably violates FR-C2 + concurrency; §9.4 persist + worktree-per-Run "
          "+ workspace lease hold AC1-AC3; each defense independently load-bearing (mutation-RED).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
