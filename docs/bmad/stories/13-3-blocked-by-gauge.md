# Story 13.3: Tasks-blocked-by gauge = the blocked-condition projection on a curated error-code enum

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS STORY DEFINES THE CURATED `error_code` ENUM AND SHIPS THE `ksquad.coord.workitem.blocked`
> UP/DOWN GAUGE (obs-plan §5.1 row + §5.6 + §15 "Tasks blocked by", NFR-OBS).** Story 13.2 (ISI-2234)
> *lists* this instrument inside the §5.1 coordination table; **this story is its elaboration** — it pins
> the two things 13.2 left open and §15 flagged as an **honest gate**: (1) the **gauge is up/down** (a work
> item **enters** the blocked condition and later **clears** it — the series must **decrement back to zero**,
> not ratchet up like a counter), and (2) the `error_code` label is drawn from a **bounded curated enum**
> whose values were never enumerated (obs-plan §15: *"the error-code taxonomy … must land in the
> architecture revision for the instrumentation to be truthful"*). The load-bearing invariants: **the gauge
> is a pure projection of the coord `blocked_reason` read model** (arch §6, the same source `state` projects
> off) — turning it on or off never changes whether a work item is blocked or claimable; and **any reason
> outside the curated enum collapses to `other`, never leaking a free-form string as a label** — an
> uncurated `blocked_reason` reaching the metric as a raw label value is a cardinality-explosion, i.e. a
> **correctness failure of the observability contract, not a cosmetic gap** (13.6 enforces the label *key*;
> this story enumerates the *values* and guarantees the collapse). Read AC2 and AC4 literally.

## ⚠️ Scope pin — this story instruments a condition, it does not invent one (read first)

The **blocked condition** already exists in the architecture. Arch r25 refined `blocked` **from a lifecycle
*state* to an orthogonal *condition***: a blocked work item keeps its workflow `state` (one of the canonical
board columns Backlog·Todo·In Progress·In Review·Done) and carries a **`blocked_reason`** + a Blocked badge
overlay — it never leaves its lane to "become blocked". Arch r24 gave the first concrete reason
(`blocked_reason=needs_approval`, the Pending Approvals human-in-the-loop gate). This story adds **zero** new
coordination behaviour and **zero** new work-item mechanics: it reads the `blocked_reason` the coord model
already records and projects it as a **bounded-cardinality up/down gauge**. The one architectural decision it
*does* land — because §15 explicitly deferred it here — is the **curated `error_code` enum** (the bounded
taxonomy of blocked reasons). Enforcement (whether an item is blocked, whether a claim is allowed) lives in
the coord read model; observation lives here.

| Concern | This story | Owned elsewhere |
|---|---|---|
| The `ksquad.coord.workitem.blocked{error_code}` **up/down gauge** (enter-blocked ↑, clear-blocked ↓, settles to 0) | **✅ delivered (AC1)** | The instrument is *listed* by **13.2** (§5.1 table); this story is its elaboration |
| The **curated `error_code` enum** — the bounded blocked-reason taxonomy (the §15 honest-gate deferral) | **✅ delivered (AC3)** — closes the obs-plan §15 gate | Human source = obs-plan §5.1 note + §5.6; machine mirror = `cardinality-allowlist.txt` |
| **Unknown reason → `other`** collapse (no free-form `blocked_reason` ever reaches the metric as a label value) | **✅ the crux (AC4)** | 13.6 enforces the label *key* is allowlisted; this story guarantees the *value* stays in-enum |
| Observe-not-enforce: the blocked **condition** and claimability are identical with the gauge on/off | **✅ the crux (AC2)** | — |
| Gauge is a projection of the coord `blocked_reason` read model, not a second stored state | **✅ delivered (AC1)** | The `blocked_reason` column / condition — **arch §6** (this story reads it) |
| Cardinality: `run.id`/`work_item.id`/`principal.id` ride as **exemplars**, never labels | **✅ delivered (AC5)** | The CI lint that greps labels vs §5.6 — **Story 13.6** (this story *obeys*, 13.6 *enforces*) |
| The stale-approval / rising-backlog **alert** that reads this gauge | consumed | **13.7** (§9 alert rules) — e.g. `blocked{error_code=needs_approval}` sustained > SLO age |
| The dashboard tile that renders "Tasks blocked by (error code)" | consumed | **Story 8.8 / 13.9** (reads this instrument) |

## Story

As **an SRE / operator of the KSquad control plane**,
I want **the work items currently in the blocked condition projected as an up/down gauge labeled by a
bounded *curated* `error_code` enum — where entering the blocked condition increments the gauge for that
reason and clearing it decrements back (so a resolved block leaves no residue), any reason outside the
curated taxonomy collapses to a single `other` bucket rather than leaking a free-form string as a label, and
the whole projection is provably OBSERVE-ONLY (turning it on or off changes nothing about whether an item is
blocked or claimable)**,
so that **I can see at a glance how much work is stuck and *why* — how many items wait on approval, on a
dependency, on a credential, on human input — catch a rising blocked-backlog or a stuck approvals queue the
moment it starts, and drill from a bounded gauge bar back to the specific blocked work item through an
exemplar, without a per-item or free-text blocked-reason ever exploding the metric cardinality.**

## Context & prerequisites (read first)

- **Observability plan:** `docs/bmad/04-observability-plan.md`
  - **§5.1 "Coordination record — the audit spine"** — the row this story elaborates:
    `ksquad.coord.workitem.blocked` | **up/down gauge** | `error_code` (curated bounded enum, §5.6) |
    *"tasks currently blocked, labeled with the blocking error code — the Paperclip 'blocked-by' analogue
    (§15)."* The sibling `workitem.state` gauge (backlog depth by `state`) is the model this one mirrors:
    both are up/down gauges projected off the coord read model, not counters.
  - **§15 "Tasks blocked by (error code)"** — the **honest gate this story closes**: *"New
    `ksquad.coord.workitem.blocked{error_code}` gauge (§5.1); `error_code` added to the §5.6 bounded-label
    allowlist as a curated enum. Architecture follow-up … the work-item lifecycle enum … has no error-code
    taxonomy — the signal is specced here; the state + taxonomy must land in the architecture revision for
    the instrumentation to be truthful."* This story **lands the taxonomy** (AC3), making the instrument
    truthful.
  - **§5.6 cardinality budget** — the enforced label allowlist. `error_code` is an **ALLOWed** label *key*
    (a bounded curated enum). This story enumerates the *value* domain and guarantees emit sites stay inside
    it (AC4). `run.id`, `work_item.id`, `principal.id`, `team`/`project` names remain **forbidden as
    labels** — they ride as **exemplars / resource attributes** (AC5).
  - **§1.1 / §5.4 "observe, not implement"** — a metric observes enforcement, never implements it. Here the
    *enforcement* is the blocked condition itself (an item with a `blocked_reason` set is surfaced as
    blocked and — for `needs_approval` — is released from its fenced claim until resolved, arch §6.3); the
    gauge merely **counts** it (AC2, the crux).
  - **§4.3 / §7 semconv attrs** — the exemplar attrs (`run.id`, `work_item.id`) that join a gauge data
    point to its 13.1 span and the specific blocked work item.
  - **§1.5 noop-on-unset** — inherited from 13.1: with the OTLP endpoint unset the gauge is non-recording,
    zero series export, the blocked condition is unchanged (AC6).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§6 the coordination record** — `work_item(id, project_id, team_id, parent_id, title, state, …)`; the
    **blocked condition** is the orthogonal `blocked_reason` (arch **r25**: blocked is a condition, not a
    sixth state; **r24**: `blocked_reason=needs_approval` is the first concrete reason, the Pending
    Approvals gate). This gauge is the quantitative projection of that condition.
  - **§6.2/6.3** — for `needs_approval`, the blocked item **releases its fenced claim** (a human resolves
    it via a provenanced approve/reject; not a Run `Paused`, not a P2P handoff). The gauge observes the
    release count; it does not cause it.
- **Depends on:**
  - **Story 13.2** (ISI-2234 — the §5.1 coordination-metrics projection this instrument belongs to: the
    observe-not-enforce contract, the exemplar-not-label discipline, the SDK/noop wiring reuse). This story
    is the elaboration of one row in 13.2's table; it inherits 13.2's crux and adds the gauge/enum specifics.
  - **Story 13.1** (ISI-2233 — the OTel SDK wiring, noop-on-unset, and the durable Run trace this gauge's
    exemplars attach to).
  - **Arch §6** blocked condition (`blocked_reason`), r24/r25 — the source of truth this gauge projects.
- **Blocks / is consumed by:** **13.6** (cardinality lint — enforces `error_code` is allowlisted; this
  story supplies the enumerated value domain it obeys), **13.7** (the §9 stale-approval / blocked-backlog
  alert that reads this gauge), **Story 8.8 / 13.9** (the "Tasks blocked by" dashboard tile).

## The curated `error_code` enum (authoritative — the §15 deferral, landed here)

The blocked condition's reason is a **bounded curated enum**. Each value maps to a real KSquad blocking
mechanism, so the taxonomy is **truthful** (§15's requirement) rather than aspirational. Emit sites map the
coord `blocked_reason` to exactly one of these; **anything unrecognized maps to `other`** (AC4).

| `error_code` | The block | Grounded in |
|---|---|---|
| `needs_approval` | Human-in-the-loop approval gate; item released its fenced claim until an authorized human approves/rejects | arch r24/r25 §6.3; §15 Pending Approvals; `ksquad.approval.pending` |
| `blocked_by_dep` | Waiting on an unresolved sibling/parent dependency work item (the literal Paperclip "blocked-by") | Paperclip `blockedByIssueIds`; arch §6 `parent_id` tree |
| `awaiting_credential` | A required per-principal credential is missing or expired | Epic 7 (Story 7.4 pause/resume on credential expiry) |
| `awaiting_input` | Waiting on a human answer to a structured question | interactions (`ask_user_questions`) |
| `awaiting_review` | Review requested changes / pending a reviewer disposition | code-review disposition path |
| `budget_exhausted` | Token/cost budget or namespace quota exhausted | §8.5 context budget / §5.5 metering / §12.1 quota |
| `upstream_failed` | A depended-on work item terminally failed | coord dependency edge |
| `other` | **Curated catch-all** — any `blocked_reason` not in the taxonomy above collapses here | cardinality safety valve (AC4) |

**Why a closed enum with an explicit `other`.** A `blocked_reason` is written by many code paths and — like a
free-text reason — is an unbounded domain. Emitting it raw as a metric label value is exactly the cardinality
explosion §5.6 forbids (one new series per distinct reason string). The **curated enum bounds the domain to a
handful**, and `other` is the **safety valve**: an unrecognized or newly-introduced reason is *observable*
(the gauge still moves) without being *unbounded* (it lands in `other`, never as a raw label). Adding a new
first-class reason is a deliberate one-line enum + allowlist edit (obs-as-code), not an accident of a new
`blocked_reason` string leaking into the label space.

## The up/down gauge crux (authoritative — AC1, distinct from a counter)

`workitem.blocked` is an **up/down gauge, not a counter**. A work item **enters** the blocked condition
(gauge `+1` for its `error_code`) and later **clears** it — the block is resolved, or the item transitions /
closes (gauge `−1` for that same `error_code`). The series therefore **reflects the current depth of blocked
work per reason and settles back to zero when nothing is blocked** — it answers *"how many items are blocked
right now, and why"*, not *"how many blocks have ever happened"* (that historical rate, if wanted, is a
separate counter, out of scope). A design that only ever increments — treating a gauge like a counter, so a
resolved `needs_approval` block still shows on the gauge forever — is a **correctness failure of AC1**: the
"blocked-by" board would report phantom stuck work that has already cleared.

## The observe-not-enforce crux (authoritative — the load-bearing invariant, AC2)

The **blocked condition is enforcement; the gauge is observation.** Whether a work item is blocked (its
`blocked_reason` is set) — and, for `needs_approval`, whether its fenced claim is released so no agent can
work it until a human resolves it (arch §6.3) — is decided entirely by the **coord read model**. The gauge
**counts** that condition; it is never **read** by it.

**The invariant:** whether an item is blocked, which reason it carries, and whether it is claimable are
**byte-for-byte identical whether the gauge emit is present or absent**. The enforcement path reads only
durable coord state (`blocked_reason`, `state`, `claim`); the gauge is a **pure projection appended after the
condition is set/cleared** and is **never** read back. A design where a claim is gated on the gauge value
(e.g. "don't dispatch if `blocked` > 0") — so that turning the exporter off changes claimability — is a
**correctness failure of the observability contract, not a cosmetic gap**. This is 13.2's AC2 (the fence
sequence identical on/off) applied to the blocked condition.

