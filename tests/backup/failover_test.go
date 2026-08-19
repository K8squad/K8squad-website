package backup

import (
	"context"
	"fmt"
	"testing"
	"time"

	ksquadv1alpha1 "github.com/ksquad/ksquad/api/v1alpha1"
	"github.com/ksquad/ksquad/internal/metrics"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
)

// FailoverTestScenario represents a single failover test scenario
type FailoverTestScenario struct {
	Name           string
	PrimaryFailure string // "crash", "timeout", "resource_exhaustion"
	ExpectedResult bool
}

// FailoverTester provides capabilities to test backup agent failover
type FailoverTester struct {
	backupClient   ksquadv1alpha1.BackupAgentHealthInterface
	primaryAgent  *ksquadv1alpha1.BackupAgentHealth
	testTimeout    time.Duration
}

// NewFailoverTester creates a new failover tester
func NewFailoverTester(backupClient ksquadv1alpha1.BackupAgentHealthInterface, timeout time.Duration) *FailoverTester {
	return &FailoverTester{
		backupClient: backupClient,
		testTimeout:  timeout,
	}
}

// TestFailoverScenarios runs comprehensive failover test scenarios
func (ft *FailoverTester) TestFailoverScenarios(t *testing.T) scenarios []FailoverTestScenario {
	scenarios := []FailoverTestScenario{
		{
			Name:           "Primary Agent Crash",
			PrimaryFailure: "crash",
			ExpectedResult: true,
		},
		{
			Name:           "Primary Agent Timeout",
			PrimaryFailure: "timeout", 
			ExpectedResult: true,
		},
		{
			Name:           "Primary Agent Resource Exhaustion",
			PrimaryFailure: "resource_exhaustion",
			ExpectedResult: true,
		},
	}

	for _, scenario := range scenarios {
		t.Run(scenario.Name, func(t *testing.T) {
			ft.testFailoverScenario(t, scenario)
		})
	}
}

// testFailoverScenario executes a single failover test scenario
func (ft *FailoverTester) testFailoverScenario(t *testing.T, scenario FailoverTestScenario) {
	ctx, cancel := context.WithTimeout(context.Background(), ft.testTimeout)
	defer cancel()

	// Create backup agent health resource for testing
	backupHealth := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("test-backup-%s", scenario.Name),
			Namespace: "test-namespace",
		},
		Spec: ksquadv1alpha1.BackupAgentHealthSpec{
			RuntimeType:           "opencode",
			EndpointURL:           "http://ollama.test.svc.cluster.local:11434/v1",
			HealthCheckInterval:   metav1.Duration{Duration: 10 * time.Second},
			FailureThreshold:      3,
			PrimaryAgentRef: &metav1.ObjectReference{
				APIVersion: "v1",
				Kind:       "Pod",
				Name:       "primary-agent",
				Namespace:  "test-namespace",
			},
		},
	}

	// Create the backup agent health resource
	err := ft.backupClient.Create(ctx, backupHealth)
	require.NoError(t, err, "Failed to create backup agent health resource")
	defer func() {
		// Cleanup
		ft.backupClient.Delete(ctx, backupHealth)
	}()

	// Simulate primary agent failure based on scenario
	ft.simulatePrimaryFailure(ctx, t, scenario.PrimaryFailure)

	// Wait for backup agent to detect failover readiness
	backupReady := ft.waitForBackupReady(ctx, t, backupHealth.Name)
	
	// Verify failover result
	assert.Equal(t, scenario.ExpectedResult, backupReady, 
		"Backup agent failover result should match expected")
	
	// Record test metrics
	metrics.RecordFailoverTest(scenario.Name, backupReady, time.Since(testStart))
}

// simulatePrimaryFailure simulates different types of primary agent failures
func (ft *FailoverTester) simulatePrimaryFailure(ctx context.Context, t *testing.T, failureType string) {
	switch failureType {
	case "crash":
		// Simulate primary agent pod crash
		ft.simulatePrimaryCrash(ctx, t)
	case "timeout":
		// Simulate primary agent timeout
		ft.simulatePrimaryTimeout(ctx, t)
	case "resource_exhaustion":
		// Simulate primary agent resource exhaustion
		ft.simulatePrimaryResourceExhaustion(ctx, t)
	default:
		t.Fatalf("Unknown primary failure type: %s", failureType)
	}
}

