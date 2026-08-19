# Domain Event Seam Integration Guide

This guide explains how to integrate the domain event seam (Postgres outbox + NATS relay) into the KSquad system.

## Architecture Overview

The domain event seam implements the **transactional outbox pattern** to ensure reliable event delivery:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   State Change  │───▶│  Postgres       │───▶│   NATS/JetStream│
│   (Write Path)  │    │   Outbox       │    │   Event Bus     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                               │
                               ▼
                          ┌─────────────────┐
                          │  Relay Worker   │
                          │ (Best-effort)   │
                          └─────────────────┘
```

## Key Principles

1. **Atomicity**: Events are written atomically with state changes in the same database transaction
2. **Decoupling**: The relay runs outside the write path and never blocks state changes
3. **Reliability**: At-least-once delivery with retry mechanism for failed events
4. **Observability**: OTel metrics for monitoring event flow and system health

## Integration Steps

### 1. Database Setup

Apply the outbox schema to your Postgres database:

```bash
psql -d ksquad -f database/schema/outbox.sql
```

### 2. Configuration

The relay is configured via Kubernetes ConfigMap with the following structure:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ksquad-event-relay-config
data:
  relay.natsUrl: "nats://ksquad-nats.ksquad-system.svc.cluster.local:4222"
  relay.jetstream: "true"
  relay.subjectPrefix: "ksquad"
  relay.batchSize: "100"
  relay.maxRetries: "5"
  relay.pollInterval: "5s"
  relay.gracefulShutdown: "30s"
  relay.enableMetrics: "true"
  relay.otlpExporterUrl: "http://otel-collector:4318"
```

### 3. Service Integration

#### For Run Operations

```go
// In your run controller or service
func (r *RunController) CreateRun(ctx context.Context, run *Run) error {
    return eventManager.ExecuteTransaction(ctx, r.db, func(ctx context.Context, tx pgx.Tx) error {
        // Create the run in the database
        if err := r.createRunInDB(ctx, tx, run); err != nil {
            return err
        }

        // Create the corresponding event (atomic)
        metadata := outbox.EventMetadata{
            Source:   "run-controller",
            Project:  run.Project,
            Squad:    run.Squad,
            Priority: "normal",
        }

        return runEvents.RunCreated(ctx, run.ID, run.Status, run.CreatedBy, metadata)
    })
}
```

#### For Work Item Operations

```go
func (w *WorkItemController) UpdateWorkItem(ctx context.Context, itemID string, updates map[string]interface{}) error {
    return eventManager.ExecuteTransaction(ctx, w.db, func(ctx context.Context, tx pgx.Tx) error {
        // Get current state
        oldItem, err := w.getWorkItem(ctx, tx, itemID)
        if err != nil {
            return err
        }

        // Update the work item
        if err := w.updateWorkItemInDB(ctx, tx, itemID, updates); err != nil {
            return err
        }

        // Create the event
        metadata := outbox.EventMetadata{
            Source:   "workitem-controller",
            Project:  oldItem.Project,
            Squad:    oldItem.Squad,
        }

        return workItemEvents.WorkItemUpdated(
            ctx, 
            itemID, 
            oldItem, 
            updates, 
            "system",
            metadata,
        )
    })
}
```

#### For Claim Operations

```go
func (c *ClaimController) CreateClaim(ctx context.Context, claim *Claim) error {
    return eventManager.ExecuteTransaction(ctx, c.db, func(ctx context.Context, tx pgx.Tx) error {
        // Create the claim in the database
        if err := c.createClaimInDB(ctx, tx, claim); err != nil {
            return err
        }

        // Create the corresponding event
        metadata := outbox.EventMetadata{
            Source:   "claim-controller",
            Project:  claim.Project,
            Squad:    claim.Squad,
        }

        return claimEvents.ClaimCreated(ctx, claim.ID, claim.WorkItemID, claim.ClaimedBy, metadata)
    })
}
```

### 4. Relay Worker Deployment

Deploy the relay worker as a separate pod:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ksquad-event-relay
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ksquad-event-relay
  template:
    spec:
      containers:
      - name: relay
        image: ksquad/event-relay:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretRef:
              name: ksquad-db-credentials
        - name: NATS_URL
          value: "nats://ksquad-nats:4222"
        volumeMounts:
        - name: config
          mountPath: /etc/ksquad
      volumes:
      - name: config
        configMap:
          name: ksquad-event-relay-config
