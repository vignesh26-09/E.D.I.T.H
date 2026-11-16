"""Integration tests for Phase B5 evaluation benchmarks and metrics computation."""

import pytest
from fastapi.testclient import TestClient

from edith_brain.core.contracts import BenchmarkRunRequest
from edith_brain.services.evaluation_benchmark_service import EvaluationBenchmarkService


def test_evaluation_benchmark_execution(
    evaluation_benchmark_service: EvaluationBenchmarkService,
):
    """Test full execution of retrieval metrics, integrity audits, and latency profiling."""
    report = evaluation_benchmark_service.run_benchmark(
        request=BenchmarkRunRequest(run_type="full", k_values=[1, 3, 5])
    )

    assert report.run_id is not None
    assert report.run_type == "full"
    assert report.execution_time_ms > 0.0

    # 1. Retrieval Metrics
    retrieval = report.retrieval_metrics
    assert "p@1" in retrieval.precision_at_k
    assert "r@1" in retrieval.recall_at_k
    assert "ndcg@1" in retrieval.ndcg_at_k
    assert retrieval.mrr > 0.0
    assert retrieval.mean_latency_ms >= 0.0
    assert retrieval.p95_latency_ms >= 0.0

    # 2. Integrity Metrics
    integrity = report.integrity_metrics
    assert integrity.citation_parentage_accuracy == 1.0
    assert integrity.acyclic_association_rate == 1.0
    assert integrity.verification_state_machine_compliance == 1.0

    # 3. System profile
    assert report.system_profile["sqlite_wal"] is True


def test_evaluation_benchmark_api(client: TestClient):
    """Test REST API endpoint for triggering benchmarks."""
    resp = client.post(
        "/api/v1/evaluation/benchmark",
        json={"run_type": "full", "k_values": [1, 3, 5]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "run_id" in data
    assert "retrieval_metrics" in data
    assert "integrity_metrics" in data
    assert data["retrieval_metrics"]["mrr"] > 0.0
