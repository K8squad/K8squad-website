package runtime

import (
	"context"
	"testing"
	"time"

	ksquadv1alpha1 "github.com/ksquad/ksquad/api/v1alpha1"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
)

// TestRuntimeCapabilityValidation tests the main runtime capability validation functionality
func TestRuntimeCapabilityValidation(t *testing.T) {
	// Create test client and scheme
	scheme := runtime.NewScheme()
	_ = ksquadv1alpha1.AddToScheme(scheme)

	// Create test backup agent
	backupAgent := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-capability-agent",
			Namespace: "test-namespace",
		},
		Spec: ksquadv1alpha1.BackupAgentHealthSpec{
			RuntimeType:           "opencode",
			EndpointURL:           "http://ollama.test.svc.cluster.local:11434/v1",
			AdvertisedCapabilities: []string{
				"context_transfer",
				"task_resumption", 
				"streaming_output",
			},
		},
		Status: ksquadv1alpha1.BackupAgentHealthStatus{
			ActualCapabilities: map[string]interface{}{
				"context_size_limit": 8192,
				"state_persistence": true,
				"checkpoint_support": true,
				"streaming_supported": true,
				"chunk_size_limit": 2048,
				"health_check_interval": 30 * time.Second,
				"failure_threshold": int32(3),
			},
		},
	}

	// Create validator
	validator := NewRuntimeCapabilityValidator(nil, scheme, nil)

	// Test successful validation
	t.Run("SuccessfulValidation", func(t *testing.T) {
		result, err := validator.ValidateRuntimeCapabilities(context.Background(), backupAgent)
		
		require.NoError(t, err)
		assert.True(t, result.OverallStatus)
		assert.Equal(t, 3, result.ValidCapabilities)
		assert.Equal(t, 3, result.TotalCapabilities)
		assert.False(t, result.FacadeDetected)
		assert.Len(t, result.Inconsistencies, 0)
	})

	// Test facade detection
	t.Run("FacadeDetection", func(t *testing.T) {
		facadeAgent := backupAgent.DeepCopy()
		facadeAgent.Spec.AdvertisedCapabilities = []string{
			"context_transfer",
			"task_resumption", 
			"streaming_output",
			"failover_readiness",
		}
		facadeAgent.Status.ActualCapabilities = map[string]interface{}{
			"context_size_limit": 100, // Unrealistically small
			"state_persistence": false, // Missing capability
		}

		result, err := validator.ValidateRuntimeCapabilities(context.Background(), facadeAgent)
		
		require.NoError(t, err)
		assert.False(t, result.OverallStatus)
		assert.True(t, result.FacadeDetected)
		assert.Less(t, result.ValidCapabilities, result.TotalCapabilities)
	})

	// Test missing capabilities
	t.Run("MissingCapabilities", func(t *testing.T) {
		minimalAgent := backupAgent.DeepCopy()
		minimalAgent.Spec.AdvertisedCapabilities = []string{}
		minimalAgent.Status.ActualCapabilities = nil

		result, err := validator.ValidateRuntimeCapabilities(context.Background(), minimalAgent)
		
		require.NoError(t, err)
		assert.True(t, result.OverallStatus) // No advertised capabilities = no validation needed
		assert.Equal(t, 0, result.ValidCapabilities)
		assert.Equal(t, 3, result.TotalCapabilities)
	})
}

