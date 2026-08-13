# Story 7.5: Ollama / BYO-endpoint credential shape (endpoint-as-Secret, model-as-config)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔑 THIS IS THE THIRD OF THE THREE CONCRETE CREDENTIAL STORIES — the BYO-endpoint instantiation of the
> Story 7.1 per-user Secret-ref shape (§11, FR-G1/G2).** Story 7.1 pins the *reference shape* (per-user
> Secret ref, no shared master, per-namespace never cross-squad — ADR-010, LOCKED). Story 7.2 is the
> **Claude-family** instantiation: an *OAuth-refresh* lifecycle. Story 7.3 is the **second-runtime** static
> **API-key** shape (resolves OQ11/F15). **This story is the third — the credential for a BYO Ollama /
> OpenAI-compatible Agent (Story 5.7)**, and its distinctive crux is the credential's *shape*: the
> "credential" is an **endpoint** — an **endpoint URL (+ an OPTIONAL token) held in a per-user Secret ref**
> (`Agent.spec.modelEndpointRef`) — while the **model name is plain, non-secret Agent-level config**
> (`Agent.spec.model`). The §11 credential table now reads **Two → Three stories** (ADR-026 / §10.3). The
> load-bearing crux is the **placement split + the no-shared-endpoint lock**: a design that (a) falls back
> to a **shared platform endpoint** when the ref is absent (the vendor-lock §11 forbids, reopened on the
> endpoint axis), (b) **bakes the endpoint into plain CR config** while **stuffing the model name into the
> Secret** (inverting the split — the private endpoint leaks into the CR and rotation stops being a Secret
> update), (c) grafts Claude's **~8h refresh controller** / a **~9-day `cred_expired`** pause onto a static
> endpoint, or (d) **crashloops opaquely** instead of Pausing legibly when the endpoint is down, has
> committed a category error, not shipped a feature. Read AC1, AC2, and AC5 literally: **there is no paid
> provider token here** — the endpoint is the credential, it lives per-user in a Secret, the model name
> does not, and an unreachable endpoint is a **legible `Paused`, never an opaque failure**.

## Gate status (read first)

This story carries **no spike gate**. Like 7.3 (and unlike 7.2, whose title carried the now-**RETIRED**
`[GATE: ISI-2112]` OAuth spike), the BYO-endpoint credential has **no OAuth step**, so no OAuth spike gates
it. The model backend it credentials — BYO Ollama as a **model-endpoint override, not an `AgentRuntime.type`**
— was already settled in **Story 5.7** (§10.3 / ADR-026): `Agent.spec.modelEndpointRef` → per-user Secret +
per-Agent `Agent.spec.model`, ridden by any `byoModelEndpoint`-capable runtime (`opencode` by default,
Story 5.8), **zero core change**. This story **applies** that settled seam on the *credential* axis and pins
the third §11 row with a runnable falsification; it does not reopen 5.7's model≠runtime decision or 7.1's
per-user Secret lock.

## Story

