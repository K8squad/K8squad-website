# Story 7.1: Per-user Secret refs (BYO, no shared master)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔐 THIS STORY PINS THE EPIC-7 CREDENTIAL LOCK — every `Agent` runs on a per-user Secret ref; KSquad
> holds NO shared master credential; credentials are per-namespace, never cross-squad (arch §11, §12.1,
> AD-9 / ADR-010, FR-G1, D3, NFR-SEC3).** This is the *invariant* story of Epic 7: it does not implement a
> concrete acquisition flow (that is 7.2 Claude-OAuth / 7.3 second-runtime API key / 7.5 BYO endpoint —
> each an instantiation of *this* shape). It fixes the three load-bearing invariants those stories, the
> shim injection seam (5.4), the consumption-attribution spine (13.4), and the tenancy boundary (4.1)
> all build on: **(1)** an `Agent` references its credential via a **per-user Kubernetes Secret ref**
> (`Agent.spec.credentialSecretRef`, or the §10.3 `modelEndpointRef` Secret for a BYO endpoint) — a bare
> **name resolved in the Agent's own namespace**, never a shared/default token; **(2)** KSquad stores **no
> shared master credential** — there is no platform-level provider key an Agent can resolve to, and a
> missing ref is a **rejection, not a fallback**; **(3)** the resolved Secret lives in the **Agent's own
> Team namespace** (§12.1) — a cross-namespace / `ksquad-system` ref is **rejected fail-closed**, so a
> squad can never reference another squad's credential. A composer that resolves a missing ref to a shared
> master, honors a namespace-qualified cross-squad ref, or admits a control-plane master Secret is a
> **security failure, not a bug ticket**. Read AC2 and AC3 literally.

## Gate status (read first)

