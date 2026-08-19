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
	"time"

	ksquadv1alpha1 "github.com/ksquad/ksquad/api/v1alpha1"
	corev1 "k8s.io/api/core/v1"
	"github.com/go-logr/logr"
	"go.uber.org/zap"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// TenancyEnforcer implements hybrid enforcement for backup agent tenancy inheritance
// Combines database-level constraints with application-level business rule validation
type TenancyEnforcer struct {
	client client.Client
	logger *zap.Logger
}

// NewTenancyEnforcer creates a new tenancy enforcer
func NewTenancyEnforcer(client client.Client, logger *zap.Logger) *TenancyEnforcer {
	return &TenancyEnforcer{
		client: client,
		logger: logger,
	}
}

// HybridEnforcement performs hybrid validation of tenancy inheritance rules
// Returns error if validation fails, nil if validation passes
func (e *TenancyEnforcer) HybridEnforcement(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) error {
	e.logger.Info("Starting hybrid tenancy enforcement",
		"agent", backupAgent.Name,
		"project", backupAgent.Spec.ProjectID,
		"parent", backupAgent.Spec.ParentProjectID)

	// Database-level enforcement (critical rules that must be met)
	if err := e.databaseEnforcement(ctx, backupAgent); err != nil {
		e.logger.Error("Database-level tenancy enforcement failed",
			"agent", backupAgent.Name,
			"error", err)
		return fmt.Errorf("database tenancy constraint violation: %w", err)
	}

	// Application-level enforcement (business rules)
	if err := e.applicationEnforcement(ctx, backupAgent); err != nil {
		e.logger.Error("Application-level tenancy enforcement failed",
			"agent", backupAgent.Name,
			"error", err)
		return fmt.Errorf("tenancy business rule violation: %w", err)
	}

	e.logger.Info("Hybrid tenancy enforcement passed",
		"agent", backupAgent.Name)
	return nil
}

// databaseEnforcement enforces constraints that must be met at database level
// These are critical rules that prevent data integrity issues
func (e *TenancyEnforcer) databaseEnforcement(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) error {
	// Rule 1: Tenancy level validation
	if backupAgent.Spec.TenancyLevel < 1 {
		return fmt.Errorf("tenancy level must be positive, got %d", backupAgent.Spec.TenancyLevel)
	}

	// Rule 2: Parent project tenancy level validation
	if backupAgent.Spec.ParentProjectID != nil && backupAgent.Spec.TenancyLevel > 1 {
		parentProject, err := e.getProjectByID(ctx, backupAgent.Spec.ParentProjectID)
		if err != nil {
			return fmt.Errorf("failed to get parent project for validation: %w", err)
		}

		if backupAgent.Spec.TenancyLevel > parentProject.Status.TenancyLevel {
			return fmt.Errorf("agent tenancy level (%d) cannot exceed parent project tenancy level (%d)",
				backupAgent.Spec.TenancyLevel, parentProject.Status.TenancyLevel)
		}
	}

	// Rule 3: Self-referential check
	if backupAgent.Spec.ParentProjectID != nil {
		if backupAgent.Spec.ParentProjectID.UID == backupAgent.UID {
			return fmt.Errorf("backup agent cannot be its own parent")
		}
	}

	return nil
}

// applicationEnforcement enforces complex business rules that can't be implemented at database level
func (e *TenancyEnforcer) applicationEnforcement(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) error {
	// Rule 1: Inheritance depth limits
	if err := e.validateInheritanceDepth(ctx, backupAgent); err != nil {
		return err
	}

	// Rule 2: Capability compatibility with project requirements
	if err := e.validateCapabilityCompatibility(ctx, backupAgent); err != nil {
		return err
	}

	// Rule 3: Circular dependency prevention
	if err := e.preventCircularDependencies(ctx, backupAgent); err != nil {
		return err
	}

	// Rule 4: Project permission validation
	if err := e.validateProjectPermissions(ctx, backupAgent); err != nil {
		return err
	}

	// Rule 5: Inheritance property validation
	if backupAgent.Spec.InheritFromParent {
		if err := e.validateInheritanceProperties(ctx, backupAgent); err != nil {
			return err
		}
	}

	return nil
}

