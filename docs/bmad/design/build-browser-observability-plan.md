<!--
  Build Browser — Observability Plan (ISI-2165)
  Turns §7 of build-browser-component-design.md (ISI-2148) into a concrete
  metrics/traces/alerts plan, aligned with the OTel metering spine (arch §17.2)
  and the KSquad Observability Plan (docs/bmad/04-observability-plan.md).
  Owner: Observability Agent. Feeds Epic 8.7 (Story Writer / Dev Amelia).
-->

# Build Browser — Observability Plan (ISI-2165)

- **Source design:** `docs/bmad/design/build-browser-component-design.md` §7 (ISI-2148, ADR-021)
- **Parent plan:** `docs/bmad/04-observability-plan.md` — this is a component sub-plan; it inherits
  that plan's standing law (§1 correlation + §1.2 cardinality gate), its `ksquad.*` Weaver registry
  (§7), its collector pipeline (§10), and its CI label-allowlist gate (§5.6/§11).
- **Spine alignment:** arch §17.2 (OTel observability) + §11 (consumption/metering provenance,
  OQ14/ADR-020) + NFR-OBS3.

---

## 0. The one hard constraint (NFR-OBS3) — read the firewall first

> **Build-read volume is legibility telemetry, NEVER a consumption / billing axis.**

Everything below obeys one rule: the browser's read signals answer *"is the build view healthy and what
does it cost the platform to operate"* — they **never** answer *"how much did principal X consume."*
Concretely:

1. **Separate metric namespace.** All build-read signals live under `ksquad.buildbrowser.*` — an
   **operational** namespace, disjoint from the `ksquad`-consumption metrics (`ksquad.agent.tokens`,
   run-minutes, sandbox resource) that §11/§17.2 attribute to a principal and feed the §13 **consumption
   dashboard**.
2. **No metering label set.** Build-read metrics are **never** labeled `model`, and never carry
   `principal.id`/`run.id`/`work_item.id` as metric labels (those are span/log/exemplar-only per parent
   §1.2 / §5.6). The `model` axis is the billing disambiguator in the metering spine (§11); its **absence
   here is deliberate and load-bearing** — a metric with no `model` and no per-principal label *cannot*
   be aggregated into a consumption bill even by accident.
3. **Disjoint from the metering query seam.** The §13 consumption dashboard reads the metering-backend
   query seam (§11); its metric allowlist **must not reference any `ksquad.buildbrowser.*` series**. See
   the enforcement gate in §7 below — this is the machine-checkable form of NFR-OBS3.
4. **The single legitimate cost tie.** The **RO-reader pod** (§4.2 of the design) is real infra spend.
   Its CPU/mem rides the *same* non-forgeable kubelet/cAdvisor signal as any sandbox (§11 spine), but it
   is attributed as **platform operating cost of the console feature** (`ksquad.buildbrowser.reader.*`),
   **not** as the requesting principal's Run consumption. Reading a build is free-to-the-user by
   contract; the reader pod's cost is the platform's, surfaced as a cost *signal* (§6 alert), never a
   charge.

If a future change would make read volume proportional to a bill, it violates NFR-OBS3 and this plan —
raise it as a change request, don't wire it.

---

## 1. Traces — per-read spans, correctly attached to the Run

§7 asks for per-read spans "as children of the Run trace." That is exactly right for a **live** Run and
subtly wrong for a **completed** one, because the pod — and the Run's trace — is torn down at completion
(design §4, §9.3). We honor the intent with the correct OTel edge in each case:

### 1.1 Span shape

Every build-read request emits one BFF-rooted span with an inner source span:

```
SPAN  buildbrowser.<endpoint>            (Next.js BFF, GET-only surface §3)
  └─ SPAN buildbrowser.read.source       (apiserver → shim | snapshot | ro_reader)
```

`<endpoint>` ∈ `tree | diff | file | meta`. Attributes (all **span/log/exemplar only** — never metric
labels):

