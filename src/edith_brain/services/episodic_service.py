"""Domain service orchestrating episodic memory creation, session clustering, and timeline queries."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from edith_brain.core.contracts import (
    EpisodeCreate,
    EpisodeResponse,
    EpisodeTimelineRequest,
    EventType,
    MemoryLinkCreate,
    MemoryLinkResponse,
    LinkType,
)
from edith_brain.core.exceptions import NotFoundError, ValidationError
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.episodic_repository import EpisodicRepository
from edith_brain.repositories.cross_memory_link_repository import CrossMemoryLinkRepository
from edith_brain.services.retrieval.query_parser import sanitize_fts5_query


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_episode_response(row) -> EpisodeResponse:
    return EpisodeResponse(
        id=row["id"],
        session_id=row["session_id"],
        title=row["title"],
        event_type=EventType(row["event_type"]),
        occurred_at=row["occurred_at"],
        duration_seconds=row["duration_seconds"],
        summary=row["summary"],
        narrative_detail=row["narrative_detail"],
        actors=json.loads(row["actors_json"]),
        context_tags=json.loads(row["context_tags_json"]),
        significance_score=row["significance_score"],
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
    )


class EpisodicService:
    """Manages episodic event logging, chronological timelines, and session groupings."""

    def __init__(
        self,
        engine: SQLiteEngine,
        episodic_repo: EpisodicRepository | None = None,
        link_repo: CrossMemoryLinkRepository | None = None,
    ) -> None:
        self.engine = engine
        self.episodic_repo = episodic_repo or EpisodicRepository()
        self.link_repo = link_repo or CrossMemoryLinkRepository()

    def create_episode(self, payload: EpisodeCreate) -> EpisodeResponse:
        """Record a new discrete episodic event, conversation session, or incident."""
        now = _utc_now_iso()
        episode_id = str(uuid.uuid4())

        episode_dict = {
            "id": episode_id,
            "session_id": payload.session_id,
            "title": payload.title,
            "event_type": payload.event_type.value,
            "occurred_at": payload.occurred_at,
            "duration_seconds": payload.duration_seconds,
            "summary": payload.summary,
            "narrative_detail": payload.narrative_detail,
            "actors_json": json.dumps(payload.actors),
            "context_tags_json": json.dumps(payload.context_tags),
            "significance_score": payload.significance_score,
            "metadata_json": json.dumps(payload.metadata),
            "created_at": now,
        }

        with self.engine.write_transaction() as conn:
            self.episodic_repo.insert(conn, episode_dict)

        with self.engine.connection() as conn:
            row = self.episodic_repo.get_by_id(conn, episode_id)
            return _row_to_episode_response(row)

    def get_episode(self, episode_id: str) -> EpisodeResponse:
        """Fetch an episode by ID."""
        with self.engine.connection() as conn:
            row = self.episodic_repo.get_by_id(conn, episode_id)
            if not row:
                raise NotFoundError(f"Episode with ID '{episode_id}' not found.")
            return _row_to_episode_response(row)

    def get_timeline(self, payload: EpisodeTimelineRequest) -> list[EpisodeResponse]:
        """Query chronological or significance-ordered episodes with multi-facet filters."""
        sanitized_query = None
        if payload.query and payload.query.strip():
            sanitized = sanitize_fts5_query(payload.query.strip(), match_mode="OR")
            if sanitized and sanitized != '""':
                sanitized_query = sanitized

        event_types = [t.value for t in payload.event_types] if payload.event_types else None

        with self.engine.connection() as conn:
            rows = self.episodic_repo.get_timeline(
                conn=conn,
                session_id=payload.session_id,
                event_types=event_types,
                start_time=payload.start_time,
                end_time=payload.end_time,
                min_significance=payload.min_significance,
                query=sanitized_query,
                limit=payload.limit,
                order=payload.order,
            )
            return [_row_to_episode_response(r) for r in rows]

    def list_sessions(self, limit: int = 50) -> list[dict]:
        """Aggregate sessions with event count, start time, and latest activity."""
        with self.engine.connection() as conn:
            return self.episodic_repo.list_sessions(conn, limit=limit)

    def delete_episode(self, episode_id: str) -> dict:
        """Physically delete an episode with cascade to cross-domain links."""
        with self.engine.write_transaction() as conn:
            count = self.episodic_repo.delete(conn, episode_id)
            if count == 0:
                raise NotFoundError(f"Episode with ID '{episode_id}' not found.")
        return {"id": episode_id, "deleted": True}

    def create_link(self, payload: MemoryLinkCreate) -> MemoryLinkResponse:
        """Create a cross-domain relation between an episode, procedure, and/or personal memory."""
        now = _utc_now_iso()
        link_id = str(uuid.uuid4())

        link_dict = {
            "id": link_id,
            "episode_id": payload.episode_id,
            "procedure_id": payload.procedure_id,
            "memory_id": payload.memory_id,
            "link_type": payload.link_type.value,
            "metadata_json": json.dumps(payload.metadata),
            "created_at": now,
        }

        with self.engine.write_transaction() as conn:
            self.link_repo.insert(conn, link_dict)

        with self.engine.connection() as conn:
            row = self.link_repo.get_by_id(conn, link_id)
            return MemoryLinkResponse(
                id=row["id"],
                episode_id=row["episode_id"],
                procedure_id=row["procedure_id"],
                memory_id=row["memory_id"],
                link_type=LinkType(row["link_type"]),
                metadata=json.loads(row["metadata_json"]),
                created_at=row["created_at"],
            )

    def get_episode_links(self, episode_id: str) -> list[MemoryLinkResponse]:
        """Fetch all cross-memory links attached to an episode."""
        with self.engine.connection() as conn:
            if not self.episodic_repo.get_by_id(conn, episode_id):
                raise NotFoundError(f"Episode with ID '{episode_id}' not found.")
            rows = self.link_repo.get_by_episode_id(conn, episode_id)
            return [
                MemoryLinkResponse(
                    id=r["id"],
                    episode_id=r["episode_id"],
                    procedure_id=r["procedure_id"],
                    memory_id=r["memory_id"],
                    link_type=LinkType(r["link_type"]),
                    metadata=json.loads(r["metadata_json"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]
