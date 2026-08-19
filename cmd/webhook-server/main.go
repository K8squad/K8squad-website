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

package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"

	ksquadv1alpha1 "github.com/ksquad/ksquad/api/v1alpha1"
	"go.uber.org/zap"
	"k8s.io/client-go/kubernetes/scheme"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/config"
)

var (
	listenAddr = flag.String("listen-address", ":8080", "Address to listen on")
)

func main() {
	flag.Parse()

	// Set up logger
	logger, err := zap.NewProduction()
	if err != nil {
		log.Fatalf("Failed to create logger: %v", err)
	}

	// Set up Kubernetes client
	k8sConfig, err := config.GetConfig()
	if err != nil {
		logger.Fatal("Failed to get Kubernetes config", zap.Error(err))
	}

	// Add Project scheme
	if err := ksquadv1alpha1.AddToScheme(scheme.Scheme); err != nil {
		logger.Fatal("Failed to add Project scheme", zap.Error(err))
	}

	// Create Kubernetes client
	k8sClient, err := client.New(k8sConfig, client.Options{Scheme: scheme.Scheme})
	if err != nil {
		logger.Fatal("Failed to create Kubernetes client", zap.Error(err))
	}

	// Create webhook handler
	webhookHandler := NewWebhookHandler(k8sClient, logger)

	// Set up HTTP routes
	http.HandleFunc("/webhook", webhookHandler.HandleWebhook)
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, "Webhook server is healthy")
	})

	// Start server
	logger.Info("Starting webhook server", "address", *listenAddr)
	if err := http.ListenAndServe(*listenAddr, nil); err != nil {
		logger.Fatal("Failed to start server", zap.Error(err))
	}
}

// WebhookHandler handles incoming webhook requests.
type WebhookHandler struct {
	k8sClient client.Client
	logger    *zap.Logger
}

// NewWebhookHandler creates a new webhook handler.
func NewWebhookHandler(k8sClient client.Client, logger *zap.Logger) *WebhookHandler {
	return &WebhookHandler{
		k8sClient: k8sClient,
		logger:    logger,
	}
}

// HandleWebhook handles incoming webhook requests.
func (h *WebhookHandler) HandleWebhook(w http.ResponseWriter, r *http.Request) {
	logger := h.logger.With(
		"method", r.Method,
		"url", r.URL.Path,
		"remote_addr", r.RemoteAddr,
	)

	// Only POST requests are allowed
	if r.Method != http.MethodPost {
		logger.Warn("Invalid method", "method", r.Method)
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Parse project from the request
	projectName, err := h.parseProjectFromRequest(r)
	if err != nil {
		logger.Error("Failed to parse project from request", zap.Error(err))
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}

	// Get project configuration
	project := &ksquadv1alpha1.Project{}
	if err := h.k8sClient.Get(r.Context(), types.NamespacedName{Name: projectName, Namespace: "default"}, project); err != nil {
		logger.Error("Failed to get project", "project", projectName, zap.Error(err))
		http.Error(w, "Project not found", http.StatusNotFound)
		return
	}

	// Verify webhook signature
	signature := r.Header.Get("X-Hub-Signature-256")
	if signature == "" {
		logger.Warn("Missing X-Hub-Signature-256 header")
		http.Error(w, "Missing signature", http.StatusUnauthorized)
		return
	}

	payload, err := h.readRequestBody(r)
	if err != nil {
		logger.Error("Failed to read request body", zap.Error(err))
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}

	if err := h.validateWebhookSignature(payload, project, signature); err != nil {
		logger.Error("Invalid webhook signature", zap.Error(err))
		http.Error(w, "Invalid signature", http.StatusUnauthorized)
		return
	}

	// Process webhook
	if err := h.processWebhook(r.Context(), project, signature, payload); err != nil {
		logger.Error("Failed to process webhook", zap.Error(err))
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	// Return success response
	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, "Webhook processed successfully")

	logger.Info("Webhook processed successfully", "project", projectName)
}

// parseProjectFromRequest parses the project name from the request.
func (h *WebhookHandler) parseProjectFromRequest(r *http.Request) (string, error) {
	// Extract project from various possible sources:
	// 1. Header: X-KSquad-Project
	projectName := r.Header.Get("X-KSquad-Project")
	if projectName != "" {
		return projectName, nil
	}

	// 2. Query parameter: ?project=project-name
	if projectName := r.URL.Query().Get("project"); projectName != "" {
		return projectName, nil
	}

	// 3. From the repository URL in the webhook payload
	var payload map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		return "", err
	}

	// Reset body for later use
	// r.Body.Close() - already closed above
	r.Body = http.MaxBytesReader(r, r.Body, 1048576) // 1MB limit

	if repo, ok := payload["repository"].(map[string]interface{}); ok {
		if fullURL, ok := repo["full_name"].(string); ok {
			// Extract project name from full_name like "owner/repo"
			parts := strings.Split(fullURL, "/")
			if len(parts) >= 2 {
				return parts[1], nil // Use repo name as project name
			}
		}
	}

	return "", fmt.Errorf("could not determine project from request")
}

