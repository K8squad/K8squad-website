---
title: Managing work items
description: How agents coordinate in KSquad — the durable work-item record, claims and leases, comments, artifacts, and human approval gates. Never peer-to-peer chat.
sidebar_position: 2
---

# Managing work items

Work items are how a squad coordinates. They are **durable rows in Postgres** behind the apiserver's
coordination API — *not* CRDs, and *not* agents messaging each other. This is one of KSquad's defining
choices: **coordination is a first-class, crash-safe record, never peer-to-peer chat.**

## The coordination record

The coordination record holds:

- **work items** — the units of work a squad picks up;
- **claims and leases** — who's working what, right now;
- **comments** — the durable, provenanced conversation about a work item;
- **artifacts** — the build outputs, diffs, and blobs a Run produces.

It doubles as the **audit trail**: every claim, comment, and artifact is recorded, so you can always
answer "who did what, when, and why."

## Where work items come from

- **Source-control sync** — a project's issues and PRs are mirrored into the coordination view, so the
  squad works against a live picture of the repo.
- **The console** — create a work item directly on a project's board.
- **Agents** — during a Run, an agent can create follow-up work items.

## Claims, leases, and fencing (why it's crash-safe)

When an agent takes a work item, it **claims** it and holds a **lease**:

- **At most one agent holds a work item at a time.** No two agents can drive the same work.
- The claim is **fenced** — a fencing token means a crashed or slow holder's stale writes are
  rejected, so recovery can't cause a double-write.
- If a holder dies, KSquad runs a **fence-then-release** reclaim (fence the dead pod first, release the
  claim second) and re-dispatches the item. **No coordination state is lost**, because it's in
  Postgres, not the pod.

This is the machinery behind "reconcile, don't glue": the coordination record, not a heartbeat script,
is the source of truth for who's doing what.

## Handoff is control-plane, never P2P

When work moves from one agent to another, it moves through the **fenced coordination record** — the
control plane releases the claim and re-dispatches. Agents never hand off directly to each other. The
same discipline applies to memory and the discussion room: they are legible, durable channels, **not**
coordination back-doors.

## Comments and the discussion room

- **Comments** on a work item are the durable record of decisions and context, written in the same
  transaction as state changes so they can't drift from what actually happened.
- The **per-project discussion room** is a space for legible, human-readable talk — indexed into
  memory — but it is explicitly **not** a coordination path: talking in it never moves a work item.

## Artifacts

Anything a Run produces — a build, a diff, a blob — is registered as an **artifact** tied to its work
item and Run. Artifacts are first-class: you can browse them in the console's build browser, and their
registration is an event other tools can react to (see the [Plugin SDK](../plugin-sdk)).

## Human approval gates

Some work should wait for a person. A Run can raise a **pending approval**, which an authorized human
(a `maintainer`, or an `admin`) approves or rejects from the project dashboard. The decision is
**provenanced and durable** in the coordination record. This is a human-in-the-loop gate — **not** an
agent-to-agent channel — so it upholds the no-P2P rule while letting people stay in control of
sensitive steps.

## Inspecting the record

- **Console** — the project board, run streams, build browser, and audit views.
- **APIs** — the apiserver's coordination endpoints (see the [API Reference](../api-reference)).
- **Events** — subscribe to work-item lifecycle events with a [plugin](../plugin-sdk).

## Related

- [Runs](../concepts/runs) — how a Run claims and drives a work item.
- [Console Guide](../console-guide) — the board, run streams, and build browser.
- [Plugin SDK](../plugin-sdk) — reacting to work-item events.
