#!/usr/bin/env python3
"""
Story X.2 falsification — residue/reuse test across Runs and principals
(arch §9.3 teardown-and-replace / ADR-006, §9.4 per-principal scoping F6/D7, §12.1;
 FR-C6, NFR-SEC5, R12; S4 blast-radius suite testing §6.5; L4 §14.4).

This is the RUNTIME RESIDUE ORACLE — the acceptance check that Story 4.5's static shape
bench (`teardown-scoping-check.py`) explicitly deferred to Epic X.2: *"actual zero-residue is
a property of pod destruction + subpath isolation, observed by the runtime test, not decidable
[in the shape model]."* Where 4.5 modelled the reconciler's DECISION (does it tear down? per-
principal subpath?), X.2 models the ADVERSARIAL OBSERVATION: a first Run writes a known poison
token into every residue channel §9.3 names; a second Run (a DIFFERENT principal) then probes
each channel and MUST observe nothing authored by the first Run.

Why a differential oracle and not just "assert clean": the story's charter is *"Gates the
reset-in-place optimization decision."* The oracle is therefore POLICY-AGNOSTIC — it scores a
CANDIDATE hygiene policy, so the exact same test that passes teardown-and-replace is the gate a
future reset-in-place scrub (should ISI-2113 ever show replace-cost prohibitive) would have to
clear. ADR-006's thesis — *proving an in-place scrub left zero residue is a losing game* — is
made operational here: a reset-in-place policy that scrubs the obvious channels but misses even
one (tmpfs secret, poisoned cache, credential env) is DETECTED, so the gate blocks the
optimization by construction. stdlib-only; `python3 <file>`  (add `--mutate` for the teeth run).

The SIX residue channels (the four §9.3 names + credential env + the cross-principal PVC vector):
  scratch-fs          scratch files on the pod's ephemeral fs (/tmp, /workspace scratch)
  in-mem-secret       in-memory / tmpfs secret material (/dev/shm, memfd, env-resident tokens)
  git-worktree        git worktree state — staged index, checked-out branch, dirty tree
  build-cache-pod     poisoned build-cache entries living IN THE POD (compiler/module cache)
  cred-env            credential env vars / mounted Secret files still present in the sandbox
  pvc-cross-principal persistent Project-PVC cache subpath authored by a DIFFERENT principal (§9.4)

Each channel is an INDEPENDENT probe. `--mutate` proves no probe is decorative: dropping any one
probe makes the oracle blind to a real leak on that channel (a reset-in-place-partial policy then
falsely PASSES) — the ISI-2346-F1 / ISI-2363-F1 teeth-gap contract, per-channel.

RUNTIME BINDING (kind, required CI artifact): this file is the oracle. The kind/kubectl driver
that plants the poison in a real sandbox and re-reads it from the successor Run is
`residue-reuse-kind.sh` (see the story doc §Runtime harness); the driver feeds observed channel
state into `observe()` and asserts `violations()==[]`. Running this file with no cluster proves
the oracle's teeth on the model so a green cluster run cannot be a vacuous pass.
"""
import hashlib
import sys

POISON = "POISON-TOKEN-run1"   # what Run 1 writes into every channel; Run 2 must never observe it

# The six residue channels the oracle probes. Ordered pod-local first, durable last.
CHANNELS = [
    "scratch-fs",
    "in-mem-secret",
    "git-worktree",
    "build-cache-pod",
    "cred-env",
    "pvc-cross-principal",
]


def principal_subpath(project, principal):
    """§9.4/4.5-AC5: deterministic, collision-safe per-principal PVC partition key (shared with
    `teardown-scoping-check.py` so the two benches agree on the partition scheme)."""
    h = hashlib.sha256(principal.encode()).hexdigest()[:12]
    return f"{project}/cache/{principal}-{h}"


# ---------------------------------------------------------------------------
# The world a Run runs in. A `pod` carries per-channel residue in-band; the Project workspace PVC
# is durable across the whole sequence (FR-C2) and is keyed by subpath.
# ---------------------------------------------------------------------------
def new_pod(pid):
    # a FRESH pod from the template: every pod-local channel starts empty.
    return {"id": pid, "scratch-fs": [], "in-mem-secret": [], "git-worktree": [],
            "build-cache-pod": [], "cred-env": []}


