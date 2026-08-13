#!/usr/bin/env python3
"""
Story 3.4 (ISI-2204) falsification — WarmPool controller, claim-time sandbox binding.

Differential falsification, same shape as run-reconcile-check.py (3.1) / run-retry-backoff-check.py
(3.2) / claim-nodouble-check.py (2.2). It proves the CLAIM-TIME BIND has teeth by contrasting NAIVE
controllers (pick-a-Ready-pod with no atomicity; always-cold-boot; return-used-pod-to-pool;
grab-fresh-every-lap; ignore-the-key) against the arch §9.2/§9.3/§5.3.4/§6.4 controller that:
  * binds a POOLED pod at ClaimingSandbox (a grab, not a cold boot) on the warm path (FR-C1, S9),
  * grabs it ATOMICALLY (K8s resourceVersion CAS — never hands one warm pod to two Runs),
  * is IDEMPOTENT per run_id (§6.4 re-entrancy — a retry lap reattaches, it does not leak a 2nd pod),
  * NEVER reuses a pod across Runs/principals (§9.3 teardown-and-replace — used pod is destroyed,
    a FRESH pod replenishes),
  * matches the (RuntimeClass × image) key (wrong runtime = wrong isolation boundary),
  * on an empty pool TRIGGERS SCALE-UP and still serves the Run (cold hit) — never wedges it.

Scope reminder (3.4 vs 3.5 / ISI-2205): THIS story owns the controller MECHANISM — the bind
(atomic, idempotent, key-matched), the scale-up trigger on a miss, and teardown-and-replace toward a
target. The DERIVATION of that target N (base-stock N=ceil(λR+z√(λR)) + autoscale on claim pressure)
is Story 3.5 / `pool_sizing.py`. This check uses a STATIC target and asserts maintain-toward-target +
scale-up-on-empty; it does NOT re-implement the sizing math (that is 3.5's check / pool_sizing.py).

Mutation contract (the three headline invariants must be falsifiable — re-run after any edit):
  * delete the resourceVersion CAS guard in Cluster.cas_bind (bind unconditionally) -> (M1) RED.
  * delete the run_id reattach lookup in bind_claim_time (always grab fresh)        -> (M2) RED.
  * make release() return the pod to Ready instead of tearing it down (reuse)        -> (M3) RED.

stdlib only. `python3 warmpool-claim-check.py`. Exits non-zero on any falsification.
No wall-clock, no RNG: latency is a fixed logical cost; pod identity is a monotonic counter.
"""
import sys

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)

# Logical latencies (seconds) — only their ORDER matters: a warm grab must be << a cold boot.
WARM_GRAB = 0.05      # bind an already-Ready pod: control-plane grab + context inject (§5.3.4/§8.5)
COLD_BOOT = 8.0       # create a pod and wait for Ready: the miss penalty the pool exists to avoid

# Pool keys = (RuntimeClass × AgentRuntime image), the one-dimensional §9.2 key.
KEY_A = ("gvisor", "runtime:v1")
KEY_B = ("kata",   "runtime:v1")   # different runtime class -> different isolation boundary
KEY_C = ("gvisor", "runtime:v2")   # same class, different image


# ---------------------------------------------------------------------------
# The cluster: warm-pool pods. A pod is a physical sandbox instance with an
# identity that PERSISTS across its whole life — the §9.3 "never reused across
# Runs/principals" invariant is a property of this identity, so the check tracks
# every principal that ever ran on each physical pod.
# ---------------------------------------------------------------------------
class Pod:
    def __init__(self, uid, key):
        self.uid = uid
        self.key = key
        self.state = "Ready"       # Ready | Bound | Torn
        self.bound_run = None
        self.rv = 0                # resourceVersion — the K8s-native optimistic-concurrency guard
        self.principals = []       # every principal that has EVER run on this physical pod


