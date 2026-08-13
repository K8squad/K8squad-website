#!/usr/bin/env python3
"""
Story 4.2 falsification — RuntimeClass-selected sandbox isolation (arch §9.1/§9.3, AD-3).

Differential check over the *pod-spec + admission decision* a Run reconciler would produce.
It proves the harness has TEETH by first showing a NAIVE selector breaks the §9.1 isolation
invariants, then showing the §9.1 selection contract holds them. stdlib-only; `python3 <file>`.

Invariants (AC1-AC6):
  AC1  every pod carries a non-empty runtimeClassName, resolved by precedence, gVisor-default.
  AC2  runc (or empty/node-default) rejected for untrusted code unless explicit trustedDev.
  AC3  every Run is a distinct pod; no pod shared/reused across Runs or principals.
  AC4  a resolved class absent from the cluster fails CLOSED — never a runc downgrade.
  AC5  the warm-pool bind matches the resolved class (no cross-class reuse).
  AC6  docker:true on gVisor gated by a backing mechanism (rootless builder / rootless dockerd / Kata).

AC7 (runtime hostile-Run containment) is proven by Epic X.1 on a real cluster, not here — this
guards the static selection shape, which is the construction-time crux.
"""
import sys

# --- cluster facts (S1 prerequisite): which RuntimeClasses are installed ---
INSTALLED = {"gvisor", "kata"}          # runc == node default (always present, but rejected for untrusted)
UNTRUSTED_CLASSES = {"gvisor", "kata"}  # acceptable for untrusted agent code
DOCKER_MECHS = {"rootless-builder", "rootless-dockerd", "kata"}  # §5.3.3 backings for docker:true


def resolve_runtime_class(run, role, pool):
    """§9.1 precedence: sandboxPolicy > runtimeClassHint > pool > gvisor-default."""
    return (run.get("sandboxPolicy", {}).get("runtimeClass")
            or role.get("runtimeClassHint")
            or pool.get("runtimeClass")
            or "gvisor")


# ---------------------------------------------------------------------------
# The two selectors under test. Each returns the list of pod-specs / admission
# decisions it would produce for a batch of Runs. A "reject" is a dict with
# {"rejected": <reason>}; an admitted pod carries runtimeClassName + identity.
# ---------------------------------------------------------------------------
def naive_selector(runs, role, pool):
    """Over-permissive: empty class => node default (runc), downgrades on missing class,
    reuses one warm pod across Runs, admits docker:true ungated."""
    shared_pod = "warm-pod-0"  # BUG: one pod reused across every Run
    out = []
    for r in runs:
        rc = resolve_runtime_class(r, role, pool)
        if rc not in INSTALLED and rc != "runc":
            rc = "runc"        # BUG: silent downgrade to node default when class missing
        out.append({
            "run": r["id"],
            "runtimeClassName": "" if rc == "runc" else rc,  # BUG: runc => empty (node default)
            "pod": shared_pod,                                # BUG: shared/reused pod
            "bound_class": pool.get("runtimeClass", "gvisor"),  # BUG: binds pool class, ignores resolved
            "docker": r.get("docker", False),
            "docker_mech": None,                              # BUG: never checks a backing mechanism
        })
    return out


def compliant_selector(runs, role, pool):
    """§9.1 contract: precedence+gvisor-default, runc rejected w/o trustedDev, fail-closed on
    missing class, per-Run distinct pod, RuntimeClass-keyed bind, docker mechanism gate."""
    out = []
    for i, r in enumerate(runs):
        rc = resolve_runtime_class(r, role, pool)
        # AC2: runc / empty rejected for untrusted code unless explicit trustedDev
        if rc == "runc" or rc == "":
            if not r.get("trustedDev"):
                out.append({"run": r["id"], "rejected": "runc-for-untrusted-code"})
                continue
        elif rc in UNTRUSTED_CLASSES:
            pass
        # AC4: selected class must exist on cluster — fail CLOSED, no runc downgrade
        if rc not in INSTALLED and not (rc == "runc" and r.get("trustedDev")):
            out.append({"run": r["id"], "rejected": f"RuntimeClassUnavailable:{rc}"})
            continue
        # AC6: docker:true on gVisor needs a backing mechanism
        if r.get("docker") and rc == "gvisor" and r.get("docker_mech") not in DOCKER_MECHS:
            out.append({"run": r["id"], "rejected": "docker-on-gvisor-no-mechanism"})
            continue
        out.append({
            "run": r["id"],
            "runtimeClassName": rc,          # AC1: non-empty, resolved
            "pod": f"pod-{r['id']}-{i}",     # AC3: distinct per-Run pod
            "bound_class": rc,               # AC5: bind matches resolved class
            "docker": r.get("docker", False),
            "docker_mech": r.get("docker_mech"),
        })
    return out


