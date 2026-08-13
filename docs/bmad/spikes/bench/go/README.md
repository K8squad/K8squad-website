# ISI-2347 — Go `TestSpine` chaos suite (C1–C7): staged, drop-in-ready

**Status: BLOCKED on the Go coordination spine landing.** This directory holds the
turnkey Go translation of the language-neutral falsification anchor
(`../chaos-harness.py` + `../claim-nodouble-check.py`, Story 2.7 / ISI-2197, green)
so that the moment the Epic 2/3 spine lands (`pkg/coord` **or** `internal/coord`),
wiring up the required gate is a rename + one adapter, not a from-scratch build.

## Why this is staged here and not in `k8squad`

`k8squad/.github/workflows/spine-chaos.yml` has a **skeleton guard**:

```yaml
if [ ! -d pkg/coord ] && [ ! -d internal/coord ]; then present=false ...
```

While both dirs are absent the gate **self-skips** (correct — it is wired before
the code so unrelated PRs are not red-flagged). Verified 2026-08-13: neither
`pkg/coord` nor `internal/coord` exists on **any** branch of `k8squad`; `pkg/`
holds only `auth`. **Dropping a `*_test.go` under `pkg/coord/` now would create
that directory, flip the guard to `present=true`, and the gate would try to
compile `TestSpine` against a package that does not exist → CI red.** So the file
is parked here as `spine_chaos_test.go.stage` — no Go tooling touches it, and it
stays clear of the guard until the spine is real.

## Drop-in procedure (only once the spine lands)

1. Confirm the spine exists: `pkg/coord` or `internal/coord` with the claim /
   lease / fencing / reconcile statements (Epic 2: 2.2 claim, 2.3 renew, 2.4
   reclaim, 2.5 outbox, 2.6 reconcile; Epic 3 reconciler).
2. `spine_chaos_test.go.stage` → rename to `spine_chaos_test.go`, place in
   `internal/coord/` (or `pkg/coord/`), package `coord_test`.
3. Implement **`newSUT`** (bottom of the file) against the real coord API. The
   `SUT` interface **is the contract** the spine must satisfy for the gate — adapt
   the adapter, never the case logic. Also expose `DB() *sql.DB` (used by `sutDB`
   for open-item polling and the differential teeth arms).
4. Pin the `database/sql` driver import to the module's driver (the stage uses
   `github.com/jackc/pgx/v5/stdlib`).
5. Close the **CI wiring gap** below.
6. Run locally against a throwaway PG:
   `DATABASE_URL=postgres://… go test -race -tags=chaos -run TestSpine ./internal/coord/... -v`

## CI wiring gap to close (flagged, not yet done)

`spine-chaos.yml` stands up kind + CNPG Postgres but its **"Run chaos suite" step
does not export `DATABASE_URL`** to the Go test. Under `-tags=chaos` a missing
`DATABASE_URL` is a **FATAL** in `dsnOrFatal` (a required gate must fail loud, not
skip silently — AC1). Before first green, wire the CNPG service DSN into that
step's `env:`. This is intentionally strict: silent-skip = false green on the one
correctness-critical subsystem.

## Case ↔ scenario ↔ invariant map

| Case | Source scenario | Invariant | §ref / AC |
|------|-----------------|-----------|-----------|
| **C1** no double-claim | `claim-nodouble-check.py` (A teeth / B hold) | at-most-one-holder under contention | §6.2 / AC2 |
| **C2** SKIP-LOCKED fan-out distinct | `claim-nodouble-check.py` | no lost work, distinct assignment | §6.2 / AC2 |
| **C3** crash-mid-claim reclaim | `chaos-harness.py` (b) | live lease not reclaimable; expired reclaimed, fence bumped | §6.3 / AC3 |
| **C4** stale-holder write/renew rejected | `chaos-harness.py` (c) | zombie fenced write + renew rejected; live-fence accepted | §6.3 / AC4 |
| **C5** zombie-writer-vs-PVC (**NEW, Go-only**) | — (live kind + PG) | fence-**before**-release ordering closes the survivor window | §6.3 / AC6 |
| **C6** double-dispatch dedup | `chaos-harness.py` (d) | re-driven external dispatch returns same task id | §6.4 / AC5 |
| **C7** re-entrant claim/complete no-op | `chaos-harness.py` (d) | re-drive is a no-op; fence stable; no double-advance | §6.4 / AC5 |

## Differential discipline (preserved 1:1 from the anchor)

Every case first proves the **broken** variant breaks, then the real statement
holds — else a PASS proves nothing. The teeth arms run the broken statement as
**raw SQL against the same `claim`/`work_item` tables** (Story 2.1 schema), so they
bite the real schema, not a toy model:

- **C1** teeth: `naiveClaimTxn` — pick open row with **no** `FOR UPDATE SKIP
  LOCKED` and **no** CAS guard → double-claims under contention.
- **C3 / C7** teeth: `naiveUnguardedAcquire` — acquire with the holder/lease guard
  removed → steals a live lease / bumps a live fence.
- **C4** teeth: `naiveUnfencedComplete` — complete without `AND
  fence_token=:myFence` → the zombie write lands.
- **C5** teeth: `naiveReleaseBeforeFenceWindowExists` — the **inverted** order
  (release/bump fence, stamp `reclaim_fenced_at` after) leaves a survivor window;
  C5 then proves the real fence-before-release order closes it.

`-race` is load-bearing (AC1): a claim/lease data race fails the gate too.

## C5 note (why it's new and Go-only)

C5 is the one case the in-process Python model **cannot** express (AC6): it needs
the live resource layer + Postgres. The stage asserts the §6.3 reclaim **protocol
order** — the holder is fenced (`reclaim_fenced_at` stamped; pod-kill/cordon at the
resource layer) **strictly before** the §6.2 release that bumps the fence — via a
`reclaim_fenced_at` marker on `claim`. When the spine's reclaim path performs the
actual pod-kill/cordon, extend `ReclaimFenced` and C5 to assert the resource-layer
fence (e.g. the pod is gone / cordoned) in addition to the DB marker.
