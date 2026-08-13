---
title: Event reference
description: KSquad's plugin event catalog — the NATS subject taxonomy, the full event taxonomy (Run lifecycle, work items, artifacts, memory, sync, credentials), and schema versioning.
sidebar_position: 1
---

# Event reference

Plugins observe KSquad by subscribing to **NATS JetStream subjects**. This page describes the subject
taxonomy, the full event catalog, and how schema versioning keeps your plugin stable.

## Subject taxonomy

Events are published on hierarchical subjects:

```
ksquad.{entity}.{project}.{squad}.{event_type}
```

The hierarchy lets you subscribe with NATS wildcards (`*` matches one token, `>` matches the rest):

| Subscription | Matches |
|--------------|---------|
| `ksquad.run.*.*.completed` | every Run that completed, in any project/squad |
| `ksquad.run.payments.*.>` | every Run event in project `payments`, any squad |
| `ksquad.*.payments.>` | everything happening in project `payments` |
| `ksquad.workitem.*.*.claimed` | every work-item claim, anywhere |
| `ksquad.>` | everything (use sparingly) |

Subjects are part of the versioned event catalog — the token positions are stable.

## The event taxonomy

Every event maps 1:1 onto a real state change (the same transaction that changed state captured the
event). The categories:

### Run lifecycle
Entity `run`. Emitted on each phase transition of a [Run](../concepts/runs):

| `event_type` | Meaning |
|--------------|---------|
| `pending` | Run admitted, awaiting scheduling |
| `claiming` | Run is acquiring a sandbox and assembling its pod |
| `running` | Agent is executing |
| `paused` | Legible pause (credential expiry) |
| `paused_rate_limited` | Provider throttled this credential |
| `succeeded` | Terminal success |
| `failed` | Terminal failure (may retry per policy) |
| `cancelled` | Operator kill |

### Work-item transitions
Entity `workitem`. The coordination record's lifecycle:

| `event_type` | Meaning |
|--------------|---------|
| `created` | A new work item exists |
| `claimed` | An agent took the item (at-most-one-holder) |
| `handoff` | Control-plane re-dispatch to another agent |
| `completed` | The item is done |

### Build outputs / artifacts
Entity `artifact`. A produced build, diff, or blob is registered against its work item and Run:

| `event_type` | Meaning |
|--------------|---------|
| `registered` | An artifact (`work_item_id`, `run_id`, `kind`) was produced |

### Memory writes
Entity `memory`. Provenanced writes to the knowledge record (memory and discussion):

| `event_type` | Meaning |
|--------------|---------|
| `written` | A memory/discussion record was written |

### Sync / CI results
Entity `sync`. Source-control mirror updates:

| `event_type` | Meaning |
|--------------|---------|
| `issue` | An issue mirror updated |
| `pr` | A pull-request mirror updated |
| `check_run` | A CI check-run result updated |
| `artifact` | A synced build artifact updated |

### Credential-refresh needs
Entity `credential`. The `Run→Paused`-on-credential-expiry transition surfaces "this agent needs a
token refresh":

| `event_type` | Meaning |
|--------------|---------|
| `refresh_needed` | An agent's credential needs attention |

> **Observe-only, even here.** A credential-manager plugin can *react* to `refresh_needed` — notify,
> open a ticket — but it **never injects the credential or resumes the Run**. That stays the fenced
> control-plane path.

## Event envelope

Every event shares a common envelope (illustrative shape; pin the schema revision for exact fields):

```json
{
  "specversion": "1.0",
  "id": "evt_01H...",
  "source": "ksquad/apiserver",
  "type": "ksquad.run.succeeded",
  "schemaversion": "v1alpha1",
  "subject": "ksquad.run.payments.payments-squad.succeeded",
  "time": "2026-08-13T09:41:02Z",
  "data": {
    "runId": "green-tests-1",
    "project": "payments-api",
    "team": "payments-squad",
    "agent": "dev-1",
    "phase": "Succeeded",
    "initiatedBy": "alice",
    "workItemRef": "wi-8123"
  }
}
```

The envelope follows CloudEvents-style conventions; `data` carries the entity-specific payload defined
by the event's schema.

## Schema versioning & the pinned-adapter discipline

The event catalog is governed like KSquad's other seams:

- **Each event type has a versioned schema** (`schemaversion`).
- **Consumers pin a revision.** Your plugin declares the event-schema revision it understands.
- **Producer changes are additive-or-gated**, never ambient breakage — a new optional field won't break
  a pinned consumer; a breaking change is gated behind a new revision.

This is how a third-party plugin survives platform upgrades: pin what you read, and evolve deliberately.

## At-least-once & idempotency

Delivery is **at-least-once** — on a relay restart or a failed publish, unflushed events are
republished. **Make your handler idempotent**: dedupe on the event `id`, or make the side effect safe
to repeat (upserts, not blind inserts; "ensure notified," not "notify again").

## Replay & catch-up

JetStream **retains** events, so a plugin that was down can replay from where it left off using a
durable consumer. This is how a plugin catches up after a deploy or an outage without missing events.

## Observing the seam itself

The event pipeline is observable: **outbox depth, unflushed-event lag, NATS publish failures, and
JetStream consumer lag** are OTel metrics. If your plugin seems to be missing events, check these
first — see [Observability](../observability#platform-health-metrics).

## Next

- [Hello-world plugin](./hello-world) — subscribe and react to your first event.
- [Examples](./examples) — notification, mirroring, and dashboard patterns.