// simulatePrimaryCrash simulates primary agent pod crash
func (ft *FailoverTester) simulatePrimaryCrash(ctx context.Context, t *testing.T) {
	// In a real implementation, this would simulate pod crash
	// For testing, we'll mark the primary as unavailable through the backup agent status
	
	primaryPod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "primary-agent",
			Namespace: "test-namespace",
		},
		Status: corev1.PodStatus{
			Phase: corev1.PodFailed,
		},
	}
	
	// Update backup agent to detect primary failure
	backupHealth := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-backup-Primary-Agent-Crash",
			Namespace: "test-namespace",
		},
		Status: ksquadv1alpha1.BackupAgentHealthStatus{
			PrimaryAgentStatus: "failed",
			LastHealthCheck:    metav1.Now(),
		},
	}
	
	err := ft.backupClient.Status().Update(ctx, backupHealth)
	require.NoError(t, err, "Failed to update backup agent status to detect primary crash")
}

// simulatePrimaryTimeout simulates primary agent timeout
func (ft *FailoverTester) simulatePrimaryTimeout(ctx context.Context, t *testing.T) {
	// Simulate primary agent timeout by marking it as unresponsive
	
	backupHealth := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-backup-Primary-Agent-Timeout",
			Namespace: "test-namespace",
		},
		Status: ksquadv1alpha1.BackupAgentHealthStatus{
			PrimaryAgentStatus:   "timeout",
			LastHealthCheck:      metav1.Now(),
			LastResponseTime:     metav1.NewTime(time.Now().Add(-2 * time.Minute)), // Last response was 2 minutes ago
			HealthCheckHistory: []ksquadv1alpha1.HealthCheckResult{
				{
					Timestamp:  metav1.Now(),
					CheckType:  "primary_connectivity",
					Passed:     false,
					Message:    "Primary agent timeout detected",
					DurationMs: 120000, // 2 minutes
				},
			},
		},
	}
	
	err := ft.backupClient.Status().Update(ctx, backupHealth)
	require.NoError(t, err, "Failed to update backup agent status to detect primary timeout")
}

// simulatePrimaryResourceExhaustion simulates primary agent resource exhaustion
func (ft *FailoverTester) simulatePrimaryResourceExhaustion(ctx context.Context, t *testing.T) {
	// Simulate primary agent resource exhaustion
	
	backupHealth := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-backup-Primary-Agent-Resource-Exhaustion",
			Namespace: "test-namespace",
		},
		Status: ksquadv1alpha1.BackupAgentHealthStatus{
			PrimaryAgentStatus:   "resource_exhausted",
			LastHealthCheck:      metav1.Now(),
			ResourceUsage: &ksquadv1alpha1.ResourceUsageStatus{
				CPUUsage:    "95%",
				MemoryUsage: "92%",
				GPUUsage:    "88%",
			},
			HealthCheckHistory: []ksquadv1alpha1.HealthCheckResult{
				{
					Timestamp:  metav1.Now(),
					CheckType:  "primary_resource_monitoring",
					Passed:     false,
					Message:    "Primary agent resource exhaustion detected",
					Error:      "CPU usage exceeds 90% threshold",
				},
			},
		},
	}
	
	err := ft.backupClient.Status().Update(ctx, backupHealth)
	require.NoError(t, err, "Failed to update backup agent status to detect primary resource exhaustion")
}

// waitForBackupReady waits for backup agent to become ready for failover
func (ft *FailoverTester) waitForBackupReady(ctx context.Context, t *testing.T, backupName string) bool {
	// Poll backup agent status until it becomes ready or timeout
	pollInterval := 2 * time.Second
	timeout := ft.testTimeout - (5 * time.Second) // Leave some buffer
	
	startTime := time.Now()
	for time.Since(startTime) < timeout {
		backupHealth := &ksquadv1alpha1.BackupAgentHealth{}
		err := ft.backupClient.Get(ctx, types.NamespacedName{Name: backupName, Namespace: "test-namespace"}, backupHealth)
		if err != nil {
			t.Logf("Error getting backup agent health: %v", err)
			return false
		}
		
		if backupHealth.Status.Ready {
			return true
		}
		
		time.Sleep(pollInterval)
	}
	
	return false
}

