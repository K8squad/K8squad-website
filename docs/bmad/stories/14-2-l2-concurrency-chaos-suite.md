# Story 14.2: L2 concurrency/chaos suite [R10 GATE — C1–C7]

Status: done (gate landed on k8squad main; ISI-2200 preflight + workflow fix in PR)

<!-- ISI-2200. Wave-0 gate. Absorbs Story 2.7 (ISI-2197) + F1–F4 (ISI-2135). -->

> **🚦 THIS IS THE WAVE-0 GATE THAT BLOCKS EVERY DOWNSTREAM EPIC.** The L2 suite adversarially
> exercises the coordination spine (claim / lease / fencing / reconcile) against a **real Postgres**
> with the **race detector on**. It is a **REQUIRED status check** — Epic 2 cannot close, and no
> spine-touching change can merge, until **C1–C7 are green**. The suite **fails the build**; it does
> not warn. It also **fails fast** if the shipped schema is missing the fence-token column or the
> unique-active-claim constraint — a spine whose structural guards were never provisioned must never
> go silently green.

## Story

As **the platform maintainer gating every change that touches the coordination spine**,
I want **a required L2 suite that runs the C1–C7 concurrency/chaos cases against real CNPG Postgres
with `-race`, and that fails fast when the fence-token column or the one-active-claim constraint is
absent**,
so that **no interleaving, crash, GC-pause, stale holder, or re-drive can double-claim an item,
resurrect a zombie writer, or double-apply an external effect — proven on every PR, not assumed
(PRD R10, FR-B2, NFR-REL1).**

## Context & prerequisites

