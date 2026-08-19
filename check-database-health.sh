#!/bin/bash

# Database Health Check and Recovery Script for backup_Coder
# This script helps resolve database locking issues and ensures backup_Coder can resume work

echo "=== Database Health Check and Recovery ==="
echo "Checking database status at $(date)"

# Check Paperclip database process
PAPERCLIP_PID=$(pgrep -f "paperclip.*postgres" | head -1)
if [ -n "$PAPERCLIP_PID" ]; then
    echo "✅ Paperclip PostgreSQL process running with PID: $PAPERCLIP_PID"
else
    echo "❌ Paperclip PostgreSQL process not found"
    echo "Attempting to restart Paperclip database..."
    cd /mnt/nas/project/paperclip && npm start &
    sleep 5
fi

# Check for stuck processes
echo "\n=== Checking for Stuck Processes ==="
STUCK_PROCESSES=$(ps aux | grep "postgres.*paperclip" | grep -v grep | grep -E "(INSERT|UPDATE|SELECT)" | grep -E "(00:|0-9:0-9:0-9)" | head -5)

if [ -n "$STUCK_PROCESSES" ]; then
    echo "Found potentially stuck processes:"
    echo "$STUCK_PROCESSES"
    
    # Kill stuck processes
    echo "\n🔧 Terminating stuck processes..."
    ps aux | grep "postgres.*paperclip" | grep -E "(INSERT|UPDATE|SELECT)" | grep -E "(00:|0-9:0-9:0-9)" | awk '{print $2}' | xargs -r kill
    
    echo "✅ Stuck processes terminated"
else
    echo "✅ No stuck processes found"
fi

# Check connection count
echo "\n=== Database Connection Status ==="
if command -v psql &> /dev/null; then
    # If PostgreSQL client is available
    ACTIVE_CONNECTIONS=$(psql -U paperclip -h localhost -p 54329 -d paperclip -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" -t | xargs)
    IDLE_CONNECTIONS=$(psql -U paperclip -h localhost -p 54329 -d paperclip -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'idle';" -t | xargs)
    
    echo "Active connections: $ACTIVE_CONNECTIONS"
    echo "Idle connections: $IDLE_CONNECTIONS"
    
    if [ "$ACTIVE_CONNECTIONS" -gt 10 ]; then
        echo "⚠️  High number of active connections detected"
        echo "Consider reducing connection pool size in the application"
    fi
else
    echo "PostgreSQL client not available - cannot check detailed connection stats"
fi

# Check for long-running transactions
echo "\n=== Long-running Transactions ==="
if command -v psql &> /dev/null; then
    LONG_RUNNING=$(psql -U paperclip -h localhost -p 54329 -d paperclip -c "SELECT query, now() - query_start AS duration FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '1 minute' ORDER BY duration DESC;" -t)
    
    if [ -n "$LONG_RUNNING" ]; then
        echo "Found long-running transactions:"
        echo "$LONG_RUNNING"
        echo "⚠️  These may be causing database contention"
    else
        echo "✅ No long-running transactions found"
    fi
fi

# Check database lock status
echo "\n=== Database Lock Status ==="
if command -v psql &> /dev/null; then
    LOCK_STATUS=$(psql -U paperclip -h localhost -p 54329 -d paperclip -c "SELECT schemaname, relname, mode FROM pg_locks JOIN pg_class ON pg_locks.relation = pg_class.oid;" -t)
    
    if [ -n "$LOCK_STATUS" ]; then
        echo "Active locks detected:"
        echo "$LOCK_STATUS"
        echo "⚠️  Database locks may be causing issues"
    else
        echo "✅ No database locks detected"
    fi
fi

# Restart backup_Coder if needed
echo "\n=== backup_Coder Status Check ==="
if pgrep -f "backup_Coder" > /dev/null; then
    echo "✅ backup_Coder process is running"
else
    echo "ℹ️  backup_Coder is not running - ready for resume"
    echo "You can now restart the backup_Coder run"
fi

echo "\n=== Recommendations ==="
echo "1. Monitor database connection usage regularly"
echo "2. Consider implementing circuit breakers for database operations"
echo "3. Set up alerts for connection pool exhaustion"
echo "4. Review transaction timeout settings"
echo "5. Implement exponential backoff for retry logic"

echo "\n=== Recovery Complete ==="
echo "Database health check completed at $(date)"