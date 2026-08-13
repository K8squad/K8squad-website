# Story 9.1: Chart creates Gateway + HTTPRoute (console + apiserver SSE)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The chart CREATES exposure, it does not assume it.** On any cluster with a Gateway API
> controller (cilium / envoy / istio / traefik), `helm install --set exposure.gateway.gatewayClassName=<x>`
> renders a `Gateway` (listeners + TLS **from values**: hostnames, cert-secret refs, http→https
> redirect) and two `HTTPRoute`s binding the **console** and **apiserver** Services — and the
> **apiserver route preserves the SSE stream** (§13): `timeouts.request: "0s"`, so no response
> buffering / default idle timeout cuts a long-lived Run progress stream. Install **fails fast with
> a clear error if `exposure.gateway.gatewayClassName` is unset** — the chart **references** the
> operator-provided `GatewayClass` and **never creates one**, never falls back to a hardcoded or
> cluster-default class. A hardcoded/defaulted class, a missing/finite apiserver-route timeout, a
> route bound to the wrong Service, a rendered `GatewayClass` object, or a silent fallback on unset
> class is a **regression**. Read AC3, AC4, and AC5 literally.

## Story

As a **platform engineer installing KSquad on my own cluster**,
I want **the chart to create the `Gateway` + `HTTPRoute` resources for the console and apiserver,
with listeners/TLS/hostnames from values, the apiserver route preserving SSE, and a fail-fast error
if `gateway.className` is unset**,
so that **exposure works on any Gateway API implementation I choose — portably, with the console's
live channel intact — and I am never silently bound to a class I didn't confirm exists.**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` Theme L (**FR-L1…L3**) — the install SHALL **create** its
  cluster-facing networking rather than assume it; the console's live channel (SSE) must survive the
  ingress path; the ≤4h air-gapped install (S1, NFR-USE1) must hold on clusters with differing
  Gateway/Ingress posture.
- **Architecture:** `docs/bmad/03-architecture.md` **§16.1** (Networking & exposure — Gateway API,
  amended 2026-08-11, CEO directive) — *"The chart creates exposure, it does not assume it."* Gateway
  API (not a legacy `Ingress`) is the primitive **because its `HTTPRoute` timeout/backend semantics
  express the SSE requirement portably**. `gatewayClassName` is a **required values input** when
  Gateway-mode is selected — never hardcoded, never the cluster default; the chart **references** the
  operator-provided class and **never creates one**. Listener + TLS (hostnames, cert-secret refs,
  HTTPS-redirect) are all values-exposed. Also **§13** (console live SSE channel, Epic 8.2), **§16.2**
  (explicit StorageClass — sibling Story 9.2), **ADR-022** (exposure model: chart creates
  `Gateway`+`HTTPRoute`; `gatewayClassName` required; `exposure.mode = gateway|ingress|clusterip`).
- **Gateway-less fallback (OQ16 — resolved, §16.1):** exposure is a **`values.exposure.mode`** switch
  with three pre-flightable options — `gateway` (this story's preferred production path, full
  SSE-timeout control), `ingress` (graceful degrade: plain `Ingress` with SSE-safe annotations for
  clusters with an Ingress controller but no Gateway API), and `clusterip` (Services only,
  zero-dependency, always brings the stack up). `ingress`/`clusterip` are documented as **not** giving
  the same portable SSE-timeout guarantee — an honest trade, surfaced not hidden. This story pins the
  **`gateway`** path; the fallback modes ride the same fail-fast validate.
- **SSE preservation is the crux (§13, Epic 8.2 — [[isi-2265-story82-live-run-sse]]):** the apiserver
  route carries the console's live Run/progress stream. A default GatewayClass route timeout (Envoy's
  15s) or response buffering **cuts the stream**. The apiserver `HTTPRoute` therefore sets
  `timeouts.request: "0s"` (+ `backendRequest: "0s"`) — the **portable** way to say "never time this
  route out." `HTTPRoute.timeouts` is *Extended* conformance (not Core): Envoy Gateway / Istio honor
  it, Traefik survives via having no default, **Cilium may silently ignore it** — the chart README
  carries the per-implementation caveat (verify per class) rather than pretending it's universal.
