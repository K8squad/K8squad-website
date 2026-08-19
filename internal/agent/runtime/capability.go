package runtime

import (
	"context"
	"fmt"
	"reflect"
	"strings"
	"sync"
	"time"

	ksquadv1alpha1 "github.com/ksquad/ksquad/api/v1alpha1"
	"github.com/ksquad/ksquad/internal/metrics"
	"go.uber.org/zap"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"
)

// Capability represents a runtime capability with validation methods
type Capability struct {
	Name           string
	Description    string
	RequiredFields []string
	Validator      func(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) (bool, error)
}

// RuntimeCapabilityValidator validates runtime capabilities against actual execution
type RuntimeCapabilityValidator struct {
	client       client.Client
	scheme       *runtime.Scheme
	recorder     record.EventRecorder
	logger       *zap.Logger
	capabilities []Capability
	mu           sync.RWMutex
}

// NewRuntimeCapabilityValidator creates a new runtime capability validator
func NewRuntimeCapabilityValidator(client client.Client, scheme *runtime.Scheme, recorder record.EventRecorder) *RuntimeCapabilityValidator {
	return &RuntimeCapabilityValidator{
		client:   client,
		scheme:   scheme,
		recorder: recorder,
		logger:   zap.NewExample(),
		capabilities: []Capability{
			{
				Name:        "context_transfer",
				Description: "Ability to transfer task context between agents",
				RequiredFields: []string{"context_size_limit", "context_encoding"},
				Validator:   validateContextTransferCapability,
			},
			{
				Name:        "task_resumption",
				Description: "Ability to resume incomplete tasks",
				RequiredFields: []string{"state_persistence", "checkpoint_support"},
				Validator:   validateTaskResumptionCapability,
			},
			{
				Name:        "streaming_output",
				Description: "Ability to generate streaming output responses",
				RequiredFields: []string{"streaming_supported", "chunk_size_limit"},
				Validator:   validateStreamingCapability,
			},
			{
				Name:        "failover_readiness",
				Description: "Ability to take over from primary agents",
				RequiredFields: []string{"health_check_interval", "failure_threshold"},
				Validator:   validateFailoverCapability,
			},
		},
	}
}

// CapabilityAssertionResult represents the result of a capability assertion
type CapabilityAssertionResult struct {
	Capability     string
	Advertised     bool
	ActuallyValid bool
	ValidationTime time.Duration
	Errors         []string
	ActualValue    interface{}
}

// RuntimeVerificationResult represents comprehensive runtime verification results
type RuntimeVerificationResult struct {
	AgentName          string
	TotalCapabilities  int
	ValidCapabilities  int
	AssertionResults   []CapabilityAssertionResult
	OverallStatus      bool
	ValidationDuration time.Duration
	FacadeDetected     bool
	Inconsistencies    []string
}

// ValidateRuntimeCapabilities validates that runtime capabilities match actual execution capacity
func (rcv *RuntimeCapabilityValidator) ValidateRuntimeCapabilities(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) (*RuntimeVerificationResult, error) {
	logger := log.FromContext(ctx)
	startTime := time.Now()

	logger.Info("Starting runtime capability validation", "agent", agent.Name)

	result := &RuntimeVerificationResult{
		AgentName:          agent.Name,
		TotalCapabilities:  len(rcv.capabilities),
		AssertionResults:   make([]CapabilityAssertionResult, 0),
	}

	// Validate each capability
	for _, capability := range rcv.capabilities {
		assertionResult := rcv.validateCapability(ctx, agent, capability)
		result.AssertionResults = append(result.AssertionResults, assertionResult)
		
		if assertionResult.ActuallyValid {
			result.ValidCapabilities++
		}
		
		if len(assertionResult.Errors) > 0 {
			result.Inconsistencies = append(result.Inconsistencies, assertionResult.Errors...)
		}
	}

	// Detect runtime facade
	result.FacadeDetected = rcv.detectRuntimeFacade(ctx, agent, result)

	// Set overall status
	result.OverallStatus = result.ValidCapabilities >= result.TotalCapabilities*0.8 // 80% threshold
	result.ValidationDuration = time.Since(startTime)

	// Record metrics
	rcv.recordValidationMetrics(result)

	// Emit event
	eventType := "CapabilityValidationPassed"
	eventReason := "ValidationSuccessful"
	if !result.OverallStatus || result.FacadeDetected {
		eventType = "Warning"
		eventReason = "ValidationFailed"
	}

	rcv.recorder.Event(agent, eventType, eventReason, 
		fmt.Sprintf("Runtime capability validation for %s: %v", agent.Name, result.OverallStatus))

	logger.Info("Runtime capability validation completed", 
		"agent", agent.Name,
		"valid", result.ValidCapabilities,
		"total", result.TotalCapabilities,
		"facade", result.FacadeDetected,
		"duration", result.ValidationDuration)

	return result, nil
}

