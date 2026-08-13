# Story 8.2: Live Run progress via SSE

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔑 THIS IS THE FOUNDATIONAL LIVE-STREAM STORY — the ONE EventSource + BFF proxy every other live
> surface rides.** FR-F2 / UX `02-run-stream-sse`: *"Given a Running Run, When I open its stream, Then
> progress streams live via SSE through the Next.js BFF proxy (hiding the Go API)."* The live-Run map (8.8f),
> the org diagram (8.10), the agent log tail (8.11), and the dashboard live tiles (8.8b/8.8c) all consume
> **this** stream — there is exactly **one** SSE progress bus and **one** BFF proxy, never a per-surface
> transport. The load-bearing crux is the **transport shape**, not a pretty timeline: the browser holds
> **one** `EventSource` to the **Next.js BFF**, which proxies the Go apiserver's SSE progress bus
> **unbuffered**; the browser **never** touches the Go apiserver directly (§13 one-choke-point BFF rule),
> **never** polls, and the stream is a **projection of the DURABLE coordination record** (§6.5 audit / §6.6
> outbox) — so a reconnect **resumes** from `Last-Event-ID` with no lost events, "durable state, not
> ephemeral chat" (FR-B3). It is **RBAC-scoped, read-only legibility** — **no** mutate/claim affordance rides
> the stream (no-P2P on the console); **Kill Run (FR-F4)** is a *separate* authorized control-plane action,
> not a stream verb. Read AC1–AC7 literally: a client that polls the Go API directly, streams unscoped,
> buffers until Run-completion, drops events on reconnect, or hangs a claim button on the feed has committed
> the FR-F2 transport defect, not shipped the feature.

## Gate status (read first)

