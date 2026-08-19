#!/bin/bash

# ISI-2827 Verification Script: Silent Active Run for backup_Coder
# Purpose: Verify the findings from ISI-2827 review and confirm backup_Coder status

set -e

echo "=== ISI-2827 Verification: Silent Active Run for backup_Coder ==="
echo "Date: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    if [ $2 -eq 0 ]; then
        echo -e "${GREEN}✅ $1${NC}"
    else
        echo -e "${RED}❌ $1${NC}"
    fi
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

print_error() {
    echo -e "${RED}🚨 $1${NC}"
}

echo "=== 1. System Status Check ==="

# Check if backup_Coder processes are running
if pgrep -f "backup.*coder" > /dev/null; then
    print_status "backup_Coder process is running" $?
else
    print_status "backup_Coder process is NOT running" $?
fi

# Check if health monitoring is active
if [ -f "/tmp/enhanced_monitoring_pid.txt" ]; then
    PID=$(cat /tmp/enhanced_monitoring_pid.txt)
    if ps -p $PID > /dev/null; then
        print_status "Health monitoring is active (PID: $PID)" $?
    else
        print_status "Health monitoring process is NOT active" $?
    fi
else
    print_status "Health monitoring PID file not found" $?
fi

echo ""
echo "=== 2. Configuration Check ==="

# Check configuration file exists and is readable
if [ -f "memory-config.json" ]; then
    print_status "Configuration file exists" $?
    if jq empty memory-config.json 2>/dev/null; then
        print_status "Configuration file is valid JSON" $?
    else
        print_error "Configuration file is invalid JSON"
    fi
else
    print_error "Configuration file not found"
fi

# Check database configuration
if jq -e '.database.port' memory-config.json >/dev/null 2>&1; then
    PORT=$(jq -r '.database.port' memory-config.json)
    print_info "Database port configured: $PORT"
else
    print_error "Database port not configured"
fi

echo ""
echo "=== 3. Process Stability Analysis ==="

# Check for recent crash reports in logs
if ls logs/enhanced_resume_backup_coder_* 1> /dev/null 2>&1; then
    echo "Recent backup_Coder logs found:"
    ls -la logs/enhanced_resume_backup_coder_* | head -3
    print_info "Process restart logs available for analysis"
else
    print_error "No recent backup_Coder logs found"
fi

# Count recent restart attempts in latest log
if [ -f "logs/enhanced_resume_backup_coder_$(date +%Y%m%d_%H%M%S).log" ]; then
    LATEST_LOG="logs/enhanced_resume_backup_coder_$(date +%Y%m%d_%H%M%S).log"
else
    LATEST_LOG=$(ls logs/enhanced_resume_backup_coder_* | tail -1)
fi

if [ -f "$LATEST_LOG" ]; then
    RESTART_COUNT=$(grep -c "backup_Coder restarted" "$LATEST_LOG" || echo "0")
    TERMINATION_COUNT=$(grep -c "backup_Coder process.*terminated" "$LATEST_LOG" || echo "0")
    
    print_info "Recent restart attempts: $RESTART_COUNT"
    print_info "Recent terminations: $TERMINATION_COUNT"
    
    if [ "$RESTART_COUNT" -gt 10 ]; then
        print_error "High number of restarts detected - instability confirmed"
    else
        print_status "Restart count within acceptable range" $?
    fi
fi

echo ""
echo "=== 4. Database Connectivity Check ==="

# Check if PostgreSQL is running
if pgrep -f "postgres" > /dev/null; then
    print_status "PostgreSQL process is running" $?
else
    print_error "PostgreSQL process is NOT running"
fi

# Check database connectivity
if [ -f "memory-config.json" ]; then
    PORT=$(jq -r '.database.port // "5432"' memory-config.json)
    HOST=$(jq -r '.database.host // "localhost"' memory-config.json)
    
    print_info "Testing database connection to $HOST:$PORT"
    if timeout 5 nc -z $HOST $PORT >/dev/null 2>&1; then
        print_status "Database connectivity successful" $?
    else
        print_error "Database connectivity failed"
    fi
fi

echo ""
echo "=== 5. Review Documentation Check ==="

# Check if ISI-2827 review document exists
if [ -f "ISI-2827-REVIEW-COMPLETE.md" ]; then
    print_status "ISI-2827 review document exists" $?
    LINE_COUNT=$(wc -l < ISI-2827-REVIEW-COMPLETE.md)
    print_info "Review document length: $LINE_COUNT lines"
else
    print_error "ISI-2827 review document not found"
fi

# Check if QA request document exists
if [ -f "ISI-2827-QA-REQUEST.md" ]; then
    print_status "ISI-2827 QA request document exists" $?
else
    print_error "ISI-2827 QA request document not found"
fi

echo ""
echo "=== 6. Previous Reviews Reference Check ==="

# Check if referenced reviews exist
REVIEWS=("ISI-2801-SILENT-ACTIVE-RUN-REVIEW.md" "ISI-2628-backup_Coder-review-report.md" "ISI-2820-SILENT-ACTIVE-RUN-REVIEW.md")

for review in "${REVIEWS[@]}"; do
    if [ -f "$review" ]; then
        print_status "Referenced review $review exists" $?
    else
        print_error "Referenced review $review not found"
    fi
done

echo ""
echo "=== 7. Final Assessment ==="

# Summary of findings
echo "ISI-2827 Key Findings:"
echo "🚨 CRITICAL ISSUES IDENTIFIED:"
echo "   - Process instability preventing stable operation"
echo "   - Configuration reading failures (ISI-2801 inheritance)"
echo "   - Silent active run risk due to non-operational but configured system"
echo ""
echo "PRODUCTION STATUS: ❌ NOT OPERATIONAL"
echo "RECOMMENDATION: Fix configuration reading and process stability"
echo ""
echo "Review completed: $(date)"
echo "Next action: QA verification of findings"

echo ""
echo "=== Verification Complete ==="