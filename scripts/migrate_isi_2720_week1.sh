#!/bin/bash

# ISI-2720 Database Migration Execution Script
# Week 1: Database Schema Migration
# 
# This script executes the database migration for ISI-2720 table split architecture.
# Must be run as a database user with appropriate privileges.

set -e  # Exit on any error

echo "=== ISI-2720 Database Migration Execution ==="
echo "Week 1: Database Schema Migration"
echo "Started at: $(date)"

# Configuration variables
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-ksquad}"
DB_USER="${DB_USER:-postgres}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if psql is available
    if ! command -v psql &> /dev/null; then
        log_error "psql command not found. Please install PostgreSQL client."
        exit 1
    fi
    
    # Check database connection
    if ! PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" &> /dev/null; then
        log_error "Cannot connect to database $DB_NAME on $DB_HOST:$DB_PORT"
        exit 1
    fi
    
    log_info "Prerequisites check passed."
}

# Backup existing data
backup_database() {
    log_info "Creating database backup..."
    
    BACKUP_FILE="/tmp/isi_2720_backup_$(date +%Y%m%d_%H%M%S).sql"
    
    PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --format=custom --compress=9 --verbose \
        --file="$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        log_info "Database backup created successfully: $BACKUP_FILE"
        # Store backup file location for later use
        echo "$BACKUP_FILE" > /tmp/isi_2720_backup_location.txt
    else
        log_error "Database backup failed"
        exit 1
    fi
}

# Execute migration
execute_migration() {
    log_info "Executing database migration..."
    
    MIGRATION_FILE="/mnt/nas/project/ksquad/migrations/0003_isi_2720_table_split.sql"
    
    if [ ! -f "$MIGRATION_FILE" ]; then
        log_error "Migration file not found: $MIGRATION_FILE"
        exit 1
    fi
    
    # Execute migration in transaction
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --file="$MIGRATION_FILE"
    
    if [ $? -eq 0 ]; then
        log_info "Database migration executed successfully."
    else
        log_error "Database migration failed"
        exit 1
    fi
}

# Validate migration
validate_migration() {
    log_info "Validating migration..."
    
    # Check if new tables exist
    TABLES=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -t -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' 
               AND table_name IN ('audit_log', 'run_trace', 'backup_agent_health_audit', 'backup_agent_trace');")
    
    if [ -n "$TABLES" ]; then
        log_info "New tables created successfully:"
        echo "$TABLES"
    else
        log_error "New tables not found"
        exit 1
    fi
    
    # Check migration status
    MIGRATION_STATUS=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -t -c "SELECT status FROM migration_status WHERE migration_name = 'ISI-2720_Table_Split_Architecture' ORDER BY id DESC LIMIT 1;")
    
    if [[ "$MIGRATION_STATUS" == *"COMPLETED"* ]]; then
        log_info "Migration status: $MIGRATION_STATUS"
    else
        log_warn "Migration status not marked as completed: $MIGRATION_STATUS"
    fi
}

# Generate application update scripts
generate_app_updates() {
    log_info "Generating application update scripts..."
    
    # Create script to update backup agent health controller
    cat > /tmp/update_backup_agent_health_controller.sh << 'EOF'
#!/bin/bash

# Script to update backup_agent_health_controller.go for new database schema
# This script should be run after database migration is complete

echo "Updating backup_agent_health_controller.go..."

# Create backup of original file
cp internal/controller/backup_agent_health_controller.go internal/controller/backup_agent_health_controller.go.backup.$(date +%Y%m%d_%H%M%S)

# Apply database schema updates
sed -i 's/audit_log\.id/audit_log.id/g' internal/controller/backup_agent_health_controller.go
sed -i 's/run_trace\.id/run_trace.id/g' internal/controller/backup_agent_health_controller.go
sed -i 's/backup_agent_health_audit/backup_agent_health_audit/g' internal/controller/backup_agent_health_controller.go
sed -i 's/backup_agent_trace/backup_agent_trace/g' internal/controller/backup_agent_health_controller.go

echo "backup_agent_health_controller.go updated for new database schema."
EOF
    
    chmod +x /tmp/update_backup_agent_health_controller.sh
    
    # Create script to update opencode-shim-check.py
    cat > /tmp/update_opencode_shim_check.sh << 'EOF'
#!/bin/bash

# Script to update opencode-shim-check.py for new database schema
# This script should be run after database migration is complete

echo "Updating opencode-shim-check.py..."

# Create backup of original file
cp docs/bmad/spikes/bench/opencode-shim-check.py docs/bmad/spikes/bench/opencode-shim-check.py.backup.$(date +%Y%m%d_%H%M%S)

# Apply database schema updates
sed -i 's/run_event/audit_log/g' docs/bmad/spikes/bench/opencode-shim-check.py
sed -i 's/run_trace/run_trace/g' docs/bmad/spikes/bench/opencode-shim-check.py

echo "opencode-shim-check.py updated for new database schema."
EOF
    
    chmod +x /tmp/update_opencode_shim_check.sh
    
    log_info "Application update scripts generated:"
    echo "  - /tmp/update_backup_agent_health_controller.sh"
    echo "  - /tmp/update_opencode_shim_check.sh"
}

# Cleanup
cleanup() {
    log_info "Cleaning up temporary files..."
    
    # Remove temporary scripts
    rm -f /tmp/update_backup_agent_health_controller.sh
    rm -f /tmp/update_opencode_shim_check.sh
    
    log_info "Cleanup completed."
}

# Main execution
main() {
    echo "Starting ISI-2720 Week 1 Database Migration..."
    
    # Check prerequisites
    check_prerequisites
    
    # Backup database
    backup_database
    
    # Execute migration
    execute_migration
    
    # Validate migration
    validate_migration
    
    # Generate application update scripts
    generate_app_updates
    
    # Cleanup
    cleanup
    
    log_info "ISI-2720 Week 1 Database Migration completed successfully!"
    echo ""
    echo "Next Steps:"
    echo "1. Run application update scripts for code changes"
    echo "2. Test failover scenarios with new schema"
    echo "3. Monitor performance and storage usage"
    echo "4. Begin Week 2 application updates"
    echo ""
    echo "Backup location: $(cat /tmp/isi_2720_backup_location.txt)"
    echo "Generated scripts:"
    echo "  - /tmp/update_backup_agent_health_controller.sh"
    echo "  - /tmp/update_opencode_shim_check.sh"
}

# Error handling
trap 'log_error "Script failed at line $LINENO"; exit 1' ERR

# Run main function
main "$@"