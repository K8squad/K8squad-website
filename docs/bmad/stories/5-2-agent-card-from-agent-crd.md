# Story 5.2: Agent Card generated from the `Agent` CRD — the honesty contract of the moat seam

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE AGENT-AGNOSTICISM HONESTY CONTRACT (arch §10.1, FR-D4, R3, Challenger F15).** The
> whole "any runtime drops into any squad, zero core changes" moat (S5/S6) rests on **one** invariant:
> a runtime's capability **gaps are advertised as first-class `false` flags on its Agent Card that the
> core reads BEFORE it dispatches** — never omitted, never special-cased, and **never discovered as a
> mid-Run failure**. A card that omits an unsupported capability turns R3 real: the core reads "absent
> → assume capable", dispatches an interactive prompt to a runtime that cannot do interactive, and the
> gap surfaces as a runtime error *mid-Run* — the "leaky abstraction" the capability-flag model exists
> to prevent. This story is the deterministic **CRD → Agent Card generation** (the Agent reconciler's
> "publishes Agent Card", §5.1) and the three honesty cruxes that keep the seam honest rather than
> leaky. Read AC2, AC3, AC4 literally — each is a correctness invariant, not a formatting rule.

## The load-bearing invariants (read first — the falsification proves these three)

The card is a pure projection of the **resolved** `Agent` CRD (+ its `Role`, `Skill` refs, resolved
`AgentRuntime`, and credential *shape*). Three properties make that projection **honest** — each is
mutation-checked in the runnable falsification, each maps to a named risk:

1. **NO-OMISSION (AC2, FR-D4 / R3).** Every capability is a **first-class flag** — `streaming`,
   `tool_calls`, `interactive`, `byoModelEndpoint` (§10.3), plus the resolved-runtime
   `docker`/`github`/`packageInstall` (§5.3). A gap is an **explicit `false`**, present on the card,
   **not an absent key**. The core's route decision reads the flags and **routes around a declared
   gap before dispatch**; an *omitted* gap is read as "capable" and dispatched, and the gap then
   surfaces as a mid-Run `RuntimeFailure` — the exact R3 leak.

2. **NO-ESCALATION (AC3, §5.3.6 trust boundary, F15).** `Agent.capabilityOverrides` **intersect the
   resolved `AgentRuntime`'s real capability ceiling.** An override may **clear** a bit (the operator
   narrows: "this agent must not use docker even though the runtime can") but may **never set** a bit
   the runtime lacks (forge `interactive: true` on a runtime that cannot). A forged flag is a
   **dishonest card** — the same self-declared-capability escalation §5.3.6 forbids for git-sourced
   skills, now on the Agent Card. The generation is `card_cap = runtime_cap AND override` — override
   is a mask that can only turn bits **off**.

3. **NO-SECRET-MATERIAL (AC4, FR-G2 / §11 / §10.1 "the shim never logs credential material").** The
   card advertises **credential *capability metadata*** — `{credentialType, credentialLifecycle}`
   derived from the §11 credential story — and **never the resolved Secret's bytes**. The card flows
   **south over A2A** (§10.1); embedding a token leaks it. An unknown credential shape **fails
   closed** (no blank/optimistic block).

## Story

