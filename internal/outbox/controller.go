package outbox

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/serializer"
	ctrl "sigs.k8s.io/controller-runtime"
)

// RelayController manages the event relay lifecycle
type RelayController struct {
	config     RelayConfig
	relay      *EventRelay
	db         *pgxpool.Pool
	eventMgr   *EventManager
	scheme     *runtime.Scheme
}

// NewRelayController creates a new relay controller
func NewRelayController(config RelayConfig, db *pgxpool.Pool) *RelayController {
	return &RelayController{
		config:   config,
		db:       db,
		eventMgr: NewEventManager(db),
		scheme:   runtime.NewScheme(),
	}
}

// Start initializes and starts the event relay
func (rc *RelayController) Start() error {
	log.Println("Starting event relay controller...")

	// Initialize the relay
	relay, err := NewEventRelay(rc.db, rc.config)
	if err != nil {
		return fmt.Errorf("failed to create event relay: %w", err)
	}

	rc.relay = relay

	// Start the relay
	if err := relay.Start(); err != nil {
		return fmt.Errorf("failed to start relay: %w", err)
	}

	log.Println("Event relay controller started successfully")

	// Set up signal handling for graceful shutdown
	rc.setupSignalHandling()

	return nil
}

// Stop gracefully stops the event relay
func (rc *RelayController) Stop() {
	if rc.relay != nil {
		log.Println("Stopping event relay controller...")
		rc.relay.Stop()
		log.Println("Event relay controller stopped")
	}
}

// setupSignalHandling sets up signal handling for graceful shutdown
func (rc *RelayController) setupSignalHandling() {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigChan
		log.Printf("Received signal: %v", sig)
		rc.Stop()
		os.Exit(0)
	}()
}

// GetHealth returns the current health status of the relay
func (rc *RelayController) GetHealth() (*HealthStatus, error) {
	return rc.relay.HealthCheck(context.Background())
}

// GetStats returns current relay statistics
func (rc *RelayController) GetStats() (*RelayStats, error) {
	return rc.relay.GetStats(context.Background())
}

// ConfigMapProvider provides configuration for the relay
type ConfigMapProvider struct {
	data map[string]string
}

// NewConfigMapProvider creates a new config map provider
func NewConfigMapProvider() *ConfigMapProvider {
	return &ConfigMapProvider{
		data: make(map[string]string),
	}
}

// LoadFromConfigMap loads configuration from Kubernetes ConfigMap data
func (p *ConfigMapProvider) LoadFromConfigMap(data map[string]string) error {
	p.data = data
	return nil
}

// GetConfig extracts and returns the relay configuration
func (p *ConfigMapProvider) GetConfig() (*RelayConfig, error) {
	config := RelayConfig{
		BatchSize:        100,
		MaxRetries:       5,
		PollInterval:     5 * time.Second,
		GracefulShutdown: 30 * time.Second,
		EnableMetrics:    true,
	}

	// Parse NATS URL
	if natsUrl, ok := p.data["relay.natsUrl"]; ok {
		config.NATSURL = natsUrl
	} else {
		return nil, fmt.Errorf("missing required configuration: relay.natsUrl")
	}

	// Parse JetStream enabled
	if jetstreamStr, ok := p.data["relay.jetstream"]; ok {
		var err error
		config.JetStreamEnabled, err = parseBool(jetstreamStr)
		if err != nil {
			return nil, fmt.Errorf("invalid relay.jetstream value: %w", err)
		}
	}

	// Parse subject prefix
	if subjectPrefix, ok := p.data["relay.subjectPrefix"]; ok {
		config.SubjectPrefix = subjectPrefix
	} else {
		config.SubjectPrefix = "ksquad"
	}

	// Parse batch size
	if batchSizeStr, ok := p.data["relay.batchSize"]; ok {
		var err error
		config.BatchSize, err = parseInt(batchSizeStr)
		if err != nil {
			return nil, fmt.Errorf("invalid relay.batchSize value: %w", err)
		}
	}

	// Parse max retries
	if maxRetriesStr, ok := p.data["relay.maxRetries"]; ok {
		var err error
		config.MaxRetries, err = parseInt(maxRetriesStr)
		if err != nil {
			return nil, fmt.Errorf("invalid relay.maxRetries value: %w", err)
		}
	}

	// Parse poll interval
	if pollIntervalStr, ok := p.data["relay.pollInterval"]; ok {
		var err error
		config.PollInterval, err = parseDuration(pollIntervalStr)
		if err != nil {
			return nil, fmt.Errorf("invalid relay.pollInterval value: %w", err)
		}
	}

	// Parse graceful shutdown timeout
	if gracefulShutdownStr, ok := p.data["relay.gracefulShutdown"]; ok {
		var err error
		config.GracefulShutdown, err = parseDuration(gracefulShutdownStr)
		if err != nil {
			return nil, fmt.Errorf("invalid relay.gracefulShutdown value: %w", err)
		}
	}

	// Parse enable metrics
	if enableMetricsStr, ok := p.data["relay.enableMetrics"]; ok {
		var err error
		config.EnableMetrics, err = parseBool(enableMetricsStr)
		if err != nil {
			return nil, fmt.Errorf("invalid relay.enableMetrics value: %w", err)
		}
	}

	// Parse OTLP exporter URL (optional)
	if otlpURL, ok := p.data["relay.otlpExporterUrl"]; ok {
		config.OTLPExporterURL = otlpURL
	}

	return &config, nil
}

