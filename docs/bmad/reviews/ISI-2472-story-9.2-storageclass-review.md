# Code Review — Story 9.2: PVC storageClassName from values (ISI-2251)

**Reviewer:** Amelia (Code Reviewer) · **Issue:** ISI-2472 · **Date:** 2026-08-16
**Verdict:** ✅ **APPROVE** — all six ACs satisfied; bench green with teeth. One non-blocking bench-coverage nit (Low).

## Scope reviewed
- `docs/bmad/spikes/bench/helm-chart-isi2149/templates/postgres-cluster.yaml` (vendored k8squad@5e6442d)
- `.../templates/operator-config.yaml`
- `.../templates/nats.yaml` (PVC stamper, ISI-2253)
- `.../templates/_helpers.tpl` (`ksquad.storageClass.*`, `ksquad.validate`)
- `.../templates/service.yaml` (validate include site)
- `.../values.yaml` (storage block)
- `docs/bmad/spikes/bench/storage-class-check.py` (falsification bench)
- `docs/bmad/stories/9-2-chart-storageclass-from-values.md`

## Acceptance audit

| AC | Requirement | Evidence | Status |
|----|-------------|----------|--------|
| AC1 | CNPG Postgres PVC class FROM VALUES, never omitted | `postgres-cluster.yaml:17` `storageClass: {{ $sc \| quote }}`, `$sc := include "ksquad.storageClass.postgres"` | ✅ |
| AC2 | Workspace class + accessMode + size handed to operator | `operator-config.yaml:17-20`; accessMode values-driven `.Values.storage.workspace.accessMode` | ✅ |
| AC3 | NATS/JetStream class FROM VALUES | Real PVC stamped at `nats.yaml:139` via `ksquad.storageClass.nats`; ref copy in `operator-config.yaml:23` | ✅ (see F1) |
| AC4 | Per-family override beats global; global fallback both directions | `_helpers.tpl:67-77` `family \| default global` (sprig `default` treats "" as unset); bench C4 asserts both directions | ✅ |
| AC5 | Fail-fast per family on unset — no silent cluster-default | `_helpers.tpl:117-126` `ksquad.validate` fail per postgres/workspace/nats; included from always-rendered `service.yaml:4` | ✅ |
| AC6 | Optional WAL PVC shares Postgres class, values-driven | `postgres-cluster.yaml:18-22` WAL block stamps the **same** `$sc`; absent when disabled | ✅ |

## Adversarial layers

- **Blind Hunter:** No hardcoded StorageClass literals anywhere. `grep` confirms the only PVC-bearing templates are `postgres-cluster.yaml` + `nats.yaml`; `operator-config.yaml` is a ConfigMap (reference values); `event-relay.yaml` has no volumes. No stray PVC can inherit the cluster default.
- **Edge Case Hunter:** `default` semantics correct — empty family → global; non-empty family → override (not frozen). Fail-fast fires from `service.yaml` (ClusterIP always renders), so unset can never render a partial manifest. NATS/Postgres accessMode hardcoded `ReadWriteOnce` is correct-by-design (per-replica JetStream / CNPG-owned), not an AC2 violation — AC2 scopes values-driven accessMode to workspace only.
- **Acceptance Auditor:** Bench `storage-class-check.py` exit 0 — baseline C1–C6 GREEN, all 11 mutations caught, 6 file-grounded detectors flip on mutation.

## Findings

**F1 (Low, non-blocking) — AC3 file-grounded detector guards the reference copy, not the real PVC stamper.**
`FG3` (`storage-class-check.py:519-520`) asserts `nats.storageClassName` in `operator-config.yaml` (the operability *reference* value), but the JetStream PVC's class is actually stamped in `templates/nats.yaml:139`. The shipped chart is correct (`nats.yaml:139` sources `ksquad.storageClass.nats`), so **no live defect** — but a regression that omitted/hardcoded the class on `nats.yaml:139` would leave FG3 GREEN. Same teeth-gap shape as the ISI-2346 durable-check lesson: the detector should guard the artifact the AC is really about.
*Recommend:* extend FG3 to also assert `nats.yaml` volumeClaimTemplate sources `ksquad.storageClass.nats`. Bench-only change; not a merge blocker.

## Disposition
Story 9.2 is **falsifiable and conformant** to arch §16.2 / §9.4 / FR-L2. Every PVC family (CNPG +WAL, operator-stamped workspace, NATS) sources its class from values, no hardcoded class, fail-fast per family from an always-rendered template, access-mode respected, default posture documented in `values.yaml`. **APPROVE.** F1 filed as an optional bench hardening follow-up.
