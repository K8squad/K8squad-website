# Story 4.4: Concurrent-Run behavior on a shared Project workspace (worktree-per-Run + per-Project write-lease)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS STORY DEFINES WHAT HAPPENS WHEN TWO+ RUNS SHARE ONE PROJECT WORKSPACE AT ONCE — the
> concurrency contract every "the workspace persists across Runs" story (4.3) quietly assumes is
> already safe (arch §9.4 workspace & concurrency / ADR-007 worktree-vs-lock, OQ5, FR-C5).** The
> naive-correct baseline (PRD/epics) is *"serialize every writer on one per-Project lock"* — correct
> but it kills all concurrency. The architecture **refined** that (ADR-007): concurrent Runs each get
> their **own git worktree** over the shared object store, so ordinary working-tree writes are
> **concurrent and clobber-free by construction** (native git, not invented locking — ponytail rung 4),
> and the **per-Project write-lease is reserved for the writes that genuinely touch *shared* state**
> (dependency install into the shared cache, git index/gc on the shared `.git`, base-ref update). Two
> complementary defenses, not alternatives: **(1) worktree-per-Run** gives concurrency *without*
> corruption for per-Run working-tree edits; **(2) the per-Project workspace lease** (the **§6.3 fenced
> lease**, same primitive as coordination — *reused, not reinvented*) serializes the shared-exclusive
> writers so they can't lose updates. **Reads never take the lease** (concurrent). A reconciler that
> serializes reads, or that lets two Runs write a *shared* checkout with no lease, or that hands every
> Run one shared working tree, is a **concurrency/correctness failure, not a tuning knob**. Read INV-WT,
> INV-LEASE and INV-READ literally.

## Story

As **the Run reconciler / workspace manager running many concurrent Runs on ONE shared Project workspace**,
I want **each concurrent Run to operate in its own git worktree over the shared checkout (so working-tree writes are concurrent and never clobber), reads to stay lease-free (concurrent), and any exclusive write to *shared* workspace state (dependency install, git index/gc, base-ref update) to serialize behind a per-Project workspace lease (the §6.3 fenced lease) — with an opt-in RWX/copy-on-write path for true parallel writes merged back by native git**,
so that **concurrent Runs on one Project never clobber each other or corrupt the shared cache/repo, reads never block, and we get concurrency-without-corruption from native git + one small lease rather than either a global lock that serializes everything or a bespoke merge engine we'd have to prove correct (arch §9.4, ADR-007, OQ5, FR-C5).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-C5** ("Concurrent Runs on the same `Project` workspace SHALL
  have a defined share/lock behavior — mechanism = Architecture, OQ5"), **FR-C2** (the persistent
  Project workspace this story governs concurrency *over*), **OQ5** (routed to Architecture: workspace
  persistence + concurrent-Run share/lock). The **epics baseline** (`04-epics-and-stories.md` §4.4):
  *"per-Project write-lease serializes writers (default); reads concurrent; opt-in copy-on-write overlay
  merged back. Default = serialize-via-lease (simplest correct)."*
