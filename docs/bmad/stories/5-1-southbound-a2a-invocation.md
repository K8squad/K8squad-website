# Story 5.1: Southbound A2A invocation — the core-side dispatch client (the moat seam)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE CONTROL-PLANE HALF OF THE A2A SHIM SEAM (arch §10.1/§8, FR-D1, NFR-EXT2/I4).**
> When a Run reaches `Claiming → Running`, the core must *reach the agent*. This story is **how the core
> reaches it**: it **submits an A2A task**, **streams SSE progress into the Run's event stream**, and
> **collects artifacts** — through **only the six A2A MUST-verbs + the Agent Card, with no other lateral
> protocol and no runtime-`type` special-casing**. That last clause is the entire moat: *"a conformant
> runtime drops into any squad with zero core changes"* (S5/NFR-EXT1, C10). The load-bearing invariant is
> **"the core sees one interface regardless of which runtime it is talking to"** — a dispatch path that
> forks on `runtime.type` or reaches a runtime-native side channel (OpenClaw's gateway, Hermes' native
> API, a second mount, direct pod exec) re-introduces per-runtime coupling and **breaks the seam that is
> the product's whole extensibility claim**. Not a style preference — a **correctness/architecture
> failure**. Read AC1 literally.

## ⚠️ Scope reconciliation — 5.1 vs ISI-2114 vs 5.2/5.3/3.x (read first, they interlock on purpose)

The originating issue (ISI-2213) says *"the core submits an A2A task, streams SSE progress into
`run_events`, collects artifacts — using only A2A + the Agent Card."* Several neighbours touch the same
seam; this story owns exactly **one side of it — the core's A2A *client***, and consumes the rest:

| Concern | Owned by | This story does |
|---|---|---|
| The **shim's** six-verb contract, SSE event schema, Agent-Card JSON schema, conformance suite C1–C10, reference OpenClaw shim | **ISI-2114** (`design/agent-shim-interface-spec.md`) | **consumes** the contract; this is the core-side counterpart the shim is conformant *to* |
| **Generating** the Agent Card from the `Agent` CRD (skills/model/capability/credential metadata) | **Story 5.2** (ISI, §7.2) | **reads** the card to negotiate; does not generate it |
| **Pinning** the A2A/MCP wire rev behind `pkg/a2a@rev` so upstream churn never reaches core | **Story 5.3** (§10.2, `internal/protocol/versions.go`) | speaks the **internal stable interface**; the adapter maps to the wire |
| **Assembling** the context envelope (work-item/goals/memory/trust-tiers) + the token budget | **Story 3.6 / 5.9** (§8.5) | **transports** the envelope as the task's system/context input; does not assemble or budget it |
| The **reconcile state machine** (Claiming→Running→Collecting), durable `reconcile_step`, dispatch re-entrancy | **Story 3.1** (§6.4) | **is invoked at** `Claiming→Running`; reuses its deterministic-id + marker re-entrancy for the *submit* step |
| **Death detection + retry/backoff** on a Run that dies mid-flight | **Story 3.2** (§8) | maps A2A `failed`/silent-death → the 3.2 failure edge; does not own detection or backoff |
| **Rate-limit** `rate_limited` signal + `Paused(rate_limited)` + fallback | **Stories 5.10 / 3.7 / 5.11** (§10.1/§8) | routes the standardized signal to the reconciler; does not implement pause/resume |

**⚠️ Scope pin (the persistence of the progress stream obeys ADR-040 — do NOT invent a firehose table).**
The issue phrase *"streams SSE progress into `run_events`"* must be read against **§6.5 / ADR-040 (ISI-2339
→ ISI-2340)**: the Story-2.1 `run_event` table was split by **volume + retention semantics**. The
**low-volume coordination/lifecycle events** (status transitions, artifact-ref registration, completion)
feed the **append-only `coord.audit_log`** and drive the Run reconciler; the **high-volume shim trace
firehose** (`message | tool | usage`, §10.1) **does NOT persist to any Postgres table in v1** — it rides
**SSE live (ephemeral) + opt-in OTel export (§17.2)**, exactly the *"Run logs = coord audit + SSE, no new
data path"* model. **This story ingests the SSE stream and routes it by kind** (lifecycle → audit + phase
transition; firehose → SSE relay + OTel) — it **does not create a new stateful `run_events` table**.
"`run_events`" is the *logical* progress stream, not a new source-of-truth surface (Story 8.11 wires the
firehose to SSE+OTel emission). Reintroducing a persisted firehose table would reopen the F1 unification
defect ADR-040 closed.