As **an operator running a squad on my own self-hosted Ollama (or any OpenAI-compatible) endpoint**,
I want **to drop my endpoint URL (and, if my endpoint needs one, an optional token) into a per-user Secret,
set my model name as plain Agent config, and have every BYO-endpoint Agent draw its endpoint from that
Secret — with no paid provider token, no OAuth dance, and rotation being nothing more than me updating that
Secret**,
so that **the credential model fits *my* self-hosted backend (a private endpoint, not a vendor token),
custody stays with me (D3), KSquad never silently falls back to a shared platform endpoint, my private
endpoint never leaks into a plaintext CR, and if my endpoint goes unreachable mid-Run the Run pauses legibly
and resumes the moment I point it at a reachable endpoint — never crashloops or fails opaquely, and never
invents an ~8h/~9-day expiry my self-hosted server never imposes.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **§9.7 FR-G1** (per-user Secret refs, no shared master — LOCKED),
  **FR-G2** (credential *type + lifecycle* as capability metadata; runtime-neutral, now **three** concrete
  stories), **FR-G3** (graceful pause/resume on expiry/rotation), **D3** (credential custody stays with the
  principal), **NFR-SEC3** (creds never logged/echoed/exposed cross-squad), **S10** (graceful credential
  pause/resume). The BYO-Ollama backend is **FR-D4 / §10.3** (model-endpoint seam, Story 5.7).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§11 — Credential Model (now Three Concrete Stories, ADR-026).** The credential table's **BYO-endpoint /
    Ollama** row is exactly this story: *acquisition* = an **endpoint URL (+ optional token) supplied
    directly** (no OAuth, no paid provider token); *placement* = endpoint (+ optional token) in a **per-user
    `modelEndpointRef` Secret**, **model name in plain `Agent.spec.model`**; *lifecycle* = **static** (no
    ~8h TTL, no refresh controller, no ~9-day window; the endpoint Secret changes **only** on operator
    rotation). Type + lifecycle are **capability metadata** (FR-G2) — `credentialLifecycle = static-endpoint`
    — so the core hardcodes no vendor's flow.
  - **§11 — Graceful pause/resume (all models).** *"Resume triggers on the referenced Secret updating."*
    For the BYO-endpoint model the only credential-adjacent pause is an **unreachable endpoint** →
    `Paused(endpoint_unreachable)` with an operator-legible condition, **resumed when the operator updates
    the referenced Secret** (points it at a reachable endpoint) — §11 confirms 7.4 covers the OAuth-refresh,
    static-key, **and Ollama-endpoint** models, and that *"an unreachable endpoint is a legible `Paused`, not
    an opaque failure."*
  - **§10.3 / ADR-026 — model-endpoint seam.** BYO Ollama is a **model backend**, not an `AgentRuntime.type`:
    `Agent.spec.modelEndpointRef` (the endpoint Secret) + `Agent.spec.model` (the plain model name), consumed
    by a `byoModelEndpoint`-capable runtime over the OpenAI-compatible wire. This story credentials that seam.
  - **§7.2 / §5.1 `Agent` Card** — the card advertises `credentialType = byo-endpoint` +
    `credentialLifecycle = static-endpoint` metadata **and the plain `model`**; **never** the endpoint URL or
    token material (NFR-SEC3).
  - **§13 — screen 05 Credentials page** — per-agent health *connected / (rotating) / invalid /
    unreachable*; the operator sees status, never the endpoint token. No "Connect" OAuth button for a BYO
    endpoint — a URL (+ optional token) is pasted/mounted, not authorized via browser.
  - **§17.1 / NFR-SEC3** — the endpoint URL/token is never logged/echoed into artifacts or exposed
    cross-squad. This story owns the endpoint's no-echo discipline on the *provision/rotation* path; the
    shim's no-log on the *injected value* is Story 5.4.
- **ADR:** **ADR-010 / AD-9** (per-user Secret ref, no shared master — the shape this instantiates; **not
  reopened**), **ADR-026 / §10.3** (model-endpoint seam — the backend this credentials; **not reopened**).
  No new ADR: this story *applies* §11's already-recorded third-story row.
- **Depends on:**
  - **Story 7.1** (the per-user Secret-ref shape + composer invariants). This story supplies an
    endpoint Secret *of* that shape; it does not re-implement the no-shared-master / per-namespace guards.
  - **Story 5.7** (the BYO model-endpoint seam — `Agent.spec.modelEndpointRef` + `Agent.spec.model`, the
    `byoModelEndpoint` capability). This story is that seam's **credential shape**; 5.7 owns the seam itself.
  - **Story 1.2 / 1.3** (the `Agent` CRD incl. `modelEndpointRef`, `model`, `credentialType` enum incl. the
    `byo-endpoint` family, and the operator/reconciler scaffold).
  - **Story 5.2** (Agent Card generation — carries the `byo-endpoint` / `static-endpoint` metadata + `model`).
  - **Story 5.4** (the shim credential-injection contract — maps this Secret to the runtime's model config,
    e.g. the OpenAI-compatible base-URL `…:11434/v1` [+ optional bearer], **without logging it**). This story
    defines *which* Secret and *what* lifecycle; 5.4 owns the mapping seam.
  - **Story 5.8** (the `opencode` runtime shim — the default `byoModelEndpoint`-capable runtime whose model
    config this endpoint feeds).
