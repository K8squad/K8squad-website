# Story 5.4: Credential injection contract (Secret ref → runtime-native form, never logged)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔑 THIS STORY IS THE SEAM WHERE A PER-USER SECRET BECOMES A RUNNING AGENT'S CREDENTIAL — WITHOUT
> THE CREDENTIAL EVER TOUCHING A LOG, A MANIFEST, OR THE SHIM'S TRUST SURFACE (arch §11 / §11.1, shim
> spec §7, FR-G1 LOCKED, NFR-SEC3).** KSquad holds **no shared master credential**: every `Agent`
> references a **per-user Kubernetes Secret** (`Agent.spec.credentialSecretRef`). When a Run claims its
> sandbox, that Secret must arrive in the runtime container **as env/volume from a `secretRef`** and be
> mapped to the **runtime-native form** the vendor CLI expects (`CLAUDE_CODE_OAUTH_TOKEN` vs an API-key
> env vs a BYO endpoint URL) — and the credential **value** must **never** be persisted or logged. The
> load-bearing invariants: **(1)** the pod spec carries a **reference, never an inline literal** — the
> value is materialized by kubelet into the runtime container only, never written into etcd/manifests/
> reconciler logs; **(2)** the **shim never reads or handles the raw secret** — it knows only the
> *shape* (Agent-Card `auth.type`) and observes auth-failure signals, so the credential stays out of the
> shim's logs, its SSE stream, and its trust surface; **(3)** the runtime-native env mapping is
> **Agent-Card metadata, not a core vendor switch** (FR-G2 / conformance C10); **(4)** the credential
> **value appears in no sink** — Run logs, shim logs, SSE, coord artifacts, `audit_log`, or OTel
> attributes (NFR-SEC3). A reconciler that inlines the token, a shim that logs it, or an auth-required
> event that echoes the raw provider error are **security failures, not bug tickets**. Read AC1 and AC4
> literally.

## Story

As **a runtime integrator wiring a per-user Secret into a running agent sandbox**,
I want **the Run reconciler to inject `Agent.spec.credentialSecretRef` into the runtime container as
env/volume from a `secretRef`, mapped to the runtime's expected native form via Agent-Card metadata,
with the shim never handling the raw value and the credential appearing in no log or durable sink**,
so that **any vendor runtime gets exactly the credential shape it expects with zero core changes, and a
compromised agent, a leaked log, or a captured event stream can never expose a user's credential
(FR-G1/G2/G3, NFR-SEC3, arch §11/§11.1, shim §7).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-G1** (per-user Secret refs, BYO, no shared master — LOCKED),
  **FR-G2** (credential type/lifecycle is capability metadata, not vendor-hardcoded), **FR-G3/S10**
  (graceful auth-failure pause/resume), **NFR-SEC3** (credentials never logged/echoed, never cross-squad).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§11 — Credential Model (Three Concrete Stories).** The authoritative shape: **per-user k8s Secret
    refs on the `Agent` CRD**, three families — (a) Claude-family OAuth token, (b) non-Claude API key,
    (c) BYO model endpoint (§10.3) — each a per-user Secret ref; **type + lifecycle are capability
    metadata** on the shim/Agent Card so the core hardcodes no vendor's auth flow (FR-G2).
  - **§11.1 — Zero-touch Claude credential lifecycle.** The centralized, **leader-elected credential
    controller** refreshes the ~8h OAuth token and writes it back to the **same Secret**; agent pods
    **just mount** it. This story owns the **mount + map + no-leak** half; the controller's refresh loop
    is Epic 7 (§5.2) — this story consumes the Secret, it does not refresh it. "Tokens live only in the
    per-user Secret (never logged/echoed, §17.1)" is the discipline AC4 enforces.
  - **§17.1 — secret hygiene:** "credentials never logged/echoed cross-squad (NFR-SEC3)."
  - **§5.3.4 pod assembly / §8 `Claiming`:** at `Claiming` the reconciler assembles the sandbox pod
    (Story 4.2 filled the RuntimeClass half); **this story fills the credential-mount half** of the same
    assembly — `envFrom: secretRef` / `valueFrom.secretKeyRef` into the runtime container.
