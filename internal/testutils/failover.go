package testutils

import (
	"context"
	"fmt"
	"sync"
	"time"

	ksquadv1alpha1 "github.com/ksquad/ksquad/api/v1alpha1"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// FailoverTestUtils provides common utilities for failover testing
type FailoverTestUtils struct {
	client          client.Client
	testTimeout     time.Duration
	cleanupMutex    sync.Mutex
	cleanupItems    []client.Object
}

// NewFailoverTestUtils creates a new failover test utilities instance
func NewFailoverTestUtils(client client.Client, timeout time.Duration) *FailoverTestUtils {
	return &FailoverTestUtils{
		client:      client,
		testTimeout: timeout,
	}
}

// CreateTestBackupAgent creates a test backup agent health resource
func (ftu *FailoverTestUtils) CreateTestBackupAgent(ctx context.Context, name string, spec ksquadv1alpha1.BackupAgentHealthSpec) *ksquadv1alpha1.BackupAgentHealth {
	backupAgent := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("test-backup-%s", name),
			Namespace: "test-namespace",
		},
		Spec: spec,
	}

	err := ftu.client.Create(ctx, backupAgent)
	require.NoError(ftu.client, err, "Failed to create test backup agent")

	// Register for cleanup
	ftu.registerForCleanup(backupAgent)

	return backupAgent
}

// CreateTestPrimaryAgent creates a test primary agent pod
func (ftu *FailoverTestUtils) CreateTestPrimaryAgent(ctx context.Context, name string) *corev1.Pod {
	primaryAgent := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("test-primary-%s", name),
			Namespace: "test-namespace",
		},
		Spec: corev1.PodSpec{
			Containers: []corev1.Container{
				{
					Name:  "primary-agent",
					Image: "ghcr.io/ksquad/agents:latest",
					Env: []corev1.EnvVar{
						{
							Name:  "AGENT_ROLE",
							Value: "primary",
						},
					},
				},
			},
		},
	}

	err := ftu.client.Create(ctx, primaryAgent)
	require.NoError(ftu.client, err, "Failed to create test primary agent")

	// Register for cleanup
	ftu.registerForCleanup(primaryAgent)

	return primaryAgent
}

// SimulatePrimaryAgentFailure simulates different types of primary agent failures
func (ftu *FailoverTestUtils) SimulatePrimaryAgentFailure(ctx context.Context, pod *corev1.Pod, failureType string) {
	switch failureType {
	case "crash":
		ftu.simulatePodCrash(ctx, pod)
	case "timeout":
		ftu.simulatePodTimeout(ctx, pod)
	case "resource_exhaustion":
		ftu.simulateResourceExhaustion(ctx, pod)
	default:
		panic(fmt.Sprintf("Unknown failure type: %s", failureType))
	}
}

// simulatePodCrash simulates a pod crash by setting its phase to Failed
func (ftu *FailoverTestUtils) simulatePodCrash(ctx context.Context, pod *corev1.Pod) {
	pod.Status.Phase = corev1.PodFailed
	pod.Status.Message = "Pod crashed"
	
	patch := client.MergeFrom(pod.DeepCopy())
	err := ftu.client.Status().Patch(ctx, pod, patch)
	require.NoError(ftu.client, err, "Failed to patch pod status to simulate crash")
}

// simulatePodTimeout simulates a pod timeout by marking it as unresponsive
func (ftu *FailoverTestUtils) simulatePodTimeout(ctx context.Context, pod *corev1.Pod) {
	now := metav1.Now()
	pod.Status.Conditions = append(pod.Status.Conditions, corev1.PodCondition{
		Type:               "Ready",
		Status:             corev1.ConditionFalse,
		LastTransitionTime: now,
		Reason:             "Timeout",
		Message:            "Pod became unresponsive",
	})
	
	patch := client.MergeFrom(pod.DeepCopy())
	err := ftu.client.Status().Patch(ctx, pod, patch)
	require.NoError(ftu.client, err, "Failed to patch pod status to simulate timeout")
}

