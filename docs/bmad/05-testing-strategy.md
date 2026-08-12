---
title: KSquad Testing Strategy & CI/CD Methodology
phase: BMAD Phase 4 — Implementation (test architecture)
authors:
  - Amelia (Testing Architect) — test layers, frameworks, coverage gates, chaos/perf/security suites
  - DevOps Engineer (00abe623) — runner fleet, ghcr.io registry strategy, image-build packaging (co-owner; see §11)
source_ticket: ISI-2157
program: ISI-2115
inputDocuments:
  - docs/bmad/03-architecture.md            # r6 — component map §3.1, coordination spine §6/§15, warm pool §9.2, security §12/§17.1
  - docs/bmad/03-architecture-review-isi2132.md  # F1–F4 coordination-spine findings → chaos-suite acceptance gates
  - docs/bmad/epics.md                      # Epic 2.7 concurrency/chaos harness as first-class CI artifact; epic→test mapping
  - docs/bmad/04-observability-plan.md      # OTel taxonomy the perf/observability-validation tests assert against
  - ISI-2135                                # F1–F4 coordination-spine design fix (chaos acceptance gates)
  - ISI-2158                                # Ollama runtime adapter → free release-testing lane in CI
status: draft-for-devops-cosign-off
revisions:
  - r1 (2026-08-11, ISI-2157): initial testing methodology + CI/CD design; DevOps-owned sections (§11) flagged for co-sign
  - r2 (2026-08-12, ISI-2305): added §6.7 **Authentication & Authorization (RBAC) test matrix** — auth session lifecycle, admin/user access matrix per endpoint, per-project isolation, agent-identity + scoped-credential enforcement, privilege-escalation prevention, console adaptive-nav (non-admin UI), and the auth+middleware+agent integration case. §6 intro bumped six→seven mechanisms; traceability (§12) + epic map (§3.3) extended; **open item: human console authN mechanism (OIDC/IdP vs local cred) is unpinned — needs an ADR (§13)**, so the auth-session cases are written mechanism-aware and the IdP-delegated variant is the design-consistent default
---

# KSquad Testing Strategy & CI/CD Methodology

> **Ownership.** This document is jointly owned. **Testing Architect** owns the test-layer
> taxonomy, frameworks, coverage gates, and the concurrency/chaos + performance + security-test
> **content** (§3–§9). **DevOps Engineer** owns the **runner fleet, `ghcr.io` registry strategy,
> image-build packaging, and branch-protection wiring** (§11) — those sections are drafted here as a
> proposal and require DevOps co-sign before the workflow skeleton is pushed.
>
> **Board constraint (Henrik, 2026-08-11).** The `K8squad/K8squad` GitHub repo must contain **only
> real source code** — **no `docs/bmad/` artifacts and no `ISI-xxxx` references in any repo file or
> commit message**. This document lives in the Paperclip workspace (`ksquad/docs/bmad/`), *not* the
> git repo. The `.github/workflows/` skeleton that ships **in the repo** is ISI-free by construction.

---

## 1. Purpose & Scope

Define *how KSquad proves it works* and *how CI enforces it*, across the whole platform, before any
feature epic can close. The strategy covers five test layers and the GitHub Actions pipeline that
runs them:

| Layer | What it proves | Primary owner |
|-------|----------------|---------------|
| **L1 Feature / functional** | each component's units + integration behave (reconcilers, spine, memory, shims, console) | Testing Architect + component Devs |
| **L2 Concurrency / chaos** | the coordination spine is correct under race / crash / GC-pause (F1–F4) | Testing Architect (correctness-critical) |
| **L3 Performance** | claim latency (S9/NFR-PERF1), warm-pool ready-count, SSE throughput hold | Testing Architect + Observability Agent |
| **L4 Security** | images/modules/CVEs clean; secrets absent; blast radius bounded (S4) | Testing Architect + DevOps |
| **L5 Code quality** | lint clean, coverage gates met, before merge | all Devs (enforced in CI) |

**Principle (non-negotiable, per persona core):** *correctness is tested, not asserted.* Every
architecture claim that a review flagged as "asserted, not designed" (F1–F4) becomes an **executable
CI gate** here — the spine's guarantees are proven by a suite that actually runs, not a paragraph.

---

## 2. Component & Deployable Inventory

The pipeline is a **matrix over these deployables** (architecture §3.1, §17.3). Every one gets its
own image, SBOM, CVE scan, and test lane.

| Component | Language | Image (ghcr.io) | Contains | Test surfaces |
|-----------|----------|-----------------|----------|---------------|
| **ksquad-operator** | Go | `ghcr.io/k8squad/ksquad-operator` | controller-runtime reconcilers: Team/Agent/Project/Run/SandboxPool + repo-sync + ImageUpdater | reconciler unit (fake client) + envtest integration |
| **ksquad-apiserver** | Go | `ghcr.io/k8squad/ksquad-apiserver` | coordination record, audit API, SSE progress bus, SCM webhook ingress, outbox delivery workers | `pkg/coord` claim/lease/fencing unit + Postgres integration + **chaos suite (L2)** + SSE throughput (L3) |
| **ksquad-memory** | Go | `ghcr.io/k8squad/ksquad-memory` | MCP server, pgvector, provenance/trust model, discussion indexing | MCP-tool unit + pgvector integration + memory-poisoning / provenance-forgery security tests (L4) |
| **ksquad-console** | Node (Next.js) | `ghcr.io/k8squad/ksquad-console` | operator UI + BFF, SSE fan-out, dark/light theme | component/unit (vitest) + Playwright E2E (semantic locators) |
| **shim images (per runtime)** | Go (+ runtime base) | `ghcr.io/k8squad/ksquad-shim-<runtime>` | A2A⇄native sidecar; v1 = OpenClaw, Hermes; Phase 2 = Claude Code, OpenCode, Ollama | A2A conformance suite (per `AgentRuntime.type`) + shim dedup/idempotency unit |
| *(dependency)* Postgres via CNPG | — | upstream `cloudnative-pg` | single stateful dependency | brought up as a service/kind workload for integration + chaos lanes |

