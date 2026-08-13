#!/usr/bin/env python3
"""Story 8.7f falsification — the on-demand RO-reader pod for full-tree completed-Run reads.

This is the FLAGGED FAST-FOLLOW of Epic 8.7 (design §4.2 "on-demand RO reader", §5 layer 2/4,
§7 alert; obs-plan §2.3 / OBS-BB4). 8.7a-e ship the whole Epic-8.7 acceptance on SNAPSHOT-ONLY: a
completed Run's build view (changed-file tree + per-file diffs + changed-file code) is served from the
8.7c build-snapshot artifact, with NO live pod. The snapshot has exactly one ceiling — it cannot show
an *unchanged* file's content for a completed Run (it captures `base...runRef`, the changed set). 8.7f
lifts that ceiling, and ONLY that ceiling: for a **full-tree-beyond-changes** read on a **completed**
Run, and ONLY when a feature flag is enabled, the BFF launches a **short-lived, read-only
workspace-reader pod** that mounts the Project PVC `RO` at the Run's commit, reader-scoped with the
Run's OWN (revoked-at-teardown) credential, torn down after idle, reused before relaunch, and whose
launch rate is an alert-worthy cost signal. Flag OFF -> the feature degrades cleanly to snapshot-only.

The load-bearing claims of THIS story (everything the snapshot path already owns is out of scope):
  1. It is FLAGGED. Flag off -> snapshot-only, and a pod is NEVER launched (a v1 ships without it).
  2. It is ON-DEMAND and the snapshot stays the DEFAULT path. A read the snapshot already covers (the
     changed set) is served from the snapshot and launches NOTHING; only a beyond-changes full-tree
     read pays for a pod.
  3. The mount is READ-ONLY, at the RUN'S COMMIT — never RW, never at HEAD/another ref.
  4. The reader runs with the RUN'S OWN per-principal credential scope, REVOKED at teardown — never a
     broader/platform scope, and the credential does not outlive the pod.
  5. It is SHORT-LIVED — torn down after idle (bounded lifetime, not a standing dev box).
  6. It REUSES a live reader for the same Run before launching a second one (bounds cost/concurrency).
  7. It inherits the 8.7d PER-PRINCIPAL GATE: a non-owner (even a same-Team peer) is denied 404
     BEFORE any launch (a deny must never spin a pod / mount a peer's worktree), and the mount exposes
     NO write verb (read-only, always).
  8. OBS-BB4: launch/active/ttl metrics + lifecycle logs, launch is a COST signal (never a
     billing/consumption axis), and the Standing law holds (no file content in any signal, no `model`
     label).

A "we launched a reader and I browsed the full tree" demo passes even if the reader ignores the flag
(no snapshot-only fallback, cost with no off switch), launches eagerly for reads the snapshot already
covers (burns pods for nothing), mounts the PVC RW or at HEAD (a write path / wrong-revision content),
runs with a broader-than-Run scope or a credential that outlives teardown (privilege bleed), never
tears down (a standing box), relaunches instead of reusing (unbounded concurrency), spins a pod for a
non-owner before the gate denies (leaks a peer's worktree + pays for it), or emits no launch metric /
leaks file content into a log (blind cost alert / content firewall breach). So this is a DIFFERENTIAL
check over the RO-reader LIFECYCLE the platform would ship: we first prove the naive "spin up a full
RW dev pod at HEAD with platform creds, ignore the flag, relaunch every time, never tear down, no
metrics" anti-pattern is DETECTED violating every invariant (real teeth), then prove the §4.2/§5/§7 +
OBS-BB4 conformant lifecycle violates nothing — driving REAL reads (changed-set vs beyond-changes,
flag on vs off, owner vs same-Team peer, first-launch vs reuse, launch -> idle-teardown) through an
executable `serve()` + `Cluster` reader manager with a metrics/log spy.

Invariants (R1-R8, one family per AC of story 8.7f; AC9 = this runnable check, folded in):
  R1  FLAGGED, OFF DEGRADES TO SNAPSHOT-ONLY (AC1): flag off -> a beyond-changes read degrades to a
      legible snapshot-only result and NO pod is launched; flag on -> the reader is available.
  R2  ON-DEMAND, SNAPSHOT IS THE DEFAULT (AC2): a changed-set read the snapshot covers is served from
      the snapshot and launches NOTHING; only a beyond-changes full-tree read launches (or reuses).
  R3  MOUNT IS RO, AT THE RUN'S COMMIT (AC3): the reader mounts the Project PVC read-only at the Run's
      commit — never RW, never HEAD/another ref.
  R4  RUN'S-OWN SCOPE, REVOKED AT TEARDOWN (AC4): the reader's credential scope == the Run's own
      per-principal scope (never broader), and the credential is revoked when the pod is torn down.
  R5  SHORT-LIVED, IDLE TEARDOWN (AC5): a reader idle past its TTL is torn down (bounded lifetime).
  R6  REUSE BEFORE RELAUNCH (AC6): a second beyond-changes read for the SAME Run reuses the live
      reader (outcome=reused), it does not launch a second pod.
  R7  PER-PRINCIPAL GATE INHERITED + READ-ONLY (AC7): a non-owner read is denied 404 BEFORE any launch
      (no pod for a deny), and the reader mount exposes NO write verb.
  R8  OBS-BB4 + STANDING LAW (AC8): launch emits `reader.launched.total{reason=full_tree,outcome}` +
      moves the `reader.active` gauge (inc on launch, dec on teardown) + records a `reader.ttl`
      histogram on teardown; lifecycle INFO logs carry ids/sizes only; NO file content in any signal,
      NO `model` label; launch volume is a cost signal, never a consumption/billing axis.

Mutation harness (real teeth): every `--mutate=<NAME>` injects EXACTLY ONE defect into the conformant
lifecycle; the check then goes RED with the mapped invariant among the failures (siblings may also trip
— acceptable for overlapping lifecycle invariants; the MAPPED tooth is the proof, ISI-2271 convention).
Baseline `python3 build-browser-ro-reader-check.py` exits 0; each `--mutate=NAME` exits 1.

    --mutate=FLAG_OFF_LAUNCHES       launch a pod even with the flag off              -> R1
    --mutate=FLAG_OFF_NO_DEGRADE     flag off -> hard error instead of snapshot-only  -> R1
    --mutate=EAGER_LAUNCH            launch for a changed-set read the snapshot covers -> R2
    --mutate=MOUNT_RW                mount the Project PVC read-write                  -> R3
    --mutate=MOUNT_WRONG_REF         mount at HEAD, not the Run's commit               -> R3
    --mutate=BROADER_SCOPE           reader runs with a platform/broader cred scope    -> R4
    --mutate=CRED_NOT_REVOKED        credential survives teardown (not revoked)        -> R4
    --mutate=NO_IDLE_TEARDOWN        a reader idle past TTL is never torn down          -> R5
    --mutate=NO_REUSE                relaunch a second pod instead of reusing           -> R6
    --mutate=LAUNCH_BEFORE_GATE      spin the pod before the per-principal gate denies  -> R7
    --mutate=READER_WRITE_VERB       the reader mount exposes a write verb              -> R7
    --mutate=NO_LAUNCH_METRIC        a launch emits no launched.total counter           -> R8
    --mutate=ACTIVE_NOT_DECREMENTED  teardown never decrements the active gauge         -> R8
    --mutate=LEAK                    put file content + a model label into a signal     -> R8

Backends (owned elsewhere). The git projection (8.7a), the completed-Run snapshot (8.7c), and the BFF
endpoints + per-principal gate (8.7d) are stubbed here — 8.7f owns ONLY the reader-pod lifecycle that
hangs off the completed path for full-tree-beyond-changes reads. It needs only stdlib (no cluster, no
PVC, no auth, no network).
"""

