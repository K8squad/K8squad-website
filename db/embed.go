// Package db embeds the forward-only SQL migrations so the ksquad-memory binary applies (or verifies)
// them on start (§7.4 discipline — same as the coord schema). The migrations directory is the single
// source of truth for the `memory` schema shape.
package db

import "embed"

// Migrations holds the versioned, forward-only SQL migrations, applied in lexical filename order.
//
//go:embed migrations/*.sql
var Migrations embed.FS
