-- Domain Event Seam Schema for Story 12.1: Postgres outbox + NATS relay
-- This schema implements the transactional outbox pattern for reliable event delivery.

-- Enable UUID extension for generating unique event IDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Domain events table (transactional outbox)
-- Events are written atomically with state changes in the same transaction
CREATE TABLE domain_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id VARCHAR(255) NOT NULL,        -- ID of the entity being changed (e.g., run_id, work_item_id)
    entity_type VARCHAR(100) NOT NULL,     -- Type of entity (run, work_item, claim, etc.)
    event_type VARCHAR(100) NOT NULL,      -- Type of event (created, updated, deleted, claimed, etc.)
    event_data JSONB NOT NULL,             -- Event payload with before/after state
    metadata JSONB,                        -- Additional metadata (timestamp, user, etc.)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,             -- When the event was published to NATS
    published_attempts INTEGER DEFAULT 0,   -- Number of publishing attempts
    published_status VARCHAR(20) DEFAULT 'pending', -- pending, published, failed
    error_message TEXT,                   -- Last error message if publishing failed
    created_by VARCHAR(100),               -- Who/what created the event (system, user, etc.)
    version INTEGER DEFAULT 1             -- Event version for schema evolution
);

-- Indexes for efficient querying and relay performance
CREATE INDEX idx_domain_events_entity_id ON domain_events(entity_id);
CREATE INDEX idx_domain_events_entity_type ON domain_events(entity_type);
CREATE INDEX idx_domain_events_event_type ON domain_events(event_type);
CREATE INDEX idx_domain_events_created_at ON domain_events(created_at);
CREATE INDEX idx_domain_events_published_status ON domain_events(published_status);
CREATE INDEX idx_domain_events_published_attempts ON domain_events(published_attempts);

-- Index for finding unpublished events (main query for relay worker)
CREATE INDEX idx_domain_events_unpublished ON domain_events(published_status, created_at) 
WHERE published_status = 'pending' OR (published_status = 'failed' AND published_attempts < 5);

-- Function to create domain events (called from application code)
-- This function ensures events are created atomically with state changes
CREATE OR REPLACE FUNCTION create_domain_event(
    p_entity_id VARCHAR(255),
    p_entity_type VARCHAR(100),
    p_event_type VARCHAR(100),
    p_event_data JSONB,
    p_metadata JSONB DEFAULT '{}',
    p_created_by VARCHAR(100) DEFAULT 'system'
) RETURNS UUID AS $$
DECLARE
    event_id UUID;
BEGIN
    INSERT INTO domain_events (
        entity_id, 
        entity_type, 
        event_type, 
        event_data, 
        metadata, 
        created_by
    ) VALUES (
        p_entity_id, 
        p_entity_type, 
        p_event_type, 
        p_event_data, 
        p_metadata, 
        p_created_by
    ) RETURNING id INTO event_id;
    
    RETURN event_id;
END;
$$ LANGUAGE plpgsql;

-- Function to mark events as published (called by relay worker)
CREATE OR REPLACE FUNCTION mark_event_published(p_id UUID) RETURNS VOID AS $$
BEGIN
    UPDATE domain_events 
    SET 
        published_at = now(),
        published_status = 'published',
        published_attempts = published_attempts + 1
    WHERE id = p_id;
END;
$$ LANGUAGE plpgsql;

-- Function to retry failed events
CREATE OR REPLACE FUNCTION retry_failed_events(p_max_attempts INTEGER DEFAULT 5) RETURNS INTEGER AS $$
DECLARE
    retried_count INTEGER := 0;
BEGIN
    UPDATE domain_events
    SET 
        published_attempts = published_attempts + 1,
        published_status = 'pending',
        error_message = NULL
    WHERE 
        published_status = 'failed' 
        AND published_attempts < p_max_attempts;
    
    GET DIAGNOSTICS retried_count = ROW_COUNT;
    RETURN retried_count;
END;
$$ LANGUAGE plpgsql;

-- Function to get unpublished events for relay worker
-- Supports pagination for large outbox tables
CREATE OR REPLACE FUNCTION get_unpublished_events(
    p_batch_size INTEGER DEFAULT 100,
    p_max_age_minutes INTEGER DEFAULT 1440 -- 24 hours
) RETURNS TABLE (
    id UUID,
    entity_id VARCHAR(255),
    entity_type VARCHAR(100),
    event_type VARCHAR(100),
    event_data JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    version INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        id,
        entity_id,
        entity_type,
        event_type,
        event_data,
        metadata,
        created_at,
        created_by,
        version
    FROM domain_events
    WHERE 
        (published_status = 'pending' 
         OR (published_status = 'failed' AND published_attempts < 5))
        AND created_at > now() - INTERVAL '1 minute' * p_max_age_minutes
    ORDER BY created_at ASC
    LIMIT p_batch_size;
END;
$$ LANGUAGE plpgsql;

-- Create sequence for event relays (for multiple relay instances)
CREATE TABLE IF NOT EXISTS event_relay_sequences (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    relay_id VARCHAR(100) NOT NULL,
    last_event_id UUID NOT NULL,
    last_processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(relay_id)
);

-- View for monitoring outbox health
CREATE OR REPLACE VIEW outbox_health_stats AS
SELECT 
    COUNT(*) as total_events,
    COUNT(CASE WHEN published_status = 'pending' THEN 1 END) as pending_events,
    COUNT(CASE WHEN published_status = 'published' THEN 1 END) as published_events,
    COUNT(CASE WHEN published_status = 'failed' THEN 1 END) as failed_events,
    COUNT(CASE WHEN published_attempts >= 5 THEN 1 END) as max_retry_events,
    MAX(created_at) as newest_event,
    MIN(created_at) as oldest_event
FROM domain_events;

-- Permissions (adjust based on your security requirements)
GRANT SELECT, INSERT, UPDATE ON domain_events TO ksquad_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO ksquad_user;

-- Initial data for event types (for reference)
INSERT INTO domain_events (entity_id, entity_type, event_type, event_data, metadata, created_by)
VALUES 
    ('demo-run-1', 'run', 'created', 
     '{"run_id": "demo-run-1", "status": "pending", "created_by": "user"}',
     '{"source": "demo", "priority": "normal"}',
     'system')
ON CONFLICT (entity_id) DO NOTHING;