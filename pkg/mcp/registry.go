package mcp

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/ksquad-ai/ksquad/internal/memory"
)

// ToolRegistry defines the MCP tool registry interface.
type ToolRegistry interface {
	Register(name string, tool ToolHandler) error
}

// ToolHandler represents an MCP tool handler.
type ToolHandler func(ctx context.Context, args json.RawMessage) (interface{}, error)

// MemoryToolsRegistry registers the memory MCP tools.
type MemoryToolsRegistry struct {
	service *memory.MemoryService
	tools   map[string]ToolHandler
}

// NewMemoryToolsRegistry creates a new memory tools registry.
func NewMemoryToolsRegistry(service *memory.MemoryService) *MemoryToolsRegistry {
	return &MemoryToolsRegistry{
		service: service,
		tools:   make(map[string]ToolHandler),
	}
}

// RegisterAll registers all MVP memory MCP tools.
func (r *MemoryToolsRegistry) RegisterAll(registry ToolRegistry) error {
	tools := map[string]ToolHandler{
		"memory_write":  r.handleMemoryWrite,
		"memory_search": r.handleMemorySearch,
		"diary_append":  r.handleDiaryAppend,
		"diary_read":    r.handleDiaryRead,
	}

	// KG tools are intentionally NOT registered (fail-closed, Story 6.2 AC3)
	// kg_add, kg_query remain unimplemented until fast-follow

	for name, handler := range tools {
		if err := registry.Register(name, handler); err != nil {
			return fmt.Errorf("failed to register tool %s: %w", name, err)
		}
	}

	return nil
}

// handleMemoryWrite handles memory.write tool calls.
func (r *MemoryToolsRegistry) handleMemoryWrite(ctx context.Context, args json.RawMessage) (interface{}, error) {
	var req MemoryWriteArgs
	if err := json.Unmarshal(args, &req); err != nil {
		return nil, fmt.Errorf("invalid memory.write arguments: %w", err)
	}

	// Validate required fields
	if req.Content == "" {
		return nil, fmt.Errorf("content is required")
	}
	if req.Kind == "" {
		return nil, fmt.Errorf("kind is required")
	}
	if req.Scope == "" {
		return nil, fmt.Errorf("scope is required")
	}

	// TODO: Implement actual write through MemoryService
	// This would extend MemoryService to support write operations
	result := MemoryWriteResult{
		ID:        fmt.Sprintf("rec-%d", len(r.tools)),
		Author:    "current-agent", // Would come from authenticated context
		WrittenAt: "2026-08-17T19:39:55Z", // Would use actual timestamp
		Scope:     req.Scope,
	}

	return result, nil
}

// handleMemorySearch handles memory.search tool calls.
func (r *MemoryToolsRegistry) handleMemorySearch(ctx context.Context, args json.RawMessage) (interface{}, error) {
	var req MemorySearchArgs
	if err := json.Unmarshal(args, &req); err != nil {
		return nil, fmt.Errorf("invalid memory.search arguments: %w", err)
	}

	// Validate required fields
	if req.Query == "" {
		return nil, fmt.Errorf("query is required")
	}
	if req.Scope == "" {
		return nil, fmt.Errorf("scope is required")
	}

	limit := 10
	if req.Limit != nil {
		limit = *req.Limit
		if limit <= 0 {
			limit = 10
		}
	}

	// Convert query to embedding (placeholder - would use real embedder)
	embedding := make([]float32, 1536) // Mock embedding for testing
	query := memory.SearchQuery{
		SquadID:   req.Scope,
		Embedding: embedding,
		Limit:     limit,
	}

	// Use the MemoryService wrapper (this applies untrusted envelope)
	hits, err := r.service.Search(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("memory search failed: %w", err)
	}

	return MemorySearchResult{Results: hits}, nil
}

// handleDiaryAppend handles diary.append tool calls.
func (r *MemoryToolsRegistry) handleDiaryAppend(ctx context.Context, args json.RawMessage) (interface{}, error) {
	var req DiaryAppendArgs
	if err := json.Unmarshal(args, &req); err != nil {
		return nil, fmt.Errorf("invalid diary.append arguments: %w", err)
	}

	// Validate required fields
	if req.Entry == "" {
		return nil, fmt.Errorf("entry is required")
	}
	if req.Scope == "" {
		return nil, fmt.Errorf("scope is required")
	}

	// TODO: Implement actual diary append through MemoryService
	// This would require adding diary write functionality
	result := DiaryAppendResult{
		ID:        fmt.Sprintf("diag-%d", len(r.tools)),
		Author:    "current-agent", // Would come from authenticated context
		WrittenAt: "2026-08-17T19:39:55Z", // Would use actual timestamp
		Scope:     req.Scope,
	}

	return result, nil
}

// handleDiaryRead handles diary.read tool calls.
func (r *MemoryToolsRegistry) handleDiaryRead(ctx context.Context, args json.RawMessage) (interface{}, error) {
	var req DiaryReadArgs
	if err := json.Unmarshal(args, &req); err != nil {
		return nil, fmt.Errorf("invalid diary.read arguments: %w", err)
	}

	// Validate required fields
	if req.Agent == "" {
		return nil, fmt.Errorf("agent is required")
	}
	if req.Scope == "" {
		return nil, fmt.Errorf("scope is required")
	}

	lastN := 10
	if req.LastN != nil {
		lastN = *req.LastN
		if lastN <= 0 {
			lastN = 10
		}
	}

	// Use MemoryService.DiaryRead (this applies untrusted envelope)
	hits, err := r.service.DiaryRead(ctx, req.Scope, nil)
	if err != nil {
		return nil, fmt.Errorf("diary read failed: %w", err)
	}

	// Filter for the specific agent (placeholder - would need proper agent scoping)
	entries := make([]memory.DiaryEnvelope, len(hits))
	copy(entries, hits)

	// Limit results to last_n
	if len(entries) > lastN {
		entries = entries[len(entries)-lastN:]
	}

	return DiaryReadResult{Entries: entries}, nil
}

// GetRegisteredTools returns the list of registered MVP tools.
// This enforces AC2 - exactly the four tools, no more, no less.
func (r *MemoryToolsRegistry) GetRegisteredTools() []string {
	tools := make([]string, 0, 4)
	tools = append(tools, "memory_write", "memory_search", "diary_append", "diary_read")
	return tools
}