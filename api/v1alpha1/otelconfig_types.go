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

// OTelConfigSpec defines the desired state of OTelConfig.
//
// OTelConfig is the dedicated CRD for OTLP export configuration.
// Default behaviour: no exporter (opt-in). Absent an OTelConfig instance,
// telemetry stays in-cluster and nothing egresses (D8 privacy-safe default).
type OTelConfigSpec struct {
	// Exporters configures per-signal OTLP export routing.
	// Each signal (traces, metrics, logs) can fan-out to a different destination.
	// When a signal is omitted, that signal type is not exported.
	// +optional
	Exporters OTelExporters `json:"exporters,omitempty"`
}

// OTelExporters holds per-signal exporter configuration.
type OTelExporters struct {
	// Traces configures the OTLP exporter for trace data.
	// +optional
	Traces *OTelExporter `json:"traces,omitempty"`

	// Metrics configures the OTLP exporter for metric data.
	// +optional
	Metrics *OTelExporter `json:"metrics,omitempty"`

	// Logs configures the OTLP exporter for log data.
	// +optional
	Logs *OTelExporter `json:"logs,omitempty"`
}

// OTelExporter defines a single OTLP export destination for one signal type.
type OTelExporter struct {
	// Endpoint is the OTLP receiver URL (e.g. "https://api.dynatrace.com/api/v2/otlp").
	// Must be a fully-qualified URL with scheme.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Endpoint string `json:"endpoint"`

	// Protocol selects the OTLP transport protocol.
	// +kubebuilder:validation:Enum=grpc;http
	// +kubebuilder:default=grpc
	Protocol OTelProtocol `json:"protocol,omitempty"`

	// AuthSecretRef references a Kubernetes Secret containing exporter credentials.
	// The Secret must contain a key "token" with the authentication header value.
	// Credentials are never logged, never inlined, never exposed in status or events.
	// This follows the BYO-Secret discipline (§11).
	// +kubebuilder:validation:Required
	AuthSecretRef SecretReference `json:"authSecretRef"`

	// ResourceAttributes are additional OTel resource attributes appended to every
	// telemetry signal exported through this exporter.
	// +optional
	ResourceAttributes map[string]string `json:"resourceAttributes,omitempty"`

	// Sampling configures the trace sampling ratio for this exporter.
	// Only applies to the traces signal.
	// +optional
	Sampling *SamplingConfig `json:"sampling,omitempty"`
}

// OTelProtocol enumerates the supported OTLP transport protocols.
// +kubebuilder:validation:Enum=grpc;http
type OTelProtocol string

const (
	// OTelProtocolGRPC uses OTLP/gRPC (default).
	OTelProtocolGRPC OTelProtocol = "grpc"

	// OTelProtocolHTTP uses OTLP/HTTP.
	OTelProtocolHTTP OTelProtocol = "http"
)

// SecretReference is a reference to a Secret in the same namespace.
type SecretReference struct {
	// Name is the name of the Secret.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Name string `json:"name"`

	// Namespace of the Secret. Defaults to the OTelConfig namespace if omitted.
	// +optional
	Namespace string `json:"namespace,omitempty"`

	// Key is the data key within the Secret that holds the auth token.
	// Defaults to "token" if omitted.
	// +kubebuilder:default=token
	// +optional
	Key string `json:"key,omitempty"`
}

// SamplingConfig configures trace sampling.
type SamplingConfig struct {
	// Type selects the sampling strategy.
	// +kubebuilder:validation:Enum=always_on;always_off;traceidratio;parentbased_traceidratio
	// +kubebuilder:default=parentbased_traceidratio
	Type string `json:"type,omitempty"`

	// Ratio is the sampling ratio for ratio-based samplers (0.0–1.0).
	// Serialized as string to avoid cross-language float issues.
	// +kubebuilder:validation:Pattern="^[01]([.][0-9]+)?$"
	// +kubebuilder:default="1"
	// +optional
	Ratio string `json:"ratio,omitempty"`
}

// OTelConfigStatus defines the observed state of OTelConfig.
type OTelConfigStatus struct {
	// ObservedGeneration is the most recent generation observed for this OTelConfig.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// Conditions represent the latest available observations of the OTelConfig state.
	// +optional
	// +patchMergeKey=type
	// +patchStrategy=merge
	// +listType=map
	// +listMapKey=type
	Conditions []metav1.Condition `json:"conditions,omitempty" patchStrategy:"merge" patchMergeKey:"type"`

	// ExportedSignals lists which signals are currently being exported.
	// +optional
	ExportedSignals []string `json:"exportedSignals,omitempty"`
}

// OTelConfigConditionType defines the condition types for OTelConfig.
const (
	// OTelConfigReady indicates the OTelConfig has been successfully reconciled
	// and all configured exporters are active.
	OTelConfigReady = "Ready"

	// OTelConfigSecretResolved indicates that all referenced auth Secrets have been
	// found and are valid.
	OTelConfigSecretResolved = "SecretResolved"

	// OTelConfigExportersApplied indicates that the exporter configuration has been
	// applied to all KSquad components.
	OTelConfigExportersApplied = "ExportersApplied"
)

//+kubebuilder:object:root=true
//+kubebuilder:subresource:status
//+kubebuilder:resource:shortName=otelc
//+kubebuilder:scope=Namespaced

// OTelConfig is the Schema for the otelconfigs API.
//
// It configures opt-in OTLP export for KSquad telemetry (traces, metrics, logs).
// When no OTelConfig exists in the ksquad-system namespace, no telemetry egresses the cluster.
type OTelConfig struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   OTelConfigSpec   `json:"spec,omitempty"`
	Status OTelConfigStatus `json:"status,omitempty"`
}

//+kubebuilder:object:root=true

// OTelConfigList contains a list of OTelConfig.
type OTelConfigList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []OTelConfig `json:"items"`
}

func init() {
	SchemeBuilder.Register(&OTelConfig{}, &OTelConfigList{})
}
