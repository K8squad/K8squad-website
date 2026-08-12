<!--
  Build Browser — Observability Validation KPIs (ISI-2169)
  Owner: Testing Architect
  Source: build-browser-observability-plan.md §10 "→ Testing Architect"
  Parent: ISI-2165 (plan), ISI-2168 (instrumentation stories Epic 8.7)
  Purpose: executable test contracts for the three KPIs delegated to the Testing Architect.
           These validate instrumentation once it lands; they do not substitute for it.
-->

# Build Browser — Observability Validation KPIs (ISI-2169)

**Owner:** Testing Architect  
**Date:** 2026-08-12  
**Source:** `docs/bmad/design/build-browser-observability-plan.md` §10  
**Parent ticket:** ISI-2165 (plan) — ISI-2168 (instrumentation, Epic 8.7)

---

## KPI-1 — Build-view Coverage (SLO §4 assertion)

### Invariant

Every completed-successful Run in the test corpus has a `build-snapshot` `coord.artifact`.  
The "no build view" SLO (§4 of the plan) is **asserted**, not assumed.

### Positive case

**Corpus:** the integration/e2e test fixture must include ≥ 1 completed Run with `outcome ≠ failed`.

**Assertion:**

```
∀ run ∈ corpus : run.status = completed AND run.outcome ≠ failed
  → EXISTS artifact WHERE artifact.run_id = run.id AND artifact.kind = "build-snapshot"
```

Expressed as a Go test in `internal/observability/buildbrowser/kpi_test.go`:

```go
func TestBuildViewCoveragePositive(t *testing.T) {
    for _, run := range testCorpus.CompletedSuccessRuns() {
        has, err := artifacts.HasBuildSnapshot(ctx, run.ID)
        require.NoError(t, err, "artifact store error for run %s", run.ID)
        require.True(t, has, "completed-success run %s has no build-snapshot artifact (SLO §4 violation)", run.ID)
    }
}
```

### Negative case — emit forced to skip must trip the coverage alert

**Setup:** a fixture Run where the snapshot-emit step is forced to skip (simulates missed Collecting hook,
operator crash, or ephemeral skip logic).

**Required behavior:**

1. `ksquad.buildbrowser.snapshot.emit.total{result="skipped"}` increments.
2. The "no build view" coverage alert fires within the evaluation window (the join of Run lifecycle vs
   artifact table finds a gap — **not** triggered by `result=failed`; this is the failure mode a pure
   error counter misses).

**Assertion:**

```go
func TestBuildViewCoverageNegativeSkipTripsAlert(t *testing.T) {
    // Force the emit to skip, not fail.
    run := fixtures.RunWithSkippedSnapshotEmit(t)

    // The skipped counter must have incremented.
    require.Equal(t, int64(1), metrics.SnapshotEmitTotal("skipped"),
        "skipped emit not counted — alert cannot fire on a counter that never moved")

    // The artifact join must find no build-snapshot for this run.
    has, _ := artifacts.HasBuildSnapshot(ctx, run.ID)
    require.False(t, has, "skipped run must have no build-snapshot artifact")

    // The coverage alert must be in a firing state (or would fire on next eval).
    alert := alertManager.CoverageAlertState(run.ID)
    require.Equal(t, AlertFiring, alert,
        "coverage alert must fire for a completed-success run with no build-snapshot (skipped emit)")
}
```

### Rationale

A `result=failed` counter triggers on active errors. A skipped emit (hook not reached, operator restart)
leaves the counter cold; the Run silently loses its build view. The coverage SLO is the **join** — only
the join catches the skip.

---

## KPI-2 — NFR-OBS3 Firewall Assertion (CI gate)

### Invariant

The §13 consumption/metering query allowlist contains **zero** `ksquad.buildbrowser.*` series.  
No `ksquad.buildbrowser.*` instrument declares a `model` label.

These are the machine-checkable forms of NFR-OBS3: "build-read volume is legibility telemetry, never a
consumption/billing axis."

### Positive gate (green build)

The CI script `scripts/ci/obs-nfr-obs3-firewall.sh` runs as a required CI step. It must exit 0 when:

- `internal/observability/metering_allowlist.go` contains no `ksquad.buildbrowser.*` entry.
- No Go source under `internal/` declares a `model` label on any `buildbrowser.*` metric.

### Red-team test (must FAIL the build)

A dedicated test fixture `internal/observability/buildbrowser/nfr_obs3_redteam_test.go` tests the gate
itself:

```go
//go:build kpi
// The red-team test patches the allowlist, runs the gate, and asserts it exits non-zero.
func TestNFROBS3GateRejectsBuildbrowserInMeteringAllowlist(t *testing.T) {
    // Write a temp allowlist that includes a forbidden buildbrowser series.
    tmp := writeTempAllowlist(t, []string{
        "ksquad.agent.tokens",              // legitimate — must pass
        "ksquad.buildbrowser.read.total",   // FORBIDDEN — triggers red-team
    })
    exitCode := runFirewallGate(t, tmp)
    require.NotEqual(t, 0, exitCode,
        "firewall gate must FAIL when ksquad.buildbrowser.* appears in the metering allowlist")
}

func TestNFROBS3GateAcceptsLegitimateAllowlist(t *testing.T) {
    tmp := writeTempAllowlist(t, []string{
        "ksquad.agent.tokens",
        "ksquad.run.duration",
        "ksquad.sandbox.claim.duration",
    })
    exitCode := runFirewallGate(t, tmp)
    require.Equal(t, 0, exitCode,
        "firewall gate must pass for a legitimate metering allowlist with no buildbrowser entries")
}
```

### CI script contract

The script at `scripts/ci/obs-nfr-obs3-firewall.sh` is the authoritative gate. It:

