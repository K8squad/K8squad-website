# Story 6.2: MCP tools (memory.write/search, diary.append/read) — the memory tool surface as a stable seam

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS STORY SHIPS THE FOUR MVP MEMORY MCP TOOLS AS A *STABLE, VERSIONED WIRE SEAM* — NOT the
> backend (6.1), NOT the trust *enforcement* (6.3/6.4/6.5).** The load-bearing thing 6.2 owns that no
> sibling story owns is **the tool contract itself**: the exact set of tools an agent may call, their
> signatures, their return shapes, and — critically — **the fast-follow cut**. The originating issue
> (ISI-2223) says *"the MVP tool set works … `memory.relate` (KG) is **designed for but not shipped**
> (fast-follow)."* That "designed-but-not-shipped" clause is the crux, and it has a **silent-stub
> failure mode**: a design that registers `kg_add`/`memory.relate` as a no-op returning `ok` lets an
> agent believe a relation persisted when nothing was stored — then `kg_query` returns empty, and the
> agent has silently lost knowledge and built a plan on a phantom edge. **A fast-follow cut that is not
> *fail-closed* is not a cut — it is a data-loss bug wearing a roadmap label.** The seam is also
> load-bearing in two more ways the arch pins: the four MVP signatures must be **stable across the
> pgvector→GRAIL backend swap** (§7.6 `MemoryBackend` seam) and **forward-compatible when KG ships**
> (adding tools, never mutating the four). Read AC3, AC4, AC6 literally.

## ⚠️ Scope reconciliation — 6.2 vs the rest of Epic 6 (read first)

Epic 6 splits the memory service across six stories that all touch the same tools; 6.2 owns the **tool
surface**, and it *consumes* — never re-specifies — the enforcement each sibling owns. The doc-section
numbering in the epics table (§8.1–8.4) is **stale**: the memory service was consolidated into
**arch §7** (§7.1 tool surface, §7.2 data model, §7.3 trust boundary, §7.6 backend seam) during the r5
fold (ISI-2151). This story cites the **live §7.x** sections; the §8.x epic labels map onto them 1:1.

| Concern | Owned by | This story (6.2) |
|---|---|---|
| The `ksquad-memory` Go service + `memory_records`/`diary_entry` schema + pgvector wiring | **6.1** (§7.1/§7.2) | consumed — 6.2 is the *surface over* the store, not the store |
| **The MVP MCP tool set** — which tools exist, their signatures, their return envelope shape, the pinned wire contract | **THIS STORY (6.2)** | the four tools + the pinned-adapter seam (§C) |
| **The KG fast-follow cut** — `memory.relate`/`kg_add`/`kg_query` designed but **not shipped**, fail-closed | **THIS STORY (6.2)** | the real cut, mutation-proven (§B) |
| **Backend-independence** of the tool contract (pgvector v1 ⇄ GRAIL) | **THIS STORY (6.2)** via §7.6 | the seam holds across backends (AC6) |
| Write-time **authorization + provenance** enforcement (reject unattributed/unauthorized) | **6.3** (§7.3.1, FR-E6) | consumed — 6.2 pins the *provenanced-ack wire shape*, 6.3 enforces it |
| **Untrusted-read** posture + poisoning defense (surface provenance, `trust:"untrusted"`) | **6.4** (§7.3.2, FR-E7) | consumed — 6.2 pins the *return-envelope shape*, 6.4 enforces the posture |
| **Scope/tenancy** — per-squad/Project + per-principal, no cross-tenant leak | **6.5** (§7.3.3, FR-E5) | consumed — 6.2 pins that every tool *takes a scope* and never issues an unscoped call |
| Context-Assembler **recall** into a Run envelope + handoff **mirror** | **6.6** (§7.3, ADR-028) | consumed — 6.6 is a *caller* of `memory_search`/`memory_write` |

