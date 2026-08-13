# Story 2.9: Coordinator dispatch pattern (delegation-with-feedback)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔒 THIS IS A LOCKED-DECISION GUARDRAIL STORY (CEO 2026-08-12), NOT A NEW SUBSYSTEM.** It adds **zero**
> new coordination primitives. The entire coordinator→squad feedback loop rides the primitives Epic 2
> already ships — **shared work items + comments + artifacts (§6.1), the fenced claim (2.2, §6.2), the
> handoff artifact (2.8), and scoped memory recall (6.6)**. The story's whole job is to **pin the shape of
> the loop** so no implementer "helpfully" wires the shortcut the architecture forbids. The shape is:
>
> ```
>    read-of-record  →  coordinator DECIDES + PRIORITIZES  →  new FENCED dispatch
> ```
>
> and **never** a message from B to A, never B driving A's next dispatch, never custody handed from B to C.
> This is the **KSquad-native BigBoss→Alfred→team pattern**: a squad-lead Agent delegates, the delegate's
> results surface **through the record**, and the lead decides what happens next. **Delegation-with-feedback,
> not custody transfer.** A design where the completing Run *messages* the coordinator, or where B's
> `recommended_next` is *executed* rather than *read*, reintroduces exactly the P2P back-channel §6/§7.3/§7.5
> forbid — it is a **no-P2P violation, not a feature request.**

## Story

As **a coordinator** (a squad-lead Agent, designated via its `Role`),
I want **to create dependent work items and, when a dependency completes, have the completing Run's handoff
artifact surfaced to my next dispatch decision through the coordination record / scoped memory recall — so I
can define and prioritize the downstream work (C/D) informed by B's findings**,
so that **the squad runs the BigBoss→Alfred→team delegation pattern with feedback, while coordination stays
shared-work-item + fencing and never becomes an agent-to-agent back-channel (FR-B3, §6.1, ADR-028, R13
locked decision).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-B1** (durable shared work items), **FR-B3** (**no agent-to-agent
  channel — coordination is shared work items + comments only; the locked decision this story guards**),
  **FR-B4** (audit trail).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§6.1** — the coordination record data model. `work_item` carries `created_by`, `parent_id` adjacency,
    and the canonical `state` enum; the loop rides these rows + `comment` + `artifact`. **There is no
    `message` table** — its absence *is* the no-P2P guarantee.
  - **§6.2** — the fenced conditional acquire (2.2). Dispatch is **open-item → fenced claim**; every custody
    move (including the coordinator's own claim and C's downstream claim) bumps the monotonic `fence_token`.
  - **§6.3** — fenced release. B's exit from an item is a **fenced release → item returns to the pool**;
    custody is **never handed** to the next holder.
  - **§6.6** — domain events / scoped memory recall. The completing Run's handoff artifact is **mirrored as
    a provenanced memory write** (`{author, written_at, scope, trust:"untrusted"}`), and the coordinator's
    Context Assembler pulls it back as the **untrusted-recall tier** — *recall, never a handoff channel.*
  - **§8.5 / ADR-028** — context injection & handoff. **"Handoff is knowledge transfer, NOT custody
    transfer"** — the artifact only *enriches the next Run's envelope*; it can never authorize or transfer
    custody. This story is the *coordinator-side* consumer of that rule.
  - **§8.6** — the Agent↔work-item core loop (claim → contextualize → work → emit artifacts → transition →
    complete). The coordinator is just an Agent running this loop whose `Role` grants it work-item *creation*
    + *prioritization* authority within its squad.
- **The Story 2.8 handoff artifact (the input this story consumes):** the standardized
  `{did, decisions, next, blockers, findings, recommended_next, artifacts_for_downstream}` artifact. The
  **CEO-2026-08-12 fields** — `findings`, `recommended_next`, `artifacts_for_downstream` — exist *precisely*
  so a coordinator can read a completed Run's results and inform its next dispatch. **`recommended_next` is
  advisory input to the coordinator's decision, NOT an instruction B executes.**
