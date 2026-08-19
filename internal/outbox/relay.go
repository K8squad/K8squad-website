package outbox

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/metric/global"
	"go.opentelemetry.io/otel/trace"
)

// RelayConfig contains configuration for the event relay worker
type RelayConfig struct {
	NATSURL            string        `json:"natsUrl"`
	JetStreamEnabled   bool          `json:"jetstream"`
	SubjectPrefix      string        `json:"subjectPrefix"`
	BatchSize          int           `json:"batchSize"`
	MaxRetries         int           `json:"maxRetries"`
	PollInterval       time.Duration `json:"pollInterval"`
	GracefulShutdown   time.Duration `json:"gracefulShutdown"`
	EnableMetrics      bool          `json:"enableMetrics"`
	OTLPExporterURL    string        `json:"otlpExporterUrl,omitempty"`
}

// EventRelay handles publishing events from the outbox to NATS/JetStream
type EventRelay struct {
	config         RelayConfig
	repository     *OutboxRepository
	natsConn       *nats.Conn
	jsContext      jetstream.JetStream
	ctx            context.Context
	cancel         context.CancelFunc
	wg             sync.WaitGroup
	meter          metric.Meter
	tracer         trace.Tracer
	eventPublished metric.Int64Counter
	publishErrors  metric.Int64Counter
	outboxDepth    metric.Int64UpDownCounter
	consumerLag    metric.Int64UpDownCounter
}

// NewEventRelay creates a new event relay instance
func NewEventRelay(db *pgxpool.Pool, config RelayConfig) (*EventRelay, error) {
	ctx, cancel := context.WithCancel(context.Background())

	// Initialize OpenTelemetry
	meter := global.Meter("ksquad-event-relay")
	tracer := otel.Tracer("ksquad-event-relay")

	// Create metrics
	eventPublished, err := meter.Int64Counter(
		"events.published",
		metric.WithDescription("Number of events successfully published to NATS"),
	)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to create event published counter: %w", err)
	}

	publishErrors, err := meter.Int64Counter(
		"events.publish.errors",
		metric.WithDescription("Number of event publishing errors"),
	)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to create publish errors counter: %w", err)
	}

	outboxDepth, err := meter.Int64UpDownCounter(
		"outbox.depth",
		metric.WithDescription("Current number of events waiting to be published"),
	)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to create outbox depth counter: %w", err)
	}

	consumerLag, err := meter.Int64UpDownCounter(
		"events.consumer.lag",
		metric.WithDescription("Number of events published but not yet consumed by subscribers"),
	)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to create consumer lag counter: %w", err)
	}

	repository := NewOutboxRepository(db)

	return &EventRelay{
		config:        config,
		repository:    repository,
		ctx:           ctx,
		cancel:        cancel,
		meter:         meter,
		tracer:        tracer,
		eventPublished: eventPublished,
		publishErrors:  publishErrors,
		outboxDepth:   outboxDepth,
		consumerLag:   consumerLag,
	}, nil
}

// Connect establishes connection to NATS/JetStream
func (r *EventRelay) Connect(ctx context.Context) error {
	// Connect to NATS
	nc, err := nats.Connect(r.config.NATSURL, nats.ReconnectWait(2*time.Second), nats.MaxReconnects(5))
	if err != nil {
		return fmt.Errorf("failed to connect to NATS: %w", err)
	}
	r.natsConn = nc

	// Create JetStream context
	if r.config.JetStreamEnabled {
		js, err := jetstream.New(nc)
		if err != nil {
			nc.Close()
			return fmt.Errorf("failed to create JetStream context: %w", err)
		}
		r.jsContext = js

		// Ensure stream exists for event publishing
		if err := r.ensureStream(ctx); err != nil {
			nc.Close()
			return fmt.Errorf("failed to ensure JetStream stream: %w", err)
		}
	}

	return nil
}