**One-line boundary:** ISI-2114 answered *"what must a shim implement to be drivable?"* This story answers
*"how does the core drive it — submit, stream, collect — through only that contract, identically for every
runtime, crash-safely, without ever reaching a native side channel?"*

## Story

As **the Run reconciler's A2A client (`internal/a2a`, the southbound dispatch seam of the I2 moat)**,
I want **to dispatch a Run to its resolved agent by submitting an A2A task with a deterministic id,
streaming its SSE progress into the Run's ordered/deduplicated event stream, and collecting its emitted
artifacts through the fenced coord API — reaching the runtime through only the six A2A MUST-verbs and the
Agent Card, with zero lateral protocol and zero `runtime.type` special-casing**,
so that **any conformant runtime (OpenClaw, Hermes, and every future shim) drops into a squad and runs a
real Run with no change to the core (S5/S6/NFR-EXT1), progress is faithfully ordered and never
double-counted despite at-least-once delivery and dropped connections, a crash during dispatch never
starts two agent executions, and a zombie shim can never corrupt the coordination record — delivering the
FR-D1 / NFR-EXT2 southbound-invocation guarantee that is the load-bearing seam of the whole platform.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-D1** (invoke southbound over A2A: capability discovery, task
  lifecycle, artifacts, SSE progress — the direct requirement), **FR-D2** (one shim per runtime,
  A2A⇄native), **FR-D4** (capability flags first-class), **NFR-EXT1/EXT2** (zero-core-change
  extensibility — the moat), **S5/S6** (a vendor runtime drops into a squad; two runtimes in one squad),
  **I4** (the A2A seam is the integration boundary).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§10.1 "Shim placement & contract"** — *"the shim sidecar terminates A2A southbound from the control
    plane … streams SSE progress, and emits artifacts to the coordination record."* This story is the
    **control-plane end** of that sentence. **Capability flags are first-class (FR-D4/R3)**: the core
    negotiates against the card, treating gaps as declared capabilities, **never special-cased hacks**.
  - **§10.2 "Spec-drift isolation"** — the core speaks an **internal stable interface**; `pkg/a2a@rev`
    isolates the wire rev at the adapter seam (Story 5.3). This story's client targets that internal
    interface, so an A2A rev bump never touches it.
  - **§8 "Run lifecycle — Running"** — *"shim invoked over A2A (§10); agent works the item(s) through the
    coordination record and memory; SSE progress streamed to apiserver → console (FR-F2/NFR-PERF2)."*
    The **`Claiming → Running`** transition is where the submit happens.
  - **§6.4 "Reconcile-safe integration"** — the **deterministic dispatch** crux this story implements on
    the core side: *"`a2a_task_id = run_id`; the shim dedups on task id; before submitting, the reconciler
    writes a durable dispatch marker (`run.dispatched_task_id`, `run.dispatched_at`) in the same
    transaction as the state transition. … No crash window produces two agent executions."* AC2's teeth.
  - **§6.5 / ADR-040** — the audit/firehose split (the scope pin above). Lifecycle events → `coord.audit_log`;
    the `message|tool|usage` firehose → SSE + OTel, **not** a new Postgres table.
  - **§6.3** — fencing: the artifact collection goes through the **fenced coord API**, which validates the
    fence token inside the write txn; a **stale-fence (zombie) write is rejected** (AC4).
