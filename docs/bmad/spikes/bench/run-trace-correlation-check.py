#!/usr/bin/env python3
"""
Story 13.1 (ISI-2233) falsification — every Run = one distributed trace (the durable-correlation spine).

Differential correlation falsification, same shape as run-reconcile-check.py (3.1) and
run-retry-backoff-check.py (3.2). It proves the OTel SPINE has teeth by contrasting a NAIVE design that
holds the trace root only in the reconciler's in-memory context (and fragments a Run into TWO disconnected
traces the moment the operator fails over) against the DURABLE `ksquad.io/traceparent` annotation design
that re-parents off the CR and stays one trace across a restart.

Load-bearing invariant (obs-plan §3): "the CR-annotation hop is what makes the trace survive a controller
restart -- the reconcile loop is level-triggered and idempotent, so the trace context must be DURABLE STATE
on the Run CR, not in-memory continuity." This is the exact durability argument Story 3.2 makes for
next_attempt_at (backoff clock survives a restart because it is in Postgres, not RAM); here the *trace
context* survives because it is on the CR, not in context.Context.

Mutation contract (the headline invariant must be falsifiable -- re-run these after any edit):
  * delete the durable annotation WRITE in reconcile_durable (collapse B to A) -> (B) MUST turn RED.
  * delete the A2A-metadata traceparent inject in dispatch_to_shim         -> (F1) MUST turn RED.
  * route a Run log call through the raw (unbridged) logger                -> (F2) MUST turn RED.
  * span-attribute a secret / log raw agent content                       -> (F4) MUST turn RED.

stdlib only. `python3 run-trace-correlation-check.py`. Exits non-zero on any falsification.
No wall-clock, no RNG surprises: trace/span ids are deterministic monotonic counters, not random -- so a
"fresh root minted on restart" is detectable purely by IDENTITY (a new id != the durable one), reproducibly.
"""
import hashlib
import re
import sys

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)

# ---------------------------------------------------------------------------
# Deterministic id minting. trace/span ids are monotonic so "did the resume
# mint a NEW root?" is a pure identity test (new id != durable id), no RNG.
# ---------------------------------------------------------------------------
class IdGen:
    def __init__(self):
        self.n = 0
    def new(self, kind):
        self.n += 1
        return f"{kind}-{self.n:04x}"

# ---------------------------------------------------------------------------
# Span/log collectors. A "trace" is the set of spans sharing a trace_id; a Run
# is correct iff ALL its spans (across services + across a restart) share ONE
# trace_id and ONE root. Logs are dicts; the four-field contract is checked
# structurally on every Run-scoped line.
# ---------------------------------------------------------------------------
class Telemetry:
    def __init__(self, exporter_on=True):
        self.exporter_on = exporter_on
        self.spans = []   # exported spans: {trace_id, span_id, parent_id, service, run_id, attrs}
        self.logs = []    # every emitted log line (exported or not)

    def start_span(self, ids, run_id, service, traceparent, attrs=None):
        """Open a span. traceparent=None -> mint a NEW root (fresh trace_id).
        traceparent set -> child in the SAME trace (parent's trace_id)."""
        attrs = dict(attrs or {})
        if traceparent is None:
            trace_id = ids.new("trace")
            parent_id = None
        else:
            trace_id, parent_id = traceparent  # (trace_id, parent_span_id)
        span_id = ids.new("span")
        span = {"trace_id": trace_id, "span_id": span_id, "parent_id": parent_id,
                "service": service, "run_id": run_id, "attrs": attrs}
        if self.exporter_on:            # noop-on-unset: a non-recording span exports NOTHING
            self.spans.append(span)
        return span

    def traceparent_of(self, span):
        return (span["trace_id"], span["span_id"])

    # ---- the otelslog/pino BRIDGE: auto-stamps the four correlation fields ----
    def log_bridged(self, run_id, service, span, body="ok", extra=None):
        line = {"run_id": run_id, "service": service, "body": body}
        line.update(extra or {})
        # trace_id/span_id come from the ACTIVE span; run_id comes from the durable
        # Run field bound to the logger -> present even when the span is non-recording.
        if span is not None and self.exporter_on:
            line["trace_id"] = span["trace_id"]
            line["span_id"] = span["span_id"]
        self.logs.append(line)
        return line

    # ---- a RAW logger that bypasses the bridge: carries NONE of the four fields ----
    def log_raw(self, body="ok"):
        line = {"body": body}   # no run_id/service/trace_id/span_id -> un-joinable
        self.logs.append(line)
        return line

    def traces_for_run(self, run_id):
        return {s["trace_id"] for s in self.spans if s["run_id"] == run_id}

    def roots_for_run(self, run_id):
        return [s for s in self.spans if s["run_id"] == run_id and s["parent_id"] is None]