**One-line boundary:** 6.1 answers *"where does memory live?"*; 6.3/6.4/6.5 answer *"what does a
write/read/scope have to prove?"*; **6.2 answers *"what is the exact, stable set of tools an agent may
call, and what does the not-yet-KG surface refuse to pretend it can do?"*** 6.2 pins the *wire shape*
the trust rules produce; it does not re-implement the rules. Where an AC references provenance/untrusted/
scope, it asserts the **tool returns/accepts the right shape**, delegating the *enforcement* to the
sibling that owns it — exactly as Story 3.2 consumed 3.1's budget check rather than duplicating it.

## Story

As **an agent (a Run) that reads and writes squad knowledge, and as the Context Assembler (6.6) that
recalls it**, I want **a small, fixed set of memory MCP tools — `memory_write(content, kind, tags)`,
`memory_search(query, scope)`, `diary_append(entry)`, `diary_read(agent, last_n)` — exposed as the *one*
way to touch memory, each with a pinned signature and a provenance-carrying return envelope, and with the
knowledge-graph relation tools (`memory.relate`/`kg_add`/`kg_query`) *designed but fail-closed
unshipped***,
so that **the MVP knowledge record (semantic search + per-agent diary, FR-E2/E4) is fully usable across
Runs (FR-E3) without exposing the raw backend; the KG fast-follow is a *real* cut that can never silently
swallow a relation write and lie about it; and the tool contract is a stable seam — unchanged when
pgvector is swapped for GRAIL (§7.6) and forward-compatible when KG finally ships (adding tools, never
breaking the four) — so agents, the Context Assembler, and plugins all bind to a versioned surface, not
to today's storage engine.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-E2** (agents read/write squad knowledge via **MCP tools** exposed
  by the memory service — the direct requirement), **FR-E4** (the MVP subset = semantic search +
  per-agent diary, KG relations a **fast-follow**; §11.2, OQ6), **FR-E3** (knowledge persists across Runs
  so a later Run retrieves prior facts/decisions — the round-trip this surface delivers), **FR-E1** (the
  service is first-class, 6.1). The trust FRs (**FR-E5/E6/E7**) are enforced by 6.3/6.4/6.5; 6.2 carries
  their *wire shape*.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§7.1 "Shape & build-vs-integrate" → the MVP tool-surface table** — *the authoritative source for
    this story.* It names the exact four v1 tools and marks **`kg_add`/`kg_query` (relations) ⛔
    fast-follow, Postgres relation table, post-v1.** It also states the seam property this story defends:
    *"the storage/retrieval backend itself is likewise behind a `MemoryBackend` seam (§7.6): pgvector is
    the default and v1 backend; alternative backends (e.g. GRAIL, ISI-2142) plug in as a memory SDK
    **without changing the MCP tool surface or the §7.3 trust model**. KG relations are **explicitly a
    fast-follow**, not a v1 blocker."* AC3/AC4/AC6 are the elaboration of those two sentences.
  - **§7.3 "Trust boundary"** — the three enforced rules (writes authorized+provenanced; reads return an
    untrusted-provenance envelope `{content, author, written_at, scope, trust:"untrusted"}`; scope is the
    tenancy boundary). **6.2 pins these as the tool *return/argument shapes*** (AC5) and delegates their
    *enforcement* to 6.3/6.4/6.5. The tool layer must never return bare text or accept an unscoped call —
    that is the wire contract the enforcement rides on.
  - **§7.6 "Memory Fan-out & Backend Seam" (ISI-2142/GRAIL; ADR-024)** — pgvector is source-of-truth; the
    internal `MemoryBackend` seam lets GRAIL plug in as a memory-SDK backend. **The MCP tool surface sits
    *above* the seam and must be backend-independent** — AC6's whole subject. *"The trust model and the
    MCP tool surface do [not change]"* across the backend swap.
  - **§10.2 pinned A2A/MCP adapter discipline (`pkg/mcp@rev`, ADR-009)** — MCP wire versions are **pinned
    in a single versioned adapter package**; a spec/tool-surface upgrade is a **deliberate, reviewed
    revision**, never silent drift. **This is why 6.2 is a "seam" story:** the four MVP tools are a pinned
    contract, and shipping KG (AC4) is a *deliberate additive revision* of that pinned surface, asserted
    to leave the four untouched.
  - **§7.2 data model** — `memory_record(... kind, content, embedding, author_principal, author_run_id,
    author_agent_id, written_at, invalidated_at)` and `diary_entry(id, agent_id, team_id, entry,
    created_at)`. The tools are the typed doorway onto these rows; 6.1 owns the rows.
