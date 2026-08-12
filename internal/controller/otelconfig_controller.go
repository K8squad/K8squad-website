/*
Copyright 2026 KSquad.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
*/

package controller

import (
	"context"
	"fmt"
	"strings"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	ksquadv1alpha1 "github.com/ksquad-ai/ksquad/api/v1alpha1"
)

// OTelConfigReconciler reconciles an OTelConfig object.
//
// The reconciler reads the OTelConfig CRD and configures every KSquad component's
// OTLP exporter SDK (operator, apiserver, memory, console, shims).
// It is platform-scoped (ksquad-system namespace).
//
// Key behaviours:
//   - Default = no exporter (opt-in). Absent an OTelConfig, telemetry stays in-cluster.
//   - Auth credentials are Secret refs, never inline, never logged.
//   - Supports fan-out: traces→Dynatrace, metrics→Prometheus, logs→Loki.
type OTelConfigReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=ksquad.io,resources=otelconfigs,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=ksquad.io,resources=otelconfigs/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=ksquad.io,resources=otelconfigs/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=configmaps,verbs=get;list;watch;create;update;patch;delete

// Reconcile handles OTelConfig CRD changes and applies exporter config to KSquad components.
func (r *OTelConfigReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	logger.Info("Reconciling OTelConfig", "namespacedName", req.NamespacedName)

	// Fetch the OTelConfig instance
	var otelConfig ksquadv1alpha1.OTelConfig
	if err := r.Get(ctx, req.NamespacedName, &otelConfig); err != nil {
		if errors.IsNotFound(err) {
			// OTelConfig deleted — components revert to no-exporter default.
			logger.Info("OTelConfig deleted; components revert to no-exporter default")
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// Validate and resolve all referenced auth Secrets
	secretResolved := r.validateSecrets(ctx, &otelConfig)

	// Build the exporter config map that components consume
	exporterConfig := r.buildExporterConfig(&otelConfig)

	// Apply config to the ksquad-export-config ConfigMap
	// Components (operator, apiserver, memory, console, shims) mount this ConfigMap
	// and read their OTLP exporter settings from it at runtime.
	if err := r.applyExporterConfigMap(ctx, &otelConfig, exporterConfig); err != nil {
		logger.Error(err, "failed to apply exporter ConfigMap")
		_ = r.updateStatus(ctx, &otelConfig, false, false, "ConfigMapApplyFailed", err.Error())
		return ctrl.Result{Requeue: true}, nil
	}

	// Update status
	exportedSignals := r.computeExportedSignals(&otelConfig)
	if err := r.updateStatus(ctx, &otelConfig, true, secretResolved, "Reconciled", exporterConfig); err != nil {
		return ctrl.Result{}, err
	}

	logger.Info("OTelConfig reconciled successfully",
		"exportedSignals", exportedSignals,
		"secretResolved", secretResolved)

	return ctrl.Result{}, nil
}

// validateSecrets checks that all referenced auth Secrets exist and are accessible.
// Credentials are never logged.
func (r *OTelConfigReconciler) validateSecrets(ctx context.Context, oc *ksquadv1alpha1.OTelConfig) bool {
	logger := log.FromContext(ctx)
	exporters := []struct {
		name     string
		exporter *ksquadv1alpha1.OTelExporter
	}{
		{"traces", oc.Spec.Exporters.Traces},
		{"metrics", oc.Spec.Exporters.Metrics},
		{"logs", oc.Spec.Exporters.Logs},
	}

	allResolved := true
	for _, e := range exporters {
		if e.exporter == nil {
			continue
		}

		ns := e.exporter.AuthSecretRef.Namespace
		if ns == "" {
			ns = oc.Namespace
		}
		key := e.exporter.AuthSecretRef.Key
		if key == "" {
			key = "token"
		}

		var secret corev1.Secret
		err := r.Get(ctx, types.NamespacedName{
			Name:      e.exporter.AuthSecretRef.Name,
			Namespace: ns,
		}, &secret)
		if err != nil {
			// Never log the secret name or content — just the signal and resolution status
			logger.Info("auth Secret not resolved for signal",
				"signal", e.name, "namespace", ns)
			allResolved = false
			continue
		}

		// Verify the expected key exists
		if _, ok := secret.Data[key]; !ok {
			logger.Info("auth Secret missing expected key for signal",
				"signal", e.name, "key", key)
			allResolved = false
		}
	}

	return allResolved
}

// buildExporterConfig creates the config data that KSquad components consume.
// This is written to a ConfigMap that all components mount.
// Auth tokens are NEVER included — components read Secrets directly at runtime
// via the projected Secret mount.
func (r *OTelConfigReconciler) buildExporterConfig(oc *ksquadv1alpha1.OTelConfig) string {
	var sb strings.Builder

	sb.WriteString("# KSquad OTel exporter configuration\n")
	sb.WriteString("# Generated by OTelConfig reconciler — do not edit manually\n")
	sb.WriteString("# Auth credentials are projected from Secrets at runtime\n\n")

	signals := []struct {
		name     string
		exporter *ksquadv1alpha1.OTelExporter
	}{
		{"traces", oc.Spec.Exporters.Traces},
		{"metrics", oc.Spec.Exporters.Metrics},
		{"logs", oc.Spec.Exporters.Logs},
	}

	for _, s := range signals {
		if s.exporter == nil {
			sb.WriteString(fmt.Sprintf("[%s]\nenabled = false\n\n", s.name))
			continue
		}

		ns := s.exporter.AuthSecretRef.Namespace
		if ns == "" {
			ns = oc.Namespace
		}
		key := s.exporter.AuthSecretRef.Key
		if key == "" {
			key = "token"
		}

		protocol := string(s.exporter.Protocol)
		if protocol == "" {
			protocol = "grpc"
		}

		sb.WriteString(fmt.Sprintf("[%s]\n", s.name))
		sb.WriteString("enabled = true\n")
		sb.WriteString(fmt.Sprintf("endpoint = %q\n", s.exporter.Endpoint))
		sb.WriteString(fmt.Sprintf("protocol = %q\n", protocol))
		sb.WriteString(fmt.Sprintf("auth_secret_name = %q\n", s.exporter.AuthSecretRef.Name))
		sb.WriteString(fmt.Sprintf("auth_secret_namespace = %q\n", ns))
		sb.WriteString(fmt.Sprintf("auth_secret_key = %q\n", key))

		// Resource attributes
		if len(s.exporter.ResourceAttributes) > 0 {
			sb.WriteString("resource_attributes:\n")
			for k, v := range s.exporter.ResourceAttributes {
				sb.WriteString(fmt.Sprintf("  %s = %q\n", k, v))
			}
		}

		// Sampling (traces only)
		if s.name == "traces" && s.exporter.Sampling != nil {
			samplingType := s.exporter.Sampling.Type
			if samplingType == "" {
				samplingType = "parentbased_traceidratio"
			}
			sb.WriteString(fmt.Sprintf("sampling_type = %q\n", samplingType))
			if s.exporter.Sampling.Ratio != "" {
				sb.WriteString(fmt.Sprintf("sampling_ratio = %s\n", s.exporter.Sampling.Ratio))
			}
		}

		sb.WriteString("\n")
	}

	return sb.String()
}

// applyExporterConfigMap creates or updates the ConfigMap that KSquad components
// mount to read their OTLP exporter configuration.
func (r *OTelConfigReconciler) applyExporterConfigMap(ctx context.Context, oc *ksquadv1alpha1.OTelConfig, data string) error {
	cmName := types.NamespacedName{
		Name:      "ksquad-otel-export-config",
		Namespace: oc.Namespace,
	}

	var cm corev1.ConfigMap
	exists := true
	if err := r.Get(ctx, cmName, &cm); err != nil {
		if !errors.IsNotFound(err) {
			return err
		}
		exists = false
	}

	if !exists {
		cm = corev1.ConfigMap{
			ObjectMeta: metav1.ObjectMeta{
				Name:      cmName.Name,
				Namespace: cmName.Namespace,
				Labels: map[string]string{
					"app.kubernetes.io/name":       "ksquad",
					"app.kubernetes.io/component":  "otel-config",
					"app.kubernetes.io/managed-by": "ksquad-operator",
				},
			},
			Data: map[string]string{
				"exporter.toml": data,
			},
		}
		if err := ctrl.SetControllerReference(oc, &cm, r.Scheme); err != nil {
			return err
		}
		return r.Create(ctx, &cm)
	}

	// Update existing
	cm.Data = map[string]string{
		"exporter.toml": data,
	}
	return r.Update(ctx, &cm)
}

// computeExportedSignals returns the list of active exporter signal names.
func (r *OTelConfigReconciler) computeExportedSignals(oc *ksquadv1alpha1.OTelConfig) []string {
	var signals []string
	if oc.Spec.Exporters.Traces != nil {
		signals = append(signals, "traces")
	}
	if oc.Spec.Exporters.Metrics != nil {
		signals = append(signals, "metrics")
	}
	if oc.Spec.Exporters.Logs != nil {
		signals = append(signals, "logs")
	}
	return signals
}

// updateStatus sets conditions and observed generation on the OTelConfig.
func (r *OTelConfigReconciler) updateStatus(ctx context.Context, oc *ksquadv1alpha1.OTelConfig, applied, secretResolved bool, reason, message string) error {
	now := metav1.Now()

	// SecretResolved condition
	secretStatus := metav1.ConditionFalse
	if secretResolved {
		secretStatus = metav1.ConditionTrue
	}
	meta.SetStatusCondition(&oc.Status.Conditions, metav1.Condition{
		Type:               ksquadv1alpha1.OTelConfigSecretResolved,
		Status:             secretStatus,
		ObservedGeneration: oc.Generation,
		LastTransitionTime: now,
		Reason:             reason,
		Message:            message,
	})

	// ExportersApplied condition
	appliedStatus := metav1.ConditionFalse
	if applied {
		appliedStatus = metav1.ConditionTrue
	}
	meta.SetStatusCondition(&oc.Status.Conditions, metav1.Condition{
		Type:               ksquadv1alpha1.OTelConfigExportersApplied,
		Status:             appliedStatus,
		ObservedGeneration: oc.Generation,
		LastTransitionTime: now,
		Reason:             reason,
		Message:            message,
	})

	// Ready condition = applied && secretResolved
	readyStatus := metav1.ConditionFalse
	if applied && secretResolved {
		readyStatus = metav1.ConditionTrue
	}
	meta.SetStatusCondition(&oc.Status.Conditions, metav1.Condition{
		Type:               ksquadv1alpha1.OTelConfigReady,
		Status:             readyStatus,
		ObservedGeneration: oc.Generation,
		LastTransitionTime: now,
		Reason:             reason,
		Message:            message,
	})

	oc.Status.ObservedGeneration = oc.Generation
	oc.Status.ExportedSignals = r.computeExportedSignals(oc)

	return r.Status().Update(ctx, oc)
}

// SetupWithManager sets up the controller with the Manager.
func (r *OTelConfigReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&ksquadv1alpha1.OTelConfig{}).
		Owns(&corev1.ConfigMap{}).
		Complete(r)
}
