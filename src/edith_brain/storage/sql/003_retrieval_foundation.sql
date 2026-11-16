-- Migration 003: Retrieval Foundation (FTS5 Keyword & Vector Embeddings)
-- Migration version: 3

-- 1. FTS5 Virtual Table for Document Chunks
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    chunk_text,
    section,
    source_location,
    content='document_chunks',
    content_rowid='rowid'
);

-- 2. Triggers to keep FTS5 synchronized with document_chunks
CREATE TRIGGER IF NOT EXISTS trg_chunks_ai AFTER INSERT ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(rowid, chunk_text, section, source_location)
    VALUES (new.rowid, new.chunk_text, new.section, new.source_location);
END;

CREATE TRIGGER IF NOT EXISTS trg_chunks_ad AFTER DELETE ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(document_chunks_fts, rowid, chunk_text, section, source_location)
    VALUES ('delete', old.rowid, old.chunk_text, old.section, old.source_location);
END;

CREATE TRIGGER IF NOT EXISTS trg_chunks_au AFTER UPDATE ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(document_chunks_fts, rowid, chunk_text, section, source_location)
    VALUES ('delete', old.rowid, old.chunk_text, old.section, old.source_location);
    INSERT INTO document_chunks_fts(rowid, chunk_text, section, source_location)
    VALUES (new.rowid, new.chunk_text, new.section, new.source_location);
END;

-- 3. Populate FTS5 table with any existing chunks
INSERT INTO document_chunks_fts(rowid, chunk_text, section, source_location)
SELECT rowid, chunk_text, section, source_location FROM document_chunks;

-- 4. Vector Embeddings Table
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    embedding_blob BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model ON chunk_embeddings(model_name);
