package outbox

import (
	"context"
	"log"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel"
)

// TestIntegration_EventFlow tests the complete event flow from creation to NATS publishing
func TestIntegration_EventFlow(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	ctx := context.Background()
	
	// Setup test database
	db := setupTestDB(t)
	defer db.Close()

	// Setup test NATS server
	natsURL := "nats://localhost:4222"
	
	// Connect to NATS
	nc, err := nats.Connect(natsURL)
	require.NoError(t, err)
	defer nc.Close()

	// Create JetStream context
	js, err := jetstream.New(nc)
	require.NoError(t, err)

	// Create test stream
	streamName := "test-events"
	streamConfig := jetstream.StreamConfig{
		Name:     streamName,
		Subjects: []string{"ksquad.>"},
		Storage:  jetstream.FileStorage,
	}

	stream, err := js.CreateStream(ctx, streamConfig)
	require.NoError(t, err)

	// Create event manager and relay
	eventManager := NewEventManager(db)

	config := RelayConfig{
		NATSURL:            natsURL,
		JetStreamEnabled:   true,
		SubjectPrefix:      "ksquad",
		BatchSize:         10,
		MaxRetries:        3,
		PollInterval:      100 * time.Millisecond, // Fast for testing
		GracefulShutdown:   1 * time.Second,
		EnableMetrics:     true,
	}

	relay, err := NewEventRelay(db, config)
	require.NoError(t, err)

	// Start the relay
	err = relay.Start()
	require.NoError(t, err)
	defer relay.Stop()

	// Create a test event
	t.Run("CreateRunEvent", func(t *testing.T) {
		err := eventManager.RunEvents.RunCreated(ctx, "integration-test-run-1", "pending", "test-user", EventMetadata{
			Source:  "integration-test",
			Project: "test-project",
			Squad:   "test-squad",
			Priority: "high",
		})
		assert.NoError(t, err)
	})

	// Wait for relay to process the event
	time.Sleep(200 * time.Millisecond)

	// Verify event was published
	t.Run("VerifyEventPublished", func(t *testing.T) {
		info, err := stream.Info(ctx)
		assert.NoError(t, err)
		assert.Greater(t, info.State.Msgs, uint64(0), "No messages found in stream")

		// Get the message
		consumer, err := stream.CreateOrUpdateConsumer(ctx, "test-consumer", jetstream.ConsumerConfig{
			DeliverPolicy: jetstream.DeliverAllPolicy,
		})
		assert.NoError(t, err)

		nextMsg, err := consumer.NextMsg(ctx, 100*time.Millisecond)
		require.NoError(t, err)
		defer nextMsg.Ack()

		// Verify the message structure
		var msg struct {
			EventID      string      `json:"event_id"`
			EventType    string      `json:"event_type"`
			EntityType   string      `json:"entity_type"`
			EntityID     string      `json:"entity_id"`
			Data         EventData   `json:"data"`
			Metadata     EventMetadata `json:"metadata"`
			Timestamp    time.Time   `json:"timestamp"`
		}

		err = json.Unmarshal(nextMsg.Data, &msg)
		assert.NoError(t, err)
		assert.Equal(t, "integration-test-run-1", msg.EntityID)
		assert.Equal(t, "run.created", msg.EventType)
		assert.Equal(t, "run", msg.EntityType)
		assert.Equal(t, "test-user", msg.Data.CreatedBy)
	})

	// Test multiple events
	t.Run("MultipleEvents", func(t *testing.T) {
		var wg sync.WaitGroup

		// Create multiple concurrent events
		for i := 0; i < 5; i++ {
			wg.Add(1)
			go func(i int) {
				defer wg.Done()
				
				err := eventManager.WorkItemEvents.WorkItemCreated(ctx, fmt.Sprintf("work-item-%d", i), "task", "test-user", EventMetadata{
					Source:  "integration-test",
					Project: "test-project",
					Squad:   "test-squad",
				})
				assert.NoError(t, err)
			}(i)
		}
		wg.Wait()

		// Wait for relay to process
		time.Sleep(300 * time.Millisecond)

		// Verify all messages were published
		info, err := stream.Info(ctx)
		assert.NoError(t, err)
		assert.GreaterOrEqual(t, info.State.Msgs, uint64(6), "Expected at least 6 messages (1 run + 5 work items)")
	})

	// Test event status updates in database
	t.Run("EventStatusInDB", func(t *testing.T) {
		// Create an event that will be processed
		err := eventManager.ClaimEvents.ClaimCreated(ctx, "test-claim-1", "test-work-item", "test-user", EventMetadata{
			Source:  "integration-test",
			Project: "test-project",
			Squad:   "test-squad",
		})
		assert.NoError(t, err)

		time.Sleep(200 * time.Millisecond)

		// Check that the event was marked as published
		repo := NewOutboxRepository(db)
		events, err := repo.GetUnpublishedEvents(ctx, 10, 1440)
		assert.NoError(t, err)
		
		// Should have no unpublished events since they all got published
		assert.Len(t, events, 0)
	})
}

