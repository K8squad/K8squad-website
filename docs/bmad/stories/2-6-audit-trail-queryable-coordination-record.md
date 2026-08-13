# Story 2.6: Audit trail — the queryable coordination record

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THE LOAD-BEARING INVARIANT IS COMPLETENESS-BY-CONSTRUCTION (arch §6.5, ADR-040).**
> The `coord` schema **is** the audit log. Every coordination mutation — checkout (claim
> acquire/renew/release), comment, artifact registration, state transition, completion — writes
> **one immutable `coord.audit_log` row IN THE SAME TRANSACTION as the mutation itself** (§6.5/§6.6).
> The audit is therefore complete **by construction**: no crash can leave a durable coordination
> mutation with no audit row (a *hole* that makes who/what/when/result non-guaranteed), and no rolled-back
> mutation leaves a phantom row. A design that logs the audit as a **separate best-effort write after**
> the mutation commits loses rows on a crash-between — that is a **correctness failure for an audit
> trail, not a bug ticket**. Read AC1 literally.

## ⚠️ Scope note — this story is the READ/QUERY contract over an existing write path

Story 2.1 (ISI-2191) already shipped the `coord.audit_log` table and the append-only trigger
(UPDATE/DELETE/TRUNCATE rejected), and the ADR-040 ruling (ISI-2340) already fixed its **shape**:
audit-only, low-volume, monotonic `bigserial` — **not** the trace firehose. Stories 2.2/2.4/2.8/2.9/3.1
already write their audit rows in the same transaction as their coordination mutations (§6.5/§6.6).
**This story does not re-implement the table or the co-commit rule** — it pins the **completeness
invariant those writers must honor** and specifies the **read-only, RBAC-scoped query API** the operator
uses to interrogate the trail *by work item / actor / time*, returning **who / what / when / result** on
every row (FR-B4/D4/NFR-OBS1). It is the story that turns "rows exist" into "the coordination record is a
**queryable audit trail**."

## Story

