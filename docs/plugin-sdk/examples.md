---
title: Examples
description: Common KSquad plugin patterns — Slack/notification on Run outcomes, mirroring work items to an external tracker, feeding a dashboard, and watching credential state via the public APIs.
sidebar_position: 3
---

# Plugin examples

These are the patterns most teams reach for. Each builds on the [hello-world](/docs/plugin-sdk/hello-world/) shape —
subscribe to a subject, handle idempotently, stay an observer — and shows where the **read-in via
events / write-out via public APIs** boundary lands.

Throughout: a plugin that acts on the outside world does so as an **ordinary, audited API client using
a BYO Secret** — never a shared master credential, and never through a coordination primitive.

## 1. Notify on Run outcomes (Slack / PagerDuty / email)

**Goal:** post to Slack when a Run fails, and page on-call if it's a production project.

- **Subscribe to:** `ksquad.run.*.*.ended` — one event for every terminal state; the payload's
  `state` field (`completed` | `failed` | `canceled`) tells you which.
- **Do:** call the Slack/PagerDuty API. The outbound token is a BYO Secret you hand the plugin at
  deploy time.
- **Idempotency:** dedupe on the event `id` so a redelivery doesn't double-post.

```go
func onRunEnded(e Event) {
	if seen(e.ID) { return }
	if e.Data.State != "failed" { return }        // only page on failures
	text := fmt.Sprintf("Run %s failed in %s (agent %s)", e.Data.RunID, e.Data.Project, e.Data.Agent)
	slack.Post(channelFor(e.Data.Project), text)   // ordinary API client, BYO token
	if isProduction(e.Data.Project) {
		pagerduty.Trigger(text)
	}
	markSeen(e.ID)
}
```

**Pattern note:** because a plugin can never block a Run, a flaky Slack endpoint can't stall the
platform — worst case, a notification is delayed and replayed later.

## 2. Mirror work items to an external tracker

**Goal:** reflect KSquad work items into Jira/Linear so a wider team sees them.

- **Subscribe to:** `ksquad.work_item.*.*.assigned`, `ksquad.work_item.*.*.claimed` (and
  `...reroute_released` if you track re-dispatches).
- **Do:** upsert the corresponding external issue via that tracker's API.
- **Idempotency is essential here:** key the external issue on the KSquad `workItemRef` and **upsert**,
  never blind-create — so a redelivered event updates rather than duplicates.

```go
func onWorkItem(e Event) {
	ext := tracker.UpsertByExternalKey(e.Data.WorkItemRef, mapFields(e))  // upsert = idempotent
	log.Printf("mirrored %s → %s", e.Data.WorkItemRef, ext.URL)
}
```

**Boundary reminder:** this mirrors *out*. The plugin reads work-item events and writes to Jira. It
does **not** — and cannot — move the KSquad work item; that stays in the fenced
[coordination record](/docs/author-guide/work-items/).

## 3. Feed a custom dashboard or warehouse

**Goal:** stream all activity into your own analytics store.

- **Subscribe to:** `ksquad.>` (everything) or a per-entity set.
- **Do:** append each event to your warehouse / time-series store, keyed by event `id`.
- **Catch-up:** use a durable JetStream consumer so a warehouse-loader outage replays cleanly and you
  never lose a row.

This is a good fit for JetStream **replay**: point a fresh durable consumer at the stream and backfill
from retained history.

## 4. React to CI / sync results

**Goal:** kick off a downstream deploy when a PR mirror shows checks passing.

- **Subscribe to:** the `scm` entity — `ksquad.scm.<project>.<squad>.>`.
- **Status:** the `scm` entity is catalog-admitted but its emitters land incrementally with the
  source-control mirror; until then, poll the [source-control mirror API](/docs/api-reference/) or
  watch run events instead.
- **Do:** when a project's PR reaches a green state, trigger your external CD system (its own API, BYO
  credential).

The plugin observes KSquad's synced view of the repo and drives an **external** system — again, read-in
via events, write-out via a public API, no coordination primitive touched.

## 5. Credential-attention watcher

**Goal:** ping an owner when an agent's credential needs attention.

- **Status:** there is no `credential` entity on the event bus today. Credential expiry surfaces in
  the control plane as a `Run → Paused` transition and in the console's credential state.
- **Do:** poll the apiserver's credentials API (an ordinary, audited read) on a timer, and notify
  the owning user or open a tracking ticket when a credential shows expired.

**Hard boundary:** the plugin **never injects the credential or resumes the Run** — credential
rotation and Run resume stay the control-plane path. This is the observe-only rule applied to the
case that most tempts you to break it.

## Design checklist for any plugin

- [ ] **Subscribe** to the narrowest subject that covers your need (per-project beats `ksquad.>`).
- [ ] **Pin** the event-schema revision you built against.
- [ ] **Dedupe** on event `id` — delivery is at-least-once.
- [ ] **Upsert / "ensure"** semantics for outbound side effects, never blind-create.
- [ ] **Use a durable consumer** so restarts replay cleanly.
- [ ] **BYO Secret** for every outbound credential; never assume a shared one.
- [ ] **Observe only** — if you find yourself wanting to move work or resume a Run, that's the
      coordination record's job, not a plugin's.
- [ ] **Fail soft** — a plugin that errors should retry its own side effect; it can never block KSquad.

## Related

- [Plugin SDK overview](/docs/plugin-sdk/) — the model and its guarantees.
- [Event reference](/docs/plugin-sdk/event-reference/) — the full catalog and subject taxonomy.
- [Observability](/docs/observability/#platform-health-metrics) — monitoring the event seam.
