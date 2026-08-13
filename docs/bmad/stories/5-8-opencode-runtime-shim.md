# Story 5.8: the `opencode` runtime shim (v1) — a real A2A Run against local Ollama at $0, paid providers unchanged

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE *CONCRETE OLLAMA RUNTIME* OF THE v1 SHIM SET (arch §10.1/§10.3, ADR-026, FR-D3/FR-D4).**
> Story 5.7 owns the *control-plane model-endpoint **seam*** — resolve an `Agent` (`model` +
> `modelEndpointRef`) into an ordinary runtime + a Secret-resolved base-URL. **This story ships the
> *runtime that actually speaks the wire*: `opencode` (`shims/opencode`) — the third member of the v1
> shim set {OpenClaw, Hermes, opencode}, pulled forward from Phase 2 (CEO 2026-08-11, ratified by
> board ISI-2131).** Given an `AgentRuntime` of `type: opencode` whose `Agent` sets `modelEndpointRef`
> → an Ollama endpoint + `model`, opencode drives a **real A2A Run** against that local model via its
> **OpenAI-compatible provider** (`baseURL …:11434/v1`) with **zero paid credential**, **passes the
> conformance Ollama lane** (Story 5.6 / ISI-2114), **and runs paid providers unchanged** (the endpoint
> is config, not baked in). The load-bearing invariant is **"opencode is a real, self-contained
> `byoModelEndpoint`-capable runtime that *actually executes* a Run against the resolved endpoint — not
> a facade, not a re-skin, and not a special core branch."** A shim that is secretly a **facade
> forwarding SubmitTask to another runtime's gateway** (so opencode never runs), that **silently routes
> the local Run to a paid vendor** or **attaches a paid key** (breaking the $0 claim), that
> **special-cases Ollama vs paid** so only one route works, that **advertises `byoModelEndpoint` but
> ignores the override** and dials a baked-in host (a dishonest capability / silent mid-Run failure),
> or that passes a **conformance lane with no teeth** (a vacuous green) — **is a leak.** Not a style
> preference: it is the exact per-runtime coupling NFR-EXT1 forbids and the §10.3 *Honesty* failure the
> capability flag exists to eliminate. Read AC1 literally.

## ⚠️ Scope reconciliation — 5.8 vs 5.7 vs 5.6/ISI-2114 vs 5.5 vs 5.1 (read first, they interlock on purpose)

The originating issue (ISI-2220) says *"Given `AgentRuntime type:opencode`, When an `Agent` sets
`modelEndpointRef` → Ollama + model, Then the opencode shim runs a real A2A Run against the local model
via the OpenAI-compatible provider, zero paid credential, passes the conformance Ollama lane. Also runs
paid providers unchanged. `shims/opencode`."* Several neighbours build the surrounding machinery;
**this story owns exactly the concrete `opencode` shim** and consumes the rest:

| Concern | Owned by | This story does |
|---|---|---|
| The **control-plane model-endpoint *seam*** — resolve `Agent` (`model` + `modelEndpointRef`) → an ordinary runtime + a Secret-resolved base-URL; no new `type`, no new image, zero core change | **Story 5.7** (ISI-2219) | **consumes** the resolved `DispatchTarget`; opencode is the default `byoModelEndpoint`-capable runtime the seam targets |
| The **shim's six-verb contract, SSE schema, Agent-Card schema, `byoModelEndpoint` flag definition, conformance suite C1–C10 + Ollama lane** | **ISI-2114** (`design/agent-shim-interface-spec.md`) | **implements** the contract for opencode; **runs green** on C1–C10 + the Ollama lane |
| The **conformance *harness* + Ollama lane** (same C1–C10 assertions with the model resolved to a BYO Ollama endpoint — task-in → run → artifacts-out, $0) | **Story 5.6** (ISI-2218) | **is the runtime that DRIVES that lane** (the $0 CI-lane driver, ISI-2157); does not build the harness |
| The **heterogeneous co-residency proof** — two different-`type` runtimes in one squad, both real, no facade | **Story 5.5** (ISI-2217, OpenClaw + Hermes) | **adds the third runtime** to the set; the same non-facade / no-core-branch discipline applies to opencode |
| The **runtime-agnostic core dispatch client** (no `type` branch, C10) | **Story 5.1** (ISI-2213, `internal/a2a`) | **is driven by** it unchanged — opencode is a black box behind the same six-verb surface |
| The **Agent Card generation** from each `Agent`/`AgentRuntime` | **Story 5.2** (ISI-2214, §10.1) | **exposes opencode's own honest card** (`byoModelEndpoint:true`, `credentialLifecycle:static`) — never borrows another runtime's caps |
| The **BYO-endpoint credential *shape*** (per-user Secret ref: endpoint URL [+ optional token]) | **Story 7.5** (§11 third story) | **mounts** that Secret shape via the resolved target; does not define it |
| The **default-deny egress + model-endpoint allowlist** | **Story 4.6** (ISI-2212, §12.2) | **dials** the allowlisted endpoint; egress policy is owned there |
| The **model-window token budget** (`contextWindow` keyed to the resolved model — Ollama ~8K) | **Story 5.9** (ISI-2221, §8.5/§10.3) | **out of scope** — the budget rides the resolved endpoint, owned there |

