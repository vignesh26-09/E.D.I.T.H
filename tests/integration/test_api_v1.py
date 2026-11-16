"""Integration tests for API v1 routes."""

from fastapi.testclient import TestClient


def test_api_health_endpoint(client: TestClient):
    """GET /api/v1/health returns healthy status with WAL mode and foreign keys enabled."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["db_connected"] is True
    assert data["wal_mode"] is True
    assert data["foreign_keys_on"] is True


def test_api_system_info_endpoint(client: TestClient):
    """GET /api/v1/system/info returns capabilities."""
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "personal" in data["supported_memory_categories"]
    assert "profile_fact" in data["supported_personal_subcategories"]
    assert data["fts5_supported"] is True


def test_api_memory_lifecycle(client: TestClient):
    """Test full memory lifecycle via HTTP API."""
    # 1. Create memory
    create_payload = {
        "category": "personal",
        "subcategory": "goal",
        "content": "Master system programming in 2026.",
        "confidence": 0.9,
        "tags": ["career", "engineering"],
    }
    create_res = client.post("/api/v1/memories", json=create_payload)
    assert create_res.status_code == 201
    mem_data = create_res.json()
    memory_id = mem_data["id"]
    assert mem_data["content"] == create_payload["content"]

    # 2. Correct memory
    correct_payload = {
        "new_content": "Master distributed systems and AI systems in 2026.",
        "confidence": 1.0,
        "reason": "Expanded scope to include AI systems.",
    }
    correct_res = client.post(f"/api/v1/memories/{memory_id}/correct", json=correct_payload)
    assert correct_res.status_code == 200
    corrected_data = correct_res.json()
    new_memory_id = corrected_data["id"]
    assert corrected_data["parent_memory_id"] == memory_id

    # 3. Revoke original memory (already superseded, but verify revoking corrected memory)
    revoke_payload = {"reason": "Goal achieved early."}
    revoke_res = client.post(f"/api/v1/memories/{new_memory_id}/revoke", json=revoke_payload)
    assert revoke_res.status_code == 200
    assert revoke_res.json()["status"] == "revoked"

    # 4. Check audit log
    audit_res = client.get(f"/api/v1/memories/{new_memory_id}/audit")
    assert audit_res.status_code == 200
    audit_trail = audit_res.json()
    assert len(audit_trail) >= 2

    # 5. Purge memory
    purge_payload = {"reason": "Permanent user purge request", "confirm_permanent_loss": True}
    purge_res = client.request("DELETE", f"/api/v1/memories/{new_memory_id}/purge", json=purge_payload)
    assert purge_res.status_code == 200
    assert purge_res.json()["purged"] is True


def test_api_document_and_chunk_provenance(client: TestClient):
    """Test document ingestion and chunk provenance via HTTP API."""
    doc_payload = {
        "title": "Core Architecture Spec",
        "raw_content": "Section 1: Monolith design. Section 2: Concurrency model.",
        "source_type": "manual_text",
        "metadata": {"author": "Architect"},
    }
    doc_res = client.post("/api/v1/documents", json=doc_payload)
    assert doc_res.status_code == 201
    doc_data = doc_res.json()
    doc_id = doc_data["id"]
    assert doc_data["title"] == doc_payload["title"]

    # Duplicate ingestion fails with 409 Conflict
    dup_res = client.post("/api/v1/documents", json=doc_payload)
    assert dup_res.status_code == 409

    # Add chunk with full provenance
    chunk_payload = {
        "chunk_index": 0,
        "chunk_text": "Section 1: Monolith design.",
        "page_number": 1,
        "section": "Section 1",
        "source_location": "characters 0-27",
        "extraction_method": "text_plain_v1",
    }
    chunk_res = client.post(f"/api/v1/documents/{doc_id}/chunks", json=chunk_payload)
    assert chunk_res.status_code == 201
    chunk_data = chunk_res.json()
    assert chunk_data["document_id"] == doc_id
    assert chunk_data["section"] == "Section 1"
    assert len(chunk_data["content_hash"]) == 64

    # Retrieve chunks
    list_chunks_res = client.get(f"/api/v1/documents/{doc_id}/chunks")
    assert list_chunks_res.status_code == 200
    chunks = list_chunks_res.json()
    assert len(chunks) == 1
    assert chunks[0]["chunk_text"] == "Section 1: Monolith design."
