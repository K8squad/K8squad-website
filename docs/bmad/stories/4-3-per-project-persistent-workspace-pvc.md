# Story 4.3: Per-Project persistent workspace (PVC) — provision, mount, persist, worktree/lease concurrency

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS STORY OWNS THE PERSISTENT WORKSPACE ITSELF: the per-Project PVC (source + build cache)
> that is provisioned once, mounted into every Run's sandbox, and — the crux — *outlives* the Run
> whose pod is torn down (§9.3), so its build cache survives across Runs (FR-C2).** The load-bearing
> claim is that **pod lifecycle is not workspace lifecycle**: Story 4.5 destroys a completed Run's
> *sandbox pod* (teardown-and-replace) — but the *PVC is not the pod*. A reconciler that ties the PVC
> to the pod (delete/recreate it per Run) throws away the cache every Run — a cold rebuild each time —
> and **silently breaks FR-C2** while a single sequential green Run still looks fine. Two more
> load-bearing invariants come from §9.4/ADR-007: **concurrent Runs on one Project each get their own
> git worktree** over the shared checkout (no clobber, and *not* a global Project lock that would
> serialize everything), and **exclusive-write operations take a Project workspace lease** (§6.3
> primitive) so two Runs rebuilding the shared cache/index don't corrupt it. This story provisions +
> mounts + persists the PVC and owns worktree/lease concurrency; **Story 4.5 partitions this same PVC
> per principal** (a per-principal subpath) and **Story 8.7d** gates the per-principal *read* path.
> Read AC1 literally: the PVC persists across Runs; only the Project's own teardown (4.1) reclaims it.

## Story

As **the Project reconciler + Run pod-assembler provisioning and mounting the durable workspace for many Runs on one Project**,
I want **each Project to have a persistent workspace PVC (source + build cache) provisioned from its `workspacePVC` spec, mounted into every Run's sandbox, persisting across Runs, with concurrent Runs isolated by a per-Run git worktree over the shared checkout and exclusive-write operations serialized by a Project workspace lease**,
so that **a Run starts warm against the prior Runs' cache instead of cold-rebuilding every time (FR-C2), concurrent Runs on one Project never clobber each other's working tree or corrupt the shared cache (FR-C5, ADR-007), and the workspace survives the teardown-and-replace of any individual Run's sandbox pod (§9.3) because the PVC is bound to the Project, not the pod (arch §9.4).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-C2** (persistent Project workspace: source + build cache persist
  across Runs), **FR-C5** (concurrent Runs on one Project don't clobber), **OQ5** (concurrency model,
  resolved to worktree-per-Run in the arch). This story is the **FR-C2/C5 mechanism** the arch routed
  to §9.4 bullets 1–2.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§9.4 — Workspace & concurrency (OQ5, FR-C2/C5).** The authoritative decision this story encodes:
    - *"Each `Project` has a **workspace PVC** (source + build cache) persisting across Runs (FR-C2)."*
      — the durable resource; **provisioned once per Project, reused by every Run**.
    - *"each Run operates in its own **git worktree** (native git, not invented locking — ponytail rung
      4) over the shared checkout, so concurrent Runs don't clobber. Operations needing exclusive write
      (dependency install, index rebuild) take a **Project workspace lease** (same lease primitive as
      §6.3). Default PVC access is `RWO` with worktree-per-Run; `RWX` (if the storage class supports it)
      enables true parallelism."* — the two concurrency defenses (worktree isolation + exclusive-write
      lease) this story owns.
  - **§9.3 — Hygiene: teardown-and-replace (the interaction to get right).** *"After a Run completes,
    its sandbox **pod** is destroyed and the pool replenishes a **fresh** pod."* The teardown target is
    the **pod**, **not** the PVC. This story's AC1 is precisely the "the PVC survives that teardown"
    guarantee — pod lifecycle ≠ workspace lifecycle.
  - **§5.2 pod-assembly step 4 — the mount.** *"Mount the shared toolchain-staging volume + the Project
    workspace PVC (§9.4) + credential Secrets (§11) + the `gh`/git credential mount when `github:
    true`."* This story wires the **workspace-PVC** mount in that assembly step (source + build cache
    into the sandbox).
  - **§16.2 / ADR-022 — explicit StorageClass exposure.** *"Relying on the cluster-default StorageClass
    is treated as a … "* configuration smell; the Helm chart surfaces `storageClassName` for all
    per-Project workspace PVCs, `RWO` default with `RWX` optional (§9.4). The PVC this story provisions
    carries an **explicit** storage class from `Project.workspacePVC.class` (never a silent cluster
    default), sized from `Project.workspacePVC.size`.
  - **§5.1 `Project` CRD row:** `Project.workspacePVC` (`size`/`class`) is the spec this story
    provisions the PVC from; the PVC lives in the Project's Team namespace (§12.1, Story 4.1).
