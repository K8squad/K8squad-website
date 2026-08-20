# ISI-2863 — Story X.2 residue/reuse test (ISI-2241) — QA Review

**Reviewer:** Testing Architect (Amelia)
**Branch:** `ISI-2858-docs-alignment` (K8squad-website), base `774e463` → review fixes at `HEAD`
**Date:** 2026-08-20
**Disposition:** ✅ **APPROVE** (three defects fixed in-review; oracle + mutation contract verified live 6/6)

## Scope reviewed

- `docs/bmad/spikes/bench/residue-reuse-check.py` — the runtime residue oracle (C1/C4/C5/C6), `--mutate` (C7), `judge_observed()`
- `docs/bmad/spikes/bench/residue-reuse-kind.sh` — kind/kubectl runtime driver (plant → hygiene → probe → judge), `--self-check`
- `.github/workflows/blast-radius.yml` — job `s4-4-reuse-residue` (the required CI artifact)
- Cross-file boundary agreement with Story 4.5 (`teardown-scoping-check.py`)

## Verified (all executed in this review)

| Gate criterion (per [ISI-2481](/ISI/issues/ISI-2481)) | Evidence | Result |
|---|---|---|
| Cross-Run / cross-principal residue isolated by the checks | oracle base run: teardown-and-replace 0/6; driver C2 pod-UID assertion (`residue-reuse-kind.sh:293`), per-principal subPath mounts | ✅ |
| No workspace-reuse violations pass undetected | `--mutate`: 6/6 probes load-bearing (differential: real leak=1, seen=0 per dropped probe); self-check proves both judge failure modes; C6a fires on exactly the 3 unscrubbed channels, C6b on `pvc-cross-principal` | ✅ |
| Verdict flags only cross-Run + cross-principal; FR-C2 not false-flagged | `violations()` skips same-run and same-principal (`residue-reuse-check.py:152-155`); positive controls offline (`check_same_principal_persists`) and in-cluster (C5 run3/p1) | ✅ |
| Mutation arm genuinely breaks the oracle | live run `MUTATE_RC=0`, all six BLIND with ground-truth differential — not decorative | ✅ |
| Boundary agreement with 4.5 | `principal_subpath("proj","p1")` = `proj/cache/p1-f64551fcd6f0` identically in oracle, 4.5 bench, and driver `subpath()` | ✅ |
| Driver self-check | `residue-reuse-kind.sh --self-check` → PASS (judge wiring + both failure modes) | ✅ |

## Findings (all fixed in-review)

### F1 — [FIXED] Cluster residue verdicts swallowed as WARN (`blast-radius.yml:191-197` @ base)
The s4-4 step ran `--policy teardown+per-principal` and converted **any** nonzero driver exit
into `WARN … offline oracle passed`. Story harness §5 is explicit: *"Non-empty violations → CI
red"* (`x-2-residue-reuse-test.md:134`). As wired, a real NFR-SEC5 leak observed on-cluster
would have left the check green. **Fix:** run the **full policy matrix** (adds in-cluster C6a/C6b
controls per harness step 6) and hard-fail the step when the driver output carries a verdict
failure (`judge FAIL|C2 violated|C5 control broken|TEETH LOST|suite: FAIL`); setup/env flakes
without a verdict line stay WARN — the offline oracle remains the merge gate (story
`x-2-residue-reuse-test.md:139-141`).

### F2 — [FIXED] `X2_VOLUME_MODE=pvc` can never bind on kind (`blast-radius.yml:164` @ base)
kind's default StorageClass (local-path provisioner) is **RWO-only**; the driver's Project-PVC
is `ReadWriteMany 1Gi` (`residue-reuse-kind.sh:187`) → PVC never binds → `setup_ns` times out
at 180s → the cluster test could never actually execute (and via F1, failed silently).
**Fix:** `X2_VOLUME_MODE=hostpath` — the driver's own documented mode for clusters without RWX
provisioning (node-pinned, durable across pods; exercises every channel including the durable
cross-principal one).

### F3 — [FIXED] Inverted git-worktree probe semantics (`residue-reuse-kind.sh:112` @ base)
`git diff --cached --quiet` exits **0 on a clean index**, so `{ git diff --cached --quiet ||
symbolic-ref … }` emitted residue observations for **clean** trees and inverted the
staged-changes signal. Not reachable in the shipped 3-policy matrix (geometry/guards masked
it), but a landmine for any future policy where a cross-principal probe sees a clean repo
(false RED) or staged-only residue without the branch (false GREEN). **Fix:** negate the diff
checks and cover the full C3 channel definition (staged index / dirty tree / branch):
`{ ! git diff --cached --quiet || ! git diff --quiet || symbolic-ref … | grep -q poison-branch; }`.
Verified against four real git states: poisoned→EMIT, clean→silent, staged-only→EMIT,
dirty-unstaged→EMIT.

### F4 — [FIXED] Lane dead-end: `helm install charts/ksquad` with no chart in repo (`blast-radius.yml:103-110` @ base)
No `charts/` exists in this repo, so every s4 matrix leg died at the chart-install step before
any test ran. The residue driver drives raw Pods/PVCs via kubectl and needs no chart.
**Fix:** existence-guarded install with a `::notice::` skip message.

## Post-fix verification (this review's HEAD)

```
bash -n residue-reuse-kind.sh                    → OK
residue-reuse-kind.sh --self-check               → PASS (judge wiring + both failure modes)
residue-reuse-check.py                           → PASS (base gate)
residue-reuse-check.py --mutate                  → PASS (6/6 load-bearing)
python3 yaml.safe_load(blast-radius.yml)         → OK
mkpod render (hostpath+subPath+env, rc omitted)  → valid Pod YAML
git-probe 4-state simulation                     → EMIT/silent/EMIT/EMIT (correct)
```

## Observations (no change requested — owners named)

- **N1** `blast-radius.yml:149` condition `s3-3-cross-namespace-isolation` and `:204`
  `s5-4-404-not-403-read-authz` never match their matrix values (`s4-3-…`, `s5-404-…`) → those
  legs pass vacuously. They are `echo PASS` placeholders for **other** stories (S4-3, S5-4);
  fix the condition strings when those stories land real tests.
- **N2** The `Upload test results` step globs `docs/bmad/spikes/bench/*.jsonl`, but the driver
  writes JSONL/uid sidecars to a `mktemp -d` workdir it deletes on exit — nothing is captured.
  A future `--artifacts-dir` driver flag would fix it; observability nicety, not a gate issue.
- **N3** `runs-on: ubuntu-latest` on all three jobs. If K8squad-website lacks GitHub-hosted
  minutes (the K8squad/K8squad constraint from ISI-2742 R1 applies repo-by-repo), these queue
  forever. Lane-owner (Epic-14 / ISI-2157) call.

## Verdict

**APPROVE.** The oracle is genuinely differential and policy-agnostic; all six channel probes
are load-bearing (verified live, 6/6 BLIND); the verdict flags exactly cross-Run +
cross-principal observations with FR-C2 protected by positive controls on both paths; the
mutation arm breaks the oracle by construction. The three delivery defects (F1–F3) plus the
lane dead-end (F4) were fixed in-review and re-verified. Story X.2 DoD's final item
("Code review (adversarial)") is satisfied by this document.