- **Tightly coupled with / consumed by:**
  - **Story 7.4** (graceful pause/resume — the `Paused(endpoint_unreachable)` transition + **resume-on-Secret-
    update** this story's AC5 names; §11 confirms 7.4 covers the Ollama-endpoint model too).
  - **Story 7.2 / 7.3** (the *other two* concrete lifecycles over the same 7.1 shape — the OAuth-refresh and
    static-key shapes this endpoint shape is the deliberate third sibling of).
  - **Story 8.6 / §13 screen 05** (the health surface — *connected / rotating / invalid / unreachable*).
  - **ISI-2157 / 14.8** (the **$0 CI / E2E Ollama lane** — a self-hosted endpoint credentialed exactly this
    way is *also* the free-testing backend).
  - **Story 13.4 / 13.10** (per-principal consumption attribution — rides the per-user endpoint Secret).

## What the BYO-endpoint credential path does (the §11 static-endpoint model — authoritative)

1. **Direct endpoint acquisition → per-user Secret; model name → plain Agent config (AC1).** The operator
   supplies the **endpoint URL** (+ an **optional** token, only if their endpoint requires one) directly. It
   is written to a **per-user Kubernetes Secret** of the Story 7.1 shape (`modelEndpointRef`, in the Agent's
   own Team namespace). The **model name** (`qwen3`/`llama`/`deepseek`) is set as **plain, non-secret
   `Agent.spec.model`**. The Secret's `credentialType = byo-endpoint`, `credentialLifecycle =
   static-endpoint`. There is **no OAuth flow**, **no refresh token**, and **no paid provider token**.

2. **Endpoint via Secret ref — never a shared platform endpoint (AC2, the §11 lock reopened).** The endpoint
   is resolved **only** from the per-user `modelEndpointRef` Secret. There is **no fallback to a shared
   platform endpoint** when the ref is absent — a shared-endpoint fallback re-introduces exactly the
   vendor-lock §11 forbids, on the endpoint axis (two operators' Agents drawing the same platform endpoint).

3. **Placement split: endpoint in the Secret, model name in plain config (AC3, the shape crux).** The
   endpoint (+ optional token) lives in the **Secret**; the model name lives in **plain `Agent.spec.model`**.
   The two axes are **not co-located**: baking the endpoint into plain CR config leaks the private endpoint
   into the CR and turns rotation into a CR edit (not a Secret update); stuffing the model name into the
   Secret couples non-secret config to the credential (changing the model would need a Secret write). Either
   inversion is a construction failure.

4. **No refresh controller; rotation = an in-place operator Secret update (AC4).** A self-hosted endpoint has
   **no ~8h access-token TTL**, so there is **nothing to refresh** and the §5.2 credential controller does
   **not** touch it. Over the credential's whole lifetime the **only** writer of the Secret is the
   **operator** (initial provision + any rotation), and rotation **updates the SAME per-user Secret name in
   place** — never a freshly minted Secret that strands existing mounters.

5. **Unreachable endpoint → `Paused(endpoint_unreachable)`, resumed on the operator's Secret update — never
   an opaque failure (AC5).** Because a static endpoint does not self-expire on an ~8h/~9-day timer, a Running
   Run **never** pauses on a Claude window. The **only** credential-adjacent pause is
   `Paused(endpoint_unreachable)`, raised on a runtime **connectivity** signal (the operator's endpoint is
   down / moved), and it **resumes when the operator updates the referenced Secret** to a reachable endpoint
   (§11, the shared 7.4 machinery). A pod that **crashloops** or a Run that **fails opaquely** with no legible
   `Paused` condition is the exact defect 7.4 forbids. A `cred_expired` pause on a ~9-day timer, or a
   `reauth_setup_token` pause at an ~8h boundary, is the Claude lifecycle misapplied.

6. **Lifecycle pinned per runtime as metadata; the core is vendor-neutral (AC6).** The credential lifecycle
   (`static-endpoint` vs `static-key` vs `oauth-refresh`) is advertised as **per-runtime capability metadata**
   on the Agent Card (FR-G2) and the **core reads it** — it does **not** hardcode any vendor's flow. A core
   that bakes in Claude's oauth-refresh lifecycle for every runtime is the not-vendor-neutral defect.

7. **Metadata (+ Secret name + model) surfaces; endpoint material never does (AC7).** The Agent Card (5.2)
   advertises `byo-endpoint` / `static-endpoint` **and the plain `model`**; screen 05 shows *connected /
   rotating / invalid / unreachable*; rotation events publish to NATS referencing the **Secret name**. **None**
   of these — and no log line — ever carries the **endpoint URL or token string** (NFR-SEC3, §17.1). The shim
   (5.4) injects the endpoint into the runtime's model config (base-URL [+ optional bearer]) and nothing else,
   and never persists or logs it.

## Acceptance Criteria

**AC1 — a directly-supplied endpoint provisions a per-user Secret; model name is plain Agent config; no
OAuth, no paid token.** Given an operator supplies a BYO endpoint URL (+ optional token) and a model name,
When it is provisioned, Then the endpoint (+ optional token) is written to a **per-user Kubernetes Secret**
of the Story 7.1 shape (`modelEndpointRef`, in the Agent's own Team namespace, no shared master) with
`credentialType = byo-endpoint` and `credentialLifecycle = static-endpoint`, and the **model name is set as
plain `Agent.spec.model`**. There is **no interactive OAuth step, no refresh token, and no paid provider
token** — any of those is a construction failure (it is Claude/paid-vendor-shaping the BYO endpoint).

**AC2 — the endpoint is resolved from the per-user Secret ref, never a shared platform endpoint.** Given a
BYO-endpoint Agent, When the core resolves its endpoint, Then it reads it **only** from the per-user
`modelEndpointRef` Secret. There is **no fallback to a shared platform endpoint** when the ref is absent —
a shared-endpoint fallback is the vendor-lock §11/FR-G1 forbids, reopened on the endpoint axis (it would let
two operators' Agents draw the same platform endpoint). *(Non-vacuous: two BYO-endpoint Agents with distinct
refs must resolve distinct endpoints; a design collapsing them to one shared endpoint flips this RED.)*

**AC3 — placement split: endpoint (+ optional token) in the Secret, model name in plain config (the shape
crux).** Given a composed BYO-endpoint Agent, When its credential shape is inspected, Then the **endpoint (+
optional token) lives in the Secret** and the **model name lives in plain `Agent.spec.model`** — the two are
**not co-located**. An endpoint baked into plain CR config (leaking the private endpoint into the CR, making
rotation a CR edit not a Secret update) **or** a model name stuffed into the Secret (coupling non-secret
config to the credential) is a construction failure.

**AC4 — no refresh controller; rotation is an in-place update of the SAME Secret.** Given the provisioned
endpoint Secret, When time passes and the operator rotates the endpoint, Then the **§5.2 credential
controller does not refresh it** (a self-hosted endpoint has no ~8h TTL), the **only** writer across the
whole lifecycle is the **operator** (provision + rotation), and rotation writes to the **same per-user Secret
name** the pods already mount — never a newly minted Secret. A controller-refresh write, or a fresh Secret
per rotation, is a construction failure.

**AC5 — unreachable endpoint → `Paused(endpoint_unreachable)`, resumed on the operator's Secret update; never
opaque.** Given a Running Run on a BYO-endpoint Agent, When the operator's endpoint becomes unreachable, Then
the Run moves to `Paused(endpoint_unreachable)` with an operator-legible condition and **resumes when the
operator updates the referenced Secret** to a reachable endpoint (§11 / 7.4). The Run **does not** crashloop
or fail opaquely, and **does not** pause on an ~8h/~9-day Claude timer (`cred_expired`/`reauth_setup_token`).
*(Non-vacuous: the model must actually fire exactly one `endpoint_unreachable` pause + resume on the Secret
update — AC5 is not satisfied by 'never pause / crash silently'.)*

**AC6 — lifecycle is pinned per runtime as metadata; the core is vendor-neutral.** Given a BYO-endpoint, a
second-runtime API-key, and a Claude-family Agent, When the core resolves each credential's lifecycle, Then
it reads the **per-runtime `credentialLifecycle` capability metadata** (FR-G2) — `static-endpoint`,
`static-key`, `oauth-refresh` respectively — and applies exactly that. The **core hardcodes no vendor's
flow**: a core that applies `oauth-refresh` to the BYO endpoint (or otherwise ignores the pinned metadata) is
the not-vendor-neutral defect. This story adds the **third** row and keeps §11 vendor-neutral.

**AC7 — endpoint metadata (+ Secret name + model) surfaces; endpoint material never does.** Given a
composed/rotating BYO-endpoint Agent, When its state is observed (Agent Card, screen-05 health, NATS rotation
events, logs), Then only `credentialType`/`credentialLifecycle` **metadata**, the plain **model** name, the
**Secret name**, and health states (*connected / rotating / invalid / unreachable*) appear — **never** the
endpoint URL or token string (NFR-SEC3, §17.1). The shim (5.4) injects the endpoint into the runtime's model
config and neither logs nor persists it.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/byo-endpoint-credential-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check over the credential **lifecycle a driver would produce** for a BYO-endpoint (Ollama /
OpenAI-compatible) Agent across a 12-day hourly timeline. It first proves the **shared/Claude-shaped
anti-pattern** (a shared platform-endpoint fallback, the endpoint baked into plain CR config with the model
name stuffed into the Secret, the §5.2 controller "refreshing" the endpoint every ~8h, a fresh Secret minted
per refresh, a spurious ~9-day `cred_expired` pause, a core that hardcodes `oauth-refresh` for every runtime,
and the endpoint token echoed on provision) is **DETECTED as violating every BYO-endpoint invariant** — so
the harness has real teeth — then proves the **§11 static-endpoint lifecycle** violates nothing and pauses
**exactly once**, on an **endpoint-unreachable** signal, resuming when the operator updates the Secret.

```
[model] shared/Claude-shaped BYO-endpoint lifecycle : 7 violation(s) -> DETECTED
[model]   - endpoint resolved from 'shared-platform-endpoint', not a per-user modelEndpointRef Secret — ...
[model]   - placement inverted: secret_holds=['model'], plain_config=['endpoint'] — ...
[model]   - Secret written by non-operator ['controller'] — a static endpoint has no ~8h TTL to refresh ...
[model]   - writes churn Secret name(s) [...] != {'alice-ollama-endpoint'} — rotation is in-place ...
[model]   - Run paused for ['cred_expired'] — a static endpoint does not self-expire on an ~8h/~9-day timer ...
[model]   - core applied lifecycle 'oauth-refresh' ... expected 'static-endpoint' — the core must be vendor-neutral ...
[model]   - endpoint material leaked on an observable surface: 'log: minted model base-url ... auth=...' ...
[model] §11 static-endpoint lifecycle: 0 violation(s); pauses=['endpoint_unreachable']; resumes=['secret_updated']; opaque_fail=False; writers=['operator']; core_applies='static-endpoint'
[model] PASS — the shared/Claude-shaped lifecycle detectably breaks the BYO-endpoint model; the §11
        third-story path holds E1-E7 ... and pauses exactly once on the unreachable endpoint, resuming
        on the operator's Secret update.
```

It encodes AC1–AC7 as assertions (E1–E7) over the lifecycle a design would produce: **(E1)** the endpoint
must resolve from a `secret-ref`, never a shared platform endpoint; **(E2)** the endpoint (+ optional token)
must live in the Secret and the model name in plain config — an inverted placement is caught; **(E3)** the
Secret's write actors must be exactly `{operator}` with **zero** `refresh`-kind writes; **(E4)** every write
targets the **same** Secret name — a name churn is caught; **(E5)** the pause set must be **exactly**
`{endpoint_unreachable}` (no `cred_expired`/`reauth`, no opaque crashloop) with a `secret_updated` resume
(non-vacuous in both directions); **(E6)** the lifecycle the **core applies** must equal the runtime's pinned
Agent-Card metadata and be `static-endpoint`; **(E7)** no observable surface may contain endpoint material.

Each guard is **independently load-bearing** — mutation-verified via `--mutate=NAME`, which injects one
single defect into the conformant static-endpoint path (`SHARED_ENDPOINT`, `PLACEMENT_INVERTED`,
`CONTROLLER_REFRESH`, `SECRET_CHURN`, `OPAQUE_FAIL`, `CORE_HARDCODE`, `LEAK`) and flips the check **RED with
exactly one violation** and no guard shadowing another (the ISI-2346-F1 vacuous-tooth class is excluded by
construction). Baseline `python3 byo-endpoint-credential-check.py` exits 0; each `--mutate=NAME` exits 1 with
exactly one violation. The check exits non-zero if the shared/Claude-shaped model *stops* violating (teeth
lost), if the static-endpoint model *ever* violates an invariant, or if the `endpoint_unreachable` pause +
`secret_updated` resume fails to fire.

**Runtime proof (owned by 5.4 + 7.4 + the ISI-2114/ISI-2157 conformance lane).** AC1/AC4 (the actual mounted
endpoint Secret + in-place rotation), AC5 (the real `Paused(endpoint_unreachable)` → resume-on-Secret-update
transition), and AC7 (no-log on the injected value) are proven on a **real cluster** by 5.4's injection
contract, 7.4's pause/resume, and the **$0 Ollama conformance/E2E lane** (5.6/14.8). The model check guards
the **construction-time credential shape** — 7.5's crux and the third §11 row.

## Out of scope (owned elsewhere)

- **The per-user Secret-ref shape + composer invariants** (**7.1**, §11/§12.1, ADR-010) — this story
  supplies an endpoint Secret *of* that shape; it does not re-implement the no-shared-master / per-namespace
  guards.
- **The BYO model-endpoint seam itself** (**5.7**, §10.3, ADR-026) — `Agent.spec.modelEndpointRef` +
  `Agent.spec.model`, the `byoModelEndpoint` capability, model≠runtime axis. This story credentials that
  seam; it does not reopen the model-vs-runtime decision.
- **The shim credential-injection contract + no-log on the injected value** (**5.4**, §7.3, NFR-SEC3) — how
  the Secret is mapped into the runtime's model config (base-URL [+ optional bearer]) without being logged.
  This story names the Secret + lifecycle; 5.4 owns the mapping.
- **The `opencode` runtime shim** (**5.8**, §10.1) — the default `byoModelEndpoint`-capable runtime whose
  model config this endpoint feeds.
- **Graceful pause/resume machinery** (**7.4**, §11/§8, FR-G3/S10) — the `Paused(endpoint_unreachable)` state
  transition + resume-on-Secret-update; this story names the *one* endpoint pause reason and *when*, not the
  transition machinery. §11 confirms 7.4 covers the Ollama-endpoint model.
- **The Claude-family OAuth credential (7.2) and second-runtime API-key credential (7.3)** — the *other two*
  concrete lifecycles over the same 7.1 shape; this story is the deliberate third sibling (a static endpoint,
  neither Claude-shaped nor a vendor API key).
- **The console health surface** (**8.6 / §13 screen 05**) — the *connected / rotating / invalid /
  unreachable* states; this story names the health metadata, not the UI.
- **The $0 CI / E2E Ollama lane** (**ISI-2157 / 14.8**) — a self-hosted endpoint credentialed this way is
  *also* the free-testing backend; this story is the credential shape, not the CI wiring.
- **Consumption attribution / metering** (**13.4 / 13.10**, §11 consumption note) — rides the per-user
  endpoint Secret; this story is the credential, not the metering spine.