POD_CHANNELS = ("scratch-fs", "in-mem-secret", "git-worktree", "build-cache-pod", "cred-env")


def write_poison(pod, pvc, run):
    """Run 1 (the adversary) plants POISON into every channel it can reach."""
    rid, principal, project = run["id"], run["principal"], run["project"]
    for ch in POD_CHANNELS:
        pod[ch].append((POISON, rid, principal))
    # durable PVC: the Run writes its own principal's cache subpath (legitimate, FR-C2) — but the
    # poison lands there too, so a SHARED-subpath policy would expose it cross-principal.
    pvc.setdefault(principal_subpath(project, principal), []).append((POISON, rid, principal))


def scrub(pod, coverage):
    """Apply a reset-in-place scrub of the given per-channel `coverage` to a REUSED pod. A channel
    in `coverage` is wiped; one not covered retains its residue — ADR-006's 'losing game': an
    in-place scrub cannot credibly claim total coverage of tmpfs secrets / poisoned caches / env."""
    for ch in POD_CHANNELS:
        if ch in coverage:
            pod[ch] = []


def observe(pod, pvc, run, *, per_principal_subpath, probes):
    """Run 2 probes each ENABLED channel and records everything it can see that it did not author.
    `probes` is the set of live probes (`--mutate` drops one to prove it was load-bearing).
    Returns list of (channel, token, author_run, author_principal) observations."""
    rid, principal, project = run["id"], run["principal"], run["project"]
    seen = []
    for ch in POD_CHANNELS:
        if ch not in probes:
            continue
        for (tok, a_run, a_principal) in pod[ch]:
            seen.append((ch, tok, a_run, a_principal))
    if "pvc-cross-principal" in probes:
        if per_principal_subpath:
            exposed = [principal_subpath(project, principal)]           # ONLY own subpath (§9.4)
        else:
            exposed = [k for k in pvc if k.startswith(f"{project}/cache/")]  # naive shared view
        for sp in exposed:
            for (tok, a_run, a_principal) in pvc.get(sp, []):
                seen.append(("pvc-cross-principal", tok, a_run, a_principal))
    return seen


def simulate(*, teardown, scrub_coverage, per_principal_subpath, probes):
    """Two Runs on ONE Project by DIFFERENT principals: Run1(p1) plants poison and completes; the
    pool serves Run2(p2), which observes. `teardown=True` destroys+replaces the pod (§9.3);
    `teardown=False` reuses it after a `scrub_coverage` reset-in-place scrub (the candidate opt)."""
    project = "proj"
    run1 = {"id": "run1", "principal": "p1", "project": project}
    run2 = {"id": "run2", "principal": "p2", "project": project}
    pvc = {}
    pod = new_pod("warm-0")

    # --- Run 1: adversary plants poison in every channel, then completes ---
    write_poison(pod, pvc, run1)

    # --- hygiene on completion ---
    if teardown:
        pod = new_pod("warm-1")               # §9.3: residue dies with the destroyed pod
    else:
        scrub(pod, scrub_coverage)            # reuse the SAME pod after an in-place scrub

    # --- Run 2 (different principal) observes ---
    observed = observe(pod, pvc, run2, per_principal_subpath=per_principal_subpath, probes=probes)
    return {"pod_id": pod["id"], "observed": observed,
            "observer_run": run2["id"], "observer_principal": run2["principal"]}


def violations(trace):
    """The oracle's verdict: ANY observation of a token authored by another Run is residue; a
    different-principal author is the crux cross-principal leak (NFR-SEC5). Same-principal cache
    reuse is legitimate (FR-C2, 4.5-AC5) and is NOT flagged. The observer is read from the trace,
    so the same verdict logic serves the cross-principal case and the same-principal control."""
    obs_run, obs_principal = trace["observer_run"], trace["observer_principal"]
    v = []
    for (ch, tok, a_run, a_principal) in trace["observed"]:
        if a_run == obs_run:
            continue                          # a Run seeing its own state is fine
        if a_principal == obs_principal:
            continue                          # FR-C2 legitimate same-principal cache persistence
        v.append(f"{obs_run}({obs_principal}): observed residue [{ch}] token={tok} "
                 f"from {a_run}({a_principal}) [CROSS-PRINCIPAL]")
    return v