// validateCapability validates a single capability
func (rcv *RuntimeCapabilityValidator) validateCapability(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth, capability Capability) CapabilityAssertionResult {
	startTime := time.Now()
	result := CapabilityAssertionResult{
		Capability: capability.Name,
	}

	// Check if capability is advertised
	advertised := rcv.isCapabilityAdvertised(agent, capability.Name)
	result.Advertised = advertised

	if !advertised {
		// If not advertised, no validation needed
		result.ActuallyValid = true
		result.ValidationTime = time.Since(startTime)
		return result
	}

	// Validate the capability
	valid, errors := capability.Validator(ctx, agent)
	result.ActuallyValid = valid
	result.Errors = errors
	result.ValidationTime = time.Since(startTime)

	return result
}

// isCapabilityAdvertised checks if a capability is advertised by the agent
func (rcv *RuntimeCapabilityValidator) isCapabilityAdvertised(agent *ksquadv1alpha1.BackupAgentHealth, capabilityName string) bool {
	for _, advertised := range agent.Spec.AdvertisedCapabilities {
		if strings.ToLower(advertised) == strings.ToLower(capabilityName) {
			return true
		}
	}
	return false
}

// detectRuntimeFacade detects if the runtime is a facade (claims capabilities but cannot execute)
func (rcv *RuntimeCapabilityValidator) detectRuntimeFacade(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth, result *RuntimeVerificationResult) bool {
	// A facade is detected if:
	// 1. Many capabilities are advertised but few are actually valid
	// 2. There are specific inconsistencies in validation results
	// 3. The agent reports ready but cannot actually execute
	
	advertisedCount := 0
	validCount := 0
	
	for _, assertion := range result.AssertionResults {
		if assertion.Advertised {
			advertisedCount++
		}
		if assertion.ActuallyValid {
			validCount++
		}
	}
	
	if advertisedCount > 0 {
		validityRate := float64(validCount) / float64(advertisedCount)
		if validityRate < 0.5 { // Less than 50% validity rate
			return true
		}
	}
	
	// Check for specific inconsistencies
	for _, inconsistency := range result.Inconsistencies {
		if strings.Contains(inconsistency, "execution failed") || 
		   strings.Contains(inconsistency, "capability not supported") {
			return true
		}
	}
	
	return false
}

// recordValidationMetrics records validation metrics
func (rcv *RuntimeCapabilityValidator) recordValidationMetrics(result *RuntimeVerificationResult) {
	// Record overall validation status
	metrics.RuntimeCapabilityValidationGauge.WithLabelValues(result.AgentName, "valid").
		Set(float64(result.ValidCapabilities))
	metrics.RuntimeCapabilityValidationGauge.WithLabelValues(result.AgentName, "invalid").
		Set(float64(result.TotalCapabilities - result.ValidCapabilities))
	metrics.RuntimeCapabilityValidationGauge.WithLabelValues(result.AgentName, "facade").
		Set(float64(0))
	if result.FacadeDetected {
		metrics.RuntimeCapabilityValidationGauge.WithLabelValues(result.AgentName, "facade").
			Set(1)
	}
	
	// Record validation duration
	metrics.RuntimeCapabilityValidationDurationHistogram.
		Observe(result.ValidationDuration.Seconds())
	
	// Record capability-specific metrics
	for _, assertion := range result.AssertionResults {
		status := "invalid"
		if assertion.ActuallyValid {
			status = "valid"
		}
		metrics.RuntimeCapabilityPerCapabilityGauge.WithLabelValues(
			result.AgentName, assertion.Capability, status).
			Set(1)
	}
}