// validateInheritanceDepth ensures inheritance chains don't become too deep
func (e *TenancyEnforcer) validateInheritanceDepth(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) error {
	const maxInheritanceDepth = 5
	
	if backupAgent.Spec.TenancyLevel > maxInheritanceDepth {
		return fmt.Errorf("inheritance depth (%d) exceeds maximum allowed (%d)",
			backupAgent.Spec.TenancyLevel, maxInheritanceDepth)
	}

	// Check if parent project has valid inheritance chain
	if backupAgent.Spec.ParentProjectID != nil {
		parentProject, err := e.getProjectByID(ctx, backupAgent.Spec.ParentProjectID)
		if err != nil {
			return fmt.Errorf("failed to validate parent project inheritance: %w", err)
		}

		if parentProject.Status.TenancyLevel >= maxInheritanceDepth {
			return fmt.Errorf("parent project inheritance depth (%d) would exceed maximum allowed (%d)",
				parentProject.Status.TenancyLevel, maxInheritanceDepth)
		}
	}

	return nil
}

// validateCapabilityCompatibility ensures backup agent capabilities match project requirements
func (e *TenancyEnforcer) validateCapabilityCompatibility(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) error {
	if backupAgent.Spec.ProjectID == nil {
		return nil // No project specified, no compatibility checks needed
	}

	project, err := e.getProjectByID(ctx, backupAgent.Spec.ProjectID)
	if err != nil {
		return fmt.Errorf("failed to get project for capability validation: %w", err)
	}

	// Check if all required capabilities are provided by the backup agent
	for _, requiredCap := range project.Spec.RequiredCapabilities {
		hasCapability := false
		for _, advertisedCap := range backupAgent.Spec.AdvertisedCapabilities {
			if requiredCap == advertisedCap {
				hasCapability = true
				break
			}
		}

		if !hasCapability {
			e.logger.Warn("Backup agent missing required capability",
				"agent", backupAgent.Name,
				"project", project.Name,
				"required", requiredCap,
				"advertised", backupAgent.Spec.AdvertisedCapabilities)
			return fmt.Errorf("backup agent missing required capability: %s", requiredCap)
		}
	}

	return nil
}

// preventCircularDependencies checks for circular inheritance chains
func (e *TenancyEnforcer) preventCircularDependencies(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) error {
	visited := make(map[types.UID]bool)
	currentAgent := backupAgent.UID

	for i := 0; i < 10; i++ { // Prevent infinite loops
		if visited[currentAgent] {
			return fmt.Errorf("circular dependency detected in inheritance chain")
		}
		visited[currentAgent] = true

		if backupAgent.Spec.ParentProjectID == nil {
			break
		}

		parentProject, err := e.getProjectByID(ctx, backupAgent.Spec.ParentProjectID)
		if err != nil {
			return fmt.Errorf("failed to check circular dependencies: %w", err)
		}

		// Check if parent project is also a backup agent (circular reference)
		parentBackupAgent := &ksquadv1alpha1.BackupAgentHealth{}
		err = e.client.Get(ctx, types.NamespacedName{Name: parentProject.Name, Namespace: backupAgent.Namespace}, parentBackupAgent)
		if err != nil {
			if errors.IsNotFound(err) {
				break // Parent is not a backup agent, no circular dependency
			}
			return fmt.Errorf("failed to check parent backup agent: %w", err)
		}

		currentAgent = parentBackupAgent.UID
		backupAgent = parentBackupAgent
	}

	return nil
}

