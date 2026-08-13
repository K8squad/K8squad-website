# Story 8.7e: Console three-pane build browser (tree → diff → code)

Status: in-review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **This is the LAST slice of Epic 8.7** (deps `8.7a → {8.7b, 8.7c} → 8.7d → 8.7e`). 8.7a–c own the git
> projection + the live/completed backends; **8.7d owns the blocking NFR-SEC5 per-principal scoping
> gate** (done — `99f0f05`). 8.7e owns exactly ONE thing the others do not: the **console composition**
> — a strictly read-only three-pane surface that is a *pure consumer* of the 8.7d edge. It adds **no new
> read path, no new backend, no new store**; every guarantee it needs (per-principal `404`, caps,
> existence-hiding, byte-for-byte diffs) it **inherits** by reading only through the 8.7d endpoints.

## Story

As an **operator using the console**,
I want **a strictly read-only three-pane build browser — changed-file tree (left) → per-file diff (center) → code-view toggle — that mirrors mock `06-build-browser` (light + dark), reachable from both the Run detail and artifact inspection**,
so that **I can see exactly what a Run changed in its workspace, live or after teardown, without kubectl, without an IDE, and without ever being able to read another principal's Run or mutate a produced artifact (R6).**

## Context & prerequisites (read first)

- **Design contract:** `docs/bmad/design/build-browser-component-design.md` — §6 (console surface: the
  three-pane read layout, two entry points, live-poll/diff-pull cadence), §1 (scope guard **R6** —
  legibility not an IDE), §3 (the four read endpoints this surface consumes), §7 (observability, owned
  by 8.7d/OBS-BB3), §9 (story slicing — this is the **8.7e** slice).
- **Mock:** `docs/bmad/ux/images/06-build-browser-{light,dark}.svg|png` — FR-F7 (light + dark parity).
- **Architecture:** `03-architecture.md` §13 (Next.js BFF → Go apiserver, **one authorization choke
  point** — the console never touches kube/Postgres/git directly), §9.4 (per-principal worktree read
  model), R6 (read-only console).
- **Depends on (must be landable/mergeable before this story is done):**
  - **8.7d** (`99f0f05`) — the four BFF endpoints + the per-principal `404` gate. This story **consumes**
    them; it does not reimplement the gate, the projection, or the caps.
  - **8.7a/8.7b/8.7c** — the git read-model + live/completed backends behind 8.7d.
  - **8.11** (Run detail) and **8.3** (artifact inspection) — the two entry points that link here. If a
    link target is not yet merged, stub the route and mark its integration test `skip` with a
    `TODO(8.11|8.3)` — the **composition invariants (this story) do not depend on them**.
- **Blocks:** nothing (Epic 8.7 closes here; 8.7f/8.7g are flagged fast-follows).

## Acceptance Criteria

**AC1 — three-pane composition, mock 06.**
Given a Run that modified its workspace, When I open the build browser, Then I see exactly three panes in
reading order — **changed-file tree (left) → per-file diff (center) → code-view (toggle)** — mirroring
mock `06`. And **selecting a changed file in the tree drives the diff pane** (the panes are wired, not
three independent widgets).

**AC2 — reads only through the 8.7d BFF (§13).**
Given any pane, When it fetches data, Then it issues a `GET` to one of the four 8.7d endpoints
(`tree`/`diff`/`file`/`meta`) — **never** git-direct, apiserver-direct, or kube-direct. Because the read
rides the gate, a **per-principal deny Run yields "no build view" and never leaks worktree content**
(bypassing the BFF is the leak this AC forbids).

**AC3 — strictly read-only (R6).**
Given the surface, When it renders, Then it exposes **no** mutating affordance (edit / apply / commit /
save / run / delete / terminal) and issues **only** `GET` — a mutating verb is **structurally absent**
from the component. (The compose/write surface — FR-F5, story 8.5 — is a **different** screen.)

**AC4 — live poll / diff pull; completed static.**
Given a **live** Run (`meta.live == true`), When it renders, Then the surface **polls `{tree, meta}`** on
the existing cadence and **pulls diffs/files on demand** — diffs/files are **never** polled/streamed (no
bespoke SSE channel; diffs are pull). Given a **completed** Run (`live == false`), When it renders, Then
it is **static**, served from the **8.7c snapshot** with **no live pod**.

**AC5 — two entry points, one component.**
Given the build browser, When it is reached from **Run detail (8.11)** or from **artifact inspection
(8.3)**, Then both routes land on the **same** component bound to the **same** `runId` — not two divergent
implementations.

**AC6 — caps surfaced, never unbounded.**
Given a pane response carrying `tooLarge` / `binary` / `truncated`, When it renders, Then it shows the
**explicit marker** (diff "too large", "binary file", truncated-tree notice) — **never** an unbounded
body and **never** a silently-dropped signal. (Passes the 8.7a caps through; does not re-cap.)

**AC7 — degrade legibly, existence-hiding.**
Given a gate `404` (per-principal **deny**) and a genuinely-**missing** Run, When each renders, Then both
show an **identical** neutral "no build view" — the console **never distinguishes** them — and the gate's
id-only `WARN` audit log is **never** surfaced to the operator. And a completed Run whose **snapshot
failed to emit** renders an **explicit** "no build view — snapshot unavailable" (surfaced, **not** a
silent blank / silent `404`; design §7 alert-worthy).

