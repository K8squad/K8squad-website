# Story 8.7a: Pure git read-model (tree/diff/file) + runnable check (build-browser foundation)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **⛔ THIS IS THE EPIC 8.7 FOUNDATION — every higher layer builds on this one tested projection.** The
> architecture is **locked** (ADR-021 / §9.4): the build browser's three views are **native git
> projections**, not an invented diff engine, VFS, or snapshot format (design §2 "do not rebuild"). Read
> every acceptance criterion literally — a read-model that *parses and re-emits* a diff instead of
> returning `git diff` **byte-for-byte**, that miscounts add/del, that silently drops a delete, or that
> streams a hostile multi-MiB blob into the response instead of a `tooLarge`/`truncated` marker has NOT
> shipped the ADR-021 contract — it has rebuilt a worse git and opened a DoS/exfil edge. **No cluster, no
> auth, no shim** — this slice is pure and self-contained by construction.

## Story

As the **build-browser backend**,
I want a **pure git read-model** that projects a Run's worktree into `tree` / `diff` / `file` views **directly from `git diff --name-status`, `git diff`, and `git show`** — bounded fail-safe by size/entry caps and binary markers — with a **self-contained runnable check** that drives real git and asserts the projection matches byte-for-byte,
so that **every higher build-browser layer (live 8.7b, completed-snapshot 8.7c, BFF scoping gate 8.7d, console 8.7e) builds on one tested projection whose fidelity to git and boundedness against a hostile Run are proven at construction time — without any cluster, auth, or shim.**

## Context & prerequisites (read first)

- **Design contract:** `docs/bmad/design/build-browser-component-design.md` — **§2** (the ADR-021 core
  insight — the three git commands, three-dot `<base>...<runRef>`, "do not rebuild"), **§3** (read API
  surface + the fail-safe limits + path safety), **§8** AC1/AC4/AC5 (projection fidelity + caps) and
  **§8.6** (the one runnable check this story must ship), **§9** (story slicing — 8.7a is the foundation).
- **Architecture:** `docs/bmad/03-architecture.md` **§9.4** (git-worktree-per-Run read model), **ADR-021**
  (build-browser read model), **ADR-007** (worktree-vs-lock — why each Run has its own worktree branch).
- **Epics:** `docs/bmad/04-epics-and-stories.md` — the **8.7a** row + the "Epic 8.7 story slicing"
  subsection (`8.7a → {8.7b, 8.7c} → 8.7d → 8.7e`) + the **OBS-BB1 fold-in** and the **Standing law**.
- **Depends on:** nothing — this is the foundation. It calls only `git` on a worktree; it does **not**
  reach the coord DB, the shim, the BFF, or any credential/Secret path.
- **Blocks:** **8.7b** (live A2A read verb runs this projection in-worktree), **8.7c** (completed-Run
  snapshot captures the same projection), **8.7d** (BFF endpoints call it behind the per-principal gate),
  and transitively **8.7e**. Every one of them reimplementing the projection is the failure this story
  prevents — they **call** it, they do not rebuild it.

## The read-model contract (ADR-021, §2)

`<base>` = merge-base of the Run's worktree branch and the Project default ref. `<runRef>` = the worktree
branch tip (or its snapshot commit for a completed Run, 8.7c). The **three-dot** form makes the view *the
Run's changes*, not base drift since the Run started.

| View          | Git command (the server runs exactly this)                          |
|---------------|---------------------------------------------------------------------|
| File tree     | `git diff --name-status -M <base>...<runRef>` (+ `--numstat` counts) |
| Per-file diff | `git diff -M <base>...<runRef> -- <path>` (unified diff, emitted verbatim) |
| Code viewer   | `git show <runRef>:<path>` (blob at the Run's commit)               |

## Acceptance Criteria

**AC1 — tree is EXACTLY the git changed set with correct status.**
Given a worktree branch with a base commit and add/modify/delete changes, When `tree` is asked, Then it
returns **exactly** the paths of `git diff --name-status -M <base>...<runRef>` — no unchanged file, no
dropped or mis-coded entry — each carrying `status ∈ {A, M, D, R}` matching git's code (and `renamedFrom`
for a rename). A deleted file is reported `D`, never `M`; an unchanged file (e.g. `keep.txt`) **never**
appears. *(Runnable-check invariant **G1**; mutation `--mutate=STATUS` mis-codes the delete → G1 RED.)*

