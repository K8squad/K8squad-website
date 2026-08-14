#!/usr/bin/env python3
"""
Story 13.4 (ISI-2236) falsification — token + cost consumption metering per principal.

Differential falsification, same shape as coord-metrics-check.py (13.2) and run-trace-correlation-check.py
(13.1). It proves the consumption-metering signal is a FAITHFUL, BEST-EFFORT, LOW-CARDINALITY, OBSERVE-ONLY
projection of what the shims report — attributed per user/principal, with per-ticket and per-user cost as a
BACKEND rollup over exemplars/traces, and NO bespoke accounting path.

Load-bearing invariants (obs-plan §5.5 / §15 / §16.5, epics row 13.4):
  * The one signal is `ksquad.agent.tokens{runtime, direction}` — direction ∈ input|output, and those two
    are the ONLY labels. It is best-effort / runtime-reported (OQ14): legibility, NOT the billing authority.
  * Per-ticket rollups aggregate on `work_item.id`; per-user cost rollups aggregate on `user.id` — BOTH via
    exemplars/traces, NEVER as a metric label (cardinality law §1.2/§5.6). `run.id`/`work_item.id`/`user.id`/
    `principal.id` ride as exemplars; adding one as a label is a build failure (13.6 enforces, this obeys).
  * Cost is a BACKEND computation over this signal × a price table (§16.5) — never a new emitted instrument,
    never a metric label; with no price table it degrades to tokens-only, never a hard failure.
  * No bespoke accounting path (epics 13.4 / 8.8): the dashboard's authoritative per-scope total IS the OTel
    token rollup (§17.2 metrics query seam) — not a second private ledger that can silently drift.
  * Metering OBSERVES; it is NEVER load-bearing. The agent run outcome — dispatch and the §5.9 context-budget
    fit/truncation decision — is byte-for-byte identical with the exporter on/off (noop-neutral, the same
    discipline 13.1 AC4 makes for the tracer, 13.2 AC2 makes for the coord path). Nothing on the enforcement
    path may read the tokens metric.

Mutation contract (re-run after any edit — each MUST turn the named check RED):
  * make the §5.9 budget-fit READ consumed tokens from the metric series (enforce_via_metric)  -> (M2) RED.
  * label output tokens as input / swap the direction (mislabel_direction)                     -> (M3) RED.
  * fabricate a default token count for a turn the shim never reported (fabricate_missing)     -> (M4) RED.
  * drop the exemplar that carries user.id/work_item.id (drop_exemplar)                         -> (M5) RED.
  * add user.id (or any unbounded id) as a metric LABEL instead of an exemplar (label_user_id) -> (M6) RED.
  * source the dashboard total from a bespoke private ledger instead of the rollup (bespoke)    -> (M7) RED.
  * emit cost as its own instrument instead of a backend rollup over tokens (cost_as_metric)    -> (M8) RED.

stdlib only. `python3 token-metering-check.py`. Exits non-zero on any falsification. No wall-clock, no RNG:
token counts are deterministic, so "did the metric leak onto the enforcement path?" is a pure identity test
(the truncation-decision sequence with the exporter off must equal the sequence with it on).
"""
import sys

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)

# --- §5.5 / §5.6 cardinality budget --------------------------------------------------------------
# The ONLY labels ksquad.agent.tokens carries. direction ∈ input|output; runtime is a finite enum.
ALLOWED_LABELS = {"runtime", "direction"}
# §5.6 "forbidden as metric labels — trace/log/exemplar only": unbounded per-actor identifiers.
FORBIDDEN_LABELS = {"run.id", "work_item.id", "principal.id", "user.id", "team", "project", "sandbox.pod"}

DIRECTIONS = {"input", "output"}
CONTEXT_WINDOW = 1000   # §5.9 model context window (a durable property of the model endpoint, §10.3)


