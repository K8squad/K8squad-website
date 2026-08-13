#!/usr/bin/env python3
"""
Story 13.2 (ISI-2234) falsification — coordination metrics = the audit-spine projection.

Differential falsification, same shape as run-trace-correlation-check.py (13.1) and the coord-spine chaos
gate (2.10 / ISI-2394). It proves the coordination metrics are a FAITHFUL, LOW-CARDINALITY, OBSERVE-ONLY
projection of the §6.2 consistency spine — not a second source of truth and never on the enforcement path.

Load-bearing invariant (obs-plan §5.1, epics row 13.2): "Metrics OBSERVE; they do not implement
enforcement." The coordination record IS the audit trail; these instruments are the quantitative projection
of it (rate/latency/SLO), and every event they count is ALSO a durable audit_log/run_events row that stays
the forensic source of truth. Two teeth follow from that: (a) removing the metric emit must change ZERO
coordination behaviour — the claim winner, the fence value, the renew accept/reject, the reclaim order are
byte-for-byte identical with metrics on or off (noop-neutral, the same discipline 13.1 AC4 makes for the
tracer); (b) each metric's bounded label is DERIVED from the same outcome the audit row records, so a
fenced-out non-holder renewal projects `stale_holder` and never a mislabelled `ok`.

The §6.2 semantics modelled here are the pinned coord spine (ISI-2394 pkg/coord): SKIP-LOCKED claim +
conditional fence CAS (Acquire), Renew guarded on holder∧fence∧live (non-holder → stale_holder),
ReclaimFenced (bumps the fence), RedriveClaim (idempotent no-op when still ours → NO fence bump). fence =
`lease_epoch`, monotonic.

Mutation contract (re-run these after any edit — each MUST turn the named check RED):
  * make the fence bump READ its value from the metric series (enforce_via_metric)   -> (M2) RED.
  * mislabel a stale_holder renewal as `result=ok` (mislabel_stale)                   -> (M3) RED.
  * increment fence.epoch.increments on an idempotent redrive no-op (count_redrive)   -> (M4) RED.
  * drop stale_holder / reclaim from the §9 concurrency-alert inputs                  -> (M5) RED.
  * add run.id / work_item.id as a metric LABEL instead of an exemplar               -> (M6) RED.
  * drop the exemplar that joins the low-card metric back to the 13.1 trace          -> (M7) RED.

stdlib only. `python3 coord-metrics-check.py`. Exits non-zero on any falsification. No wall-clock, no RNG:
fence epochs are a deterministic monotonic counter, so "did the metric leak onto the enforcement path?" is a
pure identity test (the epoch sequence with metrics off must equal the sequence with metrics on).
"""
import sys

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)

# --- §5.6 cardinality budget (the subset of the allowlist §5.1 draws from) -------------------
ALLOWED_LABELS = {"result", "trigger", "state", "kind", "error_code"}
# §5.6 "forbidden as metric labels — trace/log/exemplar only": unbounded per-actor identifiers.
FORBIDDEN_LABELS = {"run.id", "work_item.id", "principal.id", "team", "project", "sandbox.pod"}

RECLAIM_THRASH_MULT = 3   # §9: "reclaim rate 3x baseline (thrash)" fires the page.


class Metrics:
    """The OTel instrument sink. Records (name, labelset) series + exemplars. A cardinality guard flags any
    label KEY outside the §5.6 allowlist (13.6's CI lint made local). `recording=False` = OTLP endpoint
    unset -> non-recording, zero series exported (13.1 AC4, inherited)."""
    def __init__(self, recording=True):
        self.recording = recording
        self.series = {}      # (name, labelset-tuple) -> count
        self.exemplars = {}   # (name, labelset-tuple) -> [exemplar dicts]
        self.card_violations = []  # forbidden/unknown label keys that reached an instrument

    def emit(self, name, labels, exemplar=None):
        for k in labels:
            if k in FORBIDDEN_LABELS or k not in ALLOWED_LABELS:
                self.card_violations.append((name, k))
        if not self.recording:
            return
        key = (name, tuple(sorted(labels.items())))
        self.series[key] = self.series.get(key, 0) + 1
        if exemplar is not None:
            self.exemplars.setdefault(key, []).append(exemplar)

    def count(self, name, **want):
        total = 0
        for (n, lbls), v in self.series.items():
            if n != name:
                continue
            d = dict(lbls)
            if all(d.get(k) == val for k, val in want.items()):
                total += v
        return total

    def exemplars_for(self, name, **want):
        out = []
        for (n, lbls), exs in self.exemplars.items():
            if n != name:
                continue
            d = dict(lbls)
            if all(d.get(k) == val for k, val in want.items()):
                out.extend(exs)
        return out


