# Story 7.3: Second-runtime API-key credential (vendor-neutral, not Claude-shaped)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔑 THIS IS THE SECOND OF THE THREE CONCRETE CREDENTIAL STORIES — the non-Claude runtime's
> instantiation of the Story 7.1 per-user Secret-ref shape (§11, FR-G2).** Story 7.1 pins the *reference
> shape* (per-user Secret ref, no shared master, per-namespace never cross-squad — ADR-010, LOCKED).
> Story 7.2 is the **Claude-family** instantiation: an *OAuth-refresh* lifecycle (zero-touch controller,
> ~8h access token, ~9-day re-login window). **This story is the deliberate contrast that answers OQ11 /
> Challenger F15**: the OpenClaw/Hermes runtime's credential is a **long-lived API key supplied directly**
> — **no interactive OAuth, no refresh token, no refresh controller, no auto-expiry timer**. Its whole
> lifecycle is **static**: the key changes *only* when the provider rotates it, and **rotation = an
> operator Secret update**. The load-bearing crux of *this* story is that the second-runtime credential
> model is **vendor-neutral, pinned per runtime as capability metadata (FR-G2) — NOT Claude-shaped**. A
> design that grafts Claude's OAuth machinery onto this key — expecting a refresh token, standing up the
> §5.2 controller to "refresh" it every ~8h, minting a fresh Secret per refresh, pausing `cred_expired`
> at ~9 days of inactivity, or **hardcoding the oauth-refresh lifecycle into the core** — has committed
> the **OQ11/F15 category error**, not shipped a feature. Read AC1, AC2, and AC5 literally: the second
> runtime has **nothing to refresh**, and the **core must read the lifecycle from metadata, never assume
> Claude's flow**.

## Gate status (read first)

This story carries **no spike gate**. Unlike 7.2 (whose title carried the now-**RETIRED** `[GATE:
ISI-2112]` — an *OAuth*-longevity spike that does not touch a static key), 7.3's credential has **no OAuth
step**, so no OAuth spike gates it. What 7.3 must do per the epic Notes is **resolve OQ11**: *pin the
exact second-runtime token type + refresh semantics in this story* so the credential model is provably
vendor-neutral. Architecture §11's credential table (the "Second runtime (OpenClaw/Hermes — non-Claude)"
row) already records the decision — **long-lived API key, static lifecycle, refresh only if the provider
rotates, per-user Secret ref** — and §11.1 confirms *"OQ11's exact second-runtime token type/refresh is
still pinned per that runtime's auth model as the shim lands."* This story **applies** that settled §11
decision and pins it with a runnable falsification; it does not reopen it.

## Story

