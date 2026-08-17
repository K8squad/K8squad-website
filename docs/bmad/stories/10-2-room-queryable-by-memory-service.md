# Story 10.2: Discussion room queryable by the memory service — pgvector projection under the untrusted-read envelope

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧠 THE ROOM BECOMES RECALLABLE KNOWLEDGE — BUT ONLY AS DISTRUSTED, ATTRIBUTED TALK (arch §7.5,
> §7.3.2, ADR-019/ADR-004).** The load-bearing invariant: a discussion message handed to an agent through
> the memory surface is returned under the **identical untrusted-provenance envelope as memory (§7.3.2)** —
> *cited, attributed, and marked `trust: "untrusted"`* — knowledge to **weigh, never authority to act on.**
> A search that surfaces room content as trusted context, or that lets one Team read another Team's room,
> is the exact anti-pattern this story forbids — even though it "returns relevant messages." The room is
> *how people and agents reason in the open*; it is **never** a channel an agent mines as trusted input
> (the §7.5 fence holds *regardless of backing store*).

## Story

As **an agent**,
I want **room content indexed by the `ksquad-memory` service in pgvector and returned through `memory_search`
(and a scoped `discussion_search(project)` MCP tool) under the same untrusted-provenance envelope and the
same Team-scope tenancy filter as memory**,
so that **decisions, context, and Q&A written in the discussion room are semantically recallable as
*distrusted, attributed* knowledge (§7.5, §7.3.2) — reusing the Epic 6 trust boundary verbatim, inventing
no second trust model, and never letting the room become trusted or cross-tenant.**

## Context & prerequisites (read first)

- **Epics source:** `docs/bmad/04-epics-and-stories.md` §Epic 10 row 10.2 (L557). *"Fast-follow acceptable
  post-v1 if the memory surface slips — flag at Gate 2."*
- **Architecture:** `docs/bmad/03-architecture.md`:
  - **§7.5 — memory-queryable (AUTHORITATIVE).** *"The memory service indexes discussion messages in
    `pgvector` and returns them through `memory_search` (and a scoped `discussion_search(project)` MCP
    tool) under the **identical untrusted-provenance envelope** (§7.3.2): a discussion message handed to an
    agent is cited, attributed, and marked `trust: "untrusted"` — consumed as knowledge to weigh, never as
    authority."* *"ISI-2147's 'memory-backed' framing is satisfied by the pgvector projection — but the
    fence holds regardless of backing store."*
  - **§7.3.2 — untrusted-read envelope (F16, FR-E7).** Reads return `{content, author, written_at, scope,
    trust:"untrusted"}`. The **exact** envelope 10.2 reuses — no new read shape.
  - **§7.3.3 — scope is the tenancy boundary (FR-E5).** Cross-tenant deny-by-construction over Team/Project
    scope. `discussion_search` reuses this filter unchanged.
  - **§17.3 — Go backend layout.** `ksquad-memory` "also indexes the `discussion` schema §7.5 later" —
    this is that story. Postgres is the sole store; pgvector is the index (ADR-004).
- **ADR:** **ADR-019** (discussion memory-projected, coordination-free), **ADR-004** (memory =
  integrate pgvector, own the trust model), **ADR-001** (single Postgres).
- **Depends on:** **10.1 (the `discussion` schema + provenance columns — the projection source)** and
  **Epic 6 — memory service (ISI-2222 done), the untrusted-read envelope (6.4 done), the tenancy filter
  (6.5 done), and the pgvector store (6.1 done).** All satisfied; this story wires discussion into the
  existing memory index + read path, it does not build a new store or a new trust model.
- **Blocks / is consumed by:** the Context Assembler recall path (6.6) — room decisions become recallable
  context; **10.4** (the untrusted-read posture is part of why the room cannot become authority).

## What this story provides

1. **A discussion indexer in `ksquad-memory`.** The memory service projects `discussion_message` rows into
   its pgvector index — either as `memory_records`-shaped projections carrying the discussion provenance
   (`author_principal`/`author_agent_id`/`author_run_id`/`project_id`/`team_id`/`created_at`), or by
   indexing the `discussion` schema directly behind the existing `MemoryBackend` seam (§7.6). **Soft-
   retracted messages (`invalidated_at IS NOT NULL`) are excluded from the index / search results** (the
   read side of §7.4, mirroring Story 6.1 AC4). Indexing is **best-effort and post-commit** — a lagging or
   down indexer never blocks a room write (10.1) or a Run.

2. **`memory_search` surfaces room content under the untrusted envelope.** A relevant discussion message is
   returned in the **same `{content, author, written_at, scope, trust:"untrusted"}` shape** as any memory
   read (§7.3.2) — no bespoke discussion read shape, no `trust:"trusted"` path. The `author` carries the
   discussion provenance (principal, agent-vs-human, Run linkage); `scope` carries Project/Team.

