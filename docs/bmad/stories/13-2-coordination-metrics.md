# Story 13.2: Coordination metrics = the audit-spine projection — observe, never enforce

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE QUANTITATIVE PROJECTION OF THE §6.2 CONSISTENCY SPINE (obs-plan §5.1, epics row 13.2,
> NFR-REL / NFR-OBS).** The coordination record **is** the audit trail (arch §6.1); this story's instruments
> — `ksquad.coord.claim.{total,duration}`, `lease.renew.total{result}`, `lease.reclaim.total{trigger}`,
> `fence.epoch.increments` (+ the rest of the §5.1 table) — are the **rate/latency/SLO projection** of it.
> Every event they count is *also* a durable `audit_log`/`run_events` row that stays the forensic source of
> truth; the metrics never duplicate the audit *content* into labels. The load-bearing invariant is
> **"metrics OBSERVE, they do not implement enforcement"**: the §6.2 consistency outcome — the claim winner,
> the fence value, the renew accept/reject, the reclaim order — must be **byte-for-byte identical whether the
> metric emit is present or absent**, and no enforcement decision may ever read a metric. A design where the
> fence bump reads its value from a metric counter, or where a correctness signal (`stale_holder`, `reclaim`)
> is emitted but **not** wired to the concurrency alert, is a **correctness failure of the observability
> contract, not a cosmetic gap.** Read AC2 and AC4 literally.

## ⚠️ Scope pin — this story instruments, it does not enforce or invent (read first)

This story adds **zero** new coordination behaviour and **zero** new consistency rules. The claim
(SKIP-LOCKED pop + conditional fence CAS), the lease renew (guarded on `holder`), the crash-reclaim
(`ReclaimFenced`), the idempotent redrive, and the `lease_epoch` fence token are all **already built and
gate-proven** in the coordination spine (Story 2.1 schema / ISI-2191, Story 2.10 `pkg/coord` / ISI-2394,
Story 2.2–2.4 claim/renew/reclaim, chaos gate C1–C7). This story reads their **outcomes** and projects a
**bounded-cardinality metric** off each — nothing more. Enforcement lives in `pkg/coord`; observation lives
here. The one-line boundary: **the coordination record decides who holds the lease and what the fence is;
these metrics let an SRE prove, in prod, that the §6.2 model is holding — without ever changing what it
decides.**

| Concern | This story | Owned elsewhere |
|---|---|---|
| The §5.1 coordination instruments (`claim`/`lease.renew`/`lease.reclaim`/`fence.epoch.increments` + `workitem.state`/`blocked`/`append`/`contention.depth`), each a projection of a durable audit row | **✅ delivered** | — |
| Each metric's bounded label derived from the same outcome the audit row records (one source of truth) | **✅ delivered (AC3)** | — |
| `stale_holder` + `reclaim` wired to the §9 **page-grade** concurrency alert as correctness signals | **✅ delivered (AC4)** | The alert *rule/runbook* is authored with 13.7; this story guarantees the signals **exist and reach it** |
| Observe-not-enforce: the coord outcome is identical with metrics on/off; no decision reads a metric | **✅ the crux (AC2)** | — |
| Cardinality: `run.id`/`work_item.id`/`principal.id` ride as **exemplars**, never labels | **✅ delivered (AC5)** | The CI **lint** that greps labels vs the §5.6 allowlist — **Story 13.6** (this story *obeys*, 13.6 *enforces*) |
| The exemplar target the metrics link to (the Run trace / span) | consumed | **Story 13.1** (ISI-2233 — the durable-correlation spine this story joins to) |
| OTel SDK wiring + noop-on-unset + the collector export/redaction pipeline | consumed | **13.1** (wiring, AC4 noop) / **13.7** (collector + SLO alert rules) |
| The §6.2 enforcement itself (claim CAS, fence, reclaim order) | **read-only** | **Stories 2.1–2.4 / 2.10** (`pkg/coord`) |

## Story

As **an SRE operating the KSquad control plane**,
I want **the coordination record's audit spine (claim, lease renew, crash-reclaim, fence-epoch increments)
projected as bounded-cardinality OTel metrics — where `stale_holder` renewals and `reclaim` counts are
first-class correctness signals wired straight to the page-grade concurrency alert, every metric joins back
to its specific §6.2 event and Run trace through an exemplar rather than a high-cardinality label, and the
whole projection is provably OBSERVE-ONLY (turning it on or off changes nothing about who holds a lease or
what the fence is)**,
so that **I can prove in production that the §6.2 consistency model is actually holding — see contention on
the SKIP-LOCKED claim, catch a fenced-out stale holder or a crash-reclaim thrash the instant it starts, and
watch fence-epoch churn — without the observability layer ever becoming load-bearing for the correctness it
observes, and without a per-actor identifier ever exploding the metric cardinality.**

