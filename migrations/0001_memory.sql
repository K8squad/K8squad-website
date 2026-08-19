-- 0001_memory.sql - Initial memory service database schema
-- Modified to work around vector extension dependency

-- Enable required extensions (skip vector for now, add later)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create memory service tables (temporarily without vector column)
CREATE TABLE memory_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT NOT NULL,
    embedding JSONB,  -- Temporarily use JSONB instead of vector
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_memory_embeddings_created_at ON memory_embeddings (created_at);
CREATE INDEX idx_memory_embeddings_updated_at ON memory_embeddings (updated_at);
CREATE INDEX idx_memory_embedding_gin ON memory_embeddings USING GIN (embedding);

-- Create memory service configuration table
CREATE TABLE memory_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key TEXT NOT NULL UNIQUE,
    value JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for config table
CREATE INDEX idx_memory_config_key ON memory_config (key);
CREATE INDEX idx_memory_config_created_at ON memory_config (created_at);