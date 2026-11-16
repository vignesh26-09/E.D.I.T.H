-- Phase B5: Memory Intelligence, Decay Dynamics, and Evaluation Benchmarks
-- Migration 006

-- 1. Telemetry columns on memories for recency and decay dynamics
ALTER TABLE memories ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN last_accessed_at TEXT;

-- Index for decay-weighted recency queries
CREATE INDEX IF NOT EXISTS idx_memories_access ON memories(last_accessed_at, access_count);

-- 2. Consolidation candidates table
-- Stores prospective semantic facts distilled from episodic clusters
CREATE TABLE IF NOT EXISTS memory_consolidations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    candidate_category TEXT NOT NULL CHECK(candidate_category IN ('personal', 'semantic', 'episodic', 'procedural')),
    candidate_subcategory TEXT CHECK(candidate_subcategory IS NULL OR candidate_subcategory IN ('profile_fact', 'preference', 'goal', 'skill', 'project_context')),
    candidate_content TEXT NOT NULL,
    rationale TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.7 CHECK(confidence >= 0.0 AND confidence <= 1.0),
    source_episode_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'applied')) DEFAULT 'pending',
    applied_memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_consol_session ON memory_consolidations(session_id);
CREATE INDEX IF NOT EXISTS idx_consol_status ON memory_consolidations(status);

-- 3. Evaluation runs table
-- Records quantitative benchmark runs (retrieval metrics, latency, accuracy)
CREATE TABLE IF NOT EXISTS memory_evaluation_runs (
    id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    execution_time_ms REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_type ON memory_evaluation_runs(run_type);
CREATE INDEX IF NOT EXISTS idx_eval_runs_created ON memory_evaluation_runs(created_at);
