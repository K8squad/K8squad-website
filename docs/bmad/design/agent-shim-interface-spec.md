---
title: Agent Shim Interface — API Spec + Reference Shim (OpenClaw)
issue: ISI-2114
owner: Architect (Winston)
status: build-ready
epic: relates to §21 spike-gate (S5/S6 conformance); feeds ISI-2112 (creds), ISI-2113 (runtime), ISI-2157 (Ollama lane)
architectureRefs: [§10.1, §10.2, §10.3, §5.3, §6.1, §6.4, §6.5, §8.5, §11, §12.2, §17.2, ADR-008, ADR-009, ADR-026, FR-D1..D5, FR-G1..G3, NFR-EXT1, NFR-EXT2, R3, R11]
date: 2026-08-12
supersedes: none (elaborates 03-architecture.md §10 into an implementable contract)
revisions:
  - r1 (2026-08-12, ISI-2114): initial build-ready shim interface spec + OpenClaw reference shim
    skeleton + conformance suite spec. No new architectural decision; pins §10 intent to a buildable
    contract. Buildable reference shim + conformance harness delegated as a child spike issue.
---

# Agent Shim Interface — API Spec + Reference Shim (ISI-2114)

> **Purpose.** The architecture (`03-architecture.md` §10, ADR-008/009/026) already decided *what* the
> shim is — **one sidecar per runtime** that terminates **A2A southbound**, translates to the runtime's
> native invocation, streams **SSE progress**, and emits **artifacts** to the coordination record, with
> the **Agent Card generated from the CRD**. This document pins that decision to a **buildable contract**:
> the exact A2A verbs the shim MUST implement, the SSE event schema, the artifact-emission contract, the
> Agent Card JSON schema and its CRD→card mapping, the credential-injection contract, the auth-failure
> pause signal, and the **conformance suite** that gates S5/S6 — plus a **reference shim for OpenClaw**.
> **No new architectural decision is made here; nothing below reopens a locked decision.** Where this
> spec would extend architecture, it defers to a spike issue rather than inventing.

Answering ISI-2114's question — *what is the minimal shim contract that lets Squad drive heterogeneous
agent runtimes via A2A?* — the answer is the **six MUST-verbs of §3**, the **Agent Card of §6**, and the
**conformance suite of §12**. Everything else is per-runtime translation the core never sees.

## 1. Scope & non-goals

**In scope (the contract every conformant shim MUST satisfy):**
1. A2A southbound task lifecycle (submit / dedup / cancel / status), workspace-local invocation.
2. SSE progress streaming from runtime-native events → A2A task events.
3. Artifact emission to the coordination record (`coord.artifact`), idempotent under re-entry.
4. Agent Card generation from `Agent` CRD + resolved `AgentRuntime` (skills, model, auth, capabilities).
5. Credential injection: env-from-Secret-ref, no inline secrets, auth-failure → pause signal.
6. Capability negotiation, incl. the `byoModelEndpoint` model-provider seam (§10.3).

**Non-goals (owned elsewhere, referenced not re-specified):**
- Claim/fence/lease semantics (§6.1–6.4) — the shim is a *consumer* of the deterministic `a2a_task_id`,
  it does not own coordination. Fencing is enforced at the memory/artifact services, not in the shim.
- Context envelope *assembly* (§8.5) — assembled by the control plane; the shim only *transports* it as
  the task's system/context input.
- Metering *authority* (§11) — the shim surfaces best-effort token counts; run-minutes/resource are the
  non-forgeable spine and live outside the sandbox trust boundary.
- The MCP northbound tool seam (`pkg/mcp`) — a sibling adapter, out of scope for this issue.

## 2. Placement, process model & lifecycle

- **Sidecar in the sandbox pod** (ADR-008). The agent runtime container and the shim container share the
  pod; the **workspace PVC is mounted into both** so the runtime's native invocation is workspace-local.
  The shim listens on `127.0.0.1:<a2aPort>` (pod-local only — never a Service; the control plane reaches
  it via the pod IP on the Team-namespace NetworkPolicy, §12).