class Coord:
    """The §6.2 coordination spine, instrumented. The ENFORCEMENT logic (holder, epoch, state) is the source
    of truth and NEVER reads a metric — except under the `enforce_via_metric` mutation, which is what the
    observe-not-enforce teeth (M2) exist to catch. Metric emits are pure projections appended after each
    decision; label values are derived from the decision the audit row records."""
    def __init__(self, metrics, enforce_via_metric=False, mislabel_stale=False,
                 count_redrive_fence=False, label_run_id=False, drop_exemplar=False):
        self.m = metrics
        self.enforce_via_metric = enforce_via_metric
        self.mislabel_stale = mislabel_stale
        self.count_redrive_fence = count_redrive_fence
        self.label_run_id = label_run_id
        self.drop_exemplar = drop_exemplar
        self.holder = None
        self.epoch = 0        # = lease_epoch / fence token (§6.2), monotonic
        self.lease_live = False
        self.state = "open"

    # -- fence token ---------------------------------------------------------------------------
    def _bump_fence(self, work_item="wi-1"):
        if self.enforce_via_metric:
            # MUTATION (M2): the enforcement path READS the metric series as its fence state. With the
            # exporter off the series is empty, so the epoch stalls -> the fencing CAS can no longer
            # distinguish a stale holder. A metric must never be load-bearing for correctness.
            self.epoch = self.m.count("ksquad.coord.fence.epoch.increments") + 1
        else:
            self.epoch += 1
        self.m.emit("ksquad.coord.fence.epoch.increments", {},
                    exemplar=None if self.drop_exemplar else {"work_item.id": work_item, "fence": self.epoch})

    def _exemplar(self, run_id, work_item="wi-1"):
        return None if self.drop_exemplar else {"run.id": run_id, "work_item.id": work_item}

    def _labels(self, base, run_id):
        # M6 mutation: put the unbounded run.id on the metric as a LABEL (cardinality explosion) instead of
        # letting it ride as an exemplar. §5.6 forbids this outright.
        if self.label_run_id:
            base = dict(base, **{"run.id": run_id})
        return base

    # -- §6.2 operations -----------------------------------------------------------------------
    def claim(self, run_id, item_available=True, contended=False):
        if not item_available:
            result = "empty"
        elif self.holder is not None and self.lease_live and contended:
            result = "contended"                       # lost the SKIP-LOCKED race
        else:
            self.holder, self.state, self.lease_live = run_id, "claimed", True
            self._bump_fence()                          # Acquire bumps the fence
            result = "acquired"
        self.m.emit("ksquad.coord.claim.total", self._labels({"result": result}, run_id),
                    exemplar=self._exemplar(run_id))
        return result

    def renew(self, run_id):
        # §6.2 Renew guard: holder ∧ fence ∧ live. A non-holder (fenced-out / expired) is rejected.
        result = "ok" if (self.holder == run_id and self.lease_live) else "stale_holder"
        label = "ok" if (self.mislabel_stale and result == "stale_holder") else result
        self.m.emit("ksquad.coord.lease.renew.total", self._labels({"result": label}, run_id),
                    exemplar=self._exemplar(run_id))
        return result   # enforcement ALWAYS returns the truthful outcome; only the metric label mutates

    def reclaim(self, trigger, work_item="wi-1"):        # trigger ∈ expiry|sweeper
        self.holder, self.lease_live, self.state = None, False, "open"
        self._bump_fence(work_item)                      # ReclaimFenced bumps the fence
        self.m.emit("ksquad.coord.lease.reclaim.total", {"trigger": trigger},
                    exemplar=None if self.drop_exemplar else {"work_item.id": work_item})

    def redrive(self, run_id):
        # RedriveClaim: idempotent no-op when the item is STILL ours -> NO fence bump (no real thrash).
        if self.holder == run_id and self.lease_live:
            if self.count_redrive_fence:
                self._bump_fence()                       # MUTATION (M4): phantom churn signal
            return "noop"
        return self.claim(run_id)


def concurrency_alert(metrics, include_stale=True, include_reclaim=True, baseline=1):
    """§9 concurrency alert (page-grade, correctness). Fires on sustained stale_holder renewals OR a reclaim
    rate above the thrash multiple. `include_*` model the mutation of disconnecting a correctness signal."""
    fired = []
    stale = metrics.count("ksquad.coord.lease.renew.total", result="stale_holder")
    reclaim = metrics.count("ksquad.coord.lease.reclaim.total")
    if include_stale and stale > 0:
        fired.append("stale_holder")
    if include_reclaim and reclaim >= RECLAIM_THRASH_MULT * baseline:
        fired.append("reclaim_thrash")
    return fired