- **Spec reconciliation (read this — it is the crux of the story, cf. ISI-2405):** the epics line and
  the architecture are **not** in conflict; the architecture **refines** the epics' *simplest-correct*
  baseline. The epics phrase *"write-lease serializes writers (default)"* as if the coarse per-Project
  lock guards **every** write. **ADR-007 explicitly rejected the "Global Project lock (serializes)"
  alternative** in favor of **git-worktree-per-Run + workspace lease**, precisely because a global lock
  is correct-but-serializes-everything. The honest synthesis this story encodes:
  - The **write-lease still exists and still "serializes writers"** — but only the writers to genuinely
    **shared** state (shared cache, shared `.git` index/gc, base ref). That is the *floor of correctness*
    and the epics' "serialize-via-lease" survives *there*.
  - **Working-tree writes are lifted off the lease** by giving each Run its **own worktree**, so the
    common case (a Run editing files in its checkout) is **concurrent, not serialized**. This is the
    ADR-007 refinement of "default = serialize everything."
  - The epics' *"opt-in copy-on-write overlay merged back"* maps to: the git worktree **is** the
    copy-on-write overlay (shared object store, per-Run working tree + branch/index), **merged back by
    native git** (commit → merge/rebase to the base ref); the **opt-in true-parallel** upgrade is an
    **RWX-capable storage class** (§9.4). We do **not** build a bespoke merge/artifact-sync engine —
    ADR-007 rejected "artifact-sync (complexity)"; **git is the merge engine** (rung 4).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§9.4 — Workspace & concurrency (OQ5, FR-C2/C5).** The authoritative decision this story encodes:
    *"each Run operates in its own git worktree (native git, not invented locking — ponytail rung 4)
    over the shared checkout, so concurrent Runs don't clobber. Operations needing exclusive write
    (dependency install, index rebuild) take a Project workspace lease (same lease primitive as §6.3).
    Default PVC access is RWO with worktree-per-Run; RWX (if the storage class supports it) enables true
    parallelism."*
  - **§6.3 — Lease, liveness, fencing.** The **workspace lease is literally called out here**:
    *"Workspace lease (§9.4): exclusive-write operations (dependency install, index rebuild) take the
    Project workspace lease under the same fence discipline."* So this story **reuses** the §6.3 fenced
    lease (holder + `fence_token` + `lease_expires_at > now()`) — it does **not** invent a new lock. The
    fence closes the zombie-writer race: a GC-paused holder that wakes after its lease expired carries a
    **stale** fence token and its shared write is **rejected** (INV-FENCE), never silent corruption.
  - **ADR-007 (worktree-vs-lock):** *Chosen* = **git worktree per Run + workspace lease**; *rejected* =
    **Global Project lock (serializes)** and **artifact-sync (complexity)**. Do not re-litigate; this
    story implements the chosen option and its two rejected alternatives are exactly the naive arms the
    falsification detects.
  - **§9.4 build-browser / read model** confirms the read path is a **native git projection** (file tree
    = `git ls-tree`, diff = `git diff` worktree-vs-base) — reinforcing that **reads are lease-free** and
    that git, not a bespoke engine, is the diff/merge tool.
- **ADR:** **ADR-007 (worktree-vs-lock)**, arch §9.4 *Trade recorded*. Also composes with **ADR-006**
  (teardown-and-replace, Story 4.5) — orthogonal axis (hygiene between Runs vs concurrency during Runs).
- **Depends on:**
  - **Story 4.3** (Project workspace PVC shape + mount, §9.4, FR-C2) — 4.3 provisions and mounts the
    persistent workspace PVC and establishes the shared checkout this story runs **concurrent worktrees
    over**. *(Assigned in the same Epic-4 wave; if 4.3's PVC/mount shape is not yet final, wire the
    worktree-per-Run mount + the workspace-lease acquisition against the §9.4 contract and gate the
    operator envtest on it — same discipline Story 4.5 used against in-flight 4.3.)*
  - **Story 2.3 (lease renewal) + Story 2.4 (crash-safe reclaim/fencing)** — the **§6.3 fenced lease**
    this story's workspace lease **reuses**. The workspace lease acquires/renews/fences with the **same**
    primitive (holder + fence + `lease>now`); this story does **not** add a second lock design.
  - **Story 1.2** (`Project.workspacePVC` + `Run.owningPrincipal`/`Run` base-ref & worktree fields CRD
    rows, §5.1). If a field is not yet generated, wire against the §5.1 rows.
  - **Story 4.1** (squad = namespace) and **Story 4.5** (per-principal PVC subpath) — the tenancy and
    per-principal partition this concurrency contract lives **inside** (see Out of scope: 4.5 scopes
    *principal↔principal*; 4.4 governs *Run↔Run concurrency* over the shared workspace, same or different
    principals).
- **Blocks / is consumed by:** **Epic 3** Run reconcile (a Run's workspace setup = mount PVC + create
  worktree; a shared-exclusive step = acquire workspace lease), the **build-browser read model** (§9.4,
  Story 8.7d — reads the worktree, lease-free), and the **concurrency chaos gate** (Epic 2.7 — the
  runtime proof that concurrent leased writers never lose an update; §6.3/§6.2 fencing on real PG).

## What the reconciler / workspace manager does (the §9.4 / ADR-007 contract — authoritative)

**A) Worktree-per-Run — concurrency without corruption for working-tree writes (§9.4, ADR-007 — INV-WT / AC1/AC2).**

