---
title: Troubleshooting
description: Diagnose common KSquad issues — installs that fail fast, rejected CRDs, stuck or paused Runs, credential and rate-limit states, exposure and storage problems.
sidebar_position: 8
---

# Troubleshooting

KSquad is designed to **fail fast and legibly** — most problems surface as a clear condition on an
object or a clear install error, not a silent hang. This page maps common symptoms to causes and fixes.

## First moves

```bash
# Control-plane health
kubectl -n ksquad-system get pods
kubectl -n ksquad-system rollout status deploy/ksquad-apiserver

# The object that's misbehaving — read its conditions
kubectl -n ksquad-system describe run <name>
kubectl -n ksquad-system describe agent <name>

# Operator logs
kubectl -n ksquad-system logs deploy/ksquad-operator
```

Almost every KSquad object reports `status.conditions` — **read them first**; they usually name the
problem directly.

## Install issues

### `helm install` fails immediately on exposure
**Cause:** you selected `exposure.mode=gateway` but no matching `GatewayClass` exists. KSquad
pre-flights this and fails fast rather than leaving a dangling route.
**Fix:** install a Gateway controller and set `exposure.gateway.gatewayClassName` to its class, or fall
back to `exposure.mode=ingress` / `clusterip`. See [Install → networking](./operator-guide/install#networking--exposure).

### `helm install` fails on storage
**Cause:** no `storageClassName` was provided. KSquad never uses the cluster-default StorageClass.
**Fix:** set `global.storageClassName` (and per-component overrides if needed) to a class that exists.

### Can't find the admin password
**Fix:** it's in the bootstrap Secret printed in the install notes:
```bash
kubectl -n ksquad-system get secret ksquad-bootstrap-admin \
  -o jsonpath='{.data.password}' | base64 -d; echo
```
If `auth.users` already has rows, the seed is a no-op and this Secret is not a live credential — use an
existing admin, or reset via your auth configuration.

## CRD rejected on apply

KSquad validates and **fails closed**. Common rejections:

| Message points to… | Cause | Fix |
|--------------------|-------|-----|
| unresolved credential | `Agent.credentialSecretRef` points at a missing/invalid Secret | Create/connect the credential first ([Credentials](./operator-guide/credentials)) |
| toolchain version conflict | two skills pin conflicting versions (e.g. `go@1.22` vs `go@1.23`) | Align the skills' `requires.toolchains` |
| capability not available | e.g. `docker: true` on a gVisor-only runtime with no supported mechanism | Use a supported build mechanism, or a Kata RuntimeClass ([Configuration](./operator-guide/configuration)) |
| immutable annotation | trying to change `ksquad.io/created-by` | It's set once at creation and can't be changed |

## Stuck or paused Runs

### Run sits in `Pending`
**Likely:** no eligible agent, or the `Team`/`Project` reference doesn't resolve.
**Check:** `kubectl describe run <name>` conditions; confirm the referenced team, project, and agents
exist and are admitted.

### Run sits in `Claiming`
**Likely:** no warm sandbox is available (pool exhausted) or the pod can't assemble (image pull,
toolchain pack missing on nodes).
**Check:** warm-pool sizing ([Configuration → warm pool](./operator-guide/configuration#warm-pool)) and
whether required runtime/toolchain images are pre-pulled. Look at the sandbox pod events.

### Run is `Paused` (credential)
**Meaning:** the agent's credential failed — this is a *legible pause*, not a failure.
**Fix:** rotate/refresh the credential. For Claude, click **re-login** in Credentials; for a static
key, update the Secret. The Run **auto-resumes when the Secret updates**. See
[Credentials → rotation](./operator-guide/credentials#rotation-and-the-graceful-pause-path).

### Run is `Paused(rate_limited)`
**Meaning:** the model provider throttled this credential. KSquad **auto-resumes** when the window
clears (using the provider's `Retry-After`), or backs off exponentially if none was given.
**Options:** configure a `fallbackModel` on the agent to keep working through limits, or rely on
control-plane re-route to an un-throttled agent. See [Runs → rate-limit recovery](./concepts/runs#rate-limit-recovery).

### Run `Failed` and retried
Expected behavior on a sandbox/agent failure — KSquad fences the dead pod, releases the claim, and
retries with backoff per `retryPolicy`. **No coordination state is lost.** If it keeps failing, read the
Run conditions and the agent's Run logs for the underlying error.

## Console / connectivity

### Live Run stream doesn't update
**Likely:** an exposure path that buffers or times out the SSE stream. `ingress`/`clusterip` modes
don't give the same SSE-timeout guarantees as Gateway API.
**Fix:** use `exposure.mode=gateway`, or confirm your Ingress controller has the SSE-safe annotations
KSquad renders. See [Install → networking](./operator-guide/install#networking--exposure).

### A user sees too little / too much
**Cause:** their global role or per-project access level. The console is role-adaptive and RBAC-scoped
server-side.
**Fix:** review the user's membership in **Users & Roles** ([RBAC](./operator-guide/rbac)).

## Telemetry not arriving

- **Nothing exported at all?** That's the default — telemetry stays in-cluster until you create an
  `OTelConfig`. See [Observability](./observability).
- **Exporter auth failing?** Confirm the `authSecretRef` Secret exists and holds a valid token; it's
  never inline and never logged, so check the Secret, not the CRD.
- **Metrics missing dimensions?** Consumption and rate-limit metrics are labeled by
  `{team, project, run, agent, principal, model}`; confirm the Run carried an initiating principal.

## Plugins not reacting

Plugins are **read-only observers** and can never block a Run — so if a plugin is silent, the platform
is still healthy.
- Check the event-seam health metrics (outbox depth, unflushed lag, NATS publish failures, consumer
  lag) in your metrics backend.
- Confirm the plugin's NATS subscription subject matches the [subject taxonomy](./plugin-sdk/event-reference#subject-taxonomy)
  and that its pinned event-schema revision is still served.

## Getting more help

- Read the object's `status.conditions` — the answer is usually there.
- Follow a Run end to end with its OTel trace ([Observability](./observability)).
- File an issue on [GitHub](https://github.com/K8squad) with the failing object's `describe` output and
  the relevant operator logs.
