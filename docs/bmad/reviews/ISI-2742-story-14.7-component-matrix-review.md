# ISI-2742 — Story 14.7 component-matrix CI pipeline — Review

**Reviewer:** Testing Architect (Amelia)
**PR:** https://github.com/K8squad/K8squad/pull/63 (`feature/isi-2742-component-matrix` → `main`)
**HEAD reviewed:** `1d49ed7` (was `dc12b45`; +1 reviewer comment-fix)
**Date:** 2026-08-17
**Disposition:** ✅ **APPROVE** (one doc defect fixed in-review; no functional blockers)

## Scope reviewed

- `.github/workflows/component-matrix.yml` (NEW, reusable `workflow_call`)
- `.github/workflows/ci.yml` (derives go/shim/helm/node fan-out from the reusable matrix)
- `.github/workflows/README.md` (stable per-component check-run registry)

## Verified

| Check | Result |
|-------|--------|
| Reusable-workflow output plumbing (step → job.emit.outputs → workflow_call outputs → `needs.components.outputs.*` → `fromJSON` matrix) | ✅ correct chain |
| Emit job runner (R1) — `runs-on: [self-hosted, linux, x64]` | ✅ no `ubuntu-latest` jobs remain across all workflows |
| `ci.yml` concurrency (R2) — `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}` | ✅ main merge-train run never cancelled; PR pushes self-cancel |
| Stable check-run names (`go / <c>`, `shim / <runtime>`, `helm / k8squad`, `node / console`, `db / migrations self-check`) match README registry + component-matrix header | ✅ in sync; wires ISI-2674 later without wedging |
| Helm lane real (not skeleton-skipped) — `config/helm/Chart.yaml` present | ✅ `helm lint` + `helm template --include-crds` will actually run |
| Skeleton skip-with-reason guards on go/shim/helm/node/migrations | ✅ fail-visible `::notice::`, no false-green |
| OOM containment on lint legs (GOMAXPROCS=1 / GOGC=30 / GOMEMLIMIT=3800MiB / `--concurrency=1`) per ISI-2614/2612 | ✅ present on both go + shim legs |
| Node-24 action pins (checkout@v5, setup-go@v6, setup-node@v5, golangci-lint-action@v7, upload-artifact@v5) | ✅ |
| DCO sign-off on all commits | ✅ `0529bc7`, `dc12b45`, `1d49ed7` all signed |

## Findings

### F1 — [FIXED in-review] Stale emit-job runner comment (`ci.yml:29`)
The R1 fix (`dc12b45`) moved the emit job to a self-hosted runner, but the
`components:` job comment still read "Runs on a GitHub-hosted runner so it never
eats a self-hosted slot." That is the exact trap R1 guards against — a maintainer
"restoring" the emit job to `ubuntu-latest` (which has **no** minutes on
`K8squad/K8squad`) would queue-hang it and wedge every downstream lane. Corrected
to describe the self-hosted placement + rationale (`1d49ed7`).

### F2 — [ACCEPT — by design, documented] go legs run the full module, not `matrix.path`
Each `go / <component>` leg runs `go build ./...` / `go test -race ./...` over the
whole module, so operator/apiserver/memory legs run identical work. This is
**intentional and documented**: the component-matrix header states coord (pkg/coord)
is deliberately *not* its own leg because "it is exercised by every go leg's
`go test ./...`." Scoping the legs to `matrix.path` would drop that coord coverage.
The cost (triple full-module run on a 2-runner fleet) is the conscious tradeoff for
per-component required-check granularity + coord coverage. No change requested.

## Merge gate (owned by developer)

Reviewer approval is granted. The remaining gate is **CI green on the two
self-hosted runners** for PR #63 (CI/DCO/Security). Merge is **DCO-only** (ISI-2609)
and owned by the implementing developer. Does **not** block on ISI-2674
(branch-protection required-check registration — separate, repo-admin-blocked).
