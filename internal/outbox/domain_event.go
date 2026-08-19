package outbox

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// EventType represents different types of domain events
type EventType string

const (
	EventRunCreated      EventType = "run.created"
	EventRunUpdated      EventType = "run.updated"
	EventRunCompleted    EventType = "run.completed"
	EventRunFailed      EventType = "run.failed"
	EventWorkItemCreated EventType = "work_item.created"
	EventWorkItemUpdated EventType = "work_item.updated"
	EventClaimCreated   EventType = "claim.created"
	EventClaimReleased  EventType = "claim.released"
	EventArtifactCreated EventType = "artifact.created"
)

// EntityType represents the different entity types that can generate events
type EntityType string

const (
	EntityTypeRun       EntityType = "run"
	EntityTypeWorkItem  EntityType = "work_item"
	EntityTypeClaim     EntityType = "claim"
	EntityTypeArtifact  EntityType = "artifact"
)

// EventStatus represents the publishing status of an event
type EventStatus string

const (
	StatusPending  EventStatus = "pending"
	StatusPublished EventStatus = "published"
	StatusFailed   EventStatus = "failed"
)

// EventData represents the event payload
type EventData struct {
	ID          string      `json:"id"`
	Status      string      `json:"status"`
	OldState    interface{} `json:"old_state,omitempty"`
	NewState    interface{} `json:"new_state"`
	CreatedBy   string      `json:"created_by"`
	Timestamp   time.Time   `json:"timestamp"`
}

// EventMetadata contains additional metadata about the event
type EventMetadata struct {
	Source      string            `json:"source"`
	Project     string            `json:"project,omitempty"`
	Squad       string            `json:"squad,omitempty"`
	Priority    string            `json:"priority,omitempty"`
	Labels      map[string]string `json:"labels,omitempty"`
	Tags        []string          `json:"tags,omitempty"`
}

// DomainEvent represents a domain event in the outbox
type DomainEvent struct {
	ID             string        `json:"id"`
	EntityID       string        `json:"entity_id"`
	EntityType     EntityType     `json:"entity_type"`
	EventType      EventType      `json:"event_type"`
	EventData      EventData      `json:"event_data"`
	Metadata       EventMetadata  `json:"metadata"`
	CreatedAt      time.Time      `json:"created_at"`
	PublishedAt    *time.Time     `json:"published_at,omitempty"`
	PublishedAttempts int         `json:"published_attempts"`
	PublishedStatus EventStatus   `json:"published_status"`
	ErrorMessage   *string       `json:"error_message,omitempty"`
	CreatedBy      string        `json:"created_by"`
	Version        int           `json:"version"`
}

// OutboxRepository handles database operations for the outbox pattern
type OutboxRepository struct {
	db *pgxpool.Pool
}

// NewOutboxRepository creates a new outbox repository
func NewOutboxRepository(db *pgxpool.Pool) *OutboxRepository {
	return &OutboxRepository{db: db}
}

// CreateEvent creates a new domain event in the outbox
// This function should be called within the same transaction as the state change
func (r *OutboxRepository) CreateEvent(ctx context.Context, event *DomainEvent) error {
	query := `
		INSERT INTO domain_events (
			entity_id, entity_type, event_type, event_data, metadata, created_by
		) VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING id, created_at
	`

	eventDataJSON, err := json.Marshal(event.EventData)
	if err != nil {
		return err
	}

	metadataJSON, err := json.Marshal(event.Metadata)
	if err != nil {
		return err
	}

	var id string
	var createdAt time.Time

	err = r.db.QueryRow(ctx, query,
		event.EntityID,
		event.EntityType,
		event.EventType,
		eventDataJSON,
		metadataJSON,
		event.CreatedBy,
	).Scan(&id, &createdAt)

	if err != nil {
		return err
	}

	event.ID = id
	event.CreatedAt = createdAt
	return nil
}

// GetUnpublishedEvents retrieves unpublished events for the relay worker
func (r *OutboxRepository) GetUnpublishedEvents(ctx context.Context, batchSize, maxAgeMinutes int) ([]DomainEvent, error) {
	query := `
		SELECT 
			id, entity_id, entity_type, event_type, 
			event_data, metadata, created_at, created_by, version
		FROM domain_events
		WHERE 
			(published_status = $1 
			 OR (published_status = $2 AND published_attempts < 5))
			AND created_at > now() - INTERVAL '1 minute' * $3
		ORDER BY created_at ASC
		LIMIT $4
	`

	rows, err := r.db.Query(ctx, query,
		StatusPending,
		StatusFailed,
		maxAgeMinutes,
		batchSize,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []DomainEvent
	for rows.Next() {
		var event DomainEvent
		var eventDataJSON, metadataJSON []byte
		var createdAt, publishedAt time.Time

		err := rows.Scan(
			&event.ID,
			&event.EntityID,
			&event.EntityType,
			&event.EventType,
			&eventDataJSON,
			&metadataJSON,
			&createdAt,
			&event.CreatedBy,
			&event.Version,
		)
		if err != nil {
			return nil, err
		}

		// Parse JSON fields
		err = json.Unmarshal(eventDataJSON, &event.EventData)
		if err != nil {
			return nil, err
		}

		err = json.Unmarshal(metadataJSON, &event.Metadata)
		if err != nil {
			return nil, err
		}

		event.CreatedAt = createdAt
		events = append(events, event)
	}

	return events, nil
}

// MarkEventPublished marks an event as successfully published
func (r *OutboxRepository) MarkEventPublished(ctx context.Context, eventID string) error {
	query := `
		UPDATE domain_events 
		SET 
			published_at = now(),
			published_status = $1,
			published_attempts = published_attempts + 1
		WHERE id = $2
	`

	cmd, err := r.db.Exec(ctx, query, StatusPublished, eventID)
	if err != nil {
		return err
	}

	if cmd.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}

	return nil
}