- **One shim binary per runtime `type`.** The shim is built into (or co-scheduled with) the
  `AgentRuntime` image (§5.3.1). `AgentRuntime.type` ∈ {`openclaw`, `hermes`, `claude-code`, …} selects
  which reference/vendor shim ships in the image.
- **Lifetime = the Run.** The shim starts with the pod (`Claiming→Running`), serves exactly one Run
  (one `a2a_task_id = run_id`), and is torn down at Run completion/reclaim (§6.3, §9.3). It holds **no
  cross-Run state**; all durable state is in the coordination record.
- **Trust boundary.** The shim runs *inside* the sandbox trust boundary (F18) — it is not a control-plane
  component. Therefore the core treats everything the shim reports (status, tokens, artifacts) as
  **fence-validated at the receiving service**, never trusted on the shim's word (§6.3, §11).

## 3. A2A southbound contract — the six MUST-verbs

The core dispatches over the **pinned A2A rev** (`pkg/a2a@rev`, §10.2). The shim MUST implement these
six operations. Field names below are the *internal stable interface* the core speaks; the adapter maps
them to the pinned wire rev.

| # | Verb | Direction | Idempotency / semantics |
|---|------|-----------|-------------------------|
| V1 | `SubmitTask{a2a_task_id, envelope, credentials_ref_mounted, model_route}` | core → shim | **Deterministic id = `run_id`.** A second submit with an existing id **MUST reattach** to the in-flight task and MUST NOT start a second agent execution (§6.4 conformance requirement C1). |
| V2 | `StreamEvents{a2a_task_id}` → SSE | shim → core | Server-Sent Events; §4 schema. Re-`StreamEvents` after a dropped connection MUST resume from the last delivered `seq` (replay from the shim's in-memory ring; on shim restart the task is re-derived from the runtime session, see §11 note). |
| V3 | `GetStatus{a2a_task_id}` → `{state, reason, lastSeq}` | core → shim | Pull fallback for SSE; states in §3.1. Pure read, always safe. |
| V4 | `CancelTask{a2a_task_id, reason}` | core → shim | Idempotent: cancelling an already-terminal task is a no-op success. MUST stop the runtime and drain to a terminal state (`canceled`). Used by the reclaim protocol (§6.3). |
| V5 | `EmitArtifact` (shim-initiated, see §5) | shim → coord API | Upsert-keyed `UNIQUE(work_item_id, run_id, kind)` + `sha256` (§6.1). Idempotent under re-entry (§6.4 C2). |
| V6 | `GetAgentCard{}` → Agent Card JSON | core → shim | §6 schema. Pure read; published at shim startup and on demand. Drives capability negotiation. |

### 3.1 Task state machine (A2A task, distinct from the Run/work-item lifecycle)

```
submitted ──> working ──> (input-required?) ──> completed
     │            │             │
     │            │             └──> working        (interactive-prompt capability only)
     │            ├──> auth-required  ──────────────> (Run→Paused §11; not a task failure)
     │            └──> failed
     └──> canceled                                   (V4, terminal)
```

- `input-required` is **only reachable if the Agent Card advertises `interactivePrompt: true`**. A
  runtime without it MUST NOT emit `input-required`; the core routes around interactive prompts (§10.1).
- `auth-required` is a **first-class signal, not a failure** — it maps to the §11 pause path. This is a
  MUST: a shim that reports auth failures as generic `failed` breaks graceful pause/resume (FR-G3).
- Terminal states: `completed`, `failed`, `canceled`. Re-`SubmitTask` on a terminal task returns the
  terminal status (dedup), it does not restart.

## 4. SSE progress event schema (V2)

The shim streams the runtime's native progress as A2A task events over SSE. The console consumes these
via native `EventSource` (§17.2 — ponytail: no bespoke transport). Each event:

```json
{
  "seq": 42,                     // monotonic per task; used for resume + ordering
  "a2a_task_id": "run-7f3a…",    // == run_id
  "ts": "2026-08-12T09:14:03.221Z",
  "type": "status | message | tool | artifact-ref | usage | auth-required",
  "payload": { … }               // type-specific, below
}
```

| `type` | `payload` | Consumed by |
|--------|-----------|-------------|
| `status` | `{state, reason?}` — mirrors §3.1 | Run reconciler (§8), console status (FR-F2) |
| `message` | `{role, text, trust:"untrusted"}` — agent progress text | console progress stream; **agent text is untrusted** (F16) — never executed, only displayed |
| `tool` | `{name, phase:"start"|"result", ok?, summary?}` | console activity view; observability spans (§17.2) |
| `artifact-ref` | `{kind, work_item_id, uri, sha256}` — pointer to a §5 artifact already committed to `coord` | console build browser (§9.4), audit |
| `usage` | `{model, input, output, cacheRead?, cacheWrite?}` — **best-effort** token counts | metering (§11) — sanity-bounded, never authoritative |
| `auth-required` | `{provider, secretRef, detail}` | Run reconciler → Paused (§11) |

**Ordering & delivery.** `seq` is monotonic and gap-free per task; the core orders on `seq`, not wall
clock. Delivery is **at-least-once** — the console/reconciler dedup on `(a2a_task_id, seq)`. SSE, not
websockets, because the stream is one-directional server→client and `EventSource` is a native browser
primitive (ADR alignment with §17.2).

## 5. Artifact emission contract (V5)

Artifacts (code diffs, docs, handoff summaries §8.5) are posted to the coordination record via the A2A
task-lifecycle artifact channel → the apiserver `coord` API. **The shim does not write Postgres
directly** — it calls the fenced coord API, which validates the fence token inside the write txn (§6.3).

```
POST /coord/artifacts
{
  "work_item_id": "...",         // the item the Run holds
  "run_id": "...",               // == a2a_task_id
  "fence_token": "...",          // the Run's current fence (§6.2); server rejects if stale
  "kind": "diff | doc | handoff | log | build-snapshot",
  "content_sha256": "...",       // content-addressed (§6.1)
  "uri": "s3://…"                // object-store URI, durable only after the row commits
}
```

- **Idempotent upsert** on `UNIQUE(work_item_id, run_id, kind)` + `sha256` (§6.1, §6.4 C2) — a
  re-entered Collecting phase republishes the *same* content-addressed row, never a duplicate.
- **Fence-guarded** — a zombie shim that lost its lease (§6.3) is rejected by the coord API even if it
  still holds a valid object blob; the orphaned blob is unreferenced and GC'able.
- The handoff artifact `{did, decisions, next, blockers}` (§8.5) is `kind:"handoff"` — **knowledge
  transfer only**, it carries no custody (custody stays the fenced §6.2/6.3 release→re-dispatch→claim).

## 6. Agent Card — generation & schema

The Agent Card is the **capability contract** the core negotiates against (FR-D4). It is generated by
the shim at startup **from the `Agent` CRD + the resolved `AgentRuntime`** (§10.1) — the runtime is the
authority on its own capabilities; the CRD supplies identity, skills, model, and the credential shape.

### 6.1 Schema

```json
{
  "schemaVersion": "ksquad.a2a/v1",
  "agent": { "name": "backend-dev", "squad": "…", "project": "…" },
  "runtime": { "type": "openclaw", "cliVersion": "2026.2.9", "shimVersion": "1.0.0" },
  "model": { "id": "claude-opus-4-8", "contextWindow": 200000 },
  "skills": ["code", "review", "git"],
  "auth": { "type": "oauth-subscription | api-key | byo-endpoint", "secretRef": "agent-x-creds" },
  "capabilities": {
    "streaming": true,            // MUST be true (SSE V2 is mandatory)
    "toolCalls": true,
    "interactivePrompt": false,   // gates §3.1 input-required
    "byoModelEndpoint": true,     // §10.3 model-provider seam
    "artifactKinds": ["diff","doc","handoff","log","build-snapshot"],
    "docker": false, "github": true, "packageInstall": true  // operator flags (§5.3)
  }
}
```

### 6.2 CRD → Card mapping (normative)

| Card field | Source | Notes |
|------------|--------|-------|
| `agent.*`, `skills` | `Agent.spec` (name, squad/project owner refs, `skills`) | identity from the CRD |
| `runtime.type`, `cliVersion` | resolved `AgentRuntime.spec` (§5.3) | the image's runtime + pinned CLI |
| `model.id` | `Agent.spec.model` | per-Agent model (§10.3) |
| `model.contextWindow` | **runtime-declared** (resolved from model id) | budget authority for §8.5 — the Assembler enforces it, fail-closed |
| `auth.type`, `secretRef` | `Agent.spec.credentialSecretRef` + runtime's auth family (§11) | one of the three §11 stories |
| `capabilities.*` | **runtime-declared** + `Agent.spec.capabilityOverrides` | runtime is authority; overrides narrow, never widen beyond runtime support |

**Rule:** the core treats capability gaps as **declared capabilities, never special-cased hacks**
(§10.1). A runtime that can't stream tool calls advertises `toolCalls:false`; the core adapts. A
`capabilityOverride` that widens beyond runtime support is a **validation error** at Agent reconcile,
not a silent grant (mirrors the §8.5 `contextBudgetOverride` above-window rule).

## 7. Credential injection contract

Per §11 (FR-G1, LOCKED): **per-user Kubernetes Secret refs, env-injected, never inline.**

- The Run reconciler mounts `Agent.spec.credentialSecretRef` as **env vars** into the runtime container
  (`envFrom: secretRef:` or explicit `valueFrom.secretKeyRef`) — the shim **does not read or handle the
  raw secret**; it only knows the *shape* (from the Agent Card `auth.type`) and observes auth-failure
  signals. This keeps the credential out of the shim's logs, its SSE stream, and its trust surface.
- **The three shapes (§11):** (a) Claude-family OAuth token → `CLAUDE_CODE_OAUTH_TOKEN`; (b) non-Claude
  API key → provider-specific env var named by the runtime; (c) BYO model endpoint → endpoint URL (+
  optional token) env var (§10.3). The exact env var names are **runtime metadata** on the shim, not
  core-hardcoded (FR-G2).
- **Auth-failure → pause (V-signal).** When the runtime signals auth failure, the shim emits the SSE
  `auth-required` event (§4) with `{provider, secretRef, detail}`; the Run reconciler transitions the
  Run to `Paused` with an operator-legible condition (§11, FR-F6) — **not** an opaque failure. Resume
  triggers on the referenced Secret updating (operator rotates the token); the reconciler re-drives the
  Run. This is one code path for both OAuth-refresh (Claude) and static-key (OpenClaw/Hermes) models.
- **Egress (§12.2).** BYO model endpoints join the Team NetworkPolicy model-endpoint allowlist;
  default-deny holds. The shim never widens egress — that is operator/NetworkPolicy territory.

## 8. Spec-drift isolation (§10.2)

- A2A wire version is **pinned** in `pkg/a2a@rev`. The shim's §3 verbs are the **internal stable
  interface**; the adapter maps them to the pinned wire rev. Upstream A2A churn stays at the adapter
  seam — it never reaches the Run reconciler or coord/knowledge services.
- The **conformance suite (§12) asserts against the pinned rev.** A spec upgrade is a deliberate gated
  change: bump `pkg/a2a@rev` → re-run conformance → release. Capability negotiation (§6) absorbs minor
  variance so a point-rev bump doesn't require every runtime to move in lockstep.

## 9. Reference shim — OpenClaw (`type: openclaw`)

OpenClaw is the org's primary runtime (gateway/sessions + event-hook API; org evidence: gateway on
`ws://…:18789`, plugin event API `api.on(...)`, token usage on `agent_end`). The reference shim proves
the contract against a real, non-Claude runtime (FR-D3/S6).

