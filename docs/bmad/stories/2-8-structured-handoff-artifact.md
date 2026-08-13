# Story 2.8: Structured handoff artifact — the advisory coordinator feedback loop

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THE LOAD-BEARING INVARIANT IS ADVISORY-ONLY (arch §8.5, no-P2P lock preserved a *sixth* time).**
> When a Run completes or pauses, the agent writes a **structured handoff artifact** — but that artifact
> is **knowledge transfer, never custody transfer**. It enriches the *next* Run's context envelope (§8.5);
> it does **not** hand a claim, a lease, or a fence to anyone. Custody moves **only** through the fenced
> **release → re-dispatch → claim** path (§6.2/§6.3). A design where reading the handoff artifact lets the
> next agent begin work on the item **without a fresh fenced claim** reintroduces the P2P back-channel that
> §6/§7.3/§7.5 structurally forbid — that is a **correctness failure, not a bug ticket**. Read AC3 literally.

## ⚠️ Schema reconciliation (issue text vs. pinned architecture §8.5)

Arch §8.5 names the handoff artifact with the **illustrative** field list `{did, decisions, next, blockers}`
("standardized schema"). The originating issue (ISI-2198) pins the **concrete standardized schema** as the
**7-field superset**:

```
{ did, decisions, next, blockers, findings, recommended_next, artifacts_for_downstream }
```

This is a **superset, not a conflict** — §8.5's four fields are the load-bearing core; the issue adds three
advisory-context fields (`findings`, `recommended_next`, `artifacts_for_downstream`) that make the handoff
usefully rich for the next Run's envelope. This story adopts the **7-field schema as the standardized
contract**; §8.5's list stays the illustrative subset. Every field is **advisory context** — none of them,
including `artifacts_for_downstream`, carries or references a claim/lease/fence (AC3).

## Story

As **a completing (or pausing) agent Run**,
I want **to write a single provenance-tagged structured handoff artifact — `{did, decisions, next, blockers, findings, recommended_next, artifacts_for_downstream}` — to the coordination record via the A2A artifact channel (§6.5) and mirror it as a provenanced memory write (§7)**,
so that **the next Run assembled on this work item inherits my findings and recommendations as legible, attributed, untrusted-recall context (§8.5) — while work custody moves *only* through the fenced release → re-dispatch → claim path, never through the artifact itself.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-B1/B3** (coordination progress + artifacts are rows), **FR-B4**
  (audit), **FR-E** (memory recall), the **no-P2P invariant (I4/R10)**.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§8.5 (authoritative for this story)** — Context Injection & Agent Handoff. **"Handoff is knowledge
    transfer, NOT custody transfer."** The structured handoff artifact rides the A2A artifact channel (§6.5)
    **and** is mirrored as a provenanced memory write (§7). It is **advisory context for the next Run** — it
    **enriches B's envelope** (handoff artifact + work-item provenance §6.5 + scoped memory recall §7). The
    custody move stays the fenced §6.2/§6.3 mechanism: A **releases**, the control plane **re-dispatches**, B
    **claims**. "If the handoff artifact could authorize or transfer custody it would reintroduce the P2P
    back-channel." Injected into B's envelope at the **untrusted-recall trust tier** (§8.5 refinement (2),
    §7.3) — reference material, never commands.
  - **§6.1** — the **`artifact` table**: `artifact(id, work_item_id, run_id, kind, uri, sha256, created_at,
    UNIQUE(work_item_id, run_id, kind))`. The handoff is one such row (`kind = 'handoff'`), **content-addressed**
    (`sha256` over the canonical serialized schema) — so the write is **idempotent under §6.4 re-entry** (the
    Story 3.1 `collecting` phase can re-drive without producing a duplicate). **The schema (§6.1) has no
    `message` table and no claim/lease/fence column on `artifact`** — custody has *no expression* in the
    artifact row (I4, structural).
  - **§6.5** — audit: registering the handoff artifact writes an **immutable `coord.audit_log` row** (event
    `artifact registered` / kind `handoff`, with `principal` + `initiated_by_user_id` §12.4 + fence + timestamp).
  - **§6.6** — the same transaction writes a **domain event to the `outbox`** (§17.4) for the relay (Story 2.5).
  - **§6.2/§6.3** — the fenced **claim** + **fence-first reclaim**: the *only* custody path. This story writes
    an artifact; it **must not touch the `claim` row**.
  - **§7.3** — the memory **trust boundary**: `memory_write` is authorized + provenanced (`author_principal /
    author_run_id / author_agent_id / written_at`); `memory_search` returns `{content, author, written_at,
    scope, trust: "untrusted"}`. The handoff **mirror obeys this** so a hostile handoff is *seen, attributed,
    and distrusted*, never silently injected as authority (D6/R9 memory-poisoning defense).
  - **ADR-028** — Context injection & agent handoff trade (handoff = knowledge not custody; fenced §6.2/6.3
    unchanged; snapshot for audit/re-entry §6.4/6.5).