// TestTaskMigrationVerification tests backup agent task migration capabilities
func (ft *FailoverTester) TestTaskMigrationVerification(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), ft.testTimeout)
	defer cancel()

	// Test backup agent's ability to resume incomplete tasks from primary agents
	testCases := []struct {
		name           string
		taskContext    string
		expectedResumed bool
	}{
		{
			name:           "Complete Task Transfer",
			taskContext:    "complete_task_context",
			expectedResumed: true,
		},
		{
			name:           "Partial Task Transfer",
			taskContext:    "partial_task_context",
			expectedResumed: true,
		},
		{
			name:           "Large Context Transfer",
			taskContext:    "large_context_that_requires_truncation",
			expectedResumed: true,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			ft.testTaskMigration(ctx, t, tc.taskContext, tc.expectedResumed)
		})
	}
}

// testTaskMigration tests individual task migration scenarios
func (ft *FailoverTester) testTaskMigration(ctx context.Context, t *testing.T, taskContext string, expectedResumed bool) {
	// Create backup agent with test configuration
	backupHealth := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("test-migration-%s", taskContext),
			Namespace: "test-namespace",
		},
		Spec: ksquadv1alpha1.BackupAgentHealthSpec{
			RuntimeType:        "opencode",
			EndpointURL:        "http://ollama.test.svc.cluster.local:11434/v1",
			TaskTransferEnabled: true,
		},
		Status: ksquadv1alpha1.BackupAgentHealthStatus{
			Ready: true,
		},
	}

	err := ft.backupClient.Create(ctx, backupHealth)
	require.NoError(t, err, "Failed to create backup agent for task migration test")
	defer func() {
		ft.backupClient.Delete(ctx, backupHealth)
	}()

	// Simulate task migration
	migrationResult := ft.simulateTaskMigration(ctx, t, backupHealth, taskContext)
	
	assert.Equal(t, expectedResumed, migrationResult.TaskResumed, 
		"Task should be resumed as expected")
	assert.Equal(t, expectedResumed, migrationResult.ContextPreserved,
		"Context should be preserved as expected")
	
	// Record migration metrics
	metrics.RecordTaskMigration(taskContext, migrationResult.TaskResumed, migrationResult.Duration)
}

// TaskMigrationResult represents the result of a task migration test
type TaskMigrationResult struct {
	TaskResumed    bool
	ContextPreserved bool
	Duration       time.Duration
	Errors         []string
}

// simulateTaskMigration simulates task migration from primary to backup agent
func (ft *FailoverTester) simulateTaskMigration(ctx context.Context, t *testing.T, backupHealth *ksquadv1alpha1.BackupAgentHealth, taskContext string) TaskMigrationResult {
	startTime := time.Now()
	
	// Simulate task migration process
	migration := &TaskMigration{
		TaskID:         "test-task-123",
		PrimaryAgent:   "primary-agent",
		BackupAgent:    backupHealth.Name,
		OriginalContext: taskContext,
		MigrationTime: startTime,
	}

	// Simulate context transfer
	contextTransferred := ft.simulateContextTransfer(ctx, t, migration)
	
	// Simulate task resumption
	taskResumed := ft.simulateTaskResumption(ctx, t, migration)
	
	// Validate migration integrity
	errors := ft.validateMigrationIntegrity(ctx, t, migration)
	
	return TaskMigrationResult{
		TaskResumed:    taskResumed,
		ContextPreserved: contextTransferred,
		Duration:       time.Since(startTime),
		Errors:         errors,
	}
}

// simulateContextTransfer simulates context transfer during failover
func (ft *FailoverTester) simulateContextTransfer(ctx context.Context, t *testing.T, migration *TaskMigration) bool {
	// In a real implementation, this would handle actual context transfer
	// For testing, we'll validate context transfer logic
	
	if len(migration.OriginalContext) > 10000 { // Large context
		// Context should be truncated appropriately
		return len(migration.TransferredContext) <= 10000 && 
		       strings.Contains(migration.TransferredContext, migration.TaskID)
	}
	
	// Small context should be transferred completely
	return migration.TransferredContext == migration.OriginalContext
}