class Cluster:
    def __init__(self):
        self.pods = {}
        self._next = 0
        self.create_calls = 0      # pod CREATIONS (cold boot / scale-up) — the expensive path
        self.grab_calls = 0        # warm GRABS against an already-Ready pod

    def _mk(self, key):
        uid = "pod-%d" % self._next
        self._next += 1
        self.pods[uid] = Pod(uid, key)
        return uid

    def add_ready(self, key, n=1):
        return [self._mk(key) for _ in range(n)]

    def create_pod(self, key):     # models a real pod create+Ready (scale-up / cold-start)
        self.create_calls += 1
        return self._mk(key)

    def ready(self, key):
        return [p for p in self.pods.values() if p.state == "Ready" and p.key == key]

    def bound_of(self, run_id):
        for p in self.pods.values():
            if p.state == "Bound" and p.bound_run == run_id:
                return p
        return None

    # ---- the atomic bind: resourceVersion CAS (K8s optimistic concurrency, ponytail rung-4:
    #      "native concurrency, not invented locking" — same discipline as the §6.2 conditional
    #      UPDATE, but on the pod object). The caller read the pod Ready from a snapshot; the rv IS
    #      the proxy for "unchanged since that snapshot" — so the rv compare is the SOLE gate (every
    #      state transition bumps rv, §below). A stale rv -> 409 Conflict -> caller retries elsewhere.
    #      NOTE: there is deliberately NO independent live `state == Ready` re-check here — that would
    #      mask a missing rv guard (it would serialize a second binder even with the CAS deleted),
    #      giving M1 false teeth. The rv compare must stand alone. ----
    def cas_bind(self, uid, run_id, expected_rv):
        p = self.pods[uid]
        if p.rv != expected_rv:    # M1 GUARD (sole gate): pod mutated since we read it -> lose
            return False
        p.state = "Bound"
        p.bound_run = run_id
        p.rv += 1
        return True


def trigger_scaleup(cluster, key, target):
    """Replenish/scale toward the target ready-buffer (maintain-to-target). The DERIVATION of
    `target` is Story 3.5 (base-stock + pressure autoscale); here it is a static policy input."""
    while len(cluster.ready(key)) < target:
        cluster.create_pod(key)


# ---------------------------------------------------------------------------
# THE CONTROLLER (arch §9.2/§9.3/§5.3.4/§6.4). Returns (pod_uid, pool_hit, latency).
# ---------------------------------------------------------------------------
def bind_claim_time(cluster, run, target):
    """
    run = {"run_id","principal","key","class"}  class in {"interactive","batch"}.
    Warm path: grab a pooled Ready pod matching the key (claim-time). Miss: scale up + serve.
    """
    # --- M2 GUARD: §6.4 idempotent re-entrancy. A retry lap for the SAME run_id reattaches to the
    #     pod it already bound — it must NOT grab a second warm pod (that would leak the first). ---
    existing = cluster.bound_of(run["run_id"])
    if existing is not None:
        return (existing.uid, "warm", 0.0)      # reattach: no new grab, zero inventory change

    key = run["key"]

    # --- warm path: bind a pooled pod matching the (RuntimeClass × image) key, ATOMICALLY ---
    for p in list(cluster.ready(key)):          # key filter: only same-key pods are eligible
        if cluster.cas_bind(p.uid, run["run_id"], p.rv):
            cluster.grab_calls += 1
            p.principals.append(run["principal"])
            trigger_scaleup(cluster, key, target)   # async replenish toward target after a grab
            return (p.uid, "warm", WARM_GRAB)
        # lost the CAS race on this pod -> try the next Ready pod of the same key

    # --- miss path: pool empty for this key -> TRIGGER SCALE-UP, then serve (never wedge) ---
    before = cluster.create_calls
    if run["class"] == "batch":
        # batch/non-interactive: target=0 pool, cold-start directly (zero idle cost, §9.2 hybrid)
        uid = cluster.create_pod(key)
    else:
        # interactive: scale up to serve this claim (>=1) and refill toward target
        trigger_scaleup(cluster, key, max(target, 1))
        uid = cluster.ready(key)[0].uid
    assert cluster.create_calls > before, "miss path must trigger a scale-up (pod create)"
    ok = cluster.cas_bind(uid, run["run_id"], cluster.pods[uid].rv)
    assert ok
    cluster.grab_calls += 1
    cluster.pods[uid].principals.append(run["principal"])
    return (uid, "cold", COLD_BOOT)


