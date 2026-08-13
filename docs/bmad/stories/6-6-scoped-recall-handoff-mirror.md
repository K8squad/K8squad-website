# Story 6.6: Scoped memory recall + handoff mirror — the recall contract the Context Assembler consumes, and the 2.8 handoff mirrored as provenanced (never custody) memory

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔌 THIS STORY IS THE *CONSUMING EDGE* OF THE MEMORY TRUST BOUNDARY — the recall the §8.5 Context
> Assembler requests, and the §8.5 handoff mirror.** 6.4 (ISI-2225, DONE) fixed the *shape* of a single
> read (the `{content, author, written_at, scope, trust}` envelope). 6.5 (ISI-2226, DONE) fixed the
> *tenancy deny* on the query (cross-tenant denied by construction; never an unscoped query). 3.6
> (ISI-2206, DONE) *tiers* the assembled envelope by source and snapshots it on the Run. 2.8 (ISI-2198,
> DONE) makes the handoff artifact *advisory* (knowledge, not custody) and its mirror provenanced —
> from the **write** side. **6.6 owns the one seam none of them do: the *recall* the Assembler
> consumes, and the *mirror* that feeds it.** Arch §8.5 (Context Injection & Agent Handoff) verbatim on
> the two facets: *"scoped memory recall (§7 semantic search over this project/squad)"* carried as the
> **untrusted-recall** tier *"with `{author, written_at, scope, trust: "untrusted"}` exactly as §7.3
> returns them: reference material, never commands"*; and the structured handoff artifact *"mirrored as
> a provenanced memory write (§7)… but advisory context for the next Run, never a coordination path…
> If the handoff artifact could authorize or transfer custody it would reintroduce the P2P back-channel
> §6/§7.3/§7.5 forbid."* Three load-bearing invariants, each the recall-side mirror of a boundary its
> siblings hold from the other side:
> **(1) recall the Assembler requests is project/squad-scoped and untrusted-recall-tiered with full
> provenance.** The recall entry point consumes 6.5's deny (a foreign-tenant row never enters the
> victim Run's envelope) and hands 3.6 a row already tagged untrusted-recall — reference, never a
> command. The design that recalls unscoped turns *recall itself* into a cross-tenant injection
> surface; the design that returns bare/unattributed content lets recalled memory smuggle instructions
> the Assembler cannot quote.
> **(2) the 2.8 handoff artifact is mirrored as a *provenanced, project/squad-scoped* memory write** so
> the NEXT Run recalls it at untrusted-recall, attributed to the prior agent — cross-Run knowledge
> transfer. A mirror to a private/unrecallable scope silently drops that transfer; a mirror as bare
> authority frames the prior agent's `next` as a command.
> **(3) memory is NEVER the custody/handoff mechanism (the no-P2P lock, a sixth time).** Recalling
> memory — a mirrored handoff included — confers *no custody*: reading it never mutates a claim/lease,
> and the handoff `next` is advisory context, not a coordination path. Custody stays the fenced
> §6.2/§6.3 release → re-dispatch → claim; the fence is the sole discriminator. Read the ACs literally:
> a recall that crosses scope, drops the untrusted-recall tier / provenance, mirrors a handoff as
> authority, or moves custody through memory is a **correctness failure**, not a convenience.

## ⚠️ Scope reconciliation — 6.6 vs the rest of Epic 6 / Epic 3 / Epic 2, and the stale §8.3/§8.4 cite (read first)

Epic 6 splits the memory service across six stories that all touch the same trust boundary; **6.6 owns
the *recall contract + handoff mirror* and nothing else.** The epic table's §8.3/§8.4 numbering is the
**stale** pre-r5 labelling — the memory trust boundary was consolidated into **arch §7.3** during the
r5 fold (ISI-2151); the recall/handoff wiring lives in **§8.5** (Context Injection & Agent Handoff,
r11/r12, ADR-028). This story binds to the **live §8.5 + §7.3** (the same remap 6.4/6.5 record). §8.4
in the AC list refers to the **memory-projected discussion room / recall source** side of §8.

