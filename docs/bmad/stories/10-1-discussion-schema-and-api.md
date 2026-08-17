# Story 10.1: Discussion schema + API — Postgres `discussion` schema (rooms/threads/messages), append-only, provenance-tagged

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS STORY LAYS THE SUBSTRATE THE WHOLE OF EPIC 10 STANDS ON (arch §7.5, ADR-001, ADR-019,
> Theme J / FR-J1…J4).** The load-bearing invariants: **(1)** the room is a **collaboration/visibility
> surface, NOT a coordination channel** — the `discussion` schema has **no `claim`/`lease`/`fence_token`/
> `state`/`holder` column and no custody-transfer expression**, so it *cannot* be a coordination record
> by construction (§7.5 three-point argument; 10.4 makes this a *tested* guarantee). **(2)** every message
> is **append-only + provenance-tagged** — `author_principal` is **server-stamped** from the authenticated
> context (never client-supplied — the §7.3.1 memory write-auth rule applied again), agent-vs-human is
> derived from `author_agent_id`, and **Run linkage is `author_run_id`** (nullable, set only when posted
> from a Run). **(3)** the schema is **Project/Team-scoped and NOT-NULL where it matters** (`project_id`,
> `team_id`, `author_principal`, `created_at`) so an unscoped or unattributed row is **un-representable** —
> that is the tenancy + provenance substrate 10.2 (memory query) and 10.3 (console) are later enforced
> *over*. A schema that accepts a client-supplied author, or that adds *any* custody column, is the exact
> anti-pattern this story forbids — even though it "stores threaded messages."

## Story

As **the KSquad platform**,
I want **the `discussion` schema in the shared Postgres (`discussion_thread` + `discussion_message`, ADR-001)
and the apiserver REST/tool surface that reads and appends to it — threaded, append-only,
provenance-tagged, Project/Team-scoped, and structurally coordination-free**,
so that **every `Project` has one persistent discussion room (context, Q&A, decisions, announcements) for
all team members — agents and humans — built with the *exact* append-only + provenance discipline of the
§6.1 coordination record and the §7.3 memory trust boundary, giving 10.2 (memory-queryable) and 10.3
(console) a correct, complete, coordination-free surface to stand on.**

## Context & prerequisites (read first)

- **Epics source:** `docs/bmad/04-epics-and-stories.md` §Epic 10 (L542–559). All four ACs pre-written;
  this is the FOUNDATION story that unblocks 10.2/10.3/10.4.
- **Architecture:** `docs/bmad/03-architecture.md`:
  - **§7.5 — Per-Project Discussion Room (Theme J, FR-J1…J4; ISI-2147, ADR-019) — AUTHORITATIVE.** The
    decision: each `Project` gets a Postgres-backed, threaded, provenanced room the memory service can
    query. *"Conversation, not custody."* The schema:
    `discussion_thread(id, project_id, team_id, title, created_by, created_at)` ·
    `discussion_message(id, thread_id, parent_id, author_principal, author_agent_id, body, created_at,
    invalidated_at)`. Threaded via `parent_id`, scoped per Project/Team, every message provenanced with an
    authenticated principal + timestamp — **the same write-auth + provenance rules as memory (§7.3.1)**.
    Soft-retract via `invalidated_at` (§7.4).
  - **§6.1 — Coordination `coord` schema (the discipline to mirror).** Append-only rows with principal +
    timestamp; **"No agent-to-agent channel exists in the schema; there is no `message` table and no
    lateral transport (I4, structural enforcement of no-P2P)."** The discussion room does not violate
    this — see the §7.5 three-point argument: discussion carries *talk*, custody moves *only* in the fenced
    `coord` claim tables. This story keeps that fence structural.
  - **§6.5 — Audit (server-stamped provenance).** Every coord row carries `principal` +
    `initiated_by_user_id`, stamped by the server. Discussion writes stamp `author_*` the **same way** —
    from the authenticated session/token, **never from the request body**.
  - **§7.3.1 — Write-auth + provenance (memory).** Writes are authorized + provenanced; the author is
    stamped, not supplied. Discussion writes carry the identical contract (10.2 AC).
  - **§17.3 — Go backend layout.** Postgres is the sole store of record (one DB; `coord`/`memory`/
    `discussion`/`scm`/… schemas). The `discussion` schema is served by the **apiserver**
    (`ksquad-apiserver`); the memory service *indexes* it later (10.2, §7.5 "memory-queryable").
