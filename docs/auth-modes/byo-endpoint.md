---
title: BYO endpoint (modelEndpointRef)
description: Point a KSquad agent at your own Ollama or OpenAI-compatible model server with modelEndpointRef — OPENAI_BASE_URL (+ optional OPENAI_API_KEY). No vendor OAuth, no paid credits. How to set it up and pass test-connection.
sidebar_position: 4
---

# BYO endpoint (modelEndpointRef)

Use this mode to run an agent against **your own** model server — a local Ollama, a self-hosted vLLM,
or any **OpenAI-compatible** endpoint — with no vendor OAuth and no paid credits. You provide an
endpoint URL and (optionally) a token.

- **Field:** `modelEndpointRef` on the Agent spec
- **Secret keys:** `endpoint` (required), `token` (optional)
- **Injected env vars:** `OPENAI_BASE_URL` (from `endpoint`) and `OPENAI_API_KEY` (from `token`, if set)
- **Lifecycle:** static — you own the server; there's no vendor OAuth to refresh

## What you need

- A reachable **OpenAI-compatible** endpoint. Examples:
  - **Ollama** — `http://ollama.internal:11434/v1`
  - **vLLM / LM Studio / llama.cpp server** — their OpenAI-compatible `/v1` URL
  - A hosted OpenAI-compatible provider's base URL
- **Network reachability** from the KSquad cluster to that endpoint (in-cluster Service DNS, a routable
  IP, or an ingress hostname — a `localhost` URL on your laptop is **not** reachable from a pod).
- A **token** only if your endpoint requires auth. Local Ollama usually needs none.

## Set it up

```bash
kubectl create secret generic my-ollama \
  --namespace ksquad-system \
  --from-literal=endpoint='http://ollama.internal:11434/v1' \
  --from-literal=token=''            # optional; leave empty for unauthenticated Ollama
```

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata: { name: local-1, namespace: ksquad-system }
spec:
  runtimeRef: opencode
  model: llama3.3
  modelEndpointRef: my-ollama        # injects OPENAI_BASE_URL (+ OPENAI_API_KEY if token set)
```

KSquad resolves `modelEndpointRef` and injects `OPENAI_BASE_URL` from the `endpoint` key. If the Secret
also carries a non-empty `token`, it is injected as `OPENAI_API_KEY`; leave `token` empty for an
unauthenticated endpoint.

## Passing test-connection

Test-connection succeeds when:

- [ ] The Secret holds a reachable `endpoint` URL, including the OpenAI-compatible path (usually `/v1`).
- [ ] The endpoint is reachable **from the cluster** (not just from your workstation).
- [ ] The `model` name is one the endpoint actually serves (e.g. a model you've `ollama pull`ed).
- [ ] A `token` is supplied **only if** the endpoint requires auth.

Common failures: a connection timeout means the endpoint isn't reachable from the pod (check Service
DNS / firewall); a `404` on the model means the `model` string doesn't match what the server serves; a
`401` means the endpoint wants a token you didn't supply.

## Related

- [OpenAI-compatible key](./openai-compatible-key) — for a hosted provider key (GLM, etc.) on a shared endpoint
- [Operator Guide → Credentials](../operator-guide/credentials) — BYO endpoints in the broader credential model