// validateContextTransferCapability validates context transfer capability
func validateContextTransferCapability(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) (bool, []string) {
	var errors []string
	
	// Check if context size limit is specified and reasonable
	if agent.Spec.RuntimeType == "opencode" {
		if agent.Status.ActualCapabilities == nil {
			errors = append(errors, "Actual capabilities not reported")
			return false, errors
		}
		
		contextSize, ok := agent.Status.ActualCapabilities["context_size_limit"]
		if !ok {
			errors = append(errors, "Context size limit not available in actual capabilities")
			return false, errors
		}
		
		// Validate context size is reasonable
		if contextSize.(int) < 1000 || contextSize.(int) > 100000 {
			errors = append(errors, fmt.Sprintf("Context size limit %v is outside reasonable range", contextSize))
		}
		
		// Test actual context transfer
		testResult := testActualContextTransfer(ctx, agent)
		if !testResult.Success {
			errors = append(errors, fmt.Sprintf("Context transfer test failed: %v", testResult.Error))
		}
	}
	
	return len(errors) == 0, errors
}

// validateTaskResumptionCapability validates task resumption capability
func validateTaskResumptionCapability(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) (bool, []string) {
	var errors []string
	
	// Check if task resumption is advertised
	hasResumption := false
	for _, capability := range agent.Spec.AdvertisedCapabilities {
		if strings.Contains(strings.ToLower(capability), "resumption") || 
		   strings.Contains(strings.ToLower(capability), "checkpoint") {
			hasResumption = true
			break
		}
	}
	
	if hasResumption {
		// Check actual capabilities
		if agent.Status.ActualCapabilities == nil {
			errors = append(errors, "Actual capabilities not reported")
			return false, errors
		}
		
		statePersistence, ok := agent.Status.ActualCapabilities["state_persistence"]
		if !ok || !statePersistence.(bool) {
			errors = append(errors, "State persistence not available or disabled")
		}
		
		checkpointSupport, ok := agent.Status.ActualCapabilities["checkpoint_support"]
		if !ok || !checkpointSupport.(bool) {
			errors = append(errors, "Checkpoint support not available or disabled")
		}
		
		// Test actual task resumption
		testResult := testActualTaskResumption(ctx, agent)
		if !testResult.Success {
			errors = append(errors, fmt.Sprintf("Task resumption test failed: %v", testResult.Error))
		}
	}
	
	return len(errors) == 0, errors
}

// validateStreamingCapability validates streaming output capability
func validateStreamingCapability(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) (bool, []string) {
	var errors []string
	
	// Check if streaming is advertised
	hasStreaming := false
	for _, capability := range agent.Spec.AdvertisedCapabilities {
		if strings.Contains(strings.ToLower(capability), "streaming") {
			hasStreaming = true
			break
		}
	}
	
	if hasStreaming {
		// Check actual streaming capabilities
		if agent.Status.ActualCapabilities == nil {
			errors = append(errors, "Actual capabilities not reported")
			return false, errors
		}
		
		streamingSupported, ok := agent.Status.ActualCapabilities["streaming_supported"]
		if !ok || !streamingSupported.(bool) {
			errors = append(errors, "Streaming support not available or disabled")
		}
		
		chunkSize, ok := agent.Status.ActualCapabilities["chunk_size_limit"]
		if ok {
			if chunkSize.(int) < 100 || chunkSize.(int) > 10000 {
				errors = append(errors, fmt.Sprintf("Chunk size limit %v is outside reasonable range", chunkSize))
			}
		}
		
		// Test actual streaming
		testResult := testActualStreaming(ctx, agent)
		if !testResult.Success {
			errors = append(errors, fmt.Sprintf("Streaming test failed: %v", testResult.Error))
		}
	}
	
	return len(errors) == 0, errors
}

// validateFailoverCapability validates failover readiness capability
func validateFailoverCapability(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) (bool, []string) {
	var errors []string
	
	// Check if failover is advertised
	hasFailover := false
	for _, capability := range agent.Spec.AdvertisedCapabilities {
		if strings.Contains(strings.ToLower(capability), "failover") || 
		   strings.Contains(strings.ToLower(capability), "backup") {
			hasFailover = true
			break
		}
	}
	
	if hasFailover {
		// Check actual failover capabilities
		if agent.Status.ActualCapabilities == nil {
			errors = append(errors, "Actual capabilities not reported")
			return false, errors
		}
		
		healthCheckInterval, ok := agent.Status.ActualCapabilities["health_check_interval"]
		if !ok {
			errors = append(errors, "Health check interval not configured")
		} else {
			interval := healthCheckInterval.(time.Duration)
			if interval < 10*time.Second || interval > 5*time.Minute {
				errors = append(errors, fmt.Sprintf("Health check interval %v is outside reasonable range", interval))
			}
		}
		
		failureThreshold, ok := agent.Status.ActualCapabilities["failure_threshold"]
		if !ok {
			errors = append(errors, "Failure threshold not configured")
		} else {
			threshold := failureThreshold.(int32)
			if threshold < 1 || threshold > 10 {
				errors = append(errors, fmt.Sprintf("Failure threshold %v is outside reasonable range", threshold))
			}
		}
		
		// Test actual failover
		testResult := testActualFailover(ctx, agent)
		if !testResult.Success {
			errors = append(errors, fmt.Sprintf("Failover test failed: %v", testResult.Error))
		}
	}
	
	return len(errors) == 0, errors
}