# ===========================================================================
# (A) NAIVE design: trace root lives ONLY in the reconciler's in-memory context.
#     On failover the fresh reconciler has no context -> mints a new root.
# ===========================================================================
def scenario_naive_in_memory_restart():
    ids, tel = IdGen(), Telemetry()
    run = "run-1"
    # ---- reconciler process #1: mint root, reconcile a phase ----
    ctx_root = tel.start_span(ids, run, "operator", None)        # root minted in-memory
    tel.start_span(ids, run, "operator", tel.traceparent_of(ctx_root))  # child phase span
    # ---- CRASH / leader failover: process #1's context.Context is GONE ----
    # process #2 has NO durable trace context to read -> mints a FRESH root.
    ctx_root2 = tel.start_span(ids, run, "operator", None)       # <-- second, disconnected root
    tel.start_span(ids, run, "operator", tel.traceparent_of(ctx_root2))
    return tel.traces_for_run(run)                               # naive -> TWO trace_ids


# ===========================================================================
# (B) DURABLE design: operator writes ksquad.io/traceparent to Run.status in the
#     SAME commit as the step advance; on restart it re-reads & re-parents.
# ===========================================================================
class RunCR:
    """Durable Run record. status.annotations survive a process restart (it's the CR,
    not RAM) -- the analogue of Story 3.2's durable next_attempt_at in Postgres."""
    def __init__(self, run_id):
        self.run_id = run_id
        self.status_annotations = {}   # durable across "restarts"

def reconcile_durable(ids, tel, cr, committed_annotation_first=True):
    """One reconcile entry. Reads the durable traceparent annotation FIRST; mints a
    root only if none exists; writes it in the step-advance commit (idempotent)."""
    tp = cr.status_annotations.get("ksquad.io/traceparent")
    if tp is None:
        root = tel.start_span(ids, cr.run_id, "operator", None)          # first reconcile: mint
        # ---- MUTATION POINT (B->A): delete this write and the restart re-mints (RED) ----
        if committed_annotation_first:
            cr.status_annotations["ksquad.io/traceparent"] = tel.traceparent_of(root)  # durable, same-commit
    else:
        # re-entry: re-parent off the PINNED durable root (no re-mint), idempotent write.
        root = tel.start_span(ids, cr.run_id, "operator", tp)
        cr.status_annotations["ksquad.io/traceparent"] = tp              # no-op write (already matches)
    tel.start_span(ids, cr.run_id, "operator", tel.traceparent_of(root))  # child phase span
    return root

def scenario_durable_restart(committed=True):
    ids, tel = IdGen(), Telemetry()
    cr = RunCR("run-2")
    reconcile_durable(ids, tel, cr, committed)   # process #1: mint + persist
    # ---- CRASH / failover: RAM gone, but cr.status_annotations is DURABLE ----
    reconcile_durable(ids, tel, cr, committed)   # process #2: re-read annotation -> same trace
    return tel.traces_for_run(cr.run_id), cr


