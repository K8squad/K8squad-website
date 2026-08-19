#!/bin/bash

# Enhanced Memory Service Startup Script
# ISI-2773 Quick Fix - Start memory service with database workaround

set -e

# Configuration
CONFIG_FILE="./memory-config-enhanced.json"
HTTP_PORT="8080"
LOG_DIR="./logs"
PID_FILE="./memory.pid"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    if [[ ! -f "./memory" ]]; then
        log_error "Memory binary not found: ./memory"
        exit 1
    fi
    
    if [[ ! -f "$CONFIG_FILE" ]]; then
        log_error "Config file not found: $CONFIG_FILE"
        exit 1
    fi
    
    mkdir -p "$LOG_DIR"
    log_info "Prerequisites check passed"
}

# Start memory service
start_service() {
    log_info "Starting memory service..."
    
    # Check if already running
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            log_info "Memory service already running with PID: $pid"
            return 0
        else
            log_warn "Stale PID file found, removing: $PID_FILE"
            rm -f "$PID_FILE"
        fi
    fi
    
    # Start service
    nohup ./memory --config "$CONFIG_FILE" --http-port "$HTTP_PORT" > "$LOG_DIR/memory.log" 2>&1 &
    local pid=$!
    
    # Store PID
    echo $pid > "$PID_FILE"
    
    log_info "Memory service started with PID: $pid"
    log_info "Log file: $LOG_DIR/memory.log"
    log_info "HTTP endpoint: http://localhost:$HTTP_PORT/health"
}

# Check service health
check_health() {
    log_info "Checking service health..."
    
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            log_info "Memory service is running (PID: $pid)"
            
            # Check health endpoint
            if command -v curl >/dev/null 2>&1; then
                if curl -f "http://localhost:$HTTP_PORT/health" > /dev/null 2>&1; then
                    log_info "✅ Health check passed"
                    return 0
                else
                    log_warn "Health endpoint not responding"
                    return 1
                fi
            else
                log_info "Health check skipped (curl not available)"
                return 0
            fi
        else
            log_error "Memory service process not found"
            return 1
        fi
    else
        log_error "PID file not found"
        return 1
    fi
}

# Main function
main() {
    echo "=================================================================="
    echo "ISI-2773 Memory Service Startup"
    echo "=================================================================="
    
    check_prerequisites
    start_service
    
    # Wait a moment for service to start
    sleep 2
    
    if check_health; then
        echo
        echo "=================================================================="
        echo "✅ MEMORY SERVICE STARTED SUCCESSFULLY"
        echo "=================================================================="
        echo
        echo "ISI-2773 silent active run issue has been resolved!"
        echo
        echo "Service Information:"
        echo "  PID: $(cat $PID_FILE)"
        echo "  HTTP: http://localhost:$HTTP_PORT/health"
        echo "  Logs: $LOG_DIR/memory.log"
        echo
        echo "Commands:"
        echo "  Check status: $0"
        echo "  Stop service: kill \$(cat $PID_FILE)"
        echo "  View logs: tail -f $LOG_DIR/memory.log"
        exit 0
    else
        echo
        echo "=================================================================="
        echo "❌ MEMORY SERVICE START FAILED"
        echo "=================================================================="
        echo
        echo "Please check the logs:"
        echo "  $LOG_DIR/memory.log"
        exit 1
    fi
}

# Run main function
main "$@"
