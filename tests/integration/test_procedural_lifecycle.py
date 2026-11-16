"""Integration tests for Phase B4 Procedural Memory lifecycle, telemetry, and FTS search."""

import pytest
from fastapi.testclient import TestClient

from edith_brain.core.contracts import (
    ProcedureCreate,
    ProcedureResponse,
    ProcedureStep,
    ProcedureStatus,
    ProcedureExecutionLogCreate,
)
from edith_brain.services.procedural_service import ProceduralService


def test_procedural_lifecycle_and_telemetry(procedural_service: ProceduralService):
    """Test procedure registration, telemetry tracking, and status transitions."""
    # 1. Register a procedure
    proc = procedural_service.create_procedure(
        ProcedureCreate(
            title="SQLite Database Vacuum Procedure",
            description="Run VACUUM INTO and verify SQLite integrity check.",
            trigger_conditions=["Disk fragmentation exceeds threshold", "Weekly maintenance schedule"],
            steps=[
                ProcedureStep(step_number=1, action="PRAGMA quick_check;"),
                ProcedureStep(step_number=2, action="VACUUM INTO 'backup.db';"),
                ProcedureStep(step_number=3, action="Verify backup file size and hash"),
            ],
            version="1.0.0",
            metadata={"tags": ["sqlite", "maintenance"]},
        )
    )
    assert proc.id is not None
    assert proc.title == "SQLite Database Vacuum Procedure"
    assert proc.status == ProcedureStatus.ACTIVE
    assert proc.execution_count == 0
    assert proc.success_count == 0
    assert proc.success_rate == 0.0
    assert proc.last_executed_at is None

    # 2. Log first execution: success
    log1 = procedural_service.log_execution(
        procedure_id=proc.id,
        payload=ProcedureExecutionLogCreate(
            execution_status="success",
            duration_seconds=0.35,
            notes="Quick check passed; vacuum completed in 350ms",
        ),
        actor="LOCAL_USER",
    )
    assert log1.id is not None
    assert log1.execution_status == "success"

    # Verify procedure stats updated
    updated_proc = procedural_service.get_procedure(proc.id)
    assert updated_proc.execution_count == 1
    assert updated_proc.success_count == 1
    assert updated_proc.success_rate == 1.0
    assert updated_proc.last_executed_at is not None

    # 3. Log second execution: failure
    log2 = procedural_service.log_execution(
        procedure_id=proc.id,
        payload=ProcedureExecutionLogCreate(
            execution_status="failure",
            duration_seconds=0.05,
            error_message="Permission denied writing backup.db",
        ),
        actor="LOCAL_USER",
    )
    assert log2.execution_status == "failure"

    # Verify updated stats (1 success out of 2 executions = 50%)
    updated_proc2 = procedural_service.get_procedure(proc.id)
    assert updated_proc2.execution_count == 2
    assert updated_proc2.success_count == 1
    assert updated_proc2.success_rate == 0.5

    # 4. List execution history
    history = procedural_service.get_execution_logs(proc.id)
    assert len(history) == 2

    # 5. Full-text search (FTS5) matching trigger condition and description
    search_results = procedural_service.search_procedures(query="weekly maintenance")
    assert len(search_results) >= 1
    assert search_results[0].id == proc.id

    search_by_trigger = procedural_service.search_procedures(query="disk fragmentation")
    assert len(search_by_trigger) >= 1
    assert search_by_trigger[0].id == proc.id

    # 6. Deprecate procedure
    deprecated = procedural_service.update_status(proc.id, ProcedureStatus.DEPRECATED)
    assert deprecated.status == ProcedureStatus.DEPRECATED

    # When searching active procedures only, it should not appear
    active_search = procedural_service.search_procedures(
        query="maintenance", status=ProcedureStatus.ACTIVE
    )
    assert not any(p.id == proc.id for p in active_search)

    # When searching deprecated, it should appear
    deprecated_search = procedural_service.search_procedures(
        query="maintenance", status=ProcedureStatus.DEPRECATED
    )
    assert any(p.id == proc.id for p in deprecated_search)


def test_procedural_api_endpoints(client: TestClient):
    """Test REST API endpoints for procedures creation, telemetry, and search."""
    # 1. Create procedure
    resp = client.post(
        "/api/v1/procedures",
        json={
            "title": "API Service Restart Playbook",
            "description": "Safely restart the background worker processes.",
            "trigger_conditions": ["Worker process crashes", "Memory leak detected"],
            "steps": [
                {"step_number": 1, "action": "SIGTERM existing worker"},
                {"step_number": 2, "action": "Wait 5s for graceful shutdown"},
                {"step_number": 3, "action": "Spawn new worker process"},
            ],
            "version": "1.0.0",
            "metadata": {"tags": ["api", "workers"]},
        },
    )
    assert resp.status_code == 201, resp.text
    proc_data = resp.json()
    proc_id = proc_data["id"]

    # 2. Search procedure via API
    resp_search = client.get("/api/v1/procedures/search?q=worker+process")
    assert resp_search.status_code == 200
    results = resp_search.json()
    assert any(p["id"] == proc_id for p in results)

    # 3. Log execution via API
    resp_log = client.post(
        f"/api/v1/procedures/{proc_id}/execute",
        json={
            "execution_status": "success",
            "duration_seconds": 0.12,
            "notes": "Workers restarted successfully.",
        },
    )
    assert resp_log.status_code == 200, resp_log.text
    log_data = resp_log.json()
    assert log_data["procedure_id"] == proc_id
    assert log_data["execution_status"] == "success"

    # 4. Get execution history via API
    resp_history = client.get(f"/api/v1/procedures/{proc_id}/executions")
    assert resp_history.status_code == 200
    history = resp_history.json()
    assert len(history) == 1
    assert history[0]["id"] == log_data["id"]

    # 5. Deprecate procedure via API
    resp_deprecate = client.patch(f"/api/v1/procedures/{proc_id}/status?status=deprecated")
    assert resp_deprecate.status_code == 200
    deprecate_data = resp_deprecate.json()
    assert deprecate_data["status"] == "deprecated"
