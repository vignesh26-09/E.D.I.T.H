"""Unit tests for embedding providers and vector serialization."""

import numpy as np
import pytest

from edith_brain.services.retrieval.embeddings import (
    DeterministicEmbeddingProvider,
    pack_vector,
    unpack_vector,
    compute_cosine_similarity,
)


def test_deterministic_embedding_provider_dimensionality():
    """Generates vectors matching configured dimensions."""
    provider = DeterministicEmbeddingProvider(dimensions=384)
    assert provider.dimensions == 384
    assert provider.model_name == "deterministic-v1"

    vec = provider.embed_query("E.D.I.T.H. Brain Core retrieval")
    assert len(vec) == 384
    assert isinstance(vec[0], float)


def test_deterministic_embedding_provider_normalization():
    """Output vector must be unit-normalized (L2 norm == 1.0)."""
    provider = DeterministicEmbeddingProvider(dimensions=384)
    vec = np.array(provider.embed_query("Architecture and design patterns"), dtype=np.float32)
    norm = np.linalg.norm(vec)
    assert pytest.approx(norm, rel=1e-4) == 1.0


def test_deterministic_embedding_reproducibility():
    """Identical input yields identical embedding vectors."""
    provider = DeterministicEmbeddingProvider(dimensions=384)
    text = "The quick brown fox jumps over the lazy dog."
    v1 = provider.embed_query(text)
    v2 = provider.embed_query(text)
    assert v1 == v2


def test_deterministic_embedding_semantic_proximity():
    """Related texts have higher similarity than unrelated texts."""
    provider = DeterministicEmbeddingProvider(dimensions=384)
    v_base = np.array(provider.embed_query("FastAPI asynchronous web application"), dtype=np.float32)
    v_sim = np.array(provider.embed_query("FastAPI async web API framework"), dtype=np.float32)
    v_diff = np.array(provider.embed_query("Delicious chocolate cookie recipe dessert"), dtype=np.float32)

    sim_related = compute_cosine_similarity(v_base, v_sim)
    sim_unrelated = compute_cosine_similarity(v_base, v_diff)

    assert sim_related > sim_unrelated


def test_pack_and_unpack_vector():
    """Vector packing and unpacking preserves float32 precision."""
    orig = np.random.randn(384).astype(np.float32)
    blob = pack_vector(orig)
    assert isinstance(blob, bytes)
    assert len(blob) == 384 * 4  # 384 float32 numbers = 1536 bytes

    unpacked = unpack_vector(blob)
    assert unpacked.shape == (384,)
    assert unpacked.dtype == np.float32
    assert np.allclose(orig, unpacked)
