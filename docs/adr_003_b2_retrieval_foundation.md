# ADR 003: Keyword, Semantic, and Hybrid Retrieval Foundation (Phase B2)

## Context
Phase B2 establishes an inspectable, deterministic, and high-performance retrieval foundation across ingested knowledge document chunks. The environment is a Windows 11 host with an 8 GB RAM budget, CPU-only hardware, and zero software cost. Brain Core must remain independent of external LLMs or cloud vector databases.

## Architectural Decisions

### 1. Native SQLite FTS5 for Keyword Search
- **Decision:** Full-text search is implemented directly in SQLite using an FTS5 virtual table (`document_chunks_fts`) linked as an external content table to `document_chunks`.
- **Triggers:** Automatic synchronization via `AFTER INSERT`, `AFTER UPDATE`, and `AFTER DELETE` triggers ensures the FTS5 index is always consistent with `document_chunks` without manual re-indexing.
- **BM25 Ranking & Snippet Generation:** Matches are scored using SQLite's native `bm25(document_chunks_fts, 2.0, 1.0, 0.5)` giving weighted priority to chunk text, section, and location. Snippets are highlighted with `<mark>` tags.
- **Query Sanitization:** `sanitize_fts5_query()` parses user inputs into safe alphanumeric prefix tokens (`"token"*`), neutralizing syntax crashes caused by colons, asterisks, unbalanced quotes, or boolean operators.

### 2. Dual-Engine Local Vector Embeddings
- **Decision:** Embedding generation is decoupled behind `BaseEmbeddingProvider`:
  1. `DeterministicEmbeddingProvider` (Default / Local-first): Projects token and character n-gram frequencies into a unit-normalized 384-dimensional vector space via consistent hashing. Runs in microseconds on CPU with zero network downloads, ideal for low-memory resource profiles and offline environments.
  2. `FastEmbedProvider`: Supports ONNX-based local neural embeddings (`BAAI/bge-small-en-v1.5`, 384 dimensions) using CPU-optimized ONNX runtime without PyTorch.
- **Storage:** Dense vectors are stored in SQLite table `chunk_embeddings` as packed `float32` BLOBs (`pack_vector` / `unpack_vector`), cascading automatically on chunk deletion.

### 3. In-Memory Vector Cosine Similarity
- **Decision:** Because the personal knowledge base on an 8 GB machine contains thousands of chunks, in-memory vectorized matrix multiplication using NumPy (`np.dot(doc_matrix, query_vector)`) computes exact cosine similarity in <2 milliseconds on CPU, avoiding the memory footprint of heavy external vector databases (Chroma, Milvus, Qdrant).

### 4. Hybrid Search via Reciprocal Rank Fusion (RRF)
- **Decision:** When `mode="hybrid"`, the system retrieves the top candidate chunks from both the keyword engine (BM25) and semantic engine (cosine similarity), and combines their ranks using standard Reciprocal Rank Fusion:
  $$RRF(d) = \sum_{m \in \{keyword, semantic\}} \frac{1.0}{60 + rank_m(d)}$$
  This balances exact lexical term matches with semantic proximity and returns unified highlights and provenance.

### 5. Automatic Ingestion Embedding Hook
- **Decision:** `DocumentService` automatically embeds document chunks at ingestion time within the primary write transaction, ensuring documents are immediately searchable upon upload.

## Consequences & Limitations
- Personal memory retrieval, episodic memory indexing, and cross-memory synthesis belong to **Phase B3: Personal Memory** and **Phase B4: Episodic & Procedural Memory**.
- Reranking via cross-encoders is deferred to Phase B5.