| Span attribute | Domain | Notes |
|----------------|--------|-------|
| `ksquad.run.id` | UUID | root correlation key (parent §7 registry) |
| `ksquad.work_item.id` | UUID | ticket-timeline join (parent §3/§15) |
| `ksquad.buildbrowser.endpoint` | `tree\|diff\|file\|meta` | also a *bounded* metric label (§2) |
| `ksquad.buildbrowser.live` | bool | live-shim vs completed-snapshot path |
| `ksquad.buildbrowser.source` | `shim\|snapshot\|ro_reader` | which read path served it |
| `ksquad.buildbrowser.cache_hit` | bool | per-principal cache partition hit (§5.3 design) |
| `ksquad.buildbrowser.bytes_returned` | int | **magnitude only — never the body** (§5 PII rule) |
| `ksquad.buildbrowser.truncated` | bool | tree cap hit (§3 design) |
| `ksquad.buildbrowser.too_large` | bool | file/diff cap hit (§3 design) |
| `ksquad.buildbrowser.path` | string | requested path — span-only, unbounded; **filename only, never content** |
| `ksquad.buildbrowser.outcome` | `ok\|truncated\|too_large\|not_found\|denied\|binary` | terminal read outcome |

### 1.2 Attachment — live vs completed (the correction)

- **Live Run (`live=true`).** The read is contemporaneous with an open Run trace. The BFF propagates
  W3C `traceparent` over the existing A2A read verb (design §4.1) into the shim; the `buildbrowser.*`
  spans are **true children of the Run trace root** (parent §3) — exactly as §7 sketched.
- **Completed Run (`live=false`).** The Run trace closed at teardown; a read happening minutes/days
  later **cannot** be a live child of a finished span. Model it as a **new BFF-rooted trace with an OTel
  span *link*** back to the Run — carrying `ksquad.run.id` and the Run's original `trace_id`
  (persisted on the `coord.artifact` build-snapshot `meta`, design §4.2). This is the correct
  causal-but-asynchronous edge; a forced parent-child would fabricate a span under a trace that no
  longer exists. This lands cleanly on the parent plan's **P1 distributed-trace** phase (§4.1) — P0
  correlates via `run.id` on logs/exemplars; P1 upgrades to the linked trace.

### 1.3 Sampling

Reads are high-frequency polls (`tree`/`meta` poll on cadence, design §6). Apply the parent plan's
tail-sampling posture (§4.2): **always keep** `outcome ∈ {denied, not_found, too_large}` and any
`source=ro_reader` read (rare, cost-bearing); head-sample the `outcome=ok` `tree`/`meta` poll firehose
low (e.g. 1–5%) so a live console's poll loop doesn't flood Tempo. `diff`/`file` are user-driven and
pulled — keep at a higher rate.

---

## 2. Metrics — `ksquad.buildbrowser.*` (operational, cardinality-bounded)

All labels below are **bounded enums**; run/principal/work-item ids stay off the labels (§0.2, parent
§5.6). New label domains introduced here — `endpoint`, `source`, `cache_hit`, `live` — are added to the
parent §5.6 allowlist (see §7).

### 2.1 Read-surface metrics (BFF + apiserver)

| Instrument | Type | Labels (bounded) | Why |
|------------|------|------------------|-----|
| `ksquad.buildbrowser.read.total` | counter | `endpoint`, `live`, `source`, `cache_hit`, `outcome` | read volume/health — **legibility, not billing (NFR-OBS3)** |
| `ksquad.buildbrowser.read.duration` | histogram | `endpoint`, `source` | read latency SLI (§8 SLO) |
| `ksquad.buildbrowser.bytes_returned` | histogram | `endpoint`, `source` | **distribution** of payload size — page-cost/limit tuning, never summed into a consumption counter |
| `ksquad.buildbrowser.scope.denied` | counter | `endpoint` | cross-principal `404` denials (design §5) — security/enumeration signal, ties S4/NFR-SEC5 |

`bytes_returned` is deliberately a **histogram, not a monotonic sum** — a sum reads like a meter; a
distribution reads like "how big are payloads," which is the operational question and cannot be
mistaken for a consumption axis.

### 2.2 Snapshot-emission metrics (operator, at Collecting §6.1)

