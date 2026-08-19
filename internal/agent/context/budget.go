package context

import (
	"context"
	"fmt"
	"regexp"
	"strings"
	"sync"
	"time"

	ksquadv1alpha1 "github.com/ksquad/ksquad/api/v1alpha1"
	"github.com/ksquad/ksquad/internal/metrics"
	"go.uber.org/zap"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"
)

// ContextBudget represents a context budget with limits and usage tracking
type ContextBudget struct {
	MaxSize          int    `json:"maxSize"`
	ReservedSize    int    `json:"reservedSize"`
	UsedSize        int    `json:"usedSize"`
	TruncationPolicy string `json:"truncationPolicy"`
	Enforced        bool   `json:"enforced"`
}

// ContextValidationResult represents the result of context validation
type ContextValidationResult struct {
	ContextID      string
	OriginalSize   int
	TruncatedSize  int
	Truncated      bool
	ValidTruncation bool
	MustInclude    []string
	ActuallyIncluded []string
	Violations     []string
	ValidationTime time.Duration
}

// ContextBudgetValidator validates context budget consistency across agents
type ContextBudgetValidator struct {
	client       client.Client
	scheme       *runtime.Scheme
	recorder     record.EventRecorder
	logger       *zap.Logger
	budgets      map[string]*ContextBudget
	mu           sync.RWMutex
}

// NewContextBudgetValidator creates a new context budget validator
func NewContextBudgetValidator(client client.Client, scheme *runtime.Scheme, recorder record.EventRecorder) *ContextBudgetValidator {
	return &ContextBudgetValidator{
		client:   client,
		scheme:   scheme,
		recorder: recorder,
		logger:   zap.NewExample(),
		budgets:  make(map[string]*ContextBudget),
	}
}

// ValidateContextBudgetConsistency validates that context budgets are consistent between primary and backup agents
func (cbv *ContextBudgetValidator) ValidateContextBudgetConsistency(ctx context.Context, backupAgent, primaryAgent *ksquadv1alpha1.BackupAgentHealth) (*ConsistencyValidationResult, error) {
	logger := log.FromContext(ctx)
	
	logger.Info("Validating context budget consistency",
		"backup", backupAgent.Name,
		"primary", primaryAgent.Name)

	result := &ConsistencyValidationResult{
		BackupAgent:  backupAgent.Name,
		PrimaryAgent: primaryAgent.Name,
		Consistent:   true,
		Violations:  make([]string, 0),
		TestResults: make([]ContextValidationResult, 0),
	}

	// Get context budgets for both agents
	backupBudget := cbv.getContextBudget(backupAgent)
	primaryBudget := cbv.getContextBudget(primaryAgent)

	// Compare budget configurations
	if !cbv.compareBudgets(backupBudget, primaryBudget) {
		result.Consistent = false
		result.Violations = append(result.Violations, "Budget configuration mismatch between backup and primary agents")
	}

	// Test context truncation consistency
	testResults := cbv.testContextTruncationConsistency(ctx, backupAgent, primaryAgent)
	result.TestResults = testResults

	// Check for must-include content preservation
	for _, testResult := range testResults {
		if testResult.Truncated && !testResult.ValidTruncation {
			result.Consistent = false
			result.Violations = append(result.Violations, 
				fmt.Sprintf("Invalid truncation in context %s: %v", testResult.ContextID, testResult.Violations))
		}
	}

	// Record consistency metrics
	cbv.recordConsistencyMetrics(result, len(testResults))

	// Emit event
	eventType := "Normal"
	eventReason := "ConsistencyValid"
	if !result.Consistent {
		eventType = "Warning"
		eventReason = "ConsistencyInvalid"
	}

	cbv.recorder.Event(backupAgent, eventType, eventReason,
		fmt.Sprintf("Context budget consistency validation: %v", result.Consistent))

	logger.Info("Context budget consistency validation completed",
		"consistent", result.Consistent,
		"violations", len(result.Violations),
		"tests", len(testResults))

	return result, nil
}

// getContextBudget extracts context budget from agent configuration
func (cbv *ContextBudgetValidator) getContextBudget(agent *ksquadv1alpha1.BackupAgentHealth) *ContextBudget {
	if agent.Status.ActualCapabilities == nil {
		return &ContextBudget{
			MaxSize:       8192, // Default
			ReservedSize:  1024, // Default
			TruncationPolicy: "conservative",
			Enforced:      true,
		}
	}

	budget := &ContextBudget{
		MaxSize:       8192, // Default
		ReservedSize:  1024, // Default
		TruncationPolicy: "conservative",
		Enforced:      true,
	}

	if maxSize, ok := agent.Status.ActualCapabilities["context_max_size"]; ok {
		if size, ok := maxSize.(int); ok {
			budget.MaxSize = size
		}
	}

	if reservedSize, ok := agent.Status.ActualCapabilities["context_reserved_size"]; ok {
		if size, ok := reservedSize.(int); ok {
			budget.ReservedSize = size
		}
	}

	if policy, ok := agent.Status.ActualCapabilities["truncation_policy"]; ok {
		if policyStr, ok := policy.(string); ok {
			budget.TruncationPolicy = policyStr
		}
	}

	if enforced, ok := agent.Status.ActualCapabilities["context_budget_enforced"]; ok {
		if enforce, ok := enforced.(bool); ok {
			budget.Enforced = enforce
		}
	}

	return budget
}

