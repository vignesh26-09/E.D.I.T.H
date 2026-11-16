"""Advisory conflict, duplicate, and contradiction detection engine for personal memories."""

import re
from typing import Optional
import numpy as np

from edith_brain.core.contracts import (
    MemoryConflictCheckRequest,
    MemoryConflictCheckResponse,
    MemoryConflictItem,
    ConflictType,
    PersonalSubcategory,
)
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.memory_repository import MemoryRepository
from edith_brain.repositories.memory_embedding_repository import MemoryEmbeddingRepository
from edith_brain.services.retrieval.embeddings import BaseEmbeddingProvider, unpack_vector, compute_cosine_similarity


# Antonym / Opposing Slot Value Dictionaries
OPPOSING_VALUE_PAIRS = [
    {"dark", "light"},
    {"dark mode", "light mode"},
    {"tabs", "spaces"},
    {"mac", "windows", "linux"},
    {"ios", "android"},
    {"vim", "emacs", "vscode"},
    {"yes", "no"},
    {"true", "false"},
    {"enable", "disable"},
    {"like", "dislike"},
    {"prefer", "avoid"},
]

NEGATION_TOKENS = {"not", "never", "no", "cannot", "don't", "dont", "dislike", "avoid", "refuse"}


def _tokenize(text: str) -> set[str]:
    """Extract lowercased alphanumeric words."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _extract_slots(text: str) -> dict[str, str]:
    """Simple heuristic extraction of key subject/predicate/value patterns."""
    cleaned = text.lower().strip()
    slots = {}

    # Extract location (e.g. based in X, lives in X)
    loc_match = re.search(r"\b(?:based in|lives in|located in|resides in)\s+([a-z\s]+)", cleaned)
    if loc_match:
        slots["location"] = loc_match.group(1).strip()

    # Extract preference (e.g. prefers X, likes X)
    pref_match = re.search(r"\b(?:prefers?|likes?|favorite|loves?)\s+([a-z\s]+)", cleaned)
    if pref_match:
        slots["preference"] = pref_match.group(1).strip()

    # Extract role/identity (e.g. is a X, works as X)
    role_match = re.search(r"\b(?:is a|works as|employed as)\s+([a-z\s]+)", cleaned)
    if role_match:
        slots["role"] = role_match.group(1).strip()

    return slots


def _detect_polarity_clash(text1: str, text2: str) -> bool:
    """Detect whether two sentences exhibit inverted negation or opposing slot values."""
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)

    has_neg1 = bool(tokens1 & NEGATION_TOKENS)
    has_neg2 = bool(tokens2 & NEGATION_TOKENS)

    # Inverted negation on high vocabulary overlap
    jaccard = len(tokens1 & tokens2) / max(len(tokens1 | tokens2), 1)
    if jaccard >= 0.4 and (has_neg1 != has_neg2):
        return True

    # Antonym pair clashes
    for pair in OPPOSING_VALUE_PAIRS:
        matched1 = any(val in text1.lower() for val in pair)
        matched2 = any(val in text2.lower() for val in pair)
        if matched1 and matched2:
            # Check if they chose different values in the opposing pair
            val1 = next((val for val in pair if val in text1.lower()), None)
            val2 = next((val for val in pair if val in text2.lower()), None)
            if val1 and val2 and val1 != val2:
                return True

    return False


class MemoryConflictEngine:
    """Evaluates candidate memories against active memories using hierarchical precedence."""

    def __init__(
        self,
        engine: SQLiteEngine,
        memory_repo: MemoryRepository | None = None,
        embedding_repo: MemoryEmbeddingRepository | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
    ) -> None:
        self.engine = engine
        self.memory_repo = memory_repo or MemoryRepository()
        self.embedding_repo = embedding_repo or MemoryEmbeddingRepository()
        self.embedding_provider = embedding_provider

    def check_conflicts(self, payload: MemoryConflictCheckRequest) -> MemoryConflictCheckResponse:
        """Advisory conflict analysis across active memories in category/subcategory."""
        candidate_text = payload.content.strip()
        candidate_tokens = _tokenize(candidate_text)
        candidate_slots = _extract_slots(candidate_text)

        # Check if real semantic provider is available
        has_semantic = (
            self.embedding_provider is not None
            and getattr(self.embedding_provider, "provider_type", "") == "neural_semantic"
        )
        capability = "full_semantic_and_slot" if has_semantic else "lexical_and_slot_only"

        candidate_vector = None
        if has_semantic:
            candidate_vector = np.array(self.embedding_provider.embed_query(candidate_text), dtype=np.float32)

        conflicts: list[MemoryConflictItem] = []

        with self.engine.connection() as conn:
            active_rows = self.memory_repo.get_active_by_subcategory(
                conn=conn,
                category=payload.category.value,
                subcategory=payload.subcategory.value if payload.subcategory else None,
            )

            # Get active model for vector loading if semantic available
            active_model_row = self.embedding_repo.get_active_model(conn) if has_semantic else None
            embeddings_by_id = {}
            if active_model_row and candidate_vector is not None:
                stored_vectors = self.embedding_repo.get_active_embeddings(
                    conn,
                    model_name=active_model_row["model_name"],
                    model_version=active_model_row["model_version"],
                )
                for sv in stored_vectors:
                    embeddings_by_id[sv["memory_id"]] = unpack_vector(sv["embedding_blob"])

            for existing in active_rows:
                existing_text = existing["content"].strip()
                existing_tokens = _tokenize(existing_text)
                existing_slots = _extract_slots(existing_text)

                # 1. Similarity calculation (if semantic available)
                sim_score: Optional[float] = None
                if candidate_vector is not None and existing["id"] in embeddings_by_id:
                    sim_score = compute_cosine_similarity(candidate_vector, embeddings_by_id[existing["id"]])

                # 2. Lexical Jaccard overlap
                jaccard = len(candidate_tokens & existing_tokens) / max(len(candidate_tokens | existing_tokens), 1)

                # Precedence 1: Potential Duplicate
                is_duplicate = (
                    candidate_text.lower() == existing_text.lower()
                    or jaccard >= 0.85
                    or (sim_score is not None and sim_score >= payload.duplicate_threshold and jaccard >= 0.6)
                )

                if is_duplicate:
                    conflicts.append(
                        MemoryConflictItem(
                            conflicting_memory_id=existing["id"],
                            existing_content=existing_text,
                            subcategory=PersonalSubcategory(existing["subcategory"]) if existing["subcategory"] else None,
                            similarity_score=sim_score,
                            conflict_type=ConflictType.POTENTIAL_DUPLICATE,
                            explanation="Candidate statement is identical or nearly identical in lexical/semantic content.",
                            recommended_action="Reference or verify the existing active memory instead of duplicating.",
                        )
                    )
                    continue

                # Precedence 2: Potential Contradiction
                slot_clash = False
                for slot_key, slot_val in candidate_slots.items():
                    if slot_key in existing_slots and existing_slots[slot_key] != slot_val:
                        slot_clash = True
                        break

                polarity_clash = _detect_polarity_clash(candidate_text, existing_text)

                is_contradiction = slot_clash or polarity_clash or (
                    sim_score is not None and sim_score >= payload.contradiction_threshold and polarity_clash
                )

                if is_contradiction:
                    conflicts.append(
                        MemoryConflictItem(
                            conflicting_memory_id=existing["id"],
                            existing_content=existing_text,
                            subcategory=PersonalSubcategory(existing["subcategory"]) if existing["subcategory"] else None,
                            similarity_score=sim_score,
                            conflict_type=ConflictType.POTENTIAL_CONTRADICTION,
                            explanation=(
                                "Detected conflicting slot values or inverted polarity against an active statement."
                            ),
                            recommended_action="Use memory correction (/correct) to supersede the old fact or confirm variation.",
                        )
                    )
                    continue

                # Precedence 3: Related Active
                is_related = (
                    (sim_score is not None and sim_score >= payload.contradiction_threshold)
                    or (jaccard >= 0.45)
                )

                if is_related:
                    conflicts.append(
                        MemoryConflictItem(
                            conflicting_memory_id=existing["id"],
                            existing_content=existing_text,
                            subcategory=PersonalSubcategory(existing["subcategory"]) if existing["subcategory"] else None,
                            similarity_score=sim_score,
                            conflict_type=ConflictType.RELATED_ACTIVE,
                            explanation="Topical overlap with an active memory without direct contradiction detected.",
                            recommended_action="Consider linking via memory associations (/associations with relation 'relates_to').",
                        )
                    )

        # Determine highest severity
        highest_severity = None
        has_real_conflict = False
        if any(c.conflict_type == ConflictType.POTENTIAL_CONTRADICTION for c in conflicts):
            highest_severity = ConflictType.POTENTIAL_CONTRADICTION
            has_real_conflict = True
        elif any(c.conflict_type == ConflictType.POTENTIAL_DUPLICATE for c in conflicts):
            highest_severity = ConflictType.POTENTIAL_DUPLICATE
            has_real_conflict = True
        elif any(c.conflict_type == ConflictType.RELATED_ACTIVE for c in conflicts):
            highest_severity = ConflictType.RELATED_ACTIVE

        return MemoryConflictCheckResponse(
            candidate_content=candidate_text,
            has_conflicts=has_real_conflict,
            highest_severity_conflict=highest_severity,
            conflicts=conflicts,
            semantic_detection_available=has_semantic,
            analysis_capability=capability,
        )