# ---------------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------------
def epoch_sequence(recording, enforce_via_metric):
    """Drive claim -> reclaim -> claim and record the fence-epoch after each bump. Observe-not-enforce
    demands this sequence be IDENTICAL whether the exporter is recording or not."""
    m = Metrics(recording=recording)
    c = Coord(m, enforce_via_metric=enforce_via_metric)
    seq = []
    c.claim("run-A"); seq.append(c.epoch)
    c.reclaim("expiry"); seq.append(c.epoch)
    c.claim("run-B"); seq.append(c.epoch)
    return seq


def scenario_observe_not_enforce(enforce_via_metric):
    """M2 crux: coordination outcome must not depend on whether metrics are recorded."""
    return epoch_sequence(True, enforce_via_metric) == epoch_sequence(False, enforce_via_metric)


def scenario_faithful_renew(mislabel_stale):
    """M3: a fenced-out non-holder renewal is enforced-rejected AND projected as stale_holder."""
    m = Metrics()
    c = Coord(m, mislabel_stale=mislabel_stale)
    c.claim("run-A")                     # run-A holds
    truth = c.renew("run-B")             # run-B is not the holder -> stale_holder (enforcement truth)
    # faithful iff the metric label matches the enforced outcome (source of truth = the audit row).
    metric_says_stale = m.count("ksquad.coord.lease.renew.total", result="stale_holder") == 1
    return truth == "stale_holder" and metric_says_stale


def scenario_redrive_no_phantom_fence(count_redrive_fence):
    """M4: an idempotent redrive (still ours) must NOT increment fence.epoch.increments."""
    m = Metrics()
    c = Coord(m, count_redrive_fence=count_redrive_fence)
    c.claim("run-A")
    before = m.count("ksquad.coord.fence.epoch.increments")
    c.redrive("run-A")                   # still ours -> no-op
    after = m.count("ksquad.coord.fence.epoch.increments")
    return after == before


def scenario_alert_wiring(include_stale, include_reclaim):
    """M5: stale_holder + reclaim must reach the page-grade §9 concurrency alert."""
    m = Metrics()
    c = Coord(m)
    c.claim("run-A")
    c.renew("run-B")                     # stale_holder
    c.reclaim("sweeper"); c.reclaim("sweeper"); c.reclaim("sweeper")  # >= 3x baseline
    return concurrency_alert(m, include_stale=include_stale, include_reclaim=include_reclaim)


def scenario_cardinality(label_run_id):
    """M6: run.id/work_item.id ride as exemplars, never labels; a forbidden label key is a violation."""
    m = Metrics()
    c = Coord(m, label_run_id=label_run_id)
    c.claim("run-A")
    c.renew("run-A")
    return m.card_violations


def scenario_exemplar_join(drop_exemplar):
    """M7: the low-card metric still joins to a specific §6.2 event (13.1 trace) via an exemplar."""
    m = Metrics()
    c = Coord(m, drop_exemplar=drop_exemplar)
    c.claim("run-A")
    exs = m.exemplars_for("ksquad.coord.claim.total", result="acquired")
    return any(e.get("run.id") == "run-A" for e in exs)


# The full §5.1 audit-spine projection this story ships (AC1). Names are the semconv names (§7).
REQUIRED_INSTRUMENTS = {
    "ksquad.coord.claim.total": ("counter", {"result"}),
    "ksquad.coord.claim.duration": ("histogram", {"result"}),
    "ksquad.coord.lease.renew.total": ("counter", {"result"}),
    "ksquad.coord.lease.reclaim.total": ("counter", {"trigger"}),
    "ksquad.coord.fence.epoch.increments": ("counter", set()),
    "ksquad.coord.workitem.state": ("gauge", {"state"}),
    "ksquad.coord.workitem.blocked": ("gauge", {"error_code"}),
    "ksquad.coord.append.total": ("counter", {"kind"}),
    "ksquad.coord.claim.contention.depth": ("gauge", set()),
}