- **Depends on:**
  - **Story 6.1** (the `ksquad-memory` service + schema + pgvector — the backing the tools dispatch to).
    Hard dependency: 6.2 is the surface *over* 6.1.
  - **Story 6.3 / 6.4 / 6.5** (the write-auth, untrusted-read, and scope-tenancy **enforcement** the tool
    return/argument shapes carry). 6.2 pins the shapes; these stories give them teeth. Design-time
    parallel; the tool contract is stable regardless of which lands first.
  - **§10.2 `pkg/mcp`** — the pinned MCP adapter package the tools register into (Epic 1/ISI-2114 seam).
- **Blocks / is consumed by:** **6.6** (Context Assembler `memory_search` recall + handoff `memory_write`
  mirror — the primary caller), **2.8** (handoff artifact mirrored via `memory_write`, §7.3), **10.2**
  (discussion room surfaced through `memory_search`), **Epic 12.3** (the GRAIL plugin — the *second*
  backend AC6 pre-commits the surface to survive), and every Role prompt that recalls knowledge. The KG
  fast-follow (`kg_add`/`kg_query`) is a **named post-v1 story** unblocked by AC3's design (not this one).

## The MVP tool surface (authoritative — §A)

The **exactly four** tools exposed to agents through `pkg/mcp` for v1 (§7.1 table). Each is a thin typed
doorway onto a `MemoryBackend` call (§7.6); none exposes a raw DB handle, SQL string, or backend-specific
field. Signatures are **pinned** (§10.2) — a change is a reviewed adapter revision, not an edit.

| MCP tool | Args | Returns | Backing (via `MemoryBackend`) |
|---|---|---|---|
| `memory_write` | `content, kind, tags[]` (+ ambient authenticated principal/run/agent, scope) | provenanced ack `{id, author, written_at, scope}` | insert `memory_record` w/ provenance envelope (§7.3.1 — 6.3 enforces) |
| `memory_search` | `query, scope` (`last_n`/`k` optional) | **list of untrusted-provenance envelopes** `{content, author, written_at, scope, trust:"untrusted"}` | pgvector cosine over `memory_record.embedding` (§7.3.2 — 6.4 enforces) |
| `diary_append` | `entry` (+ ambient principal/agent/team, scope) | provenanced ack | insert `diary_entry` for the calling agent (§7.3.1) |
| `diary_read` | `agent, last_n` (+ scope) | **list of untrusted-provenance envelopes**, that agent only, newest-first, ≤ `last_n` | per-agent `diary_entry` rows (§7.3.2/§7.3.3 — 6.4/6.5 enforce) |

**Not in the v1 surface (fast-follow, §B):** `memory.relate` / `kg_add` / `kg_query`. Their schema is
**designed** (arguments and semantics specified below) so callers can be written against a known future
contract, but they are **not registered** in the v1 `pkg/mcp` tool set; a call **fails closed** with an
explicit `unimplemented`/not-registered error. **Never a silent `ok`.**

- Designed (post-v1) KG signatures — recorded so AC4's additive check has a concrete target:
  `kg_add(from_ref, relation, to_ref)` → provenanced ack; `kg_query(ref, relation?, depth?)` → list of
  provenanced relation envelopes. Backing = a Postgres relation table (§7.1), same trust model (§7.3).

## The fast-follow cut is a real cut (authoritative — §B)

The issue's *"designed for but not shipped"* has one correct implementation and one seductive-wrong one:

- **WRONG (the silent stub):** register `kg_add` returning `ok` (or a no-op that swallows the write). An
  agent calls `kg_add("A","depends_on","B")`, gets success, records in its plan that the edge exists —
  but nothing persisted. Later `kg_query("A")` returns empty, or worse, `kg_query` is *also* a stub
  returning `[]`, so the loss is never even surfaced. **Silent knowledge loss + a false capability
  signal.** This is strictly worse than not having the tool: the agent *reasoned on a phantom edge*.