## Acceptance Criteria

**AC1 — the up/down gauge exists, with the §5.1 shape, projecting the coord blocked condition.**
Given the coord read model records a work item's blocked condition (`blocked_reason`, arch §6/r24/r25), When
an item **enters** the blocked condition, Then `ksquad.coord.workitem.blocked{error_code=…}` increments by 1
for that reason; And when the item **clears** the block (resolved / transitioned / closed), the gauge
decrements by 1 for that same reason; And the series **settles to zero when nothing is blocked** — it is a
current-depth **up/down gauge** (like the sibling `workitem.state` gauge), **not** a monotonic counter that
retains resolved blocks; And it is a **projection of the coord `blocked_reason`** (the same source `state`
projects off) — not a second stored state and not duplicating the audit content into a label.

**AC2 — the gauge OBSERVES, it does not ENFORCE (the crux): the blocked condition is identical with the gauge on/off.**
Given a work item's blocked condition, When it is evaluated with the OTLP exporter recording and again with
it unset, Then whether the item is blocked, which `error_code` it carries, and whether it is **claimable**
are **byte-for-byte identical**; And **no enforcement decision reads the gauge**: the coord path reads only
durable state (`blocked_reason`, `state`, `claim`), and the gauge emit is a pure projection appended after
the condition is set/cleared and never read back; And a design where claim/dispatch is gated on the gauge
value — so turning the exporter off changes claimability — is a **correctness failure of the observability
contract, not a cosmetic gap**.