As **an operator running an OpenClaw or Hermes squad against a provider that issues a long-lived API
key**,
I want **to drop my provider API key into a per-user Secret and have every OpenClaw/Hermes Agent draw its
credential from it — with no OAuth dance, no token-refresh chore, and rotation being nothing more than me
updating that Secret**,
so that **the credential model fits *my* runtime's real auth (a static key), custody stays with me (D3),
KSquad never assumes a Claude-shaped OAuth flow it doesn't have, and if the provider ever invalidates my
key mid-Run the Run pauses legibly and resumes the moment I rotate the Secret — never fails opaquely and
never invents a ~9-day expiry my provider never imposed.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **§9.7 FR-G1** (per-user Secret refs, no shared master — LOCKED),
  **FR-G2** (credential *type + lifecycle* as capability metadata; runtime-neutral, ≥2 concrete stories),
  **FR-G3** (graceful pause/resume on expiry/rotation), **D3** (credential custody stays with the
  principal), **NFR-SEC3** (creds never logged/echoed/exposed cross-squad), **S6** (two concrete
  credential stories at v1), **S10** (graceful credential pause/resume). **OQ11** (§ open questions):
  *"Second launch runtime's concrete credential model (token type + refresh semantics for the non-Claude
  runtime), so the credential story is vendor-neutral, not Claude-shaped"* — **this story resolves it**.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§11 — Credential Model (Three Concrete Stories).** The credential table's **"Second runtime
    (OpenClaw/Hermes — non-Claude)"** row is exactly this story: *acquisition* = a long-lived **API key /
    provider token supplied directly** (no interactive OAuth step); *lifecycle* = **static** (no ~8h
    access-token TTL; refresh **only if the provider rotates**); *Secret shape* = per-user Secret ref
    holding the API key. Type + lifecycle are **capability metadata** (FR-G2), so the core hardcodes no
    vendor's flow.
  - **§11 — Graceful pause/resume (both models).** *"Resume triggers on the referenced Secret updating
    (operator rotates the token)."* For the static-key model, the only credential pause is a runtime
    **auth-failure** signal → `Paused` with an operator-legible condition, **resumed when the operator
    updates the Secret** — explicitly *"This holds for both OAuth-refresh (Claude) and static-key (second
    runtime) models."*
  - **§11.1** — confirms OQ11's exact second-runtime token type/refresh *"is still pinned per that
    runtime's auth model as the shim lands"* — i.e. **here**. The zero-touch **controller (§5.2) is a
    Claude-only mechanism**; it does **not** own the static key (there is nothing to refresh).
  - **§7.2 / §5.1 `Agent` Card** — the card advertises `credentialType` + `credentialLifecycle` metadata;
    for a second-runtime Agent these are `openclaw-api-key` (or `hermes-api-key`) / **`static-key`**.
    Never the material (NFR-SEC3).
  - **§13 — screen 05 Credentials page** — per-agent health *connected / (rotating) / invalid*; the
    operator sees status, never the key string (8.6). No "Connect" OAuth button for this runtime — a key
    is pasted/mounted, not authorized via browser.
  - **§17.1 / NFR-SEC3** — the credential material is never logged/echoed into artifacts or exposed
    cross-squad. This story owns the API key's no-echo discipline on the *provision/rotation* path; the
    shim's no-log on the *injected value* is Story 5.4.
- **ADR:** **ADR-010 / AD-9** (per-user Secret ref, no shared master — the shape this instantiates; **not
  reopened**). No new ADR: this story *applies* §11's already-recorded second-runtime row and resolves
  OQ11.