// validateProjectPermissions checks if the project has sufficient permissions for backup agents
func (e *TenancyEnforcer) validateProjectPermissions(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) error {
	if backupAgent.Spec.ProjectID == nil {
		return nil // No project specified, no permission checks needed
	}

	project, err := e.getProjectByID(ctx, backupAgent.Spec.ProjectID)
	if err != nil {
		return fmt.Errorf("failed to get project for permission validation: %w", err)
	}

	// Check if project allows backup agents
	if !project.Spec.AllowBackupAgents {
		return fmt.Errorf("project %s does not allow backup agents", project.Name)
	}

	// Check project quota for backup agents
	projectBackupAgentCount := &ksquadv1alpha1.BackupAgentHealthList{}
	err = e.client.List(ctx, projectBackupAgentCount, client.InNamespace(backupAgent.Namespace),
		client.MatchingFields{projectID: project.Name})
	if err != nil {
		return fmt.Errorf("failed to count project backup agents: %w", err)
	}

	if len(projectBackupAgentCount.Items) >= int(project.Spec.MaxBackupAgents) {
		return fmt.Errorf("project %s has reached maximum backup agent limit (%d)",
			project.Name, project.Spec.MaxBackupAgents)
	}

	return nil
}

// validateInheritanceProperties validates properties when inheriting from parent
func (e *TenancyEnforcer) validateInheritanceProperties(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) error {
	if backupAgent.Spec.ParentProjectID == nil {
		return nil // No parent to inherit from
	}

	parentProject, err := e.getProjectByID(ctx, backupAgent.Spec.ParentProjectID)
	if err != nil {
		return fmt.Errorf("failed to get parent project for inheritance validation: %w", err)
	}

	// Validate that parent has capabilities to inherit
	if len(parentProject.Spec.AdvertisedCapabilities) == 0 {
		return fmt.Errorf("parent project %s has no capabilities to inherit", parentProject.Name)
	}

	// Validate context budget compatibility if inheriting
	if backupAgent.Spec.ContextBudget != nil && backupAgent.Spec.InheritFromParent {
		parentBudget := parentProject.Spec.ContextBudget
		if parentBudget != nil {
			// Ensure inherited budget doesn't exceed parent budget
			if backupAgent.Spec.ContextBudget.TotalTokens > parentBudget.TotalTokens {
				return fmt.Errorf("inherited context budget cannot exceed parent context budget")
			}
		}
	}

	return nil
}

// getProjectByID retrieves a project by its object reference
func (e *TenancyEnforcer) getProjectByID(ctx context.Context, projectRef *corev1.ObjectReference) (*ksquadv1alpha1.Project, error) {
	project := &ksquadv1alpha1.Project{}
	err := e.client.Get(ctx, types.NamespacedName{Name: projectRef.Name, Namespace: projectRef.Namespace}, project)
	if err != nil {
		return nil, err
	}
	return project, nil
}

// UpdateBackupAgentStatus updates the backup agent status with tenancy validation results
func (e *TenancyEnforcer) UpdateBackupAgentStatus(ctx context.Context, backupAgent *ksquadv1alpha1.BackupAgentHealth) error {
	// Perform validation
	err := e.HybridEnforcement(ctx, backupAgent)
	if err != nil {
		// Update status to reflect validation failure
		backupAgent.Status.TenancyValid = false
		backupAgent.Status.TenancyValidationMessage = err.Error()
		
		// Set condition
		condition := metav1.Condition{
			Type:               string(TenancyValidCondition),
			Status:             metav1.ConditionFalse,
			Reason:             ReasonInvalid,
			Message:            err.Error(),
			LastTransitionTime: metav1.Now(),
		}
		ksquadv1alpha1.SetStatusCondition(&backupAgent.Status.Conditions, condition)
	} else {
		// Update status to reflect validation success
		backupAgent.Status.TenancyValid = true
		backupAgent.Status.TenancyValidationMessage = ""
		
		// Set condition
		condition := metav1.Condition{
			Type:               string(TenancyValidCondition),
			Status:             metav1.ConditionTrue,
			Reason:             ReasonValid,
			Message:            "Tenancy validation passed",
			LastTransitionTime: metav1.Now(),
		}
		ksquadv1alpha1.SetStatusCondition(&backupAgent.Status.Conditions, condition)
	}

	// Inherited status (for UI/display purposes)
	if backupAgent.Spec.InheritFromParent && backupAgent.Spec.ParentProjectID != nil {
		backupAgent.Status.InheritedFromParent = true
	} else {
		backupAgent.Status.InheritedFromParent = false
	}

	return nil
}