- **Design (the contract this story formalizes):** `docs/bmad/design/agent-shim-interface-spec.md`
  - **§7 — Credential injection contract:** env-from-Secret-ref, **no inline secrets**, the shim knows
    only the *shape*, the three runtime-native env shapes, and auth-failure → `auth-required{provider,
    secretRef, detail}` → §11 pause. **This story is the AC-and-falsification form of §7.**
  - **§4 events / §12 conformance:** **C7** (auth-failure → `auth-required`/Paused, never generic
    `failed`) and **C10** (zero-core-change: no `type ==` special-casing) are the conformance ties.
- **ADR / epic decision:** **AD-9** (credential plumbing & graceful pause/resume — the epic-level locked
  decision for Epic 7), **ADR-032** (zero-touch lifecycle). The BYO-per-principal Secret model is LOCKED
  (F15/OQ11 resolved) — do **not** re-open shared-credential or inline-secret alternatives; implement it.
- **Depends on:**
  - **Story 1.2** — `Agent.spec.credentialSecretRef` + the Agent-Card `auth.type` capability (the shape).
  - **Story 4.1** (squad = namespace) — the Secret is the **per-user Secret in the Team namespace**; the
    mount composes on top of the namespace boundary (this is what makes AC5 "never cross-squad" true).
  - **Story 4.2** (RuntimeClass pod assembly) — the same `Claiming` pod-assembly step; this story adds
    the credential env/volume to the pod 4.2 builds.
  - **Shim seam (Epic 5, ISI-2114)** — the reference shim reads only the shape and surfaces
    auth-failure; the buildable shim binary + conformance harness is the ISI-2114 child.
- **Blocks / is consumed by:** **Epic 7** (7.1 per-user Secret refs, 7.2 the pause/resume reconcile loop
  and the §11.1 refresh controller — "coupled with Epic 7" per the epic text), and **every runtime
  family** (each MUST pass conformance C7 with this contract). **Story 5.9** (context-injection contract)
  is the sibling seam — envelope in, credential in — sharing the same "inject-without-leaking" discipline.

## What the reconciler + shim do (the §7/§11 injection contract — authoritative)

At `Claiming`, when the Run reconciler assembles the sandbox pod, it wires the credential by this contract:

1. **Resolve the runtime-native mapping from Agent-Card metadata, not core code (FR-G2, C10).** The
   runtime's advertised `auth.type` (`oauth-subscription` | `api-key` | `byo-endpoint`, and any later
   family) is a **data key** into a mapping table that yields the **env var name** the runtime expects
   (`CLAUDE_CODE_OAUTH_TOKEN`, a provider-named API-key env, a BYO endpoint URL env) and the **Secret
   key** to read. The Run reconciler carries **no `if vendor == …` switch** — a new runtime family is a
   metadata row, not a code branch (the C10 grep gate).

2. **Inject as env/volume FROM a `secretRef` — never inline (AC1, the crux).** The pod spec the
   reconciler writes carries `envFrom: [{secretRef: {name: credentialSecretRef}}]` and/or
   `valueFrom.secretKeyRef` — a **reference**. The credential **value** is materialized by **kubelet**
   into the **runtime container** at run time; it is **never** written into the manifest, etcd-as-
   manifest, a ConfigMap, a command arg, the envelope, or reconciler logs. "Inline the literal" is the
   exact hole this story closes.

3. **Keep the shim out of the credential's trust surface (AC3).** The **shim is a separate sidecar**; it
   is **not** injected with the credential env. It knows only the **shape** (`auth.type` + the Secret ref
   *name*) and observes auth-failure signals. It **cannot** read, log, or stream the raw value because it
   never holds it. Its logs/SSE carry the shape and the ref name — never the value.

4. **Scope the Secret to the Run's own Team namespace — fail-closed (AC5, NFR-SEC3 cross-squad).** The
   reconciler binds only a Secret in the **Run's Team namespace** (Story 4.1). A ref naming another
   team's Secret is **rejected** (`CrossSquadCredentialDenied`) — credentials are never mounted cross-
   squad, so one compromised Run cannot pull another principal's credential.

