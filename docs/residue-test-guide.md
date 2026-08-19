# ISI-2241 Residue/Reuse Test - Developer Guide

## Overview

This document explains how to run and understand the residue/reuse test (Story X.2) that verifies no filesystem/in-memory/credential/scratch state bleeds across Runs or principals.

## Quick Start

### Prerequisites

- Python 3.6+ (stdlib only)
- Optional: Docker + Kind for cluster-based testing

### Setup

```bash
# Run the setup script
./setup-residue-test.sh

# Or run manually
cd docs/bmad/spikes/bench
python3 residue-reuse-check.py          # Base oracle
python3 residue-reuse-check.py --mutate  # Mutation contract
./residue-reuse-kind.sh --self-check   # Self-check (no cluster needed)
```

### Running Tests

```bash
# Full test suite (requires Kind cluster)
./residue-reuse-kind.sh

# Specific policy test
./residue-reuse-kind.sh --policy teardown+per-principal

# Test with custom namespace
./residue-reuse-kind.sh --namespace my-test-namespace

# Self-check only (no cluster required)
./residue-reuse-kind.sh --self-check
```

## Test Architecture

### Components

1. **Oracle (`residue-reuse-check.py`)**: The falsification oracle that judges residue observations
2. **Runtime Driver (`residue-reuse-kind.sh`)**: Kind cluster driver for real cluster testing
3. **Six Residue Channels**: Independent probes for each residue type

### Six Residue Channels

| Channel | Description | Test Method |
|---------|-------------|-------------|
| **scratch-fs** | Ephemeral files (/tmp, /workspace scratch) | File presence check |
| **in-mem-secret** | tmpfs secret material (/dev/shm, memfd, env vars) | Memory dump + env check |
| **git-worktree** | Git worktree state (staged index, branches, dirty tree) | Git status check |
| **build-cache-pod** | Poisoned build cache entries in pod | Cache file presence |
| **cred-env** | Credential env vars / mounted Secret files | Environment variable check |
| **pvc-cross-principal** | Persistent PVC subpath from different principal | Directory traversal check |

### How It Works

1. **Run 1 (Principal p1)**: Writes `POISON-TOKEN-run1` into every channel
2. **Hygiene Policy**: Applies the policy under test (teardown/reset)
3. **Run 2 (Principal p2)**: Probes every channel and records observations
4. **Oracle Judgment**: Checks for cross-principal residue violations

## Test Policies

### 1. teardown+per-principal (Default)
- **Mechanism**: Pod destroyed + fresh pod; per-principal PVC subpath
- **Expected**: 0 residue observations (CLEAN)
- **Purpose**: Validates the shipped posture

### 2. reset-partial (Candidate Optimization)
- **Mechanism**: Same pod reused after partial scrub (scratch-fs + git-worktree only)
- **Expected**: 3 residue observations (in-mem-secret, build-cache-pod, cred-env)
- **Purpose**: Tests detection of incomplete scrub

### 3. reset-shared-pvc (Edge Case)
- **Mechanism**: Fresh pod + perfect scrub but shared PVC subpath
- **Expected**: 1 residue observation (pvc-cross-principal)
- **Purpose**: Tests PVC isolation requirement

## Mutation Contract

The test includes a mutation contract that proves each probe is load-bearing:

```bash
python3 residue-reuse-check.py --mutate
```

This drops each probe one at a time and verifies that:
- A leak on the dropped channel goes undetected
- All 6 probes are necessary for complete coverage

## CI Integration

The test is integrated into the S4 blast-radius CI workflow:

```yaml
- name: S4-4 Residue/Reuse Test (Story X.2)
  run: |
    # Step 1: Offline oracle (always required)
    python3 residue-reuse-check.py
    python3 residue-reuse-check.py --mutate
    
    # Step 2: Cluster-based test (if available)
    if kind get clusters | grep -q "ksquad-s4"; then
      ./residue-reuse-kind.sh --policy teardown+per-principal
    fi
```

## Understanding Results

### Success Indicators

- ✅ **Base Oracle**: `PASS — teardown-and-replace is CLEAN`
- ✅ **Mutation Contract**: `PASS — all 6 channel probes load-bearing`
- ✅ **No Residue Observations**: Zero cross-principal leaks detected

### Expected Failures

- ❌ **Partial Scrub**: `FAIL on [in-mem-secret, build-cache-pod, cred-env]`
- ❌ **Shared PVC**: `FAIL on [pvc-cross-principal]`
- ❌ **Cross-Principal Leak**: `FAIL — cross-principal residue observed`

## Troubleshooting

### Common Issues

1. **No Kubernetes Cluster**
   ```bash
   # Run self-check instead
   ./residue-reuse-kind.sh --self-check
   
   # Or create Kind cluster
   kind create cluster --name ksquad-s4
   ```

2. **Missing Dependencies**
   ```bash
   # Install Kind
   curl -L https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64 -o kind
   chmod +x kind
   sudo mv kind /usr/local/bin/
   ```

3. **Permission Issues**
   ```bash
   # Use user installation
   mkdir -p ~/bin
   mv kind ~/bin/
   export PATH=$PATH:~/bin
   ```

### Debug Mode

```bash
# Enable verbose output
./residue-reuse-kind.sh --policy teardown+per-principal 2>&1 | tee residue-test.log

# Check specific channel
grep "scratch-fs" residue-test.log
grep "in-mem-secret" residue-test.log
```

## Architecture References

- **Story**: `docs/bmad/stories/x-2-residue-reuse-test.md`
- **Oracle**: `docs/bmad/spikes/bench/residue-reuse-check.py`
- **Driver**: `docs/bmad/spikes/bench/residue-reuse-kind.sh`
- **CI Workflow**: `.github/workflows/blast-radius.yml`

## Security Context

This test implements a security gate that:
- Blocks reset-in-place optimizations by construction
- Ensures no residue bleeds across Runs/principals
- Provides runtime proof of isolation guarantees
- Serves as the gate for any future optimization attempts

The test is designed to be **policy-agnostic** - it can test any candidate hygiene policy and provides differential verification that the teardown-and-replace posture is clean while detecting deviations that would compromise security.