**AC2 — add/deletion counts equal `git diff --numstat`.**
Given the changed set, When counts are attached, Then each file's `additions`/`deletions` equal
`git diff --numstat -M <base>...<runRef>` (a binary file's counts are `-`/`-` → `null`/`null`). *(Invariant
**G2**; `--mutate=COUNT` zeros the counts → G2 RED.)*

**AC3 — unified diff matches `git diff` BYTE-FOR-BYTE.**
Given a changed text path, When `diff` is asked, Then `unifiedDiff` is **identical, byte-for-byte**, to
`git diff -M <base>...<runRef> -- <path>` — the server emits git's output verbatim (client renders); no
normalization, re-wrap, trailing-newline munging, or re-serialization. *(Invariant **G3**; `--mutate=DIFF`
strips a trailing newline → G3 RED against the raw-git oracle.)*

**AC4 — file content is the blob `git show` returns.**
Given a changed path, When `file` is asked for `ref=run`, Then `content` is **identical** to
`git show <runRef>:<path>` — the blob at the Run's commit — with `encoding: utf8` (or `base64` for a
binary, per AC7). Path resolution is through `git show`/`git cat-file`, **never** raw FS `open`, so `../`
traversal and symlink escape out of the worktree are structurally impossible (git refuses out-of-tree
paths). *(Invariant **G4**; `--mutate=CONTENT` mangles a byte → G4 RED.)*

**AC5 — oversize diff / file / tree return capped markers, never an unbounded body.**
Given a hostile or pathological Run, When a read exceeds a cap, Then the read-model returns a **bounded**
result: a per-file diff over **512 KiB** → `tooLarge:true` with **no body**; a file over **2 MiB** →
`tooLarge:true` with `content:null`; a changed set over **5 000 entries** → `truncated:true` (body capped
to the first 5 000). No cap may be fail-open — an unbounded body is a DoS edge, not a feature. *(Invariants
**G5/G6/G7**; `--mutate=DIFFCAP|FILECAP|TREECAP` each ignore one cap → the mapped invariant RED.)*

**AC6 — binary files return `binary:true` with no body.**
Given a binary changed file, When `diff`/`file` is asked, Then the result is `binary:true` with **no**
`unifiedDiff` and **no** `content` (never streamed as decoded text). Binary is detected from git's
`Binary files … differ` hunk (diff) and a NUL byte in the blob (file). *(Invariant **G8**; `--mutate=BINARY`
emits a body → G8 RED.)*

**AC7 — OBS-BB1 span attributes are magnitudes/status only (Standing law).**
Given the read-model produces a projection, When it records telemetry, Then the current read **span**
carries **only** `ksquad.buildbrowser.truncated`, `.too_large`, `.file_count`, and `.bytes_returned` — all
as **magnitudes/status**. The foundation emits **no metric** (metrics land with 8.7c/8.7d/8.7f — no
big-bang) and adds **no new transport**. And the **Standing law** holds:
1. `run.id` / `work_item.id` / `principal.id` / `path` / `bytes_returned` **never** a **metric label**
   (span/log/exemplar only);
2. file **content**, diff **bodies**, blob **bytes** are in **no** signal — only magnitudes, status
   (A/M/D/R, binary, truncated, too_large), and filename-only paths (span/log only);
3. **no `model` label** on any `ksquad.buildbrowser.*` instrument (its absence is load-bearing — a metric
   with no `model` and no per-principal label cannot be aggregated into a consumption bill, NFR-OBS3);
4. `bytes_returned` is a **histogram, not a monotonic sum** (a sum reads like a meter).
*(Invariant **G9**; `--mutate=LEAK` puts content into a span attr → G9 RED.)*

