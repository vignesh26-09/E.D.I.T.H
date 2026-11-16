"""Integration tests for Phase B5 memory compaction and deduplication."""

import pytest
from fastapi.testclient import TestClient

from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCategory,
    PersonalSubcategory,
    CompactionExecuteRequest,
)
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.memory_compaction_service import MemoryCompactionService


def test_compaction_analysis_and_execution_lifecycle(
    memory_service: MemoryService,
    compaction_service: MemoryCompactionService,
):
    """Test discovering redundant memories and compacting them into a single entry."""
    # 1. Create near-duplicate memories in subcategory PREFERENCE
    m1 = memory_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="User prefers dark theme mode with high contrast accents for code editing.",
        )
    )
    m2 = memory_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="User prefers dark theme mode with high contrast accents.",
        )
    )

    # 2. Analyze compaction opportunities
    plan = compaction_service.analyze_compaction_opportunities(
        subcategory=PersonalSubcategory.PREFERENCE,
        similarity_threshold=0.6,
    )
    assert len(plan.clusters) >= 1
    cluster = plan.clusters[0]
    assert m1.id in cluster.memory_ids
    assert m2.id in cluster.memory_ids
    assert plan.redundant_memories_identified >= 1

    # 3. Dry run compaction
    dry_run_result = compaction_service.execute_compaction(
        plan=plan,
        request=CompactionExecuteRequest(dry_run=True, confirmed=False),
    )
    assert dry_run_result.dry_run is True
    assert dry_run_result.executed is False

    # 4. Confirmed execution without confirmed flag should fail
    with pytest.raises(Exception):
        compaction_service.execute_compaction(
            plan=plan,
            request=CompactionExecuteRequest(dry_run=False, confirmed=False),
        )

    # 5. Execute confirmed compaction
    exec_result = compaction_service.execute_compaction(
        plan=plan,
        request=CompactionExecuteRequest(dry_run=False, confirmed=True),
    )
    assert exec_result.executed is True
    assert len(exec_result.created_memory_ids) == 1
    assert m1.id in exec_result.superseded_memory_ids
    assert m2.id in exec_result.superseded_memory_ids

    # Verify newly created unified memory
    new_mem = memory_service.get_memory(exec_result.created_memory_ids[0])
    assert new_mem.status == "active"
    assert "compacted" in new_mem.tags


def test_compaction_api_endpoints(client: TestClient):
    """Test REST API endpoints for compaction planning and execution."""
    # 1. Create duplicate memories via API
    resp_m1 = client.post(
        "/api/v1/memories",
        json={
            "category": "personal",
            "subcategory": "goal",
            "content": "Master Rust systems programming and memory safety patterns.",
        },
    )
    assert resp_m1.status_code == 201
    id1 = resp_m1.json()["id"]

    resp_m2 = client.post(
        "/api/v1/memories",
        json={
            "category": "personal",
            "subcategory": "goal",
            "content": "Master Rust systems programming and memory safety.",
        },
    )
    assert resp_m2.status_code == 201
    id2 = resp_m2.json()["id"]

    # 2. Get compaction plan via API
    resp_plan = client.get("/api/v1/intelligence/compaction/plan?subcategory=goal&similarity_threshold=0.6")
    assert resp_plan.status_code == 200
    plan_data = resp_plan.json()
    assert len(plan_data["clusters"]) >= 1

    # 3. Execute compaction dry-run via API
    resp_dry = client.post(
        "/api/v1/intelligence/compaction/execute",
        json={"dry_run": True, "confirmed": False},
    )
    assert resp_dry.status_code == 200
    assert resp_dry.json()["dry_run"] is True

    # 4. Execute confirmed compaction via API
    resp_exec = client.post(
        "/api/v1/intelligence/compaction/execute",
        json={"dry_run": False, "confirmed": True},
    )
    assert resp_exec.status_code == 200
    assert resp_exec.json()["executed"] is True
