---
title: Auth modes
description: Pick the right authentication mode for an agent — Claude subscription seat, Anthropic API key, OpenAI-compatible key, your own model endpoint, or a GitHub repo connection — and see exactly what each one needs to pass test-connection.
sidebar_position: 4
---

# Auth modes

When you add a credential in the console, the **Docs↗** link next to each auth mode brings you here.
Each page below tells you **exactly what that mode needs** — which token to generate, what to paste,
and which environment variable KSquad injects — so your first **test-connection** passes on the first
try.

KSquad is **vendor-neutral by construction**: every agent authenticates with **its own per-user
Kubernetes Secret**, and the control plane holds no shared master credential. The auth mode you pick
maps to a `credentialClass` and (for models) an injected environment variable; nothing is hardcoded
outside the reviewed injector table.

## Which mode do I need?

| I want to… | Auth mode | Page |
|------------|-----------|------|
| Use my **Claude subscription** (Pro/Max/Team seat) — no per-token billing | Claude subscription / OAuth seat | [Claude subscription](./claude-subscription) |
| Use a raw **Anthropic API key** (pay-as-you-go, no OAuth) | Anthropic API key | [Anthropic API key](./anthropic-api-key) |
| Use **GLM (Zhipu)** or another **OpenAI-compatible** provider key | OpenAI-compatible key | [OpenAI-compatible key](./openai-compatible-key) |
| Run **Codex** (OpenAI's Rust coding agent) with an **OpenAI API key** | OpenAI key for Codex | [OpenAI key for Codex](./openai-codex-key) |
| Point at **my own** Ollama / self-hosted / OpenAI-compatible **endpoint** | BYO endpoint | [BYO endpoint](./byo-endpoint) |
| Give an agent a **GitHub repo** to work on | GitHub connect | [GitHub connect](./github-connect) |

## The env-var contract at a glance

Every model auth mode resolves to one injected environment variable. The console shows this mapping in
the required-settings panel; it is read from the injector's reviewed table, not guessed.

| Auth mode | `credentialClass` | Secret key | Injected env var |
|-----------|-------------------|------------|------------------|
| Claude subscription (OAuth seat) | `human-seat` | `token` | `CLAUDE_CODE_OAUTH_TOKEN` |
| Anthropic API key | `service-account` | `apiKey` | `ANTHROPIC_API_KEY` |
| OpenAI-compatible key (GLM, etc.) | `service-account` | `apiKey` | `OPENAI_API_KEY` |
| OpenAI key for Codex | `service-account` | `token` (or `apiKey`) | `OPENAI_API_KEY` |
| BYO endpoint | `service-account` (+ `modelEndpointRef`) | `endpoint` (+ optional `token`) | `OPENAI_BASE_URL` (+ `OPENAI_API_KEY`) |

GitHub connect is a **project** credential (repo access), not a model credential, so it does not appear
in the model env-var table — see [GitHub connect](./github-connect).

> **Secrets are never echoed.** Whatever mode you pick, the token bytes live only in your per-user
> Kubernetes Secret. KSquad injects them by reference — the control plane never reads, logs, or stores
> the value, and the console never renders it back to you.

See also: [Operator Guide → Credentials](../operator-guide/credentials) for lifecycle, rotation, and
the graceful-pause-on-auth-failure path.
