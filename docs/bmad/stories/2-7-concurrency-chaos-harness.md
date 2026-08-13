# Story 2.7: Concurrency / chaos test harness — the REQUIRED CI gate for the spine

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🚦 THIS STORY IS A REQUIRED CI GATE, NOT AN OPTIONAL SUITE.** Epic 2 does **not** close until this
> gate is green on a real Postgres. The coordination spine (claim / lease / fencing / reconcile) is the
> single correctness-critical subsystem (PRD R10, arch §6, §15): *concurrency is tested, not assumed.* A
> spine change that lands without this suite passing is a **process failure**. The suite fails the build
> — it does not warn.

## Story

As **the platform maintainer merging any change that touches the coordination spine**,
I want **a required CI gate that adversarially exercises parallel claim, crash-mid-claim reclaim,
stale-holder fenced writes, and idempotent reconcile against a real Postgres**,
so that **no interleaving, crash, GC-pause, or re-drive can double-claim an item, resurrect a zombie
writer, or double-apply an external effect — proven on every PR, not assumed (R10, FR-B2, NFR-REL1).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-B2** (at-most-one-holder), **R10** (spine is the correctness-critical
  risk; *"concurrency is tested, not assumed"* — this story is that test).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§6.2** — the claim SQL (`FOR UPDATE SKIP LOCKED` pop → conditional fence-bump acquire → `state='claimed'`).
  - **§6.3** — lease / liveness / fencing: bounded lease, renew-on-heartbeat, reclaim by the exact `WHERE
    holder IS NULL OR lease_expires_at < now()` guard, **fence-before-release** reclaim protocol, and the
    every-mutation `… AND fence_token = :myFence` guard that rejects a zombie writer.
  - **§6.4** — reconcile-safe re-entrancy: re-read claim+fence, never re-drive an item you already hold;
    durable dispatch marker for external effects; conditional `… WHERE status = :expected` transitions.
- **Depends on:** the whole Epic-2 spine — **2.1** (schema), **2.2** (claim), **2.3** (renew), **2.4**
  (reclaim + pod-fence), **2.5** (outbox), **2.6** (reconcile-safe). The **model + real-PG SQL** arm of
  this harness runs **now** (it drives the §6.2/§6.3/§6.4 statements directly); the **Go `TestSpine`** arm
  runs once `pkg/coord`/`internal/coord` land (the gate skips itself until then — see "CI wiring").
- **Consumes / promotes:** Story 2.2's `claim-nodouble-check.py` — the no-double-claim falsification — is
  wrapped here as scenario (a) so the whole gate is one command.

## The four scenarios (issue text) ↔ named CI cases (Epic 14.2 C1–C7)

The originating issue names four scenarios (a)–(d); the promoted CI suite (`spine-chaos.yml`) names seven
cases C1–C7. They are the same invariants at finer grain:

| Issue | CI case | Invariant | Proven by |
|-------|---------|-----------|-----------|
| **(a)** parallel claimers | **C1** no double-claim · **C2** work-pull fan-out (SKIP LOCKED distinct, no lost work) | at-most-one-holder under contention (§6.2, AC3) | `claim-nodouble-check.py` (model + real-PG), 200 items × 32 claimers, differential |
| **(b)** crash-mid-claim | **C3** reclaim after lease expiry, `fence_token` bump | a live lease is **not** reclaimable; an expired one is, with a bumped fence (§6.3) | `chaos-harness.py` scenario (b) (model + real-PG) |
| **(c)** stale-holder completion | **C4** stale-holder write rejection / renew no-op | a woken zombie's fenced write / renew is **rejected** (`… AND fence_token=:myFence`, §6.3) | `chaos-harness.py` scenario (c) (model + real-PG) |
| **(d)** idempotent reconcile | **C6** double-dispatch dedup · **C7** re-entrant claim/complete | re-drive of claim / complete / external dispatch is a **no-op** (§6.4) | `chaos-harness.py` scenario (d) (model + real-PG) |
| — | **C5** zombie-writer-vs-PVC (**fence-before-release**) | pod-kill/PVC-detach ordering fences the holder **before** the claim releases (§6.3 reclaim protocol) | **Go `TestSpine` only** — a live-kind + Postgres scenario the model cannot represent (see AC5) |

## Runnable harness (already green — the falsification anchor)

`docs/bmad/spikes/bench/chaos-harness.py` — stdlib-only, `python3` it directly:

```
[a] parallel claimers — no double-claim (delegates to Story 2.2 check) … PASS
[b] crash-mid-claim — reclaim after lease expiry (§6.3) … PASS  (live lease not reclaimable; expired 1->2)
[c] stale-holder completion — fenced write rejected (§6.3) … PASS
[d] idempotent reconcile — re-entrant claim/complete/dispatch safe (§6.4) … PASS
OK — concurrency/chaos harness passed (a,b,c,d).
```

- **Every scenario is *differential*** (the same discipline as Story 2.2): each first proves the *broken*
  variant breaks — an unguarded reclaim steals a live lease (b); an unfenced write lands the zombie
  completion (c); an unconditional re-acquire bumps the fence, a guardless complete double-advances (d) —
  **then** proves the real §6.2/§6.3/§6.4 statement holds. A happy-path "it worked once" demo can pass with
  a broken design under a lucky interleaving; proving the harness can *catch* the failure first is what
  makes each PASS mean something.