1. When a Run starts, its sandbox mounts the Project workspace PVC and the manager creates a
   **dedicated git worktree** for that Run (`git worktree add`) over the **shared object store** — a
   per-Run working tree + branch/index, a copy-on-write overlay on the shared `.git`. The Run edits
   files in **its own** worktree.
2. Concurrent Runs therefore write **disjoint** working trees: two Runs editing files at the same time
   **never clobber** each other and **never serialize on a global lock** — this is the whole point of
   ADR-007 (native git over invented locking). No per-file lock is invented.
3. A Run's changes are **merged back** to the base ref by **native git** (commit on the worktree branch
   → merge/rebase to base). We build **no** merge/diff engine (ADR-007 rejected "artifact-sync"); git is
   the merge engine.

**B) Reads are lease-free and concurrent (§9.4 — INV-READ / AC3).**

4. Reads of the shared checkout (file tree walk / `git ls-tree`, `git diff` worktree-vs-base, file read)
   **never take the workspace lease**. N concurrent Runs can read at once; a reader never blocks a reader
   or a writer, and is never blocked by them. Serializing reads on the write-lease is a **defect**, not a
   safe default.

**C) The per-Project workspace lease serializes shared-exclusive writers (§9.4 + §6.3 — INV-LEASE / INV-FENCE / AC4/AC5).**

5. An operation that must write **shared** state — dependency install into the **shared** build cache,
   git **index rebuild / gc / pack** on the shared `.git`, an update to the **base ref** — acquires the
   **per-Project workspace lease before writing**. The lease is the **§6.3 primitive** (one holder;
   `holder + fence_token + lease_expires_at > now()`), scoped by Project. At most **one** holder at a
   time → shared-exclusive writers **serialize**; a second writer **waits** (or is rejected) until the
   lease frees. No unsynchronized concurrent write to shared state (that path loses updates / corrupts
   the shared cache).
6. The lease is **fenced and crash-safe** (§6.3, reused from Story 2.3/2.4): a holder that stops renewing
   loses the lease on expiry; a **zombie** that wakes after expiry carries a **stale** `fence_token`, and
   its shared write is **rejected** (`… AND fence_token = :myFence`). A crashed holder never wedges the
   Project (lease expiry + reclaim), and a slow holder never corrupts shared state after handoff. This
   story **asserts reuse** of the §6.3 fence discipline; it does **not** ship a second lock.

**D) Default vs opt-in (§9.4 — AC6).**

7. **Default (RWO PVC):** worktree-per-Run + workspace-lease-on-shared-writes. Simplest **correct**
   concurrency with real parallelism on ordinary edits; depends on nothing beyond a single-writer PVC.
8. **Opt-in true-parallelism (RWX-capable storage class):** the copy-on-write overlay path where Runs
   truly write in parallel and **merge back by native git**. Enabled **only** when the storage class
   advertises `RWX`; the default path **never depends on RWX**. This is the epics' *"opt-in copy-on-write
   overlay merged back."* No bespoke merge engine either way.

## Acceptance Criteria

**AC1 — each concurrent Run gets its own git worktree over the shared object store (the ADR-007 crux).**
Given two or more Runs active on one Project, When each starts, Then the manager creates a **dedicated
git worktree** for it (`git worktree add`) over the shared `.git`, and each Run's working-tree writes go
to **its own** worktree. A design that hands all concurrent Runs **one shared working tree** is a
**construction failure** (ADR-007 worktree-vs-lock), not a tuning choice.

**AC2 — concurrent working-tree writes never clobber and never serialize on a global lock.**
Given N Runs editing files at the same time, When they write, Then each write lands in its own worktree
with **zero cross-Run clobber** and **without** acquiring any per-Project lock (worktree writes are
lease-free). Merge-back to the base ref is by **native git** (commit → merge/rebase), not a bespoke
engine. (INV-WT.)

**AC3 — reads are concurrent and never take the write-lease (the read-concurrency crux).**
Given N Runs reading the shared checkout concurrently, When they read (file tree / `git ls-tree` / `git
diff` / file read), Then all N proceed **concurrently**; a read **never** acquires the workspace lease
and is **never** blocked by a writer or another reader. A policy that routes reads through the write-lease
(serializing them) is a **defect** (INV-READ), not a safe default.