// Helper functions for parsing configuration values
func parseBool(s string) (bool, error) {
	switch s {
	case "true", "1", "yes", "on":
		return true, nil
	case "false", "0", "no", "off":
		return false, nil
	default:
		return false, fmt.Errorf("invalid boolean value: %s", s)
	}
}

func parseInt(s string) (int, error) {
	var i int
	_, err := fmt.Sscanf(s, "%d", &i)
	return i, err
}

func parseDuration(s string) (time.Duration, error) {
	return time.ParseDuration(s)
}

// SetupOpenTelemetry sets up OpenTelemetry metrics and tracing
func SetupOpenTelemetry(config *RelayConfig) error {
	if !config.EnableMetrics {
		log.Println("Metrics disabled")
		return nil
	}

	if config.OTLPExporterURL != "" {
		log.Printf("Setting up OTLP exporter: %s", config.OTLPExporterURL)
		// In a real implementation, this would set up the OTLP exporter
		// For now, we'll use the global no-op provider
	}

	log.Println("OpenTelemetry setup completed")
	return nil
}

// Main entry point for the relay worker
func Main() {
	metricsAddr := ":8080" // Default metrics address

	// Create controller manager
	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme:             runtime.NewScheme(),
		MetricsBindAddress: metricsAddr,
		Port:               9443,
	})
	if err != nil {
		log.Fatalf("Failed to create manager: %v", err)
	}

	// Create database connection pool
	dbConfig, err := createDatabaseConfig()
	if err != nil {
		log.Fatalf("Failed to create database config: %v", err)
	}

	db, err := pgxpool.NewWithConfig(context.Background(), dbConfig)
	if err != nil {
		log.Fatalf("Failed to create database pool: %v", err)
	}
	defer db.Close()

	// Ensure database connection
	if err := db.Ping(context.Background()); err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}

	// Load configuration
	configMapProvider := NewConfigMapProvider()
	
	// In a real implementation, load from Kubernetes ConfigMap
	// For now, use defaults or environment variables
	config, err := loadConfigurationFromEnv()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup OpenTelemetry
	if err := SetupOpenTelemetry(config); err != nil {
		log.Fatalf("Failed to setup OpenTelemetry: %v", err)
	}

	// Create and start relay controller
	relayController := NewRelayController(*config, db)
	
	if err := relayController.Start(); err != nil {
		log.Fatalf("Failed to start relay controller: %v", err)
	}

	// Wait for shutdown signal
	stopCh := ctrl.SetupSignalHandler()
	<-stopCh

	// Graceful shutdown
	relayController.Stop()
}

// loadConfigurationFromEnv loads configuration from environment variables
func loadConfigurationFromEnv() (*RelayConfig, error) {
	config := RelayConfig{
		BatchSize:        100,
		MaxRetries:       5,
		PollInterval:     5 * time.Second,
		GracefulShutdown: 30 * time.Second,
		EnableMetrics:    true,
	}

	// NATS URL
	if natsURL := os.Getenv("NATS_URL"); natsURL != "" {
		config.NATSURL = natsURL
	}

	// JetStream enabled
	if jetstreamStr := os.Getenv("JETSTREAM_ENABLED"); jetstreamStr != "" {
		var err error
		config.JetStreamEnabled, err = parseBool(jetstreamStr)
		if err != nil {
			return nil, fmt.Errorf("invalid JETSTREAM_ENABLED: %w", err)
		}
	}

	// Subject prefix
	if subjectPrefix := os.Getenv("SUBJECT_PREFIX"); subjectPrefix != "" {
		config.SubjectPrefix = subjectPrefix
	}

	return &config, nil
}

// createDatabaseConfig creates database configuration from environment variables
func createDatabaseConfig() (*pgxpool.Config, error) {
	// In a real implementation, this would load from environment variables
	// or Kubernetes configuration
	config, err := pgxpool.ParseConfig("")
	if err != nil {
		return nil, err
	}

	// Example configuration - in production, load from environment/config
	config.MaxConns = 20
	config.MinConns = 5
	config.HealthCheckPeriod = 30 * time.Second

	return config, nil
}