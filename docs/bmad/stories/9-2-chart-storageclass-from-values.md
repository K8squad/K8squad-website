# Story 9.2: Every PVC takes storageClassName from values

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The chart CREATES its storage bindings, it does not assume them.** On a cluster whose
> *default* StorageClass is unsuitable — wrong provisioner/tier, no `allowVolumeExpansion`,
> no RWX, or no default class at all — `helm install --set storage.postgres.storageClassName=<x>
> --set storage.workspace.storageClassName=<y>` renders the CNPG Postgres `Cluster` PVC (and,
> when enabled, the WAL PVC), the operator-config that stamps every per-Project workspace PVC,
> and the NATS/JetStream file-store PVC **all with those classes** — per-family override falling
> back to a global `storage.storageClassName`. An **unset** class (no family value *and* no
> global) **fails the install fast with a clear error** — the chart **never** omits `storageClass`
> and **never** relies on the cluster-default StorageClass. An omitted class, a hardcoded literal,
> a per-family override that silently falls through to the global, a dropped global fallback, or a
> silent default on unset is a **regression**. Read AC1, AC4, and AC5 literally.

## Story

As a **platform engineer installing KSquad on my own cluster**,
I want **every PVC the install creates — CNPG Postgres (+ WAL), the operator-stamped per-Project
workspaces, and the NATS/JetStream store — to take its `storageClassName` from values (per-family
override or a global fallback), with the install failing fast if a class is unset**,
so that **KSquad's data-of-record and workspaces land on the storage I chose — never silently on an
unsuitable cluster-default class — and a missing class is a loud pre-flight failure, not a
mis-provisioned volume I discover in production.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` Theme L (**FR-L2**) — the install SHALL bind its persistent
  storage to an operator-chosen `StorageClass` rather than assuming the cluster default, so the
  ≤4h air-gapped install (S1, NFR-USE1) holds on clusters with differing storage posture.
- **Architecture:** `docs/bmad/03-architecture.md` **§16.2** (Storage & StorageClass) and **§9.4**
  (per-Project workspace PVCs; worktree-per-Run) — *"Every PVC's StorageClass comes from values,
  never the cluster default."* The class is a **required values input**; per-family
  (`storage.{postgres,workspace,nats}.storageClassName`) overrides a global
  (`storage.storageClassName`), and an unset class **fails the install fast**. CNPG is the sole
  store of record (**ADR-001 / §4**); its `Cluster` CR PVC (and optional WAL PVC) must carry an
  explicit class. Also **§16** (single-instance default profile, raise `instances` for HA).
- **Why explicit, never default (§16.2):** a cluster's *default* StorageClass may be the wrong
  provisioner/tier, may lack `allowVolumeExpansion`, may not support `ReadWriteMany`, or may not
  exist at all (a PVC then hangs `Pending`). Binding the data-of-record and every workspace to
  "whatever the cluster defaults to" is a silent mis-provision — green `kubectl get pvc`, wrong
  disk. The chart therefore **stamps** the class on every PVC and **fails fast** when it can't.
- **StorageClass capability matrix (§9.4, surfaced in `values.yaml` + README):** the operator
  must pre-flight the chosen class against what it needs — `ReadWriteOnce` (every class; the
  default, pairs with worktree-per-Run), `ReadWriteMany` (only some classes: CephFS/NFS/Azure
  Files/EFS — required **only** if `storage.workspace.accessMode=ReadWriteMany` for true
  parallel-Run write access), volume expansion (needs `allowVolumeExpansion=true`), snapshots
  (needs a CSI driver + `VolumeSnapshotClass`). The chart surfaces the matrix; it cannot verify a
  class's capabilities offline, so this is an honest pre-flight, not a silent guarantee.
- **Who creates which PVC:** the **CNPG operator** owns the Postgres (+ WAL) PVC from the `Cluster`
  CR the chart renders; the **KSquad operator** owns the per-Project workspace PVCs, created at
  Project reconcile (§9.4) from the class/accessMode/size the chart hands it via the `*-storage`
  ConfigMap; the **NATS subchart** owns the JetStream PVC from the class surfaced in values. Helm
  renders the Postgres CR and the operator ConfigMap; it does not itself create the workspace/NATS
  PVCs — but every one of them sources its class from `storage.*`, never the cluster default.
- **Chart implementation:** the chart lives and is CI-tested in the **`k8squad`** source repo at
  `deploy/helm/ksquad/` — commit `5e6442d` on `feature/helm-exposure-storage` (**ISI-2149**
  `feat(helm): parameterized Gateway API exposure + explicit StorageClass`). `ci/test.sh`
  renders + asserts `storageClass: "fast-ssd"` on the CNPG PVC, `workspace.storageClassName` in the
  operator ConfigMap, the per-family override (`storage.postgres.storageClassName=db-class`), and
  the fail-fast on unset (needs a `helm` binary). This story (ISI-2251) pins the
  **construction-time contract** those templates must satisfy and adds a `helm`-free falsification
  bench. The pinned chart snapshot under `docs/bmad/spikes/bench/helm-chart-isi2149/` now vendors
  `templates/postgres-cluster.yaml` + `templates/operator-config.yaml` for the file-grounded pass.
- **Scope guard:** this story is **StorageClass parameterization for every PVC family** (§16.2 /
  §9.4). Gateway/Ingress exposure is **Story 9.1** ([[isi-2250-story91-gateway-httproute]]);
  NATS/JetStream Helm dep wiring is **Story 9.4**; auth config packaging is **Story 9.5**. The
  chart never vendors the CNPG/NATS operators — they are cluster prerequisites so the chart renders
  and lints offline.

## Acceptance Criteria

**AC1 — CNPG Postgres PVC StorageClass FROM VALUES (never omitted → never cluster-default).**
The chart renders the CNPG `Cluster` CR with `spec.storage.storageClass` set to the resolved
Postgres class (`storage.postgres.storageClassName` else `storage.storageClassName`). The class is
**never omitted** (which would let Kubernetes pick the cluster default) and **never a hardcoded
literal** — it tracks the values input.
*(Bench: C1 — differential over two profiles; FG1.)*

**AC2 — Workspace StorageClass handed to the operator FROM VALUES.** The chart renders the
`*-storage` ConfigMap carrying `workspace.storageClassName` (resolved as above), `workspace.accessMode`,
and `workspace.size`, so the operator stamps the operator-chosen class (never the cluster default)
onto **every** per-Project workspace PVC at reconcile (§9.4). `accessMode` is itself values-driven
(`ReadWriteOnce` default; `ReadWriteMany` only where the class supports it).
*(Bench: C2 — differential incl. accessMode; FG2.)*

**AC3 — NATS/JetStream StorageClass FROM VALUES.** The NATS file-store class
(`storage.nats.storageClassName` else the global) is surfaced from values for the NATS subchart PVC —
never the cluster default. *(Bench: C3 — differential; FG3.)*

**AC4 — Per-family override beats the global; the global is the fallback (both directions).**
Resolution is `family || global`: a per-family `storage.postgres.storageClassName` **overrides** the
global (it is not silently frozen to the global), and a family left empty **falls back** to
`storage.storageClassName` (the global fallback is not dropped — a global-only install must succeed).
*(Bench: C4 — asserts both directions; FG4.)*

**AC5 — Install fails fast if a StorageClass is unset — no silent cluster-default.** With a family
class **and** the global both empty, `helm install`/`template` **fails with a clear error**
(`ksquad.validate`: *"never relies on the cluster-default StorageClass"*), rendering **nothing**. The
guard is **per family** — postgres, workspace, and NATS are each independently required — and never
substitutes a hardcoded/default class. *(Bench: C5 — per-family teeth; FG5.)*

**AC6 — The optional WAL PVC is values-driven and shares the Postgres class.** When
`storage.postgres.walStorage.enabled`, the CNPG WAL volume PVC renders with the **same** resolved
Postgres class (never omitted → no second cluster-default PVC, never a divergent hardcoded class);
when disabled it is absent. *(Bench: C6; FG6.)*

## Falsification bench

`docs/bmad/spikes/bench/storage-class-check.py` (stdlib only, `helm`-free):

- **Layer A — model-based mutation battery.** A faithful mini-renderer of the chart's storage
  templates (`postgres-cluster.yaml`, `operator-config.yaml`) + `ksquad.storageClass.*` /
  `ksquad.validate` fail-fast. Six checks **C1–C6 ↔ AC1–AC6**; differential checks render two
  distinct value profiles (A: per-family overrides + WAL on; B: global-only fallback + WAL off) and
  assert the rendered class **tracks the input** — the teeth against omission/hardcoding that "it
  renders / the PVC is Bound" cannot give. **11 broken-chart mutations**, each caught by its
  designated check going RED; the §16.2-conformant baseline is GREEN on all six.
- **Layer B — file-grounded pass.** Reads the **pinned real chart snapshot** (k8squad@5e6442d,
  now including `postgres-cluster.yaml` + `operator-config.yaml`), asserts the **shipped** templates
  satisfy each invariant, and text-mutates each template to prove the detector flips — teeth on the
  real artifact, not just the model. 6 detectors (FG1 CNPG PVC class-from-values, FG2 workspace
  class-from-values, FG3 NATS class-from-values, FG4 `family|default global` resolution, FG5
  fail-fast on unset, FG6 WAL PVC shares the Postgres class).

**Result: baseline C1–C6 GREEN; all 11 mutations caught; 6 file-grounded detectors pass with teeth.**
Mutation → caught-by map:

| Mutation | Break | Caught by |
|---|---|---|
| M1 hardcode CNPG `storageClass` | Postgres PVC frozen to a literal, ignores values | C1 |
| M2 omit CNPG `storageClass` | Postgres PVC → cluster-default | C1 |
| M3 ignore per-family override | override silently frozen to the global | C4 |
| M4 silent default on unset | unset class → `"standard"` instead of fail | C5 |
| M5 skip storage validate | unset renders an omitted-class PVC anyway | C5 |
| M6 workspace class missing (op cfg) | operator stamps cluster-default on every Project PVC | C2 |
| M7 hardcode workspace class | workspace class frozen, ignores values | C2 |
| M8 omit NATS class | NATS store on the cluster-default class | C3 |
| M9 WAL omits `storageClass` | second cluster-default PVC | C6 |
| M10 WAL different hardcoded class | WAL PVC drifts from the main Postgres class | C6 |
| M11 drop global fallback | family-only resolution → global-only install fails | C4 |

Run: `python3 docs/bmad/spikes/bench/storage-class-check.py` (exit 0 = all teeth hold).
Full render/lint gate (needs `helm`): `k8squad` `deploy/helm/ksquad/ci/test.sh`.

## Definition of Done

- [x] Construction-time contract (AC1–AC6) pinned against arch §16.2 / §9.4 / Theme L (FR-L2).
- [x] Chart shipped in `k8squad` (`deploy/helm/ksquad/`, ISI-2149) satisfies all six ACs:
      `postgres-cluster.yaml` stamps the CNPG (+ WAL) PVC class, `operator-config.yaml` hands the
      workspace + NATS class to the operator, `_helpers.tpl` resolves `family|default global` and
      fails fast per family, and `ci/test.sh` asserts each positively and negatively.
- [x] Falsification bench green: C1–C6 baseline GREEN, 11 mutations caught, 6 file-grounded
      detectors pass with teeth (`storage-class-check.py`, exit 0).
- [x] Pinned chart snapshot extended with the two storage templates for the file-grounded pass.

## Notes

- **k8squad is the source of truth for the chart; ksquad holds the story + bench artifacts** — the
  vendored snapshot is a read-only fixture pinned to a commit, not a fork. Story 9.1 vendored the
  exposure templates; this story adds `postgres-cluster.yaml` + `operator-config.yaml` (same commit
  `5e6442d`; `_helpers.tpl` + `values.yaml` were already vendored and are byte-identical). Refresh
  by re-vendoring + bumping the commit in `PROVENANCE.md` if the chart changes.
- **The capability matrix is a pre-flight, not a guarantee** (§9.4): the chart surfaces which
  StorageClass capabilities each PVC needs (RWO/RWX, expansion, snapshots) but cannot verify a
  class's capabilities offline — setting `workspace.accessMode=ReadWriteMany` on a class that lacks
  RWX is the operator's pre-flight to get right, surfaced in `values.yaml` + README, not hidden.
- **Sibling to Story 9.1** ([[isi-2250-story91-gateway-httproute]]): same "the chart CREATES its
  cluster bindings, it does not assume them" contract, same `ksquad.validate` fail-fast seam
  (exposure + storage validated together), same falsification-bench shape.
