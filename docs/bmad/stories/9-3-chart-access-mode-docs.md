# Story 9.3: Access-mode behavior documented per storage-class

Status: Done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The chart tells the truth about access modes — it documents the class-dependent
> behavior, validates the enum so a typo fails fast, and warns (never silently succeeds)
> when you pick RWX.** Reading the chart's storage docs states plainly: `ReadWriteOnce`
> (RWO) is the default and works on every class (worktree-per-Run, §9.4); `ReadWriteMany`
> (RWX) is optional and honored **only** where the StorageClass supports it; volume
> expansion and snapshots are class-dependent too. `values.schema.json` validates
> `storage.workspace.accessMode` against the enum `ReadWriteOnce|ReadWriteMany|ReadWriteOncePod`
> so a mistyped mode (`ReadWriteMnay`, `rwx`, `ReadOnlyMany`) fails `helm install`/`template`
> up front rather than producing a PVC that never binds — and because the chart **cannot**
> verify a class's RWX capability offline, RWX passes the enum but triggers a render-time
> **warning** to pre-flight the class. Silently accepting a bad mode, rejecting RWX outright,
> or docs that omit the RWX-is-conditional / expansion+snapshot-class-dependent facts are
> regressions.

## Story

As a **platform engineer installing KSquad on my own cluster**,
I want **the chart's storage docs to state the access-mode behavior per StorageClass (RWO
default, RWX only where supported, expansion/snapshots class-dependent) and the values schema
to validate the `accessMode` enum and warn when I pick RWX**,
so that **I choose an access mode my StorageClass actually supports — with a typo caught at
install time and an honest warning when RWX needs pre-flighting — instead of discovering a
workspace PVC stuck `Pending` in production.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` Theme L (**FR-L2**) — the install binds persistent storage
  to an operator-chosen StorageClass, not the cluster default, so the ≤4h air-gapped install
  (S1, NFR-USE1) holds across clusters with differing storage posture. Access mode is part of
  that "bind explicitly, never guess" contract.
- **Architecture:** `docs/bmad/03-architecture.md` **§9.4** (per-Project workspace PVCs;
  worktree-per-Run) and **§16.2** (Storage & StorageClass). RWO pairs with worktree-per-Run;
  RWX is the opt-in for true parallel-Run write access and is a **class capability the chart
  cannot verify offline** — surfaced as a pre-flight, not a guarantee.
- **Sibling to Story 9.2** ([[isi-2251-story92-storageclass-from-values]]): 9.2 made every PVC's
  `storageClassName` values-driven and introduced `storage.workspace.accessMode` (RWO default,
  values-driven) plus the StorageClass **capability matrix** in the README. This story (9.3)
  adds the **schema teeth** on the access-mode enum, the **warn-on-RWX** render behavior, and a
  dedicated **access-mode behavior** doc subsection — the "documented + validated" half of the
  access-mode seam.
- **Chart implementation:** the chart lives and is CI-tested in the **`k8squad`** source repo at
  `deploy/helm/ksquad/`. This story's delta is on branch `feature/isi-2252-access-mode-docs`
  (off `main`): `values.schema.json` (new), the `templates/NOTES.txt` RWX warning block, the
  README "Access-mode behavior per StorageClass (§9.4)" subsection, and four `ci/test.sh`
  schema assertions. The pinned snapshot under `docs/bmad/spikes/bench/helm-chart-isi2149/`
  vendors the delta for the file-grounded bench pass (see `PROVENANCE.md`).
- **Why a warning, not a rejection, for RWX:** `values.schema.json` runs offline at value
  coalescing time; it can validate the *shape* of the value (is it a known access mode?) but
  cannot reach the cluster to ask whether the chosen StorageClass provides RWX. Rejecting RWX
  outright would break every legitimate CephFS/NFS/EFS install; silently accepting it on a
  class that lacks RWX leaves PVCs `Pending`. The honest seam: **enum-validate the mode, warn
  on RWX to pre-flight the class** (surfaced in `helm install` NOTES).
- **Scope guard:** this is the **access-mode documentation + schema validation** slice. PVC
  `storageClassName` parameterization is Story 9.2; Gateway/Ingress exposure is Story 9.1
  ([[isi-2250-story91-gateway-httproute]]); NATS/JetStream wiring is Story 9.4. The chart never
  vendors the CNPG/NATS operators — it renders and lints offline.

## Acceptance Criteria

**AC1 — Storage docs state RWO default, RWX optional (only when class supports it).** The chart
README storage section states plainly that `ReadWriteOnce` is the default (works on every class,
pairs with worktree-per-Run §9.4) and that `ReadWriteMany` is optional and honored **only where
the StorageClass supports it** (CephFS/NFS/Azure Files/EFS). *(Bench: C3; ci: n/a — doc.)*

**AC2 — Docs state expansion + snapshots are class-dependent.** The storage docs state that
volume expansion needs `allowVolumeExpansion: true` on the class and snapshots need a CSI driver
+ `VolumeSnapshotClass` — capabilities of the chosen class, independent of access mode.
*(Bench: C3.)*

**AC3 — `values.schema.json` validates the `accessMode` enum.** The chart ships a
`values.schema.json` constraining `storage.workspace.accessMode` to
`ReadWriteOnce|ReadWriteMany|ReadWriteOncePod`; an off-list value fails `helm install`/`template`
with a clear schema error, rendering nothing — never a workspace PVC with an unusable mode.
*(Bench: C1; ci: `render_fail "invalid accessMode fails schema enum"`.)*

**AC4 — The schema warns on RWX, it does not reject it.** `ReadWriteMany` passes the enum (it is
a valid mode); the chart instead emits a render-time WARNING (`helm install` NOTES) that RWX is
honored only on a class that supports it and the operator must pre-flight the class. RWO renders
no warning. *(Bench: C2; ci: `render_ok "accessMode RWX passes schema (valid enum, warned not
rejected)"`.)*

