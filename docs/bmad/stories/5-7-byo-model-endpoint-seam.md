# Story 5.7: BYO Ollama endpoint — the model-endpoint seam (no new runtime type, no new image, zero core change)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE *CATEGORY-ERROR FIREWALL* OF THE MODEL AXIS (arch §10.3, ADR-026, FR-D4).**
> An `Agent` points at its **own Ollama / any OpenAI-compatible endpoint** (BYO local model, **$0**)
> and a squad runs on it — *without* a new `AgentRuntime.type`, *without* a new image, and with
> **zero core change**. The load-bearing invariant is **"BYO Ollama is a *model-endpoint override*,
> not a runtime."** The *coding-agent runtime* (opencode / OpenClaw / Hermes) is one pluggable axis
> (§5.3/§10.1); the **model** those runtimes call is a **separate axis** (§10.3). Ollama is **not a
> coding runtime — it is an OpenAI-compatible model server** — so it lands on the model axis as
> `Agent.spec.model` + an endpoint resolved from `Agent.spec.modelEndpointRef` (a per-user Secret),
> consumed by **any runtime advertising the `byoModelEndpoint` capability** (`opencode` by default,
> Story 5.8). **Treating Ollama as an `AgentRuntime.type` is the category error ADR-026 forbids** —
> a new runtime surface, a new image, and a new core branch where the architecture says there is
> only a model-endpoint override. A design that registers `type: ollama`, that bakes the endpoint
> into the image (so it cannot be retargeted), that assumes every runtime can accept a base-URL
> override (so a weak local model **fails silently mid-Run** instead of being routed around
> pre-dispatch), that falls back to a **shared platform endpoint** (reopening the §11 BYO-credential
> lock on the model axis), or that opens egress **allow-all** to reach the endpoint — **is a leak.**
> Not a style preference: it is the exact per-model coupling ADR-026 forbids and the failure mode
> §10.3 names. Read AC1 literally.

## ⚠️ Scope reconciliation — 5.7 vs 5.8 vs 5.6/ISI-2114 vs 7.5 vs 1.2 (read first, they interlock on purpose)

The originating issue (ISI-2219) says *"Given an `Agent` with `modelEndpointRef` → Secret + model set,
When a Run dispatches, Then the resolved runtime rides the OpenAI-compatible wire to the endpoint
through the existing shim seam — no new `AgentRuntime.type`, no new image, zero core change; the Agent
Card advertises the `byoModelEndpoint` capability. Reference runtime = opencode (5.8)."* Several
neighbours build the pieces; **this story owns exactly the *model-endpoint seam itself*** — the
resolve-to-config path + its five invariants — and consumes the rest:

| Concern | Owned by | This story does |
|---|---|---|
| The **`opencode` runtime shim** (native Ollama / OpenAI-compatible provider, `baseURL …:11434/v1`) — the concrete reference runtime that speaks the wire | **Story 5.8** (ISI-2220) | **consumes** opencode as the default `byoModelEndpoint`-capable runtime; the seam is runtime-agnostic (any advertising runtime works) |
| The **shim's six-verb contract, SSE schema, Agent-Card schema, and the `byoModelEndpoint` capability flag definition + conformance suite C1–C10** | **ISI-2114** (`design/agent-shim-interface-spec.md`) | **reads** each runtime's honest card to negotiate; **requires** the conformance Ollama lane green as the ship-gate |
| The **conformance *harness* + Ollama lane** (same C1–C10 assertions with the model resolved to a BYO Ollama endpoint — task-in → run → artifacts-out, $0) | **Story 5.6** (ISI-2218) | **runs the proof on** that lane; does not build the harness |
| The **model axis vs runtime axis split** + the `byoModelEndpoint` capability + the §11 third credential story + the CI-free-lane framing | **Architecture §10.3 / ADR-026** (ISI-2157, r8) | **implements** the resolve/dispatch/egress seam that §10.3 specifies |
| The **Ollama / BYO-endpoint credential *shape*** — endpoint URL (+ optional token) as a per-user Secret ref, model name per Agent, rotation = Secret update, unreachable-endpoint pause/resume | **Story 7.5** (§11 third story) | **mounts** that Secret shape; proves no shared platform endpoint, no shared master; does not define the credential model |
| The **`Agent.spec.modelEndpointRef` CRD field** (→ Secret) | **Story 1.2** (ISI-2188, added at Gate 2 — arch §5.1 r26) | **resolves** that field; the field already landed (the 5.7-flagged Gate-2 gap is closed) |
| The **default-deny egress + model-endpoint allowlist** on the Team NetworkPolicy | **Story 4.6** (ISI-2212, §12.2) | **adds** the resolved BYO endpoint host to that allowlist; default-deny still holds |
| The **runtime-agnostic core dispatch client** (no `type` branch, C10) | **Story 5.1** (ISI-2213, `internal/a2a`) | **drives** the resolved target **unchanged** — the endpoint override is config the same client reads for every Agent |
| The **model-window token budget** (`contextWindow` keyed to the resolved model — Claude ~200K vs BYO Ollama ~8K) | **Story 5.9** (ISI-2221, §8.5/§10.3) | **out of scope** — the budget rides the resolved endpoint this story produces, but is owned there |
| The **rate-limit fallback / mid-Run model switch** (`Agent.spec.fallbackModel`) | **§8 tier 1 / ADR-030/031** (Epic 7/13) | **out of scope** — reuses this seam's model-endpoint-override machinery re-resolved live; not built here |

