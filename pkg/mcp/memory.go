package mcp

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/ksquad-ai/ksquad/internal/memory"
)

// MemoryTools provides the MCP tools surface for memory operations.
// This is the tool surface that agents use to interact with memory,
// wrapping the MemoryBackend with the necessary trust envelope (Story 6.2).
type MemoryTools struct {
	service *memory.MemoryService
}

// NewMemoryTools creates MCP tools that wrap the memory service with untrusted envelope.
func NewMemoryTools(service *memory.MemoryService) *MemoryTools {
	return &MemoryTools{service: service}
}

// MemoryWriteArgs represents the arguments for memory.write tool.
type MemoryWriteArgs struct {
	Content string   `json:"content"`
	Kind    string   `json:"kind"`
	Tags    []string `json:"tags,omitempty"`
	Scope   string   `json:"scope"` // Required: squad or squad:project
}

// MemoryWriteResult represents the result of memory.write tool.
type MemoryWriteResult struct {
	ID        string    `json:"id"`
	Author    string    `json:"author"`
	WrittenAt string    `json:"written_at"`
	Scope     string    `json:"scope"`
}

// MemorySearchArgs represents the arguments for memory.search tool.
type MemorySearchArgs struct {
	Query string `json:"query"`
	Scope string `json:"scope"` // Required: squad or squad:project
	Limit *int   `json:"limit,omitempty"`
}

// MemorySearchResult represents the result of memory.search tool.
type MemorySearchResult struct {
	Results []memory.SearchEnvelope `json:"results"`
}

// DiaryAppendArgs represents the arguments for diary.append tool.
type DiaryAppendArgs struct {
	Entry  string `json:"entry"`
	Scope  string `json:"scope"` // Required: squad or squad:project
}

// DiaryAppendResult represents the result of diary.append tool.
type DiaryAppendResult struct {
	ID        string    `json:"id"`
	Author    string    `json:"author"`
	WrittenAt string    `json:"written_at"`
	Scope     string    `json:"scope"`
}

// DiaryReadArgs represents the arguments for diary.read tool.
type DiaryReadArgs struct {
	Agent string `json:"agent"`   // Which agent's diary to read
	Scope string `json:"scope"`   // Required: squad or squad:project
	LastN *int   `json:"last_n,omitempty"` // Optional: number of most recent entries
}

// DiaryReadResult represents the result of diary.read tool.
type DiaryReadResult struct {
	Entries []memory.DiaryEnvelope `json:"entries"`
}

// memoryWrite implements the memory.write MCP tool.
// It writes a knowledge record and returns a provenanced acknowledgment.
func (m *MemoryTools) memoryWrite(ctx context.Context, args MemoryWriteArgs) (*MemoryWriteResult, error) {
	// TODO: Implement actual write through the MemoryService
	// This would require extending the MemoryService interface or adding a write method
	// For now, return the expected shape
	return &MemoryWriteResult{
		ID:        "mock-id",
		Author:    "mock-author",
		WrittenAt: "mock-timestamp",
		Scope:     args.Scope,
	}, nil
}

// memorySearch implements the memory.search MCP tool.
// It performs semantic search and returns results in untrusted envelopes.
func (m *MemoryTools) memorySearch(ctx context.Context, args MemorySearchArgs) (*MemorySearchResult, error) {
	limit := 10
	if args.Limit != nil {
		limit = *args.Limit
	}

	// Convert the query to an embedding (placeholder - would use real embedder in production)
	embedding := make([]float32, 1536) // Mock embedding
	
	query := memory.SearchQuery{
		SquadID:   args.Scope,
		Embedding: embedding,
		Limit:     limit,
	}

	hits, err := m.service.Search(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("memory search failed: %w", err)
	}

	return &MemorySearchResult{
		Results: hits,
	}, nil
}

// diaryAppend implements the diary.append MCP tool.
// It appends an entry to the specified agent's diary.
func (m *MemoryTools) diaryAppend(ctx context.Context, args DiaryAppendArgs) (*DiaryAppendResult, error) {
	// TODO: Implement actual diary append through MemoryService
	// This would require adding diary write functionality to MemoryService
	return &DiaryAppendResult{
		ID:        "mock-diary-id",
		Author:    "mock-author",
		WrittenAt: "mock-timestamp",
		Scope:     args.Scope,
	}, nil
}

// diaryRead implements the diary.read MCP tool.
// It reads entries from the specified agent's diary.
func (m *MemoryTools) diaryRead(ctx context.Context, args DiaryReadArgs) (*DiaryReadResult, error) {
	lastN := 10
	if args.LastN != nil {
		lastN = *args.LastN
	}

	// Use MemoryService.DiaryRead with the agent's scope
	// For now, we'll use squad scope as the diary scope
	hits, err := m.service.DiaryRead(ctx, args.Scope, nil)
	if err != nil {
		return nil, fmt.Errorf("diary read failed: %w", err)
	}

	// Filter for the specific agent (placeholder - would need agent-scoped diary)
	entries := make([]memory.DiaryEnvelope, len(hits))
	copy(entries, hits)

	return &DiaryReadResult{
		Entries: entries,
	}, nil
}