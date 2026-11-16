"""Unit tests for Phase B5 MemoryDecayEngine recency decay and dynamic scoring."""

from datetime import datetime, timezone, timedelta
import math
import pytest

from edith_brain.core.contracts import DecayConfig
from edith_brain.services.memory_decay_engine import MemoryDecayEngine
from edith_brain.storage.db import SQLiteEngine


def test_decay_score_zero_elapsed_time(test_engine: SQLiteEngine):
    """When elapsed time is 0, decayed score equals the base confidence."""
    engine = MemoryDecayEngine(engine=test_engine)
    t0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)

    score = engine.calculate_decay_score(
        base_confidence=0.9,
        created_at=t0.isoformat(),
        last_accessed_at=t0.isoformat(),
        reference_time=t0,
    )
    assert score == 0.9


def test_decay_score_at_exact_half_life(test_engine: SQLiteEngine):
    """At t = T_half, score should be exactly 50% of base confidence."""
    config = DecayConfig(default_half_life_days=30.0)
    engine = MemoryDecayEngine(engine=test_engine, config=config)
    t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t_after_half_life = t0 + timedelta(days=30)

    score = engine.calculate_decay_score(
        base_confidence=1.0,
        created_at=t0.isoformat(),
        last_accessed_at=None,
        reference_time=t_after_half_life,
    )
    # Expected: 1.0 * e^(-ln(2)) = 0.5
    assert abs(score - 0.5) < 0.01


def test_decay_score_subcategory_specific_half_life(test_engine: SQLiteEngine):
    """Preference (180d half life) decays much slower than project_context (30d half life)."""
    engine = MemoryDecayEngine(engine=test_engine)
    t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t_eval = t0 + timedelta(days=60)

    pref_score = engine.calculate_decay_score(
        base_confidence=1.0,
        created_at=t0.isoformat(),
        last_accessed_at=None,
        subcategory="preference",  # half-life: 180d
        reference_time=t_eval,
    )
    proj_score = engine.calculate_decay_score(
        base_confidence=1.0,
        created_at=t0.isoformat(),
        last_accessed_at=None,
        subcategory="project_context",  # half-life: 30d
        reference_time=t_eval,
    )

    # 60 days on 180d half-life: factor ~ 2^(-60/180) = 2^(-1/3) ~ 0.7937
    # 60 days on 30d half-life: factor ~ 2^(-60/30) = 2^(-2) = 0.25
    assert pref_score > proj_score
    assert abs(pref_score - 0.7937) < 0.02
    assert abs(proj_score - 0.25) < 0.02


def test_combined_relevance_calculation(test_engine: SQLiteEngine):
    """Verify combination of similarity, decay, and access frequency bonus."""
    config = DecayConfig(
        similarity_weight=0.7,
        recency_weight=0.2,
        access_weight=0.1,
    )
    engine = MemoryDecayEngine(engine=test_engine, config=config)

    # High similarity (0.9), fresh (decay=0.9), accessed 5 times
    combined_high = engine.calculate_combined_relevance(
        similarity_score=0.9,
        decay_score=0.9,
        access_count=5,
    )

    # Low similarity (0.3), stale (decay=0.2), never accessed
    combined_low = engine.calculate_combined_relevance(
        similarity_score=0.3,
        decay_score=0.2,
        access_count=0,
    )

    assert combined_high > combined_low
    assert combined_high <= 1.0
    assert combined_low >= 0.0