1. Reads the metering allowlist from `internal/observability/metering_allowlist.go`.
2. Greps for any `ksquad\.buildbrowser\.` pattern — fails (exit 1) if found.
3. Greps all Go sources for any `ksquad.buildbrowser.*` metric declared with a `model` label attribute —
   fails if found.
4. Self-tests its own detection by running against a known-bad fixture and asserting non-zero exit (the
   "red-team" leg of this KPI).

---

## KPI-3 — S4 / NFR-SEC5 Blast-Radius Scoping (cross-principal read)

### Invariant

A cross-principal read (principal B reading a Run owned by principal A) must:

1. Return HTTP 404 (existence never confirmed — design §5).
2. Emit `ksquad.buildbrowser.scope.denied{endpoint=<ep>}` counter increment.
3. Emit a structured WARN log with **id-only** provenance: `{run.id, principal.id, endpoint, outcome=denied}`.
   No path, no content, no confirmation of existence in the log body.

Telemetry is part of the **security gate**, not just the response code — a 404 without the metric/log
means the blast-radius scope guard ran but is invisible to the S4 audit trail.

### Test contract

```go
//go:build kpi

func TestCrossPrincipalReadEmitsScopeDenied(t *testing.T) {
    runID := fixtures.RunOwnedBy(t, principalA)
    metrics.Reset() // clear scope.denied counter

    resp := bff.GET(t, fmt.Sprintf("/api/build/%s/tree", runID), withPrincipal(principalB))

    // 1. Response must be 404.
    require.Equal(t, http.StatusNotFound, resp.StatusCode,
        "cross-principal read must return 404 (existence never confirmed)")

    // 2. scope.denied counter must have incremented.
    require.Equal(t, int64(1), metrics.ScopeDenied("tree"),
        "scope.denied{endpoint=tree} must increment on cross-principal read")

    // 3. WARN log must carry id-only provenance — no content, no path, no existence confirmation.
    warn := logs.LastWarnMatching("outcome", "denied")
    require.NotNil(t, warn, "no WARN log emitted for scope.denied — S4 audit trail broken")
    require.Equal(t, runID.String(), warn.Field("ksquad.run.id"),
        "WARN log must carry run.id")
    require.Equal(t, principalB.String(), warn.Field("ksquad.principal.id"),
        "WARN log must carry requesting principal.id")
    require.Equal(t, "tree", warn.Field("ksquad.buildbrowser.endpoint"))
    require.Empty(t, warn.Field("ksquad.buildbrowser.path"),
        "path must NOT appear in the WARN log (unbounded + sensitivity)")
    require.Empty(t, warn.Field("body"),
        "file content must never appear in telemetry")
}

func TestCrossPrincipalReadDoesNotLeakExistenceInLog(t *testing.T) {
    // A non-existent run and a cross-principal run must produce indistinguishable 404 responses.
    // The log distinguishes them for audit; the response never does.
    runID := fixtures.RunOwnedBy(t, principalA)
    nonExistentRunID := uuid.New()

    respOwned := bff.GET(t, fmt.Sprintf("/api/build/%s/tree", runID), withPrincipal(principalB))
    respMissing := bff.GET(t, fmt.Sprintf("/api/build/%s/tree", nonExistentRunID), withPrincipal(principalB))

    require.Equal(t, http.StatusNotFound, respOwned.StatusCode)
    require.Equal(t, http.StatusNotFound, respMissing.StatusCode)

    // The WARN log for the owned-but-denied case must exist; the missing case must not emit scope.denied.
    require.Equal(t, int64(1), metrics.ScopeDenied("tree"),
        "scope.denied fires only for cross-principal access, not 404-not-found")
}
```

### Coverage requirement

The scoping suite (once instrumentation lands) must include all four BFF endpoints:
`tree`, `diff`, `file`, `meta` — each must independently trip `scope.denied` on a cross-principal read.
A single endpoint hit is insufficient; the guard must exist on all read surfaces.

---

## Validation checklist (gate before ISI-2168 stories close)

| KPI | Gate | Status |
|-----|------|--------|
| KPI-1 positive: corpus join | `go test -tags kpi ./internal/observability/buildbrowser/...` green | ☐ pending ISI-2168 8.7c |
| KPI-1 negative: skip trips alert | same | ☐ pending ISI-2168 8.7c |
| KPI-2 green gate: `obs-nfr-obs3-firewall.sh` exits 0 | `make ci-obs-firewall` green | ☐ pending ISI-2168 OBS-BB5 |
| KPI-2 red-team: forbidden entry fails | `go test -tags kpi -run TestNFROBS3Gate` — redteam exits non-zero | ☐ pending OBS-BB5 |
| KPI-3 scope.denied counter | `go test -tags kpi ./internal/observability/buildbrowser/...` green | ☐ pending ISI-2168 8.7d |
| KPI-3 WARN log id-only | same | ☐ pending ISI-2168 8.7d |
| KPI-3 404 indistinguishable | same | ☐ pending ISI-2168 8.7d |

All KPI tests use `//go:build kpi` tag and skip in the default `go test ./...` run until instrumentation
lands. Add `-tags kpi` to the Epic 8.7 acceptance CI step.

---

## Dependencies

| Depends on | Provides |
|------------|----------|
| ISI-2168 8.7c (snapshot emit instrumentation) | `snapshot.emit.total{result}`, artifact store, coverage alert |
| ISI-2168 8.7d (BFF/apiserver read instrumentation) | `scope.denied`, denial WARN log, `read.total` |
| ISI-2168 OBS-BB5 (CI gate OBS-OBS3 gate) | `internal/observability/metering_allowlist.go`, `scripts/ci/obs-nfr-obs3-firewall.sh` |
