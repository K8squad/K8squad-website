---
title: Plugin SDK
description: Extend KSquad with out-of-process plugins that observe the event stream. Overview of the plugin model, the event seam, and the guarantees that keep plugins safe.
sidebar_position: 9
---

# Plugin SDK

Plugins let you extend KSquad by **reacting to what happens** in the platform — a Run completes, a work
item is claimed, an artifact is produced, a credential needs a refresh. A plugin might post to Slack,
mirror work to an external tracker, drive a custom dashboard, or notify an on-call rotation.

This guide covers the plugin model and its guarantees, then walks you through building one.

## In this guide

| Page | What it covers |
|------|----------------|
| [Event reference](./event-reference) | The event catalog, subject taxonomy, and event schemas |
| [Hello-world plugin](./hello-world) | Build and run your first plugin end to end |
| [Examples](./examples) | Common plugin patterns — notifications, mirroring, dashboards |

## The plugin model in one picture

```
   State change (Run, work item, memory, sync, credential)
        │  committed atomically with…
        ▼
   Postgres outbox  ──relay──▶  NATS JetStream subjects  ──▶  your plugin (subscribes, read-only)
   (durable capture)            (event flow, replayable)         │
                                                                 └─▶ acts on the world via public APIs
```

- **Postgres stores, NATS flows, plugins observe.** Domain events are captured in a transactional
  Postgres outbox (durability) and a relay publishes them to NATS JetStream subjects (transport). Your
  plugin subscribes to NATS.
- **Plugins are out-of-process** — a sidecar or a standalone service — registered per project/squad.
- **You don't build an outbox consumer.** You subscribe to a NATS subject. JetStream retains events, so
  a plugin can **replay and catch up** on anything it missed.

## The guarantees (read these before you build)

These properties are the whole point of the design — they're what make plugins safe to run against a
control plane that's driving real work.

1. **A plugin can never block the platform.** The relay runs *outside* the reconcile/coordination
   transaction. A slow, failing, or absent plugin — or an unavailable NATS — **can never block a Run, a
   claim, or a memory write.** NATS being down only delays fan-out; it never stalls the write path.

2. **Delivery is at-least-once.** Because events are captured in the same transaction as the state
   change, an event exists **if and only if** its state change committed — no lost events, no phantom
   events. On restart or a failed publish, the relay republishes unflushed events. Design your plugin to
   be **idempotent** (handle the same event twice safely).

3. **Plugins are observers, not a coordination path.** The plugin contract is **read-only event
   consumption.** There is no plugin affordance to claim, lease, fence, hand off, or otherwise mutate
   coordination or knowledge state. Nothing a plugin publishes on NATS re-enters the coordination
   record — the relay is strictly one-way (outbox → NATS). A plugin **cannot move a work item.**

4. **Plugins are untrusted and least-privilege.** They run outside the trust boundary. If a plugin
   needs to *act on the world* (e.g. write to an external tracker), it does so as an ordinary,
   **authored and audited API client** — using a **BYO per-user Secret**, never a shared master
   credential — through the same public APIs as any principal. Read-in via events; write-out via public
   APIs; **no coordination primitive** either way.

5. **The event catalog is versioned.** Each event type has a versioned schema. Consumers **pin an
   event-schema revision**; producer changes are additive-or-gated, never ambient breakage — so a
   third-party plugin survives platform evolution.

## When to use a plugin (and when not to)

**Use a plugin to:**
- send notifications (Slack, email, PagerDuty) on Run or work-item events;
- mirror KSquad activity into an external system of record;
- feed a custom dashboard or data warehouse;
- trigger external CI/CD or webhooks off build artifacts.

**Don't reach for a plugin to:**
- move work between agents — that's the fenced [coordination record](../author-guide/work-items),
  never a plugin;
- inject a credential or resume a Run — a plugin can *signal* "this agent needs a refresh," but the
  refresh stays the control-plane path;
- change platform state — plugins observe; they don't mutate.

## Registering a plugin

Plugins are registered and configured **per project/squad** from the console
[Settings](../operator-guide/settings#plugins). You provide the plugin's connection details and its
outbound credentials (as BYO Secret refs). From there, subscribe to the subjects you care about — see
the [Event reference](./event-reference) — and start with the [Hello-world tutorial](./hello-world).

> **Stability.** The plugin SDK and event catalog ship under `v1alpha1`. Pin an event-schema revision
> and expect additive, non-breaking evolution.
