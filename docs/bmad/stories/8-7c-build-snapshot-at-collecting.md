# Story 8.7c: Build-snapshot artifact at Collecting (build-browser completed path)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **⛔ THIS IS THE COMPLETED HALF OF THE EPIC-8.7 READ FABRIC — the durable snapshot a Run leaves behind
> so its build view outlives the pod.** The architecture is **locked** (design §4.2, §6.1; ADR-021 / ADR-040
> / §6.5): a Run's pod is **torn down at completion** (§9.3), so a completed Run cannot serve tree/diff/file
> from a live shim — it serves them from a **fence-guarded, content-addressed `coord.artifact`
> build-snapshot** emitted at **Collecting**, flagged `live:false`. Read every acceptance criterion
> literally — a snapshot that is written **without** fence discipline (a stale re-run clobbers a fresher
> snapshot), whose bytes are **not** verified against the recorded `sha256`, that **rebuilds** a worse git
> instead of capturing the **8.7a** projection, that serves `live:true`, or that lets an emit-miss surface
> as a **silent `404`** (indistinguishable from "this Run does not exist") has NOT shipped 8.7c — it has
> either corrupted the durable record or turned a legibility gap into a phantom not-found. The emitter
> **calls** `pkg/buildbrowser` (8.7a); it does **not** rebuild the projection (ADR-021 "do not rebuild"
> propagates up).

## Story

As the **build-browser BFF (serving a completed Run)**,
I want the Run to emit a **fence-guarded, content-addressed build-snapshot `coord.artifact`** at
**Collecting** — capturing the **8.7a** tree/diff/file projection into a git-native bundle with
`{kind:"build-snapshot", sha256, uri, meta{base, runRef, commit, fileCount, totalAdditions,
totalDeletions, truncated, traceId}}` — so that a **completed** Run (pod gone) serves tree + diffs +
changed-file code **from the snapshot** with `live:false`, and an emit failure surfaces as a **legible
"no build view" signal, never a silent 404**,
so that **a Run's build view is durable and legible after teardown — reproducible, integrity-verifiable,
and pod-independent — without inventing a store, a diff engine, or an authZ path.**

## Context & prerequisites (read first)

- **Design contract:** `docs/bmad/design/build-browser-component-design.md` — **§4.2** (completed path —
  the build-snapshot `coord.artifact` upsert at Collecting + the `coord.artifact` row shape + the
  snapshot-only v1 target / flagged RO-reader fast-follow), **§4** (the live-vs-completed split; the API
  is identical bar the `live` flag), **§3** (read API surface + fail-safe caps + path safety), **§2**
  (ADR-021 "do not rebuild"), **§9** (story slicing — 8.7c is the completed half).
- **Architecture:** `docs/bmad/03-architecture.md` **§6.1 / §6.4** (Collecting phase + re-entrancy-safe
  reconcile), **§6.3** (claim/lease **fence** — the write discriminator the upsert is guarded by), **§6.5
  / ADR-040** (durable content-addressed `coord.artifact`, the ONE record — no bespoke store), **§9.3**
  (teardown-not-reset — why the completed path exists), **§9.4** (worktree read model), **§17.2** (OTel
  spine).
- **Observability (OBS-BB2, 8.7c half):** `docs/bmad/design/build-browser-observability-plan.md` §2.2
  (snapshot-emission metrics — `snapshot.emit.{total,duration}` + `snapshot.bytes`/`.file_count`
  histograms at Collecting), **§1.2** (the **correction** — a completed read is a BFF-rooted trace with an
  OTel span **link** back to the Run's original `trace_id`, persisted on `meta.traceId`; **not** a forced
  child of the torn-down Run trace), §4/§6 (the **"no build view" coverage SLO** — the headline alert), §5
  (the NFR-OBS3 content firewall).
- **Depends on (must be landable before this story is done):**
  - **8.7a** — pure git read-model (`project_tree` / `project_diff` / `project_file` over a worktree,
    `pkg/buildbrowser`). **This story CAPTURES it; do NOT reimplement it.** ✅ DONE (ISI-2271, 004a7bb).