- **Chart implementation:** the chart lives and is CI-tested in the **`k8squad`** source repo at
  `deploy/helm/ksquad/` — commit `5e6442d` on `feature/helm-exposure-storage`
  (**ISI-2149** `feat(helm): parameterized Gateway API exposure + explicit StorageClass`, hardened by
  **ISI-2286** `fix(helm): honest SSE-timeout conformance docs + guard empty Gateway`). `ci/test.sh`
  lints + renders all three modes + asserts the fail-fast guards (needs a `helm` binary). This story
  (ISI-2250) pins the **construction-time contract** those templates must satisfy and adds a
  `helm`-free falsification bench. A read-only snapshot of the shipped chart is vendored under
  `docs/bmad/spikes/bench/helm-chart-isi2149/` for the bench's file-grounded pass (see PROVENANCE.md).
- **Scope guard:** this story is exposure for **console + apiserver only** (the two user-facing
  Services). Explicit StorageClass is **Story 9.2** (§16.2); NATS/JetStream Helm dep is **Story 9.4**;
  auth config packaging is **Story 9.5**. The chart never vendors the Gateway/CNPG/NATS operators —
  they are cluster prerequisites so the chart renders and lints offline.

## Acceptance Criteria

**AC1 — Gateway rendered with listeners + TLS FROM VALUES (never hardcoded/defaulted).**
With `exposure.mode=gateway` and `gatewayClassName` set, the chart renders exactly one `Gateway`
whose `gatewayClassName` is the values input (cilium/envoy/istio/traefik), with http and/or https
listeners per `exposure.gateway.listeners.*.enabled`, ports from values, and — for the https listener —
`tls.mode: Terminate` with `certificateRefs` pointing at the values-supplied cert Secret. No listener,
port, class, hostname, or cert-secret is a hardcoded literal or a cluster default.
*(Bench: C1 — differential over two distinct value profiles; FG3.)*

**AC2 — Two HTTPRoutes bind the console and apiserver Services.** The chart renders a console
`HTTPRoute` (backendRef → the **console** Service, host = `exposure.hostnames.console`) and an
apiserver `HTTPRoute` (backendRef → the **apiserver** Service, host = `exposure.hostnames.apiserver`),
each with `parentRefs` → the rendered Gateway and a `sectionName` that names a **real enabled
listener** (never a dangling section). The two routes bind **different** Services (no misbind).
*(Bench: C2; FG5.)*

**AC3 — The apiserver route preserves SSE (the live-channel crux).** The **apiserver** `HTTPRoute`
(the SSE endpoint, §13) sets `timeouts.request: "0s"` (and `backendRequest: "0s"`) so a long-lived
progress stream is never cut by the route/backend timeout. The timeout override is on the **apiserver**
route specifically — an absent override, a finite timeout, or the override placed only on the console
route is a **regression** (the stream dies). *(Bench: C3 — catches drop/finite/console-only; FG1.)*

**AC4 — Install fails fast if `gateway.className` is unset — no silent fallback.** With
`exposure.mode=gateway` and `gatewayClassName` empty, `helm install`/`template` **fails with a clear
error** (`ksquad.validate`), rendering **nothing** — it never falls back to a hardcoded or
cluster-default class. The same fail-fast covers an https listener with no cert-secret and a Gateway
with zero enabled listeners (ISI-2286 F2 — no dangling `sectionName`). *(Bench: C4; FG4.)*

**AC5 — The chart NEVER creates a `GatewayClass`.** No template renders a `kind: GatewayClass`
object in any mode/profile — the chart **references** the operator-provided class (a `gatewayClassName`
string), never owns one. *(Bench: C5; FG2.)*

