"""Retrieval service orchestrating FTS5 keyword, vector semantic, and hybrid RRF search."""

import time
from typing import Optional
import numpy as np

from edith_brain.core.config import Settings, get_settings
from edith_brain.core.contracts import (
    RetrievalMode,
    RetrievalQuery,
    SearchResultItem,
    SearchResponse,
    IndexStatsResponse,
    EmbeddingIndexResponse,
)
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.retrieval_repository import RetrievalRepository
from edith_brain.services.retrieval.query_parser import sanitize_fts5_query
from edith_brain.services.retrieval.embeddings import (
    BaseEmbeddingProvider,
    get_embedding_provider,
    pack_vector,
    unpack_vector,
)


class RetrievalService:
    """Domain service managing multi-modal search across document knowledge."""

    def __init__(
        self,
        engine: SQLiteEngine,
        retrieval_repo: RetrievalRepository | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.engine = engine
        self.retrieval_repo = retrieval_repo or RetrievalRepository()
        self.settings = settings or get_settings()
        self.embedding_provider = embedding_provider or get_embedding_provider(settings=self.settings)

    def keyword_search(
        self,
        query: str,
        document_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchResultItem]:
        """Execute SQLite FTS5 full-text keyword search with BM25 ranking."""
        sanitized = sanitize_fts5_query(query)
        if not sanitized or sanitized == '""':
            return []

        with self.engine.connection() as conn:
            rows = self.retrieval_repo.search_keyword_fts5(
                conn=conn,
                sanitized_query=sanitized,
                document_id=document_id,
                limit=top_k * 2,
            )

        results = []
        for row in rows:
            # FTS5 bm25 produces negative numbers where more negative = better match
            raw_bm25 = row["bm25_score"]
            # Normalize to 0.0-1.0 range: score = 1.0 / (1.0 + abs(raw_bm25))
            norm_score = float(1.0 / (1.0 + abs(raw_bm25)))

            if norm_score < min_score:
                continue

            results.append(
                SearchResultItem(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    document_title=row["document_title"],
                    chunk_index=row["chunk_index"],
                    chunk_text=row["chunk_text"],
                    score=round(norm_score, 4),
                    page_number=row["page_number"],
                    section=row["section"],
                    source_location=row["source_location"],
                    highlights=row["highlight"],
                    retrieval_mode=RetrievalMode.KEYWORD,
                )
            )

        # Sort by score descending and take top_k
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def semantic_search(
        self,
        query: str,
        document_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchResultItem]:
        """Execute vector semantic search via cosine similarity."""
        if not query or not query.strip():
            return []

        # 1. Generate query embedding
        query_vector = np.array(self.embedding_provider.embed_query(query), dtype=np.float32)

        # 2. Fetch stored document embeddings
        with self.engine.connection() as conn:
            rows = self.retrieval_repo.get_all_embeddings(conn, document_id=document_id)

        if not rows:
            return []

        # 3. Vectorized cosine similarity computation
        # Since vectors are unit-normalized upon storage, dot product == cosine similarity
        embedding_blobs = [unpack_vector(r["embedding_blob"]) for r in rows]
        doc_matrix = np.vstack(embedding_blobs)  # shape (N, D)
        similarities = np.dot(doc_matrix, query_vector)  # shape (N,)

        results = []
        for idx, row in enumerate(rows):
            sim_score = float(similarities[idx])
            if sim_score < min_score:
                continue

            # Generate contextual highlight snippet (first 180 chars)
            txt = row["chunk_text"]
            preview = (txt[:180] + "...") if len(txt) > 180 else txt

            results.append(
                SearchResultItem(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    document_title=row["document_title"],
                    chunk_index=row["chunk_index"],
                    chunk_text=row["chunk_text"],
                    score=round(sim_score, 4),
                    page_number=row["page_number"],
                    section=row["section"],
                    source_location=row["source_location"],
                    highlights=preview,
                    retrieval_mode=RetrievalMode.SEMANTIC,
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def hybrid_search(
        self,
        query: str,
        document_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchResultItem]:
        """Combine keyword and semantic search using Reciprocal Rank Fusion (RRF)."""
        fetch_k = top_k * 3

        # Run both retrieval modes
        keyword_results = self.keyword_search(query, document_id=document_id, top_k=fetch_k)
        semantic_results = self.semantic_search(query, document_id=document_id, top_k=fetch_k)

        # RRF scoring
        k_param = self.settings.rrf_k_parameter
        rrf_scores: dict[str, float] = {}
        items_by_id: dict[str, SearchResultItem] = {}

        # 1. Accumulate keyword ranks
        for rank, item in enumerate(keyword_results, start=1):
            rrf_scores[item.chunk_id] = rrf_scores.get(item.chunk_id, 0.0) + (1.0 / (k_param + rank))
            items_by_id[item.chunk_id] = item

        # 2. Accumulate semantic ranks
        for rank, item in enumerate(semantic_results, start=1):
            rrf_scores[item.chunk_id] = rrf_scores.get(item.chunk_id, 0.0) + (1.0 / (k_param + rank))
            if item.chunk_id not in items_by_id:
                items_by_id[item.chunk_id] = item
            else:
                # If item already present from keyword, keep keyword's snippet highlight if available
                if not items_by_id[item.chunk_id].highlights and item.highlights:
                    items_by_id[item.chunk_id].highlights = item.highlights

        # 3. Construct unified sorted list
        hybrid_results = []
        for chunk_id, combined_score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
            if combined_score < min_score:
                continue
            base_item = items_by_id[chunk_id]
            hybrid_results.append(
                SearchResultItem(
                    chunk_id=base_item.chunk_id,
                    document_id=base_item.document_id,
                    document_title=base_item.document_title,
                    chunk_index=base_item.chunk_index,
                    chunk_text=base_item.chunk_text,
                    score=round(combined_score, 4),
                    page_number=base_item.page_number,
                    section=base_item.section,
                    source_location=base_item.source_location,
                    highlights=base_item.highlights,
                    retrieval_mode=RetrievalMode.HYBRID,
                )
            )

        return hybrid_results[:top_k]

    def search(self, payload: RetrievalQuery) -> SearchResponse:
        """Execute search dispatching to chosen mode and measuring latency."""
        start_time = time.perf_counter()

        if payload.mode == RetrievalMode.KEYWORD:
            results = self.keyword_search(
                query=payload.query,
                document_id=payload.document_id,
                top_k=payload.top_k,
                min_score=payload.min_score,
            )
        elif payload.mode == RetrievalMode.SEMANTIC:
            results = self.semantic_search(
                query=payload.query,
                document_id=payload.document_id,
                top_k=payload.top_k,
                min_score=payload.min_score,
            )
        else:
            results = self.hybrid_search(
                query=payload.query,
                document_id=payload.document_id,
                top_k=payload.top_k,
                min_score=payload.min_score,
            )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        return SearchResponse(
            query=payload.query,
            mode=payload.mode,
            total_results=len(results),
            results=results,
            latency_ms=elapsed_ms,
        )

    def index_unembedded_chunks(
        self,
        document_id: Optional[str] = None,
        batch_size: int = 50,
    ) -> EmbeddingIndexResponse:
        """Batch generate and store embeddings for chunks without vectors."""
        total_indexed = 0

        while True:
            with self.engine.connection() as conn:
                unembedded = self.retrieval_repo.get_unembedded_chunks(
                    conn=conn,
                    document_id=document_id,
                    limit=batch_size,
                )

            if not unembedded:
                break

            texts = [row["chunk_text"] for row in unembedded]
            chunk_ids = [row["id"] for row in unembedded]

            # Generate embeddings
            vectors = self.embedding_provider.embed_documents(texts)

            embeddings_data = [
                {
                    "chunk_id": chunk_ids[i],
                    "model_name": self.embedding_provider.model_name,
                    "dimensions": self.embedding_provider.dimensions,
                    "embedding_blob": pack_vector(vectors[i]),
                }
                for i in range(len(chunk_ids))
            ]

            with self.engine.write_transaction() as conn:
                self.retrieval_repo.insert_embeddings_bulk(conn, embeddings_data)

            total_indexed += len(embeddings_data)

        return EmbeddingIndexResponse(
            indexed_count=total_indexed,
            model_name=self.embedding_provider.model_name,
            dimensions=self.embedding_provider.dimensions,
        )

    def get_index_stats(self) -> IndexStatsResponse:
        """Retrieve keyword and vector index statistics."""
        with self.engine.connection() as conn:
            raw_stats = self.retrieval_repo.get_index_stats(conn)

        return IndexStatsResponse(
            total_documents=raw_stats["total_documents"],
            total_chunks=raw_stats["total_chunks"],
            fts5_indexed_chunks=raw_stats["fts5_indexed_chunks"],
            embedded_chunks=raw_stats["embedded_chunks"],
            embedding_model=self.embedding_provider.model_name,
            embedding_dimensions=self.embedding_provider.dimensions,
        )
