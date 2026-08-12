# Code Review — coord schema migration (Story 2.1 / ISI-2191, PR #5)

**Reviewer:** Amelia (Code Reviewer) · **Date:** 2026-08-12 · **Authority:** Arch §6.1
**Target:** `K8squad/K8squad` PR #5, branch `feature/isi-2191-coord-schema`
**Files:** `db/migrations/0001_coord_schema.sql`, `0001_coord_schema_test.sql`, `README.md`

## Verdict: ✅ APPROVE WITH FINDINGS

Schema is structurally sound and downstream Epic 2 (2.2 claim/lease) can build on it now. No
blocking-critical findings. **F1 (`run_event` shape) is a design decision for the Architect and
should be resolved before Story 8.11 wires the shim stream to this table** — it does not block 2.2.

## Answers to the four review asks

1. **§6.2/§6.4 mechanism SQL executes cleanly — CONFIRMED (static trace; no PG in env).**
   Every column the acquire/renew UPDATEs touch exists on `coord.claim` (`0001_coord_schema.sql:92-102`).
   The `AFTER INSERT` trigger `work_item_provision_claim` (`:115-117`) fires in the *same transaction*
   as the `work_item` INSERT, so no work_item can exist without its unheld claim row (`holder NULL`,
   `fence_token 0`). First acquire therefore matches `holder_principal IS NULL`, `RETURNING fence_token`
   → 1. The `artifact_upsert_key` UNIQUE (`:82`) backs the §6.4 `ON CONFLICT … DO UPDATE`. Trigger
   guarantees the row the §6.2 UPDATE assumes. ✓

2. **FK `ON DELETE` choices — CONFIRMED consistent with §6.1 lifecycle.**
   `comment/artifact/run_event → work_item` `RESTRICT` (`:64,:76,:127`) pins any item with history;
   `claim → work_item` `CASCADE` (`:93`) lets custody die with the item; `parent_id` `SET NULL`
   (`:35`) gives orphans-as-roots. Internally consistent and matches §6.1. **Caveat (F5):** the §6.1(c)
   cross-Project tenancy-inheritance invariant is NOT structural — no constraint enforces it.

3. **`run_event` unifying §6.5 audit + §8.11/§10.1 shim stream — CONCERN, see F1.** Recommend
   reconsidering the one-table shape before 2.2/8.11 wire to it.

4. **Self-check run — NOT RUN: no Postgres in the authoring env** (no `psql`, no `docker`,
   `DATABASE_URL` unset). Performed a line-by-line static execution trace instead: all 7 assertions
   trace green against the schema. **Strongly recommend wiring the self-check into CI (F4)** so
   check-4 runs automatically on every push.

## Findings

### F1 — [MEDIUM] `run_event` unification makes the shim firehose unprunable · `0001_coord_schema.sql:125-161`
`run_event` carries both the low-volume immutable coord audit (§6.5) and the high-volume shim
trace stream (`tool_call|llm_call|build_output|error`, `:130`). The `run_event_append_only` trigger
(`:159-161`) rejects every DELETE, so the trace firehose is **unprunable** — retention forces
declarative-partition `DROP`, which itself *bypasses* the "structurally immutable" guarantee the file
advertises (`:124,:145`). The `bigserial id` "monotonic audit sequence" (`:124`) is also interleaved
with trace noise → gaps once you filter by `event_type`.
**Failure scenario:** 2.7 chaos + normal Runs emit millions of `tool_call`/`llm_call` rows; audit
queries slow and the table cannot be pruned without partition surgery that contradicts the immutability
claim. **Recommend:** split into `audit_log` (immutable) + `run_trace` (time-partitioned, retention-managed),
OR commit to declarative time-partitioning of `run_event` + documented `DROP PARTITION` retention and
soften the "structurally immutable" wording. **Owner: Architect** (shape decision) — resolve before 8.11.

### F2 — [LOW-MED] Append-only enforcement evaded by `TRUNCATE` · `0001_coord_schema.sql:155-161`
`FOR EACH ROW` triggers do NOT fire on `TRUNCATE`, so `TRUNCATE coord.comment` / `coord.run_event`
wipes history silently — contradicting "a stray or compromised code path cannot mutate history" (`:145`).
**Fix:** add `BEFORE TRUNCATE … FOR EACH STATEMENT EXECUTE FUNCTION coord.reject_mutation()` on both
tables (the same function works — `TG_OP='TRUNCATE'`), or document a least-privilege `GRANT` mitigation.
Ceiling: `TRUNCATE` needs table-owner rights — but the migration-runner role owns these tables.

### F3 — [LOW] Self-check never exercises the §6.2 acquire — the exact thing check-1 asks · `0001_coord_schema_test.sql:26-40`
Assertion 2 proves the auto-provisioned claim row *exists* but never runs the §6.2 acquire UPDATE.
**Add an 8th assertion:** run the acquire, assert `fence_token → 1` + `holder` set + `RETURNING` one
row, then a second acquire (live lease) returns 0 rows. Single-threaded, structural, belongs here
(concurrency stays in the Go chaos suite).

### F4 — [LOW] Self-check orphaned from CI · `.github/workflows/ci.yml`
`ci.yml` gates `pkg/coord` Go coverage (≥90%) but no job runs `0001_coord_schema_test.sql` against a
Postgres service — the runnable check can silently rot. Add a `postgres:` service job that runs the
two-file `psql -v ON_ERROR_STOP=1` invocation. Also makes check-4 run automatically.

### F5 — [LOW] Tenancy inheritance across parent/child is not structural · `0001_coord_schema.sql:34-35`
§6.1(c) (child inherits parent `project_id`/`team_id`; cross-Project reparent rejected) has no DB
constraint — relies entirely on `pkg/coord`. Consistent with the documented design, but flag so 2.2 /
§12.1 tenancy filters don't assume DB enforcement.

### F6 — [NIT] `§8.11` is a dangling cross-ref · `0001_coord_schema.sql:120,124`
Arch has no §8.11; the shim Run-event contract lives at §10.1 (§8 stops at 8.6). The ticket inherited
the same wrong ref. Fix the comment cross-ref.

### F7 — [NIT] No re-provision if a claim row is removed · `0001_coord_schema.sql:105-117`
A direct `DELETE FROM coord.claim` (not via work_item cascade) leaves the item permanently unclaimable
(acquire matches 0 rows → reads as "held"). Intended path never deletes claim rows; residual-only note.

## Strengths (verified)
- Structural-not-disciplinary enforcement done right: PK + auto-provision trigger, append-only trigger,
  `artifact_upsert_key` UNIQUE, `state` CHECK, self-parent CHECK, `SET NULL` orphans.
- `gen_random_uuid()` PG13-core note (`:25`) is correct — no `CREATE EXTENSION`, least-privilege role holds.
- Indexes map to every §13 access path (project, parent lazy-load, board, List sort, reclaim scan).
- Story↔§6.1 name reconciliation is clean and documented (`README.md:27-38`).
- No `message` table → structural no-P2P (I4). Good.
