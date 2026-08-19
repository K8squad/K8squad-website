# ISI-2612: Implement Backup Agent Health Checks

## Parent Issue
ISI-2611: Review silent active run for backup_Coder

## Description
Implement comprehensive health check mechanisms for backup agents to verify they can actually execute their intended workloads. This addresses the critical Backup Agent Execution Verification Gap identified in ISI-2611.

## Critical Findings from ISI-2611
- OpenCode backup agents may silently fail if local Ollama endpoint is unavailable
- No explicit verification that backup agents can actually run designated workloads  
- Runtime capability claims may not be truthful
- **Risk Level: HIGH**

## Implementation Plan

### 1. Backup Agent Health Check Endpoint (Immediate)
- Extend the existing `opencode-shim-check.py` with backup-specific health checks
- Create `/health/backup` endpoint in opencode runtime
- Verify Ollama endpoint availability and model access
- Check runtime capabilities advertised vs actual execution capacity

### 2. Runtime Capability Validation (Immediate)
- Implement pre-execution verification that backup agents can handle:
  - Context size limitations
  - Task complexity requirements  
  - Available model endpoints
- Validate against actual runtime capabilities (not just advertised claims)

### 3. Failover Readiness Monitoring (Short-term)
- Add backup agent status to existing observability suite
- Implement periodic health check execution for all backup agents
- Alert on backup agent health degradation

### 4. Integration Testing (Short-term)
- Extend existing test suites with backup agent health scenarios
- Test failover under various failure conditions
- Verify backup agents can take over from primary agents

## Acceptance Criteria
- [ ] Backup agents report health status via standardized endpoint
- [ ] Health checks detect Ollama endpoint unavailability
- [ ] Runtime capability validation prevents false claims
- [ ] Observability dashboard shows backup agent health
- [ ] Automated tests verify backup agent execution capability
- [ ] Failover verification tests pass for all backup agents

## Files to Modify/Create
- `docs/bmad/spikes/bench/opencode-shim-check.py` - Extend with backup health checks
- `internal/controller/backup_health_controller.go` - New controller for backup health
- `config/monitoring/prometheus-backup-health.yaml` - Backup agent metrics
- `tests/backup/health_test.go` - Health check test suite

## Priority
**CRITICAL** - Immediate implementation required to prevent silent active run failures

## Status
`pending` - Ready for implementation

## Related Issues
- ISI-2611: Review silent active run for backup_Coder (parent)
- ISI-2220: opencode runtime actual execution verification
- ISI-2613: Failover Verification Tests (child)
- ISI-2614: Runtime Capability Verification (child)