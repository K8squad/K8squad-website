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

package controller

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"regexp"
	"time"

	ksquadv1alpha1 "github.com/ksquad/ksquad/api/v1alpha1"
	"github.com/ksquad/ksquad/internal/metrics"
	"github.com/ksquad/ksquad/pkg/scm"
	"go.uber.org/zap"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"
)

// RepoSyncReconciler reconciles a Project resource with repo-sync configuration.
type RepoSyncReconciler struct {
	client.Client
	Scheme            *runtime.Scheme
	Recorder          record.EventRecorder
	logger            *zap.Logger
	providers         map[string]scm.SourceControlProvider
	pollWorkers       map[string]*PollWorker
	webhookHandler    *WebhookHandler
}

// PollWorker manages periodic polling for a specific project.
type PollWorker struct {
	projectName      string
	projectNamespace string
	interval         time.Duration
	stopCh           chan struct{}
	reconciler      *RepoSyncReconciler
	lastPollTime     time.Time
	errorCount      int
}

// WebhookHandler handles webhook events from source control providers.
type WebhookHandler struct {
	reconciler *RepoSyncReconciler
}

//+kubebuilder:rbac:groups=ksquad.io,resources=projects,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=ksquad.io,resources=projects/status,verbs=get;update;patch
//+kubebuilder:rbac:groups=ksquad.io,resources=projects/finalizers,verbs=update
//+kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch
//+kubebuilder:rbac:groups="",resources=pods,verbs=get;list;watch
//+kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch

// Reconcile is the main reconciliation loop for repo-sync.
func (r *RepoSyncReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Fetch the Project instance
	project := &ksquadv1alpha1.Project{}
	if err := r.Get(ctx, req.NamespacedName, project); err != nil {
		if errors.IsNotFound(err) {
			logger.Info("Project resource not found. Ignoring since object must be deleted.")
			return ctrl.Result{}, nil
		}
		logger.Error(err, "Failed to get Project")
		return ctrl.Result{}, err
	}

	// Check if project has sync configuration
	if project.Spec.Sync == nil || !project.Spec.Sync.Mirror.Enabled {
		logger.Info("Project has no sync configuration or mirroring is disabled", "project", project.Name)
		return ctrl.Result{}, nil
	}

	// Initialize provider if not already done
	providerKey := fmt.Sprintf("%s/%s", project.Namespace, project.Name)
	if _, exists := r.providers[providerKey]; !exists {
		provider, err := r.createProvider(ctx, project)
		if err != nil {
			logger.Error(err, "Failed to create provider", "project", project.Name)
			r.updateProjectStatus(ctx, project, "SecretsResolved", false, err.Error())
			return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
		}
		r.providers[providerKey] = provider
		logger.Info("Created source control provider", "provider", provider.Name(), "project", project.Name)
	}

	// Start poll worker if not already running
	if _, exists := r.pollWorkers[providerKey]; !exists {
		worker := &PollWorker{
			projectName:      project.Name,
			projectNamespace: project.Namespace,
			interval:         time.Duration(project.Spec.Sync.PollIntervalSeconds) * time.Second,
			stopCh:           make(chan struct{}),
			reconciler:      r,
		}
		r.pollWorkers[providerKey] = worker
		go worker.Start(ctx)
		logger.Info("Started poll worker", "project", project.Name, "interval", worker.interval)
	}

	// Mark project as ready and sync-ready
	r.updateProjectStatus(ctx, project, "Ready", true, "")
	r.updateProjectStatus(ctx, project, "SyncReady", true, "")
	r.updateProjectStatus(ctx, project, "SecretsResolved", true, "")

	return ctrl.Result{RequeueAfter: 5 * time.Minute}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *RepoSyncReconciler) SetupWithManager(mgr ctrl.Manager) error {
	r.logger = mgr.GetLogger()
	r.providers = make(map[string]scm.SourceControlProvider)
	r.pollWorkers = make(map[string]*PollWorker)
	r.webhookHandler = &WebhookHandler{reconciler: r}

	return ctrl.NewControllerManagedBy(mgr).
		For(&ksquadv1alpha1.Project{}).
		Complete(r)
}