### 9.1 Translation table (A2A internal interface ⇄ OpenClaw native)

| A2A verb / event (§3–§5) | OpenClaw native |
|--------------------------|-----------------|
| `SubmitTask{a2a_task_id, envelope}` (V1) | create/attach an OpenClaw **session** keyed on `a2a_task_id` (session id = `run_id`); send the envelope as the initial message. **Dedup:** if a session for `run_id` already exists, reattach — do not create a second (satisfies §6.4 C1). |
| `StreamEvents` SSE (V2) | subscribe to OpenClaw hooks: `before_agent_start`→`status:working`; `message_received`/assistant messages→`message`; `tool_result_persist`→`tool{phase:result}` (and turn-start→`tool{phase:start}`); `agent_end`→`usage` (map `.usage.input/.output/.cacheRead/.cacheWrite`) + `status:completed` on session end |
| `GetStatus` (V3) | derive from session state (active/ended/errored) |
| `CancelTask` (V4) | stop the OpenClaw session/agent turn; drain to `canceled` |
| `EmitArtifact` (V5) | on turn/session completion, collect workspace diffs (`git diff` in the mounted workspace) + the handoff summary → `POST /coord/artifacts` per §5 |
| `GetAgentCard` (V6) | fill §6 schema; `capabilities.streaming:true, toolCalls:true, interactivePrompt:false` (OpenClaw gateway is non-interactive in sandbox), `byoModelEndpoint:true` |
| `auth-required` (§4) | OpenClaw provider auth error on `agent_end`/error hook → SSE `auth-required{provider, secretRef}` → §11 pause |