// simulateResourceExhaustion simulates resource exhaustion by setting high resource usage
func (ftu *FailoverTestUtils) simulateResourceExhaustion(ctx context.Context, pod *corev1.Pod) {
	// In a real implementation, this would simulate actual resource exhaustion
	// For testing, we'll mark the pod as having resource issues
	pod.Status.Phase = corev1.PodPending
	pod.Status.Reason = "ResourceExhausted"
	
	patch := client.MergeFrom(pod.DeepCopy())
	err := ftu.client.Status().Patch(ctx, pod, patch)
	require.NoError(ftu.client, err, "Failed to patch pod status to simulate resource exhaustion")
}

// WaitForBackupAgentReady waits for a backup agent to become ready
func (ftu *FailoverTestUtils) WaitForBackupAgentReady(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) bool {
	return ftu.waitForCondition(ctx, backupAgent, func(obj client.Object) bool {
		if backupAgent, ok := obj.(*ksquadv1alpha1.BackupAgentHealth); ok {
			return backupAgent.Status.Ready
		}
		return false
	})
}

// WaitForBackupAgentStatus waits for a backup agent to reach a specific status
func (ftu *FailoverTestUtils) WaitForBackupAgentStatus(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth, expectedStatus bool) bool {
	return ftu.waitForCondition(ctx, backupAgent, func(obj client.Object) bool {
		if backupAgent, ok := obj.(*ksquadv1alpha1.BackupAgentHealth); ok {
			return backupAgent.Status.Ready == expectedStatus
		}
		return false
	})
}

// waitForCondition waits for a specific condition to be met
func (ftu *FailoverTestUtils) waitForCondition(ctx context.Context, obj client.Object, conditionFunc func(client.Object) bool) bool {
	pollInterval := 2 * time.Second
	timeout := ftu.testTimeout - (5 * time.Second) // Leave some buffer
	
	startTime := time.Now()
	for time.Since(startTime) < timeout {
		err := ftu.client.Get(ctx, types.NamespacedName{Name: obj.GetName(), Namespace: obj.GetNamespace()}, obj)
		if err != nil {
			return false
		}
		
		if conditionFunc(obj) {
			return true
		}
		
		time.Sleep(pollInterval)
	}
	
	return false
}

// CreateTaskMigrationScenario creates a task migration scenario for testing
func (ftu *FailoverTestUtils) CreateTaskMigrationScenario(ctx context.Context, backupAgentName string, taskContext string) *TaskMigrationScenario {
	return &TaskMigrationScenario{
		BackupAgentName: backupAgentName,
		TaskContext:     taskContext,
		CreatedAt:       metav1.Now(),
		TransferComplete: false,
		ContextPreserved: false,
	}
}

// TaskMigrationScenario represents a task migration test scenario
type TaskMigrationScenario struct {
	BackupAgentName string            `json:"backupAgentName"`
	TaskContext     string            `json:"taskContext"`
	CreatedAt       metav1.Time       `json:"createdAt"`
	TransferComplete bool             `json:"transferComplete"`
	ContextPreserved bool             `json:"contextPreserved"`
	Errors          []string          `json:"errors"`
	Metrics         MigrationMetrics  `json:"metrics"`
}

// MigrationMetrics tracks migration performance metrics
type MigrationMetrics struct {
	Duration       time.Duration `json:"duration"`
	ContextSize    int          `json:"contextSize"`
	TransferRate   float64      `json:"transferRate"`
	SuccessRate    float64      `json:"successRate"`
}

// SimulateTaskMigration simulates task migration from primary to backup agent
func (ftu *FailoverTestUtils) SimulateTaskMigration(ctx context.Context, scenario *TaskMigrationScenario) error {
	startTime := time.Now()
	
	// Get backup agent
	backupAgent := &ksquadv1alpha1.BackupAgentHealth{}
	err := ftu.client.Get(ctx, types.NamespacedName{Name: scenario.BackupAgentName, Namespace: "test-namespace"}, backupAgent)
	if err != nil {
		return fmt.Errorf("failed to get backup agent: %w", err)
	}
	
	// Simulate context transfer
	contextTransferred := ftu.simulateContextTransfer(ctx, backupAgent, scenario.TaskContext)
	
	// Update scenario
	scenario.TransferComplete = true
	scenario.ContextPreserved = contextTransferred
	scenario.Metrics.Duration = time.Since(startTime)
	scenario.Metrics.ContextSize = len(scenario.TaskContext)
	
	if !contextTransferred {
		scenario.Errors = append(scenario.Errors, "Context transfer failed")
	}
	
	// Update backup agent status
	backupAgent.Status.TaskTransferComplete = scenario.TransferComplete
	backupAgent.Status.ContextPreserved = scenario.ContextPreserved
	backupAgent.Status.LastTransferTime = metav1.Now()
	
	patch := client.MergeFrom(backupAgent.DeepCopy())
	err = ftu.client.Status().Patch(ctx, backupAgent, patch)
	if err != nil {
		scenario.Errors = append(scenario.Errors, fmt.Sprintf("Failed to update backup agent status: %v", err))
	}
	
	return nil
}