**One-line boundary:** Story 5.8 ships *the runtime that speaks the wire*; Story 7.5 defines *the
credential shape*; Story 5.6/ISI-2114 build *the conformance lane that proves it end-to-end*; Story 1.2
added *the CRD field*. **This story owns the *seam in between*: the control-plane resolve that turns an
`Agent` (`model` + `modelEndpointRef`) into a dispatch target — an *ordinary* runtime + a
Secret-resolved OpenAI-compatible base-URL — with no new type, no new image, no core branch, honest
capability negotiation, a per-user credential, and default-deny egress preserved.**

> **⚠️ Cite correction (the epic's `Arch §7.5` is stale).** The 04-epics-and-stories.md rows for
> Epic 5 cite *"Arch §7.5, §11.2 (`shims/…`)"*. **§7.5 is the per-Project *Discussion Room*, not the
> shim/model architecture** (the same stale-pointer class flagged on ISI-2212/ISI-2189/ISI-2217). The
> governing architecture for this story is **§10.3 "Model-provider seam — BYO endpoints & Ollama"**
> (the model axis, `byoModelEndpoint`, ADR-026), **§10.1** (shim contract + capability flags), **§11**
> (credential model — the **third** story, Two→Three per ADR-026), and **§12.2** (default-deny egress +
> model-endpoint allowlist). This story targets **§10.3/§10.1/§11/§12.2 + ADR-026**, not §7.5.

## Story

As **the KSquad platform proving the *model* axis is as pluggable as the *runtime* axis without
re-opening either seam (the ISI-2157 "run a squad on your own Ollama, $0, zero core change" claim)**,
I want **an `Agent` that sets `Agent.spec.model` + `Agent.spec.modelEndpointRef` (→ a per-user Secret
holding a BYO Ollama / OpenAI-compatible endpoint URL [+ optional token]) to resolve, at dispatch, onto
an *ordinary* `byoModelEndpoint`-capable runtime (opencode by default, Story 5.8) whose shim rides the
OpenAI-compatible wire to that endpoint — with the runtime-type registry gaining **no** `ollama` entry,
**no** new image built, **no** `type`-branch added to the core, the endpoint carried as **config** (so
the same image retargets a paid provider unchanged), the capability **negotiated** against each
runtime's honest Agent Card (a runtime that cannot accept a base-URL override is routed **around**
pre-dispatch, never dispatched-then-failed on a weak local model), the endpoint drawn from the Agent's
**own** per-user Secret (no shared platform endpoint, no shared master), and the endpoint host added to
the Team **model-endpoint allowlist** under a still-default-deny egress**,
so that **"Ollama is a model backend, not a runtime type" is met not as a naming convention but as a
structural guarantee: the ADR-026 category error is impossible to commit accidentally, a squad runs on
a self-hosted local model with zero paid credits, and the BYO-credential lock (FR-G1) and default-deny
egress (§12.2) are *reinforced* on the model axis rather than reopened — the §10.3 / FR-D4 / NFR-EXT1
model-provider seam that doubles as the free CI/conformance lane (ISI-2157).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-D4** (capability flags first-class — `byoModelEndpoint` is one),
  **FR-D1/D2** (southbound A2A; one shim per runtime), **FR-D5** (conformance suite — the Ollama-lane
  ship-gate), **NFR-EXT1/EXT2** (zero-core-change extensibility — the moat this story extends to the
  model axis), **FR-G1/G2** (per-user Secret refs; credential type/lifecycle is capability metadata —
  the §11 lock the third credential story reinforces), **S6** (runtimes drop into a squad).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§10.3 "Model-provider seam — BYO endpoints & Ollama" (ISI-2157, r8)** — *the governing section.*
    The **honest distinction**: §5.3/§10.1 make the *coding-agent runtime* pluggable; the **model** is a
    *separate axis*. Ollama is *"not a coding runtime — it is an OpenAI-compatible model server,"* so it
    is implemented as a **model-endpoint override** (`Agent.spec.model` + endpoint from a Secret ref),
    consumed by any runtime advertising **`byoModelEndpoint`**. *"Treating Ollama as an
    `AgentRuntime.type` would be a category error — recorded in ADR-026."* **Capability-negotiated
    (FR-D4)**; **credential shape = §11 third story** (per-user Secret ref, no shared master); **egress
    via the model-endpoint allowlist (§12.2)** with default-deny intact; **free CI / conformance lane**
    (no paid credits). **Honesty:** local models are weaker — the Ollama lane is for correctness/plumbing
    e2e + conformance, never a production quality bar.
  - **ADR-026** — BYO model-provider seam / Ollama on the model axis (recorded in §10.3 *Trade recorded*).
    The category-error firewall this story makes testable.
  - **§10.1 "Shim placement & contract"** — capability flags are first-class (FR-D4/R3); the core
    negotiates against each card, never special-cases a runtime. `byoModelEndpoint` is one such flag.
  - **§11 "Credential Model — Three Concrete Stories" (Two→Three per ADR-026)** — the **third** row:
    **BYO model endpoint (Ollama / OpenAI-compatible)** — user supplies an **endpoint URL** (+ optional
    token) as a **per-user Secret ref**; model is `Agent.spec.model`; **static, no vendor OAuth, no paid
    credits, no shared master** (FR-G1 LOCKED).
  - **§12.2 (Story 4.6)** — default-deny egress + **model-endpoint allowlist**. A BYO Ollama endpoint
    (in-cluster Service or a LAN/remote host) is an **allowlisted egress target**; default-deny holds.
  - **§5.1 (r26, ISI-2188)** — the `Agent` CRD carries **`modelEndpointRef?`** (→ Secret), added at
    Gate 2 for exactly this story (the 5.7-flagged gap, now closed). Plus `model`, `fallbackModel?`.