import argparse
import sys

# The 8.7c snapshot captures `base...runRef` — the CHANGED set. These it can always serve (no reader).
CHANGED_SET = {"mod.py", "new.py", "gone.py"}
# Beyond-changes: an UNCHANGED file's content on a completed Run — the one thing the snapshot cannot
# serve. This is the *only* read that legitimately launches an RO reader.
BEYOND_CHANGES = {"src/unchanged/lib.py", "README.md", "vendor/dep.go"}

IDLE_TTL_MS = 120_000          # a reader idle past this is torn down (short-lived, §4.2)
READ_VERBS = ("read", "ls", "git-show")   # the RO reader's allowed verbs — no write verb, ever (§5.4)

# metric-label allowlists (Standing law: ids/sizes are span/log only; NO `model` label anywhere).
LAUNCHED_LABELS = {"reason", "outcome"}
TTL_LABELS = {"outcome"}


# ---- the runs the completed path serves (owner + its Project PVC + the Run's frozen commit) --------
RUN_DB = {
    "run-done":  {"id": "run-done",  "live": False, "owner": "alice",
                  "pvc": "proj-p1-pvc", "commit": "abc123", "team": "t1"},
    "run-done2": {"id": "run-done2", "live": False, "owner": "alice",
                  "pvc": "proj-p1-pvc", "commit": "def456", "team": "t1"},
    # "run-missing" is intentionally absent -> 404.
}