- **ADR:** **ADR-007 (worktree-vs-lock — git-worktree-per-Run + workspace lease chosen)**, arch §9.4
  *Trade recorded* and §22 ADR-007 (*"Global Project lock (serializes); artifact-sync (complexity)"*
  rejected). Do not re-litigate; implement worktree-per-Run + lease.
- **Depends on:**
  - **Story 1.2** (`Project.workspacePVC{Size,Class}` CRD field) and **Story 1.3** (operator scaffold +
    Project reconciler). If the field is not yet generated, wire against the §5.1 `Project` row.
  - **Story 4.1** (squad = namespace tenancy) — the per-`Team` namespace + per-namespace storage boundary
    the PVC is provisioned **inside**; the PVC is reclaimed by the Project/namespace finalizer teardown
    4.1 owns (this story does **not** re-implement Project deletion — see Out of scope).
  - **Story 4.2** (RuntimeClass sandbox) — emits the per-Run sandbox pod into which this story's PVC is
    mounted (§5.2 step 4).
- **Blocks / is consumed by:**
  - **Story 4.5** (per-principal PVC scoping) — **partitions this exact PVC per principal** (a
    per-principal subpath) and destroys the pod (teardown-and-replace). 4.5's AC4/AC5 mount a
    per-principal `subPath` of the PVC this story provisions; if 4.5 lands first against the §9.4
    partition, this story's mount composes the subpath under it. *This story provisions + persists;
    4.5 partitions.*
  - **Story 8.7 / 8.7d** (build browser) — reads the Run's git worktree over this PVC (the completed-Run
    read path snapshots the worktree diff; the live path reads through the shim). This story provides the
    worktree + persistent PVC that read model projects; it does **not** own the read API or its
    per-principal gate (ISI-2166).
  - **Epic 5** (Run reconcile) drives Run start → PVC mount → worktree open, and Run complete → worktree
    drop (PVC retained).

## What the reconciler / pod-assembler does (the §9.4 contract — authoritative)

**A) Provision the persistent PVC once per Project (§9.4, §16.2/ADR-022 — AC1/AC4).**

1. The Project reconciler provisions **one** workspace PVC per Project, from `Project.workspacePVC`
   (`size`, `class`), in the Project's Team namespace (§12.1). The `storageClassName` is **explicit**
   from the spec — never a silent reliance on the cluster-default StorageClass (§16.2/ADR-022). Access
   mode is **`RWO` by default** (worktree-per-Run makes RWO sufficient); **`RWX` opt-in** when the
   storage class supports it (true parallel mounts).
2. The PVC is **bound to the Project**, not to any Run or pod. It is created on first need and **reused
   by every subsequent Run**. It is reclaimed **only** by the Project/namespace finalizer teardown
   (Story 4.1), never by Run completion.

**B) Mount source + build cache into every Run's sandbox (§5.2 step 4 — AC2).**

3. At Run pod-assembly (§8 `Claiming`, §5.2 step 4), the operator mounts the workspace PVC into the
   sandbox so the Run sees **source + build cache**. A Run therefore starts against the **warm cache**
   left by prior Runs on the same Project (dependency caches, build outputs, indexes) — not a cold tree.

**C) Persist across Runs — the crux (§9.4, §9.3 interaction — AC1).**

4. When a Run completes, its sandbox **pod is torn down** (§9.3, Story 4.5). The **PVC is not torn
   down** — pod lifecycle ≠ workspace lifecycle. The next Run on the same Project mounts the **same**
   PVC and sees the retained cache. Tying PVC lifecycle to pod lifecycle (delete/recreate per Run) is
   a **FR-C2 regression**, not a cleanup nicety.

**D) Concurrency: worktree-per-Run + exclusive-write lease (§9.4, ADR-007 — AC3/AC5).**

5. Concurrent Runs on one Project each operate in their **own git worktree** over the shared checkout
   (native git — `git worktree add` per Run, ponytail rung 4), so two Runs writing their working trees
   at the same time **do not clobber** each other. This is chosen over a **global Project lock** (which
   would serialize every Run and kill parallelism, ADR-007 rejected) and over bespoke artifact-sync.
6. Operations that mutate the **shared** checkout/cache (dependency install, index rebuild) take a
   **Project workspace lease** (the same lease primitive as §6.3) so they run **one-at-a-time**.
   Worktree-per-Run isolates *working trees* but **not** the shared cache/index; the lease is the
   defense for the shared resource. Ordinary per-worktree writes stay **parallel** (the lease scopes
   only exclusive-write critical sections, not every write).