> **Registry note (DevOps §11).** `ghcr.io/k8squad/<image>` uses `${{ github.repository_owner }}`
> so the org rename is a no-op. Multi-arch `linux/amd64,linux/arm64` per prior org practice.

---

## 3. L1 — Feature / Functional Tests (per component)

### 3.1 Go components (operator, apiserver, memory, shims)

- **Framework:** standard `testing` + `testify` (assert/require) + table-driven tests — matches the
  org's existing Go test idiom (holmes-operator, semconv-proxy). No new framework introduced.
- **Reconciler units:** `sigs.k8s.io/controller-runtime` **fake client** for pure reconcile logic
  (state transitions, requeue, condition-setting) — fast, no cluster.
- **Integration:** `controller-runtime` **envtest** (real kube-apiserver + etcd binaries, no kubelet)
  for CRD validation, admission, and controller wiring; a **Postgres container** (or CNPG-in-kind)
  for coord/memory schema behaviour under real transactions.
- **Coverage target:** ≥ **80%** statement coverage per Go package; the `pkg/coord` spine package is
  held to a higher bar (≥ **90%**, every claim/renew/reclaim branch exercised).
- **Case discipline:** happy path + error cases + edge/boundary — e.g. claim SQL under
  null-holder / expired-lease / live-lease; fence-token monotonicity; status conditional-UPDATE with
  stale expected-state.

### 3.2 Node console

- **Framework:** **Vitest** for unit/component (BFF handlers, SSE-hub fan-out logic, theme tokens);
  **ESLint** for quality. Detect and follow whatever the console scaffolding lands with — do not
  impose a framework the repo did not choose (persona core: *detect before generating*).
- **API tests** (BFF): status codes (200/400/404/500), response structure, happy + error per route.
- **E2E:** see §6.4 (Playwright, semantic locators).

### 3.3 Epic → L1 mapping

| Epic | Component under test | L1 obligation |
|------|----------------------|---------------|
| 1 CRD Foundation | operator, apiserver | CRD schema validation (envtest), API scaffolding handlers |
| 2 Coordination Spine | apiserver `pkg/coord` | claim/renew/reclaim/fence units + Postgres integration (feeds L2) |
| 3 Run reconcile & warm-pool | operator | Run lifecycle transitions, retry/resume, kill; SandboxPool ready-count logic |
| 4 Sandbox & workspace | operator | teardown-and-replace, per-principal PVC scoping |
| 5 Shims & A2A | shims | Agent Card generation, capability negotiation, **deterministic `a2a_task_id` dedup** |
| 6 Memory service | memory | MCP tool surface, pgvector search, provenance surfacing on read |
| 7 Credentials & pause/resume | operator, shims | credential injection (never logged), Paused→resume |
| 8 Console | console | UI/BFF units + E2E; **BFF authZ choke point + adaptive-nav (§6.7.2/6.7.6)** |
| 10 Discussion rooms | apiserver, memory | discussion schema, memory-projection, **not-a-coordination-channel** guard |
| 11 Source-control sync | operator, apiserver | repo-sync reconciler, webhook ingress, mirror mapping |
| 12 Plugin architecture | apiserver `pkg/events` | outbox transactional append, delivery worker retry/dead-letter/circuit-breaker, **read-only observer guard** |

---

## 4. L2 — Concurrency / Chaos Suite (the coordination spine)

> **This is the single most important suite in KSquad.** The spine (checkout/claim/lease/fencing) is
> a from-scratch distributed-systems build and the #1 correctness-critical track (architecture §15,
> R10). Epic **2.7** makes this harness a **first-class, required CI artifact** — not optional. The
> four architecture-review findings **F1–F4** (ISI-2135) become **named acceptance gates**.

### 4.1 Harness shape

- **Runtime:** a **kind** cluster in CI + a real **Postgres** (CNPG single-instance) so claim
  transactions run against the actual engine (`SELECT … FOR UPDATE SKIP LOCKED`, MVCC, fencing). A
  fake DB would not exercise the property under test.
- **Fault injection:** deterministic, code-driven — pod freeze (SIGSTOP / cgroup freezer to simulate
  a GC pause), controller kill between two ordered steps, injected clock skew past lease expiry,
  N concurrent claimers as goroutines/pods. No wall-clock flakiness: leases use a short, pinned TTL;
  the harness advances a controllable time source or uses bounded polling with explicit deadlines.
- **Determinism guard:** the suite **fails fast** if a required precondition (fence-token column,
  unique-active-claim constraint, dispatch marker) is absent — it must not silently pass on a schema
  that never shipped the fence (the F2 trap).

### 4.2 Named acceptance gates (F1–F4 → executable cases)

| Gate | Scenario | Assertion (pass condition) |
|------|----------|----------------------------|
| **C1 · parallel claimers** (Epic 2.7a) | N agents claim the same work item simultaneously | exactly **one** claim succeeds; N−1 get no row and back off; no double-claim |
| **C2 · work-pull fan-out** | N agents pull from an open backlog via `SKIP LOCKED` | each dequeues a **distinct** item; none blocks; no item double-served |
| **C3 · crash-mid-claim reclaim** (Epic 2.7b) | holder stops renewing; lease expires | item becomes reclaimable by the exact §6.2 `WHERE`; a new holder acquires with **fence_token+1** |
| **C4 · stale-holder write rejection / fencing** (Epic 2.7c, **F2/F3**) | reclaimed item; old holder wakes and tries to renew + write comment/status/artifact/memory with its **stale fence** | every stale-fence write is **rejected**; stale-row renewal is a **no-op** (`holder AND fence AND lease>now` all guard) — no two live leases |
| **C5 · zombie-writer-vs-PVC** (**F1**, §6.3, R10 gate) | freeze holder's sandbox past lease expiry (simulated GC pause) → reconciler reclaims to a new Run → unfreeze old holder | old pod was **terminated before the claim was released** (fence-before-release ordering); its stale-fence memory + artifact writes are **rejected**; shared Project workspace shows **no cross-Run interleave**; `reclaim_fenced_at` marker present |
| **C6 · double-dispatch** (**F4**, §6.4, R10 gate) | kill the reconciler between A2A submit and the dispatch-marker write; restart | **exactly one** shim task exists (`a2a_task_id = run_id`, shim dedup) and **exactly one** agent execution occurred; re-entered Collecting phase → artifact **upsert**, no duplicate rows |
| **C7 · idempotent reconcile re-entry** (Epic 2.7d) | re-drive claim/complete/status passes repeatedly | conditional UPDATEs make every re-entry safe; no resurrect/double-advance of a Run |