# ---- OBS-BB4 spy: launch/active/ttl metrics + lifecycle logs (the cost signal, obs §2.3) -----------
class Obs:
    def __init__(self, cfg):
        self.cfg = cfg
        self.launched_total = []   # [{reason, outcome, (model?)}] — the launch-rate cost counter
        self.active = 0            # gauge: live reader pods (concurrency/cost ceiling)
        self.active_peak = 0
        self.ttl = []              # [{outcome, ms}] — reader lifetime histogram (idle-teardown health)
        self.logs = []             # lifecycle INFO lines (ids/sizes only)

    def on_launch(self, pod, outcome):
        if not self.cfg["no_launch_metric"]:
            entry = {"reason": "full_tree", "outcome": outcome}
            if self.cfg["leak"]:
                entry["model"] = "claude-opus"          # DEFECT: forbidden `model` label (Standing law)
            self.launched_total.append(entry)
        if outcome == "launched":
            self.active += 1
            self.active_peak = max(self.active_peak, self.active)
        log = {"level": "INFO", "event": "reader.launch", "run.id": pod["run_id"],
               "reader.pod": pod["name"], "reason": "full_tree"}
        if self.cfg["leak"]:
            log["file_content"] = "SECRET=hunter2\nprint('x')"   # DEFECT: content in a signal
        self.logs.append(log)

    def on_teardown(self, pod, outcome, ttl_ms):
        self.ttl.append({"outcome": outcome, "ms": ttl_ms})
        if not self.cfg["active_not_decremented"]:
            self.active -= 1                                # gauge falls back as pods are reclaimed
        self.logs.append({"level": "INFO", "event": "reader.teardown", "run.id": pod["run_id"],
                          "reader.pod": pod["name"], "ttl_ms": ttl_ms, "outcome": outcome})