**AC8 — code-view toggle = ref switch.**
Given the code-view toggle, When I flip it, Then it reads `file?path=<path>&ref=run|base` — a `ref` param
on the **same** read endpoint via `GET`, **never** a new/mutating call — and the **default ref is `run`**
(the Run's own commit).

**AC9 — light + dark parity (FR-F7).**
Given the surface, When it renders in **light** and in **dark** (mock 06 both themes), Then the **pane
structure and the control set are identical** — no pane/affordance present in one theme and absent in the
other.

## Runnable falsification check (ships with this story)

`docs/bmad/spikes/bench/build-browser-console-check.py` — a self-contained, no-cluster/no-browser
differential check over the console **composition**. It (i) proves the naive *"render whatever git
returns, add an edit button"* anti-pattern is **DETECTED** violating **every** invariant E1–E9 (real
teeth), then (ii) proves the §6/R6/FR-F7 conformant composition violates nothing — driving **real
renders** (live / completed / no-snapshot / per-principal-deny / missing Runs; light + dark; select-file
+ code-view-toggle interactions) through an executable `render()` with a **BFF spy** that records the
transport + verb of every backend fetch.

Invariants **E1–E9 == AC1–AC9**. Mutation harness (each injects exactly one defect; mapped invariant goes
RED):

| mutation | → | mutation | → |
|---|---|---|---|
| `PANE_SWAP`, `TREE_NOT_WIRED` | **E1** | `DROP_MARKER` | **E6** |
| `GIT_DIRECT` | **E2** | `DENY_DISTINGUISH`, `SILENT_NOSNAP`, `AUDIT_SURFACED` | **E7** |
| `EDIT_AFFORDANCE`, `MUTATING_VERB` | **E3** | `TOGGLE_MUTATES`, `DEFAULT_REF_BASE` | **E8** |
| `STREAM_DIFFS`, `COMPLETED_NEEDS_POD` | **E4** | `THEME_ASYMMETRY` | **E9** |
| `DIVERGENT_ENTRY` | **E5** | `UNBOUNDED_RENDER` | **E6** |

**Verified:** baseline `python3 build-browser-console-check.py` exits `0`; the naive anti-pattern trips
**20 violations across all 9 invariants**; each of the **16 mutations** exits `1` with its mapped tooth
RED, **0 survivors**. The React/Next.js console component is still greenfield in the source repo — this
bench is the **executable spec** it must match (the 8.7a–d pattern).

## Tasks / Subtasks

- [ ] **Task 1 — Three-pane composition + tree→diff wiring (AC1).** Compose `tree` (left) → `diff`
  (center) → `code` (toggle) mirroring mock 06; selecting a tree file sets the diff pane's `path`.
- [ ] **Task 2 — Read only through the 8.7d BFF (AC2).** Every pane fetch is a `GET` to
  `/api/runs/{runId}/build/{tree|diff|file|meta}`. No direct git/apiserver/kube access — the surface
  inherits the per-principal `404` gate; a deny renders as "no build view".
- [ ] **Task 3 — Read-only guard (AC3).** No edit/apply/commit/save/run/terminal control; issue only
  `GET`. Assert (a component test) that no mutating verb is emitted. Compose/write is story 8.5's screen.
- [ ] **Task 4 — Cadence: live poll / diff pull; completed static (AC4).** Poll `{tree, meta}` while
  live on the existing cadence; pull diffs/files on demand. Completed → static from the 8.7c snapshot, no
  pod. No bespoke SSE.
- [ ] **Task 5 — Two entry points, one component (AC5).** Link from Run detail (8.11) and artifact
  inspection (8.3) to the **same** component + `runId`. Stub-and-`skip` a not-yet-merged link target with
  `TODO(8.11|8.3)`.
- [ ] **Task 6 — Caps + legible degrade (AC6, AC7).** Render `tooLarge`/`binary`/`truncated` markers
  (never raw/unbounded). Deny and missing → identical "no build view"; never surface the audit log;
  no-snapshot completed Run → explicit "no build view — snapshot unavailable".
- [ ] **Task 7 — Code-view toggle + theme parity (AC8, AC9).** Toggle = `GET file?ref=run|base` (default
  `run`), never a mutating call. Light + dark identical pane structure + control set (mock 06).
- [ ] **Task 8 — Keep the runnable check green.** Wire the bench into CI alongside the 8.7a–d checks;
  baseline exits 0, every mutation exits 1 with its mapped tooth RED.

## Dev Notes

- **8.7e is a pure consumer — do not reimplement the gate or the projection.** The per-principal `404`
  (ISI-2166 / 8.7d), the byte-for-byte diffs and `tooLarge`/`binary`/`truncated` caps (8.7a), and the
  live/completed dispatch (8.7b/8.7c) all live **behind the four endpoints**. The console's only job is
  to **compose** and **render** them read-only. If you find yourself adding a store, an SSE channel, or a
  git call in the console, stop — that is a different layer's job.
- **Existence-hiding is a UI property here too.** A `404` from the gate is a same-Team peer being denied
  a Run they must not even learn exists. The console MUST render it **identically** to a genuinely-missing
  Run and MUST NOT surface the gate's id-only `WARN` audit log (that log is for the S4 audit /
  enumeration detection, not the operator). Distinguishing deny from missing re-leaks the boundary 8.7d
  spent a whole story closing.
- **Live = poll, diff = pull (design §6).** Tree/meta ride the existing poll cadence; diffs and files are
  fetched **on demand** when a file is selected / the toggle is flipped. **No bespoke SSE channel** — the
  build browser is not a live-stream surface (that is 8.2's EventSource, for Run progress, not diffs).
- **Completed Runs render from the snapshot, not a pod (design §4.2).** The pod is gone at teardown
  (§9.3). A completed Run's three views come from the 8.7c build-snapshot artifact; the RO-reader pod for
  full-tree reads is the **flagged 8.7f** fast-follow — out of scope here.
- **R6 is the whole point.** No edit, no apply, no commit, no run, no terminal. This is legibility, not an
  IDE. The one write surface in Epic 8 is the compose stepper (story 8.5, FR-F5) — a **different** screen
  with its own maintainer-only RBAC gate.