## Acceptance Criteria

**AC1 — the workspace PVC persists across Runs; pod teardown does NOT reclaim it (FR-C2, the crux).**
Given a Run writes to the build cache (e.g. a dependency install) and completes — its sandbox **pod
torn down** (§9.3), When a later Run starts on the **same Project**, Then it mounts the **same** PVC and
sees the **retained** cache (a warm hit, not a cold rebuild). A reconciler that deletes/recreates the
PVC on Run completion — tying PVC lifecycle to pod lifecycle — **loses the cache every Run** and is a
**FR-C2 regression**. The PVC is reclaimed **only** by the Project/namespace finalizer teardown (Story
4.1), never by Run completion.

**AC2 — the workspace PVC (source + build cache) is provisioned from spec and mounted into the
sandbox.** Given a `Project` with a `workspacePVC` spec (`size`/`class`), When the Project reconciles
and a Run assembles, Then the operator provisions **one** PVC per Project in the Team namespace with an
**explicit `storageClassName`** from the spec (never a silent cluster-default, §16.2/ADR-022) and the
Run's sandbox **mounts** it (§5.2 step 4) so the Run sees source + build cache. Access mode is **`RWO`
default**, **`RWX` opt-in** when the storage class supports it (§9.4).

**AC3 — concurrent Runs on one Project each get their own git worktree; they don't clobber (FR-C5,
ADR-007).** Given two Runs run **concurrently** on one Project, When each writes its working tree, Then
each operates in its **own git worktree** over the shared checkout and reads back **its own** content —
neither overwrites the other's working state. A single shared working directory across concurrent Runs
(clobber) is a **failure**; so is a global Project lock that **serializes** every Run (ADR-007 rejected
— worktree-per-Run preserves parallelism).

**AC4 — the PVC is bound to the Project and provisioned once, reused by every Run.** Given multiple
Runs (sequential and concurrent) on one Project, When each starts, Then all mount the **same** PVC
(one PVC per Project, not one per Run) in the Project's Team namespace. The PVC is created on first
need and reused; it is not re-provisioned per Run (AC1) and not shared across Projects/namespaces
(§12.1, Story 4.1 boundary).

**AC5 — exclusive-write operations serialize on a Project workspace lease; ordinary writes stay
parallel (§9.4, §6.3).** Given two concurrent Runs each performing an **exclusive-write** operation
against the **shared** cache/index (dependency install, index rebuild), When they run, Then the
Project **workspace lease** (§6.3 primitive) serializes those critical sections — no two run against
the shared cache at once, so it is not corrupted. The lease scopes **only** exclusive-write critical
sections; ordinary per-worktree writes remain **parallel** (AC3). Worktree isolation alone does **not**
cover the shared cache — the lease is the distinct defense for it.

**AC6 — PVC provisioning and worktree/lease lifecycle are crash-safe and idempotent.** Given the
controller crashes mid-provision (PVC created but not recorded, or a worktree opened but not tracked),
When it re-reconciles, Then it converges: the Project has **exactly one** workspace PVC (no duplicate,
no orphan), a Run's worktree is re-derived idempotently, and a workspace lease held by a **dead** Run
is reclaimable (the §6.3 lease is fenced/expiring, not a permanent deadlock). The reconciler reports
workspace/PVC state via `status.conditions` so a half-provisioned workspace is legible. (Envtest —
real API server — with an injected mid-provision crash.)

## Runnable check (the falsification)

`docs/bmad/spikes/bench/workspace-pvc-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check over the *workspace provision + mount + concurrency decisions a Project
reconciler / Run pod-assembler would make across a sequence of Runs on one Project* (some sequential,
some concurrent). It first proves a **naive** reconciler (PVC lifecycle == pod lifecycle; one shared
working directory; no exclusive-write lease) **detectably** violates FR-C2 + the concurrency
invariants — so the harness has real teeth — then proves the §9.4/ADR-007 reconciler holds every
invariant.

```
[model] §9.4/ADR-007 arm (persist + worktree-per-Run + workspace lease):
          PASS AC1 persist-across-Runs (FR-C2) — cache HIT across Runs (PVC persisted)
          PASS AC2 worktree-per-Run        — worktree-per-Run: each Run reads its OWN working tree, no clobber
          PASS AC3 exclusive-write lease    — exclusive-writes serialized by workspace lease — no shared-cache overlap
