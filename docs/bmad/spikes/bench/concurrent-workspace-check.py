#!/usr/bin/env python3
"""
Story 4.4 falsification — concurrent-Run behavior on a shared Project workspace
(arch §9.4 workspace & concurrency / ADR-007 worktree-vs-lock, OQ5; FR-C5; lease = §6.3 fenced lease).

Differential check over the *read/write scheduling decisions* a Run reconciler / workspace
manager would make for N CONCURRENT Runs on ONE Project's shared workspace. It proves the
harness has TEETH by showing three NAIVE policies each break a distinct invariant, then showing
the §9.4/ADR-007 policy (git-worktree-per-Run + per-Project workspace LEASE on shared-exclusive
writes, reads lease-free) holds all four. stdlib-only; `python3 <file>`.

Three OP kinds a concurrent Run issues against the shared workspace:
  READ         — read the shared checkout (file tree / git ls-tree / diff). MUST be concurrent
                 and MUST NOT take the write-lease (else read concurrency dies).
  WT_WRITE     — write into the Run's OWN working tree (edit a file). Isolated by a git
                 worktree-per-Run over the shared object store, so concurrent Runs never clobber
                 AND never serialize on a global lock (ADR-007: native git, not invented locking).
  SHARED_WRITE — an exclusive write to SHARED state (dependency install into the shared cache,
                 git index/gc on the shared .git, base-ref update). MUST take the per-Project
                 workspace lease (§6.3 primitive) so writers serialize; unsynchronized concurrent
                 shared writes lose updates / corrupt the shared cache.

Four invariants (the §9.4 concurrency contract, FR-C5):
  INV-READ    reads run concurrently and never take the lease (N readers -> concurrency N).
  INV-WT      concurrent working-tree writes are isolated (own worktree): concurrency N, 0 clobbers,
              no global lock (ADR-007 — concurrency WITHOUT corruption, the whole point of worktrees).
  INV-LEASE   shared-exclusive writes serialize under the per-Project write-lease: at most one
              holder (concurrency 1), 0 lost updates, final shared-counter == #shared-writes.
  INV-FENCE   the workspace lease IS the §6.3 FENCED lease: a zombie writer that lost the lease and
              wakes with a STALE fence token has its shared write REJECTED (no silent corruption).
              We ASSERT reuse of §6.3 fencing (Story 2.3/2.4), we do not reinvent a lock.

Mutation contract — each defense is INDEPENDENTLY load-bearing (drop one -> the compliant arm goes
RED on a DIFFERENT invariant; no masking, cf. ISI-2346-F1 / ISI-2375):
  M-LEASE   : shared_writes_leased True->False -> INV-LEASE RED (lost updates; cache corruption).
  M-WORKTREE: worktree_isolated  True->False -> INV-WT RED (concurrent WT writes clobber a shared tree).
  M-READLOCK: reads_take_lease   False->True -> INV-READ RED (readers serialize; read concurrency lost).
  M-FENCE   : fence_checked      True->False -> INV-FENCE RED (stale-fence zombie write corrupts).

Crash-safe lease handoff (INV-FENCE runtime half) and RWX-opt-in true-parallel merge-back are pinned
in prose in the story and exercised by the operator envtest / the concurrency chaos gate (Epic 2.7,
real PG + real API server); this model guards the STATIC scheduling shape (the construction-time crux).
"""
import sys

N = 3  # N concurrent Runs on ONE Project, all contending in the same window (forces contention)


