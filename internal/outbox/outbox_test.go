package outbox

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func setupTestDB(t *testing.T) *pgxpool.Pool {
	ctx := context.Background()
	
	// Use a test database - in CI this would be a test container
	dbConfig, err := pgxpool.ParseConfig("postgres://postgres:password@localhost:5432/ksquad_test?sslmode=disable")
	require.NoError(t, err)
	
	dbConfig.MaxConns = 10
	dbConfig.MinConns = 2
	dbConfig.HealthCheckPeriod = 30 * time.Second
	
	pool, err := pgxpool.NewWithConfig(ctx, dbConfig)
	require.NoError(t, err)
	
	// Create the outbox schema
	schemaSQL := `
		CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
		
		CREATE TABLE IF NOT EXISTS domain_events (
			id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
			entity_id VARCHAR(255) NOT NULL,
			entity_type VARCHAR(100) NOT NULL,
			event_type VARCHAR(100) NOT NULL,
			event_data JSONB NOT NULL,
			metadata JSONB,
			created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
			published_at TIMESTAMPTZ,
			published_attempts INTEGER DEFAULT 0,
			published_status VARCHAR(20) DEFAULT 'pending',
			error_message TEXT,
			created_by VARCHAR(100),
			version INTEGER DEFAULT 1
		);
		
		CREATE INDEX idx_domain_events_entity_id ON domain_events(entity_id);
		CREATE INDEX idx_domain_events_entity_type ON domain_events(entity_type);
		CREATE INDEX idx_domain_events_event_type ON domain_events(event_type);
		CREATE INDEX idx_domain_events_created_at ON domain_events(created_at);
		CREATE INDEX idx_domain_events_published_status ON domain_events(published_status);
		CREATE INDEX idx_domain_events_unpublished ON domain_events(published_status, created_at) 
		WHERE published_status = 'pending' OR (published_status = 'failed' AND published_attempts < 5);
	`
	
	_, err = pool.Exec(ctx, schemaSQL)
	require.NoError(t, err)
	
	// Clean up before each test
	cleanupSQL := `TRUNCATE domain_events`
	_, err = pool.Exec(ctx, cleanupSQL)
	require.NoError(t, err)
	
	return pool
}

func TestOutboxRepository_CreateEvent(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	
	repo := NewOutboxRepository(db)
	
	ctx := context.Background()
	
	event := &DomainEvent{
		EntityID:   "test-run-1",
		EntityType: EntityTypeRun,
		EventType:  EventRunCreated,
		EventData: EventData{
			ID:        "test-run-1",
			Status:    "pending",
			NewState:  map[string]interface{}{"run_id": "test-run-1", "status": "pending"},
			CreatedBy: "test-user",
			Timestamp: time.Now(),
		},
		Metadata: EventMetadata{
			Source:   "test",
			Project:  "test-project",
			Squad:    "test-squad",
		},
		CreatedBy: "test-user",
	}
	
	err := repo.CreateEvent(ctx, event)
	assert.NoError(t, err)
	assert.NotEmpty(t, event.ID)
	assert.NotEmpty(t, event.CreatedAt)
	
	// Verify the event was stored
	var storedEvent DomainEvent
	var eventDataJSON, metadataJSON []byte
	err = db.QueryRow(ctx, 
		"SELECT id, entity_id, entity_type, event_type, event_data, metadata, created_at, created_by, version FROM domain_events WHERE id = $1",
		event.ID,
	).Scan(
		&storedEvent.ID,
		&storedEvent.EntityID,
		&storedEvent.EntityType,
		&storedEvent.EventType,
		&eventDataJSON,
		&metadataJSON,
		&storedEvent.CreatedAt,
		&storedEvent.CreatedBy,
		&storedEvent.Version,
	)
	assert.NoError(t, err)
	
	assert.Equal(t, event.EntityID, storedEvent.EntityID)
	assert.Equal(t, event.EntityType, storedEvent.EntityType)
	assert.Equal(t, event.EventType, storedEvent.EventType)
	assert.Equal(t, event.CreatedBy, storedEvent.CreatedBy)
	
	// Parse JSON fields to verify data
	assert.NoError(t, json.Unmarshal(eventDataJSON, &storedEvent.EventData))
	assert.Equal(t, event.EventData.ID, storedEvent.EventData.ID)
	assert.Equal(t, event.EventData.Status, storedEvent.EventData.Status)
	
	assert.NoError(t, json.Unmarshal(metadataJSON, &storedEvent.Metadata))
	assert.Equal(t, event.Metadata.Source, storedEvent.Metadata.Source)
}

