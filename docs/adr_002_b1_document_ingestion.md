# ADR 002: Document Ingestion Subsystem and Multi-Format Chunking Engine (Phase B1)

## Context
Phase B1 transforms uploaded documents into validated, normalized, structured, and traceable text chunks for downstream indexing and retrieval in Phase B2. The operational environment remains Windows 11 with an 8 GB RAM profile, CPU-only hardware, and zero software budget.

## Architectural Decisions

### 1. Isolated Parser Adapters
- **Decision:** Document parsing is encapsulated behind `BaseDocumentParser`, producing a standardized `ExtractionResult` containing text, structural elements (`ExtractedElement`), extraction method, warnings, and metadata.
- **Adapters Implemented:**
  - `PlainTextParser`: Multi-encoding fallback (UTF-8, UTF-8-SIG, Latin-1, CP1252), line range tracking.
  - `MarkdownParser`: Preserves ATX heading hierarchy (`#`, `##`, `###`), section breadcrumbs (`Doc > Section > Sub`), code blocks, and lists.
  - `PDFParser`: Uses lightweight `pypdf`, tracking page numbers, outline/TOC headings, and page paragraph blocks.
  - `DocxParser`: Isolated adapter using `python-docx`, parsing heading styles, paragraphs, and tables.
- **Factory:** `ParserRegistry` resolves adapters via file extension and MIME type.

### 2. Dual-Tier Storage Preservation
- **Decision:**
  - Original uploaded files are preserved unmodified in `data/storage/raw/{content_hash}{ext}` to guarantee exact byte preservation.
  - Cleaned, normalized plaintext is saved separately in `data/storage/extracted/{doc_id}.txt`.
- **Integrity Rule:** Canonical path validation (`validate_safe_path`) and file-size validation guard against path traversal attacks and resource exhaustion.

### 3. Controlled Text Normalization
- **Decision:** `normalize_text()` enforces uniform `\n` line endings, strips non-printable control characters (while strictly keeping tabs and newlines), trims trailing whitespace per line, and collapses excessive empty lines (>2 down to 2). Text semantics, punctuation, and wording are preserved without aggressive destructive cleaning.

### 4. Deterministic Multi-Strategy Chunking & Lightweight Token Estimation
- **Decision:**
  - Chunking strategies: `FixedSizeChunker`, `SlidingWindowChunker`, and `StructureAwareChunker` (default).
  - Structure-aware chunking preserves heading contexts, section breadcrumbs, and page boundaries without breaking sentences or paragraphs unless an element exceeds target chunk size.
  - Lightweight heuristic token estimation (~4 chars/token) runs in microseconds with zero neural network or model dependencies, implemented via the `TokenEstimator` protocol for easy drop-in replacement in B2.

### 5. Checksum-Verified Database Migration & Cleanup
- **Decision:**
  - Migration `002_document_ingestion.sql` extends `documents` with `original_filename`, `file_extension`, `ingestion_status`, `error_message`, and `chunk_count`.
  - Document deletion (`DELETE /api/v1/documents/{id}`) cascades SQLite chunks and unlinks raw/extracted physical files.
  - Ingestion failure rollback unlinks partial files if parsing or database insertion fails.

## Consequences & Limitations
- Keyword indexing (FTS5 search queries) and semantic embeddings are intentionally deferred to Phase B2.
- Scanned PDF optical character recognition (OCR) is out of scope for B1 CPU-only constraints.