# ---- the reader-pod manager (THIS story): launch / reuse / idle-teardown ----------------------------
class Cluster:
    def __init__(self, cfg, obs):
        self.cfg = cfg
        self.obs = obs
        self.pods = {}        # run_id -> live reader pod
        self.launched = []    # every pod ever launched (history — reuse must NOT append here)

    def get_or_launch_reader(self, run):
        """Return (pod, outcome). Reuse a live reader for this Run before launching a second (R6)."""
        run_id = run["id"]
        existing = self.pods.get(run_id)
        if existing is not None and not self.cfg["no_reuse"]:
            existing["idle_ms"] = 0                          # reuse resets the idle clock (R5/R6)
            self.obs.on_launch(existing, "reused")
            return existing, "reused"
        pod = {
            "run_id": run_id,
            "name": f"ro-reader-{run_id}",
            "pvc": run["pvc"],
            # R3: read-only mount at the Run's frozen commit — never RW, never HEAD.
            "read_only": not self.cfg["mount_rw"],
            "ref": "HEAD" if self.cfg["mount_wrong_ref"] else run["commit"],
            # R4: the Run's OWN per-principal scope, never broader.
            "cred_scope": "platform" if self.cfg["broader_scope"]
            else f"run:{run_id}:principal:{run['owner']}",
            # R7: read-only, always — no write verb on the mount.
            "verbs": list(READ_VERBS) + (["write"] if self.cfg["reader_write_verb"] else []),
            "cred_revoked": False,
            "idle_ms": 0,
            "alive_ms": 0,
            "torn_down": False,
        }
        self.pods[run_id] = pod
        self.launched.append(pod)
        self.obs.on_launch(pod, "launched")
        return pod, "launched"

    def tick_idle(self, elapsed_ms):
        """Advance time. A reader idle past IDLE_TTL_MS is torn down (R5) + its credential revoked (R4)."""
        for run_id, pod in list(self.pods.items()):
            pod["idle_ms"] += elapsed_ms
            pod["alive_ms"] += elapsed_ms
            if pod["idle_ms"] >= IDLE_TTL_MS and not self.cfg["no_idle_teardown"]:
                self._teardown(run_id, "idle_teardown")

    def _teardown(self, run_id, outcome):
        pod = self.pods.pop(run_id)
        pod["torn_down"] = True
        if not self.cfg["cred_not_revoked"]:
            pod["cred_revoked"] = True                       # R4: revoked-at-teardown
        self.obs.on_teardown(pod, outcome, pod["alive_ms"])


# ---- the completed-path BFF edge that decides snapshot-vs-reader (behind the gate + flag) ----------
def serve(cfg, cluster, obs, run_id, path, caller):
    """Serve one completed-Run read. `path` in CHANGED_SET -> the 8.7c snapshot; a beyond-changes path
    -> the RO reader (only when flagged on, only for the owner). Returns a result dict; `reader` is the
    launched/reused pod or None."""
    run = RUN_DB.get(run_id)
    if run is None:
        return {"status": 404, "reader": None}               # genuinely-missing -> bare 404

    gate_ok = (run["owner"] == caller)

    def deny_404():
        obs.logs.append({"level": "WARN", "run.id": run_id, "principal.id": caller,
                         "endpoint": "file", "outcome": "denied"})
        return {"status": 404, "reader": None}

    # R7: the per-principal gate runs BEFORE any launch — a deny must never spin a pod.
    if not cfg["launch_before_gate"]:
        if not gate_ok:
            return deny_404()

    covered = path in CHANGED_SET
    needs_reader = (not covered) or cfg["eager_launch"]      # R2: only beyond-changes needs a reader

    if not needs_reader:                                     # the snapshot is the default path
        return {"status": 200, "source": "snapshot", "reader": None, "path": path}

    # A full-tree-beyond-changes read. R1: the whole reader path is behind a feature flag.
    flag_on = cfg["flag_enabled"] or cfg["flag_off_launches"]
    if not flag_on:
        if cfg["flag_off_no_degrade"]:
            return {"status": 500, "reader": None}           # DEFECT: not a legible degrade
        return {"status": 200, "source": "snapshot-only", "full_tree": "unavailable",
                "reader": None, "path": path}                # clean degrade to snapshot-only

    # Flag on: launch or reuse a reader.
    if cfg["launch_before_gate"]:
        # DEFECT: the pod is spun BEFORE the gate — a non-owner still pays + mounts a peer's worktree.
        pod, outcome = cluster.get_or_launch_reader(run)
        if not gate_ok:
            return deny_404()
    else:
        pod, outcome = cluster.get_or_launch_reader(run)

    return {"status": 200, "source": "ro-reader", "reader": pod, "outcome": outcome, "path": path}


# ---- driver: a fresh Cluster + Obs per scenario -----------------------------------------------------
def _fresh(cfg):
    obs = Obs(cfg)
    return Cluster(cfg, obs), obs