func TestOutboxRepository_GetUnpublishedEvents(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	
	repo := NewOutboxRepository(db)
	ctx := context.Background()
	
	// Create some test events
	events := []*DomainEvent{
		{
			EntityID:   "run-1",
			EntityType: EntityTypeRun,
			EventType:  EventRunCreated,
			EventData: EventData{
				ID:        "run-1",
				Status:    "pending",
				NewState:  map[string]interface{}{"run_id": "run-1"},
				CreatedBy: "user1",
			},
			Metadata:   EventMetadata{Source: "test"},
			CreatedBy: "user1",
		},
		{
			EntityID:   "run-2",
			EntityType: EntityTypeRun,
			EventType:  EventRunCompleted,
			EventData: EventData{
				ID:        "run-2",
				Status:    "completed",
				NewState:  map[string]interface{}{"run_id": "run-2"},
				CreatedBy: "user2",
			},
			Metadata:   EventMetadata{Source: "test"},
			CreatedBy: "user2",
		},
	}
	
	for _, event := range events {
		err := repo.CreateEvent(ctx, event)
		assert.NoError(t, err)
	}
	
	// Test getting unpublished events
	unpublished, err := repo.GetUnpublishedEvents(ctx, 10, 1440)
	assert.NoError(t, err)
	assert.Len(t, unpublished, 2)
	
	// Test batch size limiting
	unpublished, err = repo.GetUnpublishedEvents(ctx, 1, 1440)
	assert.NoError(t, err)
	assert.Len(t, unpublished, 1)
}

func TestOutboxRepository_MarkEventPublished(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	
	repo := NewOutboxRepository(db)
	ctx := context.Background()
	
	// Create a test event
	event := &DomainEvent{
		EntityID:   "test-run-1",
		EntityType: EntityTypeRun,
		EventType:  EventRunCreated,
		EventData: EventData{
			ID:        "test-run-1",
			Status:    "pending",
			NewState:  map[string]interface{}{"run_id": "test-run-1"},
			CreatedBy: "test-user",
		},
		Metadata:   EventMetadata{Source: "test"},
		CreatedBy: "test-user",
	}
	
	err := repo.CreateEvent(ctx, event)
	assert.NoError(t, err)
	
	// Mark it as published
	err = repo.MarkEventPublished(ctx, event.ID)
	assert.NoError(t, err)
	
	// Verify the status was updated
	var publishedStatus string
	err = db.QueryRow(ctx, 
		"SELECT published_status FROM domain_events WHERE id = $1",
		event.ID,
	).Scan(&publishedStatus)
	assert.NoError(t, err)
	assert.Equal(t, StatusPublished, publishedStatus)
	
	var publishedAt time.Time
	err = db.QueryRow(ctx, 
		"SELECT published_at FROM domain_events WHERE id = $1",
		event.ID,
	).Scan(&publishedAt)
	assert.NoError(t, err)
	assert.NotEmpty(t, publishedAt)
}

func TestOutboxRepository_MarkEventFailed(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	
	repo := NewOutboxRepository(db)
	ctx := context.Background()
	
	// Create a test event
	event := &DomainEvent{
		EntityID:   "test-run-1",
		EntityType: EntityTypeRun,
		EventType:  EventRunCreated,
		EventData: EventData{
			ID:        "test-run-1",
			Status:    "pending",
			NewState:  map[string]interface{}{"run_id": "test-run-1"},
			CreatedBy: "test-user",
		},
		Metadata:   EventMetadata{Source: "test"},
		CreatedBy: "test-user",
	}
	
	err := repo.CreateEvent(ctx, event)
	assert.NoError(t, err)
	
	// Mark it as failed
	errorMsg := "NATS connection failed"
	err = repo.MarkEventFailed(ctx, event.ID, errorMsg)
	assert.NoError(t, err)
	
	// Verify the status and error message were updated
	var publishedStatus, errorMessage string
	var publishedAttempts int
	err = db.QueryRow(ctx, 
		"SELECT published_status, published_attempts, error_message FROM domain_events WHERE id = $1",
		event.ID,
	).Scan(&publishedStatus, &publishedAttempts, &errorMessage)
	assert.NoError(t, err)
	assert.Equal(t, StatusFailed, publishedStatus)
	assert.Equal(t, 1, publishedAttempts)
	assert.Equal(t, errorMsg, errorMessage)
}

