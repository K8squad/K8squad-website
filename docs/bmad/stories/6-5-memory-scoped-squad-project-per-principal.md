# Story 6.5: Memory scoped to squad/Project + per-principal — cross-tenant read/write denied *by construction*, and one principal cannot write another's diary

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔐 THIS STORY IS THE *TENANCY* RULE OF THE MEMORY TRUST BOUNDARY (arch §7.3 rule 3, FR-E5,
> NFR-SEC5).** 6.3 (ISI-2224, DONE) makes a write's *author* honest — *"impersonation impossible by
> construction."* 6.4 (ISI-2225, DONE) makes every *reader* distrust it — the untrusted-provenance
> envelope. **6.5 owns the one thing neither does: *which tenant may read or write at all.*** Arch
> §7.3 rule 3 verbatim: *"Every read/write is filtered by `scope_team_id` (+ optional project).
> Cross-tenant read/write is denied by construction; the service never issues an unscoped query.
> Per-principal partitioning bounds what one compromised agent can influence."* Two load-bearing
> invariants, each with a single seductive-wrong implementation:
> **(1) cross-tenant read/write is denied *by construction* — the scope is the caller's
> server-authenticated tenant, never a request field, and the service never issues an unscoped query.**
> The design that filters by a caller-supplied `scope` argument lets squad S2 read squad S1 *by asking
> nicely* (`memory_search(query, scope="team-S1")`); the design that runs the unscoped pgvector search
> and post-filters in the shim not only invites a leak on any bypass, it *silently corrupts recall* —
> a higher-ranked cross-tenant row evicts the caller's own in-tenant match from the top-k window. This
> is the exact tenancy-side mirror of 6.3's *"author stamped, not supplied"* and 6.4's *"trust stamped,
> not supplied"*: here the **tenant** is stamped, not supplied.
> **(2) per-principal partitioning — one principal cannot write another's diary.** `diary_append`
> stamps the partition key (`agent_id`) from the caller's authenticated principal; a design that honors
> a caller-supplied target agent lets principal B forge principal A's private working memory. Read the
> ACs literally: a read/write that trusts a *request-supplied* scope or target principal, and a service
> that *ever* issues an unscoped query, are **correctness failures**, not conveniences.

## ⚠️ Scope reconciliation — 6.5 vs the rest of Epic 6, and the stale §8.3/§8.4 cite (read first)

Epic 6 splits the memory service across six stories that all touch the same trust boundary; **6.5 owns
the *tenancy + per-principal scope* rule and nothing else.** The epic table (§8.3/§8.4) numbering is
**stale**: the memory trust boundary — including its tenancy rule — was consolidated into **arch §7.3**
during the r5 fold (ISI-2151). This story cites the **live §7.3 rule 3 (§7.3.3)**; the §8.3/§8.4 epic
labels map onto it 1:1 (the same remap the 6.4 story records for §8.4→§7.3.2).

| Concern | Owned by | This story (6.5) |
|---|---|---|
| The `ksquad-memory` Go service + `memory_record` schema (incl. `scope_team_id` / `scope_project_id` columns) + `diary_entry(agent_id, team_id, …)` + pgvector | **6.1** (§7.1/§7.2) | consumed — 6.5 filters *over* the scope columns, does not create them |
| The MVP MCP tool surface (`memory_search(query, scope)`, `memory_write`, `diary_append`, `diary_read`) | **6.2** (§7.1, §10.2) | consumed — 6.2 pins the tool surface; **6.5 makes every call resolve scope+principal from the caller** |
| **Writes authorized + provenanced** — author server-stamped, impersonation impossible by construction | **6.3** (§7.3.1, FR-E6) — DONE | sibling — 6.3 stamps the *author*; **6.5 stamps the *tenant + diary partition*** (the same "stamped, not supplied" shape) |
| **Reads as untrusted input with provenance** — the `{content, author, written_at, scope, trust}` envelope | **6.4** (§7.3.2, FR-E7) — DONE | sibling — 6.4 *surfaces* `scope` in the envelope; **6.5 *enforces the cross-tenant deny* on the query that produced it** |
| **Scope/tenancy — per-squad/Project + per-principal, cross-tenant read/write DENY by construction; one principal cannot write another's diary** | **THIS STORY (6.5)** (§7.3.3, FR-E5, NFR-SEC5) | the enforcement + its falsification (S/D/W/P/C) |
| Context-Assembler **scoped recall** as the untrusted-recall tier | **6.6 / 3.6** (§8.5, ADR-028) | consumed — 6.6 requests recall; **6.5 guarantees that recall is squad/Project-scoped** before the envelope wraps it |

