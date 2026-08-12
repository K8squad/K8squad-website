# Story 8.7d: Build-browser BFF endpoints + per-principal scoping gate (NFR-SEC5)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **⛔ THIS IS THE NFR-SEC5 BLOCKING SECURITY GATE.** Nothing ships to the console (8.7e) until the S4
> cross-principal read-authZ case passes. The visibility model is **per-principal, not Team-legible**
> (pinned by Architect Winston, ISI-2166 / arch r15). Read every acceptance criterion literally — a
> `403` where a `404` is required, or a same-Team read that returns `200`, is a **security regression**,
> not a cosmetic bug.

## Story

As the **operator console's edge (BFF)**,
I want **GET-only build-browser endpoints that authorize every read against the caller's principal + Team scope *before* any git/shim/reader call, denying with `404` whenever the caller is not the Run's owning principal**,
so that **the raw worktree content a Run produces — which may contain that principal's BYO secrets — is never legible to any other principal, including a principal in the same Team/Project (NFR-SEC5).**

## Context & prerequisites (read first)

- **Design contract:** `docs/bmad/design/build-browser-component-design.md` — §3 (API surface), §5 (per-principal scoping, the security crux), §8 AC3 + AC7 (runnable authZ check), §9 (story slicing). This story implements the **8.7d** slice.
- **Architecture:** `docs/bmad/03-architecture.md` §9.4 (workspace/worktree read model + owning-principal gate), §13 (Next.js BFF → Go apiserver, one authorization choke point), §11 (BYO-per-principal credentials + metering principal), §12.1 (Team-namespace tenancy).
- **Testing:** `docs/bmad/05-testing-strategy.md` §6.5 (S4 blast-radius suite — the new cross-principal-same-Team read-authZ row this story must make pass).
- **Depends on (must be landable/mergeable before this story is done):**
  - **8.7a** — pure git read-model (`tree`/`diff`/`file` over a worktree). This story calls it; do **not** reimplement it.
  - **8.7b** — live path (read-only A2A verb on the Run's shim).
  - **8.7c** — completed path (build-snapshot `coord.artifact` + reader).
  - 8.7b/8.7c are the two backends the endpoints dispatch to based on the Run's `live` state. If either is not yet merged, stub its call behind the same interface and mark the corresponding integration test `skip` with a `TODO(8.7x)` — but the **authZ gate itself (the deliverable of this story) does not depend on them** and must be fully implemented and tested.
- **Blocks:** **8.7e** (console three-pane surface). 8.7e must not ship until this story's S4 case is green.

## Acceptance Criteria

**AC1 — GET-only surface, four endpoints.**
Given the build-browser API, When it is deployed, Then exactly these four routes exist and accept **only** `GET`:
```
GET /api/runs/{runId}/build/tree
GET /api/runs/{runId}/build/diff?path=<path>
GET /api/runs/{runId}/build/file?path=<path>&ref=run|base
GET /api/runs/{runId}/build/meta
```
And any mutating verb (`POST`/`PUT`/`PATCH`/`DELETE`) on any of them returns `405` (or the route simply does not exist) — a mutating verb is **structurally absent**, not merely rejected by a guard.

**AC2 — authorize before any backend call.**
Given any of the four endpoints, When it is called, Then the handler resolves `caller.principal` + `caller.teamScope` (from the authenticated session, §13) and evaluates the `authorizeRead(caller, run)` gate **before** issuing any git command, any shim A2A read query (8.7b), or any snapshot/reader call (8.7c). And on `deny`, **no** backend call is made (verify via a backend spy/mock that records zero invocations on the deny path).

**AC3 — per-principal deny, existence-hiding (the security crux, ISI-2166).**
Given principals **A** and **B** in the **same Team/Project**, and a Run owned by A (`Run.owningPrincipal == A`), When **B** calls any of `tree`/`diff`/`file`/`meta` for A's `runId`, Then every endpoint returns **`404`** (not `403` — do not confirm the Run exists). And the deny reason is `Run.owningPrincipal != caller.principal` — the same-Team, non-owner case. **Positive control:** when **A** (the owner) calls the same endpoints, Then they return `200` with the expected payload.

**AC4 — the gate checks BOTH conditions; either failure → 404.**
Given the `authorizeRead(caller, run)` predicate, When it evaluates, Then it authorizes **allow** only if **both**:
(a) `run` is within `caller.teamScope`, **AND**
(b) `run.owningPrincipal == caller.principal`.
And if **either** is false → **`deny(404)`**. And a cross-Team caller (Run outside the caller's Team scope) → `404`. And a same-Team non-owner → `404`. And the owner in-scope → `allow`.

**AC5 — `Run.owningPrincipal` is the already-recorded principal (no new field).**
Given the Run record, When the gate reads the owning principal, Then it reads the **existing** initiating-principal identity already persisted for BYO-credential scope + per-principal metering attribution (§11, arch §9.4) — **no new schema field, no migration**. The gate is purely an authZ **read** of existing state.

**AC6 — runnable authZ-predicate unit test (design §8 AC7 / I4 closure).**
Given the pure predicate `authorizeRead(caller, run) → allow | deny(404)`, When a self-contained unit test (no cluster, no Postgres, no network) exercises it, Then it asserts all three rows:
| caller | run.owningPrincipal | same Team? | expected |
|--------|--------------------|-----------|----------|
| principal A | A | yes | **allow** |
| principal B | A | yes | **deny(404)** |
| principal C | A | no (cross-Team) | **deny(404)** |
And the test lives next to the read-model / gate implementation and fails if the predicate logic breaks.

**AC7 — S4 live-BFF cross-principal read-authZ case (NFR-SEC5).**
Given the live BFF and two same-Team principals A (owner) and B (non-owner), When the S4 blast-radius suite (`05-testing-strategy.md` §6.5, the "cross-principal same-Team read-authZ" row) runs, Then B → `404` on all four endpoints, cross-Team → `404`, and the **positive control** owner A → `200`. This is the row that certifies the NFR-SEC5 gate over the real edge (not just the pure predicate).

**AC8 — every layer fails closed.**
Given the layered enforcement (design §5), When any single layer is bypassed in a test, Then the read still fails closed: (i) the BFF gate denies with `404`; (ii) the Team-namespace NetworkPolicy/RBAC denies cross-namespace read independently of the BFF; (iii) the per-principal cache partition prevents shared-workspace residue leak. Note: layers (ii) and (iii) are **defense-in-depth** — they do **not** cover the git tree/diff/file read path on their own; **the owning-principal check in layer (i) is the mechanism** that denies same-Team B. Do not rely on the cache partition as the read gate.

**AC9 — no mutating verb; path traversal structurally rejected.**
Given `path` inputs, When `diff`/`file` resolve a path, Then `../`, absolute paths, and symlink-escape are rejected **structurally** — paths are validated against the Run's changed set and resolved through `git show` / `git cat-file` (never raw FS `open`), so escape out of the worktree tree object is impossible, not merely filtered. (This behavior is delivered by 8.7a; this story asserts the endpoints preserve it end-to-end and never introduce a raw-FS path.)

**AC10 — read-surface observability (OBS-BB3, BFF slice — ISI-2168 / plan ISI-2165 §1–§3).**
Given any served read on the four endpoints, When it completes, Then the BFF emits:
- a root span `buildbrowser.<endpoint>` (`endpoint ∈ tree|diff|file|meta`) carrying the plan §1.1 span attributes as **span-only** values — `ksquad.run.id`, `ksquad.work_item.id`, `ksquad.buildbrowser.{endpoint,live,source,cache_hit,bytes_returned,truncated,too_large,path,outcome}` (`bytes_returned`/`path` are **span/log only, never a metric label**; `path` is **filename only, never content**);
- the metrics `ksquad.buildbrowser.read.total{endpoint,live,source,cache_hit,outcome}` (counter), `.read.duration{endpoint,source}` (histogram), `.bytes_returned{endpoint,source}` (**histogram, not a sum**), and `.scope.denied{endpoint}` (counter) — **bounded enum labels only**.
And **trace attachment** follows the live/completed split (plan §1.2): a **live** read (`live:true`) propagates W3C `traceparent` over the A2A read verb (8.7b) so the read span is a **true child of the Run trace**; a **completed** read (`live:false`) opens a **BFF-rooted trace with an OTel span *link*** back to the Run's original `trace_id` read from the snapshot `coord.artifact.meta` (persisted by 8.7c / OBS-BB2). And a **`deny`** (AC3) increments `scope.denied{endpoint}` and writes a **provenanced id-only `WARN`** log `{run.id, principal.id, endpoint, outcome:denied}` that **never confirms Run existence** in any client-visible surface — the log carries the id for the S4 audit + enumeration detection (plan §3), the response stays `404`.

**AC11 — NFR-OBS3 standing law (AC on every OBS-touched 8.7 story).**
Given any `ksquad.buildbrowser.*` instrument this story emits, When telemetry is produced, Then **all** hold: (a) `run.id`/`work_item.id`/`principal.id`/`path`/`bytes_returned` are **never** a **metric label** (span/log/exemplar only); (b) file **content** and diff **bodies** are **never** placed in any signal — only magnitudes, status, and filename-only paths; (c) **no `model` label** on any build-browser instrument; (d) `bytes_returned` is a **histogram, not a monotonic sum**. Read volume is **legibility telemetry, never a consumption / billing axis** (plan §0, §7). Verified by the OBS-BB5 CI gates (Epic 14); this story must not emit anything that would trip them.

## Tasks / Subtasks

- [ ] **Task 1 — Pure authZ predicate `authorizeRead(caller, run)` (AC4, AC5, AC6).** *Do this first — it is the security core and needs no backend.*
  - [ ] Define `caller` = `{ principal, teamScope }` and the minimal `run` view = `{ runId, teamId, owningPrincipal }` (read the **existing** owning-principal field; do not add one).
  - [ ] Implement the predicate: `allow` iff `run.teamId ∈ caller.teamScope` **AND** `run.owningPrincipal == caller.principal`; otherwise `deny` mapped to HTTP `404`. Return a typed decision (`allow` | `deny`) plus an internal-only reason enum (`out-of-team-scope` | `not-owner`) for logging — **never** leak the reason to the client body (existence-hiding).
  - [ ] Co-locate the predicate with the read-model / build handler package so it ships with the code it guards (design §8 AC7).
  - [ ] Write the runnable unit test (AC6 table): owner→allow, same-Team non-owner→deny(404), cross-Team→deny(404). No cluster, no DB, no network.
- [ ] **Task 2 — Wire the gate into all four endpoints, before any backend call (AC1, AC2).**
  - [ ] Add a single shared authorization middleware/guard invoked by `tree`/`diff`/`file`/`meta` that: resolves `caller` from the authenticated session (§13), loads the Run's `{teamId, owningPrincipal}`, runs `authorizeRead`, and on `deny` returns `404` **immediately** — no git/shim/reader/snapshot call.
  - [ ] Ensure the Run lookup itself does not leak existence (a `deny` and a genuinely-missing `runId` are **indistinguishable** to the client — both `404`, same body/shape).
  - [ ] Confirm only `GET` is routed; assert mutating verbs are absent/`405` (AC1).
- [ ] **Task 3 — Dispatch to live vs completed backend after allow (AC2 integration).**
  - [ ] On `allow`, branch on the Run's `live` flag: live → 8.7b shim A2A read verb; completed → 8.7c snapshot artifact (reader is the flagged 8.7f fallback, out of scope here).
  - [ ] Map backend results to the design §3 response shapes (`tree`/`diff`/`file`/`meta`), preserving the `truncated`/`tooLarge`/`binary` caps from 8.7a (do not re-cap; pass through).
  - [ ] If 8.7b or 8.7c is not yet merged, stub behind the interface and `skip` its integration test with `TODO(8.7b|8.7c)` — the **authZ tests must not be skipped**.
- [ ] **Task 4 — Path & verb safety end-to-end (AC9).**
  - [ ] Assert `diff`/`file` never call raw FS `open`; all path resolution flows through the 8.7a git-backed read model.
  - [ ] Add negative tests: `path=../..`, absolute path, and a symlink-escape path → rejected (existence-hiding `404`/`400` per 8.7a contract), never a file outside the worktree.
- [ ] **Task 5 — S4 live-BFF case (AC7, AC8).**
  - [ ] Add the `05-testing-strategy.md` §6.5 **cross-principal same-Team read-authZ** case to the S4 blast-radius suite: seed a Run owned by A; drive B (same Team, non-owner) against all four endpoints → assert `404`; drive a cross-Team caller → `404`; **positive control** owner A → `200`.
  - [ ] Tag it `NFR-SEC5` so the L4 security gate (testing §6.5 / §ledger) tracks it.
  - [ ] Add a fail-closed assertion: with the BFF gate stubbed to `allow`, the Team-namespace NetworkPolicy/RBAC still denies a cross-namespace read (documents defense-in-depth; may live as a separate S4 sub-case).
- [ ] **Task 6 — Read-surface observability (OBS-BB3 BFF slice — AC10, AC11; plan ISI-2165 §1–§3, §8 BFF row).**
  - [ ] Emit the root span `buildbrowser.<endpoint>` with the plan §1.1 **span-only** attributes (`ksquad.run.id`, `ksquad.work_item.id`, `ksquad.buildbrowser.{endpoint,live,source,cache_hit,bytes_returned,truncated,too_large,path,outcome}`). `bytes_returned`/`path` are span/log only — **never** a metric label; `path` is filename-only, never content.
  - [ ] Emit the metrics `ksquad.buildbrowser.read.total{endpoint,live,source,cache_hit,outcome}` (counter), `.read.duration{endpoint,source}` (histogram), `.bytes_returned{endpoint,source}` (**histogram, not a sum**), `.scope.denied{endpoint}` (counter) — bounded enum labels only.
  - [ ] Trace attachment (plan §1.2): live (`live:true`) → propagate `traceparent` over the 8.7b A2A read verb so the read span is a child of the Run trace; completed (`live:false`) → BFF-rooted trace + OTel span **link** to the Run `trace_id` read from the snapshot `coord.artifact.meta` (persisted by 8.7c). If 8.7b/8.7c are stubbed, wire the attachment behind the same interface and `skip` the link/child integration assertion with `TODO(8.7b|8.7c)`.
  - [ ] On `deny` (AC3): increment `scope.denied{endpoint}` and write a provenanced **id-only `WARN`** `{run.id, principal.id, endpoint, outcome:denied}` — the response body still `404`, never confirming existence.
  - [ ] **Standing-law self-check (AC11):** no `model` label, no `principal.id`/`run.id`/`work_item.id`/`path`/`bytes_returned` on any metric label, no file content/diff bodies in any signal, `bytes_returned` stays a histogram. The OBS-BB5 CI gates (Epic 14) will fail the build otherwise — do not treat read volume as a consumption axis.

## Dev Notes

- **Enforcement location & source of truth.** §13 mandates **one authorization choke point and one source of truth** (BFF → Go apiserver; the browser never touches kube/Postgres directly). Recommended split: the **pure `authorizeRead` predicate + Run `{teamId, owningPrincipal}` load is authoritative in the Go apiserver read-model package** (single source of truth); the **Next.js BFF endpoints propagate the authenticated caller principal + Team scope and surface the apiserver's `404` verbatim**. Enforcing the predicate authoritatively server-side (Go) — not only in the BFF/TS layer — keeps the choke point honest even if the BFF is compromised (design §5 layer 4: a compromised BFF still cannot read another principal's worktree). If you instead enforce primarily in the BFF, the apiserver **must still** independently gate (never trust a BFF-asserted principal for the owning-principal check). **Flag to Architect (Winston) if the split needs pinning** — see Questions.
- **404, never 403.** This is existence-hiding, a deliberate security property (design §5.1, AC3). A `403` confirms the Run exists to a non-owner and leaks the per-principal boundary. Deny and not-found must be **indistinguishable** to the client.
- **`Run.owningPrincipal` already exists.** It is the initiating-principal identity recorded for BYO-credential scope + per-principal metering (§11, arch §9.4). No new field, no migration. If you cannot find where it is persisted, that is a real gap — raise it, do **not** invent a new field silently.
- **Do not rebuild the read model or the diff engine.** 8.7a owns git projection (`git diff --name-status`, `git diff <base>...<runRef>`, `git show <runRef>:<path>`), the `tooLarge`/`truncated`/`binary` caps (512 KiB / 2 MiB / 5 000 entries), and structural path safety. This story **calls** it and preserves its guarantees — it does not reimplement any of it (design §2, §3).
- **Cache partition is NOT the read gate.** The per-principal cache partition (arch §9.4) is defense-in-depth against residue/poisoning; it does **not** cover the git tree/diff/file read path. The **owning-principal check is the mechanism** that denies same-Team B. Reviewers have flagged this exact conflation (F7/B1) — do not repeat it.
- **Team scope is the outer bound, not the gate.** Same-Team is necessary but **not sufficient**; owning-principal equality is the sufficient condition. Both must hold.

### Project Structure Notes

- **Repo shape (current):** Go monorepo; only `internal/discussion/*` + `migrations/` exist so far (the discussion-room slice, ISI-2147). The Go apiserver read-model for the build browser is greenfield — create it under `internal/` following the `internal/discussion` package pattern (`handler.go`, `store.go`, `*_test.go`). Suggested: `internal/buildbrowser/` (handler + `authorize.go` for the pure predicate + `authorize_test.go` for AC6).
- **BFF:** the Next.js/TypeScript console app (§13, ADR-013) is **not yet in the repo**. If it does not exist when you start, the BFF-side route wiring is a thin proxy that can land in the same story or be stubbed with a `TODO` — but the **authoritative Go apiserver gate + AC6 predicate test + AC7 S4 case are the non-negotiable deliverables of this story** and must land here regardless of BFF readiness.
- **Naming:** match `internal/discussion` conventions (lowercase package, `store`/`handler` split, table-driven `_test.go`). Do not introduce a new test framework — use Go's standard `testing` + whatever assertion helper `internal/discussion/store_test.go` already uses.

### References

- [Source: docs/bmad/design/build-browser-component-design.md#5 Per-principal scoping — the security crux] — Layer-1 gate `Run.owningPrincipal == caller.principal`, 404 existence-hiding, layers 1–4 fail-closed.
- [Source: docs/bmad/design/build-browser-component-design.md#8 Acceptance criteria] — AC3 (per-principal 404), AC7 (runnable authZ predicate: owner→allow, same-Team non-owner→deny(404), cross-Team→deny(404)).
- [Source: docs/bmad/design/build-browser-component-design.md#3 Read API surface] — the four GET endpoints + response shapes + limits.
- [Source: docs/bmad/design/build-browser-component-design.md#9 Story slicing hint] — 8.7d = BFF endpoints + per-principal scoping gate; deps 8.7b/8.7c; chain `8.7a → {8.7b,8.7c} → 8.7d → 8.7e`.
- [Source: docs/bmad/03-architecture.md#9.4 Workspace & concurrency] — owning-principal gate (arch r15/ISI-2166), cache partition is residue-only defense-in-depth, not the read gate.
- [Source: docs/bmad/03-architecture.md#13 Operator Console — Node Frontend Approach] — Next.js BFF → Go apiserver, one authorization choke point, one source of truth.
- [Source: docs/bmad/03-architecture.md#11] — BYO-per-principal credentials + per-principal metering principal (= `Run.owningPrincipal`, no new field).
- [Source: docs/bmad/05-testing-strategy.md#6.5 Blast-radius / NetworkPolicy validation (S4)] — the cross-principal same-Team read-authZ row (NFR-SEC5); B→404, cross-Team→404, owner→200 positive control.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.7 row 8.7d] — epic-level AC + the ⛔ NFR-SEC5 blocking-gate note; deps 8.7b, 8.7c.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8.7 observability fold-in (ISI-2168)] — OBS-BB slice→story map + the ⛔ NFR-OBS3 Standing law (AC on every touched story).
- [Source: docs/bmad/design/build-browser-observability-plan.md §1–§3, §7, §8] — read spans + `read.*`/`scope.denied` metrics (OBS-BB3), live/completed trace attachment (§1.2), provenanced id-only denial logs (§3), NFR-OBS3 firewall + CI gates (§7).

### Open questions (for the dev agent to resolve with the named owner — do not block the security core on these)

1. **Enforcement split (Architect / Winston).** Is the authoritative `authorizeRead` gate in the Go apiserver read-model (recommended, keeps §13 "one source of truth") with the BFF as a principal-propagating proxy, or is the BFF the primary gate with the apiserver as a second independent check? Either way the apiserver must independently gate; confirm the pinning. *This does not block Task 1 (the pure predicate) or its test — implement those regardless.*
2. **BFF app bootstrap (Architect / PM).** If the Next.js console app is not yet scaffolded when 8.7d starts, confirm whether the BFF route layer lands here or in 8.7e. The Go-side gate + AC6 + AC7 land here in all cases.

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