// ensureStream creates the JetStream stream for events if it doesn't exist
func (r *EventRelay) ensureStream(ctx context.Context) error {
	streamName := "ksquad-events"
	streamConfig := jetstream.StreamConfig{
		Name:     streamName,
	 Subjects: []string{r.config.SubjectPrefix + ".>"},
		Storage:  jetstream.FileStorage,
		Retention: jetstream.LimitsPolicyRetention,
		Discard:  jetstream.DiscardOld,
		Duplicates: 60 * time.Second,
	}

	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	// Create stream if it doesn't exist
	stream, err := r.jsContext.CreateStream(ctx, streamConfig)
	if err != nil {
		// Check if stream already exists
		if err := r.jsContext.StreamInfo(ctx, streamName); err != nil {
			return fmt.Errorf("failed to create stream: %w", err)
		}
	}

	log.Printf("JetStream stream %s ready", streamName)
	return nil
}

// Start begins the event relay worker
func (r *EventRelay) Start() error {
	if err := r.Connect(r.ctx); err != nil {
		return fmt.Errorf("failed to connect: %w", err)
	}

	log.Printf("Event relay started with config: %+v", r.config)

	r.wg.Add(1)
	go r.runRelayLoop()

	return nil
}

// Stop gracefully stops the event relay worker
func (r *EventRelay) Stop() {
	log.Println("Stopping event relay...")

	r.cancel()

	// Wait for graceful shutdown
	done := make(chan struct{})
	go func() {
		r.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		log.Println("Event relay stopped gracefully")
	case <-time.After(r.config.GracefulShutdown):
		log.Println("Event relay forced shutdown after timeout")
	}

	if r.natsConn != nil {
		r.natsConn.Close()
	}
}

// runRelayLoop is the main loop for processing events
func (r *EventRelay) runRelayLoop() {
	defer r.wg.Done()

	ticker := time.NewTicker(r.config.PollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-r.ctx.Done():
			return
		case <-ticker.C:
			if err := r.processEvents(); err != nil {
				log.Printf("Error processing events: %v", err)
				r.publishErrors.Add(r.ctx, 1)
			}
		}
	}
}

// processEvents retrieves and publishes pending events
func (r *EventRelay) processEvents() error {
	ctx, span := r.tracer.Start(r.ctx, "processEvents")
	defer span.End()

	// Get unpublished events
	events, err := r.repository.GetUnpublishedEvents(ctx, r.config.BatchSize, 1440) // 24 hours max age
	if err != nil {
		span.SetStatus(codes.Error, "failed to get unpublished events")
		return fmt.Errorf("failed to get unpublished events: %w", err)
	}

	if len(events) == 0 {
		return nil
	}

	span.AddEvent("events retrieved", trace.WithAttributes(
		attribute.Int("count", len(events)),
	))

	// Update outbox depth metric
	r.outboxDepth.Add(ctx, int64(len(events)))

	// Process events in batches
	var wg sync.WaitGroup
	semaphore := make(chan struct{}, 10) // Limit concurrent publishing

	for _, event := range events {
		wg.Add(1)
		go func(e DomainEvent) {
			defer wg.Done()
			
			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			if err := r.publishEvent(ctx, e); err != nil {
				log.Printf("Failed to publish event %s: %v", e.ID, err)
				r.publishErrors.Add(ctx, 1)
			} else {
				r.eventPublished.Add(ctx, 1)
			}
		}(event)
	}

	wg.Wait()

	span.AddEvent("events processed", trace.WithAttributes(
		attribute.Int("published", int(r.eventPublished.Load(ctx))),
		attribute.Int("errors", int(r.publishErrors.Load(ctx))),
	))

	return nil
}

