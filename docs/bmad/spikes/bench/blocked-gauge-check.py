#!/usr/bin/env python3
"""blocked-gauge-check.py — differential falsification for Story 13.3.

Models the coord *blocked condition* (arch §6/r24/r25) instrumented with the
`ksquad.coord.workitem.blocked{error_code}` up/down gauge (obs-plan §5.1/§5.6/§15),
and proves the projection has TEETH: for each acceptance invariant there is a
mutation that turns the check RED. Stdlib-only; `python3 blocked-gauge-check.py`.

Invariants under test (see the story's AC list):
  AC1  up/down gauge, not a counter — a resolved block decrements back, settles to 0.
  AC2  observe-not-enforce (crux) — claimability identical with the gauge on/off.
  AC3/AC4 unknown blocked_reason -> `other` (crux) — no free-form string as a label,
       and the block is still observable (moves the `other` bar, not dropped).
  AC5  cardinality — only `error_code` is a label; work_item.id/run.id ride as exemplars.
"""

import sys

# The curated error_code enum — the §15 taxonomy, landed by Story 13.3 (AC3).
CURATED = {
    "needs_approval", "blocked_by_dep", "awaiting_credential", "awaiting_input",
    "awaiting_review", "budget_exhausted", "upstream_failed", "other",
}
# §5.6: the ONLY label key this gauge may carry. Everything else rides as an exemplar.
ALLOWED_LABEL_KEYS = {"error_code"}
FORBIDDEN_AS_LABEL = {"work_item.id", "run.id", "principal.id", "team", "project"}


def curate(blocked_reason):
    """Map a raw coord blocked_reason to the curated enum; unknown -> `other` (AC4)."""
    return blocked_reason if blocked_reason in CURATED else "other"


class Gauge:
    """The up/down gauge sink + its exemplars. A projection — never read by enforcement."""

    def __init__(self, mut=None):
        self.mut = mut or set()
        self.values = {}       # error_code -> current depth
        self.exemplars = {}    # error_code -> list of {work_item.id, run.id}
        self.label_keys = set()

    def _emit_labels(self, error_code, wi_id):
        # Clean path: the sole label key is `error_code`.
        labels = {"error_code": error_code}
        if "raw_reason_label" in self.mut:
            # MUTATION (AC4): leak the raw (uncurated) reason as the label value.
            labels["error_code"] = wi_id  # stand-in for a free-form string value
        if "label_work_item_id" in self.mut:
            # MUTATION (AC5): promote a forbidden identifier to a label key.
            labels["work_item.id"] = wi_id
        self.label_keys.update(labels.keys())
        return labels

    def enter(self, error_code, wi_id, run_id):
        labels = self._emit_labels(error_code, wi_id)
        code = labels.get("error_code", error_code)
        self.values[code] = self.values.get(code, 0) + 1
        if "drop_exemplar" not in self.mut:  # MUTATION (AC5): drop the trace-join exemplar
            self.exemplars.setdefault(code, []).append({"work_item.id": wi_id, "run.id": run_id})

    def clear(self, error_code, wi_id, run_id):
        if "counter_not_gauge" in self.mut:
            return  # MUTATION (AC1): a counter never decrements — resolved block lingers.
        labels = self._emit_labels(error_code, wi_id)
        code = labels.get("error_code", error_code)
        self.values[code] = self.values.get(code, 0) - 1


class WorkItem:
    def __init__(self, wi_id, run_id):
        self.id, self.run_id = wi_id, run_id
        self.blocked_reason = None  # durable coord state — the source of truth.

    def block(self, reason, gauge):
        self.blocked_reason = reason
        gauge.enter(curate(reason), self.id, self.run_id)

    def unblock(self, gauge):
        reason = self.blocked_reason
        self.blocked_reason = None
        gauge.clear(curate(reason), self.id, self.run_id)

    def claimable(self, gauge, mut):
        """Enforcement: reads ONLY durable coord state (AC2)... unless mutated."""
        if "enforce_via_gauge" in mut:
            # MUTATION (AC2): gate claim on the OBSERVATION, not the condition.
            return sum(gauge.values.values()) == 0
        # needs_approval releases the claim (arch §6.3); otherwise blocked==not-claimable.
        return self.blocked_reason is None


