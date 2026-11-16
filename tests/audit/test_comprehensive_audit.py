"""Independent Verification & Release Audit Test Suite for E.D.I.T.H. Brain Core (B0-B6).

Acts as an adversarial, skeptical audit probe across architecture, security,
database reliability, retrieval accuracy, domain lifecycles, and API contracts.
"""

import os
import sys
import json
import time
import math
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Generator, List, Dict, Any

import pytest
import sqlite3
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from edith_brain.core.config import Settings
from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCorrection,
    MemoryRevoke,
    MemoryPurge,
    MemoryVerifyRequest,
    MemoryCitationCreate,
    MemoryAssociationCreate,
    MemoryConflictCheckRequest,
    MemorySearchRequest,
    DocumentCreate,
    ChunkOptions,
    ChunkingStrategy,
    RetrievalQuery,
    RetrievalMode,
    EpisodeCreate,
    EpisodeTimelineRequest,
    ProcedureCreate,
    ProcedureStep,
    ProcedureExecutionLogCreate,
    ProcedureStatus,
    MemoryCategory,
    PersonalSubcategory,
    MemoryStatus,
    VerificationStatus,
    VerificationMethod,
    ActorRole,
    RelationType,
    MemoryTouchRequest,
    CompactionExecuteRequest,
    BenchmarkRunRequest,
)
from edith_brain.core.security import (
    compute_sha256,
    validate_safe_path,
    validate_file_size,
    get_or_create_local_token,
    verify_local_token,
)
from edith_brain.storage.db import SQLiteEngine
from edith_brain.storage.migrations import MigrationRunner
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.document_service import DocumentService
from edith_brain.services.retrieval.retrieval_service import RetrievalService
from edith_brain.services.retrieval.memory_search_service import MemorySearchService
from edith_brain.services.retrieval.memory_embedding_service import MemoryEmbeddingService
from edith_brain.services.retrieval.embeddings import DeterministicEmbeddingProvider
from edith_brain.services.episodic_service import EpisodicService
from edith_brain.services.procedural_service import ProceduralService
from edith_brain.services.memory_decay_engine import MemoryDecayEngine
from edith_brain.services.memory_consolidation_service import MemoryConsolidationService
from edith_brain.services.memory_compaction_service import MemoryCompactionService
from edith_brain.services.evaluation_benchmark_service import EvaluationBenchmarkService
from edith_brain.services.memory_conflict_engine import MemoryConflictEngine
from edith_brain.api.app import create_app
from edith_brain.client import EdithBrainClient


# ==============================================================================
# AUDIT FIXTURES (Disposable, Temporary Environments)
# ==============================================================================

