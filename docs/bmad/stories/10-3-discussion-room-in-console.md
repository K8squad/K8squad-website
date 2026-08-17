# Story 10.3: Discussion room in the console — threaded history, provenance badges, post/reply-in-thread

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🖥️ THE ROOM BECOMES A HUMAN-IN-THE-LOOP COLLABORATION SURFACE (arch §7.5, §13; Theme J FR-J1/J2/J3;
> mock 07-discussion-room / ISI-2160).** The load-bearing invariants: **(1)** every message renders an
> **author/provenance badge** (agent / human / Run) derived from the 10.1 columns
> (`author_agent_id`/`author_run_id`) — attribution is never dropped or spoofable in the UI (FR-J3).
> **(2)** the surface is a **pure consumer of the 10.1 API behind the same BFF authorization choke point**
> as every other console read model (§13, arch r21/OQ20) — **deny renders as 404-not-403** (the 8.7d gate,
> reused), and it **never** crosses tenancy boundaries (FR-J4). **(3)** it is a **collaboration surface,
> not a coordination affordance** — there is no claim/checkout/assign control in the room UI; the §7.3/§7.5
> no-P2P argument applied to the console (arch §13, L1812). Humans post via the console; agents post via
> the apiserver tool surface (10.1) — **both hit the same server-stamped write path.**

## Story

As **an operator**,
I want **the per-Project discussion room in the console — threaded history with author/provenance badges
(agent/human/Run), post and reply-in-thread, agents and humans side by side**,
so that **the team's open reasoning (context, Q&A, decisions, announcements) is legible and participable in
the console (FR-J1/J2/J3), rendered as a pure consumer of the 10.1 API behind the shared BFF authz choke
point, themed per 8.9, and structurally free of any coordination affordance.**

## Context & prerequisites (read first)

- **Epics source:** `docs/bmad/04-epics-and-stories.md` §Epic 10 row 10.3 (L558). *"Epic 8 surface; mock in
  flight (story 8.9 theming applies)."* — mock now **done** (07-discussion-room, ISI-2160).
- **Mock:** `docs/bmad/ux/images/07-discussion-room.svg` (+ `-light.svg`, `.png`). The authoritative visual
  spec — threaded messages, author rows, the Project-scoped `Discussion` nav item
  (`docs/bmad/ux/console_kit_ia.py`: `PROJECT → Issues · Discussion · Project Board · File Explorer`).
- **Architecture:** `docs/bmad/03-architecture.md`:
  - **§7.5 — served by the apiserver, rendered per Project in the console, behind the same BFF
    authorization choke point (§13) and the same Team-scope tenancy filter as memory (§7.3.3).**
    *"human-in-the-loop collaboration surface (FR-J1/J2), messages author-attributed (FR-J3), Project-scoped
    and never crosses tenancy boundaries (FR-J4, NFR-SEC7)."*
  - **§13 / arch r21 (OQ20) — one enforcement point, every surface.** The discussion room passes the
    **same** deny-by-default middleware as every console read model — no per-surface authz path.
  - **§13 (L1812) — no-P2P applied to the console.** The room is *not* a coordination affordance.
  - **Story 8.2 (SSE, ISI-2265, done) — the ONE EventSource/BFF proxy** every live surface rides.
  - **Story 8.9 (theming, ISI-2279, done) — whole-shell dark+light** T1–T7 contract; applies to the room.
  - **Story 8.7d (BFF per-principal scoping gate, ISI-2274, done) — 404-not-403** deny pattern; reused.
- **Depends on:** **10.1 (the REST/tool surface + provenance columns — the read/write API)** and **Epic 8
  (console shell + BFF + SSE 8.2 + theming 8.9 + the 8.7d 404-gate — all done)** and the **mock ISI-2160
  (done).** This is a console feature over an existing API + existing console substrate.
- **Blocks / is consumed by:** operators/agents collaborating in the room; **10.4** (the UI carries no
  coordination affordance — part of the structural guardrail's console face).

## What this story provides

1. **The Project-scoped `Discussion` route + view.** Reachable from the Project nav
   (`Issues · Discussion · Project Board · File Explorer`, per the IA). Lists the room's threads (title,
   opener badge, last-activity, reply count), opens a thread into threaded history.
2. **Threaded message rendering with provenance badges (FR-J3).** Each message shows body, timestamp
   (`created_at`), and an **author/provenance badge** derived from 10.1 columns:
   - **agent** — `author_agent_id` present → agent name/avatar badge;
   - **human** — `author_agent_id` NULL → user badge;
   - **Run** — `author_run_id` present → a Run chip that **deep-links to the Run detail page (8.11)**.
   Reply-in-thread nests via `parent_id` (adjacency, like the 8.x tree renders). Retracted messages
   (`invalidated_at`) render as a tombstone/collapsed, not silently dropped (audit-honest).
