# Story 5.3: Protocol version pinning behind the seam — the spec-drift firewall

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE SPEC-DRIFT FIREWALL OF THE A2A/MCP MOAT SEAM (arch §10.2, OQ12 / Challenger F9 / risk
> R11; NFR-EXT2).** Stories 5.1/5.2/6.2 make the core *speak* A2A/MCP; this story makes sure that when the
> **external A2A or MCP spec revs** — as it inevitably will — **the churn stops at one adapter package and
> never reaches the Run reconciler, the coordination services, or the memory/knowledge services.** The
> load-bearing invariant is one sentence: **"a version bump changes an adapter, never core."** The whole
> point of a shim architecture (NFR-EXT1/EXT2) evaporates if an upstream A2A minor rev forces an edit to
> `internal/reconcile` — that is *exactly* the coupling F9/R11 flagged as the moat's soft underbelly.

## ⚠️ Cite reconciliation — the ticket says "§7.4"; the real home is **§10.2** (read first)

The originating issue (ISI-2215) cites *"Arch §7.4."* **That cite is stale.** In the current architecture
(`docs/bmad/03-architecture.md`), **§7.4 is "Durability (NFR-REL3)"** — memory-write crash-safety, wholly
unrelated to protocol versioning. The **actual home of this story** is **§10.2 "Spec-drift isolation
(OQ12 / F9 / R11)"**, which states the pin verbatim:

> *"A2A and MCP wire versions are **pinned** in a single versioned adapter package (`pkg/a2a@rev`,
> `pkg/mcp@rev`). The core speaks an **internal stable interface**; the external spec revs are isolated *at
> the adapter seam only*. Upstream churn stays at the seam, never reaches the Run reconciler or the
> coordination/knowledge services. … spec upgrades are a deliberate, gated change (bump rev → re-run
> conformance → release), not an ambient break. Capability negotiation absorbs minor variance."*