- **Depends on:**
  - **Story 7.1** (the per-user Secret-ref shape + composer invariants this story produces an API-key
    Secret *of*). This story does not re-implement the ref / no-shared-master / per-namespace guards — it
    supplies a Secret that satisfies them.
  - **Story 1.2 / 1.3** (the `Agent` CRD incl. `credentialSecretRef`, `credentialType` enum incl. the
    api-key family, and the operator/reconciler scaffold).
  - **Story 5.2** (Agent Card generation — carries the `openclaw-api-key` / `static-key` metadata).
  - **Story 5.4** (the shim credential-injection contract — maps this Secret to the runtime-native
    API-key env, e.g. `OPENCLAW_API_KEY`, **without logging it**; §5.4's `auth.type = api-key → provider-
    named env` branch). This story defines *which* Secret and *what* lifecycle; 5.4 owns the mapping seam.
  - **Story 5.5** (the OpenClaw + Hermes shims themselves — the runtimes whose credential this is).
- **Tightly coupled with / consumed by:**
  - **Story 7.4** (graceful pause/resume — the `Paused(cred_invalid)` transition + **resume-on-Secret-
    update** this story's AC4 names, for the static-key path; §11 confirms 7.4 covers *both* models).
  - **Story 7.2** (the Claude-family credential — the *other* concrete lifecycle over the same 7.1 shape;
    the deliberate contrast this story is defined against).
  - **Story 7.5** (the BYO-endpoint credential — the *third* concrete story; a static endpoint URL Secret,
    a sibling of this static key, not Claude-shaped either).
  - **Story 8.6 / §13 screen 05** (the health surface — *connected / rotating / invalid*; no OAuth button).
  - **Story 13.4 / 13.10** (per-principal consumption attribution — rides the per-user API-key Secret).

## What the second-runtime credential path does (the §11 static-key model — authoritative)

1. **Direct API-key acquisition → per-user Secret (AC1).** The operator supplies the provider's
   **long-lived API key** directly (paste in screen 05 / `kubectl`-mounted Secret / CLI). It is written to
   a **per-user Kubernetes Secret** of the Story 7.1 shape, in the Agent's own Team namespace. The
   Secret's `credentialType = openclaw-api-key` (or `hermes-api-key`), `credentialLifecycle = static-key`.
   There is **no OAuth flow** and **no refresh token** — a provisioning path that runs OAuth or stores a
   refresh token has Claude-shaped the second runtime (the OQ11/F15 category error).

2. **No refresh controller — the key is static (AC2).** A long-lived API key has **no ~8h access-token
   TTL**, so there is **nothing to refresh** and the leader-elected §5.2 credential controller does **not**
   touch it. Over the credential's whole lifetime the **only** writer of the Secret is the **operator**
   (initial provision + any rotation). A controller "refresh" write on this key is the Claude lifecycle
   grafted onto a static key.

3. **Rotation = an in-place operator Secret update (AC3).** The only way the credential changes is the
   operator rotating the provider key and **updating the SAME per-user Secret name in place**; all mounting
   pods pick up the new key. Minting a fresh Secret per rotation (stranding existing mounters) is a
   construction failure — same discipline as 7.2's AC3, different trigger (operator, not controller).

4. **No auto-expiry pause; the only pause is auth-failure → resume-on-Secret-update (AC4).** Because a
   static key does not self-expire on an ~8h or ~9-day timer, a Running Run **never** pauses on a Claude
   window. The **only** credential pause is `Paused(cred_invalid)`, raised on a runtime **auth-failure**
   signal (e.g. the provider revokes/rotates the key out-of-band), and it **resumes when the operator
   updates the referenced Secret** (§11, the shared 7.4 machinery). A `cred_expired` pause fired on a
   ~9-day inactivity timer is the Claude lifecycle misapplied.

5. **Lifecycle pinned per runtime as metadata; the core is vendor-neutral (AC5 — the OQ11/F15 crux).** The
   credential lifecycle (`static-key` vs `oauth-refresh`) is advertised as **per-runtime capability
   metadata** on the Agent Card / shim (FR-G2) and the **core reads it** — it does **not** hardcode any
   vendor's flow. The core dispatches the same for both families, branching **only** on the metadata. A
   core that bakes in Claude's oauth-refresh lifecycle for every runtime (so the second runtime inherits an
   ~8h-refresh / ~9-day-window it never has) is the OQ11/F15 not-vendor-neutral defect this story exists to
   forbid.

6. **Metadata surfaces, material never does (AC6).** The Agent Card (5.2) advertises `openclaw-api-key` /
   `static-key`; screen 05 shows *connected / rotating / invalid*; rotation events publish to NATS
   (§17.4). **None** of these — and no log line — ever carries the API-key string (NFR-SEC3, §17.1). The
   shim (5.4) maps the Secret to the runtime-native `*_API_KEY` env and nothing else, and never persists or
   logs it.

## Acceptance Criteria

**AC1 — a directly-supplied API key provisions a per-user Secret; no OAuth, no refresh token.** Given an
operator supplies the second runtime's long-lived provider API key, When it is provisioned, Then the key is
written to a **per-user Kubernetes Secret** of the Story 7.1 shape (in the Agent's own Team namespace, no
shared master), with `credentialType = openclaw-api-key` (or `hermes-api-key`) and
`credentialLifecycle = static-key`. There is **no interactive OAuth step and no refresh token** — an OAuth
acquisition or a stored refresh token is a construction failure (it is Claude-shaping the second runtime,
the OQ11/F15 category error).

**AC2 — the credential is static: no refresh controller ever writes it (the OQ11/F15 crux).** Given the
provisioned API-key Secret, When time passes, Then the **leader-elected §5.2 credential controller does
not refresh it** — a static key has no ~8h TTL to refresh. Across the whole lifecycle the **only** writer
of the Secret is the **operator** (provision + rotation); there is **exactly zero** controller-refresh
write. Any controller/per-pod refresh write is the Claude lifecycle wrongly grafted onto a static key.

**AC3 — rotation is an in-place update of the SAME Secret.** Given the operator rotates the provider key,
When the new key is persisted, Then it is written to the **same per-user Secret name** the pods already
mount — never a newly minted Secret. The Secret name is **stable across every rotation**, so concurrent
mounters keep resolving the current key without re-reference. Minting a fresh Secret per rotation
(stranding existing mounters) is a construction failure.

**AC4 — no auto-expiry pause; the only credential pause is `Paused(cred_invalid)`, resumed on the operator's
Secret update.** Given a Running Run on a second-runtime Agent, When the ~8h and ~9-day Claude windows pass,
Then the Run **does not pause** — a static key has no such timers. The **only** credential pause is
`Paused(cred_invalid)`, raised **only** on a runtime **auth-failure** signal (the provider invalidated the
key), and it **resumes when the operator updates the referenced Secret** (§11 / 7.4). Any `cred_expired`
pause on a ~9-day inactivity timer, or a `reauth_setup_token` pause at an ~8h boundary, is the retired /
Claude model, not this story. *(Non-vacuous: the model must both* stay silent *through the Claude windows*
and *actually fire exactly one `cred_invalid` + resume on the Secret update when the provider revokes the
key.)*

**AC5 — token type/refresh is pinned per runtime as metadata; the core is vendor-neutral.** Given both a
Claude-family and a second-runtime Agent, When the core resolves each credential's lifecycle, Then it reads
the **per-runtime `credentialLifecycle` capability metadata** (FR-G2) — `oauth-refresh` for Claude,
**`static-key`** for the second runtime — and applies exactly that. The **core hardcodes no vendor's flow**:
a core that applies `oauth-refresh` to the second runtime (or otherwise ignores the pinned metadata) is the
OQ11/F15 not-vendor-neutral defect. This story **pins the second-runtime token model and resolves OQ11**.

**AC6 — key metadata surfaces; key material never does.** Given a composed/rotating second-runtime Agent,
When its state is observed (Agent Card, screen-05 health, NATS rotation events, logs), Then only
`credentialType`/`credentialLifecycle` **metadata** and health states (*connected / rotating / invalid*)
appear — **never** the API-key string (NFR-SEC3, §17.1). The shim (5.4) maps the Secret to the runtime-
native `*_API_KEY` env and neither logs nor persists it.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/second-runtime-apikey-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check over the credential **lifecycle a driver would produce** for a second-runtime
(OpenClaw/Hermes) API-key Agent across a 12-day hourly timeline. It first proves the **OQ11/F15
Claude-shaped lifecycle** (interactive-OAuth acquisition storing a refresh token, the §5.2 controller
"refreshing" the key every ~8h, a fresh Secret minted per refresh, a spurious ~9-day `cred_expired` pause,
a core that hardcodes `oauth-refresh` for every runtime, and the key echoed on provision) is **DETECTED as
violating every static-key invariant** — so the harness has real teeth — then proves the **§11 static-key
lifecycle** violates nothing and pauses **exactly once**, on a provider **auth-failure**, resuming when the
operator updates the Secret.

```
[model] Claude-shaped second-runtime lifecycle : 6 violation(s) -> DETECTED
[model]   - acquisition is not a direct API key (has_refresh=True, acquired_via='interactive-oauth') — ...
[model]   - Secret written by non-operator ['controller'] — a static key has no ~8h TTL to refresh ...
[model]   - writes churn Secret name(s) [...] != {'alice-openclaw-apikey'} — rotation is in-place ...
[model]   - Run paused for ['cred_expired'] — a static key does not self-expire on an ~8h/~9-day timer ...
[model]   - core applied lifecycle 'oauth-refresh' ... expected 'static-key' — the core must be vendor-neutral ...
[model]   - key material leaked on an observable surface: 'log: minted OPENCLAW_API_KEY=...' ...
[model] §11 static-key lifecycle: 0 violation(s); pauses=['cred_invalid']; resumes=['secret_updated']; writers=['operator']; core_applies='static-key'
[model] PASS — the Claude-shaped lifecycle detectably breaks the static-key model; the §11 second-runtime
        path holds SC1-SC6 ... and pauses exactly once on a provider auth-failure, resuming on the
        operator's Secret update.
```

It encodes AC1–AC6 as assertions (SC1–SC6) over the lifecycle a design would produce: **(SC1)** the
provisioned Secret must hold an **API key**, **no** refresh token, acquired **directly** (not via OAuth);
**(SC2)** the Secret's write actors must be exactly `{operator}` with **zero** `refresh`-kind writes — any
controller refresh flips it RED; **(SC3)** every write targets the **same** Secret name — a name churn is
caught; **(SC4)** the pause set must contain **no** `cred_expired`/`reauth` and must be **exactly**
`{cred_invalid}` with a `secret_updated` resume (non-vacuous in both directions); **(SC5)** the lifecycle
the **core applies** must equal the runtime's **pinned Agent-Card metadata** and be `static-key` — a
hardcoded `oauth-refresh` core flips it RED; **(SC6)** no observable surface may contain key material.

Each guard is **independently load-bearing** — mutation-verified via `--mutate=NAME`, which injects one
single defect into the conformant static-key path (`OAUTH_ACQUIRE`, `CONTROLLER_REFRESH`, `SECRET_CHURN`,
`NINE_DAY_PAUSE`, `CORE_HARDCODE`, `LEAK`) and flips the check **RED with exactly one violation** and no
guard shadowing another (the ISI-2346-F1 vacuous-tooth class is excluded by construction). Baseline
`python3 second-runtime-apikey-check.py` exits 0; each `--mutate=NAME` exits 1 with exactly one violation.
The check exits non-zero if the Claude-shaped model *stops* violating (teeth lost), if the static-key model
*ever* violates an invariant, or if the `cred_invalid` pause + `secret_updated` resume fails to fire.

**Runtime proof (owned by 5.4 + 7.4 + the ISI-2114 conformance lane).** AC1/AC3 (the actual mounted API-key
Secret + in-place rotation), AC4 (the real `Paused(cred_invalid)` → resume-on-Secret-update transition), and
AC6 (no-log on the injected value) are proven on a **real cluster** by 5.4's injection contract, 7.4's
pause/resume, and the OpenClaw/Hermes conformance run. The model check guards the **construction-time
credential model** — 7.3's crux and the thing OQ11/F15 asked (vendor-neutral, not Claude-shaped).

## Out of scope (owned elsewhere)

- **The per-user Secret-ref shape + composer invariants** (**7.1**, §11/§12.1, ADR-010) — this story
  supplies an API-key Secret *of* that shape; it does not re-implement the no-shared-master / per-namespace
  guards.
- **The shim credential-injection contract + no-log on the injected value** (**5.4**, §7.3, NFR-SEC3) — how
  the Secret is mapped into the runtime as its `*_API_KEY` env without being logged (the `auth.type =
  api-key` branch). This story names the Secret + lifecycle; 5.4 owns the mapping.
- **The OpenClaw/Hermes shims themselves** (**5.5**, §10.1) — the runtimes whose credential this is.
- **Graceful pause/resume machinery** (**7.4**, §11/§8, FR-G3/S10) — the `Paused(cred_invalid)` state
  transition + resume-on-Secret-update; this story names the *one* static-key pause reason and *when*, not
  the transition machinery. §11 confirms 7.4 covers **both** the OAuth-refresh and static-key models.
- **The Claude-family OAuth credential + zero-touch controller** (**7.2 / 7.7**, §11.1/ADR-032) — the
  *other* concrete lifecycle and the controller that serves it. This story is the deliberate **contrast**:
  the second runtime has no OAuth and no controller.
- **The BYO-endpoint credential** (**7.5**, §10.3/ADR-026) — the *third* concrete story (endpoint URL [+
  optional token] Secret), a sibling static shape, likewise not Claude-shaped.
- **The console health surface** (**8.6 / §13 screen 05**) — the *connected / rotating / invalid* states;
  this story names the health metadata, not the UI.
- **Rate-limit pause/resume attribution** (**7.6**, §11.1) — a *sibling* pause family (self-recovering,
  per-credential), distinct from this story's credential-invalid pause.
- **Consumption attribution / metering** (**13.4 / 13.10**, §11 consumption note) — rides the per-user
  API-key Secret; this story is the credential, not the metering spine.
