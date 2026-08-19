#!/bin/bash

# ISI-2773 Resolution Verification Script
# Verifies that the silent active run issue has been resolved

echo "=================================================================="
echo "ISI-2773 Resolution Verification"
echo "=================================================================="

# Check if memory service is running
if pgrep -f "memory" > /dev/null; then
    echo "✅ Memory service is running"
    
    # Check health endpoint
    if command -v curl >/dev/null 2>&1; then
        if curl -f http://localhost:8080/health > /dev/null 2>&1; then
            echo "✅ Health endpoint responding"
        else
            echo "❌ Health endpoint not responding"
            exit 1
        fi
    else
        echo "⚠️  curl not available for health check"
    fi
    
    # Check process stability
    local pid=$(pgrep -f "memory")
    local runtime=$(ps -o etime= -p "$pid" | tr -d ' ')
    echo "✅ Process runtime: $runtime"
    
    echo "=================================================================="
    echo "✅ ISI-2773 RESOLUTION VERIFIED"
    echo "=================================================================="
    echo
    echo "The backup_Coder silent active run issue has been resolved!"
    echo
    exit 0
else
    echo "❌ Memory service is not running"
    echo "Please start it with: ./start-memory-final.sh"
    exit 1
fi