- **Sibling (independent, parallel-buildable):** **8.7b** (live path — read-only A2A verb on the Run's
  shim, `live:true`). 8.7b and 8.7c both depend only on 8.7a and can be built in parallel.
- **Blocks:** **8.7d** (BFF GET endpoints + per-principal 404 scoping gate — this is the **completed
  backend** it dispatches to when a Run is not `live`). 8.7c serves the payloads; 8.7d owns the
  per-principal authZ gate over them (NFR-SEC5).

## The completed read path (design §4.2)

A Run's pod is **torn down at completion** (§9.3). So a completed Run's build view is served not from a
live shim but from a durable snapshot the Run wrote at **Collecting** (§6.1/§6.4):

```
coord.artifact {
  work_item_id, run_id, kind: "build-snapshot",   # UNIQUE(work_item_id, run_id, kind) -> the upsert key
  sha256,                                          # content hash of the bundle (content-addressed)
  uri,                                             # object-store URI of the bundle
  meta: { base, runRef, commit, fileCount, totalAdditions, totalDeletions, truncated, traceId }
}
```

The bundle is a **git-native** capture of `base...runRef` (a `git bundle`, or the pre-rendered
`name-status` + per-file unified diffs + changed-file blobs — an implementation detail behind the same
API). A completed read deserializes the bundle and serves the identical **8.7a** projection with
`live:false`.

| Read op | Served from snapshot bundle (captured via 8.7a `pkg/buildbrowser`) | Payload |
|---------|---------------------------------------------------------------------|---------|
| `tree`  | `git diff --name-status -M <base>...<runRef>` (+`--numstat`) capture | `{ base, runRef, files[], truncated, live:false }` |
| `diff`  | `git diff -M <base>...<runRef> -- <path>` capture (byte-for-byte)    | `{ path, unifiedDiff, binary, tooLarge, live:false }` |
| `file`  | `git show <runRef>:<path>` capture                                  | `{ path, content, encoding, binary, tooLarge, live:false }` |

> **ponytail (design §4.2):** v1 target = **snapshot-only** (covers tree + diffs + changed-file code view
> — the whole Epic-8.7 acceptance). The on-demand RO-reader pod for full-tree completed reads beyond the
> changed set is the **flagged 8.7f** fast-follow — do NOT build it here.

## Acceptance Criteria

**AC1 — the snapshot is a FENCE-GUARDED upsert on UNIQUE(work_item_id, run_id, kind) (§6.3/§6.4).**
Given a Run reaching Collecting holding a fence at some token, When the build-snapshot is emitted, Then it
is written as a **fence-guarded** `coord.artifact` upsert keyed on `UNIQUE(work_item_id, run_id,
kind="build-snapshot")` — a **stale-fence emitter** (a fence **lower** than the current claim fence, e.g.
a slow re-run) does **not** overwrite a fresher snapshot row, and a **re-entrant** Collecting at the same
fence with identical content is an **idempotent no-op** (exactly one row). *(Runnable-check invariant
**S1**; `--mutate=STALEFENCE` inverts the stale comparison and `--mutate=NOFENCE` drops the guard — either
lets a stale write clobber the fresher row → S1 RED.)*

**AC2 — the snapshot is CONTENT-ADDRESSED (`sha256` + `uri`, verified on read).**
Given the emitted row, When it is written, Then it records a `sha256` that **equals the hash of the bundle
bytes** and an object-store `uri`; and When a completed read serves the bundle, Then the served bytes are
**verified against the recorded `sha256`** — a mismatch is caught, never served blind. *(Invariant
**S2**; `--mutate=SHA_MISMATCH` records a digest that does not match the bytes and `--mutate=NOURI` omits
the uri → S2 RED.)*

