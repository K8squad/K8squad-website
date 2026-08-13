# Story 7.2: Claude-family OAuth credential (zero-touch lifecycle)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔐 THIS IS THE FIRST OF THE THREE CONCRETE CREDENTIAL STORIES — the Claude-family instantiation of the
> Story 7.1 per-user Secret-ref shape (§11, FR-G2).** Story 7.1 pins the *reference shape* (per-user Secret
> ref, no shared master, per-namespace never cross-squad — ADR-010, LOCKED). This story pins the
> **Claude-family acquisition + lifecycle**: a **one-time OAuth** connect (console **"Connect Claude"** /
> CLI `ksquad auth login`) writes the **access + refresh tokens** into a per-user Secret of 7.1's shape
> (`credentialType: claude-oauth`, `credentialLifecycle: oauth-refresh`), the shim (5.4) maps it to the
> runtime's `CLAUDE_CODE_OAUTH_TOKEN`, and the **zero-touch controller (7.7 / §11.1 / ADR-032)** owns the
> lifecycle. The load-bearing invariant of *this* story is the lifecycle the CEO's 2026-08-12 field finding
> locked in and that **retired the ISI-2112 gate**: **(1)** the leader-elected credential controller is the
> **sole refresher** — it refreshes the ~8h access token **before** it expires and writes back to the
> **SAME** Secret; **(2)** agent pods are **read-only mounters** that never refresh (no thundering-refresh
> race); **(3)** many pods sharing the one Secret run **concurrently** (Paperclip-proven), so shared-
> credential concurrency is **correct, not a conflict**; **(4)** the ~8h expiry **never pauses a Run** — the
> **only** credential pause is `Paused(cred_expired)` at the **~9-day** refresh-window lapse → one-click
> re-login (screen 05 / 8.6); **(5)** the token **material** never lands on a log, Agent Card, or event —
> only `credentialType` / `credentialLifecycle` **metadata** does. A design that refreshes per-pod, stores a
> static non-refreshing bearer, pauses the Run every 8h for a manual `setup-token`, rejects concurrent
> mount, or echoes the token is the **retired ISI-2112 anti-pattern, not a bug ticket**. Read AC2 and AC4
> literally.

## Gate status (read first — the gate is RETIRED, not pending)

**The issue title carries `[GATE: ISI-2112]`; that gate is RETIRED and this story is UNBLOCKED for full
authoring/close — not merely a provisional draft.** ISI-2112 (OAuth setup-token longevity / refresh cadence
/ concurrency-on-one-subscription) was **retired by the CEO on 2026-08-12 (ADR-032)**: Henrik's real-world
Paperclip deployment runs **many concurrent `claude -p` processes against a single `claude login`
credential with no manual refresh**, proving the spike's `.credentials.json`-sharing worry was
over-cautious. The lifecycle is now the **zero-touch controller model (7.7, arch §11.1/§5.2)** — connect-
once OAuth + a leader-elected auto-refresh controller replaces the manual `setup-token` cadence. Per the
epic's spike-gate table (`04-epics-and-stories.md`, ISI-2112 row) and arch **§21**, ISI-2112 is *"largely
resolved, not a gate"* — only refresh **lead-time / window length** remain as controller **tuning** behind
the §11.1 seam. This story therefore **applies** the settled §11.1 decision to the Claude-family credential
path; it does **not** reopen it, and it does **not** wait on a spike.

## Story

