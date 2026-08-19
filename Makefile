.PHONY: build event-relay test clean docker-build docker-run

# Build the event relay binary
build:
	go build -o bin/event-relay ./cmd/event-relay

# Build event relay with Docker
docker-build:
	docker build -f Dockerfile.event-relay -t ksquad/event-relay:latest .

# Run the event relay locally
run: build
	./bin/event-relay -config config/relay-config.json

# Run with environment variables
run-env:
	./bin/event-relay \
		-database-url "${DATABASE_URL}" \
		-nats-url "${NATS_URL}"

# Run integration tests
test:
	./test-event-relay.sh

# Build and run in Docker
docker-run:
	docker run -p 8080:8080 \
		-e DATABASE_URL="${DATABASE_URL}" \
		-e NATS_URL="${NATS_URL}" \
		ksquad/event-relay:latest

# Clean build artifacts
clean:
	rm -rf bin/
	docker rmi ksquad/event-relay:latest || true

# Generate Go modules
mod:
	go mod tidy
	go mod download

# Format Go code
fmt:
	go fmt ./...

# Run linter
lint:
	golangci-lint run

# Test unit tests
unit-test:
	go test -v ./internal/outbox/...

# Build all components
all: mod fmt lint build

# Development setup
dev-setup:
	go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
	go install github.com/air-verse/air@latest

# Development hot reload
dev:
	air -c .air.toml