- **ADR:** **ADR-001 (single Postgres, NOT a CRD — a *schema*, not a new datastore).** **ADR-019
  (discussion-room storage — Postgres `discussion` schema, memory-projected, coordination-free by
  construction).** Do not re-litigate; implement them. **No CRD for rooms** (Epic AC 10.1).
- **Depends on:** **Epic 2 (ISI-2191, coord schema patterns — done)** for the append-only / provenance /
  migration discipline and the principal/Run/Agent identifier shapes referenced in provenance; **Epic 1
  (Project CRD)** for what a `Project` *is* (the room is 1:1 with it). Neither blocks authoring the schema.
- **Blocks / is consumed by:** **10.2** (memory service indexes `discussion_message` into pgvector and
  serves it under the untrusted-read envelope — writes here carry the provenance contract 10.2 asserts),
  **10.3** (console renders threads/messages + provenance badges and posts via this API), **10.4** (the
  covert-channel guardrail is *tested* against this exact schema + API surface).

## Schema-shape confirmation (the epic's open item — resolved, light arch confirmation, NOT a new ADR)

The epic's 10.1 detailing item asks: *confirm the schema shape (rooms/threads/messages tables, provenance
columns) against Arch §6.1/§7.* Two reconciliations between the epic's prose and the authoritative §7.5
column list — both resolved toward the **smaller design** (ADR-001), mirroring how Story 6.1 reconciled
issue column names to §7.2:

**R1 — "rooms table" → the room is the Project (1:1, derived, NO separate table).** §7.5 defines exactly
**two** tables (`discussion_thread`, `discussion_message`); it deliberately has **no** `discussion_room`
table. The room *is* the Project: 1:1 by construction because `discussion_thread.project_id` is the room
key and there is exactly one Project per room. "One persistent room exists when a Project is created"
(epic AC) means the room is **addressable the instant the Project exists** — `GET
/projects/{id}/discussion` returns an (empty) thread list — with **no provisioning step, no finalizer, no
seed row**. This matches the §6.1 discipline of not adding a table you do not need (cf. the `parent_id`
adjacency vs. a join table). If room-level metadata is ever required (a pinned announcement, a room-level
mute), *that* is when a thin `discussion_room(project_id PK, …)` row is introduced — **not now, not in
v1.** **Dev ruling: do NOT create a `discussion_room` table; key everything off `project_id`.**

**R2 — Run linkage → add `author_run_id` (nullable).** §7.5's `discussion_message` column list omits a Run
column, but the epic 10.1 AC requires *"Run linkage when posted from a Run."* Reconcile by adding
**`author_run_id` (NULL ok)** to `discussion_message`, aligning with the memory provenance triple
(§7.2 `author_run_id`). Set only when a message is posted from within a Run (agent tool surface); NULL for
a human console post or a system/bot post. This makes the provenance triple
`author_principal`/`author_agent_id`/`author_run_id` identical to memory's — which 10.2's shared index and
untrusted-read envelope depend on.

## What the schema + API provides (authoritative)

**Tables (`discussion` schema, forward-only migration under `db/migrations`, same discipline as §6.1/§7.4):**

`discussion_thread`
| Column | Type | Role | NULL? |
|--------|------|------|-------|
| `id` | uuid | PK | NOT NULL |
| `project_id` | uuid/text | **room key** — tenancy + 1:1-with-Project (R1) | **NOT NULL** |
| `team_id` | uuid/text | tenancy root (§7.3.3 filter; = squad/namespace) | **NOT NULL** |
| `title` | text | thread title | NOT NULL |
| `created_by` | text (principal) | thread opener, **server-stamped** | **NOT NULL** |
| `created_at` | timestamptz | open time | **NOT NULL** |

`discussion_message`
| Column | Type | Role | NULL? |
|--------|------|------|-------|
| `id` | uuid | PK | NOT NULL |
| `thread_id` | uuid → `discussion_thread(id)` | owning thread | **NOT NULL** |
| `parent_id` | uuid → `discussion_message(id)` NULL | reply-in-thread (adjacency, like §6.1 `work_item.parent_id`) | NULL ok |
| `author_principal` | text | **who** — server-stamped (§7.3.1/§6.5) | **NOT NULL** |
| `author_agent_id` | text NULL | which agent (present ⇒ agent-authored; NULL ⇒ human) | NULL ok |
| `author_run_id` | text NULL | **Run linkage** (R2) — set only when posted from a Run | NULL ok |
| `body` | text | the message | **NOT NULL** |
| `created_at` | timestamptz | write time (provenance) | **NOT NULL** |
| `invalidated_at` | timestamptz NULL | **soft-retract** (§7.4) | NULL ok |