As **an enterprise operator running Claude-family squads on my own Anthropic subscription**,
I want **to connect Claude once (browser "Connect Claude" or `ksquad auth login`) and have every
Claude-family Agent draw its token from a per-user Secret that a leader-elected controller silently
auto-refreshes — with many pods sharing one login concurrently and no periodic token chore**,
so that **credential custody stays with me (D3), concurrent Runs on one subscription just work (the
Paperclip field-proven model), I never handle raw token strings, and the only time I touch auth again is a
single re-login click after ~9 days of non-use — never a manual `setup-token` every 8 hours (the retired
ISI-2112 path).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **§9.7 FR-G1** (per-user Secret refs, no shared master — LOCKED),
  **FR-G2** (credential *type + lifecycle* as capability metadata; runtime-neutral, ≥2 concrete stories),
  **FR-G3** (graceful pause/resume on expiry), **D3** (credential custody stays with the principal),
  **NFR-SEC3** (creds never logged/echoed/exposed cross-squad), **S6** (two concrete credential stories at
  v1), **S10** (graceful credential pause/resume).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§11 — Credential Model (Three Concrete Stories).** The credential table's **Claude-family row** is
    exactly this story: *acquisition* = one-time OAuth (console "Connect Claude" / CLI `ksquad auth login`);
    *lifecycle* = zero-touch centralized controller auto-refresh, re-login only after the ~9-day window;
    *Secret shape* = per-user Secret ref holding the **OAuth access + refresh token**. Type + lifecycle are
    **capability metadata** (FR-G2), so the core hardcodes no vendor's flow.
  - **§11.1 — Zero-touch Claude credential lifecycle (ADR-032, the authoritative decision).** The mechanism
    this story encodes: one-time login → access+refresh tokens in a **per-user Secret**; a **leader-elected
    credential controller** (operator-internal, one owner, no race) refreshes the ~8h access token **before
    expiry** and **writes back to the SAME Secret**; agent pods **just mount** it (env/file) — concurrent
    Runs work; **only** a ~9-day refresh-window lapse pauses `Paused(cred_expired)` → console one-click
    re-login. *"Agents never refresh; the auth-failure pause path remains only a backstop."* Tokens live
    **only** in the per-user Secret (never logged/echoed, §17.1); refresh events publish to NATS (§17.4).
  - **§5.2 — the leader-elected credential controller** is a real reconcile loop in the operator manager
    (*"auto-refreshes Claude OAuth tokens before expiry and writes them back to the per-user Secret"*).
  - **§7.2 / §5.1 `Agent` Card** — the card advertises `credentialType` + `credentialLifecycle` metadata;
    for a Claude-family Agent these are `claude-oauth` / `oauth-refresh`. Never the material (NFR-SEC3).
  - **§13 — screen 05 Credentials page** — per-agent health *connected / refreshing / expired*, a
    **"Connect Claude"** button + `ksquad auth login` CLI parity, and **one-click re-login** on the expired
    state. The operator sees status, never token strings (8.6).
  - **§17.1 / NFR-SEC3** — the credential material is never logged/echoed into artifacts or exposed
    cross-squad. This story owns the Claude token's no-echo discipline on the *provision/refresh* path; the
    shim's no-log on the *injected value* is Story 5.4.
- **ADR:** **ADR-032** (zero-touch Claude credential lifecycle — the decision; *rejected* alternatives:
  manual `setup-token` every 8h, per-pod refresh racing the shared Secret, a static non-refreshing bearer,
  a console that exposes raw token strings). **ADR-010 / AD-9** (per-user Secret ref, no shared master — the
  shape this instantiates; **not reopened**).
- **Depends on:**
  - **Story 7.1** (the per-user Secret-ref shape + composer invariants this story produces a Claude Secret
    *of*). This story does not re-implement the ref/no-shared-master/per-namespace guards — it supplies a
    Secret that satisfies them.
  - **Story 1.2 / 1.3** (the `Agent` CRD incl. `credentialSecretRef`, `credentialType` enum incl.
    `claude-oauth`, and the operator/reconciler scaffold).
  - **Story 5.2** (Agent Card generation — carries the `claude-oauth` / `oauth-refresh` metadata).
  - **Story 5.4** (the shim credential-injection contract — maps this Secret to `CLAUDE_CODE_OAUTH_TOKEN`
    without logging it). This story defines *which* Secret and *what* env key; 5.4 owns the mapping seam.