## Falsification bench

`docs/bmad/spikes/bench/access-mode-check.py` (stdlib only, `helm`-free) reads the **pinned real
chart snapshot** and proves three teeth on the shipped artifact, then mutates each to prove the
detector flips RED:

- **C1 — schema enum.** Parses `values.schema.json`; asserts the `accessMode` enum is exactly
  `{ReadWriteOnce, ReadWriteMany, ReadWriteOncePod}`, that all three pass, and that off-list modes
  (`ReadWriteMnay`, `rwx`, `ReadOnlyMany`, `""`) fail.
- **C2 — warn-on-RWX.** Faithfully models the NOTES.txt Go-template conditional; asserts a WARNING
  renders **only** when accessMode=ReadWriteMany, that RWX still passes the schema (warned, not
  failed), and that the warning tells the operator to **pre-flight** the class.
- **C3 — docs.** Asserts the README states RWO-is-default, RWX-only-where-supported, and
  expansion+snapshots class-dependent.

**Result: baseline C1–C3 GREEN; all 6 mutations caught.**

| Mutation | Break | Caught by |
|---|---|---|
| M1 drop RWX from the enum | a valid access mode is rejected | C1 |
| M2 schema freeform accessMode | a typo slips through → PVC never binds | C1 |
| M3 remove the RWX warning block | RWX chosen silently, no pre-flight nudge | C2 |
| M4 re-point the warning guard to RWO | warns on the safe default, silent on RWX | C2 |
| M5 README drops the "only if supported" RWX qualifier | RWX reads as always-available | C3 |
| M6 README drops expansion+snapshot class-dependence | operator assumes both always work | C3 |

Run: `python3 docs/bmad/spikes/bench/access-mode-check.py` (exit 0 = all teeth hold).
Full render/lint + schema gate (needs `helm`): `k8squad` `deploy/helm/ksquad/ci/test.sh`.

## Definition of Done

- [x] README storage section states RWO default / RWX optional-only-when-supported /
      expansion+snapshot class-dependent (AC1, AC2) against arch §9.4 / §16.2 / Theme L.
- [x] `values.schema.json` validates `storage.workspace.accessMode` enum; off-list value fails
      `helm template`/`install` (AC3) — verified via `ci/test.sh` `render_fail`.
- [x] Chart warns on RWX at render (NOTES.txt), does not reject it; RWO renders no warning (AC4).
- [x] Falsification bench green: C1–C3 baseline GREEN, 6 mutations caught
      (`access-mode-check.py`, exit 0).
- [x] Pinned chart snapshot extended with `values.schema.json` + the NOTES/README delta;
      `PROVENANCE.md` records the Story 9.3 branch.
- [x] `k8squad` PR #45 reviewed (APPROVE, ISI-2657) + merged — chart delta on `main` as
      merge `15b2a3d` (feat `09d6770`). `ci/test.sh` schema assertions + `access-mode-check.py`
      re-verified GREEN on merged `main`.

## Notes

- **k8squad is the source of truth for the chart; ksquad holds the story + bench artifacts.** The
  vendored snapshot is a read-only fixture; refresh by re-vendoring + bumping the commit in
  `PROVENANCE.md` when the PR merges.
- **`helm template` does not render NOTES.txt**, so the warn-on-RWX teeth live in the python bench
  (which models the conditional file-grounded) rather than in `ci/test.sh`; `ci/test.sh` covers the
  schema enum (which `helm template` *does* enforce) positively and negatively.
- **The capability matrix is a pre-flight, not a guarantee** (§9.4): setting RWX on a class that
  lacks it is the operator's pre-flight to get right — the chart surfaces and warns, it cannot
  verify offline.
