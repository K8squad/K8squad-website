# Story 13.4: Token + cost consumption metering per principal — the best-effort, observe-only usage projection

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE CONSUMPTION-METERING SPINE (obs-plan §5.5 / §15 / §16.5, epics row 13.4, NFR-OBS1 /
> CTO consumption-metering checklist).** There is exactly **one** signal — `ksquad.agent.tokens{runtime,
> direction}` (§5.5, aligned to OTel `gen_ai.usage.*`, §7) — surfaced **best-effort by the shims** as running
> agents report usage. **Per-ticket** rollups aggregate on `work_item.id` and **per-user cost** rollups
> aggregate on `user.id` — **both via exemplars/traces, never as a metric label** (the cardinality law
> §1.2/§5.6). Consumption is **attributed per user/principal** (first-class under the BYO-subscription
> credential model, §11) and **surfaced by dashboard 8.8** through the §17.2 metrics query seam with **no
> bespoke accounting path** — no second ledger, no rollup datastore. Token counts are **best-effort /
> runtime-reported (OQ14): legibility, not the billing authority.** The load-bearing invariant is the same
> one 13.1 makes for the tracer and 13.2 makes for the coord path: **metering OBSERVES, it is never
> load-bearing** — the agent run outcome (dispatch and the §5.9 context-budget fit/truncation decision) is
> **byte-for-byte identical whether the token metric is emitted or not**, and nothing on the enforcement path
> ever reads it. A design where the §5.9 budget fit reads consumed tokens from the metric counter, or where
> the dashboard total is sourced from a private ledger that drifts from the metered truth, is a **failure of
> the metering contract, not a cosmetic gap.** Read AC2 and AC6 literally.

## ⚠️ Scope pin — this story instruments, it does not invent an accounting system (read first)

This story adds **zero** new accounting behaviour and **zero** new datastore. The shims already surface token
usage over A2A (Epic 5 shim token surfacing, obs-plan §5.5 Appendix); the OTel SDK wiring, noop-on-unset, and
the durable Run trace the exemplars attach to are **already built** in Story 13.1 (ISI-2233); the `user.id` /
`work_item.id` / `run.id` correlation dimensions are the ones 13.1 stamps on every span/log/exemplar. This
story **projects** the shim-reported usage as the single §5.5 counter, wires the exemplars so the backend can
roll consumption up **per principal and per ticket**, and proves the projection is faithful, best-effort, and
observe-only. The dashboard that renders it is 8.8e (ISI-2325); the CI lint that enforces the label law is
13.6; the collector/redaction pipeline is 13.7; a first-class currency **cost unit** (if ever wanted) is the
same backend rollup × a price table (§16.5). **The one-line boundary: the shims decide how many tokens a turn
used; this story lets an operator see consumption per user / per ticket / per project in the dashboard —
without inventing a ledger and without the metering ever becoming load-bearing for what an agent does.**

| Concern | This story | Owned elsewhere |
|---|---|---|
| The §5.5 `ksquad.agent.tokens{runtime, direction}` counter, best-effort shim-surfaced, aligned to `gen_ai.usage.*` (§7) | **✅ delivered (AC1)** | — |
| Per-ticket (`work_item.id`) + per-user (`user.id`/`principal.id`) rollups as **backend aggregations over exemplars**, never a label | **✅ delivered (AC5)** | — |
| Per-principal attribution, first-class under the BYO-subscription credential model (§11) | **✅ delivered (AC5)** | The credential/principal model — **Epic 7** (this reads its `principal`) |
| **No bespoke accounting path** — the dashboard total IS the §17.2 OTel rollup, not a private ledger | **✅ the crux (AC6)** | The dashboard read model / query seam — **8.8a** (ISI-2325); the widget — **8.8e** |
| Observe-not-enforce: the run outcome (dispatch, §5.9 fit) is identical with metering on/off; nothing reads the metric | **✅ the crux (AC2)** | The §5.9 budget enforcement itself — **Story 5.9** (this reads its inputs, never its metric) |
| Cost = a **backend computation** over tokens × a price table; degrades to tokens-only | **✅ delivered (AC7)** | The price table / FinOps currency unit — **console/FinOps owner (§16.5)** |
| Cardinality: `run.id`/`work_item.id`/`user.id`/`principal.id` ride as **exemplars**, never labels | **✅ delivered (AC5)** | The CI **lint** that greps labels vs §5.6 — **Story 13.6** (this *obeys*, 13.6 *enforces*) |
| Best-effort / runtime-reported honesty (OQ14): a silent shim advances nothing, the metric never fabricates | **✅ delivered (AC4)** | The shim's token surfacing — **Epic 5** (this projects what it reports) |
| OTel SDK wiring + noop-on-unset + the collector export/redaction pipeline | consumed | **13.1** (wiring, AC4 noop) / **13.7** (collector + PII/secret redaction) |

