-- Migration 005: Episodic and Procedural Memory Subsystem
-- Migration version: 5

-- 1. Episodic Memory: Discrete events, conversations, and experiences
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    title TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('conversation', 'task_execution', 'observation', 'system_event', 'incident')),
    occurred_at TEXT NOT NULL,
    duration_seconds REAL CHECK (duration_seconds IS NULL OR duration_seconds >= 0.0),
    summary TEXT NOT NULL,
    narrative_detail TEXT,
    actors_json TEXT NOT NULL DEFAULT '[]',
    context_tags_json TEXT NOT NULL DEFAULT '[]',
    significance_score REAL NOT NULL DEFAULT 0.5 CHECK (significance_score >= 0.0 AND significance_score <= 1.0),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_episodes_occurred_at ON episodes(occurred_at);
CREATE INDEX IF NOT EXISTS idx_episodes_session_id ON episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_episodes_event_type ON episodes(event_type);
CREATE INDEX IF NOT EXISTS idx_episodes_significance ON episodes(significance_score);

-- FTS5 table for fast keyword and narrative queries across episodes
CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
    title,
    summary,
    narrative_detail,
    content='episodes',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS trg_episodes_ai AFTER INSERT ON episodes BEGIN
    INSERT INTO episodes_fts(rowid, title, summary, narrative_detail)
    VALUES (new.rowid, new.title, new.summary, new.narrative_detail);
END;

CREATE TRIGGER IF NOT EXISTS trg_episodes_ad AFTER DELETE ON episodes BEGIN
    INSERT INTO episodes_fts(episodes_fts, rowid, title, summary, narrative_detail)
    VALUES ('delete', old.rowid, old.title, old.summary, old.narrative_detail);
END;

CREATE TRIGGER IF NOT EXISTS trg_episodes_au AFTER UPDATE ON episodes BEGIN
    INSERT INTO episodes_fts(episodes_fts, rowid, title, summary, narrative_detail)
    VALUES ('delete', old.rowid, old.title, old.summary, old.narrative_detail);
    INSERT INTO episodes_fts(rowid, title, summary, narrative_detail)
    VALUES (new.rowid, new.title, new.summary, new.narrative_detail);
END;

-- 2. Procedural Memory: Reusable workflows, recipes, and operational playbooks
CREATE TABLE IF NOT EXISTS procedures (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0.0',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft', 'active', 'deprecated')),
    trigger_conditions_json TEXT NOT NULL DEFAULT '[]',
    prerequisites_json TEXT NOT NULL DEFAULT '[]',
    steps_json TEXT NOT NULL,
    execution_count INTEGER NOT NULL DEFAULT 0 CHECK (execution_count >= 0),
    success_count INTEGER NOT NULL DEFAULT 0 CHECK (success_count >= 0),
    last_executed_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_procedures_status ON procedures(status);
CREATE INDEX IF NOT EXISTS idx_procedures_version ON procedures(title, version);

-- FTS5 for trigger matching and procedure text lookup
CREATE VIRTUAL TABLE IF NOT EXISTS procedures_fts USING fts5(
    title,
    description,
    trigger_conditions_json,
    content='procedures',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS trg_procedures_ai AFTER INSERT ON procedures BEGIN
    INSERT INTO procedures_fts(rowid, title, description, trigger_conditions_json)
    VALUES (new.rowid, new.title, new.description, new.trigger_conditions_json);
END;

CREATE TRIGGER IF NOT EXISTS trg_procedures_ad AFTER DELETE ON procedures BEGIN
    INSERT INTO procedures_fts(procedures_fts, rowid, title, description, trigger_conditions_json)
    VALUES ('delete', old.rowid, old.title, old.description, old.trigger_conditions_json);
END;

CREATE TRIGGER IF NOT EXISTS trg_procedures_au AFTER UPDATE ON procedures BEGIN
    INSERT INTO procedures_fts(procedures_fts, rowid, title, description, trigger_conditions_json)
    VALUES ('delete', old.rowid, old.title, old.description, old.trigger_conditions_json);
    INSERT INTO procedures_fts(rowid, title, description, trigger_conditions_json)
    VALUES (new.rowid, new.title, new.description, new.trigger_conditions_json);
END;

-- 3. Procedure Execution Telemetry Log
CREATE TABLE IF NOT EXISTS procedure_execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_id TEXT NOT NULL REFERENCES procedures(id) ON DELETE CASCADE,
    executed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    execution_status TEXT NOT NULL CHECK (execution_status IN ('success', 'failure', 'aborted', 'partial')),
    duration_seconds REAL CHECK (duration_seconds IS NULL OR duration_seconds >= 0.0),
    execution_actor TEXT NOT NULL CHECK (execution_actor IN ('LOCAL_USER', 'SYSTEM_PIPELINE', 'TEST_HARNESS')),
    step_results_json TEXT NOT NULL DEFAULT '[]',
    error_message TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_proc_log_procedure ON procedure_execution_logs(procedure_id);
CREATE INDEX IF NOT EXISTS idx_proc_log_executed_at ON procedure_execution_logs(executed_at);

-- 4. Cross-Domain Memory Links: Connecting Episodes, Procedures, and Memories
CREATE TABLE IF NOT EXISTS episodic_procedural_links (
    id TEXT PRIMARY KEY,
    episode_id TEXT REFERENCES episodes(id) ON DELETE CASCADE,
    procedure_id TEXT REFERENCES procedures(id) ON DELETE CASCADE,
    memory_id TEXT REFERENCES memories(id) ON DELETE CASCADE,
    link_type TEXT NOT NULL CHECK (link_type IN ('executed_procedure', 'derived_memory', 'exemplar_episode', 'troubleshooting_context')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((episode_id IS NOT NULL AND procedure_id IS NOT NULL) OR 
           (episode_id IS NOT NULL AND memory_id IS NOT NULL) OR 
           (procedure_id IS NOT NULL AND memory_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_link_episode ON episodic_procedural_links(episode_id);
CREATE INDEX IF NOT EXISTS idx_link_procedure ON episodic_procedural_links(procedure_id);
CREATE INDEX IF NOT EXISTS idx_link_memory ON episodic_procedural_links(memory_id);
