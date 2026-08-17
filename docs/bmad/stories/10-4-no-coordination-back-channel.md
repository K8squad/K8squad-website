# Story 10.4: [Guardrail] The discussion room is structurally unable to become a coordination back-channel

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔒 A LOCKED-DECISION GUARDRAIL — MADE STRUCTURAL, THEN TESTED (arch §7.5, §6, §7.3; PRD FR-B3 / §8.4
> honest framing; F6).** The locked decision — *coordination is shared work-items + fencing, NOT agent
> P2P chat* — is preserved for the room the **same way it is for memory (§7.3): by construction.** This
> story owns two things: **(1)** asserting the *structural* guarantee already built into 10.1 — the
> `discussion` schema/API has **no** claim/lease/fence/state/holder column and **no** custody-transfer
> verb; and **(2)** the *review-time evidence* — an **F6-style covert-channel case** proving a hostile Run
> cannot drive a coordinator's dispatch through room state. That evidence **lands in the L4 security suite
> (ISI-2245, DONE) as case S4-6/AC7**, NOT a standalone harness. This is a guardrail, not a feature: it
> ships *no product surface*; it ships a *proof* that the surface 10.1/10.3 built cannot become a
> back-channel. Threaded messaging superficially **looks** like P2P — the whole point is to demonstrate it
> structurally is not.

## Story

As **the team**,
I want **the discussion room to be structurally unable to carry coordination — no claim/handoff/state-
transition semantics — with review-time F6 evidence that coordination state cannot be mutated via the
room**,
so that **the locked "coordination via fenced work-items, not P2P chat" decision (Epic 2, §6) is honored by
construction for the room exactly as it is for memory (§7.3), and we can *demonstrate* (not merely assert)
that a hostile or well-meaning Run cannot use the room as a covert coordination back-channel (F6, FR-B3).**

## Context & prerequisites (read first)

- **Epics source:** `docs/bmad/04-epics-and-stories.md` §Epic 10 row 10.4 (L559). *"Locked-decision
  guardrail; pairs with FR-B3 / §8.4 honest framing (F6)."* Build order: **10.4 is evaluated against the
  10.1 API surface.**
- **Architecture:** `docs/bmad/03-architecture.md`:
  - **§7.5 — "Why this is NOT a coordination channel (the §7.3 argument, applied again)."** The three-point
    structural argument this story tests: (1) discussion carries **talk, not work custody** — no
    `claim`/`lease`/`fence_token` and no message→custody-holder mapping; (2) **the coordination act has no
    expression here** — transfer of custody exists *only* in the fenced `coord` claim/comment tables (§6),
    checkout-gated and fenced; (3) so the **no-P2P spirit is honored for the identical reason memory honors
    it** — the coordination primitive stays structurally confined to the fenced work-item record.
  - **§6 — coordination record.** *"No agent-to-agent channel exists in the schema; there is no `message`
    table and no lateral transport (I4)."* Custody moves **only** here, fenced.
  - **§7.3.2 — untrusted read.** Room content handed to an agent is `trust:"untrusted"` (10.2) — part of
    why a room message cannot *become* authority.
- **PRD:** **FR-B3** (coordination via shared record, not P2P) and **§8.4 honest framing** — the room must
  not covertly re-introduce the lateral channel the product claims it does not have (F6).
- **The F6 evidence home:** **Story 14.4 — L4 security suite (ISI-2245, DONE), case S4-6 / AC7.** That case
  already asserts: a hostile Run's poisoned **room message** intended to steer a coordinator is (a) surfaced
  **untrusted** with un-forgeable provenance, and (b) the coordinator's claim/dispatch decision rides
  **shared work-items + fencing only** — *"there is no memory/room semantics that mutate a
  claim/handoff/state (10.4/12.4, §6, F6)."* This story **owns the 10.4 half** of that case.
- **Depends on:** **10.1 (the API surface this is evaluated against)** and **Story 14.4 / ISI-2245 (the L4
  suite that hosts the F6 evidence — DONE, merged on main).**
- **Pairs with:** **12.4** (agent identity / no-P2P covert-channel guard) — the sibling guardrail; together
  they are the covert-channel arm of S4-6.

## What this story owns (a guardrail, not a product surface)

1. **The structural assertion over the 10.1 surface (the design constraint, verified).** Confirm — as a
   *tested* property, not just prose — that the built `discussion` schema + API has **no** `claim`,
   `lease`, `fence_token`, `state`, `holder`, `assignee`, or any custody/status column, and **no** endpoint
   or tool that claims / checks out / transitions / completes / reassigns a work item, and that **no**
   discussion write mutates any `coord` row. (10.1 builds this by construction; 10.4 makes it a gate.)