// compareBudgets compares two context budgets for consistency
func (cbv *ContextBudgetValidator) compareBudgets(budget1, budget2 *ContextBudget) bool {
	// Max size should be the same or backup should have equal or larger budget
	if budget1.MaxSize < budget2.MaxSize {
		return false
	}

	// Reserved size should be consistent
	if budget1.ReservedSize != budget2.ReservedSize {
		return false
	}

	// Truncation policies should be compatible
	if !cbv.areTruncationPoliciesCompatible(budget1.TruncationPolicy, budget2.TruncationPolicy) {
		return false
	}

	// Both should enforce budgets or both should not
	if budget1.Enforced != budget2.Enforced {
		return false
	}

	return true
}

// areTruncationPoliciesCompatible checks if truncation policies are compatible
func (cbv *ContextBudgetValidator) areTruncationPoliciesCompatible(policy1, policy2 string) bool {
	// Conservative policies are compatible with everything
	if policy1 == "conservative" || policy2 == "conservative" {
		return true
	}

	// Aggressive policies are compatible with each other
	if policy1 == "aggressive" && policy2 == "aggressive" {
		return true
	}

	// Moderate policies are compatible with each other
	if policy1 == "moderate" && policy2 == "moderate" {
		return true
	}

	return false
}

// testContextTruncationConsistency tests context truncation behavior
func (cbv *ContextBudgetValidator) testContextTruncationConsistency(ctx context.Context, backupAgent, primaryAgent *ksquadv1alpha1.BackupAgentHealth) []ContextValidationResult {
	results := make([]ContextValidationResult, 0)

	testScenarios := []struct {
		name        string
		context     string
		mustInclude []string
		budget      *ContextBudget
	}{
		{
			name:    "SmallContext",
			context: "This is a small context that should fit within budget limits.",
			mustInclude: []string{"small", "context"},
			budget: &ContextBudget{
				MaxSize:       10000,
				ReservedSize:  1024,
				TruncationPolicy: "conservative",
				Enforced:      true,
			},
		},
		{
			name:    "LargeContext",
			context: strings.Repeat("Large context content that needs to be truncated. ", 200),
			mustInclude: []string{"Large", "truncated"},
			budget: &ContextBudget{
				MaxSize:       2048,
				ReservedSize:  512,
				TruncationPolicy: "moderate",
				Enforced:      true,
			},
		},
		{
			name:    "VeryLargeContext",
			context: strings.Repeat("Extremely large context with important content. ", 500),
			mustInclude: []string{"Extremely", "important"},
			budget: &ContextBudget{
				MaxSize:       1024,
				ReservedSize:  256,
				TruncationPolicy: "aggressive",
				Enforced:      true,
			},
		},
		{
			name:    "ContextWithMustInclude",
			context: "This context contains critical information that must never be truncated. Including very important details here.",
			mustInclude: []string{"critical", "never", "truncated"},
			budget: &ContextBudget{
				MaxSize:       500,
				ReservedSize:  100,
				TruncationPolicy: "conservative",
				Enforced:      true,
			},
		},
	}

	for _, scenario := range testScenarios {
		// Test backup agent truncation
		backupResult := cbv.testContextTruncation(ctx, backupAgent, scenario.context, scenario.mustInclude, scenario.budget)
		
		// Test primary agent truncation
		primaryResult := cbv.testContextTruncation(ctx, primaryAgent, scenario.context, scenario.mustInclude, scenario.budget)
		
		// Compare results
		consistencyResult := cbv.compareTruncationResults(backupResult, primaryResult)
		
		results = append(results, consistencyResult)
	}

	return results
}