def main():
    # AC1 — the projection is the §5.1 shape, and every declared label is a bounded §5.6 enum key.
    for name, (_typ, labels) in REQUIRED_INSTRUMENTS.items():
        for k in labels:
            check(k in ALLOWED_LABELS,
                  f"AC1 FAILED: instrument {name} declares label {k!r} outside the §5.6 allowlist")
        check(labels.isdisjoint(FORBIDDEN_LABELS),
              f"AC1 FAILED: instrument {name} declares a forbidden (unbounded) label")

    # AC2/M2 — observe, do not enforce: the fence-epoch sequence is identical with metrics on/off.
    check(scenario_observe_not_enforce(enforce_via_metric=False) is True,
          "AC2/M2 FAILED: the coordination outcome differed between metrics-on and metrics-off even on the "
          "clean (non-enforcing) path — a metric is leaking onto the enforcement path")
    check(scenario_observe_not_enforce(enforce_via_metric=True) is False,
          "AC2/M2 mutation-guard FAILED: routing the fence bump THROUGH the metric series did NOT change the "
          "coord outcome when the exporter was off — the observe-not-enforce invariant has no teeth")

    # AC3/M3 — faithful projection: a non-holder renewal is stale_holder in the metric, never `ok`.
    check(scenario_faithful_renew(mislabel_stale=False) is True,
          "AC3/M3 FAILED: a fenced-out non-holder renewal was not projected as result=stale_holder")
    check(scenario_faithful_renew(mislabel_stale=True) is False,
          "AC3/M3 mutation-guard FAILED: mislabelling a stale_holder renewal as result=ok was NOT detected "
          "— the fencing signal has no teeth")

    # AC3/M4 — fence.epoch.increments counts REAL bumps only; an idempotent redrive does not increment.
    check(scenario_redrive_no_phantom_fence(count_redrive_fence=False) is True,
          "AC3/M4 FAILED: an idempotent redrive no-op incremented fence.epoch.increments on the clean path")
    check(scenario_redrive_no_phantom_fence(count_redrive_fence=True) is False,
          "AC3/M4 mutation-guard FAILED: incrementing fence.epoch.increments on an idempotent redrive was "
          "NOT detected — a phantom-thrash false alert would be invisible")

    # AC4/M5 — stale_holder + reclaim are wired to the §9 page-grade concurrency alert.
    fired = scenario_alert_wiring(include_stale=True, include_reclaim=True)
    check("stale_holder" in fired and "reclaim_thrash" in fired,
          "AC4/M5 FAILED: sustained stale_holder and reclaim-thrash did not fire the §9 concurrency alert")
    check("stale_holder" not in scenario_alert_wiring(include_stale=False, include_reclaim=True),
          "AC4/M5 mutation-guard FAILED: disconnecting stale_holder from the alert inputs did NOT drop it "
          "from the page — the correctness signal is demoted to a nicety with no teeth")
    check("reclaim_thrash" not in scenario_alert_wiring(include_stale=True, include_reclaim=False),
          "AC4/M5 mutation-guard FAILED: disconnecting reclaim from the alert inputs did NOT drop it")

    # AC5/M6 — cardinality: run.id/work_item.id are exemplars, never labels.
    check(scenario_cardinality(label_run_id=False) == [],
          "AC5/M6 FAILED: the clean path emitted a metric label outside the §5.6 allowlist")
    check(len(scenario_cardinality(label_run_id=True)) > 0,
          "AC5/M6 mutation-guard FAILED: adding run.id as a metric LABEL was NOT caught by the cardinality "
          "guard — the §5.6 forbidden-label law has no teeth")

    # AC5/M7 — the low-card metric still joins to the specific §6.2 event via a 13.1 exemplar.
    check(scenario_exemplar_join(drop_exemplar=False) is True,
          "AC5/M7 FAILED: claim.total carried no exemplar joining it to the run's 13.1 trace")
    check(scenario_exemplar_join(drop_exemplar=True) is False,
          "AC5/M7 mutation-guard FAILED: dropping the exemplar still left the metric joinable — the "
          "trace-join has no teeth")

    if FAIL:
        print("FALSIFIED — Story 13.2 coordination-metrics design check FAILED:")
        for msg in FAIL:
            print("  ✗", msg)
        sys.exit(1)
    print("OK — Story 13.2 coordination metrics project the §6.2 audit spine with teeth:")
    print("  (AC1) the §5.1 instrument set is present; every label is a bounded §5.6 enum")
    print("  (M2)  metrics OBSERVE, not enforce: fence-epoch sequence identical with the exporter on/off;")
    print("        routing the fence bump through the metric series is caught (observe-not-enforce crux)")
    print("  (M3)  a fenced-out non-holder renewal projects result=stale_holder; mislabelling it ok is caught")
    print("  (M4)  fence.epoch.increments counts real bumps only; a redrive-noop increment is caught")
    print("  (M5)  stale_holder + reclaim fire the §9 page-grade concurrency alert; disconnecting either is caught")
    print("  (M6)  run.id/work_item.id ride as exemplars; adding one as a metric label is caught (§5.6)")
    print("  (M7)  the low-card metric still joins to the run's 13.1 trace via an exemplar; dropping it is caught")


if __name__ == "__main__":
    main()