**AC3 — the curated `error_code` enum is defined and is the bounded label domain (closes the §15 gate).**
Given the blocked gauge, When it is emitted, Then its `error_code` label value is drawn from the **curated
bounded enum** `needs_approval | blocked_by_dep | awaiting_credential | awaiting_input | awaiting_review |
budget_exhausted | upstream_failed | other`; And that enum is version-controlled as the single source of
truth (obs-plan §5.1 note + §5.6, machine mirror `cardinality-allowlist.txt`), closing the obs-plan §15
honest gate (the taxonomy is now defined, so the instrument is truthful); And adding a new first-class reason
is a **deliberate enum + allowlist edit** (obs-as-code), not an accident.

**AC4 — unknown reason collapses to `other`: no free-form `blocked_reason` ever reaches the metric as a label (the crux).**
Given a `blocked_reason` that is **not** one of the curated enum values (an uncurated, misspelled, or
newly-introduced reason), When the gauge is emitted, Then the `error_code` label is **`other`** — the raw
`blocked_reason` string is **never** used as the label value; And this collapse is what keeps the metric
bounded: an unbounded/free-text reason emitted raw as a label is the cardinality explosion §5.6 forbids (one
series per distinct string) and is a **correctness failure of the observability contract, not a cosmetic
gap**; And the block is still **observable** — it moves the `other` bar (so a rising `other` is itself a
signal to curate a new first-class reason), it is not silently dropped.

