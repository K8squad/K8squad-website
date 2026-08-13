---
title: Runs (Run)
description: A Run is a unit of squad work — a reconciled, crash-safe Kubernetes workload that claims a durable work item, gets an isolated sandbox, and drives an agent to completion.
sidebar_position: 6
---

# Runs

**CRD:** `Run` (`ksquad.io/v1alpha1`)

A **Run** is a unit of squad work. It's the heart of KSquad's "reconcile, don't glue" bet: instead of
heartbeat scripts nudging agents along, a Run is a **reconciled Kubernetes workload with an explicit,
crash-safe state machine**. A controller restart never double-drives a Run, and no coordination state
is ever trapped inside a dead pod.

```yaml
apiVersion: ksquad.io/v1alpha1
kind: Run
metadata:
  name: fix-flaky-tests
  namespace: ksquad-system
spec:
  teamRef: payments-squad
  projectRef: payments-api
  agents: [dev-1]
  workItemRef: wi-8123            # opaque pointer to a durable work item (optional)
  inputs:
    task: "Stabilize the flaky payment-retry test."
  sandboxPolicy:
    runtimeClass: gvisor
  retryPolicy:
    maxRetries: 2
```

## The lifecycle

A Run moves through an explicit set of phases (its `status.phase`):

```
 Pending ─► Claiming ─► Running ─┬─► Succeeded
    ▲          │           │     ├─► Failed ──(retryPolicy, backoff)──► Claiming
    │          │           │     └─► Cancelled (operator kill)
    │          │           ▼
    │          │        Paused ──(credential refreshed)──► Running
    │          │        Paused(rate_limited) ──(window clears)──► Claiming
    └──────────┴── retry / backoff on sandbox or agent failure ──┘
```

- **Pending** — the Run is admitted and waiting to be scheduled.
- **Claiming** — the Run reconciler requests a **warm sandbox** and **assembles the pod**: it stages
  the toolchain packs and capability-gated sidecars declared by the Run's skills. What gates latency
  here is claim time, not cold boot, because sandboxes are pre-warmed.
- **Running** — the agent is invoked over the shim (A2A); it works the item through the coordination
  record and memory, and progress **streams live over SSE** to the console.
- **Succeeded / Failed / Cancelled** — terminal outcomes. A failure retries with backoff per
  `retryPolicy`; a cancel tears down the sandbox promptly (the pod is disposable).
- **Paused** — a legible pause (never an opaque failure), used for credential expiry and rate limits
  (below).

## Crash-safe by construction

If a sandbox or agent dies mid-Run, KSquad **doesn't lose coordination state** — it lives in Postgres,
not the pod. The reconciler runs a **fence-then-release** reclaim protocol (fence the dead pod first,
release the claim second), then retries with backoff. This is the core difference from heartbeat
orchestration: at-most-one-holder is enforced with fencing tokens, so a controller restart can never
cause two agents to drive the same work.

## Work items and claims

A Run **references** a durable **work item** (`workItemRef`) — it doesn't own or embed it. Work items,
claims, comments, and artifacts are rows in Postgres, behind the apiserver's coordination API. At most
one agent claims a work item at a time, holds a **lease** on it, and the claim is **fenced** so a
crashed holder's stale writes are rejected. This is what "coordinate through durable work items, never
peer-to-peer chat" means in practice.

See [Author Guide → Managing work items](../author-guide/work-items).

## Sandboxes

Every Run executes in an **isolated sandbox** — a pod under a RuntimeClass (gVisor by default), in the
squad's namespace, under its NetworkPolicy. Sandboxes come from a **warm pool** so claim latency stays
low, and they're **torn down and replaced** after use rather than reset in place, so no state leaks
between Runs.

## Rate-limit recovery

When the model provider throttles an agent, KSquad recovers automatically, in priority order:

1. **Fallback model (no pause).** If the agent or project declares a `fallbackModel`, the Run switches
   models mid-flight and keeps running.
2. **Timed pause + auto-resume.** Otherwise the Run enters `Paused(rate_limited)` with a persisted
   `resume_at` (using the provider's `Retry-After` when given), and a single **durable timer** wakes it
   — no polling, no wasted API calls. If no `Retry-After` is given, KSquad uses exponential backoff
   with jitter, per credential.
3. **Re-route (persistent limit).** Rather than idle indefinitely, KSquad may release the fenced claim
   and re-dispatch the work item to another eligible agent whose credential isn't throttled — a
   **control-plane re-dispatch**, never agent-to-agent handoff.

Attribution is **per credential**, so one subscription's limit never silently blocks or charges
another.

## Human attribution

When a person triggers a Run from the console, KSquad stamps the triggering user onto the Run and into
the coordination record and telemetry — so consumption is attributable to the human who initiated it.
The Run does **not** inherit the user's session; the sandbox uses only the agent's own credential.

## Related

- [Agents](./agents) — who executes a Run.
- [Author Guide → Managing work items](../author-guide/work-items) — the coordination record.
- [Observability](../observability) — Run traces, metrics, and consumption metering.
- [Troubleshooting](../troubleshooting) — stuck or paused Runs.
