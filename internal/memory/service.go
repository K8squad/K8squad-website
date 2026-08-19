package memory

import (
	"context"
	"encoding/json"
	"time"
)

// Envelope is the untrusted-provenance envelope every read MUST return (§7.3.2 rule 2).
// Every read path wraps records in this envelope so readers can see, attribute, and weight
// records instead of silently consuming them as trusted system context.
type Envelope struct {
	Content     string          `json:"content"`
	Author      string          `json:"author"`
	WrittenAt   time.Time       `json:"written_at"`
	Scope       string          `json:"scope"`
	Trust       string          `json:"trust"`
	Provenance  json.RawMessage `json:"provenance,omitempty"`
}

// SearchEnvelope is a ranked search result wrapped in the untrusted envelope.
type SearchEnvelope struct {
	Envelope
	Distance float64 `json:"distance"`
}

// DiaryEnvelope is a diary result wrapped in the untrusted envelope.
type DiaryEnvelope struct {
	Envelope
}

// MemoryService wraps the MemoryBackend with the untrusted envelope enforcement.
// It ensures every read returns the proper envelope with server-stamped trust="untrusted"
// and surfaced provenance, defending against memory poisoning (Story 6.4 / ISI-2242).
type MemoryService struct {
	backend MemoryBackend
}

// NewMemoryService creates a memory service with untrusted envelope enforcement.
func NewMemoryService(backend MemoryBackend) *MemoryService {
	return &MemoryService{backend: backend}
}

// Search wraps the backend search with untrusted envelope enforcement.
// Every result is wrapped in the envelope so provenance is surfaced and trust is marked.
func (s *MemoryService) Search(ctx context.Context, query SearchQuery) ([]SearchEnvelope, error) {
	// Delegate to the backend for the actual search
	hits, err := s.backend.Search(ctx, query)
	if err != nil {
		return nil, err
	}

	// Wrap every result in the untrusted envelope
	envelopes := make([]SearchEnvelope, len(hits))
	for i, hit := range hits {
		envelopes[i] = SearchEnvelope{
			Envelope: Envelope{
				Content:   hit.Content,
				Author:    hit.PrincipalID, // Honest provenance from the 6.3 write path
				WrittenAt: hit.CreatedAt,
				Scope:     buildScope(hit.SquadID, hit.ProjectID),
				Trust:     TRUST_UNTRUSTED, // Server-stamped "untrusted" by construction
				Provenance: hit.Provenance,
			},
			Distance: hit.Distance,
		}
	}

	return envelopes, nil
}

// DiaryRead wraps the diary read with untrusted envelope enforcement.
// Same envelope as search, ensuring uniform read paths (no bypass).
func (s *MemoryService) DiaryRead(ctx context.Context, squadID string, projectID *string) ([]DiaryEnvelope, error) {
	// Build a search query for diary read (scoped by squad/project)
	query := SearchQuery{
		SquadID: squadID,
		Limit:   100, // Reasonable default for diary reads
	}
	if projectID != nil {
		// Note: current backend doesn't support project-level scoping in search
		// This would need to be implemented if project-level diary reads are required
	}

	hits, err := s.backend.Search(ctx, query)
	if err != nil {
		return nil, err
	}

	// Wrap every result in the untrusted envelope (same as search)
	envelopes := make([]DiaryEnvelope, len(hits))
	for i, hit := range hits {
		envelopes[i] = DiaryEnvelope{
			Envelope: Envelope{
				Content:   hit.Content,
				Author:    hit.PrincipalID, // Honest provenance from the 6.3 write path
				WrittenAt: hit.CreatedAt,
				Scope:     buildScope(hit.SquadID, hit.ProjectID),
				Trust:     TRUST_UNTRUSTED, // Server-stamped "untrusted" by construction
				Provenance: hit.Provenance,
			},
		}
	}

	return envelopes, nil
}

// buildScope constructs the scope string from squad and optional project.
func buildScope(squadID string, projectID *string) string {
	if projectID != nil {
		return squadID + ":" + *projectID
	}
	return squadID
}

// TRUST_UNTRUSTED is the only legal value for the server-stamped trust tier.
// Memory recall is the "untrusted-recall" tier — never authoritative, never system.
const TRUST_UNTRUSTED = "untrusted"