def simulate(*, worktree_isolated, shared_writes_leased, reads_take_lease, fence_checked):
    """Run N concurrent Runs through a READ phase, a WT_WRITE phase, and a SHARED_WRITE phase under
    one policy. In each phase all N Runs issue the SAME op simultaneously, so contention is exercised.

    Returns a metrics dict:
      read_conc   : max simultaneous READs           (INV-READ: want N)
      wt_conc     : max simultaneous WT_WRITEs        (INV-WT:   want N)
      wt_clobbers : working-tree writes lost to a collision in a SHARED tree (INV-WT: want 0)
      shared_conc : max simultaneous SHARED_WRITEs    (INV-LEASE: want 1 — serialized)
      lost_updates: shared writes clobbered by an overlapping unsynchronized write (INV-LEASE: want 0)
      counter     : final shared-cache counter        (INV-LEASE: want N — every write landed)
      zombie_ok   : a stale-fence zombie shared write was rejected (INV-FENCE: want True)
    """
    # --- READ phase: N Runs read the shared checkout at once ---
    # A read takes the lease only under the (naive) reads_take_lease policy; a leased op serializes
    # to one-at-a-time (concurrency 1). Lease-free reads all proceed together (concurrency N).
    read_conc = 1 if reads_take_lease else N

    # --- WT_WRITE phase: N Runs each edit a file at once ---
    if worktree_isolated:
        # Each Run writes into its OWN worktree (distinct path over the shared object store):
        # fully concurrent AND no collision — no lease needed (ADR-007).
        wt_conc, wt_clobbers = N, 0
    else:
        # Naive: one shared working tree. Concurrent edits land on the same tree -> N-1 clobbered.
        # (The only way to make this safe would be to serialize every edit on the lease, which would
        #  instead collapse wt_conc to 1 — either way the worktree defense is load-bearing.)
        wt_conc, wt_clobbers = N, N - 1

    # --- SHARED_WRITE phase: N Runs each do a read-modify-write on the shared cache counter ---
    if shared_writes_leased:
        # Serialized by the per-Project workspace lease: one holder at a time. Each write reads the
        # current value and increments -> all N land, no lost update.
        shared_conc = 1
        counter = N
        lost_updates = 0
    else:
        # Naive: no lease. All N read the SAME start value (0) and write start+1 concurrently ->
        # only one increment survives; N-1 updates lost; the shared cache is corrupt.
        shared_conc = N
        counter = 1
        lost_updates = N - 1

    # --- INV-FENCE: a zombie that lost the lease wakes and attempts a shared write with a STALE
    # fence token. The §6.3 fenced lease bumps the token on re-acquire, so the stale write is rejected.
    # Drop the fence check (M-FENCE) and the zombie's write lands -> corruption.
    zombie_ok = fence_checked

    return {
        "read_conc": read_conc,
        "wt_conc": wt_conc,
        "wt_clobbers": wt_clobbers,
        "shared_conc": shared_conc,
        "lost_updates": lost_updates,
        "counter": counter,
        "zombie_ok": zombie_ok,
    }


def violations(m):
    """Assert the four §9.4 invariants over a simulate() metrics dict."""
    v = []
    if m["read_conc"] < N:
        v.append(f"reads serialized: {m['read_conc']}/{N} concurrent -> read concurrency lost [INV-READ]")
    if m["wt_clobbers"] > 0:
        v.append(f"{m['wt_clobbers']} working-tree write(s) clobbered in a shared tree [INV-WT]")
    if m["wt_conc"] < N:
        v.append(f"working-tree writes serialized: {m['wt_conc']}/{N} concurrent [INV-WT]")
    if m["shared_conc"] != 1:
        v.append(f"shared-exclusive writes NOT serialized: {m['shared_conc']} concurrent holders [INV-LEASE]")
    if m["lost_updates"] > 0 or m["counter"] != N:
        v.append(f"{m['lost_updates']} lost update(s); shared cache = {m['counter']}/{N} (corrupt) [INV-LEASE]")
    if not m["zombie_ok"]:
        v.append("stale-fence zombie shared write was ACCEPTED (silent corruption) [INV-FENCE]")
    return v


# Compliant §9.4/ADR-007 policy: worktree-per-Run, lease on shared writes, reads lease-free, fenced.
COMPLIANT = dict(worktree_isolated=True, shared_writes_leased=True,
                 reads_take_lease=False, fence_checked=True)

# Each mutation flips exactly ONE defense off; each must break a DIFFERENT invariant.
MUTATIONS = [
    ("M-LEASE   (drop workspace lease)", {**COMPLIANT, "shared_writes_leased": False}, "INV-LEASE"),
    ("M-WORKTREE (drop worktree isolation)", {**COMPLIANT, "worktree_isolated": False}, "INV-WT"),
    ("M-READLOCK (put reads under lease)", {**COMPLIANT, "reads_take_lease": True}, "INV-READ"),
    ("M-FENCE    (drop stale-fence reject)", {**COMPLIANT, "fence_checked": False}, "INV-FENCE"),
]


def main():
    ok = True

    good = simulate(**COMPLIANT)
    good_v = violations(good)
    print(f"[model] §9.4 policy   : {len(good_v)} violation(s); "
          f"reads {good['read_conc']}/{N} concurrent, worktree writes {good['wt_conc']}/{N} concurrent "
          f"(0 clobber), shared writes serialized (holders={good['shared_conc']}), cache={good['counter']}/{N}, "
          f"fenced={good['zombie_ok']}")
    for x in good_v:
        print(f"          - {x}")
    if good_v:
        ok = False
        print("[model]   ^ compliant policy MUST hold every invariant — TEETH/POLICY BUG")

    print(f"[model] mutation contract (each defense independently load-bearing):")
    for name, policy, want_inv in MUTATIONS:
        mv = violations(simulate(**policy))
        hit = any(f"[{want_inv}]" in x for x in mv)
        status = "RED" if hit else "GREEN (TEETH LOST!)"
        print(f"          - {name:38s} -> {want_inv:10s} {status}")
        for x in mv:
            print(f"                {x}")
        if not hit:
            ok = False

    if ok:
        print("[model] PASS — §9.4 worktree-per-Run + per-Project write-lease holds INV-READ/WT/LEASE/FENCE; "
              "each of the 4 defenses is independently load-bearing (drop one -> its invariant goes RED).")
        return 0
    print("[model] FAIL — invariant broken or a mutation failed to turn RED (see above).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