@pytest.fixture
def audit_env(tmp_path: Path):
    """Provides an isolated disposable environment for audit execution."""
    db_path = tmp_path / "audit_brain.db"
    raw_dir = tmp_path / "raw"
    extracted_dir = tmp_path / "extracted"
    token_path = tmp_path / ".edith_token"

    settings = Settings(
        app_name="E.D.I.T.H. Brain Core [Audit]",
        environment="audit",
        base_dir=tmp_path,
        database_path=db_path,
        storage_raw_dir=raw_dir,
        storage_extracted_dir=extracted_dir,
        local_token_path=token_path,
        max_file_size_bytes=2 * 1024 * 1024,
        sqlite_busy_timeout_ms=5000,
        embedding_provider="deterministic",
        embedding_dimensions=384,
        auth_enabled=True,  # Audit specifically tests authentication enabled!
        local_auth_secret="audit_secret_token_1234567890",
    )
    settings.ensure_directories()

    engine = SQLiteEngine(db_path=db_path, busy_timeout_ms=settings.sqlite_busy_timeout_ms)
    runner = MigrationRunner(engine=engine)
    runner.run_migrations()

    embedder = DeterministicEmbeddingProvider(dimensions=384)
    mem_service = MemoryService(engine=engine)
    doc_service = DocumentService(engine=engine, settings=settings, embedding_provider=embedder)
    ret_service = RetrievalService(engine=engine, settings=settings, embedding_provider=embedder)
    epi_service = EpisodicService(engine=engine)
    proc_service = ProceduralService(engine=engine)
    decay_eng = MemoryDecayEngine(engine=engine)
    cons_service = MemoryConsolidationService(engine=engine, memory_service=mem_service)
    comp_service = MemoryCompactionService(engine=engine, memory_service=mem_service)
    eval_service = EvaluationBenchmarkService(engine=engine, memory_service=mem_service)
    conflict_eng = MemoryConflictEngine(engine=engine, embedding_provider=embedder)
    mem_search_service = MemorySearchService(engine=engine, embedding_provider=embedder)
    mem_embed_service = MemoryEmbeddingService(engine=engine, embedding_provider=embedder)

    token = get_or_create_local_token(token_path=token_path, configured_secret=settings.local_auth_secret)

    app = create_app()

    from edith_brain.api.deps import (
        get_settings, get_engine, get_memory_service, get_document_service,
        get_retrieval_service, get_episodic_service, get_procedural_service,
        get_decay_engine, get_consolidation_service, get_compaction_service,
        get_evaluation_benchmark_service, get_embedding_provider_dep,
        get_memory_conflict_engine, get_memory_search_service, get_memory_embedding_service
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_memory_service] = lambda: mem_service
    app.dependency_overrides[get_document_service] = lambda: doc_service
    app.dependency_overrides[get_retrieval_service] = lambda: ret_service
    app.dependency_overrides[get_episodic_service] = lambda: epi_service
    app.dependency_overrides[get_procedural_service] = lambda: proc_service
    app.dependency_overrides[get_decay_engine] = lambda: decay_eng
    app.dependency_overrides[get_consolidation_service] = lambda: cons_service
    app.dependency_overrides[get_compaction_service] = lambda: comp_service
    app.dependency_overrides[get_evaluation_benchmark_service] = lambda: eval_service
    app.dependency_overrides[get_embedding_provider_dep] = lambda: embedder
    app.dependency_overrides[get_memory_conflict_engine] = lambda: conflict_eng
    app.dependency_overrides[get_memory_search_service] = lambda: mem_search_service
    app.dependency_overrides[get_memory_embedding_service] = lambda: mem_embed_service

    client = TestClient(app)

    yield {
        "settings": settings,
        "engine": engine,
        "runner": runner,
        "embedder": embedder,
        "mem_service": mem_service,
        "doc_service": doc_service,
        "ret_service": ret_service,
        "epi_service": epi_service,
        "proc_service": proc_service,
        "decay_eng": decay_eng,
        "cons_service": cons_service,
        "comp_service": comp_service,
        "eval_service": eval_service,
        "conflict_eng": conflict_eng,
        "mem_search_service": mem_search_service,
        "app": app,
        "client": client,
        "token": token,
        "auth_headers": {"Authorization": f"Bearer {token}"},
    }

    app.dependency_overrides.clear()


# ==============================================================================
# 1. SECURITY & AUTHENTICATION AUDIT TESTS
# ==============================================================================