def release(cluster, uid, key, target):
    """Run completed/died: §9.3 teardown-and-replace. The used pod is DESTROYED (never returned to
    Ready) and a FRESH pod replenishes — 'warm' is a property of the POOL, not of a reused pod."""
    p = cluster.pods[uid]
    p.state = "Torn"                 # M3 GUARD: destroy, never set back to Ready
    p.bound_run = None
    p.rv += 1                        # a teardown is a mutation -> bump rv (keeps rv monotonic)
    trigger_scaleup(cluster, key, target)


# ===========================================================================
# SCENARIOS
# ===========================================================================

# (M1) atomic bind — two Runs race for the ONE warm pod. Correct: exactly one wins.
def scenario_concurrent_bind_correct():
    c = Cluster(); c.add_ready(KEY_A, 1)
    p = c.ready(KEY_A)[0]
    rv_seen = p.rv                                  # both concurrent binders snapshot the same rv
    okA = c.cas_bind(p.uid, "runA", rv_seen)        # winner: rv 0 -> 1
    okB = c.cas_bind(p.uid, "runB", rv_seen)        # stale rv -> 409, loses
    return okA, okB, (c.pods[p.uid].bound_run)

# (M1 twin) NAIVE pick-a-Ready-pod with no atomicity hands the SAME physical pod to both Runs.
def scenario_concurrent_bind_naive():
    c = Cluster(); c.add_ready(KEY_A, 1)
    snap = c.ready(KEY_A)                            # both binders read the same Ready snapshot
    uidA = snap[0].uid                              # runA picks pod0
    uidB = snap[0].uid                              # runB picks pod0 (no atomic removal) -> shared
    return uidA == uidB                            # True => double-bind (one sandbox, two Runs)

# (M2) idempotent rebind — a retry lap reattaches; pool inventory is unchanged.
def scenario_idempotent_rebind():
    c = Cluster(); c.add_ready(KEY_A, 2)
    run = {"run_id": "R1", "principal": "alice", "key": KEY_A, "class": "interactive"}
    uid1, hit1, _ = bind_claim_time(c, run, target=2)
    ready_after_first = len(c.ready(KEY_A))
    uid2, hit2, _ = bind_claim_time(c, run, target=2)   # SAME run_id re-enters ClaimingSandbox
    ready_after_second = len(c.ready(KEY_A))
    bound_count = sum(1 for p in c.pods.values() if p.state == "Bound" and p.bound_run == "R1")
    return uid1, uid2, ready_after_first, ready_after_second, bound_count

# (M2 twin) NAIVE grab-fresh-every-lap leaks a second pod on the retry lap.
def scenario_rebind_naive():
    c = Cluster(); c.add_ready(KEY_A, 2)
    # naive: no run_id reattach — every ClaimingSandbox entry grabs a fresh Ready pod
    p1 = c.ready(KEY_A)[0]; c.cas_bind(p1.uid, "R1", p1.rv)
    p2 = c.ready(KEY_A)[0]; c.cas_bind(p2.uid, "R1", p2.rv)   # SAME run, SECOND pod
    bound_count = sum(1 for p in c.pods.values() if p.state == "Bound" and p.bound_run == "R1")
    return bound_count                              # 2 => leaked a warm pod for one Run

# (M3) never-reuse — two sequential Runs by different principals share NO physical pod.
def scenario_no_reuse_correct():
    c = Cluster(); c.add_ready(KEY_A, 1)
    r1 = {"run_id": "R1", "principal": "alice", "key": KEY_A, "class": "interactive"}
    uid1, _, _ = bind_claim_time(c, r1, target=1)
    release(c, uid1, KEY_A, target=1)               # teardown pod0, replenish a fresh pod
    r2 = {"run_id": "R2", "principal": "bob", "key": KEY_A, "class": "interactive"}
    uid2, _, _ = bind_claim_time(c, r2, target=1)
    reused = any(len(set(p.principals)) > 1 for p in c.pods.values())
    return uid1, uid2, reused

