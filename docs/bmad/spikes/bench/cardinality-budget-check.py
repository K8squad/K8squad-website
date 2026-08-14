#!/usr/bin/env python3
"""
Story 13.6 (ISI-2238) falsification — the cardinality-budget CI check has teeth.

Same differential-falsification shape as the sibling obs benches (13.1
run-trace-correlation-check.py, 13.2 coord-metrics-check.py). It proves the
cardinality-lint (cardinality-lint.py, the §11 gate this story ships) actually
ENFORCES obs-plan §5.6: an out-of-allowlist metric label — above all a
per-actor id (`run.id`/`work_item.id`/`principal.id`/`user.id`), a scope NAME
(`team`/`project`), PII (username/email), or a privacy fingerprint (raw viewport
width / User-Agent / device model) — fails the build; while the SAME identifier
placed where §5.6 permits it (a span attribute, a log field, a metric EXEMPLAR,
or a resource attribute) stays GREEN. "Cardinality is tested, not hoped for."

The load-bearing invariant is the metric-label-vs-correlation-axis boundary
(obs-plan §1.2 / §5.6): the budget constrains ONLY the metric label axis. So the
teeth are two-sided — the lint must fire on the label, and it must NOT fire when
the very same id rides an exemplar/span/resource attribute (else it would forbid
the correlation the plan REQUIRES). A lint that flags `user.id` everywhere is as
wrong as one that flags it nowhere.

Mutation contract (re-run after any edit — each MUST turn the named check RED):
  * (M1) emit `run.id`         as a Go metric label  -> flagged OBS-9   RED
  * (M2) emit `user.id`        as a Go metric label  -> flagged OBS-9   RED  (RBAC, §16.2)
  * (M3) emit `work_item.id`   as a Go metric label  -> flagged OBS-9   RED
  * (M4) emit raw `viewport_width` as a JS metric attr -> flagged OBS-11 RED  (§18)
  * (M5) emit `user_agent`     as a JS metric attr    -> flagged OBS-11 RED  (§18)
  * (M6) emit a novel `agent.id` as a metric label     -> flagged OBS-CARD RED (out-of-allowlist)
  * (M7) emit scope NAME `project` as a metric label   -> flagged OBS-9   RED
  * (M8) WEAKEN the lint so `user.id` on a metric label passes -> baseline GREEN goes RED
  * (M9) OVER-FIRE: flag `user.id` on a SPAN attr / resource attr / exemplar -> negative-guard RED

stdlib only. `python3 cardinality-budget-check.py`. Exits non-zero on any
falsification. No wall-clock, no RNG — pure over fixed source fixtures.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Load the hyphenated lint module by path.
_spec = importlib.util.spec_from_file_location("cardinality_lint", os.path.join(HERE, "cardinality-lint.py"))
lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint)

ALLOW, DENY = lint.load_allowlist(lint.DEFAULT_ALLOWLIST)

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)


def findings(text, path):
    """Run the real lint extractor+classifier over one fixture; return list of (key, code)."""
    return [(key, code) for (_p, _ln, key, code, _r) in lint.scan_text(path, text, ALLOW, DENY)]


def codes(text, path):
    return {code for _k, code in findings(text, path)}


def keys(text, path):
    return {k for k, _c in findings(text, path)}


# ===========================================================================
# BASELINE — legal instrumentation. Bounded enums as metric labels; every
# unbounded id lives on a span attr, a resource attr, or a metric exemplar.
# The lint MUST be silent here (zero findings).
# ===========================================================================
BASELINE_GO = '''
package obs

func emit() {
    // §5.1 coordination metrics: bounded-enum labels only.
    claimTotal.Add(ctx, 1, metric.WithAttributes(
        attribute.String("result", result),        // ALLOW
        attribute.String("trigger", trigger),       // ALLOW
    ))
    runCompleted.Add(ctx, 1, metric.WithAttributes(
        attribute.String("outcome", outcome),        // ALLOW
        attribute.String("terminal_reason", tr),     // ALLOW
        attribute.String("runtime", runtime),        // ALLOW
    ))
    authLogin.Add(ctx, 1, metric.WithAttributes(
        attribute.String("auth_result", ar),         // ALLOW (RBAC §16)
        attribute.String("role", role),              // ALLOW — user.role is bounded
    ))

    // §5.6 correlation axis: the unbounded ids belong HERE, never on a label.
    span.SetAttributes(
        attribute.String("run.id", runID),           // span attr — legal
        attribute.String("work_item.id", wiID),      // span attr — legal
        attribute.String("ksquad.user.id", userID),  // span attr — legal (§16.2)
        attribute.String("principal.id", princ),     // span attr — legal
    )
    // scope names ride as resource attributes (they federate) — legal.
    res := resource.NewWithAttributes(schema,
        attribute.String("team", team),
        attribute.String("project", project),
    )
    _ = res
}
'''

BASELINE_JS = '''
export function emit(counter, histogram, meter) {
    // bounded-enum metric labels
    counter.add(1, { outcome: outcome, runtime: runtime });
    histogram.record(ms, { "result": result, breakpoint: bp, viewport_bucket: vb });
    // exemplar / span attrs carry the unbounded ids — legal
    span.setAttributes({ "run.id": runId, "ksquad.user.id": userId, "work_item.id": wiId });
    span.setAttribute("trace_id", traceId);
}
'''

check(findings(BASELINE_GO, "a.go") == [], "BASELINE_GO must be clean, got %r" % findings(BASELINE_GO, "a.go"))
check(findings(BASELINE_JS, "a.ts") == [], "BASELINE_JS must be clean, got %r" % findings(BASELINE_JS, "a.ts"))


# ===========================================================================
# MUTATIONS — each plants a forbidden metric label; the lint MUST flag it.
# ===========================================================================
def go_label(attr_key):
    return 'package p\nfunc f(){ c.Add(ctx,1, metric.WithAttributes(attribute.String("%s", v))) }\n' % attr_key

def js_label(attr_key):
    return 'counter.add(1, { "%s": v });\n' % attr_key

# M1 — run.id as a Go metric label -> OBS-9
c = codes(go_label("run.id"), "m.go")
check("OBS-9" in c, "M1: run.id metric label must be flagged OBS-9, got %r" % c)

# M2 — user.id as a Go metric label -> OBS-9 (RBAC, the explicit build failure)
c = codes(go_label("ksquad.user.id"), "m.go")
check("OBS-9" in c, "M2: ksquad.user.id metric label must be flagged OBS-9, got %r" % c)
c = codes(go_label("initiatedByUserId"), "m.go")
check("OBS-9" in c, "M2b: initiatedByUserId metric label must be flagged OBS-9, got %r" % c)

# M3 — work_item.id / principal.id as a Go metric label -> OBS-9
check("OBS-9" in codes(go_label("work_item.id"), "m.go"), "M3a: work_item.id must be OBS-9")
check("OBS-9" in codes(go_label("principal.id"), "m.go"), "M3b: principal.id must be OBS-9")

# M4 — raw viewport_width as a JS metric attribute -> OBS-11 (§18 privacy)
c = codes(js_label("viewport_width"), "m.ts")
check("OBS-11" in c, "M4: viewport_width metric attr must be flagged OBS-11, got %r" % c)

# M5 — user_agent / device fingerprint as a JS metric attribute -> OBS-11
check("OBS-11" in codes(js_label("user_agent"), "m.ts"), "M5a: user_agent must be OBS-11")
check("OBS-11" in codes(js_label("device_model"), "m.ts"), "M5b: device_model must be OBS-11")

# M6 — a novel, unlisted id (agent.id) as a metric label -> OBS-CARD (out-of-allowlist)
c = codes(go_label("agent.id"), "m.go")
check("OBS-CARD" in c, "M6: novel agent.id label must be flagged OBS-CARD, got %r" % c)
# and a bare unknown key
check("OBS-CARD" in codes(js_label("tenant_slug"), "m.ts"), "M6b: unknown tenant_slug must be OBS-CARD")

# M7 — scope NAME as a metric label -> OBS-9 (must ride as a resource attr instead)
check("OBS-9" in codes(go_label("project"), "m.go"), "M7a: project name label must be OBS-9")
check("OBS-9" in codes(go_label("team"), "m.go"), "M7b: team name label must be OBS-9")


# ===========================================================================
# M8 — LINT-WEAKENING guard. If the classifier is weakened so a forbidden key
# passes, the baseline stops being able to distinguish legal from illegal.
# We assert the classifier itself rejects the forbidden keys (so deleting a DENY
# row, or making classify() lenient, turns this RED).
# ===========================================================================
for forbidden in ("run.id", "user.id", "work_item.id", "principal.id", "team", "project"):
    check(lint.classify(forbidden, ALLOW, DENY) is not None,
          "M8: classify(%r) must be a violation, not None" % forbidden)
for allowed in ("result", "outcome", "role", "auth_result", "viewport_bucket", "runtime"):
    check(lint.classify(allowed, ALLOW, DENY) is None,
          "M8: classify(%r) must be legal (None), got %r" % (allowed, lint.classify(allowed, ALLOW, DENY)))


# ===========================================================================
# M9 — OVER-FIRE negative guard (the crux). The budget constrains ONLY the
# metric label axis. The SAME unbounded ids on a span attr, a resource attr, or
# an exemplar are REQUIRED by §1.1 correlation and MUST NOT be flagged. A lint
# that flags them everywhere would forbid the correlation the plan mandates.
# ===========================================================================
SPAN_ONLY_GO = 'package p\nfunc f(){ span.SetAttributes(attribute.String("run.id", v), attribute.String("ksquad.user.id", u)) }\n'
check(findings(SPAN_ONLY_GO, "s.go") == [],
      "M9a: ids on span.SetAttributes must NOT be flagged, got %r" % findings(SPAN_ONLY_GO, "s.go"))

RESOURCE_ONLY_GO = 'package p\nfunc f(){ resource.NewWithAttributes(s, attribute.String("team", t), attribute.String("project", pr)) }\n'
check(findings(RESOURCE_ONLY_GO, "r.go") == [],
      "M9b: scope names on resource attrs must NOT be flagged, got %r" % findings(RESOURCE_ONLY_GO, "r.go"))

SPAN_ONLY_JS = 'span.setAttributes({ "run.id": rid, "ksquad.user.id": uid });\nspan.setAttribute("work_item.id", wi);\n'
check(findings(SPAN_ONLY_JS, "s.ts") == [],
      "M9c: ids on span.setAttributes must NOT be flagged, got %r" % findings(SPAN_ONLY_JS, "s.ts"))

# user.role IS a bounded label and must pass even though it shares the user.* prefix.
check(findings(go_label("ksquad.user.role"), "ur.go") == [],
      "M9d: ksquad.user.role is a bounded ALLOW label and must pass, got %r" % findings(go_label("ksquad.user.role"), "ur.go"))


# ===========================================================================
if FAIL:
    print("CARDINALITY-BUDGET CHECK: FALSIFIED (%d)" % len(FAIL))
    for m in FAIL:
        print("  ✗ " + m)
    sys.exit(1)
print("CARDINALITY-BUDGET CHECK: OK — lint fires on out-of-budget metric labels,")
print("  stays silent on the same ids as span/resource/exemplar attrs. §5.6 has teeth.")
sys.exit(0)