### 9.2 Reference skeleton (normative shape, Go — the buildable version is delegated §13)

```go
// pkg/shim/openclaw — reference A2A⇄OpenClaw shim (sidecar, one Run).
// Speaks the internal stable interface (§3); pkg/a2a@rev maps to the wire.
type OpenClawShim struct {
    runID   string          // == a2a_task_id
    session *openclaw.Session
    coord   coord.Client    // fenced artifact API (§5); NOT direct Postgres
    fence   string          // the Run's fence token, injected at submit
    ring    *seqRing        // in-mem SSE replay buffer keyed by seq
}

// V1 — deterministic id + dedup (§6.4 C1).
func (s *OpenClawShim) SubmitTask(t Task) error {
    if s.session != nil && s.session.ID == t.A2ATaskID {
        return nil // reattach — no second execution
    }
    s.runID, s.fence = t.A2ATaskID, t.FenceToken
    sess, err := openclaw.Attach(t.A2ATaskID) // create-or-attach on session id
    if err != nil { return err }
    s.session = sess
    s.wireHooks(sess) // before_agent_start/message/tool_result_persist/agent_end → emit()
    return sess.Send(t.Envelope.SystemContext()) // §8.5 envelope as system input
}

// hooks → SSE (§4). agent_end carries best-effort usage (§11).
func (s *OpenClawShim) wireHooks(sess *openclaw.Session) {
    sess.On("before_agent_start", func(e Event) { s.emit("status", statusWorking) })
    sess.On("tool_result_persist", func(e Event) { s.emit("tool", toolResult(e)) })
    sess.On("agent_end", func(e Event) {
        s.emit("usage", usage(e))            // input/output/cacheRead/cacheWrite
        s.emitArtifacts()                    // git diff + handoff → V5
        s.emit("status", statusCompleted)
    })
    sess.OnAuthError(func(e Event) { s.emit("auth-required", authReq(e)) }) // §11 pause
}

// V5 — fenced, idempotent upsert (§5). Server rejects a stale fence.
func (s *OpenClawShim) emitArtifacts() {
    diff := gitDiff(s.workspace)             // read-only over mounted PVC
    s.coord.PutArtifact(coord.Artifact{
        WorkItemID: s.workItemID, RunID: s.runID, Fence: s.fence,
        Kind: "diff", ContentSHA256: sha256(diff), URI: s.upload(diff),
    })
}
```

