# Story 3.1: Run reconcile state machine — the crash-safe I1 control plane

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE HEART OF I1 (arch §8, ADR-005) — the reconcile control plane that replaces heartbeat
> orchestration (F1–F4, R4).** The load-bearing invariant is **crash-safe idempotency**: a controller
> can die at *any* point and the failover leader re-reads **durable Postgres state** and continues —
> **never re-driving a phase's external side effect twice, never losing committed progress**. The Run
> keeps **zero** liveness state in controller memory: on every reconcile it reads the durable step and
> level-triggers from there. A design that resumes from in-memory continuity — or that re-dispatches a
> second agent execution after a restart — is a **correctness failure, not a bug ticket**. Read AC3 and
> AC4 literally.

## ⚠️ Wording reconciliation (issue text vs. pinned architecture)

The originating issue (ISI-2201) phrases the machine as
`Pending → ClaimingSandbox → Dispatching → Running → Collecting → (Succeeded|Failed|Canceled)`. That is a
**finer-grained draft** of the reconcile flow. The **CRD-visible `Run.status.phase` enum was pinned at
architecture r28** (2026-08-13, ISI-2343 ← Story 1.2 AC6, §5.1 Run row) to the CEL-validated set
**`Pending | Claiming | Running | Paused | Succeeded | Failed | Cancelled`** — the same coarse enum §8
draws. This story implements the **pinned** contract; where the issue text and arch §5.1/§8 differ,
**arch is authoritative**:

- **`status.phase` (the K8s-visible enum "everything downstream watches", §5.1)** stays the **pinned
  coarse set**. The issue's `ClaimingSandbox`, `Dispatching`, `Collecting` are **NOT new top-level enum
  values** — adding them would reopen the r28 CEL-validated enum a day after it was pinned. They are
  modeled as **fine-grained durable reconcile checkpoints** (the Postgres source of truth for re-entry)
  and surfaced as **`status.conditions`** detail. `status.phase` is the projection; the durable step is
  the truth (AC2).
- **Spelling:** the pinned enum is **`Cancelled`** (double-l), not the issue's `Canceled`. Use
  `Cancelled` — it must match the r28 CEL enum on `Run.status.phase` or the status patch is rejected.
- **`Paused`** (and `Paused(rate_limited)`, §8) is a first-class pinned phase the issue omits; it is
  **not in scope to *drive*** here (rate-limit recovery = Epic 3 later / §8 3-tier), but the machine
  **must not make `Paused` unreachable** — the terminal-vs-non-terminal classification (AC5) accounts
  for it.

**Checkpoint → phase mapping (authoritative):**

| Issue draft step | Pinned `status.phase` | Durable checkpoint (`coord.run.reconcile_step`) | Where it lives |
|---|---|---|---|
| Pending | `Pending` | `pending` | admission |
| ClaimingSandbox | `Claiming` | `claiming_sandbox` | §8 Claiming, §9 warm-pool bind + §5.3.4 pod assembly |
| Dispatching | `Claiming`→`Running` boundary | `dispatching` (`dispatched_task_id` marker, §6.4) | §6.4 A2A dispatch |
| Running | `Running` | `running` | §8 Running, shim over A2A §10 |
| Collecting | `Running` | `collecting` | §6.4 artifact emission (upsert) |
| Succeeded / Failed / Cancelled | `Succeeded` / `Failed` / `Cancelled` | terminal | §8 terminal + retryPolicy |

## Story

