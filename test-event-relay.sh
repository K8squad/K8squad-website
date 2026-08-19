#!/bin/bash

# Integration test script for the KSquad Event Relay
# This script tests the complete event flow from database to NATS

set -e

echo "🚀 Starting KSquad Event Relay Integration Test..."

# Configuration
NAMESPACE="ksquad-system"
RELAY_POD="ksquad-event-relay-"
NATS_POD="ksquad-nats-"
DATABASE_POD="ksquad-postgresql-"
TEST_TIMEOUT=120
RETRY_INTERVAL=5

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if we're in a Kubernetes cluster
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Not connected to a Kubernetes cluster"
        exit 1
    fi
    
    # Check if required pods are running
    if ! kubectl get pods -n "$NAMESPACE" | grep -q "$NATS_POD.*Running"; then
        log_error "NATS pod is not running in $NAMESPACE"
        exit 1
    fi
    
    if ! kubectl get pods -n "$NAMESPACE" | grep -q "$DATABASE_POD.*Running"; then
        log_error "Database pod is not running in $NAMESPACE"
        exit 1
    fi
    
    log_info "All prerequisites met"
}

wait_for_relay() {
    log_info "Waiting for event relay to be ready..."
    
    local timeout=$TEST_TIMEOUT
    while [ $timeout -gt 0 ]; do
        if kubectl get pods -n "$NAMESPACE" | grep "$RELAY_POD.*Running" >/dev/null 2>&1; then
            # Check if it's ready
            if kubectl exec -n "$NAMESPACE" "$RELAY_POD" -- curl -s http://localhost:8080/health | grep -q '"status":"healthy"'; then
                log_info "Event relay is healthy"
                return 0
            fi
        fi
        sleep 1
        timeout=$((timeout - 1))
    done
    
    log_error "Event relay did not become ready within $TEST_TIMEOUT seconds"
    return 1
}

test_database_connection() {
    log_info "Testing database connection..."
    
    # Create a test event directly in the database
    kubectl exec -n "$NAMESPACE" "$DATABASE_POD" -- psql -U postgres -d ksquad -c "
    CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";
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
    
    INSERT INTO domain_events (
        entity_id, entity_type, event_type, event_data, metadata, created_by
    ) VALUES (
        'test-event-1', 
        'run', 
        'run.created', 
        '{\"id\": \"test-event-1\", \"status\": \"pending\"}', 
        '{\"source\": \"test\", \"project\": \"test-project\"}', 
        'integration-test'
    );
    
    SELECT COUNT(*) FROM domain_events WHERE entity_id = 'test-event-1';
    " > /tmp/db_test.log 2>&1
    
    if [ $? -eq 0 ]; then
        local count=$(kubectl exec -n "$NAMESPACE" "$DATABASE_POD" -- psql -U postgres -d ksquad -t -c "SELECT COUNT(*) FROM domain_events WHERE entity_id = 'test-event-1';")
        if [ "$count" -eq "1" ]; then
            log_info "Database connection test passed"
            return 0
        fi
    fi
    
    log_error "Database connection test failed"
    cat /tmp/db_test.log
    return 1
}

test_nats_connection() {
    log_info "Testing NATS connection..."
    
    # Check if NATS is accessible
    if kubectl exec -n "$NAMESPACE" "$NATS_POD" -- nats -s "nats://localhost:4222" stream ls >/dev/null 2>&1; then
        log_info "NATS connection test passed"
        return 0
    else
        log_error "NATS connection test failed"
        return 1
    fi
}

test_relay_health() {
    log_info "Testing relay health endpoint..."
    
    local relay_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=event-relay -o jsonpath='{.items[0].metadata.name}')
    if [ -z "$relay_pod" ]; then
        log_error "No relay pod found"
        return 1
    fi
    
    local response=$(kubectl exec -n "$NAMESPACE" "$relay_pod" -- curl -s http://localhost:8080/health)
    if echo "$response" | grep -q '"status":"healthy"'; then
        log_info "Relay health check passed"
        return 0
    else
        log_error "Relay health check failed"
        echo "Response: $response"
        return 1
    fi
}

test_relay_stats() {
    log_info "Testing relay stats endpoint..."
    
    local relay_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=event-relay -o jsonpath='{.items[0].metadata.name}')
    if [ -z "$relay_pod" ]; then
        log_error "No relay pod found"
        return 1
    fi
    
    local response=$(kubectl exec -n "$NAMESPACE" "$relay_pod" -- curl -s http://localhost:8080/stats)
    if echo "$response" | grep -q '"outbox_stats"'; then
        log_info "Relay stats endpoint is working"
        echo "$response" | jq .
        return 0
    else
        log_error "Relay stats endpoint failed"
        echo "Response: $response"
        return 1
    fi
}

