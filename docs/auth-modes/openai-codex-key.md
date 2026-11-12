---
title: OpenAI key for Codex
description: Authenticate a KSquad agent on the Codex runtime (OpenAI's official Rust coding agent) with a BYO OpenAI API key — OPENAI_API_KEY, service-account class. Where to get the key, why ChatGPT-subscription auth is not available yet, and how to pass test-connection.
sidebar_position: 4
---

# OpenAI key for Codex

Use this mode to run an agent on the **Codex** runtime — **OpenAI's official Rust coding agent**
(`AgentRuntime{type: codex}`). Codex is a **conformant, first-class runtime**, documented here the
same way as `claude-code` and `opencode`; it speaks the OpenAI wire natively, so it authenticates with
a **bring-your-own OpenAI API key**.

- **`credentialClass`:** `service-account`
- **Secret key:** `token` (as in [`examples/codex/`](https://github.com/K8squad/K8squad/tree/main/examples/codex)) — or `apiKey`, the default; the key name is selected by `credentialSecretRef.key`
- **Injected env var:** `OPENAI_API_KEY`
- **Lifecycle:** static — rotate only when you regenerate the key

> **ChatGPT-subscription (human-seat) auth is not available in v1.** There is no OAuth seat path for
> Codex yet — a `human-seat` class on a `codex` Agent **fails closed** (the pair is deliberately
> unmapped, so no Run authenticates under an env the CLI ignores). It is a ToS-gated roadmap item; use
> `service-account` today.

## What you need

- An **OpenAI Platform** account with billing enabled: <https://platform.openai.com>.
- An **API key** created under **API keys** (starts with `sk-...`).
- Squad **network egress to `api.openai.com`** (see below).

> Keep the key scoped and treat it as a secret. Anyone holding it can spend against your account.

## Get the key

1. Sign in to the [OpenAI Platform](https://platform.openai.com).
2. Open **API keys → Create new secret key**.
3. Copy the key value (`sk-...`) — it is shown **once**.

## Wire it to an agent

Paste the key into the credential sheet's **API key** field, or create the Secret directly:

```bash
kubectl create secret generic openai-credentials \
  --namespace ksquad-system \
  --from-literal=token='sk-...'
```

Point a `codex` runtime and an Agent at it:

```yaml
apiVersion: ksquad.io/v1alpha1
kind: AgentRuntime
metadata: { name: codex, namespace: ksquad-system }
spec:
  type: codex                        # conformant — no experimental flag
  cliVersion: rust-v0.152.0
---
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata: { name: cody, namespace: ksquad-system }
spec:
  runtimeRef: codex
  model: gpt-5.4-codex               # the codex default model
  credentialClass: service-account   # injected as OPENAI_API_KEY
  credentialSecretRef:
    name: openai-credentials
    key: token                       # or `apiKey` — selected here
```

The credential-injection contract maps the referenced Secret value onto the runtime-native env var
**`OPENAI_API_KEY`** *by reference* — the control plane never reads, logs, or stores the bytes.

A minimal, applyable one-agent example (namespace, credential, runtime, prompt, role, agent) lives at
[`examples/codex/`](https://github.com/K8squad/K8squad/tree/main/examples/codex).

## Network egress

Codex Run pods need egress to **`api.openai.com`** — allow it in the squad `NetworkPolicy`. To point
Codex at a **BYO OpenAI-compatible endpoint** instead, add a `modelEndpointRef` (which carries its own
base URL + token) and allow egress to that host; see [BYO endpoint](./byo-endpoint).

## Passing test-connection

Test-connection succeeds when:

- [ ] The Secret holds a valid `sk-...` key under the key named by `credentialSecretRef.key` (`token` in the example, or `apiKey`).
- [ ] The auth mode is **`service-account`**, not `human-seat` (which fails closed for Codex in v1).
- [ ] The squad `NetworkPolicy` permits egress to `api.openai.com` (or your BYO endpoint host).
- [ ] The `model` name is one OpenAI serves for Codex (e.g. `gpt-5.4-codex`).

A `401`/`403` means a revoked or mistyped key; a connection error usually means egress to
`api.openai.com` is blocked or a BYO base URL is missing.

## Rotation

Rotate by updating the Secret — the Run auto-resumes when the Secret changes:

```bash
kubectl create secret generic openai-credentials -n ksquad-system \
  --from-literal=token='<new-key>' --dry-run=client -o yaml | kubectl apply -f -
```

## Related

- [OpenAI-compatible key (GLM & others)](./openai-compatible-key) — for the `opencode` runtime against GLM and other OpenAI-compatible providers
- [BYO endpoint](./byo-endpoint) — point Codex at your own OpenAI-compatible host via `modelEndpointRef`
- [Credentials](../operator-guide/credentials) — the full credential lifecycle and rotation
