# Story 5.9: Context-injection contract + model-window token budget — the fit-or-fail-closed seam

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE SHIM-SIDE INJECTION SEAM THAT MAKES Story-3.6'S ENVELOPE ACTUALLY FIT THE MODEL
> (arch §8.5(3), §10.1/§10.3, ADR-028).** Story 3.6 (the Context Assembler) *assembles* a
> **provenance-tiered envelope** — the right elements, each stamped with its trust tier, snapshotted on
> the Run. But 3.6 stops at "the right content in the right tiers"; it explicitly **defers token
> budgeting to this story** (epic 3.6 note: *"Token budgeting = Epic 5.9"*). This story is the seam where
> that tiered envelope crosses the **shim (§10.1)** into the runtime's A2A system/context input **and must
> physically fit the resolved model's `contextWindow`** — Claude ~200K vs a BYO-Ollama ~8K local model
> (§10.3). The load-bearing invariant is **"must-include is the task itself — it is placed first and is
> never truncated to make room; best-effort tiers are summarized/truncated lowest-priority-first, and if
> the task alone will not fit, the Run FAILS CLOSED — it never silently ships a mangled task to a
> too-small model."** A budget that proportionally shaves every tier (including the acceptance criteria)
> to hit the window is a **correctness failure, not a UX rough edge**: the agent then works a *different,
> silently-truncated task* and nobody knows. Read AC1 and AC3 literally.

## ⚠️ Scope reconciliation — 5.9 vs 3.6 (read first, they compose on one envelope)