class Metrics:
    """The OTel instrument sink. Records (name, labelset) -> summed value + exemplars. A cardinality guard
    flags any label KEY outside the §5.6 allowlist (13.6's CI lint made local). `recording=False` = OTLP
    endpoint unset -> non-recording, zero series exported (13.1 AC4, inherited)."""
    def __init__(self, recording=True):
        self.recording = recording
        self.series = {}         # (name, labelset-tuple) -> summed value
        self.exemplars = {}      # (name, labelset-tuple) -> [exemplar dicts, each carries "value"]
        self.instruments = set() # every instrument NAME an emit touched (recording or not)
        self.card_violations = []

    def emit(self, name, labels, value=1, exemplar=None):
        self.instruments.add(name)
        for k in labels:
            if k in FORBIDDEN_LABELS or k not in ALLOWED_LABELS:
                self.card_violations.append((name, k))
        if not self.recording:
            return
        key = (name, tuple(sorted(labels.items())))
        self.series[key] = self.series.get(key, 0) + value
        if exemplar is not None:
            ex = dict(exemplar); ex["value"] = value
            self.exemplars.setdefault(key, []).append(ex)

    def total(self, name, **want):
        t = 0
        for (n, lbls), v in self.series.items():
            if n != name:
                continue
            d = dict(lbls)
            if all(d.get(k) == val for k, val in want.items()):
                t += v
        return t

    def exemplars_for(self, name, **want):
        out = []
        for (n, lbls), exs in self.exemplars.items():
            if n != name:
                continue
            d = dict(lbls)
            if all(d.get(k) == val for k, val in want.items()):
                out.extend(exs)
        return out


class Ledger:
    """A private, bespoke accounting store (the anti-pattern 13.4 / 8.8 forbid). A SECOND write path that
    inevitably drifts from the metered truth."""
    def __init__(self):
        self.by_user = {}
    def add(self, user_id, tokens):
        self.by_user[user_id] = self.by_user.get(user_id, 0) + tokens
    def total(self):
        return sum(self.by_user.values())


class TokenMeter:
    """Shim-surfaced token accounting. The shim REPORTS usage best-effort; the meter PROJECTS it as
    ksquad.agent.tokens{runtime, direction} with run.id/work_item.id/user.id on the EXEMPLAR. Enforcement
    (dispatch, the §5.9 budget fit) NEVER reads this metric — except under the enforce_via_metric mutation,
    which is exactly what the observe-not-enforce teeth (M2) exist to catch."""
    def __init__(self, metrics, mislabel_direction=False, fabricate_missing=False,
                 label_user_id=False, drop_exemplar=False, cost_as_metric=False):
        self.m = metrics
        self.mislabel_direction = mislabel_direction
        self.fabricate_missing = fabricate_missing
        self.label_user_id = label_user_id
        self.drop_exemplar = drop_exemplar
        self.cost_as_metric = cost_as_metric
        self.reported_truth = 0   # sum of tokens the shim ACTUALLY reported (source-of-truth for M4)

    def report(self, run_id, work_item, user_id, runtime, input_tokens, output_tokens, reported=True):
        if not reported:
            if not self.fabricate_missing:
                return   # best-effort honesty: a silent shim advances NOTHING; absent, never a fake number
            # MUTATION (M4): invent consumption the shim never reported (does NOT touch reported_truth).
            input_tokens, output_tokens = 1000, 1000
        else:
            self.reported_truth += input_tokens + output_tokens

        for direction, val in (("input", input_tokens), ("output", output_tokens)):
            # M3 mutation: project output tokens under direction=input (and vice-versa) — the input/output
            # split silently lies. The label MUST be derived from the direction the shim actually reported.
            lbl_dir = {"input": "output", "output": "input"}[direction] if self.mislabel_direction else direction
            labels = {"runtime": runtime, "direction": lbl_dir}
            if self.label_user_id:
                # M6 mutation: put the unbounded user.id on the metric as a LABEL (cardinality explosion).
                labels = dict(labels, **{"user.id": user_id})
            ex = None if self.drop_exemplar else {"run.id": run_id, "work_item.id": work_item, "user.id": user_id}
            self.m.emit("ksquad.agent.tokens", labels, value=val, exemplar=ex)
            if self.cost_as_metric:
                # M8 mutation: bake pricing into a NEW emitted instrument instead of a backend rollup (§16.5).
                self.m.emit("ksquad.agent.cost", {"runtime": runtime}, value=val, exemplar=ex)


