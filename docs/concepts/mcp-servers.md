---
title: MCP Servers (MCPServer)
description: An MCPServer is a registered Model Context Protocol server — streamable-http or stdio — whose tool surface the control plane discovers, filters, and grants to skills on an allow/deny basis.
sidebar:
  order: 5
---

# MCP Servers

**CRD:** `MCPServer` (`ksquad.io/v1alpha1`)

An **MCPServer** is a registered [Model Context Protocol](https://modelcontextprotocol.io) server —
the endpoint that serves *tools* to your agents. Where a [Skill](./skills) declares *which* servers an
agent may reach, the `MCPServer` CRD declares *what each server is*: its transport, its endpoint or
command, its credential, and the **tool envelope** (allow/deny globs) the cluster is willing to grant
from it.

The CRD is **data-only** — transport, endpoint, credential ref, tool envelope, and optional egress
linkage. It never carries the credential itself (that lives in a Secret ref) and never carries the
tool list (that is *discovered*, below).

```yaml
apiVersion: ksquad.io/v1alpha1
kind: MCPServer
metadata:
  name: github-mcp
  namespace: bmad-squad
spec:
  transport: streamable-http        # stdio | streamable-http
  endpoint: https://api.githubcopilot.com/mcp/
  credentialSecretRef:              # BYO Secret, same namespace
    name: github-mcp-token
    key: token
  toolFilter:
    allow: ["*"]                    # globs; empty allow = everything observed
    deny: ["delete_*"]              # subtracted after allow matching
  # egressRef: { name: github-egress }   # optional EgressPolicy covering the endpoint
  discovery:
    intervalMinutes: 10             # default 10; 0 disables periodic re-probe
```

## Two transports

- **`streamable-http`** — one endpoint, POST for messages, `Mcp-Session-Id` header echo. The operator
  probes it directly from the control plane. Legacy SSE-only servers are **not** a v1alpha1 transport;
  they surface as `Ready=False` connect failures.
- **`stdio`** — a command plus an optional container image. At Run time the server runs as a
  **sidecar container** in the sandbox pod (when `image` is set), inheriting the pod's isolation and
  NetworkPolicy. Discovery runs it in a short-lived probe Job in the MCPServer's namespace — the
  operator never executes untrusted commands in its own process.

## Control-plane tool discovery

A discovery controller in the operator performs the MCP handshake (`initialize` → `tools/list`) and
records the result on the object's status:

```yaml
status:
  observedTools: [create_pull_request, list_issues, ...]
  lastProbedAt: "2026-08-26T12:00:00Z"
  conditions: [Ready, EgressAllowed, CredentialsValid, ToolsDiscovered]
```

Probing happens on create and spec change, then periodically per `discovery.intervalMinutes`.
`observedTools` is the cluster's **cached truth** about what the server actually serves — it feeds
the status conditions, the Run admission checks, and the console.

**Expect a probe cycle after the first apply.** Until discovery succeeds (`observedTools` empty,
`ToolsDiscovered=False`), any Run referencing the server **fails closed** — it stays `Pending` with
an actionable condition rather than admitting against an unknown tool surface. This is deliberate:
admission is a decision over cached status, never a live probe per Run.

## The tool envelope, and who may narrow it

`toolFilter` is the granted envelope: `allow` globs minus `deny` globs, computed against the server's
observed tools. An empty `allow` grants everything observed — useful for a trusted read-only server,
dangerous for anything else, so the example above keeps the broad allow and subtracts the destructive
corners.

The trust rule that matters:

> **A [Skill](./skills) may only *narrow* a server's `toolFilter`, never widen it.**

At Run assembly the effective tool set is `server.allow (empty = observedTools) ∩ skill narrowing −
deny`. A skill that narrows to a tool the server has never observed is a **fail-closed rejection** at
Run admission — which catches typos (`create_pull_request` → `create_pullrequest`) instead of
silently granting nothing. If narrowing plus deny leaves an empty effective set, the Run is rejected
too. Nobody widens an envelope after admission.

## Fail-closed at every hop

| Failure | Behavior |
|---|---|
| Skill references a missing `MCPServer` | Skill admission rejected (dangling `mcpToolRefs`) |
| `credentialSecretRef` / `egressRef` unresolvable | Condition `False`; Runs blocked while `False` |
| Server tool surface unknown (never discovered) | Run stays `Pending` (fail-closed staleness) |
| Skill narrows to a tool not in `observedTools` | Run admission rejected (dangling tool) |
| Effective allow set empty after narrowing/deny | Run admission rejected |

Credentials ride a Secret into **container env only** — never into a file the runtime workspace
persists, never into status or logs. Discovery probes hold the secret in-memory for header
construction and drop it.

## Egress

stdio sidecars run **inside the sandbox pod**, so they inherit its pod-level NetworkPolicy — no
separate policy surface. streamable-http endpoints must be inside the allow-union of the Run's
effective EgressPolicies; `spec.egressRef` names the policy that covers the endpoint, and assembly
fail-closes a Run whose server has a missing or broken egress policy. Discovery probes
(operator → endpoint) are control-plane traffic, not sandbox egress.

## Related

- [Skills](./skills) — `mcpToolRefs` bind skills to servers; skills only narrow.
- [Toolchains](./toolchains) — the other half of the capability plane (CLI/tool packs).
- [Runs](./runs) — assembly computes the effective tool set and records it in the capability manifest.