- **Two backends, same as 2.2:** the **model** (in-process, virtual clock for deterministic lease expiry,
  zero deps) is authoritative for the *logic*; set **`DATABASE_URL`** (+ psycopg) and the (b)/(c)/(d) SQL
  runs against a **real Postgres** with a 1-second lease so expiry is exercised in real time. Scenario (a)
  carries the parallelism (real threads); (b)/(c)/(d) are adversarial *orderings* under a controlled
  clock — deterministic on purpose, because **a required gate must not be flaky**.

## Acceptance Criteria

**AC1 — the gate is required and fails the build (not optional, not a warning).**
Given a PR that touches the spine (`cmd/apiserver/**`, `pkg/coord/**`, `internal/coord/**`, or the
workflow itself), When CI runs, Then `spine-chaos.yml` runs and its result is a **required status check**:
a failing case **blocks merge**. And the suite runs `go test -race` (data-race detector on) so a claim/lease
data race fails the gate too. And it runs nightly on `schedule` to catch flakes the PR path masks.

**AC2 — (a)/C1/C2: no double-claim, no lost work, under real contention.**
Given N open items and M concurrent claimers against a **real Postgres**, When all claim at once, Then
every item is held by **exactly one** Run, every open item is **eventually** claimed (SKIP LOCKED skips
*contended* rows, never *loses* them), and each `(work_item_id, fence_token)` is unique. Proven by
`claim-nodouble-check.py` (wrapped as scenario (a)); the naive-variant arm must **still double-claim**, or
the gate has lost its teeth and fails loud.

**AC3 — (b)/C3: crash-mid-claim reclaims only after lease expiry, with a bumped fence.**
Given a holder that claims then stops renewing (crash), When another claimer attempts a reclaim, Then
**before** `lease_expires_at` the reclaim is **rejected** (a live lease is not stealable) and **after**
expiry the same §6.2 conditional UPDATE reclaims the item with a **monotonically bumped** `fence_token` —
no operator action, no stuck lease. And the crashed holder can **no longer renew** (its lease lapsed).

**AC4 — (c)/C4: a stale holder's fenced write and renew are rejected.**
Given a holder whose item was reclaimed while it was paused (a stale `fence_token`), When it wakes and
attempts a state-mutating write (complete/comment/status) or a renew, Then the `… AND fence_token=:myFence`
guard **rejects** it (zombie-writer race closed), and the **current** holder's write with the live fence is
**accepted**. The differential arm proves an *unfenced* write would have let the zombie completion land.

**AC5 — (d)/C6/C7: reconcile is idempotent (re-entry is a no-op).**
Given a controller that crashes and re-drives a claim / complete / external-effect dispatch, When it
re-enters K times, Then re-reading claim+fence makes the re-drive a **no-op**: the fence is **not** bumped
(a Run holds one live fence per item, §6.4/AC5-of-2.2), `complete` on a `done` item does **not** double-
advance (`… WHERE status='claimed'`), and a re-driven external dispatch returns the **same** recorded task
id (durable marker, no double-dispatch). The differential arm proves the naive re-drive bumps/duplicates.

**AC6 — (C5) fence-before-release is proven at the live layer (Go only).**
Given a lease expires, When the reconciler reclaims, Then it **fences the holder before releasing the
claim** (§6.3 reclaim protocol: pod-kill / cordon / `reclaim_fenced_at` marker → confirm-unfenced → *then*
the §6.2 release that bumps the fence), so even a holder that survived the kill is fenced at the resource
layer. This ordering is a **live-kind + Postgres** scenario that the in-process model **cannot** represent;
it is implemented in the Go `TestSpine` suite (C5) and is part of the required gate once the spine lands.
The model/SQL harness explicitly scopes it out (documented, not silently skipped).

## CI wiring (the gate)

`k8squad/.github/workflows/spine-chaos.yml` — **already in place**. It:
- triggers on spine-path PRs, `push` to `main`, and a nightly `schedule`;
- **skips itself while the spine source is absent** (`pkg/coord`/`internal/coord` not yet created —
  skeleton phase), so it is wired *before* the code lands without red-flagging unrelated PRs;
- once the source lands, stands up a **kind cluster + CNPG Postgres** and runs
  `go test -race -tags=chaos -run 'TestSpine' ./pkg/coord/... ./internal/coord/...`;
- uploads the chaos report artifact.

**What this story delivers vs. what it hands off:**
- **Delivered now (Architect):** this spec, the C1–C7 ↔ (a)–(d) acceptance mapping, and the green
  language-neutral falsification harness (`chaos-harness.py` + `claim-nodouble-check.py`) — model + real-PG
  SQL, which anchors the Go tests (they must reproduce these exact assertions) and lets the invariants be
  falsified **before** the Go spine exists.
- **Handed off (downstream dev):** implement the Go `TestSpine` cases C1–C7 (build tag `chaos`) in
  `pkg/coord`/`internal/coord`, translating each `chaos-harness.py` scenario 1:1 and adding **C5** (the
  live pod-kill/fence-before-release ordering the model can't express). This is gated on the Go spine
  (Epics 2/3) landing — tracked as a child issue with that blocker.

## Out of scope (owned elsewhere)

- The spine *implementations* themselves (claim 2.2, renew 2.3, reclaim 2.4, outbox 2.5, reconcile 2.6).
- Load/latency benchmarking (that is the `claim-latency-bench.sh` / pool-sizing spike, ISI-2292).
- The Go `TestSpine` code (delegated child issue; needs `pkg/coord`).