def budget_fit(metrics, envelope_tokens, enforce_via_metric=False):
    """§5.9 context-budget decision: does the assembled envelope fit the model window? The correct path reads
    ONLY durable inputs (the model window + the envelope size). Returns True=fits, False=must-truncate."""
    window = CONTEXT_WINDOW
    if enforce_via_metric:
        # MUTATION (M2): subtract already-METERED consumption read FROM THE METRIC series. With the exporter
        # off the series is empty, so the fit decision flips — a metric made load-bearing for correctness.
        window -= metrics.total("ksquad.agent.tokens")
    return envelope_tokens <= window


def rollup(metrics, by="user.id", price_table=None):
    """Backend per-scope aggregation over the token exemplars (§15/§16.5): sum token values grouped by the
    exemplar dimension (user.id for per-user, work_item.id for per-ticket). Cost = the same rollup × a price
    table; with no price table it DEGRADES to tokens-only (never a hard failure)."""
    agg = {}
    for ex in metrics.exemplars_for("ksquad.agent.tokens"):
        key = ex.get(by)
        if key is None:
            continue   # no exemplar -> the data point cannot be attributed to a principal/ticket
        agg[key] = agg.get(key, 0) + ex["value"]
    if price_table is not None:
        return {k: v * price_table for k, v in agg.items()}
    return agg


# ---------------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------------
def truncation_sequence(recording, enforce_via_metric):
    """Drive two agent turns, each reporting usage, and record the §5.9 fit decision for a fixed envelope.
    Observe-not-enforce demands this sequence be IDENTICAL whether the exporter is recording or not."""
    m = Metrics(recording=recording)
    meter = TokenMeter(m)
    seq = []
    meter.report("run-A", "wi-1", "user-1", "openclaw", 400, 400)
    seq.append(budget_fit(m, 700, enforce_via_metric))
    meter.report("run-A", "wi-1", "user-1", "openclaw", 400, 400)
    seq.append(budget_fit(m, 700, enforce_via_metric))
    return seq


def scenario_observe_not_enforce(enforce_via_metric):
    """M2 crux: the agent run outcome must not depend on whether tokens are metered."""
    return truncation_sequence(True, enforce_via_metric) == truncation_sequence(False, enforce_via_metric)


def scenario_faithful_direction(mislabel_direction):
    """M3: input/output are separate direction series, each derived from what the shim reported."""
    m = Metrics()
    meter = TokenMeter(m, mislabel_direction=mislabel_direction)
    meter.report("run-A", "wi-1", "user-1", "openclaw", 100, 30)
    return (m.total("ksquad.agent.tokens", direction="input") == 100 and
            m.total("ksquad.agent.tokens", direction="output") == 30)


def scenario_best_effort(fabricate_missing):
    """M4: a silent shim (no usage reported) advances NOTHING — the metric never exceeds the reported truth."""
    m = Metrics()
    meter = TokenMeter(m, fabricate_missing=fabricate_missing)
    meter.report("run-A", "wi-1", "user-1", "openclaw", 100, 50)          # reported
    meter.report("run-B", "wi-2", "user-1", "openclaw", 0, 0, reported=False)  # silent shim
    return m.total("ksquad.agent.tokens") == meter.reported_truth


def scenario_attribution(drop_exemplar):
    """M5: per-user AND per-ticket totals are backend rollups over the exemplar dimension."""
    m = Metrics()
    meter = TokenMeter(m, drop_exemplar=drop_exemplar)
    meter.report("run-A", "wi-1", "user-1", "openclaw", 100, 50)
    meter.report("run-B", "wi-2", "user-2", "hermes", 200, 100)
    per_user = rollup(m, by="user.id")
    per_ticket = rollup(m, by="work_item.id")
    return (per_user.get("user-1") == 150 and per_user.get("user-2") == 300 and
            per_ticket.get("wi-1") == 150 and per_ticket.get("wi-2") == 300)