# ---- invariants (R1-R8) ----------------------------------------------------------------------------
def check(cfg):
    v = []

    # R1 — flag OFF degrades to snapshot-only and launches NOTHING; flag ON makes the reader available.
    off = {**cfg, "flag_enabled": False}
    cl_off, obs_off = _fresh(off)
    r_off = serve(off, cl_off, obs_off, "run-done", "README.md", "alice")   # beyond-changes, flag off
    if cl_off.launched:
        v.append("R1 a reader pod was launched with the feature flag OFF — flag off must degrade to "
                 "snapshot-only, never spend on a pod (AC1)")
    if r_off["status"] != 200 or r_off.get("source") != "snapshot-only":
        v.append(f"R1 flag off did not degrade to a legible snapshot-only result (got status "
                 f"{r_off['status']}, source {r_off.get('source')}) — a v1 must ship on snapshot-only (AC1)")
    cl_on, obs_on = _fresh(cfg)
    r_on = serve(cfg, cl_on, obs_on, "run-done", "README.md", "alice")      # beyond-changes, flag on
    if r_on.get("source") != "ro-reader":
        v.append(f"R1 flag on did not make the reader available for a beyond-changes read (source "
                 f"{r_on.get('source')}) (AC1)")

    # R2 — a changed-set read the snapshot covers launches NOTHING; only beyond-changes launches.
    cl, obs = _fresh(cfg)
    r_cov = serve(cfg, cl, obs, "run-done", "mod.py", "alice")              # in the changed set
    if r_cov.get("source") != "snapshot":
        v.append(f"R2 a changed-set read was not served from the snapshot (source {r_cov.get('source')}) "
                 f"— the snapshot is the default path (AC2)")
    if cl.launched:
        v.append("R2 a changed-set read (the snapshot already covers it) launched a reader pod — the "
                 "reader is on-demand for beyond-changes reads ONLY (AC2)")
    cl2, obs2 = _fresh(cfg)
    serve(cfg, cl2, obs2, "run-done", "vendor/dep.go", "alice")            # beyond changes
    if not cl2.launched:
        v.append("R2 a beyond-changes full-tree read did not launch a reader — that is the one read the "
                 "snapshot cannot serve (AC2)")

    # R3 — the mount is read-only, at the Run's commit; never RW, never HEAD.
    cl, obs = _fresh(cfg)
    r = serve(cfg, cl, obs, "run-done", "README.md", "alice")
    pod = r.get("reader")
    if pod is None:
        v.append("R3 no reader launched for a beyond-changes read (AC3)")
    else:
        if not pod["read_only"]:
            v.append("R3 the reader mounts the Project PVC READ-WRITE — the mount must be RO, always (AC3)")
        if pod["ref"] != RUN_DB["run-done"]["commit"]:
            v.append(f"R3 the reader mounts at ref '{pod['ref']}' — it must mount at the Run's commit "
                     f"'{RUN_DB['run-done']['commit']}', not HEAD/another ref (AC3)")

    # R4 — the reader runs with the Run's OWN per-principal scope, revoked at teardown; never broader.
    cl, obs = _fresh(cfg)
    r = serve(cfg, cl, obs, "run-done", "README.md", "alice")
    pod = r.get("reader")
    if pod is None:
        v.append("R4 no reader launched to check credential scope (AC4)")
    else:
        expected = f"run:run-done:principal:{RUN_DB['run-done']['owner']}"
        if pod["cred_scope"] != expected:
            v.append(f"R4 the reader runs with scope '{pod['cred_scope']}' — it must be the Run's OWN "
                     f"per-principal scope '{expected}', never a broader/platform scope (AC4)")
        cl.tick_idle(IDLE_TTL_MS)                            # idle past TTL -> teardown
        if not pod["torn_down"]:
            v.append("R4 the reader was not torn down, so its credential could not be revoked (AC4)")
        elif not pod["cred_revoked"]:
            v.append("R4 the reader's credential was NOT revoked at teardown — the Run's credential must "
                     "not outlive the pod (revoked-at-teardown, AC4)")

    # R5 — short-lived: a reader idle past its TTL is torn down.
    cl, obs = _fresh(cfg)
    r = serve(cfg, cl, obs, "run-done", "README.md", "alice")
    pod = r.get("reader")
    cl.tick_idle(IDLE_TTL_MS)
    if pod is not None and not pod["torn_down"]:
        v.append("R5 a reader idle past its TTL was NOT torn down — it must be short-lived, not a "
                 "standing dev box (AC5)")
    if pod is not None and pod["run_id"] in cl.pods:
        v.append("R5 the torn-down reader is still tracked as live (AC5)")

    # R6 — a second beyond-changes read for the SAME Run reuses the live reader (no second launch).
    cl, obs = _fresh(cfg)
    r1 = serve(cfg, cl, obs, "run-done", "README.md", "alice")
    r2 = serve(cfg, cl, obs, "run-done", "vendor/dep.go", "alice")         # same Run, still live
    if r1.get("outcome") != "launched":
        v.append(f"R6 the first beyond-changes read did not launch (outcome {r1.get('outcome')}) (AC6)")
    if r2.get("outcome") != "reused":
        v.append(f"R6 a second read for the SAME live Run did not REUSE the reader (outcome "
                 f"{r2.get('outcome')}) — reuse before relaunch bounds cost/concurrency (AC6)")
    if len(cl.launched) != 1:
        v.append(f"R6 {len(cl.launched)} reader pods launched for one Run — the second read must reuse "
                 f"the first, not relaunch (AC6)")

    # R7 — the per-principal gate is inherited (deny BEFORE launch), and the mount is read-only.
    cl, obs = _fresh(cfg)
    r_peer = serve(cfg, cl, obs, "run-done", "README.md", "bob")          # same-Team peer, NOT the owner
    if r_peer["status"] != 404:
        v.append(f"R7 a non-owner read returned {r_peer['status']}, not 404 — the reader path inherits "
                 f"the 8.7d per-principal gate (existence-hiding, AC7)")
    if cl.launched:
        v.append("R7 a non-owner read LAUNCHED a reader pod before the gate denied it — a deny must "
                 "never spin a pod / mount a peer's worktree (gate before launch, AC7)")
    cl2, obs2 = _fresh(cfg)
    r_owner = serve(cfg, cl2, obs2, "run-done", "README.md", "alice")     # positive control
    pod = r_owner.get("reader")
    if pod is not None and "write" in pod["verbs"]:
        v.append(f"R7 the reader mount exposes verbs {pod['verbs']} — it must be read-only, always; no "
                 f"write verb (AC7)")

    # R8 — OBS-BB4 launch/active/ttl metrics + lifecycle logs + Standing law.
    cl, obs = _fresh(cfg)
    serve(cfg, cl, obs, "run-done", "README.md", "alice")                 # one launch
    if not obs.launched_total:
        v.append("R8 a reader launch emitted NO launched.total counter — the launch rate is the cost "
                 "signal (§7 alert); a blind counter cannot fire the launch-rate alert (AC8)")
    else:
        if any(e["outcome"] != "launched" or e["reason"] != "full_tree" for e in obs.launched_total):
            v.append("R8 the launch counter mis-labeled reason/outcome (must be {reason=full_tree, "
                     "outcome=launched}) (AC8)")
        bad_labels = sorted({k for e in obs.launched_total for k in e} - LAUNCHED_LABELS)
        if bad_labels:
            v.append(f"R8 launched.total carries forbidden label(s) {bad_labels} — bounded to "
                     f"{sorted(LAUNCHED_LABELS)}; NO `model` label on any buildbrowser instrument "
                     f"(Standing law, AC8)")
    if obs.active != 1:
        v.append(f"R8 the reader.active gauge is {obs.active} after one launch, expected 1 (AC8)")
    cl.tick_idle(IDLE_TTL_MS)                                # idle teardown -> active falls, ttl recorded
    if obs.active != 0:
        v.append(f"R8 the reader.active gauge is {obs.active} after teardown, expected 0 — the gauge "
                 f"must decrement on teardown or it reports phantom concurrency (AC8)")
    if not obs.ttl or obs.ttl[-1]["outcome"] != "idle_teardown":
        v.append("R8 no reader.ttl histogram recorded with outcome=idle_teardown on teardown (AC8)")
    bad_ttl = sorted({k for e in obs.ttl for k in ("outcome",) if k not in TTL_LABELS})
    # content-leak firewall: no file content in any log/metric line.
    leaked = [ln for ln in obs.logs if "file_content" in ln] + \
             [e for e in obs.launched_total if "model" in e]
    if leaked:
        v.append("R8 a signal leaked file content or a `model` label — buildbrowser telemetry is "
                 "magnitudes/status only; content firewall (NFR-OBS3, AC8)")

    return v


