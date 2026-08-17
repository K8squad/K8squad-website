-- 0003_discussion_schema.sql — per-Project Discussion Room schema
-- (Arch §7.5 Theme J / FR-J1…J4, Story 10.1 / ISI-2702, ADR-001, ADR-019)
--
-- CANONICAL REFERENCE DDL. This is the authoritative shape the Epic-10 apiserver build
-- materializes under k8squad `db/migrations/` (target name `0003_discussion_schema.sql`,
-- applied in filename order after 0001_coord / 0002_coord_dispatch). It lives in the BMAD
-- workspace so k8squad stays BMAD-free (see repo-cleanup constraint); copy it verbatim into
-- the migration runner when the Epic-10 Go surface lands.
--
-- Forward-only, versioned, applied exactly once by the apiserver migration runner on startup
-- (mirrors the `coord` schema discipline, §12.3). There is NO down migration — the record is
-- append-only by contract (§7.4). Retraction is the soft `invalidated_at` stamp, never a DELETE.
--
-- The load-bearing invariants (falsified by discussion-schema-check.py, INV1–INV5):
--   * the room IS the Project — 1:1, keyed by project_id; NO `discussion_room` table (R1)
--   * exactly two tables — `discussion_thread`, `discussion_message` (§7.5)
--   * NO coordination/custody column (claim/lease/fence_token/state/holder/assignee) and NO
--     custody-transfer verb anywhere — the room is conversation, not custody (§7.5; 10.4 tests it)
--   * project_id / team_id / author_principal / created_at are NOT NULL — an unscoped or
--     unattributed row is un-representable (the tenancy + provenance substrate 10.2/10.3 stand on)
--   * provenance is server-stamped by the apiserver handler from the authenticated context,
--     NEVER read from the request body (§7.3.1/§6.5) — enforced in the handler, not the DDL
--   * agent-vs-human is DERIVED: author_agent_id IS NOT NULL ⇒ agent; else human (no flag column)

CREATE SCHEMA IF NOT EXISTS discussion;

-- gen_random_uuid() is a core function since PG13 (CNPG ships ≥13) — no pgcrypto extension
-- needed, so the migration runs under a least-privilege app role without CREATE EXTENSION.

-- ---------------------------------------------------------------------------
-- discussion_thread — a conversation within a Project's room (§7.5)
--   The room is the Project (project_id), 1:1, addressable the instant the Project exists —
--   no provisioning step, no seed row, no finalizer. GET .../discussion/threads on a new
--   Project returns an empty list.
-- ---------------------------------------------------------------------------
CREATE TABLE discussion.discussion_thread (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  uuid        NOT NULL,              -- room key + tenancy (1:1 with Project, R1)
    team_id     uuid        NOT NULL,              -- tenancy root (§7.3.3; = squad/namespace)
    title       text        NOT NULL,
    created_by  text        NOT NULL,              -- opener principal — SERVER-STAMPED (§6.5)
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_discussion_thread_project ON discussion.discussion_thread (project_id);
CREATE INDEX idx_discussion_thread_team    ON discussion.discussion_thread (team_id);

-- ---------------------------------------------------------------------------
-- discussion_message — an append-only, provenance-tagged message in a thread (§7.5)
--   Threaded via parent_id (adjacency list, like coord.work_item.parent_id). The provenance
--   triple (author_principal, author_agent_id, author_run_id) is identical to memory's (§7.2)
--   so 10.2's shared pgvector index + untrusted-read envelope project it directly.
-- ---------------------------------------------------------------------------
CREATE TABLE discussion.discussion_message (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id         uuid        NOT NULL REFERENCES discussion.discussion_thread(id),
    parent_id         uuid        REFERENCES discussion.discussion_message(id),  -- reply (NULL = root)
    author_principal  text        NOT NULL,        -- WHO — SERVER-STAMPED (§7.3.1/§6.5)
    author_agent_id   text,                         -- present ⇒ agent-authored; NULL ⇒ human
    author_run_id     text,                         -- Run linkage (R2) — set only from a Run
    body              text        NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    invalidated_at    timestamptz                   -- soft-retract (§7.4); NULL = live
);

-- Note the deliberate ABSENCE of: claim / lease / fence_token / state / holder / assignee /
-- status / any custody column, and any ON DELETE CASCADE. Custody of a work item moves ONLY in
-- the fenced coord claim tables (§6.2/§6.3). This absence is the §7.5 fence, made structural.

CREATE INDEX idx_discussion_message_thread ON discussion.discussion_message (thread_id);
CREATE INDEX idx_discussion_message_parent ON discussion.discussion_message (parent_id)
    WHERE parent_id IS NOT NULL;
-- Default reads filter invalidated_at IS NULL; this partial index serves the live-message path.
CREATE INDEX idx_discussion_message_live   ON discussion.discussion_message (thread_id, created_at)
    WHERE invalidated_at IS NULL;