- **agent-vs-human is derived, not a separate flag:** `author_agent_id IS NOT NULL` ⇒ agent; else human.
  `author_principal` is always the authenticated identity. (The console badge — 10.3 — renders
  agent/human/Run from exactly these three columns; no extra `author_kind` column is needed.)
- **NOT-NULL discipline (the substrate):** `project_id`, `team_id`, `author_principal`, `created_at` are
  NOT NULL so an **unscoped or unattributed** row is un-representable — the tenancy (10.2/10.3, NFR-SEC7)
  and provenance (10.2) rules are enforced *over* these columns.
- **NO coordination columns (the fence, structural):** the schema has **no** `claim`, `lease`,
  `fence_token`, `state`, `holder`, `assignee`, or any custody/status column, and **no** custody-transfer
  expression. This is not convention — it is the §7.5 construction 10.4 tests. Custody of a work item
  moves **only** in the fenced `coord` claim tables (§6.2/§6.3).
- **Indexes:** btree on `thread_id` (message fetch), `project_id`/`team_id` (room + tenancy filter),
  `parent_id` (reply subtree). Default reads filter `invalidated_at IS NULL`.

**API surface (apiserver REST, behind the §13 BFF authorization choke point + the §7.3.3 Team-scope
tenancy filter — the same choke point every console read model passes, arch r21 OQ20):**

- `GET  /api/projects/{projectId}/discussion/threads` — list room threads (paged; excludes fully-retracted).
- `POST /api/projects/{projectId}/discussion/threads` — open a thread `{title, body}`; creates thread +
  first message atomically.
- `GET  /api/projects/{projectId}/discussion/threads/{threadId}` — thread + messages (threaded via
  `parent_id`).
- `POST /api/projects/{projectId}/discussion/threads/{threadId}/messages` — post/reply
  `{body, parent_id?}`.
- `PATCH /api/projects/{projectId}/discussion/threads/{threadId}/messages/{id}` — soft-retract (set
  `invalidated_at`); **author or admin only**. No hard delete on the forward path.
- **Agents post via the apiserver tool surface** (MCP tools `discussion_post` / `discussion_reply` — the
  tool *contract* rides Epic 6's `pkg/mcp` seam; wiring the concrete tools MAY be a 10.2/6.2 fast-follow,
  but the REST endpoints above are v1); **humans post via the console** (10.3). Both paths hit the **same
  apiserver handler and the same server-stamping**.