**One-line boundary:** Story 5.7 ships *the seam that resolves the target*; Story 5.6/ISI-2114 build
*the conformance lane that proves it*; Story 5.5 proves *heterogeneous co-residency*. **This story
ships *the concrete `opencode` runtime* that speaks the OpenAI-compatible wire to a local Ollama model
at $0, passes the conformance Ollama lane, and runs paid providers unchanged from one image — a real,
self-contained, honestly-advertised runtime with no facade and no core branch.**

> **⚠️ Cite correction (the epic's `Arch §7.5` is stale).** The 04-epics-and-stories.md rows for
> Epic 5 cite *"Arch §7.5, §11.2 (`shims/…`)"*. **§7.5 is the per-Project *Discussion Room*, not the
> shim/model architecture** (the same stale-pointer class flagged on ISI-2212/ISI-2189/ISI-2217/5.7).
> The governing architecture for this story is **§10.1 "Shim placement & contract"** (the six MUST-verbs,
> capability flags, one shim per runtime), **§10.3 "Model-provider seam — BYO endpoints & Ollama"** (the
> OpenAI-compatible wire, `byoModelEndpoint`, the $0 lane, ADR-026), and **design
> `agent-shim-interface-spec.md` §9/§10/§12** (the shim skeleton + conformance suite + Ollama lane).
> This story targets **§10.1/§10.3 + ADR-026 + design §9/§10/§12**, not §7.5.

## Story

As **the KSquad platform proving the v1 shim set is complete and the "$0, zero-core-change Ollama"
claim (ISI-2157) is real end-to-end**, I want **a concrete `opencode` runtime shim (`shims/opencode`)
that — given a resolved `DispatchTarget` (an Ollama `…:11434/v1` base-URL + `model`, from Story 5.7) —
runs a *real A2A Run* against that local model via opencode's OpenAI-compatible provider with *zero
paid credential*, implements the six A2A MUST-verbs itself (SubmitTask → SSE progress → EmitArtifact,
each artifact stamped `produced_by: opencode`) driven by the runtime-agnostic Story-5.1 client with
*no* `type:opencode` branch in the core, advertises its *own honest* Agent Card (`byoModelEndpoint:true`
that it *actually honors* by dialing the resolved override, `credentialLifecycle:static`), retargets a
*paid* provider unchanged by swapping only the resolved endpoint+token config (one image, many
endpoints), and passes the conformance Ollama lane (Story 5.6 / ISI-2114 — task-in → run →
artifacts-out, $0)**, so that **"opencode covers Ollama through a concrete, natively-compatible OSS
runtime" is met not as a naming convention but as a structural guarantee: a squad runs on a self-hosted
local model with zero paid credits, opencode is the driver for the $0 CI/E2E lane (ISI-2157 / Epic
14.8), and the facade / dishonest-capability / vacuous-conformance failure modes are impossible to
commit accidentally — the §10.1/§10.3 / FR-D3/FR-D4 / NFR-EXT1 shim contract instantiated for the
cheapest runtime to stand up (OSS + local model + no OAuth).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-D1/D2** (southbound A2A; one shim per runtime), **FR-D3**
  (heterogeneous runtimes in one squad), **FR-D4** (capability flags first-class — `byoModelEndpoint`),
  **FR-D5** (conformance suite — the Ollama-lane ship-gate), **NFR-EXT1/EXT2** (zero-core-change
  extensibility), **FR-G1/G2** (per-user Secret refs; credential lifecycle = capability metadata).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§10.1 "Shim placement & contract"** — one shim per runtime, sidecar, six MUST-verbs; capability
    flags first-class; the core negotiates against each honest card and never special-cases a runtime
    (C10). opencode is a v1 shim alongside OpenClaw + Hermes.
  - **§10.3 "Model-provider seam — BYO endpoints & Ollama" (ISI-2157, r8)** — opencode rides the
    **OpenAI-compatible wire** (`baseURL …:11434/v1`) to a resolved endpoint; `byoModelEndpoint` is the
    capability; the Ollama lane is the **$0 CI lane**. **Honesty:** local models are weaker — the lane
    proves correctness/plumbing e2e + conformance, **never a production quality bar**.
  - **ADR-026** — BYO model-provider seam / opencode pulled from Phase 2 into v1; Ollama on the model
    axis (not an `AgentRuntime.type`).
- **Companion design (consumed, not re-specified):** **`docs/bmad/design/agent-shim-interface-spec.md`
  (ISI-2114)** — the six-verb contract (§3), Agent Card schema + `byoModelEndpoint` flag (§5/§6), the
  reference shim skeleton (§9), and the conformance suite C1–C10 + **Ollama lane** (§12).
- **Depends on:**
  - **Story 5.7** (ISI-2219 — the control-plane resolve producing the `DispatchTarget` opencode
    consumes). **Seam dependency.**
  - **Story 5.6 / ISI-2114** (the conformance harness + Ollama lane opencode runs green on — the
    ship-gate). **Hard gate.**
  - **Story 5.1** (ISI-2213 — the runtime-agnostic dispatch client that drives opencode unchanged).
    **Hard dependency.**
  - **Story 5.2** (ISI-2214 — Agent Card generation; opencode exposes its own honest card).
  - **Story 7.5** (§11 third story — the BYO-endpoint credential *shape* opencode mounts). No OAuth ⇒
    no spike gate (cheapest runtime to stand up).
  - **Story 4.6** (ISI-2212, §12.2 — the allowlisted egress opencode dials).
- **Blocks / is consumed by:** the **$0 Ollama CI/E2E lane** (ISI-2157 / Epic 14.8 — full-squad E2E
  with no paid API credits, driven by opencode), **Story 5.7's reference-runtime AC** (opencode is its
  default `byoModelEndpoint`-capable runtime), and every future BYO-Ollama Agent.

