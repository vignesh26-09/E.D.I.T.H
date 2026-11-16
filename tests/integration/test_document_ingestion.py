"""Integration tests for document ingestion, multi-format upload, status, and cleanup."""

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import docx

from edith_brain.core.contracts import IngestionStatus
from edith_brain.services.document_service import DocumentService
from edith_brain.storage.db import SQLiteEngine


def test_upload_plain_text_document(client: TestClient):
    """Upload plain text file via multipart form."""
    content = b"This is line 1.\nThis is line 2.\n\nParagraph 2."
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("guide.txt", content, "text/plain")},
        data={"title": "Test Guide", "strategy": "structure_aware", "chunk_size": 200},
    )
    assert response.status_code == 201
    doc = response.json()
    assert doc["title"] == "Test Guide"
    assert doc["original_filename"] == "guide.txt"
    assert doc["file_extension"] == ".txt"
    assert doc["ingestion_status"] == "processed"
    assert doc["chunk_count"] >= 1
    doc_id = doc["id"]

    # Verify chunks
    chunks_res = client.get(f"/api/v1/documents/{doc_id}/chunks")
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()
    assert len(chunks) == doc["chunk_count"]
    assert "This is line 1." in chunks[0]["chunk_text"]


def test_upload_markdown_document(client: TestClient):
    """Upload Markdown document and verify heading sections in chunk provenance."""
    md_content = b"""# Main Architecture
System overview content here.

## Storage Subsystem
SQLite in WAL mode with busy timeout.
"""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("architecture.md", md_content, "text/markdown")},
        data={"strategy": "structure_aware", "chunk_size": 100},
    )
    assert response.status_code == 201
    doc = response.json()
    assert doc["title"] == "architecture"
    assert doc["file_extension"] == ".md"

    # Inspect chunks for section provenance
    chunks_res = client.get(f"/api/v1/documents/{doc['id']}/chunks")
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()
    assert any(c["section"] is not None for c in chunks)


def test_upload_pdf_document(client: TestClient):
    """Upload PDF file and verify page provenance in chunks."""
    pdf_bytes = b"""%PDF-1.4
1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj
2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj
3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>> endobj
4 0 obj <</Length 50>> stream
BT
/F1 12 Tf
72 712 Td
(E.D.I.T.H. Brain Core PDF Spec) Tj
ET
endstream endobj
5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000344 00000 n 
trailer <</Size 6 /Root 1 0 R>>
startxref
423
%%EOF"""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("brain_spec.pdf", pdf_bytes, "application/pdf")},
        data={"title": "PDF Spec"},
    )
    assert response.status_code == 201
    doc = response.json()
    assert doc["original_filename"] == "brain_spec.pdf"
    assert doc["file_extension"] == ".pdf"
    assert doc["chunk_count"] >= 1

    chunks_res = client.get(f"/api/v1/documents/{doc['id']}/chunks")
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()
    assert chunks[0]["page_number"] == 1
    assert "PDF Spec" in chunks[0]["chunk_text"]


def test_upload_docx_document(client: TestClient):
    """Upload DOCX file and verify table and paragraph extraction."""
    d = docx.Document()
    d.add_heading("E.D.I.T.H. Core Features", level=1)
    d.add_paragraph("Feature list follows below:")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Feature 1"
    t.cell(0, 1).text = "Document Ingestion"

    buf = io.BytesIO()
    d.save(buf)
    docx_bytes = buf.getvalue()

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("features.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"title": "Features Spec"},
    )
    assert response.status_code == 201
    doc = response.json()
    assert doc["original_filename"] == "features.docx"
    assert doc["chunk_count"] >= 1

    chunks_res = client.get(f"/api/v1/documents/{doc['id']}/chunks")
    chunks = chunks_res.json()
    all_chunk_text = " ".join(c["chunk_text"] for c in chunks)
    assert "Feature 1" in all_chunk_text


def test_upload_duplicate_document_conflict(client: TestClient):
    """Uploading the exact same content twice raises 409 Conflict."""
    content = b"Unique content for duplicate test: 9876543210."
    res1 = client.post(
        "/api/v1/documents/upload",
        files={"file": ("orig.txt", content, "text/plain")},
    )
    assert res1.status_code == 201

    res2 = client.post(
        "/api/v1/documents/upload",
        files={"file": ("duplicate.txt", content, "text/plain")},
    )
    assert res2.status_code == 409
    assert "identical content hash already exists" in res2.json()["detail"]


def test_upload_corrupted_file_validation_error(client: TestClient):
    """Uploading corrupted DOCX or invalid file returns 422 Unprocessable Entity."""
    corrupted_docx = b"PK\x03\x04 fake corrupted zip header without valid structure"
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("corrupt.docx", corrupted_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert response.status_code == 422
    assert "Invalid or corrupted DOCX" in response.json()["detail"]


def test_document_status_endpoint(client: TestClient):
    """GET /api/v1/documents/{id}/status reports accurate status and metadata."""
    content = b"Content for status inspection."
    res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("status_test.txt", content, "text/plain")},
    )
    doc_id = res.json()["id"]

    status_res = client.get(f"/api/v1/documents/{doc_id}/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["id"] == doc_id
    assert status_data["ingestion_status"] == "processed"
    assert status_data["chunk_count"] >= 1
    assert len(status_data["content_hash"]) == 64


def test_document_deletion_cascades_and_cleans_files(client: TestClient):
    """DELETE /api/v1/documents/{id} deletes DB records and physically removes storage files."""
    content = b"Content to be deleted cleanly."
    create_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("delete_me.txt", content, "text/plain")},
    )
    doc_data = create_res.json()
    doc_id = doc_data["id"]
    raw_path = Path(doc_data["raw_storage_path"])
    extracted_path = Path(doc_data["extracted_storage_path"])

    assert raw_path.exists()
    assert extracted_path.exists()

    # Delete document
    del_res = client.delete(f"/api/v1/documents/{doc_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # Check database: document and chunks no longer exist
    get_res = client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 404

    chunks_res = client.get(f"/api/v1/documents/{doc_id}/chunks")
    assert chunks_res.status_code == 404

    # Check filesystem: files physically deleted
    assert not raw_path.exists()
    assert not extracted_path.exists()


def test_failed_ingestion_cleans_up_filesystem_rollback(
    document_service: DocumentService,
    test_engine: SQLiteEngine,
):
    """If parsing or chunking throws during ingestion, no orphaned files remain on disk."""
    corrupted_data = b"Corrupted header data"

    # Attempt ingestion directly on service with invalid extension
    with pytest.raises(Exception):
        document_service.ingest_binary_document(
            filename="corrupt.docx",
            raw_bytes=corrupted_data,
        )

    # Check that raw storage has no leftover files matching this content hash
    from edith_brain.core.security import compute_sha256
    c_hash = compute_sha256(corrupted_data)
    leftovers = list(document_service.settings.storage_raw_dir.glob(f"{c_hash}*"))
    assert len(leftovers) == 0
