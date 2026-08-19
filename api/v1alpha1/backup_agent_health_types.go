/*
Copyright 2026 KSquad.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

*/

package v1alpha1

import (
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/scheme"
)

// BackupAgentHealthSpec defines the desired state of BackupAgentHealth
type BackupAgentHealthSpec struct {
	// RuntimeType is the type of runtime (e.g., "opencode", "ollama", etc.)
	RuntimeType string `json:"runtimeType"`
	
	// EndpointURL is the URL of the endpoint the backup agent should connect to
	EndpointURL string `json:"endpointURL,omitempty"`
	
	// AdvertisedCapabilities are the capabilities the backup agent claims to have
	AdvertisedCapabilities []string `json:"advertisedCapabilities,omitempty"`
	
	// HealthCheckInterval defines how often to perform health checks
	HealthCheckInterval metav1.Duration `json:"healthCheckInterval,omitempty"`
	
	// FailureThreshold is the number of consecutive failures before marking as unhealthy
	FailureThreshold int32 `json:"failureThreshold,omitempty"`
	
	// PrimaryAgentRef is a reference to the primary agent this backup agent is for
	PrimaryAgentRef *corev1.ObjectReference `json:"primaryAgentRef,omitempty"`
	
	// ContextBudget defines the context budget configuration for the backup agent (Story 5.9 integration)
	ContextBudget *ContextBudget `json:"contextBudget,omitempty"`
	
	// MustIncludeMinTokens defines the minimum tokens required for must-include content (Story 5.9 AC1)
	MustIncludeMinTokens int32 `json:"mustIncludeMinTokens,omitempty"`
	
	// Tenancy fields for inheritance (ISI-2722 Phase 3)
	// ProjectID is the project this backup agent belongs to (tenancy root)
	ProjectID *corev1.ObjectReference `json:"projectID,omitempty"`
	
	// SquadID is the squad within the project (optional narrower scope)
	SquadID *corev1.ObjectReference `json:"squadID,omitempty"`
	
	// ParentProjectID is the parent project for inheritance chains
	ParentProjectID *corev1.ObjectReference `json:"parentProjectID,omitempty"`
	
	// TenancyLevel defines the inheritance level (1 = root, higher = nested)
	TenancyLevel int32 `json:"tenancyLevel,omitempty"`
	
	// InheritFromParent determines whether to inherit properties from parent project
	InheritFromParent bool `json:"inheritFromParent,omitempty"`
}

// BackupAgentHealthStatus defines the observed state of BackupAgentHealth
type BackupAgentHealthStatus struct {
	// Ready indicates whether the backup agent is ready for failover
	Ready bool `json:"ready"`
	
	// PodReady indicates whether the backup agent pod is ready
	PodReady bool `json:"podReady"`
	
	// RuntimeCapabilityVerified indicates whether runtime capabilities are verified
	RuntimeCapabilityVerified bool `json:"runtimeCapabilityVerified"`
	
	// EndpointAvailable indicates whether the endpoint is available
	EndpointAvailable bool `json:"endpointAvailable"`
	
	// ContextBudgetValid indicates whether the context budget configuration is valid (Story 5.9)
	ContextBudgetValid bool `json:"contextBudgetValid"`
	
	// ContextFittingValid indicates whether context fitting is valid (Story 5.9 AC1)
	ContextFittingValid bool `json:"contextFittingValid"`
	
	// ArchitectConfirmationValid indicates whether Architect confirmation requirements are met
	ArchitectConfirmationValid bool `json:"architectConfirmationValid"`
	
	// ResolvedModelContextWindow is the resolved model's context window (Story 5.9 AC2)
	ResolvedModelContextWindow int32 `json:"resolvedModelContextWindow,omitempty"`
	
	// LastHealthCheck is the timestamp of the last health check
	LastHealthCheck metav1.Time `json:"lastHealthCheck,omitempty"`
	
	// ActualCapabilities are the capabilities the backup agent actually has
	ActualCapabilities []string `json:"actualCapabilities,omitempty"`
	
	// HealthCheckHistory stores the history of health check results
	HealthCheckHistory []HealthCheckResult `json:"healthCheckHistory,omitempty"`
	
	// Conditions stores the latest available observations of the backup agent state
	// +patchMergeKey=type
	// +patchStrategy=merge
	Conditions []metav1.Condition `json:"conditions,omitempty"`
	
	// Tenancy validation status (ISI-2722 Phase 3)
	// TenancyValid indicates whether tenancy inheritance validation passed
	TenancyValid bool `json:"tenancyValid"`
	
	// TenancyValidationMessage contains details about tenancy validation failures
	TenancyValidationMessage string `json:"tenancyValidationMessage,omitempty"`
	
	// InheritedFromParent indicates whether this agent inherits properties from parent
	InheritedFromParent bool `json:"inheritedFromParent"`
	
	// ParentProjectTenancyLevel is the tenancy level of the parent project
	ParentProjectTenancyLevel int32 `json:"parentProjectTenancyLevel,omitempty"`
}

