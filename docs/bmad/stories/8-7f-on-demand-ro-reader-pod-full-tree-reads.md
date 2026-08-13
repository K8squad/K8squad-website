# Story 8.7f: On-demand RO-reader pod for full-tree completed-Run reads (fast-follow, flagged)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **⛔ THIS IS THE ONE THING THE SNAPSHOT PATH CANNOT DO — and it is a FLAGGED, FAST-FOLLOW COST
> SURFACE.** Epic 8.7 ships its whole acceptance on **snapshot-only** (8.7a–e): a completed Run's build
> view — changed-file tree + per-file diffs + changed-file code — is served from the 8.7c build-snapshot
> artifact with **no live pod**. The snapshot has exactly one ceiling: it captures `base...runRef` (the
> **changed set**), so it cannot show an **unchanged** file's content for a completed Run. 8.7f lifts
> **that ceiling and only that ceiling** (design §4.2): for a **full-tree-beyond-changes** read on a
> **completed** Run, and **only when a feature flag is enabled**, the BFF launches a **short-lived,
> read-only workspace-reader pod** that mounts the Project PVC **`RO`** at the Run's commit. Read every
> acceptance criterion literally — a reader that ignores the flag (a cost surface with no off switch),
> launches for reads the snapshot already covers (burns pods for nothing), mounts the PVC **RW** or at
> **HEAD** (a write path / wrong-revision content), runs with a **broader-than-Run** scope or a
> credential that **outlives teardown** (privilege bleed), **never tears down** (a standing dev box),
> **relaunches** instead of reusing (unbounded concurrency), spins a pod for a **non-owner** before the
> gate denies (leaks a peer's worktree **and** pays for it), or emits **no launch metric** / leaks file
> **content** into a log (a blind cost alert / a content-firewall breach) has NOT shipped 8.7f — it has
> turned a cheap legibility feature into an ungoverned cost-and-exfil surface. **This story does not
> block 8.7e; 8.7e ships on snapshot-only.**

## Story

As the **build-browser BFF (serving a completed Run's full-tree read)**,
I want to launch — **only behind a feature flag**, and **only for a full-tree-beyond-changes read** — a
**short-lived, read-only workspace-reader pod** that mounts the Project PVC **`RO`** at the Run's commit,
runs with the **Run's own (revoked-at-teardown) per-principal credential scope**, is **reused** before a
second launch and **torn down after idle**, and whose **launch rate is an alert-worthy cost signal**,
so that **an operator can view an unchanged file's content on a completed Run without a live pod — and
when the flag is off the feature degrades cleanly to snapshot-only — without opening a write path, a
privilege-bleed path, or an ungoverned standing-pod cost.**

## Context & prerequisites (read first)

- **Design contract:** `docs/bmad/design/build-browser-component-design.md` — **§4.2** (the on-demand
  RO-reader: "the BFF may launch an **on-demand read-only workspace-reader pod** that mounts the Project
  PVC **`RO`** at the Run's commit … short-lived, reader-scoped, torn down after idle … **feature-flagged**
  so a v1 can ship on snapshot-only"; the **ponytail** — "don't build it until a full-tree-beyond-changes
  need is proven … Ceiling: snapshot-only can't show an unchanged file's content for a completed Run;
  upgrade path = the flagged RO reader"), **§5** (per-principal scoping — layer 2 tenancy namespace,
  layer 4 "read-only, always … the RO reader mount is RO"; **Secret hygiene** — "the RO-reader pod runs
  with the Run's own (revoked-at-teardown) credential scope, never a broader one"), **§7** (observability
  — "**Alert-worthy: RO-reader pod launch rate (cost signal)**"), **§9** (story slicing — "**8.7f**
  (fast-follow, flagged) on-demand RO-reader pod for full-tree completed-Run reads").
- **Observability (OBS-BB4, this story):** `docs/bmad/design/build-browser-observability-plan.md` **§2.3**
  (RO-reader pod metrics — `reader.launched.total{reason=full_tree, outcome=launched|reused|failed}`,
  `reader.active` gauge, `reader.ttl{outcome=idle_teardown|error}` histogram; "**Reader CPU/mem is *not*
  re-invented here — it rides `k8s.pod.*`** … attributed as **feature operating cost** … never principal
  consumption"), **§3** (RO-reader lifecycle **INFO** launch/teardown logs `{run.id, reader.pod, reason,
  ttl_ms}`; "**Never logged:** file content, diff bodies, blob bytes"), **§4** (the **RO-reader launch
  rate** ticket-grade cost alert), **§5** (the NFR-OBS3 content firewall), and the **OBS-BB4 (8.7f,
  flagged)** line in the coverage table.
- **Architecture:** `docs/bmad/03-architecture.md` **§9.3** (teardown-not-reset — the pod is gone at
  completion, which is *why* a reader must be launched on demand), **§9.4** (per-principal worktree read
  model + per-principal PVC subpath), **§11 / §12** (per-principal BYO credentials + tenancy namespace +
  NetworkPolicy — the reader lives in the Run's Team namespace), **§17.2** (OTel spine + `k8s.pod.*` cost
  attribution).
- **Depends on (must be landable before this story is done):**
  - **8.7c** — the build-snapshot completed path (`live:false`, the default read source). ✅ DONE
    (ISI-2273, `2f8478f`). The reader is the **fallback** *behind* it, not a replacement.
  - **8.7d** — the BFF endpoints + per-principal `404` scoping gate (NFR-SEC5). ✅ DONE (ISI-2274,
    `99f0f05`). The reader launch rides **behind** this gate — a deny is a `404` *before* any launch.
  - **4.5** — teardown-and-replace + per-principal PVC subpath scoping (§9.3/§9.4). ✅ DONE (ISI-2211).
    The reader mounts the same per-principal PVC subpath **RO**.
- **Does NOT block:** **8.7e** (the console three-pane surface). ✅ DONE (ISI-2275). 8.7e renders a
  completed Run from the snapshot; when this flag is off it simply has no full-tree affordance. This
  story is a **fast-follow** — it is not on the Epic-8.7 critical path.

## The on-demand reader path (design §4.2)

A completed Run's pod is **torn down** (§9.3). The **default** completed read is the 8.7c snapshot
(`live:false`, cheap, always available) and covers the **changed set** (`base...runRef`). The one thing
it cannot serve is an **unchanged** file's content. When (and only when) a caller needs that **and** the
feature flag is on, the BFF launches an on-demand reader:

```
                 completed-Run read
                        │
        ┌───────────────┴────────────────┐
   path ∈ changed set            path ∉ changed set (full-tree-beyond-changes)
        │                                │
   8.7c SNAPSHOT                   feature flag?
   (live:false, no pod)      ┌──────────┴──────────┐
                            OFF                     ON
                             │                       │
                   degrade: snapshot-only    reuse live reader? ──yes──▶ REUSED
                   (full_tree:"unavailable")        │no
                   NO pod launched                  ▼
                                             LAUNCH RO-reader pod
                                             · mounts Project PVC RO @ Run's commit
                                             · Run's-own per-principal cred scope
                                             · read-only verbs only
                                             · idle TTL ⇒ teardown ⇒ revoke cred
                                             · launched.total{reason=full_tree} (cost signal)
```

The reader mounts the **same per-principal PVC subpath** (§9.4) the Run used, **RO**, at the Run's frozen
commit, in the Run's **Team namespace** (§12.1, cross-namespace read denied by NetworkPolicy + RBAC). It
runs with the **Run's own credential scope** (§11) — the same principal already owns the Run — **revoked
at teardown**, and it exposes **no write verb**. It is torn down after idle; a second beyond-changes read
for the same Run while the reader is live **reuses** it.

## Acceptance Criteria

**AC1 — the reader is FEATURE-FLAGGED; flag OFF degrades to snapshot-only and launches NOTHING.**
Given a completed Run and a full-tree-**beyond-changes** read, When the feature flag is **off**, Then the
read degrades to a **legible snapshot-only** result (`source:"snapshot-only"`, `full_tree:"unavailable"`)
and **no reader pod is launched** — a v1 ships on snapshot-only. And When the flag is **on**, Then the
reader is available for that read. *(Runnable-check invariant **R1**; `--mutate=FLAG_OFF_LAUNCHES` spins a
pod despite the flag being off and `--mutate=FLAG_OFF_NO_DEGRADE` returns a hard error instead of the
snapshot-only degrade → R1 RED.)*

**AC2 — the reader is ON-DEMAND; the snapshot stays the DEFAULT path.**
Given a read the 8.7c snapshot **already covers** (a path in the changed set), When it is served, Then it
is served **from the snapshot** and launches **nothing**; and only a **beyond-changes** full-tree read
launches (or reuses) a reader. The reader is the fallback, never the default. *(Invariant **R2**;
`--mutate=EAGER_LAUNCH` launches a reader for a changed-set read → R2 RED.)*

**AC3 — the mount is READ-ONLY, at the RUN'S COMMIT.**
Given a launched reader, When it mounts the Project PVC, Then the mount is **read-only** (`readOnly:true`)
and at the **Run's commit** (its frozen `runRef`/commit) — never RW, never HEAD or another ref.
*(Invariant **R3**; `--mutate=MOUNT_RW` mounts read-write and `--mutate=MOUNT_WRONG_REF` mounts at HEAD →
R3 RED.)*

**AC4 — the reader runs with the RUN'S OWN scope, REVOKED at teardown; never broader.**
Given a launched reader, When it is scoped, Then its credential scope **equals the Run's own
per-principal scope** (`run:<id>:principal:<owner>`, §11) — **never** a broader/platform scope — and When
the pod is torn down, Then that credential is **revoked** (it does not outlive the pod). *(Invariant
**R4**; `--mutate=BROADER_SCOPE` runs the reader with a platform scope and `--mutate=CRED_NOT_REVOKED`
lets the credential survive teardown → R4 RED.)*

**AC5 — the reader is SHORT-LIVED; torn down after idle.**
Given a launched reader that has been **idle past its TTL**, When the idle sweep runs, Then the reader is
**torn down** (bounded lifetime, not a standing dev box) and no longer tracked as live. *(Invariant
**R5**; `--mutate=NO_IDLE_TEARDOWN` leaves an idle reader running forever → R5 RED.)*

**AC6 — a live reader is REUSED before a second is launched.**
Given a live reader for a Run, When a **second** beyond-changes read for the **same** Run arrives, Then
the live reader is **reused** (`outcome:"reused"`, idle clock reset) — a second pod is **not** launched —
bounding cost and concurrency. *(Invariant **R6**; `--mutate=NO_REUSE` relaunches a second pod → R6 RED.)*

**AC7 — the per-principal GATE is inherited (deny BEFORE launch) and the mount is READ-ONLY, always.**
Given a full-tree read by a **non-owner** (even a same-Team peer, §5), When the read is authorized, Then
the 8.7d per-principal gate denies it **`404`** **before any launch** — a deny must **never** spin a pod
or mount a peer's worktree. And Given a launched reader, Then its mount exposes **no write verb**
(read-only, always — §5 layer 4). *(Invariant **R7**; `--mutate=LAUNCH_BEFORE_GATE` spins the pod before
the gate denies and `--mutate=READER_WRITE_VERB` adds a write verb to the mount → R7 RED.)* **Note the
seam vs 8.7d:** this AC does not re-implement the gate — it asserts the reader path **inherits** it, and
that the launch is **downstream** of the `Run.owningPrincipal == caller.principal` decision.

**AC8 — OBS-BB4: launch/active/ttl metrics + lifecycle logs + Standing law.**
Given a reader launch, When it is instrumented, Then it emits
`ksquad.buildbrowser.reader.launched.total{reason=full_tree, outcome=launched|reused|failed}` and moves
the `reader.active` **gauge** (inc on launch, **dec on teardown**), and When a reader is torn down, Then
it records a `reader.ttl` **histogram** `{outcome=idle_teardown|error}` and an **INFO** lifecycle log
`{run.id, reader.pod, reason, ttl_ms}`. The launch rate is an **alert-worthy cost signal** (§7 / obs §4),
attributed as **feature operating cost** (`k8s.pod.*`), **never** a principal consumption/billing axis.
And the **Standing law** holds: **no** file content / diff body / blob bytes in **any** signal, and **no**
`model` label on any `ksquad.buildbrowser.*` instrument. *(Invariant **R8**; `--mutate=NO_LAUNCH_METRIC`
drops the launch counter, `--mutate=ACTIVE_NOT_DECREMENTED` never lowers the gauge on teardown, and
`--mutate=LEAK` puts file content + a `model` label into a signal → R8 RED.)*

**AC9 — the runnable check — the deliverable that proves AC1–AC8.**
Given the RO-reader lifecycle, When the self-contained runnable check runs, Then it (i) drives real reads
through an executable `serve()` + `Cluster` reader manager with a metrics/log spy — changed-set vs
beyond-changes, flag on vs off, owner vs same-Team peer, first-launch vs reuse, launch → idle-teardown —
(ii) asserts the reader is flagged (off degrades to snapshot-only, no launch), on-demand (snapshot is the
default), mounts RO at the Run's commit, runs with the Run's own revoked-at-teardown scope, is short-lived
and reused, is denied before launch for a non-owner and exposes no write verb, and emits the OBS-BB4
launch/active/ttl signals under the content firewall, and (iii) is **mutation-proven**: baseline exits
`0`; the naive "standing RW dev box at HEAD, ignore the flag, never tear down, no metrics" anti-pattern
trips **every** invariant R1–R8; and each
`--mutate=<FLAG_OFF_LAUNCHES|FLAG_OFF_NO_DEGRADE|EAGER_LAUNCH|MOUNT_RW|MOUNT_WRONG_REF|BROADER_SCOPE|CRED_NOT_REVOKED|NO_IDLE_TEARDOWN|NO_REUSE|LAUNCH_BEFORE_GATE|READER_WRITE_VERB|NO_LAUNCH_METRIC|ACTIVE_NOT_DECREMENTED|LEAK>`
injects one defect and exits `1` with exactly the mapped invariant RED. It needs **only stdlib** (no
cluster, no PVC, no auth, no network).

## Tasks / Subtasks

- [x] **Task 1 — runnable check (AC1–AC9).** `docs/bmad/spikes/bench/build-browser-ro-reader-check.py`:
  models the reader-pod lifecycle (`Cluster.get_or_launch_reader` / `tick_idle` / `_teardown`), the
  completed-path `serve()` decision (snapshot-vs-reader behind the gate + flag), and an `Obs` spy for the
  OBS-BB4 metrics/logs; drives the scenarios above and ships the `--mutate` harness. **DONE — 8 invariants
  R1–R8, baseline green, the naive anti-pattern trips all 8, all 14 mutants RED on exactly their mapped
  tooth.**
- [ ] **Task 2 — feature flag + on-demand decision (k8squad repo).** Behind a feature flag (off by
  default), extend the completed-read serving path (8.7c/8.7d): a read whose `path` is in the snapshot's
  changed set is served from the snapshot unchanged; a full-tree-**beyond-changes** read, with the flag
  **on**, routes to the reader; with the flag **off**, returns a legible `snapshot-only` /
  `full_tree:"unavailable"` result — **never** a pod launch and **never** a hard error.
- [ ] **Task 3 — the RO-reader pod (launch/reuse).** In the Run's **Team namespace** (§12.1), launch a
  short-lived reader pod that mounts the **per-principal PVC subpath** (§9.4) **`readOnly:true`** at the
  Run's commit, with the Run's **own per-principal credential scope** (§11), exposing **read-only** verbs.
  Reuse a live reader for the same Run before launching a second (`outcome=reused`, reset idle clock). The
  reader must **not** require the Run's original pod (torn down, §9.3).
- [ ] **Task 4 — idle teardown + credential revocation (AC4/AC5).** Track reader idle time; a reader idle
  past its TTL is torn down and its credential **revoked** (revoked-at-teardown, §5 Secret hygiene). Emit
  `reader.ttl{outcome=idle_teardown}` and the teardown INFO log. Decrement `reader.active` on teardown.
- [ ] **Task 5 — OBS-BB4 wiring (AC8).** Emit `reader.launched.total{reason=full_tree, outcome}` +
  `reader.active` gauge + `reader.ttl` histogram; INFO launch/teardown logs `{run.id, reader.pod, reason,
  ttl_ms}`; ride `k8s.pod.*` for CPU/mem (feature operating cost, not principal consumption). Wire the
  **RO-reader launch-rate cost alert** (obs §4). Attach only magnitude/status attributes — no content, no
  `model` label. Do not trip the OBS-BB5 CI firewall gates (Epic 14).
- [ ] **Task 6 — no core coupling (grep gate).** Confirm the reader path adds **no** `AgentRuntime.type`
  branch to the core reconcile/dispatch (the C10 zero-core-change moat) and reuses the 8.7d gate rather
  than re-implementing an authZ path.

## Dev notes

- **The flag is load-bearing, not decoration.** The whole point of the ponytail is that a v1 ships on
  snapshot-only. Flag **off** must degrade to a **legible** snapshot-only result and launch **nothing** —
  a cost surface with no off switch is the AC1 failure (`--mutate=FLAG_OFF_LAUNCHES` /
  `--mutate=FLAG_OFF_NO_DEGRADE`).
- **On-demand, or you burn pods for free.** The snapshot serves the changed set. A reader that launches
  for a read the snapshot already covers (`--mutate=EAGER_LAUNCH`) turns a cheap read into a pod spin. The
  reader is **only** for the unchanged-file-content ceiling.
- **RO at the Run's commit — a write path or a wrong ref is a different feature.** `readOnly:true`
  (`--mutate=MOUNT_RW`) and the Run's frozen commit (`--mutate=MOUNT_WRONG_REF`) are both hard
  requirements. §5 layer 4: "no layer exposes a write verb" (`--mutate=READER_WRITE_VERB`).
- **The Run's own scope, revoked at teardown — never a shortcut to a broader one.** §5 Secret hygiene is
  explicit: the reader runs with the Run's own (revoked-at-teardown) credential scope, never a broader
  one. A platform scope (`--mutate=BROADER_SCOPE`) or a credential that outlives the pod
  (`--mutate=CRED_NOT_REVOKED`) is privilege bleed.
- **Short-lived + reused = bounded cost.** Idle teardown (`--mutate=NO_IDLE_TEARDOWN`) and reuse
  (`--mutate=NO_REUSE`) are what keep the launch-rate cost signal meaningful. The `reader.active` gauge
  must **fall** on teardown (`--mutate=ACTIVE_NOT_DECREMENTED`) or it reports phantom concurrency.
- **Gate before launch — a deny must not cost.** The 8.7d per-principal gate denies a non-owner `404`
  *before* any launch (`--mutate=LAUNCH_BEFORE_GATE`). Spinning a pod for a deny both **pays** for a
  denied request and **mounts a peer's worktree** — the exact NFR-SEC5 boundary 8.7d closed.
- **Launch is a cost signal, never a billing axis.** `reader.launched.total` / `reader.active` /
  `reader.ttl` are the §7 "RO-reader launch rate (cost signal)" alert; CPU/mem rides `k8s.pod.*` as
  **feature operating cost** (obs §0.4), never principal consumption. No content, no `model` label
  (`--mutate=LEAK`).
- **Runnable check:** `python3 docs/bmad/spikes/bench/build-browser-ro-reader-check.py` (green);
  `--mutate=<NAME>` for each tooth.

## Change log

| Date       | Version | Description                                                                                                                                                         | Author       |
|------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------|
| 2026-08-13 | 0.1     | Story authored; runnable check `build-browser-ro-reader-check.py` shipped (8 invariants R1–R8, 14 mutants, naive anti-pattern trips all 8, mutation-proven). ISI-2276. | Dev (Claude) |