// simulateTaskResumption simulates task resumption after failover
func (ft *FailoverTester) simulateTaskResumption(ctx context.Context, t *testing.T, migration *TaskMigration) bool {
	// Check if backup agent can resume the task
	backupHealth := &ksquadv1alpha1.BackupAgentHealth{}
	err := ft.backupClient.Get(ctx, types.NamespacedName{Name: migration.BackupAgent, Namespace: "test-namespace"}, backupHealth)
	if err != nil {
		return false
	}
	
	// Verify backup agent has the capability to resume the task
	return backupHealth.Status.Ready && backupHealth.Spec.TaskTransferEnabled
}

// validateMigrationIntegrity validates that the migration was performed correctly
func (ft *FailoverTester) validateMigrationIntegrity(ctx context.Context, t *testing.T, migration *TaskMigration) []string {
	var errors []string
	
	// Check that task ID is preserved
	if !strings.Contains(migration.TransferredContext, migration.TaskID) {
		errors = append(errors, "Task ID not preserved during migration")
	}
	
	// Check that migration time is recorded
	if migration.MigrationTime.IsZero() {
		errors = append(errors, "Migration time not recorded")
	}
	
	// Check backup agent has necessary capabilities
	if migration.BackupAgent == "" {
		errors = append(errors, "Backup agent not specified in migration")
	}
	
	return errors
}

// TestFailoverPerformance measures failover performance metrics
func (ft *FailoverTester) TestFailoverPerformance(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), ft.testTimeout)
	defer cancel()

	// Test failover performance under various load conditions
	testScenarios := []struct {
		name           string
		loadLevel      string // "low", "medium", "high"
		concurrentFails int
	}{
		{
			name:           "Low Load Failover",
			loadLevel:      "low",
			concurrentFails: 1,
		},
		{
			name:           "Medium Load Failover",
			loadLevel:      "medium", 
			concurrentFails: 5,
		},
		{
			name:           "High Load Failover",
			loadLevel:      "high",
			concurrentFails: 10,
		},
	}

	for _, scenario := range testScenarios {
		t.Run(scenario.name, func(t *testing.T) {
			ft.testFailoverPerformanceUnderLoad(ctx, t, scenario)
		})
	}
}

// testFailoverPerformanceUnderLoad tests failover performance under specific load conditions
func (ft *FailoverTester) testFailoverPerformanceUnderLoad(ctx context.Context, t *testing.T, scenario struct {
	name           string
	loadLevel      string
	concurrentFails int
}) {
	startTime := time.Now()
	
	// Create backup agents for concurrent failover testing
	var backupAgents []*ksquadv1alpha1.BackupAgentHealth
	for i := 0; i < scenario.concurrentFails; i++ {
		backupHealth := &ksquadv1alpha1.BackupAgentHealth{
			ObjectMeta: metav1.ObjectMeta{
				Name:      fmt.Sprintf("test-perf-backup-%d-%s", i, scenario.loadLevel),
				Namespace: "test-namespace",
			},
			Spec: ksquadv1alpha1.BackupAgentHealthSpec{
				RuntimeType:           "opencode",
				EndpointURL:           "http://ollama.test.svc.cluster.local:11434/v1",
				FailureThreshold:      3,
			},
		}
		
		err := ft.backupClient.Create(ctx, backupHealth)
		require.NoError(t, err, "Failed to create backup agent for performance test")
		backupAgents = append(backupAgents, backupHealth)
	}
	
	// Cleanup backup agents
	defer func() {
		for _, backup := range backupAgents {
			ft.backupClient.Delete(ctx, backup)
		}
	}()

	// Simulate concurrent primary agent failures
	var wg sync.WaitGroup
	resultChan := make(chan FailoverPerformanceResult, scenario.concurrentFails)
	
	for i, backup := range backupAgents {
		wg.Add(1)
		go func(index int, backupAgent *ksquadv1alpha1.BackupAgentHealth) {
			defer wg.Done()
			
			failStart := time.Now()
			ft.simulatePrimaryFailure(ctx, t, "crash")
			
			// Wait for backup ready
			ready := ft.waitForBackupReady(ctx, t, backupAgent.Name)
			
			resultChan <- FailoverPerformanceResult{
				AgentIndex:     index,
				FailoverTime:  time.Since(failStart),
				Success:        ready,
				LoadLevel:     scenario.loadLevel,
			}
		}(i, backup)
	}
	
	wg.Wait()
	close(resultChan)
	
	// Collect and analyze results
	var results []FailoverPerformanceResult
	for result := range resultChan {
		results = append(results, result)
	}
	
	// Analyze performance metrics
	ft.analyzeFailoverPerformance(t, results, time.Since(startTime), scenario)
}