Story 3.6 (ISI, Context Assembler) and this story both touch "context injection," and arch §8.5 discusses
them as one flow. That is not duplication — they own **two disjoint halves of the same envelope**, split
exactly where the epic splits them (3.6 note: *"Token budgeting = Epic 5.9"*; 5.9 row: *"Pairs with the
injection seam (5.4)"*):

| Concern | Owned by | This story adds |
|---|---|---|
| **Gathering** the elements (work item/AC/comments, project meta, goals, scoped memory recall, linked artifacts) | **Story 3.6** | — (consumed as the input envelope, not re-gathered) |
| **Trust-tiering** each element (*authoritative* / *untrusted-recall* / *untrusted-external*, F16/§7.3) | **Story 3.6** | — (consumed; this story **preserves** the tiers across the wire, §D) |
| **Snapshotting** the resolved envelope on the Run (work-item rev, goal rev, memory doc-ids) for audit + re-entrant reuse (§6.4) | **Story 3.6** | — (consumed; this story is **deterministic over the snapshot** so a resume re-injects identically, §D) |
| **Resolving the effective per-tier BUDGET** (per-runtime default → per-Agent `contextBudgetOverride`), and **clamping it by the model `contextWindow`** | **THIS STORY (5.9)** | the budget-resolution + clamp (§B) |
| **Fitting** the tiered envelope to the resolved budget: must-include placed first & never truncated; best-effort summarized/truncated **lowest-priority-first** | **THIS STORY (5.9)** | the priority-ordered fit algorithm (§C) |
| **Fail-closed** when must-include alone exceeds the window (too-small model) — a clear Run condition, never silent task truncation | **THIS STORY (5.9)** | the fail-closed gate (§C, AC3) |
| **Delivering** the fitted envelope through the shim as the A2A system/context input, **tiers preserved on the wire** | **THIS STORY (5.9)** | the injection contract (§D), pairing the §5.4 credential-injection seam |
| Where `contextWindow` comes from (Agent Card capability, model-keyed) | **Story 5.2 / 1.2** (Agent Card gen from `Agent` CRD + resolved `AgentRuntime`/model) | — (consumed as a capability read, §B) |

**One-line boundary:** 3.6 answered *"what context should this agent see, and how is each piece framed
so untrusted text can't smuggle commands?"* This story answers *"given that tiered envelope and the
resolved model's real context window, how does it get delivered to the runtime so the task is always
intact and the whole thing always fits — or the Run fails loud instead of quietly working a truncated
task?"* — it takes the envelope in, resolves+clamps the budget, fits it priority-first, and hands it to
the shim with the trust tiers still legible.

## Story

As **the shim + the Run reconciler's injection step (§10.1, the runtime-facing half of the context
seam)**, I want **to deliver Story 3.6's resolved provenance-tiered envelope to the runtime as its A2A
system/context input under a priority-ordered token budget that is keyed to the resolved model's real
`contextWindow` (Agent Card capability, §10.1/§10.3) — placing must-include (work item + acceptance
criteria + goals) first and never truncating it, summarizing/truncating best-effort tiers (memory recall,
artifacts) lowest-priority-first to fit, failing the Run closed with a clear condition if must-include
alone exceeds the window, resolving the budget per-runtime-default then per-Agent override and clamping it
by the physical window, and preserving each element's trust tier across the wire**,
so that **every agent starts with a context that (a) always contains the *complete, untruncated* task,
(b) always physically fits the model it will actually run on (a ~200K Claude and a ~8K local Ollama get
different, correct budgets on the same project), (c) never silently ships a mangled task to a too-small
model (it fails loud instead), and (d) preserves the F16 trust framing to the runtime so injected recall
stays reference and never becomes commands — closing the FR-D / §8.5(3) token-budget half of the
context-injection guarantee that Story 3.6 assembled but did not fit.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-D1…D5** (the runtime/shim seam, capability negotiation, Agent
  Card), **FR-E** (memory recall — the best-effort tier this story budgets), the context-injection +
  handoff requirement (CEO/CTO 2026-08-11). **NFR-SEC** (F16 — untrusted content must not smuggle
  instructions; this story keeps the tiers legible to the runtime so recall stays reference).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§8.5(3) "Token budget is keyed to the resolved MODEL window, not the runtime CLI"** — *"the context
    window is a property of the **model endpoint** … so `contextWindow` is declared as a capability on the
    Agent Card (§10.1) and the Assembler enforces a **priority-ordered budget**: must-include (work item +
    acceptance criteria + goals) is placed first and **never truncated**; best-effort tiers (memory recall
    K, artifacts L) are summarized/truncated to fit, lowest-priority first. If must-include alone exceeds
    the window … the Run **fails closed** with a clear condition — never silent truncation of the task
    itself."* **This story's whole spec is the elaboration of that paragraph**, delivered at the shim
    seam. (Arch attributes the enforcement to "the Assembler" as one flow; the epic splits assembly=3.6
    from budgeting=5.9 — this story owns the budgeting half.)
  - **§8.5 hierarchical budget** — *"resolution order is **Project default → Agent override → Run
    dynamic**, and the whole thing is **clamped by the resolved model `contextWindow`** (§10.1) —
    configuration can shrink the budget but never exceed the physical window; a `contextBudgetOverride`
    above the model window is a **fail-closed validation error**, not a silent overflow."* AC2/AC4's teeth
    live in that clause: the override is **shrink-only**; over-window config is rejected, not obeyed.
  - **§8.5(2) provenance tiers (the F16 crux)** — the envelope is *"**not a flat prompt blob**"*; every
    element carries a trust tier so *"a malicious source cannot smuggle instructions."* This story is the
    place the envelope becomes wire bytes; **flattening the tiers into one prompt blob at injection would
    re-open the exact vector 3.6's tiering closed** — so the injection contract (§D) preserves the tiers.
  - **§10.1 "Shim placement & contract"** — the shim *"terminates A2A southbound … and translates to the
    runtime's native invocation … as the A2A task's system/context input."* The **Agent Card is generated
    from the `Agent` CRD + resolved `AgentRuntime`** and advertises **capability flags** — `contextWindow`
    is read from the card here as the hard budget ceiling. Capability gaps are declared, never special-
    cased: a runtime that summarizes natively vs one that needs pre-truncation is a card capability.
  - **§10.3 "Model-provider seam"** — the model window is **model-keyed, not CLI-keyed**: a runtime
    advertising `byoModelEndpoint` pointed at an ~8K Ollama gets an ~8K budget; the same runtime on a
    frontier API gets ~200K. `contextWindow` follows the **resolved model endpoint**, so the budget is
    re-resolved when the model is (ties to the 5.11 mid-Run fallback switch — the fallback's own window
    is honored, AC5).
  - **§5.1 CRDs (r28)** — `Project.contextBudget` (per-tier default allocations), `Agent
    .contextBudgetOverride` (optional, shrink-only), and the Agent Card's `contextWindow` capability
    (from the resolved model, Story 1.2/5.2). This story **reads** these; it does not add CRD fields
    (Story 1.2 owns shape) and does not assemble the envelope (3.6 does).
  - **§6.4 re-entrancy + §6.5 snapshot/audit** — the resolved envelope is snapshotted on the Run (3.6);
    a re-entrant resume **reuses the snapshot instead of re-querying**. This story's fit must therefore be
    **deterministic over `(envelope snapshot, contextWindow, resolved budget)`** so a resumed Run
    re-injects *identical* context (AC6). The injected result is auditable — "what did the agent actually
    see?" is answerable from the fitted envelope, not reconstructed.
