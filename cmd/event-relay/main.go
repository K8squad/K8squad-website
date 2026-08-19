package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	"go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/semconv/v1.24.0"
	"go.uber.org/zap"

	"github.com/ksquad-ai/ksquad/internal/outbox"
)

var (
	configPath = flag.String("config", "/etc/ksquad/relay-config.json", "Path to relay configuration file")
	databaseURL = flag.String("database-url", "", "Database connection URL")
	natsURL     = flag.String("nats-url", "nats://localhost:4222", "NATS server URL")
)

func main() {
	// Parse command line flags
	flag.Parse()

	// Initialize logger
	logger, err := zap.NewProduction()
	if err != nil {
		log.Fatalf("Failed to create logger: %v", err)
	}
	defer logger.Sync()

	// Load configuration
	config, err := loadConfig(*configPath)
	if err != nil {
		logger.Fatal("Failed to load configuration", zap.Error(err))
	}

	// Override config with command line flags if provided
	if *databaseURL != "" {
		config.DatabaseURL = *databaseURL
	}
	if *natsURL != "" {
		config.NATSURL = *natsURL
	}

	// Initialize OpenTelemetry
	if config.OTLPExporterURL != "" {
		tracerProvider := initTelemetry(config.OTLPExporterURL)
		defer tracerProvider.Shutdown(context.Background())
	}

	// Connect to database
	db, err := connectToDatabase(config.DatabaseURL)
	if err != nil {
		logger.Fatal("Failed to connect to database", zap.Error(err))
	}
	defer db.Close()

	// Create event relay
	relay, err := outbox.NewEventRelay(db, config.RelayConfig)
	if err != nil {
		logger.Fatal("Failed to create event relay", zap.Error(err))
	}

	// Start event relay
	if err := relay.Start(); err != nil {
		logger.Fatal("Failed to start event relay", zap.Error(err))
	}
	logger.Info("Event relay started successfully")

	// Setup HTTP server
	mux := http.NewServeMux()
	
	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		health, err := relay.HealthCheck(r.Context())
		if err != nil {
			http.Error(w, fmt.Sprintf("Health check failed: %v", err), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(health)
	})

	// Stats endpoint
	mux.HandleFunc("/stats", func(w http.ResponseWriter, r *http.Request) {
		stats, err := relay.GetStats(r.Context())
		if err != nil {
			http.Error(w, fmt.Sprintf("Failed to get stats: %v", err), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(stats)
	})

	// Metrics endpoint (Prometheus format)
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, r *http.Request) {
		// This would typically use Prometheus client library
		// For now, return basic metrics
		stats, err := relay.GetStats(r.Context())
		if err != nil {
			http.Error(w, fmt.Sprintf("Failed to get stats: %v", err), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/plain")
		fmt.Fprintf(w, "events_published_total %d\n", stats.PublishedEvents)
		fmt.Fprintf(w, "events_publish_errors_total %d\n", stats.FailedEvents)
		fmt.Fprintf(w, "outbox_depth %d\n", stats.PendingEvents)
	})

	// Configure server
	server := &http.Server{
		Addr:         ":" + fmt.Sprintf("%d", config.HTTPPort),
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	// Start HTTP server in a goroutine
	go func() {
		logger.Info("Starting HTTP server", zap.String("address", server.Addr))
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal("HTTP server failed", zap.Error(err))
		}
	}()

	// Wait for shutdown signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down server...")

	// Stop event relay
	relay.Stop()

	// Shutdown HTTP server with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		logger.Error("Server shutdown failed", zap.Error(err))
	}

	logger.Info("Server stopped gracefully")
}

// RelayConfig represents the complete configuration for the event relay
type RelayConfig struct {
	DatabaseURL         string `json:"databaseUrl"`
	NATSURL             string `json:"natsUrl"`
	JetStreamEnabled    bool   `json:"jetStreamEnabled"`
	SubjectPrefix       string `json:"subjectPrefix"`
	BatchSize           int    `json:"batchSize"`
	MaxRetries          int    `json:"maxRetries"`
	PollInterval        int    `json:"pollInterval"` // in seconds
	GracefulShutdown    int    `json:"gracefulShutdown"` // in seconds
	EnableMetrics       bool   `json:"enableMetrics"`
	OTLPExporterURL     string `json:"otlpExporterUrl"`
	HTTPPort            int    `json:"httpPort"`
}

// loadConfig loads configuration from file or defaults
func loadConfig(path string) (*RelayConfig, error) {
	// Default configuration
	config := &RelayConfig{
		DatabaseURL:         "postgres://postgres:password@localhost:5432/ksquad?sslmode=disable",
		NATSURL:             "nats://localhost:4222",
		JetStreamEnabled:    true,
		SubjectPrefix:       "ksquad",
		BatchSize:           100,
		MaxRetries:          5,
		PollInterval:        5,
		GracefulShutdown:    30,
		EnableMetrics:       true,
		HTTPPort:            8080,
	}

	// Try to load from file if it exists
	if _, err := os.Stat(path); err == nil {
		file, err := os.Open(path)
		if err != nil {
			return nil, fmt.Errorf("failed to open config file: %w", err)
		}
		defer file.Close()

		decoder := json.NewDecoder(file)
		if err := decoder.Decode(config); err != nil {
			return nil, fmt.Errorf("failed to decode config file: %w", err)
		}
	}

	return config, nil
}

// connectToDatabase establishes a connection to the PostgreSQL database
func connectToDatabase(url string) (*pgxpool.Pool, error) {
	config, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, fmt.Errorf("failed to parse database URL: %w", err)
	}

	// Configure connection pool - optimized to prevent exhaustion
	config.MaxConns = 10
	config.MinConns = 3
	config.MaxConnLifetime = 30 * time.Minute
	config.MaxConnIdleTime = 15 * time.Minute
	config.HealthCheckPeriod = 1 * time.Minute

	pool, err := pgxpool.New(context.Background(), config)
	if err != nil {
		return nil, fmt.Errorf("failed to create connection pool: %w", err)
	}

	// Test connection
	if err := pool.Ping(context.Background()); err != nil {
		pool.Close()
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	return pool, nil
}

// initTelemetry initializes OpenTelemetry tracing
func initTelemetry(exporterURL string) *trace.TracerProvider {
	exporter, err := otlptracehttp.New(context.Background(),
		otlptracehttp.WithEndpoint(exporterURL),
		otlptracehttp.WithInsecure(),
	)
	if err != nil {
		log.Fatalf("Failed to create OTLP trace exporter: %v", err)
	}

	tracerProvider := trace.NewTracerProvider(
		trace.WithBatcher(exporter),
		trace.WithResource(resource.NewAttributes(
			semconv.SchemaURL,
			semconv.ServiceNameKey.String("ksquad-event-relay"),
		)),
	)

	otel.SetTracerProvider(tracerProvider)
	return tracerProvider
}