// TestCapabilityValidationIndividual tests individual capability validation
func TestCapabilityValidationIndividual(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = ksquadv1alpha1.AddToScheme(scheme)
	validator := NewRuntimeCapabilityValidator(nil, scheme, nil)

	testCases := []struct {
		name           string
		capabilityName string
		agentConfig    func() *ksquadv1alpha1.BackupAgentHealth
		expectedValid  bool
	}{
		{
			name:           "ContextTransferValid",
			capabilityName: "context_transfer",
			agentConfig: func() *ksquadv1alpha1.BackupAgentHealth {
				return &ksquadv1alpha1.BackupAgentHealth{
					Spec: ksquadv1alpha1.BackupAgentHealthSpec{
						AdvertisedCapabilities: []string{"context_transfer"},
					},
					Status: ksquadv1alpha1.BackupAgentHealthStatus{
						ActualCapabilities: map[string]interface{}{
							"context_size_limit": 8192,
						},
					},
				}
			},
			expectedValid: true,
		},
		{
			name:           "ContextTransferInvalid",
			capabilityName: "context_transfer",
			agentConfig: func() *ksquadv1alpha1.BackupAgentHealth {
				return &ksquadv1alpha1.BackupAgentHealth{
					Spec: ksquadv1alpha1.BackupAgentHealthSpec{
						AdvertisedCapabilities: []string{"context_transfer"},
					},
					Status: ksquadv1alpha1.BackupAgentHealthStatus{
						ActualCapabilities: map[string]interface{}{
							"context_size_limit": 100, // Unrealistically small
						},
					},
				}
			},
			expectedValid: false,
		},
		{
			name:           "TaskResumptionValid",
			capabilityName: "task_resumption",
			agentConfig: func() *ksquadv1alpha1.BackupAgentHealth {
				return &ksquadv1alpha1.BackupAgentHealth{
					Spec: ksquadv1alpha1.BackupAgentHealthSpec{
						AdvertisedCapabilities: []string{"task_resumption"},
					},
					Status: ksquadv1alpha1.BackupAgentHealthStatus{
						ActualCapabilities: map[string]interface{}{
							"state_persistence": true,
							"checkpoint_support": true,
						},
					},
				}
			},
			expectedValid: true,
		},
		{
			name:           "StreamingValid",
			capabilityName: "streaming_output",
			agentConfig: func() *ksquadv1alpha1.BackupAgentHealth {
				return &ksquadv1alpha1.BackupAgentHealth{
					Spec: ksquadv1alpha1.BackupAgentHealthSpec{
						AdvertisedCapabilities: []string{"streaming_output"},
					},
					Status: ksquadv1alpha1.BackupAgentHealthStatus{
						ActualCapabilities: map[string]interface{}{
							"streaming_supported": true,
							"chunk_size_limit": 2048,
						},
					},
				}
			},
			expectedValid: true,
		},
		{
			name:           "FailoverValid",
			capabilityName: "failover_readiness",
			agentConfig: func() *ksquadv1alpha1.BackupAgentHealth {
				return &ksquadv1alpha1.BackupAgentHealth{
					Spec: ksquadv1alpha1.BackupAgentHealthSpec{
						AdvertisedCapabilities: []string{"failover_readiness"},
					},
					Status: ksquadv1alpha1.BackupAgentHealthStatus{
						ActualCapabilities: map[string]interface{}{
							"health_check_interval": 30 * time.Second,
							"failure_threshold": int32(3),
						},
					},
				}
			},
			expectedValid: true,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			agent := tc.agentConfig()
			
			// Find the capability
			var capability *Capability
			for _, cap := range validator.capabilities {
				if cap.Name == tc.capabilityName {
					capability = &cap
					break
				}
			}
			require.NotNil(t, capability, "Capability not found")
			
			// Validate the capability
			valid, errors := capability.Validator(context.Background(), agent)
			
			assert.Equal(t, tc.expectedValid, valid, "Capability validation result mismatch")
			if tc.expectedValid {
				assert.Len(t, errors, 0, "No errors expected for valid capability")
			} else {
				assert.Greater(t, len(errors), 0, "Errors expected for invalid capability")
			}
		})
	}
}

// TestCapabilityConsistency tests capability consistency validation
func TestCapabilityConsistency(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = ksquadv1alpha1.AddToScheme(scheme)
	validator := NewRuntimeCapabilityValidator(nil, scheme, nil)

	t.Run("ConsistentAgents", func(t *testing.T) {
		backupAgent := &ksquadv1alpha1.BackupAgentHealth{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test-backup",
				Namespace: "test-namespace",
			},
			Spec: ksquadv1alpha1.BackupAgentHealthSpec{
				RuntimeType:           "opencode",
				EndpointURL:           "http://ollama.test.svc.cluster.local:11434/v1",
				AdvertisedCapabilities: []string{"context_transfer", "task_resumption"},
			},
		}

		primaryAgent := &ksquadv1alpha1.BackupAgentHealth{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test-primary",
				Namespace: "test-namespace",
			},
			Spec: ksquadv1alpha1.BackupAgentHealthSpec{
				RuntimeType:           "opencode",
				EndpointURL:           "http://ollama.test.svc.cluster.local:11434/v1",
				AdvertisedCapabilities: []string{"context_transfer", "task_resumption"},
			},
		}

		result, err := validator.ValidateCapabilityConsistency(context.Background(), backupAgent, primaryAgent)
		
		require.NoError(t, err)
		assert.True(t, result.Consistent)
		assert.Len(t, result.Inconsistencies, 0)
	})

	t.Run("InconsistentAgents", func(t *testing.T) {
		backupAgent := &ksquadv1alpha1.BackupAgentHealth{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test-backup",
				Namespace: "test-namespace",
			},
			Spec: ksquadv1alpha1.BackupAgentHealthSpec{
				RuntimeType:           "opencode",
				EndpointURL:           "http://ollama.test.svc.cluster.local:11434/v1",
				AdvertisedCapabilities: []string{"context_transfer"},
			},
		}

		primaryAgent := &ksquadv1alpha1.BackupAgentHealth{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test-primary",
				Namespace: "test-namespace",
			},
			Spec: ksquadv1alpha1.BackupAgentHealthSpec{
				RuntimeType:           "hermes", // Different runtime type
				EndpointURL:           "https://api.anthropic.com/v1",
				AdvertisedCapabilities: []string{"context_transfer", "task_resumption"},
			},
		}

		result, err := validator.ValidateCapabilityConsistency(context.Background(), backupAgent, primaryAgent)
		
		require.NoError(t, err)
		assert.False(t, result.Consistent)
		assert.Greater(t, len(result.Inconsistencies), 0)
		assert.Contains(t, result.Inconsistencies[0], "Runtime type mismatch")
	})
}

