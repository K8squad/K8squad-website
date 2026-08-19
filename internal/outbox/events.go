package outbox

import (
	"context"
	"fmt"
	"time"

	"go.opentelemetry.io/otel"
)

// EventPublisher provides methods to create domain events
type EventPublisher struct {
	repository *OutboxRepository
}

// NewEventPublisher creates a new event publisher
func NewEventPublisher(db *pgxpool.Pool) *EventPublisher {
	return &EventPublisher{
		repository: NewOutboxRepository(db),
	}
}

// RunEvents events related to runs
type RunEvents struct {
	Publisher *EventPublisher
}

// RunCreated creates an event for when a run is created
func (r *RunEvents) RunCreated(ctx context.Context, runID string, status string, createdBy string, metadata EventMetadata) error {
	ctx, span := otel.Tracer("ksquad-events").Start(ctx, "RunCreated")
	defer span.End()

	event := &DomainEvent{
		EntityID:   runID,
		EntityType: EntityTypeRun,
		EventType:  EventRunCreated,
		EventData: EventData{
			ID:        runID,
			Status:    status,
			NewState:  map[string]interface{}{"run_id": runID, "status": status},
			CreatedBy: createdBy,
			Timestamp: time.Now(),
		},
		Metadata: metadata,
		CreatedBy: createdBy,
	}

	return r.Publisher.repository.CreateEvent(ctx, event)
}

// RunUpdated creates an event for when a run is updated
func (r *RunEvents) RunUpdated(ctx context.Context, runID string, oldStatus, newStatus string, createdBy string, metadata EventMetadata) error {
	ctx, span := otel.Tracer("ksquad-events").Start(ctx, "RunUpdated")
	defer span.End()

	event := &DomainEvent{
		EntityID:   runID,
		EntityType: EntityTypeRun,
		EventType:  EventRunUpdated,
		EventData: EventData{
			ID:        runID,
			Status:    newStatus,
			OldState:  map[string]interface{}{"status": oldStatus},
			NewState:  map[string]interface{}{"status": newStatus},
			CreatedBy: createdBy,
			Timestamp: time.Now(),
		},
		Metadata: metadata,
		CreatedBy: createdBy,
	}

	return r.Publisher.repository.CreateEvent(ctx, event)
}

// RunCompleted creates an event for when a run completes successfully
func (r *RunEvents) RunCompleted(ctx context.Context, runID string, result interface{}, createdBy string, metadata EventMetadata) error {
	ctx, span := otel.Tracer("ksquad-events").Start(ctx, "RunCompleted")
	defer span.End()

	event := &DomainEvent{
		EntityID:   runID,
		EntityType: EntityTypeRun,
		EventType:  EventRunCompleted,
		EventData: EventData{
			ID:        runID,
			Status:    "completed",
			NewState:  map[string]interface{}{"run_id": runID, "result": result},
			CreatedBy: createdBy,
			Timestamp: time.Now(),
		},
		Metadata: metadata,
		CreatedBy: createdBy,
	}

	return r.Publisher.repository.CreateEvent(ctx, event)
}

// RunFailed creates an event for when a run fails
func (r *RunEvents) RunFailed(ctx context.Context, runID string, error string, createdBy string, metadata EventMetadata) error {
	ctx, span := otel.Tracer("ksquad-events").Start(ctx, "RunFailed")
	defer span.End()

	event := &DomainEvent{
		EntityID:   runID,
		EntityType: EntityTypeRun,
		EventType:  EventRunFailed,
		EventData: EventData{
			ID:        runID,
			Status:    "failed",
			NewState:  map[string]interface{}{"run_id": runID, "error": error},
			CreatedBy: createdBy,
			Timestamp: time.Now(),
		},
		Metadata: metadata,
		CreatedBy: createdBy,
	}

	return r.Publisher.repository.CreateEvent(ctx, event)
}

// WorkItemEvents events related to work items
type WorkItemEvents struct {
	Publisher *EventPublisher
}

// WorkItemCreated creates an event for when a work item is created
func (w *WorkItemEvents) WorkItemCreated(ctx context.Context, itemID string, itemType string, createdBy string, metadata EventMetadata) error {
	ctx, span := otel.Tracer("ksquad-events").Start(ctx, "WorkItemCreated")
	defer span.End()

	event := &DomainEvent{
		EntityID:   itemID,
		EntityType: EntityTypeWorkItem,
		EventType:  EventWorkItemCreated,
		EventData: EventData{
			ID:        itemID,
			Status:    "created",
			NewState:  map[string]interface{}{"work_item_id": itemID, "type": itemType},
			CreatedBy: createdBy,
			Timestamp: time.Now(),
		},
		Metadata: metadata,
		CreatedBy: createdBy,
	}

	return w.Publisher.repository.CreateEvent(ctx, event)
}

