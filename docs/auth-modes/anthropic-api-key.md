---
title: Anthropic API key
description: Authenticate a KSquad agent with a raw Anthropic API key (ANTHROPIC_API_KEY) — pay-as-you-go, no OAuth seat. Where to get the key and how to pass test-connection.
sidebar_position: 2
---

# Anthropic API key

Use this mode when you want to bill Claude usage **pay-as-you-go** against an Anthropic API key rather
than a subscription seat. There's no interactive OAuth step — the key is static.

- **`credentialClass`:** `service-account`
- **Secret key:** `apiKey`
- **Injected env var:** `ANTHROPIC_API_KEY`
- **Lifecycle:** static — rotate only when you regenerate the key

## What you need

- An **Anthropic Console** account with billing enabled: <https://console.anthropic.com>.
- An **API key** created under **Settings → API Keys** (starts with `sk-ant-`).

> Keep the key scoped and treat it as a secret. Anyone holding it can spend against your account.

## Get the key

1. Sign in to the [Anthropic Console](https://console.anthropic.com).
2. Go to **Settings → API Keys → Create Key**.
3. Copy the key value (`sk-ant-...`) — it is shown **once**.

## Wire it to an agent

Paste the key into the credential sheet's **API key** field, or create the Secret directly:

```bash
kubectl create secret generic my-anthropic-key \
  --namespace ksquad-system \
  --from-literal=apiKey='sk-ant-...'
```

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Agent
metadata: { name: dev-1, namespace: ksquad-system }
spec:
  runtimeRef: claude-code
  credentialClass: service-account   # default; the raw-API-key path
  credentialSecretRef: my-anthropic-key
```

`service-account` is the **default** class, so you can also omit `credentialClass` entirely for this
mode. KSquad injects the key as `ANTHROPIC_API_KEY`.

## Passing test-connection

Test-connection succeeds when:

- [ ] The Secret holds a valid `sk-ant-...` key under key `apiKey`.
- [ ] The key is active and the Anthropic account has billing/credit available.
- [ ] The auth mode is **Anthropic API key** (`service-account`), not the OAuth seat.

A `401`/`403` at test-connection means the key is revoked or mistyped; regenerate it in the Anthropic
Console. A quota/billing error means the account has no available credit.

## Rotation

Rotate by updating the Secret — the Run auto-resumes when the Secret changes:

```bash
kubectl create secret generic my-anthropic-key -n ksquad-system \
  --from-literal=apiKey='<new-key>' --dry-run=client -o yaml | kubectl apply -f -
```

## Related

- [Claude subscription (OAuth seat)](./claude-subscription) — use a subscription instead of per-token billing
- [OpenAI-compatible key](./openai-compatible-key) — for GLM and other non-Anthropic providers
