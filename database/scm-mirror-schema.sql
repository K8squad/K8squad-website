-- This script creates the SCM mirror tables for the repo-sync reconciler.
-- These tables store an untrusted-external provenanced mirror of source control data.
-- The schema follows the design in docs/bmad/stories/11-1-repo-sync-reconciler.md.

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create SCM schema
CREATE SCHEMA IF NOT EXISTS scm;

-- scm_repo table: tracks repositories being mirrored
CREATE TABLE IF NOT EXISTS scm.scm_repo (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_name VARCHAR(255) NOT NULL,
    project_namespace VARCHAR(255) NOT NULL,
    url VARCHAR(512) NOT NULL,
    provider VARCHAR(50) NOT NULL, -- github, gitlab, gitea
    mirror_enabled BOOLEAN DEFAULT true,
    last_mirror_update TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_project_repo UNIQUE (project_name, project_namespace, url)
);

-- scm_issue_mirror table: mirrored GitHub issues
CREATE TABLE IF NOT EXISTS scm.scm_issue_mirror (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_name VARCHAR(255) NOT NULL,
    project_namespace VARCHAR(255) NOT NULL,
    external_id INTEGER NOT NULL, -- GitHub issue number
    title VARCHAR(1024) NOT NULL,
    body TEXT,
    state VARCHAR(50) NOT NULL, -- open, closed
    url VARCHAR(2048),
    actor VARCHAR(255), -- username of creator
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    assignees TEXT[], -- JSON array of usernames
    labels TEXT[], -- JSON array of label names
    external_origin JSONB NOT NULL, -- provenance: {provider, repo, external_id, actor}
    trust_level VARCHAR(20) DEFAULT 'untrusted-external' CHECK (trust_level IN ('untrusted-external', 'trusted-control')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_project_issue UNIQUE (project_name, project_namespace, external_id)
);

-- scm_pr_mirror table: mirrored GitHub pull requests
CREATE TABLE IF NOT EXISTS scm.scm_pr_mirror (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_name VARCHAR(255) NOT NULL,
    project_namespace VARCHAR(255) NOT NULL,
    external_id INTEGER NOT NULL, -- GitHub PR number
    title VARCHAR(1024) NOT NULL,
    body TEXT,
    state VARCHAR(50) NOT NULL, -- open, closed, merged
    url VARCHAR(2048),
    actor VARCHAR(255), -- username of creator
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    assignees TEXT[], -- JSON array of usernames
    labels TEXT[], -- JSON array of label names
    head_ref VARCHAR(255), -- source branch
    base_ref VARCHAR(255), -- target branch
    merged BOOLEAN DEFAULT false,
    review_state VARCHAR(50), -- draft, ready_for_review, approved, changes_requested, etc.
    external_origin JSONB NOT NULL, -- provenance: {provider, repo, external_id, actor}
    trust_level VARCHAR(20) DEFAULT 'untrusted-external' CHECK (trust_level IN ('untrusted-external', 'trusted-control')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_project_pr UNIQUE (project_name, project_namespace, external_id)
);

-- scm_check_run table: mirrored GitHub check runs
CREATE TABLE IF NOT EXISTS scm.scm_check_run (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_name VARCHAR(255) NOT NULL,
    project_namespace VARCHAR(255) NOT NULL,
    external_id BIGINT NOT NULL, -- GitHub check run ID
    title VARCHAR(255) NOT NULL,
    state VARCHAR(50) NOT NULL, -- queued, in_progress, success, failure, etc.
    conclusion VARCHAR(50), -- completed check run conclusion
    url VARCHAR(2048),
    actor VARCHAR(255), -- username of creator
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    external_origin JSONB NOT NULL, -- provenance: {provider, repo, external_id, actor}
    trust_level VARCHAR(20) DEFAULT 'untrusted-external' CHECK (trust_level IN ('untrusted-external', 'trusted-control')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_project_check_run UNIQUE (project_name, project_namespace, external_id)
);

-- scm_artifact_ref table: mirrored GitHub workflow artifacts
CREATE TABLE IF NOT EXISTS scm.scm_artifact_ref (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_name VARCHAR(255) NOT NULL,
    project_namespace VARCHAR(255) NOT NULL,
    external_id BIGINT NOT NULL, -- GitHub artifact ID
    name VARCHAR(255) NOT NULL,
    url VARCHAR(2048),
    expires_at TIMESTAMP WITH TIME ZONE,
    size_bytes BIGINT,
    external_origin JSONB NOT NULL, -- provenance: {provider, repo, external_id, actor}
    trust_level VARCHAR(20) DEFAULT 'untrusted-external' CHECK (trust_level IN ('untrusted-external', 'trusted-control')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_project_artifact UNIQUE (project_name, project_namespace, external_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_scm_mirror_project ON scm.scm_issue_mirror(project_name, project_namespace);
CREATE INDEX IF NOT EXISTS idx_scm_pr_project ON scm.scm_pr_mirror(project_name, project_namespace);
CREATE INDEX IF NOT EXISTS idx_scm_check_run_project ON scm.scm_check_run(project_name, project_namespace);
CREATE INDEX IF NOT EXISTS idx_scm_artifact_project ON scm.scm_artifact_ref(project_name, project_namespace);

CREATE INDEX IF NOT EXISTS idx_scm_mirror_external_id ON scm.scm_issue_mirror(external_id);
CREATE INDEX IF NOT EXISTS idx_scm_pr_external_id ON scm.scm_pr_mirror(external_id);
CREATE INDEX IF NOT EXISTS idx_scm_check_run_external_id ON scm.scm_check_run(external_id);
CREATE INDEX IF NOT EXISTS idx_scm_artifact_external_id ON scm.scm_artifact_ref(external_id);

CREATE INDEX IF NOT EXISTS idx_scm_mirror_state ON scm.scm_issue_mirror(state);
CREATE INDEX IF NOT EXISTS idx_scm_pr_state ON scm.scm_pr_mirror(state);
CREATE INDEX IF NOT EXISTS idx_scm_check_run_state ON scm.scm_check_run(state);

-- Index for external_origin queries (for provenance tracking)
CREATE INDEX IF NOT EXISTS idx_scm_mirror_origin ON scm.scm_issue_mirror USING GIN (external_origin);
CREATE INDEX IF NOT EXISTS idx_scm_pr_origin ON scm.scm_pr_mirror USING GIN (external_origin);
CREATE INDEX IF NOT EXISTS idx_scm_check_run_origin ON scm.scm_check_run USING GIN (external_origin);
CREATE INDEX IF NOT EXISTS idx_scm_artifact_origin ON scm.scm_artifact_ref USING GIN (external_origin);

-- Function to handle idempotent upserts
CREATE OR REPLACE FUNCTION upsert_scm_issue_mirror(
    p_project_name VARCHAR(255),
    p_project_namespace VARCHAR(255),
    p_external_id INTEGER,
    p_title VARCHAR(1024),
    p_body TEXT,
    p_state VARCHAR(50),
    p_url VARCHAR(2048),
    p_actor VARCHAR(255),
    p_created_at TIMESTAMP WITH TIME ZONE,
    p_updated_at TIMESTAMP WITH TIME ZONE,
    p_assignees TEXT[],
    p_labels TEXT[],
    p_external_origin JSONB
) RETURNS VOID AS $$
BEGIN
    INSERT INTO scm.scm_issue_mirror (
        project_name, project_namespace, external_id, title, body, state,
        url, actor, created_at, updated_at, assignees, labels, external_origin
    ) VALUES (
        p_project_name, p_project_namespace, p_external_id, p_title, p_body, p_state,
        p_url, p_actor, p_created_at, p_updated_at, p_assignees, p_labels, p_external_origin
    ) ON CONFLICT (project_name, project_namespace, external_id) DO UPDATE SET
        title = EXCLUDED.title,
        body = EXCLUDED.body,
        state = EXCLUDED.state,
        url = EXCLUDED.url,
        actor = EXCLUDED.actor,
        updated_at = EXCLUDED.updated_at,
        assignees = EXCLUDED.assignees,
        labels = EXCLUDED.labels,
        external_origin = EXCLUDED.external_origin;
END;
$$ LANGUAGE plpgsql;

-- Similar function for PRs
CREATE OR REPLACE FUNCTION upsert_scm_pr_mirror(
    p_project_name VARCHAR(255),
    p_project_namespace VARCHAR(255),
    p_external_id INTEGER,
    p_title VARCHAR(1024),
    p_body TEXT,
    p_state VARCHAR(50),
    p_url VARCHAR(2048),
    p_actor VARCHAR(255),
    p_created_at TIMESTAMP WITH TIME ZONE,
    p_updated_at TIMESTAMP WITH TIME ZONE,
    p_assignees TEXT[],
    p_labels TEXT[],
    p_head_ref VARCHAR(255),
    p_base_ref VARCHAR(255),
    p_merged BOOLEAN,
    p_review_state VARCHAR(50),
    p_external_origin JSONB
) RETURNS VOID AS $$
BEGIN
    INSERT INTO scm.scm_pr_mirror (
        project_name, project_namespace, external_id, title, body, state,
        url, actor, created_at, updated_at, assignees, labels, head_ref,
        base_ref, merged, review_state, external_origin
    ) VALUES (
        p_project_name, p_project_namespace, p_external_id, p_title, p_body, p_state,
        p_url, p_actor, p_created_at, p_updated_at, p_assignees, p_labels, p_head_ref,
        p_base_ref, p_merged, p_review_state, p_external_origin
    ) ON CONFLICT (project_name, project_namespace, external_id) DO UPDATE SET
        title = EXCLUDED.title,
        body = EXCLUDED.body,
        state = EXCLUDED.state,
        url = EXCLUDED.url,
        actor = EXCLUDED.actor,
        updated_at = EXCLUDED.updated_at,
        assignees = EXCLUDED.assignees,
        labels = EXCLUDED.labels,
        head_ref = EXCLUDED.head_ref,
        base_ref = EXCLUDED.base_ref,
        merged = EXCLUDED.merged,
        review_state = EXCLUDED.review_state,
        external_origin = EXCLUDED.external_origin;
END;
$$ LANGUAGE plpgsql;

-- View for quick access to active repositories
CREATE OR REPLACE VIEW scm.active_repos AS
SELECT 
    r.project_name,
    r.project_namespace,
    r.url,
    r.provider,
    r.last_mirror_update,
    COUNT(i.external_id) as issue_count,
    COUNT(pr.external_id) as pr_count,
    COUNT(cr.external_id) as check_run_count
FROM scm.scm_repo r
LEFT JOIN scm.scm_issue_mirror i ON r.project_name = i.project_name AND r.project_namespace = i.project_namespace
LEFT JOIN scm.scm_pr_mirror pr ON r.project_name = pr.project_name AND r.project_namespace = pr.project_namespace
LEFT JOIN scm.scm_check_run cr ON r.project_name = cr.project_name AND r.project_namespace = cr.project_namespace
WHERE r.mirror_enabled = true
GROUP BY r.project_name, r.project_namespace, r.url, r.provider, r.last_mirror_update;