The epics doc (`04-epics-and-stories.md`, row 5.3) carries the same stale "§7.4" cite next to the correct
"OQ12, R11, `protocol/versions.go`" — a copy of the ticket. **This story is authored against §10.2**; the
"§7.4" pointer in the ticket/epics is superseded here (no arch edit is needed — §10.2 already says exactly
what this story builds; this note just records the reconciliation so a reader isn't sent to the wrong
section). Sibling Story 5.1 already cites §10.2 for this same seam ("`pkg/a2a@rev` isolates the wire rev at
the adapter seam (Story 5.3)"), confirming §10.2 is canonical.

## ⚠️ Scope reconciliation — 5.3 vs 5.1/5.2/6.2 vs ISI-2114 vs the event catalog (they interlock)

This story owns exactly **one thing: the version-pinning *discipline* + the `internal/protocol` stable
seam** that every wire touchpoint sits behind. It does **not** implement any wire verb, card, or tool —
those are the neighbours it protects:

| Concern | Owned by | This story does |
|---|---|---|
| The **six A2A MUST-verbs**, SSE schema, Agent-Card schema, conformance suite C1–C10, reference shim | **ISI-2114** (`design/agent-shim-interface-spec.md`) | pins the **rev** those verbs speak; the suite runs against the *pinned* rev |
| The **core-side A2A dispatch client** (submit / stream / collect) | **Story 5.1** (`internal/a2a`) | 5.1 speaks the **internal stable interface** this story defines behind `pkg/a2a@rev` |
| **Agent-Card generation** from the CRD | **Story 5.2** | consumes the card schema at the pinned rev |
| The **northbound MCP tool seam** (memory tools) | **Story 6.2** (`pkg/mcp`) | the *same* pinning discipline applies via `pkg/mcp@rev`; this story establishes it once |
| The **versioned event catalog** (`pkg/events@rev`, §17.4) | **Epic 12 / ISI-2156** | governed by the **same discipline** (§10.2/§17.4 say so explicitly); this story is its template |
| **Model-endpoint / BYO-Ollama** wire (OpenAI-compatible) | **Stories 5.7/5.8** (§10.3) | a *different axis* (model provider, not agent-runtime spec) — out of scope here |

**One-line boundary:** the neighbours answer *"what does the core say over A2A/MCP?"* **This story answers
*"where is the wire revision declared, what does core import instead, and why does bumping it never touch a
core package?"*** — the F9/R11 spec-drift firewall itself.

## Story

As **the platform's protocol-seam owner (`internal/protocol` + the `pkg/a2a@rev` / `pkg/mcp@rev` adapter
packages)**,
I want **every external A2A/MCP (and event-catalog) wire revision pinned in one registry
(`internal/protocol/versions.go`) and every external-spec touchpoint placed behind a versioned
adapter that exposes only an internal stable interface — so the core imports the stable types, never the
wire types, and never reads a raw rev**,
so that **when upstream A2A or MCP churns, a version bump is a deliberate, conformance-gated change to a
single adapter package — the Run reconciler, coordination, and memory services are byte-for-byte untouched
and their behaviour is identical — delivering the NFR-EXT1/EXT2 zero-core-change guarantee and closing the
F9/R11 spec-drift risk that is the moat's soft underbelly.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **NFR-EXT2** (*"agent invocation via A2A … no bespoke lateral
  protocols"*), **NFR-EXT1** (*"adding a runtime requires only a conformant shim, zero core changes"* — the
  drift firewall is what keeps "zero core changes" true across *spec* churn, not just new runtimes),
  **OQ12** (*"A2A/MCP external-spec drift: how the protocol surface is version-pinned and isolated behind
  the shim/adapter seam so upstream churn does not reach core"* — routed to Architecture, tracked as risk
  **R11**, raised by Challenger **F9**).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§10.2 "Spec-drift isolation (OQ12 / F9 / R11)"** — the authoritative source (quoted above): pinned
    `pkg/a2a@rev` / `pkg/mcp@rev`, internal stable interface, isolation *at the seam only*, gated
    bump→re-run-conformance→release, capability negotiation absorbs minor variance.
  - **§10.1 "Shim placement & contract"** — the seam this pins; **capability flags are first-class
    (FR-D4/R3)**, which is *how* minor variance is absorbed (negotiate against declared capabilities, never
    special-case a rev).
  - **§17.3 (package layout)** — `pkg/a2a`, `pkg/mcp` are the **pinned adapter seams**; `internal/protocol`
    is the stable-interface home. **§17.4** — the **event catalog** (`pkg/events@rev`) is governed by *this
    same* drift discipline ("*versioned event catalog under §10.2 drift discipline*").
- **Consumed by (the packages this seam protects):** **Story 5.1** (`internal/a2a` dispatch client speaks
  the stable interface), **Story 5.2** (Agent-Card at the pinned rev), **Story 6.2** (`pkg/mcp` memory
  tools), the **event catalog** (§17.4). **Depends on:** **ISI-2114** (the A2A contract whose rev is
  pinned) — soft dependency; the pin registry + stable-interface skeleton can land before the shim spike
  completes, since the *discipline* is independent of the specific rev value.
- **This is an architecture-establishing story**, not a feature: its deliverable is the **seam shape +
  the enforced invariants** (single registry, layering gate, adapter-local bump, fail-closed negotiation),
  proven by a differential falsification. It ships small on purpose.

## The contract (authoritative)

### §A — One registry: every wire-rev literal lives in `internal/protocol/versions.go` (AC1)

The **only** module in the tree that contains an external-spec **revision literal** is
`internal/protocol/versions.go` (e.g. `A2ARev = "…"`, `MCPRev = "…"`, `EventCatalogRev = "…"`). Every other
package references those symbols — **no adapter, and emphatically no core package, hardcodes a wire-version
string.** A stray literal is a drift landmine: the next upstream bump updates the registry and silently
misses the copy. A CI **grep gate** enforces "no rev literal outside `versions.go`."

### §B — Layering: core imports the stable interface, the wire lives only in the adapter (AC2, the moat)