| Instrument | Type | Labels (bounded) | Why |
|------------|------|------------------|-----|
| `ksquad.buildbrowser.snapshot.emit.total` | counter | `result` (ok\|failed\|skipped) | snapshot-emit success/failure — drives the "no build view" alert (§6) |
| `ksquad.buildbrowser.snapshot.emit.duration` | histogram | `result` | emit cost at Collecting |
| `ksquad.buildbrowser.snapshot.bytes` | histogram | `truncated` (bool) | bundle size (§7 design `buildbrowser.snapshot.bytes`) — capacity/at-rest planning |
| `ksquad.buildbrowser.snapshot.file_count` | histogram | `truncated` (bool) | changed-file count (§7 design `.fileCount`) |

### 2.3 RO-reader pod metrics (the cost signal, §4.2 design)

| Instrument | Type | Labels (bounded) | Why |
|------------|------|------------------|-----|
| `ksquad.buildbrowser.reader.launched.total` | counter | `reason` (full_tree), `outcome` (launched\|reused\|failed) | **RO-reader launch rate = cost signal** (§7 design) |
| `ksquad.buildbrowser.reader.active` | gauge | — | live reader pods (concurrency/cost ceiling) |
| `ksquad.buildbrowser.reader.ttl` | histogram | `outcome` (idle_teardown\|error) | reader lifetime (idle-teardown health) |

Reader **CPU/mem** is *not* re-invented here — it rides `k8s.pod.*` from kubelet/cAdvisor (parent §5.3 /
arch §11 spine), scoped by the reader pod's resource attributes and attributed as **feature operating
cost** (§0.4), never principal consumption.

---

## 3. Logs

Parent §6 rules apply verbatim (structured, `trace_id`/`span_id`/`ksquad.run.id` auto-stamped; BFF uses
`pino`, Go uses `slog`). Build-browser-specific lines:

- **Scope denial** — `WARN`, `{run.id, principal.id, endpoint, outcome=denied}`. Never confirms
  existence in the response (404), but the **log** carries the id for the S4 audit + enumeration
  detection. Provenanced, id-only.
- **Snapshot-emit failure** — `ERROR` at Collecting, `{run.id, work_item.id, result=failed, cause}`.
- **RO-reader lifecycle** — `INFO` launch/teardown with `{run.id, reader.pod, reason, ttl_ms}`.
- **Never logged:** file **content**, diff **bodies**, blob bytes. Only sizes/counts/paths/status — see
  §5.

---

## 4. Alerting & SLOs

Alerts derive from §7's two named concerns (snapshot-emit failure, RO-reader launch rate) plus the
scoping gate. All are **ticket-grade** — the browser is a legibility surface that **degrades to 404, not
outage** (design §7 "surface it, don't silently 404"); none page.

| SLO / SLI | Target | Alert condition | Severity |
|-----------|--------|-----------------|----------|
| **Build-view coverage** — fraction of **completed & successful** Runs (`run.completed{outcome!=failed}`) with a `build-snapshot` `coord.artifact` | ≈ 100% | a successful completed Run has **no** build-snapshot artifact within N min of Collecting → **"no build view" degradation** | **ticket** (legibility) |
| **Snapshot-emit failure** `snapshot.emit.total{result=failed}` | ≈ 0 | rate > 0 sustained 15m | **ticket** |
| **RO-reader launch rate (cost)** `reader.launched.total` / `reader.active` | within budget | launch rate ≥ N× baseline **or** `reader.active` sustained above ceiling | **ticket** (cost) |
| **Read availability** `read.total{outcome=ok}` ratio | ≥ target | error ratio (`outcome ∈ {not_found_unexpected, error}`) > 5% over 15m | **ticket** |
| **Read latency** `read.duration{endpoint=tree}` | p95 within budget | p95 > budget 10m | **ticket** |
| **Scope-denial spike** `scope.denied` | baseline noise | one principal's denial rate spikes (enumeration probe) → correlate S4 | **ticket** (security) |

