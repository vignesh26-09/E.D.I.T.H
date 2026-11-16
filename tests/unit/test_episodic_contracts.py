"""Unit tests for Phase B4 Episodic Memory contracts and validation."""

import pytest
from pydantic import ValidationError

from edith_brain.core.contracts import (
    EpisodeCreate,
    EpisodeResponse,
    EpisodeTimelineRequest,
    EventType,
    LinkType,
    MemoryLinkCreate,
    MemoryLinkResponse,
)


def test_episode_create_valid():
    """Verify EpisodeCreate schema accepting standard attributes."""
    episode = EpisodeCreate(
        session_id="session-xyz-123",
        title="Diagnostic Run",
        event_type=EventType.TASK_EXECUTION,
        summary="Executed diagnostic playbook.",
        actors=["orchestrator"],
        significance_score=0.8,
        metadata={"step": 1, "status": "ok"},
    )
    assert episode.session_id == "session-xyz-123"
    assert episode.title == "Diagnostic Run"
    assert episode.event_type == EventType.TASK_EXECUTION
    assert episode.significance_score == 0.8
    assert episode.metadata == {"step": 1, "status": "ok"}


def test_episode_create_defaults():
    """Verify default values for significance, actors, and metadata."""
    episode = EpisodeCreate(
        session_id="session-1",
        title="Chat Session",
        event_type=EventType.CONVERSATION,
        summary="A simple conversation turn.",
    )
    assert episode.event_type == EventType.CONVERSATION
    assert episode.actors == ["user"]
    assert episode.significance_score == 0.5
    assert episode.metadata == {}
    assert episode.occurred_at is not None


def test_episode_create_significance_validation():
    """Verify significance_score must be between 0.0 and 1.0."""
    with pytest.raises(ValidationError):
        EpisodeCreate(
            session_id="session-1",
            title="Chat Session",
            event_type=EventType.CONVERSATION,
            summary="Invalid negative significance",
            significance_score=-0.1,
        )

    with pytest.raises(ValidationError):
        EpisodeCreate(
            session_id="session-1",
            title="Chat Session",
            event_type=EventType.CONVERSATION,
            summary="Invalid high significance",
            significance_score=1.5,
        )


def test_episode_timeline_request_validation():
    """Verify bounds and ordering for EpisodeTimelineRequest."""
    req = EpisodeTimelineRequest(
        session_id="session-123",
        event_types=[EventType.TASK_EXECUTION, EventType.SYSTEM_EVENT],
        min_significance=0.4,
        order="desc",
        limit=50,
    )
    assert req.order == "desc"
    assert req.limit == 50

    # Limit must be >= 1 and <= 500
    with pytest.raises(ValidationError):
        EpisodeTimelineRequest(limit=0)

    with pytest.raises(ValidationError):
        EpisodeTimelineRequest(limit=501)


def test_cross_memory_link_validation():
    """Verify link creation and LinkType validation."""
    link = MemoryLinkCreate(
        episode_id="ep-123",
        procedure_id="proc-456",
        link_type=LinkType.EXECUTED_PROCEDURE,
        metadata={"notes": "Execution instance of procedure"},
    )
    assert link.link_type == LinkType.EXECUTED_PROCEDURE
    assert link.episode_id == "ep-123"
    assert link.procedure_id == "proc-456"

    # Must connect at least two entities
    with pytest.raises(ValidationError):
        MemoryLinkCreate(
            episode_id="ep-123",
            link_type=LinkType.EXECUTED_PROCEDURE,
        )