- **Depends on:** **2.8** (extended handoff artifact — the surfaced content), **2.2** (fenced claim — the
  dispatch mechanism), **6.6** (scoped memory recall — the surfacing path), and the **`Role` CRD (Epic 1)**
  (marks the Agent a squad lead / grants create+prioritize authority). If any are unlanded, wire against the
  pinned arch sections above and gate the DB-backed test on them.
- **Blocks / is consumed by:** **2.10** (rate-limit re-route — "the coordinator (2.9) re-dispatches the work
  item"), and the **Epic 14 L4 covert-channel review gate** (14.4 blast-radius suite absorbs the 10.4/12.4
  covert-channel guards) — which promotes this story's falsification into a **required real-engine check that
  the coordinator cannot be driven by a back-channel.**

## The pinned loop (authoritative)

A coordinator dispatches dependent work and consumes the result **entirely through the record**:

```
1. DEFINE          coordinator creates WB, WC (WC.blocked_by = WB), created_by = coordinator   (§6.1)
2. DISPATCH        WB is opened for dispatch → B CLAIMS it (fenced, fence f_b)                  (§6.2, 2.2)
3. WORK + EMIT     B works WB, writes the 2.8 handoff artifact to the coordination record,
                   mirrored as a provenanced memory write (trust:"untrusted")                  (2.8, §6.6)
4. RELEASE         B COMPLETES/RELEASES WB (fenced). Custody does NOT move to anyone.           (§6.3)
       │
       │   ✗ B does NOT message the coordinator.   ✗ B does NOT dispatch the next item.
       │   ✗ B does NOT hand its claim/lease to C.  (all three = no-P2P violations)
       ▼
5. SURFACE         the coordinator's NEXT reconcile/claim decision READS WB's handoff artifact
                   (coordination record §6.5) + scoped memory recall (§6.6, untrusted tier).
                   This READ is the ONLY path by which the coordinator learns B's results.
6. DECIDE          the coordinator DEFINES and PRIORITIZES the next work item. It MAY adopt,
                   re-order, or OVERRIDE B's `recommended_next` — `recommended_next` is advisory.
                   The dispatched item is created_by = coordinator.
7. RE-DISPATCH     the chosen item is opened → C CLAIMS FRESH (fenced, fence f_c > f_b).        (§6.2, 2.2)
```

**Why every "✗" matters (the load-bearing subtlety).** Steps 3–7 look like they could be collapsed — "B
finished, so B just tells the coordinator / dispatches C directly, saving a hop." That collapse is the exact
back-channel the architecture is built to forbid: it turns coordination into a peer-to-peer edge where one
agent drives another's work, custody flows on a self-report, and the audit trail no longer explains *who
decided what*. The feedback loop is legitimate **only** because it is **read-of-record → coordinator decides
→ new fenced dispatch**: the coordinator is the sole decider, the record is the sole surfacing path, and
custody only ever moves through the fenced §6.2/§6.3 mechanism.

## Acceptance Criteria

**AC1 — the coordinator defines dependent work items (create + ordering).**
Given an Agent whose `Role` marks it a squad lead, When it creates dependent work items, Then each is a
durable `work_item` row with `created_by = coordinator` and its dependency expressed via
`blocked_by`/`parent_id` ordering (§6.1) — a normal fenced coord write, no special coordination primitive.
And a non-lead Agent (no squad-lead `Role`) **cannot** create-and-prioritize squad work on another Agent's
behalf — the authority is `Role`-gated (Epic 1), not implicit.

