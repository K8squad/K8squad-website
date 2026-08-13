# Story 4.5: Teardown-and-replace + per-principal PVC scoping (the residue & cross-principal boundary)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS STORY CLOSES THE RESIDUE / CROSS-PRINCIPAL EXFIL HOLE THAT EVERY OTHER ISOLATION
> BOUNDARY ASSUMES IS ALREADY SHUT (arch §9.3 teardown-and-replace / ADR-006, §9.4 per-principal
> scoping F6/D7, §12.1, NFR-SEC5).** Story 4.1 gave each squad its own namespace; Story 4.2 gave
> each Run its own kernel/syscall boundary and *asserted* "distinct per-Run pod, no reuse" — but
> **4.2 only asserted it; this story is the mechanism that makes it true and the residue proof
> that shows it holds.** Two load-bearing invariants, two distinct defenses (defense-in-depth):
> **(1) teardown-and-replace** — a completed Run's sandbox pod is **destroyed** and the pool
> replenishes a **fresh** pod; a pod is **never reused/reset across Runs or principals**, because
> proving an in-place scrub left *zero* residue (scratch, in-memory secrets, git worktree state,
> poisoned build cache) is a losing game (ADR-006). **(2) per-principal PVC/cache scoping** — the
> persistent Project workspace PVC is partitioned **per principal** (a per-principal subpath), so a
> Run mounts **only its own principal's** source/cache and a **shared** Project workspace can never
> expose one user's data to another agent's Run. A reconciler that resets-and-reuses a pod, or that
> mounts one shared per-Project cache subpath across principals, is a **security failure, not a bug
> ticket**. Read AC2 and AC4 literally.

## Story

As **the Run reconciler / sandbox-pool manager running many principals' Runs on one shared Project workspace**,
I want **every completed Run's sandbox pod to be destroyed and replaced by a fresh pooled pod (never reset-and-reused), and the persistent Project workspace PVC to be scoped per principal (a per-principal cache/source subpath) so a Run mounts only its own principal's partition**,
so that **no residue (scratch, in-memory secrets, git worktree state, poisoned build cache) bleeds from one Run into the next, and a shared Project workspace never leaks one user's source or secrets into another agent's Run — the guarantee is enforced by pod destruction + subpath isolation, not by a scrub we can't prove clean (arch §9.3/§9.4, ADR-006, D7, NFR-SEC5).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **NFR-SEC5** (no reuse/residue across Runs; workspace scoped per
  principal), **FR-C6** (sandbox hygiene), **FR-C2** (persistent Project workspace across Runs),
  **D7** (per-principal isolation of workspace/secrets within a squad), **F6** (warm-pool hygiene —
  PRD Challenger). This story is the **F6/D7 mechanism** the arch routed to §9.3/§9.4.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§9.3 — Hygiene: teardown-and-replace (F6/D7, FR-C6, NFR-SEC5).** The authoritative decision this
    story encodes: *"After a Run completes, its sandbox pod is destroyed and the pool replenishes a
    fresh pod from the template… warm-pool economics survive because 'warm' is a property of the pool
    (async replenish), not of an individual reused pod. **A sandbox is never reused across Runs or
    principals.**"* (ADR-006, teardown-vs-reset). **Not** an in-place scrub.
  - **§9.4 — Workspace & concurrency, per-principal scoping (F6/D7):** *"the build cache is partitioned
    per principal (separate subpath/volume)… Workspace access is scoped per principal, not merely per
    Project — a shared Project workspace never exposes one user's secrets/source to another agent's
    Run."* The Project workspace PVC **persists across Runs** (FR-C2) — the partition scopes
    **cross-principal** access; it does **not** reset a principal's own cache (same-principal reuse is
    the point of a persistent cache).
  - **§12.1 — Tenancy boundary:** *"Within a Team namespace, per-principal isolation of Secrets is
    enforced by RBAC + the per-principal workspace scoping (§9.4), so multiple users in one squad don't
    cross-access credentials."* This story **is** the "per-principal workspace scoping" half of that
    sentence; Story 4.1 laid the RBAC/namespace half.
  - **§9.2 — Warm pool.** Replenishment is **async** — a claimed pod's replacement is minted in the
    background so the pool stays warm without ever handing one pod to two Runs. This story consumes the
    pool's replenish path; it does **not** re-tune the sizing curve (ISI-2113, locked).
  - **§5.1 `SandboxPool` / `Project` CRD rows:** `SandboxPool` (pool size + template + hygiene) drives
    teardown-and-replace; `Project.workspacePVC` (size/class) is the PVC this story partitions per
    principal. `Run.owningPrincipal` (§11, r20/§12.4 `initiatedByUserId`) is the **principal key** the
    subpath and the read gate are scoped on.