**AC3 — `meta` is complete and its counts equal the 8.7a projection.**
Given the row's `meta`, When it is written, Then it carries `{base, runRef, commit, fileCount,
totalAdditions, totalDeletions, truncated, traceId}`, and `fileCount` / `totalAdditions` /
`totalDeletions` / `truncated` **equal the 8.7a projection over `base...runRef`** (not an independent
recount that can drift). `traceId` persists the Run's original `trace_id` for the OBS-BB2 span link (AC7).
*(Invariant **S3**; `--mutate=NOMETA` drops a required meta field → S3 RED.)*

**AC4 — a completed Run serves `live:false` from the snapshot, needing NO pod.**
Given a **completed** Run (pod torn down, §9.3), When the BFF serves `tree`/`diff`/`file`, Then it is
served **from the snapshot bundle** flagged **`live:false`** (the discriminator vs 8.7b's `live:true`), and
the read **never reaches for the (gone) live shim/pod**. *(Invariant **S4**; `--mutate=LIVEFLAG` serves
`live:true` and `--mutate=NEEDPOD` reaches for the torn-down pod → S4 RED.)*

**AC5 — the snapshot CAPTURES 8.7a byte-for-byte; it does not rebuild the projection.**
Given the bundle, When a completed read serves it, Then the tree/diff/file are **identical** to the 8.7a
projection functions (`project_tree`/`project_diff`/`project_file`) run over the same `base...runRef` — and
the `diff` is **byte-for-byte** to raw `git diff` (no re-serialization). The emitter **captures**
`pkg/buildbrowser`; it does not reimplement a worse git (ADR-021 "do not rebuild"). *(Invariant **S5**;
`--mutate=REBUILD` re-serializes the diff and mis-codes a delete in the bundle → the served projection
diverges from the 8.7a oracle → S5 RED.)*

**AC6 — an emit failure is a LEGIBLE "no build view", never a silent 404.**
Given a completed Run whose snapshot emission **failed or was skipped** (no build-snapshot row), When its
owner requests the build view, Then the read returns a **legible `no-build-view` signal** (`runExists:true`
+ a reason) — **not** a bare `404`/empty body that is indistinguishable from "this Run does not exist"
(design §7 "surface it, don't silently 404"). And emission records `snapshot.emit.total{result=failed}`,
feeding the **"no build view" coverage SLO** (obs §4/§6). *(Invariant **S6**; `--mutate=SILENT404` serves
a bare `404` on the emit-miss → S6 RED.)* **Note the seam vs 8.7d:** 8.7d's per-principal `404` is
**existence-hiding for a non-owner**; this AC is about the **owner** of a real, completed Run getting a
legible answer — the two `404`s are different states and must not be conflated.

**AC7 — OBS-BB2: emission metrics + completed-read span LINK (§1.2 correction) + Standing law.**
Given emission at Collecting, When the snapshot is written, Then it emits
`ksquad.buildbrowser.snapshot.emit.{total,duration}` and `snapshot.bytes` / `snapshot.file_count`
(**histograms**, not sums). And Given a completed read, When it is traced, Then it opens a **BFF-rooted
trace with an OTel span *link*** back to the Run's original `trace_id` (read from `meta.traceId`) — **not**
a forced child of the torn-down Run trace (the §1.2 correction; a child under a closed trace fabricates a
span). And the **Standing law** holds: every `ksquad.buildbrowser.*` span attribute is **magnitude/status
only** — **no** file content, **no** diff body, **no** `path`/`bytes_returned` metric label, **no**
`model` label. *(Invariant **S7**; `--mutate=LINKCHILD` forces the read span to be a child of the Run
trace → S7 RED; `--mutate=LEAK` puts bundle content into a span attr → S7 RED.)*

**AC8 — Standing law (Epic-8.7, every touched story).**
Given any `ksquad.buildbrowser.*` instrument this story emits, When telemetry is recorded, Then: (1)
`run.id`/`work_item.id`/`principal.id`/`path`/`bytes_returned` are **never** a metric label (span/log
only); (2) file content, diff bodies, and blob bytes appear in **no** signal (only magnitudes/status +
filename-only paths); (3) **no `model` label** on any `ksquad.buildbrowser.*` instrument; (4)
`snapshot.bytes`/`snapshot.file_count`/`bytes_returned` are **histograms, not monotonic sums**. Read/emit
volume is **legibility telemetry, never a consumption / billing axis** (obs §0, §7). *(Folded into
invariant **S7** — the span-attribute allowlist + content-leak firewall + histogram-not-sum check.)*

**AC9 — the runnable check — the deliverable that proves AC1–AC8.**
Given the build-snapshot implementation, When the self-contained runnable check runs, Then it (i) imports
the **actual 8.7a projection functions**, emits a snapshot over a **throwaway git repo** (base →
add/modify/delete/rename), and serves completed reads from the bundle, (ii) asserts the upsert is
fence-guarded + content-addressed, `meta` matches the 8.7a projection, the completed read is `live:false`
and pod-independent, the served projection matches the 8.7a oracle byte-for-byte, an emit-miss is a
legible `no-build-view` (not a silent 404), and the completed-read span is a BFF-rooted **link** with
magnitudes-only attrs, and (iii) is **mutation-proven**: baseline exits `0`; each
`--mutate=<STALEFENCE|NOFENCE|SHA_MISMATCH|NOURI|NOMETA|LIVEFLAG|NEEDPOD|REBUILD|SILENT404|LINKCHILD|LEAK>`
injects one defect and exits `1` with exactly the mapped invariant RED (no vacuous guard, no
cross-shadowing). It needs **only git + stdlib** (no cluster, no auth, no network, no object store).

## Tasks / Subtasks

- [x] **Task 1 — runnable check (AC1–AC9).** `docs/bmad/spikes/bench/build-snapshot-collecting-check.py`:
  imports and **calls** `git-read-model-check.py`'s `project_tree`/`project_diff`/`project_file` (so
  "captures 8.7a byte-for-byte, not rebuilt" is proven by construction), models the `coord.claim` fence +
  `coord.artifact` upsert, drives emission at Collecting + completed reads over the 8.7a throwaway-repo
  fixture, and ships the `--mutate` harness. **DONE — 7 invariants S1–S7, baseline green, all 11 mutants
  RED on exactly their mapped tooth, zero shadowing.**
- [ ] **Task 2 — snapshot emission at Collecting (k8squad repo).** In the Run reconcile machine's
  **Collecting** phase (§6.1/§6.4), capture the 8.7a projection into a git-native bundle, hash it
  (`sha256`), persist the bundle to the artifact store (`uri`), and **fence-guarded upsert** a
  `coord.artifact{kind:"build-snapshot", sha256, uri, meta{…, traceId}}` row on `UNIQUE(work_item_id,
  run_id, kind)`. The upsert must be **re-entrancy-safe** (§6.4: identical content → no-op;
  `ON CONFLICT` guarded by the current fence) and it must **call `pkg/buildbrowser`** (8.7a), not
  reimplement any git projection. Persist `meta.traceId` = the Run's current `trace_id` (13.1 spine).
- [ ] **Task 3 — completed-read serving path.** Add the completed backend the 8.7d BFF dispatches to when
  a Run is **not** `live`: load the build-snapshot row, **verify** the bundle bytes against the recorded
  `sha256`, deserialize, and serve `tree`/`diff`/`file` from it with `live:false`. Preserve the 8.7a
  `truncated`/`tooLarge`/`binary` caps captured in the bundle (do not re-cap). **No pod dependency** —
  this path must work with the Run's pod torn down.
- [ ] **Task 4 — "no build view" fallback (AC6).** When a completed Run has **no** build-snapshot row
  (emit failed/skipped), return a **legible** `no-build-view` result (`runExists:true` + reason) to the
  Run's owner — never a bare `404`. Keep this distinct from 8.7d's per-principal existence-hiding `404`.
  Wire the `snapshot.emit.total{result=failed}` signal + the coverage-SLO join (completed-success Run ⋈
  build-snapshot artifact) per obs §4/§6.
- [ ] **Task 5 — OBS-BB2 wiring (AC7, AC8).** Emit `snapshot.emit.{total,duration}` +
  `snapshot.bytes`/`.file_count` histograms at Collecting. For a completed read, open a BFF-rooted trace
  with an OTel span **link** to the Run's original `trace_id` from `meta.traceId` (the §1.2 correction —
  **not** a child span). Attach only magnitude/status span attributes; no content, no `model` label, no
  `path`/`bytes_returned` metric label. Do not trip the OBS-BB5 CI firewall gates (Epic 14).
- [ ] **Task 6 — no rebuild, no core coupling (grep gates).** Confirm the emitter (a) captures via
  `pkg/buildbrowser` rather than reimplementing any git projection (the 8.7a single-call-site gate still
  holds), and (b) adds no `AgentRuntime.type` branch to the core reconcile/dispatch (C10 zero-core-change
  moat).

## Dev notes

- **Fence discipline is the write gate.** The single most common way to break AC1 is an unguarded
  `INSERT … ON CONFLICT DO UPDATE` that lets any writer overwrite the row. The upsert must be guarded by
  the **current claim fence** (§6.3): a stale re-run (lower fence) must **not** clobber a fresher
  snapshot. `--mutate=STALEFENCE` / `--mutate=NOFENCE` are the teeth. Re-entrancy (§6.4) rides
  content-addressing: identical bundle → identical `sha256` → no-op.
- **Content-addressed, verified.** Record `sha256 = hash(bundle)` at emit and **re-verify** it when
  serving (`--mutate=SHA_MISMATCH`). This is the same durable `coord.artifact` shape story 2.8 (handoff)
  and 8.3 (artifact inspection) read — **ADR-040 firehose, no bespoke store.** The `uri` is required
  (`--mutate=NOURI`).
- **Capture 8.7a; do not rebuild.** The bundle **is** the 8.7a projection, frozen. Re-parsing and
  re-emitting the diff at emit time (line-ending normalization, a stripped trailing newline) is the
  ADR-021 violation — `--mutate=REBUILD` is the tooth. The check imports 8.7a's functions so the capture
  is structural.
- **`live:false` is the path discriminator.** 8.7b serves the identical shape with `live:true` from the
  pod; this story serves `live:false` from the snapshot. `--mutate=LIVEFLAG` guards it; `--mutate=NEEDPOD`
  guards that the completed path never reaches for the torn-down pod.
- **"No build view" ≠ "not found".** An emit-miss on a real completed Run must be **legible** to its
  owner (`--mutate=SILENT404`). Do **not** conflate it with 8.7d's per-principal `404` existence-hiding —
  that is a non-owner denial; this is the owner's degradation signal. The obs plan makes the coverage a
  **join** of the Run lifecycle against the artifact table (an emit that never *ran* is the failure a pure
  `result=failed` counter misses).
- **Trace attachment is a LINK, not a child (§1.2).** The Run trace closed at teardown; a completed read
  minutes/days later opens a **BFF-rooted** trace and **links** back to the Run `trace_id` from
  `meta.traceId`. Forcing a child (`--mutate=LINKCHILD`) fabricates a span under a dead trace.
  `--mutate=LEAK` guards the Standing-law content firewall.
- **Runnable check:** `python3 docs/bmad/spikes/bench/build-snapshot-collecting-check.py` (green);
  `--mutate=<NAME>` for each tooth.

## Change log

| Date       | Version | Description                                                                 | Author |
|------------|---------|-----------------------------------------------------------------------------|--------|
| 2026-08-13 | 0.1     | Story authored; runnable check `build-snapshot-collecting-check.py` shipped (7 invariants S1–S7, 11 mutants, imports+captures 8.7a projection, mutation-proven). ISI-2273. | Dev (Claude) |