### 4.3 Gate policy

- The L2 suite is a **required status check**. Epic 2 **cannot close** until C1–C7 are green.
- C5 (zombie-writer) and C6 (double-dispatch) are the two explicitly named R10 acceptance gates —
  they block the coordination-spine epic before any dependent epic (3/4/5) builds on it.

---

## 5. L3 — Performance Tests

Performance targets ride the OTel taxonomy from the observability plan (§17.2). Tests assert
**relative thresholds** (regression gates vs a pinned baseline), not brittle absolute numbers, since
final numeric tuning is spike-gated (ISI-2113).

| Perf test | Target | Source signal | Gate |
|-----------|--------|---------------|------|
| **P1 · claim latency** (S9 / **NFR-PERF1**) | time from work-available → claim acquired under the warm pool is "grab-time" | claim span duration p50/p95 | p95 within baseline + tolerance; **no regression** > X% vs main |
| **P2 · warm-pool ready-count** | `SandboxPool` keeps N pods `Ready` per (RuntimeClass × AgentRuntime) key; claim draws a warm pod | ready-count gauge, cold-start rate | interactive Runs draw warm (cold-start rate ≈ 0 under policy); batch may cold-start (expected) |
| **P3 · SSE throughput** | progress bus fans out to M subscribers without lag/backpressure collapse | SSE emit→deliver latency, dropped-event count | latency p95 bounded; **zero** dropped events at target concurrency |
| **P4 · outbox delivery lag** | plugin event seam keeps up; a slow plugin never blocks the write path | outbox depth, delivery lag, dead-letter count, circuit state | depth bounded; write path latency **independent** of plugin health (proves §17.4 isolation) |

- **Load driver:** lightweight Go benchmark harness (`go test -bench` for micro; a k6/vegeta-style
  driver for SSE fan-out) run on a dedicated CI lane (not on every PR — nightly + release, plus
  on-demand). Numeric tuning curves (P1/P2 sizing) land after ISI-2113.
- Perf lanes publish results as artifacts and (later) into the consumption/OTel dashboards the
  Observability Agent owns — coordinate the metric names there so tests and dashboards agree.

---

## 6. L4 — Security Tests

Seven mechanisms, run as a dedicated `security` workflow + inline gates. §6.1–6.6 are supply-chain /
blast-radius mechanisms; **§6.7 is the authentication & authorization (RBAC) test matrix** (ISI-2305)
— the identity-and-access half of the "tested, not asserted" security bar.

### 6.1 Dependency & module scanning
- **`govulncheck`** on every Go module — call-graph-aware, gates on **known-exploitable** vulns.
- **Node:** `npm audit --audit-level=high` (or `pnpm audit`) on the console.

### 6.2 Image CVE scanning
- **Trivy** (primary) on **every** built image; **Grype** as cross-check on release images.
- **Gate:** fail on **CRITICAL** (and HIGH with a fix available) — `--exit-code 1 --severity CRITICAL,HIGH --ignore-unfixed`. A curated `.trivyignore` (with expiry dates + justification) is the only escape hatch, reviewed like code.

### 6.3 SAST
- **CodeQL** (Go + JavaScript/TypeScript) on PR + weekly schedule. Node24-compatible action.

### 6.4 Secrets scanning
- **Gitleaks** on PR + full-history scan on schedule. Zero-tolerance gate. (Reinforces the board's
  no-secrets-in-repo posture and NFR-SEC3 "credentials never logged/echoed".)

### 6.5 Blast-radius / NetworkPolicy validation (S4, §12.2, §17.1)
The architecture's security model is "tested, not asserted" (§17.1). The **S4 blast-radius suite**
runs in kind against a hostile-Run fixture:

| Case | Proves |
|------|--------|
| **default-deny egress** | a sandbox with no allowlist entry cannot reach arbitrary endpoints; only model/tool/control-plane endpoints resolve (§12.2, NFR-SEC4) |
| **exfil-attempt via allowlisted model endpoint** (review F11) | the allowlisted hole is **named and observed** (egress proxy audits), not mistaken for containment |
| **cross-namespace isolation** | a Team-A pod cannot reach Team-B services / Secrets (namespace tenancy, NFR-SEC1) |
| **reuse-residue** (F6/F7) | after teardown-and-replace, a fresh sandbox exposes **no** prior-Run scratch/secret/worktree state; per-principal PVC scoping holds |
| **cross-principal same-Team read-authZ** (B1/F7, ISI-2166; NFR-SEC5) | in the **build browser** (§9.4, ISI-2148), principal **B** calling `GET /api/runs/{A's runId}/build/{tree,diff,file,meta}` — where A and B are **in the same Team/Project** but B is not the Run's owner — gets **`404`** (existence-hiding), because Layer-1 authZ requires `Run.owningPrincipal == caller.principal`; the per-principal cache partition alone does **not** gate the git read path. **Positive control:** owner A reads own Run → `200`. Cross-Team → `404`. This is the blocking **8.7d** security gate — proves the visibility model is per-principal, not Team-legible |
| **memory-poisoning / provenance forgery** (F5/F6) | a hostile Run cannot forge another principal's provenance; reads are surfaced as untrusted; memory is **not** a covert coordination channel (covert-channel test, review F6) |

