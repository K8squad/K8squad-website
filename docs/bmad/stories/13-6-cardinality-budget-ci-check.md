# Story 13.6: Cardinality budget CI check — the label-discipline gate

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE ENFORCEMENT OF THE PLAN'S #1 LAW (obs-plan §1.2 / §5.6, §11 gate #1).**
> Every other Epic-13 story *obeys* the cardinality budget ("`run.id` is a trace/log dimension, never a
> metric label"); this story is the CI check that makes the budget **tested, not hoped for**. It greps the
> instrumentation for metric label keys, checks them against the **§5.6 allowlist**, and **fails the build**
> on any out-of-allowlist label — with the explicit build failure being a per-actor id (`run.id`,
> `work_item.id`, `principal.id`, **`user.id`**), a scope **name** (`team`/`project`), PII
> (username/email), or a privacy fingerprint (raw viewport width / User-Agent / device model). The
> load-bearing subtlety, and the thing that makes this a real check rather than a blunt grep, is the
> **metric-label-vs-correlation-axis boundary**: the budget constrains the *label* axis **only**. The very
> same `run.id`/`user.id` on a **span attribute, a log field, a metric exemplar, or a resource attribute**
> is not merely tolerated — it is **required** by §1.1 correlation, and the check MUST stay silent on it.
> A lint that flags those ids everywhere is exactly as broken as one that flags them nowhere.

## ⚠️ Scope pin — this story enforces, it does not instrument (read first)

This story adds **zero** metrics and **zero** instrumentation. It ships one thing: the **cardinality-lint**
— a CI gate that reads the version-controlled §5.6 allowlist and scans source for metric label keys outside
it. The instruments it polices are authored by the other Epic-13 stories (§5.1 coord metrics / 13.2, Run +
warm-pool / 13.3–13.5, RBAC auth §16 / 13.10, console-RUM §18). **Story 14.7 owns the pipeline wiring** —
this story delivers the check + its allowlist + its falsification bench; 14.7 adds the `ci.yml` step and the
required-check name. The one-line boundary: **13.6 makes the label law enforceable; 14.7 makes CI run it;
every other Epic-13 story keeps its labels inside the law this gate encodes.**

| Concern | This story | Owned elsewhere |
|---|---|---|
| The cardinality-lint tool (scans Go + TS/JS metric emit sites; fails on out-of-allowlist label) | **✅ delivered** — `cardinality-lint.py` | — |
| The §5.6 allowlist as a version-controlled single source of truth (obs-as-code) | **✅ delivered** — `cardinality-allowlist.txt` | Human source stays obs-plan §5.6 (edit both together) |
| Teeth: planted forbidden labels fail; the same ids on span/exemplar/resource pass | **✅ the crux (AC2/AC4)** — `cardinality-budget-check.py` | — |
| Explicit build failure on `user.id`/username/email (OBS-9) and raw viewport/UA/fingerprint (OBS-11) | **✅ delivered (AC3)** | The PII/fingerprint dims themselves are forbidden at emit by §1.4/§18 (13.10/§18 stories) |
| Wiring the gate into the GitHub Actions pipeline as a required check | consumed | **Story 14.7** (ISI free-testing lane / component-matrix `ci.yml`) |
| The metric label enums the gate allows (each a bounded domain) | consumed | **§5.1/§16/§18 instruments** (13.2, 13.3–13.5, 13.10, §18) — they *obey* this gate |

## Story

As **the platform team**,
I want **the §5.6 cardinality budget enforced by a CI check that greps metric label keys against a
version-controlled allowlist and fails the build on any out-of-allowlist label — while leaving the same
high-cardinality dimensions untouched when they ride as resource attributes or exemplars**,
so that **label discipline can't silently rot: the moment anyone adds `run.id`, `work_item.id`,
`principal.id`, `user.id`, a team/project name, PII, or a device fingerprint as a metric label, the build
goes red with a precise file:line and reason — and the correlation model the plan requires (those same ids
on spans, logs, and exemplars) keeps working untouched.**

## Context & prerequisites (read first)

- **Observability plan:** `docs/bmad/04-observability-plan.md`
  - **§5.6 "Cardinality budget (the enforced label allowlist)"** — the authoritative allowlist this story
    mechanizes: the bounded label domains that MAY be labels, and the forbidden set (ids/names/PII) that may
    not. The machine mirror is `docs/bmad/spikes/bench/cardinality-allowlist.txt`.
  - **§1.2 "Cardinality is the enemy — the Run is a trace/log dimension, never a metric label."** — the law.
  - **§11 gate #1 "Cardinality lint"** — "grep instrumentation for metric label keys outside the §5.6
    allowlist → fail. Explicitly fails on `user.id`/`initiatedByUserId`/username/email (OBS-9) … and on raw
    viewport width / User-Agent / device-fingerprint (OBS-11)."
  - **§16.2** (RBAC — `user.id` never a label, exemplar only) and **§18** (console-RUM — bucketed not
    fingerprinted) — the two revisions that add the OBS-9 / OBS-11 explicit failures.
- **Epics:** `docs/bmad/04-epics-and-stories.md` row **13.6** ("cardinality budget enforced by a CI check …
  fails the build on any out-of-allowlist label"); wired by row **14.7** (component-matrix `ci.yml`); ISI
  parent **ISI-2157** (CI free-testing lane / cardinality CI check).
- **Sibling obs stories that OBEY this gate:** 13.1 (ISI-2233 run trace — exemplar target), 13.2 (ISI-2234
  coord metrics — asserts its own labels locally; this gate makes it repo-wide).

## Acceptance criteria

- **AC1 — the check exists and greps metric label keys vs the §5.6 allowlist.** `cardinality-lint.py`
  scans Go (`metric.WithAttributes(attribute.*("key", …))` on `.Add`/`.Record`/observer emits) and TS/JS
  (`counter.add`/`histogram.record`/`observableResult.observe` attribute-object keys), extracts every metric
  **label** key, and classifies it against `cardinality-allowlist.txt` (the machine mirror of §5.6). Bounded
  enums pass; anything else is a finding.
- **AC2 — it fails the build on any out-of-allowlist label.** Exit code 1 with `file:line: [CODE] metric
  label 'key': reason` for every violation. `run.id`/`work_item.id`/`principal.id` as a metric label are the
  canonical example from the epic and MUST fail (M1/M3).
- **AC3 — the explicit failures are explicit.** `user.id` / `initiatedByUserId` / username / email as a
  metric label fail with **OBS-9** (RBAC §16.2); raw viewport width / `user_agent` / device model as a
  metric label or console-RUM attribute fail with **OBS-11** (§18). Scope **names** (`team`/`project`) as a
  label fail (OBS-9 — they ride as resource attributes).
- **AC4 — high-cardinality dims ride free as resource attributes / exemplars (the crux).** The check MUST
  **NOT** fire when the same `run.id`/`user.id` appears on a `span.SetAttributes` / `resource.WithAttributes`
  / exemplar / log field. It constrains the label axis only; the correlation axis is untouched. (M9.)
- **AC5 — obs-as-code single source of truth.** The allowlist is a version-controlled file, not hard-coded
  in the scanner; §5.6 and the file are edited together and a drift is a review finding. The lint reads it at
  runtime (`--allowlist` overridable).
- **AC6 — tested, not hoped for.** `cardinality-budget-check.py` is a differential-falsification bench:
  a clean baseline is GREEN and nine mutations each turn it RED (per-actor ids, PII, fingerprints, novel
  ids, scope names as labels, a lint-weakening mutation, and an over-fire mutation). Weakening `classify()`
  or breaking the metric/span discriminator both flip it RED (verified by live mutation).

## Deliverables

- `docs/bmad/spikes/bench/cardinality-lint.py` — the CI gate (the tool). `python3 cardinality-lint.py [PATH…]`,
  exit 0/1/2. Scans Go + TS/JS metric emit sites only; distinguishes metric labels from span/resource attrs.
- `docs/bmad/spikes/bench/cardinality-allowlist.txt` — the machine mirror of §5.6 (ALLOW bounded enums +
  DENY forbidden keys with OBS-9/OBS-11 codes and reasons). The single source of truth the lint reads.
- `docs/bmad/spikes/bench/cardinality-budget-check.py` — the falsification bench (AC6). GREEN baseline +
  9 mutations. `python3 cardinality-budget-check.py`, exit non-zero on any falsification.

## Verification

```
python3 docs/bmad/spikes/bench/cardinality-budget-check.py   # → OK (baseline GREEN, all mutations RED)
python3 docs/bmad/spikes/bench/cardinality-lint.py <tree>    # → OK on clean tree; FAIL(1) once a bad label lands
```

Live mutation evidence (2026-08-14): weakening `classify()` to always-legal → bench RED (18 checks);
treating `span.SetAttributes` keys as metric labels → bench RED (baseline + M9 over-fire); restore → GREEN.

## Handoff → Story 14.7 (pipeline wiring)

14.7 wires this gate into `.github/workflows/ci.yml` as a required check on the `K8squad/K8squad` repo. The
skeleton leg **skips-with-reason** until Epic-13 instrumentation lands, then enforces (§10.4 check-run name,
e.g. `cardinality-lint`). Drop-in step (the tool + allowlist land in the source repo under `hack/`):

```yaml
  cardinality-lint:
    name: cardinality-lint
    runs-on: [self-hosted, linux, x64]     # homelab has no hosted runners — ubuntu-latest queue-hangs
                                           # (see stories/epic-14-ci-runner-constraints.md R1)
    steps:
      - uses: actions/checkout@v4
      - name: Enforce §5.6 metric-label cardinality budget
        run: python3 hack/cardinality-lint.py internal shims console
```

Until the source-repo copy lands, the check is runnable today from the BMAD workspace against any tree:
`python3 docs/bmad/spikes/bench/cardinality-lint.py /path/to/k8squad`.