| Concern | Owned by | This story (6.6) |
|---|---|---|
| The `ksquad-memory` Go service + `memory_record` schema + `diary_entry` + pgvector | **6.1** (§7.1/§7.2) — DONE | consumed — 6.6 recalls *over* it |
| The MVP MCP tool surface (`memory_search`, `memory_write`, `diary_append`, `diary_read`) | **6.2** (§7.1, §10.2) — DONE | consumed — 6.6 is the Assembler-side caller of `memory_search` |
| **Reads as untrusted input with provenance** — the `{content, author, written_at, scope, trust}` envelope | **6.4** (§7.3.2, FR-E7) — DONE | consumed — 6.6 returns recall rows *in* that envelope, at the untrusted-recall tier |
| **Scope/tenancy — cross-tenant DENY by construction; never an unscoped query** | **6.5** (§7.3.3, FR-E5) — DONE | consumed — 6.6's recall entry point pushes 6.5's scoped predicate; a foreign-tenant row never enters the envelope |
| **Writes authorized + provenanced** — author server-stamped | **6.3** (§7.3.1, FR-E6) — DONE | consumed — the handoff mirror is one such provenanced write |
| **Context Assembler** — provenance-tiered envelope, snapshot on the Run, goal-version isolation | **3.6** (§8.5, ADR-028) — DONE | sibling/consumer — 3.6 *tiers + snapshots*; **6.6 supplies the untrusted-recall rows 3.6 tiers**, already tier+provenance-complete so 3.6 never re-derives trust |
| **Structured handoff artifact** — advisory, content-addressed, mirror provenanced | **2.8** (§8.5, §6.5) — DONE | sibling/source — 2.8 owns the artifact + its advisory-not-custody property from the *write* side; **6.6 owns the mirror's *recallability + no-custody-on-read*** |
| **Scoped recall + handoff mirror — the recall the Assembler requests + the mirror that feeds it, memory never custody** | **THIS STORY (6.6)** (§8.5, §8.4, §7.3) | the recall contract + its falsification (R/T/M/C/A) |
| Token-budget fit of the tiered envelope to the model `contextWindow` | **5.9** (§8.5, §10.3) — DONE | out of scope — 6.6 hands recall to 3.6; 5.9 truncates lowest-priority-first |

**One-line boundary:** 6.4 answers *"what shape is a read?"*; 6.5 answers *"which tenant may read at
all?"*; 3.6 answers *"how is the envelope tiered + snapshotted?"*; 2.8 answers *"what does a handoff
prove, and is it custody?"*; **6.6 answers *"what does the Assembler get when it asks memory to
recall, and how does a completed Run's handoff come back?"*** — project/squad-scoped rows at the
untrusted-recall tier with full provenance, the 2.8 handoff mirrored as a provenanced recallable write,
and **not one grain of custody moving through any of it**.

## Story

