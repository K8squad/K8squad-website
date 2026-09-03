---
title: Claude subscription (OAuth seat)
description: Use your Claude Pro, Max, or Team subscription seat to authenticate a KSquad agent — one-time OAuth, zero-touch ~8h token refresh, CLAUDE_CODE_OAUTH_TOKEN. What you need and how to pass test-connection.
sidebar_position: 1
---

# Claude subscription (OAuth seat)

Use this mode when you want an agent to run on your **Claude subscription** (Pro, Max, or Team) instead
of paying per token. You authenticate **once** with an OAuth flow; KSquad then keeps the seat alive for
you with zero-touch refresh.

- **`credentialClass`:** `human-seat`
- **Secret key:** `token`
- **Injected env var:** `CLAUDE_CODE_OAUTH_TOKEN`
- **Access token lifetime:** ~8 hours, **auto-refreshed** by a controller — you don't manage it

## What you need

- A **Claude subscription** (Pro, Max, or Team) with a seat available to you.
- The **Claude Code CLI** installed locally (only for the CLI path below), or access to the console's
  **Connect Claude** button.

## Get the token

You have two ways to produce the OAuth token.

### Option A — Console (recommended)

1. In the console, open the credential sheet and choose **Claude subscription**.
2. Click **Connect Claude** and complete the browser OAuth flow **once**.
3. KSquad writes the access + refresh tokens into your per-user Secret. You never handle the string.

### Option B — CLI `claude setup-token`

If you prefer the terminal, generate a long-lived setup token with the Claude Code CLI:

```bash
claude setup-token
```

This opens the OAuth flow and prints a `CLAUDE_CODE_OAUTH_TOKEN` value. Paste it into the credential
sheet's **token** field (or store it in the Secret key `token`).

```bash
kubectl create secret generic my-claude-seat \
  --namespace ksquad-system \
  --from-literal=token='<CLAUDE_CODE_OAUTH_TOKEN>'
```

## Wire it to an agent

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata: { name: dev-1, namespace: ksquad-system }
spec:
  runtimeRef: claude-code
  credentialClass: human-seat        # <-- required for the OAuth-seat path
  credentialSecretRef: my-claude-seat
```

> **`credentialClass: human-seat` is required.** If you leave it off, KSquad assumes a
> service-account (raw API key) and looks for `ANTHROPIC_API_KEY` instead — test-connection will fail
> because the OAuth token is not an API key. A human OAuth seat must say so explicitly.

## Zero-touch refresh

The ~8-hour access token is refreshed for you by a **leader-elected credential controller** — *not* by
each agent pod. It writes the new token back to the **same** Secret before the old one expires, so
concurrent Runs on one subscription just work. Agents never refresh tokens themselves.

If the subscription goes unused long enough that the **refresh token** itself expires (~9 days idle),
the console surfaces **"credential expired — click to re-login"**: a single OAuth click, not a
recurring chore.

## Passing test-connection

Test-connection succeeds when:

- [ ] The auth mode is set to **Claude subscription** / `credentialClass: human-seat`.
- [ ] The Secret holds a valid OAuth token under key `token` (from **Connect Claude** or
      `claude setup-token`).
- [ ] The token has not passed its ~9-day refresh window.

If it fails, re-run **Connect Claude** (or `claude setup-token`) to mint a fresh token — the token, not
the config, is almost always the issue.

## Related

- [Anthropic API key](./anthropic-api-key) — pay-as-you-go alternative, no subscription seat
- [Operator Guide → Credentials](../operator-guide/credentials) — lifecycle and rotation in depth
