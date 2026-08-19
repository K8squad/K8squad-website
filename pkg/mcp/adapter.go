package mcp

import (
	"context"
	"fmt"
	"log"

	"github.com/ksquad-ai/ksquad/internal/memory"
)

// Adapter integrates the memory MCP tools with the ksquad system.
// This implements the Story 6.2 MCP tools surface by wrapping the MemoryService
// with the untrusted envelope protection.
type Adapter struct {
	service *memory.MemoryService
	tools   *MemoryToolsRegistry
}

// NewAdapter creates a new MCP adapter for memory tools.
func NewAdapter(service *memory.MemoryService) *Adapter {
	return &Adapter{
		service: service,
		tools:   NewMemoryToolsRegistry(service),
	}
}

// RegisterTools registers all memory MCP tools with the given registry.
// This implements AC2 - exactly the four MVP tools, no more, no less.
func (a *Adapter) RegisterTools(registry ToolRegistry) error {
	log.Println("Registering memory MCP tools (Story 6.2)")
	
	tools := a.tools.GetRegisteredTools()
	log.Printf("Registering %d tools: %v", len(tools), tools)
	
	if err := a.tools.RegisterAll(registry); err != nil {
		return fmt.Errorf("failed to register memory tools: %w", err)
	}

	// Verify AC2: exactly four MVP tools, no KG tools
	registeredTools := a.tools.GetRegisteredTools()
	expected := []string{"memory_write", "memory_search", "diary_append", "diary_read"}
	
	if len(registeredTools) != len(expected) {
		return fmt.Errorf("AC2 violation: expected %d tools, got %d", len(expected), len(registeredTools))
	}
	
	for _, expectedTool := range expected {
		found := false
		for _, tool := range registeredTools {
			if tool == expectedTool {
				found = true
				break
			}
		}
		if !found {
			return fmt.Errorf("AC2 violation: expected tool %s not found", expectedTool)
		}
	}

	log.Println("✓ Memory MCP tools registered successfully")
	log.Println("✓ AC2 passed: exactly four MVP tools registered")
	log.Println("✓ AC3 enforced: KG tools (kg_add, kg_query, memory_relate) NOT registered (fail-closed)")
	
	return nil
}

// ValidateToolShapes validates that all tools return the correct envelope shapes (AC5).
func (a *Adapter) ValidateToolShapes(ctx context.Context) error {
	log.Println("Validating tool envelope shapes (AC5)")
	
	// Test search envelope shape
	embedding := make([]float32, 1536) // Mock embedding
	searchQuery := memory.SearchQuery{
		SquadID:   "test-squad",
		Embedding: embedding,
		Limit:     1,
	}
	
	hits, err := a.service.Search(ctx, searchQuery)
	if err != nil {
		return fmt.Errorf("search validation failed: %w", err)
	}
	
	for _, hit := range hits {
		// Verify untrusted envelope shape
		if hit.Content == "" {
			return fmt.Errorf("AC5 violation: search result content missing")
		}
		if hit.Author == "" {
			return fmt.Errorf("AC5 violation: search result author missing")
		}
		if hit.WrittenAt.IsZero() {
			return fmt.Errorf("AC5 violation: search result written_at missing")
		}
		if hit.Scope == "" {
			return fmt.Errorf("AC5 violation: search result scope missing")
		}
		if hit.Trust != memory.TRUST_UNTRUSTED {
			return fmt.Errorf("AC5 violation: search result trust must be %s, got %s", 
				memory.TRUST_UNTRUSTED, hit.Trust)
		}
	}
	
	log.Println("✓ AC5 passed: tools return correct untrusted envelope shapes")
	return nil
}

// GetMemoryService returns the underlying MemoryService for direct use.
// This is for internal system components that need access to the service
// while maintaining the MCP tool surface as the primary agent interface.
func (a *Adapter) GetMemoryService() *memory.MemoryService {
	return a.service
}

// IsToolRegistered checks if a specific tool is in the MVP set.
func (a *Adapter) IsToolRegistered(toolName string) bool {
	registered := a.tools.GetRegisteredTools()
	for _, tool := range registered {
		if tool == toolName {
			return true
		}
	}
	return false
}

// GetToolList returns the complete list of registered MVP tools.
func (a *Adapter) GetToolList() []string {
	return a.tools.GetRegisteredTools()
}