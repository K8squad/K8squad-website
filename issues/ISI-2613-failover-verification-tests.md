# ISI-2613: Add Failover Verification Tests

## Parent Issue  
ISI-2611: Review silent active run for backup_Coder

## Description
Implement comprehensive failover verification tests to ensure backup agents can actually take over from primary agents when needed. This addresses the Failover Architecture Gaps identified in ISI-2611.

## Critical Findings from ISI-2611
- 1:1 backup relationship exists but lacks automatic failover verification
- Silent failures during failover transitions go undetected
- Limited monitoring of backup agent health and readiness
- **Risk Level: HIGH**

## Implementation Plan

### 1. Failover Test Suite (Immediate)
- Create comprehensive test suite simulating primary agent failures
- Test various failure scenarios (crash, timeout, resource exhaustion)
- Verify backup agents can successfully take over and complete pending tasks

### 2. Task Migration Verification (Immediate)  
- Implement tests to verify backup agents can:
  - Resume incomplete tasks from primary agents
  - Handle task context transfer properly
  - Maintain task state consistency during failover
  - Respect truncation constraints during backup execution

### 3. Performance Testing (Short-term)
- Measure failover time and success rate
- Test failover under load conditions
- Verify backup agent performance meets service level requirements

### 4. Integration with Existing Test Infrastructure
- Extend `opencode-shim-check.py` with failover-specific scenarios
- Integrate with existing falsification test framework
- Add backup failover verification to CI/CD pipeline

## Acceptance Criteria
- [ ] Comprehensive failover test suite created
- [ ] Tests verify backup agents can take over from primary agents
- [ ] Task migration verification passes for all scenarios
- [ ] Performance tests meet failover time requirements
- [ ] CI/CD pipeline includes failover verification
- [ ] 100% test coverage for failover scenarios

## Test Scenarios Required
1. **Primary Agent Crash** - Verify backup takeover when primary crashes mid-execution
2. **Primary Agent Timeout** - Verify backup handles primary timeout scenarios
3. **Resource Exhaustion** - Verify backup handles primary resource failure
4. **Context Transfer** - Verify backup can resume incomplete tasks with full context
5. **Concurrent Failures** - Verify behavior when multiple agents fail simultaneously
6. **Load Testing** - Verify failover under high load conditions

## Files to Modify/Create
- `docs/bmad/spikes/bench/opencode-shim-check.py` - Extend with failover scenarios
- `tests/backup/failover_test.go` - Comprehensive failover test suite
- `tests/falsification/backup-failover-check.py` - Failover falsification tests
- `internal/testutils/failover.go` - Failover testing utilities

## Priority  
**CRITICAL** - Immediate implementation required to ensure failover reliability

## Status
`pending` - Ready for implementation

## Related Issues
- ISI-2611: Review silent active run for backup_Coder (parent)
- ISI-2612: Backup Agent Health Checks (sibling)
- ISI-2614: Runtime Capability Verification (sibling)
- ISI-2615: Context Budget Consistency Tests (child)