As **the Agent reconciler (§5.1 "validates Secret + runtime, publishes Agent Card") + the A2A
southbound seam (§10.1)**,
I want **to deterministically generate an Agent Card from a resolved `Agent` CRD — advertising its
skills (from the `Skill`/`Role` refs), its `model`, its capability flags (streaming / tool-calls /
interactive / byoModelEndpoint) as first-class metadata where every gap is an explicit `false`, and
its credential capability metadata (`credentialType`, `credentialLifecycle`) with no secret material —
where overrides can only narrow the runtime's real capability, never forge one**,
so that **the core can route work to a runtime knowing exactly what it can and cannot do *before* it
dispatches (closing the R3 leaky-abstraction risk), a squad author's runtime is a first-class citizen
with its gaps declared not special-cased (S5/S6, FR-D4), the credential model stays vendor-neutral and
material-free (F15, FR-G2), and no agent can advertise a capability or skill it was not operator-granted
(§5.3.6) — the honesty contract Epic 7 credential handling and the ISI-2114 conformance suite build on.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` —
  - **FR-D4** (the direct requirement): *"Runtime capability gaps (streaming, tool-calls, interactive
    prompts) SHALL be expressed as **capability flags on the Agent Card**, and the core SHALL treat
    them as first-class — not special-cased hacks."*
  - **FR-D1** (A2A Agent Card capability discovery — the card is what 5.1 dispatches against),
    **FR-D3** (OpenClaw + Hermes v1 shims), **FR-D5** (conformance suite consumes the card, 5.6).
  - **FR-G2** (credential *type* + *lifecycle* exposed as **capability metadata** so the core hardcodes
    no vendor's auth flow — three concrete stories at v1), **FR-G1** (per-user Secret refs; no shared
    master credential — the material this card must never carry).
  - **R3** (*"Agent-agnosticism is a leaky abstraction"* → mitigated by FR-D4 capability flags + FR-D5
    conformance; **the core treats gaps as first-class**), **Challenger F15** (*credential model must be
    vendor-neutral, not Claude-shaped*).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§10.1 Shim placement & contract** — the authoritative spec: *"**Agent Card generated from the
    `Agent` CRD + resolved `AgentRuntime`** (skills, model, auth method, capability flags including
    docker/github/packageInstall)"* and *"**Capability flags are first-class (FR-D4, R3):** streaming /
    tool-calls / interactive-prompt / credential-type / model-endpoint override (`byoModelEndpoint`)
    are negotiated on the Agent Card; the core treats gaps as **declared capabilities, never
    special-cased hacks**. A runtime with no interactive-prompt support advertises that; the core
    **routes around it**."* **This story's whole spec is the elaboration of those two bullets.** Note
    the arch doc renumbered: the originating epic cites **§7.2** (the old numbering); the live section
    is **§10.1** (Agent Card) + **§11** (credential metadata).
  - **§5.1 `Agent` CRD** (r26/ISI-2188) — the resolved inputs: `runtimeRef` (→`AgentRuntime`, the
    capability **ceiling**), `roleRef` (→`Role`, `defaultSkills`), `skillRefs[]` (→`Skill`),
    `credentialSecretRef` (→ the §11 credential *shape*, **never** the material), `capabilityOverrides`
    (**"= the agent-card capability overrides"** — the mask this story intersects), `model`,
    `modelEndpointRef?` (§10.3, gates the `byoModelEndpoint` flag). Reconciled-by column: *"Agent
    reconciler → validates Secret + runtime, **publishes Agent Card**."* — **this story.**
  - **§5.3.6 skill-source trust boundary** — *"the `permissions`/`mcpToolRefs` capability envelope
    stays **CRD/operator-authorized, never self-declared by the repo** … a malicious repo could
    self-declare its own capability envelope [→] privilege escalation."* **AC3 is this exact boundary
    applied to the card:** an override (or a runtime) cannot self-declare a capability it was not
    granted. Skills on the card come from the **CRD refs**, resolved to the `Skill` CRDs' declared
    envelope — never from a runtime self-report.
  - **§10.3 model-provider seam** — `byoModelEndpoint` is *"a capability [a runtime] advertises… the
    core routes the Agent's endpoint + model to it. Runtimes that only speak a fixed vendor endpoint
    simply don't advertise it — no special-casing."* So the flag obeys the AC2/AC3 honesty rule; a
    `modelEndpointRef` set on a runtime that lacks the capability **fails closed** (AC5), it does not
    forge the flag.
  - **§11 Credential Model — Three Concrete Stories** — the `{acquisition, lifecycle, Secret shape}`
    table this story maps to `{credentialType, credentialLifecycle}`: **Claude-family** → `oauth` /
    `zero-touch-refresh` (§11.1); **second runtime (OpenClaw/Hermes)** → `api-key` / `static`; **BYO
    model endpoint (Ollama)** → `byo-endpoint` / `static` (§10.3). *"Credential type + lifecycle are
    capability metadata on the shim/Agent Card (FR-G2), so the core hardcodes no vendor's auth flow."*
- **Depends on:**
  - **Story 1.2** (ISI-2188 — the six `v1alpha1` CRD types; this story reads `Agent`/`Role`/`Skill`/
    `AgentRuntime` shape incl. `capabilityOverrides`, `modelEndpointRef`, `skillRefs`). Hard shape dep.
  - **§10.1 shim contract + §5.3 `AgentRuntime.capabilities`** — the resolved runtime's honest
    capability ceiling this story intersects. The Agent reconciler resolves the `AgentRuntime` to read
    it (validates Secret + runtime).
  - **ISI-2114 conformance suite (§10.1 / Story 5.6)** — the "Agent Card JSON schema + CRD→card
    mapping" is pinned in `design/agent-shim-interface-spec.md`; the **byte-stable** card this story
    generates (AC5) is what conformance asserts against. This story is the CRD→card *mapping*; ISI-2114
    is the schema + the vendor-runnable assertions.
- **Blocks / is consumed by:** **Story 5.1** (southbound A2A dispatch — *"Given a **resolved Agent
  Card**, when a Run dispatches…"* — this story produces that card), **Story 5.6** (conformance checks
  Agent Card validity + capability-flag honesty + credential-metadata correctness), **Story 5.10**
  (`rate_limited` is itself a capability flag on the card — same honesty rule), **Epic 7** (credential
  handling reads `credentialType`/`credentialLifecycle` — 7.2 OAuth, 7.3 API-key, 7.5 BYO-endpoint),
  **Story 8.10/8.11** (the console org diagram + agent detail surface runtime type + capability badges,
  read from the card).

## The generation (authoritative — §A, drives §10.1 / §5.1)

The Agent reconciler resolves the `Agent` CRD and its references, then projects them into the card. The
projection is **deterministic** (same resolved inputs → byte-identical card) and reads **only** the
CRDs — never a runtime self-report:

1. **`runtimeType`, `model`** — from the resolved `AgentRuntime.type` and `Agent.spec.model`.
2. **`capabilities` — every known key, first-class (AC2).** For each capability key
   `k ∈ {streaming, tool_calls, interactive, byoModelEndpoint, docker, github, packageInstall}`:
   `card.capabilities[k] = runtimeCap(k) AND overrideMask(k)`, where `runtimeCap(k)` is the resolved
   `AgentRuntime`'s real ability (absent → `false`) and `overrideMask(k)` is `Agent.capabilityOverrides[k]`
   if present else `true`. **Every key is emitted with an explicit boolean — a gap is `false`, never
   omitted.** The `AND` is the no-escalation intersect (AC3): an override can only clear a bit.
3. **`byoModelEndpoint` fail-closed (AC5, §10.3).** If `Agent.modelEndpointRef` is set but the resolved
   runtime lacks the `byoModelEndpoint` capability, generation **fails closed** with an operator-legible
   condition — the card never advertises a model-endpoint override the runtime cannot honor.
4. **`skills` — the CRD-authorized union (AC1, §5.3.6).** `sorted(union(Agent.skillRefs,
   Role.defaultSkills))`, each resolved to its `Skill` CRD and emitted with its **operator-authorized
   envelope** (`mcpToolRefs`, `permissions`). Canonical (sorted) order → byte-stable. A runtime cannot
   inject a skill: the projection reads no runtime skill source.
5. **`credential` — capability metadata only (AC4, §11).** Resolve `Agent.credentialSecretRef` to its
   credential **shape** and emit `{credentialType, credentialLifecycle}` from the §11 mapping. **Never
   read or embed the Secret's material.** An unknown shape **fails closed**.

The card is **generated by the control plane from the CRDs**, published by the Agent reconciler, and is
the *only* thing Story 5.1 dispatches against — the runtime never authors its own card (AC6/§5.3.6).

## The honesty rule, stated as the core's contract (why the flags are load-bearing — §B)

The core's route decision (§10.1 *"the core routes around"* a gap) reads the capability **flags**:

- **Honest card:** a gap is `interactive: false` → the core **routes around** it (re-dispatch to a
  capable agent, or degrade the task) **before** any dispatch. The runtime is **never** asked to do
  what it advertised it cannot.
- **Omitted gap (the R3 leak):** the flag is *absent* → the core reads *absent → capable* → dispatches
  → the runtime hits the gap → **mid-Run `RuntimeFailure`.** The gap became a runtime error instead of
  a routing decision — exactly the "leaky abstraction" FR-D4 forbids.

This is why "emit every key as an explicit boolean" is not cosmetic: it is the difference between a
**routing decision** and a **mid-Run failure**. The falsification proves it by having the core actually
consume the card and dispatch.

## Acceptance Criteria

**AC1 — the card advertises skills resolved from the CRD refs (operator-authorized), deterministically.**
Given an `Agent` CR with `skillRefs[]` and a `Role` with `defaultSkills[]`, When the card is generated,
Then `card.skills = sorted(union(Agent.skillRefs, Role.defaultSkills))` resolved to the `Skill` CRDs,
each carrying its **operator-authorized** envelope (`mcpToolRefs`, `permissions`). And **no runtime
self-declared skill** ever appears — the projection reads only the CRDs (§5.3.6). And two generations of
the same resolved inputs are **byte-identical** (canonical order).

**AC2 — capability flags are first-class; a gap is an explicit `false`, never omitted; the core routes
around a declared gap before dispatch (FR-D4 / R3).**
Given a resolved `AgentRuntime` that lacks a capability (e.g. `interactive`), When the card is generated,
Then `card.capabilities` contains **every** known key with an **explicit boolean**, and the unsupported
one is **`false`** (present, not absent). And the core's route decision reads that `false` and **routes
around** the gap **before** dispatching — the runtime is never asked to perform it. And a card that
**omits** the gap is a defect: the core reads absent→capable, dispatches, and the gap surfaces as a
**mid-Run failure** (the R3 leak the falsification's arm A reproduces).

**AC3 — `capabilityOverrides` intersect the runtime's capability ceiling: they can narrow, never forge
(§5.3.6 / F15).**
Given `Agent.capabilityOverrides`, When the card is generated, Then each flag is
`runtimeCap AND override` — an override that sets a capability the runtime **lacks** is **ignored**
(the flag stays `false`; the card never advertises a capability the runtime cannot honor), while an
override that **clears** a capability the runtime **has** takes effect (the operator narrows). A design
where the override **wins** (forges `interactive: true` on a non-interactive runtime) is a **dishonest
card** — the same self-declared-capability escalation §5.3.6 forbids — and the falsification proves it
fails mid-Run.

**AC4 — credential capability metadata is `{credentialType, credentialLifecycle}` only, never secret
material; unknown shapes fail closed (FR-G2 / §11 / §10.1).**
Given `Agent.credentialSecretRef`, When the card is generated, Then `card.credential` carries **only**
`{credentialType, credentialLifecycle}` mapped from the §11 story — **Claude-family** →
`oauth`/`zero-touch-refresh`, **second runtime** → `api-key`/`static`, **BYO endpoint** →
`byo-endpoint`/`static`. And the resolved Secret's **material never appears** anywhere in the
serialized card (which flows south over A2A). And an **unknown** credential shape **fails closed** — it
does **not** emit a blank/optimistic credential block.

**AC5 — `model` and `byoModelEndpoint` are advertised honestly; the card is byte-stable (§10.3 /
conformance §10.1).**
Given an `Agent` with a `model` (and optionally `modelEndpointRef`), When the card is generated, Then
`card.model` is advertised, and `byoModelEndpoint` obeys the AC2/AC3 honesty rule (advertised iff the
resolved runtime supports it). And a `modelEndpointRef` set on a runtime that **lacks**
`byoModelEndpoint` **fails closed** (never forges the flag). And the serialized card is **canonical and
byte-stable** — the CRD→card mapping the ISI-2114 conformance suite pins.

**AC6 — the card is generated from the CRDs by the control plane, never self-authored by the runtime
(§5.1 / §5.3.6).**
Given the Agent reconciler, When it publishes the card, Then the card is a **pure projection of the
resolved `Agent`/`Role`/`Skill`/`AgentRuntime` CRDs + credential shape** — the runtime is a **consumer**
of the card (Story 5.1 dispatches against it), never its author. A runtime cannot add a capability or a
skill it was not operator-granted; the operator/admin who registers the CRDs is the sole authority for
what the card advertises (the §5.3.6 trust boundary).

## Runnable check (the falsification)

`docs/bmad/spikes/bench/agent-card-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same discipline as `handoff-advisory-check.py` / `run-retry-backoff-check.py`), not a
happy-path demo. It generates cards through the real CRD→card projection SUT and has the **core actually
consume the card and dispatch**, so the honesty invariants have teeth:

- **(A) NAIVE omit-gaps card.** The card omits the `interactive` gap; the core's route decision reads
  absent→capable, dispatches, and the runtime raises a mid-Run `RuntimeFailure`. **MUST break** — if the
  omit-gaps card ever stops leaking, the harness lost its detecting power (the R3 leak is real).
- **(B) §10.1 HONEST card.** Every key is a first-class boolean; the gap is `false`; the core **routes
  around** it pre-dispatch (never dispatches the bad task) and still runs a task the runtime *can* do.
- **(F2) override NO-ESCALATION teeth (AC3).** An override `interactive: true` on a non-interactive
  runtime: the honest intersect keeps the flag `false` (forge ignored), while a naive **override-wins**
  path forges `true` → dishonest card → dispatch → mid-Run failure. *Mutation-proven:* replacing the
  `runtimeCap AND override` intersect with "override wins" turns the check **RED**. A narrowing override
  (`docker: false` on a docker-capable runtime) is honored, leaving the other flags intact.
- **(F3) credential NO-MATERIAL teeth (AC4).** The honest card's serialized wire form contains **no**
  token bytes; a naive card that embeds the resolved Secret material has the token string appear in the
  wire form (the leak). *Mutation-proven:* always-embed turns the check **RED**.
- **(C) skills from CRD refs (AC1).** `card.skills` is exactly `sorted(union(skillRefs, defaultSkills))`
  resolved to the `Skill` CRDs; a runtime-self-declared `exfil` skill never appears; two generations are
  byte-identical; each skill carries its envelope.