// createProvider creates a SourceControlProvider instance for the project.
func (r *RepoSyncReconciler) createProvider(ctx context.Context, project *ksquadv1alpha1.Project) (scm.SourceControlProvider, error) {
	// Resolve token secret
	tokenSecret, err := r.resolveSecret(ctx, project.Namespace, project.Spec.Sync.TokenSecretRef)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve token secret: %w", err)
	}

	// Create provider credentials
	creds := scm.ProviderCredentials{
		Token:     string(tokenSecret.Data["token"]),
		TokenType: "pat",
	}

	// Create provider based on configuration
	var provider scm.SourceControlProvider
	switch project.Spec.Sync.Provider {
	case "github":
		provider = scm.NewGitHubProvider("", creds)
	default:
		return nil, fmt.Errorf("unsupported provider: %s", project.Spec.Sync.Provider)
	}

	return provider, nil
}

// resolveSecret resolves a SecretReference to a Kubernetes Secret.
func (r *RepoSyncReconciler) resolveSecret(ctx context.Context, namespace string, ref ksquadv1alpha1.SecretReference) (*corev1.Secret, error) {
	secretNamespace := namespace
	if ref.Namespace != "" {
		secretNamespace = ref.Namespace
	}

	secret := &corev1.Secret{}
	secretKey := types.NamespacedName{Name: ref.Name, Namespace: secretNamespace}
	if err := r.Get(ctx, secretKey, secret); err != nil {
		return nil, fmt.Errorf("failed to get secret %s/%s: %w", secretNamespace, ref.Name, err)
	}

	return secret, nil
}

// updateProjectStatus updates the status of a Project resource.
func (r *RepoSyncReconciler) updateProjectStatus(ctx context.Context, project *ksquadv1alpha1.Project, conditionType string, conditionStatus bool, message string) {
	logger := log.FromContext(ctx)

	// Update or add condition
	condition := metav1.Condition{
		Type:    conditionType,
		Status:  metav1.ConditionStatus(corev1.ConditionTrue),
		Reason:  "StatusUpdated",
		Message: message,
	}

	if !conditionStatus {
		condition.Status = metav1.ConditionFalse
		condition.Reason = "Error"
	}

	// Find existing condition and update it
	for i, existing := range project.Status.Conditions {
		if existing.Type == conditionType {
			project.Status.Conditions[i] = condition
			break
		}
	}
	
	// If condition not found, add it
	if !hasCondition(project.Status.Conditions, conditionType) {
		project.Status.Conditions = append(project.Status.Conditions, condition)
	}

	// Update sync status
	if project.Status.SyncStatus == nil {
		project.Status.SyncStatus = &ksquadv1alpha1.SyncStatus{}
	}

	now := metav1.Now()
	switch conditionType {
	case "SyncActive":
		project.Status.SyncStatus.LastMirrorUpdate = &now
	case "SyncReady":
		project.Status.SyncStatus.LastWebhookTime = &now
	}

	// Update the resource
	if err := r.Status().Update(ctx, project); err != nil {
		logger.Error(err, "Failed to update Project status", "project", project.Name)
	}
}

// HandleWebhook handles incoming webhook events from source control providers.
func (h *WebhookHandler) HandleWebhook(ctx context.Context, project *ksquadv1alpha1.Project, signature string, payload []byte) error {
	logger := log.FromContext(ctx)

	// Resolve webhook secret
	webhookSecret, err := h.reconciler.resolveSecret(ctx, project.Namespace, project.Spec.Sync.WebhookSecretRef)
	if err != nil {
		return fmt.Errorf("failed to resolve webhook secret: %w", err)
	}

	// Verify webhook signature before parsing
	webhookSecretValue := string(webhookSecret.Data["webhookSecret"])
	if !h.reconciler.providers[fmt.Sprintf("%s/%s", project.Namespace, project.Name)].ValidateWebhook(ctx, signature, webhookSecretValue, payload) {
		metrics.WebhookValidationCounter.Inc()
		return fmt.Errorf("invalid webhook signature")
	}

	// Parse webhook payload
	var webhookEvent WebhookPayload
	if err := json.Unmarshal(payload, &webhookEvent); err != nil {
		return fmt.Errorf("failed to parse webhook payload: %w", err)
	}

	// Trigger reconcile based on webhook event
	go func() {
		ctx := context.Background()
		logger.Info("Triggering reconcile from webhook", "event", webhookEvent.Event, "project", project.Name)
		
		// Update sync status
		h.reconciler.updateProjectStatus(ctx, project, "SyncActive", true, "Webhook processed successfully")
		
		// In a real implementation, this would call the reconcile logic
		// For now, just log the event
		metrics.WebhookEventCounter.WithLabelValues(webhookEvent.Event, project.Spec.Sync.Provider).Inc()
	}()

	return nil
}

