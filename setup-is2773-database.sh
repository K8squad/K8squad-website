#!/bin/bash

# ISI-2773 Database Setup Script
# This script sets up the database for backup_Coder system
# Resolves the silent active run issue by installing required extensions

set -e

# Configuration
DB_HOST="localhost"
DB_PORT="54329"
DB_NAME="postgres"
DB_USER="paperclip"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if PostgreSQL is accessible
check_database_connection() {
    log_step "Checking database connection..."
    
    if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
        log_error "Cannot connect to database at $DB_HOST:$DB_PORT"
        log_error "Please ensure PostgreSQL is running and accessible"
        exit 1
    fi
    
    log_info "Database connection successful"
}

# Check if vector extension exists
check_vector_extension() {
    log_step "Checking for vector extension..."
    
    local extension_exists
    if extension_exists=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector');"); then
        if [[ "$extension_exists" == "t" ]]; then
            log_info "Vector extension already exists"
            return 0
        else
            log_warn "Vector extension not found - installing..."
            return 1
        fi
    else
        log_error "Failed to check vector extension"
        exit 1
    fi
}

# Install vector extension
install_vector_extension() {
    log_step "Installing vector extension..."
    
    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null; then
        log_info "Vector extension installed successfully"
    else
        log_error "Failed to install vector extension"
        log_error "This may require superuser privileges"
        exit 1
    fi
}

# Install uuid-ossp extension (required for migrations)
install_uuid_extension() {
    log_step "Installing uuid-ossp extension..."
    
    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";" 2>/dev/null; then
        log_info "UUID extension installed successfully"
    else
        log_warn "Failed to install uuid-ossp extension (may already exist)"
    fi
}

# Execute database migrations
execute_migrations() {
    log_step "Executing database migrations..."
    
    # Check if migration files exist
    local migration_dir="./db/migrations"
    if [[ ! -d "$migration_dir" ]]; then
        log_warn "Migration directory not found: $migration_dir"
        return 0
    fi
    
    # Execute each migration file
    for migration_file in "$migration_dir"/*.sql; do
        if [[ -f "$migration_file" ]]; then
            log_step "Executing migration: $(basename "$migration_file")"
            if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$migration_file" 2>/dev/null; then
                log_info "Migration completed: $(basename "$migration_file")"
            else
                log_error "Migration failed: $(basename "$migration_file")"
                log_error "Please check the migration file for errors"
                exit 1
            fi
        fi
    done
    
    log_info "All migrations completed successfully"
}

# Create memory database if it doesn't exist
create_memory_database() {
    log_step "Creating memory database..."
    
    # Check if memory database exists
    local db_exists
    if db_exists=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = 'memory');"); then
        if [[ "$db_exists" == "t" ]]; then
            log_info "Memory database already exists"
        else
            log_step "Creating memory database..."
            if createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "memory" 2>/dev/null; then
                log_info "Memory database created successfully"
            else
                log_warn "Failed to create memory database (may require superuser privileges)"
            fi
        fi
    fi
}

# Verify setup
verify_setup() {
    log_step "Verifying database setup..."
    
    # Check vector extension
    local vector_exists
    if vector_exists=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector');"); then
        if [[ "$vector_exists" == "t" ]]; then
            log_info "✅ Vector extension: OK"
        else
            log_error "❌ Vector extension: FAILED"
            return 1
        fi
    fi
    
    # Check memory schema
    local schema_exists
    if schema_exists=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'memory');"); then
        if [[ "$schema_exists" == "t" ]]; then
            log_info "✅ Memory schema: OK"
        else
            log_warn "⚠️ Memory schema: Not found (will be created on first run)"
        fi
    fi
    
    # Check memory records table
    local table_exists
    if table_exists=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'memory_records' AND table_schema = 'memory');"); then
        if [[ "$table_exists" == "t" ]]; then
            log_info "✅ Memory records table: OK"
        else
            log_warn "⚠️ Memory records table: Not found (will be created on first run)"
        fi
    fi
    
    log_info "Database verification completed"
}

# Test memory service
test_memory_service() {
    log_step "Testing memory service..."
    
    # Test if memory service can start
    if timeout 5 ./memory --config ./memory-config.json --http-port 8080 > /dev/null 2>&1; then
        log_info "✅ Memory service: OK (can start successfully)"
    else
        log_error "❌ Memory service: FAILED (still cannot start)"
        return 1
    fi
}

# Main function
main() {
    echo "=================================================================="
    echo "ISI-2773 Database Setup Script"
    echo "=================================================================="
    echo
    
    # Execute setup steps
    check_database_connection
    
    if ! check_vector_extension; then
        install_vector_extension
    fi
    
    install_uuid_extension
    create_memory_database
    execute_migrations
    verify_setup
    
    # Test the memory service
    if test_memory_service; then
        echo
        echo "=================================================================="
        echo "✅ DATABASE SETUP COMPLETED SUCCESSFULLY"
        echo "=================================================================="
        echo
        echo "ISI-2773 silent active run issue has been resolved!"
        echo
        echo "Next steps:"
        echo "1. Test backup_Coder: ./start-backup-coder start"
        echo "2. Check health: curl http://localhost:8080/health"
        echo "3. Monitor logs: tail -f logs/memory.log"
        echo
        exit 0
    else
        echo
        echo "=================================================================="
        echo "❌ DATABASE SETUP COMPLETED WITH ISSUES"
        echo "=================================================================="
        echo
        echo "The database setup completed, but the memory service still cannot start."
        echo "Please check the logs above for details."
        echo
        exit 1
    fi
}

# Error handling
trap 'log_error "Script failed at line $LINENO"; exit 1' ERR

# Run main function
main "$@"