# --- policies under test ------------------------------------------------------
FULL = set(POD_CHANNELS)


def run_policy(name, *, teardown, scrub_coverage, per_principal_subpath, probes=None):
    probes = set(CHANNELS) if probes is None else probes
    t = simulate(teardown=teardown, scrub_coverage=scrub_coverage,
                 per_principal_subpath=per_principal_subpath, probes=probes)
    v = violations(t)
    return t, v


def check_same_principal_persists(probes):
    """Positive control: the oracle must NOT over-fire on legitimate same-principal PVC cache
    (FR-C2 / 4.5-AC5). Run1(p1) writes cache; a LATER Run by the SAME principal p1 re-reads it —
    that is the whole point of a persistent per-Project cache, and must not be flagged as residue."""
    project = "proj"
    pvc = {}
    pvc.setdefault(principal_subpath(project, "p1"), []).append(("CACHE-p1", "run1", "p1"))
    r2 = {"id": "run2b", "principal": "p1", "project": project}   # SAME principal, later Run
    seen = observe(new_pod("warm-x"), pvc, r2, per_principal_subpath=True, probes=probes)
    trace = {"observed": seen, "observer_run": r2["id"], "observer_principal": r2["principal"]}
    saw_own = any(a_run == "run1" and a_principal == "p1" for (_ch, _t, a_run, a_principal) in seen)
    ok = saw_own and violations(trace) == []
    print(f"[oracle] positive ctrl : same-principal cache persists (FR-C2) and is NOT flagged -> "
          f"{'OK' if ok else 'BROKEN'}")
    return ok