- **Companion design (consumed, not re-specified):** **`docs/bmad/design/agent-shim-interface-spec.md`
  (ISI-2114)** — the `byoModelEndpoint` capability flag on the Agent Card (§5/§6), and the **conformance
  Ollama lane** (§12) that runs C1–C10 with the model resolved to a BYO Ollama endpoint (task-in → run →
  artifacts-out, $0) — the ship-gate.
- **Depends on:**
  - **Story 5.8** (ISI-2220 — the `opencode` shim, the concrete `byoModelEndpoint`-capable reference
    runtime that rides the OpenAI-compatible wire to `…:11434/v1`). **Reference-runtime dependency.**
  - **Story 5.6 / ISI-2114** (the conformance harness + Ollama lane — the $0 ship-gate proving an
    Ollama-backed runtime passes task-in → run → artifacts-out). **Hard gate.**
  - **Story 7.5** (§11 third story — the BYO-endpoint credential *shape* this story mounts). **Hard
    dependency for the credential-isolation AC.** No spike gate (no OAuth).
  - **Story 1.2** (ISI-2188 — `Agent.spec.modelEndpointRef` field; landed at Gate 2). **Satisfied.**
  - **Story 4.6** (ISI-2212, §12.2 — the default-deny egress + model-endpoint allowlist this story adds
    the endpoint to). **Hard dependency for the egress AC.**
  - **Story 5.1** (ISI-2213 — the runtime-agnostic dispatch client that drives the resolved target
    unchanged). **Hard dependency.**