- **Tightly coupled with / consumed by:**
  - **Story 7.7** (the zero-touch controller — the leader-elected reconcile loop that *implements* the
    refresh/write-back this story's lifecycle **contract** requires; §11.1/§5.2/ADR-032). 7.2 is the
    Claude-family *credential + lifecycle contract*; 7.7 is the controller that satisfies it. They ship
    together; if 7.7's controller is not yet landed, gate the runtime lifecycle proof on it and keep this
    story's construction-time contract + model check as the standing gate.
  - **Story 7.4** (graceful pause/resume — the `Paused(cred_expired)` transition + resume-on-refresh this
    story's AC4 names, for the Claude path).
  - **Story 8.6 / §13 screen 05** (the "Connect Claude" one-click UX + health surface + one-click re-login).
  - **Story 13.4 / 13.10** (per-principal consumption attribution — rides the per-user Claude Secret).

## What the Claude-family credential path does (the §11.1 lifecycle contract — authoritative)

1. **One-time OAuth acquisition → per-user Secret with access + refresh tokens (AC1).** The operator
   connects **once**: console **"Connect Claude"** (browser OAuth) or CLI **`ksquad auth login`** (parity
   with the legacy `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`, but the zero-touch model supersedes the
   manual cadence). The resulting **access token AND refresh token** are written to a **per-user Kubernetes
   Secret** of the Story 7.1 shape, in the Agent's own Team namespace. The Secret's
   `credentialType = claude-oauth`, `credentialLifecycle = oauth-refresh`. A **static-only bearer (no
   refresh token)** is rejected — it is the retired path that hard-breaks at the ~8h TTL.

2. **The leader-elected controller is the sole refresher (AC2).** The **credential controller** (§5.2,
   operator-internal, **leader-elected — one owner**) watches token expiry and, **before** the ~8h access
   token expires, refreshes it via the refresh token. **No agent pod ever refreshes** — agents are
   read-only consumers. Over any timeline there is **exactly one writer** of the Secret (the controller); a
   per-pod refresher is the **thundering-refresh race** ADR-032 forbids.

3. **Refresh writes back to the SAME Secret in place (AC3).** The refreshed token is written to the **same
   per-user Secret name** the pods already mount — never a freshly minted Secret. All mounting pods pick up
   the new token without re-referencing anything. Name churn would strand every existing mounter.

4. **The ~8h expiry never pauses a Run; only the ~9-day window lapse does (AC4).** Because refresh is
   pre-emptive, a Running Run **never** pauses on the ~8h boundary. The **only** credential pause is
   `Paused(cred_expired)`, raised **only** when the subscription goes unused long enough (~9 days) that the
   **refresh token itself** expires; the console (screen 05) then shows **"credential expired — click to
   re-login"** (one OAuth click, 8.6). The runtime auth-failure signal (§11) remains a **backstop**, not the
   normal path.

5. **Concurrent pods share one Secret — correct, not a conflict (AC5).** Multiple agent pods mounting the
   **same** per-user Secret and running concurrently is the **intended** model (Paperclip field-proven: many
   concurrent `claude -p` on one credential). The platform never treats shared-credential concurrency as a
   claim/lease conflict or a double-use error.

6. **Metadata surfaces, material never does (AC6).** The Agent Card (5.2) advertises `claude-oauth` /
   `oauth-refresh`; screen 05 shows *connected / refreshing / expired*; refresh events publish to NATS
   (§17.4). **None** of these — and no log line — ever carries the access/refresh token strings (NFR-SEC3,
   §17.1). The shim (5.4) maps the Secret to `CLAUDE_CODE_OAUTH_TOKEN` and nothing else, and never persists
   or logs it.

## Acceptance Criteria

**AC1 — one-time OAuth provisions a per-user Secret holding access + refresh tokens.** Given an operator
connects Claude once (console "Connect Claude" or `ksquad auth login`), When the flow completes, Then the
**access and refresh tokens** are written to a **per-user Kubernetes Secret** of the Story 7.1 shape (in the
Agent's own Team namespace, no shared master), with `credentialType = claude-oauth` and
`credentialLifecycle = oauth-refresh`. A **static-only bearer with no refresh token** is a construction
failure — it is the retired path that breaks at the ~8h access-token TTL.

**AC2 — the leader-elected controller is the sole refresher; agent pods never refresh (the ADR-032 crux).**
Given the provisioned Secret, When the ~8h access token nears expiry, Then the **leader-elected credential
controller** (§5.2) — and only it — refreshes the token; **agent pods are read-only mounters that never
refresh**. Across the whole lifecycle there is **exactly one distinct writer** of the Secret. A **per-pod
refresher** (any pod writing the Secret) is the **thundering-refresh race** ADR-032 rejects, not a runtime
tuning knob.

**AC3 — refresh writes back to the SAME Secret in place.** Given a controller refresh, When the new token is
persisted, Then it is written to the **same per-user Secret name** the pods already mount — never a newly
minted Secret. The Secret name is **stable across every refresh**, so concurrent mounters keep resolving the
current token without re-reference. Minting a fresh Secret per refresh (stranding existing mounters) is a
construction failure.

**AC4 — the ~8h access expiry never pauses a Run; the only credential pause is `Paused(cred_expired)` at the
~9-day window lapse.** Given a Running Run on a Claude-family Agent, When the ~8h access token expires, Then
the Run **does not pause** — the controller's pre-emptive refresh keeps it live. The **only** credential
pause is `Paused(cred_expired)`, raised **only** after the ~9-day refresh-window lapses under inactivity,
resolved by **one-click re-login** (7.4 / 8.6). Any pause at an 8h boundary (a manual `setup-token` reauth)
is the **retired ISI-2112 model**, not this story.

**AC5 — concurrent pods sharing the one Secret run concurrently (Paperclip-proven).** Given N Claude-family
Agent pods mounting the **same** per-user Secret, When they run concurrently, Then all N proceed — shared-
credential concurrency is **correct by construction**, never a claim/lease conflict or double-use error. The
`.credentials.json`-sharing worry the ISI-2112 spike raised is answered in production (§11.1) and is **not**
re-litigated as a runtime guard.

**AC6 — token metadata surfaces; token material never does.** Given a composed/refreshing Claude Agent, When
its state is observed (Agent Card, screen-05 health, NATS refresh events, logs), Then only
`credentialType`/`credentialLifecycle` **metadata** and health states (*connected / refreshing / expired*)
appear — **never** the access/refresh **token strings** (NFR-SEC3, §17.1). The shim (5.4) maps the Secret to
`CLAUDE_CODE_OAUTH_TOKEN` and neither logs nor persists it.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/claude-oauth-lifecycle-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check over the credential **lifecycle a driver would produce** for a fleet of concurrent
Claude agent pods sharing one per-user OAuth Secret across a 12-day hourly timeline. It first proves the
**retired ISI-2112 manual/per-pod lifecycle** (static bearer with no refresh token, each pod re-provisions
its own token at the ~8h boundary → racing writers, the Run pauses every 8h for a manual `setup-token`,
concurrent mount treated as a conflict, token echoed on provision) is **DETECTED as violating every §11.1
invariant** — so the harness has real teeth — then proves the **§11.1 zero-touch lifecycle** violates
nothing and pauses **exactly once**, at the ~9-day window lapse, **only** under idleness.

```
[model] retired manual lifecycle : 6 lifecycle violation(s) -> DETECTED
[model]   - provisioned Secret lacks a refresh token (has_refresh=False) — a static-only bearer ...
[model]   - Secret written by ['pod-0', ... 'pod-5'] — the leader-elected controller must be the SOLE writer ...
[model]   - Run paused for ['reauth_setup_token', ...] — the ~8h expiry must be refreshed, never paused ...
[model]   - concurrent mount of 'alice-claude-oauth' by 6 pods rejected as a conflict ...
[model]   - token material leaked on an observable surface: 'log: minted CLAUDE_CODE_OAUTH_TOKEN=...' ...
[model] §11.1 zero-touch lifecycle: 0 violation(s); active_pauses=[]; idle_pauses=['cred_expired']; writers=['controller']; concurrency_ok=True
[model] PASS — retired manual lifecycle detectably breaks §11.1; the zero-touch controller holds AC1-AC6 ...
```

It encodes AC1–AC6 as assertions over the lifecycle a design would produce: **(AC1)** the provisioned Secret
must hold **both** an access **and** a refresh token and advertise `oauth-refresh` — a static-only bearer is
caught; **(AC2)** the set of distinct Secret **writers** across the timeline must be exactly `{controller}` —
any per-pod writer flips it RED; **(AC3)** every write targets the **same** Secret name — a name churn is
caught; **(AC4)** the pause set must contain **no** 8h-boundary reauth and must be **exactly**
`{cred_expired}` when idle past the ~9-day window and **empty** when active (non-vacuous in both directions);
**(AC5)** concurrent mount of the one Secret must be **admitted**; **(AC6)** no observable surface may
contain token material. Each guard is **independently load-bearing** — mutation-verified: injecting each
single defect into the zero-touch model (drop the refresh token, add a per-pod writer, churn the Secret
name, add an 8h pause, reject concurrency, leak the token) flips the check **RED with exactly one
violation** and no guard shadows another (the ISI-2346-F1 vacuous-tooth class is excluded by construction).
The check exits non-zero if the retired model *stops* violating (teeth lost), if the zero-touch model *ever*
violates an invariant, or if the ~9-day pause fails to fire when idle **or** fires when active.

**Runtime proof (owned by 7.7 + Epic X).** AC2/AC3 (single-writer refresh, in-place write-back) and AC5
(concurrent shared-credential Runs) are proven on a **real cluster** by the 7.7 controller's leader-elected
reconcile + a concurrent-Run test on one Claude Secret; AC4's pause/resume is exercised by 7.4 on the real
`Paused(cred_expired)` transition. The model check guards the **construction-time lifecycle contract**,
which is 7.2's crux and the thing the retired ISI-2112 gate was about.

## Out of scope (owned elsewhere)

- **The per-user Secret-ref shape + composer invariants** (**7.1**, §11/§12.1, ADR-010) — this story
  supplies a Claude Secret *of* that shape; it does not re-implement the no-shared-master / per-namespace
  guards.
- **The zero-touch controller reconcile loop itself** (**7.7**, §5.2/§11.1/ADR-032) — the leader-elected
  loop that performs the refresh + write-back. This story pins the Claude-family **lifecycle contract** that
  controller satisfies; 7.7 builds the controller.
- **The shim credential-injection contract + no-log on the injected value** (**5.4**, §7.3, NFR-SEC3) — how
  the Secret is mapped into the runtime as `CLAUDE_CODE_OAUTH_TOKEN` without being logged. This story names
  the Secret + env key; 5.4 owns the mapping.
- **Graceful pause/resume machinery** (**7.4**, §11/§8, FR-G3/S10) — the `Paused(cred_expired)` state
  transition + resume-on-refresh; this story names the *one* Claude pause reason and *when*, not the
  transition machinery.
- **The console "Connect Claude" UX, health surface, one-click re-login** (**8.6 / §13 screen 05**) — the
  operator-facing OAuth button, *connected/refreshing/expired* health, and re-login click.
- **The second-runtime API-key story (7.3) and BYO-endpoint story (7.5)** — the other two concrete
  credential stories; each is a *different* acquisition/lifecycle over the same 7.1 shape, not Claude-shaped.
- **Rate-limit pause/resume attribution** (**7.6**, §11.1) — a *sibling* pause family (self-recovering,
  per-credential), distinct from this story's credential-expiry pause.
- **Consumption attribution / metering** (**13.4 / 13.10**, §11 consumption note) — rides the per-user
  Claude Secret; this story is the credential, not the metering spine.