**No spike gate.** Unlike Story 4.2 (ISI-2113 RuntimeClass) this story introduces **no OAuth flow, no new
runtime, and no measurable performance trade** — it is a construction-time invariant over the credential
*reference shape*, already locked by **ADR-010** (per-user Secret ref; shared service account excluded by
lock) and reinforced by **CEO 2026-08-12** (zero-touch controller 7.7 / ADR-032 — the controller owns
refresh but each principal's Secret is still its own; §11.1). This story **applies** that locked decision
to the Agent composer/reconciler; it does **not** reopen it. The runtime proof that the boundary holds is
the **cross-squad blast-radius / hostile-Run test (Epic X.1, S4, NFR-SEC1)** — a Run in squad A cannot read
squad B's Secret — which composes on top of Story 4.1's namespace boundary.

## Story

As **an enterprise operator composing squads on my own model subscriptions**,
I want **every `Agent` to reference its provider credential via a per-user Kubernetes Secret ref resolved
in the Agent's own Team namespace — with KSquad holding no shared master credential and no cross-squad
Secret reference ever admitted**,
so that **credential custody stays with the principal (D3): one user's subscription can never be silently
shared, mis-charged, or leaked to another squad; the platform is never a single-point credential honeypot;
and consumption is attributable per principal by construction (§11, feeds 13.4) — enforced by the composer,
not by operator good behavior.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **§9.7 FR-G1** (per-user Secret refs, BYO; no shared master — LOCKED),
  **FR-G2** (runtime-neutral, ≥2 concrete stories — not Claude-shaped), **FR-G3** (graceful pause/resume on
  expiry), **D3** (credential custody stays with the principal), **NFR-SEC3** (creds never logged/echoed/
  exposed cross-squad), **NFR-SEC1** (cross-squad isolation), **S6** (two concrete credential stories ship
  at v1), **S10** (graceful credential pause/resume).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§11 — Credential Model (Three Concrete Stories).** The authoritative decision this story encodes:
    **per-user Kubernetes Secret refs on the `Agent` CRD (FR-G1, LOCKED); KSquad never holds a shared master
    credential.** Credential *type + lifecycle* are capability metadata on the shim/Agent Card (FR-G2), so
    the core hardcodes no vendor's auth flow. The three v1 stories (Claude-OAuth 7.2, second-runtime API key
    7.3, BYO endpoint 7.5) are **instantiations of this one shape**; this story is the shape.
  - **§11 consumption note** — *"Because every credential is a per-user Secret ref (FR-G1, LOCKED) and
    KSquad holds no shared master credential, consumption is attributable to the owning principal **by
    construction** … no shared-credential disambiguation problem."* The per-user lock is *why* 13.4 metering
    is attributable — this story is that lock's load-bearing half.
  - **§11.1 — zero-touch controller (ADR-032).** The credential controller auto-refreshes and **writes back
    to the SAME per-user Secret**; agent pods are **read-only consumers** that just mount it. That model
    **reinforces, never reopens** the per-user ref lock — the controller holds no shared master; each
    principal's Secret is its own. This story keeps the Agent a read-only consumer of a per-user ref.
  - **§12.1 — tenancy boundary (a squad is a namespace).** *"A Team's Projects, Runs, sandbox pods,
    workspace PVCs, and **per-user Secrets** live in its namespace."* Within a Team namespace, per-principal
    Secret isolation is enforced by RBAC + §9.4 workspace scoping. **AC3 is this bullet made a composer
    invariant:** the referenced Secret must live in the Agent's own namespace.
  - **§5.1 `Agent` CRD row** — `credentialSecretRef` (the per-user Secret; *"Agent reconciler → validates
    Secret + runtime, publishes Agent Card"*), plus `modelEndpointRef?` (§10.3 BYO endpoint Secret). The
    Agent is a **namespaced** CRD living in its Team namespace (§12.1); `credentialSecretRef` is a **bare
    name resolved in that namespace** — never a namespace-qualified cross-ns pointer.
  - **§17.1 / NFR-SEC3** — the credential material itself is never logged/echoed into artifacts or exposed
    cross-squad. This story governs the *reference*; the shim's no-log discipline on the *value* is Story
    5.4 (injection contract, out of scope here).
- **ADR:** **AD-9 / ADR-010** (*Credentials — per-user Secret ref; two concrete stories; type as
  capability; shared service account **excluded by lock***) — the locked decision. **ADR-032** (zero-touch
  controller — reinforces the lock). Do **not** re-litigate the per-user shape; implement it.
- **Depends on:**
  - **Story 1.2** (the `Agent` CRD type incl. `credentialSecretRef` + `modelEndpointRef?`, §5.1 row r26)
    and **Story 1.3** (operator scaffold / Agent reconciler). If the type is not yet generated, wire the
    invariant against the §5.1 row and gate envtest on it.
  - **Story 4.1** (squad = namespace tenancy) — the namespace this story resolves Secrets *within*, and the
    RBAC floor that keeps them per-principal (Story 4.1 F1: the agent SA gets `secrets: get` **by name
    only**, never a namespace-wide `list` — the RBAC counterpart to this story's composer invariant).
- **Blocks / is consumed by:** **7.2 / 7.3 / 7.5** (the three concrete credential stories — each supplies a
  per-user Secret of this shape), **7.4 / 7.6** (pause/resume on the per-user Secret's expiry / rate-limit),
  **7.7** (zero-touch controller writes back to this per-user Secret), **Story 5.4** (shim injects *this*
  Secret and never logs it), **Story 13.4 / 13.10** (per-principal consumption attribution rides this
  lock), **Epic X.1** (the cross-squad blast-radius test that *proves at runtime* squad A cannot read squad
  B's Secret — the hard gate this boundary must satisfy).

## What the composer/reconciler does (the §11 + §12.1 credential-ref contract — authoritative)

When the Agent reconciler composes an Agent (validates its Secret + runtime and publishes the Agent Card,
§5.1), it resolves the credential reference by this contract:

1. **Require a per-user credential ref (AC1, fail-closed).** The Agent must carry a `credentialSecretRef`
   (or, for a §10.3 BYO endpoint, a `modelEndpointRef` Secret). A **missing/empty** ref is a **rejection**
   (`CredentialRefMissing` condition) — the reconciler **never** falls back to a platform-default or shared
   token to "keep the Agent composable." No ref, no compose.

2. **Resolve the ref in the Agent's OWN namespace, name-only (AC3, §12.1).** `credentialSecretRef` is a
   **bare Secret name**, looked up in the Agent's Team namespace. A **namespace-qualified** ref
   (`{name, namespace}`) whose namespace is **not** the Agent's own is **rejected fail-closed**
   (`CrossNamespaceCredentialRef` condition). This is what makes "per-namespace, never cross-squad" true by
   construction — a squad literally cannot name another squad's Secret.

3. **Reject shared-master / control-plane Secrets (AC2, AD-9).** KSquad maintains **no** shared master
   credential catalog. A ref that resolves into `ksquad-system` (the control plane) or names a well-known
   shared master is **rejected** — there is no platform provider key for an Agent to point at. Custody
   stays with the principal (D3).

4. **Publish the Agent Card with credential *metadata*, never the value (AC4, §11/FR-G2).** The reconciler
   validates the referenced Secret **exists** and advertises its **`credentialType` + `credentialLifecycle`
   capability metadata** (Claude-OAuth / API-key / BYO-endpoint) on the Agent Card — it **never** reads,
   logs, or embeds the credential **material** (NFR-SEC3, §17.1). The Agent remains a **read-only consumer**
   of a per-user Secret the §11.1 controller (7.7) owns/refreshes.

5. **Per-principal within the namespace (AC5, defense-in-depth).** Two Agents in the **same** squad
   namespace, owned by different principals, reference **different** per-user Secrets — the composer never
   collapses them onto one shared Secret. Namespace membership is the outer bound; per-principal Secret
   naming + the Story 4.1 F1 get-by-name RBAC floor is the inner one (§12.1, §9.4).

## Acceptance Criteria

**AC1 — every composed Agent resolves to a per-user Secret ref; a missing ref is rejected, never
defaulted.** Given an Agent reaches composition, When the reconciler resolves its credential, Then it
resolves to a **per-user** Secret ref (`credentialSecretRef`, or the §10.3 `modelEndpointRef` Secret) — and
an Agent with **no** credential ref is **rejected** (`CredentialRefMissing`), **never** silently composed
against a platform-default / shared token. A shared-token fallback is a **construction failure**, not a
runtime check.

**AC2 — KSquad stores no shared master credential (the AD-9 crux, fail-closed).** Given the platform, When
Agents are composed, Then there is **no shared master credential** any Agent can resolve to: no
platform-level provider-key catalog exists, and a ref that resolves into the control-plane namespace
(`ksquad-system`) or names a well-known shared master is **rejected**. Every credential is a per-user Secret
whose custody stays with the principal (D3) — the platform is never a single-point credential honeypot.

**AC3 — creds are per-namespace, never cross-squad.** Given an Agent in Team namespace *N*, When its
credential ref is resolved, Then the resolved Secret lives in **namespace *N*** — a **name-only** ref
resolves in-namespace by construction, and a **namespace-qualified** ref naming a **different** namespace
(another squad's, or `ksquad-system`) is **rejected fail-closed** (`CrossNamespaceCredentialRef`). A squad
can never reference another squad's Secret (§12.1, NFR-SEC1).

**AC4 — the Agent Card carries credential *metadata*, never the material.** Given a composed Agent, When its
Agent Card is published, Then it advertises `credentialType` + `credentialLifecycle` capability metadata
(FR-G2) and the reconciler validates the Secret **exists** — but it **never reads, logs, or embeds the
credential value** (NFR-SEC3, §17.1). The Agent is a **read-only consumer** of the per-user Secret the
§11.1 controller owns.

**AC5 — per-principal within a squad namespace.** Given two Agents in the **same** namespace owned by
different principals, When both are composed, Then they reference **distinct** per-user Secrets — the
composer never collapses different principals onto one shared Secret. Namespace is the outer isolation
bound; per-principal Secret naming + the Story 4.1 F1 get-by-name RBAC floor is the inner one (§9.4/§12.1).

**AC6 — the cross-squad blast-radius gate is satisfiable.** Given the per-user/per-namespace boundary this
story pins, When Epic X.1's hostile-Run blast-radius test attacks a Run (attempt to read another squad's or
the control plane's Secret), Then the attempt is **contained** — there is no shared master to reach, no
cross-squad ref was ever admitted, and the namespaced get-by-name RBAC (4.1) denies the reach. This story
builds the construction-time boundary; X.1 attacks it at runtime and is the hard gate.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/per-user-secret-ref-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check: it models the *credential resolution an Agent composer/reconciler would produce* for
sample Agents across two squads, then asserts the §11 + §12.1 invariants. It first proves a **naive**
composer (keeps a shared master catalog, resolves a missing ref to that master, honors namespace-qualified
cross-namespace + `ksquad-system` refs verbatim) **violates** the invariants — so the harness demonstrably
detects a credential-isolation break — then proves the §11/§12.1 composer **violates nothing** and
**rejects exactly** the hostile Agents.

```
[model] naive composer : 12 credential-isolation violation(s) -> DETECTED; rejected=[]
[model] §11 composer    : 0 violations; rejected=['master-grab', 'master-grab-local', 'no-cred', 'xsquad-leak']; admitted=3
[model] PASS — naive detectably breaks credential isolation; §11/§12.1 composer holds AC1-AC3 (per-user Secret ref, no shared master, per-namespace never cross-squad).
```

It encodes the AC1–AC3 invariants as assertions over the *resolution + admission decision a reconciler
would produce* for sample Agents: (a) every admitted Agent resolves to a **per-user** Secret, and a missing
ref is **rejected** — not defaulted to a shared master (AC1); (b) the platform holds **no shared master
catalog**, and no resolved Secret is a control-plane / well-known-master Secret (AC2, the crux) — the
`master-grab-local` case (a shared-master name in the Agent's **own** namespace) is what gives the AC2
name-guard **independent teeth**: a control-plane-qualified master (`master-grab`) would already be caught
by the AC3 cross-namespace branch, so only a name-only own-ns master forces the shared-master-name check to
be the decisive rejector (mutation-verified: dropping that guard admits `master-grab-local` → the check
goes RED); (c) the resolved Secret's namespace **equals the Agent's own** — derived from the ref, not
hardcoded — so a cross-namespace ref is a violation the composer must **reject**, not resolve (AC3). The valid name-only Agents pass under **both** composers, so the signal
is crisply the hostile-ref handling; it exits non-zero if the naive composer *stops* violating (teeth lost),
if the naive composer *rejects* a hostile ref (it must admit them, proving the teeth are real), or if the
§11/§12.1 composer *ever* violates an invariant or fails to reject exactly the expected hostile set.
**AC4 (no material logged), AC5 (per-principal distinctness at scale), and AC6 (runtime cross-squad
containment)** are pinned in prose here — AC4/AC5 are code-review + envtest properties of the reconciler,
AC6 is **proven at runtime by Epic X.1's blast-radius test** on a real cluster; the model check guards the
*static resolution/admission shape* (AC1–AC3), which is the construction-time crux.

## Out of scope (owned elsewhere)

- **The three concrete acquisition flows** — **7.2** (Claude one-time OAuth → `CLAUDE_CODE_OAUTH_TOKEN`),
  **7.3** (second-runtime long-lived API key), **7.5** (BYO Ollama / OpenAI-compatible endpoint URL) — each
  supplies a per-user Secret of *this* shape; this story pins the shape, not the acquisition.
- **Graceful pause/resume on credential expiry / rate-limit** (**7.4 / 7.6**, §11/§8, FR-G3/S10) — the
  lifecycle on top of the per-user Secret; this story establishes the ref, not the pause machinery.
- **Zero-touch refresh controller** (**7.7**, §11.1, ADR-032) — the leader-elected loop that writes the
  refreshed token **back to this per-user Secret**; this story keeps the Agent a read-only consumer of it.
- **The shim credential-injection contract + no-log discipline on the *value*** (**5.4**, §7.3, NFR-SEC3) —
  how the per-user Secret is mapped into the runtime's env/volume without being logged; this story governs
  the *reference*, not the injection of the material.
- **Namespace + RBAC + NetworkPolicy provisioning** (**4.1**, §12.1) — the per-Team namespace and the
  get-by-name secrets RBAC floor this story resolves *within*; it does not provision the namespace.
- **Per-principal workspace/PVC scoping + reuse-residue proof** (**4.5**, §9.4/§9.3) — the workspace half of
  per-principal isolation; complements, but is not, the credential-ref boundary.
- **Consumption attribution / metering** (**13.4 / 13.10**, §11 consumption note) — *rides* this lock (per-
  user ref → per-principal attribution by construction); this story is the lock, not the metering spine.
- **The cross-squad blast-radius test itself** (**Epic X.1**, S4, NFR-SEC1) — this story builds the
  construction-time boundary; X.1 attacks it at runtime and is the hard gate.