// FailoverPerformanceResult represents the performance metrics for a failover test
type FailoverPerformanceResult struct {
	AgentIndex     int
	FailoverTime  time.Duration
	Success        bool
	LoadLevel     string
}

// analyzeFailoverPerformance analyzes failover performance metrics
func (ft *FailoverTester) analyzeFailoverPerformance(t *testing.T, results []FailoverPerformanceResult, totalTime time.Duration, scenario struct {
	name           string
	loadLevel      string
	concurrentFails int
}) {
	// Calculate performance metrics
	var totalFailoverTime time.Duration
	var successfulFails int
	
	for _, result := range results {
		totalFailoverTime += result.FailoverTime
		if result.Success {
			successfulFails++
		}
	}
	
	averageFailoverTime := totalFailoverTime / time.Duration(len(results))
	successRate := float64(successfulFails) / float64(len(results)) * 100
	
	// Verify performance requirements
	assert.Less(t, averageFailoverTime, 30*time.Second, 
		"Average failover time should be less than 30 seconds")
	assert.GreaterOrEqual(t, successRate, 95.0, 
		"Failover success rate should be at least 95%")
	
	// Record performance metrics
	metrics.RecordFailoverPerformance(scenario.name, averageFailoverTime, successRate, totalTime)
	
	t.Logf("Performance Test Results - %s:", scenario.name)
	t.Logf("  Average Failover Time: %v", averageFailoverTime)
	t.Logf("  Success Rate: %.2f%%", successRate)
	t.Logf("  Total Test Time: %v", totalTime)
}

// Integration with existing falsification test framework
func (ft *FailoverTester) TestFailoverFalsification(t *testing.T) {
	// Extend existing falsification framework with failover scenarios
	testCases := []struct {
		name        string
		mutation    string
		shouldBreak bool
	}{
		{
			name:        "Concurrent Failover",
			mutation:    "concurrent_failover",
			shouldBreak: true,
		},
		{
			name:        "Context Loss During Migration",
			mutation:    "context_loss",
			shouldBreak: true,
		},
		{
			name:        "Backup Agent Not Ready",
			mutation:    "backup_not_ready",
			shouldBreak: true,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			ft.testFailoverFalsification(t, tc.mutation, tc.shouldBreak)
		})
	}
}

// testFailoverFalsification tests failover scenarios with mutations to verify robustness
func (ft *FailoverTester) testFailoverFalsification(t *testing.T, mutation string, shouldBreak bool) {
	// Setup falsification test environment
	originalConfig := ft.getCurrentConfig()
	defer ft.restoreConfig(originalConfig)
	
	// Apply mutation
	ft.applyFailoverMutation(mutation)
	
	// Run failover test
	success := ft.runFailoverTest(t)
	
	if shouldBreak {
		assert.False(t, success, "Failover should fail with mutation: %s", mutation)
	} else {
		assert.True(t, success, "Failover should succeed with mutation: %s", mutation)
	}
}

// getCurrentConfig gets the current test configuration
func (ft *FailoverTester) getCurrentConfig() TestConfig {
	return TestConfig{
		FailureThreshold:   3,
		HealthCheckInterval: 10 * time.Second,
		TaskTransferEnabled: true,
	}
}

// applyFailoverMutation applies a mutation to test failover robustness
func (ft *FailoverTester) applyFailoverMutation(mutation string) {
	switch mutation {
	case "concurrent_failover":
		// Simulate multiple concurrent failovers
		ft.concurrentFails = 10
	case "context_loss":
		// Simulate context loss during migration
		ft.contextLossEnabled = true
	case "backup_not_ready":
		// Simulate backup agent not being ready
		ft.backupReadyEnabled = false
	}
}