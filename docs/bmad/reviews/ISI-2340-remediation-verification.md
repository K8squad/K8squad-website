# Remediation Verification — ISI-2340 (findings from ISI-2339 coord-schema review)

**Reviewer:** Amelia (Code Reviewer) · **Date:** 2026-08-12 · **Target:** `K8squad/K8squad` PR #5,
branch `feature/isi-2191-coord-schema` @ `f8d5a2e` (origin == local; pushed).
**Source review:** `docs/bmad/reviews/ISI-2339-coord-schema-review.md` (APPROVE WITH FINDINGS).
**Remediation commits:** `7d2b3a7` (F1–F6) + `f8d5a2e` (align firehose → ADR-040).

## Verdict: ✅ ALL FINDINGS RESOLVED — remediation APPROVED

Static line-by-line verification against `0001_coord_schema.sql` / `_test.sql` / `.github/workflows/ci.yml`
at the pushed tip. No local Postgres in this env (no `psql`/`docker`) — but F4 now wires the runtime
self-check into CI (the `migrations` lane), so real-PG execution runs automatically on every PR push.

| Finding | Sev | Resolution | Evidence |
|---|---|---|---|
| **F1** run_event unification / unprunable firehose | MED | Per **ADR-040**: firehose gets **no Postgres table** in v1; `run_event` replaced by `coord.audit_log` holding only bounded, immutable §6.5 coord audit → structurally immutable **without qualification**, retention-free. Shim trace rides SSE + opt-in OTel (§17.2). Both rejected alternatives (run_trace table; single-table DROP-PARTITION) documented as the F1 defect, not the fix. | `0001_coord_schema.sql:127-161`; arch §6.5 + ADR-040 @ `5a6fb29` |
| **F2** TRUNCATE evades append-only | LOW-MED | `BEFORE TRUNCATE … FOR EACH STATEMENT` guards added on `coord.comment` **and** `coord.audit_log` (same `reject_mutation`, `TG_OP='TRUNCATE'`). | `:181-190`; test assertion 10 `:185-195` |
| **F3** self-check never exercises §6.2 acquire | LOW | 8th assertion added: first acquire bumps fence 0→1 + sets holder + `RETURNING` 1 row; second acquire vs live lease affects 0 rows (no double-claim). Runs the exact §6.2 conditional UPDATE. | `_test.sql:139-168` |
| **F4** self-check orphaned from CI | LOW | New `migrations` job: `postgres:16` service, applies every non-`_test` migration then every `*_test.sql` with `psql -v ON_ERROR_STOP=1`. Skeleton-phase guard skips cleanly when `db/migrations` absent. Also satisfies review **ask-4** (run vs real PG) automatically. | `ci.yml:84-129` |
| **F5** tenancy inheritance not structural | LOW | Went beyond flag-only: `enforce_parent_tenancy` BEFORE INSERT/UPDATE trigger rejects cross-Project reparent + inherits `team_id`. §12.1 filter stays a single `project_id` predicate. | `:206-236`; test assertion 9 `:170-183` |
| **F6** dangling `§8.11` cross-ref | NIT | Corrected to §10.1 (shim contract); §8.11 = *wiring* story, not the arch section. | `:22-24, :138` |
| **F7** no re-provision if claim row deleted | NIT | Residual note added: direct `DELETE FROM coord.claim` (outside CASCADE) → permanently unclaimable; intended path never deletes; pkg/coord obligation. Not enforced structurally (would fight the work_item CASCADE). | `:111-115` |

## Cross-checks (no regressions introduced)
- Assertion 7 (orphans) inserts parent+child under the **same** `project_id`, so the new F5 tenancy
  trigger passes; the `ON DELETE SET NULL` cascade fires `enforce_parent_tenancy` with `NEW.parent_id
  IS NULL` → early return. No interaction defect.
- `audit_log` INSERT path (assertion 4) unaffected by the new TRUNCATE/tenancy triggers.
- Self-check count raised 7→10 assertions; final `\echo` updated to match. (Nit: `ci.yml:88` comment
  still says "7+ structural assertions" — accurate as a floor, non-blocking.)

## Disposition
Remediation is complete and correct. **F1 is resolved before Story 8.11 wires the shim stream**, as the
ticket required — and 8.11 now needs no migration (firehose is SSE+OTel, not a coord table). PR #5
(ISI-2191) is unblocked to merge; the `migrations` CI lane is the standing real-PG gate. → **done**.