// TestFacadeDetection tests runtime facade detection
func TestFacadeDetection(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = ksquadv1alpha1.AddToScheme(scheme)
	validator := NewRuntimeCapabilityValidator(nil, scheme, nil)

	t.Run("ValidAgentNotFacade", func(t *testing.T) {
		agent := &ksquadv1alpha1.BackupAgentHealth{
			Spec: ksquadv1alpha1.BackupAgentHealthSpec{
				AdvertisedCapabilities: []string{"context_transfer"},
			},
			Status: ksquadv1alpha1.BackupAgentHealthStatus{
				ActualCapabilities: map[string]interface{}{
					"context_size_limit": 8192,
				},
			},
		}

		result := &RuntimeVerificationResult{
			TotalCapabilities: 4,
			AssertionResults: []CapabilityAssertionResult{
				{
					Capability:     "context_transfer",
					Advertised:     true,
					ActuallyValid: true,
				},
				{
					Capability:     "task_resumption",
					Advertised:     false,
					ActuallyValid: true,
				},
				{
					Capability:     "streaming_output",
					Advertised:     false,
					ActuallyValid: true,
				},
				{
					Capability:     "failover_readiness",
					Advertised:     false,
					ActuallyValid: true,
				},
			},
		}

		isFacade := validator.detectRuntimeFacade(context.Background(), agent, result)
		assert.False(t, isFacade, "Valid agent should not be detected as facade")
	})

	t.Run("FacadeAgent", func(t *testing.T) {
		agent := &ksquadv1alpha1.BackupAgentHealth{
			Spec: ksquadv1alpha1.BackupAgentHealthSpec{
				AdvertisedCapabilities: []string{"context_transfer", "task_resumption", "streaming_output"},
			},
			Status: ksquadv1alpha1.BackupAgentHealthStatus{
				ActualCapabilities: map[string]interface{}{
					"context_size_limit": 100, // Unrealistically small
				},
			},
		}

		result := &RuntimeVerificationResult{
			TotalCapabilities: 4,
			AssertionResults: []CapabilityAssertionResult{
				{
					Capability:     "context_transfer",
					Advertised:     true,
					ActuallyValid: false,
				},
				{
					Capability:     "task_resumption",
					Advertised:     true,
					ActuallyValid: false,
				},
				{
					Capability:     "streaming_output",
					Advertised:     true,
					ActuallyValid: false,
				},
				{
					Capability:     "failover_readiness",
					Advertised:     false,
					ActuallyValid: true,
				},
			},
			Inconsistencies: []string{"execution failed", "capability not supported"},
		}

		isFacade := validator.detectRuntimeFacade(context.Background(), agent, result)
		assert.True(t, isFacade, "Invalid agent should be detected as facade")
	})
}