// HealthCheckResult represents a single health check result
type HealthCheckResult struct {
	Timestamp   metav1.Time `json:"timestamp"`
	CheckType   string      `json:"checkType"`
	Passed      bool        `json:"passed"`
	Message     string      `json:"message,omitempty"`
	Error       string      `json:"error,omitempty"`
	DurationMs  int64       `json:"durationMs,omitempty"`
}

// ContextBudget defines the context budget configuration for agents (Story 5.9 integration)
type ContextBudget struct {
	// TotalTokens is the total context budget in tokens
	TotalTokens int32 `json:"totalTokens"`
	
	// AuthoritativeTokens is the budget for authoritative content (must-include)
	AuthoritativeTokens int32 `json:"authoritativeTokens,omitempty"`
	
	// UntrustedRecallTokens is the budget for untrusted recall content
	UntrustedRecallTokens int32 `json:"untrustedRecallTokens,omitempty"`
	
	// UntrustedExternalTokens is the budget for untrusted external content
	UntrustedExternalTokens int32 `json:"untrustedExternalTokens,omitempty"`
}

//+kubebuilder:object:root=true
//+kubebuilder:subresource:status

// BackupAgentHealth is the Schema for the backupagenthealths API
type BackupAgentHealth struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   BackupAgentHealthSpec   `json:"spec,omitempty"`
	Status BackupAgentHealthStatus `json:"status,omitempty"`
}

//+kubebuilder:object:root=true

// BackupAgentHealthList contains a list of BackupAgentHealth
type BackupAgentHealthList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []BackupAgentHealth `json:"items"`
}

// Conditions for BackupAgentHealth
const (
	// ReadyCondition indicates the backup agent is ready for failover
	ReadyCondition = "Ready"
	
	// PodReadyCondition indicates the backup agent pod is ready
	PodReadyCondition = "PodReady"
	
	// RuntimeReadyCondition indicates the runtime is ready
	RuntimeReadyCondition = "RuntimeReady"
	
	// EndpointReadyCondition indicates the endpoint is ready
	EndpointReadyCondition = "EndpointReady"
	
	// ArchitectConfirmationCondition indicates the Architect confirmation is obtained
	ArchitectConfirmationCondition = "ArchitectConfirmation"
	
	// TenancyValidCondition indicates the tenancy inheritance validation passed
	TenancyValidCondition = "TenancyValid"
)

// Condition reasons
const (
	// ReasonHealthy indicates the backup agent is healthy
	ReasonHealthy = "Healthy"
	
	// ReasonUnhealthy indicates the backup agent is unhealthy
	ReasonUnhealthy = "Unhealthy"
	
	// ReasonPending indicates the backup agent is pending
	ReasonPending = "Pending"
	
	// ReasonFailed indicates the backup agent failed health check
	ReasonFailed = "Failed"
	
	// ReasonDegraded indicates the backup agent is degraded
	ReasonDegraded = "Degraded"
	
	// ReasonValid indicates tenancy validation passed
	ReasonValid = "Valid"
	
	// ReasonInvalid indicates tenancy validation failed
	ReasonInvalid = "Invalid"
	
	// ReasonInherited indicates properties inherited from parent
	ReasonInherited = "Inherited"
)

// Setup adds types to the scheme.
func (BackupAgentHealth) SetupWithScheme(scheme *scheme.Builder) {
	scheme.Register(&BackupAgentHealth{}, &BackupAgentHealthList{})
}

func init() {
	SchemeBuilder.Register(&BackupAgentHealth{}, &BackupAgentHealthList{})
}