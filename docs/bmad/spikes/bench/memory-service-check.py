#!/usr/bin/env python3
"""Story 6.1 falsification — ksquad-memory service schema + pgvector integration (arch §7.1/§7.2, OQ10, FR-E1).

Differential check. It models the *schema + the semantic-search query plan a memory service would
define* for the `memory_records` table, then asserts the arch §7 / FR-E1 invariants over that model:

  INV1  (FR-E1 schema completeness) every required column exists with the right type; `embedding`
        is a pgvector `vector(dim)` column, NOT bytea/json/float[]-in-text.
  INV2  (OQ10 integrate-not-invent — the story's headline crux) semantic search runs ON pgvector:
        a `vector` column + an ANN index (ivfflat|hnsw with a *_cosine/l2/ip_ops opclass) + a
        pgvector distance operator (`<=>` / `<#>` / `<->`) in the search plan. A bespoke app-side
        cosine scan over rows is a build-not-integrate violation, even if it "returns results".
  INV3  (§7.3 trust substrate) the scope columns (squad_id, project_id) and provenance columns
        (principal_id, run_id, agent_id, created_at) EXIST and the load-bearing ones are NOT NULL,
        so an unscoped / unattributed row is not even representable. (6.1 lays the substrate; the
        write-auth *check* is 6.3, the tenancy-filter *predicate* is 6.5 — out of scope here.)
  INV4  (§7.4 durability / forward-only) the migration is forward-only — no destructive DROP/DELETE
        of the record; retraction is the soft `invalidated_at` column, preserving the audit trail.

Why differential: a happy-path "memory search returned something" demo passes with a bespoke,
un-scoped, in-app vector engine — exactly the OQ10 anti-pattern the story forbids. We first prove a
NAIVE provisioner (embeddings in a `bytea` blob, no vector index, app-side linear-scan search, no
scope/provenance columns, a destructive re-create migration) is DETECTED as violating every
invariant — so the harness has real teeth — then prove the §7 schema violates nothing.
stdlib only; `python3 memory-service-check.py`.
"""
import re
import sys

# Columns FR-E1 / arch §7.2 require on memory_records. Names are the issue's public spelling;
# the value is (sql_type_regex, not_null) — the reconciliation to §7.2 roles is pinned in the story.
REQUIRED = {
    "id":           (r"uuid|bigint|bigserial",           True),
    "squad_id":     (r"uuid|text",                        True),   # §7.2 scope_team_id — tenancy root
    "project_id":   (r"uuid|text",                        False),  # §7.2 scope_project_id — optional narrower scope
    "principal_id": (r"uuid|text",                        True),   # §7.2 author_principal — write-auth substrate
    "run_id":       (r"uuid|text",                        False),  # §7.2 author_run_id
    "agent_id":     (r"uuid|text",                        False),  # §7.2 author_agent_id
    "kind":         (r"text|varchar",                     True),
    "content":      (r"text",                             True),
    "embedding":    (r"vector\(\d+\)",                    True),   # pgvector type — INV1/INV2 crux
    "created_at":   (r"timestamptz|timestamp",            True),   # §7.2 written_at
    "invalidated_at": (r"timestamptz|timestamp",          False),  # §7.4 soft-retract — INV4
    "provenance":   (r"jsonb",                            False),  # extensible envelope (tags/trust/embedder)
}
VECTOR_OPS = {"<=>", "<#>", "<->"}            # pgvector distance operators (cosine / ip / l2)
ANN_INDEXES = {"ivfflat", "hnsw"}             # pgvector ANN index methods


# ---- provisioners: each returns a model of {ddl_columns, indexes, search_plan, migration} ----------

def provision_correct():
    """The arch §7 schema: pgvector `vector` column, ANN cosine index, `<=>` search, scoped+provenanced,
    forward-only migration with a soft-retract column."""
    return {
        "columns": {
            "id":            {"type": "uuid",        "not_null": True},
            "squad_id":      {"type": "uuid",        "not_null": True},
            "project_id":    {"type": "uuid",        "not_null": False},
            "principal_id":  {"type": "uuid",        "not_null": True},
            "run_id":        {"type": "uuid",        "not_null": False},
            "agent_id":      {"type": "uuid",        "not_null": False},
            "kind":          {"type": "text",        "not_null": True},
            "content":       {"type": "text",        "not_null": True},
            "embedding":     {"type": "vector(768)", "not_null": True},
            "created_at":    {"type": "timestamptz", "not_null": True},
            "invalidated_at":{"type": "timestamptz", "not_null": False},
            "provenance":    {"type": "jsonb",       "not_null": False},
        },
        # Integrate the store: an ANN index on the pgvector column + a scope index for the tenancy filter.
        "indexes": [
            {"name": "memory_records_embedding_ann", "method": "hnsw",
             "column": "embedding", "opclass": "vector_cosine_ops"},
            {"name": "memory_records_scope", "method": "btree",
             "column": "squad_id", "opclass": None},
        ],
        # Semantic search is pushed into Postgres/pgvector — ANN order-by the cosine operator, scoped.
        "search_plan": (
            "SELECT id, content, principal_id, run_id, created_at "
            "FROM memory_records "
            "WHERE squad_id = $1 AND invalidated_at IS NULL "
            "ORDER BY embedding <=> $2 LIMIT $3"
        ),
        # Forward-only: extension + table + index. No DROP/DELETE of the record; retract is soft.
        "migration": (
            "CREATE EXTENSION IF NOT EXISTS vector; "
            "CREATE TABLE IF NOT EXISTS memory_records (...); "
            "CREATE INDEX IF NOT EXISTS memory_records_embedding_ann "
            "ON memory_records USING hnsw (embedding vector_cosine_ops);"
        ),
    }