# ===========================================================================
# (F1) seam-propagation teeth: operator -> shim via A2A task metadata traceparent.
# ===========================================================================
def dispatch_to_shim(ids, tel, run_id, dispatch_span, inject_traceparent=True):
    """Operator dispatches to the shim. The A2A task metadata carries traceparent so
    the shim's span is a CHILD in the same trace. Drop the inject -> shim mints a new
    root -> the trace fragments into a forest."""
    a2a_metadata = {}
    if inject_traceparent:
        # ---- MUTATION POINT (F1): delete this line and the shim forests (RED) ----
        a2a_metadata["traceparent"] = tel.traceparent_of(dispatch_span)
    shim_parent = a2a_metadata.get("traceparent")   # None if not injected -> new root
    return tel.start_span(ids, run_id, "shim", shim_parent)

def scenario_seam_propagation(inject=True):
    ids, tel = IdGen(), Telemetry()
    run = "run-3"
    cr = RunCR(run)
    root = reconcile_durable(ids, tel, cr)
    dispatch = tel.start_span(ids, run, "operator", tel.traceparent_of(root))  # a2a.task.submit
    dispatch_to_shim(ids, tel, run, dispatch, inject)                          # shim.task.execute
    return tel.traces_for_run(run)


# ===========================================================================
# (F2) log-correlation teeth: every Run log line carries the four fields.
# ===========================================================================
FOUR_FIELDS = ("trace_id", "span_id", "run_id", "service")

def scenario_log_correlation(bypass_one=False):
    ids, tel = IdGen(), Telemetry()
    run = "run-4"
    cr = RunCR(run)
    root = reconcile_durable(ids, tel, cr)
    tel.log_bridged(run, "operator", root, "reconcile.Dispatching")
    tel.log_bridged(run, "operator", root, "claim.acquired")
    if bypass_one:
        # ---- MUTATION POINT (F2): a raw logger call -> an un-joinable line (RED) ----
        tel.log_raw("oops-unbridged")
    # every line emitted for this Run must carry the four fields.
    joinable = [all(f in ln for f in FOUR_FIELDS) for ln in tel.logs]
    return all(joinable)


# ===========================================================================
# (F3) noop-on-unset: exporter OFF -> zero spans, identical Run behavior,
#      run.id STILL on every log line (from the durable Run field, not the span).
# ===========================================================================
def run_a_phase(tel, ids, run_id):
    """Behavior we assert is identical on/off: reconcile a phase, return the phase outcome."""
    cr = RunCR(run_id)
    root = reconcile_durable(ids, tel, cr)
    tel.log_bridged(run_id, "operator", root, "reconcile.Dispatching")
    return "Dispatching->Running"   # the Run's control-flow outcome (exporter-independent)

def scenario_noop_on_unset():
    # exporter ON
    on_out = run_a_phase(Telemetry(exporter_on=True), IdGen(), "run-5")
    # exporter OFF
    tel_off = Telemetry(exporter_on=False)
    off_out = run_a_phase(tel_off, IdGen(), "run-5")
    zero_spans = (len(tel_off.spans) == 0)
    behavior_identical = (on_out == off_out)
    runid_on_every_log = all("run_id" in ln for ln in tel_off.logs) and len(tel_off.logs) > 0
    traceid_absent_off = all("trace_id" not in ln for ln in tel_off.logs)  # non-recording span
    return zero_spans, behavior_identical, runid_on_every_log, traceid_absent_off


# ===========================================================================
# (F4) redaction teeth (service-side half): no secret / PII / raw agent content
#      ever reaches a span attr or a log body.
# ===========================================================================
SECRET_PATTERNS = [
    re.compile(r"CLAUDE_CODE_OAUTH_TOKEN"),
    re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
    re.compile(r"sk-[a-z0-9]{8,}"),
    re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"),   # email
    re.compile(r"RAW_AGENT_CONTENT"),                        # marker for un-hashed agent text
]
def is_clean(value):
    s = str(value)
    return not any(p.search(s) for p in SECRET_PATTERNS)