This story carries **no spike gate**. It is pure console/BFF transport wiring over settled seams:
architecture **§13 — "Live Run progress via SSE"** already records the decision — *"the apiserver publishes
an SSE progress bus fed by shim A2A-SSE; the console consumes `EventSource` (native). Human-imperceptible lag
under normal load"* — and **§3.1** pins the component shape (*ksquad-console: BFF; SSE fan-out; no direct
kube* → *ksquad-apiserver: SSE progress bus*). The durable source is **§6.5** (audit) / **§6.6** (transactional
outbox), and **§16.1** already requires the Gateway to preserve SSE (*"no response buffering / default
timeouts that kill the stream"*). This story **applies** those settled decisions as the concrete stream +
proxy and pins them with a runnable falsification; it does not reopen them.

> **⚠ Ticket/epic section numbers are STALE.** The ISI-2265 ticket and the Epic 8 row cite *"Arch §4.4/§4.5"*;
> the live-Run-stream + BFF material actually lives in **§13** (Operator Console — Live Run progress via SSE),
> **§3.1** (component map — console BFF + apiserver SSE bus), **§6.5/§6.6** (the durable coord-record source),
> and **§16.1** (Gateway SSE preservation). Use those.

## Story

As **an operator (Priya) or squad author (Sam) opening a Running Run**,
I want **its progress to stream live into the console via a single SSE connection that goes through the
Next.js BFF — so I watch coordination events (checkout, comment, handoff, memory, artifact) appear in real
time, reconnect without losing anything, and never talk to the Go apiserver directly**,
so that **I can see exactly what a squad is doing right now without `kubectl`, the browser holds one
authorization choke point (the BFF), the live feed is a durable, replayable projection of the coordination
record rather than ephemeral chat, and the stream is read-only legibility — I can open, navigate, and (via
the separate 2-click control) kill a Run, but the stream itself never becomes a coordination channel
(FR-F2 / NFR-PERF2 / FR-B3 / no-P2P).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md`
  - **§9.6 FR-F2** — *"The console SHALL stream **live Run progress via SSE**."* (MVP) — the requirement this
    story implements.
  - **FR-F1** (squad/run views the stream opens from), **FR-F3** (artifact inspection the stream deep-links
    to, screen 03), **FR-F4** (2-click Kill Run — a *separate* authorized action the Run-detail header
    carries, **not** a stream verb), **FR-B3** (the coordination record is **durable state**, not ephemeral
    chat — why the stream is replayable), **FR-I3** (server-stamped provenance on every event).
  - **NFR-PERF2** — console live progress (SSE) SHALL reflect Run state changes with **low, human-imperceptible
    lag** — why the proxy must be **unbuffered**, not batch-until-close.
  - **NFR-OBS2** — Runs emit progress/lifecycle signals consumable by the console (SSE); **NFR-OBS3** — no
    per-item ids (`run.id`/`work_item.id`/`agent`/`user.id`) as metric labels (the stream is legibility,
    never a consumption axis).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§13 — Operator Console → "Live Run progress via SSE" (FR-F2/NFR-PERF2).** *"the apiserver publishes an
    SSE progress bus fed by shim A2A-SSE; the console consumes `EventSource` (native). Human-imperceptible lag
    under normal load."* Plus the **BFF rule**: *"The browser never talks to the Kubernetes API or Postgres
    directly; the Next.js server proxies/aggregates the Go apiserver (REST + SSE) — one authorization choke
    point"* — **now identity-aware (§12.3)**: the BFF holds the HttpOnly session cookie, the apiserver mints
    the internal JWT, and the deny-by-default RBAC middleware is the single wall.
  - **§13 — "Live tiles are SSE, one bus."** The live-Run map (8.8f), the KPI counters, and the approval
    count stream over the **existing SSE progress bus (same BFF proxy as the org diagram and Run stream) — no
    new transport, no polling.** This story **owns that one bus**; the others consume it.
  - **§3.1 — Component map.** `ksquad-console (Node/Next.js): polished UI + BFF; SSE fan-out; no direct kube`
    → `REST + SSE (HTTPS)` → `ksquad-apiserver (Go): … SSE progress bus`. The stream is a console→apiserver
    proxy; the shim feeds the apiserver over A2A-SSE (§10.1).
  - **§6.5 (audit) / §6.6 (transactional outbox).** Every coordination state change (claim/checkout, comment,
    handoff, completion) writes a **durable** audit row **and** a domain event to the Postgres `outbox` in the
    same transaction. This is the stream's **durable source** — the projection replays from it on reconnect
    (FR-B3), so the stream is *not* ephemeral in-memory chat. Event kinds: `CHECKOUT`, `COMMENT`, `HANDOFF`,
    `MEMORY`, `ARTIFACT` (UX §3.2).
  - **§12.3 — Identity/RBAC.** The stream opens through the **deny-by-default RBAC middleware** on the
    apiserver; the caller streams only a Run it is entitled to see. The BFF adds **no** second authz path and
    **no** client-side authz.
  - **§16.1 — Gateway API / SSE preservation.** The `HTTPRoute` for the apiserver **preserves SSE** — *"no
    response buffering / default timeouts that kill the stream."* The BFF proxy must likewise flush
    incrementally (Next.js streaming response, no buffering).
  - **§10.1 — shim A2A-SSE.** The shim translates the runtime's native progress into A2A-SSE the apiserver
    fans out; the apiserver publishes to the console. This story consumes the apiserver bus — it does not own
    the shim translation.
- **UX:** `docs/bmad/ux/README.md §3.2` + `images/02-run-stream-sse.png` (+ `-light`). Run detail: header with
  live **status**, run meta, and the **Kill Run** button (rose — the separate FR-F4 action); the main column
  is the **SSE timeline** of coordination events tagged by kind (`CHECKOUT`/`COMMENT`/`HANDOFF`/`MEMORY`/
  `ARTIFACT`) with actor (agent·role), mono timestamp, and a live-pulsing head on the streaming event; right
  rail summarizes agents / work items / a credentials mini-status (deep-links to §3.5). The header line states
  the source: *"via coordination record (work items · comments · artifacts)"* — durable state, not chat (FR-B3).
- **ADR:** No new ADR. This story **applies** **ADR-013** (Next.js BFF vs SPA-direct-to-kube — the choke-point
  decision this stream honors) and **ADR-033** (identity-aware BFF/RBAC wall). **ADR-040** (audit=SSE+OTel
  firehose; *no* separate `run_trace` table — the stream projects the durable audit/outbox, not a bespoke
  table) is **not reopened**.
- **Depends on:**
  - **Story 1.2/1.3** — the `Run` CRD + status conditions the stream renders (Running/Paused/Failed/…).
  - **Story 2.1/2.6/2.10** — the `coord` schema, the **audit trail (§6.5)** and **domain-event outbox (§6.6)**
    the stream projects (the durable source; ISI-2196 audit, ISI-2394 coord spine).
  - **Story 5.1/5.5/5.8** — the **shim A2A-SSE** feed into the apiserver (the upstream progress source, §10.1).
  - **Story 15.x / §12.3** — the `pkg/auth` session→JWT + deny-by-default RBAC wall the stream opens through.
  - **Story 9.1 / §16.1** — the Gateway `HTTPRoute` that preserves SSE (no buffering / no stream-killing
    timeouts) in front of the apiserver.
- **Consumed by (this story owns the ONE bus they ride):**
  - **8.8f** (Live Runs panel), **8.8b/8.8c** (KPI/approval live counters), **8.10** (org-diagram live
    status), **8.11** (agent-detail live log tail) — each subscribes to **this** EventSource + BFF proxy; none
    stands up a second transport (§13 "one bus, no new transport, no polling").
- **Tightly coupled with (owned elsewhere):**
  - **Story 3.3** (Kill a Run) — the FR-F4 2-click kill the Run-detail header triggers is a **separate
    authorized control-plane POST**, not a stream verb; the stream shows the resulting `Cancelling→Cancelled`
    transition but never *is* the kill channel.
  - **Story 7.4 / 8.6** (Paused-on-credential) — the stream renders the `Paused(reason)` condition + operator
    signal (§13 screen 05); it does not own the pause reducer.
  - **Story 13.1** (per-Run OTel trace) — the stream deep-links to the Run's trace; the trace is a separate
    store (ADR-040), not carried on the SSE feed.

## What the live Run stream does (the §13/§3.1 transport — authoritative)

1. **SSE push over one EventSource, never polling (AC1 — the FR-F2 shape).** The console opens **one**
   `EventSource`; progress arrives as **server-pushed SSE events**. There is **no** client polling loop
   (repeated GET on a timer) — that is the exact anti-pattern §13 rules out ("no new transport, no polling")
   and the NFR-PERF2 regression.

2. **The BFF proxy hides the Go API (AC2 — the crux).** The browser's stream connection terminates at the
   **Next.js BFF**, which proxies the Go apiserver's SSE progress bus. The browser **never** connects to the
   Go apiserver directly and holds **no** apiserver URL/credential — one authorization choke point (§13):
   the BFF holds the HttpOnly session cookie and forwards the apiserver-minted internal JWT. A stream URL that
   points the browser at the apiserver bypasses the BFF/RBAC/JWT wall — the ADR-013 defect.

3. **Unbuffered passthrough — live means incremental flush (AC3).** The BFF proxy (Next.js streaming
   response) and the Gateway `HTTPRoute` (§16.1) pass the SSE through **unbuffered** — each event flushes to
   the browser **as it arrives**. A proxy that **buffers** (batches events until the stream closes) turns
   "live" into "on-completion" — the NFR-PERF2 defect.

4. **RBAC-scoped, deny-by-default (AC4).** The stream is opened **through** the §12.3 RBAC wall — the caller
   may stream **only** a Run it is entitled to see (server-filtered by project membership). The BFF adds **no**
   second authz path and **no** client-side authz. An unscoped stream (any Run id streams to any caller) is
   the regression.

5. **A durable, resumable projection — not ephemeral chat (AC5).** The stream **projects the durable
   coordination record** (§6.5 audit / §6.6 outbox), so on reconnect (`Last-Event-ID`) it **resumes from the
   last delivered event with no loss and no gap** — the events are durable, replayable rows (FR-B3). An
   in-memory-only stream that drops events across a reconnect has broken "durable state, not ephemeral chat."

6. **Read model — no coordination affordance rides the stream (AC6 — no-P2P on the console).** The stream
   carries **read-only legibility only**: no mutate/claim/lease/fence/transition affordance rides it. Kill Run
   (FR-F4) is a **separate authorized control-plane action** (Story 3.3), not a stream verb. A claim/mutate
   channel on the feed reintroduces the console coordination affordance the architecture forbids (the §6/§7.5
   no-P2P argument, applied to the live stream).

7. **Server-stamped provenance on every event (AC7).** Every streamed event carries **server-stamped**
   provenance derived from the coordination record — **kind** ∈ {`CHECKOUT`,`COMMENT`,`HANDOFF`,`MEMORY`,
   `ARTIFACT`}, **actor** (agent·role), **timestamp** (FR-I3) — never client-fabricated. And observability:
   ordinary console/BFF request+stream telemetry only; **no** per-item ids as metric labels (NFR-OBS3).

## Acceptance Criteria

**AC1 — live progress via SSE push, not polling.** Given a Running Run, When the operator opens its stream,
Then progress arrives as **server-pushed SSE events over one `EventSource`** — **never** a client polling
loop (repeated GET on an interval). A polling fallback (or a second SSE client per surface) is the FR-F2/
NFR-PERF2 / §13-"one bus, no polling" regression.

**AC2 — the stream goes through the Next.js BFF proxy, hiding the Go API (the transport crux).** Given the
console stream, When the browser opens it, Then the connection **terminates at the Next.js BFF**, which
**proxies** the Go apiserver's SSE progress bus (§3.1/§13). The browser **never** connects to the Go
apiserver directly and holds **no** apiserver URL/credential — the BFF is the **one authorization choke
point** (holds the HttpOnly session cookie, forwards the apiserver-minted JWT). A design that streams the
browser straight from the apiserver leaks the Go API and bypasses the RBAC/JWT wall (ADR-013 defect).

**AC3 — unbuffered passthrough (live = incremental flush).** Given the stream open, When the apiserver emits
an event, Then the BFF proxy **and** the Gateway `HTTPRoute` (§16.1) flush it to the browser **as it
arrives** — **no** response buffering that batches events until the stream closes. A buffered proxy turns
"live" into "on-completion," violating NFR-PERF2's human-imperceptible-lag requirement.

**AC4 — RBAC-scoped, deny-by-default; no client-side authz.** Given the stream request, When it is opened,
Then it passes the **§12.3 deny-by-default RBAC wall** on the apiserver — the caller streams **only** a Run
it is entitled to see (server-filtered by project membership). The BFF adds **no** second authz path and the
console adds **no** client-side authz. An unscoped stream (any Run id → any caller) is the regression.

**AC5 — a durable, resumable projection of the coordination record, not ephemeral chat.** Given a client that
disconnects mid-stream and reconnects with `Last-Event-ID`, When the stream resumes, Then it **replays the
coordination-record tail** (every event after the last delivered id) with **no loss and no gap** — because
the stream **projects the durable audit/outbox (§6.5/§6.6)**, not an in-memory buffer (FR-B3: durable state,
not ephemeral chat). *(Non-vacuous: the model must actually deliver the durable events **and** replay the
full tail on reconnect — a stream that vacuously "delivers nothing" does not pass.)*

**AC6 — read model, no coordination affordance rides the stream (no-P2P on the console).** Given the live
stream, When it renders, Then it is **read + navigate only** — click through to the Run, the work item
(8.14), the agent, the artifact (8.7) — with **no** mutate/claim/lease/fence/transition affordance riding the
stream. **Kill Run (FR-F4)** is a **separate authorized control-plane action** (Story 3.3, a 2-click POST from
the Run-detail header), **not** a stream verb. A claim/mutate channel on the feed reintroduces the console
coordination affordance the architecture forbids (§6/§7.5 no-P2P).

**AC7 — server-stamped provenance + observability.** Given a streamed event, When it is rendered, Then it
carries **server-stamped** provenance from the coordination record — **kind** ∈ {`CHECKOUT`,`COMMENT`,
`HANDOFF`,`MEMORY`,`ARTIFACT`}, **actor** (agent·role), **timestamp** (FR-I3) — never client-fabricated. And
the stream emits **only** ordinary console/BFF request+stream telemetry — **no** new domain metric, and
**no** per-item ids (`run.id`/`work_item.id`/`agent`/`user.id`) as metric labels (NFR-OBS3): the live feed is
legibility, never a consumption axis.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/live-run-sse-check.py` — stdlib-only, `python3` it directly. It is a **differential**
check over the **stream DESIGN** a console would ship. It first proves the **FR-F2 anti-pattern** — a
"direct-poll ephemeral" client (the browser polls the Go apiserver directly, unscoped, the proxy buffers, the
stream is in-memory only with no reconnect replay, and a claim button rides the feed) — is **DETECTED as
violating every transport invariant** (so the harness has real teeth), then proves the **§13/§3.1 BFF-SSE
durable-read-model** design violates nothing **and actually replays events {4,5,6} across a mid-stream
reconnect** at `Last-Event-ID=3`.

```
[model] FR-F2 direct-poll-ephemeral client : 7 violation(s) -> DETECTED
[model]   - progress delivered via 'poll', not server-pushed SSE — FR-F2/NFR-PERF2 requires ONE EventSource ...
[model]   - the browser opens the stream against 'apiserver' directly — the Next.js BFF must proxy ... (S2/§13)
[model]   - the BFF/gateway BUFFERS the SSE response ... (S3/§16.1/NFR-PERF2)
[model]   - the stream is UNSCOPED ... §12.3 deny-by-default RBAC wall (S4)
[model]   - reconnect at Last-Event-ID=3 replayed [] not [4, 5, 6] — must project the DURABLE record (S5/FR-B3)
[model]   - the stream carries coordination affordance(s) ['claim'] ... no-P2P on the console (S6)
[model]   - event id=1 has provenance source='client' ... server-stamped projection (S7/FR-I3)
[model] §13/§3.1 BFF-SSE durable read model: 0 violation(s); transport=sse, browser->bff, buffered=False, rbac_scoped=True, durable=True
[model] PASS — the direct-poll-ephemeral client detectably breaks the transport model; the §13/§3.1 BFF-SSE
        design holds S1-S7 ... and actually replays events {4,5,6} across a mid-stream reconnect.
```

It encodes AC1–AC7 as assertions (S1–S7) over the transport design: **(S1)** SSE push, never a polling loop;
**(S2)** the browser connects to the BFF, never the Go apiserver directly (the crux); **(S3)** the proxy is
unbuffered; **(S4)** the stream passes the §12.3 deny-by-default RBAC wall; **(S5)** a reconnect replays the
durable coord-record tail with no loss (non-vacuous — the model must actually deliver *and* replay); **(S6)**
no coordination affordance rides the stream; **(S7)** every event is a server-stamped coord-record projection
with a legible kind.

Each guard is **independently load-bearing** — mutation-verified via `--mutate=NAME`, which injects one
single defect into the conformant BFF-SSE design (`POLL`, `DIRECT_API`, `BUFFERED`, `UNSCOPED`, `EPHEMERAL`,
`P2P_AFFORDANCE`, `CLIENT_PROV`) and flips the check **RED with exactly one violation** and no guard
shadowing another (the ISI-2346-F1 vacuous-tooth class is excluded by construction). Baseline `python3
live-run-sse-check.py` exits 0; each `--mutate=NAME` exits 1 with exactly one violation. The check exits
non-zero if the direct-poll-ephemeral model *stops* violating (teeth lost), if the BFF-SSE model *ever*
violates an invariant, or if it fails to actually deliver the durable events and replay the tail on reconnect.

**Runtime proof (owned by the console E2E + §16.1 Gateway conformance).** The actual EventSource→BFF→apiserver
SSE on a real cluster — a Running Run, the browser opening the stream **through the BFF** with no
direct-to-apiserver reachability, unbuffered flush under the §16.1 `HTTPRoute`, and reconnect-resume — is
exercised by the console E2E (`05-testing`) and the Gateway SSE-preservation check (Story 9.1). The model
check guards the **construction-time transport shape** — 8.2's crux and the thing FR-F2 asked (live, via SSE,
through the BFF, hiding the Go API).