Core packages (`internal/reconcile`, `internal/coord`, `internal/memory`, and the 5.1 `internal/a2a`
*client* that speaks the stable interface) import **only** `internal/protocol` (the stable types).
**Only** the adapter packages (`pkg/a2a`, `pkg/mcp`) import the wire-rev codec. A **`core → wire` import
edge** re-couples core to the external spec and is a **C10-style grep-gate violation** — the same
zero-core-change gate Story 5.1 asserts for `runtime.type`. The stable types (`StableTask`, the card view,
the tool descriptor) carry **no wire field names and no rev** — a bump cannot change their shape.

### §C — A version bump is adapter-local: core is untouched *and* behaves identically (AC3, the headline)

Bumping a pinned rev (R1→R2) is a **two-touch change**: (1) register the new codec in the adapter's codec
table (`pkg/a2a`), (2) flip the pin in `versions.go`. **No core file is edited.** Because the adapter maps
the new wire onto the *same* stable type and **capability negotiation absorbs minor variance**, the core
receives an **identical `StableTask`** before and after the bump — its observed behaviour is byte-for-byte
unchanged. Contrast the anti-pattern: if core itself branches on the raw rev (`if rev == "v2" … else …`),
a bump forces a core edit — the coupling this story exists to forbid. A **gated** bump then re-runs
conformance (ISI-2114 C1–C10) against the new rev before release — an upgrade is deliberate, never ambient.

### §D — Negotiation is fail-closed at the seam: an incompatible rev never reaches core (AC4)

The adapter negotiates the pinned rev against the peer's advertised rev. A **compatible** rev (within the
pin's capability range — same major, minor variance) is **adapted** and delivered to core as a valid
`StableTask`. An **incompatible** rev (beyond the range) is **rejected at the seam** — the malformed wire
payload **never reaches core**; the operator must perform a gated bump. The failure is **closed**: a
wrong-shaped payload does not silently flow past the adapter and mis-parse inside the reconciler. Capability
negotiation (§10.1, FR-D4) is the *mechanism* — the core adapts to *declared capabilities*, never to a
hardcoded rev assumption.

## Acceptance Criteria

**AC1 — every external-spec rev literal is declared in `internal/protocol/versions.go` and nowhere else.**
Given the tree, When the CI grep gate scans for wire-version literals, Then the **only** file that contains
one is `internal/protocol/versions.go`; every other package (adapters included) references the registry
**symbolically**. And a **stray literal in any core package is a build-blocking violation** — it is the
drift landmine the next upstream bump would silently miss.