As **an operator (and, transitively, every RBAC/identity surface in Epic 15 and the console §13)**,
I want **the coordination record exposed as a queryable audit trail — every checkout, comment, artifact,
state transition, and completion a durable immutable row (who / what / when / result), filterable by work
item, actor, and time**,
so that **I can answer "who did what, when, with what result" over activity across Runs — non-repudiably,
completely (no holes), and scoped to what I'm allowed to see — because the audit row is co-committed with
the coordination mutation and can never be edited or erased.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-B4** ("The coordination record SHALL be queryable as an audit
  trail — who did what, when, with what result"), **FR-B1/B3** (all coordination is rows; no P2P chat),
  **NFR-OBS1** ("The coordination record SHALL serve as a queryable audit trail (D4)"). §12.3/§12.4 for
  the RBAC scope + `initiated_by_user_id` on every audited action.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§6.5 (authoritative for this story)** — "The `coord` schema *is* the audit log — every checkout,
    comment, artifact, and completion is an immutable-append row with principal + timestamp. The apiserver
    exposes a **read-only audit query API**; the console renders it (§13)." Plus the **audit-only shape
    ruling (F1, ISI-2339 → ISI-2340; ADR-040):** the durable rows live in `coord.audit_log` (née
    `run_event`) — one clean **monotonic `bigserial`** carrying **only the low-volume coordination
    events** (claim acquired/renewed/released, comment added, artifact registered, state transition,
    completion), each with `principal` + `initiated_by_user_id` (§12.4) + fence + timestamp;
    append-only-by-trigger (UPDATE/DELETE/**TRUNCATE** all rejected) → **structurally immutable without
    qualification**. The **high-volume shim Run-trace firehose** (`tool_call | llm_call | build_output |
    error`, §10.1) does **NOT** persist here — it rides **SSE live + opt-in OTel (§17.2)**.
  - **§6.6** — the same transaction that changes coordination state **also** writes a domain event to the
    `outbox` (§17.4). The audit log is the **queryable durable history**; the outbox is the **event
    journal**. Both are rows in the state-change transaction — neither can diverge from what committed. The
    event seam is **emit-only / read-only downstream — it grants no custody** (§17.4 guard).
  - **§6.1** — the `coord` data model the audit rows reference (`work_item`, `comment`, `artifact`,
    `claim`) and the **`initiated_by_user_id`** on the claim (§12.4). `work_item.project_id`/`team_id` is
    the tenancy predicate the query API's RBAC filter rides (§12.1).
  - **§6.2/§6.3** — the fenced claim/reclaim: every audited mutation carries the writer's `fence`, so the
    audit row's `what`/`when` is fence-stamped and non-repudiable. **This story never writes the claim
    row** — it reads the audit of writes to it.
  - **§12.3 / §12.4** — deny-by-default RBAC middleware (the **sole** authorization wall; the query API is
    one endpoint behind it) + the control-plane-stamped `initiated_by_user_id` that makes every audit row
    answer "on whose behalf" (confused-deputy closed, §1614–1626).
  - **§13 / §17.2** — the console renders the audit query (the "Run logs = coord audit + SSE, **no new
    data path**" model); OTel `ksquad.*` spans are a *parallel* emission, not this table.
  - **ADR-040** (§18) — audit table is audit-only, not a trace firehose. **ADR-003/023/025** — the
    Postgres-row-lock + outbox + fence-before-release trades this audit sits on top of.
- **Depends on:**
  - **Story 2.1** (`coord` schema — the `audit_log` table + append-only trigger + the ADR-040 shape this
    story queries). **Done + merged** (k8squad PR #5).
  - **Stories 2.2 / 2.4 / 2.8 / 2.9 / 3.1** — the **writers** whose mutations co-commit their audit rows
    (checkout, reclaim, handoff artifact, dispatch, state transitions/completion). This story pins the
    completeness rule they honor; it does not re-implement their writes.
  - **Epic 15.4** (identity middleware) — supplies the resolved principal + `initiated_by_user_id` the
    query API filters on and the RBAC scope it enforces. The query API is **behind** that middleware.
- **Consumed by:** the **console audit view (§13)**; **Epic 15.2/15.3/15.5 + Story 1.6** (every user/
  membership/ownership mutation is "recorded in the audit trail (2.6)" and the per-user view queries it);
  **Story 8.15** (Users & Roles screen surfaces audit); the **auth/RBAC audit (NFR-OBS4, §1614)** which
  joins `ksquad.auth.*`/`ksquad.rbac.*` to `initiated_by_user_id` in this same trail.

## The design (authoritative)

**The write contract (pinned, not re-implemented).** Every coordination mutation writes **exactly one**
`coord.audit_log` row **in the same transaction** as the mutation and its §6.6 outbox event. Atomicity is
the whole point: the mutation, its audit row, and its outbox event **commit together or roll back
together**. This is what makes the trail *complete by construction* — there is no separate best-effort
"log after commit" step that a crash can drop. Each row carries:

| column | who / what / when / result | source |
|---|---|---|
| `who`    | `principal` (the acting Run/agent) **+ `initiated_by_user_id`** (the human, §12.4) | §6.1 claim / §12.4 |
| `what`   | `event` ∈ {claim_acquired, claim_renewed, claim_released, comment_added, artifact_registered, state_transition, run_completed} + target (`work_item_id`/`run_id`/comment/artifact ref) + `fence` | §6.5 |
| `when`   | monotonic `bigserial seq` + `timestamptz` + `fence` | §6.5 |
| `result` | the outcome — `acquired`/`rejected`/`released` (claim), `committed` (comment/artifact), the new state (transition), the terminal phase `Succeeded`/`Failed`/`Cancelled` (completion) | §6.5 |

**The read contract (what this story ships).** A **read-only** audit query endpoint on the apiserver
(`GET /audit`, behind the §12.3 deny-by-default middleware), filterable by:

- `work_item_id` — every event for one item (the console ticket's "activity" tab; the completeness axis);
- `actor` (`principal` **or** `initiated_by_user_id`) — everything one Run/agent/human did;
- `since` / `until` — a time window;
- any **intersection** of the three,

returning rows **ordered by the monotonic `seq`**, each with the full **who/what/when/result** tuple.
Three B-tree indexes back the three axes (`(work_item_id, seq)`, `(principal, seq)`,
`(initiated_by_user_id, seq)`, `(created_at)`), so no query axis is a table scan.

**RBAC scope is the same single wall (§12.3).** The query endpoint is **not** a second authorization path:
it passes the identical deny-by-default middleware, which resolves the caller's project memberships and
**filters rows to work items in Projects the caller may see** (`admin` sees all; a `user` sees only their
`project_memberships`). A caller outside a Project's membership gets **no rows** for its items — not a
403-that-confirms-existence, just absence (§12.3/§15.4). Tenancy rides `work_item.project_id` (§12.1) — one
predicate.

**Audit-only — the firehose is NOT here (ADR-040).** The query API reads `coord.audit_log`, which by
construction holds **only** the bounded coordination events. The high-volume shim trace
(`tool_call|llm_call|build_output|error`) is **never** written to this table; a "Run trace" view is SSE +
OTel (§10.1/§17.2, Story 8.11), a *parallel* surface. Keeping the firehose out is what keeps the audit
both **unqualified-immutable** (never retention-managed — coordination volume is bounded) and its
`bigserial` a **clean, gap-free coordination sequence**.

**What it must NOT do.** The query API is **read-only** — it never writes, never touches the `claim` row,
grants **no custody**, and exposes **no** claim/lease/fence *mutation* surface (fence is a read-only stamp
on the row). Reading the audit trail is not a coordination action (no P2P — the audit is history, not
transport).

## Acceptance Criteria

**AC1 — every coordination mutation co-commits exactly one immutable audit row (the completeness crux).**
Given any coordination mutation — checkout (claim acquire/renew/release), comment add, artifact register,
state transition, run completion — When it commits, Then **exactly one** `coord.audit_log` row is written
**in the same transaction** as the mutation (and its §6.6 outbox event), so that: (a) a crash can **never**
leave a durable coordination mutation with **no** audit row (no hole); (b) a rolled-back mutation leaves
**no** phantom audit row. A design that logs the audit as a **separate write after** the mutation commits
is **rejected** — it violates completeness under a crash-between.

**AC2 — audit rows are immutable (append-only, structural).**
Given a committed `coord.audit_log` row, When any process attempts `UPDATE`, `DELETE`, or `TRUNCATE`, Then
all three are **rejected by the append-only trigger** (§6.5) — who/what/when/result is **non-repudiable**;
a committed audit event can never be edited or erased. The `seq` is a **monotonic `bigserial`**, never
reset or reused, and — because the table is coordination-only (AC5) — **gap-free** under the coordination
stream.

**AC3 — every row carries who / what / when / result.**
Given any audit row, When it is read, Then it carries **who** = `principal` + `initiated_by_user_id`
(§12.4), **what** = `event` + target (`work_item_id`/`run_id`/comment/artifact ref) + `fence`, **when** =
monotonic `seq` + timestamp + `fence`, **result** = the outcome (`acquired`/`rejected`/`released` /
`committed` / new state / terminal phase). No audited event is written without all four.

**AC4 — the trail is queryable by work item / actor / time, complete, ordered, and RBAC-scoped.**
Given activity across Runs, When the operator queries `GET /audit` by `work_item_id`, by `actor`
(`principal` or `initiated_by_user_id`), by `since`/`until`, or any **intersection**, Then it returns the
matching rows **ordered by `seq`**, each with the full who/what/when/result tuple; **completeness:** a
query by `work_item_id` returns **every** coordination event for that item (checkout, comment, artifact,
transition, completion) — none missing; **RBAC:** the query passes the §12.3 deny-by-default middleware and
returns **only** rows for work items in Projects the caller may see (a non-member gets absence, not
existence). Each axis is index-backed (no table scan).

**AC5 — audit-only: the shim trace firehose is never in the audit trail (ADR-040).**
Given the shim emits its high-volume Run-trace firehose (`tool_call | llm_call | build_output | error`,
§10.1), When those events are produced, Then they are **NOT** written to `coord.audit_log` (they ride SSE +
opt-in OTel, §17.2) and **never** appear in a `GET /audit` result — so the audit trail stays **audit-only,
bounded, unqualified-immutable**, and its `bigserial` a clean coordination sequence. A design that dumps
the firehose into `audit_log` is **rejected** (it pollutes the monotonic sequence and forces retention that
breaks the immutability claim).

## Runnable check (the falsification)

`docs/bmad/spikes/bench/audit-trail-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same discipline as the Story 2.8 handoff / 2.4 reclaim checks), targeting the completeness,
immutability, queryability, and audit-only invariants:

- **(A) NAIVE separate-log audit** logs the audit as a **best-effort append after** the mutation commits.
  A crash in the between-window leaves a **durable mutation with NO audit row** — a hole. The check asserts
  the naive design **detectably** orphans a mutation (teeth). If it ever stops orphaning, the test fails
  **loud** (teeth lost) — routed through the same `record(...)` SUT so re-introducing co-commit makes the
  hole disappear and the arm fail.
- **(B) §6.5 CO-COMMIT audit** shares one transaction between the mutation and its audit row. The **same**
  crash window leaves **zero orphans** (atomic rollback: the mutation didn't persist either) and **zero
  phantoms** — `mutations == audit_rows` always. Completeness holds by construction (AC1).
- **(C) immutability** (AC2) — `UPDATE`/`DELETE`/`TRUNCATE` on a committed row are all rejected; the
  `seq` stream is monotonic + gap-free. A **naive mutable log** is shown to let who-did-what be
  edited/erased/truncated (teeth).
- **(D) queryability** (AC4) — query by work item / actor / time and their intersection; **completeness**
  (a work-item query returns every event kind); who/what/when/result present on every row; **RBAC
  deny-by-default** drops rows outside the caller's membership; results ordered by `seq`.
- **(E) audit-only** (AC5) — coordination events land in the trail; the shim firehose (`tool_call`/…)
  does **not** and never appears in a query. A **naive** design that appends firehose rows is shown to
  **pollute the monotonic coordination sequence** (teeth).

Exits non-zero if (A) ever stops orphaning (harness toothless), or if (B)–(E) ever leave a mutation with no
audit row / a phantom row / let an audit row be mutated / drop a who/what/when/result field / mis-scope a
query / let firehose rows enter the audit trail. Models Postgres row + transaction semantics in-process;
real-Postgres promotion rides the **Story 2.7 chaos harness** (the CI gate on real PG).

## Out of scope (owned elsewhere)

- **The `coord.audit_log` table + append-only trigger + ADR-040 shape** (Story 2.1 / ISI-2340) — this
  story **queries** it and pins the completeness rule; it does not create it.
- **The coordination writers** (Stories 2.2/2.4/2.8/2.9/3.1) — they co-commit their own audit rows; this
  story specifies the invariant they honor and the read surface over them, not their write paths.
- **The RBAC middleware / identity propagation** (Epic 15.4) — this story's query endpoint sits **behind**
  it and reuses it; it does not implement authz.
- **The console audit view** (§13, Epic 8) — renders this API; **the auth/RBAC audit rows** (NFR-OBS4,
  Epic 15) — written *by* those surfaces *into* this same trail and queried through this API.
- **The Run-trace firehose surface** (SSE + OTel, §10.1/§17.2, Story 8.11) — the *parallel* live-trace
  path this story explicitly keeps **out** of the audit table. This story ships the **queryable audit
  trail contract + read API spec + the completeness/immutability/audit-only invariants and their
  falsification** — turning the coordination record into an answerable "who did what, when, with what
  result."