## Context & prerequisites (read first)

- **Observability plan:** `docs/bmad/04-observability-plan.md`
  - **§5.1 "Coordination record — the audit spine"** — the authoritative instrument table (names, types,
    bounded labels) this story implements verbatim. Note the standing sentence: *"The coordination record
    **is** the audit trail (§6.1); these metrics are the quantitative projection of it. Every event here is
    *also* a durable `audit_log`/`run_events` row… Do not duplicate the audit content into metric labels."*
    And the correctness clause: *"**Fencing observability is a correctness gate, not a nicety.**
    `stale_holder` renewals and `reclaim` counts are exactly the signals that prove the §6.2 consistency
    model holds in production; they feed the concurrency alert (§9) and are asserted by the concurrency
    harness (§10)."* **This story is the elaboration of §5.1.**
  - **§1.1 / §5.4 "observe, not implement"** — the standing law that a metric **observes** enforcement and
    never implements it (§5.4 memory: *"these metrics observe the enforcement, they do not implement it"*);
    this story makes that law load-bearing for the coordination path (AC2, the crux).
  - **§5.6 cardinality budget** — the enforced label allowlist. `result` (acquired\|contended\|empty /
    ok\|stale_holder), `trigger` (expiry\|sweeper), `state`, `kind`, `error_code` are **bounded enums →
    allowed labels**. `run.id`, `work_item.id`, `principal.id`, `team`/`project` names are **forbidden as
    labels** — they ride as **exemplars / resource attributes** and are rolled up in the backend. A `run.id`
    label is an explicit build failure (13.6's lint; this story obeys it and *tests* it locally, AC5).
  - **§9 alerting** — the **"Crash-reclaim health"** SLO (`coord.lease.reclaim.total`): *"reclaim rate 3×
    baseline (thrash) **or** `stale_holder` renewals > 0 sustained"* → **page (correctness)**. This story
    guarantees the two signals exist and reach that alert (AC4).
  - **§4.3 / §7 semconv attrs** — `ksquad.fence.epoch` (int, monotonic = `lease_epoch`/fence token, §6.2);
    the exemplar attrs (`run.id`, `work_item.id`) that join a data point to its 13.1 span.
  - **§1.5 noop-on-unset** — inherited from 13.1: with the OTLP endpoint unset the instruments are
    non-recording, zero series export, coord behaviour is unchanged (AC6). Turning observability on is an
    operator config, not a redeploy.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§6.1 the two records** — the coordination record *is* the audit trail; metrics project it, they are
    not a second record. §6.2 the consistency model (SKIP-LOCKED claim, lease + fence token, crash-reclaim);
    §6.4 idempotency.
- **Depends on:**
  - **Story 2.1** (ISI-2191 — the coordination schema; the `audit_log`/`run_events` rows and `lease_epoch`
    column these metrics project off) and **Story 2.10** (ISI-2394 — `pkg/coord`: `ClaimNext`/`Acquire`,
    `Renew`, `ReclaimFenced`, `RedriveClaim`, `DispatchOnce`, the gate-proven §6.2 statements this story
    instruments). The claim/renew/reclaim/redrive **outcomes** are the metric sources.
  - **Story 2.2–2.4** (ISI-2192/2193/2194 — claim / lease renewal / reclaim + fencing; the specific
    outcomes labelled `acquired\|contended\|empty`, `ok\|stale_holder`, `expiry\|sweeper`).
  - **Story 13.1** (ISI-2233 — the OTel SDK wiring, noop-on-unset, and the durable Run trace these metrics
    attach **exemplars** to; the metric's low-cardinality data point joins to the specific §6.2 event's span
    through that exemplar, §4.3).
- **Blocks / is consumed by:** **13.6** (cardinality lint — enforces the label allowlist this story obeys),
  **13.7** (collector + the §9 concurrency-alert rule / runbook that consumes `stale_holder` + `reclaim`),
  **13.9** (the coordination/backlog dashboard that reads `workitem.state`/`blocked`/`contention.depth`).

## The projection model (authoritative — obs-plan §5.1, arch §6)

Each §6.2 operation, on completion, appends its durable audit row **and** increments/records exactly one
bounded-cardinality metric derived from the **same outcome**. The metric is the projection; the row is the
source of truth.

| §6.2 operation (source of truth) | Durable row | Projected metric | Bounded label (derived from the outcome) |
|---|---|---|---|
| `Acquire` — SKIP-LOCKED pop + fence CAS | `run_events` claim row | `ksquad.coord.claim.{total,duration}` | `result` ∈ `acquired`\|`contended`\|`empty` |
| `Acquire` bumps `lease_epoch` | fence bump in the same commit | `ksquad.coord.fence.epoch.increments` | — (a spike = churn/thrash) |
| `Renew` — guarded on `holder ∧ fence ∧ live` | lease row | `ksquad.coord.lease.renew.total` | `result` ∈ `ok`\|`stale_holder` |
| `ReclaimFenced` — expiry sweep / crash-reclaim | reclaim row + fence bump | `ksquad.coord.lease.reclaim.total` | `trigger` ∈ `expiry`\|`sweeper` |
| `RedriveClaim` — idempotent no-op when still ours | *(no state change)* | **no fence increment** | — (a redrive-noop is **not** thrash) |
| append comment/artifact | `audit_log` append | `ksquad.coord.append.total` | `kind` ∈ `comment`\|`artifact` |
| work-item state / blocked / claimer race | *(read model)* | `workitem.state{state}`, `workitem.blocked{error_code}`, `claim.contention.depth` | bounded enums (§5.6) |

**The unbounded identifiers ride as exemplars, never labels.** `run.id` and `work_item.id` are attached to
the data point as an **exemplar** (joining it to the Run's 13.1 span, §4.3) — the metric stays low-cardinality
(the label domain is a handful of enum values) while a specific claim/reclaim event remains drillable back to
its trace and its audit row. Putting `run.id` on the metric as a *label* is the cardinality-explosion the
§5.6 allowlist forbids outright.

## The observe-not-enforce crux (authoritative — the load-bearing invariant, AC2)

A metric that is **read by an enforcement decision** stops being an observation and becomes part of the
consistency machinery — and the moment the exporter is off (or the metric is dropped), correctness silently
changes. Concretely: if the fence bump computes its next `lease_epoch` by reading the
`fence.epoch.increments` **counter** instead of the durable `lease_epoch` column, then with the exporter
unset the counter is empty, the epoch stalls, and the fencing CAS can no longer tell a stale holder from a
live one — a **correctness regression caused by turning observability off.**

**The invariant:** the coordination outcome — the claim winner, the fence value sequence, the renew
accept/reject, the reclaim order — is **byte-for-byte identical whether the metric emit is present or
absent**. The enforcement path reads only durable coordination state (`holder`, `lease_epoch`, `state`);
metrics are **pure projections appended after each decision** and are **never** read back. This is the exact
noop-neutrality discipline Story 13.1 makes for the tracer (AC4: Run behaviour identical with the exporter
on/off) — here extended to the correctness-critical coordination path.

- **First-class corollary (AC4):** because `stale_holder` and `reclaim` are *correctness* signals (they
  prove the §6.2 model is holding), they must be **wired to the page-grade concurrency alert** (§9). A
  design that emits them but leaves them ticket-grade, or disconnects them from the alert inputs, has
  demoted a correctness gate to a nicety — the exact anti-pattern §5.1 calls out.

## Acceptance Criteria

**AC1 — the §5.1 coordination instruments exist, with exactly the §5.1 shape, each a projection of a durable audit row.**
Given the coordination spine (Epic 2), When claims / leases / reclaims / fence bumps / appends run, Then
`ksquad.coord.claim.total{result}`, `ksquad.coord.claim.duration{result}`,
`ksquad.coord.lease.renew.total{result}`, `ksquad.coord.lease.reclaim.total{trigger}`,
`ksquad.coord.fence.epoch.increments`, `ksquad.coord.workitem.state{state}`,
`ksquad.coord.workitem.blocked{error_code}`, `ksquad.coord.append.total{kind}`, and
`ksquad.coord.claim.contention.depth` are emitted with the §5.1 types and **only** the §5.1 bounded labels;
And every one is the quantitative projection of an event that is **also** a durable `audit_log`/`run_events`
row — the metric is for rate/latency/SLO, the row is the forensic source of truth, and the audit *content*
is **not** duplicated into a label.

**AC2 — metrics OBSERVE, they do not ENFORCE (the crux): the coord outcome is identical with metrics on/off.**
Given any §6.2 operation, When it is executed with the OTLP exporter recording and again with it unset, Then
the coordination outcome — the claim winner, the `lease_epoch` sequence, the renew accept/reject, the
reclaim order — is **byte-for-byte identical**; And **no enforcement decision reads a metric**: the
enforcement path reads only durable coordination state (`holder`, `lease_epoch`, `state`), and metric emits
are pure projections appended after the decision and never read back; And a design where the fence bump (or
any CAS) derives its value from a metric counter — so that turning the exporter off stalls the epoch and
breaks fencing — is a **correctness failure of the observability contract, not a cosmetic gap**.

**AC3 — faithful projection: each bounded label is derived from the same outcome the audit row records.**
Given a §6.2 operation and its durable row, When the metric is emitted, Then its label value is **derived
from that same outcome** (one source of truth): a `Renew` rejected by the `holder` guard (a fenced-out /
expired non-holder) projects `result=stale_holder` and **never** a mislabelled `result=ok`; an `Acquire`
projects `acquired`\|`contended`\|`empty` matching the actual claim result; a `ReclaimFenced` projects
`trigger=expiry`\|`sweeper` matching the sweep source; And `fence.epoch.increments` increments **exactly once
per real `lease_epoch` bump** (Acquire / ReclaimFenced) and **not** on an idempotent `RedriveClaim` no-op
(still ours → no bump → no phantom-thrash signal).

**AC4 — `stale_holder` + `reclaim` are wired to the §9 page-grade concurrency alert as correctness signals.**
Given the `lease.renew.total{result=stale_holder}` and `lease.reclaim.total{trigger}` series, When
`stale_holder` renewals are sustained above zero **or** the reclaim rate exceeds the §9 thrash multiple (3×
baseline), Then the **page-grade** concurrency-alert condition (§9 "Crash-reclaim health") fires on them;
And these two are treated as **first-class correctness signals**, not nice-to-haves — a design that emits
them but leaves them ticket-grade or disconnects them from the alert inputs has demoted a §6.2 correctness
gate to a nicety, the exact anti-pattern §5.1 forbids.

**AC5 — cardinality discipline: forbidden identifiers ride as exemplars, never as metric labels.**
Given any coordination metric, When it is emitted, Then its label **keys** are drawn **only** from the §5.6
bounded allowlist (`result`, `trigger`, `state`, `kind`, `error_code`); And `run.id`, `work_item.id`,
`principal.id`, and `team`/`project` names are **never** metric labels — they ride as **exemplars** (joining
the data point to the specific §6.2 event's Run trace, 13.1 / §4.3) or as resource attributes, and are
rolled up per-actor in the backend; And adding one as a label is an explicit build failure (13.6 enforces;
this story *obeys* and asserts it locally) — while the low-cardinality metric **still joins** to its specific
event and audit row through the exemplar, so drill-down survives without cardinality explosion.

**AC6 — noop-on-unset (inherited from 13.1): observability on/off is config, never a coord-behaviour change.**
Given the OTLP endpoint is **unset**, When the coordination spine runs, Then the instruments are
**non-recording**, **zero series are exported**, and — per AC2 — the coordination outcome is unchanged;
turning coordination observability on is an **operator config (set the endpoint), not a redeploy** and never
alters who holds a lease or what the fence is.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/coord-metrics-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same shape as the 13.1 correlation check and the 2.10 coord-spine chaos gate), not a
happy-path demo. It models the §6.2 spine (SKIP-LOCKED `Acquire` + fence CAS, `Renew` guarded on the holder,
`ReclaimFenced`, idempotent `RedriveClaim`, monotonic `lease_epoch`) instrumented with a metric sink, and
proves the projection has teeth by driving each modelled mutation and asserting it is **detectably wrong**.
Fence epochs are a deterministic monotonic counter, so "did a metric leak onto the enforcement path?" is a
pure identity test — the epoch sequence with the exporter off must equal the sequence with it on.

- **(AC1) the §5.1 shape.** Asserts every required instrument is declared and every declared label is a
  bounded §5.6 enum key (none in the forbidden set).
- **(M2 — the crux, AC2) observe, not enforce.** Runs the spine with the exporter recording and again with
  it unset and asserts the **fence-epoch sequence is identical**. *Mutation-proven:* making the fence bump
  read its value from the `fence.epoch.increments` **metric series** (`enforce_via_metric`) stalls the epoch
  when the exporter is off → the two sequences diverge → the check turns **RED**. The observe-not-enforce
  invariant is falsifiable, not decorative.
- **(M3, AC3) faithful renew projection.** A non-holder `Renew` is enforcement-rejected **and** projected as
  `result=stale_holder`. *Mutation-proven:* mislabelling it `result=ok` (`mislabel_stale`) is detected as a
  divergence between the enforced outcome and the metric label → **RED** (the fencing signal is silently
  lost).
- **(M4, AC3) fence counts real bumps only.** An idempotent `RedriveClaim` (still ours) does **not**
  increment `fence.epoch.increments`. *Mutation-proven:* incrementing on the redrive-noop
  (`count_redrive_fence`) is detected → **RED** (a phantom-thrash false alert would otherwise be invisible).
- **(M5, AC4) alert wiring.** Sustained `stale_holder` + a reclaim rate ≥ 3× baseline fire the §9
  page-grade concurrency alert. *Mutation-proven:* disconnecting `stale_holder` (or `reclaim`) from the
  alert inputs drops it from the page → **RED** (a correctness signal demoted to a nicety).
- **(M6, AC5) cardinality.** The clean path emits **no** label key outside the §5.6 allowlist.
  *Mutation-proven:* adding `run.id` as a metric **label** (`label_run_id`) is caught by the cardinality
  guard → **RED** (the forbidden-label law has teeth).
- **(M7, AC5) exemplar join.** The low-cardinality metric still carries an **exemplar** with `run.id` that
  joins it to the specific §6.2 event's 13.1 trace. *Mutation-proven:* dropping the exemplar
  (`drop_exemplar`) leaves the metric un-joinable → **RED**.

Exits non-zero if the coordination outcome differs between exporter on/off (a metric leaked onto the
enforcement path), a fenced-out renewal is mislabelled `ok`, a redrive-noop fabricates a fence increment,
`stale_holder`/`reclaim` fail to reach the page-grade alert, a forbidden identifier reaches a metric label,
or the low-cardinality metric loses its trace-join exemplar. **The headline invariant is mutation-checked:**
routing the fence bump through the metric series makes the metrics-on and metrics-off outcomes diverge and
turns the check **RED** — the "observe, not enforce" contract is falsifiable, not aspirational.

## Out of scope (owned elsewhere)

- **The §6.2 enforcement itself** (SKIP-LOCKED claim CAS, lease renewal guard, `ReclaimFenced` order, fence
  token) — **Stories 2.1–2.4 / 2.10** (`pkg/coord`). This story **reads their outcomes**; it does not
  implement or change consistency.
- **The OTel SDK wiring, noop-on-unset providers, and the durable Run trace** the exemplars attach to —
  **Story 13.1** (ISI-2233). This story **joins to** that trace via exemplars; it does not build the tracer.
- **The cardinality CI lint** (grep metric label keys vs the §5.6 allowlist; `run.id`≠label) — **Story 13.6**
  (this story **obeys** the law and asserts it locally; 13.6 **enforces** it at build time).
- **The collector pipeline, PII/secret redaction, and the authored §9 concurrency-alert rule + runbook** —
  **Story 13.7**. This story guarantees the `stale_holder`/`reclaim` **signals exist and reach the alert**
  (AC4); 13.7 authors the alert rule and the export path.
- **The coordination/backlog dashboard** that renders `workitem.state`/`blocked`/`contention.depth` —
  **Story 13.9** (reads the instruments this story emits).
- **The concurrency harness** that asserts these signals under crash injection — **Story 2.7 / Epic 14.2**
  (the L2 gate); this story emits the signals that harness asserts on.

This story ships the **§5.1 coordination instruments (claim / lease.renew / lease.reclaim /
fence.epoch.increments + the workitem/append/contention projections), the faithful-projection contract
(each bounded label derived from the audit row's outcome), the `stale_holder`+`reclaim`→page-grade-alert
wiring, the exemplar-not-label cardinality discipline, the noop-on-unset neutrality inherited from 13.1, and
the differential falsification** — the quantitative, observe-only projection that lets an SRE prove the §6.2
consistency model is holding in production without the observability layer ever becoming load-bearing for
the correctness it observes.