- **RIGHT (fail-closed):** the KG tools are **absent from the registered v1 surface**; a call raises a
  loud `unimplemented`/`tool_not_registered` error the agent (and its Role prompt) can see and route
  around (e.g. fall back to `memory_write` with a `kind=relation` tag as flat knowledge, no graph
  semantics). The *cut is legible*: the agent learns the capability is not here yet, rather than being
  lied to. The **schema is still designed** (§A) so the fast-follow story ships *additively* (AC4).

AC3 and falsification (B)/(A-teeth) pin this: a silent-success stub is a **detected regression**, not an
acceptable placeholder.

## The seam is stable across backend and across the KG fast-follow (authoritative — §C)

Two independent stability properties, both from §7.6 + §10.2:

1. **Backend-independent (AC6, §7.6).** The four tool signatures and their return-envelope shapes are a
   function of the `MemoryBackend` *interface*, not of the concrete backend. Swapping pgvector (v1) for a
   GRAIL-model backend (ISI-2142/Epic 12.3) yields **byte-identical tool signatures and envelope keys** —
   no backend-specific field (`embedding`, a DQL cursor, a GRAIL entity id) leaks into the tool contract.
   The trust model (§7.3) sits above the seam and is likewise unchanged. A design that returns the raw
   backend row (leaking `embedding`/internal ids) *couples* the surface to pgvector and breaks the seam.