[model] naive arm (PVC lifecycle == pod lifecycle; one shared working dir; no lease):
          DETECTED AC1 persist-across-Runs (FR-C2) — cache MISS — PVC gen bumped to 2, cold rebuild (FR-C2 violated)
          DETECTED AC2 worktree-per-Run        — CLOBBER — r1 reads 'from-r2', r2 reads 'from-r2' (shared working dir)
          DETECTED AC3 exclusive-write lease    — CORRUPTION — 1 overlapping exclusive-write(s) on shared cache
[model] naive arm       : 3/3 invariant(s) DETECTED as violated
[model] mutation contract (flip ONE defense off in the §9.4 arm — the matching AC must go RED):
          RED     drop PERSISTENCE -> AC1 persist-across-Runs (FR-C2) RED (others GREEN)
          RED     drop WORKTREE    -> AC2 worktree-per-Run RED (others GREEN)
          RED     drop LEASE       -> AC3 exclusive-write lease RED (others GREEN)
[model] PASS — naive detectably violates FR-C2 + concurrency; §9.4 persist + worktree-per-Run + workspace lease hold AC1-AC3; each defense independently load-bearing (mutation-RED).
```

It encodes the three load-bearing invariants over their **distinct** failure vectors (defense-in-depth,
no masking): (a) **persistence** — a cache artifact written by an earlier Run must be visible to a later
Run on the same Project; a reconciler that recreates the PVC per Run (pod-tied lifecycle) misses it
(AC1/FR-C2); (b) **worktree isolation** — two *concurrent* Runs writing the same working-tree path must
each read back **their own** content; one shared working dir clobbers (AC3); (c) **exclusive-write
lease** — two concurrent exclusive-writes on the **shared** cache must not overlap; no lease corrupts it
(AC5). The naive arm's shared working dir is keyed on the **project** (a fixed path), **not** on PVC
identity, so the worktree defect is **not** accidentally masked by the persistence defect (the two
defects are independent, as in production) — the naive arm detects **3/3**. The **mutation contract**
is proven: dropping **persistence** turns AC1 **RED** (others green), dropping **worktree-per-Run**
turns AC2 **RED** (others green), and dropping the **lease** turns AC3 **RED** (others green) — so each
defense is **independently load-bearing**, none decorative. It exits non-zero if the naive arm *stops*
being detected (teeth lost) or the §9.4 arm *ever* violates an invariant.

**AC4 (one PVC per Project, reused) and AC6 (crash-safe idempotent provision + lease reclaim)** are
pinned in prose here and exercised by the operator **envtest** (real API server — AC6, mid-provision
crash injection; AC4, repeated reconcile → single PVC). The model check guards the *provision +
persistence + concurrency shape* (AC1/AC3/AC5), which is the construction-time crux; actual PVC binding,
git-worktree mechanics, and lease fencing under a real kubelet are properties the envtest + a real
storage class observe, not decidable in a model.

## Out of scope (owned elsewhere)

- **Per-principal PVC/cache subpath partitioning + pod teardown-and-replace + residue proof** (**4.5**,
  §9.3/§9.4 per-principal scoping) — 4.5 **partitions this exact PVC per principal** (a per-principal
  subpath the mount uses) and destroys the completed Run's **pod**. This story provisions + mounts +
  persists the PVC and owns worktree/lease concurrency; it does **not** partition per principal.
- **The per-principal build-browser READ gate** (§9.4/ISI-2166, **Story 8.7d**) — the owning-principal
  identity check on the read API (`Run.owningPrincipal == caller.principal`, →404). This story provides
  the worktree + persistent PVC the read model projects; it does **not** own the read API or its gate.
- **Squad = namespace tenancy + Project/namespace finalizer teardown** (**4.1**, §12.1) — the namespace
  the PVC lives in, and the finalizer that reclaims the PVC on Project deletion. This story provisions
  the PVC **inside** that namespace and relies on 4.1's teardown to reclaim it; it does not re-implement
  Project deletion.
- **RuntimeClass-selected per-Run sandbox pod** (**4.2**, §9.1) — emits the pod this story mounts the
  PVC into; the sandbox kernel/syscall boundary is 4.2's.
- **Warm-pool sizing + pod hygiene** (**3.4 / 3.5 / §9.2 / §9.3**) — pod warmth and teardown-and-replace
  are pool concerns; this story is about the **workspace PVC** (which outlives the pool's pods).
- **The `coord` workspace-lease table + reclaim protocol internals** (**§6.3, Epic 2**) — this story
  **consumes** the §6.3 lease primitive for exclusive-write serialization; it does not re-implement the
  lease/fencing mechanism.
- **The build-snapshot artifact shape + live shim read path** (**§9.4/§6.1, Story 8.7**) — the
  completed-Run worktree-diff snapshot and the live read-through-shim path are the build browser's; this
  story provides the worktree they read.