**AC2 — a completed dependency's results are surfaced to the coordinator through the record, never pushed.**
Given a dependency Run (B) that completes WB and writes the 2.8 handoff artifact
(`findings, recommended_next, artifacts_for_downstream`), When the coordinator makes its next dispatch
decision, Then it **reads** that artifact from the coordination record (§6.5) **and/or** as scoped memory
recall (§6.6, carried as the **untrusted-recall** tier with full provenance) — and this read is the **sole**
path by which it learns B's results. And **B never sends a message to the coordinator** and the coordinator
is **never woken/driven by B** — the surfacing is a coordinator-initiated read of durable rows, not a B→A
delivery.

**AC3 — the coordinator defines and prioritizes the next item; `recommended_next` is advisory (not executed).**
Given B's handoff artifact carrying a `recommended_next` and a `priority_hint`, When the coordinator decides,
Then it **may adopt, re-order, or override** them — the dispatched work item reflects the **coordinator's**
choice and priority, is `created_by = coordinator`, and is **never** authored or dispatched by B. A design in
which B's `recommended_next` is *executed as an instruction* (B creates/dispatches the next item) is a
rejected no-P2P violation.

**AC4 — no custody transfer: B releases, control plane re-dispatches, C claims fresh (the R13 crux).**
Given WB done by B (fence f_b) and a downstream item the coordinator dispatches, When C picks it up, Then C
**claims a fresh, open item via the §6.2 conditional acquire** at a **new monotonic fence f_c > f_b** — C
**never inherits B's claim, lease, or fence.** B's exit from WB is a **fenced release** (§6.3); the item
returns to the pool and is re-dispatched. Custody moves **only** through open-item → fenced-claim, exactly
as for any other work item — the coordinator feedback loop grants **no** custody shortcut.

**AC5 — no agent-to-agent channel; the whole loop rides shared work items + comments + artifacts (FR-B3).**
Given the coordinator dispatch loop end to end, When it is inspected, Then there is **no `message` table and
no B→A / B→C channel** — every step is a row on `work_item`/`comment`/`artifact` (§6.1) with provenance and
audit (§6.5). And a **review-time covert-channel check (Epic 14 L4, 14.4 blast-radius suite)** proves the
coordinator's dispatch decision **cannot be driven by a back-channel**: removing the coordinator's
record/recall read leaves it with **no** alternate source of B's results (there is no second, covert path).
**Verified by `docs/bmad/spikes/bench/coordinator-dispatch-check.py`** (below), a *differential* check that
first proves a "helpful" naive design (B messages A + B drives the dispatch + B hands C its lease)
**does** back-channel and transfer custody — so the harness has honest teeth — then proves the §2.9 design
keeps **zero** P2P rows, a coordinator-authored + coordinator-**overridden** next item, and a **fresh higher
fence** for C, *while the coordinator still successfully learns B's results from the record.*

**AC6 — the loop is fully audited (who decided what, when).**
Given the loop runs, When the audit trail (§6.5) is queried, Then every step is a durable, provenanced row:
the coordinator's item creation (`created_by`), B's claim/complete/handoff-artifact, the coordinator's
next-item creation + priority, and C's fresh claim — so the trail **explains the decision chain**
(coordinator delegated → B reported via record → coordinator decided → C claimed), never a hidden causal
edge. The handoff artifact is **advisory context** in this trail, tagged `trust:"untrusted"` on the memory
mirror (§6.6), never a custody-bearing record.

## Runnable check (the falsification, already green)

`docs/bmad/spikes/bench/coordinator-dispatch-check.py` — stdlib-only, `python3` it directly:

```
[model] NAIVE  (B messages A + B drives dispatch + hands lease): messages=1 next.created_by='agentB' C.fence=1 (==B.fence 1? True)
[model]        -> back-channel=True b_authored=True custody_inherited=True (all must be True: teeth)
[model] NAIVE2 (coord-authored + fresh fence but custody PUSHED, no acquire): C.fence=2(>1? True) custody_via=None
[model]        -> fence_looks_fresh=True custody_forged=True (both True: the fresh-fence shortcut is detectable, not just fence-copy)
[model] §2.9   (read-of-record -> coordinator decides -> fenced dispatch): messages=0 next.created_by='coordinator' B.rec='WC_token_refresh' dispatched='WD_rate_limit_guard' C.fence=2(>1? True)
[model]        -> no_back_channel=True coord_authored=True overrode_recommendation=True fresh_custody=True learned_from_record=True
[model] PASS — naive detectably back-channels+transfers custody; §2.9 keeps zero P2P, coordinator authors+overrides+prioritizes, C claims fresh, and the coordinator still learns B's results from the record.
```

