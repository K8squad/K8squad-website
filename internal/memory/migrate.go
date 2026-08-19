package memory

import (
	"context"
	"fmt"
	"io/fs"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ksquad-ai/ksquad/db"
)

// applyMigrations applies every embedded forward-only migration exactly once, in lexical order,
// tracking applied versions in memory.schema_migrations. Each migration runs in its own transaction,
// so a crash mid-apply commits or rolls back a whole file, never a partial schema (§7.4). It is
// idempotent — already-applied versions are skipped — and forward-only: it never drops or rewrites a
// previously applied migration.
func applyMigrations(ctx context.Context, pool *pgxpool.Pool) error {
	entries, err := fs.Glob(db.Migrations, "migrations/*.sql")
	if err != nil {
		return fmt.Errorf("enumerate migrations: %w", err)
	}
	if len(entries) == 0 {
		return fmt.Errorf("no embedded migrations found")
	}
	sort.Strings(entries)

	// The bookkeeping table lives in the memory schema; the memory schema is created by 0001 itself,
	// so create the schema + tracker up front (idempotent, non-destructive).
	if _, err := pool.Exec(ctx, `
		CREATE SCHEMA IF NOT EXISTS memory;
		CREATE TABLE IF NOT EXISTS memory.schema_migrations (
			version    text        PRIMARY KEY,
			applied_at timestamptz NOT NULL DEFAULT now()
		);`); err != nil {
		return fmt.Errorf("ensure schema_migrations: %w", err)
	}

	for _, name := range entries {
		version := name // full embedded path is a stable, unique key

		var already bool
		if err := pool.QueryRow(ctx,
			`SELECT EXISTS(SELECT 1 FROM memory.schema_migrations WHERE version = $1)`,
			version).Scan(&already); err != nil {
			return fmt.Errorf("check migration %s: %w", version, err)
		}
		if already {
			continue
		}

body, err := fs.ReadFile(db.Migrations, name)
		if err != nil {
			return fmt.Errorf("read migration %s: %w", version, err)
		}

		tx, err := pool.Begin(ctx)
		if err != nil {
			return fmt.Errorf("begin migration %s: %w", version, err)
		}
		
		// Temporary workaround for ISI-2826: Handle vector extension creation failure for 0001_memory.sql
		if name == "migrations/0001_memory.sql" {
			// Try to create the vector extension first
			_, err := tx.Exec(ctx, "CREATE EXTENSION IF NOT EXISTS vector;")
			if err != nil {
				fmt.Printf("WARNING: Vector extension creation failed - applying migration without vector functionality (ISI-2826 workaround): %v\n", err)
				
				// Roll back this transaction and start fresh for the modified migration
				_ = tx.Rollback(ctx)
				
				// Start a new transaction for the modified migration
				tx, err := pool.Begin(ctx)
				if err != nil {
					return fmt.Errorf("begin modified migration %s: %w", version, err)
				}
				
				// Create a complete modified version of the migration
				modifiedMigration := string(body)
				
				// Remove vector extension creation
				modifiedMigration = strings.ReplaceAll(modifiedMigration, 
					"CREATE EXTENSION IF NOT EXISTS vector;\n", "")
				
				// Modify table creation to use text instead of vector for embedding column
				modifiedMigration = strings.ReplaceAll(modifiedMigration, 
					"embedding      vector(768) NOT NULL,",
					"embedding      text NOT NULL,")
				
				// Remove vector-specific index creation
				modifiedMigration = strings.ReplaceAll(modifiedMigration,
					"CREATE INDEX IF NOT EXISTS memory_records_embedding_ann\n    ON memory.memory_records USING hnsw (embedding vector_cosine_ops);\n", "")
				
				// Debug: Print the modified migration
				fmt.Printf("DEBUG: Modified migration length: %d\n", len(modifiedMigration))
				fmt.Printf("DEBUG: Original migration length: %d\n", len(body))
				
				// Execute the complete modified migration
				if _, err := tx.Exec(ctx, modifiedMigration); err != nil {
					_ = tx.Rollback(ctx)
					return fmt.Errorf("apply modified migration %s: %w", version, err)
				}
				
				// Continue with the rest of the migration flow (record and commit)
				goto record_migration
			}
		} else {
			// For other migrations, execute normally
			if _, err := tx.Exec(ctx, string(body)); err != nil {
				_ = tx.Rollback(ctx)
				return fmt.Errorf("apply migration %s: %w", version, err)
			}
		}
		
		// Common code path for recording migration
		record_migration:
		if _, err := tx.Exec(ctx,
			`INSERT INTO memory.schema_migrations (version) VALUES ($1)`, version); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("record migration %s: %w", version, err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("commit migration %s: %w", version, err)
		}

		// Record the migration as applied
		if _, err := tx.Exec(ctx,
			`INSERT INTO memory.schema_migrations (version) VALUES ($1)`, version); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("record migration %s: %w", version, err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("commit migration %s: %w", version, err)
		}
	}
	return nil
}