### 6.6 Supply chain (nice-to-have → recommended)
- **SBOM** per image (see §11) is itself a security artifact.
- **cosign** keyless (OIDC) **sign + attest** each release image; SBOM attached as an attestation.
  Marked nice-to-have in the brief; recommend enabling on release images from day one (cheap, high
  provenance value).

### 6.7 Authentication & Authorization (RBAC) test matrix (ISI-2305)

> **What this proves.** Identity is *established* correctly (authN), *scoped* correctly (authZ/RBAC),
> and *cannot be widened* (escalation-proof) — across the three enforcement points the architecture
> actually names: the **console BFF choke point** (§13 — resolves `caller.principal` + Team scope
> *before* any backend call), the **apiserver middleware** (write-auth + provenance, §7.3.1), and the
> **agent execution identity** (per-principal BYO Secret, read-only consumer, §11/§12). These sit
> alongside — not on top of — the Kubernetes primitives (namespace RBAC / NetworkPolicy / Secrets)
> that §6.5 already exercises; here we prove the *application-layer* gate, because K8s RBAC does not
> see a BFF request's principal.

#### 6.7.0 Architecture ground-truth & the one open decision (read first)

The access model these tests assert against, pinned from the architecture:

- **Principal is the authZ subject.** `Run.owningPrincipal == caller.principal` gates per-Run reads
  (§9.4, ISI-2166); memory/discussion writes are provenanced and impersonation is *impossible by
  construction* (§7.3.1). There is **no principal spoofing path** — that is a property under test, not
  an assumption.
- **Two console roles + one platform role.** `operator` (acts within their Team — create/pause/
  resume/kill own-Team Runs, connect own credential), `viewer` (read-only, Team-scoped; the org
  chart/dashboards **never** expose a mutate/claim/handoff affordance — §12.1), and `platform-admin`
  (K8s-RBAC layer — registers `AgentRuntime`/`Skill.source`, authors `Team`/`Agent` CRDs, sets the
  capability envelope; §5.3.6). "admin vs user" in ISI-2305 maps to **platform-admin vs operator/
  viewer**; "user cannot access admin endpoints" = operator/viewer cannot reach the platform-admin
  plane.