// TestCapabilityAdvertisedChecking tests capability advertised checking
func TestCapabilityAdvertisedChecking(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = ksquadv1alpha1.AddToScheme(scheme)
	validator := NewRuntimeCapabilityValidator(nil, scheme, nil)

	t.Run("CapabilityAdvertised", func(t *testing.T) {
		agent := &ksquadv1alpha1.BackupAgentHealth{
			Spec: ksquadv1alpha1.BackupAgentHealthSpec{
				AdvertisedCapabilities: []string{"context_transfer", "TASK_RESUMPTION"},
			},
		}

		assert.True(t, validator.isCapabilityAdvertised(agent, "context_transfer"))
		assert.True(t, validator.isCapabilityAdvertised(agent, "task_resumption")) // Case insensitive
		assert.False(t, validator.isCapabilityAdvertised(agent, "streaming_output"))
	})

	t.Run("CapabilityNotAdvertised", func(t *testing.T) {
		agent := &ksquadv1alpha1.BackupAgentHealth{
			Spec: ksquadv1alpha1.BackupAgentHealthSpec{
				AdvertisedCapabilities: []string{"context_transfer"},
			},
		}

		assert.False(t, validator.isCapabilityAdvertised(agent, "task_resumption"))
		assert.False(t, validator.isCapabilityAdvertised(agent, "nonexistent_capability"))
	})
}

// TestCapabilityTestResults tests capability test result validation
func TestCapabilityTestResults(t *testing.T) {
	t.Run("SuccessfulTest", func(t *testing.T) {
		result := CapabilityTestResult{
			Success: true,
			Error:   "",
			Details: map[string]interface{}{
				"context_size": 5000,
				"transfer_rate": 50000.0,
			},
		}

		assert.True(t, result.Success)
		assert.Empty(t, result.Error)
		assert.Equal(t, 5000, result.Details["context_size"])
	})

	t.Run("FailedTest", func(t *testing.T) {
		result := CapabilityTestResult{
			Success: false,
			Error:   "Connection timeout",
			Details: map[string]interface{}{
				"error_code": "TIMEOUT",
			},
		}

		assert.False(t, result.Success)
		assert.Equal(t, "Connection timeout", result.Error)
	})
}

// BenchmarkRuntimeCapabilityValidation benchmarks runtime capability validation performance
func BenchmarkRuntimeCapabilityValidation(b *testing.B) {
	scheme := runtime.NewScheme()
	_ = ksquadv1alpha1.AddToScheme(scheme)
	validator := NewRuntimeCapabilityValidator(nil, scheme, nil)

	agent := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "benchmark-agent",
			Namespace: "benchmark-namespace",
		},
		Spec: ksquadv1alpha1.BackupAgentHealthSpec{
			RuntimeType:           "opencode",
			EndpointURL:           "http://ollama.test.svc.cluster.local:11434/v1",
			AdvertisedCapabilities: []string{"context_transfer", "task_resumption", "streaming_output"},
		},
		Status: ksquadv1alpha1.BackupAgentHealthStatus{
			ActualCapabilities: map[string]interface{}{
				"context_size_limit": 8192,
				"state_persistence": true,
				"checkpoint_support": true,
				"streaming_supported": true,
				"chunk_size_limit": 2048,
				"health_check_interval": 30 * time.Second,
				"failure_threshold": int32(3),
			},
		},
	}

	b.ResetTimer()
	
	for i := 0; i < b.N; i++ {
		_, err := validator.ValidateRuntimeCapabilities(context.Background(), agent)
		assert.NoError(b, err)
	}
}

// BenchmarkCapabilityConsistency benchmarks capability consistency validation
func BenchmarkCapabilityConsistency(b *testing.B) {
	scheme := runtime.NewScheme()
	_ = ksquadv1alpha1.AddToScheme(scheme)
	validator := NewRuntimeCapabilityValidator(nil, scheme, nil)

	backupAgent := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "benchmark-backup",
			Namespace: "benchmark-namespace",
		},
		Spec: ksquadv1alpha1.BackupAgentHealthSpec{
			RuntimeType:           "opencode",
			EndpointURL:           "http://ollama.test.svc.cluster.local:11434/v1",
			AdvertisedCapabilities: []string{"context_transfer", "task_resumption"},
		},
	}

	primaryAgent := &ksquadv1alpha1.BackupAgentHealth{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "benchmark-primary",
			Namespace: "benchmark-namespace",
		},
		Spec: ksquadv1alpha1.BackupAgentHealthSpec{
			RuntimeType:           "opencode",
			EndpointURL:           "http://ollama.test.svc.cluster.local:11434/v1",
			AdvertisedCapabilities: []string{"context_transfer", "task_resumption"},
		},
	}

	b.ResetTimer()
	
	for i := 0; i < b.N; i++ {
		_, err := validator.ValidateCapabilityConsistency(context.Background(), backupAgent, primaryAgent)
		assert.NoError(b, err)
	}
}