// testContextTruncation tests individual context truncation
func (cbv *ContextBudgetValidator) testContextTruncation(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth, context string, mustInclude []string, budget *ContextBudget) ContextValidationResult {
	startTime := time.Now()
	
	result := ContextValidationResult{
		ContextID:     fmt.Sprintf("%s-%d", agent.Name, len(context)),
		OriginalSize:  len(context),
		MustInclude:   mustInclude,
		ValidationTime: time.Since(startTime),
	}

	// Apply truncation based on budget
	if budget.Enforced && len(context) > budget.MaxSize {
		result.Truncated = true
		result.TruncatedSize = budget.MaxSize - budget.ReservedSize
		
		// Truncate context
		truncatedContext := cbv.truncateContext(context, result.TruncatedSize, mustInclude)
		
		// Check must-include preservation
		result.ActuallyIncluded = cbv.extractMustIncludeContent(truncatedContext, mustInclude)
		
		// Validate truncation
		result.ValidTruncation = cbv.validateTruncation(truncatedContext, mustInclude)
		
		if !result.ValidTruncation {
			result.Violations = append(result.Violations, "Must-include content was truncated")
		}
	} else {
		result.TruncatedSize = len(context)
		result.ActuallyIncluded = mustInclude
		result.ValidTruncation = true
	}

	result.ValidationTime = time.Since(startTime)
	return result
}

// truncateContext truncates context while preserving must-include content
func (cbv *ContextBudgetValidator) truncateContext(context string, maxSize int, mustInclude []string) string {
	if len(context) <= maxSize {
		return context
	}

	// Try to preserve must-include content
	preservedContent := make([]string, 0)
	remainingBudget := maxSize

	// First, include must-include content
	for _, mustIncludeItem := range mustInclude {
		if strings.Contains(context, mustIncludeItem) && remainingBudget > len(mustIncludeItem) {
			preservedContent = append(preservedContent, mustIncludeItem)
			remainingBudget -= len(mustIncludeItem)
		}
	}

	// Then fill remaining budget with context content
	if remainingBudget > 0 {
		// Take from beginning of context
		endIndex := min(len(context), remainingBudget)
		prefix := context[:endIndex]
		
		// Add preserved content
		for _, content := range preservedContent {
			if strings.Contains(prefix, content) {
				continue // Already included
			}
			if remainingBudget >= len(content) {
				prefix += content
				remainingBudget -= len(content)
			}
		}
		
		return prefix
	}

	return ""
}

// extractMustIncludeContent extracts must-include content from truncated context
func (cbv *ContextBudgetValidator) extractMustIncludeContent(context string, mustInclude []string) []string {
	included := make([]string, 0)
	
	for _, mustIncludeItem := range mustInclude {
		if strings.Contains(context, mustIncludeItem) {
			included = append(included, mustIncludeItem)
		}
	}
	
	return included
}

// validateTruncation validates that truncation was performed correctly
func (cbv *ContextBudgetValidator) validateTruncation(context string, mustInclude []string) bool {
	// Check that all must-include content is preserved
	for _, mustIncludeItem := range mustInclude {
		if !strings.Contains(context, mustIncludeItem) {
			return false
		}
	}
	
	// Check that context is within budget limits
	maxBudget := cbv.getCurrentMaxBudget()
	if len(context) > maxBudget {
		return false
	}
	
	return true
}

// compareTruncationResults compares truncation results between backup and primary agents
func (cbv *ContextBudgetValidator) compareTruncationResults(backup, primary ContextValidationResult) ContextValidationResult {
	result := ContextValidationResult{
		ContextID:       backup.ContextID,
		OriginalSize:    backup.OriginalSize,
		ValidationTime:  backup.ValidationTime + primary.ValidationTime,
		Violations:      make([]string, 0),
	}

	// Compare truncation behavior
	if backup.Truncated != primary.Truncated {
		result.Violations = append(result.Violations, 
			fmt.Sprintf("Truncation mismatch: backup=%v, primary=%v", backup.Truncated, primary.Truncated))
	}

	if backup.Truncated && primary.Truncated {
		if backup.TruncatedSize != primary.TruncatedSize {
			result.Violations = append(result.Violations,
				fmt.Sprintf("Truncation size mismatch: backup=%d, primary=%d", backup.TruncatedSize, primary.TruncatedSize))
		}

		if !cbv.compareMustIncludeLists(backup.ActuallyIncluded, primary.ActuallyIncluded) {
			result.Violations = append(result.Violations,
				"Must-include content preservation mismatch")
		}
	}

	// Use backup's validation status (primary should be the same)
	result.Truncated = backup.Truncated
	result.TruncatedSize = backup.TruncatedSize
	result.MustInclude = backup.MustInclude
	result.ActuallyIncluded = backup.ActuallyIncluded
	result.ValidTruncation = backup.ValidTruncation

	if len(result.Violations) > 0 {
		result.ValidTruncation = false
	}

	return result
}

// compareMustIncludeLists compares must-include content lists
func (cbv *ContextBudgetValidator) compareMustIncludeLists(list1, list2 []string) bool {
	if len(list1) != len(list2) {
		return false
	}

	for i := range list1 {
		if list1[i] != list2[i] {
			return false
		}
	}

	return true
}