- **Depends on:**
  - **Story 2.1** (`coord` schema — the `artifact`, `audit_log`, `outbox` tables this story writes).
  - **Story 2.2 / 2.4** (the fenced `claim` + reclaim — the custody path the handoff explicitly does *not*
    take; this story asserts custody stays there).
  - **Story 3.1** (Run reconcile) — the handoff write fires at the Run's `collecting` / terminal-or-`Paused`
    boundary and is **content-addressed** so a 3.1 re-entry republishes the identical row (§6.4).
  - **Epic 6 / §7** (memory service — the `memory_write` MCP tool this story mirrors into; "Epic 6.6" in the
    issue = the provenanced memory-write surface, §7.3).
- **Consumed by:** **Story 3.6 / §8.5 Context Assembler** — assembles the next Run's envelope from the handoff
  artifact (§6.5) + work-item provenance + scoped memory recall, at the **untrusted-recall tier**. **Epic 13**
  (the handoff artifact registration is one span on the Run trace).

## The design (authoritative)

**When it fires.** At the Run's `collecting` phase (Story 3.1 §6.4) on the way to a terminal state, **and**
on entry to `Paused` (§8) — i.e. any point where the agent yields the item. The reconciler, holding the
Run's live fence, writes the handoff **in the same transaction** as the phase's audit + outbox rows (§6.5/§6.6).

**What it writes — one content-addressed artifact row (§6.1).**

```
INSERT INTO coord.artifact (work_item_id, run_id, kind, uri, sha256, created_at)
VALUES (:wi, :run, 'handoff', :uri, :sha256, now())
ON CONFLICT (work_item_id, run_id, kind) DO NOTHING   -- §6.4 content-addressed upsert
```

- `sha256` is computed over the **canonically serialized 7-field schema**. A §6.4 re-entry recomputes the
  **same** hash → the `ON CONFLICT DO NOTHING` makes the re-write a **no-op** (never a duplicate handoff row).
- The serialized body (the 7 fields) lives at `uri` (artifact blob store / coord content addressed by
  `sha256`); the row is the durable, audited pointer.
- **Provenance-tagged:** `run_id` + the audit row's `principal` / `initiated_by_user_id` / fence pin *who*
  produced it, in *which* Run, under *which* fence — non-repudiable, matching §6.5.

**What it mirrors — one provenanced memory write (§7.3, the issue's "Epic 6.6").**

```
memory_write(content = serialized_handoff, kind = 'handoff',
             tags = [work_item_id, project, role],
             -- provenance envelope is recorded by the service, not the caller (§7.3 rule 1):
             author_principal / author_run_id / author_agent_id / written_at)
```

Future recall returns it as `{content, author, written_at, scope, trust: "untrusted"}` (§7.3 rule 2) — the
Context Assembler injects it at the **untrusted-recall tier** (§8.5). It is **scope-filtered** (§7.3 rule 3),
so it only enriches Runs on the same team/project. **The mirror is best-effort advisory** — if the memory
service is unavailable the handoff artifact (the audited coord row) still commits; the mirror is a *read
convenience for recall*, not the source of truth, and never gates the Run's terminal transition.

**What it must NOT do (the invariant).** The handoff artifact and its mirror **carry no custody**. The
`artifact` row has no claim/lease/fence column (§6.1); the 7 schema fields are advisory text/refs only —
`next` and `recommended_next` are **suggestions to the control plane / next agent**, not directives that move
the claim; `artifacts_for_downstream` lists **build/PR/output refs** (content), never a claim handle. Custody
moves **only** by the §6.2/§6.3 sequence: the reconciler **releases** A's claim (fenced), the control plane
**re-dispatches** the item, and B **acquires a fresh fenced claim**. B's *only* legible authority to work the
item is **its own fence token from its own acquire** — never "the previous agent told me to."

## Acceptance Criteria

**AC1 — the 7-field structured schema is written to the A2A artifact channel, provenance-tagged.**
Given a Run reaching `collecting`/terminal or entering `Paused`, When the agent hands off, Then it writes a
`coord.artifact` row `kind = 'handoff'` whose body is the standardized 7-field schema
`{did, decisions, next, blockers, findings, recommended_next, artifacts_for_downstream}`, content-addressed by
`sha256`, tagged with `run_id` + the §6.5 audit `principal` / `initiated_by_user_id` / fence. A write missing
a schema field (or with an unknown field) is **rejected** by the standardized-schema validator — the contract
is fixed, not free-form.

**AC2 — registration writes audit + outbox in the same transaction (§6.5/§6.6).**
Given the handoff artifact is registered, When it commits, Then the immutable `coord.audit_log` row (event
`artifact registered`, kind `handoff`, principal + fence + timestamp, §6.5) and the `outbox` domain event
(§6.6) are written in the **same transaction** as the `artifact` insert — so a crash can never leave a
registered handoff with no audit trail, or a phantom event with no artifact.

**AC3 — the handoff is advisory context ONLY; custody stays fenced (the no-P2P crux).**
Given a handoff artifact exists for Run A on work item W, When the next agent B is to pick up W, Then B obtains
custody **only** by a fresh **fenced claim** (§6.2) after A **releases** and the control plane **re-dispatches**
(§6.3) — reading the handoff artifact **never** grants B custody, and the `claim` row (holder/fence) is
**unchanged** by any artifact write or read. And the artifact **exposes no claim/lease/fence field** (§6.1):
`next`/`recommended_next`/`artifacts_for_downstream` are advisory content, structurally incapable of moving
the claim. If the handoff could authorize B to work W without B's own fenced acquire, that is the forbidden
P2P back-channel.

**AC4 — content-addressed idempotency under §6.4 re-entry.**
Given the Story 3.1 reconciler re-enters `collecting` after a crash, When it re-writes the handoff, Then the
**same `sha256`** over the identical serialized schema makes the insert a **no-op** (`ON CONFLICT
(work_item_id, run_id, kind) DO NOTHING`) — **exactly one** handoff row per `(work_item_id, run_id)`, never a
duplicate, matching §6.4.

**AC5 — the memory mirror is provenanced and untrusted-tiered (§7.3); best-effort, never custody.**
Given the handoff is registered, When it is mirrored to memory, Then the `memory_write` records the §7.3
provenance envelope (`author_principal / author_run_id / author_agent_id / written_at`) and later
`memory_search` returns it as `{…, trust: "untrusted"}` — so the Context Assembler injects it at the
untrusted-recall tier (§8.5), and a **poisoned** handoff is attributable and distrusted, never injected as
authority. And the mirror is **best-effort**: a memory-service outage does **not** fail the Run's terminal
transition (the audited coord artifact is the source of truth), and the mirror grants **no** custody.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/handoff-advisory-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same discipline as the Story 2.4 reclaim-fencing check), targeting the load-bearing invariant:

- **(A) NAIVE handoff** treats the artifact as a **custody transfer**: it carries a `grant_custody_to` field
  and the next agent B begins working W on the strength of the artifact alone — **no fenced claim**. The check
  asserts the naive design **detectably** lets B hold W without an acquire (two "holders", a P2P hand-off) —
  proving the harness can catch a custody leak. If it ever stops leaking, the test fails **loud** (teeth lost).
- **(B) §8.5 ADVISORY handoff** writes a content-only artifact (no custody field) and mirrors it to memory;
  B can obtain custody **only** via the §6.2 fenced acquire after A's release. The check asserts: reading the
  handoff **never** mutates the `claim` row; B holds W **iff** B did its own fenced acquire; the sole custody
  discriminator remains the **fence** (§6.2/6.3) — not the artifact.
- **(C) content-addressed idempotency** (AC4) — a re-entered `collecting` re-writes the identical schema →
  the `sha256` upsert yields **exactly one** handoff row; removing the content-address guard makes it fail loud.
- **(D) schema validity** (AC1) — the standardized-schema validator **rejects** a handoff missing a field or
  carrying an unknown field; a valid 7-field handoff is accepted.
- **(E) memory-mirror provenance** (AC5) — the mirror returns `trust: "untrusted"` with a full provenance
  envelope; a **naive** mirror that stores bare text (no provenance) is shown to let a poisoned handoff read
  back as trusted authority (teeth) — and the best-effort path: a memory outage does **not** roll back the
  committed handoff artifact.

Exits non-zero if (A) ever stops leaking custody (harness toothless), or if (B)–(E) ever let the artifact move
custody / mutate the claim / produce a duplicate handoff / accept a malformed schema / drop mirror provenance /
let a memory outage lose the committed artifact.

## Out of scope (owned elsewhere)

- **The Context Assembler that consumes the handoff** into the next Run's envelope (Story 3.6, §8.5) — this
  story *produces* the artifact + mirror; 3.6 *reads* them at the untrusted-recall tier.
- **The Run reconcile state machine** that drives `collecting`/terminal (Story 3.1, §8) — this story is the
  handoff-write *action* at that boundary, not the machine.
- **The fenced claim / reclaim** custody mechanism itself (Stories 2.2/2.4, §6.2/6.3) — this story *asserts*
  custody stays there; it does not implement it.
- **The outbox relay to NATS** (Story 2.5, §17.4), **the memory service internals / embedder** (Epic 6, §7),
  **the Run trace/spans** (Epic 13.1). This story ships the **structured handoff schema + content-addressed
  provenance-tagged artifact write (§6.5) + provenanced memory mirror (§7.3) + the advisory-only invariant and
  its falsification** — the coordinator feedback loop that stays knowledge, never custody.