**"No build view" is the headline alert** (§7): the correctness question is not "did a read fail" but
"did a completed Run silently lose its build view." That's why the coverage SLO is a **join of the Run
lifecycle signal against the artifact table**, not just an emit-error counter — an emit that never *ran*
(skipped, missed Collecting) is the failure mode a pure `result=failed` counter misses.

---

## 5. PII / secret hygiene (persona critical rule)

Diffs and files are raw workspace content and **may contain secrets a Run wrote to disk** (design §5).
The telemetry firewall:

- **Content never enters a signal.** No span attribute, log line, or metric ever carries file content,
  diff body, or blob bytes. Only **magnitudes** (`bytes_returned`, `size_bytes`, `file_count`),
  **status** (A/M/D/R, binary, truncated, too_large), and **paths** (filename only, span/log only).
- **Paths are span/log-only and unbounded** → never a metric label (both cardinality *and* the small
  chance a path itself is sensitive).
- **`validate-telemetry-data`** (Weaver, parent §7) runs emitted build-browser telemetry against the
  registry schema before vendor sign-off, and the redaction processor in the collector (parent §10)
  runs **before export** as the belt-and-suspenders backstop.

---

## 6. Semantic conventions — registry additions (Weaver, parent §7)

Add to `docs/observability/semconv/` under the `ksquad.buildbrowser.*` group:

| Attribute | Type | Domain | Metric-label eligible? |
|-----------|------|--------|------------------------|
| `ksquad.buildbrowser.endpoint` | string | `tree\|diff\|file\|meta` | ✅ bounded |
| `ksquad.buildbrowser.source` | string | `shim\|snapshot\|ro_reader` | ✅ bounded |
| `ksquad.buildbrowser.live` | bool | true\|false | ✅ bounded |
| `ksquad.buildbrowser.cache_hit` | bool | true\|false | ✅ bounded |
| `ksquad.buildbrowser.outcome` | string | `ok\|truncated\|too_large\|not_found\|denied\|binary\|error` | ✅ bounded (curated enum) |
| `ksquad.buildbrowser.reader.reason` | string | `full_tree` | ✅ bounded |
| `ksquad.buildbrowser.bytes_returned` | int | magnitude | ❌ span/exemplar only |
| `ksquad.buildbrowser.truncated` / `.too_large` | bool | — | ✅ bounded (snapshot label) |
| `ksquad.buildbrowser.path` | string | filename | ❌ span/log only (unbounded + sensitivity) |

**Reuse:** OTel `k8s.pod.*` resource semconv for the RO-reader cost (no new attribute); `ksquad.run.id`
/ `ksquad.work_item.id` unchanged from parent §7.

---

## 7. Enforcement gates (make NFR-OBS3 machine-checkable)

Two CI gates, extending the parent §5.6/§11 gates:

1. **Cardinality allowlist (extend parent §5.6).** Add `endpoint`, `source`, `cache_hit`, `live`,
   `reader.reason` to the bounded-label allowlist; `bytes_returned`, `path`, `run.id`, `work_item.id`,
   `principal.id` stay on the forbidden-as-label list. The existing label-key grep gate then covers
   build-browser instrumentation automatically.
2. **NFR-OBS3 firewall gate (new).** A CI check asserts the **§13 consumption-dashboard / metering
   query allowlist contains zero `ksquad.buildbrowser.*` series**, and that no `ksquad.buildbrowser.*`
   instrument declares a `model` label. This is the executable form of "read volume is never a
   consumption axis" — it fails the build if a future edit wires the two together.

---

## 8. Instrumentation scope (Phase-4, per Epic 8.7 story slice)