- **Server-stamped provenance (the crux, mirrors §6.5 / §7.3.1):** `author_principal`, `author_agent_id`,
  `author_run_id`, `created_by`, `created_at` are stamped by the server from the authenticated
  session/token/Run context — **NEVER read from the request body.** A body that carries an `author_*` is
  ignored (or 400'd), not honored. This makes impersonation un-representable, exactly as memory writes
  (§7.3.1) and the audit trail (§6.5) do it.
- **NO coordination verb exists on this surface:** there is no endpoint that claims, checks out,
  transitions, completes, or reassigns a work item, and nothing a discussion write does re-enters the
  `coord` record. (10.4 asserts this against the built surface.)

**Downstream seam (noted, not a v1 core AC):** a discussion write MAY emit a best-effort domain event on
the transactional outbox → NATS bus (`ksquad.discussion.{project}.{squad}.message_posted`, §6.6/§17.4) for
plugin observers and the §5.4 CI-failure auto-post path — **one-way, post-commit, never a coordination
path** (the §7.5 no-P2P argument holds: nothing a plugin sees on NATS re-enters coordination). Flagged as
a downstream integration; if implemented it follows the §6.6 outbox pattern (no dual-write).

## Acceptance Criteria

**AC1 — the `discussion` schema exists with both tables at the right shape (Project/Team-scoped, threaded).**
Given the applied forward-only migration, When the schema is inspected, Then `discussion_thread(id,
project_id, team_id, title, created_by, created_at)` and `discussion_message(id, thread_id, parent_id,
author_principal, author_agent_id, author_run_id, body, created_at, invalidated_at)` exist in a dedicated
`discussion` schema (ADR-001 — a schema, **not** a new datastore, **not** a CRD); `parent_id` and
`thread_id` are FKs; and there is **no `discussion_room` table** — the room is the Project, keyed by
`project_id` (R1).

**AC2 — append-only + provenance-tagged, with the load-bearing columns NOT NULL.**
Given the schema, When a message is written, Then `author_principal` and `created_at` (message) and
`project_id`/`team_id`/`created_by`/`created_at` (thread) are **NOT NULL** so an unattributed or unscoped
row is un-representable; agent-vs-human is derived from `author_agent_id`; **Run linkage is
`author_run_id`** (nullable, set only from a Run, R2); and the forward migration path contains **no**
`DROP`/`DELETE`/`TRUNCATE` of the record — retraction is the soft `invalidated_at` stamp (§7.4), default
reads filter `invalidated_at IS NULL`.

**AC3 — provenance is SERVER-STAMPED, never client-supplied (the impersonation fence, §7.3.1/§6.5).**
Given the POST endpoints (and the agent tool surface), When a caller posts a message, Then
`author_principal`/`author_agent_id`/`author_run_id`/`created_by`/`created_at` are stamped by the server
from the authenticated context; an `author_*` field in the **request body is ignored or rejected, never
honored**. A message attributed to a principal the caller is not is **un-representable** through this API.

**AC4 — the schema is structurally coordination-free (the §7.5 fence; 10.4's substrate).**
Given the `discussion` schema and API, When they are inspected, Then there is **no** `claim`/`lease`/
`fence_token`/`state`/`holder`/`assignee` column, **no** custody-transfer expression, and **no** endpoint
that claims/checks-out/transitions/completes/reassigns a work item. Work custody exists **only** in the
fenced `coord` claim tables (§6.2/§6.3). Nothing a discussion write does mutates `coord`. (10.4 turns this
into a *tested* guarantee via the F6 covert-channel case in the L4 suite, ISI-2245.)

**AC5 — reads are Project/Team-scoped behind the shared authz choke point (tenancy, NFR-SEC7).**
Given the GET endpoints, When a principal reads a room, Then the query is filtered by `project_id` **and**
the caller's authorized Team scope (§7.3.3, the same deny-by-default middleware every console read model
passes, arch r21/OQ20); a cross-tenant read returns **no rows / 404-not-403** (mirrors the 8.7d BFF gate),
never another Team's threads. The room **never crosses tenancy boundaries** (FR-J4).

## Test guidance (the falsification)

Author `docs/bmad/spikes/bench/discussion-schema-check.py` — stdlib-only, `python3` it directly. A
**differential** check that models the *schema + write-path a discussion service would define*, then
asserts the FR-J / §7.5 invariants. It first proves a **naive** service — a `discussion_room` table with a
`state`/`holder` column, a **client-supplied `author`**, nullable `project_id`/`author_principal`, and a
**destructive** retract (`DELETE`) — **fails** every invariant (harness has teeth), then proves the §7.5
schema **passes** them all.

Invariants (map to ACs): **(INV1, AC1/AC4 — the crux)** the schema has the two §7.5 tables, **no**
`discussion_room` table, and **no** coordination column (`claim`/`lease`/`fence_token`/`state`/`holder`/
`assignee`) and no custody-transfer verb — a schema with *any* of these is a violation *even if messages
thread correctly*; **(INV2, AC2)** `project_id`/`team_id`/`author_principal`/`created_at` are NOT NULL and
`author_run_id` exists (nullable); **(INV3, AC3)** the write path stamps `author_*` from context and
ignores a body-supplied author — a plan that reads `author` from the request is a violation; **(INV4,
AC2/§7.4)** the migration is forward-only (no `DROP`/`DELETE`/`TRUNCATE`) and the default read filters
`invalidated_at IS NULL`; **(INV5, AC5)** the read plan is scoped by `project_id` **and** Team scope.

**Mutation contract (teeth):** starting from the §7.5 schema — add a `state` (or `holder`/`fence_token`)
column → **RED** (INV1); make `author_principal` nullable → **RED** (INV2); make the write read `author`
from the request body → **RED** (INV3); make retract a `DELETE` → **RED** (INV4); strip the Team-scope
predicate from the read plan → **RED** (INV5). The **coordination-free** crux (INV1/AC4) is the primary
tooth and is the same property 10.4 verifies at runtime.

AC3 (server-stamp) and AC5 (tenancy) are additionally exercised by an **apiserver integration test**
against a real Postgres: post a message with a forged `author` in the body → stored row shows the
authenticated principal, not the forgery; read as a principal in Team B → zero rows from Team A's Project.

## Out of scope (owned elsewhere)

- **Memory indexing + `memory_search`/`discussion_search` + the untrusted-read envelope** (**10.2**,
  §7.5/§7.3.2) — this story provides the provenance columns the envelope is built from; the pgvector
  projection and `trust:"untrusted"` read are 10.2.
- **Console rendering — threaded history, provenance badges, post/reply UI** (**10.3**, §13, mock
  07-discussion-room / ISI-2160) — this story provides the REST/tool surface 10.3 consumes.
- **The tested covert-channel guarantee (F6 evidence in the L4 suite)** (**10.4**, ISI-2245) — this story
  makes the fence *structural*; 10.4 makes it *tested*.
- **Concrete MCP tools `discussion_post`/`discussion_reply` wiring** — the tool *contract* is named here;
  wiring on Epic 6's `pkg/mcp` seam MAY be a 10.2/6.2 fast-follow. The REST endpoints are v1.
- **The outbox→NATS `message_posted` event + CI-failure auto-post** (§6.6/§5.4/§17.4) — a downstream
  plugin-observer seam, not a v1 core AC.

## Dev Agent Record (ISI-2702)

**Delivered (this workspace, verifiable now):**
- **Falsification bench — `docs/bmad/spikes/bench/discussion-schema-check.py` (stdlib-only, GREEN).**
  Differential model: Layer A proves a **naive** discussion service (a `discussion_room`+`state` table,
  client-supplied `author_type`/`author_name`, nullable `project_id`/`author_principal`, `ON DELETE
  CASCADE` destructive retract, team-blind read) fails **all** of INV1–INV5, then proves the §7.5 schema
  passes all five; Layer B is an 11-mutation battery where each single weakening flips its designated
  invariant RED (add `state` col / add room table / add `claim` verb → INV1; null `author_principal` /
  null `project_id` / drop `author_run_id` → INV2; author-from-body → INV3; hard retract / migration
  `DELETE` / drop `invalidated_at` filter → INV4; drop Team-scope predicate → INV5). Run:
  `python3 docs/bmad/spikes/bench/discussion-schema-check.py` → exit 0, all GREEN.
- **Canonical reference DDL — `docs/bmad/implementation/10-1-discussion-schema.sql`.** The authoritative
  `discussion` schema (`discussion_thread` + `discussion_message`, provenance triple, soft-retract, no
  custody column, no room table) the Epic-10 apiserver build materializes verbatim as k8squad
  `db/migrations/0003_discussion_schema.sql`. Kept in the BMAD workspace so k8squad stays BMAD-free.

**⚠ Conflict flagged — a pre-existing anti-pattern migration is on the k8squad tree.**
`k8squad migrations/001_create_discussion_rooms.sql` (landed via `feaf920`, ISI-2147/2253 helm-storage
train) is the **exact shape this story forbids**: a `discussion_rooms` table (R1 violation),
client-supplied `author_type`/`author_name`/`author_id` (AC3 impersonation violation), **no `team_id`**
(AC5 tenancy violation), `ON DELETE CASCADE` + `edited_at` instead of soft `invalidated_at` (AC2
append-only violation), a `metadata jsonb`/`kind` surface, and no `author_principal`/`author_agent_id`/
`author_run_id` provenance triple. It predates the LOCKED `room = Project` decision (ADR-019). The
Epic-10 Go build MUST supersede it with `0003_discussion_schema.sql` (this story's DDL), not extend it —
10.4's covert-channel suite would go RED against the `discussion_rooms` shape. Tracked for the Epic-10
implementer as a first-class blocker on that build.

**Downstream (Epic-10 apiserver build, k8squad, substrate-gated — not this workspace):** materialize the
reference DDL as the forward migration; implement the five REST endpoints behind the §13 BFF authz choke
point with server-stamped provenance; add the apiserver integration test against real Postgres (forged
`author` in body → stored row shows authenticated principal; read as Team B → zero rows from Team A's
Project). The design is falsifiable and the DDL is canonical; the build consumes both.