- **ADR:** **ADR-006 (teardown-vs-reset — teardown-and-replace chosen)** and **ADR-007
  (worktree-vs-lock)**, arch §9.4 *Trade recorded*. Do not re-litigate; implement teardown-and-replace.
- **Depends on:**
  - **Story 4.2** (RuntimeClass-selected sandbox isolation) — 4.2 emits a **distinct per-Run pod** and
    *asserts* "no reuse across Runs/principals"; **this story owns the teardown mechanism + residue
    proof that makes that assertion true** (4.2 AC3 explicitly defers the residue proof to 4.5).
  - **Story 4.1** (squad = namespace tenancy) — the per-`Team` namespace and per-namespace PVC boundary
    the per-principal partition lives **inside**; per-principal scoping composes *on top of* the
    namespace boundary (4.1 = squad↔squad; 4.5 = principal↔principal within a squad).
  - **Story 4.3** (Project workspace PVC shape + mount, §9.4) — 4.3 provisions/mounts the workspace PVC;
    **this story partitions it per principal** (the subpath the mount uses). If 4.3's PVC shape is not
    yet final, wire the subpath against the §9.4 partition and gate envtest on it.
  - **Story 1.2** (`SandboxPool` hygiene + `Project.workspacePVC` + `Run.owningPrincipal` CRD fields)
    and **Story 1.3** (operator scaffold). If a field is not yet generated, wire against the §5.1 rows.
- **Blocks / is consumed by:** **Epic 5** (Run reconcile drives complete→teardown→replenish), **Epic
  6.5** (memory scope per Team/principal composes with this workspace scope), the **build-browser
  per-principal read gate** (§9.4/ISI-2166, Story 8.7d — the *read-path* specialization of this same
  per-principal boundary), and **Epic X.2** (the **residue/reuse blast-radius test** that *proves at
  runtime* no state bleeds across Runs or principals — the hard gate this story's boundary must satisfy).

## What the reconciler / pool manager does (the §9.3/§9.4 contract — authoritative)

**A) Teardown-and-replace on Run completion (§9.3, ADR-006 — AC1/AC2/AC3).**

1. When a Run reaches a **terminal state** (`Succeeded`/`Failed`/`Cancelled`; the §8 lifecycle),
   its sandbox pod is **destroyed** — deleted, not reset. There is **no in-place scrub-and-reuse
   path** for the untrusted agent path. (Unlike 4.2's `runc` `trustedDev` escape, §9.3 grants **no**
   reuse escape: *"a sandbox is never reused across Runs or principals"* is absolute.)
2. The pool **replenishes asynchronously** — a **fresh** pod from the template is created to restore
   the warm count (§9.2). "Warm" is a property of the **pool** (async replenish), not of an individual
   reused pod, so warm-claim latency (S9/NFR-PERF1) survives teardown-and-replace.
3. A given sandbox pod is **bound to exactly one Run** over its lifetime. The next Run claims a
   **different** (fresh) pod. No pod is handed to two Runs, and never across two principals.

**B) Per-principal workspace/cache scoping (§9.4 F6/D7 — AC4/AC5).**

4. The persistent Project workspace PVC (§9.4, Story 4.3, FR-C2) is partitioned by a
   **per-principal subpath** derived deterministically + collision-safely from `Run.owningPrincipal`
   (e.g. `.../cache/<principal>-<short-hash(principal-id)>`, mirroring 4.1's DNS-safe + UID-hash
   discipline: a raw principal id can collide or contain unsafe chars; the hash disambiguates and a
   principal-rename does not strand the partition). Build cache and any per-principal scratch live
   under **that** subpath (`separate subpath/volume`, §9.4).
5. A Run mounts **only its own principal's subpath** (`subPath` mount / per-principal sub-volume). It
   **cannot** read another principal's cache/source partition — a **shared per-Project cache subpath
   mounted across principals is the exfil hole this story closes** (§9.4, §12.1 per-principal Secret
   isolation). Cross-principal exposure is a **construction failure**, not a runtime check.
6. The partition scopes **cross-principal** access only — it does **not** defeat FR-C2: a principal's
   **own** cache **persists across that principal's own Runs** (that is the point of a persistent
   workspace cache). The subpath isolates one principal from another; it is not a per-Run reset.