- **Blocks / is consumed by:** the **$0 Ollama CI/e2e lane** (ISI-2157 / Epic 14.8 — full-squad e2e with
  no paid API credits), **Story 5.9** (the model-window token budget keyed to the resolved endpoint),
  and every future BYO-endpoint Agent (this is the template for pointing a squad at any
  OpenAI-compatible server).

## The model-endpoint seam contract (authoritative)

### §A — Model axis ≠ runtime axis: BYO Ollama is an override, not a runtime (the moat, AC1 / ADR-026)

A BYO-Ollama `Agent` names an **ordinary** `AgentRuntime.type` (opencode by default) via `runtimeRef`
and expresses the model backend as **`Agent.spec.model` + `Agent.spec.modelEndpointRef`** (a per-user
Secret resolving an OpenAI-compatible endpoint URL [+ optional token]). At dispatch, the control-plane
resolver produces a dispatch target = **(the runtime's existing type-keyed image) + (the
Secret-resolved base-URL) + (the model name)**. The **runtime-type registry gains no `ollama` entry**,
**no new image is built** (the image is keyed by `type` only — the same opencode image serves every
endpoint it is pointed at), and **the core dispatch path adds no `type`-branch**. Registering
`type: ollama`, or building an `ollama` image, is the **ADR-026 category error** — a new runtime
surface where the architecture says there is only a model-endpoint override.

### §B — OpenAI-compatible wire; the endpoint is CONFIG, not baked in (AC2)

The resolved runtime rides the **OpenAI-compatible wire** (base-URL + model, e.g. opencode's provider
against `http://…:11434/v1`) to the resolved endpoint. The endpoint is **configuration layered on the
image at dispatch**, never compiled in: the **same** runtime image retargets a **paid** provider by
swapping only the resolved base-URL — one image, many endpoints. A shim that **hardcodes** its base-URL
cannot be retargeted (the Ollama Agent and the paid Agent, same image, would reach the same endpoint),
so retargeting would demand a new image — the "no new image, endpoint is config" claim broken.

### §C — Capability-negotiated, honest gap routed AROUND pre-dispatch (AC3, FR-D4/§10.1)

A runtime advertises **`byoModelEndpoint`** on its **own honest Agent Card** (Story 5.2) iff it can
accept an OpenAI-compatible base-URL override. The core routes a BYO-endpoint Agent **only** onto a
runtime that advertises it, and routes the Agent **around** a runtime that does **not** — **pre-dispatch**
(Story 5.2's honesty contract), never dispatch-then-fail. Because local models are weaker (§10.3
*Honesty*), a runtime that cannot honor the override must **not fail silently mid-Run** — the gap is
declared on the card and caught before dispatch. Assuming every runtime is byoModelEndpoint-capable
re-introduces the per-model special-casing the capability flag exists to eliminate.

### §D — Credential lock reinforced: per-user Secret, no shared platform endpoint (AC4, §11 third story)

The endpoint URL (+ optional token) is drawn from the Agent's **own** `modelEndpointRef` per-user
Secret (the §11 third-story shape — static, no OAuth). There is **no shared platform endpoint** and
**no shared master credential** (FR-G1 LOCKED): two BYO-endpoint Agents resolve **distinct** endpoints
from **distinct** Secrets, and a **cross-principal** endpoint-Secret read is **rejected** (§9.1
least-privilege). Rotation = Secret update; an unreachable endpoint surfaces via pause/resume (Story
7.4/7.5), not an opaque failure. A shared platform-default fallback (used when no ref is set) collapses
every Agent onto one endpoint — the exact vendor-lock §11 forbids, reopened on the model axis.

### §E — Default-deny egress holds; the endpoint is allowlisted (AC4, §12.2)

The resolved BYO endpoint host joins the Team **model-endpoint allowlist** on the NetworkPolicy (Story
4.6). **Default-deny still holds**: the allowlisted endpoint is reachable and every **un-allowlisted**
host is **blocked**. The BYO seam does **not** relax egress to "allow-all" so the endpoint "just works"
— that would turn the model-endpoint override into an exfil hole around the §12.2 default-deny. A
LAN/remote Ollama host joins the allowlist exactly like any other provider endpoint.

## Acceptance Criteria

