/*
Copyright 2026 KSquad.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// RepoSyncConfig defines the source-control sync configuration for a Project.
type RepoSyncConfig struct {
	// Provider specifies the source control provider (github, gitlab, gitea).
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:Enum=github;gitlab;gitea
	Provider string `json:"provider"`

	// TokenSecretRef references a Kubernetes Secret containing the provider token.
	// The Secret must contain a key "token" with the authentication token.
	// Credentials are scoped mirror-read only, never shared or logged.
	// +kubebuilder:validation:Required
	TokenSecretRef SecretReference `json:"tokenSecretRef"`

	// WebhookSecretRef references a Kubernetes Secret containing the HMAC secret
	// for webhook signature verification. The Secret must contain a key "webhookSecret"
	// with the HMAC key value.
	// +kubebuilder:validation:Required
	WebhookSecretRef SecretReference `json:"webhookSecretRef"`

	// PollIntervalSeconds specifies the interval for periodic polls when webhooks
	// are absent or lossy. This ensures convergence even when webhook delivery fails.
	// +kubebuilder:validation:Minimum=60
	// +kubebuilder:default=300
	PollIntervalSeconds int32 `json:"pollIntervalSeconds"`

	// Mirror configuration for source control mirroring.
	Mirror MirrorConfig `json:"mirror"`

	// ReflectOutbound controls whether the system writes status/comments back
	// to the source control provider. When enabled, outbound writes are made
	// through the same provider seam with echo suppression.
	// +kubebuilder:default=false
	ReflectOutbound bool `json:"reflectOutbound,omitempty"`
}

// MirrorConfig defines the mirroring behavior for source control sync.
type MirrorConfig struct {
	// Enabled controls whether source control mirroring is active.
	// When false, no mirror synchronization occurs.
	// +kubebuilder:default=true
	Enabled bool `json:"enabled,omitempty"`

	// Repositories specifies which repositories to mirror.
	// If empty, mirrors the main repository configured in Project.spec.repo.
	// +optional
	Repositories []RepositorySpec `json:"repositories,omitempty"`
}

// RepositorySpec defines a repository to mirror.
type RepositorySpec struct {
	// URL is the full repository URL (e.g., "https://github.com/owner/repo").
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	URL string `json:"url"`

	// Branch specifies the branch to monitor. If empty, monitors all branches.
	// +optional
	Branch string `json:"branch,omitempty"`
}

// ProjectSpec defines the desired state of a Project.
type ProjectSpec struct {
	// Repo defines the main repository for this Project.
	// When sync is configured, this repository is mirrored.
	Repo RepositorySpec `json:"repo"`

	// Team specifies the team responsible for this Project.
	// +kubebuilder:validation:Required
	Team string `json:"team"`

	// Goals define the objectives for this Project.
	// +optional
	Goals []string `json:"goals,omitempty"`

	// ContextBudget defines the context budget for this Project.
	// +optional
	ContextBudget *ContextBudget `json:"contextBudget,omitempty"`

	// EgressPolicyRef references a network policy that controls egress from this Project.
	// +optional
	EgressPolicyRef *LocalObjectReference `json:"egressPolicyRef,omitempty"`

	// Sync defines the source control synchronization configuration.
	// When configured, enables repo-sync reconciler for this Project.
	// +optional
	Sync *RepoSyncConfig `json:"sync,omitempty"`
}

// ProjectStatus defines the observed state of a Project.
type ProjectStatus struct {
	// ObservedGeneration is the most recent generation observed for this Project.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// Conditions represent the latest available observations of the Project state.
	// +optional
	// +patchMergeKey=type
	// +patchStrategy=merge
	// +listType=map
	// +listMapKey=type
	Conditions []metav1.Condition `json:"conditions,omitempty" patchStrategy:"merge" patchMergeKey:"type"`

	// SyncStatus holds information about the source control sync status.
	// +optional
	SyncStatus *SyncStatus `json:"syncStatus,omitempty"`

	// RepositoryURL is the URL of the main repository.
	// +optional
	RepositoryURL string `json:"repositoryURL,omitempty"`

	// LastSyncTime is the timestamp of the last successful sync.
	// +optional
	LastSyncTime *metav1.Time `json:"lastSyncTime,omitempty"`

	// SyncError contains the last sync error if any.
	// +optional
	SyncError string `json:"syncError,omitempty"`
}

// SyncStatus defines the status of source control synchronization.
type SyncStatus struct {
	// LastWebhookTime is the timestamp of the last webhook event.
	// +optional
	LastWebhookTime *metav1.Time `json:"lastWebhookTime,omitempty"`

	// LastPollTime is the timestamp of the last poll event.
	// +optional
	LastPollTime *metav1.Time `json:"lastPollTime,omitempty"`

	// LastMirrorUpdate is the timestamp when the mirror was last updated.
	// +optional
	LastMirrorUpdate *metav1.Time `json:"lastMirrorUpdate,omitempty"`

	// ProviderStatus contains provider-specific status information.
	// +optional
	ProviderStatus map[string]interface{} `json:"providerStatus,omitempty"`

	// ErrorCount tracks the number of consecutive sync errors.
	// +optional
	ErrorCount int32 `json:"errorCount,omitempty"`

	// LastError contains the last sync error if any.
	// +optional
	LastError string `json:"lastError,omitempty"`
}

// ProjectConditionType defines the condition types for Project.
const (
	// ProjectReady indicates the Project has been successfully reconciled
	// and all required resources are available.
	ProjectReady = "Ready"

	// ProjectSyncReady indicates the repo-sync reconciler is active
	// and successfully configured for this Project.
	ProjectSyncReady = "SyncReady"

	// ProjectSecretsResolved indicates that all referenced Secrets
	// (tokenSecretRef, webhookSecretRef) have been found and are valid.
	ProjectSecretsResolved = "SecretsResolved"

	// ProjectSyncActive indicates that the repo-sync is actively
	// mirroring from the source control provider.
	ProjectSyncActive = "SyncActive"
}

//+kubebuilder:object:root=true
//+kubebuilder:subresource:status
//+kubebuilder:resource:shortName=proj
//+kubebuilder:scope=Namespaced

// Project is the Schema for the projects API.
//
// A Project represents a team's workspace with repository sync capabilities.
// When sync is configured, it enables the repo-sync reconciler to mirror
// source control state (issues, PRs, checks, artifacts) through a provider seam.
type Project struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   ProjectSpec   `json:"spec,omitempty"`
	Status ProjectStatus `json:"status,omitempty"`
}

//+kubebuilder:object:root=true

// ProjectList contains a list of Project.
type ProjectList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []Project `json:"items"`
}

// ContextBudget defines the context budget for a Project.
type ContextBudget struct {
	// TotalTokens is the total number of tokens available for context.
	// This respects the model's physical window (AC4 from Story 5.9).
	// +kubebuilder:validation:Minimum=1
	TotalTokens int64 `json:"totalTokens"`

	// MustIncludeMinTokens specifies the minimum tokens that must always
	// be included in context. This content is never truncated (AC1 from Story 5.9).
	// +kubebuilder:validation:Minimum=0
	// +kubebuilder:default=0
	MustIncludeMinTokens int64 `json:"mustIncludeMinTokens,omitempty"`
}

// LocalObjectReference contains enough information to let you locate the
// referenced object inside the same namespace.
type LocalObjectReference struct {
	// Name of the referent.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Name string `json:"name"`
}

func init() {
	SchemeBuilder.Register(&Project{}, &ProjectList{})
}