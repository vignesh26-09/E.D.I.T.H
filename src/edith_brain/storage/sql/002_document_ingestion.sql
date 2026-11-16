-- Migration 002: Document Ingestion Enhancements
-- Migration version: 2

ALTER TABLE documents ADD COLUMN original_filename TEXT;
ALTER TABLE documents ADD COLUMN file_extension TEXT;
ALTER TABLE documents ADD COLUMN ingestion_status TEXT NOT NULL DEFAULT 'processed';
ALTER TABLE documents ADD COLUMN error_message TEXT;
ALTER TABLE documents ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(ingestion_status);