- **Depends on:**
  - **Story 3.6** (Context Assembler — the provenance-tiered, snapshotted envelope this story fits and
    injects). Hard dependency: 5.9 is the consumer of 3.6's output; it does not gather or tier.
  - **Story 5.2 / 1.2** (Agent Card generation from `Agent` CRD + resolved `AgentRuntime`/model — the
    `contextWindow` capability + `Agent.contextBudgetOverride` this story reads). `contextWindow` is
    model-keyed (§10.3).
  - **Story 5.4** (the credential-injection contract — the sibling injection seam; this story rides the
    same shim→runtime A2A system/context path, adding the *content* budget where 5.4 adds the *credential*
    mapping). "Pairs with the injection seam (5.4)" (5.9 row).
  - **Story 6.6** (scoped memory recall — the *untrusted-recall* best-effort tier this story budgets and,
    when over-budget, summarizes/drops lowest-relevance-first).
- **Blocks / is consumed by:** **Story 5.5** (the OpenClaw + Hermes shims that carry this injection
  contract), **Story 5.11 / ISI-2297/2296** (mid-Run fallback model switch — re-resolves the budget to
  the fallback's own window, AC5), **Epic 13** (`ksquad.agent.tokens` metering observes the injected
  budget; not implemented here).

## The injection contract & the model window (authoritative — §A)

The resolved envelope (3.6) is a **priority-ordered list of tiered elements**, not a blob. Each element
carries `{tier, priority, content, provenance}` where `tier ∈ {authoritative, untrusted-recall,
untrusted-external}` (§8.5(2)) and `priority` orders eviction. The **budget ceiling is the resolved
model's `contextWindow`**, read from the Agent Card capability (§10.1) — a property of the **model
endpoint** (§10.3), *not* the runtime CLI. The two must-hold facts:

- **`contextWindow` is model-keyed.** The same OpenClaw runtime advertises ~200K on a frontier API and
  ~8K when its Agent points at a local Ollama (§10.3). Budgeting against the *CLI's* nominal limit instead
  of the *resolved model's* window would over-fill the small model and under-fill the large one — the
  §8.5(3) mistake this story exists to not make.
- **The tiers are the injection contract, not decoration.** The shim delivers the fitted envelope as the
  A2A system/context input **with the tier framing preserved** so the runtime frames *authoritative* as
  the task and *untrusted-\** as reference material (§8.5(2)/F16). Flattening to one prompt string at the
  wire re-opens the prompt-injection vector 3.6 closed (§D).

## The budget resolution & clamp (authoritative — §B, drives §8.5 hierarchical)

The effective budget is resolved in layers and then **clamped by the physical window** — configuration
can only *shrink* the budget, never grow it past what the model can hold:

1. **Per-runtime / model default.** The resolved model endpoint carries a default per-tier allocation
   (the "per-runtime-defaulted" of the 5.9 AC) — a small local model defaults to a tight budget, a
   frontier model to a generous one. (Where a `Project.contextBudget` default is set, §8.5, it feeds this
   layer for every agent on the project.)
2. **Per-Agent override.** `Agent.contextBudgetOverride` (§5.1) lets a Claude-backed agent take a ~200K
   allocation while a BYO-Ollama agent takes ~8K on the same project — **overridable per Agent** (the 5.9
   AC).
3. **Clamp by `contextWindow` (the fail-closed rule, §8.5).** The resolved budget is
   `min(resolved_allocation, contextWindow)` per what the model physically holds. **A
   `contextBudgetOverride` that exceeds the model's `contextWindow` is a fail-closed validation error, not
   a silent overflow** (AC4) — the operator gets told the override is impossible for this model, rather
   than the model silently truncating on its own opaque terms.

Resolution is **deterministic** given `(model contextWindow, Project default, Agent override)`; the same
inputs always resolve the same budget, so a resumed Run (§6.4) re-injects identically (AC6).