## Tasks / Subtasks

- [ ] **Task 1 — Console EventSource client + Run-stream timeline (AC1, AC7).**
  - [ ] Open **one** `EventSource` against the **BFF** stream route; render the coordination-event timeline
    (kind badge + actor·role + mono timestamp + live-pulsing head), per UX §3.2. **No** polling loop; **no**
    second SSE client (8.8f/8.10/8.11 consume this one).
  - [ ] Render event kinds {`CHECKOUT`,`COMMENT`,`HANDOFF`,`MEMORY`,`ARTIFACT`} from the server-stamped
    provenance; empty/"no events yet" state until the first event.
- [ ] **Task 2 — BFF SSE proxy route (AC2, AC3).**
  - [ ] Next.js BFF route that **proxies** the apiserver SSE progress bus — streaming (unbuffered) response,
    forwarding the apiserver-minted JWT from the HttpOnly session cookie. The browser holds **no** apiserver
    URL/credential.
  - [ ] Confirm no response buffering (Next.js streaming / `Content-Type: text/event-stream`, flush per
    event); the `HTTPRoute` (§16.1, Story 9.1) preserves SSE (no buffering / stream-killing timeouts).
- [ ] **Task 3 — Durable projection + reconnect replay (AC5).**
  - [ ] The apiserver stream projects the **durable audit/outbox (§6.5/§6.6)**; on `Last-Event-ID` reconnect,
    replay the coord-record tail (events after the last delivered id) with no loss. Client sends
    `Last-Event-ID` on auto-reconnect; server resumes from it.