Design notes locking this to the arch: session id = `run_id` gives §6.4 C1 dedup for free; artifacts go
through the fenced coord client (never raw Postgres) so §6.3 fencing holds; token usage from `agent_end`
is emitted as **best-effort** `usage` (§11), never as a billing claim; `auth-required` routes to the §11
pause path, not to `failed`.

> **Shim-restart note (§3 V2).** The in-memory `seqRing` is lost on shim container restart. On restart
> the shim re-attaches to the live OpenClaw session (durable side) and resumes emitting from the next
> native event; already-committed artifacts are idempotent (§5), and the console/reconciler dedup on
> `(a2a_task_id, seq)`. **ponytail:** in-mem ring is the deliberate simplification — ceiling is "events
> between last-delivered-seq and restart are not replayable," acceptable because status/artifacts are
> re-derivable from the coord record and the live session; upgrade path is a durable per-task event log
> if replay-completeness is later required. Not built until needed (YAGNI).

## 10. Hermes (`type: hermes`) — second runtime, contract-only

Hermes is the second v1 runtime (FR-D3). It reaches the **same six verbs** via its native API; the
translation table is Hermes-specific and produced when the Hermes runtime image lands (ISI-2113). The
point of two v1 runtimes is to prove the seam is **not Claude-shaped and not OpenClaw-shaped** — the
conformance suite (§12) is the shared gate both MUST pass. No Hermes-specific core code exists; if it
did, the seam would have leaked.