// simulateContextTransfer simulates context transfer during failover
func (ftu *FailoverTestUtils) simulateContextTransfer(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth, context string) bool {
	// In a real implementation, this would handle actual context transfer
	// For testing, we'll simulate context transfer logic
	
	maxContextSize := 10000 // Typical context limit
	
	if len(context) > maxContextSize {
		// Large contexts should be truncated appropriately
		return len(context) <= maxContextSize*2 // Allow some expansion
	}
	
	return true // Small contexts should transfer completely
}

// CreateLoadBalancingScenario creates a load balancing scenario for testing
func (ftu *FailoverTestUtils) CreateLoadBalancingScenario(ctx context.Context, numBackups int, numTasks int) *LoadBalancingScenario {
	backups := make([]*ksquadsquad1.BackupAgentHealth, numBackups)
	tasks := make([]Task, numTasks)
	
	// Create backup agents
	for i := 0; i < numBackups; i++ {
		backup := ftu.CreateTestBackupAgent(ctx, fmt.Sprintf("load-balanced-%d", i), ksquadv1alpha1.BackupAgentHealthSpec{
			RuntimeType: "opencode",
			EndpointURL: "http://ollama.test.svc.cluster.local:11434/v1",
		})
		backups[i] = backup
	}
	
	// Create test tasks
	for i := 0; i < numTasks; i++ {
		tasks[i] = Task{
			ID:         fmt.Sprintf("task-%d", i),
			Context:    fmt.Sprintf("task context %d", i),
			Priority:   "medium",
			Complexity: "medium",
		}
	}
	
	return &LoadBalancingScenario{
		BackupAgents: backups,
		Tasks:        tasks,
		CreatedAt:    metav1.Now(),
		Distribution: make(map[string]int),
	}
}

// LoadBalancingScenario represents a load balancing test scenario
type LoadBalancingScenario struct {
	BackupAgents []*ksquadv1alpha1.BackupAgentHealth `json:"backupAgents"`
	Tasks        []Task                               `json:"tasks"`
	CreatedAt    metav1.Time                          `json:"createdAt"`
	Distribution map[string]int                      `json:"distribution"`
}

// Task represents a test task
type Task struct {
	ID         string `json:"id"`
	Context    string `json:"context"`
	Priority   string `json:"priority"`
	Complexity string `json:"complexity"`
}

// SimulateLoadBalancing simulates load balancing across backup agents
func (ftu *FailoverTestUtils) SimulateLoadBalancing(ctx context.Context, scenario *LoadBalancingScenario) error {
	// Distribute tasks across backup agents
	tasksPerBackup := len(scenario.Tasks) / len(scenario.BackupAgents)
	
	for i, backup := range scenario.BackupAgents {
		startIdx := i * tasksPerBackup
		endIdx := startIdx + tasksPerBackup
		if i == len(scenario.BackupAgents)-1 {
			endIdx = len(scenario.Tasks) // Last agent gets remaining tasks
		}
		
		batchTasks := scenario.Tasks[startIdx:endIdx]
		
		// Simulate task assignment
		err := ftu.assignTasksToBackup(ctx, backup, batchTasks)
		if err != nil {
			return fmt.Errorf("failed to assign tasks to backup %s: %w", backup.Name, err)
		}
		
		// Update distribution
		scenario.Distribution[backup.Name] = len(batchTasks)
	}
	
	return nil
}