- **Existence-hiding.** Out-of-scope reads return **`404`, not `403`** (don't confirm existence) —
  already locked for the build browser (8.7d); §6.7 applies the same rule Team-wide.
- **⚠ OPEN DECISION (blocks fully-concrete auth-session cases).** KSquad has **no home-grown password/
  session store** designed. The *provider* credential model is OAuth (§11.1), but the **human console
  authN mechanism is unpinned**: OIDC/IdP-delegated (SSO) vs a local credential store. The
  design-consistent default — matching the K8s-native, no-secret-handling posture (NFR-SEC3) and the
  existing OAuth lifecycle — is **IdP-delegated (OIDC)**, in which case *password reset lives in the
  IdP, and KSquad never stores or handles a password*. The §6.7.1 auth-session cases are therefore
  written **mechanism-aware**: the IdP variant is the primary suite; a local-cred variant is scaffolded
  **skipped-with-reason** and activates only if an ADR chooses local creds. **Handoff: this needs an
  ADR (PM/Architect) before §6.7.1 can drop its `skip` (§13 open items).**

**Determinism guard (matches §4.1):** the §6.7 suite **fails fast** if the BFF has no principal-
resolution middleware wired, or if any endpoint reaches a backend before an authZ decision is
recorded — it must not silently pass on a build where the choke point was never installed.

**Positive controls are mandatory (matches §6.5):** every deny case ships with the matching allow case
(the legitimate role *can* do the thing) so a blanket-500 or blanket-deny bug cannot masquerade as
"secure". A test suite that only proves denials proves nothing.

#### 6.7.1 Auth session lifecycle (apiserver middleware + BFF)

Framework: Go `testing`+`testify` against the apiserver auth middleware; Playwright for the console
redirect/teardown legs. IdP faked by a pinned local OIDC stub (e.g. mock-oidc) in CI — no external IdP
dependency, no real credentials.

| Case | Scenario | Assertion (pass condition) |
|------|----------|----------------------------|
| **A1 · login (valid)** | caller presents a valid IdP token/session | BFF resolves a principal + its Team memberships; a scoped session is established; the principal is attached to the request context for every downstream authZ decision |
| **A2 · invalid credentials** | malformed / bad-signature / wrong-audience / expired-at-presentation token | **`401`**, **no** principal established, **no** downstream apiserver/kube/git call made (verified by a backend spy); no stack/secret leak in the body |
| **A3 · session expiry** | a session valid at login crosses its TTL mid-use | next request → **`401`** + re-auth signal; any **in-flight SSE stream is closed** (not left streaming under a dead principal); no authZ decision uses the stale principal |
| **A4 · logout** | principal logs out | session invalidated server-side; subsequent calls with the old session → **`401`**; SSE subscriptions torn down; a replayed post-logout session token is **not** re-accepted |
| **A5 · password reset** *(IdP variant — primary)* | user triggers "reset/recover" | KSquad **redirects to the IdP** and **never stores/handles the password** (asserted: no password field crosses the BFF, nothing password-shaped hits any log — reinforces NFR-SEC3); on IdP completion the next login (A1) succeeds with the same principal identity |
| **A5-local** · password reset *(local-cred variant)* | — | **skipped-with-reason** pending the authN ADR; if local creds are chosen: reset token single-use + time-boxed, old sessions invalidated on reset, no user-enumeration via reset responses |

#### 6.7.2 RBAC access matrix — per endpoint × role

Table-driven over `(endpoint-family, verb, role, scope) → expected status`. Endpoint families are the
real ones in the architecture; every cell is one test row. `own` = caller's Team/principal; `other` =
a different Team or a non-owner principal in the same Team.

| Endpoint family (real ref) | platform-admin | operator (own) | viewer (own) | any role (other-scope) |
|---|---|---|---|---|
| **Read own dashboards / consumption / org-chart / audit** (§13, §6/§8 read model) | `200` | `200` | `200` | **`404`** |
| **Per-Run build browser** `GET /runs/{id}/build/{tree,diff,file,meta}` (8.7d) | owner-only¹ | `200` iff owner | `200` iff owner | **`404`** |
| **Mutate Run** (create / pause / resume / kill; §13 BFF→operator) | `200` | `200` | **`403`** | **`404`** |
| **Coordination / claim write** (`pkg/coord`; §6.2 — agent/coordinator principals only) | **`403`**² | **`403`**² | **`403`** | **`403`** |
| **Credentials** ("Connect Claude" / re-login; §11.1) | own principal only | own principal only | own principal only | **`403/404`** — cannot connect/refresh/read another principal's Secret |
| **Admin plane** (register `AgentRuntime`/`Skill.source`, set capability envelope, `Team` RBAC; §5.3.6) | `200` | **`403`** | **`403`** | **`403`** |

¹ platform-admin is not implicitly a Run owner — the build view is per-*principal*, so even admin gets
`404` on a Run they don't own (existence-hiding holds against admin too, unless an explicit break-glass
audit path is later ADR'd). ² the console is a **read-only org chart** with **no P2P/claim affordance**
(§12.1, no-P2P) — a human console caller reaching a claim-write verb is itself the anomaly under test.

- The matrix runs at **both** layers: BFF integration (fake principal header + scope) **and** an
  apiserver-middleware unit layer, so a BFF that forgets to forward scope can't hide behind a correct
  apiserver, and vice-versa.

#### 6.7.3 Per-project / per-team isolation (extends §6.5)

Builds directly on §6.5's cross-namespace + cross-principal cases; adds the **Project-scope** cut the
ticket names.

| Case | Scenario | Assertion |
|------|----------|-----------|
| **I1 · cross-Project read** | user with access to Project A requests a Run/artifact/build/memory record scoped to **Project B** (same or different Team) | **`404`** — Project scope is enforced at the BFF *and* by the Team-namespace RBAC/NetworkPolicy underneath; no listing endpoint leaks B's IDs into A's response |
| **I2 · cross-Project write** | A-scoped principal attempts a mutate/claim/memory-write targeting a Project-B object | rejected at the apiserver (**`403/404`**), never reaches the DB row; provenance would have mis-attributed → blocked by construction (§7.3.1) |
| **I3 · enumeration** | A-scoped principal pages/filters list endpoints trying to surface B's Projects/Runs | zero B-scoped rows in any response; counts/aggregates (consumption, org chart) exclude B — no side-channel via totals |

#### 6.7.4 Agent identity & scoped-credential enforcement

Proves the *agent-execution* identity leg (not human console) — the third enforcement point.

| Case | Scenario | Assertion |
|------|----------|-----------|
| **AG1 · Run carries correct identity** | a Run executes and writes a comment / status / artifact / memory record | every write is attributed to the Run's `owningPrincipal` / `author_run_id` / `author_agent_id`; a Run **cannot** author a record attributed to a different principal (§7.3.1 impersonation-impossible) |
| **AG2 · scoped credential — mount only** | agent pod consumes its BYO provider Secret | pod **mounts** the per-user Secret read-only; the Run's SA **cannot read another principal's / another Team's** credential Secret (K8s RBAC + §12 per-principal isolation); credential value **never** appears in logs/spans (NFR-SEC3, redaction §6.7.1-adjacent) |
| **AG3 · stale-fence identity** | a fenced/zombie holder (see L2 **C4/C5**) tries to write under its old identity after reclaim | rejected — ties the auth model to the coordination fence: identity alone is insufficient, the **live fence** must also hold (cross-refs L2, no new mechanism) |

#### 6.7.5 Privilege-escalation prevention

| Case | Scenario | Assertion |
|------|----------|-----------|
| **E1 · vertical escalation** | operator/viewer calls a **platform-admin** endpoint (§6.7.2 admin row) | **`403`**; no partial effect (no CRD created then rejected — fail *before* the write) |
| **E2 · capability self-declaration** | a git-sourced `Skill` body (untrusted, D8) declares broader `permissions`/`mcpToolRefs` than the operator authorized | the **CRD/operator-authorized envelope wins**; the repo-declared widening is **ignored**, not merged (§5.3.6 — "never self-declared by the repo"); no new tool/permission is reachable at runtime |
| **E3 · token/scope confusion** | caller replays a *provider* OAuth token (§11.1) as if it were a *console* session, or a viewer session against a mutate verb | rejected — provider creds are not console-authZ tokens; scope is not transferable across the two planes |
| **E4 · horizontal via identity swap** | caller sets/forges a principal header the BFF is supposed to derive, not trust | BFF derives principal from the authenticated session **only**; a client-supplied principal/Team header is **ignored** (asserted against a spoofed header — this is the E4 trap) |

#### 6.7.6 Console adaptive nav (non-admin UI) — Playwright E2E

Semantic-locator E2E (per §8 conventions), one run per role fixture. UI is a *reflection* of the
authZ model, not a substitute — every hidden affordance also has a §6.7.2 API-layer deny (a hidden
button is not a security control; the API is).

| Case | Role fixture | Assertion |
|------|--------------|-----------|
| **N1 · viewer nav** | viewer | no mutate/claim/handoff/kill controls rendered; Settings→admin panes absent; org chart is read-only (§12.1, §13) — asserted by **role/label absence**, not CSS `hidden` |
| **N2 · operator nav** | operator | Run mutate controls + own-credential "Connect Claude" present; **platform-admin** panes (runtime/skill-source registration) absent |
| **N3 · admin nav** | platform-admin | admin registration surfaces present |
| **N4 · nav ≠ authZ** | viewer, via devtools/direct fetch | invoking a hidden mutate endpoint directly still returns **`403`** — proves the nav is cosmetic and the BFF is the real gate (defeats "hidden-in-UI ≈ secure") |

#### 6.7.7 Integration — auth service + apiserver middleware + agent execution

One end-to-end identity-propagation test (kind + Postgres + OIDC stub, joins the L2/E2E harness):

- **Path:** IdP login → BFF establishes principal+scope → apiserver middleware authZ on a Run action →
  operator reconciles → **agent pod runs under the Run's `owningPrincipal` with its scoped Secret** →
  the agent's coordination/memory writes are provenanced to that same principal → the console reads
  back **only** what that principal is scoped to see.
- **Assertion:** identity is **one continuous thread** end-to-end — the principal established at login
  is the same principal that authorizes the write and stamps the provenance; **no boundary silently
  re-derives, widens, or drops it**. A break anywhere (BFF forwards no scope; middleware trusts a
  client header; agent runs under a shared/ambient identity; provenance mis-attributes) fails this test.
- Runs on the **`e2e.yml`** lane (nightly + release), reusing the OIDC stub; the API-layer matrix
  (§6.7.2/6.7.5) runs on **`security.yml`** every PR (fast, no cluster).

| Check | Tool | Gate |
|-------|------|------|
| Go lint | **golangci-lint** (pinned config `.golangci.yml`; govet, staticcheck, errcheck, gosec, revive, ineffassign) | zero findings |
| Node lint | **ESLint** (+ Prettier check) | zero errors |
| Go coverage | `go test -coverprofile` | ≥ 80% per package; ≥ 90% `pkg/coord` |
| Node coverage | vitest `--coverage` | ≥ 70% console (raise as UI stabilizes) |
| `go vet` / build / `-race` | toolchain | clean; **`-race` required** on the spine + concurrency lanes |

Coverage is reported per-package (not a single global number) so the correctness-critical spine
cannot hide behind high coverage in trivial packages — the audit discipline from prior TA work.

---

## 8. Test Frameworks — Summary (detect-before-generate)

| Surface | Framework | Rationale |
|---------|-----------|-----------|
| Go unit | `testing` + `testify`, table-driven | org-standard, already in use |
| Go controller integration | controller-runtime **envtest** | real apiserver, no kubelet — fast + faithful |
| Go DB integration + chaos | **kind** + CNPG Postgres | real transactions/fencing under real MVCC |
| Go perf | `go test -bench` + SSE load driver | micro + macro |
| Node unit/component | **Vitest** + ESLint | modern, fast; confirm against actual scaffolding |
| Console E2E | **Playwright** | **semantic locators** (roles/labels/text), user-workflow assertions, visible-outcome checks — persona E2E conventions |
| A2A shim conformance | Go conformance suite keyed by `AgentRuntime.type` | one suite, per-runtime lanes (ISI-2114 owns the reference assertions) |

> **Console E2E note:** headless-browser E2E needs the browser libs present on the runner. Prior TA
> work hit a wall running Chromium headless locally without the GUI libs — in CI this is solved by
> Playwright's own action (`microsoft/playwright-github-action` / `npx playwright install --with-deps`),
> so E2E belongs in CI, not on a dev box. The console E2E lane installs deps explicitly.

---

## 9. E2E Squad Scenarios & the Ollama Free-Testing Lane (ISI-2158)

Full-platform E2E ("run a squad end-to-end") normally needs a live agent runtime + model, which
costs paid API credits per run. The **Ollama runtime adapter (ISI-2158)** doubles as a **free
release-testing lane**:

- CI spins an **Ollama service container** (or a self-hosted GPU runner) with a **small model pinned
  by digest**; a smoke squad scenario runs a Run through the full path (claim → dispatch → shim →
  agent → artifact → complete) with **zero API keys**.
- This gives a deterministic, credit-free E2E gate for the coordination + shim + Run-lifecycle path.
  Runs on release + nightly (not every PR — it is heavier).
- Requires the Ollama shim (Phase 2) + the ISI-2114 conformance harness to be present; until then the
  E2E lane is scaffolded and skipped-with-reason (never silently dropped).

---

## 10. CI/CD Pipeline — GitHub Actions Design

Repo: `K8squad/K8squad`. Workflows live in `.github/workflows/` (ISI-free repo content). Design
follows the org's proven Docker-build patterns (mcp-proxy, securityevents, holmes fork) adapted to a
**component matrix**.

### 10.1 Workflow set (skeleton shipped in the repo)

| Workflow file | Trigger | Jobs |
|---------------|---------|------|
| `ci.yml` | PR + push to `main` | matrix per component: lint → build → unit+integration test → coverage upload. Node + Go legs. **Required.** |
| `spine-chaos.yml` | PR touching `apiserver`/`pkg/coord` + push + nightly | kind + Postgres; run L2 C1–C7 with `-race`. **Required** for spine changes. |
| `build-images.yml` | push to `main` + tags `v*` | matrix per component: buildx multi-arch → push `ghcr.io` → **SBOM (Syft)** artifact → **Trivy** CVE scan (gate) → cosign sign+attest (release). |
| `security.yml` | PR + weekly schedule | govulncheck, Trivy fs/config, gitleaks, CodeQL (Go+JS). |
| `e2e.yml` | nightly + release + manual dispatch | Ollama service container + smoke squad scenario; Playwright console E2E. |

### 10.2 Matrix strategy
Each of `ci.yml` / `build-images.yml` uses a `strategy.matrix.component` over
`[operator, apiserver, memory, console]` + a nested shim matrix over `[openclaw, hermes]` (extensible).
Component legs run **in parallel**; each is an independent **required status check** so branch
protection can require green per component.

### 10.3 Node 24-compatible actions (brief constraint)
Node 20 action runtimes are deprecated; **pin actions to majors that run on the Node 24 runtime.**
The skeleton uses: `actions/checkout@v5`, `actions/setup-go@v6`, `actions/setup-node@v5`,
`actions/upload-artifact@v5`, `docker/*` current majors, `github/codeql-action@v3`,
`golangci/golangci-lint-action` current, `anchore/sbom-action`, `aquasecurity/trivy-action`,
`sigstore/cosign-installer@v3`, `gitleaks/gitleaks-action@v2`. **Renovate/Dependabot** keeps them on
node24-compatible majors — a stale action pin is a CI-quality regression, tracked like any other.

### 10.4 Required checks & branch protection (DevOps §11) — ratified check names
Before merge to `main`, the following **required status checks** (check-run = job name) must pass.
`build-images.yml` runs post-merge (push to `main` / tags); `e2e.yml` is scheduled + dispatch (not a
PR gate). Applied via the branch-protection API — see §11.4.

| Workflow | Required check-run name(s) |
|----------|---------------------------|
| `ci.yml` | `go / operator`, `go / apiserver`, `go / memory`, `node / console` |
| `spine-chaos.yml` | `coordination-spine chaos suite` |
| `security.yml` | `govulncheck (Go modules)`, `npm audit (console)`, `Trivy (filesystem + config)`, `Gitleaks (secrets)`, `CodeQL (go)`, `CodeQL (javascript)` |

Lint + coverage gates run **inside** the `ci.yml` component legs, so gating those legs gates them.
Skeleton-phase legs pass via skip-with-reason until each component's source lands (§13), so the
protection can be wired now without wedging merges.

---

## 11. DevOps-Owned Sections — ratified (DevOps Engineer 00abe623, 2026-08-11)

**Co-sign:** the `.github/workflows/` skeleton is reviewed and co-signed as pushable. The DevOps half
below is now decided, not proposal; the Dockerfile set + guard hardening + branch-protection recipe
ship with the same PR.

### 11.1 Runner fleet
| Lane | Runner | Rationale |
|------|--------|-----------|
| `ci.yml` (Go/Node build, lint, unit, coverage) | `ubuntu-latest` (2-core) | fast, cheap, parallel matrix |
| `build-images.yml` (multi-arch buildx + QEMU) | `ubuntu-latest` + `type=gha` layer cache | QEMU arm64 emulation is slow but acceptable post-merge; revisit native arm64 runner (`ubuntu-24.04-arm`) if push time hurts |
| `spine-chaos.yml` (kind + Postgres, `-race`) | **`ubuntu-latest-4-core`** (larger runner) initially | kind + CNPG + race detector needs RAM/CPU headroom; promote to a **self-hosted** node if the scheduled nightly saturates |
| `security.yml` (govulncheck / Trivy-fs / gitleaks / CodeQL) | `ubuntu-latest` | CodeQL wants ≥2-core; fine on hosted |
| `e2e.yml` squad-smoke (Ollama, credit-free) | `ubuntu-latest` for small models; **self-hosted GPU optional** | Ollama CPU inference is enough for a smoke; GPU only if the scenario grows |

Decision: **stay on GitHub-hosted runners for v1**; introduce one self-hosted node only when the
nightly chaos/perf lane measurably needs it. No self-hosted footprint blocks the initial merge. The
`runs-on:` in `spine-chaos.yml`/`e2e.yml` carries an inline DevOps note marking the promotion point.

### 11.2 ghcr.io registry governance
- **Namespace:** `ghcr.io/k8squad/ksquad-<component>` (+ `ksquad-shim-<runtime>`). Workflows use
  `${{ github.repository_owner }}`, so the org name is never hard-coded — an org rename is a no-op.
- **Auth:** CI pushes with the built-in `GITHUB_TOKEN` + `packages: write` (already scoped per
  workflow). No long-lived PAT in secrets for image push.
- **Visibility:** packages inherit repo visibility; set **public** at first publish if the repo is
  public, else internal. Link each package to the repo (`org.opencontainers.image.source` label is set
  in every Dockerfile so GHCR auto-associates).
- **Retention:** keep all `vX.Y.Z` release tags; prune untagged/`sha-*` dev digests older than **30
  days** via a scheduled `actions/delete-package-versions` cleanup (follow-up lane, not blocking).
- **Immutability:** treat release (`v*`) tags as immutable by convention — CI never re-pushes an
  existing semver tag; only digests are signed/attested (`cosign` in `build-images.yml`).

### 11.3 Image build packaging — shipped in this PR
- One `Dockerfile.<component>` per deployable: `operator`, `apiserver`, `memory`, `console`, plus a
  `Dockerfile.shim` template (per-runtime, Phase 2 / ISI-2114, not yet in the matrix).
- **Go images:** cross-compiled from `--platform=$BUILDPLATFORM golang:1.23-alpine` (fast, no QEMU in
  the compile step) into `gcr.io/distroless/static-debian12:nonroot` — static, non-root (uid 65532),
  `-trimpath -ldflags="-s -w"`, full OCI `org.opencontainers.image.*` labels.
- **Console:** `node:24-bookworm-slim` multi-stage → Next.js `output: 'standalone'` →
  `gcr.io/distroless/nodejs24-debian12:nonroot` (requires `output: 'standalone'` in `next.config`).
- **Cache:** `cache-from/to: type=gha,mode=max` + `BUILDKIT_INLINE_CACHE=1` (already in
  `build-images.yml`) + BuildKit `--mount=type=cache` for the Go mod/build caches in-Dockerfile.
- **Guard hardening:** `build-images.yml` now gates each lane on **Dockerfile *and* component source**
  (`go.mod` / `console/package.json`), so shipping the Dockerfiles ahead of source can't trip a doomed
  build on `main`; lanes skip-with-reason until source lands (never a silent drop).
- `.dockerignore` keeps the build context lean/deterministic across the multi-arch matrix.

### 11.4 Branch protection wiring (§10.4)
Applied via REST once the checks have reported once on the first PR (so the context names resolve):

```bash
gh api -X PUT repos/K8squad/K8squad/branches/main/protection \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[checks][][context]=go / operator' \
  -f 'required_status_checks[checks][][context]=go / apiserver' \
  -f 'required_status_checks[checks][][context]=go / memory' \
  -f 'required_status_checks[checks][][context]=node / console' \
  -f 'required_status_checks[checks][][context]=coordination-spine chaos suite' \
  -f 'required_status_checks[checks][][context]=govulncheck (Go modules)' \
  -f 'required_status_checks[checks][][context]=npm audit (console)' \
  -f 'required_status_checks[checks][][context]=Trivy (filesystem + config)' \
  -f 'required_status_checks[checks][][context]=Gitleaks (secrets)' \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -f 'enforce_admins=false' -f 'restrictions=' 
```
> **Requires repo-admin scope.** The CI/push credential has `contents:write` but branch-protection is
> an **Administration** setting. If the push token lacks it, this step is the one hand-off to a
> **repo admin (Alfred / org owner)** — everything else in §11 ships without it.

### 11.5 Secrets
`build-images.yml` uses **cosign keyless (OIDC)** — `id-token: write`, no stored signing key. Only
CI-provisioned secret needed for v1 is the built-in `GITHUB_TOKEN`. No registry PAT, no cosign key.

---

## 12. Traceability (test → architecture → epic)

| Test | Architecture ref | Epic | Requirement |
|------|------------------|------|-------------|
| L2 C1–C2 (claim/pull) | §6.2 | 2.1/2.7 | FR-B2, no double-claim |
| L2 C3–C4 (reclaim/fence) | §6.2/§6.3 | 2.7, R10 | NFR-REL1, F2/F3 |
| L2 C5 (zombie-vs-PVC) | §6.3, §15 | R10 gate | **F1** (ISI-2135) |
| L2 C6 (double-dispatch) | §6.4, §15 | R10 gate | **F4** (ISI-2135) |
| L2 C7 (idempotent reconcile) | §6.4 | 2.7d | re-entrancy |
| L3 P1 (claim latency) | §9.2 | 3 | S9 / NFR-PERF1 |
| L3 P2 (warm-pool ready) | §9.2 | 3 | FR-C1/C4 |
| L3 P3 (SSE throughput) | §3.1, §17.2 | 8 | NFR-USE / progress bus |
| L3 P4 (outbox lag) | §17.4 | 12 | plugin isolation |
| L4 blast-radius (S4) | §12.2, §17.1 | 4 / X | NFR-SEC1/4/5, F6/F7/F11 |
| L4 provenance/poisoning | §7.3 | 6 | NFR-SEC6, F5/F6 |
| **L4 §6.7.1 auth session (A1–A5)** | §13 BFF choke, §11.1 | 8 / 7 | NFR-SEC3; **authN-mechanism ADR (open)** |
| **L4 §6.7.2 RBAC matrix** | §13, §12.1, §5.3.6 | 8 | NFR-SEC1; admin/operator/viewer |
| **L4 §6.7.3 per-Project isolation (I1–I3)** | §12.1, §9.4 | 4 / 8 | NFR-SEC1/5 |
| **L4 §6.7.4 agent identity (AG1–AG3)** | §7.3.1, §11, §12 | 6 / 7 | NFR-SEC3/6; impersonation-impossible |
| **L4 §6.7.5 escalation (E1–E4)** | §5.3.6, §11.1 | 5 / 8 | no-privilege-escalation (D8) |
| **L4 §6.7.6 adaptive nav (N1–N4)** | §12.1, §13 | 8 | NFR-SEC1 (UI≠authZ) |
| **L4 §6.7.7 auth integration** | §13, §7.3.1, §11 | 5 / 8 | end-to-end identity thread |
| L4 govulncheck/Trivy/gitleaks/CodeQL | §17.1 | all | supply-chain / NFR-SEC3 |
| L5 lint/coverage | — | all | quality gate |
| E2E Ollama smoke | §10, §9.2 | 5 / 3 | ISI-2158 free-testing lane |

---

## 13. Open Items / Handoffs

- **DevOps (00abe623): DONE (2026-08-11)** — co-signed §10/§11; runner fleet sized (§11.1, hosted for
  v1); ghcr governance set (§11.2); `Dockerfile.{operator,apiserver,memory,console,shim}` + `.dockerignore`
  shipped and the `build-images.yml` guard hardened to gate on source presence (§11.3); branch-protection
  recipe ready (§11.4, needs repo-admin scope to apply); cosign keyless / no stored secrets (§11.5).
  Skeleton pushed to `K8squad/K8squad`. *Only residual:* applying branch protection needs an
  Administration-scoped token (repo admin / Alfred).
- **⚠ Human console authN mechanism — needs an ADR (PM/Architect), blocks §6.7.1 `skip` drop.** The
  auth-*session* cases (A1–A5) are scaffolded mechanism-aware, with **IdP-delegated (OIDC)** as the
  design-consistent primary suite (matches the K8s-native, no-secret-handling NFR-SEC3 posture and the
  existing OAuth credential lifecycle §11.1); the local-credential variant (A5-local) stays
  **skipped-with-reason** until the decision lands. Everything else in §6.7 (RBAC matrix, isolation,
  agent identity, escalation, adaptive nav, integration) is mechanism-independent and active now.
  *Owner of the unblock: PM (John) / Architect ADR — until then A5-local cannot un-skip.*
- **Observability Agent:** align the OTel metric/span names the L3 perf tests assert on with the
  dashboard taxonomy (04-observability-plan.md, §17.2) so tests and dashboards read the same signals.
- **Spike ISI-2113:** provides the numeric baselines for P1/P2 gates (thresholds stay relative until
  then).
- **ISI-2114 (shim conformance):** owns the reference shim + A2A conformance assertions the shim lanes
  invoke; the Ollama E2E lane depends on it + the Ollama shim (ISI-2158, Phase 2).
- **Source scaffolding:** L1 lanes activate as each component's source lands in the repo; workflows
  are scaffolded now (skipped-with-reason where a component doesn't exist yet — never silently
  dropped).

*All existing + new tests must pass 100% before any epic is marked complete (persona core principle).*
