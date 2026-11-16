"""Integration tests for Phase B5 episodic memory consolidation pipeline and review."""

import pytest
from fastapi.testclient import TestClient

from edith_brain.core.contracts import (
    EpisodeCreate,
    EventType,
    ConsolidationReviewAction,
    ConsolidationStatus,
    PersonalSubcategory,
)
from edith_brain.services.episodic_service import EpisodicService
from edith_brain.services.memory_consolidation_service import MemoryConsolidationService
from edith_brain.services.memory_service import MemoryService


def test_consolidation_scan_and_approval_flow(
    episodic_service: EpisodicService,
    consolidation_service: MemoryConsolidationService,
    memory_service: MemoryService,
):
    """Test extracting candidate preferences from episodes and applying them upon review."""
    session_id = "session-consolidation-test"

    # 1. Ingest session episodes
    episodic_service.create_episode(
        EpisodeCreate(
            session_id=session_id,
            title="IDE Configuration Discussion",
            event_type=EventType.CONVERSATION,
            summary="User discussed theme preferences.",
            narrative_detail="I prefer dark mode with high contrast accents for all coding editors.",
            significance_score=0.85,
        )
    )
    episodic_service.create_episode(
        EpisodeCreate(
            session_id=session_id,
            title="General Chat",
            event_type=EventType.CONVERSATION,
            summary="Weather is nice today.",
            significance_score=0.2,
        )
    )

    # 2. Trigger consolidation scan for the session
    candidates = consolidation_service.consolidate_session_episodes(session_id=session_id, min_significance=0.5)
    assert len(candidates) >= 1
    cand = candidates[0]
    assert cand.candidate_subcategory == PersonalSubcategory.PREFERENCE
    assert "dark mode" in cand.candidate_content.lower()
    assert cand.status == ConsolidationStatus.PENDING

    # 3. Approve candidate
    approved = consolidation_service.review_candidate(
        candidate_id=cand.id,
        action=ConsolidationReviewAction(action="approve"),
        reviewer="LOCAL_USER",
    )
    assert approved.status == ConsolidationStatus.APPLIED
    assert approved.applied_memory_id is not None

    # 4. Verify created memory exists, has unverified status, and is linked to the episode
    applied_mem = memory_service.get_memory(approved.applied_memory_id)
    assert applied_mem.verification_status.value == "unverified"
    assert "dark mode" in applied_mem.content.lower()


def test_consolidation_rejection_flow(
    episodic_service: EpisodicService,
    consolidation_service: MemoryConsolidationService,
):
    """Test rejecting a consolidation candidate prevents memory creation."""
    session_id = "session-reject-test"

    episodic_service.create_episode(
        EpisodeCreate(
            session_id=session_id,
            title="Transient Goal",
            event_type=EventType.CONVERSATION,
            summary="User mentioned a short-term goal.",
            narrative_detail="My goal is to finish this quick scratch script in 10 minutes.",
            significance_score=0.7,
        )
    )

    candidates = consolidation_service.consolidate_session_episodes(session_id=session_id)
    assert len(candidates) >= 1
    cand = candidates[0]

    # Reject candidate
    rejected = consolidation_service.review_candidate(
        candidate_id=cand.id,
        action=ConsolidationReviewAction(action="reject", review_notes="Too ephemeral for persistent memory"),
        reviewer="LOCAL_USER",
    )
    assert rejected.status == ConsolidationStatus.REJECTED
    assert rejected.applied_memory_id is None


def test_consolidation_api_endpoints(client: TestClient):
    """Test REST API endpoints for consolidation proposal and review."""
    # 1. Create episode via API
    resp_ep = client.post(
        "/api/v1/episodes",
        json={
            "session_id": "api-consol-sess",
            "title": "Language Preferences",
            "event_type": "conversation",
            "summary": "User discusses development toolchain.",
            "narrative_detail": "I always use Python for data pipelines and backend microservices.",
            "significance_score": 0.8,
        },
    )
    assert resp_ep.status_code == 201

    # 2. Trigger consolidation scan via API
    resp_scan = client.post(
        "/api/v1/intelligence/consolidations/session",
        json={"session_id": "api-consol-sess", "min_significance": 0.5},
    )
    assert resp_scan.status_code == 200, resp_scan.text
    candidates = resp_scan.json()
    assert len(candidates) >= 1
    cand_id = candidates[0]["id"]

    # 3. List candidates via API
    resp_list = client.get("/api/v1/intelligence/consolidations?session_id=api-consol-sess")
    assert resp_list.status_code == 200
    listed = resp_list.json()
    assert any(c["id"] == cand_id for c in listed)

    # 4. Review candidate via API
    resp_review = client.post(
        f"/api/v1/intelligence/consolidations/{cand_id}/review",
        json={"action": "approve"},
    )
    assert resp_review.status_code == 200
    rev_data = resp_review.json()
    assert rev_data["status"] == "applied"
    assert rev_data["applied_memory_id"] is not None
