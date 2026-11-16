"""API router for procedural workflows, operational playbooks, and execution telemetry."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from edith_brain.core.contracts import (
    ProcedureCreate,
    ProcedureResponse,
    ProcedureStatus,
    ProcedureExecutionLogCreate,
    ProcedureExecutionLogResponse,
    ActorRole,
)
from edith_brain.services.procedural_service import ProceduralService
from edith_brain.api.deps import get_procedural_service, get_current_actor

router = APIRouter(prefix="/procedures", tags=["Procedural Memory"])


@router.get("/search", response_model=list[ProcedureResponse])
def search_procedures(
    q: str = Query(..., min_length=1),
    status_filter: Optional[ProcedureStatus] = Query(default=ProcedureStatus.ACTIVE, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    service: ProceduralService = Depends(get_procedural_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[ProcedureResponse]:
    """Search procedures by trigger condition, title, or description matching."""
    return service.search_procedures(query=q, status=status_filter, limit=limit)


@router.post("", response_model=ProcedureResponse, status_code=status.HTTP_201_CREATED)
def create_procedure(
    payload: ProcedureCreate,
    service: ProceduralService = Depends(get_procedural_service),
    actor: ActorRole = Depends(get_current_actor),
) -> ProcedureResponse:
    """Register a new repeatable workflow or operational procedure."""
    return service.create_procedure(payload)


@router.get("", response_model=list[ProcedureResponse])
def list_procedures(
    status_filter: Optional[ProcedureStatus] = Query(default=ProcedureStatus.ACTIVE, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: ProceduralService = Depends(get_procedural_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[ProcedureResponse]:
    """List procedures with status filtering and pagination."""
    return service.list_procedures(status=status_filter, limit=limit, offset=offset)


@router.get("/{procedure_id}", response_model=ProcedureResponse)
def get_procedure(
    procedure_id: str,
    service: ProceduralService = Depends(get_procedural_service),
    actor: ActorRole = Depends(get_current_actor),
) -> ProcedureResponse:
    """Retrieve procedure steps, validation checks, and telemetry."""
    return service.get_procedure(procedure_id)


@router.patch("/{procedure_id}/status", response_model=ProcedureResponse)
def update_procedure_status(
    procedure_id: str,
    new_status: ProcedureStatus = Query(..., alias="status"),
    service: ProceduralService = Depends(get_procedural_service),
    actor: ActorRole = Depends(get_current_actor),
) -> ProcedureResponse:
    """Update procedure lifecycle status (draft, active, deprecated)."""
    return service.update_status(procedure_id, new_status)


@router.post("/{procedure_id}/execute", response_model=ProcedureExecutionLogResponse)
def log_procedure_execution(
    procedure_id: str,
    payload: ProcedureExecutionLogCreate,
    service: ProceduralService = Depends(get_procedural_service),
    actor: ActorRole = Depends(get_current_actor),
) -> ProcedureExecutionLogResponse:
    """Log an execution run of a procedure and update success rate metrics."""
    return service.log_execution(procedure_id=procedure_id, payload=payload, actor=actor.value)


@router.get("/{procedure_id}/executions", response_model=list[ProcedureExecutionLogResponse])
def get_execution_logs(
    procedure_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    service: ProceduralService = Depends(get_procedural_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[ProcedureExecutionLogResponse]:
    """Retrieve execution history logs for a procedure."""
    return service.get_execution_logs(procedure_id=procedure_id, limit=limit)


@router.delete("/{procedure_id}", response_model=dict)
def delete_procedure(
    procedure_id: str,
    service: ProceduralService = Depends(get_procedural_service),
    actor: ActorRole = Depends(get_current_actor),
) -> dict:
    """Physically delete a procedure."""
    return service.delete_procedure(procedure_id)