**AC4 — shared-exclusive writes serialize behind the per-Project workspace lease (the FR-C5 default).**
Given two Runs that both need an exclusive write to **shared** workspace state (dependency install into
the shared cache, git index/gc on the shared `.git`, base-ref update), When they attempt it concurrently,
Then each **acquires the per-Project workspace lease before writing**; at most **one** holds it at a time,
so the writers **serialize** (the second waits/rejects), and **no update is lost** — the shared cache
reflects **every** committed write. Unsynchronized concurrent shared writes (no lease) are a **correctness
failure** (INV-LEASE), not a race we tolerate.

**AC5 — the workspace lease IS the §6.3 fenced lease (reuse, not reinvent); a stale-fence zombie is
rejected.** Given the workspace lease, When it is acquired/renewed/reclaimed, Then it is the **§6.3
primitive** (`holder + fence_token + lease_expires_at > now()`) scoped by Project — **not** a second,
bespoke lock. And given a holder that lost the lease (expiry + reclaim, fence bumped) then **wakes** and
attempts a shared write with its **stale** fence token, When the write is evaluated, Then it is
**rejected** (`… AND fence_token = :myFence`), never silently applied. Crash-safety (a crashed holder
never wedges the Project) and zombie rejection are the §6.3 guarantees this story **consumes** (INV-FENCE).

**AC6 — default is RWO worktree-per-Run + lease; RWX true-parallelism is opt-in and never a default
dependency.** Given a Project on an ordinary **RWO** storage class, When Runs run concurrently, Then the
default worktree-per-Run + workspace-lease path works with **no** RWX requirement. And given a Project on
an **RWX-capable** storage class, When true-parallel writes are opted into, Then Runs write in parallel
and **merge back by native git** (the copy-on-write overlay merged back) — an **optimization**, not a
correctness dependency of the default.

**AC7 — the concurrency contract is crash-safe end to end and legible; no wedged Project, no half-held
lease.** Given a controller/holder crash mid-operation (worktree created but not registered, or lease
acquired but the writer died before renew), When it re-reconciles, Then it converges: an orphaned worktree
is reaped, an expired workspace lease is reclaimed (§6.3 reclaim: fence → confirm → release, fence bumped),
a shared write in flight by the dead holder cannot land after handoff (stale fence), and the manager
reports concurrency/lease state via `status.conditions` so a stuck writer is **legible**, never silently
assumed done. (Envtest — real API server — with an injected mid-operation crash; runtime lost-update proof
on real PG by the Epic 2.7 concurrency chaos gate.)

## Runnable check (the falsification)

`docs/bmad/spikes/bench/concurrent-workspace-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check over the *read/write scheduling decisions a Run reconciler / workspace manager
would make for N concurrent Runs on ONE Project's shared workspace*. It exercises three op kinds under
contention — **READ**, **WT_WRITE** (own working tree), **SHARED_WRITE** (exclusive write to shared
cache / `.git` / base ref) — and proves that the §9.4/ADR-007 policy (worktree-per-Run + per-Project
write-lease on shared writes, reads lease-free, §6.3 fenced) holds all four invariants, while each of
three naive policies breaks a **distinct** one.

```
[model] §9.4 policy   : 0 violation(s); reads 3/3 concurrent, worktree writes 3/3 concurrent (0 clobber), shared writes serialized (holders=1), cache=3/3, fenced=True
[model] mutation contract (each defense independently load-bearing):
          - M-LEASE   (drop workspace lease)       -> INV-LEASE  RED
                shared-exclusive writes NOT serialized: 3 concurrent holders [INV-LEASE]
                2 lost update(s); shared cache = 1/3 (corrupt) [INV-LEASE]
          - M-WORKTREE (drop worktree isolation)   -> INV-WT     RED
                2 working-tree write(s) clobbered in a shared tree [INV-WT]
          - M-READLOCK (put reads under lease)     -> INV-READ   RED
                reads serialized: 1/3 concurrent -> read concurrency lost [INV-READ]
          - M-FENCE    (drop stale-fence reject)   -> INV-FENCE  RED
                stale-fence zombie shared write was ACCEPTED (silent corruption) [INV-FENCE]