2. **The F6 covert-channel case, in the L4 suite (S4-6/AC7).** A differential case: a fixture hostile Run
   posts a room message crafted to steer a coordinator's next dispatch; the case asserts (a) the read is
   **untrusted** with the hostile author's **un-forgeable** provenance (server-stamped, 10.1 AC3 / §7.3.1),
   and (b) the coordinator's claim/dispatch decision is driven by **fenced work-items only** — **no** path
   exists by which a room message silently becomes a claim/handoff/state change. A path by which it does →
   **the case fails.** Confirm the S4-6/AC7 case as merged in ISI-2245 already exercises the **room** arm
   (not only the memory arm); if the merged suite covers only memory, add the **additive room arm** to
   S4-6 (a small case addition, self-skip-with-reason gated on the room API being deployable in kind, per
   14.4 AC8) — do **not** stand up a standalone harness (the memory note and the epic both route the
   evidence into the L4 suite).

## Acceptance Criteria

**AC1 — structural: no coordination column or verb exists on the room surface (the §7.5 fence, tested).**
Given the 10.1 `discussion` schema + API, When they are inspected by the guardrail check, Then there is
**no** `claim`/`lease`/`fence_token`/`state`/`holder`/`assignee` column and **no** endpoint/tool that
claims/checks-out/transitions/completes/reassigns a work item. Any such column or verb **fails** the
guardrail. (This is 10.1 AC4 promoted to a standing gate.)

**AC2 — no discussion write mutates coordination state (the crux, F6).**
Given the room API, When any discussion write executes (post/reply/retract), Then **no** `coord` row
(claim/lease/comment/state) is created or mutated as a side effect — a discussion write moves **zero** work
items and changes **zero** custody. A write path with a side effect into `coord` **fails** the case.

**AC3 — the F6 covert-channel evidence lives in the L4 suite (S4-6/AC7), room arm present.**
Given the L4 security suite (ISI-2245), When it runs, Then case **S4-6/AC7** exercises the **room** arm: a
hostile Run's room message is surfaced **untrusted** with un-forgeable provenance, and the coordinator's
dispatch rides **fenced work-items only** — no room-driven coordination. If the merged suite's S4-6 covers
only the memory arm, an **additive room arm** is added there (not a new harness), gated self-skip-with-
reason per 14.4 AC8.

**AC4 — provenance is un-forgeable (server-stamped), so the channel cannot be laundered.**
Given a hostile Run attempting to post as another principal, When it writes to the room, Then the
provenance is **server-stamped** (10.1 AC3 / §7.3.1) — the message is attributed to the hostile Run's real
principal, never the impersonated one — so even the *content* of a covert-steer attempt is fully
attributable and distrusted (§7.3.2). Forged attribution is **un-representable.**

**AC5 — honest framing (FR-B3 / §8.4): the product's no-P2P claim holds for the room.**
Given the guardrail + the S4-6 evidence, When the coordination model is described, Then the claim
"coordination is fenced work-items, not P2P chat" is **true of the room** — demonstrated, not asserted —
matching how §7.3 makes it true of memory. The room is *how people/agents reason in the open*; the `coord`
record is *where custody actually moves* (§7.5).

## Test guidance (the falsification — the deliverable)

- **Static/structural guardrail** (AC1/AC2): a check (co-located with the 10.1 schema check, or a small
  `discussion-no-coordination-check.py`) that greps/model-asserts the `discussion` schema + API surface for
  the forbidden columns/verbs and for any write path touching `coord`. **Mutation contract (teeth):** add a
  `state`/`holder`/`fence_token` column to the schema → **RED** (AC1); add a `POST …/claim` verb → **RED**
  (AC1); make a discussion write upsert a `coord.claim` row → **RED** (AC2). Green requires the surface to
  carry talk only.
- **F6 covert-channel case** (AC3/AC4) — in the L4 suite (S4-6/AC7): differential — a hostile Run posts a
  steering room message; assert (a) the read is `trust:"untrusted"` with the hostile principal's provenance
  (not the impersonated one), and (b) the coordinator's next claim/dispatch is unchanged by the room
  message — it rides fenced work-items only. **Teeth:** if a code path let the room message flip a claim or
  seed a handoff, the case goes **RED**. Reuse the 14.4 fixture harness; do not build a parallel one.
- **Confirm-then-augment:** first read the **merged** S4-6/AC7 in ISI-2245 (on main) to see whether the
  **room** arm is already present; only add the additive room case if it is memory-only. Record the finding
  in the story's review notes so the L4 suite owner (this is a co-owned case) is not surprised.

## Out of scope (owned elsewhere)

- **The room schema/API and its structural coordination-freeness *by construction*** (**10.1** — 10.4
  promotes that to a *tested* gate).
- **The untrusted-read envelope** (**10.2 / §7.3.2** — 10.4 relies on it for AC4/AC5 but does not build it).
- **The L4 suite harness + the other S4 cases** (**14.4 / ISI-2245, DONE** — 10.4 contributes/confirms the
  room arm of S4-6 only).
- **Agent-identity / no-P2P covert-channel guard** (**12.4** — the sibling half of the S4-6 covert arm).