# ---- designs ---------------------------------------------------------------------------------------
def conformant_cfg():
    """The §4.2 / §5 / §7 + OBS-BB4 RO-reader lifecycle that holds R1-R8 (flag ON — the feature's own
    happy path; R1 exercises the flag-OFF degrade against a copy)."""
    return {
        "flag_enabled": True,             # R1: the feature is on for its own tests
        "flag_off_launches": False,       # R1: flag off never launches
        "flag_off_no_degrade": False,     # R1: flag off degrades legibly to snapshot-only
        "eager_launch": False,            # R2: on-demand for beyond-changes only; snapshot is default
        "mount_rw": False,                # R3: read-only mount
        "mount_wrong_ref": False,         # R3: at the Run's commit
        "broader_scope": False,           # R4: the Run's own per-principal scope
        "cred_not_revoked": False,        # R4: credential revoked at teardown
        "no_idle_teardown": False,        # R5: idle -> teardown
        "no_reuse": False,                # R6: reuse before relaunch
        "launch_before_gate": False,      # R7: gate denies before any launch
        "reader_write_verb": False,       # R7: read-only mount, no write verb
        "no_launch_metric": False,        # R8: launch emits launched.total
        "active_not_decremented": False,  # R8: teardown decrements the active gauge
        "leak": False,                    # R8: no content / no `model` label in any signal
    }