// publishEvent publishes a single event to NATS/JetStream
func (r *EventRelay) publishEvent(ctx context.Context, event DomainEvent) error {
	ctx, span := r.tracer.Start(ctx, "publishEvent", trace.WithAttributes(
		attribute.String("event_id", event.ID),
		attribute.String("entity_type", string(event.EntityType)),
		attribute.String("event_type", string(event.EventType)),
	))
	defer span.End()

	subject := fmt.Sprintf("%s.%s.%s.%s.%s", 
		r.config.SubjectPrefix,
		event.EntityType,
		event.Metadata.Project,
		event.Metadata.Squad,
		event.EventType,
	)

	var msg []byte
	if r.config.JetStreamEnabled {
		// Create structured message for JetStream
		jetstreamMsg := struct {
			EventID      string      `json:"event_id"`
			EventType    string      `json:"event_type"`
			EntityType    string      `json:"entity_type"`
			EntityID     string      `json:"entity_id"`
			Data         EventData   `json:"data"`
			Metadata     EventMetadata `json:"metadata"`
			Timestamp    time.Time   `json:"timestamp"`
			Sequence     int64       `json:"sequence"`
		}{
			EventID:      event.ID,
			EventType:    string(event.EventType),
			EntityType:   string(event.EntityType),
			EntityID:     event.EntityID,
			Data:         event.EventData,
			Metadata:     event.Metadata,
			Timestamp:    event.CreatedAt,
		}

		var err error
		msg, err = json.Marshal(jetstreamMsg)
		if err != nil {
			span.SetStatus(codes.Error, "failed to marshal message")
			return fmt.Errorf("failed to marshal message: %w", err)
		}
	} else {
		// Simple message for basic NATS
		var err error
		msg, err = json.Marshal(event)
		if err != nil {
			span.SetStatus(codes.Error, "failed to marshal message")
			return fmt.Errorf("failed to marshal message: %w", err)
		}
	}

	var jetstreamMsg jetstream.Msg
	if r.config.JetStreamEnabled {
		// Publish to JetStream
		jsMsg, err := r.jsContext.PublishMsg(ctx, &jetstreamMsg{
			Subject: subject,
			Header:  nats.Header{},
			Payload: msg,
		})
		if err != nil {
			span.SetStatus(codes.Error, "failed to publish to JetStream")
			return fmt.Errorf("failed to publish to JetStream: %w", err)
		}

		// Update consumer lag metric
		r.consumerLag.Add(ctx, 1)
		
		span.AddEvent("published to JetStream", trace.WithAttributes(
			attribute.String("subject", subject),
			attribute.String("sequence", jsMsg.Sequence.String()),
		))
	} else {
		// Publish to basic NATS
		if err := r.natsConn.Publish(subject, msg); err != nil {
			span.SetStatus(codes.Error, "failed to publish to NATS")
			return fmt.Errorf("failed to publish to NATS: %w", err)
		}

		span.AddEvent("published to NATS", trace.WithAttributes(
			attribute.String("subject", subject),
		))
	}

	// Mark event as published in database
	if err := r.repository.MarkEventPublished(ctx, event.ID); err != nil {
		span.SetStatus(codes.Error, "failed to mark event as published")
		log.Printf("Failed to mark event %s as published: %v", event.ID, err)
	}

	span.SetStatus(codes.Ok, "event published successfully")
	return nil
}

// GetStats returns current relay statistics
func (r *EventRelay) GetStats(ctx context.Context) (*RelayStats, error) {
	stats, err := r.repository.GetOutboxStats(ctx)
	if err != nil {
		return nil, err
	}

	return &RelayStats{
		OutboxStats:      *stats,
		NATSConnected:    r.natsConn != nil && r.natsConn.IsConnected(),
		JetStreamEnabled: r.config.JetStreamEnabled,
	}, nil
}

// RelayStats contains current relay statistics
type RelayStats struct {
	OutboxStats      OutboxStats `json:"outbox_stats"`
	NATSConnected    bool        `json:"nats_connected"`
	JetStreamEnabled bool        `json:"jetstream_enabled"`
}

// HealthCheck performs a health check of the relay
func (r *EventRelay) HealthCheck(ctx context.Context) (*HealthStatus, error) {
	stats, err := r.GetStats(ctx)
	if err != nil {
		return &HealthStatus{
			Status:  "unhealthy",
			Message: fmt.Sprintf("Failed to get stats: %v", err),
		}, err
	}

	healthy := stats.NATSConnected && (stats.OutboxStats.FailedEvents == 0 || stats.OutboxStats.FailedEvents < 10)
	
	status := "healthy"
	if !healthy {
		status = "unhealthy"
	}

	return &HealthStatus{
		Status:    status,
		Message:   "Relay is operational",
		Stats:     stats,
		Timestamp: time.Now(),
	}, nil
}

// HealthStatus represents the health status of the relay
type HealthStatus struct {
	Status    string           `json:"status"`
	Message   string           `json:"message"`
	Stats     *RelayStats      `json:"stats,omitempty"`
	Timestamp time.Time        `json:"timestamp"`
}