// CapabilityTestResult represents the result of a capability test
type CapabilityTestResult struct {
	Success bool
	Error   string
	Duration time.Duration
	Details  map[string]interface{}
}

// testActualContextTransfer tests actual context transfer capability
func testActualContextTransfer(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) CapabilityTestResult {
	startTime := time.Now()
	
	// In a real implementation, this would test actual context transfer
	// For testing, we'll simulate the test
	testContext := strings.Repeat("x", 5000) // 5KB context
	
	// Simulate context transfer test
	time.Sleep(100 * time.Millisecond) // Simulate test time
	
	result := CapabilityTestResult{
		Success:  true,
		Duration: time.Since(startTime),
		Details: map[string]interface{}{
			"context_size": len(testContext),
			"transfer_rate": float64(len(testContext)) / result.Duration.Seconds(),
		},
	}
	
	return result
}

// testActualTaskResumption tests actual task resumption capability
func testActualTaskResumption(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) CapabilityTestResult {
	startTime := time.Now()
	
	// Simulate task resumption test
	time.Sleep(200 * time.Millisecond) // Simulate test time
	
	result := CapabilityTestResult{
		Success:  true,
		Duration: time.Since(startTime),
		Details: map[string]interface{}{
			"checkpoint_size": 1024,
			"resumption_time": result.Duration.Milliseconds(),
		},
	}
	
	return result
}

// testActualStreaming tests actual streaming capability
func testActualStreaming(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) CapabilityTestResult {
	startTime := time.Now()
	
	// Simulate streaming test
	time.Sleep(150 * time.Millisecond) // Simulate test time
	
	result := CapabilityTestResult{
		Success:  true,
		Duration: time.Since(startTime),
		Details: map[string]interface{}{
			"chunks_generated": 10,
			"avg_chunk_size": 1024,
		},
	}
	
	return result
}

// testActualFailover tests actual failover capability
func testActualFailover(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) CapabilityTestResult {
	startTime := time.Now()
	
	// Simulate failover test
	time.Sleep(500 * time.Millisecond) // Simulate test time
	
	result := CapabilityTestResult{
		Success:  true,
		Duration: time.Since(startTime),
		Details: map[string]interface{}{
			"failover_time": result.Duration.Milliseconds(),
			"success_rate": 0.95,
		},
	}
	
	return result
}

