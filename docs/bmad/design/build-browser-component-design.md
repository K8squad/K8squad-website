---
title: Build Browser — Component Design Spec
issue: ISI-2148
owner: Architect (Winston)
status: build-ready
epic: 8.7 (+ 8.11 links, 11.4 CI artifacts)
architectureRefs: [§9.4, §13, §6.1, §6.3, ADR-021, ADR-007, FR-K1, FR-K2, FR-C6, NFR-SEC5, OQ17]
date: 2026-08-11
supersedes: none (elaborates 03-architecture.md §9.4/§13 into an implementable contract)
revisions:
  - r1 (2026-08-11, ISI-2148): initial build-ready component design
  - r2 (2026-08-11, ISI-2166): resolved review B1/F7 — pinned the **per-principal** visibility model
    (§5 Decision + Layer 1 `Run.owningPrincipal == caller.principal`); fixed AC3 to cite the correct
    proof; added the §8.7 authZ-predicate runnable check; routed the new S4 cross-principal-same-Team
    read-authZ case (`05-testing-strategy.md` §6.5). Unblocks Story Writer on 8.7d. No projection-core
    change; arch §9.4 tightened in lockstep (arch r15)
---

# Build Browser — Component Design (ISI-2148)

> **Purpose.** The architecture (`03-architecture.md` §9.4/§13, ADR-021) already decided *what* the
> build browser is — a **read-only projection of the Run's git worktree**, git as the diff engine,
> per-principal scoped at the BFF. This document pins that decision down to a **buildable contract**:
> the read API surface, the live-vs-completed read paths, the completed-Run snapshot artifact shape,
> the exact scoping enforcement points, telemetry hooks, and acceptance criteria — so the Story Writer
> can slice Epic 8.7 into stories and implementers/reviewers have one reference. **No new architectural
> decision is made here; nothing below reopens a locked decision.**

## 1. Scope & non-goals

**In scope (FR-K1/K2):** for a given Run, show (a) a **file tree** scoped to what that Run changed,
(b) a **per-file diff** (worktree branch vs `Project.repo` default ref), (c) a **code viewer** for any
file at the Run's commit — all linked to the producing Run and (once Epic 11 lands) its PR/CI state.
Extends artifact inspection (Epic 8.3): existing `coord.artifact` blobs + handoff summaries stay
reachable from the same surface.

**Non-goals (scope guard R6 — legibility, not an IDE):** no editing, no writes to the workspace, no
running code, no terminal, no cross-Run/cross-principal browsing, no general file-system browser
outside the Run's changed set + explicit file reads. **The browser is strictly read-only and never a
coordination path** (§7.3/§7.5 no-P2P argument applied to the console).

## 2. The core insight (ADR-021, do not rebuild)

Each Run already works in its **own git worktree** over the Project workspace PVC (§9.4, ADR-007).
Therefore the three views are **native git projections** — we build **no diff engine, no VFS, no
snapshot format of our own**:

| View        | Mechanism                                            |
|-------------|------------------------------------------------------|
| File tree   | `git diff --name-status <base>...<runRef>` (changed set) + `git ls-tree` for full-tree fallback |
| Per-file diff | `git diff <base>...<runRef> -- <path>` (unified diff; server emits, client renders) |
| Code viewer | `git show <runRef>:<path>` (file at the Run's commit) |

`<base>` = merge-base of the Run's worktree branch and `Project.repo` default ref (three-dot diff, so
the view is *the Run's changes*, not drift on the base since the Run started). `<runRef>` = the Run's
worktree branch tip (or its snapshot commit for completed Runs, §4).

## 3. Read API surface (BFF → apiserver, read-only)

All endpoints are **GET-only**, served by the Next.js BFF (§13, ADR-013), principal-scoped (§5). No
mutating verbs exist on this surface — a design invariant, not a config.

```
GET /api/runs/{runId}/build/tree
    → { runId, base, runRef, live: bool, files: [ { path, status: A|M|D|R, additions, deletions,
                                                    renamedFrom? } ], truncated: bool }
GET /api/runs/{runId}/build/diff?path=<path>
    → { runId, path, status, unifiedDiff: string, binary: bool, tooLarge: bool, oldSha, newSha }
GET /api/runs/{runId}/build/file?path=<path>&ref=run|base
    → { runId, path, ref, content: string|null, encoding: utf8|base64, binary: bool,
        tooLarge: bool, sizeBytes }
GET /api/runs/{runId}/build/meta
    → { runId, workItemId, teamId, live: bool, commit, base, prUrl?, ciStatus?, artifacts: [...] }
```

- `live` distinguishes the two read paths (§4). Clients poll `tree`/`meta`; diffs/files are on-demand.
- **Limits (fail-safe, not fail-open):** per-file diff cap (default 512 KiB → `tooLarge:true`, no body),
  file cap (default 2 MiB), tree cap (default 5 000 entries → `truncated:true`). Binary files return
  `binary:true` with no diff/content body. These bound the read cost of a hostile or pathological Run.
- **Path safety:** `path` is validated against the Run's changed set (for diff) or resolved through
  `git show`/`git cat-file` (never through raw FS `open`), so `../` traversal and symlink escape out of
  the worktree are structurally impossible — git refuses paths outside the tree object.

## 4. Two read paths — live vs completed

A Run's pod is **torn down at completion** (§9.3, teardown-not-reset). So the source of the git
projection differs by Run state; the API contract above is identical for both (`live` flag aside).

### 4.1 Live Run — via the shim (pod has the workspace mounted)
The BFF issues a **read-only query over A2A** to the Run's shim, which runs the git commands in-worktree
and returns tree/diff/file payloads. This reuses the existing shim channel (§10) — **no new mount, no new
transport.** Read queries are a distinct A2A verb from task dispatch; the shim exposes them **read-only**
(a conformance requirement, §10.1/ISI-2114) and they never touch claim/lease/fence state.

### 4.2 Completed Run — snapshot artifact + on-demand RO reader
At Collecting (§6.1, §6.4), the Run emits a **build-snapshot artifact** (fence-guarded `coord.artifact`
upsert, so it is re-entrancy-safe and content-addressed):

```
coord.artifact {
  work_item_id, run_id, kind: "build-snapshot",   # UNIQUE(work_item_id, run_id, kind)
  sha256,                                          # content hash of the bundle
  uri,                                             # object-store URI of the bundle
  meta: { base, runRef, commit, fileCount, totalAdditions, totalDeletions, truncated }
}
```

The bundle is a **git-native** capture (a `git bundle` of `base..runRef` **or** the pre-rendered
`name-status` + per-file unified diffs + changed-file blobs) — chosen at build time; the bundle format
is an implementation detail behind the same API. For **full-tree** code viewing of a completed Run
beyond the changed set, the BFF may launch an **on-demand read-only workspace-reader pod** that mounts
the Project PVC **`RO`** at the Run's commit (short-lived, reader-scoped, torn down after idle). Default
path = the snapshot artifact (cheap, always available); the RO reader is the fallback for full-tree
reads and is **feature-flagged** so a v1 can ship on snapshot-only.

> **ponytail:** v1 target = **snapshot artifact only** (covers tree + diffs + changed-file code view,
> which is the whole Epic 8.7 acceptance). The RO-reader pod is a fast-follow behind a flag — don't
> build it until a full-tree-beyond-changes need is proven. Ceiling: snapshot-only can't show an
> unchanged file's content for a completed Run; upgrade path = the flagged RO reader.

## 5. Per-principal scoping — the security crux (FR-K1, FR-C6, NFR-SEC5, D7)

> **Decision (ISI-2166, Architect — resolves review B1 / F7).** The visibility model is **per-principal,
> not Team-legible.** Even two principals in the *same Team/Project* cannot read each other's Run build
> view. This is forced, not chosen: the build browser surfaces **raw worktree content** (diffs/files
> that may hold a Run's BYO secrets, "Secret hygiene" below), and the architecture's *locked* invariant
> (arch §9.4/§11/§12, D7, NFR-SEC5) is that "a shared Project workspace never exposes one user's
> secrets/source to another agent's Run," with credentials **BYO per-principal**. A Team-legible browser
> would be the exfil path *around* that locked per-principal Secret isolation. So the browser inherits
> the per-principal boundary — this **applies** the locked decision to the read API, it does not reopen
> it. Team-legibility of *outcomes* (Run status, PR/CI, explicitly-published artifacts) lives on other,
> Team-scoped surfaces (Run detail §6, discussion room, dashboards) — not on this raw-content surface.

Enforcement is **layered**, and every layer fails closed:

1. **BFF authZ gate (primary — the per-principal mechanism).** Every build endpoint resolves the
   caller's principal + Team scope (§13) and authorizes `runId` **before** any git/shim/reader call,
   checking **both**:
   (a) the Run is within the caller's Team scope, **and**
   (b) `Run.owningPrincipal == caller.principal` — the Run was initiated by *this* principal.
   Either check failing → `404` (not `403` — don't confirm existence). Check **(b) is the mechanism**
   that denies a same-Team principal B reading principal A's Run; Layers 2–3 below do **not** cover the
   git tree/diff/file read path (Layer 2 = Team↔Team; Layer 3 = cache residue). `Run.owningPrincipal`
   is the initiating-principal identity **already recorded** for BYO-credential scope and per-principal
   metering attribution (§11, arch §9.4) — no new field, just an authZ check that reads it.
2. **Tenancy namespace.** The Run's worktree/shim/reader live in the Run's **Team namespace** (§12.1);
   cross-namespace read is denied by NetworkPolicy + RBAC, independent of the BFF.
3. **Per-principal cache partition (§9.4).** The build cache is partitioned per principal (separate
   subpath/volume), so even within a shared Project workspace the browser can only surface the
   requesting principal's own Run residue — a shared Project workspace **never** leaks one user's
   source/secrets/build residue to another. Verified by the S4 blast-radius reuse/residue case (cache
   residue) **and** the S4 cross-principal-same-Team read-authZ case (the Layer-1 gate, NFR-SEC5).
4. **Read-only, always.** No layer exposes a write verb; the shim read query and RO reader mount are
   both RO. A compromised BFF still cannot mutate the workspace through this surface.

**Secret hygiene:** diffs/files are raw workspace content and *may* contain a secret a Run wrote to
disk. The browser does **not** add new exposure — the same principal already owns that Run — but the
snapshot bundle inherits the artifact store's at-rest encryption + per-principal ACL (§11), and the
RO-reader pod runs with the Run's own (revoked-at-teardown) credential scope, never a broader one.

## 6. Console surface (§13, Epic 8.7 / 8.11 / 11.4)

- Three-pane read layout: **changed-file tree** (left) → **diff** (center) → **code view** toggle;
  mirrors mock `06-build-browser` (light + dark, FR-F7). Reachable from the Run detail (Epic 8.11
  "build output" tab links here) and from artifact inspection (Epic 8.3).
- **PR/CI linkage (Epic 11.4, deferred until Epic 11):** `meta.prUrl` / `meta.ciStatus` render as a
  header strip when SCM sync (§5.4) has mirrored them; absent otherwise. Build browser does **not**
  depend on Epic 11 to ship — it degrades to git-only.
- Live Run: tree/meta poll on the existing cadence; no bespoke SSE channel needed (diffs are pull).

## 7. Observability (hand to Observability agent, §17.2)

- Each build-read request emits a span child of the Run's trace (`buildbrowser.tree|diff|file`, with
  `runId`, `live`, `cacheHit`, `bytesReturned`, `truncated`).
- Snapshot emission at Collecting emits `buildbrowser.snapshot.bytes` / `.fileCount` metrics.
- **Metric, not billing** (NFR-OBS3): read volume is legibility telemetry, never a consumption axis.
- Alert-worthy: RO-reader pod launch rate (cost signal), snapshot-emit failures (a completed Run with
  no snapshot degrades to "no build view" — surface it, don't silently 404).

> **Concrete plan (ISI-2165):** the above is operationalized into `ksquad.buildbrowser.*` metrics,
> per-read spans, and alerts/SLOs in **`build-browser-observability-plan.md`** (sibling), aligned to the
> arch §17.2 metering spine + `04-observability-plan.md`. Two corrections to note: (1) completed-Run
> reads use an OTel **span *link*** to the Run (not a child span — the Run trace closed at teardown);
> (2) the "no build view" alert is a **coverage SLO** (completed-success Run ⋈ build-snapshot artifact),
> not just an emit-error counter. NFR-OBS3 is enforced by a CI firewall gate, not just documented.

## 8. Acceptance criteria (Epic 8.7 gate + one runnable check)

1. For a Run that added/modified/deleted files, `tree` returns exactly the changed set with correct
   `status` and add/del counts; `diff` matches `git diff <base>...<runRef> -- <path>` byte-for-byte.
2. A **completed** Run (pod gone) serves tree + diffs + changed-file code view from the snapshot
   artifact with no live pod.
3. **Scoping (per-principal — ISI-2166 decision):** even within a shared Team/Project, principal A
   cannot read principal B's Run build view — every `tree`/`diff`/`file`/`meta` endpoint returns `404`
   (existence-hiding), because Layer 1 requires `Run.owningPrincipal == caller.principal`. Verified by
   the S4 blast-radius suite's **cross-principal-same-Team read-authZ** case (NFR-SEC5;
   `05-testing-strategy.md` §6.5), with a positive control (owner reads own Run → `200`).
   **This is the blocking security gate.**
4. No endpoint accepts a mutating verb; `path` traversal (`../`, absolute, symlink-escape) is rejected.
5. Oversize file/diff/tree return the capped `tooLarge`/`truncated` markers, never an unbounded body.
6. **Runnable check (ponytail):** a self-contained test that (i) builds a throwaway git repo with a
   base commit + a worktree branch that touches 3 files (add/modify/delete), (ii) drives the same
   `git diff --name-status`/`git diff`/`git show` commands the server uses, and (iii) asserts the
   tree/diff/file projection matches — proving the git-projection contract without any cluster. Lives
   next to the read-model implementation; fails if the projection logic breaks.
7. **Runnable check for the scoping gate (ISI-2166, ships with 8.7d):** the Layer-1 decision is a pure
   predicate `authorizeRead(caller, run) → allow | deny(404)` — unit-testable with no cluster. A
   self-contained test asserts: owner (`run.owningPrincipal == caller.principal`, same Team) → `allow`;
   **same-Team non-owner → `deny(404)`**; cross-Team → `deny(404)`. This co-locates the AC3 assertion
   with the code (closes review I4 for the security-critical AC), while the full cross-principal `404`
   over the live BFF is exercised by the S4 case (§6.5).

## 9. Story slicing hint for Epic 8.7 (Story Writer)

- **8.7a** git read-model service (tree/diff/file over a worktree) + the §8.6 runnable check — no
  cluster, no auth; pure git projection. *Foundation, unblocks everything.*
- **8.7b** live path: shim read-only A2A verb (§10.1 conformance) wired to 8.7a.
- **8.7c** completed path: build-snapshot artifact emission at Collecting (§6.1 upsert) + reader.
- **8.7d** BFF endpoints + per-principal scoping gate (§5 Layer 1: `Run.owningPrincipal == caller.principal`)
  + the authZ-predicate runnable check (§8.7) + the S4 cross-principal-same-Team read-authZ case (§6.5).
  (**security gate — NFR-SEC5; ISI-2166 resolved: per-principal model, AC3 stands**).
- **8.7e** console three-pane surface (light+dark, mock `06`), Run-detail + artifact-inspection links.
- **8.7f** (fast-follow, flagged) on-demand RO-reader pod for full-tree completed-Run reads.
- **8.7g** (with Epic 11) PR/CI header strip.

Dependencies: 8.7a → {8.7b, 8.7c} → 8.7d → 8.7e. 8.7d carries the blocking NFR-SEC5 gate.