def cardinality_ok(gauge):
    """AC4/AC5: every emitted label key is allowlisted AND every value is curated."""
    if not gauge.label_keys <= ALLOWED_LABEL_KEYS:
        return False
    if gauge.label_keys & FORBIDDEN_AS_LABEL:
        return False
    return set(gauge.values.keys()) <= CURATED  # no raw string leaked as a value


def run_scenario(mut):
    """Drive the modelled blocked condition; return observable facts for assertions."""
    g_on = Gauge(mut)
    a = WorkItem("wi-a", "run-a")   # will block on approval, then resolve
    b = WorkItem("wi-b", "run-b")   # will block on a dependency, stays blocked
    c = WorkItem("wi-c", "run-c")   # will block on an UNCURATED reason

    a.block("needs_approval", g_on)
    b.block("blocked_by_dep", g_on)
    c.block("waiting_on_vendor", g_on)     # uncurated -> must land in `other`
    claim_on = {w.id: w.claimable(g_on, mut) for w in (a, b, c)}
    a.unblock(g_on)                        # approval granted -> gauge must decrement

    # Re-run claimability with the exporter UNSET (a no-recording gauge, AC2/AC6).
    g_off = Gauge(mut)  # never emitted into; enforcement must not depend on it
    a2 = WorkItem("wi-a", "run-a"); a2.block("needs_approval", None) if False else None
    # rebuild the same durable state without touching a gauge:
    a2.blocked_reason, b2, c2 = None, WorkItem("wi-b", "run-b"), WorkItem("wi-c", "run-c")
    a2.blocked_reason = "needs_approval"; b2.blocked_reason = "blocked_by_dep"
    c2.blocked_reason = "waiting_on_vendor"
    claim_off = {w.id: w.claimable(g_off, mut) for w in (a2, b2, c2)}

    return {
        "gauge": g_on,
        "settled": {k: v for k, v in g_on.values.items()},
        "claim_on": claim_on,
        "claim_off": claim_off,
    }


def assert_clean(r):
    """The GREEN baseline — all invariants hold on the un-mutated model."""
    g = r["gauge"]
    # AC1: resolved needs_approval decremented to 0; dep + other still up.
    assert g.values.get("needs_approval", 0) == 0, "AC1: resolved block did not clear"
    assert g.values.get("blocked_by_dep") == 1, "AC1: live block miscounted"
    assert g.values.get("other") == 1, "AC3/AC4: uncurated block not observed in `other`"
    # AC2: claimability identical exporter on vs off.
    assert r["claim_on"] == r["claim_off"], "AC2: claimability differs with gauge on/off"
    # AC2: an approval-blocked item is not claimable; a plain-blocked item is not either.
    assert r["claim_on"]["wi-a"] is False and r["claim_on"]["wi-b"] is False
    # AC5/AC4: label discipline + curated values only.
    assert cardinality_ok(g), "AC5: forbidden label key or raw value leaked"
    assert "other" in g.exemplars and g.exemplars["other"], "AC5: exemplar join lost"
    assert g.exemplars["other"][0]["work_item.id"] == "wi-c"


MUTATIONS = {
    "counter_not_gauge": "AC1: gauge never decrements (treated as a counter)",
    "enforce_via_gauge": "AC2: claim gated on the gauge (observation drives enforcement)",
    "raw_reason_label": "AC4: raw blocked_reason leaked as the label value",
    "label_work_item_id": "AC5: work_item.id promoted to a metric label",
    "drop_exemplar": "AC5: trace-join exemplar dropped",
}


def mutation_detected(mut_name):
    """A mutation is 'detected' iff assert_clean would now FAIL (the check turns RED)."""
    try:
        assert_clean(run_scenario({mut_name}))
        return False
    except AssertionError:
        return True


def main():
    failures = []

    # 1) GREEN baseline: the clean model satisfies every invariant.
    try:
        assert_clean(run_scenario(set()))
        print("OK   baseline GREEN — up/down gauge, observe-only, curated+`other`, exemplar-joined")
    except AssertionError as e:
        failures.append(f"baseline not GREEN: {e}")

    # 2) Each mutation must be DETECTED (turn the check RED) — the teeth.
    for mut_name, desc in MUTATIONS.items():
        if mutation_detected(mut_name):
            print(f"OK   mutation caught — {desc}")
        else:
            failures.append(f"mutation NOT caught ({mut_name}): {desc}")

    if failures:
        print("\nFAIL:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)
    print("\nAll invariants falsifiable and held: 13.3 blocked-gauge check GREEN.")


if __name__ == "__main__":
    main()