# (M3 twin) NAIVE return-to-pool reuses one physical pod across two principals (contamination).
def scenario_reuse_naive():
    c = Cluster(); c.add_ready(KEY_A, 1)
    p = c.ready(KEY_A)[0]
    c.cas_bind(p.uid, "R1", p.rv); p.principals.append("alice")
    # naive release: return the used pod to Ready instead of tearing it down
    p.state = "Ready"; p.bound_run = None
    p2 = c.ready(KEY_A)[0]                           # bob's Run grabs the SAME physical pod
    c.cas_bind(p2.uid, "R2", p2.rv); p2.principals.append("bob")
    return any(len(set(pp.principals)) > 1 for pp in c.pods.values())  # True => cross-principal reuse

# (T2) warm path is claim-time, not a cold boot. Start ABOVE target so the post-grab pool still
# meets target and no async replenish fires — isolating the CLAIM-PATH boot count (must be 0).
def scenario_warm_is_claim_time():
    c = Cluster(); c.add_ready(KEY_A, 3)
    creates_before = c.create_calls
    run = {"run_id": "R1", "principal": "alice", "key": KEY_A, "class": "interactive"}
    uid, hit, lat = bind_claim_time(c, run, target=2)     # 3 Ready, grab -> 2 Ready == target
    return hit, lat, (c.create_calls - creates_before)   # a warm hit must NOT boot on the claim path

# (T5) empty pool -> scale-up + serve, never wedged.
def scenario_empty_pool_scaleup():
    c = Cluster()                                   # no Ready pods at all
    creates_before = c.create_calls
    run = {"run_id": "R1", "principal": "alice", "key": KEY_A, "class": "interactive"}
    uid, hit, lat = bind_claim_time(c, run, target=2)
    return uid, hit, (c.create_calls - creates_before)

# (T6) key-match — a Run needing (gvisor,v1) must never bind a (kata,v1) or (gvisor,v2) pod.
def scenario_key_match():
    c = Cluster()
    c.add_ready(KEY_B, 2)                            # only WRONG-runtime pods are warm
    c.add_ready(KEY_C, 2)                            # and wrong-image pods
    run = {"run_id": "R1", "principal": "alice", "key": KEY_A, "class": "batch"}
    uid, hit, lat = bind_claim_time(c, run, target=0)
    bound = c.pods[uid]
    # the bound pod must carry KEY_A; the mismatched warm pods must be untouched (still Ready)
    mismatched_touched = any(p.state != "Ready" for p in c.pods.values() if p.key in (KEY_B, KEY_C))
    return bound.key, hit, mismatched_touched

# (T7) warm/cold accounting — pool_hit reflects reality (feeds obs §5.3 / 13.7 exhaustion alert).
def scenario_pool_hit_accounting():
    c = Cluster(); c.add_ready(KEY_A, 1)            # exactly one warm pod
    r1 = {"run_id": "R1", "principal": "alice", "key": KEY_A, "class": "interactive"}
    r2 = {"run_id": "R2", "principal": "bob",   "key": KEY_A, "class": "interactive"}
    _, hit1, _ = bind_claim_time(c, r1, target=1)  # grabs the warm pod -> warm
    # after the grab, replenish is triggered toward target=1, so r2 also finds a Ready pod -> warm.
    # To force a genuine miss we drain: bind with target=0 so nothing replenishes.
    c2 = Cluster(); c2.add_ready(KEY_A, 1)
    a, hitA, _ = bind_claim_time(c2, dict(r1), target=0)   # warm (the one pod)
    b, hitB, _ = bind_claim_time(c2, dict(r2), target=0)   # pool now empty -> cold
    return hit1, hitA, hitB