```

### 5. Monitoring and Observability

The relay provides OTel metrics for monitoring:

- `events.published`: Number of successfully published events
- `events.publish.errors`: Number of publishing errors
- `outbox.depth`: Current number of unpublished events
- `events.consumer.lag`: Number of events not yet consumed

#### Health Checks

```bash
# Check relay health
curl http://ksquad-event-relay:8080/health

# Get relay statistics
curl http://ksquad-event-relay:8080/stats
```

### 6. Event Schema

Events follow this subject taxonomy:

```
ksquad.{entity}.{project}.{squad}.{event_type}
```

Example subjects:
- `ksquad.run.default.squad.run.created`
- `ksquad.work-item.default.team.work-item.updated`
- `ksquad.clain.default.team.claim.created`
- `ksquad.artifact.default.team.artifact.created`

## Event Payload Structure

```json
{
  "event_id": "uuid",
  "event_type": "run.created",
  "entity_type": "run",
  "entity_id": "run-123",
  "data": {
    "id": "run-123",
    "status": "pending",
    "old_state": null,
    "new_state": {
      "run_id": "run-123",
      "status": "pending"
    },
    "created_by": "user",
    "timestamp": "2026-08-16T10:00:00Z"
  },
  "metadata": {
    "source": "run-controller",
    "project": "default",
    "squad": "team",
    "priority": "normal",
    "labels": {
      "environment": "production"
    }
  },
  "timestamp": "2026-08-16T10:00:00Z"
}
```

## Error Handling and Retries

The relay implements automatic retry logic:

- Failed events are retried up to `maxRetries` times
- After max retries, events remain marked as "failed" and require manual intervention
- The relay logs all errors for debugging

### Manual Recovery

For failed events, you can:

1. Check the failed events in the database:
```sql
SELECT * FROM domain_events 
WHERE published_status = 'failed' 
ORDER BY created_at DESC;
```

2. Retry failed events by updating their status:
```sql
UPDATE domain_events 
SET published_status = 'pending', error_message = NULL
WHERE published_status = 'failed' 
AND published_attempts < 5;
```

## Performance Considerations

1. **Batch Processing**: Events are processed in batches to optimize performance
2. **Connection Pooling**: The relay uses connection pooling for database and NATS connections
3. **Parallel Processing**: Multiple events are processed concurrently (limited by semaphore)
4. **Polling Interval**: Adjust based on your event volume and latency requirements

## Security Considerations

1. **Network Security**: Use TLS for NATS connections in production
2. **Authentication**: Configure proper authentication for NATS and database
3. **Authorization**: Ensure proper RBAC for accessing event data
4. **Data Encryption**: Sensitive data in event payloads should be encrypted

## Troubleshooting

### Common Issues

1. **High Outbox Depth**: Increase polling interval or batch size
2. **Publishing Errors**: Check NATS connectivity and permissions
3. **Failed Events**: Review error messages and retry if necessary
4. **High Latency**: Monitor database and NATS performance

### Debug Commands

```bash
# Check database connection
psql -d ksquad -c "SELECT COUNT(*) FROM domain_events;"

# Check NATS connectivity
nats -s nats://ksquad-nats:4222 stream ls

# Check relay logs
kubectl logs ksquad-event-relay-pod
```

## Testing

### Unit Testing

```go
func TestEventCreation(t *testing.T) {
    db := setupTestDB(t)
    repo := NewOutboxRepository(db)
    publisher := NewEventPublisher(db)

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
    }

    err := publisher.repository.CreateEvent(context.Background(), event)
    assert.NoError(t, err)
    assert.NotEmpty(t, event.ID)
}
```

### Integration Testing

Use the provided integration test to validate the complete event flow:

```bash
go test ./internal/outbox -integration
```

## Migration Guide

### From Previous Event System

1. **Schema Migration**: Apply the new outbox schema
2. **Code Changes**: Replace existing event publishing with the new API
3. **Configuration**: Update NATS configuration for the new subject format
4. **Monitoring**: Update dashboards to track new metrics

### Rollback Plan

1. Keep the existing event system running in parallel
2. Deploy the new relay with dual publishing (both systems)
3. Gradually migrate event producers
4. Monitor both systems during transition
5. Remove the old system after validation