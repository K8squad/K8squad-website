---
title: "Spike ISI-2112 — claude setup-token longevity + headless Claude Code behavior"
author: Winston (Architect)
date: 2026-08-12
issue: ISI-2112
status: complete
decision: GO — credential-model recommendation SUPERSEDED 2026-08-12 (see banner)
gates_unblocked: [Epic 3, Epic 4, Epic 5, Epic 7]
supersedes_note: "The 'static bearer per seat / NO-GO on shared .credentials.json' recommendation is superseded by the CEO field finding + controller model in arch §11.1 / ADR-032 / Epic 7 Story 7.7."
---

# Spike ISI-2112 — Headless Claude Code on a Pro/Max subscription

> ## ⚠️ REVISION 2026-08-12 — credential-model recommendation SUPERSEDED
> **The core GO stands** (headless Claude Code on a subscription works — verified below).
> **What changed:** this spike recommended *"one static `setup-token` bearer per seat, NO-GO on
> sharing `.credentials.json` across replicas"* out of a refresh-token-rotation-race concern.
> **CEO field finding (Henrik, 2026-08-12):** Paperclip already runs **many concurrent `claude -p`
> processes on one host against a single `claude login` credential with no manual refresh** — the
> sharing concern was **over-cautious**. The refresh race is eliminated not by avoiding sharing but by
> **centralizing refresh in one owner**.
> **Adopted model (authoritative):** connect-once OAuth → tokens in one per-user K8s Secret → a
> **leader-elected credential controller** auto-refreshes the ~8h access token before expiry and writes
> back to the *same* Secret → agent pods are **read-only mounters** (concurrent Runs share one token) →
> re-login only if the ~9-day refresh window lapses (one-click, console screen 05). See
> **arch `03-architecture.md` §11.1 / ADR-032** and **Epic 7 Story 7.7** — those are the source of truth.
> The empirical measurements and failure-mode analysis below remain valid *as data*; only the
> **§"GO / NO-GO" recommendation** is overridden by the controller model.

## Question
Can Claude Code run **headless in a container** on a Pro/Max subscription via
`CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`)? Produce a go/no-go for the
BYO-subscription credential model + token-rotation requirements.

## TL;DR — **GO**, with one hard constraint
- **GO** for headless Claude Code on a subscription. Verified live: `claude -p`
  print mode runs the full agentic loop non-interactively and returns clean JSON.
- **Use the `setup-token` model** (`CLAUDE_CODE_OAUTH_TOKEN` env, one token per
  subscription/seat). This is the only model that fans out safely.
- **NO-GO for sharing a mounted `~/.claude/.credentials.json` across parallel
  replicas** — refresh-token rotation makes concurrent consumers knock each other
  offline (see Model A).
- **Open risk (not an architecture blocker):** running a multi-agent product on a
  *single* consumer Pro/Max sub is a Terms-of-Service gray area. BYO-per-seat is
  defensible; pooling many agents on one company sub needs a legal/AUP check →
  delegated as a child issue.

---

## Empirical findings (this container, verified 2026-08-12 ~01:04Z)

Claude Code **v2.1.217**, running headless in this container.

### 1. Headless print mode works
`claude -p "…" --output-format json` returned:
```
result: HEADLESS_OK   is_error: false   num_turns: 1   duration_ms: 1430
total_cost_usd: 0.1385   session_id: present
```
Full tool/MCP loop is available headless (`num_turns` can exceed 1). Only the
interactive TUI (`/`-slash UI) and the **browser OAuth login flow** are unavailable.

> **Cost note:** `total_cost_usd` is reported even under a subscription. It is a
> **notional API-equivalent** figure, *not* an actual charge — subscription usage
> is not metered per-token. Useful for internal cost attribution, misleading if
> read as real billing.

### 2. Credential mechanism observed here
This container authenticates via `~/.claude/.credentials.json` → `claudeAiOauth`
(the *interactive-login* refresh-token model, **not** a setup-token). Redacted schema:

| field | value (redacted) | meaning |
|---|---|---|
| `accessToken` | 108-char opaque | short-lived bearer |
| `refreshToken` | 108-char opaque | rotates on each use |
| `expiresAt` | 2026-08-12T08:11:22Z | **access token ~8h window** (~7h left at obs.) |
| `refreshTokenExpiresAt` | 2026-08-21T01:45:18Z | **refresh token ~9-day sliding window** |
| `scopes` | `user:inference`, `user:sessions:claude_code`, `user:file_upload`, `user:mcp_servers`, `user:profile` | Claude-Code-scoped |
| `subscriptionType` | `max` | plan tier |
| `rateLimitTier` | `default_claude_max_20x` | shared rolling limit pool |

### 3. Not empirically measured here (limitation — needs a follow-up)
This session had **no `CLAUDE_CODE_OAUTH_TOKEN`** set, so the *setup-token* TTL was
not directly observed. `claude setup-token` requires an interactive browser consent
and cannot be completed headless, so it could not be generated in-container. Its
lifetime is documented/observed externally as **long-lived (~1 year order)**, but
Anthropic publishes no guaranteed TTL — **treat as revocable at any time.** A quick
human follow-up (generate one, inspect its `exp`) is recommended to pin the number.

