"""API router for running quantitative evaluation benchmarks and inspecting system metrics."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from edith_brain.core.contracts import (
    BenchmarkRunRequest,
    BenchmarkReportResponse,
    ActorRole,
)
from edith_brain.services.evaluation_benchmark_service import EvaluationBenchmarkService
from edith_brain.api.deps import get_evaluation_benchmark_service, get_current_actor

router = APIRouter(prefix="/evaluation", tags=["Evaluation & Benchmarks"])


@router.post("/benchmark", response_model=BenchmarkReportResponse)
def run_benchmark(
    payload: BenchmarkRunRequest,
    service: EvaluationBenchmarkService = Depends(get_evaluation_benchmark_service),
    actor: ActorRole = Depends(get_current_actor),
) -> BenchmarkReportResponse:
    """Execute evaluation benchmark suite measuring retrieval metrics, integrity, and latency."""
    return service.run_benchmark(payload)