- **PRD:** `docs/bmad/02-prd.md` — **FR-B2** (at-most-one-holder), **R10** ("concurrency is tested,
  not assumed" — this story is the Wave-0 realization of that mandate).
- **Architecture:** `docs/bmad/03-architecture.md` — **§6.2** claim SQL (`FOR UPDATE SKIP LOCKED` pop →
  conditional fence-bump acquire → `state='claimed'`), **§6.3** lease / fencing / fence-before-release
  reclaim + the `… AND fence_token = :myFence` zombie-writer guard, **§6.4** reconcile-safe re-entrancy
  and durable dispatch marker.
- **Schema (fail-fast subject):** `db/migrations/0001_coord_schema.sql` (Story 2.1 / ISI-2191) —
  `coord.claim.fence_token bigint NOT NULL` and `coord.claim.work_item_id … PRIMARY KEY` (the
  structural "exactly one claim row per work item", F3).

## Absorption ledger

This story is the canonical L2 gate. It **absorbs**:

- **Story 2.7 / ISI-2197** — the language-neutral falsification anchor
  (`docs/bmad/spikes/bench/chaos-harness.py` + `claim-nodouble-check.py`, all four scenarios green,
  each differential). The Go `TestSpine` suite is a faithful 1:1 translation of that anchor.
- **F1–F4 / ISI-2135** — the four spine failure modes, each pinned to a named case:
  - **F1** zombie-writer-vs-PVC → **C5** (fence-before-release ordering).
  - **F2/F3** stale-holder fencing → **C4** (stale fence write/renew rejected).
  - **F4** double-dispatch → **C6** (idempotent dispatch dedup).

## The C1–C7 cases ↔ failure mode ↔ invariant ↔ spec

| Case | Assertion | Falsification arm (2.7) | Failure mode | Arch |
|------|-----------|-------------------------|--------------|------|
| **C1** | parallel claimers — no double-claim | `claim-nodouble-check.py` (A/B) | — | §6.2 AC2/AC3 |
| **C2** | work-pull fan-out — SKIP-LOCKED distinct, no lost work | `claim-nodouble-check.py` | — | §6.2 |
| **C3** | crash-mid-claim reclaim only after lease expiry + fence bump | `chaos-harness.py` (b) | — | §6.3 AC3 |
| **C4** | stale-holder write / renew rejected | `chaos-harness.py` (c) | **F2/F3** | §6.3 AC4 |
| **C5** | zombie-writer-vs-PVC — fence **before** release | Go-only (live layer) | **F1** | §6.3 AC6 |
| **C6** | double-dispatch dedup — deterministic task id | `chaos-harness.py` (d) | **F4** | §6.4 AC5 |
| **C7** | idempotent reconcile re-entry — no-op when still held | `chaos-harness.py` (d) | — | §6.4 AC5 |

## Acceptance criteria

1. **AC1 — real PG, race on, fail loud.** C1–C7 run via
   `go test -race -tags=chaos -run 'TestSpine' ./pkg/coord/... [./internal/coord/...] -v` against a real
   Postgres. A missing `DATABASE_URL` under `-tags=chaos` is a **FATAL**, never a silent skip
   (`dsnOrFatal`). `-race` is load-bearing: a claim/lease data race fails the gate too.
2. **AC2 — all seven green.** C1–C7 pass; each case is **differential** (a broken variant of the guard
   breaks first, so a PASS proves something).
3. **AC3 — REQUIRED status check.** The suite is a required check on spine-affecting paths
   (`cmd/apiserver/**`, `pkg/coord/**`, `internal/coord/**`, the workflow itself) + nightly. Epic 2
   cannot close until it is green.
4. **AC4 — fail fast on absent schema invariants (ISI-2200 core).** Before running C1–C7 the suite
   applies the **checked-in** `0001_coord_schema.sql` to real PG and FATALs if:
   - `coord.claim.fence_token` is absent, or
   - there is no PRIMARY KEY/UNIQUE on exactly `coord.claim(work_item_id)`.
   Dropping either from the migration flips the gate **RED** — the teeth bite production DDL, not a
   fabricated test schema.

## Implementation (k8squad source repo)

- `pkg/coord/coord.go` — the §6.2/§6.3/§6.4 spine (ISI-2394).
- `pkg/coord/spine_chaos_test.go` — `TestSpine` + C1–C7, `//go:build chaos`, `-race`-ready (ISI-2347).
- `.github/workflows/spine-chaos.yml` — the required gate: `postgres:16` service, `DATABASE_URL`
  exported, self-skips only while no coord package exists.

### What ISI-2200 adds on top of the landed suite

1. **Fail-fast schema preflight** (`schemaPreflightFailFast` in `spine_chaos_test.go`) — runs FIRST,
   before C1, applying the real migration and asserting the fence-token column + the unique-active-claim
   constraint. This closes the blind spot where the inline `freshSchema` fabricated those columns and
   would have gone green against an under-provisioned spine (AC4).
2. **Workflow target-path fix** — the run step resolves test targets from whichever coord dir exists
   (`pkg/coord` / `internal/coord`) instead of hardcoding a non-existent `./internal/coord/...`, which
   was aborting the run with `lstat: no such file or directory [setup failed]` — a false RED that would
   have kept the REQUIRED gate from ever going green.

## Verification evidence

- Local: embedded **PostgreSQL 16**, `go test -race -tags=chaos -run TestSpine` → **all C1–C7 + preflight
  green** (~57s).
- Preflight teeth (mutation of `0001_coord_schema.sql`): remove `fence_token` → RED
  ("shipped coord migration failed to apply … column fence_token does not exist"); demote the
  `coord.claim` PK to a plain column → RED (`ISI-2200 FAIL-FAST: … no unique/primary-key constraint on
  (work_item_id)`). Migration restored; suite green.
- `go build` / `go vet` / `gofmt` clean under `-tags=chaos`.

## Out of scope / owner note

- Marking the check **branch-protection-required** in GitHub settings is a repo-admin action (board /
  maintainer), not something the suite can self-assert. The workflow already scopes itself to
  spine-affecting paths + nightly.
- C5 currently asserts the §6.3 fence-before-release **ordering** via the `reclaim_fenced_at` marker.
  Live pod-kill fidelity (kind + CNPG resource-layer fence) is a follow-up; reintroduce kind+CNPG when
  C5 gains that fidelity (noted in `spine_chaos_test.go` and `spine-chaos.yml`).
