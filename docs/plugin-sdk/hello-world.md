---
title: Hello-world plugin
description: Build your first KSquad plugin — subscribe to Run-completed events over NATS, print a message, and learn the idempotent, replayable, observe-only pattern.
sidebar_position: 2
---

# Hello-world plugin

In this tutorial you'll build a minimal KSquad plugin that **prints a line every time a Run
completes**. It's deliberately tiny — the point is to learn the shape: subscribe to a subject, handle
an event idempotently, and stay a read-only observer.

> **Prerequisites:** a running KSquad install ([Quickstart](/docs/quickstart/)), and the ability to run a
> small service that can reach the cluster's NATS. Any NATS client works — a plugin is just a NATS
> subscriber — but this tutorial uses Go to match KSquad's own stack.

## 1. What we're building

A standalone service that subscribes to `ksquad.run.*.*.ended` and logs each Run that reaches a
terminal state. No state is mutated; nothing can block the platform. When you've got this working,
swapping the log line for a Slack post (see [Examples](/docs/plugin-sdk/examples/)) is a one-line
change.

## 2. Register the plugin & get NATS access

> **Status:** the console's **Settings → Plugins** page is a placeholder ("plugin management is
> coming") — there is no registration UI yet. For now, run your plugin as a standalone service and
> hand it the connection details yourself: the NATS URL, the subject prefix (`ksquad`), and any
> credentials. Store credentials as a Kubernetes Secret — plugins use **BYO Secret refs**, never a
> shared master credential.

For local development you can port-forward NATS:

```bash
kubectl -n ksquad-system port-forward svc/ksquad-nats 4222:4222
```

## 3. Subscribe with a durable consumer

Using JetStream's **durable** consumer means your plugin can go down and **replay** what it missed when
it comes back.

```go
package main

import (
	"encoding/json"
	"log"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"context"
)

// The event envelope (pin to the schema revision you built against).
type Event struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	Subject string `json:"subject"`
	Data    struct {
		RunID       string `json:"runId"`
		Project     string `json:"project"`
		Team        string `json:"team"`
		Agent       string `json:"agent"`
		InitiatedBy string `json:"initiatedBy"`
	} `json:"data"`
}

func main() {
	nc, err := nats.Connect("nats://localhost:4222" /*, nats.UserCredentials("plugin.creds") */)
	if err != nil {
		log.Fatal(err)
	}
	defer nc.Drain()

	js, err := jetstream.New(nc)
	if err != nil {
		log.Fatal(err)
	}

	ctx := context.Background()

	// A DURABLE consumer over terminal Run events, across all projects/squads.
	cons, err := js.CreateOrUpdateConsumer(ctx, "KSQUAD", jetstream.ConsumerConfig{
		Durable:       "hello-world-plugin",           // survives restarts → replay/catch-up
		FilterSubject: "ksquad.run.*.*.ended",         // Runs that reached a terminal state
		AckPolicy:     jetstream.AckExplicitPolicy,     // ack after we handle it
	})
	if err != nil {
		log.Fatal(err)
	}

	seen := map[string]bool{} // trivial in-memory dedupe; use a durable store in production

	_, err = cons.Consume(func(msg jetstream.Msg) {
		var e Event
		if err := json.Unmarshal(msg.Data(), &e); err != nil {
			log.Printf("skip malformed event: %v", err)
			_ = msg.Ack() // don't redeliver forever on a parse error
			return
		}

		// 4. Handle idempotently — delivery is AT-LEAST-ONCE.
		if seen[e.ID] {
			_ = msg.Ack()
			return
		}
		seen[e.ID] = true

		log.Printf("Run %s ended in project %s (agent %s, started by %s)",
			e.Data.RunID, e.Data.Project, e.Data.Agent, e.Data.InitiatedBy)

		_ = msg.Ack() // ack only after the side effect succeeded
	})
	if err != nil {
		log.Fatal(err)
	}

	select {} // run forever
}
```

## 4. The three things this teaches

- **Subscribe by subject.** `FilterSubject: "ksquad.run.*.*.ended"` uses the
  [subject taxonomy](/docs/plugin-sdk/event-reference/#subject-taxonomy) wildcards. Narrow it to one project with
  `ksquad.run.payments.*.ended`.
- **Be idempotent.** Delivery is at-least-once, so we dedupe on the event `id` and **ack only after**
  the work is done. If your handler dies before the ack, JetStream redelivers — and the dedupe makes
  that safe.
- **Stay an observer.** This plugin only *reads*. It never claims a work item, resumes a Run, or writes
  to the coordination record — and there's no API that would let it. That's the guarantee that makes it
  safe to run against a live control plane.

## 5. Run it

```bash
go mod init hello-world-plugin
go get github.com/nats-io/nats.go@latest
go run .
```

Now start a Run (from the console or `kubectl apply` a `Run`). When it reaches a terminal state
(`Succeeded` / `Failed` / `Cancelled`), the `ended` event fires and your plugin logs a line — the
event payload's `state` field tells you which. Stop the plugin, run a few more, restart it — the
durable consumer **replays** the ones it missed. That's the whole model.

## 6. Where to go next

- **Do something useful:** swap the `log.Printf` for a Slack/webhook call. Remember: outbound calls go
  through a normal, audited API client with a **BYO Secret** — see [Examples](/docs/plugin-sdk/examples/).
- **Widen or narrow the subjects:** subscribe to work-item claims (`ksquad.work_item.*.*.claimed`),
  or — as those emitters land — artifact registrations and source-control mirror results — see the
  [Event reference](/docs/plugin-sdk/event-reference/#the-event-taxonomy).
- **Pin your schema revision** so platform upgrades don't surprise you.