## 11. Model-provider seam (`byoModelEndpoint`, §10.3)

Orthogonal to the runtime seam. A runtime advertising `byoModelEndpoint:true` (§6.1) accepts an
OpenAI-compatible base-URL override (`Agent.spec.model` + endpoint from a Secret ref, §11 third story).
The shim routes the resolved endpoint+model to the runtime; runtimes that speak only a fixed vendor
endpoint simply don't advertise it. **Ollama is the credential-free CI/conformance lane** (§10.3,
ISI-2157) — the conformance suite (§12) runs against an Ollama-served model with **no paid credits**, so
S5/S6 e2e is runnable in CI without vendor keys.

## 12. Conformance suite — the ISI-2114 deliverable gate

**A vendor runs this independently; passing ⇒ the runtime drops into any squad with zero core changes
(S5/NFR-EXT1).** The suite asserts the six verbs + the invariants, against the **pinned A2A rev** (§8),
using the **Ollama lane** (§11) so it needs no paid credentials. Each `AgentRuntime.type` MUST pass
before S5/S6 can be claimed (§21 gate).

| ID | Assertion (MUST) | Ties to |
|----|------------------|---------|
| C1 | **Deterministic-id dedup** — two `SubmitTask` with the same `a2a_task_id` ⇒ exactly one agent execution | §3 V1, §6.4 |
| C2 | **Artifact idempotency** — re-emit same `(work_item_id, run_id, kind)`+sha256 ⇒ one row, upsert not duplicate | §5, §6.4 |
| C3 | **Fence rejection** — `EmitArtifact` with a stale fence token ⇒ rejected, blob unreferenced | §5, §6.3 |
| C4 | **SSE ordering + resume** — events strictly increasing `seq`, gap-free; re-`StreamEvents` resumes from `lastSeq` | §4, §3 V2 |
| C5 | **Agent Card fidelity** — card reflects CRD+runtime; a `capabilityOverride` widening beyond runtime ⇒ validation error | §6 |
| C6 | **Capability honesty** — a runtime advertising `interactivePrompt:false` never emits `input-required` | §3.1, §10.1 |
| C7 | **Auth-failure → pause** — an auth error surfaces as `auth-required` (→Paused), never generic `failed` | §7, §11 |
| C8 | **Cancel is terminal + idempotent** — `CancelTask` drains to `canceled`; cancelling a terminal task is a no-op success | §3 V4 |
| C9 | **BYO endpoint routing** — `byoModelEndpoint:true` runtime honors the injected Ollama base-URL; token `usage` surfaces best-effort | §11, §10.3 |
| C10 | **Zero-core-change** — the runtime joins a squad with no change to the Run reconciler / coord services (grep gate: no `type ==` special-casing) | NFR-EXT1, §10.1 |