3. **A scoped `discussion_search(project)` MCP tool.** Same envelope, narrowed to one Project's room —
   Project/Team-scoped, cross-tenant deny (§7.3.3), retracted-excluded. Rides Epic 6's `pkg/mcp` seam
   (fail-closed on a KG/index cut, per 6.2), like the other memory tools.

4. **Room writes carry the memory write-auth + provenance contract (10.1 AC3 restated as a boundary
   assertion).** The provenance the envelope cites is the **server-stamped** `author_*` from 10.1 — the
   indexer never invents or trusts a client-supplied author. Provenance in = provenance out; no laundering.

## Acceptance Criteria

**AC1 — room messages are indexed in pgvector and semantically searchable.**
Given `discussion_message` rows (10.1), When the memory service indexes them, Then a semantic
`memory_search` over the pgvector index surfaces relevant room messages, scoped by Team/Project, with the
search pushed into pgvector (ANN + distance operator — the Story 6.1 AC3 property, reused, **not** an
app-side scan).

**AC2 — reads return the IDENTICAL untrusted-provenance envelope (the crux, §7.3.2).**
Given a room message surfaced by `memory_search` or `discussion_search`, When it is handed to an agent,
Then it is returned as `{content, author, written_at, scope, trust:"untrusted"}` — the **same** envelope
as any memory read — cited, attributed, and marked `trust:"untrusted"`. There is **no** trusted read path
for room content; a room message is **never** returned as authority/control input.

**AC3 — `discussion_search(project)` is Project-scoped and cross-tenant deny (§7.3.3, NFR-SEC7).**
Given the scoped tool, When an agent in Team B queries a Team A Project's room, Then it receives **zero
rows** — the same namespace/Team-scope tenancy filter that gates memory reads applies unchanged; the room
never crosses tenancy boundaries.

**AC4 — soft-retracted messages do not resurface on read (§7.4 read side).**
Given a message with `invalidated_at` set (10.1 soft-retract), When `memory_search`/`discussion_search`
runs, Then the retracted message is **excluded** from results — retraction is honored on read, not just on
write (mirrors Story 6.1 AC4).

**AC5 — indexing is best-effort/post-commit; the room + Runs never hard-depend on it.**
Given the indexer, When it lags or is unavailable, Then room writes (10.1) and Runs proceed unaffected —
indexing catches up (the §7.6/§17.4 decoupling, same posture as the outbox relay never blocking a claim).
The provenance cited on read is the **server-stamped** `author_*` from 10.1 — the indexer neither invents
nor trusts a client-supplied author (10.1 AC3 boundary).

## Test guidance

Extend/author `docs/bmad/spikes/bench/discussion-memory-check.py` — stdlib-only differential model of the
*index + read plan*. Prove a **naive** projection — room content returned `trust:"trusted"`, **no** Team-
scope filter, retracted rows included — **fails**, then the §7.5 projection **passes**.

Invariants: **(INV1, AC2 — crux)** every room read carries `trust:"untrusted"` and the full
`{content, author, written_at, scope}` envelope — a `trusted` room read is a violation *even if it returns
correct content*; **(INV2, AC1)** search runs on pgvector (ANN + distance op), not an app-side scan;
**(INV3, AC3)** the read plan is scoped by Team/Project; **(INV4, AC4)** the plan filters
`invalidated_at IS NULL`.

**Mutation contract (teeth):** flip a room read to `trust:"trusted"` → **RED** (INV1); drop the Team-scope
predicate → **RED** (INV3); include retracted rows → **RED** (INV4); swap the ANN search for an app-side
cosine scan → **RED** (INV2). The untrusted-envelope crux (INV1/AC2) is the primary tooth.

A real-pgvector **integration test** (reusing the Story 6.1 harness): index a discussion message, run
`discussion_search`, assert the returned object is `trust:"untrusted"` with correct provenance, assert a
cross-Team query returns zero rows, assert a retracted message is absent.

## Out of scope (owned elsewhere)

- **The `discussion` schema + write API + server-stamped provenance** (**10.1**) — the projection source.
- **The pgvector store, ANN index, and untrusted-read envelope machinery** (**Epic 6 — 6.1/6.4/6.5, done**)
  — reused, not rebuilt.
- **Console rendering of search results** (**10.3 / §13**).
- **GRAIL/alt memory backends** (**§7.6, Phase-4**) — v1 is pgvector source-of-truth.

## Gate-2 note

Per the epic, this story is **fast-follow-acceptable post-v1 if the memory surface slips** — flag at
Gate 2. 10.1 (schema/API) and 10.3 (console) can ship a usable room without 10.2; 10.2 adds recall. It
does **not** gate the room's existence or its coordination-free guarantee (10.4).
