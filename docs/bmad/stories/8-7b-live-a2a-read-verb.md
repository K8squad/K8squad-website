# Story 8.7b: Live A2A build-read verb on the Run shim (build-browser live path)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **⛔ THIS IS THE LIVE HALF OF THE EPIC-8.7 READ FABRIC — a read surface bolted onto the shim that must
> NOT open a coordination edge.** The architecture is **locked** (design §4.1, §10; ADR-021 / §9.4): a
> live Run serves tree/diff/file by a **read-only A2A query to its shim**, which runs the **8.7a**
> read-model in-worktree — **no new mount, no new transport.** Read every acceptance criterion literally
> — a read verb that routes through `SubmitTask` (a second execution), that bumps the fence / renews the
> lease, that exposes a mutating op, that drops the `live` flag, or that hand-rolls a *worse* git instead
> of **calling 8.7a**, has NOT shipped 8.7b — it has turned a read surface into a coordination/exfil edge.
> The shim **calls** `pkg/buildbrowser` (8.7a); it does **not** rebuild the projection (ADR-021 "do not
> rebuild" propagates up).

## Story

As the **build-browser BFF**,
I want a **read-only A2A query verb on a live Run's shim** — **distinct from task dispatch**, running the
**8.7a** read-model in-worktree and returning tree/diff/file payloads flagged `live:true`, that **never**
touches claim/lease/fence and exposes **no mutating verb** —
so that **a Running Run's build view is served from the pod's already-mounted worktree over the existing
shim channel (no new mount/transport), while the read stays a pure projection that can never become a
coordination or write path.**

## Context & prerequisites (read first)

- **Design contract:** `docs/bmad/design/build-browser-component-design.md` — **§4.1** (live path — the
  read-only A2A query to the shim, "no new mount, no new transport"), **§3** (read API surface + fail-safe
  limits + path safety), **§2** (ADR-021 "do not rebuild"), **§9** (story slicing — 8.7b is the live half).
- **Architecture:** `docs/bmad/03-architecture.md` **§10.1** (the shim/A2A conformance surface — read
  queries are read-only, a conformance requirement), **§9.4** (git-worktree-per-Run read model), **§6.2 /
  §6.3** (claim/lease/fence — the coordination state a read must never touch), **§17.2** (OTel spine),
  **ADR-021 / ADR-007**.
- **Conformance:** the read verb is exposed **read-only** as a **§10.1 / ISI-2114 conformance
  requirement** — it belongs to the same shim surface the 5.6 conformance suite (ISI-2218) gates, and it
  MUST NOT add a runtime-`type` branch to the core (the C10 / zero-core-change moat still holds).
- **Observability (OBS-BB3, 8.7b half):** `docs/bmad/design/build-browser-observability-plan.md` §1.2
  (live) / §8 (apiserver row) — the shim emits the inner `buildbrowser.read.source` span and propagates
  W3C `traceparent` over the read verb so the read span is a **true child of the live Run trace**.
- **Depends on (must be landable before this story is done):**
  - **8.7a** — pure git read-model (`project_tree` / `project_diff` / `project_file` over a worktree,
    `pkg/buildbrowser`). **This story CALLS it; do NOT reimplement it.** ✅ DONE (ISI-2271, 004a7bb).
- **Blocks:** **8.7d** (BFF GET endpoints + per-principal 404 scoping gate — the live backend it
  dispatches to when a Run is `live`). 8.7b and **8.7c** (completed snapshot path) are independent and can
  be built in parallel once 8.7a landed.

## The live read path (design §4.1)

A Run's pod is **torn down at completion** (§9.3). So while a Run is **Running**, its shim + git worktree
are live in the pod and the BFF serves the build view by issuing a **read-only query over A2A** to the
shim. The shim runs the **same** `git diff --name-status` / `git diff` / `git show` commands 8.7a already
proved (it **calls** `pkg/buildbrowser`), and returns tree/diff/file payloads with `live:true`. Read
queries are a **distinct A2A verb** from task dispatch; the shim exposes them **read-only** (a §10.1
conformance requirement) and they **never** touch claim/lease/fence state.

| Read op | Shim runs (via 8.7a `pkg/buildbrowser`) | Payload |
|---------|------------------------------------------|---------|
| `tree`  | `git diff --name-status -M <base>...<runRef>` (+`--numstat`) | `{ base, runRef, files[], truncated, live:true }` |
| `diff`  | `git diff -M <base>...<runRef> -- <path>` (byte-for-byte) | `{ path, unifiedDiff, binary, tooLarge, live:true }` |
| `file`  | `git show <runRef>:<path>` | `{ path, content, encoding, binary, tooLarge, live:true }` |

## Acceptance Criteria

**AC1 — the read verb is DISTINCT from task dispatch (starts no execution).**
Given a live shim, When the BFF issues a build-read query, Then it is handled by a **distinct A2A verb**,
**not** `SubmitTask` — it starts **zero** agent executions and reattaches to no task. A read is never a
dispatch. *(Runnable-check invariant **L1**; mutation `--mutate=DISPATCH` routes the read through
`SubmitTask` → an execution starts → L1 RED.)*

**AC2 — the read NEVER touches claim/lease/fence (read-only coordination state).**
Given the shim holds a lease at some fence, When any build-read (`tree`/`diff`/`file`) is served, Then the
**fence token, lease holder, renewal count, and claim count are byte-identical** before and after — the
read acquires no claim, renews no lease, and bumps no fence. *(Invariant **L2**; `--mutate=FENCE` bumps
the fence and `--mutate=RENEW` renews the lease on a read → L2 RED.)*

**AC3 — no mutating verb exists on the query path (structurally absent).**
Given the build-read verb, When it is driven, Then its op set is **closed to `{tree, diff, file}`** — a
mutating op is **rejected** (`unknown-op`), and the worktree **HEAD is byte-identical** before and after
every read (no read leaves a commit/write). A mutating verb is structurally **absent**, not merely
guarded. *(Invariant **L3**; `--mutate=MUTVERB` exposes an `apply` op that writes to the worktree → the
op is accepted and HEAD changes → L3 RED.)*

**AC4 — live payloads carry `live:true`.**
Given a Running Run, When the shim returns any read payload, Then it carries `live:true` — distinguishing
the live path from the **8.7c** completed-snapshot path (which serves `live:false`), so the BFF and client
can tell a pod-backed read from a snapshot read. *(Invariant **L4**; `--mutate=LIVEFLAG` serves
`live:false` → L4 RED.)*

**AC5 — the shim CALLS 8.7a byte-for-byte; it does not rebuild the projection.**
Given the shim serves a read, When the payload is produced, Then it is **identical** to the **8.7a**
projection functions (`project_tree`/`project_diff`/`project_file`) run over the same worktree — and the
`diff` is **byte-for-byte** to raw `git diff` (no re-serialization). The shim **delegates** to
`pkg/buildbrowser`; it does not reimplement a worse git (ADR-021 "do not rebuild"). *(Invariant **L5**;
`--mutate=REBUILD` hand-rolls a divergent projection — re-serialized diff, mis-coded delete, mangled blob
— → the payload diverges from the 8.7a oracle → L5 RED.)*

**AC6 — OBS-BB3: the read span is a TRUE CHILD of the live Run trace (Standing law).**
Given a live read, When the BFF issues the A2A read verb, Then the apiserver/shim emits the inner
**`buildbrowser.read.source`** span and **propagates W3C `traceparent`** over the read verb, so the read
span's `trace_id` is the **live Run's trace_id** and its parent is the incoming span (a true child, not a
fresh root). And the **Standing law** holds: every `ksquad.buildbrowser.*` span attribute is
**magnitude/status only** (`live`, `truncated`, `too_large`, `file_count`, `bytes_returned`) — **no** file
content, **no** diff body, **no** `path`/`bytes_returned` metric label, **no** `model` label. *(Invariant
**L6**; `--mutate=NOTRACE` opens a fresh root trace → span not a child → L6 RED; `--mutate=LEAK` puts file
content into a span attr → Standing law #2 → L6 RED.)*

**AC7 — Standing law (Epic-8.7, every touched story).**
Given any `ksquad.buildbrowser.*` instrument this story emits, When telemetry is recorded, Then: (1)
`run.id`/`work_item.id`/`principal.id`/`path`/`bytes_returned` are **never** a metric label (span/log
only); (2) file content, diff bodies, and blob bytes appear in **no** signal (only magnitudes/status +
filename-only paths); (3) **no `model` label** on any `ksquad.buildbrowser.*` instrument; (4)
`bytes_returned` is a **histogram, not a monotonic sum**. This story emits only the span attributes of
OBS-BB3 (no metric — read metrics land at the BFF in 8.7d); the read verb adds **no new transport**.
*(Folded into invariant **L6** — the read-span attribute allowlist + content-leak firewall.)*

**AC8 — the runnable check — the deliverable that proves AC1–AC7.**
Given the live-read-verb implementation, When the self-contained runnable check runs, Then it (i) imports
the **actual 8.7a projection functions** and drives a live shim over a **throwaway git repo** (base →
add/modify/delete), (ii) asserts the read verb is distinct from dispatch, is read-only over
claim/lease/fence, exposes no mutating verb, flags `live:true`, matches the 8.7a projection byte-for-byte,
and emits a Run-trace-child read span with magnitudes-only attrs, and (iii) is **mutation-proven**:
baseline exits `0`; each `--mutate=<DISPATCH|FENCE|RENEW|MUTVERB|LIVEFLAG|REBUILD|NOTRACE|LEAK>` injects
one defect and exits `1` with exactly the mapped invariant RED (no vacuous guard, no cross-shadowing). It
needs **only git + stdlib** (no cluster, no auth, no network).

## Tasks / Subtasks

- [x] **Task 1 — runnable check (AC1–AC8).** `docs/bmad/spikes/bench/live-a2a-read-verb-check.py`: a live
  shim model exposing the six task verbs + one distinct read verb, driven over the 8.7a throwaway-repo
  fixture; the read verb **imports and calls** `git-read-model-check.py`'s `project_tree`/`project_diff`/
  `project_file` (so "calls 8.7a, byte-for-byte" is proven by construction); the OBS-BB3 read-span
  builder (traceparent-child + magnitudes-only attrs); and the `--mutate` harness. **DONE — 6 invariants
  L1–L6, baseline green, all 8 mutants RED on exactly their mapped tooth, zero shadowing.**
- [ ] **Task 2 — shim read verb (k8squad repo).** Add the read-only build-query A2A verb to the Run shim:
  a distinct verb (not `SubmitTask`), op ∈ `{tree, diff, file}`, that **calls `pkg/buildbrowser`** (8.7a)
  over the mounted worktree and returns payloads with `live:true`. It must touch **no** claim/lease/fence
  code path (verify by a spy/mock recording zero lease/fence mutations on the read path) and expose **no**
  mutating op. Register it in the **5.6 conformance suite** surface (§10.1) as read-only.
- [ ] **Task 3 — OBS-BB3 wiring.** The read handler starts a `buildbrowser.read.source` span as a child of
  the live Run trace by parsing the W3C `traceparent` the BFF propagates over the read verb; attach only
  the magnitude/status span attributes (`live`, `truncated`, `too_large`, `file_count`, `bytes_returned`).
  No metric here (8.7d owns the BFF read metrics). No content, no `model` label, no `path` label.
- [ ] **Task 4 — no rebuild, no core coupling (grep gates).** Confirm the shim read verb (a) calls
  `pkg/buildbrowser` rather than reimplementing any git projection (the 8.7a single-call-site gate still
  holds), and (b) adds no `AgentRuntime.type` branch to the core dispatch (C10 zero-core-change moat).

## Dev notes

- **Distinct verb, not a dispatch.** The single most common way to break AC1 is to fold the read into the
  task-submission handler (reattach to the run's task and read its workspace) — which starts/reattaches an
  execution and blurs read vs. dispatch. The read is its **own** A2A verb with its own handler; the
  `--mutate=DISPATCH` arm (a read that calls `SubmitTask`) is the guard.
- **Read-only means read-only over coordination state.** The read runs `git` in the worktree but must not
  renew the lease "while it's here", bump the fence, or re-assert the claim. The `--mutate=FENCE` /
  `--mutate=RENEW` arms prove the read path is inert w.r.t. §6.2/§6.3 state.
- **Call 8.7a; do not rebuild.** The read verb is a thin adapter over `pkg/buildbrowser`. Re-parsing and
  re-emitting the diff (line-ending normalization, a stripped trailing newline) is the ADR-021 violation —
  `--mutate=REBUILD` is the tooth. The check imports 8.7a's functions so the delegation is structural.
- **`live:true` is the path discriminator.** 8.7c serves the identical shape with `live:false` from the
  snapshot; the flag is how the BFF/console tell a pod-backed read from a snapshot read (design §3/§4).
- **traceparent is load-bearing.** OBS-BB3 wants the read span to be a **true child** of the live Run
  trace — the shim must propagate the incoming W3C `traceparent`, not open a fresh root. `--mutate=NOTRACE`
  (a root span) is the guard; `--mutate=LEAK` guards the Standing-law content firewall.
- **Runnable check:** `python3 docs/bmad/spikes/bench/live-a2a-read-verb-check.py` (green);
  `--mutate=<NAME>` for each tooth.

## Change log

| Date       | Version | Description                                                                 | Author |
|------------|---------|-----------------------------------------------------------------------------|--------|
| 2026-08-13 | 0.1     | Story authored; runnable check `live-a2a-read-verb-check.py` shipped (6 invariants L1–L6, 8 mutants, imports+calls 8.7a projection, mutation-proven). ISI-2272. | Dev (Claude) |