**AC8 — the runnable check (design §8.6) — the deliverable that proves AC1–AC7.**
Given the read-model implementation, When the self-contained runnable check runs, Then it (i) builds a
**throwaway git repo** with a base commit + a worktree branch touching **3 files** (add / modify / delete),
(ii) drives the **same** `git diff --name-status` / `git diff` / `git show` commands the server uses, and
(iii) asserts the `tree`/`diff`/`file` projection matches an **independent raw-git oracle** — plus the
cap/binary/OBS cases (AC5–AC7). It needs **only git + stdlib** (no cluster, no auth, no network), lives
next to the read-model, and **fails if the projection logic breaks**. The check is **mutation-proven**:
baseline exits `0`; each `--mutate=<STATUS|COUNT|DIFF|CONTENT|DIFFCAP|FILECAP|TREECAP|BINARY|LEAK>` injects
one defect and exits `1` with exactly the mapped invariant RED (no vacuous guard, no cross-shadowing).

## Tasks / Subtasks

- [x] **Task 1 — runnable check (AC1–AC8).** `docs/bmad/spikes/bench/git-read-model-check.py`: throwaway
  repo fixture (base → add/modify/delete worktree branch), the projection functions
  (`project_tree`/`project_diff`/`project_file`/`build_span_attrs`) as the executable spec, the raw-git
  oracle assertions (G1–G4), the cap/binary/OBS cases (G5–G9), and the `--mutate` harness. **DONE — 9
  invariants, baseline green, all 9 mutants RED, zero shadowing.**
- [ ] **Task 2 — Go read-model service (AC1–AC7).** Implement `pkg/buildbrowser` (k8squad repo) mirroring
  the projection: shell the three git commands over a worktree, apply the 512 KiB / 2 MiB / 5 000 caps +
  binary markers, emit the unified diff verbatim (no re-serialization), and record the OBS-BB1 span attrs.
  Port `git-read-model-check.py`'s assertions into a Go table-driven test over a throwaway repo (the §8.6
  runnable check in the production language). Reference: this story + the check as the executable spec.
- [ ] **Task 3 — no leakage upward.** Confirm 8.7b/8.7c/8.7d **call** `pkg/buildbrowser` rather than
  reimplementing any git projection (grep gate: exactly one `git diff --name-status` / `git show` call
  site in the codebase).

## Dev notes

- **Three-dot is load-bearing.** `<base>...<runRef>` diffs from `merge-base(base, runRef)` to `runRef` —
  it shows the Run's changes, not drift on the base since the Run branched. The check asserts the fixture's
  `merge-base == base` so the semantics are exercised, not assumed.
- **Byte-for-byte means byte-for-byte.** The single most common way to break AC3 is to `.decode()` →
  transform → `.encode()` the diff (line-ending normalization, a stripped trailing newline, a re-wrapped
  hunk header). Emit git's bytes verbatim; the `--mutate=DIFF` arm is the guard.
- **Caps are fail-safe, not fail-open.** Every cap returns a *marker*, never a partial-then-unbounded body.
  The check sizes real fixtures past 512 KiB / 2 MiB and a synthetic 5 250-entry changed set past the tree
  cap to prove the bound bites.
- **Path safety comes free from git.** Because content is resolved through `git show <runRef>:<path>` (a
  tree-object lookup), not FS `open`, `../` and symlink-escape are impossible — git refuses out-of-tree
  paths. (The BFF-level `path`-against-changed-set validation is 8.7d's; this layer inherits git's refusal.)
- **Runnable check:** `python3 docs/bmad/spikes/bench/git-read-model-check.py` (green);
  `--mutate=<NAME>` for each tooth.

## Change log

| Date       | Version | Description                                                        | Author |
|------------|---------|--------------------------------------------------------------------|--------|
| 2026-08-13 | 0.1     | Story authored; runnable check `git-read-model-check.py` shipped (9 invariants, mutation-proven). ISI-2271. | Dev (Claude) |