test_event_flow() {
    log_info "Testing complete event flow..."
    
    # Create a test event in the database
    kubectl exec -n "$NAMESPACE" "$DATABASE_POD" -- psql -U postgres -d ksquad -c "
    INSERT INTO domain_events (
        entity_id, entity_type, event_type, event_data, metadata, created_by
    ) VALUES (
        'flow-test-event', 
        'run', 
        'run.created', 
        '{\"id\": \"flow-test-event\", \"status\": \"pending\"}', 
        '{\"source\": \"integration-test\", \"project\": \"test-project\"}', 
        'integration-test'
    ) ON CONFLICT (entity_id) DO NOTHING;
    " > /tmp/flow_test.log 2>&1
    
    if [ $? -ne 0 ]; then
        log_error "Failed to create test event"
        cat /tmp/flow_test.log
        return 1
    fi
    
    # Wait for the relay to process the event
    log_info "Waiting for relay to process the event..."
    sleep 10
    
    # Check if the event was published to NATS
    if kubectl exec -n "$NAMESPACE" "$NATS_POD" -- nats -s "nats://localhost:4222" stream info ksquad-events >/dev/null 2>&1; then
        local msg_count=$(kubectl exec -n "$NAMESPACE" "$NATS_POD" -- nats -s "nats://localhost:4222" stream info ksquad-events --format json | jq '.state.msgs')
        if [ "$msg_count" -gt "0" ]; then
            log_info "Event flow test passed - $msg_count message(s) found in NATS stream"
            return 0
        fi
    fi
    
    log_error "Event flow test failed - no messages found in NATS stream"
    return 1
}

test_metrics_endpoint() {
    log_info "Testing metrics endpoint..."
    
    local relay_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=event-relay -o jsonpath='{.items[0].metadata.name}')
    if [ -z "$relay_pod" ]; then
        log_error "No relay pod found"
        return 1
    fi
    
    local response=$(kubectl exec -n "$NAMESPACE" "$relay_pod" -- curl -s http://localhost:8080/metrics)
    if echo "$response" | grep -q "events_published"; then
        log_info "Metrics endpoint is working"
        # Show a few key metrics
        echo "$response" | grep -E "(events_published|events_publish.errors|outbox_depth)"
        return 0
    else
        log_error "Metrics endpoint failed"
        echo "Response: $response"
        return 1
    fi
}

cleanup_test_data() {
    log_info "Cleaning up test data..."
    
    kubectl exec -n "$NAMESPACE" "$DATABASE_POD" -- psql -U postgres -d ksquad -c "
    DELETE FROM domain_events WHERE entity_id LIKE 'test-event%' OR entity_id = 'flow-test-event';
    " > /tmp/cleanup.log 2>&1
    
    if [ $? -eq 0 ]; then
        log_info "Test data cleaned up"
    else
        log_warn "Failed to clean up test data"
        cat /tmp/cleanup.log
    fi
}

generate_test_report() {
    log_info "Generating test report..."
    
    local report_file="/tmp/event-relay-test-report-$(date +%Y%m%d-%H%M%S).md"
    
    cat > "$report_file" << EOF
# KSquad Event Relay Integration Test Report

**Test Date:** $(date)
**Namespace:** $NAMESPACE
**Test Duration:** $TEST_TIMEOUT seconds

## Test Results

$(cat /tmp/test_results.log)

## Test Configuration

- Relay Image: ksquad/event-relay:latest
- NATS URL: nats://ksquad-nats.ksquad-system.svc.cluster.local:4222
- Database: PostgreSQL ksquad database
- Metrics Port: 8080

## Environment Information

$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/component in (event-relay,nats,postgresql)" -o wide)

## Logs

### Relay Logs
$(kubectl logs -n "$NAMESPACE" -l app.kubernetes.io/component=event-relay --tail=20)

### NATS Logs  
$(kubectl logs -n "$NAMESPACE" -l app.kubernetes.io/component=nats --tail=20)

### Database Logs
$(kubectl logs -n "$NAMESPACE" -l app.kubernetes.io/component=postgresql --tail=20)

EOF

    log_info "Test report generated: $report_file"
}

# Main test execution
main() {
    # Initialize test results
    > /tmp/test_results.log
    
    # Record start time
    local start_time=$(date +%s)
    
    # Run tests with error handling
    check_prerequisites || exit 1
    
    {
        test_database_connection
        echo "Database connection test: $?"
    } >> /tmp/test_results.log
    
    {
        test_nats_connection
        echo "NATS connection test: $?"
    } >> /tmp/test_results.log
    
    {
        wait_for_relay
        echo "Relay readiness test: $?"
    } >> /tmp/test_results.log
    
    {
        test_relay_health
        echo "Relay health test: $?"
    } >> /tmp/test_results.log
    
    {
        test_relay_stats
        echo "Relay stats test: $?"
    } >> /tmp/test_results.log
    
    {
        test_event_flow
        echo "Event flow test: $?"
    } >> /tmp/test_results.log
    
    {
        test_metrics_endpoint
        echo "Metrics test: $?"
    } >> /tmp/test_results.log
    
    # Clean up test data
    cleanup_test_data
    
    # Calculate total duration
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Generate report
    generate_test_report
    
    # Final results
    echo ""
    echo "==============================================="
    echo "📊 Integration Test Results"
    echo "==============================================="
    echo "🕒 Duration: ${duration}s"
    echo "📄 Report: $(ls -1 /tmp/event-relay-test-report-* | tail -1)"
    echo ""
    cat /tmp/test_results.log
    
    # Check if all tests passed
    if grep -q "0$" /tmp/test_results.log; then
        echo ""
        log_info "✅ All tests passed successfully!"
        exit 0
    else
        echo ""
        log_error "❌ Some tests failed!"
        exit 1
    fi
}

# Cleanup on exit
trap 'cleanup_test_data; exit' INT TERM

# Run main function
main "$@"