## The priority-ordered fit (authoritative — §C, drives §8.5(3))

Given the resolved budget and the tiered envelope, the fit is a **single deterministic pass** that never
touches the task:

1. **Place must-include first, never truncate it.** The **must-include set = the *authoritative* tier**:
   work item (description + acceptance criteria + comment history that is task-defining), project goals,
   project metadata required to act. It is placed first and consumes budget **verbatim** — it is *never*
   summarized or truncated to make room. It is the task; a truncated task is a *different* task.
2. **Fail closed if must-include alone exceeds the window.** If `size(must-include) > contextWindow`
   (a too-small model — e.g. a large arch-doc-heavy task on an ~8K Ollama), the fit **does not proceed**:
   the Run transitions to a **fail-closed condition** (`reason=ContextWindowExceeded`) with an operator-
   legible message ("task requires N tokens, model window is M"). It **never** truncates the task to
   "make it fit" — silent task truncation is the one outcome §8.5(3) forbids. (Remediation is operator-
   side: a bigger model / a per-Agent override to a larger-window endpoint, or splitting the work item —
   none of which this story silently does on the agent's behalf.)
3. **Fill best-effort tiers, lowest-priority-first eviction.** With the remaining budget
   (`contextWindow − size(must-include)`), add the best-effort tiers — *untrusted-recall* (memory, ranked
   by relevance) then *untrusted-external* (artifacts) — **highest-priority element first**. When the
   next element does not fit, **summarize it** (if the runtime/summarizer supports it) or **drop it**, and
   continue; eviction proceeds **lowest-priority-first** so the highest-value recall/artifact survives and
   the lowest-value is the first cut. Best-effort tiers degrade gracefully; the task never degrades.
4. **Deliver via the shim, tiers preserved (§D).** The fitted, tier-labeled envelope is handed to the
   shim as the A2A system/context input **with the trust tiers intact** on the wire.

The fit is **total and deterministic**: for any envelope + window it yields either a fitted envelope
(task intact, best-effort trimmed to fit) or a fail-closed condition — never a silently-truncated task,
never an over-window payload handed to the model.

## The injection contract preserves the trust tiers (authoritative — §D, drives §8.5(2)/F16)

The shim delivers the fitted envelope as the A2A system/context input in a form that **keeps each
element's trust tier legible to the runtime** — *authoritative* framed as the task/instructions,
*untrusted-recall* and *untrusted-external* framed as reference material carried with their provenance
(`{author, written_at, scope, trust}`, §7.3). This is the **injection contract**, and it is load-bearing:
**flattening the tiers into a single undifferentiated prompt string at the wire re-opens the exact
prompt-injection vector 3.6's tiering closed** — a malicious memory note or a synced README could then
present as an instruction. Preserving the tiers to the runtime is what makes budgeted recall safe to
inject; it is not cosmetic. (Runtimes negotiate *how* they consume tiers as an Agent Card capability,
§10.1 — native system/user/context roles vs delimited sections — but every path preserves the framing;
the core never emits a flat blob.)

## Acceptance Criteria

**AC1 — must-include (the task) is placed first and is NEVER truncated to fit; best-effort tiers are
summarized/truncated lowest-priority-first.**
Given a resolved tiered envelope (3.6) and a `contextWindow`, When the shim fits it, Then the
**must-include set** (authoritative tier: work item + acceptance criteria + goals) is placed **first** and
consumes budget **verbatim — never summarized or truncated** to make room; and the **best-effort tiers**
(untrusted-recall memory K, then untrusted-external artifacts L) are added with the remaining budget,
**summarized/truncated lowest-priority-first** when they don't fit (highest-value recall/artifact
survives, lowest-value is cut first). A design that proportionally shrinks *all* tiers (mangling the
acceptance criteria to hit the window) is a correctness failure (AC3).

**AC2 — the budget is keyed to the resolved MODEL window (model-keyed, not CLI-keyed) and resolved
per-runtime-default then per-Agent override.**
Given an Agent Card advertising `contextWindow` as a capability of the **resolved model endpoint** (§10.1
/§10.3 — Claude ~200K vs BYO-Ollama ~8K), When the budget resolves, Then the ceiling is that **model's**
window (the *same* runtime on two different model endpoints gets two different budgets), and the per-tier
allocation resolves **per-runtime/model default → per-Agent `contextBudgetOverride`** (§8.5 hierarchical).
The budget is **never** keyed to the runtime CLI's nominal limit.