// MarkEventFailed marks an event as failed to publish
func (r *OutboxRepository) MarkEventFailed(ctx context.Context, eventID, errorMessage string) error {
	query := `
		UPDATE domain_events 
		SET 
			published_status = $1,
			published_attempts = published_attempts + 1,
			error_message = $2
		WHERE id = $3
	`

	cmd, err := r.db.Exec(ctx, query, StatusFailed, errorMessage, eventID)
	if err != nil {
		return err
	}

	if cmd.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}

	return nil
}

// RetryFailedEvents retries failed events that haven't exceeded max attempts
func (r *OutboxRepository) RetryFailedEvents(ctx context.Context, maxAttempts int) (int, error) {
	query := `
		UPDATE domain_events
		SET 
			published_status = $1,
			published_attempts = published_attempts + 1,
			error_message = NULL
		WHERE 
			published_status = $2 
			AND published_attempts < $3
	`

	cmd, err := r.db.Exec(ctx, query, StatusPending, StatusFailed, maxAttempts)
	if err != nil {
		return 0, err
	}

	return int(cmd.RowsAffected()), nil
}

// GetOutboxStats returns statistics about the outbox for monitoring
func (r *OutboxRepository) GetOutboxStats(ctx context.Context) (*OutboxStats, error) {
	query := `
		SELECT 
			COUNT(*) as total_events,
			COUNT(CASE WHEN published_status = $1 THEN 1 END) as pending_events,
			COUNT(CASE WHEN published_status = $2 THEN 1 END) as published_events,
			COUNT(CASE WHEN published_status = $3 THEN 1 END) as failed_events,
			COUNT(CASE WHEN published_attempts >= $4 THEN 1 END) as max_retry_events,
			MAX(created_at) as newest_event,
			MIN(created_at) as oldest_event
		FROM domain_events
	`

	var stats OutboxStats
	var newestEvent, oldestEvent *time.Time

	err := r.db.QueryRow(ctx, query,
		StatusPending,
		StatusPublished,
		StatusFailed,
		5, // max attempts
	).Scan(
		&stats.TotalEvents,
		&stats.PendingEvents,
		&stats.PublishedEvents,
		&stats.FailedEvents,
		&stats.MaxRetryEvents,
		&newestEvent,
		&oldestEvent,
	)

	if err != nil {
		return nil, err
	}

	stats.NewestEvent = newestEvent
	stats.OldestEvent = oldestEvent
	stats.PendingRatio = float64(stats.PendingEvents) / float64(stats.TotalEvents) if stats.TotalEvents > 0 else 0

	return &stats, nil
}

// OutboxStats contains statistics about the outbox
type OutboxStats struct {
	TotalEvents      int          `json:"total_events"`
	PendingEvents    int          `json:"pending_events"`
	PublishedEvents  int          `json:"published_events"`
	FailedEvents     int          `json:"failed_events"`
	MaxRetryEvents   int          `json:"max_retry_events"`
	PendingRatio     float64      `json:"pending_ratio"`
	NewestEvent      *time.Time   `json:"newest_event"`
	OldestEvent      *time.Time   `json:"oldest_event"`
}

// TransactionalEventer provides the interface for creating events within transactions
type TransactionalEventer interface {
	CreateEvent(ctx context.Context, event *DomainEvent) error
}

// ExecInTransaction executes a function within a database transaction
// and ensures events are created atomically with state changes
func ExecInTransaction(ctx context.Context, db *pgxpool.Pool, fn func(ctx context.Context, tx pgx.Tx) error) error {
	tx, err := db.Begin(ctx)
	if err != nil {
		return err
	}

	defer func() {
		if p := recover(); p != nil {
			tx.Rollback(ctx)
			panic(p) // re-panic
		}
	}()

	err = fn(ctx, tx)
	if err != nil {
		tx.Rollback(ctx)
		return err
	}

	return tx.Commit(ctx)
}