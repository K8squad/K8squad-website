# L4 Security Suite CI Workflows

This directory contains the GitHub Actions workflows for the L4 Security Suite (Epic-14), which implements the S4 blast-radius testing as required by the architecture and PRD.

## Overview

The L4 Security Suite consists of two complementary workflows:

### 1. `security.yml` - Supply Chain Security (Half A)
This workflow implements the supply-chain security checks mentioned in L4 §14.4:

- **govulncheck**: Go vulnerability scanning
- **npm audit**: JavaScript vulnerability scanning  
- **trivy-scan**: Container image and filesystem vulnerability scanning
- **gitleaks**: Secret detection
- **codeql-analysis**: Static application security testing (SAST)

**Triggers**: 
- Push to main/master branches
- Pull requests to main/master
- Weekly scheduled runs (Sundays at 03:00 UTC)
- Manual workflow dispatch

**Gate**: All checks must pass to allow code to be merged.

### 2. `blast-radius.yml` - S4 Blast-Radius Suite (Half B) 
This workflow implements the S4 blast-radius testing against a real Kind cluster:

**S4 Test Cases**:
- **S4-1**: Default-deny egress isolation
- **S4-2**: Exfil-via-allowlist endpoint testing
- **S4-3**: Cross-namespace isolation verification  
- **S4-4**: Residue/Reuse Test (Story X.2) - **this story's deliverable**
- **S5-4**: Read AuthZ (404-not-403 pattern)

**Triggers**:
- Push to main/master branches
- Pull requests to main/master  
- Daily scheduled runs (02:00 UTC)
- Manual workflow dispatch

**Special Features**:
- Uses Kind cluster for realistic testing environment
- Includes Story X.2 residue/reuse test with all six residue channels
- Tests multiple hygiene policies (teardown+per-principal, reset-partial, reset-shared-pvc)
- Mutation contract verification (all 6 probes load-bearing)
- Comprehensive logging and artifact collection on failures

## Story X.2: Residue/Reuse Test Integration

The S4-4 residue/reuse test is fully integrated and operational:

### Implementation Complete:
- ✅ **Falsification oracle**: `residue-reuse-check.py` - offline six-channel differential
- ✅ **Runtime driver**: `residue-reuse-kind.sh` - Kind cluster binding  
- ✅ **CI integration**: Wired into S4 blast-radius workflow
- ✅ **Boundary agreement**: Matches `principal_subpath()` with `teardown-scoping-check.py`

### Verification Passing:
- ✅ **Base test**: Teardown-and-replace policy passes (0/6 residue observations)
- ✅ **Mutation contract**: All 6 channel probes are load-bearing (--mutate)
- ✅ **Gate semantics**: Blocks reset-in-place deviations by construction
- ✅ **Positive control**: Same-principal cache persists (FR-C2) without false positives

### Six Residue Channels Tested:
1. **scratch-fs**: Ephemeral files on pod (/tmp, /workspace scratch)
2. **in-mem-secret**: tmpfs secret material (/dev/shm, memfd, env vars)
3. **git-worktree**: Git worktree state (staged index, branches, dirty tree)
4. **build-cache-pod**: Poisoned build cache entries in pod
5. **cred-env**: Credential env vars / mounted Secret files
6. **pvc-cross-principal**: Persistent PVC subpath from different principal

## CI Integration Details

### Environment Setup:
- **Cluster**: Kind (k8s v1.27.3) with realistic network policies
- **Runtime**: gvisor RuntimeClass for isolation (when available)
- **Storage**: PVC with per-principal subpath mounting
- **Namespace**: ksquad-s4 with proper label annotations

### Test Execution:
```bash
# Run residue/reuse test with shipped policy
./residue-reuse-kind.sh --policy teardown+per-principal

# Verify mutation contract (offline)
python3 residue-reuse-check.py --mutate
```

### CI Output:
- **Success**: Green CI state with test logs and artifacts
- **Failure**: Red CI state with detailed residue observations and diagnostic logs
- **Artifacts**: JSONL observations, pod UIDs, cluster logs (7-day retention)

## Security Gate

Both workflows implement strict security gates:

1. **Security Gate**: All supply-chain scans must pass
2. **Blast-Radius Gate**: All S4 tests must pass  
3. **Residue Test**: S4-4 must pass with mutation contract intact

No code can be merged unless both gates are satisfied.

## References

- **Architecture**: `docs/bmad/03-architecture.md` (§9.3/§9.4 isolation)
- **Story X.2**: `docs/bmad/stories/x-2-residue-reuse-test.md`
- **L4 Story**: `docs/bmad/stories/14-4-l4-security-suite.md`
- **Epic-14**: `docs/bmad/04-epics-and-stories.md` (L4 Security Suite)
- **ADR-006**: `docs/bmad/adr/006-teardown-vs-reset.md`