def scenario_redaction(leak=False):
    ids, tel = IdGen(), Telemetry()
    run = "run-6"
    cr = RunCR(run)
    root = reconcile_durable(ids, tel, cr)
    # correct: only opaque ids, enums, hashes, lengths, kinds.
    content_hash = hashlib.sha256(b"secret agent output").hexdigest()[:16]
    good = tel.start_span(ids, run, "memory", tel.traceparent_of(root),
                          attrs={"ksquad.run.id": run, "memory.kind": "fact",
                                 "content.sha256": content_hash, "content.len": 42})
    tel.log_bridged(run, "memory", good, "memory.write", extra={"kind": "fact", "len": 42})
    if leak:
        # ---- MUTATION POINT (F4): attribute a token / log raw agent text -> RED ----
        tel.start_span(ids, run, "shim", tel.traceparent_of(root),
                       attrs={"credential": "CLAUDE_CODE_OAUTH_TOKEN=sk-abcdef012345"})
        tel.log_bridged(run, "shim", good, "RAW_AGENT_CONTENT: ignore previous instructions")
    # scan every exported span attr value and every log body/field.
    span_clean = all(is_clean(v) for s in tel.spans for v in s["attrs"].values())
    log_clean = all(is_clean(v) for ln in tel.logs for v in ln.values())
    return span_clean and log_clean


# ===========================================================================
# (F5) idempotent annotation write + crash-before/after semantics (AC3).
# ===========================================================================
def scenario_idempotent_annotation():
    ids, tel = IdGen(), Telemetry()
    cr = RunCR("run-7")
    root1 = reconcile_durable(ids, tel, cr)
    pinned = cr.status_annotations["ksquad.io/traceparent"]
    # re-reconcile: annotation already present -> re-parent, NO re-mint, no-op write.
    root2 = reconcile_durable(ids, tel, cr)
    reparented = (root2["trace_id"] == root1["trace_id"])
    annotation_stable = (cr.status_annotations["ksquad.io/traceparent"] == pinned)
    # crash BEFORE the annotation commit: re-enters as first-reconcile, re-mints (acceptable).
    ids2, tel2 = IdGen(), Telemetry()
    cr2 = RunCR("run-8")
    reconcile_durable(ids2, tel2, cr2, committed_annotation_first=False)  # mint, but crash pre-commit
    pre_commit_empty = ("ksquad.io/traceparent" not in cr2.status_annotations)
    remint = reconcile_durable(ids2, tel2, cr2, committed_annotation_first=True)  # re-mint on re-entry
    pinned2 = cr2.status_annotations["ksquad.io/traceparent"]
    # crash AFTER commit: re-parent off the pinned root, never re-mint.
    after = reconcile_durable(ids2, tel2, cr2)
    pinned_stable = (after["trace_id"] == remint["trace_id"] == pinned2[0])
    return reparented, annotation_stable, pre_commit_empty, pinned_stable