// TestIntegration_RelayHealth tests the relay health monitoring
func TestIntegration_RelayHealth(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	ctx := context.Background()
	
	// Setup test database
	db := setupTestDB(t)
	defer db.Close()

	// Create event manager
	eventManager := NewEventManager(db)

	config := RelayConfig{
		NATSURL:            "nats://localhost:4222", // This will fail, testing health check
		JetStreamEnabled:   true,
		SubjectPrefix:      "ksquad",
		BatchSize:         10,
		MaxRetries:        3,
		PollInterval:      100 * time.Millisecond,
		GracefulShutdown:   1 * time.Second,
		EnableMetrics:     true,
	}

	relay, err := NewEventRelay(db, config)
	require.NoError(t, err)

	// Start the relay (should fail to connect to NATS)
	err = relay.Start()
	assert.NoError(t, err) // Start should not fail, it will try to connect continuously
	defer relay.Stop()

	// Wait a bit for connection attempts
	time.Sleep(500 * time.Millisecond)

	// Test health check (should show degraded state due to NATS connection failure)
	health, err := relay.HealthCheck(ctx)
	assert.NoError(t, err)
	assert.Equal(t, "unhealthy", health.Status)
	assert.Contains(t, health.Message, "NATS connected")
	assert.Equal(t, false, health.Stats.NATSConnected)

	// Test stats retrieval
	stats, err := relay.GetStats(ctx)
	assert.NoError(t, err)
	assert.NotNil(t, stats)
	assert.Greater(t, stats.OutboxStats.TotalEvents, 0)
	assert.Equal(t, false, stats.NATSConnected)
}

// TestIntegration_RetryLogic tests the event retry mechanism
func TestIntegration_RetryLogic(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	ctx := context.Background()
	
	// Setup test database
	db := setupTestDB(t)
	defer db.Close()

	// Create event manager
	eventManager := NewEventManager(db)

	config := RelayConfig{
		NATSURL:            "nats://localhost:4222", // Invalid URL for testing retries
		JetStreamEnabled:   true,
		SubjectPrefix:      "ksquad",
		BatchSize:         10,
		MaxRetries:        5,
		PollInterval:      100 * time.Millisecond,
		GracefulShutdown:   1 * time.Second,
		EnableMetrics:     true,
	}

	relay, err := NewEventRelay(db, config)
	require.NoError(t, err)

	// Start the relay
	err = relay.Start()
	assert.NoError(t, err)
	defer relay.Stop()

	// Create an event that will fail to publish
	err = eventManager.RunEvents.RunCreated(ctx, "retry-test-run", "pending", "test-user", EventMetadata{
		Source:  "integration-test",
		Project: "test-project",
		Squad:   "test-squad",
	})
	assert.NoError(t, err)

	// Wait for processing attempts
	time.Sleep(2 * time.Second)

	// Check that the event is marked as failed after max retries
	repo := NewOutboxRepository(db)
	events, err := repo.GetUnpublishedEvents(ctx, 10, 1440)
	assert.NoError(t, err)
	
	// Should find the event as failed but not retried beyond max
	var failedEvents []DomainEvent
	for _, event := range events {
		if event.PublishedStatus == StatusFailed {
			failedEvents = append(failedEvents, event)
		}
	}
	
	assert.Len(t, failedEvents, 1)
	assert.GreaterOrEqual(t, failedEvents[0].PublishedAttempts, 5) // Should have reached max retries
}

// BenchmarkIntegration tests performance under load
func BenchmarkIntegration_EventFlow(b *testing.B) {
	if testing.Short() {
		b.Skip("Skipping integration benchmark in short mode")
	}

	ctx := context.Background()
	
	// Setup test database
	db := setupTestDB(b)
	defer db.Close()

	// Setup test NATS server
	natsURL := "nats://localhost:4222"
	
	nc, err := nats.Connect(natsURL)
	require.NoError(b, err)
	defer nc.Close()

	js, err := jetstream.New(nc)
	require.NoError(b, err)

	streamName := "benchmark-events"
	streamConfig := jetstream.StreamConfig{
		Name:     streamName,
		Subjects: []string{"ksquad.>"},
		Storage:  jetstream.MemoryStorage,
	}

	stream, err := js.CreateStream(ctx, streamConfig)
	require.NoError(b, err)

	eventManager := NewEventManager(db)

	config := RelayConfig{
		NATSURL:            natsURL,
		JetStreamEnabled:   true,
		SubjectPrefix:      "ksquad",
		BatchSize:         50,
		MaxRetries:        3,
		PollInterval:      50 * time.Millisecond,
		GracefulShutdown:   1 * time.Second,
		EnableMetrics:     false, // Disable metrics for benchmark
	}

	relay, err := NewEventRelay(db, config)
	require.NoError(b, err)

	err = relay.Start()
	require.NoError(b, err)
	defer relay.Stop()

	b.ResetTimer()

	// Benchmark event creation and processing
	b.RunParallel(func(pb *testing.PB) {
		i := 0
		for pb.Next() {
			err := eventManager.RunEvents.RunCreated(ctx, fmt.Sprintf("benchmark-run-%d", i), "pending", "benchmark-user", EventMetadata{
				Source:  "benchmark",
				Project: "benchmark-project",
				Squad:   "benchmark-squad",
			})
			if err != nil {
				b.Errorf("Failed to create event: %v", err)
			}
			i++
		}
	})

	// Allow time for processing
	time.Sleep(1 * time.Second)

	// Verify all events were processed
	info, err := stream.Info(ctx)
	require.NoError(b, err)
	assert.Equal(b, uint64(b.N), info.State.Msgs, "Expected all benchmark events to be processed")
}

func setupTestDB(t testing.TB) *pgxpool.Pool {
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