// WebhookPayload represents the common structure of webhook events.
type WebhookPayload struct {
	Event   string                 `json:"event"`
	Repo    WebhookRepository      `json:"repository"`
	Payload map[string]interface{} `json:"payload"`
}

// WebhookRepository represents repository information in webhooks.
type WebhookRepository struct {
	URL string `json:"url"`
}

// PollWorker methods

// Start starts the poll worker.
func (w *PollWorker) Start(ctx context.Context) {
	logger := log.FromContext(ctx)
	ticker := time.NewTicker(w.interval)
	defer ticker.Stop()

	logger.Info("Starting poll worker", "project", w.projectName, "interval", w.interval)

	for {
		select {
		case <-ticker.C:
			if err := w.poll(ctx); err != nil {
				logger.Error(err, "Poll failed", "project", w.projectName)
				w.errorCount++
				if w.errorCount > 5 {
					logger.Error(fmt.Errorf("too many consecutive errors"), "Stopping poll worker", "project", w.projectName)
					return
				}
			} else {
				w.errorCount = 0
			}
		case <-ctx.Done():
			logger.Info("Stopping poll worker", "project", w.projectName)
			return
		case <-w.stopCh:
			logger.Info("Poll worker stopped", "project", w.projectName)
			return
		}
	}
}

// poll performs a periodic sync from the source control provider.
func (w *PollWorker) poll(ctx context.Context) error {
	logger := log.FromContext(ctx)
	
	// Get project from reconciler
	project := &ksquadv1alpha1.Project{}
	if err := w.reconciler.Get(ctx, types.NamespacedName{Name: w.projectName, Namespace: w.projectNamespace}, project); err != nil {
		return fmt.Errorf("failed to get project: %w", err)
	}

	providerKey := fmt.Sprintf("%s/%s", project.Namespace, project.Name)
	provider, exists := w.reconciler.providers[providerKey]
	if !exists {
		return fmt.Errorf("provider not found")
	}

	// Fetch snapshot from provider
	snapshot, err := provider.Snapshot(ctx, project.Spec.Repo.URL, scm.SnapshotOptions{})
	if err != nil {
		return fmt.Errorf("failed to fetch snapshot: %w", err)
	}

	// Process snapshot (this would be the idempotent upsert to the database)
	logger.Info("Processed snapshot", "project", project.Name, "records", len(snapshot))
	
	// Update metrics
	metrics.PollCounter.Inc()
	metrics.RecordCounter.Add(float64(len(snapshot)))

	// Update last poll time
	w.lastPollTime = time.Now()

	// Update project status
	w.reconciler.updateProjectStatus(ctx, project, "SyncActive", true, "Poll completed successfully")

	return nil
}

// Stop stops the poll worker.
func (w *PollWorker) Stop() {
	close(w.stopCh)
}

// hasCondition checks if a condition exists in the conditions list.
func hasCondition(conditions []metav1.Condition, conditionType string) bool {
	for _, c := range conditions {
		if c.Type == conditionType {
			return true
		}
	}
	return false
}

// ParseWebhookSignature parses the signature from the Authorization header.
func ParseWebhookSignature(header string) (string, error) {
	re := regexp.MustCompile(`^sha256=([a-f0-9]+)$`)
	matches := re.FindStringSubmatch(header)
	if len(matches) != 2 {
		return "", fmt.Errorf("invalid signature format")
	}
	return matches[1], nil
}

// ValidateWebhookSignature validates the HMAC signature of a webhook payload.
func ValidateWebhookSignature(payload []byte, secret string, signature string) bool {
	expectedSig := computeHMACSHA256(payload, secret)
	return hmac.Equal([]byte(signature), []byte(expectedSig))
}

// computeHMACSHA256 computes HMAC-SHA256 signature.
func computeHMACSHA256(payload []byte, secret string) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write(payload)
	return hex.EncodeToString(h.Sum(nil))
}