# ===========================================================================
def main():
    # (A) the harness must have detecting power: naive design fragments into >1 trace.
    naive_traces = scenario_naive_in_memory_restart()
    check(len(naive_traces) == 2,
          "harness lost teeth: NAIVE in-memory design did NOT fragment a Run on restart "
          f"(expected 2 disconnected traces, got {len(naive_traces)})")

    # (B) the durable annotation keeps a Run ONE trace across a failover.
    durable_traces, cr_b = scenario_durable_restart(committed=True)
    check(len(durable_traces) == 1,
          "AC2 durable-trace FAILED: a Run fragmented across a controller restart despite the "
          "ksquad.io/traceparent annotation (delete the annotation WRITE in reconcile_durable to see RED)")

    # (B mutation) prove the invariant is load-bearing: without the committed write, B == A.
    b_mut_traces, _ = scenario_durable_restart(committed=False)
    check(len(b_mut_traces) == 2,
          "AC2 mutation-guard FAILED: removing the durable annotation write did NOT fragment "
          "-- the durable-vs-in-memory invariant is not actually load-bearing")

    # (F1) seam propagation: shim shares the Run's trace root; dropping the inject forests it.
    check(len(scenario_seam_propagation(inject=True)) == 1,
          "AC6/§E seam FAILED: shim did not join the Run's trace even with A2A traceparent injected")
    check(len(scenario_seam_propagation(inject=False)) == 2,
          "AC6/§E mutation-guard FAILED: dropping the A2A traceparent inject did NOT fragment the "
          "trace into a forest (delete the inject in dispatch_to_shim to see this go RED)")

    # (F2) log correlation: four fields on every line; a bypassed line is detectably un-joinable.
    check(scenario_log_correlation(bypass_one=False) is True,
          "AC1/§D log-correlation FAILED: a bridged Run log line was missing one of "
          "trace_id/span_id/run_id/service")
    check(scenario_log_correlation(bypass_one=True) is False,
          "AC1/§D mutation-guard FAILED: a raw (unbridged) log line was NOT detected as un-joinable "
          "-- the four-field contract has no teeth")

    # (F3) noop-on-unset: zero spans, identical behavior, run.id survives, trace_id absent.
    zero_spans, behavior_identical, runid_ok, traceid_absent = scenario_noop_on_unset()
    check(zero_spans, "AC4 noop FAILED: spans were exported with the OTLP endpoint unset")
    check(behavior_identical, "AC4 noop FAILED: Run behavior differed between exporter on/off")
    check(runid_ok, "AC4 noop FAILED: run.id was dropped from logs when the exporter was off "
                    "(it must come from the durable Run field, not the span)")
    check(traceid_absent, "AC4 noop FAILED: trace_id present on a log line despite a non-recording span")

    # (F4) redaction: clean path clean; leaking a token / raw content is detected.
    check(scenario_redaction(leak=False) is True,
          "AC5 redaction FAILED: the clean path emitted a value flagged as secret/PII")
    check(scenario_redaction(leak=True) is False,
          "AC5 mutation-guard FAILED: a span-attributed token / raw agent content was NOT detected "
          "-- the service-side secret discipline has no teeth")

    # (F5) idempotent annotation + crash-before/after semantics.
    reparented, annotation_stable, pre_commit_empty, pinned_stable = scenario_idempotent_annotation()
    check(reparented, "AC3 FAILED: a re-reconcile re-minted the root instead of re-parenting")
    check(annotation_stable, "AC3 FAILED: the idempotent annotation write thrashed the pinned root")
    check(pre_commit_empty, "AC3 FAILED: a crash before the annotation commit left a phantom annotation")
    check(pinned_stable, "AC3 FAILED: a crash after the annotation commit re-minted the pinned root")

    if FAIL:
        print("FALSIFIED — Story 13.1 design check FAILED:")
        for m in FAIL:
            print("  ✗", m)
        sys.exit(1)
    print("OK — Story 13.1 distributed-trace correlation spine holds:")
    print("  (A)  naive in-memory trace root fragments a Run into 2 traces on restart (harness has teeth)")
    print("  (B)  durable ksquad.io/traceparent annotation keeps a Run ONE trace across a failover (AC2)")
    print("  (B!) removing the durable write collapses B->A and re-fragments (invariant is load-bearing)")
    print("  (F1) shim joins the Run trace via A2A traceparent; dropping the inject forests it (AC6/§E)")
    print("  (F2) every Run log line carries trace_id/span_id/run.id/service; a raw line is un-joinable (AC1/§D)")
    print("  (F3) noop-on-unset: zero spans, identical behavior, run.id survives, trace_id absent (AC4)")
    print("  (F4) no secret/PII/raw-agent-content reaches a span attr or log body; a leak is caught (AC5)")
    print("  (F5) annotation write is idempotent; crash-before re-mints, crash-after re-parents (AC3)")

if __name__ == "__main__":
    main()