As **the Run controller (the reconcile control plane)**,
I want **to drive a `Run` CR from `Pending` to a terminal state through idempotent, durably-checkpointed phases so a controller crash or leader failover at any point re-reads Postgres and continues exactly where it left off**,
so that **every Run reaches a terminal state exactly once — no lost progress, no double-dispatched agent, no double-collected artifact, no in-memory continuity assumed — which is the delta over heartbeat orchestration that R4 (arch §8, ADR-005) exists to close.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-A4** (Run reconcile lifecycle), **FR-A5** (failure/retry with
  backoff), **FR-A6** (operator kill), **R4** (reconcile vs heartbeat is the architectural bet),
  **NFR-REL1/REL2** (no coordination state lost on crash; failover).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§8** — the Run lifecycle state machine (the diagram, Claiming/Running/Failure-resume/Kill/Pause,
    ADR-005). **Authoritative for the phase set and transitions.**
  - **§5.2** — the operator: **controller-runtime / Kubebuilder, one manager, leader-elected**;
    reconcilers **idempotent and level-triggered**, each writes `status.observedGeneration` +
    conditions; the Run reconciler coordinates with the claim service via **fencing tokens** (§6.3) so
    a controller restart never double-drives (this story's AC3/AC4).
  - **§5.1** — the **`Run` CRD** row (r28): `spec` `{teamRef, projectRef, workItemRef (opaque
    coord-DB pointer), inputs, sandboxPolicy, agents[], retryPolicy}`; **`status` subresource**
    `{phase (the pinned CEL enum), sandboxRef, claimedAt, conditions, artifactRefs}`. This story writes
    that `status`; it does **not** add fields (Story 1.2 owns the shape).
  - **§6.4 (the correctness spine of this story)** — reconcile-safe re-entrancy for external-effect
    steps: **deterministic `a2a_task_id = run_id` + shim dedup** (no crash window yields two agent
    executions); **content-addressed artifact upsert** `UNIQUE(work_item_id, run_id, kind)` (a
    re-entered Collecting republishes the same row, never a duplicate); **conditional status UPDATEs**
    `… WHERE status = :expected` (a stale pass cannot resurrect or double-advance a Run). "This is why
    coordination lives in Postgres transactions, not controller memory."
  - **§6.3** — lease/fencing + the **reclaim protocol (fence the pod first, release the claim second)**
    used on the Failure/resume edge.
  - **§6.2** — the fenced **claim** (Story 2.2) the reconciler drives at `ClaimingSandbox` to bind the
    work item; **§6.5/§6.6** — every phase transition writes an **audit row** (`coord.audit_log`) and a
    **domain event** to the **outbox** in the same transaction as the status write.
- **Review findings honored:** **r28 pinned enum** (reconciliation above — do not expand
  `status.phase`); **§6.4 F4** (external-effect idempotency is *designed*, the crux of AC3).
- **Depends on:**
  - **Story 1.2** (ISI-2188 — the `Run` CRD type + pinned `status` subresource + CEL enum). If not
    landed, wire against §5.1 r28.
  - **Epic 2** (the coord spine): **2.2** (claim, drives `ClaimingSandbox`), **2.5** (outbox relay,
    consumes the events this story writes), **2.6** (cross-dispatch reconcile-safety — the general form
    of §6.4 this story specializes to the Run machine). The DB-backed integration test gates on the
    `coord` schema (Story 2.1).
  - **Story 3.2** (warm-pool `SandboxPool` bind — `ClaimingSandbox` requests a sandbox from it) and
    **§5.3.4** pod assembly. This story owns the *state machine + durability + idempotency*; 3.2 owns
    *what a sandbox bind physically does*.
- **Blocks / is consumed by:** **3.3** (kill/cancel path reuses the terminal transition + reclaim),
  **3.6** (Context Assembler runs at the `Claiming → Running` boundary this machine defines), **8.4**
  (console kill → `Cancelling`), **Epic 11** (PR status updated by the reconciler), **Epic 13.1** (each
  Run is one trace — the reconcile phases are its spans).

## The pinned machine (authoritative)

```
 Pending ─► Claiming ─► Running ─┬─► Succeeded            (durable reconcile_step within a phase:
    ▲          │           │     ├─► Failed ──┐            Claiming = {claiming_sandbox, dispatching}
    │          │           │     └─► Cancelled│            Running  = {running, collecting})
    │          │           ▼                  │
    │          │        Paused ──(refresh)──► Running      status.phase = pinned coarse enum (r28, CEL)
    └──────────┴── retryPolicy backoff ◄──────┘            status.conditions = fine-grained checkpoint
```

Every reconcile pass is **one transaction** that (a) reads the durable `reconcile_step` + fence, (b)
performs the phase's effect **idempotently** (§6.4), (c) advances `reconcile_step` with a **conditional
UPDATE** `WHERE reconcile_step = :expected AND fence_token = :fence`, and (d) writes the audit row
(§6.5) + outbox event (§6.6) in the **same** transaction, then (e) patches `Run.status` (phase +
conditions + `observedGeneration`) as the observed projection. The Postgres step is the source of
truth; the K8s status is downstream of it — a crash between (d) and (e) is safe because the next
reconcile re-derives status from the committed step.

**Per-phase durable effect + its idempotency mechanism (§6.4):**

- **`claiming_sandbox`** — drive the fenced claim (§6.2) to bind `workItemRef`; request a warm sandbox
  (Story 3.2) and record `status.sandboxRef` + `claimedAt`. Idempotent: re-entry re-reads the claim
  (holder + fence) — if this Run already holds it with a current fence, it does **not** re-claim or
  re-bump the fence (§6.4). A sandbox bind is keyed by `run_id` so a re-entry reattaches, never
  double-provisions.
- **`dispatching`** — write the durable dispatch marker (`dispatched_task_id = run_id`,
  `dispatched_at`) in the **same txn** as the `claiming → running` step advance, **then** submit the
  A2A task. Idempotent: **deterministic task id + shim dedup** (§6.4/§10.1, conformance ISI-2114) — a
  crash after submit but before the marker commits re-submits the **same** id and the shim reattaches;
  a crash before submit re-submits once. **No crash window produces two agent executions** (AC3).
- **`running`** — the shim works the item; SSE progress is **ephemeral** (§6.5, not durable — it is
  *not* recovery state). Recovery state is the committed `reconcile_step` only.
- **`collecting`** — register artifacts via **content-addressed upsert** `UNIQUE(work_item_id, run_id,
  kind)` (§6.4/§6.1); populate `status.artifactRefs`. A re-entered Collecting republishes the identical
  content-addressed rows — **never a duplicate artifact** (AC3).
- **terminal (`Succeeded|Failed|Cancelled`)** — conditional UPDATE to the terminal step + completion
  audit row + terminal outbox event, **one txn**. `Failed` consults `spec.retryPolicy`: within budget →
  back to `Claiming` with backoff (§8, FR-A5) after the §6.3 **fence-first reclaim** (fence the dead
  pod, *then* release the claim); budget exhausted → stays `Failed`. `Cancelled` (operator kill,
  FR-A6 / Story 3.3) tears down the sandbox and releases via the same reclaim.

**Leader-election (§5.2, failover — AC4):** exactly one controller-runtime manager holds the lease and
drives reconciles; on leader death the failover leader re-reads durable `reconcile_step` + fence and
continues. A **zombie old leader** cannot double-drive because every mutation is fenced (§6.3): its
stale fence loses the conditional UPDATE. Leader-election is the *availability* mechanism; **fencing is
the *safety* mechanism** — the machine is correct even if two managers briefly believe they are leader.

## Acceptance Criteria

**AC1 — the pinned phase set, level-triggered.**
Given a `Run` CR, When the controller reconciles, Then it advances the Run through
`Pending → Claiming → Running → (Succeeded | Failed | Cancelled)` (the r28 CEL-validated
`status.phase` enum), writing `status.phase`, `status.conditions` (the fine-grained checkpoint:
`ClaimingSandbox` / `Dispatching` / `Collecting`), and `status.observedGeneration` on every pass. And
reconciliation is **level-triggered** — each pass reads current durable state and acts on it, never
relying on the previous pass having run in the same process.

**AC2 — durable state is the source of truth; status is a projection.**
Given any reconcile pass, When it advances a phase, Then it persists the fine-grained
`reconcile_step` (+ any phase marker: `sandboxRef`, `dispatched_task_id`, `artifactRefs`) to **Postgres
in one transaction** with the audit row (§6.5) and outbox event (§6.6), **before** patching
`Run.status`. And the controller holds **zero** liveness/continuity state in memory: a fresh process
reconstructs exactly where the Run is from the committed `reconcile_step` alone.

**AC3 — every phase is idempotent under re-entry (the §6.4 crux — no double external effect).**
Given a controller that crashes and re-enters a phase, When it re-drives, Then the phase's external side
effect happens **at most once across all crash windows**:
- **Dispatch:** re-entry submits the **deterministic** `a2a_task_id = run_id`; the shim **dedups** and
  reattaches — **no crash window produces a second agent execution.**
- **Collect:** re-entry re-upserts **content-addressed** artifacts — **no duplicate artifact row.**
- **Transition:** each step advance is a **conditional UPDATE** `WHERE reconcile_step = :expected` — a
  stale/duplicate pass **cannot double-advance or resurrect** a Run.
Re-entering an already-completed phase is a **no-op**, not a re-execution.

**AC4 — leader-election failover continues from durable state; fencing prevents zombie double-drive.**
Given a leader controller that dies mid-Run, When the failover leader takes the lease, Then it re-reads
the durable `reconcile_step` + fence and **continues the Run from that point** (no restart from
`Pending`, no lost progress). And if a **zombie old leader** briefly issues a stale mutation, its
**stale fence token loses the conditional UPDATE** (§6.3) — so correctness does **not** depend on
leader-election being perfectly single-writer; leader-election is availability, **fencing is safety**.

**AC5 — terminal classification, retry, and Paused reachability.**
Given a Run reaches `Succeeded`, `Failed`, or `Cancelled`, When it is terminal, Then no further
reconcile advances it (terminal is absorbing; only `Failed`+`retryPolicy`-within-budget re-enters
`Claiming` after a **fence-first reclaim**, §6.3). And the machine **does not make `Paused` unreachable**
— the phase classifier treats `Paused`/`Paused(rate_limited)` as non-terminal resumable (driving them
is §8's rate-limit tiers, out of scope here), so a later story can wire them without re-architecting the
machine.

**AC6 — each transition writes audit + domain event in the same transaction (§6.5/§6.6).**
Given any phase transition, When it commits, Then the `coord.audit_log` row (principal +
`initiated_by_user_id` §12.4 + fence + timestamp, §6.5) and the outbox domain event (§6.6) are written
in the **same transaction** as the `reconcile_step`/status advance — so a crash can never leave a
transitioned Run with no audit trail or a phantom event with no transition, and Story 2.5's relay has a
durable row to publish.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/run-reconcile-check.py` — stdlib-only, `python3` it directly. A **differential**
crash-injection falsification (same shape as the Story 2.2 check), not a happy-path demo:

- **(A) NAIVE reconciler** keeps phase progress in **controller memory** and re-dispatches from its
  in-memory phase. Injected crash-and-failover at each phase boundary → it **loses progress and/or
  double-dispatches a second agent execution** (and double-collects). The check asserts the naive design
  **detectably breaks** — proving the harness can catch a double-drive.
- **(B) §6.4 DURABLE reconciler** persists `reconcile_step` to a simulated Postgres, uses the
  deterministic `a2a_task_id = run_id` + dedup, content-addressed artifact upsert, and conditional
  step-advance UPDATE guarded by fence. Injected crash at **every** phase boundary (and a zombie-leader
  stale-fence mutation) → the check asserts **exactly-one agent execution, exactly-one artifact set,
  exactly-one terminal transition, zero lost progress** across all crash points.

If (A) ever stops breaking (no double-drive seen), the check fails **loud** — the harness lost its
detecting power and (B) proves nothing. Exits non-zero if (B) ever double-dispatches, double-collects,
loses progress, resumes from `Pending`, or lets a stale-fence zombie mutation win.

## Out of scope (owned elsewhere)

- **Warm-pool sandbox bind internals** (Story 3.2, §9.2), **kill UX/API** (Story 3.3 / 8.4), **Context
  Assembler envelope** (Story 3.6, §8.5), **rate-limit `Paused` recovery tiers** (§8, later Epic 3),
  **outbox relay to NATS** (Story 2.5, §17.4), **the Run trace/spans** (Epic 13.1). This story ships the
  **state machine, its durable checkpointing, per-phase idempotency, leader-election + fencing
  failover, and the crash-injection falsification** — the I1 crash-safety guarantee itself.