**Runnable form:** a `conformance/` harness that spins the shim sidecar + an Ollama service container,
drives the ten cases, and emits a pass/fail report per `type`. This harness is the **first-class
deliverable of the ISI-2114 spike** — the contract above is done; the harness + reference shim binary
are the buildable part (§13).

## 13. What is delegated (buildable spike) vs done here

**Done here (this doc):** the shim API contract (§3–§8), Agent Card schema+mapping (§6), credential
contract (§7), OpenClaw reference translation + skeleton (§9), conformance suite spec (§12). This is the
Architect deliverable — the *contract*, per §10.1 "the shim *contract* is designed here."

**Delegated to a coding spike (child issue):** the **buildable reference OpenClaw shim binary**
(`pkg/shim/openclaw`) + the **runnable conformance harness** (`conformance/`, Ollama lane) that asserts
C1–C10 against the pinned `pkg/a2a@rev`. Per arch §10.1/§21, *"ISI-2114 has not been executed … the
reference shim + conformance assertions are the spike's deliverable and must land before S5/S6."* That
is code + CI, owned by an implementer, not the Architect.

## 14. Acceptance criteria (for the spike that implements this)

- **AC1** — the OpenClaw reference shim implements V1–V6 (§3) speaking `pkg/a2a@rev`; verified by C1–C10.
- **AC2** — the conformance harness runs green for `type: openclaw` on the Ollama lane in CI, **no paid
  credentials** (§11).
- **AC3** — a second runtime stub (or Hermes) passing the same harness demonstrates zero-core-change
  (C10) — the seam is proven non-single-runtime-shaped.
- **AC4** — auth-failure e2e drives a Run to `Paused` and resume-on-Secret-update re-drives it (C7, §11).
- **AC5** — Agent Card generated from a real `Agent`+`AgentRuntime` matches §6.2 mapping; over-wide
  `capabilityOverride` is rejected at reconcile (C5).

## 15. Traceability

| Requirement | Where satisfied |
|-------------|-----------------|
| FR-D1…D3 (runtime-agnostic shim, v1 OpenClaw+Hermes) | §2, §3, §9, §10 |
| FR-D4 (capability negotiation) | §6, §11 |
| FR-D5 (conformance suite) | §12 |
| FR-G1…G3 (BYO creds, pause/resume) | §7 |
| NFR-EXT1/EXT2 (zero-core-change extensibility) | §8, §10, §12 C10 |
| R3 (capability flags first-class) | §6.1 |
| R11 (spec-drift isolation) | §8 |
| ISI-2157 / ADR-026 (Ollama / BYO model seam, CI lane) | §11, §12 |
| §6.4 (deterministic id, re-entrancy) | §3 V1, §12 C1/C2 |
| §6.3 (fencing) | §5, §12 C3 |
| §8.5 (context envelope transport) | §3 V1, §5 handoff |
| §17.2 (SSE, OTel) | §4 |
| ADR-008/009 (sidecar, pinned adapter) | §2, §8 |
