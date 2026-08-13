# Story 5.5: OpenClaw + Hermes shims — two runtimes, one squad, one seam (the S6 proof)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE *PROOF* STORY OF THE I2 MOAT — TWO DIFFERENT-`type` RUNTIMES RUN REAL RUNS IN ONE
> SQUAD (arch §10.1, FR-D3, NFR-EXT1/EXT2, S6).**
> Stories 5.1/5.2/5.3 + ISI-2114 built the seam (runtime-agnostic dispatch client, Agent-Card
> negotiation, pinned wire rev, the six-verb shim contract + reference OpenClaw shim). **This story
> proves the seam is real by standing two runtimes of *different `type`* — OpenClaw and Hermes — side by
> side in the *same Team namespace*, and having *both run real Runs* against the *same coordination
> record*.** The load-bearing invariant is **"heterogeneous runtimes share one spine: one coordination
> record, one fenced-claim/lease/fence mechanism, one dispatch path, one Agent-Card negotiation, one
> per-user credential model — and the *only* per-runtime code that exists lives inside each shim's
> native-translation, never in the core, the coord services, or the squad's shared coordination
> record."** A second runtime that requires **any** core/coord change to run, that gets its **own
> per-`type` claim queue or dispatch branch**, that is secretly a **facade forwarding to the first
> runtime's native gateway** (so only one runtime actually executes), or that **borrows the first
> runtime's capability assumptions** instead of its own honest Agent Card — **is a moat leak**. Not a
> style preference: it is the exact per-runtime coupling NFR-EXT1 forbids and the failure mode design
> §10 names — *"No Hermes-specific core code exists; if it did, the seam would have leaked."* Read AC1
> literally.

## ⚠️ Scope reconciliation — 5.5 vs ISI-2114 vs 5.1/5.2/5.6/5.8 (read first, they interlock on purpose)

The originating issue (ISI-2217) says *"Given a squad with an OpenClaw agent and a Hermes agent, When a
Run executes, Then both runtimes run real Runs in the same squad (S6)."* Several neighbours build the
machinery; **this story owns exactly the heterogeneous *co-residency proof* + the shipping second
runtime**, and consumes the rest:

| Concern | Owned by | This story does |
|---|---|---|
| The **shim's** six-verb contract, SSE schema, Agent-Card JSON schema, conformance suite C1–C10, and the **reference OpenClaw shim skeleton + translation table** | **ISI-2114** (`design/agent-shim-interface-spec.md` §9) | **consumes** the OpenClaw reference; **ships** the second runtime (Hermes §10) as a genuine, non-facade translation |
| The **core-side A2A dispatch client** (runtime-agnostic submit/stream/collect, C10 no-`type`-branch) | **Story 5.1** (ISI-2213, `internal/a2a`) | **exercises** it with *two* live runtimes at once — the same client drives both, unchanged |
| **Generating** the Agent Card from each `Agent` CRD + resolved `AgentRuntime` | **Story 5.2** (ISI-2214, §10.1) | **reads** each runtime's *own* honest card to negotiate; never borrows one runtime's caps for the other |
| **Pinning** the A2A wire rev behind `pkg/a2a@rev` | **Story 5.3** (ISI-2215, §10.2) | both shims speak the **internal stable interface** behind the pin |
| The **conformance harness** (C1–C10) + the **Ollama credential-free lane** | **Story 5.6** (§12, ISI-2114 deliverable) | **each `type` passes it** as the ship-gate; this story does not build the harness, it requires both runtimes green on it |
| The **`opencode`** third v1 runtime (pulled forward from Phase 2) | **Story 5.8** (CEO 2026-08-11) | **out of scope here** — 5.5 ships {OpenClaw, Hermes}; opencode is the sibling that makes the set three |
| The **squad = Team namespace** tenancy, RuntimeClass isolation, per-Project workspace, egress allowlist | **Stories 4.1–4.6** (§9) | **runs inside** one Team namespace; both runtimes co-reside under the same tenancy/isolation/egress baseline |
| The **coordination spine** (fenced claim / lease / fence, §6.2/§6.3), **audit trail**, **handoff** | **Stories 2.2/2.3/2.4/2.6/2.8** | both runtimes **claim/coordinate through the identical spine** — type never touches a claim/lease/fence decision |
| **Second-runtime credential model** (OQ11: static API key, per-user Secret, no OAuth) | **Story 7.3** (§11 row 2) | **mounts** each runtime's own per-user Secret; proves no shared master, no cross-runtime read |