- [ ] **Task 4 — RBAC-scoped open (AC4).**
  - [ ] The apiserver opens the stream **through** the §12.3 deny-by-default RBAC middleware (project
    membership); the BFF adds no second authz path; the console adds no client-side authz.
- [ ] **Task 5 — Read model, no coordination affordance (AC6).**
  - [ ] Read + navigate only (deep-link to Run / work item 8.14 / agent / artifact 8.7). **No** claim/mutate/
    transition control on the stream. Wire **Kill Run** as the **separate** FR-F4 control-plane action (Story
    3.3) on the Run-detail header — a 2-click POST, not a stream verb.
- [ ] **Task 6 — Observability self-check (AC7).**
  - [ ] Confirm no new domain metric; only ordinary request/stream telemetry. NFR-OBS3: no per-item ids on
    labels, no `model` label.
- [ ] **Task 7 — Falsification + E2E.**
  - [ ] `python3 docs/bmad/spikes/bench/live-run-sse-check.py` exits 0; each `--mutate=NAME` exits 1 with
    exactly one violation.
  - [ ] Console E2E (`05-testing`): open a Running Run's stream, assert events arrive live through the BFF
    (no direct-to-apiserver), and a reconnect replays the tail; assert no claim/mutate affordance on the feed.

## Dev Notes