**AC6 — TLS + http→https redirect are values-driven.** Listener TLS (cert Secret) and the edge
http→https redirect (`exposure.gateway.httpsRedirect`, rendered as a `RequestRedirect`→https route on
the http listener when both listeners are enabled) are controlled entirely by values — present when
requested, absent when not, no template edit required. *(Bench: C6.)*

## Falsification bench

`docs/bmad/spikes/bench/gateway-httproute-check.py` (stdlib only, `helm`-free):

- **Layer A — model-based mutation battery.** A faithful mini-renderer of the chart's gateway-mode
  exposure + `ksquad.validate` fail-fast. Six checks **C1–C6 ↔ AC1–AC6**; differential checks render
  two distinct value profiles (A: cilium/tls-a/redirect-on, B: envoy/tls-b/redirect-off) and assert
  the output **tracks the input** — the teeth against hardcoding that "it renders once" cannot give.
  **11 broken-chart mutations**, each caught by its designated check going RED; the §16.1-conformant
  baseline is GREEN on all six.
- **Layer B — file-grounded pass.** Reads the **pinned real chart snapshot** (k8squad@5e6442d), asserts
  the **shipped** templates satisfy each invariant, and text-mutates each template to prove the
  detector flips — teeth on the real artifact, not just the model. 5 detectors (FG1 SSE `0s`, FG2 no
  GatewayClass, FG3 class-from-values, FG4 fail-fast-on-unset, FG5 both backends bound).

**Result: baseline C1–C6 GREEN; all 11 mutations caught; 5 file-grounded detectors pass with teeth.**
Mutation → caught-by map:

| Mutation | Break | Caught by |
|---|---|---|
| M1 hardcode `gatewayClassName` | class frozen, ignores values | C1 |
| M2 silent default-class fallback | unset class → `"default"` instead of fail | C4 |
| M3 drop apiserver timeout | default route timeout cuts SSE | C3 |
| M4 finite 60s apiserver timeout | SSE cut at 60s | C3 |
| M5 `0s` on console route only | apiserver stream defaulted | C3 |
| M6 apiserver route → console svc | route misbind | C2 |
| M7 render a `GatewayClass` object | chart creates a class | C5 |
| M8 skip `gatewayClassName` validate | unset renders anyway | C4 |
| M9 ignore `httpsRedirect` value | redirect not values-driven | C6 |
| M10 hardcode hostnames | hosts frozen, ignore values | C2 |
| M11 hardcode TLS cert secret | cert frozen, ignores values | C1 |

Run: `python3 docs/bmad/spikes/bench/gateway-httproute-check.py` (exit 0 = all teeth hold).
Full render/lint gate (needs `helm`): `k8squad` `deploy/helm/ksquad/ci/test.sh`.

## Definition of Done

- [x] Construction-time contract (AC1–AC6) pinned against arch §16.1 / ADR-022 / Theme L.
- [x] Chart shipped in `k8squad` (`deploy/helm/ksquad/`, ISI-2149 + ISI-2286) satisfies all six ACs.
- [x] Falsification bench green: C1–C6 baseline GREEN, 11 mutations caught, 5 file-grounded detectors
      pass with teeth (`gateway-httproute-check.py`, exit 0).
- [x] Pinned chart snapshot + PROVENANCE recorded for the file-grounded pass.

## Notes

- **k8squad is the source of truth for the chart; ksquad holds the story + bench artifacts** — the
  vendored snapshot is a read-only fixture pinned to a commit, not a fork. Refresh by re-vendoring +
  bumping the commit in `PROVENANCE.md` if the chart changes.
- **SSE portability caveat is honest, not hidden** (§16.1, ISI-2286): `HTTPRoute.timeouts` is Extended
  conformance — Cilium may ignore `0s`. The README documents per-class behavior and the `ingress`/
  `clusterip` fallbacks; this story's guarantee is that the chart *expresses* the SSE requirement the
  most portable way Gateway API allows, and surfaces where it can't be enforced.