7. **Relationship to the read-path gate (defense-in-depth, not a substitute).** The per-principal
   **cache partition is defense-in-depth against residue/poisoning** — it is **not** the build-browser
   read-path gate. The read gate is the **owning-principal identity check**
   (`Run.owningPrincipal == caller.principal`, §9.4/ISI-2166, Story 8.7d), which covers the git
   tree/diff/file read path the cache partition does not. This story owns the **storage/mount**
   partition; 8.7d owns the **read API** gate. Both enforce the same per-principal boundary at
   different layers.

## Acceptance Criteria

**AC1 — teardown-and-replace is the default; a completed Run's pod is destroyed, not reset.**
Given a Run reaches a terminal state, When hygiene runs, Then its sandbox pod is **destroyed**
(deleted), and the pool **replenishes a fresh pod** asynchronously to restore the warm count (§9.2).
There is **no in-place scrub-and-reuse** path for the sandbox. Warm-pool economics survive because
"warm" is a property of the pool (async replenish), not of a reused pod (NFR-PERF1 unaffected).

**AC2 — a sandbox pod is never reused across Runs or principals (the §9.3 absolute, the crux).**
Given two Runs (sequential, same or different principals, same Project), When their sandboxes exist,
Then each is bound to its **own distinct pod** — no pod is bound to two Runs, and **no pod is ever
handed from one principal's Run to another's**. A reconciler that resets-and-rebinds one pod across
Runs is a **construction failure**, not a runtime check (ADR-006).

**AC3 — no pod residue crosses Runs (the residue proof this story owns).**
Given a fresh pod claimed by a Run, When the Run reads its sandbox, Then it carries **no residue
authored by any prior Run** (scratch files, in-memory secrets, git worktree state, poisoned build
cache) — least of all a **different principal's** residue. Teardown-and-replace makes this true **by
construction** (the prior pod is gone); an in-place scrub cannot prove it (ADR-006 rationale). Proven
at runtime by the Epic X.2 residue test (NFR-SEC5).

**AC4 — workspace/cache access is per-principal, not per-Project (the D7 crux, fail-closed).**
Given the persistent Project workspace PVC, When a Run mounts it, Then it mounts **only its own
principal's subpath** (per-principal partition derived from `Run.owningPrincipal`). A Run **cannot
read another principal's cache/source partition**. A **shared per-Project cache subpath mounted across
principals** — which would let principal B read principal A's cached artifacts/secrets — is a
**construction failure** (§9.4, §12.1 per-principal Secret isolation, NFR-SEC5).

**AC5 — the per-principal partition is deterministic, collision-safe, and preserves same-principal
reuse (FR-C2 intact).** Given `Run.owningPrincipal`, When the subpath is derived, Then it is
**deterministic** (same principal → same subpath) and **collision-safe** (distinct principals → distinct
subpaths, via a stable hash; a principal-rename does not strand the partition). And the partition scopes
**cross-principal** access only — a principal's **own** cache **persists across that principal's own
Runs** (a persistent workspace cache, FR-C2); scoping is **not** a per-Run or same-principal reset.

**AC6 — teardown-and-replace is crash-safe and idempotent; no orphaned pod, no leaked partition.**
Given the controller crashes mid-teardown (pod deleted but replenishment not yet recorded, or vice
versa), When it re-reconciles, Then it converges: a completed Run never re-binds its destroyed pod, a
missing warm pod is replenished (no double-replenish, no leaked orphan pod holding a prior Run's
residue), and the per-principal partitions are neither duplicated nor cross-wired. The reconciler
reports hygiene state via `status.conditions` so a half-torn-down sandbox is legible, never silently
assumed reused. (Envtest — real API server — with an injected mid-teardown crash.)

**AC7 — the residue/reuse blast-radius gate is satisfiable at runtime.**
Given the boundary this story builds, When Epic X.2's residue/reuse test attacks it (a Run writes a
marker secret/scratch, completes; a later Run — a **different principal** on the **same Project** —
attempts to read that marker via the pod or the workspace cache), Then the read **fails** (destroyed
pod + per-principal subpath), proving no state bleeds across Runs or principals (NFR-SEC5). This story
builds the boundary; X.2 attacks it and is the hard gate on the mechanism.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/teardown-scoping-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check over the *hygiene + workspace-mount decisions a Run reconciler / pool manager
would make across a sequence of completed Runs on one Project by different principals*. It first proves
a **naive** policy (in-place reset + reuse one pod across Runs, one shared per-Project cache subpath)
**leaks residue and crosses principals** — so the harness demonstrably detects a boundary violation —
then proves the §9.3/§9.4 policy (teardown-and-replace + per-principal subpath) **holds** every
invariant.

