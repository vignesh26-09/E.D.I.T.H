"""Integration tests for Phase B2 retrieval: Keyword (FTS5), Semantic (Vector), and Hybrid (RRF)."""

import pytest
from fastapi.testclient import TestClient
from edith_brain.core.contracts import RetrievalMode


@pytest.fixture
def setup_search_corpus(client: TestClient) -> dict:
    """Ingest three distinct documents into the test database via upload."""
    doc1_content = (
        b"Section 1: Database Write-Ahead Logging.\n"
        b"SQLite database lock handling in WAL mode allows multiple readers and a single writer concurrency.\n"
        b"Busy timeouts prevent database locking deadlocks during concurrent transactions.\n"
        b"Per-connection foreign key enforcement guarantees relational database integrity."
    )
    doc1 = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sqlite_wal.txt", doc1_content, "text/plain")},
        data={"title": "SQLite WAL Concurrency", "chunk_size": 150},
    ).json()

    doc2_content = (
        b"Section 1: System Structure.\n"
        b"The modular monolith architecture pattern separates domain services from storage layers.\n"
        b"API presentation routes must never execute raw SQL statements directly.\n"
        b"Repositories encapsulate SQLite tables and Pydantic schema contracts."
    )
    doc2 = client.post(
        "/api/v1/documents/upload",
        files={"file": ("architecture.txt", doc2_content, "text/plain")},
        data={"title": "Modular Monolith Architecture", "chunk_size": 150},
    ).json()

    doc3_content = (
        b"Section 1: REST Endpoints.\n"
        b"FastAPI web framework leverages asynchronous python coroutines and type annotations.\n"
        b"Dependency injection manages service lifecycles cleanly and reliably.\n"
        b"OpenAPI interactive documentation generates automatically at the /docs route."
    )
    doc3 = client.post(
        "/api/v1/documents/upload",
        files={"file": ("fastapi_guide.txt", doc3_content, "text/plain")},
        data={"title": "FastAPI Web Framework", "chunk_size": 150},
    ).json()

    # Ensure embeddings are generated
    client.post("/api/v1/retrieval/index-embeddings", json={"batch_size": 50})

    return {"doc1": doc1, "doc2": doc2, "doc3": doc3}


def test_keyword_search_bm25_and_snippets(client: TestClient, setup_search_corpus: dict):
    """Keyword search finds exact terms with FTS5 BM25 ranking and highlights."""
    res = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "concurrency",
            "mode": "keyword",
            "top_k": 5,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_results"] >= 1
    assert data["mode"] == "keyword"

    first_hit = data["results"][0]
    assert first_hit["document_id"] == setup_search_corpus["doc1"]["id"]
    assert "concurrency" in first_hit["chunk_text"].lower()
    assert "<mark>" in first_hit["highlights"]
    assert "</mark>" in first_hit["highlights"]


def test_keyword_search_with_document_filter(client: TestClient, setup_search_corpus: dict):
    """Filtering by document_id scopes keyword search strictly to that document."""
    doc2_id = setup_search_corpus["doc2"]["id"]
    res = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "sqlite",
            "mode": "keyword",
            "document_id": doc2_id,
            "top_k": 5,
        },
    )
    assert res.status_code == 200
    data = res.json()
    # All results must strictly belong to doc2
    for r in data["results"]:
        assert r["document_id"] == doc2_id


def test_keyword_search_no_matches(client: TestClient, setup_search_corpus: dict):
    """Searching for non-existent terms returns empty results cleanly."""
    res = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "nonexistentquantumcryptographyterm",
            "mode": "keyword",
        },
    )
    assert res.status_code == 200
    assert res.json()["total_results"] == 0


def test_semantic_search_cosine_similarity(client: TestClient, setup_search_corpus: dict):
    """Semantic search retrieves relevant chunks via vector dot product."""
    res = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "database lock handling and journal mode",
            "mode": "semantic",
            "top_k": 3,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_results"] >= 1
    assert data["mode"] == "semantic"

    # Best hit should be doc1 (SQLite WAL Concurrency)
    top_hit = data["results"][0]
    assert top_hit["document_id"] == setup_search_corpus["doc1"]["id"]
    assert top_hit["score"] > 0.0


def test_hybrid_search_rrf(client: TestClient, setup_search_corpus: dict):
    """Hybrid search merges keyword and semantic rankings using Reciprocal Rank Fusion."""
    res = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "modular monolith domain services",
            "mode": "hybrid",
            "top_k": 3,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_results"] >= 1
    assert data["mode"] == "hybrid"

    top_hit = data["results"][0]
    assert top_hit["document_id"] == setup_search_corpus["doc2"]["id"]
    assert "monolith" in top_hit["chunk_text"].lower()
    assert top_hit["score"] > 0.0


def test_convenience_get_search_endpoint(client: TestClient, setup_search_corpus: dict):
    """GET /api/v1/retrieval/search endpoint functions identically."""
    res = client.get("/api/v1/retrieval/search?q=coroutines&mode=keyword")
    assert res.status_code == 200
    data = res.json()
    assert data["total_results"] >= 1
    assert data["results"][0]["document_id"] == setup_search_corpus["doc3"]["id"]


def test_retrieval_stats_and_index_metrics(client: TestClient, setup_search_corpus: dict):
    """GET /api/v1/retrieval/stats returns index and embedding counts."""
    res = client.get("/api/v1/retrieval/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["total_documents"] >= 3
    assert data["total_chunks"] >= 3
    assert data["fts5_indexed_chunks"] >= 3
    assert data["embedded_chunks"] >= 3
    assert data["embedding_dimensions"] == 384