**AC5 — cardinality discipline: forbidden identifiers ride as exemplars, never as metric labels.**
Given the blocked gauge, When it is emitted, Then its **only** label key is `error_code` (from the §5.6
allowlist); And `run.id`, `work_item.id`, `principal.id`, and `team`/`project` names are **never** labels —
they ride as **exemplars** (joining the gauge data point to the specific blocked work item and its 13.1 Run
trace, §4.3) or as resource attributes; And adding one as a label is an explicit build failure (13.6
enforces; this story *obeys* and asserts it locally) — while the bounded gauge **still joins** to the
specific blocked item through the exemplar, so drill-down survives without cardinality explosion.

**AC6 — noop-on-unset (inherited from 13.1): observability on/off is config, never a coord-behaviour change.**
Given the OTLP endpoint is **unset**, When the coord blocked condition is set/cleared, Then the gauge is
**non-recording**, **zero series are exported**, and — per AC2 — the blocked condition and claimability are
unchanged; turning this observability on is an **operator config (set the endpoint), not a redeploy**.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/blocked-gauge-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same shape as the 13.2 coord-metrics check), not a happy-path demo. It models the coord
blocked condition (a work item gains/loses a `blocked_reason`; `needs_approval` releases the fenced claim)
instrumented with an up/down gauge sink, and proves the projection has teeth by driving each modelled
transition and asserting it is **detectably wrong** under mutation.