**AC3 — if must-include alone exceeds the window, the Run FAILS CLOSED with a clear condition — never
silent truncation of the task.**
Given a must-include set whose size exceeds the resolved `contextWindow` (a too-small model), When the fit
runs, Then it **does not truncate the task**: the Run transitions to a **fail-closed condition**
(`reason=ContextWindowExceeded`) with an operator-legible message (required tokens vs model window), and
**no context is injected**. It **never** silently drops/summarizes acceptance criteria to make the task
"fit." Silent task truncation — the agent then working a *different, mangled* task with no signal — is the
one forbidden outcome (§8.5(3)).

**AC4 — configuration can shrink the budget but NEVER exceed the physical window; an over-window override
is a fail-closed validation error.**
Given an `Agent.contextBudgetOverride` (or Project default) larger than the resolved model's
`contextWindow`, When the budget resolves, Then the resolution is **clamped**: the effective budget is
`min(configured, contextWindow)` for shrink-only config, and an override that *exceeds* the window is a
**fail-closed validation error** (rejected at resolve time with a clear message), **not** a silent
overflow handed to the model to truncate on its own opaque terms. Configuration can shrink, never grow
past the physical window.

**AC5 — the fitted envelope is delivered through the shim as A2A system/context with the trust tiers
preserved on the wire (the injection contract).**
Given a fitted envelope, When the shim injects it, Then it is delivered as the runtime's A2A system/context
input with **each element's trust tier legible** — *authoritative* framed as the task, *untrusted-recall*
/ *untrusted-external* framed as provenance-carrying reference material (§7.3/§8.5(2)) — and it is **never
flattened into a single undifferentiated prompt blob** (which would re-open the F16 prompt-injection
vector). And when the resolved **model changes mid-Run** (the 5.11 fallback switch), the budget is
**re-resolved against the fallback model's own `contextWindow`** and the injection re-fitted — the window
follows the model (§10.3), never the CLI.