- **Companion design (consumed, not re-specified):** **`docs/bmad/design/agent-shim-interface-spec.md`
  (ISI-2114)** — the **six MUST-verbs (§3)**: `SubmitTask` (V1, deterministic-id dedup), `StreamEvents`
  (V2, SSE + resume from `lastSeq`), `GetStatus` (V3), `CancelTask` (V4), `EmitArtifact` (V5, fenced
  idempotent upsert), `GetAgentCard` (V6); the **SSE event schema (§4)**: `{seq, a2a_task_id, ts, type ∈
  {status, message, tool, artifact-ref, usage, auth-required}, payload}`, `seq` monotonic + gap-free,
  **at-least-once** delivery deduped on `(a2a_task_id, seq)`; the **artifact contract (§5)**: fenced coord
  API, `UNIQUE(work_item_id, run_id, kind)` + `sha256` upsert; the **task state machine (§3.1)**:
  `submitted→working→completed|failed|canceled`, with `auth-required` a **first-class pause signal, not a
  failure**; the **conformance suite (§12)** C1–C10 — this story is the core-side counterpart the shim's
  C1/C2/C3/C4/C7/C8/**C10** assert against.
- **Depends on:**
  - **ISI-2114** (the shim interface spec — the contract this client speaks; the reference OpenClaw shim +
    conformance harness are the spike's buildable deliverable, §13, gating S5/S6).
  - **Story 5.2** (Agent Card generation — the card this client reads to negotiate). Soft dependency: the
    client can be built against the §6.1 card schema before generation lands.
  - **Story 3.1** (ISI-2201 — the reconcile machine + deterministic-id + durable marker re-entrancy this
    story's *submit* step reuses). Hard dependency for the crash-safety wiring.
  - **Story 5.3** (protocol version pinning — `pkg/a2a@rev`; this client speaks the internal stable
    interface behind it).
- **Blocks / is consumed by:** **Story 5.5** (OpenClaw + Hermes both run real Runs in one squad — the
  proof this client is not single-runtime-shaped), **Story 5.9** (context injection rides the V1 envelope
  this client transports), **Stories 3.7/5.10/5.11** (the `rate_limited` signal this client relays),
  **Story 8.11** (agent-detail Run logs — consumes the SSE firehose this client relays to SSE+OTel),
  **Story 3.2** (the failure edge this client feeds on `failed`/silent-death).

## The core-side contract (authoritative)

### §A — Dispatch is runtime-AGNOSTIC (the moat, AC1)

The core reaches the agent through **exactly** the six verbs (ISI-2114 §3) and the Agent Card (§6). There
is **no other lateral protocol** — no SSH, no `kubectl exec`, no direct OpenClaw gateway call, no second
workspace mount, no vendor SDK in the reconciler. The dispatch code path **does not branch on
`runtime.type`**: it negotiates against the card's capability flags (streaming/toolCalls/
interactivePrompt/byoModelEndpoint) and adapts to *declared capabilities*, never to a hardcoded
per-runtime assumption. This is the **C10 grep-gate**: *no `type ==` special-casing in the Run reconciler
/ coord services.* Two runtimes of different `type` with identical capability cards MUST produce an
identical dispatch path. **A native-channel reach or a type-branch is the moat leak — the exact coupling
NFR-EXT1 forbids.**

### §B — Submit is deterministic + crash-safe (AC2, §6.4)

The core submits `SubmitTask{a2a_task_id = run_id, envelope, credentials_ref_mounted, model_route}` and
writes the durable dispatch marker (`dispatched_task_id`, `dispatched_at`) **in the same transaction as
the `Claiming → Running` transition**. Because the id is **deterministic** and the shim **dedups on it**
(V1 / C1), both crash windows are safe: crash **after** submit **before** the marker commits → re-entry
re-submits the *same* id → the shim **reattaches** (no second execution); crash **before** submit →
re-entry finds no marker and submits once. **No crash window produces two agent executions.** The core
never generates a fresh (random/uuid) task id per attempt — that would defeat the dedup and double-dispatch.

### §C — SSE progress is ordered, deduped, and resumable (AC3)

The core consumes `StreamEvents` (V2) and ingests each event into the Run's progress stream: it **orders
on `seq`** (monotonic + gap-free per task, §4) — **never on wall-clock `ts`** — and **dedups on
`(a2a_task_id, seq)`** because delivery is **at-least-once**. On a dropped connection it re-`StreamEvents`
**resuming from `lastSeq`**, tolerating the redelivery of already-seen events across the resume boundary.
The result written to the run-event stream is strictly increasing, gap-free, each `seq` exactly once —
regardless of duplicates, reorders, or drops on the wire. **Routing by kind obeys the ADR-040 scope pin
(§6.5):** lifecycle/`status`/`artifact-ref` → audit + phase transition; the `message|tool|usage` firehose
→ SSE relay + OTel, **not** a new persisted table.

### §D — Artifacts collect fenced + idempotent (AC4, §5/§6.3)

The core collects artifacts through the **fenced coord API** (`EmitArtifact` V5 → `POST /coord/artifacts`),
**never a raw Postgres write**. The API validates the Run's **fence token inside the write txn** (§6.3)
and **upserts on `UNIQUE(work_item_id, run_id, kind)` + `content_sha256`** (§6.4 C2): a re-entered
Collecting phase republishes the *same* content-addressed row — **one row, never a duplicate**. A **zombie
shim** that lost its lease (fence bumped under it by a reclaim, §6.3) is **rejected on the stale fence** —
its orphaned object blob is unreferenced and GC'able (C3). Collection is safe under re-entry *and* under a
split-brain resurrection.

### §E — Task states map to Run phases without conflation (AC5, §3.1)

The A2A **task** lifecycle (`submitted/working/input-required/auth-required/failed/canceled/completed`) is
**distinct** from the Run **phase** and the work-item lifecycle. The core maps them explicitly: `working`
→ `Running`; **`auth-required` → `Paused` (a first-class signal, NOT a Run failure, §11)**; `completed`
→ Collecting → `done`; `failed` (and silent death) → the **Story 3.2 failure/backoff edge**; `canceled`
→ `Cancelled`; a `rate_limited` signal → the reconciler's pause path (5.10/3.7). Collapsing
`auth-required` into a generic failure breaks graceful pause/resume (FR-G3) — the core must route it to
`Paused`, mirroring the shim-side C7 assertion.

## Acceptance Criteria

**AC1 — the core dispatches through only the six verbs + the Agent Card, identically for every runtime,
touching no native side channel.**
Given a resolved Agent Card, When a Run dispatches, Then the core reaches the agent via **only** `SubmitTask`
/ `StreamEvents` / `GetStatus` / `CancelTask` / `EmitArtifact` / `GetAgentCard` (ISI-2114 §3) and the card's
capability flags — **no SSH / pod-exec / native gateway / second mount / vendor SDK**. And the dispatch
code path **does not branch on `runtime.type`**: two runtimes with identical capability cards produce an
**identical dispatch trace** (the C10 zero-core-change gate). And a design that reaches a runtime-native
channel or forks on `type` is a moat leak — a correctness failure, not a style nit.

**AC2 — dispatch is deterministic-id + crash-safe: no crash window starts two agent executions.**
Given a Run at `Claiming → Running`, When the core submits, Then it uses `a2a_task_id = run_id` and writes
the durable dispatch marker **in the same transaction** as the transition (§6.4). And a crash **after
submit before the marker** re-enters, re-submits the **same** deterministic id, and the shim **reattaches**
(no second execution); a crash **before submit** re-enters and submits **once**. And **exactly one agent
execution** results across every crash window. And the core **never** generates a fresh per-attempt id
(which would double-dispatch).

**AC3 — SSE progress is ordered on `seq`, deduped on `(task, seq)`, and resumes from `lastSeq`.**
Given the shim's `StreamEvents` (V2) with **at-least-once** delivery, When the core ingests progress, Then
it **orders on `seq`** (gap-free per task) — **never wall clock — **dedups on `(a2a_task_id, seq)`**, and on
a dropped connection **re-`StreamEvents` resuming from `lastSeq`**, tolerating redelivered events. And the
resulting run-event stream is **strictly increasing, gap-free, each `seq` once**, despite duplicates,
reorders, and drops. And event routing honors ADR-040 (§6.5): lifecycle → audit + phase; `message|tool|
usage` firehose → SSE + OTel, **not** a new persisted table.

**AC4 — artifacts collect through the fenced coord API: idempotent upsert, stale-fence zombie rejected.**
Given a Run collecting artifacts, When the core collects, Then it calls the **fenced coord API** (never a
raw Postgres write) which validates the fence **inside the write txn** (§6.3) and **upserts on
`UNIQUE(work_item_id, run_id, kind)` + sha256** (§6.4 C2) — a re-entered Collecting phase yields **one
row, not two**. And a **zombie shim** whose fence went stale (reclaim bumped it, §6.3) is **rejected** on
the stale fence, its blob left unreferenced (C3). So neither re-entry nor a split-brain resurrection
corrupts the coordination record.

**AC5 — A2A task states map to Run phases without conflation; `auth-required` pauses, never fails.**
Given the A2A task state machine (§3.1), When the core interprets a state/signal, Then it maps `working`
→ `Running`, **`auth-required` → `Paused`** (first-class, §11 — **not** a Run failure), `completed` →
Collecting → `done`, `failed`/silent-death → the **Story 3.2** failure/backoff edge, `canceled` →
`Cancelled`, and `rate_limited` → the reconciler pause path (5.10/3.7). And the A2A **task** lifecycle is
kept **distinct** from the Run **phase** — collapsing `auth-required` into a generic failure (breaking
graceful pause/resume, FR-G3) is a defect.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/southbound-a2a-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same shape as the Story 2.9 / 3.1 / 3.2 checks): every property runs a NAIVE/cheating design
that MUST break (teeth) alongside the conformant design that MUST hold. If a naive arm stops breaking, the
check fails **loud** — the clean conformant result would then prove nothing.

- **(M) the moat — runtime-agnostic dispatch (AC1).** A **conformant core** dispatches openclaw and hermes
  through only the card + verbs and produces a **byte-identical trace** with `native_calls == 0`; a
  **cheating core** with an `if type == "openclaw"` branch reaches OpenClaw's **native gateway** and
  **forks the trace on type**. Asserts conformant-agnostic + zero-native AND cheating-forks + touched-native.
  *Mutation-proven:* making the conformant path touch `native_gateway` (or branch on `type`) turns the
  check **RED** — the C10/NFR-EXT1 seam has teeth.
- **(D) deterministic-id dispatch dedup (AC2, §6.4 C1).** Runs the conformant dispatch through **both** crash
  windows (after-submit/before-marker; before-submit) and asserts **exactly one** agent execution each; a
  **naive** design with a **fresh per-attempt id** double-dispatches (executions == 2). *Mutation-proven:*
  disabling the shim's id-dedup makes the conformant path start two executions → **RED**.
- **(S) SSE ordering + dedup + resume (AC3).** Delivers a stream with a **duplicate** (`seq` 2 twice), a
  **reorder** (5 before 4), and a **mid-stream drop** forcing a resume that **redelivers** `seq` 3. The
  conformant ingest yields **`[1,2,3,4,5]`** (gap-free, deduped, seq-ordered); the **naive** append-in-arrival
  ingest yields `[1,2,2,3,3,5,4]` (dups + reorder). *Mutation-proven:* dropping the `(task, seq)` dedup makes
  the conformant ingest carry duplicates → **RED**.
- **(A) artifact fenced + idempotent (AC4, §5/C2/C3).** A **double-upsert** of the same content-addressed
  `(work_item, run, diff)` yields **one row**; a **stale-fence** write (reclaim bumped `live_fence`) is
  **rejected**; a **naive unfenced** write **accepts the zombie** (corruption). *Mutation-proven:* removing
  the coord fence check accepts the zombie on the conformant path → **RED**.
- **(T) task-state mapping distinct (AC5, §3.1).** Asserts `auth-required → Paused` (not `Failed`), `failed
  → FailureEdge` (3.2), `completed → Collecting`, `canceled → Cancelled`; a **naive** map that **collapses
  `auth-required` into a failure** is flagged. *Mutation-proven:* mapping `auth-required → FailureEdge` on
  the conformant path → **RED**.

Exits non-zero if the dispatch forks on runtime type or reaches a native channel, a crash window
double-dispatches, SSE ingestion carries duplicates / drops ordering / loses the resume, an artifact
double-writes or a stale-fence zombie is accepted, or `auth-required` is conflated with failure. **All four
headline invariants are mutation-checked** (baseline exit 0; each mutation exit 1) — verified 2026-08-13.

## Out of scope (owned elsewhere)

- **The shim's six-verb implementation, SSE schema, Agent-Card schema, conformance suite C1–C10, and the
  reference OpenClaw shim** (ISI-2114 `design/agent-shim-interface-spec.md` — this story is the *core-side
  counterpart* the shim conforms to, not the shim). **Agent-Card *generation* from the CRD** (Story 5.2 —
  consumed, not generated here). **A2A/MCP wire-rev pinning** (Story 5.3 — this client speaks the internal
  stable interface behind `pkg/a2a@rev`). **Context envelope *assembly* + token budget** (Stories 3.6/5.9
  — transported, not assembled). **The reconcile state machine + durable `reconcile_step`** (Story 3.1 —
  invoked, its deterministic-id/marker re-entrancy reused). **Death detection + retry/backoff** (Story 3.2
  — fed on `failed`/silent-death). **Rate-limit pause/resume + fallback** (Stories 5.10/3.7/5.11 — the
  standardized signal is relayed, not implemented). **The MCP *northbound* tool seam** (`pkg/mcp` — a
  sibling adapter). **The persisted firehose table** — explicitly NOT built (ADR-040 scope pin: firehose
  rides SSE + OTel). This story ships the **core A2A dispatch client**: runtime-agnostic submit, crash-safe
  deterministic-id dedup, ordered/deduped/resumable SSE ingestion, fenced idempotent artifact collection,
  the task-state→Run-phase mapping, and the differential falsification — the FR-D1 / NFR-EXT2
  southbound-invocation guarantee itself.