func TestOutboxRepository_RetryFailedEvents(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	
	repo := NewOutboxRepository(db)
	ctx := context.Background()
	
	// Create a failed event
	event := &DomainEvent{
		EntityID:   "test-run-1",
		EntityType: EntityTypeRun,
		EventType:  EventRunCreated,
		EventData: EventData{
			ID:        "test-run-1",
			Status:    "pending",
			NewState:  map[string]interface{}{"run_id": "test-run-1"},
			CreatedBy: "test-user",
		},
		Metadata:   EventMetadata{Source: "test"},
		CreatedBy: "test-user",
	}
	
	err := repo.CreateEvent(ctx, event)
	assert.NoError(t, err)
	
	// Mark it as failed
	err = repo.MarkEventFailed(ctx, event.ID, "test error")
	assert.NoError(t, err)
	
	// Retry failed events
	retriedCount, err := repo.RetryFailedEvents(ctx, 5)
	assert.NoError(t, err)
	assert.Equal(t, 1, retriedCount)
	
	// Verify the event was marked as pending again
	var publishedStatus string
	err = db.QueryRow(ctx, 
		"SELECT published_status FROM domain_events WHERE id = $1",
		event.ID,
	).Scan(&publishedStatus)
	assert.NoError(t, err)
	assert.Equal(t, StatusPending, publishedStatus)
}

func TestOutboxRepository_GetOutboxStats(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	
	repo := NewOutboxRepository(db)
	ctx := context.Background()
	
	// Create test events
	events := []*DomainEvent{
		{
			EntityID:   "run-1",
			EntityType: EntityTypeRun,
			EventType:  EventRunCreated,
			EventData: EventData{
				ID:        "run-1",
				Status:    "pending",
				NewState:  map[string]interface{}{"run_id": "run-1"},
				CreatedBy: "user1",
			},
			Metadata:   EventMetadata{Source: "test"},
			CreatedBy: "user1",
		},
		{
			EntityID:   "run-2",
			EntityType: EntityTypeRun,
			EventType:  EventRunCompleted,
			EventData: EventData{
				ID:        "run-2",
				Status:    "completed",
				NewState:  map[string]interface{}{"run_id": "run-2"},
				CreatedBy: "user2",
			},
			Metadata:   EventMetadata{Source: "test"},
			CreatedBy: "user2",
		},
	}
	
	for _, event := range events {
		err := repo.CreateEvent(ctx, event)
		assert.NoError(t, err)
	}
	
	// Get one event and mark it as published
	repo.MarkEventPublished(ctx, events[0].ID)
	
	// Get stats
	stats, err := repo.GetOutboxStats(ctx)
	assert.NoError(t, err)
	assert.Equal(t, 2, stats.TotalEvents)
	assert.Equal(t, 1, stats.PendingEvents)
	assert.Equal(t, 1, stats.PublishedEvents)
	assert.Equal(t, 0, stats.FailedEvents)
	assert.Greater(t, stats.PendingRatio, 0.0)
}

// Test the EventManager integration
func TestEventManager_ExecuteTransaction(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	
	eventManager := NewEventManager(db)
	ctx := context.Background()
	
	// Test that events are created atomically within a transaction
	err := eventManager.ExecuteTransaction(ctx, db, func(ctx context.Context, tx pgx.Tx) error {
		// This should fail, demonstrating atomicity
		// Create an event, then return an error to rollback
		
		event := &DomainEvent{
			EntityID:   "transaction-test",
			EntityType: EntityTypeRun,
			EventType:  EventRunCreated,
			EventData: EventData{
				ID:        "transaction-test",
				Status:    "pending",
				NewState:  map[string]interface{}{"run_id": "transaction-test"},
				CreatedBy: "test-user",
			},
			Metadata:   EventMetadata{Source: "test"},
			CreatedBy: "test-user",
		}
		
		repo := NewOutboxRepository(db) // Note: using the pool, not tx for this test
		if err := repo.CreateEvent(ctx, event); err != nil {
			return err
		}
		
		// Return an error to trigger rollback
		return fmt.Errorf("intentional error")
	})
	
	// The error should be propagated
	assert.Error(t, err)
	
	// Verify no event was created (due to rollback)
	var count int
	err = db.QueryRow(ctx, "SELECT COUNT(*) FROM domain_events").Scan(&count)
	assert.NoError(t, err)
	assert.Equal(t, 0, count)
}

