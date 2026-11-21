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
| `ksquad.run.*.*.ended` | every Run that reached a terminal state, in any project/squad |
| `ksquad.run.payments.*.>` | every Run event in project `payments`, any squad |
| `ksquad.*.payments.>` | everything happening in project `payments` |
| `ksquad.work_item.*.*.claimed` | every work-item claim, anywhere |
| `ksquad.>` | everything (use sparingly) |

Subjects are part of the versioned event catalog — the token positions are stable. An empty squad
component is published as the literal token `_` (e.g. `ksquad.run.payments._.ended`), which the `*`
wildcard matches.

The **entity token** is one of the catalog entities: `run`, `work_item`, `artifact`, `memory`,
`scm`, `mesh` (enforced by the outbox's database constraint — a typo'd entity is rejected at
capture time, never published to a garbage subject).

## The event taxonomy

Every event maps 1:1 onto a real state change (the same transaction that changed state captured the
event). The categories:

### Run lifecycle
Entity `run`. Emitted on each reconcile-step transition of a [Run](/docs/concepts/runs/) (the Run's
`status.phase` — Pending/Claiming/Running/Paused/… — rides in the event payload; the live SSE stream
carries the full phase detail):

| `event_type` | Meaning |
|--------------|---------|
| `scheduled` | Run admitted; sandbox claim requested |
| `sandbox_bound` | Run bound to a sandbox pod |
| `started` | Agent is executing in the sandbox |
| `ended` | Terminal state reached (payload `state`: `completed` \| `failed` \| `canceled`) |
| `thinking` | Progress-mirror event: agent progress within a Run (live activity feed) |
| `ticket_comment` | A comment was posted on the Run's work item (live-echo) |
| `discussion_message` | A discussion-room message was written for the Run |

### Work-item transitions
Entity `work_item`. The coordination record's lifecycle:

| `event_type` | Meaning |
|--------------|---------|
| `assigned` | The item's Run was scheduled to an agent/team |
| `claimed` | An agent took the item (at-most-one-holder, fenced lease) |
| `reroute_released` | A throttled holder released the claim for control-plane re-dispatch |

### Build outputs / artifacts
Entity `artifact` — **catalog-admitted; emitters land incrementally.** A produced build, diff, or
blob is registered against its work item and Run (`work_item_id`, `run_id`, `kind`).

### Memory writes
Entity `memory` — **catalog-admitted; emitters land incrementally.** Provenanced writes to the
knowledge record (memory and discussion).

### Source-control mirror results
Entity `scm` — **catalog-admitted; emitters land incrementally.** Source-control mirror updates
(issues, PRs, check runs) as the scm-webhook/reposync pipeline lands them.

### Agent mesh
Entity `mesh` — **planned, not yet on the bus.** Standing role-provisioned agent-process lifecycle
(`mesh.register` / `mesh.deregister` / `mesh.hibernate` / `mesh.wake` / `mesh.stop`) will publish
here once the mesh gateway emits them; the entity is already admitted by the catalog.

### Credential-refresh needs
There is **no `credential` entity** in the event catalog. Credential expiry surfaces as a
`Run → Paused` transition in the control plane (visible via the run events above and the console's
credential state), and a plugin **never injects the credential or resumes the Run** — that stays the
fenced control-plane path. If you want to alert a human, subscribe to the run events and react to the
pause.

## Event envelope

Every event shares a common envelope (illustrative shape; pin the schema revision for exact fields):

```json
{
  "specversion": "1.0",
  "id": "evt_01H...",
  "source": "ksquad/apiserver",
  "type": "ksquad.run.ended",
  "schemaversion": "v1alpha1",
  "subject": "ksquad.run.payments.payments-squad.ended",
  "time": "2026-08-13T09:41:02Z",
  "data": {
    "runId": "green-tests-1",
    "project": "payments-api",
    "team": "payments-squad",
    "agent": "dev-1",
    "state": "completed",
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
first — see [Observability](/docs/observability/#platform-health-metrics).

## Next

- [Hello-world plugin](/docs/plugin-sdk/hello-world/) — subscribe and react to your first event.
- [Examples](/docs/plugin-sdk/examples/) — notification, mirroring, and dashboard patterns.