2. **Forward-compatible with KG (AC4, §10.2).** Shipping the KG fast-follow is a **deliberate additive
   revision** of the pinned `pkg/mcp` surface: it **adds** `kg_add`/`kg_query`; it does **not** change the
   four MVP tool signatures or their return shapes. An MVP caller (6.6's recall, a Role prompt) written
   against v1 keeps working unchanged after KG lands. A change that mutated a MVP signature to bolt on KG
   (e.g. adding a required `relation` arg to `memory_write`) is a **breaking** revision and is rejected.

Both are the §10.2 pinned-adapter discipline made concrete: the surface is a versioned contract; growth
is additive and reviewed, drift is a bug.

## Acceptance Criteria

**AC1 — the four MVP tools are exposed and round-trip across Runs (FR-E2/E3/E4).**
Given the `ksquad-memory` MCP surface (6.1) with `memory_write`, `memory_search`, `diary_append`,
`diary_read` registered, When an agent (Run A) calls `memory_write(content, kind, tags)` and a **later**
Run calls `memory_search(query, scope)` matching it, Then the written record is returned (semantic search
round-trips through the `MemoryBackend`, FR-E3 cross-Run persistence). And `diary_append(entry)` followed
by `diary_read(agent, last_n)` returns that agent's entry, **newest-first and bounded by `last_n`**. And
every tool dispatches through the `MemoryBackend` seam — **no tool exposes a raw DB handle, SQL string,
or backend-native row** to the agent.

**AC2 — the MCP tool surface is the *only* memory access path, and its signatures are a pinned contract
(§10.2).**
Given an agent, When it interacts with memory, Then the **four registered MCP tools are the sole
doorway** — there is no direct SQL, backend handle, or out-of-band write path exposed to agent code. And
the tool signatures live in the **pinned `pkg/mcp` adapter** (§10.2): a change to a signature is a
**deliberate, reviewed revision** of the versioned surface, never an ad-hoc edit — the conformance check
asserts the registered v1 surface is exactly the four tools with their pinned argument/return shapes.

**AC3 — `memory.relate`/KG is designed but NOT shipped, and the cut is *fail-closed*, never a silent
success.**
Given the v1 surface, When an agent calls `memory.relate`/`kg_add`/`kg_query`, Then the call **fails
closed** with an explicit `unimplemented`/`tool_not_registered` error (the tool is **absent from the
registered v1 set**) — it does **not** return `ok`, a no-op success, or an empty result that masquerades
as "no relations yet." And the KG schema is nonetheless **designed** (the `kg_add(from,relation,to)` /
`kg_query(ref,relation?,depth?)` signatures in §A are recorded) so the fast-follow ships additively
(AC4). A silent-success KG stub — one that lets an agent believe a relation persisted when nothing was
stored — is a **correctness failure** (phantom-edge knowledge loss), not an acceptable placeholder.

**AC4 — shipping the KG fast-follow is additive: it never mutates the four MVP signatures (§10.2 seam,
forward-compatible).**
Given a future revision that ships `kg_add`/`kg_query`, When it registers into `pkg/mcp`, Then it **adds**
those tools to the surface and leaves the **four MVP tool signatures and return-envelope shapes
unchanged** — an MVP caller (6.6 recall, a Role prompt) written against v1 continues to work unmodified.
And a revision that would mutate an MVP signature to accommodate KG (e.g. a new required arg on
`memory_write`) is a **breaking change** and is rejected by the seam contract — growth is additive, not
mutative.

**AC5 — the tool return/argument shapes carry the §7.3 trust envelope (wire shape pinned here;
enforcement is 6.3/6.4/6.5).**
Given a read tool, When `memory_search`/`diary_read` returns, Then each result is an
**untrusted-provenance envelope** `{content, author, written_at, scope, trust:"untrusted"}` — **never
bare text** (the shape 6.4's poisoning defense rides on). And `memory_write`/`diary_append` return a
**provenanced ack** carrying `{id, author, written_at, scope}` (the shape 6.3's write-auth produces). And
every tool **takes a scope** and issues no unscoped backend call (the argument shape 6.5's tenancy filter
rides on). This AC pins the **wire shape**; the write-rejection, poisoning-distrust, and cross-tenant-deny
**enforcement** are asserted by 6.3/6.4/6.5 respectively — 6.2 does not re-specify them.

**AC6 — the tool surface is backend-independent (§7.6 `MemoryBackend` seam).**
Given the `MemoryBackend` seam, When the backend is pgvector (v1) versus an alternate (GRAIL,
ISI-2142/Epic 12.3), Then the **four tool signatures and their return-envelope keys are identical** — no
backend-specific field (`embedding` vector, DQL cursor, GRAIL entity id) leaks into the tool contract,
and the §7.3 trust envelope is unchanged. The surface binds to the `MemoryBackend` *interface*, not to
the concrete engine, so a backend swap is invisible to every agent, the Context Assembler, and the pinned
`pkg/mcp` contract.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/run-mcp-tools-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification in the same discipline as the Story 2.8 handoff check: it models the MCP tool surface over
two `MemoryBackend` implementations and drives the seductive-wrong designs to prove the teeth.

- **(A) NAIVE silent-KG-stub — the fast-follow "cut" that lies.** A surface that registers `kg_add`
  returning `ok` (no-op). The check calls `kg_add("A","depends_on","B")`, asserts it returned success,
  then `kg_query("A")` returns **empty** → the agent believes a relation persisted that never was
  (phantom-edge knowledge loss). This **MUST** reproduce, else the harness proves nothing. *Mutation
  anchor:* if the silent stub is ever "fixed" to fail-closed, arm (A) stops leaking and fails **loud** —
  it exists only to give AC3 teeth against the same SUT.
- **(B) §7.1/§B FAIL-CLOSED cut (AC3).** The v1 surface has KG **absent from the registered set**; a
  `memory.relate`/`kg_add`/`kg_query` call raises `unimplemented`/`tool_not_registered`. The check asserts
  the call **raises** (never returns `ok`/`[]`), so no agent can mistake absence for "no relations yet."
  *Mutation-proven:* re-registering `kg_add` as a silent no-op turns this arm **RED** — the cut has teeth.
- **(C) MVP round-trip across Runs (AC1).** Run A `memory_write`s; a later Run `memory_search`es and gets
  the record back through the seam; `diary_append` then `diary_read(agent, last_n)` returns that agent's
  entries newest-first, **length ≤ `last_n`**. Asserts FR-E3 cross-Run persistence and the `last_n` bound.
- **(D) pinned surface = exactly the four (AC2).** Asserts the registered v1 tool set is **exactly**
  `{memory_write, memory_search, diary_append, diary_read}` — no KG tool present, no raw-SQL/DB-handle
  tool exposed. A surface that leaks a `raw_query`/DB-handle tool fails **loud** (the "MCP tools are the
  sole doorway" invariant).
- **(E) additive KG revision leaves the four untouched (AC4).** Registers a **v1.1** surface that **adds**
  `kg_add`/`kg_query`; asserts the four MVP tool signatures + return-envelope keys are **byte-identical**
  to v1 (a superset, not a mutation). Then a **breaking** revision that adds a required `relation` arg to
  `memory_write` is asserted **rejected** by the seam contract → the additive-only discipline has teeth.
- **(F) trust-envelope wire shape (AC5).** `memory_search`/`diary_read` results are asserted to be the
  full `{content, author, written_at, scope, trust:"untrusted"}` envelope — **never bare text**; a naive
  surface that returns bare strings fails **loud** (the poisoning-defense wire shape 6.4 rides on). And
  `memory_write` returns a provenanced ack `{id, author, written_at, scope}`; and a tool called with **no
  scope** is rejected (the argument shape 6.5 rides on) — 6.2 pins the shape, not the enforcement.
- **(G) backend-independence (AC6).** Runs the **identical** tool-surface conformance over two backends —
  a `PgvectorBackend` model and a `GrailBackend` model (different internal row shapes) — and asserts the
  four signatures and the return-envelope keys are **identical** across both, with **no** backend-specific
  field (`embedding`, `dql_cursor`, `grail_entity_id`) leaking into any tool return. A design that returns
  the raw backend row leaks engine detail and fails **loud** — the §7.6 seam has teeth.

Exits non-zero if the fast-follow cut ever returns a silent success (A stops leaking / B stops raising),
the round-trip drops a record or blows the `last_n` bound, the pinned surface is not exactly the four (or
leaks a raw-DB doorway), an additive KG revision mutates a MVP signature (or a breaking revision is
accepted), a read tool returns bare text, a write ack drops provenance, an unscoped call is accepted, or a
backend-specific field leaks into the tool contract. **The two headline invariants are mutation-checked:**
turning the fail-closed cut back into a silent stub (A↔B) flips the check **RED**, and mutating a MVP
signature to bolt on KG (E) flips it **RED** — the fast-follow-cut and stable-seam guarantees have teeth.

## Out of scope (owned elsewhere)

- **The `ksquad-memory` service, schema, and pgvector wiring** (Story 6.1 — the store the tools dispatch
  to), **write-time authorization + provenance enforcement** (Story 6.3, §7.3.1 — 6.2 pins the ack shape,
  6.3 rejects unauthorized/unattributed writes), **untrusted-read posture + memory-poisoning defense**
  (Story 6.4, §7.3.2 — 6.2 pins the envelope shape, 6.4 makes readers distrust it), **scope/tenancy
  enforcement + cross-tenant deny + one-principal-can't-write-another's-diary** (Story 6.5, §7.3.3 — 6.2
  pins that tools take a scope, 6.5 denies cross-tenant by construction), **Context-Assembler recall +
  handoff mirror** (Story 6.6 — a *caller* of these tools), **the KG relation table + `kg_add`/`kg_query`
  implementation** (the named post-v1 fast-follow story — 6.2 only *designs* the signatures and *fences
  off* the unshipped surface), **the GRAIL memory-SDK backend** (Epic 12.3/ISI-2142 — 6.2 only pre-commits
  the tool surface to survive the swap, AC6), **the discussion-room `discussion_search` tool** (§7.5 /
  Epic 10.2), and **embeddings/embedder choice** (§7.1 embedder seam, 6.1). This story ships **the four
  MVP memory MCP tools as a pinned, backend-independent, forward-compatible wire seam, the fail-closed KG
  fast-follow cut, and the differential falsification** — the FR-E2/E4 tool-surface guarantee itself.
