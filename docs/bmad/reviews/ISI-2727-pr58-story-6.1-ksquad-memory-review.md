# ISI-2727 — Code Review: PR #58 (Story 6.1 `ksquad-memory` runtime, ISI-2222)

**Reviewer:** Amelia (Code Reviewer) · **Date:** 2026-08-17
**PR:** https://github.com/K8squad/K8squad/pull/58 — `feature/isi-2222-ksquad-memory` → `main`
**Head:** `983f9e6` · **Diff:** +737 / −0 across 8 files (net-new `cmd/memory` + `internal/memory`)

## Verdict: ✅ APPROVE — cleared to merge on CI green (DCO already signed)

Three adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) run line-by-line
over all 8 files. No correctness defects. Two non-blocking notes below.

## Verification performed (this review)
| Check | Result |
|-------|--------|
| `go build ./cmd/memory` (go 1.25.9) | ✅ exit 0 |
| `go vet ./internal/memory/... ./cmd/memory` | ✅ exit 0 |
| `go test -tags integration` (compile, no DB) | ✅ compiles |
| Real-PG arm `MEMORY_TEST_DATABASE_URL=… go test -tags integration ./internal/memory/...` | ⚠️ **not run** — no pgvector Postgres on host; CI-gated |
| Falsification bench `memory-service-check.py` | ✅ GREEN — 16-violation teeth on the naive/bespoke provisioner, 0 on §7 schema |
| DCO signoff | ✅ `Signed-off-by: Paperclip Agent` |
| Mergeability vs `main` | ✅ clean fast-forward; `cmd/memory`+`internal/memory` net-new (no collision) |
| Repo cleanliness | ✅ no `docs/bmad/` paths; `ISI-` only in code comments (precedent: 35 Go files on `main` already do) |

## Acceptance audit (ticket focus items — all met)
- **OQ10/ADR-004 integrate-not-invent** ✅ — `store.go` search is `ORDER BY embedding <=> $2::vector`
  over the hnsw `vector_cosine_ops` ANN index; distance computed by pgvector, never in-process.
  `encodeVector` binds a text pgvector literal cast `::vector` — no app-side cosine scan.
- **AC1 fail-closed start** ✅ — `Open` pings, applies migrations, then `Ready()` probes
  `pg_extension.vector` **and** `memory.schema_migrations` for `0001`; hard error (no silent
  fallback) if either is absent. `main.go` `log.Fatalf` on `Open` error.
- **Migration isolation** ✅ — `embed.go` `//go:embed migrations/*.sql` is package-local to
  `internal/memory`; the embed FS cannot reach the shared `db/migrations` (coord/discussion) set,
  and `migrate.go` globs only `migrations/*.sql`. Structurally cannot apply another schema's SQL.
- **§7.3 substrate NOT NULL** ✅ — `0001_memory.sql`: `squad_id` + `principal_id` NOT NULL;
  `project_id`/`run_id`/`agent_id` nullable per spec; `Write` also guards required fields.
- **§7.4 soft-retract, forward-only** ✅ — `invalidated_at` column; `Invalidate` is `UPDATE … SET
  invalidated_at = now()`, never DELETE; migration carries no DROP/DELETE/TRUNCATE; idempotent
  re-invalidate returns `false` (tested).
- **Dockerfile.memory** ✅ — now builds `./cmd/memory`, the target that was previously absent on
  every branch (the root cause this PR resolves).

## Non-blocking findings
- **N1 (edge case — concurrent pod start):** two `ksquad-memory` pods starting simultaneously both
  run `applyMigrations`; both may `INSERT` version `migrations/0001_memory.sql` into the
  `schema_migrations` PK → one loses on the unique constraint, its migration tx rolls back, `Open`
  fails closed, and that pod recovers on restart (sees already-applied). **No corruption**, but a
  transient startup crash-loop is possible under a cold multi-replica rollout.
  *Upgrade path:* wrap the migrator in a `pg_advisory_lock`. `ponytail:` acceptable for v1 —
  fail-closed + restart is self-healing; single-writer at bootstrap is the common deploy shape.
- **N2 (doc nit):** `cmd/memory/main.go:3` comment says "applies (or verifies) `db/migrations`" —
  the code correctly applies `internal/memory/migrations`. Comment only; behavior is correct and is
  in fact the isolation the ticket demands. Worth a one-word fix on a later touch.
- **N3 (naming deviation, documented):** SQL uses `squad_id`/`principal_id`/`created_at` vs the §7.2
  authoritative `scope_team_id`/`author_principal`/`written_at`. The 1:1 mapping is spelled out in
  the migration header and matches the falsification bench's `REQUIRED` set — consistent, not a
  defect. (Same unstuttering pattern noted on ISI-2709.)
- **N4 (pgvector recall caveat):** hnsw ANN + `WHERE squad_id … AND invalidated_at IS NULL` is a
  filtered-ANN query; on older pgvector the post-filter can under-fill `LIMIT` under heavy scoping.
  Acceptable for v1 correctness (results are still correctly scoped/ranked); a recall-tuning concern
  for later, not a merge blocker.

## Merge disposition
Clean FF, DCO green, zero blast radius on existing code. The only unmet ticket precondition is **CI
green**, which I could not confirm from here: the Checks API is 403 for the available PAT (same
branch-protection lockout as ISI-2674) and the commit's combined status is **pending** (nothing
failing — checks in-flight). **Cleared to merge the moment CI resolves green; merge closes ISI-2222.**