# ---------------------------------------------------------------------------
# Invariant assertions over an admitted/rejected batch. Returns list of violations.
# `runs` carries the intent so we can tell "should have been rejected" from "was".
# ---------------------------------------------------------------------------
def violations(decisions, runs):
    v = []
    by_id = {r["id"]: r for r in runs}
    pods_seen = {}
    for d in decisions:
        r = by_id[d["run"]]
        untrusted = not r.get("trustedDev")
        if d.get("rejected"):
            continue  # a rejection is never itself a violation; missing rejections are (below)
        rc = d.get("runtimeClassName", "")
        # AC1: non-empty runtimeClassName for every admitted pod
        if rc == "":
            v.append(f"{d['run']}: empty runtimeClassName (node-default/runc) [AC1]")
        # AC2: untrusted code must not run on runc/empty
        if untrusted and rc in ("", "runc"):
            v.append(f"{d['run']}: untrusted Run admitted on runc/node-default [AC2]")
        # AC4: an admitted class must actually be installed (no downgrade-admit)
        if rc and rc != "runc" and rc not in INSTALLED:
            v.append(f"{d['run']}: admitted on uninstalled class {rc} [AC4]")
        if untrusted and rc == "" and r.get("sandboxPolicy", {}).get("runtimeClass") not in INSTALLED \
           and r.get("sandboxPolicy", {}).get("runtimeClass"):
            pass  # covered by AC1/AC2 above
        # AC5: bound pool class must match the resolved class
        if d.get("bound_class") and rc and d["bound_class"] != rc:
            v.append(f"{d['run']}: cross-class bind resolved={rc} bound={d['bound_class']} [AC5]")
        # AC3: no pod reused across Runs
        if d.get("pod") in pods_seen:
            v.append(f"{d['run']}: pod {d['pod']} reused (also {pods_seen[d['pod']]}) [AC3]")
        pods_seen[d.get("pod")] = d["run"]
        # AC6: docker:true on gvisor must carry a backing mechanism
        if d.get("docker") and rc == "gvisor" and d.get("docker_mech") not in DOCKER_MECHS:
            v.append(f"{d['run']}: docker:true on gvisor with no mechanism [AC6]")
    # AC2/AC4: a Run that SHOULD be rejected but was admitted is a violation
    admitted = {d["run"] for d in decisions if not d.get("rejected")}
    for r in runs:
        rc = resolve_runtime_class(r, ROLE, POOL)
        should_reject = ((rc in ("runc", "") and not r.get("trustedDev"))
                         or (rc not in INSTALLED and rc != "runc"))
        if should_reject and r["id"] in admitted:
            v.append(f"{r['id']}: should have been rejected (resolved={rc}) but was admitted [AC2/AC4]")
    return v


# --- test batch: exercises precedence, runc-reject, missing-class, cross-class, docker gate ---
ROLE = {"runtimeClassHint": None}
POOL = {"runtimeClass": "gvisor"}
RUNS = [
    {"id": "r-default"},                                              # -> gvisor (default)
    {"id": "r-policy", "sandboxPolicy": {"runtimeClass": "kata"}},    # -> kata (precedence)
    {"id": "r-runc", "sandboxPolicy": {"runtimeClass": "runc"}},      # -> reject (untrusted)
    {"id": "r-trusted", "sandboxPolicy": {"runtimeClass": "runc"}, "trustedDev": True},  # -> allowed
    {"id": "r-missing", "sandboxPolicy": {"runtimeClass": "firecracker"}},  # -> fail-closed (absent)
    {"id": "r-docker-ok", "docker": True, "docker_mech": "rootless-builder"},  # -> gvisor + builder
    {"id": "r-docker-bad", "docker": True},                          # -> reject (no mechanism)
]


def check_precedence():
    cases = [
        ({"sandboxPolicy": {"runtimeClass": "kata"}}, {"runtimeClassHint": "gvisor"}, {"runtimeClass": "runc"}, "kata"),
        ({}, {"runtimeClassHint": "kata"}, {"runtimeClass": "gvisor"}, "kata"),
        ({}, {}, {"runtimeClass": "kata"}, "kata"),
        ({}, {}, {}, "gvisor"),
    ]
    for run, role, pool, want in cases:
        got = resolve_runtime_class(run, role, pool)
        assert got == want, f"precedence: run={run} role={role} pool={pool} => {got}, want {want}"
    print("[model] precedence : sandboxPolicy>runtimeClassHint>pool>gvisor-default resolves correctly across 4 cases")


def main():
    check_precedence()

    naive = naive_selector(RUNS, ROLE, POOL)
    naive_v = violations(naive, RUNS)
    print(f"[model] naive selector : {len(naive_v)} isolation violation(s) -> "
          f"{'DETECTED' if naive_v else 'NONE (TEETH LOST!)'}")
    for x in naive_v:
        print(f"          - {x}")

    good = compliant_selector(RUNS, ROLE, POOL)
    good_v = violations(good, RUNS)
    rejected = [d["run"] for d in good if d.get("rejected")]
    distinct_pods = len({d["pod"] for d in good if not d.get("rejected")})
    admitted = len(good) - len(rejected)
    print(f"[model] §9.1 selector : {len(good_v)} violations; "
          f"rejected={rejected}; {admitted} admitted -> {distinct_pods} distinct pods")
    for x in good_v:
        print(f"          - {x}")

    # teeth: naive must break, compliant must hold, runc must be rejected, missing-class fail-closed
    ok = (len(naive_v) > 0
          and len(good_v) == 0
          and "r-runc" in rejected
          and "r-missing" in rejected
          and "r-docker-bad" in rejected
          and "r-trusted" not in rejected           # explicit trustedDev escape works
          and distinct_pods == admitted)            # every admitted Run got its own pod
    if ok:
        print("[model] PASS — naive detectably breaks isolation; §9.1 selection contract holds AC1-AC6.")
        return 0
    print("[model] FAIL — invariant broken (see above).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