---

## The two credential models

### Model A — mounted `.credentials.json` (refresh-token) — what this container uses
- Access token short (~8h); CLI **auto-refreshes** using the refresh token and
  **writes the rotated token back** to disk.
- **Failure modes:**
  - Read-only / ephemeral mount → refresh succeeds once but the rotated token is
    lost on restart → auth dies within ~8h–9d.
  - **Concurrency race:** refresh tokens are single-use/rotating. N replicas sharing
    one file → the first to refresh invalidates the token for all others →
    cascading 401s. **Does not fan out.**
  - Hard ceiling: ~9-day refresh sliding window. Break the chain or idle past it →
    full **interactive** re-login required (impossible headless).
- **Verdict:** OK for a *single* long-lived stateful pet pod with a writable PVC.
  NO-GO for a parallel fleet.

### Model B — `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` — recommended
- One-time interactive setup emits a **long-lived static bearer**; inject as env.
- **No in-container refresh cycle** → simplest ops, no disk write-back, no PVC.
- **Concurrency-safe for auth:** static bearer, no rotation race — many replicas
  can use the same token. The scaling ceiling is **rate limits, not auth**.
- Revocable from the Claude console (and by password change / sub cancellation).
  **No self-serve rotation API** — rotation = re-run `setup-token` interactively.
- **Verdict:** the credential model for the BYO-subscription design.

---

## Rate limits & concurrency
- Pro/Max limits are **per-account**, 5-hour rolling windows + weekly caps
  (here `default_claude_max_20x`). Every headless agent on one subscription draws
  from the **same** pool → concurrency is **throttle-bound, not seat-licensed**.
- Fan-out on one sub must add **backoff + a queue**; unbounded parallelism will hit
  429s and starve interactive use of the same account.

## Feature parity: headless vs interactive
| Capability | Headless `-p` |
|---|---|
| Agentic tool loop, MCP servers | ✅ verified |
| `--output-format json` / `stream-json` | ✅ |
| `--permission-mode`, pre-approved settings | ✅ (required — no human to approve) |
| Interactive TUI / slash UI | ❌ |
| Browser OAuth login & refresh-expiry recovery | ❌ (must be done out-of-band) |

Headless **requires** `--permission-mode`, an allow-list, or
`--dangerously-skip-permissions` (scope this carefully — it disables all guards).

---

## GO / NO-GO
> **⚠️ SUPERSEDED 2026-08-12 (see top banner).** The Model-B "static bearer per seat" pick and the
> "never share `.credentials.json`" rule below were overridden by the CEO field finding + the
> controller model in **arch §11.1 / ADR-032 / Epic 7 Story 7.7**. The adopted design *does* share one
> Secret across pods, made safe by a single-writer refresh controller (not by per-seat static tokens).
> Read the items below as the *original* analysis, not current guidance.

**GO** for BYO-subscription headless Claude Code using **Model B
(`CLAUDE_CODE_OAUTH_TOKEN` from `setup-token`)**. Model A is a single-pod fallback
only. Ship dependent Epics 3/4/5/7 against Model B.

## Token-rotation requirements (the deliverable)
1. **One `CLAUDE_CODE_OAUTH_TOKEN` per subscription/seat**, injected as a K8s
   Secret / vault ref — never baked into an image, never in git.
2. **Never share a mounted `.credentials.json` across replicas.** If refresh-token
   creds are unavoidable, pin to a **single** stateful replica with a **writable PVC**
   at `~/.claude/`.
3. **Treat the token as revocable-at-any-time.** Ship a `claude -p` **canary health
   probe**; on 401/auth-failure, page for re-issue. No silent death.
4. **Proactive rotation:** rotation is manual/interactive (re-run `setup-token`) and
   there is **no rotation API**. Record issue-date, alert at ~75% of assumed
   lifetime, keep a runbook. Pin the real TTL via the follow-up measurement.
5. **Budget against the shared account limits:** backoff + queue; don't fan out
   unboundedly on one sub.
6. **Secrets hygiene:** the token grants full inference on the user's paid account —
   encrypt at rest, short-lived secret mounts, least-privilege, audit access.

## Follow-ups (delegated / open)
- **ToS/AUP legal check** — is a single company sub powering a multi-agent product
  compliant, or must it be strictly BYO-per-human-seat? → child issue, needs a
  named legal/CEO owner. Blocks *productizing*, not the architecture answer.
- **Empirical setup-token TTL** — generate one on a real Max sub, inspect `exp`,
  confirm behavior on revocation & password change. Human, ~15 min.

## KSquad relevance
Confirms the credential-auth-state design (`docs/bmad/ux/…/05-credential-auth-state`)
and the build-browser BYO model: Model B + a canary probe + a rotation runbook is
the pattern the auth/credential stories should implement.
