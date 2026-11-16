-- Migration 001: Initial Schema for E.D.I.T.H. Brain Core
-- Migration version: 1

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- 1. Knowledge Documents Table
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_uri TEXT,
    source_type TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT 'text/plain',
    file_size_bytes INTEGER NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    raw_storage_path TEXT NOT NULL,
    extracted_storage_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type);

-- 2. Document Chunks with Retrieval Provenance
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    section TEXT,
    source_location TEXT,
    extraction_method TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    token_count INTEGER,
    chunk_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON document_chunks(content_hash);

-- 3. Structured Memories Table
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,                    -- 'personal', 'semantic', 'episodic', 'procedural'
    subcategory TEXT,                          -- For personal: 'profile_fact', 'preference', 'goal', 'skill', 'project_context', 'decision'
    content TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    source_type TEXT NOT NULL,                 -- 'user_explicit', 'inferred', 'document_extract', 'system'
    source_reference_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',     -- 'active', 'superseded', 'revoked'
    parent_memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    verified_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_subcategory ON memories(subcategory);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);

-- 4. Memory Audit Log (Privacy-Preserving Audit Trail)
CREATE TABLE IF NOT EXISTS memory_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL,
    action TEXT NOT NULL,                      -- 'created', 'updated', 'corrected', 'revoked', 'purged'
    change_reason TEXT NOT NULL,
    previous_state_json TEXT,                  -- Sanitized JSON; overwritten with '[REDACTED_PURGED]' on purge
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_memory_id ON memory_audit_log(memory_id);