- **One SSE bus, and this story owns it.** The Run stream, the live-Run map (8.8f), the org-diagram live
  status (8.10), the agent log tail (8.11), and the dashboard live counters (8.8b/8.8c) all ride the **same**
  `EventSource` + BFF proxy (§13 "live tiles are SSE, one bus — no new transport, no polling"). This story
  wires that one bus; the others **consume** it. Do **not** stand up a second EventSource client or a polling
  loop anywhere — that is the exact anti-pattern §13 rules out.
- **The BFF is the choke point (ADR-013), and it must not buffer.** The browser talks to the Next.js BFF, and
  the BFF proxies the Go apiserver — one authorization choke point, the browser never touching kube/apiserver
  directly. Two easy regressions: (1) exposing the apiserver stream URL to the browser (bypasses the RBAC/JWT
  wall — AC2), and (2) the BFF or Gateway **buffering** the SSE response so events only flush at close
  (breaks "live" — AC3/§16.1). Use a Next.js streaming response and confirm the `HTTPRoute` preserves SSE.
- **Durable, not ephemeral (FR-B3).** The stream is a **projection of the durable coordination record** (§6.5
  audit / §6.6 outbox), *not* an in-memory chat buffer. That is precisely what lets a reconnect replay the
  tail on `Last-Event-ID` with no loss (AC5). ADR-040 already decided the firehose is the audit/outbox +
  SSE/OTel — there is **no** separate `run_trace` table; the stream projects the durable rows.