3. **Post + reply composers.** Humans post a new thread (`POST …/threads`) or reply
   (`POST …/threads/{id}/messages` with `parent_id`). The composer sends **only `{body, parent_id?}`** —
   provenance is server-stamped (10.1 AC3); the console never sends an `author`.
4. **Live append via the 8.2 SSE channel (preferred).** New messages/threads appear live over the single
   8.2 EventSource/BFF proxy (the same live channel 8.8f/8.10/8.11 ride) — no bespoke socket. If the SSE
   room feed slips, the view degrades to poll-on-focus; live is the target, not a hard gate.
5. **Theming + a11y from 8.9.** The room honors the whole-shell T1–T7 dark+light contract; badges use the
   theme-invariant chip conventions (8.9 lesson: channel/badge borders derive from base, not hardcoded).

## Acceptance Criteria

**AC1 — the room renders threaded history for a Project, agents + humans side by side (FR-J1).**
Given a Project room, When an operator opens `Discussion`, Then they see the room's threads and can open a
thread into **threaded** message history (`parent_id` nesting), with agent- and human-authored messages
shown side by side — matching the 07-discussion-room mock.

**AC2 — every message carries an author/provenance badge (agent/human/Run) (FR-J3, the crux).**
Given a rendered message, When it is displayed, Then it shows an author badge derived from the 10.1
provenance columns — **agent** (`author_agent_id` set), **human** (NULL), and a **Run** chip
(`author_run_id` set) that deep-links to the Run detail (8.11). Attribution is **never** dropped; a message
with no visible author is a defect.

**AC3 — post + reply-in-thread; provenance is server-stamped, not sent by the console (§7.3.1).**
Given the composer, When a human posts or replies, Then the console sends **only** `{body, parent_id?}` to
the 10.1 endpoint and the message appears attributed to the **authenticated user** — the console **never**
supplies `author_*`. Agents posting via the apiserver tool surface (10.1) appear in the same thread with an
agent badge. Both write paths are the same server-stamped 10.1 handler.

**AC4 — the room passes the shared BFF authz choke point; deny is 404-not-403; no cross-tenant read.**
Given an unauthorized principal (or a Team-B user against a Team-A Project), When they request the room,
Then the BFF denies via the **same deny-by-default middleware** as every console read model (§13/OQ20) and
the room **renders as missing / 404-not-403** (the 8.7d pattern) — never another Team's threads (FR-J4,
NFR-SEC7).

**AC5 — the room is a collaboration surface with NO coordination affordance (§7.5/§13 no-P2P).**
Given the room UI, When it is inspected, Then it exposes **no** claim / checkout / assign / state-transition
/ complete control — posting a message moves no work item and changes no coordination state. Work custody
lives **only** on work items (Tickets / Epic 2). (Part of the 10.4 guardrail's console face.)

**AC6 — theming + live update (8.9 / 8.2).**
Given dark and light themes, When the room renders, Then it honors the 8.9 whole-shell T1–T7 contract; and
new messages appear **live over the 8.2 SSE channel** (degrading to poll-on-focus if the feed slips), with
no bespoke second live channel.

## Test guidance

- **Component/view tests:** badge derivation is exhaustive over the provenance triple — `author_agent_id`
  set ⇒ agent badge; NULL ⇒ human; `author_run_id` set ⇒ Run chip with the correct 8.11 deep-link; a
  message missing all three renders no fabricated author (defect). Retracted (`invalidated_at`) ⇒ tombstone,
  not dropped.
- **Composer test:** the outbound POST body contains **only** `{body, parent_id?}` — assert no `author_*`
  field is ever sent (the server-stamp boundary; a console that sends `author` is a defect).
- **Authz test (reuse 8.7d harness):** unauthorized / cross-Team request → 404-not-403, zero foreign
  threads rendered.
- **No-coordination test (10.4 console face):** static assertion that the room view exposes no
  claim/checkout/assign/transition control — grep the view surface for coordination verbs, expect none.
- **Theming snapshot:** dark + light over the room screens honor the 8.9 T1–T7 tokens.

## Out of scope (owned elsewhere)

- **The REST/tool API + provenance columns + server-stamp** (**10.1**) — consumed, not built.
- **Memory recall of room content** (**10.2**) — the console renders the room; searching it as memory is
  10.2's surface.
- **The console shell / BFF / SSE (8.2) / theming (8.9) / 404-gate (8.7d)** — reused Epic 8 substrate.
- **The tested covert-channel guarantee** (**10.4**, L4 suite ISI-2245) — this story just carries no
  coordination affordance in the UI; the *test* is 10.4.