def naive_cfg():
    """The 'spin up a full RW dev pod at HEAD with platform creds, ignore the flag, relaunch every time,
    never tear down, no metrics' anti-pattern — every knob wrong. Must be DETECTED violating every
    invariant R1-R8, or the harness has no teeth."""
    c = conformant_cfg()
    c.update(
        flag_off_launches=True,          # R1: launches even with the flag off
        flag_off_no_degrade=True,        # R1: (and no legible degrade path)
        eager_launch=True,               # R2: launches for changed-set reads too
        mount_rw=True,                   # R3: RW mount
        mount_wrong_ref=True,            # R3: mounts at HEAD
        broader_scope=True,              # R4: platform scope
        cred_not_revoked=True,           # R4: credential outlives teardown
        no_idle_teardown=True,           # R5: standing box, never torn down
        no_reuse=True,                   # R6: relaunches every read
        launch_before_gate=True,         # R7: spins a pod before the gate denies
        reader_write_verb=True,          # R7: write verb on the mount
        no_launch_metric=True,           # R8: no launch counter
        active_not_decremented=True,     # R8: gauge never falls
        leak=True,                       # R8: content + model label in signals
    )
    return c


MUTATIONS = {
    "FLAG_OFF_LAUNCHES":      lambda d: d.update(flag_off_launches=True),
    "FLAG_OFF_NO_DEGRADE":    lambda d: d.update(flag_off_no_degrade=True),
    "EAGER_LAUNCH":           lambda d: d.update(eager_launch=True),
    "MOUNT_RW":               lambda d: d.update(mount_rw=True),
    "MOUNT_WRONG_REF":        lambda d: d.update(mount_wrong_ref=True),
    "BROADER_SCOPE":          lambda d: d.update(broader_scope=True),
    "CRED_NOT_REVOKED":       lambda d: d.update(cred_not_revoked=True),
    "NO_IDLE_TEARDOWN":       lambda d: d.update(no_idle_teardown=True),
    "NO_REUSE":               lambda d: d.update(no_reuse=True),
    "LAUNCH_BEFORE_GATE":     lambda d: d.update(launch_before_gate=True),
    "READER_WRITE_VERB":      lambda d: d.update(reader_write_verb=True),
    "NO_LAUNCH_METRIC":       lambda d: d.update(no_launch_metric=True),
    "ACTIVE_NOT_DECREMENTED": lambda d: d.update(active_not_decremented=True),
    "LEAK":                   lambda d: d.update(leak=True),
}