| Component | Emits | SDK | Epic 8.7 story |
|-----------|-------|-----|----------------|
| **BFF (Next.js)** | `buildbrowser.<endpoint>` root span; `read.total`/`read.duration`/`bytes_returned`; `scope.denied`; denial + reader logs | `@opentelemetry/sdk-node` + `pino` (parent §11) | 8.7d (BFF + scoping), 8.7e (console) |
| **apiserver (Go)** | `buildbrowser.read.source` span; A2A read-verb propagation (`traceparent`); reader launch metrics/logs | `go.opentelemetry.io/otel` + `slog` | 8.7b (live/shim), 8.7d, 8.7f (RO reader) |
| **operator (Go)** | `snapshot.emit.*` metrics + logs at Collecting; persists Run `trace_id` onto artifact `meta` (for §1.2 span link) | otel-go | 8.7c (snapshot emit) |
| **git read-model svc** | span attrs on projection (`truncated`/`too_large`/`file_count`); no new transport | otel-go | 8.7a (foundation) |

The **8.7a foundation** (pure git projection, no cluster) needs only span attributes; metrics/alerts
land with **8.7c** (snapshot emit) and **8.7d/f** (BFF + reader) — instrumentation phases with the
feature, no big-bang.

---

## 9. Signal-to-component matrix (append to parent Appendix A)

| Component | Metrics | Traces | Logs / Audit | Alert |
|-----------|---------|--------|--------------|-------|
| Build browser — read surface (design §3–§5) | §2.1 | `buildbrowser.*` span (child on live / **linked** on completed §1.2) | scope-denial WARN (id-only) | read availability/latency, scope-denial spike |
| Build browser — snapshot emit (design §4.2/§6.1) | §2.2 | emit span at Collecting | emit-failure ERROR | **"no build view" coverage** + emit-failure |
| Build browser — RO-reader pod (design §4.2) | §2.3 + `k8s.pod.*` (spine §11) | reader-launch span | reader lifecycle INFO | RO-reader launch-rate **cost** |

---

## 10. Handoffs

### → Developer (Amelia) — implementation stories (fold into Epic 8.7)
- **OBS-BB1 (8.7a):** span attributes on the git read-model projection (`truncated`/`too_large`/
  `file_count`/`bytes_returned` as magnitudes only).
- **OBS-BB2 (8.7c):** operator emits `snapshot.emit.*` + `snapshot.bytes`/`.file_count` at Collecting;
  persist Run `trace_id` on the artifact `meta` for the §1.2 completed-Run span link.
- **OBS-BB3 (8.7b/8.7d):** BFF/apiserver read spans + `read.*`/`scope.denied` metrics; `traceparent`
  propagation over the A2A read verb; provenanced id-only denial logs.
- **OBS-BB4 (8.7f, flagged):** RO-reader launch/active/ttl metrics + lifecycle logs.
- **OBS-BB5 (CI):** the two §7 enforcement gates (allowlist extension + NFR-OBS3 firewall check).
- **Standing law:** never put `run.id`/`work_item.id`/`principal.id`/`path`/`bytes_returned` on a metric
  label; never log file content or diff bodies.

### → Testing Architect — validation KPIs
- **Build-view coverage KPI:** every completed successful Run in the test corpus has a `build-snapshot`
  artifact → the "no build view" SLO is asserted, not assumed. A negative case (emit forced to skip)
  must trip the coverage alert.
- **NFR-OBS3 assertion:** the firewall CI gate is green **and** a red-team test that adds a
  `ksquad.buildbrowser.*` series to the consumption allowlist must fail the build.
- **S4 tie (NFR-SEC5):** the blast-radius scoping suite asserts a cross-principal read emits
  `scope.denied` + a provenanced id-only WARN and returns 404 — telemetry is part of the security gate,
  not just the response code.

### → Architect (Winston) / Story Writer
- No new architectural decision; this operationalizes ADR-021 (§9.4) telemetry under the §17.2 spine
  and the NFR-OBS3 / OQ14 provenance boundary (ADR-020). Ready to slice into Epic 8.7 alongside the
  design doc.

---

## 11. Disposition

Turns design §7 into concrete metrics (`ksquad.buildbrowser.*`, §2), traces (§1, with the live/completed
attachment correction), logs (§3), and alerts/SLOs (§4) — all inside the NFR-OBS3 firewall (§0/§7) and
aligned to the arch §17.2 metering spine + parent §04 plan. Ready for Story-Writer/Dev pickup in
Epic 8.7 and for Testing-Architect KPI wiring.