def provision_naive():
    """A plausible-but-wrong 'memory' service: a BESPOKE vector engine (OQ10 anti-pattern). Embeddings
    live in a `bytea` blob, there is no vector index, and search is an app-side linear scan that pulls
    every row and cosines them in the service process. No scope/provenance columns. The migration
    re-creates the table destructively. Every invariant is violated — the harness must catch it."""
    return {
        "columns": {
            "id":        {"type": "bigserial", "not_null": True},
            "kind":      {"type": "text",      "not_null": True},
            "content":   {"type": "text",      "not_null": True},
            # INV1/INV2 violation: embedding is an opaque blob, not a pgvector `vector` column.
            "embedding": {"type": "bytea",     "not_null": False},
            "created_at":{"type": "timestamptz","not_null": True},
            # INV3 violation: no squad_id/principal_id/run_id — unscoped, unattributed rows.
            # INV4 violation: no invalidated_at — retraction can only be a hard DELETE.
        },
        "indexes": [],  # INV2 violation: no ANN index — nothing to search on in the DB.
        # INV2 violation: search is app-side. Postgres just hands over rows; cosine runs in-process.
        "search_plan": "SELECT id, content, embedding FROM memory_records  -- then cosine() in Go/app memory",
        # INV4 violation: destructive re-create drops the knowledge record on every migrate.
        "migration": "DROP TABLE IF EXISTS memory_records; CREATE TABLE memory_records (...);",
    }


# ---- invariant checks: return a list of violation strings -----------------------------------------

def check_memory(model, provision_name):
    viol = []
    cols = model["columns"]

    # INV1: every required column present with the right type; embedding is a pgvector vector(dim).
    for name, (type_rx, want_nn) in REQUIRED.items():
        if name not in cols:
            viol.append(f"{provision_name}: missing required column {name!r} (FR-E1/INV1)")
            continue
        if not re.fullmatch(type_rx, cols[name]["type"]):
            viol.append(f"{provision_name}: column {name!r} type {cols[name]['type']!r} "
                        f"does not match required /{type_rx}/ (FR-E1/INV1)")
        if want_nn and not cols[name]["not_null"]:
            viol.append(f"{provision_name}: column {name!r} must be NOT NULL — "
                        f"unscoped/unattributed rows must not be representable (§7.3/INV3)")

    # INV2 (OQ10 crux): semantic search must run ON pgvector, not a bespoke app-side engine.
    emb = cols.get("embedding", {}).get("type", "")
    is_vector_col = bool(re.fullmatch(r"vector\(\d+\)", emb))
    if not is_vector_col:
        viol.append(f"{provision_name}: embedding column is {emb!r}, not a pgvector `vector(dim)` — "
                    f"a bespoke/blob store, not integration of pgvector (OQ10/INV2)")
    ann = [i for i in model["indexes"]
           if i.get("method") in ANN_INDEXES and i.get("column") == "embedding"
           and (i.get("opclass") or "").startswith("vector_")]
    if not ann:
        viol.append(f"{provision_name}: no pgvector ANN index (ivfflat|hnsw + vector_*_ops) on "
                    f"`embedding` — search cannot use the vector index (OQ10/INV2)")
    plan = model["search_plan"]
    uses_vector_op = any(op in plan for op in VECTOR_OPS)
    app_side = bool(re.search(r"cosine\(|--.*cosine|in\s+(go|app|process|memory)", plan, re.I))
    if not uses_vector_op:
        viol.append(f"{provision_name}: search plan does not use a pgvector distance operator "
                    f"({'/'.join(sorted(VECTOR_OPS))}) — semantic search is not pushed into pgvector "
                    f"(OQ10/INV2)")
    if app_side:
        viol.append(f"{provision_name}: search plan cosines rows app-side (bespoke vector engine) "
                    f"instead of ORDER BY embedding <=> $q in Postgres (OQ10/INV2)")

    # INV4 (§7.4): forward-only migration; retract is soft (invalidated_at), never a destructive drop.
    mig = model["migration"]
    if re.search(r"\bDROP\s+TABLE\b|\bDELETE\s+FROM\s+memory_records\b|\bTRUNCATE\b", mig, re.I):
        viol.append(f"{provision_name}: migration is destructive (DROP/DELETE/TRUNCATE of the record) "
                    f"— memory writes are durable Postgres commits, forward-only (§7.4/INV4)")
    if "invalidated_at" not in cols:
        viol.append(f"{provision_name}: no `invalidated_at` column — retraction can only be a hard "
                    f"delete, destroying the audit trail (§7.4/INV4)")

    return viol


def main():
    naive = check_memory(provision_naive(), "naive")
    print(f"[model] naive/bespoke engine : {len(naive)} invariant violation(s) -> "
          f"{'DETECTED' if naive else 'NONE (teeth lost!)'}")
    for v in naive:
        print(f"[model]   - {v}")
    if not naive:
        print("[model] FAIL — a bespoke un-scoped vector engine should violate FR-E1/OQ10 but did not; "
              "harness has no teeth.")
        return 1

    good = check_memory(provision_correct(), "§7 schema")
    print(f"[model] §7 pgvector schema  : {len(good)} violations "
          f"({'clean' if not good else 'UNEXPECTED'})")
    for v in good:
        print(f"[model]   - {v}")
    if good:
        print("[model] FAIL — the §7 pgvector schema must hold every FR-E1/OQ10/§7.3/§7.4 invariant.")
        return 1

    print("[model] PASS — bespoke engine detectably breaks FR-E1/OQ10; §7 pgvector schema holds "
          "schema-completeness, integrate-not-invent, trust-substrate, and forward-only durability.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