**AC6 — the fit is deterministic over the snapshot; a resumed Run re-injects identical context.**
Given a Run whose resolved envelope is snapshotted (3.6, §6.4/§6.5), When the Run is re-entrant/resumed,
Then the fit re-runs over the **snapshot** (not a fresh query) and, being **deterministic over `(envelope
snapshot, contextWindow, resolved budget)`**, yields the **identical injected context** — the resumed
agent sees exactly what the original saw (reproducibility + audit). And the injected result is
auditable — "what did the agent actually see?" is answered from the fitted envelope, not reconstructed.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/run-context-budget-check.py` — stdlib-only, `python3` it directly. A
**differential** falsification (same shape as the Story 3.1/3.2/2.4 checks), not a happy-path demo. It
contrasts a **NAIVE budgeter that proportionally shrinks every tier to hit the window** (and thereby
mangles the task, or silently truncates instead of failing closed) against the **§C priority-ordered
fail-closed budgeter** that does not:

- **(A) NAIVE proportional budgeter — shaves the task to fit.** Scales *all* tiers (including
  must-include) by `window / total` so the payload fits the window. On a small window it **truncates the
  acceptance criteria**; the check asserts the naive design **detectably mangles the task** (the injected
  must-include ≠ the source must-include). If (A) ever stops breaking, the check fails **loud** — the
  harness lost its detecting power.
- **(F1) must-include-never-truncated teeth (AC1).** Drives a window smaller than
  `must-include + best-effort` but larger than `must-include` alone, and asserts the §C fit ships the
  **must-include verbatim** (byte-identical to source) while trimming best-effort. *Mutation-proven:*
  deleting the "place must-include verbatim, budget only the remainder" guard (letting must-include enter
  the proportional/greedy trim) turns the check **RED** — the load-bearing "task is never truncated"
  invariant now has teeth.
- **(F2) fail-closed gate teeth (AC3).** Drives `size(must-include) > contextWindow` (a too-small model)
  and asserts the fit returns a **fail-closed** result (`ContextWindowExceeded`, zero context injected),
  **not** a truncated-task injection. A differential twin runs the NAIVE truncate-to-fit path and asserts
  it produces a Run that *ran on a silently-truncated task* (undetectable corruption). *Mutation-proven:*
  deleting the `if size(must_include) > window: return fail_closed` gate turns the check **RED**.
- **(B) §C PRIORITY-ORDERED FIT — lowest-priority-first eviction.** With must-include placed and the
  remainder budgeted, asserts best-effort tiers are added highest-priority-first and evicted
  **lowest-priority-first**: the highest-value memory recall survives, the lowest-value artifact is cut
  first. The check asserts the surviving set is exactly the highest-priority prefix that fits, and that a
  higher-priority element is **never** dropped while a lower-priority one is kept.
- **(F3) clamp / over-window override teeth (AC4).** Sets `contextBudgetOverride = 300K` on a model whose
  `contextWindow = 200K` and asserts the resolve is a **fail-closed validation error** (not a 300K payload
  handed to the model); and sets a *shrink* override (`50K` on a 200K model) and asserts the budget is
  clamped **down** to 50K (config shrinks, never grows). *Mutation-proven:* replacing the clamp with the
  raw configured value turns the over-window case **RED** (a 300K payload would be injected to a 200K
  model).
- **(F4) model-keyed window teeth (AC2).** Runs the *same* runtime/envelope against two resolved model
  endpoints — a ~200K frontier model and an ~8K local Ollama — and asserts the two produce **different
  budgets** (the small model trims best-effort the large one keeps), proving the window follows the
  **model**, not the CLI. A twin that keys off a fixed CLI limit injects an over-window payload to the 8K
  model → the check flags it.
- **(F5) trust-tiers-preserved teeth (AC5, F16).** Asserts every element in the fitted, injected envelope
  still carries its `{tier, provenance}` and that must-include is framed *authoritative* while recall/
  artifacts are framed *untrusted-\**. *Mutation-proven:* a `flatten_to_prompt_blob` injection that
  concatenates all tiers into one string turns the check **RED** — the F16 framing must survive the wire.
- **(F6) determinism / snapshot-reuse teeth (AC6).** Runs the fit twice over the same snapshot in two
  *fresh* budgeter instances (simulating an original Run and a resumed Run) and asserts the injected
  context is **byte-identical** — the fit is deterministic over `(snapshot, window, budget)`. A twin that
  re-queries recall (non-deterministic order) diverges → the check flags it.
- **(F7) mid-Run model switch re-resolves the window (AC5/§10.3).** Switches the resolved model from the
  ~200K primary to an ~8K fallback mid-Run and asserts the budget is **re-resolved against the fallback's
  window** (best-effort re-trimmed to fit 8K) — the window follows the model, never the CLI or the
  original.

Exits non-zero if the budgeter truncates must-include, silently truncates the task instead of failing
closed, evicts a higher-priority best-effort element while keeping a lower one, hands an over-window
payload to the model, keys the window off the CLI instead of the model, flattens the trust tiers, or is
non-deterministic over the snapshot. **The two headline invariants are mutation-checked:** deleting the
must-include-verbatim guard (F1) or the fail-closed gate (F2) each turns the check **RED** — the §8.5(3)
"task first, never truncated, fail-closed-or-fit" contract has teeth.

## Out of scope (owned elsewhere)

- **Assembling + trust-tiering + snapshotting the envelope** (Story 3.6 — consumed as input, not
  re-gathered), **the scoped memory recall query** (Story 6.6 — this story budgets its results, does not
  produce them), **the Agent Card generation + `contextWindow`/`contextBudgetOverride` shape** (Stories
  5.2/1.2 — read as capabilities, not defined here), **the credential-injection contract** (Story 5.4 —
  the sibling injection seam; this story adds the content budget, not the credential mapping), **the
  mid-Run fallback model *switch* mechanism itself** (Story 5.11 / ISI-2297/2296 — this story only honors
  the fallback's window when it re-resolves, AC5), **the `ksquad.agent.tokens` metering** (Epic 13 —
  observes the injected budget, does not implement it), **runtime-native summarization internals** (an
  Agent Card capability, §10.1 — this story calls the summarize/drop decision, the runtime executes it).
  This story ships the **model-window token budget (resolution + clamp), the priority-ordered fail-closed
  fit, the tier-preserving injection contract, and the differential falsification** — the §8.5(3)
  fit-or-fail-closed guarantee itself.