**AC1 — BYO Ollama is a model-endpoint OVERRIDE, not a runtime: no new `type`, no new image, zero core change (the moat / ADR-026).**
Given an `Agent` with `runtimeRef` → an **ordinary** runtime (opencode by default, Story 5.8),
`Agent.spec.model` set, and `Agent.spec.modelEndpointRef` → a per-user Secret (BYO Ollama /
OpenAI-compatible endpoint), When a Run dispatches, Then the control-plane resolver produces a dispatch
target using the runtime's **existing type-keyed image** + the **Secret-resolved endpoint** + the
model — with **no `ollama` entry added to the runtime-type registry**, **no new image built**, and **no
`type`-branch added to the core dispatch path**; And the same runtime-agnostic Story-5.1 client drives
the target unchanged. Registering `type: ollama` or building an `ollama` image is the **ADR-026 category
error** — a correctness/architecture failure, not a style nit.

**AC2 — OpenAI-compatible wire; the endpoint is config, so the same image retargets a paid provider unchanged.**
Given a BYO-Ollama Agent and a paid-provider Agent that both name the **same** runtime type (opencode),
When each Run dispatches, Then both resolve to the **same** runtime image and each rides the
**OpenAI-compatible wire** to its **own** resolved base-URL — **distinct** endpoints from **one** image
— proving the endpoint is **configuration**, not baked in; And swapping an Agent's `modelEndpointRef`
retargets it with **no image change**. A shim with a hardcoded base-URL that reaches the same endpoint
regardless of the Agent's resolved endpoint is a defect (it would demand a new image per endpoint).

**AC3 — capability-negotiated; a runtime lacking `byoModelEndpoint` is routed AROUND pre-dispatch, never failed mid-Run.**
Given each runtime's **own** honest Agent Card (§10.1/FR-D4), When the core routes a BYO-endpoint Agent,
Then it dispatches **only** onto a runtime that advertises `byoModelEndpoint`, and routes the Agent
**around** a runtime that does **not** — **pre-dispatch** (Story 5.2), **never** dispatching then
failing silently mid-Run on a model the runtime cannot retarget; And a runtime that only speaks a fixed
vendor endpoint honestly advertises the gap rather than being assumed capable. Assuming every runtime is
byoModelEndpoint-capable (dispatch-then-fail) is the failure §10.3 *Honesty* forbids.

