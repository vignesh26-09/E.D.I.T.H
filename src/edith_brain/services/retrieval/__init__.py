"""Retrieval subsystem: Keyword (FTS5), Semantic (Vector), and Hybrid (RRF) search."""

from edith_brain.services.retrieval.embeddings import (
    BaseEmbeddingProvider,
    DeterministicEmbeddingProvider,
    FastEmbedProvider,
    get_embedding_provider,
    pack_vector,
    unpack_vector,
    compute_cosine_similarity,
)
from edith_brain.services.retrieval.query_parser import sanitize_fts5_query
from edith_brain.services.retrieval.retrieval_service import RetrievalService

__all__ = [
    "BaseEmbeddingProvider",
    "DeterministicEmbeddingProvider",
    "FastEmbedProvider",
    "get_embedding_provider",
    "pack_vector",
    "unpack_vector",
    "compute_cosine_similarity",
    "sanitize_fts5_query",
    "RetrievalService",
]
