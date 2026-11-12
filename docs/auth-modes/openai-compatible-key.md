---
title: OpenAI-compatible key (GLM & others)
description: Authenticate a KSquad agent with an OpenAI-compatible provider key such as GLM (Zhipu) — OPENAI_API_KEY. Where to get the key, when you also need a base URL, and how to pass test-connection.
sidebar_position: 3
---

# OpenAI-compatible key (GLM & others)

Use this mode for providers that speak the **OpenAI-compatible** wire protocol — for example **GLM
(Zhipu AI)** — with a long-lived provider key. The key rides the OpenAI-standard environment variable.

- **`credentialClass`:** `service-account`
- **Secret key:** `apiKey`
- **Injected env var:** `OPENAI_API_KEY`
- **Lifecycle:** static — rotate only when you regenerate the key

## What you need

- An account with an **OpenAI-compatible** provider. Common examples:
  - **GLM (Zhipu AI)** — <https://open.bigmodel.cn> (or the international BigModel console)
  - Any provider that exposes an OpenAI-compatible `/v1/chat/completions` API
- A **provider API key** from that account.
- The provider's **base URL** *if* it is not the default OpenAI host (most non-OpenAI providers, GLM
  included, require one — see below).

## Get the key

1. Sign in to your provider's console (e.g. GLM / BigModel).
2. Create an **API key** in the API-keys / credentials section.
3. Copy the key value.

## Wire it to an agent

Paste the key into the credential sheet's **API key** field, or create the Secret:

```bash
kubectl create secret generic my-glm-key \
  --namespace ksquad-system \
  --from-literal=apiKey='<provider-api-key>'
```

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata: { name: writer-1, namespace: ksquad-system }
spec:
  runtimeRef: opencode
  model: glm-4.6
  credentialClass: service-account   # default; injected as OPENAI_API_KEY
  credentialSecretRef: my-glm-key
```

## Do I also need a base URL?

The key alone points at the **default OpenAI host**. GLM and most other OpenAI-compatible providers run
on their **own** host, so you must also tell KSquad the endpoint. That's the **BYO endpoint** path: add
a `modelEndpointRef` alongside the key so KSquad injects `OPENAI_BASE_URL`.

```bash
kubectl create secret generic my-glm-endpoint \
  --namespace ksquad-system \
  --from-literal=endpoint='https://open.bigmodel.cn/api/paas/v4' \
  --from-literal=token='<provider-api-key>'
```

```yaml
spec:
  runtimeRef: opencode
  model: glm-4.6
  modelEndpointRef: my-glm-endpoint   # injects OPENAI_BASE_URL (+ OPENAI_API_KEY)
```

See [BYO endpoint](./byo-endpoint) for the full endpoint mechanics. Rule of thumb: **default OpenAI →
key only; any other host (GLM included) → key + base URL.**

## Passing test-connection

Test-connection succeeds when:

- [ ] The Secret holds a valid provider key under key `apiKey` (or `token` when using an endpoint Secret).
- [ ] For non-OpenAI providers, a **base URL** is supplied via `modelEndpointRef` (`OPENAI_BASE_URL`).
- [ ] The `model` name is one the provider actually serves (e.g. `glm-4.6`).

A connection error usually means a **missing or wrong base URL**; a `401` means a bad key; a
model-not-found error means the `model` string doesn't match the provider's catalog.

## Related

- [BYO endpoint](./byo-endpoint) — the `modelEndpointRef` / `OPENAI_BASE_URL` mechanics in full
- [Anthropic API key](./anthropic-api-key) — for Anthropic's own API instead of an OpenAI-compatible provider