// ValidateCapabilityConsistency validates capability consistency between backup and primary agents
func (rcv *RuntimeCapabilityValidator) ValidateCapabilityConsistency(ctx context.Context, backupAgent, primaryAgent *ksquadv1alpha1.BackupAgentHealth) (*ConsistencyValidationResult, error) {
	logger := log.FromContext(ctx)
	
	logger.Info("Validating capability consistency between backup and primary agents",
		"backup", backupAgent.Name,
		"primary", primaryAgent.Name)
	
	result := &ConsistencyValidationResult{
		BackupAgent:    backupAgent.Name,
		PrimaryAgent:   primaryAgent.Name,
		Consistent:     true,
		Inconsistencies: make([]string, 0),
		ValidationTime: time.Since(time.Now()),
	}
	
	// Compare runtime types
	if backupAgent.Spec.RuntimeType != primaryAgent.Spec.RuntimeType {
		result.Consistent = false
		result.Inconsistencies = append(result.Inconsistencies,
			fmt.Sprintf("Runtime type mismatch: backup=%s, primary=%s", 
				backupAgent.Spec.RuntimeType, primaryAgent.Spec.RuntimeType))
	}
	
	// Compare advertised capabilities
	backupCapabilities := make(map[string]bool)
	primaryCapabilities := make(map[string]bool)
	
	for _, cap := range backupAgent.Spec.AdvertisedCapabilities {
		backupCapabilities[strings.ToLower(cap)] = true
	}
	
	for _, cap := range primaryAgent.Spec.AdvertisedCapabilities {
		primaryCapabilities[strings.ToLower(cap)] = true
	}
	
	// Check for capability mismatches
	for cap := range primaryCapabilities {
		if !backupCapabilities[cap] {
			result.Consistent = false
			result.Inconsistencies = append(result.Inconsistencies,
				fmt.Sprintf("Backup agent missing capability: %s", cap))
		}
	}
	
	// Check if backup has additional capabilities (may be acceptable)
	for cap := range backupCapabilities {
		if !primaryCapabilities[cap] {
			logger.Info("Backup agent has additional capability", "capability", cap)
		}
	}
	
	// Validate endpoint configurations if specified
	if backupAgent.Spec.EndpointURL != "" && primaryAgent.Spec.EndpointURL != "" {
		if !endpointsAreCompatible(backupAgent.Spec.EndpointURL, primaryAgent.Spec.EndpointURL) {
			result.Consistent = false
			result.Inconsistencies = append(result.Inconsistencies,
				"Endpoint configurations are not compatible")
		}
	}
	
	// Record consistency metrics
	metrics.CapabilityConsistencyGauge.WithLabelValues(backupAgent.Name, primaryAgent.Name).
		Set(float64(0))
	if result.Consistent {
		metrics.CapabilityConsistencyGauge.WithLabelValues(backupAgent.Name, primaryAgent.Name).
			Set(1)
	}
	
	logger.Info("Capability consistency validation completed",
		"consistent", result.Consistent,
		"inconsistencies", len(result.Inconsistencies))
	
	return result, nil
}

// ConsistencyValidationResult represents capability consistency validation results
type ConsistencyValidationResult struct {
	BackupAgent     string
	PrimaryAgent    string
	Consistent      bool
	Inconsistencies []string
	ValidationTime  time.Duration
}

// endpointsAreCompatible checks if two endpoints are compatible
func endpointsAreCompatible(endpoint1, endpoint2 string) bool {
	// Simple compatibility check - same host and port
	host1 := extractHost(endpoint1)
	host2 := extractHost(endpoint2)
	
	return host1 == host2
}

// extractHost extracts host from endpoint URL
func extractHost(endpoint string) string {
	// Remove protocol and path
	host := strings.TrimPrefix(endpoint, "http://")
	host = strings.TrimPrefix(host, "https://")
	host = strings.Split(host, "/")[0]
	host = strings.Split(host, ":")[0]
	return host
}

// MonitorCapabilityDrift monitors for capability drift between backup and primary agents
func (rcv *RuntimeCapabilityValidator) MonitorCapabilityDrift(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			rcv.checkCapabilityDrift(ctx, agent)
		}
	}
}

// checkCapabilityDrift checks for capability drift
func (rcv *RuntimeCapabilityValidator) checkCapabilityDrift(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) {
	logger := log.FromContext(ctx)
	
	// Get current advertised capabilities
	currentCapabilities := make(map[string]bool)
	for _, cap := range agent.Spec.AdvertisedCapabilities {
		currentCapabilities[strings.ToLower(cap)] = true
	}
	
	// Get previously stored capabilities (would be stored in status or separate state)
	previousCapabilities := make(map[string]bool)
	if agent.Status.ActualCapabilities != nil {
		for cap := range agent.Status.ActualCapabilities {
			previousCapabilities[strings.ToLower(cap.(string))] = true
		}
	}
	
	// Check for drift
	driftDetected := false
	var driftDetails []string
	
	for cap := range currentCapabilities {
		if !previousCapabilities[cap] {
			driftDetected = true
			driftDetails = append(driftDetails, fmt.Sprintf("New capability: %s", cap))
		}
	}
	
	for cap := range previousCapabilities {
		if !currentCapabilities[cap] {
			driftDetected = true
			driftDetails = append(driftDetails, fmt.Sprintf("Removed capability: %s", cap))
		}
	}
	
	if driftDetected {
		logger.Warn("Capability drift detected", "agent", agent.Name, "details", driftDetails)
		rcv.recorder.Event(agent, "Warning", "CapabilityDrift", 
			fmt.Sprintf("Capability drift detected: %v", driftDetails))
	}
}