- **(D) credential-metadata mapping fidelity + fail-closed (AC4/AC5).** The three §11 stories map to
  their correct `{type, lifecycle}`; an unknown credential shape **fails closed** (raises, no blank
  block); a `modelEndpointRef` on a runtime lacking `byoModelEndpoint` **fails closed**.

Exits non-zero if a gap is ever omitted from a card, an override forges a capability the runtime lacks,
secret material reaches the serialized card, a self-declared skill lands on the card, the card is
non-deterministic, or an unknown/un-backed credential emits a block instead of failing closed. **The
three headline invariants are mutation-checked:** deleting the no-omission defaulting (A/F1), the
override intersect (F2), or the no-material guard (F3) each turns the check **RED** — verified. Models
the Agent-reconciler CRD→card generation in-process; real-runtime promotion rides the ISI-2114
conformance suite (§10.1, Story 5.6).

## Out of scope (owned elsewhere)

- **The A2A southbound dispatch loop** (Story 5.1 — *consumes* the resolved card; not built here), the
  **conformance suite + Agent Card JSON schema + reference shim** (Story 5.6 / ISI-2114 — asserts against
  the card this story maps; the schema pin lives in `design/agent-shim-interface-spec.md`), the
  **`rate_limited` signal + its capability flag** (Story 5.10 — a flag on the card, same honesty rule,
  driven there), the **context-injection budget / `contextWindow` capability** (Story 5.9 — a separate
  model-keyed capability), the **credential *handling*** (Epic 7 — acquires/refreshes/injects the Secret
  this story only advertises the *shape* of), the **CRD types themselves** (Story 1.2 / ISI-2188 — shape
  owner), the **console capability/runtime badges** (Story 8.10/8.11 — read model over the card). This
  story ships the **deterministic CRD→Agent-Card generation, the three honesty invariants (no-omission,
  no-escalation, no-secret-material), the credential-metadata mapping, and the differential
  falsification** — the FR-D4 / R3 honesty contract itself.