// readRequestBody reads the request body.
func (h *WebhookHandler) readRequestBody(r *http.Request) ([]byte, error) {
	defer r.Body.Close()
	
	// Limit request size to 10MB
	r.Body = http.MaxBytesReader(r, r.Body, 10*1024*1024)
	
	return io.ReadAll(r.Body)
}

// validateWebhookSignature validates the HMAC signature of the webhook payload.
func (h *WebhookHandler) validateWebhookSignature(payload []byte, project *ksquadv1alpha1.Project, signature string) error {
	// Resolve webhook secret
	webhookSecret, err := h.resolveSecret(context.Background(), project.Namespace, project.Spec.Sync.WebhookSecretRef)
	if err != nil {
		return fmt.Errorf("failed to resolve webhook secret: %w", err)
	}

	// Parse signature header
	signatureValue := strings.TrimPrefix(signature, "sha256=")
	
	// Compute expected signature
	expectedSig := computeHMACSHA256(payload, string(webhookSecret.Data["webhookSecret"]))
	
	// Compare signatures
	if !hmac.Equal([]byte(signatureValue), []byte(expectedSig)) {
		return fmt.Errorf("signature mismatch: expected %s, got %s", expectedSig, signatureValue)
	}

	return nil
}

// processWebhook processes the webhook payload.
func (h *WebhookHandler) processWebhook(ctx context.Context, project *ksquadv1alpha1.Project, signature string, payload []byte) error {
	// Parse webhook event
	var event map[string]interface{}
	if err := json.Unmarshal(payload, &event); err != nil {
		return fmt.Errorf("failed to parse webhook payload: %w", err)
	}

	// Extract event type
	eventType, ok := event["zen"].(string)
	if !ok {
		eventType = "unknown"
	}

	h.logger.Info("Processing webhook event",
		"project", project.Name,
		"event", eventType,
		"repository", project.Spec.Repo.URL,
	)

	// In a real implementation, this would:
	// 1. Parse the specific event type
	// 2. Extract relevant information (PR number, issue number, etc.)
	// 3. Trigger the repo-sync reconciler
	// 4. Update the mirror database with the new state
	// 5. Handle echo suppression for outbound writes

	// For now, just log the event
	return nil
}

// resolveSecret resolves a SecretReference to a Kubernetes Secret.
func (h *WebhookHandler) resolveSecret(ctx context.Context, namespace string, ref ksquadv1alpha1.SecretReference) (*corev1.Secret, error) {
	secretNamespace := namespace
	if ref.Namespace != "" {
		secretNamespace = ref.Namespace
	}

	secret := &corev1.Secret{}
	secretKey := types.NamespacedName{Name: ref.Name, Namespace: secretNamespace}
	if err := h.k8sClient.Get(ctx, secretKey, secret); err != nil {
		return nil, fmt.Errorf("failed to get secret %s/%s: %w", secretNamespace, ref.Name, err)
	}

	return secret, nil
}

// computeHMACSHA256 computes HMAC-SHA256 signature.
func computeHMACSHA256(payload []byte, secret string) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write(payload)
	return hex.EncodeToString(h.Sum(nil))
}