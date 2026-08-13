# Code Review — Story 3.1: Run reconcile state machine (ISI-2346 ← ISI-2201)

**Reviewer:** Amelia (Code Reviewer) · **Date:** 2026-08-13 · **Verdict:** ✅ **APPROVE for dev — with findings** (F1+F2 remediated in-place; F3+F4 filed as follow-up).

Story is a spec/acceptance artifact (ready-for-dev, no Go yet). Review = arch faithfulness + AC internal consistency + whether the falsification actually exercises what the ACs claim. Layers: Blind Hunter (does the machine hold?), Edge Case Hunter (crash windows), Acceptance Auditor (AC↔arch↔check).

## The four flagged decisions — all CONFIRMED sound

1. **Wording reconciliation does NOT reopen r28.** `status.phase` stays the pinned coarse CEL enum (`Pending|Claiming|Running|Paused|Succeeded|Failed|Cancelled`, arch §5.1:309); the issue's `ClaimingSandbox/Dispatching/Collecting` are modeled as durable `reconcile_step` checkpoints + `status.conditions`, **not** new enum values. Spelling `Cancelled` (double-l) matches the §5.1 CEL enum. Checkpoint→phase table (story:41-48) is faithful to §8: `Dispatching = Claiming→Running boundary` matches §6.4:755; `Collecting` under `Running` matches §6.4:764. ✓
2. **AC3 idempotency is pinned as *designed*, not assumed** — mirrors arch §6.4:753 verbatim (deterministic `a2a_task_id=run_id`+shim dedup, content-addressed upsert `UNIQUE(work_item_id,run_id,kind)` §6.1:641, conditional step-advance UPDATE). ✓
3. **AC4 does not make correctness depend on single-writer leader-election** — prose is explicit: "leader-election is availability, fencing is safety" (story:180). See F4 for a precision nit on *which* mechanism covers *which* split-brain shape. ✓
4. **AC6 audit+outbox same-txn** — prose matches §6.5/§6.6. Was prose-only in the check → see F2 (now closed). ✓

## Findings

### F1 (MED, CONFIRMED, **REMEDIATED**) — durable arm never exercised the §6.4 idempotency mechanisms it exists to prove
The falsification's durable reconciler injected crashes **only at phase boundaries** (`reconcile_durable` raised `Crash` *before* `run_phase`), so every phase's external effect committed cleanly before any crash and **no phase was ever re-entered**. Instrumentation across all 5 crash points showed `dispatch_REENTRIES=0, collect_REENTRIES=0`. Consequence: the deterministic-id **dedup** early-return and content-addressed **upsert** — the exact mechanisms AC3 centers on — were **never taken**; the durable arm passed identically with them removed. The check's entire detecting power came from the naive arm's restart-from-pending. Proven: with dedup/upsert crudely disabled the *old* durable check still exited 0.

**Fix (applied):** added `crash_after_effect` to inject a crash at the §6.4 **crux window** (external effect fired, step-advance transaction not yet committed) + `check_durable_intraphase()` covering `dispatching` and `collecting`. Now re-entry re-drives an already-performed effect, so dedup/upsert are load-bearing. Proven to have teeth: neutering dedup → `intraphase@dispatching: 2 agent executions (want 1)`; neutering upsert → `intraphase@collecting: duplicate artifact`. Both fail loud now.

### F2 (MED, **REMEDIATED**) — AC6 (audit + outbox same-txn) was entirely unmodeled
The check had no `audit_log`/`outbox` at all — AC6's crux (audit §6.5 + event §6.6 co-committed in the *same* transaction as the transition; a fenced-out/stale pass writes **neither** → no phantom event, no orphaned transition) had zero coverage.

**Fix (applied):** `DurableStore.advance` now co-writes an audit row + outbox event **inside** the committed branch. `check_durable` asserts (a) exactly one audit + one outbox per committed transition (`== len(STEPS)-1`, no double-audit across failover, no transition without a trail) and (b) the zombie stale-fence pass adds **zero** audit/outbox rows (no phantom event).

### F3 (MED, OPEN → follow-up) — AC5 retry lap + claiming_sandbox bind idempotency are prose-only
`STEPS` is a linear happy path ending at `succeeded`. Never exercised: (a) the **`Failed → Claiming` retry lap** (§8 + FR-A5) — the *trickiest* re-entry, because after a fence-first reclaim (§6.3) the second lap must re-run `claiming_sandbox` **idempotently**; (b) **Paused** non-terminal classification (AC5); (c) the `claiming_sandbox` step has **no modeled side effect**, so the story's "sandbox bind keyed by `run_id`, re-entry reattaches, never double-provisions" (story:122-125) is unfalsifiable even though a crash IS injected at that boundary. Design prose is sound; this is a coverage gap. Not blocking (design is arch-faithful), but should close before the machine ships. **Filed as child issue for falsification hardening during dev.**

### F4 (LOW, OPEN → note for dev) — AC4 "fencing is safety" is precise only for the *reclaim* (bumped-fence) zombie
On a **pure leader-election split-brain** (leader crashes, claim *not* reclaimed → `fence_token` unchanged), the old leader and the failover leader share the **same** fence, so fencing does **not** distinguish them — the conditional step-advance CAS (`WHERE reconcile_step = :expected`, AC3) is what prevents double-advance there, not fencing. The prose is complete (AC3 names the CAS) but AC4's emphasis could lead a dev to think fencing alone covers split-brain and drop the step-CAS. The check only ever tests a *lower*-fence zombie (`fence=0`), never a *same*-fence competitor; model uses `fence >= self.fence` where arch §6.3:711 is equality `fence_token = :myFence`. Recommend one line in AC4 crediting the step-CAS for the same-fence case, and a same-fence concurrent-advance arm in the check.

## Disposition
- **Story → APPROVE for dev.** Design is arch-faithful (§8/§5.1/§5.2/§6.3/§6.4) and internally consistent on all four load-bearing decisions.
- **Falsification** strengthened: F1 (mid-phase crux crash → dedup/upsert now exercised) + F2 (AC6 audit/outbox co-commit + no-phantom-on-zombie). Passes; proven to fail loud when either mechanism is removed.
- **F3 + F4** → child issue (falsification hardening: retry lap, claiming-bind idempotency, Paused classifier assert, same-fence split-brain arm) assigned to Developer to close alongside implementation + the real-Postgres integration test (Story 2.7 gate).
