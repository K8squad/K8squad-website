-- ISI-2722 Phase 3: Tenancy Inheritance Strategy Implementation
-- Database Schema Migration for Backup Agent Tenancy Constraints
-- Created: August 17, 2026
-- Purpose: Implement hybrid enforcement for backup agent tenancy inheritance

-- Create backup_agents table with tenancy constraints
CREATE TABLE IF NOT EXISTS backup_agents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,                    -- Foreign key to projects (tenancy root)
    squad_id uuid NOT NULL,                      -- Foreign key to squads (optional narrower scope)
    parent_project_id uuid,                      -- For inheritance chains
    tenancy_level integer NOT NULL DEFAULT 1,    -- Inheritance level (1 = root, higher = nested)
    inherit_from_parent boolean NOT NULL DEFAULT false, -- Whether to inherit parent properties
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    
    -- Critical tenancy inheritance constraint (database-level enforcement)
    -- Child agents cannot have higher tenancy level than their parent project
    CONSTRAINT valid_tenancy_inheritance 
    CHECK (
        parent_project_id IS NULL OR 
        tenancy_level <= (SELECT tenancy_level FROM projects WHERE id = parent_project_id)
    ),
    
    -- Tenancy level validation (must be positive)
    CONSTRAINT valid_tenancy_level 
    CHECK (tenancy_level > 0),
    
    -- Self-referential constraint (cannot be parent of self)
    CONSTRAINT self_parent_not_allowed 
    CHECK (id != parent_project_id),
    
    -- Foreign key constraints for data integrity
    CONSTRAINT fk_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_squad FOREIGN KEY (squad_id) REFERENCES squads(id) ON DELETE SET NULL,
    CONSTRAINT fk_parent_project FOREIGN KEY (parent_project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Indexes for performance optimization
CREATE INDEX idx_backup_agents_project ON backup_agents(project_id);
CREATE INDEX idx_backup_agents_squad ON backup_agents(squad_id);
CREATE INDEX idx_backup_agents_parent_project ON backup_agents(parent_project_id);
CREATE INDEX idx_backup_agents_tenancy ON backup_agents(tenancy_level);
CREATE INDEX idx_backup_agents_inheritance ON backup_agents(inherit_from_parent);

-- View for backup agents with parent project details (for easier querying)
CREATE OR REPLACE VIEW backup_agents_with_parents AS
SELECT 
    ba.id,
    ba.project_id,
    ba.squad_id,
    ba.parent_project_id,
    ba.tenancy_level,
    ba.inherit_from_parent,
    ba.created_at,
    ba.updated_at,
    p.name as project_name,
    p.tenancy_level as project_tenancy_level,
    pp.name as parent_project_name,
    pp.tenancy_level as parent_project_tenancy_level,
    s.name as squad_name
FROM backup_agents ba
LEFT JOIN projects p ON ba.project_id = p.id
LEFT JOIN projects pp ON ba.parent_project_id = pp.id
LEFT JOIN squads s ON ba.squad_id = s.id;

-- Trigger for automatic updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_backup_agents_updated_at 
    BEFORE UPDATE ON backup_agents 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions (adjust based on your deployment)
GRANT SELECT, INSERT, UPDATE, DELETE ON backup_agents TO backup_agent_controller;
GRANT SELECT ON backup_agents_with_parents TO backup_agent_controller;
GRANT USAGE, SELECT ON ALL TABLES IN SCHEMA public TO backup_agent_controller;