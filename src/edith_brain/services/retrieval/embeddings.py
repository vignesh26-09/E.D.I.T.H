"""Embedding providers and vector serialization utilities for semantic retrieval."""

import math
import hashlib
from abc import ABC, abstractmethod
from typing import Optional
import numpy as np

from edith_brain.core.config import Settings, get_settings


def pack_vector(vec: list[float] | np.ndarray) -> bytes:
    """Pack float array or list into compact float32 binary buffer."""
    if isinstance(vec, list):
        arr = np.array(vec, dtype=np.float32)
    else:
        arr = vec.astype(np.float32)
    return arr.tobytes()


def unpack_vector(blob: bytes) -> np.ndarray:
    """Unpack float32 binary buffer into NumPy 1D array."""
    return np.frombuffer(blob, dtype=np.float32)


def compute_cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between two 1D float vectors."""
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return float(np.dot(vec1, vec2) / (norm1 * norm2))


class BaseEmbeddingProvider(ABC):
    """Abstract interface for generating vector embeddings."""

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """'test_hash' vs 'neural_semantic'."""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimensionality."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name/identifier of the embedding model."""
        pass

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Version of the embedding model."""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Generate embedding vector for a search query."""
        pass

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of text documents."""
        pass


class DeterministicEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic, zero-dependency, local mock embedding provider.

    Projects token, word, and character n-gram frequencies into a fixed-dimensional
    unit-normalized vector space using consistent hashing. Strictly designated as a
    non-semantic test/hash projection. Runs in microseconds on CPU with zero network downloads.
    """

    def __init__(self, dimensions: int = 384, model_name: str = "deterministic-v1", model_version: str = "1.0") -> None:
        self._dimensions = dimensions
        self._model_name = model_name
        self._model_version = model_version

    @property
    def provider_type(self) -> str:
        return "test_hash"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    def _hash_to_vector(self, text: str) -> np.ndarray:
        """Map text into a normalized dense vector via token and n-gram hash accumulation."""
        vec = np.zeros(self._dimensions, dtype=np.float32)
        if not text or not text.strip():
            return vec

        cleaned = text.lower().strip()
        words = cleaned.split()

        # 1. Word token hashing
        for word in words:
            # MD5 hash to 4 unsigned 32-bit integers
            digest = hashlib.md5(word.encode("utf-8")).digest()
            idx1 = int.from_bytes(digest[0:4], "little") % self._dimensions
            idx2 = int.from_bytes(digest[4:8], "little") % self._dimensions
            sign1 = 1.0 if digest[8] % 2 == 0 else -1.0
            sign2 = 1.0 if digest[9] % 2 == 0 else -1.0

            vec[idx1] += sign1 * 1.5
            vec[idx2] += sign2 * 1.0

        # 2. Character 3-gram hashing for subword semantics
        for i in range(len(cleaned) - 2):
            trigram = cleaned[i : i + 3]
            h = int(hashlib.md5(trigram.encode("utf-8")).hexdigest()[:6], 16)
            idx = h % self._dimensions
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            vec[idx] += sign * 0.3

        # L2 Normalize
        norm = np.linalg.norm(vec)
        if norm > 0.0:
            vec = vec / norm
        return vec

    def embed_query(self, text: str) -> list[float]:
        return self._hash_to_vector(text).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_to_vector(t).tolist() for t in texts]


class FastEmbedProvider(BaseEmbeddingProvider):
    """Local, CPU-optimized embedding provider using FastEmbed ONNX runtime."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", model_version: str = "1.0") -> None:
        self._model_name = model_name
        self._model_version = model_version
        self._dimensions = 384
        self._model = None

    def _ensure_model(self):
        """Lazy load the fastembed model on first call."""
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self._model_name)

    @property
    def provider_type(self) -> str:
        return "neural_semantic"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    def embed_query(self, text: str) -> list[float]:
        self._ensure_model()
        # FastEmbed returns a generator of numpy arrays
        embeddings = list(self._model.embed([text]))
        vec = embeddings[0]
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0.0:
            vec = vec / norm
        return vec.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model()
        embeddings = list(self._model.embed(texts))
        results = []
        for vec in embeddings:
            norm = np.linalg.norm(vec)
            if norm > 0.0:
                vec = vec / norm
            results.append(vec.tolist())
        return results


def get_embedding_provider(
    provider_name: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> BaseEmbeddingProvider:
    """Factory function to resolve configured embedding provider."""
    cfg = settings or get_settings()
    name = (provider_name or cfg.embedding_provider).lower()

    if name == "fastembed":
        try:
            return FastEmbedProvider(model_name=cfg.embedding_model)
        except Exception:
            # Graceful fallback to deterministic if fastembed fails to initialize
            return DeterministicEmbeddingProvider(dimensions=cfg.embedding_dimensions)

    return DeterministicEmbeddingProvider(dimensions=cfg.embedding_dimensions)
