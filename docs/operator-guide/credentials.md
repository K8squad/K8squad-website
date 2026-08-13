---
title: Credentials
description: Connect and manage agent credentials in KSquad — one-time Claude OAuth with zero-touch refresh, non-Claude API keys, BYO model endpoints, and rotation.
sidebar_position: 3
---

# Credentials

KSquad is **vendor-neutral by construction**: every agent authenticates with **its own per-user
Kubernetes Secret**, and KSquad holds **no shared master credential**. Credential type and lifecycle
are treated as capability metadata, so the core hardcodes no vendor's auth flow.

Three credential shapes ship at v1.

## The three credential shapes

| Runtime family | How you connect | Lifecycle | Secret holds |
|----------------|-----------------|-----------|--------------|
| **Claude-family** | One-time OAuth — console **Connect Claude** or CLI `ksquad auth login` | **Zero-touch** — a controller auto-refreshes the ~8h access token; re-login only after the refresh window (~9 days idle) expires | OAuth access + refresh token |
| **Non-Claude runtime** (e.g. OpenClaw, Hermes) | Supply a long-lived **API key / provider token** | Static — refresh only if the provider rotates the key | API key |
| **BYO model endpoint** (Ollama / OpenAI-compatible) | Supply an **endpoint URL** (+ optional token) | Static — a local/self-hosted model, no vendor OAuth | Endpoint URL (+ token) |

## Connect Claude (zero-touch)

This is the smoothest path and the one most teams start with.

1. In the console, open **Credentials** → **Connect Claude** (or run `ksquad auth login`).
2. Complete the browser OAuth flow **once**.
3. KSquad writes the access + refresh tokens to a **per-user Secret**. You never handle token strings
   again.

Under the hood, a **leader-elected credential controller** — *not* each agent pod — watches token
expiry and refreshes the access token **before it expires**, writing the new token back to the *same*
Secret. Every agent pod that mounts that Secret benefits at once, so **concurrent Runs on one
subscription just work**. Agents never refresh tokens themselves.

If the subscription goes unused long enough that the **refresh token** itself expires (~9 days idle),
the controller marks the Secret `expired` and the console surfaces **"credential expired — click to
re-login"** — a single OAuth click, not a recurring manual task.

## Non-Claude runtimes (API key)

For runtimes that authenticate with a long-lived key, create a Secret with the provider token and
reference it from the agent:

```bash
kubectl create secret generic hermes-key \
  --namespace ksquad-system \
  --from-literal=token='<provider-api-key>'
```

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata: { name: writer-1, namespace: ksquad-system }
spec:
  runtimeRef: hermes
  roleRef: docs-writer
  credentialSecretRef: hermes-key
  model: <provider-model>
```

There's no interactive OAuth step; the key is static. Rotate it by updating the Secret (below).

## BYO model endpoint

Point an agent at **your own** Ollama or OpenAI-compatible server — no paid credits, no vendor OAuth:

```bash
kubectl create secret generic my-ollama \
  --namespace ksquad-system \
  --from-literal=endpoint='http://ollama.internal:11434' \
  --from-literal=token=''            # optional
```

```yaml
spec:
  runtimeRef: opencode
  model: llama3.3
  modelEndpointRef: my-ollama
```

## Rotation and the graceful-pause path

Whatever the credential type, KSquad never turns an auth failure into an opaque crash:

- The shim detects an auth-failure signal from the runtime and reports it.
- The Run transitions to **`Paused`** with an operator-legible condition — *not* a `Failed`.
- **Resume triggers automatically when the referenced Secret updates** — rotate the token (or complete
  a re-login) and KSquad re-drives the Run.

To rotate a static key, update the Secret:

```bash
kubectl create secret generic hermes-key -n ksquad-system \
  --from-literal=token='<new-key>' --dry-run=client -o yaml | kubectl apply -f -
```

## Rate limits are per-credential

Because each credential is a per-user Secret, provider throttling is a **per-credential** condition —
one subscription hitting its limit never blocks or mis-charges another. KSquad auto-pauses and
auto-resumes on the provider's `Retry-After`, applies exponential backoff on repeats, and can re-route
work to an agent whose credential isn't throttled. See [Runs → rate-limit recovery](../concepts/runs#rate-limit-recovery).

## Security discipline

- Tokens live **only** in the per-user Secret — never logged, echoed, or embedded in a CRD.
- The credential controller holds **no shared master credential**; each principal's Secret is its own.
- Consumption is **attributable to the owning principal by construction** (there's no shared-credential
  disambiguation problem) — see [Observability → consumption metering](../observability#consumption-metering).