- **(AC1) up/down, not a counter.** Blocks two items (`needs_approval`, `blocked_by_dep`), resolves one, and
  asserts the gauge reads `{needs_approval:0, blocked_by_dep:1}` and settles to all-zero once both clear.
  *Mutation-proven:* making the gauge **monotonic** (never decrement on clear, `counter_not_gauge`) leaves a
  resolved block showing forever → the settled-to-zero assertion fails → **RED**.
- **(AC2 — the crux) observe, not enforce.** Runs the blocked/claimable evaluation with the gauge recording
  and again with it unset and asserts **claimability is identical**. *Mutation-proven:* gating claim on the
  gauge value (`enforce_via_gauge` — "not claimable while `blocked>0`") makes claimability differ when the
  exporter is off → the two runs diverge → **RED**.
- **(AC3/AC4 — the crux) unknown reason → `other`.** An uncurated `blocked_reason` ("waiting_on_vendor")
  projects `error_code=other`, never the raw string. *Mutation-proven:* passing the raw reason through as
  the label (`raw_reason_label`) is caught by the cardinality guard (a label value outside the curated enum)
  → **RED**; and the block still moved the `other` bar (not silently dropped).
- **(AC5) cardinality + exemplar join.** The clean path emits **no** label key but `error_code`, and each
  gauge data point carries an exemplar with `work_item.id`/`run.id` joining it to the blocked item's trace.
  *Mutation-proven:* adding `work_item.id` as a **label** (`label_work_item_id`) trips the guard → **RED**;
  dropping the exemplar (`drop_exemplar`) leaves the bar un-drillable → **RED**.

Exits non-zero if the gauge fails to decrement a resolved block (counter-not-gauge), if claimability differs
between exporter on/off (the gauge leaked onto enforcement), if an uncurated reason reaches the label as a
raw string (cardinality explosion) or is silently dropped, if a forbidden identifier reaches a label, or if
the bounded gauge loses its trace-join exemplar. **The headline invariant is mutation-checked:** gating claim
on the gauge makes the gauge-on and gauge-off claimability diverge and turns the check **RED** — the
"observe, not enforce" contract is falsifiable, not aspirational.

## Out of scope (owned elsewhere)

- **The blocked condition itself** (setting/clearing `blocked_reason`, releasing the fenced claim for
  `needs_approval`, the human approve/reject) — **arch §6 / Epic 8 (Pending Approvals)**. This story
  **reads** the condition; it does not implement or change it.
- **The rest of the §5.1 coordination instruments and the observe-not-enforce/exemplar contract** —
  **Story 13.2** (ISI-2234). This story is the elaboration of one row; it inherits that contract.
- **The OTel SDK wiring, noop-on-unset providers, and the durable Run trace** the exemplars attach to —
  **Story 13.1** (ISI-2233).
- **The cardinality CI lint** (grep the `error_code` label key vs §5.6; `work_item.id`≠label) — **Story 13.6**
  (this story supplies the enumerated value domain and asserts the collapse locally; 13.6 enforces the key
  at build time).
- **The §9 stale-approval / blocked-backlog alert** that reads this gauge (e.g. `needs_approval` sustained
  past an SLO age) — **Story 13.7**.
- **The "Tasks blocked by (error code)" dashboard tile** — **Story 8.8 / 13.9** (reads this instrument).

This story ships the **`ksquad.coord.workitem.blocked` up/down gauge, the curated `error_code` enum (closing
the obs-plan §15 honest gate so the instrument is truthful), the unknown-reason→`other` collapse that keeps
the label domain bounded, the observe-not-enforce neutrality (blocked/claimable identical with the gauge
on/off), the exemplar-not-label cardinality discipline, and the differential falsification** — the
quantitative, observe-only projection of the blocked condition that lets an operator see how much work is
stuck and why, without a free-form blocked-reason ever exploding the metric cardinality.
