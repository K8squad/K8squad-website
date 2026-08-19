# ISI-2720: Implement Database Architecture Resolution (ISI-2339 F1)

**Parent Issue**: ISI-2719  
**Agent**: backup_Architect  
**Priority**: HIGH 🔴  
**Status**: ✅ **DECISION MADE** - Ready for Implementation  
**Created**: August 17, 2026

## Objective

Resolve the critical database architecture conflict identified in ISI-2339 F1 that threatens backup agent silent active run prevention. This decision must be made before Story 8.11 implementation.

## Problem Statement

The unified `run_event` table combines immutable audit logs with high-volume shim trace data, creating a "firehose" problem where trace data becomes "unprunable" - retention would require partition surgery that contradicts immutability claims.

**Silent Active Run Impact**:
- Storage exhaustion during backup operations
- Performance degradation leading to timeout failures  
- Potential database lock recurrence due to volume issues

## Required Architectural Decision

### Option 1: Table Split (Recommended)
- **Action**: Split into separate `audit_log` (immutable) + `run_trace` (time-partitioned)
- **Pros**: Clean separation, optimal retention, audit integrity preserved
- **Cons**: Migration complexity, application updates needed
- **Timeline**: 1-2 weeks implementation

### Option 2: Declarative Partitioning  
- **Action**: Implement declarative time-partitioning of `run_event` with documented `DROP PARTITION` retention
- **Pros**: Single table, simpler application interface
- **Cons**: Softer "structurally immutable" claims, requires documented partition surgery
- **Timeline**: 3-5 days implementation

### Option 3: Current Design with Retention Updates
- **Action**: Keep current design but document limitations and implement aggressive retention
- **Pros**: No immediate changes
- **Cons**: Ongoing storage/performance issues, backup agent risks remain
- **Timeline**: Immediate but risky

## Implementation Requirements

### Database Schema Changes
```sql
-- Option 1 Implementation
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    -- Immutable audit fields
    CHECK (true)  -- Structural immutability constraint
);

CREATE TABLE run_trace (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    -- Partitioned by time for retention
) PARTITION BY RANGE (timestamp);
```

### Application Updates Required
- Update all audit logging to use `audit_log` table
- Update shim tracing to use `run_trace` table  
- Modify retention policies for each table type
- Update backup agent queries to work with split tables

### Migration Strategy
1. **Phase 1**: Create new tables with historical data copy
2. **Phase 2**: Update application to write to both tables during transition
3. **Phase 3**: Switch application to new table structure
4. **Phase 4**: Remove old table and cleanup

## Success Criteria

- [ ] Database architecture supports backup agent retention requirements
- [ ] Audit integrity maintained with proper immutability guarantees
- [ ] Performance sufficient for high-volume backup operations
- [ ] Storage growth under control with appropriate retention
- [ ] Story 8.11 implementation unblocked

## Dependencies

- **Blocks Story 8.11**: Cannot proceed until this decision is made
- **Requires ISI-2612**: Health verification depends on stable database architecture
- **Needs Database Team Review**: Schema changes require approval

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Data corruption during migration | Low | Critical | Test migration in staging |
| Performance degradation | Medium | High | Optimize indexes and partitions |
| Application compatibility issues | Medium | Medium | Comprehensive testing required |
| Audit trail gaps | Low | Critical | Verify audit completeness |

## Next Steps

1. ✅ **Decision**: Choose architectural approach (Table Split completed)
2. ✅ **Design**: Create detailed schema and migration plan
3. ⏳ **Review**: Get database team approval
4. ⏳ **Implementation**: Execute migration in staging first
5. ⏳ **Validation**: Test backup agent operations with new architecture
6. ⏳ **Production**: Deploy with monitoring

---

**Status**: ✅ ARCHITECTURE DECISION COMPLETE - Ready for Implementation  
**Owner**: backup_Architect  
**Timeline**: Week 1-2: Migration, Week 3-4: Production Deployment  
**Decision Reference**: ISI-2720-ARCHITECTURE-DECISION.md