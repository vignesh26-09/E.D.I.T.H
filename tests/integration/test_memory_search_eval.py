"""Integration tests for memory retrieval modes, fallback semantics, and benchmark evaluation."""

import json
import time
from pathlib import Path
from edith_brain.core.contracts import (
    MemoryCreate,
    MemorySearchRequest,
    SearchMode,
    MemoryCategory,
    PersonalSubcategory,
)
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.retrieval.memory_search_service import MemorySearchService
from edith_brain.storage.db import SQLiteEngine


def test_memory_search_fallback_when_neural_model_unconfigured(test_engine: SQLiteEngine):
    """Semantic and hybrid search fall back to keyword FTS5 when no neural model is active."""
    mem_service = MemoryService(engine=test_engine)
    search_service = MemorySearchService(engine=test_engine)

    # 1. Ingest memory
    mem_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="Prefers writing backend code in Python and FastAPI.",
        )
    )

    # 2. Search in SEMANTIC mode without configured active model
    resp = search_service.search(
        MemorySearchRequest(
            query="Python FastAPI backend",
            mode=SearchMode.SEMANTIC,
        )
    )

    assert resp.effective_mode == SearchMode.KEYWORD
    assert resp.fallback_applied is True
    assert "No active neural semantic model" in resp.fallback_reason
    assert resp.total_results >= 1
    assert "Python" in resp.results[0].memory.content


def test_memory_search_quick_benchmark_evaluation(test_engine: SQLiteEngine):
    """Execute quick 5-query benchmark corpus and evaluate Precision@3, Recall@3, and MRR."""
    benchmark_path = Path(__file__).parent.parent / "fixtures" / "memory_search_quick_benchmark.json"
    benchmark_data = json.loads(benchmark_path.read_text(encoding="utf-8"))

    mem_service = MemoryService(engine=test_engine)
    search_service = MemorySearchService(engine=test_engine)

    # Ingest benchmark memories
    id_map = {}
    for item in benchmark_data["memories"]:
        created = mem_service.create_memory(
            MemoryCreate(
                category=MemoryCategory(item["category"]),
                subcategory=PersonalSubcategory(item["subcategory"]),
                content=item["content"],
                confidence=item["confidence"],
                tags=item["tags"],
            )
        )
        id_map[item["id"]] = created.id

    latencies = []
    precisions = []
    recalls = []
    reciprocal_ranks = []

    for q in benchmark_data["queries"]:
        query_text = q["query"]
        expected_created_ids = {id_map[eid] for eid in q["expected_memory_ids"]}

        start_time = time.perf_counter()
        search_res = search_service.search(
            MemorySearchRequest(query=query_text, mode=SearchMode.KEYWORD, limit=3)
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        latencies.append(elapsed_ms)

        retrieved_ids = [r.memory.id for r in search_res.results]
        hits = [mid for mid in retrieved_ids if mid in expected_created_ids]

        # Top-1 Precision (Precision@1) & Top-3 Recall (Recall@3)
        p_at_1 = 1.0 if retrieved_ids and retrieved_ids[0] in expected_created_ids else 0.0
        r_at_3 = len(hits) / max(len(expected_created_ids), 1)

        precisions.append(p_at_1)
        recalls.append(r_at_3)

        # MRR
        rr = 0.0
        for rank, mid in enumerate(retrieved_ids, start=1):
            if mid in expected_created_ids:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

    mean_precision = sum(precisions) / len(precisions)
    mean_recall = sum(recalls) / len(recalls)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)

    # Latencies
    latencies.sort()
    p50_latency = latencies[len(latencies) // 2]
    p95_latency = latencies[int(len(latencies) * 0.95)]

    # Assert evaluation criteria
    assert mean_precision >= 0.80, f"Mean Precision@1 was {mean_precision}"
    assert mean_recall >= 0.80, f"Mean Recall@3 was {mean_recall}"
    assert mrr >= 0.80, f"MRR was {mrr}"
    assert p50_latency < 50.0, f"p50 latency too high: {p50_latency}ms"
    assert mean_recall >= 0.60, f"Mean Recall@3 was {mean_recall}"
    assert mrr >= 0.70, f"MRR was {mrr}"
    assert p50_latency < 50.0, f"p50 latency too high: {p50_latency}ms"