**One-line boundary:** ISI-2114 answered *"what must a shim implement to be drivable?"* and shipped the
OpenClaw reference. Story 5.1 built *"how the core drives one shim."* **This story answers *"do two
runtimes of different `type` actually co-reside in one squad and both run real Runs through the identical
spine — with the only per-runtime code buried in each shim, and no facade faking the second runtime?"* —
by shipping the Hermes shim and standing it next to OpenClaw as the S6 acceptance.**

> **⚠️ Cite correction (the epic's `Arch §7.5` is stale).** The 04-epics-and-stories.md row for 5.5 cites
> *"Arch §7.5, §11.2 (`shims/openclaw`, `shims/hermes`)"*. **§7.5 is the per-Project *Discussion Room*,
> not the shim architecture** (a stale pointer of the same class flagged on ISI-2212/ISI-2189). The
> governing architecture is **§10.1 "Shim placement & contract"** (v1 shims: OpenClaw + Hermes; one shim
> per runtime, sidecar, six MUST-verbs), **§10.2** (spec-drift isolation), **§10.3** (BYO model
> endpoint / Ollama lane), and **§11** (credential model — the three concrete stories). The shim images
> live at `shims/openclaw` / `shims/hermes` (packaging referenced in §10.1 / design §9/§10). This story
> targets **§10.1/§10.2/§11 + design §9/§10/§12**, not §7.5.

## Story

As **the KSquad platform proving the runtime-extensibility moat is real (I2/S6, the whole product claim
that "a vendor runtime drops into a squad with zero core changes")**,
I want **the OpenClaw and Hermes shims to both ship as conformant v1 runtime images and both run real
Runs concurrently inside one Team namespace — claiming from the same coordination record through the same
fenced-claim/lease/fence mechanism, dispatched by the same runtime-agnostic core client through the same
Agent-Card negotiation, each mounting its own per-user credential Secret, and each independently executing
its claimed work to a real artifact — with the only per-runtime code living inside each shim's
native-translation and zero `runtime.type` branching anywhere in the core, the coord services, or the
shared coordination record**,
so that **S6 ("two runtimes in one squad") is met not as a demo but as a structural guarantee: a
heterogeneous squad coordinates on one spine, the second runtime is a genuine independent executor rather
than a facade forwarding to the first, no runtime is privileged or holds a shared master credential, and
the seam is proven neither Claude-shaped nor OpenClaw-shaped — the FR-D3 / NFR-EXT1 zero-core-change
extensibility guarantee that is the moat.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-D3** (ship OpenClaw + Hermes shims; both run real Runs in one
  squad — the direct requirement), **FR-D1/D2** (southbound A2A; one shim per runtime, A2A⇄native),
  **FR-D4** (capability flags first-class), **FR-D5** (conformance suite), **NFR-EXT1/EXT2**
  (zero-core-change extensibility — the moat), **S6** (two runtimes in one squad), **S5** (a vendor
  runtime drops into a squad). **FR-G1/G2** (per-user Secret refs; credential type is capability
  metadata — the §11 credential lock).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§10.1 "Shim placement & contract"** — *"**v1 shims: OpenClaw + Hermes** (FR-D3/S6)."* One shim per
    runtime, sidecar in the sandbox pod, terminating A2A southbound and translating to the runtime's
    **native** invocation (*"OpenClaw gateway/sessions API; Hermes native"*). **Capability flags are
    first-class (FR-D4/R3)**; the core negotiates against each card, never special-cases a runtime.
    **Standardized control signals** (`auth_failure`, `rate_limited`) are normalized *in the shim* so the
    core sees one signal set regardless of runtime.
  - **§10.2 "Spec-drift isolation"** — both shims speak the core's **internal stable interface**; the
    wire rev is pinned at `pkg/a2a@rev` (Story 5.3). A rev bump never touches either runtime's
    co-residency.
  - **§10.3 "Model-provider seam — BYO endpoints & Ollama"** — the *model* is a separate axis from the
    *runtime*; both runtimes may advertise `byoModelEndpoint` and be pointed at an Ollama endpoint (the
    credential-free conformance lane, §12/Story 5.6). This story's proof runs on that lane so it needs
    **no paid credentials**.
  - **§11 "Credential Model — Three Concrete Stories"** — the **second-runtime row**: OpenClaw/Hermes use
    a **long-lived API key / provider token as a per-user Secret ref** (static; no interactive OAuth;
    OQ11 pinned in Story 7.3). **KSquad never holds a shared master credential** (FR-G1 LOCKED). Each
    runtime mounts its **own** Secret; neither reads the other's.
  - **§9 (Epic 4)** — the **squad = Team namespace** tenancy (§9.1, Story 4.1), RuntimeClass isolation
    (§9.1/4.2), per-Project workspace (§9.4/4.3), default-deny egress + model-endpoint allowlist
    (§12.2/4.6). Both runtimes co-reside **inside one such namespace**, under the same isolation/egress
    baseline — the second runtime introduces **no new tenancy surface**.
  - **§6.2/§6.3** — the fenced **claim / lease / fence** spine (Stories 2.2/2.3/2.4). Both runtimes' Runs
    claim from the **same** `coord` record through the **identical** mechanism; **`runtime.type` never
    participates in a claim/lease/fence decision** (AC1).
- **Companion design (consumed, not re-specified):** **`docs/bmad/design/agent-shim-interface-spec.md`
  (ISI-2114)** —
  - **§3** the six MUST-verbs; **§4** the SSE schema; **§5/§6** artifact + Agent-Card contracts.
  - **§9 "Reference shim — OpenClaw"** — the OpenClaw native translation table (sessions keyed on
    `a2a_task_id`; `agent_end`→`usage`+artifacts; `interactivePrompt:false`, `byoModelEndpoint:true`) and
    the reference skeleton. **This story consumes it as the first runtime.**
  - **§10 "Hermes — second runtime, contract-only"** — *"Hermes reaches the **same six verbs** via its
    native API; the translation table is Hermes-specific and produced when the Hermes runtime image lands
    (ISI-2113). The point of two v1 runtimes is to prove the seam is **not Claude-shaped and not
    OpenClaw-shaped** — the conformance suite (§12) is the shared gate both MUST pass. **No
    Hermes-specific core code exists; if it did, the seam would have leaked.**"* **This story ships that
    Hermes translation table + image** and stands it next to OpenClaw.
  - **§12 "Conformance suite — the ISI-2114 deliverable gate"** — C1–C10; *"Each `AgentRuntime.type` MUST
    pass before S5/S6 can be claimed."* **The ship-gate: both `type: openclaw` and `type: hermes` green
    on C1–C10 (Story 5.6 harness, Ollama lane).**
- **Depends on:**
  - **ISI-2114** (the shim spec + reference OpenClaw shim + conformance harness — the contract both
    runtimes conform to). **Hard gate** (§21): the reference shim + conformance assertions must land
    before S5/S6 can be claimed.
  - **Story 5.1** (ISI-2213 — the runtime-agnostic core dispatch client both runtimes are driven by,
    unchanged). **Hard dependency.**
  - **Story 5.2** (ISI-2214 — the Agent Card each runtime's negotiation reads). **Hard dependency.**
  - **Story 5.6** (the conformance harness + Ollama lane — the ship-gate both `type`s pass). **Hard gate.**
  - **Story 7.3** (§11 second-runtime credential model — the static-API-key per-user Secret each runtime
    mounts; OQ11). **Hard dependency for the credential-isolation AC.**
  - **Stories 4.1–4.6** (the Team-namespace squad both runtimes co-reside in). **Hard dependency.**
- **Blocks / is consumed by:** **S6 acceptance** (the epic's headline — "two runtimes in one squad"),
  **Story 5.8** (opencode — the third runtime that reuses this exact co-residency proof), the
  **conformance/ship gate** for every future vendor runtime (this is the template a new `type` follows to
  "drop into a squad with zero core changes").

## The co-residency contract (authoritative)

### §A — Two `type`s, one spine: coordination is runtime-AGNOSTIC (the moat, AC1)

Both Runs — the OpenClaw agent's and the Hermes agent's — live in the **same Team namespace** and claim
from the **same `coord` work-item backlog** through the **identical** fenced claim/lease/fence mechanism
(§6.2/§6.3). **`runtime.type` never participates in a claim, lease, or fence decision**, and there is **no
per-`type` work queue, claim path, or backlog partition.** Two agents of different `type` compete for and
claim from one shared backlog exactly as two agents of the same `type` would. A per-`type` queue would
mean the two runtimes cannot share one squad's work — **the S6 failure**.

### §B — Zero-core-change dispatch: no `type` branch anywhere (AC1/C10)

The **same** Story-5.1 dispatch client drives both runtimes, **unchanged**. The dispatch code path (Run
reconciler + coord services) **does not branch on `runtime.type`**: it negotiates against each runtime's
own Agent Card capability flags and reaches the agent through **only** the six A2A verbs. Two runtimes
with identical capability cards produce an **identical dispatch trace** (the C10 grep-gate: *no `type ==`
special-casing in the Run reconciler / coord services*). The **only** per-runtime code that exists is
inside each shim's native-translation (OpenClaw sessions ⇄ A2A; Hermes native ⇄ A2A) — **never** in the
core. Any `type`-branch in the core/coord is the exact coupling NFR-EXT1 forbids.

### §C — Both run REAL Runs: the second runtime is not a facade (AC2, design §10)

Each runtime **independently executes its own claimed work item to a real artifact**. The Hermes shim
translates to **Hermes' native runtime** and produces the artifact — it is **not** a stub that forwards
`SubmitTask` to OpenClaw's gateway (which would mean only one runtime ever executes and the "second
runtime" is a lie). The proof: the artifact each Run emits is **stamped with the executing runtime**, and
that stamp **equals the claimed agent's `runtime.type`** (an OpenClaw Run's artifact is produced by
OpenClaw; a Hermes Run's by Hermes). A facade forwards across the runtime boundary and the stamps collapse
to one runtime — detectably. This is design §10's *"if it did, the seam would have leaked"* made testable.

### §D — Per-runtime credential isolation: no shared master (AC3, §11)

Each agent mounts its **own per-user Secret** (the §11 second-runtime shape: a **static API key / provider
token**, no interactive OAuth). The OpenClaw agent's Run uses the OpenClaw agent's Secret; the Hermes
agent's Run uses the Hermes agent's Secret. **KSquad holds no shared master credential** (FR-G1 LOCKED),
and **neither runtime reads the other's Secret** (tenancy/least-privilege, §9.1). Credential **type +
lifecycle are capability metadata on each card** (FR-G2) — the core hardcodes no runtime's auth flow. A
shared master both runtimes draw from is the exact vendor-lock §11 forbids.

### §E — Capability-negotiated, never type-assumed (AC4, §10.1/FR-D4)

The core routes each Run by **that runtime's own honest Agent Card** — it does **not** assume Hermes has
OpenClaw's capabilities (or vice versa). OpenClaw advertises `interactivePrompt:false, byoModelEndpoint:
true` (design §9.1); Hermes advertises **its own** honest flags. A task requiring a capability a given
runtime lacks is routed **around** that runtime pre-dispatch (Story 5.2's honesty contract), never
dispatched-then-failed. Borrowing one runtime's capability assumptions for the other re-introduces the
per-runtime special-casing the Agent Card exists to eliminate. **The standardized control signals**
(`auth_failure → Paused`, `rate_limited → Paused(rate_limited)`) are normalized **in each shim**, so the
core sees one signal set for both runtimes (§10.1).

## Acceptance Criteria

**AC1 — two different-`type` runtimes coordinate on ONE spine, with zero `type` branching (the moat / C10).**
Given a squad (one Team namespace) with an **OpenClaw** `Agent` and a **Hermes** `Agent`, When both
dispatch Runs, Then both claim from the **same `coord` work-item backlog** through the **identical**
fenced claim/lease/fence mechanism (§6.2/§6.3) with **`runtime.type` never touching a claim/lease/fence
decision** and **no per-`type` queue or backlog partition**; And the **same** Story-5.1 dispatch client
drives both **unchanged**, with **no `type ==` branch** in the Run reconciler / coord services (the C10
grep-gate) — two runtimes with identical capability cards produce an **identical dispatch trace**; And the
**only** per-runtime code lives inside each shim's native-translation. A per-`type` claim path/queue or a
core/coord `type`-branch is a moat leak — a correctness/architecture failure, not a style nit.

**AC2 — both runtimes run REAL Runs; the second runtime is not a facade forwarding to the first.**
Given the OpenClaw Run and the Hermes Run executing concurrently in the one squad, When each completes,
Then each **independently executes its own claimed work item to a real artifact**, and the artifact is
**stamped with the executing runtime** such that the stamp **equals the claimed agent's `runtime.type`**
(OpenClaw's artifact ⟵ OpenClaw; Hermes's ⟵ Hermes); And the Hermes shim translates to **Hermes' native
runtime**, **not** by forwarding `SubmitTask` across the runtime boundary to OpenClaw's gateway. A facade
whose "second runtime" secretly re-enters the first (so only one runtime executes) collapses the stamps to
one runtime and is a defect (design §10: *"if it did, the seam would have leaked"*).

**AC3 — per-runtime credential isolation: each mounts its own per-user Secret, no shared master.**
Given both agents provisioned per §11, When each Run dispatches, Then each mounts its **own per-user
Secret** (the second-runtime static-API-key shape — no interactive OAuth), the OpenClaw Run uses the
OpenClaw agent's Secret and the Hermes Run the Hermes agent's, **KSquad holds no shared master
credential** (FR-G1), and **neither runtime reads the other's Secret** (§9.1 least-privilege); And
credential type/lifecycle ride each card as capability metadata (FR-G2). A shared master credential both
runtimes draw from is the vendor-lock §11 forbids.

**AC4 — capability-negotiated routing, never type-assumption; both pass conformance C1–C10.**
Given each runtime's **own** honest Agent Card (§10.1/FR-D4), When the core routes a Run, Then it
negotiates against **that** runtime's flags — **not** by assuming one runtime has the other's
capabilities — and routes **around** a declared gap pre-dispatch (Story 5.2), never dispatch-then-fail;
And the standardized control signals (`auth_failure`, `rate_limited`) are normalized **in each shim** so
the core sees **one** signal set for both; And **both `type: openclaw` and `type: hermes` pass the
conformance suite C1–C10** (Story 5.6 harness, Ollama lane, no paid credentials) — the §12/§21 ship-gate
that lets S6 be **claimed** rather than demoed.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/two-runtimes-one-squad-check.py` — stdlib-only, `python3` it directly. A
**differential** falsification (same shape as the Story 5.1 / 5.2 / 2.9 checks): every property runs a
NAIVE/cheating design that MUST break (teeth) alongside the conformant design that MUST hold. If a naive
arm stops breaking, the check fails **loud** — the clean conformant result would then prove nothing.

- **(H) heterogeneous same-squad shared spine (AC1).** A **conformant squad** puts an OpenClaw Run and a
  Hermes Run in one Team namespace claiming from **one shared backlog** via a **type-blind** fenced
  claim; both claim successfully and the claim decision **never reads `type`**. A **naive** design gives
  each runtime its **own per-`type` queue**, so the Hermes agent **cannot claim** an item enqueued for
  the shared backlog (or the two runtimes never share one squad's work) → **S6 fails**. *Mutation-proven:*
  making the conformant claim consult `runtime.type` (partition the backlog) starves one runtime → **RED**.
- **(Z) zero-core-change / no `type` branch dispatch (AC1/C10).** The conformant core produces a
  **byte-identical dispatch trace** for the OpenClaw and Hermes Runs (identical capability cards, trace
  recorded from the **real verb calls**, not a constant); a **cheating** core with an `if type ==
  "hermes"` branch **forks the trace** (different verb order / envelope / a native reach). *Mutation-proven:*
  making the conformant path branch on `type` (even a behaviour-neutral fork — the ISI-2377 probe class)
  forks the trace → **RED**. The C10/NFR-EXT1 seam has teeth.
- **(R) both real, no facade (AC2, design §10).** Each Run's artifact is stamped with the runtime that
  produced it; the conformant squad yields `{openclaw-run → openclaw, hermes-run → hermes}` (two real
  executors). A **facade** Hermes shim that forwards `SubmitTask` to OpenClaw's gateway yields `{hermes-run
  → openclaw}` — the stamps collapse to one runtime (only OpenClaw ever executed). *Mutation-proven:*
  routing the conformant Hermes shim through OpenClaw's native gateway collapses the stamp → **RED**.
- **(C) per-runtime credential isolation (AC3, §11).** Each Run mounts its **own** per-user Secret; the
  conformant squad records **distinct** credentials per runtime and **no shared master**, and a
  cross-runtime Secret read is **rejected** (§9.1). A **naive** shared-master design has **both** runtimes
  draw the **same** master credential. *Mutation-proven:* pointing both conformant runtimes at one shared
  master collapses the credential set to one → **RED**.
- **(K) capability-negotiated, not type-assumed (AC4, §10.1/FR-D4).** Hermes advertises its **own** honest
  card (say `interactivePrompt:false`); the conformant core routes an interactive task **around** Hermes
  pre-dispatch. A **naive** core that **assumes Hermes has OpenClaw's capabilities** dispatches the
  interactive task to Hermes → **mid-Run failure**. *Mutation-proven:* making the conformant router borrow
  OpenClaw's caps for Hermes dispatches the un-runnable task → **RED**.

Exits non-zero if the two runtimes cannot share one squad's backlog, the dispatch forks on `runtime.type`,
the second runtime is a facade (stamps collapse), a shared master credential appears (or a cross-runtime
Secret read is accepted), or the core routes by type-assumption instead of each card. **All five headline
invariants are mutation-checked** (baseline exit 0; each mutation exit 1) — verified 2026-08-13. Models the
squad-level co-residency in-process; real-runtime promotion rides the ISI-2114 conformance suite (§12,
Story 5.6, Ollama lane) — the §21 gate that lets S6 be *claimed*.

## Out of scope (owned elsewhere)

- **The shim's six-verb implementation, SSE schema, Agent-Card schema, conformance suite C1–C10, and the
  reference OpenClaw shim skeleton + translation table** (ISI-2114 `design/agent-shim-interface-spec.md`
  §3–§9/§12 — this story *consumes* the OpenClaw reference and *ships* the Hermes translation next to it).
  **The core-side A2A dispatch client** (Story 5.1 — exercised here by two live runtimes, not rebuilt).
  **Agent-Card *generation* from the CRD** (Story 5.2 — each runtime's card is read, not generated here).
  **A2A/MCP wire-rev pinning** (Story 5.3 — both shims speak the internal stable interface behind it).
  **The conformance *harness* + Ollama lane** (Story 5.6 — the ship-gate both `type`s pass; not built
  here). **The `opencode` third runtime** (Story 5.8 — the sibling that makes the v1 set three; this
  story ships {OpenClaw, Hermes}). **The second-runtime credential *model*** (Story 7.3 / §11 — the
  static-API-key per-user Secret shape is mounted, not defined here). **The Team-namespace squad
  tenancy / RuntimeClass isolation / workspace / egress** (Stories 4.1–4.6 — both runtimes co-reside
  inside one such namespace; no new tenancy surface). **The coordination spine itself** (Stories
  2.2/2.3/2.4/2.6 — claimed/coordinated-through, type-blind, not re-specified). This story ships the
  **second runtime image + the heterogeneous co-residency proof**: two different-`type` runtimes running
  real Runs on one spine, no facade, no shared master, no `type` branch — the FR-D3 / NFR-EXT1 / S6
  guarantee itself.
