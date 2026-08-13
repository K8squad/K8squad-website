# Story 6.1: `ksquad-memory` Go service — Postgres + pgvector, the `memory_records` schema

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS STORY LAYS THE KNOWLEDGE-RECORD SUBSTRATE THE WHOLE OF EPIC 6 STANDS ON (arch §7.1/§7.2,
> AD-6, ADR-004, OQ10, FR-E1).** The load-bearing invariants are: **(1)** semantic search runs **on
> `pgvector`** — a `vector(dim)` column + an ANN index + a pgvector distance operator in the query —
> **not** a bespoke in-process vector engine (OQ10 — *integrate the store, don't invent one*); **(2)**
> the `memory_records` schema carries **every** FR-E1 column with the **right type** — most critically
> `embedding` as a real `vector` type, and the **scope + provenance columns** (`squad_id`,
> `principal_id`, `run_id`, `created_at`) that the §7.3 trust boundary is later enforced *over*; **(3)**
> migrations are **forward-only** — memory writes are durable Postgres commits, retraction is the soft
> `invalidated_at` column, never a destructive drop (§7.4). A service that stores embeddings in a
> `bytea`/`json` blob and cosines rows app-side is the **exact OQ10 anti-pattern this story forbids**,
> even though it "returns search results." Read the headline **And** literally: *integrate the store —
> **not** a bespoke vector engine.*

## Story

As **the KSquad platform**,
I want **`ksquad-memory` as a first-class Go service (`cmd/memory`, `internal/memory`) over the shared
Postgres with the `pgvector` extension, whose `db/migrations` create the `memory_records` table and
whose semantic search is pushed into `pgvector` (ANN index + cosine distance operator)**,
so that **squad knowledge is a durable, scoped, provenanced, semantically-searchable record built by
*integrating* a proven vector store rather than inventing a bespoke one (arch §7.1/§7.2, AD-6, ADR-004,
OQ10, FR-E1) — and so the trust boundary (6.3/6.4/6.5) and the MCP tool surface (6.2) have a correct,
complete schema to stand on.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-E1** (first-class memory service), **OQ10** (memory
  build-vs-integrate: *integrate `pgvector`, do not build a bespoke vector engine*), **F5** (memory is
  *parity, not the moat* — least effort that fully satisfies the trust model), **NFR-REL3** (durable
  knowledge record), **NFR-SEC6** (memory is a security surface).
- **Architecture:** `docs/bmad/03-architecture.md` (§ numbers are the current doc's; the epic row's
  "§8.2/§8.4" is the pre-renumber pointer to the **§7 Knowledge Record** section):
  - **§7.1 — Shape & build-vs-integrate (OQ10/F13).** The authoritative decision: the memory service is
    a first-class Go service that **wraps `pgvector`** in the shared Postgres (ADR-001). *"Integrate,
    don't invent."* Embeddings come from a **pluggable embedder** behind a seam (default: a small local
    model in `ksquad-system`, or an allowlisted endpoint) so an air-gapped cluster can swap it; the
    storage/retrieval backend sits behind a `MemoryBackend` seam (§7.6) with **`pgvector` as the default
    and v1 backend**.
  - **§7.2 — Data model (Postgres `memory` schema).** The authoritative column set:
    `memory_record(id, scope_team_id, scope_project_id, kind, content, embedding vector,
    author_principal, author_run_id, author_agent_id, written_at, invalidated_at)` and
    `diary_entry(id, agent_id, team_id, entry, created_at)`. **This story builds `memory_records`**
    (the issue's public spelling of `memory_record`); the `diary_entry` table + the diary tools are
    **6.2**.
  - **§7.3 — Trust boundary (F16 resolution).** Writes are authorized + provenanced (E6), reads return
    an untrusted-provenance envelope (E7), scope is the tenancy boundary (E5). **This story provides the
    *schema substrate* those three rules are enforced over** — the `author_*`/`scope_*` columns and
    their NOT-NULL discipline — but the **enforcement itself is 6.3 (write-auth), 6.4 (untrusted-read),
    6.5 (scoping)**, not here (see Out of scope).
  - **§7.4 — Durability (NFR-REL3).** Memory writes are ordinary Postgres commits; a crash mid-write
    commits or rolls back, never corrupts. `invalidated_at` is the **soft-retract** path (a later
    authorized write supersedes a fact) without destroying the audit trail — so the migration is
    **forward-only** and retraction is a column, not a `DELETE`.
  - **§7.6 — Backend seam / GRAIL fan-out.** `pgvector` is **source-of-truth**; the `MemoryBackend`
    seam and the GRAIL consumer (ISI-2142) are their own Phase-4 stories. v1 = `pgvector`, full stop.
  - **§17.3 — Go backend service layout.** `ksquad-memory` is its **own binary** (MCP server + pgvector,
    also indexes the `discussion` schema §7.5 later), distinct from `ksquad-operator` and
    `ksquad-apiserver`. **Postgres is the sole store of record** (one database; `coord`/`memory`/
    `discussion`/… schemas). This story adds the `memory` schema + `memory_records` table.
- **ADR:** **ADR-004 (Memory build-vs-integrate — integrate `pgvector`; own the trust model)**, arch
  line ~2194: chosen over an in-house vector store and an external vector DB (BYO, excluded by lock).
  **ADR-001 (single Postgres, not a CRD).** Do not re-litigate; implement them.
- **Depends on:** **Epic 1 (CRD types)** for the identifier shapes referenced in provenance
  (`principal_id`, `run_id`, `agent_id` are the same principals/Runs/Agents the coord record uses) and
  **Story 4.1 (squad = namespace tenancy)** for what `squad_id` *means* (a squad **is** a Team = a
  namespace, AD-5) — the scope column the 6.5 tenancy filter will key on. Neither blocks authoring the
  schema; the migration can land ahead of a live embedder (the embedder is config, §7.1).
- **Blocks / is consumed by:** **6.2** (MCP tools `memory.write`/`memory.search` write/query this
  table; `diary_entry` is added there), **6.3** (write-auth enforced over the `author_*` columns this
  story defines), **6.4** (untrusted-read envelope built from these provenance columns), **6.5**
  (tenancy filter over `squad_id`/`project_id`), **6.6** (Context Assembler recall + handoff mirror),
  **Epic X** (the memory-poisoning test attacks reads written to this table).

## What the service + migration provides (the §7.1/§7.2 substrate — authoritative)

1. **The `ksquad-memory` binary skeleton** — `cmd/memory` (main + config: DB DSN, embedder endpoint
   behind the §7.1 seam) and `internal/memory` (store package). It is a **distinct binary** from the
   operator/apiserver (§17.3). On start it **applies `db/migrations`** (or verifies they are applied)
   and **fails closed** if the `vector` extension is absent or the schema is at an unexpected version.
   The MCP tool surface itself is **6.2** — this story stands up the service + store, not the tools.

2. **`CREATE EXTENSION IF NOT EXISTS vector`** in the migration — the service **integrates** `pgvector`
   (ADR-004/OQ10). If the extension cannot be created (image without pgvector), the service fails
   closed with a legible error, never silently degrading to an app-side scan.

3. **The `memory_records` table** in a dedicated `memory` schema, with the FR-E1 columns. The issue's
   public column names map 1:1 to the §7.2 authoritative names — **pin this reconciliation** so the DDL
   and the arch agree:

   | Issue (this story) | Arch §7.2 | Role | NULL? |
   |--------------------|-----------|------|-------|
   | `id` | `id` | PK (uuid) | NOT NULL |
   | `squad_id` | `scope_team_id` | tenancy root (§7.3.3 filter, 6.5) | **NOT NULL** |
   | `project_id` | `scope_project_id` | optional narrower scope | NULL ok |
   | `principal_id` | `author_principal` | write-auth substrate (§7.3.1, 6.3) | **NOT NULL** |
   | `run_id` | `author_run_id` | provenance | NULL ok |
   | `agent_id` | `author_agent_id` | provenance | NULL ok |
   | `kind` | `kind` | record kind (fact/decision/note/handoff-mirror) | NOT NULL |
   | `content` | `content` | the knowledge text | NOT NULL |
   | `embedding` | `embedding vector` | **pgvector `vector(dim)`** | NOT NULL |
   | `created_at` | `written_at` | write time (provenance) | NOT NULL |
   | `invalidated_at` | `invalidated_at` | **soft-retract** (§7.4) | NULL ok |
   | `provenance` | *(envelope)* | `jsonb` — extensible envelope (tags, trust hint, embedder id/model+dim, source) that **complements**, never replaces, the typed provenance columns | NULL ok |

   The typed `author_*`/`scope_*` columns are load-bearing (§7.3 keys on them and NOT-NULL makes an
   unattributed/unscoped row **un-representable**); `provenance jsonb` from the issue is kept as the
   *extensible* envelope on top, **not** as a substitute for the typed columns.

4. **The pgvector ANN index** on `embedding` — an `hnsw` (or `ivfflat`) index with a `vector_cosine_ops`
   opclass — plus a btree index on `squad_id` for the tenancy filter. Semantic search is an
   `ORDER BY embedding <=> $q LIMIT k` **pushed into Postgres**, scoped by `squad_id` and filtered on
   `invalidated_at IS NULL`. The embedding **dimension** is fixed by the configured embedder and
   recorded in `provenance` (model + dim), so a dimension mismatch is detectable, not silent.

5. **Forward-only migration discipline** — versioned SQL under `db/migrations` (same discipline as the
   coord schema, §6.1/§7.4). No `DROP TABLE`/`DELETE`/`TRUNCATE` of the record on the forward path;
   retraction is a soft `invalidated_at` stamp. A crash mid-write commits or rolls back atomically
   (§7.4); the record is never corrupted.

## Acceptance Criteria

**AC1 — the service exists as a first-class Go binary that stands up the store.**
Given `cmd/memory` + `internal/memory`, When the service starts against the shared Postgres, Then it
applies (or verifies) `db/migrations`, ensures the `vector` extension, and reports readiness — and it
**fails closed** (legible error, non-ready) if `pgvector` is absent or the schema version is
unexpected, **never** silently falling back to a bespoke in-app store. It is a **distinct binary** from
`ksquad-operator`/`ksquad-apiserver` (§17.3).

**AC2 — `memory_records` exists with every FR-E1 column at the right type.**
Given the applied migration, When the schema is inspected, Then `memory_records(id, squad_id,
project_id, principal_id, run_id, agent_id, kind, content, embedding, created_at, invalidated_at,
provenance)` exists, **`embedding` is a pgvector `vector(dim)` column** (not `bytea`/`json`/`float[]`
in text), `provenance` is `jsonb`, and the load-bearing scope/provenance columns (`squad_id`,
`principal_id`, `created_at`) are **NOT NULL** so an unscoped/unattributed row is not representable
(the §7.3 substrate). Column naming reconciles to §7.2 per the table above.

**AC3 — semantic search runs ON pgvector (integrate, don't invent — OQ10, the crux).**
Given records with embeddings, When the service performs a semantic search, Then the query is pushed
into Postgres/`pgvector`: it uses an **ANN index** (`hnsw`|`ivfflat` with a `vector_*_ops` opclass) on
`embedding` and a **pgvector distance operator** (`<=>` cosine / `<#>` / `<->`) in an
`ORDER BY embedding <=> $q LIMIT k`, scoped by `squad_id` and filtered on `invalidated_at IS NULL`.
Search that pulls rows and cosines them **in the service process** (a bespoke vector engine) is a
**construction failure**, not a performance nit — it is the exact OQ10 anti-pattern ADR-004 forbids.

**AC4 — migrations are forward-only; retraction is soft (durability, §7.4/NFR-REL3).**
Given the `db/migrations`, When they apply, Then the forward path contains **no** `DROP TABLE`/`DELETE`/
`TRUNCATE` of `memory_records`, an `invalidated_at` column provides the **soft-retract** path (a later
authorized write supersedes a fact without destroying the audit trail), and a write is an ordinary
atomic Postgres commit (crash mid-write commits or rolls back, never corrupts the record).

**AC5 — pgvector is the v1 source-of-truth behind the seam (no premature backend swap).**
Given the `MemoryBackend` seam (§7.1/§7.6), When v1 ships, Then `pgvector` is the **default and only**
backend wired; the seam exists so GRAIL/alt backends can plug in later (their own Phase-4 stories) but
v1 introduces **no** second store of record — **Postgres is the sole store** (§17.3, ADR-001). The
embedder is **config behind a seam** (§7.1), so an air-gapped cluster swaps it without touching the
schema or the query path.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/memory-service-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check: it models the *schema + the semantic-search query plan a memory service would
define* for `memory_records`, then asserts the FR-E1 / OQ10 / §7 invariants. It first proves a
**naive** service — embeddings in a `bytea` blob, **no** ANN index, an **app-side linear-scan** search,
**no** scope/provenance columns, and a **destructive re-create** migration — **fails** every invariant
(so the harness demonstrably detects the OQ10 anti-pattern), then proves the §7 schema **passes** them
all.

```
[model] naive/bespoke engine : 15 invariant violation(s) -> DETECTED
[model] §7 pgvector schema  : 0 violations (clean)
[model] PASS — bespoke engine detectably breaks FR-E1/OQ10; §7 pgvector schema holds schema-completeness, integrate-not-invent, trust-substrate, and forward-only durability.
```

It encodes as assertions over the modeled schema/query-plan: **(INV1, AC2)** every required column
present with the right type — `embedding` a pgvector `vector(dim)`, not a blob; **(INV2, AC3 — the
crux)** semantic search runs on pgvector: a `vector` column **and** an ANN index (`ivfflat`|`hnsw` +
`vector_*_ops`) **and** a pgvector distance operator (`<=>`/`<#>`/`<->`) in the plan — an app-side
cosine scan is a violation *even if it returns results*; **(INV3, AC2/§7.3)** the scope/provenance
columns exist and the load-bearing ones are NOT NULL (unscoped/unattributed rows un-representable);
**(INV4, AC4)** the migration is forward-only (no `DROP`/`DELETE`/`TRUNCATE` of the record) and
`invalidated_at` gives soft-retract. It exits non-zero if the naive service *stops* violating (teeth
lost) or the §7 schema *ever* violates one invariant.

**Mutation contract (teeth, verified):** starting from the §7 schema — delete the ANN index **and**
swap the `<=>` plan for an app-side cosine scan → **RED** (3 INV2/OQ10 violations); make `principal_id`
nullable → **RED** (INV3); make the migration `DROP TABLE memory_records` → **RED** (INV4). The
integrate-not-invent crux (AC3) is the primary tooth.

**AC1 (service skeleton / fail-closed start) and AC5 (single-backend v1 / embedder seam)** are pinned
in prose here and exercised by the **service integration test** the dev writes against a real
Postgres+pgvector container (the model check guards the *static schema/query-plan shape* — AC2/AC3/AC4
— which is the construction-time crux). A real-pgvector integration test — apply the migration, insert
an embedding, run the `<=>` ANN search, assert the index is used and results come back scoped — is the
runtime gate, analogous to Story 2.7's real-PG arm for the coord schema.

## Out of scope (owned elsewhere)

- **MCP tool surface** `memory.write` / `memory.search` / `diary.append` / `diary.read` and the
  `diary_entry` table (**6.2**, §7.1 tool table) — this story stands up the service + `memory_records`
  store; the tools and the diary table are 6.2.
- **Write authorization + provenance *enforcement*** (**6.3**, §7.3.1, FR-E6) — this story provides the
  `author_*` columns + NOT-NULL substrate; **rejecting** unattributed/unauthorized/impersonating writes
  at the service is 6.3.
- **Untrusted-read provenance envelope** (**6.4**, §7.3.2, FR-E7) — reads returning
  `{content, author, written_at, scope, trust:"untrusted"}` and the poisoning defense are 6.4.
- **Tenancy filter / per-principal scoping *predicate*** (**6.5**, §7.3.3, FR-E5) — cross-tenant
  deny-by-construction over `squad_id`/`project_id` is 6.5; this story only guarantees the columns exist
  and are NOT NULL.
- **Scoped recall for the Context Assembler + handoff-artifact mirror** (**6.6**, §7.3/§8.5, ADR-028).
- **`MemoryBackend` alt backends + GRAIL fan-out** (**§7.6**, ISI-2142, Phase-4 stories) — v1 is
  `pgvector` source-of-truth; the seam exists but no second backend is wired.
- **Discussion-room indexing** (**§7.5**, Epic 10) — the memory service indexes `discussion` later;
  not this story.
