"""Engine for computing memory recency decay, access frequency weighting, and dynamic scoring."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional, Sequence

from edith_brain.core.contracts import (
    DecayConfig,
    MemoryDecayScore,
)
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.intelligence_repository import IntelligenceRepository


def _parse_iso_to_utc(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        # SQLite strftime or ISO format
        cleaned = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


class MemoryDecayEngine:
    """Computes exponential half-life decay and dynamic relevance scoring for personal memories."""

    def __init__(
        self,
        engine: SQLiteEngine,
        config: Optional[DecayConfig] = None,
        intel_repo: Optional[IntelligenceRepository] = None,
    ) -> None:
        self.engine = engine
        self.config = config or DecayConfig()
        self.intel_repo = intel_repo or IntelligenceRepository()

    def calculate_decay_score(
        self,
        base_confidence: float,
        created_at: str,
        last_accessed_at: Optional[str],
        subcategory: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> float:
        """Calculate the decayed confidence score for a memory based on time elapsed."""
        now = reference_time or datetime.now(timezone.utc)
        last_active = _parse_iso_to_utc(last_accessed_at) or _parse_iso_to_utc(created_at)

        if not last_active:
            return base_confidence

        delta_seconds = max(0.0, (now - last_active).total_seconds())
        delta_days = delta_seconds / 86400.0

        # Subcategory-specific half-life
        half_life_days = self.config.default_half_life_days
        if subcategory and subcategory in self.config.subcategory_half_lives:
            half_life_days = self.config.subcategory_half_lives[subcategory]

        # Decay equation: S(t) = S0 * e^(-lambda * t), where lambda = ln(2) / T_half
        decay_constant = math.log(2.0) / max(0.1, half_life_days)
        decay_factor = math.exp(-decay_constant * delta_days)

        return round(base_confidence * decay_factor, 4)

    def calculate_combined_relevance(
        self,
        similarity_score: float,
        decay_score: float,
        access_count: int,
    ) -> float:
        """Combine retrieval similarity, recency decay, and access frequency into a single score."""
        w_sim = self.config.similarity_weight
        w_decay = self.config.recency_weight
        w_access = self.config.access_weight

        # Normalize weights if sum != 1.0
        total_w = w_sim + w_decay + w_access
        if total_w > 0:
            w_sim /= total_w
            w_decay /= total_w
            w_access /= total_w

        # Frequency bonus with diminishing returns
        frequency_bonus = min(1.0, math.log1p(max(0, access_count)) / math.log(10.0)) if access_count > 0 else 0.0

        final_score = (w_sim * similarity_score) + (w_decay * decay_score) + (w_access * frequency_bonus)
        return round(final_score, 4)

    def touch_memories(self, memory_ids: list[str]) -> int:
        """Record retrieval/access touch on a set of memories."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.engine.write_transaction() as conn:
            return self.intel_repo.touch_memories(conn, memory_ids, now_iso)

    def get_decay_evaluation(
        self,
        memory_id: str,
        reference_time: Optional[datetime] = None,
    ) -> Optional[MemoryDecayScore]:
        """Inspect decay and telemetry metrics for a single memory."""
        with self.engine.connection() as conn:
            row = self.intel_repo.get_memory_access_telemetry(conn, memory_id)
            if not row:
                return None

            base_conf = float(row["confidence"])
            access_cnt = int(row["access_count"])
            last_acc = row["last_accessed_at"]
            created = row["created_at"]
            subcat = row["subcategory"]

            decay = self.calculate_decay_score(
                base_confidence=base_conf,
                created_at=created,
                last_accessed_at=last_acc,
                subcategory=subcat,
                reference_time=reference_time,
            )

            # Combined baseline assuming neutral 1.0 match
            effective = self.calculate_combined_relevance(
                similarity_score=1.0,
                decay_score=decay,
                access_count=access_cnt,
            )

            return MemoryDecayScore(
                memory_id=memory_id,
                base_confidence=base_conf,
                decay_score=decay,
                access_count=access_cnt,
                last_accessed_at=last_acc,
                effective_score=effective,
            )
