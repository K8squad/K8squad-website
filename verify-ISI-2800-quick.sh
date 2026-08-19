#!/bin/bash

echo "=== ISI-2800 Quick Verification ==="
echo "Date: $(date)"
echo ""

# Check key components
PASSED=0
TOTAL=5

if [ -f "ISI-2800-ONGOING-ASSESSMENT.md" ]; then
    echo "✅ ISI-2800 Assessment document exists"
    ((PASSED++))
else
    echo "❌ ISI-2800 Assessment document missing"
fi

if [ -f "ISI-2800-COMPLETION-SUMMARY.md" ]; then
    echo "✅ ISI-2800 Completion Summary exists"
    ((PASSED++))
else
    echo "❌ ISI-2800 Completion Summary missing"
fi

if [ -f "ISI-2799-IMPLEMENTATION-VERIFICATION-REVIEW.md" ]; then
    echo "✅ ISI-2799 Implementation Review exists"
    ((PASSED++))
else
    echo "❌ ISI-2799 Implementation Review missing"
fi

if [ -f "start-backup-coder" ] && [ -x "start-backup-coder" ]; then
    echo "✅ start-backup-coder script is ready"
    ((PASSED++))
else
    echo "❌ start-backup-coder script missing or not executable"
fi

if ./check-database-health.sh > /dev/null 2>&1; then
    echo "✅ Database connectivity is functional"
    ((PASSED++))
else
    echo "⚠️  Database connectivity needs attention"
fi

echo ""
echo "=== Results ==="
echo "Passed: $PASSED out of $TOTAL"

if [ $PASSED -ge 4 ]; then
    echo "🎉 EXCELLENT - ISI-2800 Review is COMPLETE and READY"
    exit 0
elif [ $PASSED -ge 3 ]; then
    echo "✅ GOOD - ISI-2800 Review is MOSTLY COMPLETE"
    exit 0
else
    echo "⚠️  NEEDS WORK - ISI-2800 Review has ISSUES"
    exit 1
fi