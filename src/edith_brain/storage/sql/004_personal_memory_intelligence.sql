-- Migration 004: Personal Memory Intelligence, Provenance, Verification, and Multi-Model Embeddings
-- Migration version: 4

-- 1. Alter memories table to add verification tracking and canonical content_hash
ALTER TABLE memories ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'unverified'
    CHECK (verification_status IN ('unverified', 'needs_review', 'verified', 'rejected'));

ALTER TABLE memories ADD COLUMN verification_method TEXT NOT NULL DEFAULT 'system_inferred'
    CHECK (verification_method IN ('user_confirmed', 'document_supported', 'externally_verified', 'system_inferred'));

ALTER TABLE memories ADD COLUMN content_hash TEXT;

-- Enforce valid lifecycle status on memories table via SQLite triggers
CREATE TRIGGER IF NOT EXISTS trg_memories_status_check_insert
BEFORE INSERT ON memories
BEGIN
    SELECT CASE
        WHEN new.status NOT IN ('active', 'superseded', 'revoked')
        THEN RAISE(ABORT, 'Constraint violation: memory status must be one of: active, superseded, revoked')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_memories_status_check_update
BEFORE UPDATE OF status ON memories
BEGIN
    SELECT CASE
        WHEN new.status NOT IN ('active', 'superseded', 'revoked')
        THEN RAISE(ABORT, 'Constraint violation: memory status must be one of: active, superseded, revoked')
    END;
END;

-- Anti-stale embedding trigger: if memory content is mutated in place, evict cached embeddings
CREATE TRIGGER IF NOT EXISTS trg_memories_content_stale_emb
AFTER UPDATE OF content ON memories
BEGIN
    DELETE FROM memory_embeddings WHERE memory_id = new.id;
END;

-- 2. External Content FTS5 Table for Memories
-- Exact column parity with 'memories' content table (content, tags_json)
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    tags_json,
    content='memories',
    content_rowid='rowid'
);

-- 3. FTS5 Synchronization Triggers
CREATE TRIGGER IF NOT EXISTS trg_memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags_json)
    VALUES (new.rowid, new.content, new.tags_json);
END;

CREATE TRIGGER IF NOT EXISTS trg_memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags_json)
    VALUES ('delete', old.rowid, old.content, old.tags_json);
END;

CREATE TRIGGER IF NOT EXISTS trg_memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags_json)
    VALUES ('delete', old.rowid, old.content, old.tags_json);
    INSERT INTO memories_fts(rowid, content, tags_json)
    VALUES (new.rowid, new.content, new.tags_json);
END;

-- Backfill active memories into FTS5
INSERT INTO memories_fts(rowid, content, tags_json)
SELECT rowid, content, tags_json FROM memories;

-- 4. Multi-Model Vector Embeddings Coexistence Table
CREATE TABLE IF NOT EXISTS memory_embeddings (
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    data_type TEXT NOT NULL DEFAULT 'float32' CHECK (data_type = 'float32'),
    content_hash TEXT NOT NULL,
    embedding_blob BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (memory_id, model_name, model_version)
);

CREATE INDEX IF NOT EXISTS idx_mem_emb_lookup ON memory_embeddings(model_name, model_version);
CREATE INDEX IF NOT EXISTS idx_mem_emb_hash ON memory_embeddings(content_hash);

-- Active memory embedding model registry (Single row singleton)
-- Starts EMPTY. Explicitly represents the absence of an active neural semantic model.
CREATE TABLE IF NOT EXISTS active_memory_embedding_model (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    activated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- 5. Directed & Canonical Memory Associations Graph
CREATE TABLE IF NOT EXISTS memory_associations (
    id TEXT PRIMARY KEY,
    source_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL CHECK (relation_type IN ('supports', 'contradicts', 'relates_to', 'derived_from', 'supersedes')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (source_memory_id != target_memory_id),
    CHECK (relation_type != 'relates_to' OR source_memory_id < target_memory_id),
    UNIQUE(source_memory_id, target_memory_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_assoc_source ON memory_associations(source_memory_id);
CREATE INDEX IF NOT EXISTS idx_assoc_target ON memory_associations(target_memory_id);
CREATE INDEX IF NOT EXISTS idx_assoc_relation ON memory_associations(relation_type);

-- 6. Dedicated Document and Chunk Provenance Citations
CREATE TABLE IF NOT EXISTS memory_citations (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
    chunk_id TEXT REFERENCES document_chunks(id) ON DELETE SET NULL,
    historical_document_id TEXT,
    historical_chunk_id TEXT,
    citation_status TEXT NOT NULL DEFAULT 'valid' CHECK (citation_status IN ('valid', 'source_removed')),
    quote_text TEXT,
    confidence_score REAL NOT NULL DEFAULT 1.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (historical_document_id IS NOT NULL OR historical_chunk_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_citations_memory ON memory_citations(memory_id);
CREATE INDEX IF NOT EXISTS idx_citations_doc ON memory_citations(document_id);
CREATE INDEX IF NOT EXISTS idx_citations_chunk ON memory_citations(chunk_id);

-- Automatic source-removal transition triggers
CREATE TRIGGER IF NOT EXISTS trg_citation_doc_deleted
AFTER UPDATE OF document_id ON memory_citations
WHEN new.document_id IS NULL AND old.document_id IS NOT NULL
BEGIN
    UPDATE memory_citations SET citation_status = 'source_removed' WHERE id = new.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_citation_chunk_deleted
AFTER UPDATE OF chunk_id ON memory_citations
WHEN new.chunk_id IS NULL AND old.chunk_id IS NOT NULL AND new.document_id IS NULL
BEGIN
    UPDATE memory_citations SET citation_status = 'source_removed' WHERE id = new.id;
END;

-- 7. Verification Audit History Table (Append-Only During Normal Lifecycle)
CREATE TABLE IF NOT EXISTS memory_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    previous_status TEXT CHECK (previous_status IS NULL OR previous_status IN ('unverified', 'needs_review', 'verified', 'rejected')),
    new_status TEXT NOT NULL CHECK (new_status IN ('unverified', 'needs_review', 'verified', 'rejected')),
    verification_method TEXT NOT NULL CHECK (verification_method IN ('user_confirmed', 'document_supported', 'externally_verified', 'system_inferred')),
    verifier_actor TEXT NOT NULL CHECK (verifier_actor IN ('LOCAL_USER', 'SYSTEM_PIPELINE', 'TEST_HARNESS')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_verifications_memory ON memory_verifications(memory_id);

-- Protect normal audit operations: rows cannot be modified once written
CREATE TRIGGER IF NOT EXISTS trg_no_update_memory_verifications
BEFORE UPDATE ON memory_verifications
BEGIN
    SELECT RAISE(ABORT, 'Illegal operation: memory_verifications records are append-only and cannot be modified.');
END;