// WorkItemUpdated creates an event for when a work item is updated
func (w *WorkItemEvents) WorkItemUpdated(ctx context.Context, itemID string, oldState, newState interface{}, createdBy string, metadata EventMetadata) error {
	ctx, span := otel.Tracer("ksquad-events").Start(ctx, "WorkItemUpdated")
	defer span.End()

	event := &DomainEvent{
		EntityID:   itemID,
		EntityType: EntityTypeWorkItem,
		EventType:  EventWorkItemUpdated,
		EventData: EventData{
			ID:        itemID,
			Status:    "updated",
			OldState:  oldState,
			NewState:  newState,
			CreatedBy: createdBy,
			Timestamp: time.Now(),
		},
		Metadata: metadata,
		CreatedBy: createdBy,
	}

	return w.Publisher.repository.CreateEvent(ctx, event)
}

// ClaimEvents events related to claims
type ClaimEvents struct {
	Publisher *EventPublisher
}

// ClaimCreated creates an event for when a claim is created
func (c *ClaimEvents) ClaimCreated(ctx context.Context, claimID string, workItemID string, claimedBy string, metadata EventMetadata) error {
	ctx, span := otel.Tracer("ksquad-events").Start(ctx, "ClaimCreated")
	defer span.End()

	event := &DomainEvent{
		EntityID:   claimID,
		EntityType: EntityTypeClaim,
		EventType:  EventClaimCreated,
		EventData: EventData{
			ID:        claimID,
			Status:    "created",
			NewState:  map[string]interface{}{"claim_id": claimID, "work_item_id": workItemID, "claimed_by": claimedBy},
			CreatedBy: claimedBy,
			Timestamp: time.Now(),
		},
		Metadata: metadata,
		CreatedBy: claimedBy,
	}

	return c.Publisher.repository.CreateEvent(ctx, event)
}

// ClaimReleased creates an event for when a claim is released
func (c *ClaimEvents) ClaimReleased(ctx context.Context, claimID string, workItemID string, releasedBy string, metadata EventMetadata) error {
	ctx, span := otel.Tracer("ksquad-events").Start(ctx, "ClaimReleased")
	defer span.End()

	event := &DomainEvent{
		EntityID:   claimID,
		EntityType: EntityTypeClaim,
		EventType:  EventClaimReleased,
		EventData: EventData{
			ID:        claimID,
			Status:    "released",
			NewState:  map[string]interface{}{"claim_id": claimID, "work_item_id": workItemID, "released_by": releasedBy},
			CreatedBy: releasedBy,
			Timestamp: time.Now(),
		},
		Metadata: metadata,
		CreatedBy: releasedBy,
	}

	return c.Publisher.repository.CreateEvent(ctx, event)
}

// ArtifactEvents events related to artifacts
type ArtifactEvents struct {
	Publisher *EventPublisher
}

// ArtifactCreated creates an event for when an artifact is created
func (a *ArtifactEvents) ArtifactCreated(ctx context.Context, artifactID string, artifactType string, runID string, createdBy string, metadata EventMetadata) error {
	ctx, span := otel.Tracer("ksquad-events").Start(ctx, "ArtifactCreated")
	defer span.End()

	event := &DomainEvent{
		EntityID:   artifactID,
		EntityType: EntityTypeArtifact,
		EventType:  EventArtifactCreated,
		EventData: EventData{
			ID:        artifactID,
			Status:    "created",
			NewState:  map[string]interface{}{"artifact_id": artifactID, "type": artifactType, "run_id": runID},
			CreatedBy: createdBy,
			Timestamp: time.Now(),
		},
		Metadata: metadata,
		CreatedBy: createdBy,
	}

	return a.Publisher.repository.CreateEvent(ctx, event)
}

// EventManager provides a unified interface for all event operations
type EventManager struct {
	RunEvents      *RunEvents
	WorkItemEvents *WorkItemEvents
	ClaimEvents    *ClaimEvents
	ArtifactEvents *ArtifactEvents
}

// NewEventManager creates a new event manager
func NewEventManager(db *pgxpool.Pool) *EventManager {
	publisher := NewEventPublisher(db)

	return &EventManager{
		RunEvents:      &RunEvents{Publisher: publisher},
		WorkItemEvents: &WorkItemEvents{Publisher: publisher},
		ClaimEvents:    &ClaimEvents{Publisher: publisher},
		ArtifactEvents: &ArtifactEvents{Publisher: publisher},
	}
}

// ExecuteTransaction executes a function within a database transaction
// and ensures events are created atomically with state changes
func (e *EventManager) ExecuteTransaction(ctx context.Context, db *pgxpool.Pool, fn func(ctx context.Context, tx pgx.Tx) error) error {
	return ExecInTransaction(ctx, db, fn)
}