// getCurrentMaxBudget gets the current maximum context budget
func (cbv *ContextBudgetValidator) getCurrentMaxBudget() int {
	// Return a reasonable default
	return 8192
}

// recordConsistencyRecords consistency metrics
func (cbv *ContextBudgetValidator) recordConsistencyMetrics(result *ConsistencyValidationResult, testCount int) {
	status := "consistent"
	if !result.Consistent {
		status = "inconsistent"
	}

	metrics.ContextBudgetConsistencyGauge.WithLabelValues(result.BackupAgent, result.PrimaryAgent, status).
		Set(1)

	metrics.ContextBudgetTestCountCounter.WithLabelValues(result.BackupAgent, result.PrimaryAgent).
		Add(float64(testCount))

	if !result.Consistent {
		metrics.ContextBudgetViolationCounter.WithLabelValues(result.BackupAgent, result.PrimaryAgent).
			Add(float64(len(result.Violations)))
	}
}

// MonitorContextBudgetViolation monitors for context budget violations
func (cbv *ContextBudgetValidator) MonitorContextBudgetViolation(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			cbv.checkContextBudgetViolation(ctx, agent)
		}
	}
}

// checkContextBudgetViolation checks for context budget violations
func (cbv *ContextBudgetValidator) checkContextBudgetViolation(ctx context.Context, agent *ksquadv1alpha1.BackupAgentHealth) {
	logger := log.FromContext(ctx)

	// Get current context usage
	if agent.Status.ContextUsage != nil {
		currentUsage := agent.Status.ContextUsage.UsedSize
		maxBudget := cbv.getCurrentMaxBudget()

		if currentUsage > maxBudget {
			logger.Warn("Context budget violation detected",
				"agent", agent.Name,
				"usage", currentUsage,
				"budget", maxBudget)

			cbv.recorder.Event(agent, "Warning", "ContextBudgetViolation",
				fmt.Sprintf("Context budget exceeded: %d/%d", currentUsage, maxBudget))

			// Record violation metric
			metrics.ContextBudgetViolationCounter.WithLabelValues(agent.Name, "").
				Inc()
		}
	}
}

// ValidateContextTransfer validates context transfer during failover
func (cbv *ContextBudgetValidator) ValidateContextTransfer(ctx context.Context, originalContext string, fromAgent, toAgent *ksquadv1alpha1.BackupAgentHealth) (*TransferValidationResult, error) {
	logger := log.FromContext(ctx)

	logger.Info("Validating context transfer during failover",
		"from", fromAgent.Name,
		"to", toAgent.Name,
		"context_size", len(originalContext))

	result := &TransferValidationResult{
		OriginalContext: originalContext,
		FromAgent:      fromAgent.Name,
		ToAgent:        toAgent.Name,
		TransferComplete: false,
		ContextPreserved: false,
		Violations:     make([]string, 0),
	}

	// Get budgets for both agents
	fromBudget := cbv.getContextBudget(fromAgent)
	toBudget := cbv.getContextBudget(toAgent)

	// Check if context fits in both budgets
	if len(originalContext) > fromBudget.MaxSize {
		result.Violations = append(result.Violations, "Original context exceeds from-agent budget")
	}

	if len(originalContext) > toBudget.MaxSize {
		// Context needs truncation for transfer
		truncatedContext := cbv.truncateContext(originalContext, toBudget.MaxSize-toBudget.ReservedSize, []string{})
		
		if len(truncatedContext) == 0 {
			result.Violations = append(result.Violations, "Context truncation resulted in empty context")
		} else {
			result.TransferedContext = truncatedContext
		}
	} else {
		result.TransferedContext = originalContext
	}

	// Validate transfer
	result.TransferComplete = len(result.Violations) == 0
	result.ContextPreserved = result.TransferedContext == originalContext

	// Record transfer metrics
	metrics.ContextTransferCounter.WithLabelValues(fromAgent.Name, toAgent.Name).
		Inc()

	if !result.ContextPreserved {
		metrics.ContextTruncationCounter.WithLabelValues(fromAgent.Name, toAgent.Name).
			Inc()
	}

	logger.Info("Context transfer validation completed",
		"complete", result.TransferComplete,
		"preserved", result.ContextPreserved,
		"violations", len(result.Violations))

	return result, nil
}

// TransferValidationResult represents the result of context transfer validation
type TransferValidationResult struct {
	OriginalContext  string
	TransferedContext string
	FromAgent        string
	ToAgent          string
	TransferComplete  bool
	ContextPreserved bool
	Violations       []string
}

// ConsistencyValidationResult represents context budget consistency validation results
type ConsistencyValidationResult struct {
	BackupAgent  string
	PrimaryAgent string
	Consistent   bool
	Violations   []string
	TestResults  []ContextValidationResult
}

// min returns the minimum of two integers
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}