5. **Persist/log nothing but the reference (AC4, NFR-SEC3 — the load-bearing invariant).** The credential
   **value** appears in **no** sink: Run logs, shim logs, the SSE stream, coord artifacts, the `audit_log`,
   or OTel span/metric attributes. Metering/audit anchors on **`{principal, agent, run, project,
   secretRef}`** (FR-I2 attribution is by *principal*, not by echoing the credential). Any provider error
   string that embeds the token is **scrubbed** before it can leave the shim (the auth-required `detail`
   carries provider + ref, never the value).

6. **Auth-failure → `Paused`, resume on Secret update — one code path (AC6, C7 / FR-G3).** When the
   runtime signals auth failure, the shim emits SSE `auth-required{provider, secretRef, detail}` (ref,
   not value); the Run reconciler transitions to **`Paused`** with an operator-legible condition — **not**
   a generic `failed`. Resume triggers on the referenced **Secret updating** (operator rotation, or the
   §11.1 controller's refresh write-back). One path serves both OAuth-refresh (Claude) and static-key
   (non-Claude) models.

## Acceptance Criteria

**AC1 — the credential is injected env/volume FROM a `secretRef`, never inline.**
Given a Run reaches `Claiming` with `Agent.spec.credentialSecretRef` set, When the sandbox pod is
assembled, Then the runtime container carries the credential via `envFrom: secretRef` and/or
`valueFrom.secretKeyRef` — a **reference** — and the pod spec (manifest/etcd) contains **no credential
literal**. The value is materialized only into the running runtime container by kubelet. A pod spec that
inlines the token value is a **construction failure**.

**AC2 — runtime-native mapping comes from Agent-Card metadata, not a core vendor switch (FR-G2, C10).**
Given a runtime's advertised `auth.type`, When the reconciler chooses the env var name + Secret key,
Then it resolves them by **data lookup on runtime metadata** (`oauth-subscription → CLAUDE_CODE_OAUTH_TOKEN`,
`api-key → provider-named env`, `byo-endpoint → endpoint URL env`, and any later family), with **no
`type ==`/`vendor ==` branch** in the Run reconciler. A new runtime family drops in as a metadata row
with **zero core change** (the C10 zero-core-change gate).

**AC3 — the shim never reads or handles the raw secret; it knows only the shape.**
Given the injected credential, When the shim sidecar runs, Then the credential env is injected into the
**runtime container only** — the shim is **not** given the value. The shim knows the **shape**
(`auth.type`) and the Secret **ref name**, and observes auth-failure signals, so the credential stays out
of the shim's logs, its SSE stream, and its trust surface (§7).

**AC4 — the credential value is never persisted or logged, in any sink (NFR-SEC3, the crux).**
Given the credential in flight, When the Run executes, pauses, fails, or emits artifacts/telemetry, Then
the credential **value** appears in **none** of: Run logs, shim logs, the SSE event stream, coord
artifacts, the `audit_log`, or OTel attributes. Attribution/metering anchors on `{principal, agent, run,
project, secretRef}` — the **reference**, never the value. Any runtime error string embedding the token is
**scrubbed** before it leaves the shim. A credential in a log or a durable store is a **security failure**.

**AC5 — the Secret is scoped to the Run's own Team namespace; cross-squad is fail-closed.**
Given a Run in Team namespace N naming `credentialSecretRef`, When the reconciler binds the Secret, Then
it binds only a Secret **in namespace N** (Story 4.1); a ref resolving to another team's namespace is
**rejected** (`CrossSquadCredentialDenied`), never mounted. Credentials are per-namespace, never
cross-squad (NFR-SEC3).

**AC6 — auth-failure routes to `Paused` (ref-not-value), resume on Secret update; never generic `failed`.**
Given the runtime signals an auth failure, When the shim reports it, Then it emits `auth-required{provider,
secretRef, detail}` — carrying the **ref and provider, never the token** — and the Run reconciler
transitions to **`Paused`** with an operator-legible condition, resuming when the **referenced Secret
updates** (rotation or §11.1 controller refresh). It is **never** a generic `failed` (conformance C7,
FR-G3/S10). One code path serves OAuth-refresh (Claude) and static-key (non-Claude) models.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/credential-injection-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check: it first proves a **naive** injector (inlines the token literal into the pod spec,
lets the shim read + log the raw value, echoes the raw runtime error into the `auth-required` event,
mounts a cross-squad Secret, and hardcodes a vendor `switch` in core) **leaks/violates** the §7/§11
invariants — so the harness demonstrably detects a credential breach — then proves the **§7/§11 contract**
injector (env/volume from a `secretRef` only, shim knows the shape not the value, mapping via Agent-Card
metadata, per-namespace scope, auth-required carries ref-not-value, every sink scrubbed) **passes** all of
them.

```
[model] (A)  naive inline injector writes the token into the pod spec AND leaks it via shim log (teeth)
[model] (B)  contract injector: secretRef-only pod spec; no leak in run_log/shim_log/sse/artifact/audit/otel (AC1/AC3/AC4)
[model] (M)  runtime-native env mapping resolves by Agent-Card metadata; a later family needs NO core edit (AC2/C10)
[model] (S)  a cross-squad Secret mount is fail-closed; naive binder leaks it (AC5/NFR-SEC3)
[model] (P)  auth-failure -> Paused(auth-required), resume-on-Secret-update, ref-not-value; naive echo leaks (AC6/C7)
[model] (N)  audit/artifact/otel carry {principal,agent,run,secretRef} but never the value (AC4)
[model] PASS — naive detectably leaks the credential; §7/§11 injection contract holds AC1-AC6.
```

It encodes AC1–AC6 as assertions over the *pod spec + shim/event behavior a reconciler would produce*:
(a) a `secretRef`-only pod spec vs an inline literal, scanned for the sentinel credential value (AC1);
(b) the env mapping resolved by a metadata table, with a **later** runtime family resolving with no core
branch while the naive `switch` cannot (AC2/C10); (c) the shim carrying only the shape/ref, never the
value (AC3); (d) a **sink scan** of Run logs, shim logs, SSE, artifacts, `audit_log`, and OTel that must
find the value in the naive path and **never** in the contract path (AC4); (e) a cross-squad mount
fail-closed (AC5); (f) auth-failure → `Paused(auth-required)` with a scrubbed, ref-only event (AC6/C7).

**Mutation contract (teeth — re-run after any edit):**
- delete `scrub(...)` in `auth_required_event_contract` (echo the raw runtime error) → **(F1) RED** — the
  token surfaces in the SSE + Run-log sinks.
- make `assemble_pod_contract` inline the literal instead of a `secretRef` mount → **(F2) RED** — the pod
  spec scan finds the credential literal.

Both were exercised: baseline exits 0; each mutation exits 1 on its named AC. **Kernel-level "value never
reaches disk/etcd" is a property of kubelet + the Secret object at runtime** — proven by the runtime
security tests (Epic X / NFR-SEC3 blast-radius, real cluster); the model check guards the **construction-
time crux** (what the reconciler/shim *emit*), which is where the leak is designed in or out.

## Out of scope (owned elsewhere)

- **The zero-touch OAuth refresh controller** (**Epic 7 / §11.1, §5.2, ADR-032**) — the leader-elected
  loop that refreshes the token and writes it back to the same Secret. This story **consumes** the
  Secret at `Claiming`; it does not refresh it.
- **The pause/resume reconcile loop itself** (**Epic 7 / 7.2, §8**) — this story emits the
  `auth-required` signal and names the `Paused` target + resume trigger; the durable Run state machine
  that watches the Secret and re-drives the Run is Epic 7's (composed with Story 3.1/3.2 reconcile).
- **Rate-limit pause/resume** (**§8, §11, ADR-030**) — the sibling `Paused(rate_limited)` clock; distinct
  from auth-failure (a different budget/condition), owned by Story 3.2 / Epic 7.
- **RuntimeClass selection + the rest of pod assembly** (**Story 4.2**, §9.1) — this story adds only the
  credential env/volume to the pod that 4.2 builds.
- **Squad = namespace tenancy** (**Story 4.1**, §12.1) — provides the Team namespace the per-user Secret
  lives in; this story binds within it and fail-closes on cross-squad.
- **The buildable reference shim binary + conformance harness** (**ISI-2114 child**, §13) — the runnable
  `pkg/shim` + `conformance/` that asserts C7/C10 against a live Ollama lane; this story is the *contract*
  + model falsification the harness makes executable.
- **Context/envelope injection + token budget** (**Story 5.9**, §8.5) — the sibling inject-without-leaking
  seam for the *envelope*; shares the discipline, not the payload.