def scenario_cardinality(label_user_id):
    """M6: user.id/run.id/work_item.id ride as exemplars, never labels."""
    m = Metrics()
    meter = TokenMeter(m, label_user_id=label_user_id)
    meter.report("run-A", "wi-1", "user-1", "openclaw", 100, 50)
    return m.card_violations


def scenario_no_bespoke_path(bespoke_ledger):
    """M7: the dashboard's authoritative total IS the OTel token rollup — not a private ledger that drifts."""
    m = Metrics()
    meter = TokenMeter(m)
    ledger = Ledger()
    reports = [("run-A", "wi-1", "user-1", "openclaw", 100, 50),
               ("run-B", "wi-2", "user-2", "hermes", 200, 100)]
    for i, (r, wi, u, rt, it, ot) in enumerate(reports):
        meter.report(r, wi, u, rt, it, ot)
        # A bespoke ledger is a SECOND write path; here it silently misses one report (the drift 13.4 forbids).
        if not (bespoke_ledger and i == 1):
            ledger.add(u, it + ot)
    otel_total = sum(rollup(m, by="user.id").values())
    dashboard_total = ledger.total() if bespoke_ledger else otel_total
    return dashboard_total == otel_total


def scenario_cost_is_backend_rollup(cost_as_metric):
    """M8: cost is a backend computation over the token signal (× price table), never its own instrument;
    and it degrades to tokens-only when no price table is configured (never a hard failure)."""
    m = Metrics()
    meter = TokenMeter(m, cost_as_metric=cost_as_metric)
    meter.report("run-A", "wi-1", "user-1", "openclaw", 100, 50)
    only_tokens_emitted = (m.instruments == {"ksquad.agent.tokens"})
    tokens_only = rollup(m, by="user.id", price_table=None)   # degrade: tokens, no cost, no error
    priced = rollup(m, by="user.id", price_table=2)           # cost = tokens × price (backend)
    degrades = tokens_only.get("user-1") == 150 and priced.get("user-1") == 300
    return only_tokens_emitted and degrades


# The signal this story ships (AC1) — the §5.5 shape, aligned to OTel gen_ai.usage.* (§7).
REQUIRED_INSTRUMENTS = {
    "ksquad.agent.tokens": ("counter", {"runtime", "direction"}),
}