- **Default (no deps):** an in-process model of the coord record (`work_item` rows), the §6.6 memory mirror,
  and — crucially — a `messages` list standing in for the **forbidden** B→A P2P channel (which a correct
  design leaves **empty**). B's half (claim → work → write handoff → mirror to memory) is **identical** in
  both variants — B always emits its results to the record; the variants differ **only** in what happens
  *after*. The **naive** variant has B message the coordinator, author + dispatch the next item per its own
  `recommended_next`, and hand C its own lease — proving all three violations are *detectable*
  (non-empty channel, `created_by = B`, inherited fence). A **second, subtler naive arm** (`NAIVE2`)
  proves the custody guard is not fence-number-deep: a **coordinator-authored** item with a **fresh,
  strictly-higher fence** whose custody was **pushed directly to C** (never opened, never claimed via
  the §6.2 conditional acquire) would satisfy a naive `f_c > f_b` test — so the check stamps
  `custody_via = "conditional_acquire"` inside `claim()` and requires it, catching the fence-bump
  shortcut a fence-only assertion would miss (AC4/R13 crux). The **§2.9** variant has the coordinator
  independently **read** the record/recall, **override** B's recommendation with its own choice + priority,
  author the next item (`created_by = coordinator`), and re-dispatch it **open** so C **claims fresh** at a
  higher fence. It exits non-zero if the naive variant *stops* exhibiting a back-channel (teeth lost) or the
  §2.9 variant *ever* leaks a P2P row, lets B author/drive the dispatch, inherits custody, **or fails to
  learn B's results from the record** (the feedback must still work — a design that forbids the back-channel
  by simply *not surfacing anything* is not a pass).
- **Real engine (Epic 14 L4 / 14.4 promotion):** the covert-channel review gate wires this against the live
  apiserver + Postgres coordination record — asserting there is no API surface by which B mutates the
  coordinator's dispatch state, and that deleting the record/recall read leaves the coordinator with no
  alternate source. This is the same "prove the back-channel is structurally impossible" discipline as the
  discussion-room guard (10.4) and the plugin-seam guard (§17.4).
- **Why differential:** a happy-path "the coordinator dispatched C after B finished" demo passes even for a
  design riddled with a back-channel — B just happened to also write the record. Proving the harness
  *catches* a real back-channel + custody transfer first is what makes the §2.9 PASS meaningful.

## Out of scope (owned elsewhere)

- **The handoff artifact schema + its write** (2.8 — this story *consumes* it, does not define it).
- **The fenced claim/acquire mechanism** (2.2) and **fenced release/reclaim** (2.4/§6.3) — reused verbatim.
- **Scoped memory recall + the untrusted-recall tier** (6.6, §8.5) — this story *reads* it; the recall
  mechanism and trust-tiering are 6.6/3.6.
- **The `Role` CRD + squad-lead designation** (Epic 1) — this story *depends on* the marker, does not define
  the CRD.
- **Rate-limit re-route** (2.10, which *reuses* this story's coordinator to re-dispatch a paused item) and
  the **CI covert-channel gate itself** (Epic 14 L4 / 14.4). This story ships the **loop shape**
  (read-of-record → coordinator decides → new fenced dispatch), the **guardrail** (no message channel, no
  B-driven dispatch, no custody transfer, `recommended_next` advisory), and the falsification that a
  coordinator cannot be driven by a back-channel.