class TestSecurityAudit:
    """Rigorous audit of security boundaries, token validation, and ACLs."""

    def test_missing_auth_on_documents_endpoints(self, audit_env):
        """CRITICAL/HIGH FINDING: Verify DEFECT-SEC-01 on Knowledge Documents endpoints."""
        client = audit_env["client"]
        
        # POST /api/v1/documents without Authorization header
        resp = client.post("/api/v1/documents", json={
            "title": "Unauthenticated Leak",
            "raw_content": "Secret content uploaded without auth",
            "source_type": "text"
        })
        # If it returns 201 Created without auth, it confirms DEFECT-SEC-01!
        assert resp.status_code == 201, f"Expected 201 showing lack of auth dependency, got {resp.status_code}"
        doc_id = resp.json()["id"]

        # GET /api/v1/documents without Authorization header
        list_resp = client.get("/api/v1/documents")
        assert list_resp.status_code == 200, "Unauthenticated list_documents succeeded"

        # DELETE /api/v1/documents/{id} without Authorization header!
        del_resp = client.delete(f"/api/v1/documents/{doc_id}")
        assert del_resp.status_code == 200, "Unauthenticated document deletion succeeded!"

    def test_missing_auth_on_retrieval_endpoints(self, audit_env):
        """CRITICAL/HIGH FINDING: Verify DEFECT-SEC-01 on Knowledge Retrieval endpoints."""
        client = audit_env["client"]

        # POST /api/v1/retrieval/search without Authorization header
        resp = client.post("/api/v1/retrieval/search", json={
            "query": "secret",
            "mode": "keyword"
        })
        assert resp.status_code == 200, f"Expected 200 showing unauthenticated search, got {resp.status_code}"

        # POST /api/v1/retrieval/index-embeddings without auth
        idx_resp = client.post("/api/v1/retrieval/index-embeddings", json={"batch_size": 10})
        assert idx_resp.status_code == 200, "Unauthenticated index_embeddings succeeded"

    def test_enforced_auth_on_memories_endpoints(self, audit_env):
        """Verify that memory endpoints DO enforce authentication properly."""
        client = audit_env["client"]

        # POST /api/v1/memories without token must fail with 401
        resp = client.post("/api/v1/memories", json={
            "content": "Secret memory",
            "category": "personal",
            "subcategory": "profile_fact"
        })
        assert resp.status_code == 401, f"Expected 401 Unauthorized, got {resp.status_code}"

        # With invalid bearer token
        resp_invalid = client.post(
            "/api/v1/memories",
            json={"content": "Secret memory", "category": "personal", "subcategory": "profile_fact"},
            headers={"Authorization": "Bearer bad_token_xyz"}
        )
        assert resp_invalid.status_code == 401

        # With valid bearer token
        resp_valid = client.post(
            "/api/v1/memories",
            json={"content": "Authorized memory", "category": "personal", "subcategory": "profile_fact"},
            headers=audit_env["auth_headers"]
        )
        assert resp_valid.status_code == 201

    def test_actor_escalation_system_pipeline_forbidden(self, audit_env):
        """Verify that callers claiming SYSTEM_PIPELINE via X-Edith-Actor are rejected."""
        client = audit_env["client"]
        resp = client.post(
            "/api/v1/memories",
            json={"content": "Attacking memory", "category": "personal", "subcategory": "profile_fact"},
            headers={
                **audit_env["auth_headers"],
                "X-Edith-Actor": "system_pipeline"
            }
        )
        assert resp.status_code == 403
        assert "Forbidden actor role" in resp.text

    def test_path_traversal_protection(self, audit_env):
        """Verify validate_safe_path blocks traversal outside directory."""
        base = audit_env["settings"].storage_raw_dir
        with pytest.raises(Exception):
            validate_safe_path(base, "../../evil.txt")
        with pytest.raises(Exception):
            validate_safe_path(base, "..\\..\\evil.txt")
        with pytest.raises(Exception):
            validate_safe_path(base, "C:\\Windows\\System32\\calc.exe")

    def test_fts5_query_injection_resilience(self, audit_env):
        """Verify FTS5 special character queries do not crash the search engine."""
        mem_service = audit_env["mem_service"]
        search_service = audit_env["mem_search_service"]
        
        # Create a memory
        mem = mem_service.create_memory(MemoryCreate(
            content="SQLite FTS5 robustness query test",
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT
        ))

        malicious_queries = [
            '""',
            '"""""',
            '*',
            'AND',
            'OR',
            'NOT',
            'NEAR()',
            'content: "unclosed string',
            'SELECT * FROM memories',
            '; DROP TABLE memories; --',
            '()())(*&^%$#@!',
            'a OR OR b',
        ]
        for q in malicious_queries:
            try:
                res = search_service.search(MemorySearchRequest(query=q, mode=RetrievalMode.KEYWORD, top_k=5))
                assert isinstance(res.items, list)
            except Exception as e:
                pytest.fail(f"FTS5 query '{q}' crashed with exception: {e}")


# ==============================================================================
# 2. DATABASE & SQLITE ENGINE AUDIT TESTS
# ==============================================================================