## The opencode shim contract (authoritative)

### §A — opencode is a real, self-contained runtime — no facade, no core branch (AC1, S6 / §10.1 / C10)

The opencode shim implements the six A2A MUST-verbs **itself** and translates to opencode-native
execution. A SubmitTask drives a genuine run lifecycle → SSE progress → EmitArtifact, each artifact
stamped `produced_by: opencode`. The runtime-agnostic Story-5.1 client drives it as a **black box** —
**no `type:opencode` branch** exists in the core, coord services, or the shared coordination record
(C10). A shim that **forwards SubmitTask to another runtime's gateway** (openclaw/hermes/a paid vendor)
is a **facade**: opencode never actually executes and the artifact stamp collapses to the other runtime
— the "opencode ran a real Run" claim faked.

### §B — Ollama over the OpenAI-compatible wire, at $0 (AC1, §10.3)

Given a resolved Ollama endpoint (`http://…:11434/v1`) + `model` (e.g. `qwen3`/`llama3`/`deepseek`),
opencode dials **that** endpoint over its **OpenAI-compatible provider** with **no paid credential** in
the request path (a keyless local Ollama endpoint spends $0). Routing the local Run to a paid vendor,
or attaching a paid API key, spends the credits the Ollama lane exists to avoid (the ISI-2157 $0 claim
broken).