- **Read model, no mutate — no-P2P on the console.** The stream shows *what happened* and lets you navigate;
  it never lets you claim, reassign, transition, or drive an agent. Kill Run (FR-F4) is a **separate**
  authorized control-plane POST (Story 3.3) — the Run-detail header carries the button, but the button is not
  a stream verb and the stream is not the kill channel. A coordination affordance on the feed is the console
  no-P2P violation (§6/§7.5).

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield console — the SSE progress bus (§13/§3.1) + the durable
  coord audit/outbox (§6.5/§6.6, Epic 2) + the shim A2A-SSE feed (§10.1, Epic 5) are landing in parallel.
  This story lands the **console EventSource client + Run-stream timeline** under `console/` and the **BFF SSE
  proxy route** in the Next.js server; the apiserver-side stream (project → durable record → SSE, RBAC-gated)
  is the apiserver surface it proxies. It adds **no** new transport and **no** new datastore — it projects the
  existing durable record over the existing bus.
- **Match conventions:** the **one** shared EventSource client (consumed by 8.8f/8.10/8.11) — do not add a
  second SSE client; reuse the §13 BFF proxy pattern and the §12.3 RBAC wall; render the durable coord-record
  kinds (do not invent client-side event types).

### References

- [Source: docs/bmad/02-prd.md#9.6 FR-F2] — the console SHALL stream live Run progress via SSE (MVP).
- [Source: docs/bmad/02-prd.md — NFR-PERF2] — SSE reflects Run state changes with human-imperceptible lag
  (why the proxy is unbuffered).
- [Source: docs/bmad/02-prd.md — FR-B3 / FR-I3 / NFR-OBS3] — durable coordination record (not ephemeral chat);
  server-stamped provenance; no per-item ids on metric labels.
- [Source: docs/bmad/03-architecture.md#13 — Live Run progress via SSE + BFF rule] — apiserver SSE progress
  bus fed by shim A2A-SSE; console consumes EventSource; browser never talks to kube/apiserver directly (one
  choke point, identity-aware §12.3).
- [Source: docs/bmad/03-architecture.md#13 — "Live tiles are SSE, one bus"] — one EventSource + BFF proxy for
  the Run stream, org diagram, and live tiles; no new transport, no polling.
- [Source: docs/bmad/03-architecture.md#3.1 — Component map] — console (BFF; SSE fan-out; no direct kube) →
  REST+SSE → apiserver (SSE progress bus).
- [Source: docs/bmad/03-architecture.md#6.5 / #6.6 — audit + transactional outbox] — the durable coordination
  record the stream projects and replays on reconnect.
- [Source: docs/bmad/03-architecture.md#16.1 — Gateway API / SSE preservation] — the HTTPRoute preserves SSE
  (no response buffering / stream-killing timeouts).
- [Source: docs/bmad/ux/README.md#3.2 + images/02-run-stream-sse.png] — the Run-stream screen: SSE timeline of
  coordination events, Kill Run in the header (separate FR-F4 action), "via coordination record" source line.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8 row 8.2] — epic-level AC (Arch §4.4/§4.5 [STALE → §13/
  §3.1]; UX 02-run-stream-sse; FR-F2).
- [Source: docs/bmad/spikes/bench/live-run-sse-check.py] — the runnable falsification (S1–S7, mutation-proven).

### Open questions (route via ISI-2325; do not block the stream)

1. **Reconnect replay window (Architect / Winston).** `Last-Event-ID` replays the coord-record tail — confirm
   whether the apiserver replays the **whole** Run history on reconnect or a **bounded** window (last N /
   since-timestamp) for a very long-running Run, so a reconnect never front-loads the entire history. *Does
   not block the durable-projection contract (AC5).*
2. **Stream lifecycle after terminal state (Designer / Architect).** Confirm the stream's behavior when a Run
   reaches a terminal condition (Completed/Failed/Cancelled) — the SSE closes after the terminal event vs
   stays open to show the final record — so the UX (live-pulsing head → settled) is honest. *Does not block
   the live stream for a Running Run.*

## Out of scope (owned elsewhere)

- **The shim A2A-SSE translation** (**5.1/5.5/5.8**, §10.1) — how the shim turns a runtime's native progress
  into the A2A-SSE the apiserver fans out. This story consumes the apiserver bus; it does not own the shim.
- **The durable coord audit/outbox itself** (**2.1/2.6/2.10**, §6.5/§6.6) — the durable record the stream
  projects. This story projects/replays it; it does not own the schema or the write path.
- **Kill a Run (FR-F4)** (**3.3**, §8) — the 2-click authorized control-plane kill the Run-detail header
  triggers. The stream renders the resulting transition; it is **not** the kill channel.
- **Paused-on-credential surface** (**7.4/8.6**, §11/§13 screen 05) — the `Paused(reason)` condition + operator
  signal the stream renders; this story does not own the pause reducer.
- **Per-Run OTel trace** (**13.1**, §17.2/ADR-040) — the trace the stream deep-links to; a separate store, not
  carried on the SSE feed.
- **The Gateway `HTTPRoute` / SSE preservation** (**9.1**, §16.1) — the chart resource that keeps the stream
  un-buffered/un-timed-out at the edge; this story relies on it, it does not author the chart.
- **The dashboard live tiles + live-Run map** (**8.8b/8.8c/8.8f**), **org diagram** (**8.10**), **agent log
  tail** (**8.11**) — consumers of this one bus; each renders its own surface over the stream this story owns.