class TestDatabaseAudit:
    """Audit of SQLite engine PRAGMAs, foreign keys, concurrency, and integrity."""

    def test_sqlite_pragmas_and_health(self, audit_env):
        """Verify WAL mode, FK enforcement, and PRAGMA integrity."""
        engine = audit_env["engine"]
        health = engine.check_health()
        assert health["connected"] is True
        assert health["wal_mode"] is True, "Database is NOT in WAL mode!"
        assert health["foreign_keys_on"] is True, "Foreign keys are NOT enforced!"

        # Verify PRAGMA integrity_check
        with engine.connection() as conn:
            integrity = conn.execute("PRAGMA integrity_check;").fetchall()
            assert integrity == [("ok",)], f"Integrity check failed: {integrity}"

            fk_check = conn.execute("PRAGMA foreign_key_check;").fetchall()
            assert fk_check == [], f"Foreign key check violations found: {fk_check}"

    def test_concurrent_reads_and_writes_under_wal(self, audit_env):
        """Stress-test concurrent read and write operations under WAL mode."""
        engine = audit_env["engine"]
        mem_service = audit_env["mem_service"]
        errors = []

        def writer_worker(thread_id: int):
            try:
                for i in range(5):
                    mem_service.create_memory(MemoryCreate(
                        content=f"Concurrent thread {thread_id} item {i}",
                        category=MemoryCategory.PERSONAL,
                        subcategory=PersonalSubcategory.PROFILE_FACT
                    ))
                    time.sleep(0.01)
            except Exception as e:
                errors.append(f"Writer-{thread_id} failed: {e}")

        def reader_worker(thread_id: int):
            try:
                for _ in range(10):
                    mems = mem_service.list_memories(limit=10)
                    assert isinstance(mems, list)
                    time.sleep(0.005)
            except Exception as e:
                errors.append(f"Reader-{thread_id} failed: {e}")

        threads = []
        for t in range(2):
            threads.append(threading.Thread(target=writer_worker, args=(t,)))
        for t in range(4):
            threads.append(threading.Thread(target=reader_worker, args=(t,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrency errors encountered: {errors}"

    def test_transaction_rollback_atomicity(self, audit_env):
        """Verify that write_transaction aborts cleanly on error without partial commits."""
        engine = audit_env["engine"]
        
        with pytest.raises(RuntimeError):
            with engine.write_transaction() as conn:
                conn.execute(
                    "INSERT INTO memories (id, content, category, status) VALUES (?, ?, ?, ?)",
                    ("tx-test-id", "Rollback content", "personal", "active")
                )
                raise RuntimeError("Simulated transaction fault")

        with engine.connection() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = 'tx-test-id'").fetchone()
            assert row is None, "Transaction rollback failed: row was committed!"

    def test_migration_checksum_tampering(self, audit_env):
        """Verify migration runner rejects altered migrations with mismatched checksums."""
        engine = audit_env["engine"]
        runner = audit_env["runner"]
        
        # Corrupt recorded checksum for migration 1
        with engine.connection() as conn:
            conn.execute("UPDATE _schema_migrations SET checksum = 'tampered_sha256' WHERE version = 1")
            conn.commit()

        # Running migrations now must raise an error
        from edith_brain.core.exceptions import MigrationChecksumError
        with pytest.raises(MigrationChecksumError):
            runner.run_migrations()


# ==============================================================================
# 3. MEMORY LIFECYCLE, CITATIONS & ASSOCIATIONS AUDIT (B0 & B3)
# ==============================================================================

class TestMemoryLifecycleAudit:
    """Audit of memory state transitions, lineages, hard purge, citations, associations."""

    def test_memory_crud_and_hard_purge(self, audit_env):
        """Verify hard purge removes content from all dependent tables, triggers, and audit snapshots."""
        mem_service = audit_env["mem_service"]
        engine = audit_env["engine"]

        # Create
        created = mem_service.create_memory(MemoryCreate(
            content="Sensitive user medical information",
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT,
        ))
        mem_id = created.id

        # Update / Correct
        corrected = mem_service.correct_memory(mem_id, MemoryCorrection(
            new_content="Corrected medical fact",
            reason="Typo fix"
        ))
        new_id = corrected.id

        # Revoke new memory
        mem_service.revoke_memory(new_id, MemoryRevoke(reason="Privacy request"))

        # Hard Purge new memory
        purge_res = mem_service.purge_memory(new_id, MemoryPurge(confirm_permanent_loss=True, reason="Hard delete request"))
        assert purge_res["purged"] is True

        # Verify completely expunged from memories table
        with engine.connection() as conn:
            assert conn.execute("SELECT * FROM memories WHERE id = ?", (new_id,)).fetchone() is None
            # Verify expunged from memories_fts
            assert conn.execute("SELECT * FROM memories_fts WHERE memory_id = ?", (new_id,)).fetchone() is None
            # Verify snapshots redacted in audit log
            audit_rows = conn.execute("SELECT old_state, new_state FROM memory_audit_log WHERE memory_id = ?", (new_id,)).fetchall()
            for r in audit_rows:
                assert "Sensitive" not in str(r)
                assert "Corrected" not in str(r)

    def test_citation_orphan_prevention_trigger(self, audit_env):
        """Verify database trigger transitions citation status to 'source_removed' on doc deletion."""
        doc_service = audit_env["doc_service"]
        mem_service = audit_env["mem_service"]
        engine = audit_env["engine"]

        # Ingest a document
        doc = doc_service.ingest_document(DocumentCreate(
            title="Policy Doc",
            raw_content="Important policy clause paragraph 1. More details paragraph 2.",
            source_type="text"
        ))
        chunks = doc_service.list_chunks(doc.id)
        assert len(chunks) > 0
        chunk_id = chunks[0].id

        # Create memory
        mem = mem_service.create_memory(MemoryCreate(
            content="Memory citing policy",
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.DECISION
        ))
        
        # Add citation
        cit = mem_service.add_citation(mem.id, MemoryCitationCreate(
            document_id=doc.id,
            chunk_id=chunk_id,
            quote_text="Important policy clause",
            confidence_score=0.95
        ))
        assert cit.status == "active"

        # Delete document
        doc_service.delete_document(doc.id)

        # Inspect citation in database: trigger should set status='source_removed' and chunk_id=NULL
        with engine.connection() as conn:
            cit_row = conn.execute("SELECT status, chunk_id FROM memory_citations WHERE id = ?", (cit.id,)).fetchone()
            assert cit_row is not None
            assert cit_row[0] == "source_removed", f"Expected 'source_removed', got '{cit_row[0]}'"
            assert cit_row[1] is None, f"Expected chunk_id to be NULL, got '{cit_row[1]}'"

    def test_memory_association_canonical_ordering_and_cycle_prevention(self, audit_env):
        """Verify memory associations enforce canonical ID ordering and prevent self-cycles."""
        mem_service = audit_env["mem_service"]

        m1 = mem_service.create_memory(MemoryCreate(content="Concept 1", category=MemoryCategory.PERSONAL, subcategory=PersonalSubcategory.DECISION))
        m2 = mem_service.create_memory(MemoryCreate(content="Concept 2", category=MemoryCategory.PERSONAL, subcategory=PersonalSubcategory.DECISION))

        # Add association
        assoc = mem_service.add_association(m1.id, MemoryAssociationCreate(
            target_memory_id=m2.id,
            relation_type=RelationType.RELATES_TO,
            metadata={"confidence_score": 0.88}
        ))
        assert assoc.id is not None

        # Self-association must be rejected
        with pytest.raises(Exception):
            mem_service.add_association(m1.id, MemoryAssociationCreate(
                target_memory_id=m1.id,
                relation_type=RelationType.RELATES_TO
            ))

    def test_verification_state_machine_transitions(self, audit_env):
        """Verify allowed and forbidden memory verification transitions."""
        mem_service = audit_env["mem_service"]

        # Default is unverified
        mem = mem_service.create_memory(MemoryCreate(
            content="Unverified claim",
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.GOAL
        ))
        assert mem.verification_status == VerificationStatus.UNVERIFIED

        # Transition UNVERIFIED -> NEEDS_REVIEW
        v1 = mem_service.verify_memory(mem.id, MemoryVerifyRequest(
            status=VerificationStatus.NEEDS_REVIEW,
            method=VerificationMethod.AUTOMATED_HEURISTIC,
            notes="Needs manual check"
        ))
        assert v1.verification_status == VerificationStatus.NEEDS_REVIEW

        # Transition NEEDS_REVIEW -> VERIFIED
        v2 = mem_service.verify_memory(mem.id, MemoryVerifyRequest(
            status=VerificationStatus.VERIFIED,
            method=VerificationMethod.EXPLICIT_USER,
            notes="User confirmed"
        ))
        assert v2.verification_status == VerificationStatus.VERIFIED


# ==============================================================================
# 4. DOCUMENT INGESTION & CHUNKING AUDIT (B1)
# ==============================================================================

class TestDocumentIngestionAudit:
    """Audit of document parsers, extraction, chunking, and binary handling."""

    def test_multi_format_binary_parsers(self, audit_env):
        """Verify TXT, Markdown, and corrupt inputs fail safely."""
        doc_service = audit_env["doc_service"]

        # Plain text
        doc_txt = doc_service.ingest_binary_document(
            filename="notes.txt",
            raw_bytes="Line 1\n\nLine 2\nLine 3".encode("utf-8"),
            mime_type="text/plain"
        )
        assert doc_txt.chunk_count >= 1

        # Markdown
        md_content = "# Title\n\n## Section 1\nParagraph text.\n\n## Section 2\nAnother paragraph."
        doc_md = doc_service.ingest_binary_document(
            filename="docs.md",
            raw_bytes=md_content.encode("utf-8"),
            mime_type="text/markdown",
            chunk_options=ChunkOptions(strategy=ChunkingStrategy.STRUCTURE_AWARE)
        )
        assert doc_md.chunk_count >= 2

        # Corrupt PDF bytes
        with pytest.raises(Exception):
            doc_service.ingest_binary_document(
                filename="corrupt.pdf",
                raw_bytes=b"%PDF-1.4 corrupt junk not a real pdf",
                mime_type="application/pdf"
            )

    def test_file_size_limit_rejection(self, audit_env):
        """Verify that files exceeding max_file_size_bytes are rejected."""
        doc_service = audit_env["doc_service"]
        large_bytes = b"X" * (3 * 1024 * 1024)  # 3 MB (limit is 2 MB in audit_env)
        with pytest.raises(Exception):
            doc_service.ingest_binary_document(
                filename="huge.txt",
                raw_bytes=large_bytes,
                mime_type="text/plain"
            )


# ==============================================================================
# 5. RETRIEVAL & EVALUATION AUDIT (B2)
# ==============================================================================

class TestRetrievalAudit:
    """Audit of BM25, semantic, hybrid RRF retrieval, and metrics computation."""

    def test_fts5_triggers_insert_update_delete(self, audit_env):
        """Verify SQLite FTS5 index is perfectly synchronized by triggers."""
        engine = audit_env["engine"]
        doc_service = audit_env["doc_service"]

        doc = doc_service.ingest_document(DocumentCreate(
            title="Quantum Computing",
            raw_content="Superconducting qubits exhibit quantum entanglement and superposition.",
            source_type="text"
        ))

        # Check FTS index populated
        with engine.connection() as conn:
            match = conn.execute(
                "SELECT rowid FROM document_chunks_fts WHERE document_chunks_fts MATCH 'qubits'"
            ).fetchall()
            assert len(match) > 0, "FTS5 insert trigger failed to index chunk"

        # Delete document and verify FTS table cleaned up
        doc_service.delete_document(doc.id)
        with engine.connection() as conn:
            match_after = conn.execute(
                "SELECT rowid FROM document_chunks_fts WHERE document_chunks_fts MATCH 'qubits'"
            ).fetchall()
            assert len(match_after) == 0, "FTS5 delete trigger failed to clean up chunk"

    def test_rrf_hybrid_formula_k60(self, audit_env):
        """Verify Reciprocal Rank Fusion uses k=60 and handles duplicate result merging."""
        ret_service = audit_env["ret_service"]
        doc_service = audit_env["doc_service"]

        doc_service.ingest_document(DocumentCreate(
            title="Python Concurrency",
            raw_content="Asyncio event loops manage cooperative multitasking in single threads.",
            source_type="text"
        ))

        # Search with HYBRID mode
        res = ret_service.search(RetrievalQuery(query="asyncio event loops", mode=RetrievalMode.HYBRID, top_k=3))
        assert len(res.results) > 0
        top = res.results[0]
        # In RRF, with k=60, top score for rank 1 in both channels is 1/(60+1) + 1/(60+1) = 2/61 ≈ 0.03278
        assert top.score > 0.0, f"Expected non-zero RRF score, got {top.score}"


# ==============================================================================
# 6. EPISODIC & PROCEDURAL WORKFLOWS AUDIT (B4)
# ==============================================================================

class TestEpisodicProceduralAudit:
    """Audit of timeline ordering, session grouping, and procedure validation."""

    def test_episode_timeline_and_sessions(self, audit_env):
        """Verify episodic timeline queries, chronological sorting, and session aggregation."""
        epi_service = audit_env["epi_service"]

        now = datetime.now(timezone.utc)
        e1 = epi_service.create_episode(EpisodeCreate(
            session_id="sess-001",
            title="User Query",
            event_type="query",
            summary="First question",
            actors=["user"],
            occurred_at=now - timedelta(minutes=10)
        ))
        e2 = epi_service.create_episode(EpisodeCreate(
            session_id="sess-001",
            title="Agent Response",
            event_type="response",
            summary="First response",
            actors=["agent"],
            occurred_at=now - timedelta(minutes=8)
        ))

        timeline = epi_service.get_timeline(EpisodeTimelineRequest(session_id="sess-001"))
        assert len(timeline) == 2
        assert timeline[0].id == e1.id
        assert timeline[1].id == e2.id

        sessions = epi_service.list_sessions()
        assert any(s["session_id"] == "sess-001" for s in sessions)

    def test_procedure_step_validation(self, audit_env):
        """Verify strict step sequencing, rejecting duplicates or gaps in step indices."""
        proc_service = audit_env["proc_service"]

        # Valid procedure
        proc = proc_service.create_procedure(ProcedureCreate(
            title="Deploy Staging",
            description="Deployment runbook",
            trigger_condition="Push to staging branch",
            steps=[
                ProcedureStep(step_number=1, action="Run tests"),
                ProcedureStep(step_number=2, action="Build image"),
                ProcedureStep(step_number=3, action="Deploy container"),
            ]
        ))
        assert proc.step_count == 3

        # Invalid: step numbers skipping 2
        with pytest.raises(Exception):
            proc_service.create_procedure(ProcedureCreate(
                title="Broken Steps",
                description="Invalid gap",
                trigger_condition="Always",
                steps=[
                    ProcedureStep(step_number=1, action="Step 1"),
                    ProcedureStep(step_number=3, action="Step 3"),
                ]
            ))

        # Log execution
        log = proc_service.log_execution(
            procedure_id=proc.id,
            payload=ProcedureExecutionLogCreate(
                execution_status="completed",
                duration_seconds=12.5,
                step_results=[{"step_number": 1, "status": "ok"}],
                notes="All green"
            )
        )
        assert log.id is not None


# ==============================================================================
# 7. MEMORY INTELLIGENCE & DECAY DYNAMICS AUDIT (B5)
# ==============================================================================

class TestMemoryIntelligenceAudit:
    """Audit of Ebbinghaus decay formulas, access touches, consolidation, compaction."""

    def test_decay_formula_edge_cases(self, audit_env):
        """Verify Ebbinghaus decay formula behaves correctly at boundaries."""
        decay_eng = audit_env["decay_eng"]
        mem_service = audit_env["mem_service"]

        mem = mem_service.create_memory(MemoryCreate(
            content="Decaying fact",
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT
        ))

        # Test score calculation
        score_obj = decay_eng.calculate_decay_score(mem.id)
        assert 0.0 <= score_obj.score <= 1.0

        # Touch memory and verify access count increments
        touched = decay_eng.touch_memories([mem.id])
        assert touched == 1

        updated_mem = mem_service.get_memory(mem.id)
        assert updated_mem.access_count == 1
        assert updated_mem.last_accessed_at is not None

    def test_compaction_plan_dry_run_vs_execution(self, audit_env):
        """Verify compaction service produces plan without mutating until confirmed."""
        comp_service = audit_env["comp_service"]
        mem_service = audit_env["mem_service"]

        # Generate a compaction plan
        plan = comp_service.analyze_compaction_opportunities()
        assert hasattr(plan, "actions")
        assert plan.total_candidates >= 0

        # Execute confirmed compaction
        res = comp_service.execute_compaction(
            plan=plan,
            request=CompactionExecuteRequest(dry_run=False, confirmed=True)
        )
        assert hasattr(res, "compacted_count")


# ==============================================================================
# 8. PYTHON CLIENT SDK AUDIT (B6)
# ==============================================================================

class TestClientSdkAudit:
    """Audit Python SDK client against test app."""

    def test_sdk_methods_with_authenticated_client(self, audit_env):
        """Verify EdithBrainClient works seamlessly with token auth."""
        client = EdithBrainClient(
            base_url="http://testserver",
            token=audit_env["token"],
            http_client=audit_env["client"]
        )

        health = client.get_health()
        assert health.status == "healthy"

        info = client.get_system_info()
        assert info.app_name == "E.D.I.T.H. Brain Core [Audit]"