### §C — Paid providers unchanged; the endpoint is CONFIG (AC2)

The **same** opencode shim (same image, same code path) runs a **paid-provider** Agent by swapping
**only** the resolved endpoint + token config — no `opencode` variant, no second image, no Ollama-only
internal path. One image, many endpoints. A shim that **special-cases Ollama vs paid** so only one
route works breaks the "runs paid providers unchanged" claim.

### §D — Honest card that actually honors the override (AC1, FR-D4 / §10.1)

opencode's **own** Agent Card advertises `byoModelEndpoint: true` (it natively accepts an
OpenAI-compatible base-URL override) and `credentialLifecycle: static` (no vendor OAuth). The
capability is **not a lie**: a BYO submit **really dials the resolved override base-URL**. A shim that
advertises the flag `true` but **ignores the override** and dials a **baked-in host** commits a silent
mid-Run failure on a capability it claimed — the §10.3 *Honesty* violation the flag exists to prevent.

### §E — The conformance Ollama lane is the ship-gate — with teeth (AC1/AC2, C1–C10 / Story 5.6)

opencode passes the conformance Ollama lane (Story 5.6 / ISI-2114 §12 — C1–C10 with the model resolved
to a BYO Ollama endpoint, task-in → run → artifacts-out, $0). The lane's pass is gated on **real
evidence**: a Run executed **by opencode**, artifacts were **produced**, SSE **progressed**, and **zero
paid credits** were spent. A lane that reports "pass" **without** asserting execution/artifacts/$0 is a
**vacuous green** (the ISI-2346-F1 / ISI-2218-F1 teeth-loss pattern) that would rubber-stamp a shim
that never ran.

## Acceptance Criteria

**AC1 — opencode runs a REAL A2A Run against a local Ollama model at $0 — self-contained, honest, no facade, no core branch (the moat).**
Given an `AgentRuntime` of `type: opencode` whose `Agent` sets `modelEndpointRef` → a per-user Secret
(Ollama `…:11434/v1`) + `model`, When a Run dispatches, Then the opencode shim — driven by the
runtime-agnostic Story-5.1 client with **no `type:opencode` core branch** (C10) — implements the six
A2A MUST-verbs **itself**, dials the **resolved** Ollama endpoint over its **OpenAI-compatible
provider** with **zero paid credential**, and produces artifacts stamped `produced_by: opencode`
(task-in → run → artifacts-out); And opencode's **own honest** Agent Card advertises `byoModelEndpoint:
true` that it **actually honors** (dialing the resolved override, not a baked-in host). A **facade**
forwarding SubmitTask to another runtime's gateway, a **paid credential** spent on the local Run, or a
**dishonest** capability (advertised but not honored) is a correctness/architecture failure, not a
style nit.

**AC2 — opencode runs paid providers unchanged — one shim, the endpoint is config.**
Given a BYO-Ollama Agent and a paid-provider Agent that both name `type: opencode`, When each Run
dispatches, Then the **same** opencode shim runs both by swapping **only** the resolved endpoint+token
config — **one image, distinct endpoints** — proving the endpoint is **configuration**, not baked in;
And swapping an Agent's `modelEndpointRef` retargets it with **no image change**. A shim that
special-cases Ollama vs paid so the paid Run breaks is a defect.

**AC3 — opencode passes the conformance Ollama lane (the ship-gate) — and the lane has teeth.**
Given the Story 5.6 / ISI-2114 conformance Ollama lane (C1–C10 with the model resolved to the BYO
Ollama endpoint), When opencode runs it, Then it **passes** at **zero paid credits** (task-in → run →
artifacts-out); And the lane's pass is gated on **real evidence** — a Run **executed by opencode**,
artifacts **produced**, **$0** — so a shim that produced no artifacts or spent a paid credential
**fails** the lane. A lane that reports pass without that evidence (a vacuous green) is the ISI-2346-F1
/ ISI-2218-F1 teeth-loss defect.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/opencode-shim-check.py` — stdlib-only, `python3` it directly. A **differential**
falsification (same shape as the Story 5.7 / 5.5 / 5.1 checks): every property runs a NAIVE/cheating
design that MUST break (teeth) alongside the conformant design that MUST hold. If a naive arm stops
breaking, the check fails **loud** — the clean conformant result would then prove nothing.