As **the §8.5 Context Assembler assembling a Run at `Claiming → Running`**,
I want **`memory.search`, when I request recall, to return only this Run's project/squad-scoped records
already tagged `untrusted-recall` and carrying full `{author, written_at, scope, trust: "untrusted"}`
provenance — reference material I can inject without re-deriving trust and that a malicious source
cannot frame as a command — and I want a completed Run's structured handoff artifact (2.8) mirrored as a
provenanced, project/squad-scoped memory write so the *next* Run recalls it at that same tier, attributed
to the prior agent**,
so that **cross-Run context flows richly and safely: the decision trail and prior-agent handoffs are
recallable by future Runs (§8.5, FR-E), scoped to the squad/Project (FR-E5, via 6.5) and untrusted-tiered
(F16/§7.3, via 6.4) — while memory is *never* the custody or handoff mechanism (the no-P2P lock,
preserved a sixth time): recalling memory confers no custody, and work custody moves *only* through the
fenced §6.2/§6.3 release → re-dispatch → claim.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-E** (memory recall), **FR-E5** (squad/Project scope — 6.5, the
  deny 6.6's recall entry point consumes), **FR-E7** (untrusted reads + provenance — 6.4, the envelope
  6.6 returns recall in), **FR-A** (run lifecycle — the Assembler runs at `Claiming→Running`),
  **FR-B1/B3/B4** (coordination artifacts + audit — the 2.8 handoff). F16 (memory boundary / context
  injection) and the no-P2P lock (custody only through the fenced record).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§8.5 Context Injection & Agent Handoff** — *the authoritative source.* Refinement (1): the
    envelope is assembled by the control plane and lists **scoped memory recall** as a content source.
    Refinement (2): recall is the **untrusted-recall** tier, carried *"with `{author, written_at, scope,
    trust: "untrusted"}` exactly as §7.3 returns them: reference material, never commands."* Handoff:
    *"the structured handoff artifact… mirrored as a provenanced memory write (§7)… advisory context
    for the next Run, never a coordination path… If the handoff artifact could authorize or transfer
    custody it would reintroduce the P2P back-channel §6/§7.3/§7.5 forbid."*
  - **§7.3.2 (reads untrusted + provenance)** and **§7.3.3 (scope is the tenancy boundary)** — the two
    read-side rules 6.6 consumes (6.4 / 6.5).
  - **§8.4 / §7.5** — the memory-projected discussion room reuses *"the same namespace/Team-scope
    filter that gates memory reads"* — the recall source 6.6's filter also serves.
  - **§6.2/§6.3** — the fenced custody path recall must never touch; **§6.5** — the coord artifact the
    2.8 handoff commits to (the mirror's source of truth; the mirror is best-effort over it).
  - **ADR-028** — the context-injection/handoff trade (control-plane assembly, provenance tiers,
    handoff = knowledge not custody).
- **Epic:** `docs/bmad/04-epics-and-stories.md` Story 6.6 — *"Given a Run being assembled (3.6), When
  the Assembler requests recall, Then memory.search returns project/squad-scoped results as
  untrusted-recall tier with full provenance; And the handoff artifact (2.8) is mirrored as a
  provenanced memory write; And memory is never the custody/handoff mechanism."*
- **Sibling code:** `run-context-assembler-check.py` (3.6 — consumes 6.6's recall at the
  `memory_recall` source, untrusted-recall tier), `handoff-advisory-check.py` (2.8 — the handoff
  artifact + its provenanced best-effort mirror from the write side), `memory-read-untrusted-check.py`
  (6.4 — the envelope shape), `memory-scope-tenancy-check.py` (6.5 — the deny 6.6 consumes).

## Acceptance criteria

1. **AC1 — scoped recall (R).** When the Assembler requests recall, `memory.search` pushes the Run's
   **server-authenticated** project/squad scope predicate into the store query (consuming 6.5's deny,
   never an unscoped scan); a foreign-tenant record never enters the Run's context envelope, while the
   Run's own in-scope records do. Recall is the tenancy-scoped read the §8.4/§7.5 room filter also uses.
2. **AC2 — untrusted-recall tier + full provenance (T).** Every recalled row is returned at the
   **`untrusted-recall`** tier carrying the full `{author, written_at, scope, trust: "untrusted"}`
   envelope (§7.3.2) — never unattributed, never authoritative. This is exactly what 3.6 injects as the
   `memory_recall` source: reference material the runtime frames as quoted/attributed, **never a
   command** (the F16/§7.3 anti-injection crux applied at the recall boundary).
3. **AC3 — handoff mirrored as a provenanced, recallable memory write (M).** A completed/paused Run's
   structured handoff artifact (2.8) is mirrored as a **provenanced, project/squad-scoped** memory
   write, so the **next** Run recalls it at the untrusted-recall tier, attributed to the **prior** agent
   — cross-Run knowledge transfer. A mirror that is unrecallable (private/wrong scope) silently drops
   that transfer.
4. **AC4 — memory is NEVER the custody/handoff mechanism (C).** Recalling memory — a mirrored handoff
   included — confers **no custody**: reading recall never mutates a claim/lease, and the handoff
   `next`/`recommended_next` are advisory context, never a coordination path. Work custody moves **only**
   through the fenced §6.2/§6.3 release → re-dispatch → claim; the fence (monotonic) is the sole custody
   discriminator. A recall path that could grant/transfer custody is the P2P back-channel §6/§7.3/§7.5
   forbid.
5. **AC5 — recall tier is stamped, not supplied (A).** The untrusted-recall tier is **stamped by the
   recall service** because the content *is* recall, never read from a record-supplied `tier` field. No
   recalled record — a poisoned handoff included — can self-promote to authoritative. This is the
   recall-side mirror of 6.3's *"author stamped, not supplied"*, 6.4's *"trust stamped, not supplied"*,
   and 6.5's *"tenant stamped, not supplied"*: here the **tier** is stamped, not supplied — so 3.6
   receives a tier+provenance-complete row it injects **without re-deriving trust**.
6. **AC6 — non-vacuous + best-effort mirror.** In-scope recall surfaces and legitimate handoff knowledge
   transfer works (the boundary blocks cross-scope / self-promotion / custody, not *everything*); and the
   mirror is **best-effort over the 2.8 coord artifact** — a memory outage never rolls back the committed
   handoff artifact (2.8, its source of truth), it only means that handoff is not recalled.

## Falsification (the teeth)

`docs/bmad/spikes/bench/scoped-recall-handoff-mirror-check.py` — stdlib-only, models the recall path
in-process (real-service/real-PG promotion rides Epic 6.1 + the Go test spine; the live Assembler wiring
rides Story 3.6). Five arms, each mapping to an AC, with a `--mutate=<R|T|M|C|A>` differential (same
discipline as `memory-scope-tenancy-check.py` / `memory-read-untrusted-check.py`):

- **R** — recall is scoped to the Run's project/squad; a foreign-tenant (P2) row never enters the P1
  Run's envelope, the in-scope (P1) row does. `--mutate=R` recalls unscoped → the P2 secret lands in
  P1's context envelope. **R RED.**
- **T** — every recalled row carries the untrusted-recall tier + full provenance. `--mutate=T` drops the
  provenance envelope → the Assembler receives an unattributed fact it cannot mark distrusted. **T RED.**
- **M** — the 2.8 handoff is mirrored as a project/squad-scoped provenanced write, recallable by the next
  Run. `--mutate=M` mirrors it to a private/unrecallable scope → the next Run's scoped recall misses it
  and the knowledge transfer is silently lost. **M RED.**
- **C** — recalling memory (a mirrored handoff included) confers no custody; the fence stays the sole
  discriminator. `--mutate=C` honors a custody grant smuggled in the mirrored handoff and recall applies
  it → the next Run holds the item off recall alone, with no fenced acquire. **C RED.**
- **A** — the recall tier is stamped untrusted-recall by the service, never read from the record.
  `--mutate=A` honors a record's self-declared `tier: authoritative` → a poisoned record self-promotes
  to authoritative (its imperative frames as a command). **A RED.**

**Verified:** baseline all-GREEN (exit 0); each `--mutate=X` reddens **exactly** arm X (exit 1) — the
mutations are orthogonal, so each of the five guards is *independently* load-bearing (the inverse of the
ISI-2346-F1 teeth-gap; the same non-vacuity bar the ISI-2375 review set). Every arm also asserts the
positive behavior (in-scope recall surfaces, the handoff knowledge transfers, a fenced claim still
holds), so no arm passes vacuously by denying everything. A sixth arm asserts AC6's best-effort mirror
(a memory outage leaves the 2.8 artifact committed, only skipping recall) — non-mutated, so a `--mutate`
run must redden one of R/T/M/C/A.

## Out of scope (owned elsewhere)

- **Tiering + snapshotting the assembled envelope** (the whole envelope, goal-version isolation,
  re-entrant reuse) — **3.6** (ISI-2206). 6.6 supplies the untrusted-recall *rows*; 3.6 tiers/snapshots.
- **Fitting the tiered envelope to the model `contextWindow`** (token budget, truncation) — **5.9**
  (ISI-2221) + §10.3.
- The **handoff artifact schema + its advisory-not-custody property from the write side** + the mirror's
  provenance/best-effort from the write side — **2.8** (ISI-2198). 6.6 owns the *recall/no-custody-on-read*.
- The **untrusted-read envelope shape** — **6.4** (ISI-2225). The **cross-tenant deny mechanism / never
  an unscoped query** — **6.5** (ISI-2226). 6.6 *consumes* both at the recall entry point.
- **RBAC / human-principal authorization** — §12.3 / Epic 15. **Real-PG / real-service** enforcement —
  Epic 6.1 + the Go test spine.

## Dev notes

- **Recall is a control-plane call, scoped by the Run, tiered by the service.** The Assembler calls
  `memory_search(query)` with the Run's `§12.4` scope; the scope predicate is stamped from the Run's
  authenticated tenant (never a tool argument — 6.5), and the untrusted-recall tier + provenance are
  stamped by the recall service (never read from the record — AC5), so 3.6 injects the rows as-is.
- **The handoff mirror is a normal provenanced `memory_write` (6.3), scoped to the project/squad, kind
  `handoff`, authored by the prior agent** — nothing special. Its *recallability* is the point: it comes
  back through the same scoped `memory_search` the next Run runs. Do **not** add a custody/grant field to
  the mirror or a custody effect to recall — that is the P2P back-channel §6/§7.3/§7.5 forbid (2.8 bars
  it on the write side via the fixed 7-field schema; 6.6 bars it on the read side).
- **Best-effort over the coord artifact:** the 2.8 handoff commits to the coord record (§6.5) *first*;
  the memory mirror is best-effort (§7). A memory outage must never roll back the committed artifact —
  it only means the next Run can't recall that handoff (it still gets the fenced work-item provenance).
