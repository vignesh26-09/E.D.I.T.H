"""Integration tests for Phase B4 Episodic Memory timeline, search, and session aggregation."""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from edith_brain.core.contracts import (
    EpisodeCreate,
    EpisodeResponse,
    EpisodeTimelineRequest,
    EventType,
)
from edith_brain.services.episodic_service import EpisodicService


def test_episodic_service_ingest_and_timeline_filtering(episodic_service: EpisodicService):
    """Test episodic event ingestion and structured timeline filtering."""
    t0 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)

    # Ingest session 1 events
    ep1 = episodic_service.create_episode(
        EpisodeCreate(
            session_id="session-alpha",
            title="User Greetings",
            event_type=EventType.CONVERSATION,
            summary="Hello EDITH, please check the system diagnostics.",
            significance_score=0.3,
            occurred_at=t0.isoformat(),
        )
    )
    ep2 = episodic_service.create_episode(
        EpisodeCreate(
            session_id="session-alpha",
            title="Diagnostics Routine",
            event_type=EventType.TASK_EXECUTION,
            summary="Running comprehensive system diagnostics on local host.",
            significance_score=0.7,
            occurred_at=(t0 + timedelta(seconds=10)).isoformat(),
        )
    )
    ep3 = episodic_service.create_episode(
        EpisodeCreate(
            session_id="session-alpha",
            title="Diagnostics Complete",
            event_type=EventType.SYSTEM_EVENT,
            summary="Diagnostic milestone completed successfully with zero warnings.",
            significance_score=0.9,
            occurred_at=(t0 + timedelta(seconds=30)).isoformat(),
        )
    )

    # Ingest session 2 event
    ep4 = episodic_service.create_episode(
        EpisodeCreate(
            session_id="session-beta",
            title="Benchmark Query",
            event_type=EventType.CONVERSATION,
            summary="What was the result of yesterday's benchmark?",
            significance_score=0.4,
            occurred_at=(t0 + timedelta(hours=1)).isoformat(),
        )
    )

    # 1. Query all episodes for session-alpha
    timeline_alpha = episodic_service.get_timeline(
        EpisodeTimelineRequest(session_id="session-alpha", order="asc")
    )
    assert len(timeline_alpha) == 3
    assert timeline_alpha[0].id == ep1.id
    assert timeline_alpha[2].id == ep3.id

    # 2. Filter by significance threshold (>= 0.7)
    high_sig = episodic_service.get_timeline(
        EpisodeTimelineRequest(session_id="session-alpha", min_significance=0.7)
    )
    assert len(high_sig) == 2
    assert all(e.significance_score >= 0.7 for e in high_sig)

    # 3. Filter by event type
    actions_only = episodic_service.get_timeline(
        EpisodeTimelineRequest(
            session_id="session-alpha",
            event_types=[EventType.TASK_EXECUTION],
        )
    )
    assert len(actions_only) == 1
    assert actions_only[0].event_type == EventType.TASK_EXECUTION

    # 4. Filter by timestamp range
    time_window = episodic_service.get_timeline(
        EpisodeTimelineRequest(
            start_time=t0.isoformat(),
            end_time=(t0 + timedelta(seconds=15)).isoformat(),
        )
    )
    assert len(time_window) == 2


def test_episodic_fts5_search(episodic_service: EpisodicService):
    """Test full-text search indexing on episodic content via SQLite FTS5."""
    episodic_service.create_episode(
        EpisodeCreate(
            session_id="session-fts",
            title="Query Run",
            event_type=EventType.TASK_EXECUTION,
            summary="Executed query against SQLite database and found 42 matching entities.",
            significance_score=0.6,
        )
    )
    episodic_service.create_episode(
        EpisodeCreate(
            session_id="session-fts",
            title="GC Event",
            event_type=EventType.SYSTEM_EVENT,
            summary="Memory allocation stabilized after garbage collection cycle.",
            significance_score=0.5,
        )
    )

    # Query matching 'SQLite database'
    results = episodic_service.get_timeline(EpisodeTimelineRequest(query="SQLite database"))
    assert len(results) >= 1
    assert "SQLite database" in results[0].summary

    # Query matching 'garbage collection'
    results2 = episodic_service.get_timeline(EpisodeTimelineRequest(query="garbage collection"))
    assert len(results2) >= 1
    assert "garbage collection" in results2[0].summary


def test_episodic_sessions_aggregation(episodic_service: EpisodicService):
    """Test listing distinct sessions with event counts and timestamps."""
    t0 = datetime(2026, 11, 2, 8, 0, 0, tzinfo=timezone.utc)

    episodic_service.create_episode(
        EpisodeCreate(
            session_id="sess-100",
            title="Event 1",
            event_type=EventType.CONVERSATION,
            summary="First message in sess-100",
            occurred_at=t0.isoformat(),
        )
    )
    episodic_service.create_episode(
        EpisodeCreate(
            session_id="sess-100",
            title="Event 2",
            event_type=EventType.CONVERSATION,
            summary="Second message in sess-100",
            occurred_at=(t0 + timedelta(minutes=5)).isoformat(),
        )
    )
    episodic_service.create_episode(
        EpisodeCreate(
            session_id="sess-200",
            title="Event 1 in sess 200",
            event_type=EventType.CONVERSATION,
            summary="Event in sess 200",
            occurred_at=(t0 + timedelta(hours=1)).isoformat(),
        )
    )

    sessions = episodic_service.list_sessions()
    assert len(sessions) >= 2
    sess_map = {s["session_id"]: s for s in sessions}

    assert "sess-100" in sess_map
    assert sess_map["sess-100"]["event_count"] == 2
    assert "sess-200" in sess_map
    assert sess_map["sess-200"]["event_count"] == 1


def test_episodic_api_endpoints(client: TestClient):
    """Test REST API endpoints for episodic events recording and timeline querying."""
    # 1. Record an episode
    resp = client.post(
        "/api/v1/episodes",
        json={
            "session_id": "api-session-1",
            "title": "API Conversation",
            "event_type": "conversation",
            "summary": "API test message for episodic tracking.",
            "significance_score": 0.85,
            "metadata": {"test_key": "test_val"},
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    episode_id = data["id"]
    assert data["session_id"] == "api-session-1"
    assert data["significance_score"] == 0.85

    # 2. Query timeline via API
    resp_timeline = client.post(
        "/api/v1/episodes/timeline",
        json={
            "session_id": "api-session-1",
            "min_significance": 0.5,
            "order": "desc",
        },
    )
    assert resp_timeline.status_code == 200
    timeline = resp_timeline.json()
    assert len(timeline) >= 1
    assert timeline[0]["id"] == episode_id

    # 3. Search episodes via timeline query
    resp_search = client.post(
        "/api/v1/episodes/timeline",
        json={"query": "episodic tracking"},
    )
    assert resp_search.status_code == 200
    search_results = resp_search.json()
    assert len(search_results) >= 1
    assert search_results[0]["id"] == episode_id

    # 4. List sessions via API
    resp_sessions = client.get("/api/v1/episodes/sessions")
    assert resp_sessions.status_code == 200
    sessions = resp_sessions.json()
    assert any(s["session_id"] == "api-session-1" for s in sessions)