**AC4 — per-user credential (no shared master) + default-deny egress preserved (allowlisted endpoint); conformance Ollama lane is the ship-gate.**
Given the Agent's `modelEndpointRef` per-user Secret (§11 third story), When a Run dispatches, Then the
endpoint is drawn from **that** Agent's own Secret — **no shared platform endpoint, no shared master**
(FR-G1) — two BYO Agents resolve **distinct** endpoints and a **cross-principal** endpoint-Secret read
is **rejected** (§9.1); And the resolved endpoint host joins the **model-endpoint allowlist** with
**default-deny still holding** (§12.2) — an **un-allowlisted** host is **blocked**; And an
**Ollama-backed runtime passes the conformance Ollama lane** (Story 5.6 / ISI-2114 — task-in → run →
artifacts-out, **zero paid credits**), the §21 ship-gate that lets the BYO-Ollama claim be **proven**.
A shared platform endpoint or an allow-all egress is the vendor-lock / exfil hole §11/§12.2 forbid.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/byo-model-endpoint-check.py` — stdlib-only, `python3` it directly. A
**differential** falsification (same shape as the Story 5.5 / 5.1 / 2.9 checks): every property runs a
NAIVE/cheating design that MUST break (teeth) alongside the conformant design that MUST hold. If a naive
arm stops breaking, the check fails **loud** — the clean conformant result would then prove nothing.

- **(M) model≠runtime axis (AC1, ADR-026).** A **conformant** resolver turns a BYO-Ollama Agent into a
  dispatch target on an **ordinary** runtime (opencode) with a model-endpoint override — the runtime
  registry gains **no** `ollama` type and **no** new image. A **naive** design commits the category
  error: `type: ollama` in the registry + a new `shims/ollama` image. *Mutation-proven:* making the
  conformant resolver synthesise `type: ollama` (register the type + image) → **RED**.
- **(W) OpenAI-compatible wire, endpoint is config (AC2).** The **same** opencode image resolves an
  Ollama Agent and a paid Agent to **distinct** base-URLs (config, not baked in). A **naive** shim
  hardcodes its base-URL so both — same image — reach the **same** endpoint. *Mutation-proven:* baking a
  fixed base-URL into the conformant shim collapses the two endpoints to one → **RED**.
- **(N) capability-negotiated + honest gap (AC3, FR-D4).** opencode advertises `byoModelEndpoint:true`
  and resolves cleanly; a `fixedvendor` runtime advertises `false` and a BYO-endpoint Agent is routed
  **around** it pre-dispatch. A **naive** core assumes every runtime is capable → dispatches the
  un-retargetable runtime → mid-Run failure. *Mutation-proven:* making the conformant resolver assume
  every runtime is byoModelEndpoint-capable dispatches the un-runnable Agent → **RED**.
- **(C) credential lock reinforced (AC4, §11).** Each Agent resolves its endpoint from its **own**
  per-user Secret; two Agents get **distinct** endpoints and a cross-principal read is **rejected**. A
  **naive** design falls back to a **shared platform endpoint**, collapsing every Agent onto one master.
  *Mutation-proven:* making the conformant resolver ignore the per-user ref for a shared platform
  default collapses the endpoints → **RED**.
- **(E) default-deny egress holds (AC4, §12.2).** The resolved endpoint host joins the allowlist and an
  un-allowlisted host is **blocked**. A **naive** allow-all egress reaches the un-allowlisted host.
  *Mutation-proven:* flipping the conformant egress to allow-all reaches the exfil host → **RED**.

Exits non-zero if BYO Ollama is modeled as a runtime type / new image, the endpoint is baked into the
image, the core assumes every runtime is byoModelEndpoint-capable, a shared platform endpoint appears
(or a cross-principal Secret read is accepted), or egress opens allow-all. **All five headline
invariants are mutation-checked** (baseline exit 0; each `--mutate=<M|W|N|C|E>` exit 1) — verified
2026-08-13. Models the resolve/dispatch/egress seam in-process; real-runtime promotion rides the
ISI-2114 conformance Ollama lane (§12, Story 5.6) — the §21 gate that lets the BYO-Ollama claim be
*proven* (task-in → run → artifacts-out, $0).

## Out of scope (owned elsewhere)

- **The `opencode` runtime shim itself** (Story 5.8 / ISI-2220 — the concrete `byoModelEndpoint`-capable
  runtime that speaks the OpenAI-compatible wire to `…:11434/v1`; this story *consumes* it as the
  default reference runtime and is otherwise runtime-agnostic). **The shim's six-verb contract, SSE
  schema, Agent-Card schema, the `byoModelEndpoint` capability-flag definition, and the conformance
  suite C1–C10 + Ollama lane** (ISI-2114 / Story 5.6 — this story *reads* the card and *requires* the
  lane green as the ship-gate). **The BYO-endpoint credential *model*** (Story 7.5 / §11 third story —
  the per-user Secret shape is mounted, not defined here; rotation + pause/resume live there). **The
  `Agent.spec.modelEndpointRef` CRD field** (Story 1.2 / ISI-2188 — landed at Gate 2, resolved here).
  **The default-deny egress + model-endpoint allowlist mechanism** (Story 4.6 / §12.2 — this story adds
  the endpoint host to it, does not build it). **The runtime-agnostic dispatch client** (Story 5.1 —
  drives the resolved target unchanged, not rebuilt). **The model-window token budget** (Story 5.9 /
  §8.5/§10.3 — `contextWindow` keyed to the resolved endpoint, owned there). **The rate-limit fallback /
  mid-Run model switch** (`Agent.spec.fallbackModel`, §8 tier 1 / ADR-030/031 — reuses this seam's
  override machinery re-resolved live, not built here). This story ships the **model-endpoint seam**:
  the control-plane resolve from `Agent` (`model` + `modelEndpointRef`) to an *ordinary* runtime + a
  Secret-resolved OpenAI-compatible base-URL — no new type, no new image, no core branch, honest
  capability negotiation, per-user credential, default-deny egress preserved — the §10.3 / ADR-026 /
  FR-D4 model-provider seam that doubles as the $0 CI/conformance lane.