- **(O) Ollama over the OpenAI-compatible wire, $0 (AC1, §10.3).** The conformant shim dials the
  resolved Ollama `…:11434/v1` endpoint and spends **zero** paid credentials. A naive shim routes the
  local Run to a paid vendor + attaches a paid key. *Mutation-proven:* `--mutate=O` → the shim dials a
  paid host / spends a credential → **RED**.
- **(P) paid provider unchanged, one shim (AC2).** The **same** opencode shim runs a paid Agent by
  config alone. A naive Ollama-only shim breaks the paid Run. *Mutation-proven:* `--mutate=P` makes the
  conformant shim Ollama-only → the paid Run fails → **RED**.
- **(V) six-verb real Run, no facade, no core branch (AC1, S6 / §10.1 / C10).** SubmitTask → run
  lifecycle → SSE → artifacts stamped `opencode`, driven by the runtime-agnostic client. A naive facade
  forwards to another runtime's gateway → the stamp collapses. *Mutation-proven:* `--mutate=V` makes the
  shim forward to an OpenClaw gateway → `executed_by != opencode` → **RED**.
- **(H) honest card honors the override (AC1, FR-D4).** opencode advertises `byoModelEndpoint:true` AND
  dials the resolved override. A naive shim advertises true but dials a baked-in host. *Mutation-proven:*
  `--mutate=H` bakes in a host so the advertised capability is not honored → **RED**.
- **(G) conformance Ollama lane has teeth (AC3, Story 5.6).** The lane passes the real shim and **fails**
  a shim that produced no artifacts or spent a paid credit. A naive lane rubber-stamps the cheat.
  *Mutation-proven:* `--mutate=G` guts the lane's evidence checks → the vacuous shim "passes" → **RED**.

Exits non-zero if opencode is a facade, spends a paid credential on the local Run, special-cases Ollama
vs paid, advertises a capability it does not honor, or the conformance lane loses its teeth. **All five
headline invariants are mutation-checked** (baseline exit 0; each `--mutate=<O|P|V|H|G>` exit 1) —
verified 2026-08-13. Models the shim's submit/stream/artifact surface in-process; real-runtime
promotion rides the ISI-2114 conformance Ollama lane (§12, Story 5.6) — a live `opencode` container
against a real `ollama serve` (`ollama launch opencode`), task-in → run → artifacts-out at $0 — the §21
gate that lets the "opencode ran a real Run against a local model" claim be *proven*.

## Out of scope (owned elsewhere)

- **The control-plane model-endpoint *seam*** (Story 5.7 / ISI-2219 — resolve `Agent` →
  `DispatchTarget`; this story *consumes* the target). **The six-verb contract / SSE / Agent-Card
  schema / conformance suite C1–C10 + Ollama lane definition** (ISI-2114 / Story 5.6 — this story
  *implements* the contract for opencode and *runs green*, does not define the schema or build the
  harness). **The BYO-endpoint credential *model*** (Story 7.5 / §11 third story — the per-user Secret
  shape is mounted, not defined here). **The `Agent.spec.modelEndpointRef` CRD field** (Story 1.2 /
  ISI-2188). **The default-deny egress + model-endpoint allowlist** (Story 4.6 / §12.2 — opencode dials
  the allowlisted endpoint). **The runtime-agnostic dispatch client** (Story 5.1 — drives opencode
  unchanged). **The heterogeneous co-residency proof** (Story 5.5 — opencode is the third runtime in the
  set, but the S6 two-runtimes acceptance is proven there). **The model-window token budget** (Story 5.9
  / §8.5/§10.3). This story ships **the concrete `opencode` runtime shim**: a real, self-contained,
  honestly-advertised `byoModelEndpoint`-capable runtime that dials a local Ollama model over the
  OpenAI-compatible wire at $0, runs paid providers unchanged from one image, and passes a
  conformance Ollama lane that has teeth — the §10.1/§10.3 / ADR-026 shim contract instantiated.
