"""Ranked memory retrieval service supporting FTS5 BM25, cosine similarity, and RRF hybrid fusion."""

import json
from typing import Optional
import numpy as np

from edith_brain.core.contracts import (
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    MemoryResponse,
    MemoryCitationResponse,
    MemoryAssociationResponse,
    SearchMode,
    MemoryCategory,
    PersonalSubcategory,
    MemoryStatus,
    VerificationStatus,
    VerificationMethod,
    CitationStatus,
    RelationType,
)
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.memory_repository import MemoryRepository
from edith_brain.repositories.memory_embedding_repository import MemoryEmbeddingRepository
from edith_brain.repositories.memory_citation_repository import MemoryCitationRepository
from edith_brain.repositories.memory_association_repository import MemoryAssociationRepository
from edith_brain.services.retrieval.embeddings import (
    BaseEmbeddingProvider,
    unpack_vector,
    compute_cosine_similarity,
)
from edith_brain.services.retrieval.query_parser import sanitize_fts5_query


class MemorySearchService:
    """Orchestrates keyword, semantic, and hybrid search over personal memories with explicit fallback semantics."""

    def __init__(
        self,
        engine: SQLiteEngine,
        memory_repo: MemoryRepository | None = None,
        embedding_repo: MemoryEmbeddingRepository | None = None,
        citation_repo: MemoryCitationRepository | None = None,
        association_repo: MemoryAssociationRepository | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
    ) -> None:
        self.engine = engine
        self.memory_repo = memory_repo or MemoryRepository()
        self.embedding_repo = embedding_repo or MemoryEmbeddingRepository()
        self.citation_repo = citation_repo or MemoryCitationRepository()
        self.association_repo = association_repo or MemoryAssociationRepository()
        self.embedding_provider = embedding_provider

    def _row_to_memory_response(self, row: dict) -> MemoryResponse:
        v_status = row.get("verification_status") or "unverified"
        v_method = row.get("verification_method") or "system_inferred"
        return MemoryResponse(
            id=row["id"],
            category=MemoryCategory(row["category"]),
            subcategory=PersonalSubcategory(row["subcategory"]) if row.get("subcategory") else None,
            content=row["content"],
            confidence=row["confidence"],
            source_type=row["source_type"],
            source_reference_id=row.get("source_reference_id"),
            status=MemoryStatus(row["status"]),
            parent_memory_id=row.get("parent_memory_id"),
            tags=json.loads(row["tags_json"]),
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            verified_at=row.get("verified_at"),
            verification_status=VerificationStatus(v_status),
            verification_method=VerificationMethod(v_method),
            content_hash=row.get("content_hash"),
        )

    def _fetch_attachments(
        self,
        conn,
        memory_id: str,
    ) -> tuple[list[MemoryCitationResponse], list[MemoryAssociationResponse]]:
        cit_rows = self.citation_repo.get_by_memory_id(conn, memory_id)
        citations = [
            MemoryCitationResponse(
                id=r["id"],
                memory_id=r["memory_id"],
                document_id=r["document_id"],
                chunk_id=r["chunk_id"],
                historical_document_id=r["historical_document_id"],
                historical_chunk_id=r["historical_chunk_id"],
                citation_status=CitationStatus(r["citation_status"]),
                quote_text=r["quote_text"],
                confidence_score=r["confidence_score"],
                metadata=json.loads(r["metadata_json"]),
                created_at=r["created_at"],
            )
            for r in cit_rows
        ]

        assoc_rows = self.association_repo.get_by_memory_id(conn, memory_id)
        associations = [
            MemoryAssociationResponse(
                id=r["id"],
                source_memory_id=r["source_memory_id"],
                target_memory_id=r["target_memory_id"],
                relation_type=RelationType(r["relation_type"]),
                metadata=json.loads(r["metadata_json"]),
                created_at=r["created_at"],
            )
            for r in assoc_rows
        ]
        return citations, associations

    def search(self, request: MemorySearchRequest) -> MemorySearchResponse:
        """Execute memory retrieval under specified or fallback mode."""
        with self.engine.connection() as conn:
            active_model_row = self.embedding_repo.get_active_model(conn)
            has_neural_model = (
                active_model_row is not None
                and self.embedding_provider is not None
                and getattr(self.embedding_provider, "provider_type", "") == "neural_semantic"
            )

            # Check if requested mode requires fallback
            effective_mode = request.mode
            fallback_applied = False
            fallback_reason = None

            if request.mode in (SearchMode.SEMANTIC, SearchMode.HYBRID) and not has_neural_model:
                effective_mode = SearchMode.KEYWORD
                fallback_applied = True
                fallback_reason = (
                    "No active neural semantic model configured or available. "
                    "Fell back to keyword FTS5 retrieval."
                )

            active_model_name = active_model_row["model_name"] if active_model_row else None
            active_model_ver = active_model_row["model_version"] if active_model_row else None

            # Execute search by effective mode
            if effective_mode == SearchMode.KEYWORD:
                results = self._search_keyword(conn, request)
            elif effective_mode == SearchMode.SEMANTIC:
                results = self._search_semantic(conn, request, active_model_row)
            else:  # HYBRID
                results = self._search_hybrid(conn, request, active_model_row)

            return MemorySearchResponse(
                results=results,
                total_results=len(results),
                effective_mode=effective_mode,
                fallback_applied=fallback_applied,
                fallback_reason=fallback_reason,
                active_model=active_model_name,
                active_model_version=active_model_ver,
            )

    def _search_keyword(self, conn, request: MemorySearchRequest) -> list[MemorySearchResult]:
        sanitized = sanitize_fts5_query(request.query, match_mode="OR")
        if not sanitized or sanitized == '""':
            return []

        rows = self.memory_repo.search_keyword_fts5(
            conn=conn,
            sanitized_query=sanitized,
            category=request.category.value if request.category else None,
            subcategory=request.subcategory.value if request.subcategory else None,
            include_statuses=[s.value for s in request.include_statuses],
            include_verification=[v.value for v in request.include_verification],
            min_confidence=request.min_confidence,
            limit=request.limit,
        )

        results = []
        for r in rows:
            mem_resp = self._row_to_memory_response(r)
            citations, associations = self._fetch_attachments(conn, mem_resp.id)
            # Normalize BM25 score for display (e.g. 1.0 / (1.0 + abs(bm25_rank)))
            bm25_val = float(r.get("bm25_rank", 0.0))
            score = round(1.0 / (1.0 + abs(bm25_val)), 4)

            results.append(
                MemorySearchResult(
                    memory=mem_resp,
                    score=score,
                    match_source="keyword_fts5",
                    citations=citations,
                    associations=associations,
                )
            )
        return results

    def _search_semantic(
        self,
        conn,
        request: MemorySearchRequest,
        active_model_row,
    ) -> list[MemorySearchResult]:
        query_vec = np.array(self.embedding_provider.embed_query(request.query), dtype=np.float32)
        stored_vectors = self.embedding_repo.get_active_embeddings(
            conn,
            model_name=active_model_row["model_name"],
            model_version=active_model_row["model_version"],
        )

        scored_memories = []
        for sv in stored_vectors:
            vec = unpack_vector(sv["embedding_blob"])
            sim = compute_cosine_similarity(query_vec, vec)
            scored_memories.append((sv["memory_id"], sim))

        # Sort by similarity descending
        scored_memories.sort(key=lambda x: x[1], reverse=True)

        results = []
        for mem_id, sim in scored_memories:
            row = self.memory_repo.get_by_id(conn, mem_id)
            if not row:
                continue

            # Apply filters
            if request.category and row["category"] != request.category.value:
                continue
            if request.subcategory and row["subcategory"] != request.subcategory.value:
                continue
            if row["status"] not in [s.value for s in request.include_statuses]:
                continue
            if row["verification_status"] not in [v.value for v in request.include_verification]:
                continue
            if row["confidence"] < request.min_confidence:
                continue

            mem_resp = self._row_to_memory_response(dict(row))
            citations, associations = self._fetch_attachments(conn, mem_resp.id)
            results.append(
                MemorySearchResult(
                    memory=mem_resp,
                    score=round(float(sim), 4),
                    match_source="semantic_cosine",
                    citations=citations,
                    associations=associations,
                )
            )
            if len(results) >= request.limit:
                break

        return results

    def _search_hybrid(
        self,
        conn,
        request: MemorySearchRequest,
        active_model_row,
    ) -> list[MemorySearchResult]:
        # Top-N keyword candidates
        kw_req = request.model_copy()
        kw_req.limit = max(request.limit * 2, 20)
        kw_results = self._search_keyword(conn, kw_req)

        # Top-N semantic candidates
        sem_req = request.model_copy()
        sem_req.limit = max(request.limit * 2, 20)
        sem_results = self._search_semantic(conn, sem_req, active_model_row)

        rrf_k = 60
        rrf_scores: dict[str, float] = {}
        memory_objects: dict[str, MemoryResponse] = {}
        attachments: dict[str, tuple[list[MemoryCitationResponse], list[MemoryAssociationResponse]]] = {}

        # Accumulate keyword ranks
        for rank, item in enumerate(kw_results, start=1):
            mem_id = item.memory.id
            rrf_scores[mem_id] = rrf_scores.get(mem_id, 0.0) + (1.0 / (rrf_k + rank))
            memory_objects[mem_id] = item.memory
            attachments[mem_id] = (item.citations, item.associations)

        # Accumulate semantic ranks
        for rank, item in enumerate(sem_results, start=1):
            mem_id = item.memory.id
            rrf_scores[mem_id] = rrf_scores.get(mem_id, 0.0) + (1.0 / (rrf_k + rank))
            memory_objects[mem_id] = item.memory
            attachments[mem_id] = (item.citations, item.associations)

        # Sort with deterministic tie-breaking
        sorted_ids = sorted(
            rrf_scores.keys(),
            key=lambda mid: (
                rrf_scores[mid],
                memory_objects[mid].confidence,
                memory_objects[mid].created_at,
                mid,
            ),
            reverse=True,
        )

        results = []
        for mid in sorted_ids[: request.limit]:
            cits, assocs = attachments[mid]
            results.append(
                MemorySearchResult(
                    memory=memory_objects[mid],
                    score=round(rrf_scores[mid], 5),
                    match_source="hybrid_rrf",
                    citations=cits,
                    associations=assocs,
                )
            )

        return results