## Story

As **a finance/ops owner of the KSquad control plane**,
I want **token + cost consumption metered per agent / Run / Project and attributed per user/principal — as a
single best-effort `ksquad.agent.tokens{runtime, direction}` signal the shims surface, where per-ticket and
per-user (and per-user cost) rollups are backend aggregations over exemplars/traces rather than
high-cardinality labels, cost is a backend computation over that signal rather than a new instrument, the
whole thing rides the existing OTel pipeline into dashboard 8.8 with no bespoke accounting path, and the
metering is provably observe-only (turning it on or off changes nothing about what an agent does)**,
so that **I can see who and what is consuming tokens — per user, per ticket, per project — legibly and
honestly, without a second ledger to reconcile, without a per-actor identifier exploding metric cardinality,
and without the metering layer ever becoming load-bearing for the agent behaviour it observes.**

## Context & prerequisites (read first)

- **Observability plan:** `docs/bmad/04-observability-plan.md`
  - **§5.5 "Shim / A2A"** — the authoritative instrument row this story implements verbatim:
    `ksquad.agent.tokens` **counter**, labels `runtime` + `direction` (input\|output), *"token accounting
    (Sympozium `agent.context.input_tokens`), best-effort per shim; **per-ticket** rollups aggregate on
    `work_item.id` and **per-user cost** rollups aggregate on `user.id` — both via exemplars/traces
    (§15/§16.5), never as a label."* **This story is the elaboration of that row.**
  - **§15 (CEO consumption requirement)** — *"per-ticket token rollups are derived in the backend by
    aggregating on `work_item.id` via exemplars/traces — deliberately **not** a metric label (cardinality law
    §1.2). A cost/pricing rollup would be a backend computation over this signal."*
  - **§16.5 "Per-user cost attribution"** — *"`user.id` is already on every `agent.tokens` exemplar (§16.1),
    so the backend rolls tokens up by `user.id` (and by `user.id × project`) and applies the pricing model to
    produce per-user / per-project cost. If a first-class cost **unit** is later wanted (currency, not
    tokens), that is the same backend rollup with a price table — a computation over this signal, not a new
    label."*
  - **§5.6 cardinality budget** — the enforced label allowlist. `runtime` and `direction` are **bounded enums
    → allowed labels**. `run.id`, `work_item.id`, `principal.id`, **`user.id`** are **forbidden as labels** —
    they ride as **exemplars / resource attributes** and are rolled up per-actor/per-ticket in the backend. A
    `user.id` label is an explicit build failure (13.6's lint; this story obeys it and *tests* it locally, AC5).
  - **§1.1 / §1.5 observe-not-implement + noop-on-unset** — the standing law that a metric **observes** and
    never implements behaviour; inherited from 13.1, with the OTLP endpoint unset the instrument is
    non-recording, zero series export, agent behaviour unchanged (AC2/noop). Turning metering on is operator
    config, not a redeploy.
  - **§7 semconv** — `ksquad.agent.tokens` aligns to `gen_ai.usage.input_tokens`/`output_tokens`; the exemplar
    attrs (`run.id`, `work_item.id`, `user.id`) that join a data point to its 13.1 span.
  - **§17.1 / §17.2** — the dashboard's token-consumption+trend panel is the **identical series read as a time
    range** (`rate()`/`increase()`), served through the metrics **query seam** — a query shape, **not** a new
    instrument; per-user/agent/Run stay exemplar rollups.
- **Architecture:** `docs/bmad/03-architecture.md` — §7 shim/A2A (token surfacing), §10.3 model endpoint
  (the `contextWindow` the §5.9 budget reads), §11 the BYO-subscription credential/principal model,
  §13 dashboard (r24), §17.2 metrics query seam (the dashboard → OTel handoff).
- **Depends on:**
  - **Story 13.1** (ISI-2233 — the OTel SDK wiring, noop-on-unset, and the durable Run trace + the
    `run.id`/`work_item.id`/`user.id` correlation dimensions these metrics attach **exemplars** to).
  - **Epic 5** (the shim token surfacing over A2A — the source of the best-effort usage this projects).
  - **Story 5.9** (ISI-2221 — the context-budget enforcement whose fit/truncation decision reads the model
    `contextWindow` + envelope size; this story proves that decision **never** reads the tokens metric).
  - **Epic 7 / §11** (the per-user Secret-ref credential model — the `principal`/`user.id` consumption is
    attributed to).
- **Blocks / is consumed by:** **8.8e** (ISI-2325 — the token-consumption+trend widget that renders this
  signal), **8.8a** (the dashboard read model / §17.2 query seam), **13.6** (cardinality lint — enforces the
  label allowlist this story obeys), **13.7** (collector + PII/secret redaction), **13.10** (ISI-2304 —
  per-user consumption flows through this metering spine unchanged with `user.id` as an exemplar).

## The projection model (authoritative — obs-plan §5.5 / §15 / §16.5)

A running agent's shim reports its token usage best-effort per turn. On each report, the meter records the
single §5.5 counter with the **two bounded labels** and attaches the unbounded identifiers as an **exemplar**.
Per-scope and cost numbers are **backend aggregations over those exemplars** — never a second store, never a
label.

| Event (source of truth) | Projected metric | Bounded label | Rides as exemplar (never a label) |
|---|---|---|---|
| shim reports **input** tokens for a turn | `ksquad.agent.tokens` `+= n` | `runtime`, `direction=input` | `run.id`, `work_item.id`, `user.id`/`principal.id` |
| shim reports **output** tokens for a turn | `ksquad.agent.tokens` `+= n` | `runtime`, `direction=output` | `run.id`, `work_item.id`, `user.id`/`principal.id` |
| shim reports **nothing** for a turn (best-effort gap) | **no advance** — absent, never a fabricated number | — | — |
| per-ticket consumption | **backend rollup** on `work_item.id` over exemplars | — | (the rollup key) |
| per-user consumption / cost | **backend rollup** on `user.id` (× price table for cost) | — | (the rollup key) |
| per-project / trend | `project` **resource attribute** federated; `rate()`/`increase()` over the same series (§17.1) | `runtime`/`direction` only | `project` as resource attr |

**Best-effort is a first-class property, not a bug.** Token counts are runtime-reported (OQ14): they are for
**legibility**, not the billing authority. A shim that fails to report a turn leaves the counter **unadvanced**
— the metering never invents a default to paper over the gap, because a fabricated number would masquerade as
authoritative consumption. Under-count honestly beats over-count confidently.

**The unbounded identifiers ride as exemplars, never labels.** `user.id` / `work_item.id` / `run.id` /
`principal.id` are attached to the data point as **exemplars** (joining it to the Run's 13.1 span, §4.3) — the
metric stays low-cardinality (label domain = a handful of `runtime` × `direction` values) while a specific
turn's consumption remains drillable back to its user, ticket, and trace. Putting `user.id` on the metric as a
*label* is the per-actor cardinality-explosion §5.6 forbids outright (§16.2 is explicit: `user.id` is unbounded
per-actor).

## The observe-not-enforce crux (authoritative — the load-bearing invariant, AC2)

A metering signal that is **read by an enforcement decision** stops being an observation and becomes part of
the agent-behaviour machinery — and the moment the exporter is off (or the metric is dropped), behaviour
silently changes. Concretely: if the §5.9 context-budget fit computes the remaining window by subtracting
**already-metered consumption read from the `ksquad.agent.tokens` counter**, then with the exporter unset the
counter is empty, the fit decision flips, and an envelope that would have been truncated now over-fills the
model window (or vice-versa) — a **behaviour regression caused by turning metering off.**

**The invariant:** the agent run outcome — the dispatch, and the §5.9 fit/truncation decision — is
**byte-for-byte identical whether the token metric is emitted or absent**. The §5.9 path reads only durable
inputs (the model `contextWindow` §10.3 + the assembled envelope size); the metric is a **pure projection
appended after the turn** and is **never** read back. This is the exact noop-neutrality discipline Story 13.1
makes for the tracer (AC4) and Story 13.2 makes for the coord path (AC2) — here extended to the consumption
path.

- **No-bespoke-accounting-path corollary (AC6):** because there is **one** signal, the dashboard's
  authoritative per-scope total **is** the §17.2 OTel rollup over that signal — not a second, private ledger.
  A parallel accounting store is a second write path that inevitably **drifts** from the metered truth (a
  dropped write, a double-count, a unit mismatch), and it re-introduces exactly the reconcile burden R6 exists
  to prevent. The dashboard reads the rollup; it does not keep its own books.

## Acceptance Criteria

**AC1 — the §5.5 signal exists, with exactly the §5.5 shape.**
Given running agents, When shims report usage, Then `ksquad.agent.tokens` is emitted as a **counter** with
**only** the two §5.5/§5.6 bounded labels `runtime` and `direction` (∈ `input`\|`output`), aligned to OTel
`gen_ai.usage.input_tokens`/`output_tokens` (§7); And it is the **only** consumption instrument — token
accounting is one signal, not a family of per-scope counters.

**AC2 — metering OBSERVES, it does not ENFORCE (the crux): the run outcome is identical with metering on/off.**
Given any agent turn and the §5.9 context-budget fit, When the turn runs with the OTLP exporter recording and
again with it unset, Then the run outcome — the dispatch and the §5.9 fit/truncation decision — is
**byte-for-byte identical**; And **no enforcement decision reads the tokens metric**: the §5.9 path reads only
the model `contextWindow` (§10.3) and the assembled envelope size, and the token emit is a pure projection
appended after the turn, never read back; And a design where the budget fit derives the remaining window from
the `ksquad.agent.tokens` counter — so that turning the exporter off flips a truncation decision — is a
**failure of the metering contract, not a cosmetic gap**.

**AC3 — faithful direction: input and output are distinct series, each derived from what the shim reported.**
Given a shim report of `input` and `output` tokens for a turn, When the metric is emitted, Then `direction` is
**derived from the actual direction** the shim reported — input tokens project `direction=input` and output
tokens project `direction=output`, **never** swapped or collapsed — so the input/output split is honest and a
per-direction query returns the real counts.

**AC4 — best-effort / runtime-reported honesty (OQ14): a silent shim advances nothing, the metric never fabricates.**
Given a turn for which the shim reports **no** usage (a best-effort gap), When the meter runs, Then the counter
**does not advance** for that turn — the metric records **absent**, never an invented default — because a
fabricated count would masquerade as authoritative consumption; And token counts are explicitly **best-effort
/ runtime-reported (legibility, not the billing authority)** — an under-count from a missed report is correct
behaviour, not an error to paper over.

**AC5 — per-principal + per-ticket attribution via exemplars, never labels.**
Given the token signal, When consumption is rolled up, Then **per-ticket** totals aggregate on `work_item.id`
and **per-user** totals (and per-user cost) aggregate on `user.id`/`principal.id` — **backend aggregations over
the exemplars/traces**, attributing consumption **per user/principal** (first-class under the BYO-subscription
model, §11); And `run.id`, `work_item.id`, `user.id`, `principal.id`, and `team`/`project` names are **never**
metric labels — they ride as **exemplars** (joining the data point to its 13.1 trace, §4.3) or resource
attributes; And adding one as a label is an explicit build failure (13.6 enforces; this story *obeys* and
asserts it locally) — while the low-cardinality metric **still** attributes to a specific principal/ticket
through the exemplar, so drill-down survives without cardinality explosion.

**AC6 — no bespoke accounting path: the dashboard total is the OTel rollup, not a private ledger.**
Given dashboard 8.8's consumption tile, When it shows a per-scope total, Then that total **is** the §17.2 OTel
rollup over `ksquad.agent.tokens` (and the trend is the identical series read as a time range, §17.1) — there
is **no second accounting store, no rollup datastore, and no bespoke accounting path** (R6); And a parallel
private ledger — a second write path that can silently drift from the metered truth — is **not** the
authoritative source and is a failure of this contract.

**AC7 — cost is a backend computation over the signal, not a new instrument.**
Given per-user / per-project cost, When it is computed, Then it is a **backend rollup over the token exemplars
× a configurable price table** (§16.5) — **not** a new emitted instrument and **not** a metric label; And with
**no price table configured** the rollup **degrades to tokens-only** (never a hard failure); And a first-class
currency **unit**, if ever wanted, is the **same** backend rollup with a price table — a computation over this
signal, not a new label or store.

**AC8 — noop-on-unset (inherited from 13.1): metering on/off is config, never an agent-behaviour change.**
Given the OTLP endpoint is **unset**, When agents run, Then the token instrument is **non-recording**, **zero
series are exported**, and — per AC2 — the run outcome is unchanged; turning consumption metering on is an
**operator config (set the endpoint), not a redeploy** and never alters what an agent does.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/token-metering-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same shape as the 13.2 coord-metrics check and the 13.1 correlation check), not a happy-path
demo. It models the shim-surfaced token signal (`ksquad.agent.tokens{runtime, direction}`), the §5.9
budget-fit decision, the backend exemplar rollups (per-user, per-ticket, cost × price table), and a bespoke
ledger, and proves the projection has teeth by driving each modelled mutation and asserting it is **detectably
wrong**. Token counts are deterministic, so "did metering leak onto the enforcement path?" is a pure identity
test — the truncation-decision sequence with the exporter off must equal the sequence with it on.

- **(AC1) the §5.5 shape.** Asserts the one required instrument is declared with exactly `{runtime,
  direction}` and every declared label is a bounded §5.6 enum key (none in the forbidden set).
- **(M2 — the crux, AC2) observe, not enforce.** Runs two turns with the exporter recording and again with it
  unset and asserts the **§5.9 fit-decision sequence is identical**. *Mutation-proven:* making the budget fit
  subtract already-metered tokens read from the `ksquad.agent.tokens` **series** (`enforce_via_metric`) flips
  a truncation decision when the exporter is off → the two sequences diverge → **RED**.
- **(M3, AC3) faithful direction.** input tokens project `direction=input`, output `direction=output`.
  *Mutation-proven:* swapping the direction label (`mislabel_direction`) makes a per-direction query return the
  wrong count → **RED**.
- **(M4, AC4) best-effort honesty.** A silent shim advances nothing; the metric total never exceeds the sum
  the shim actually reported. *Mutation-proven:* fabricating a default count for an unreported turn
  (`fabricate_missing`) pushes the metric above the reported truth → **RED** (invented billing data caught).
- **(M5, AC5) per-principal + per-ticket attribution.** The per-user and per-ticket rollups aggregate over the
  exemplar dimension. *Mutation-proven:* dropping the `run.id`/`work_item.id`/`user.id` exemplar
  (`drop_exemplar`) leaves the consumption un-attributable → **RED**.
- **(M6, AC5) cardinality.** The clean path emits **no** label key outside `{runtime, direction}`.
  *Mutation-proven:* adding `user.id` as a metric **label** (`label_user_id`) is caught by the cardinality
  guard → **RED** (the §5.6 forbidden-label law has teeth).
- **(M7, AC6) no bespoke accounting path.** The dashboard total equals the OTel rollup. *Mutation-proven:*
  sourcing it from a private ledger that silently misses a report (`bespoke_ledger`) drifts from the metered
  truth → **RED**.
- **(M8, AC7) cost is a backend rollup.** Cost = the token rollup × a price table, degrading to tokens-only
  with no table; the emitted instrument set stays `{ksquad.agent.tokens}`. *Mutation-proven:* emitting a
  distinct `ksquad.agent.cost` instrument (`cost_as_metric`) instead of a backend computation is caught →
  **RED**.

Exits non-zero if the run outcome differs between exporter on/off (metering leaked onto the §5.9 path), an
input/output direction is mislabelled, an unreported turn fabricates consumption, a rollup loses its
attribution exemplar, a forbidden identifier reaches a metric label, the dashboard sources a bespoke ledger
that drifts, or cost is emitted as its own instrument instead of a backend rollup. **The headline invariant is
mutation-checked:** routing the §5.9 budget fit through the tokens metric makes the metering-on and
metering-off outcomes diverge and turns the check **RED** — the "observe, not enforce" contract is falsifiable,
not aspirational.

## Out of scope (owned elsewhere)

- **The shim's token surfacing over A2A** (the source of the best-effort usage this projects) — **Epic 5**.
  This story projects what the shim reports; it does not change how the shim counts.
- **The §5.9 context-budget enforcement itself** (must-include-first, truncate-to-fit, fail-closed) — **Story
  5.9** (ISI-2221). This story proves that decision **never reads** the tokens metric; it does not implement
  budgeting.
- **The OTel SDK wiring, noop-on-unset providers, and the durable Run trace** the exemplars attach to —
  **Story 13.1** (ISI-2233). This story **joins to** that trace via exemplars.
- **The cardinality CI lint** (grep metric label keys vs the §5.6 allowlist; `user.id`≠label) — **Story 13.6**
  (this story **obeys** the law and asserts it locally; 13.6 **enforces** it at build time).
- **The collector pipeline + PII/secret redaction** (no username/email/token ever exported) — **Story 13.7**.
- **The dashboard consumption tile + trend + estimated-cost render** — **Story 8.8e** (ISI-2325) over the
  **8.8a** read model / §17.2 query seam. This story emits the signal 8.8e reads.
- **A first-class currency cost unit / the price table itself** — the console/FinOps owner (§16.5). This story
  proves cost is a backend rollup over the signal (× price table) and degrades to tokens-only; it does not own
  the pricing model.

This story ships the **§5.5 `ksquad.agent.tokens{runtime, direction}` consumption signal (best-effort,
shim-surfaced), the per-principal + per-ticket exemplar-rollup attribution (never a label), the
cost-as-backend-computation (× price table, degrades to tokens-only) contract, the no-bespoke-accounting-path
guarantee (the dashboard total IS the §17.2 OTel rollup), the observe-not-enforce neutrality (the §5.9 run
outcome is identical with metering on/off), the noop-on-unset behaviour inherited from 13.1, and the
differential falsification** — the honest, legible, observe-only consumption projection that lets a finance/ops
owner see token + cost usage per user / per ticket / per project in dashboard 8.8 without a second ledger and
without the metering ever becoming load-bearing for what an agent does.