**AC2 — core imports the internal stable interface, never the wire adapter (the moat, C10-style gate).**
Given the import graph, When it is checked, Then core packages (`internal/reconcile` / `internal/coord` /
`internal/memory` and the 5.1 dispatch client) import **only** `internal/protocol`; **only** `pkg/a2a` /
`pkg/mcp` import the wire-rev codec. And a **`core → wire` edge is a grep-gate violation** (the same
zero-core-change discipline as Story 5.1's `runtime.type` gate). And the stable types carry no wire field
names and no rev, so a bump cannot alter their shape.

**AC3 — a version bump changes an adapter, never core; core behaviour is identical across the bump.**
Given a pinned rev R1, When it is bumped to R2, Then the change-set is **⊆ {`internal/protocol/versions.go`,
the adapter package}** — **no core file is edited**. And the core, dispatching before and after the bump,
receives an **identical `StableTask`** and produces **identical behaviour** (capability negotiation absorbs
the wire variance). And a design where **core branches on the raw rev** — forcing a core edit on every
bump — is the coupling this AC forbids. And the bump is **gated**: conformance (ISI-2114 C1–C10) re-runs
against R2 before release.

**AC4 — negotiation is fail-closed: an incompatible rev is rejected at the seam, never reaching core.**
Given a peer advertising a rev, When the adapter negotiates against the pin, Then a **compatible** rev
(within the pin's capability range) is **adapted** to a valid `StableTask` for core, and an **incompatible**
rev is **rejected at the seam** — the malformed payload **never reaches core** (a gated bump is required).
And a seam with **no rev gate** — passing an incompatible wire payload straight to core, which mis-parses
(silent corruption) — is the failure mode this AC closes. The seam **fails closed**, not open.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/protocol-version-pin-check.py` — stdlib-only, `python3` it directly. A
**differential** falsification (same discipline as `southbound-a2a-check.py` / `run-mcp-tools-check.py`):
every property runs a NAIVE/drift-prone design that MUST break (teeth) alongside the conformant design that
MUST hold. If a naive arm stops breaking, the check fails **loud** — the clean conformant result would then
prove nothing. **All four invariants are mutation-checked** (baseline exit 0; each mutation exit 1) —
verified 2026-08-13.

- **(R) single Registry (AC1).** A codebase model where each module declares the wire-rev literals it
  hardcodes; a scan asserts the **conformant** tree has zero literals outside `versions.go`, while a
  **naive** tree with an inlined `"a2a/2025-06-11"` in `internal/reconcile` yields a stray literal.
  *Mutation-proven (MUT-R):* neutering the scanner so it stops flagging non-registry literals turns the
  conformant arm **RED** (`if name != registry_name and lits` → `if False and lits`).
- **(L) Layering / import direction (AC2, the moat).** The conformant import graph has core→`internal/
  protocol` only and adapter→wire; a naive graph adds a **`core → pkg/a2a/wire`** edge. Asserts conformant
  has **zero** illegal core→wire edges and naive has ≥1. *Mutation-proven (MUT-L):* adding a
  `"pkg/a2a/wire"` import to the conformant `internal/reconcile` node turns it **RED**.
- **(B) Bump is adapter-local, headline (AC3).** A real bump v2→v2.1: register the codec in the adapter +
  flip the registry pin; the conformant core's dispatch yields an **identical `StableTask`** before/after
  and the change-set is `{versions.go, adapter}` — **core absent**. A naive core that reads the raw rev
  puts `internal/reconcile/run.go` in the change-set. *Mutation-proven (MUT-B):* flipping the conformant
  `Core.reads_raw_rev` to `True` makes the bump reach core → **RED**.
- **(N) Negotiation fail-closed (AC4).** A compatible rev (`v2.3`, same major as the `v2` pin) is adapted
  and reaches core; an incompatible rev (`v1`) is **rejected at the seam** (core never sees it); a naive
  no-gate adapter hands the `v1` payload to core, which mis-parses (`CORRUPTED`). *Mutation-proven
  (MUT-N):* replacing the adapter's rev gate with `if False:` lets the incompatible payload reach core →
  **RED**.

Exits non-zero if a stray rev-literal escapes the registry, a core→wire import edge exists, a bump's
change-set reaches a core file (or core behaviour differs across the bump), or an incompatible rev flows
past the seam into core. Baseline exit 0; each of the four documented mutations exits 1.

## Out of scope (owned elsewhere)

- **Any wire verb / SSE schema / Agent-Card schema / conformance suite** (ISI-2114 — this story pins the
  *rev* they speak, it does not implement them). **The core-side A2A dispatch client** (Story 5.1 — it
  *consumes* this story's stable interface). **Agent-Card generation** (Story 5.2). **The MCP tool
  implementations** (Story 6.2 — the *same* `pkg/mcp@rev` discipline applies, established here once). **The
  event catalog's concrete event types** (Epic 12 / ISI-2156 — governed by this discipline via
  `pkg/events@rev`, §17.4, but its schemas are theirs). **The model-endpoint / BYO-Ollama wire** (Stories
  5.7/5.8, §10.3 — a *model-provider* axis, distinct from the *agent-runtime spec* axis this story pins).
  **Actually performing a real upstream A2A/MCP rev upgrade** (a future gated change — this story ships the
  seam that *makes* such an upgrade adapter-local, not the upgrade itself). This story ships the
  **spec-drift firewall**: the single pin registry (`internal/protocol/versions.go`), the internal
  stable-interface seam core imports instead of the wire, the adapter-local-bump guarantee, the
  fail-closed negotiation gate, and the differential falsification that gives all four teeth — the
  NFR-EXT1/EXT2 zero-core-change-across-spec-churn guarantee that closes risk R11.