**One-line boundary:** 6.1 answers *"where does memory live?"*; 6.2 answers *"what tools?"*; 6.3 answers
*"what must a write prove?"*; 6.4 answers *"what shape does a read return?"*; **6.5 answers *"which
tenant / principal may read or write at all?"*** — the scope predicate is the caller's *authenticated*
tenant, the service *never* issues an unscoped query, and the diary partition is the caller's *own*
principal. 6.5 is the tenancy twin of 6.3/6.4: all three are *"stamped by the server, not supplied by
the request."* The tenancy boundary is **the same boundary as the K8s namespace-per-squad model**
(Epic 4.1 / ISI-2207, *"matches the namespace model, AD-5"*): `scope_team_id` is the squad tenancy
axis, and cross-tenant deny is the memory-layer mirror of the default-deny NetworkPolicy.

## Story

As **a tenant (squad) on the shared memory service**,
I want **every memory read and write filtered by the caller's *server-authenticated* `scope_team_id`
(+ optional `scope_project_id`) — the scope derived from the caller's identity, never from a
request-supplied argument, and the service *never* issuing an unscoped query — so a principal in squad
S2 can neither read nor write squad S1's records even by asking for S1's scope; and every diary write
stamped to the caller's *own* principal so one principal cannot write (or read) another's diary**,
so that **shared memory is genuinely multi-tenant: squad S1's knowledge and each principal's private
diary are unreachable to squad S2 / to another principal *by construction* (FR-E5, NFR-SEC5) — the
tenancy rule of CEO Gate 1's F16 memory boundary, aligned with the namespace-per-squad isolation model
(AD-5, Epic 4.1), bounding what one compromised agent can read or influence and completing the memory
trust boundary alongside 6.3's honest author and 6.4's untrusted-read envelope.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-E5** (*"The memory record SHALL be scoped to its squad/`Project`
  and SHALL NOT leak across tenancy boundaries"*, MVP — the direct requirement), **NFR-SEC5**
  (per-principal isolation), **FR-E6** (writes authorized + provenanced — 6.3, the author-stamp shape
  6.5 mirrors for the tenant), **FR-E7** (untrusted reads + per-principal trust boundaries — 6.4),
  **FR-E8** (the `MemoryBackend` seam — scope is enforced *above* it, backend-independent). PRD
  §"Scope is the tenancy boundary" (*"Records are squad/`Project`-scoped and per-principal-attributed;
  cross-tenant read/write is denied by construction"*).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§7.3 rule 3 (§7.3.3) "Scope is the tenancy boundary (FR-E5)"** — *the authoritative source for
    this story.* Verbatim: *"Every read/write is filtered by `scope_team_id` (+ optional project).
    Cross-tenant read/write is denied by construction; the service never issues an unscoped query.
    Per-principal partitioning bounds what one compromised agent can influence."*
  - **§7.2 data model** — `memory_record(… scope_team_id, scope_project_id, …)`,
    `diary_entry(id, agent_id, team_id, entry, created_at)` (the scope/partition columns 6.5 filters on).
  - **§7.6** — the `MemoryBackend` seam (pgvector v1 / GRAIL): scope is enforced *above* the seam;
    the backend is opaque storage and never sees the caller.
  - **§12.4** — agent execution identity: the Run carries a non-forgeable, control-plane-stamped
    caller (`initiatedByUserId` / owning principal / team) — the *source* of the scope, never a request field.
  - **§7.5** — the discussion room reuses *"the same namespace/Team-scope filter that gates memory
    reads"* (FR-J4/NFR-SEC7) — 6.5's filter is the one that story references.
  - Namespace-per-squad tenancy: **§4.1 / ISI-2207** (Team→namespace 1:1, default-deny) — the AD-5
    model this boundary aligns to.
- **Epic:** `docs/bmad/04-epics-and-stories.md` Story 6.5 — *"Given records in squad S1, When a
  principal in squad S2 queries, Then cross-tenant read/write is denied by construction (matches the
  namespace model, AD-5); And one principal cannot write another's diary."*

## Acceptance criteria

1. **AC1 — the service never issues an unscoped query (S).** Every read pushes the caller's
   `scope_team_id` predicate INTO the backend query, *before* the pgvector top-k — never an unscoped
   full-corpus scan post-filtered in the shim. An unscoped query silently corrupts recall (a
   higher-ranked cross-tenant row evicts the caller's own in-tenant match from the top-k window), so
   "never an unscoped query" is a **correctness** invariant, not only a hygiene one.
2. **AC2 — cross-tenant READ denied by construction (D).** The effective scope is derived from the
   caller's server-authenticated tenant; a caller in S2 that *requests* `scope=S1` is still bound to
   S2. A request may only ever narrow *within* the caller's own tenant, never widen past it. (The
   optional `scope_project_id` narrows further within the team; it can never widen beyond it.)
3. **AC3 — cross-tenant WRITE denied by construction (W).** A write's `scope_team_id` is stamped from
   the caller's tenant; a principal in S2 cannot plant a record INTO S1's scope (a poisoning vector: a
   write a victim tenant would later recall as context).
4. **AC4 — per-principal diary write (P).** `diary_append` stamps the partition key (`agent_id`) from
   the caller's authenticated principal; a caller-supplied target agent is ignored — **one principal
   cannot write another's diary** (the story's explicit second AC).
5. **AC5 — uniform choke, no bypass, above the backend seam (C).** Every read AND write path
   (`memory_search`, `memory_write`, `diary_append`, `diary_read`) resolves scope + principal from the
   caller through the *same* server-side derivation, enforced ABOVE the opaque `MemoryBackend` (§7.6).
   No single path (e.g. a `diary_read` honoring a caller-supplied target) may bypass the boundary the
   others hold.
6. **AC6 — non-vacuous + backend-independent.** In-tenant reads/writes and same-principal diary access
   still succeed (the boundary denies *cross*-tenant/cross-principal, not *everything*), and the
   enforcement holds regardless of backend (pgvector v1 or GRAIL), because it sits above the seam.

## Falsification (the teeth)

`docs/bmad/spikes/bench/memory-scope-tenancy-check.py` — stdlib-only, models the memory scope path
in-process (real-service/real-PG promotion rides Epic 6.1 + the Go test spine). Five arms, each mapping
to an AC, with a `--mutate=<S|D|W|P|C>` differential (same discipline as `byo-model-endpoint-check.py`
/ `run-mcp-tools-check.py`):

- **S** — the service issues a SCOPED query; the S2 caller's own top-k match survives.
  `--mutate=S` issues the unscoped query + post-filter → the S1 row evicts the S2 match → the caller
  gets NOTHING, and an unscoped query was issued. **S RED.**
- **D** — an S2 caller requesting `scope=S1` is still bound to S2. `--mutate=D` honors the requested
  scope → S2 reads S1's secret. **D RED.**
- **W** — a write is stamped to the caller's tenant. `--mutate=W` honors a caller-supplied write scope
  → S2 plants a record into S1 that an S1 reader then recalls. **W RED.**
- **P** — `diary_append` stamps the caller's own principal. `--mutate=P` honors the target agent →
  principal B forges principal A's diary. **P RED.**
- **C** — `diary_read` is bound to the caller's principal+tenant. `--mutate=C` honors a caller-supplied
  target → a bypass path reads principal A's private diary. **C RED.**

**Verified:** baseline all-GREEN (exit 0); each `--mutate=X` reddens **exactly** arm X (exit 1) — the
mutations are orthogonal, so each of the five guards is *independently* load-bearing (the inverse of
the ISI-2346-F1 teeth-gap; the same non-vacuity bar the ISI-2375 review set). Every arm also asserts
the positive in-tenant behavior, so no arm passes vacuously by denying everything.

## Out of scope (owned elsewhere)

- The untrusted-provenance **envelope shape** itself (`{content, author, written_at, scope, trust}`) —
  **6.4** (ISI-2225). 6.5 surfaces `scope` as the tenancy axis but does not own the envelope contract.
- **Write authorization + author provenance** (who may write, author stamp) — **6.3** (ISI-2224).
- The `memory_record` / `diary_entry` **schema + pgvector** — **6.1**. The MCP **tool signatures** — **6.2**.
- **RBAC / user↔project membership** (human-principal authorization) — **§12.3 / Epic 15**. 6.5 scopes
  by the squad tenancy axis and the diary principal partition; it does not implement the human RBAC wall.
- **Real-PG / real-service** enforcement of the same predicates — **Epic 6.1 + the Go test spine**.

## Dev notes

- The scope is **not a tool argument the agent controls.** `memory_search(query, scope)`'s `scope`
  parameter may only ever *narrow within* the caller's authenticated tenant (e.g. pick a project within
  the team); the team axis is stamped from `§12.4` Run identity. Implement `_effective_scope` as
  `caller.team` (with an optional in-team project narrowing), never `request.scope`.
- **Push the predicate down.** Add `WHERE scope_team_id = $caller_team [AND scope_project_id = …]` to
  the pgvector query itself (the `<->` ORDER BY / LIMIT runs *after* the WHERE); do not `SELECT` the
  corpus and filter in Go. This is AC1's correctness point, not just defense-in-depth.
- The diary partition key is `(team_id, agent_id)` from the caller; `diary_append`/`diary_read` never
  read a target principal from the request.