[model] PASS — §9.4 worktree-per-Run + per-Project write-lease holds INV-READ/WT/LEASE/FENCE; each of the 4 defenses is independently load-bearing (drop one -> its invariant goes RED).
```

It encodes the four §9.4 invariants over the contended window and proves a **four-way mutation contract**
in which **each defense is independently load-bearing** (no masking — the discipline ISI-2346-F1 /
ISI-2375 warn about): (a) dropping the **workspace lease** on shared writes (`M-LEASE`, keeping
worktrees) turns the arm **RED** on **INV-LEASE** — concurrent unsynchronized shared writes lose updates
and the shared cache reads `1/3` instead of `3/3`; (b) dropping **worktree isolation** (`M-WORKTREE`,
keeping the lease) turns it **RED** on **INV-WT** — concurrent working-tree writes clobber the one shared
tree (the alternative — locking every edit — would instead collapse worktree concurrency to `1`, so the
worktree is load-bearing *for concurrency* either way); (c) routing **reads through the lease**
(`M-READLOCK`) turns it **RED** on **INV-READ** — read concurrency collapses to `1/3`; and (d) dropping
the **stale-fence reject** (`M-FENCE`) turns it **RED** on **INV-FENCE** — a zombie writer that lost the
lease lands a shared write anyway. The compliant policy holds **all four** (reads `3/3`, worktree writes
`3/3` with 0 clobber, shared writes serialized to one holder with `3/3` landed, zombie rejected). It exits
non-zero if the compliant policy ever violates an invariant **or** any mutation fails to turn its target
invariant RED (teeth lost).

**AC7 (crash-safe, legible concurrency) and the runtime lost-update proof** are pinned in prose here and
exercised by the operator **envtest** (real API server — mid-operation crash: orphaned-worktree reap,
lease reclaim, post-handoff stale-fence rejection) and the **Epic 2.7 concurrency chaos gate** (real
PostgreSQL — concurrent leased writers under injected pauses never lose an update; §6.2/§6.3 fencing).
The model check guards the **static scheduling shape** (INV-READ/WT/LEASE/FENCE), which is the
construction-time crux; actual no-lost-update under real concurrency is a property of the fenced lease on
a real store, observed by the runtime gate, not decidable in a model.

## Out of scope (owned elsewhere)

- **Project workspace PVC shape + mount + persistence across Runs** (**4.3**, §9.4, FR-C2) — 4.3
  provisions/mounts the persistent workspace; this story governs **concurrency over** it (worktrees +
  lease). If 4.3's shape is in flight, wire the worktree mount + lease acquisition against the §9.4
  contract.
- **The §6.3 lease/fence primitive itself** (**2.3 lease renewal / 2.4 reclaim-fencing**) — this story
  **reuses** that fenced lease as the per-Project workspace lease; it does not re-implement the lock,
  renewal, or reclaim protocol.
- **Teardown-and-replace + per-principal PVC/cache subpath** (**4.5**, §9.3/§9.4, ADR-006, D7) — the
  *between-Runs hygiene* and *principal↔principal* isolation axis; this story is the *during-Runs
  Run↔Run concurrency* axis. Orthogonal: a per-principal subpath still hosts a shared checkout that
  concurrent Runs of the **same** principal contend over — that contention is 4.4's worktree+lease.
- **Squad = namespace tenancy** (**4.1**, §9.1/§12.1) — the namespace boundary the shared workspace lives
  inside; this story is intra-Project concurrency, not cross-squad isolation.
- **The build-browser per-principal READ gate** (**8.7d**, §9.4/ISI-2166) — the read-path authZ
  (`Run.owningPrincipal == caller.principal`) over the worktree projection; this story establishes that
  reads are **lease-free/concurrent**, 8.7d gates **who** may read.
- **The concurrency chaos gate / lost-update runtime proof** (**Epic 2.7**, §6.2/§6.3) — this story
  builds the worktree+lease concurrency contract; 2.7 attacks it on real PG (concurrent leased writers
  under pauses) and is the runtime hard gate on no-lost-update.
- **Warm-pool sizing / teardown economics** (**3.4/3.5/4.5**) — pool mechanics, not workspace concurrency.