```
[model] AC5 keys      : distinct principals -> distinct subpaths (alice-2bd806c97f0e != bob-81b637d8fcd2), deterministic
[model] AC5 subpath   : per-principal partition preserves same-principal cache reuse (FR-C2 intact), collision-safe hash
[model] naive policy  : 7 residue/scoping violation(s) -> DETECTED
          - pod warm-0 reused across Runs ['r1', 'r2', 'r3'] [AC2 teardown-and-replace]
          - r2(p2): read POD residue from r1(p1) [CROSS-PRINCIPAL] [AC3]
          - r3(p1): read POD residue from r1(p1) [same-principal] [AC3]
          - r3(p1): read POD residue from r2(p2) [CROSS-PRINCIPAL] [AC3]
          - r2(p2): read PVC/cache residue from r1(p1) [CROSS-PRINCIPAL leak] [AC4]
          - r3(p1): read PVC/cache residue from r2(p2) [CROSS-PRINCIPAL leak] [AC4]
          - only 0/3 completed Runs replenished a fresh pod [AC1]
[model] §9.3/§9.4     : 0 violations; 3 Runs -> 3 distinct pods, 3 fresh replenishments, 0 cross-principal reads
[model] PASS — naive detectably leaks residue + crosses principals; §9.3 teardown + §9.4 per-principal scoping hold AC1-AC5.
```

It encodes the AC1–AC5 invariants over **two distinct leak vectors** (defense-in-depth): (a) **pod
residue** — scratch/in-mem secrets/worktree state/poisoned cache **living in the pod**, defended by
**teardown-and-replace** (destroy the pod; a reused/reset pod is modeled as retaining residue per the
ADR-006 "can't prove the scrub clean" rationale) — a Run reading residue authored by a **prior Run**
(esp. a different principal) is a violation (AC3), and a pod bound to two Runs is a violation (AC2),
and fewer replenishments than completed Runs is a violation (AC1); (b) **PVC/cache residue** on the
**persistent** Project workspace PVC, defended by the **per-principal subpath** — a Run reading a
subpath entry authored by a **different principal** is a violation (AC4), while a principal reading its
**own** prior cache is **not** flagged (AC5 / FR-C2 preserved), and distinct principals resolve to
distinct, deterministic subpaths (AC5). The **mutation contract** is proven: removing **teardown**
(keeping per-principal subpath) turns the compliant arm **RED** (pod reuse + cross-principal pod
residue), and removing the **per-principal subpath** (keeping teardown) turns it **RED**
(cross-principal cache leak) — so **neither defense is decorative**; each is independently
load-bearing. It exits non-zero if the naive policy *stops* leaking (teeth lost) or the §9.3/§9.4
policy *ever* violates an invariant.

**AC6 (crash-safe idempotent teardown) and AC7 (runtime residue/reuse blast-radius)** are pinned in
prose here and exercised by the operator **envtest** (real API server — AC6, mid-teardown crash
injection) and **Epic X.2's residue/reuse test on a real cluster** (AC7, NFR-SEC5). The model check
guards the *static hygiene + scoping shape* (AC1–AC5), which is the construction-time crux; actual
zero-residue is a property of pod destruction + subpath isolation observed by the runtime test, not
decidable in a model.

## Out of scope (owned elsewhere)

- **RuntimeClass-selected per-Run sandbox** (**4.2**, §9.1) — 4.2 emits the distinct per-Run pod and
  *asserts* no reuse; this story owns the **teardown mechanism + residue proof** behind that assertion.
- **Squad = namespace tenancy + per-namespace PVC boundary** (**4.1**, §12.1) — the squad↔squad
  boundary the per-principal partition lives inside; this story is principal↔principal within a squad.
- **Project workspace PVC shape + mount + git-worktree concurrency** (**4.3 / 4.4**, §9.4, ADR-007) —
  4.3 provisions/mounts the PVC and the per-Run worktree; this story **partitions it per principal**.
- **The build-browser per-principal READ gate** (§9.4/ISI-2166, **Story 8.7d**) — the owning-principal
  identity check on the read API (`Run.owningPrincipal == caller.principal`, →404 existence-hiding),
  the *read-path* specialization of this same per-principal boundary; this story owns the
  **storage/mount** partition (defense-in-depth), not the read API.
- **Warm-pool sizing curve + replenish constants** (**3.4 / 3.5 / ISI-2113**, §9.2) — this story
  consumes the async replenish path; the sizing policy is locked.
- **The residue/reuse blast-radius test itself** (**Epic X.2**, S4, NFR-SEC5) — this story builds the
  boundary; X.2 attacks it at runtime and is the hard gate on the mechanism.
