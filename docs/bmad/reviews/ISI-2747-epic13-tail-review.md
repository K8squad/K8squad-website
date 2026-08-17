# ISI-2747 — Code Review: Epic 13 tail (13.4 metering, 13.6 cardinality CI)

**Reviewer:** Amelia (Code Reviewer) · **Date:** 2026-08-17 · **Verdict: APPROVE (both)**

Scope: review-and-land the two `in_review` Epic 13 stories (no active reviewer, outside PM
authorization boundary) per board directive. Self-hosted runners online → bench/CI lanes run.

## Artifacts under review

| Story | Docs | Bench (CI lane) |
|---|---|---|
| 13.4 ISI-2236 | `docs/bmad/stories/13-4-token-cost-consumption-metering.md` | `docs/bmad/spikes/bench/token-metering-check.py` |
| 13.6 ISI-2238 | `docs/bmad/stories/13-6-cardinality-budget-ci-check.md` | `cardinality-lint.py` + `cardinality-budget-check.py` + `cardinality-allowlist.txt` |

## Review layers

**Acceptance Auditor.** Every AC maps to bench coverage:
- 13.4: AC1 signal-shape=`ksquad.agent.tokens{runtime,direction}` (both §5.6-bounded); AC2 observe-not-enforce (§5.9 fit byte-identical exporter on/off); AC3 direction fidelity; AC4 best-effort/no-fabricate; AC5 per-principal+per-ticket via exemplars-never-labels; AC6 no bespoke ledger (dashboard total IS the OTel rollup); AC7 cost=backend rollup not instrument; AC8 noop-on-unset. → `token-metering-check.py` exit 0, 7 mutations RED.
- 13.6: AC1 greps metric label keys vs §5.6 allowlist; AC2 fail-build exit 1 `file:line:[CODE]`; AC3 explicit PII/fingerprint failures (OBS-9/OBS-11); AC4 high-card dims ride free as resource/exemplar/span attrs (the crux); AC5 obs-as-code allowlist file; AC6 differential-falsification bench. → both benches exit 0, 9 mutations RED.

**Blind Hunter / Edge Case Hunter — live adversarial checks (not just trusting bench self-report):**
- Injected `counter.Add(..., metric.WithAttributes(attribute.String("run.id", …)))` → lint FIRES `[OBS-9] metric label 'run.id'`, exit 1. ✅ teeth.
- Same `run.id` as a `SetAttributes` span attr in the same file → NOT flagged. ✅ two-sided; the §1.1 correlation the plan REQUIRES is preserved.
- `cardinality-lint.py .` on the whole repo → exit 0 (vacuous pass; k8squad has zero OTel instrumentation yet — gate armed for when 13.1/13.2 labels land). ✅ expected.

**Allowlist diff (working-tree):** comment-only clarification of the already-`ALLOW`ed `error_code`
curated enum (Story 13.3 / §15). No new ALLOW/DENY rule. Benign — benches stay GREEN.

## Findings

None blocking. No CHANGES. `token-metering-check.py`, `cardinality-budget-check.py`, and
`cardinality-lint.py` all exit 0; lint proven two-sided by live injection.

## Boundary note (not a defect)

13.6 delivers the check+teeth+allowlist. Wiring `cardinality-lint` as a **required** `ci.yml`
check-run is owned by **14.7 (ISI-2157)** — out of scope here. Story ships a drop-in ci.yml step.

## Disposition

APPROVE both → 13.4 ISI-2236 `done`, 13.6 ISI-2238 `done`. Clears Epic 13 (ISI-2185) tail for
umbrella close.
