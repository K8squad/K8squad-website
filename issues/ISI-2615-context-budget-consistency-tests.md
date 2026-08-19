# ISI-2615: Context Budget Consistency Tests

## Parent Issue
ISI-2611: Review silent active run for backup_Coder

## Description
Implement context budget consistency checks to ensure backup agents respect truncation constraints and maintain context budget consistency across backup/primary agents. This addresses the Context Truncation Vulnerability identified in ISI-2611.

## Critical Findings from ISI-2611
- While primary agents have strong truncation safeguards (Story 5.9), backup agents may not respect these constraints
- Risk of silent task truncation during backup agent execution
- Context budget enforcement may not apply consistently across all runtime types
- **Risk Level: MEDIUM**

## Implementation Plan

### 1. Context Budget Validation Framework (Immediate)
- Implement cross-runtime context budget validation system
- Add backup agent context budget compliance checks
- Ensure backup agents respect the same truncation constraints as primary agents

### 2. Truncation Consistency Testing (Immediate)
- Create tests to verify backup agents handle truncation identically to primary agents
- Test various truncation scenarios and edge cases
- Verify backup agents never silently truncate must-include content

### 3. Context Budget Monitoring (Short-term)
- Add context budget usage metrics to backup agent monitoring
- Implement alerts for context budget violations
- Track consistency across backup/primary agent context usage

### 4. Cross-Agent Context Transfer Validation (Short-term)
- Test backup agents can properly resume truncated tasks from primary agents
- Verify context transfer maintains budget consistency
- Ensure backup agents handle partial contexts correctly

## Acceptance Criteria
- [ ] Context budget validation framework implemented
- [ ] Backup agents respect truncation constraints consistently
- [ ] Truncation consistency tests pass for all scenarios
- [ ] Context budget monitoring detects violations
- [ ] Cross-agent context transfer maintains budget consistency
- [ ] Backup agents never silently truncate must-include content

## Test Scenarios Required
1. **Truncation Consistency** - Verify backup agents truncate identically to primary agents
2. **Must-Include Protection** - Ensure backup agents never silently truncate must-include content
3. **Budget Transfer** - Test context transfer maintains budget consistency
4. **Edge Cases** - Test truncation with various context sizes and complexities
5. **Load Testing** - Verify truncation consistency under high load conditions

## Files to Modify/Create
- `internal/agent/context/budget.go` - Enhanced context budget validation
- `tests/backup/context_budget_test.go` - Context budget consistency tests
- `config/monitoring/context-budget.yaml` - Context budget metrics
- `internal/testutils/context_budget.go` - Context budget testing utilities

## Priority
**HIGH** - Important for preventing silent truncation issues

## Status
`pending` - Ready for implementation

## Related Issues
- ISI-2611: Review silent active run for backup_Coder (parent)
- ISI-2612: Backup Agent Health Checks (sibling)
- ISI-2613: Failover Verification Tests (sibling)
- ISI-2614: Runtime Capability Verification (sibling)
- ISI-2221: Context budget enforcement to prevent silent truncation