def main():
    # AC1 — the §5.5 shape: one counter, exactly {runtime, direction}, every label a bounded §5.6 enum key.
    for name, (_typ, labels) in REQUIRED_INSTRUMENTS.items():
        for k in labels:
            check(k in ALLOWED_LABELS,
                  f"AC1 FAILED: instrument {name} declares label {k!r} outside the §5.6 allowlist")
        check(labels.isdisjoint(FORBIDDEN_LABELS),
              f"AC1 FAILED: instrument {name} declares a forbidden (unbounded) label")

    # AC2/M2 — observe, do not enforce: the run outcome (the §5.9 fit decision) is identical metrics on/off.
    check(scenario_observe_not_enforce(enforce_via_metric=False) is True,
          "AC2/M2 FAILED: the agent run outcome differed between metering-on and metering-off even on the "
          "clean path — the tokens metric is leaking onto the §5.9 enforcement path")
    check(scenario_observe_not_enforce(enforce_via_metric=True) is False,
          "AC2/M2 mutation-guard FAILED: routing the §5.9 budget fit THROUGH the tokens metric did NOT change "
          "the run outcome when the exporter was off — the observe-not-enforce invariant has no teeth")

    # AC3/M3 — faithful direction: input and output are distinct, each derived from the shim's report.
    check(scenario_faithful_direction(mislabel_direction=False) is True,
          "AC3/M3 FAILED: input/output token direction series were not recorded faithfully")
    check(scenario_faithful_direction(mislabel_direction=True) is False,
          "AC3/M3 mutation-guard FAILED: swapping the input/output direction label was NOT detected — the "
          "direction split has no teeth")

    # AC4/M4 — best-effort honesty: a silent shim advances nothing; the metric never fabricates consumption.
    check(scenario_best_effort(fabricate_missing=False) is True,
          "AC4/M4 FAILED: a silent shim (no usage reported) advanced the tokens metric on the clean path")
    check(scenario_best_effort(fabricate_missing=True) is False,
          "AC4/M4 mutation-guard FAILED: fabricating a default token count for an unreported turn was NOT "
          "detected — best-effort/runtime-reported (OQ14) has no teeth and the metric invents billing data")

    # AC5/M5 — per-principal + per-ticket rollups are backend aggregations over the exemplar dimension.
    check(scenario_attribution(drop_exemplar=False) is True,
          "AC5/M5 FAILED: per-user / per-ticket token rollups over the exemplars were wrong on the clean path")
    check(scenario_attribution(drop_exemplar=True) is False,
          "AC5/M5 mutation-guard FAILED: dropping the run.id/work_item.id/user.id exemplar still left the "
          "metric attributable — per-principal attribution has no teeth")

    # AC5/M6 — cardinality: user.id/run.id/work_item.id are exemplars, never labels.
    check(scenario_cardinality(label_user_id=False) == [],
          "AC5/M6 FAILED: the clean path emitted a metric label outside the §5.6 allowlist")
    check(len(scenario_cardinality(label_user_id=True)) > 0,
          "AC5/M6 mutation-guard FAILED: adding user.id as a metric LABEL was NOT caught by the cardinality "
          "guard — the §5.6 forbidden-label law has no teeth")

    # AC6/M7 — no bespoke accounting path: the dashboard total is the OTel rollup, not a private ledger.
    check(scenario_no_bespoke_path(bespoke_ledger=False) is True,
          "AC6/M7 FAILED: the dashboard total diverged from the OTel token rollup on the clean path")
    check(scenario_no_bespoke_path(bespoke_ledger=True) is False,
          "AC6/M7 mutation-guard FAILED: sourcing the dashboard from a bespoke private ledger did NOT drift "
          "from the metered truth — the no-bespoke-accounting-path law has no teeth")

    # AC7/M8 — cost is a backend rollup over the token signal (× price table), never its own instrument.
    check(scenario_cost_is_backend_rollup(cost_as_metric=False) is True,
          "AC7/M8 FAILED: cost was not a backend rollup over tokens, or it did not degrade to tokens-only "
          "without a price table")
    check(scenario_cost_is_backend_rollup(cost_as_metric=True) is False,
          "AC7/M8 mutation-guard FAILED: emitting cost as its own instrument instead of a backend rollup was "
          "NOT detected — cost-as-computation-over-the-signal has no teeth")

    if FAIL:
        print("FALSIFIED — Story 13.4 token-metering design check FAILED:")
        for msg in FAIL:
            print("  ✗", msg)
        sys.exit(1)
    print("OK — Story 13.4 token + cost metering is a faithful, best-effort, observe-only per-principal projection:")
    print("  (AC1) ksquad.agent.tokens is a counter with exactly {runtime, direction}; both bounded §5.6 enums")
    print("  (M2)  metering OBSERVES, not enforces: the §5.9 fit decision is identical with the exporter on/off;")
    print("        routing the budget fit through the tokens metric is caught (observe-not-enforce crux)")
    print("  (M3)  input/output direction is faithful; swapping the direction label is caught")
    print("  (M4)  best-effort: a silent shim advances nothing; fabricating unreported consumption is caught")
    print("  (M5)  per-user + per-ticket rollups aggregate over the exemplar; dropping it is caught")
    print("  (M6)  user.id/run.id/work_item.id ride as exemplars; adding one as a metric label is caught (§5.6)")
    print("  (M7)  the dashboard total IS the OTel rollup; a bespoke private ledger that drifts is caught")
    print("  (M8)  cost is a backend rollup over tokens (× price, degrades to tokens-only); a cost instrument is caught")


if __name__ == "__main__":
    main()