# the invariant each mutation is PRIMARILY expected to flip RED (siblings may also trip — acceptable).
MUT_INVARIANT = {
    "FLAG_OFF_LAUNCHES": "R1", "FLAG_OFF_NO_DEGRADE": "R1", "EAGER_LAUNCH": "R2",
    "MOUNT_RW": "R3", "MOUNT_WRONG_REF": "R3", "BROADER_SCOPE": "R4", "CRED_NOT_REVOKED": "R4",
    "NO_IDLE_TEARDOWN": "R5", "NO_REUSE": "R6", "LAUNCH_BEFORE_GATE": "R7", "READER_WRITE_VERB": "R7",
    "NO_LAUNCH_METRIC": "R8", "ACTIVE_NOT_DECREMENTED": "R8", "LEAK": "R8",
}

ALL_INVARIANTS = [f"R{i}" for i in range(1, 9)]


def main():
    ap = argparse.ArgumentParser(
        description="Story 8.7f on-demand RO-reader pod lifecycle falsification (design §4.2 / OBS-BB4)")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS),
                    help="inject one defect into the conformant reader lifecycle")
    args = ap.parse_args()

    # 1) Teeth: the naive 'RW dev box at HEAD, ignore the flag, never tear down, no metrics' anti-pattern
    #    must violate EVERY invariant R1-R8.
    naive_v = check(naive_cfg())
    fams = {x.split()[0] for x in naive_v}
    print(f"[bb-ro-reader] NAIVE standing-RW-dev-box anti-pattern : {len(naive_v)} violation(s) across "
          f"{len(fams)} invariant(s) -> DETECTED")
    missing = [r for r in ALL_INVARIANTS if r not in fams]
    if missing:
        print(f"[bb-ro-reader] FAIL — the naive anti-pattern did NOT trip {missing} (teeth lost)")
        for x in naive_v:
            print(f"[bb-ro-reader]   - {x}")
        return 1

    # 2) The conformant §4.2/§5/§7 + OBS-BB4 lifecycle (optionally mutated).
    cfg = conformant_cfg()
    if args.mutate:
        MUTATIONS[args.mutate](cfg)
    v = check(cfg)

    if args.mutate:
        hit = sorted({x.split()[0] for x in v}, key=lambda s: int(s[1:]))
        expected = MUT_INVARIANT[args.mutate]
        print(f"[bb-ro-reader] conformant + --mutate={args.mutate}: {len(v)} violation(s) {hit}")
        for x in v:
            print(f"[bb-ro-reader]   - {x}")
        if expected in hit:
            others = [r for r in hit if r != expected]
            tag = f" (also tripped {others} — acceptable, {expected} is the mapped tooth)" if others else ""
            print(f"[bb-ro-reader] KILLED — --mutate={args.mutate} -> {expected} RED{tag}.")
            return 1
        print(f"[bb-ro-reader] SURVIVED — --mutate={args.mutate} did NOT trip {expected} (VACUOUS GUARD)")
        return 1

    if v:
        print("[bb-ro-reader] FAIL — the conformant lifecycle violated an invariant:")
        for x in v:
            print(f"[bb-ro-reader]   - {x}")
        return 1
    print("[bb-ro-reader] PASS — the naive standing-RW-dev-box anti-pattern detectably breaks every")
    print("        invariant; the §4.2/§5/§7 + OBS-BB4 RO-reader lifecycle holds R1-R8 (flagged, off")
    print("        degrades to snapshot-only · on-demand, snapshot is default · RO mount at the Run's")
    print("        commit · Run's-own scope revoked at teardown · short-lived idle teardown · reuse")
    print("        before relaunch · per-principal gate before launch + read-only · OBS-BB4 launch/")
    print("        active/ttl + Standing-law content firewall).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
