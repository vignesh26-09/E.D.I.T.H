"""Domain service for distilling episodic interactions into verified semantic memories."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from edith_brain.core.contracts import (
    ConsolidationCandidateCreate,
    ConsolidationCandidateResponse,
    ConsolidationReviewAction,
    ConsolidationStatus,
    MemoryCategory,
    PersonalSubcategory,
    MemoryCreate,
    MemoryLinkCreate,
    LinkType,
)
from edith_brain.core.exceptions import NotFoundError, ValidationError
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.intelligence_repository import IntelligenceRepository
from edith_brain.repositories.episodic_repository import EpisodicRepository
from edith_brain.repositories.cross_memory_link_repository import CrossMemoryLinkRepository
from edith_brain.services.memory_service import MemoryService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_candidate_response(row) -> ConsolidationCandidateResponse:
    subcat = PersonalSubcategory(row["candidate_subcategory"]) if row["candidate_subcategory"] else None
    return ConsolidationCandidateResponse(
        id=row["id"],
        session_id=row["session_id"],
        candidate_category=MemoryCategory(row["candidate_category"]),
        candidate_subcategory=subcat,
        candidate_content=row["candidate_content"],
        rationale=row["rationale"],
        confidence=float(row["confidence"]),
        source_episode_ids=json.loads(row["source_episode_ids_json"]),
        status=ConsolidationStatus(row["status"]),
        applied_memory_id=row["applied_memory_id"],
        reviewed_by=row["reviewed_by"],
        reviewed_at=row["reviewed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# Heuristic patterns for extracting prospective facts/preferences from text
PREFERENCE_PATTERNS = [
    (re.compile(r"\b(?:i prefer|i like|i always use|my preference is)\s+([^.!?]+)", re.IGNORECASE), PersonalSubcategory.PREFERENCE),
    (re.compile(r"\b(?:my goal is|i want to achieve|aiming to)\s+([^.!?]+)", re.IGNORECASE), PersonalSubcategory.GOAL),
    (re.compile(r"\b(?:i am proficient in|skilled in|experience with)\s+([^.!?]+)", re.IGNORECASE), PersonalSubcategory.SKILL),
    (re.compile(r"\b(?:working on project|current project is)\s+([^.!?]+)", re.IGNORECASE), PersonalSubcategory.PROJECT_CONTEXT),
    (re.compile(r"\b(?:my name is|i live in|i work as)\s+([^.!?]+)", re.IGNORECASE), PersonalSubcategory.PROFILE_FACT),
]


class MemoryConsolidationService:
    """Orchestrates consolidation of episodic events into prospective semantic personal memories."""

    def __init__(
        self,
        engine: SQLiteEngine,
        memory_service: MemoryService,
        intel_repo: Optional[IntelligenceRepository] = None,
        episodic_repo: Optional[EpisodicRepository] = None,
        link_repo: Optional[CrossMemoryLinkRepository] = None,
    ) -> None:
        self.engine = engine
        self.memory_service = memory_service
        self.intel_repo = intel_repo or IntelligenceRepository()
        self.episodic_repo = episodic_repo or EpisodicRepository()
        self.link_repo = link_repo or CrossMemoryLinkRepository()

    def consolidate_session_episodes(
        self,
        session_id: str,
        min_significance: float = 0.5,
    ) -> list[ConsolidationCandidateResponse]:
        """Analyze session episodes, identify salient statements, and generate consolidation candidates."""
        with self.engine.connection() as conn:
            episodes = self.episodic_repo.get_timeline(
                conn=conn,
                session_id=session_id,
                min_significance=min_significance,
                limit=200,
            )

        if not episodes:
            return []

        candidates_created: list[ConsolidationCandidateResponse] = []
        now = _utc_now_iso()

        for ep in episodes:
            summary = ep["summary"]
            narrative = ep["narrative_detail"] or ""
            text = f"{summary} {narrative}".strip()

            matched_subcat: Optional[PersonalSubcategory] = None
            extracted_fact: Optional[str] = None

            for pattern, subcat in PREFERENCE_PATTERNS:
                m = pattern.search(text)
                if m:
                    matched_subcat = subcat
                    extracted_fact = m.group(0).strip().capitalize()
                    break

            # If no regex matched but significance is very high (>= 0.8), treat as salient session observation
            if not extracted_fact and ep["significance_score"] >= 0.8:
                matched_subcat = PersonalSubcategory.PROJECT_CONTEXT
                extracted_fact = f"Noted milestone in session {session_id}: {summary}"

            if extracted_fact:
                candidate_id = str(uuid.uuid4())
                candidate_dict = {
                    "id": candidate_id,
                    "session_id": session_id,
                    "candidate_category": MemoryCategory.PERSONAL.value,
                    "candidate_subcategory": matched_subcat.value if matched_subcat else None,
                    "candidate_content": extracted_fact,
                    "rationale": f"Distilled from episode {ep['id']} (significance {ep['significance_score']})",
                    "confidence": round(min(0.85, ep["significance_score"] * 0.9), 2),
                    "source_episode_ids_json": json.dumps([ep["id"]]),
                    "status": ConsolidationStatus.PENDING.value,
                    "applied_memory_id": None,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "created_at": now,
                    "updated_at": now,
                }

                with self.engine.write_transaction() as conn:
                    self.intel_repo.insert_consolidation_candidate(conn, candidate_dict)

                with self.engine.connection() as conn:
                    row = self.intel_repo.get_consolidation_candidate(conn, candidate_id)
                    if row:
                        candidates_created.append(_row_to_candidate_response(row))

        return candidates_created

    def create_candidate(
        self,
        payload: ConsolidationCandidateCreate,
    ) -> ConsolidationCandidateResponse:
        """Manually register or propose a consolidation candidate."""
        now = _utc_now_iso()
        candidate_id = str(uuid.uuid4())
        candidate_dict = {
            "id": candidate_id,
            "session_id": payload.session_id,
            "candidate_category": payload.candidate_category.value,
            "candidate_subcategory": payload.candidate_subcategory.value if payload.candidate_subcategory else None,
            "candidate_content": payload.candidate_content,
            "rationale": payload.rationale,
            "confidence": payload.confidence,
            "source_episode_ids_json": json.dumps(payload.source_episode_ids),
            "status": ConsolidationStatus.PENDING.value,
            "applied_memory_id": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": now,
            "updated_at": now,
        }

        with self.engine.write_transaction() as conn:
            self.intel_repo.insert_consolidation_candidate(conn, candidate_dict)

        with self.engine.connection() as conn:
            row = self.intel_repo.get_consolidation_candidate(conn, candidate_id)
            if not row:
                raise NotFoundError(f"Candidate '{candidate_id}' could not be created.")
            return _row_to_candidate_response(row)

    def review_candidate(
        self,
        candidate_id: str,
        action: ConsolidationReviewAction,
        reviewer: str = "LOCAL_USER",
    ) -> ConsolidationCandidateResponse:
        """Approve or reject a consolidation candidate, creating active memory and links if approved."""
        now = _utc_now_iso()

        with self.engine.connection() as conn:
            row = self.intel_repo.get_consolidation_candidate(conn, candidate_id)
            if not row:
                raise NotFoundError(f"Consolidation candidate with ID '{candidate_id}' not found.")

        if row["status"] != ConsolidationStatus.PENDING.value:
            raise ValidationError(f"Candidate '{candidate_id}' is already in status '{row['status']}'.")

        applied_memory_id: Optional[str] = None
        new_status = ConsolidationStatus.REJECTED.value

        if action.action == "approve":
            # 1. Create personal memory with unverified verification state
            mem = self.memory_service.create_memory(
                payload=MemoryCreate(
                    category=MemoryCategory(row["candidate_category"]),
                    subcategory=PersonalSubcategory(row["candidate_subcategory"]) if row["candidate_subcategory"] else None,
                    content=row["candidate_content"],
                    confidence=float(row["confidence"]),
                    tags=["consolidated", f"session:{row['session_id']}"],
                    metadata={"rationale": row["rationale"], "reviewed_by": reviewer},
                )
            )
            applied_memory_id = mem.id
            new_status = ConsolidationStatus.APPLIED.value

            # 2. Link candidate source episodes to the newly created memory
            source_ep_ids = json.loads(row["source_episode_ids_json"])
            for ep_id in source_ep_ids:
                link_id = str(uuid.uuid4())
                link_dict = {
                    "id": link_id,
                    "episode_id": ep_id,
                    "procedure_id": None,
                    "memory_id": mem.id,
                    "link_type": LinkType.DERIVED_MEMORY.value,
                    "metadata_json": json.dumps({"consolidation_candidate_id": candidate_id}),
                    "created_at": now,
                }
                with self.engine.write_transaction() as conn:
                    self.link_repo.insert(conn, link_dict)

        # 3. Update candidate status
        with self.engine.write_transaction() as conn:
            self.intel_repo.update_consolidation_status(
                conn=conn,
                candidate_id=candidate_id,
                status=new_status,
                applied_memory_id=applied_memory_id,
                reviewed_by=reviewer,
                reviewed_at=now,
                updated_at=now,
            )

        with self.engine.connection() as conn:
            updated = self.intel_repo.get_consolidation_candidate(conn, candidate_id)
            return _row_to_candidate_response(updated)

    def list_candidates(
        self,
        session_id: Optional[str] = None,
        status: Optional[ConsolidationStatus] = None,
        limit: int = 50,
    ) -> list[ConsolidationCandidateResponse]:
        """List consolidation candidates with optional filtering."""
        with self.engine.connection() as conn:
            rows = self.intel_repo.list_consolidation_candidates(
                conn=conn,
                session_id=session_id,
                status=status.value if status else None,
                limit=limit,
            )
            return [_row_to_candidate_response(r) for r in rows]