func TestEventManager_RunEvents(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	
	eventManager := NewEventManager(db)
	ctx := context.Background()
	
	// Test RunCreated event
	err := eventManager.RunEvents.RunCreated(ctx, "run-1", "pending", "test-user", EventMetadata{
		Source:  "test",
		Project: "test-project",
		Squad:   "test-squad",
	})
	assert.NoError(t, err)
	
	// Verify the event was created
	var count int
	err = db.QueryRow(ctx, "SELECT COUNT(*) FROM domain_events").Scan(&count)
	assert.NoError(t, err)
	assert.Equal(t, 1, count)
	
	// Test RunUpdated event
	err = eventManager.RunEvents.RunUpdated(ctx, "run-1", "pending", "running", "test-user", EventMetadata{
		Source:  "test",
		Project: "test-project",
		Squad:   "test-squad",
	})
	assert.NoError(t, err)
	
	// Verify the second event was created
	err = db.QueryRow(ctx, "SELECT COUNT(*) FROM domain_events").Scan(&count)
	assert.NoError(t, err)
	assert.Equal(t, 2, count)
}

func TestEventSubjectGeneration(t *testing.T) {
	testCases := []struct {
		eventType    EventType
		entityType   EntityType
		project      string
		squad        string
		expected     string
	}{
		{
			eventType:    EventRunCreated,
			entityType:   EntityTypeRun,
			project:      "default",
			squad:        "team",
			expected:     "ksquad.run.default.team.run.created",
		},
		{
			eventType:    EventWorkItemUpdated,
			entityType:   EntityTypeWorkItem,
			project:      "project-x",
			squad:        "squad-y",
			expected:     "ksquad.work-item.project-x.squad-y.work-item.updated",
		},
		{
			eventType:    EventClaimCreated,
			entityType:   EntityTypeClaim,
			project:      "default",
			squad:        "team",
			expected:     "ksquad.claim.default.team.claim.created",
		},
		{
			eventType:    EventArtifactCreated,
			entityType:   EntityTypeArtifact,
			project:      "project-z",
			squad:        "squad-w",
			expected:     "ksquad.artifact.project-z.squad-w.artifact.created",
		},
	}
	
	for _, tc := range testCases {
		result := fmt.Sprintf("%s.%s.%s.%s.%s", 
			"ksquad",
			tc.entityType,
			tc.project,
			tc.squad,
			tc.eventType,
		)
		assert.Equal(t, tc.expected, result, "Subject generation failed for %+v", tc)
	}
}

// Benchmark tests
func BenchmarkOutboxRepository_CreateEvent(b *testing.B) {
	db := setupTestDB(b)
	defer db.Close()
	
	repo := NewOutboxRepository(db)
	ctx := context.Background()
	
	event := &DomainEvent{
		EntityID:   "benchmark-run",
		EntityType: EntityTypeRun,
		EventType:  EventRunCreated,
		EventData: EventData{
			ID:        "benchmark-run",
			Status:    "pending",
			NewState:  map[string]interface{}{"run_id": "benchmark-run"},
			CreatedBy: "benchmark-user",
		},
		Metadata:   EventMetadata{Source: "benchmark"},
		CreatedBy: "benchmark-user",
	}
	
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		event.EntityID = fmt.Sprintf("benchmark-run-%d", i)
		repo.CreateEvent(ctx, event)
	}
}

func BenchmarkOutboxRepository_GetUnpublishedEvents(b *testing.B) {
	db := setupTestDB(b)
	defer db.Close()
	
	repo := NewOutboxRepository(db)
	ctx := context.Background()
	
	// Create 100 test events
	for i := 0; i < 100; i++ {
		event := &DomainEvent{
			EntityID:   fmt.Sprintf("benchmark-run-%d", i),
			EntityType: EntityTypeRun,
			EventType:  EventRunCreated,
			EventData: EventData{
				ID:        fmt.Sprintf("benchmark-run-%d", i),
				Status:    "pending",
				NewState:  map[string]interface{}{"run_id": fmt.Sprintf("benchmark-run-%d", i)},
				CreatedBy: "benchmark-user",
			},
			Metadata:   EventMetadata{Source: "benchmark"},
			CreatedBy: "benchmark-user",
		}
		repo.CreateEvent(ctx, event)
	}
	
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		repo.GetUnpublishedEvents(ctx, 10, 1440)
	}
}