// assignTasksToBackup assigns tasks to a backup agent
func (ftu *FailoverTestUtils) assignTasksToBackup(ctx context.Context, backup *ksquadv1alpha1.BackupAgentHealth, tasks []Task) error {
	// Update backup agent with assigned tasks
	backup.Status.AssignedTasks = len(tasks)
	backup.Status.LastTaskAssignment = metav1.Now()
	
	patch := client.MergeFrom(backup.DeepCopy())
	err := ftu.client.Status().Patch(ctx, backup, patch)
	if err != nil {
		return fmt.Errorf("failed to update backup agent task assignment: %w", err)
	}
	
	return nil
}

// ValidateFailoverResults validates the results of failover testing
func (ftu *FailoverTestUtils) ValidateFailoverResults(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth, expectedReady bool) error {
	// Get latest backup agent status
	err := ftu.client.Get(ctx, types.NamespacedName{Name: backupAgent.Name, Namespace: backupAgent.Namespace}, backupAgent)
	if err != nil {
		return fmt.Errorf("failed to get backup agent status: %w", err)
	}
	
	// Validate readiness
	if backupAgent.Status.Ready != expectedReady {
		return fmt.Errorf("backup agent readiness mismatch: expected %v, got %v", expectedReady, backupAgent.Status.Ready)
	}
	
	// Validate health check history
	if len(backupAgent.Status.HealthCheckHistory) == 0 {
		return fmt.Errorf("no health check history found")
	}
	
	// Validate recent health check
	latestCheck := backupAgent.Status.HealthCheckHistory[len(backupAgent.Status.HealthCheckHistory)-1]
	if latestCheck.Timestamp.IsZero() {
		return fmt.Errorf("invalid health check timestamp")
	}
	
	return nil
}

// registerForCleanup registers an object for cleanup after testing
func (ftu *FailoverTestUtils) registerForCleanup(obj client.Object) {
	ftu.cleanupMutex.Lock()
	defer ftu.cleanupMutex.Unlock()
	
	ftu.cleanupItems = append(ftu.cleanupItems, obj)
}

// CleanupTestResources cleans up all test resources
func (ftu *FailoverTestUtils) CleanupTestResources(ctx context.Context) error {
	ftu.cleanupMutex.Lock()
	defer ftu.cleanupMutex.Unlock()
	
	var lastErr error
	
	// Delete all cleanup items in reverse order (dependencies)
	for i := len(ftu.cleanupItems) - 1; i >= 0; i-- {
		obj := ftu.cleanupItems[i]
		err := ftu.client.Delete(ctx, obj)
		if err != nil {
			lastErr = fmt.Errorf("failed to delete %s/%s: %w", obj.GetNamespace(), obj.GetName(), err)
		}
	}
	
	// Clear cleanup items
	ftu.cleanupItems = ftu.cleanupItems[:0]
	
	return lastErr
}

// AssertFailoverMetrics asserts that failover metrics meet expectations
func (ftu *FailoverTestUtils) AssertFailoverMetrics(t *testing.T, metrics MigrationMetrics, maxDuration time.Duration, minSuccessRate float64) {
	assert.Less(t, metrics.Duration, maxDuration, "Migration should complete within time limit")
	assert.GreaterOrEqual(t, metrics.SuccessRate, minSuccessRate, "Success rate should meet minimum threshold")
	
	if metrics.ContextSize > 10000 {
		assert.Less(t, metrics.Duration, 30*time.Second, "Large context migration should complete quickly")
	} else {
		assert.Less(t, metrics.Duration, 10*time.Second, "Small context migration should be fast")
	}
}

// BenchmarkFailover benchmarks failover performance
func (ftu *FailoverTestUtils) BenchmarkFailover(b *testing.B, backupAgent *ksquadv1alpha1.BackupAgentHealth, numTasks int) {
	ctx := context.Background()
	
	b.ResetTimer()
	
	for i := 0; i < b.N; i++ {
		// Create test scenario
		scenario := ftu.CreateTaskMigrationScenario(ctx, backupAgent.Name, "test context")
		
		// Simulate task migration
		err := ftu.SimulateTaskMigration(ctx, scenario)
		assert.NoError(b, err, "Task migration should succeed")
		
		// Validate results
		err = ftu.ValidateFailoverResults(ctx, backupAgent, true)
		assert.NoError(b, err, "Failover results should be valid")
	}
}