def main(mutate=False):
    probes = set(CHANNELS)

    # (A) §9.3/§9.4 COMPLIANT: teardown-and-replace + per-principal subpath -> clean across all 6.
    _, good_v = run_policy("teardown+per-principal", teardown=True, scrub_coverage=FULL,
                           per_principal_subpath=True, probes=probes)
    print(f"[oracle] §9.3/§9.4     : teardown-and-replace + per-principal subpath -> "
          f"{len(good_v)} residue observation(s) {'CLEAN' if not good_v else '(LEAK!)'}")
    for x in good_v:
        print(f"           - {x}")

    # (B) reset-in-place, PARTIAL scrub (the honest optimization): wipes the obvious fs channels but
    # misses tmpfs secret + poisoned pod build-cache + credential env (ADR-006's losing game).
    partial = {"scratch-fs", "git-worktree"}
    _, partial_v = run_policy("reset-in-place/partial", teardown=False, scrub_coverage=partial,
                              per_principal_subpath=True, probes=probes)
    print(f"[oracle] reset/partial : in-place scrub misses {sorted(FULL - partial)} -> "
          f"{len(partial_v)} residue observation(s) {'DETECTED' if partial_v else 'NONE (TEETH LOST!)'}")
    for x in partial_v:
        print(f"           - {x}")

    # (C) reset-in-place, claims PERFECT pod scrub but still shares ONE per-Project PVC subpath ->
    # the cross-principal PVC vector leaks even with a spotless pod (§9.4 is independently required).
    _, shared_v = run_policy("reset-in-place/shared-pvc", teardown=False, scrub_coverage=FULL,
                             per_principal_subpath=False, probes=probes)
    print(f"[oracle] shared-pvc    : perfect pod scrub + shared per-Project subpath -> "
          f"{len(shared_v)} residue observation(s) {'DETECTED' if shared_v else 'NONE (TEETH LOST!)'}")
    for x in shared_v:
        print(f"           - {x}")

    pos = check_same_principal_persists(probes)

    # Gate semantics: the COMPLIANT policy passes; BOTH deviating candidates are blocked, and the
    # partial-scrub leak spans exactly the channels the scrub missed.
    partial_channels = {x.split("[")[1].split("]")[0] for x in partial_v}
    base_ok = (
        len(good_v) == 0                                   # teardown-and-replace clears every channel
        and len(partial_v) > 0                             # reset-in-place/partial is BLOCKED
        and partial_channels == (FULL - partial)           # ...on exactly the un-scrubbed channels
        and any("[pvc-cross-principal]" in x for x in shared_v)   # shared PVC leaks cross-principal
        and pos                                            # no over-fire on same-principal cache
    )

    if not mutate:
        if base_ok:
            print("[oracle] PASS — teardown-and-replace is CLEAN; every reset-in-place deviation "
                  "(partial scrub, shared PVC) is DETECTED. The gate blocks the optimization by "
                  "construction (ADR-006), positive control holds.")
            return 0
        print("[oracle] FAIL — oracle verdict wrong (see above).")
        return 1

    # ---- MUTATION CONTRACT: drop each probe; a real leak on that channel must go undetected -----
    print("\n[mutate] per-channel teeth — drop one probe, a reset-in-place leak on it must slip:")
    all_ok = base_ok
    for dropped in CHANNELS:
        surviving = set(CHANNELS) - {dropped}
        # a scrub/PVC policy that leaks ONLY on `dropped`: pod scrub covers everything except
        # `dropped` (for pod channels); PVC handled via the shared-subpath toggle.
        if dropped == "pvc-cross-principal":
            _, v = run_policy("m", teardown=False, scrub_coverage=FULL,
                              per_principal_subpath=False, probes=surviving)
            # ground truth WITH the probe present:
            _, truth = run_policy("m", teardown=False, scrub_coverage=FULL,
                                  per_principal_subpath=False, probes=set(CHANNELS))
        else:
            cover = FULL - {dropped}
            _, v = run_policy("m", teardown=False, scrub_coverage=cover,
                              per_principal_subpath=True, probes=surviving)
            _, truth = run_policy("m", teardown=False, scrub_coverage=cover,
                                  per_principal_subpath=True, probes=set(CHANNELS))
        blinded = (len(truth) > 0 and len(v) == 0)   # real leak exists, dropped-probe oracle misses
        print(f"           - drop [{dropped:20s}] probe: real leak={len(truth)} seen={len(v)} -> "
              f"{'BLIND (probe was load-bearing ✓)' if blinded else 'still caught (DECORATIVE?!)'}")
        all_ok = all_ok and blinded

    if all_ok:
        print("[mutate] PASS — all 6 channel probes load-bearing; none decorative; base gate holds.")
        return 0
    print("[mutate] FAIL — a probe is decorative or the base gate broke (see above).")
    return 1


def judge_observed(path, observer_run, observer_principal):
    """Runtime-judge mode. `residue-reuse-kind.sh` runs the plant/probe on a real kind cluster and
    writes Run 2's observations as JSON lines: {"channel","token","author_run","author_principal"}.
    This feeds those real observations through the SAME `violations()` oracle proven above, so a
    green CI run is the identical verdict function the mutation contract gives teeth to — not a
    second, weaker check. Exit 0 = clean; exit 1 = residue leak (CI red)."""
    import json
    observed = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            observed.append((o["channel"], o["token"], o["author_run"], o["author_principal"]))
    trace = {"observed": observed, "observer_run": observer_run,
             "observer_principal": observer_principal}
    v = violations(trace)
    print(f"[judge] observer={observer_run}({observer_principal}) observations={len(observed)} "
          f"-> {len(v)} residue leak(s)")
    for x in v:
        print(f"          - {x}")
    if v:
        print("[judge] FAIL — cross-principal residue observed on a real cluster (NFR-SEC5). CI RED.")
        return 1
    print("[judge] PASS — no residue bled across Runs/principals (§9.3/§9.4, NFR-SEC5).")
    return 0


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


if __name__ == "__main__":
    if "--observed" in sys.argv:
        sys.exit(judge_observed(_arg("--observed"),
                                _arg("--observer-run", "run2"),
                                _arg("--observer-principal", "p2")))
    sys.exit(main(mutate=("--mutate" in sys.argv)))