def main():
    target_static = 2   # a STATIC policy input; deriving it is Story 3.5 (pool_sizing.py), not here.

    # (M1) atomic bind: exactly one Run wins the single warm pod; the other loses the CAS.
    okA, okB, owner = scenario_concurrent_bind_correct()
    check(okA and not okB and owner == "runA",
          "M1 atomic-bind FAILED: the resourceVersion CAS did not serialize two racing binds "
          "(delete the `if p.rv != expected_rv` guard in cas_bind to see this go RED)")
    check(scenario_concurrent_bind_naive() is True,
          "HARNESS LOST TEETH: naive pick-a-Ready-pod no longer double-binds a shared sandbox")

    # (M2) idempotent §6.4 rebind: a retry lap reattaches, inventory unchanged, one Bound pod.
    uid1, uid2, r_after1, r_after2, bound_cnt = scenario_idempotent_rebind()
    check(uid1 == uid2 and r_after1 == r_after2 and bound_cnt == 1,
          "M2 idempotent-rebind FAILED: a retry lap grabbed a SECOND warm pod / leaked inventory "
          "(delete the run_id reattach lookup in bind_claim_time to see this go RED)")
    check(scenario_rebind_naive() == 2,
          "HARNESS LOST TEETH: naive grab-fresh-every-lap no longer leaks a second pod")

    # (M3) never-reuse §9.3: distinct pods across principals, no physical pod ran two principals.
    u1, u2, reused = scenario_no_reuse_correct()
    check(u1 != u2 and reused is False,
          "M3 teardown-and-replace FAILED: a used pod was reused across Runs/principals "
          "(make release() set state='Ready' instead of 'Torn' to see this go RED)")
    check(scenario_reuse_naive() is True,
          "HARNESS LOST TEETH: naive return-to-pool no longer reuses a pod across principals")

    # (T2) warm path is claim-time (grab), not a cold boot: no pod created, latency is the grab.
    hit, lat, creates = scenario_warm_is_claim_time()
    check(hit == "warm" and lat <= WARM_GRAB and creates == 0,
          "T2 claim-time FAILED: a warm hit cold-booted a pod (start latency is not claim-time, "
          "violates FR-C1/S9)")

    # (T5) empty pool: scale-up triggered AND the Run is served (cold), never wedged.
    euid, ehit, ecreates = scenario_empty_pool_scaleup()
    check(euid is not None and ehit == "cold" and ecreates >= 1,
          "T5 empty-pool FAILED: an empty pool did not trigger scale-up / left the Run wedged")

    # (T6) key discipline: bound pod matches the requested key; mismatched warm pods untouched.
    bkey, khit, touched = scenario_key_match()
    check(bkey == KEY_A and khit == "cold" and touched is False,
          "T6 key-match FAILED: a Run bound a pod of the WRONG (RuntimeClass × image) key "
          "(wrong isolation boundary) or disturbed a mismatched warm pod")

    # (T7) warm/cold accounting is truthful.
    hit1, hitA, hitB = scenario_pool_hit_accounting()
    check(hit1 == "warm" and hitA == "warm" and hitB == "cold",
          "T7 pool_hit accounting FAILED: warm/cold classification does not match reality "
          "(would misreport the §9.2 warm-hit SLI / 13.7 exhaustion alert)")

    if FAIL:
        print("FALSIFIED — Story 3.4 WarmPool design check FAILED:")
        for m in FAIL:
            print("  ✗", m)
        sys.exit(1)
    print("OK — Story 3.4 WarmPool claim-time-binding design holds:")
    print("  (M1) resourceVersion CAS serializes racing binds; naive pick-a-pod double-binds (AC-atomic)")
    print("  (M2) §6.4 run_id rebind reattaches (no leak); naive grab-fresh leaks a 2nd pod (AC-idempotent)")
    print("  (M3) §9.3 teardown-and-replace never reuses a pod; naive return-to-pool contaminates (AC-hygiene)")
    print("  (T2) warm hit is a claim-time grab, not a cold boot (FR-C1/S9)")
    print("  (T5) empty pool triggers scale-up and still serves the Run — never wedged")
    print("  (T6) bind matches the (RuntimeClass × image) key — never a wrong isolation boundary")
    print("  (T7) warm/cold pool_hit accounting is truthful (obs §9.2 SLI / 13.7 exhaustion alert)")


if __name__ == "__main__":
    main()
