"""Domain service orchestrating procedural knowledge, playbooks, and execution telemetry."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from edith_brain.core.contracts import (
    ProcedureCreate,
    ProcedureResponse,
    ProcedureStep,
    ProcedureStatus,
    ProcedureExecutionLogCreate,
    ProcedureExecutionLogResponse,
)
from edith_brain.core.exceptions import NotFoundError, ValidationError
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.procedural_repository import ProceduralRepository
from edith_brain.services.retrieval.query_parser import sanitize_fts5_query


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_procedure_response(row) -> ProcedureResponse:
    steps_raw = json.loads(row["steps_json"])
    steps = [ProcedureStep(**s) for s in steps_raw]

    exec_count = row["execution_count"]
    succ_count = row["success_count"]
    succ_rate = round(float(succ_count) / float(exec_count), 4) if exec_count > 0 else 0.0

    return ProcedureResponse(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        version=row["version"],
        status=ProcedureStatus(row["status"]),
        trigger_conditions=json.loads(row["trigger_conditions_json"]),
        prerequisites=json.loads(row["prerequisites_json"]),
        steps=steps,
        execution_count=exec_count,
        success_count=succ_count,
        success_rate=succ_rate,
        last_executed_at=row["last_executed_at"],
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ProceduralService:
    """Manages operational playbooks, multi-step routines, and execution tracking."""

    def __init__(
        self,
        engine: SQLiteEngine,
        procedural_repo: ProceduralRepository | None = None,
    ) -> None:
        self.engine = engine
        self.procedural_repo = procedural_repo or ProceduralRepository()

    def create_procedure(self, payload: ProcedureCreate) -> ProcedureResponse:
        """Register a new repeatable workflow or operational procedure."""
        now = _utc_now_iso()
        procedure_id = str(uuid.uuid4())

        # Validate step order
        step_numbers = [s.step_number for s in payload.steps]
        if step_numbers != list(range(1, len(payload.steps) + 1)):
            raise ValidationError("Procedure steps must be numbered sequentially starting from 1.")

        proc_dict = {
            "id": procedure_id,
            "title": payload.title,
            "description": payload.description,
            "version": payload.version,
            "status": payload.status.value,
            "trigger_conditions_json": json.dumps(payload.trigger_conditions),
            "prerequisites_json": json.dumps(payload.prerequisites),
            "steps_json": json.dumps([s.model_dump() for s in payload.steps]),
            "execution_count": 0,
            "success_count": 0,
            "last_executed_at": None,
            "metadata_json": json.dumps(payload.metadata),
            "created_at": now,
            "updated_at": now,
        }

        with self.engine.write_transaction() as conn:
            self.procedural_repo.insert(conn, proc_dict)

        with self.engine.connection() as conn:
            row = self.procedural_repo.get_by_id(conn, procedure_id)
            return _row_to_procedure_response(row)

    def get_procedure(self, procedure_id: str) -> ProcedureResponse:
        """Fetch a procedure by ID."""
        with self.engine.connection() as conn:
            row = self.procedural_repo.get_by_id(conn, procedure_id)
            if not row:
                raise NotFoundError(f"Procedure with ID '{procedure_id}' not found.")
            return _row_to_procedure_response(row)

    def update_status(self, procedure_id: str, new_status: ProcedureStatus) -> ProcedureResponse:
        """Update procedure lifecycle status (draft, active, deprecated)."""
        now = _utc_now_iso()
        with self.engine.write_transaction() as conn:
            row = self.procedural_repo.get_by_id(conn, procedure_id)
            if not row:
                raise NotFoundError(f"Procedure with ID '{procedure_id}' not found.")
            self.procedural_repo.update_status(conn, procedure_id, new_status.value, now)

        with self.engine.connection() as conn:
            updated = self.procedural_repo.get_by_id(conn, procedure_id)
            return _row_to_procedure_response(updated)

    def log_execution(
        self,
        procedure_id: str,
        payload: ProcedureExecutionLogCreate,
        actor: str = "LOCAL_USER",
    ) -> ProcedureExecutionLogResponse:
        """Record an execution run of a procedure and update success metrics."""
        now = _utc_now_iso()

        with self.engine.write_transaction() as conn:
            row = self.procedural_repo.get_by_id(conn, procedure_id)
            if not row:
                raise NotFoundError(f"Procedure with ID '{procedure_id}' not found.")

            log_id = self.procedural_repo.record_execution(
                conn=conn,
                procedure_id=procedure_id,
                executed_at=now,
                execution_status=payload.execution_status,
                duration_seconds=payload.duration_seconds,
                execution_actor=actor,
                step_results_json=json.dumps(payload.step_results),
                error_message=payload.error_message,
                notes=payload.notes,
            )

        return ProcedureExecutionLogResponse(
            id=log_id,
            procedure_id=procedure_id,
            executed_at=now,
            execution_status=payload.execution_status,
            duration_seconds=payload.duration_seconds,
            execution_actor=actor,
            step_results=payload.step_results,
            error_message=payload.error_message,
            notes=payload.notes,
        )

    def list_procedures(
        self,
        status: Optional[ProcedureStatus] = ProcedureStatus.ACTIVE,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProcedureResponse]:
        """List procedures with pagination and status filtering."""
        with self.engine.connection() as conn:
            rows = self.procedural_repo.list(
                conn=conn,
                status=status.value if status else None,
                limit=limit,
                offset=offset,
            )
            return [_row_to_procedure_response(r) for r in rows]

    def search_procedures(
        self,
        query: str,
        status: Optional[ProcedureStatus] = ProcedureStatus.ACTIVE,
        limit: int = 20,
    ) -> list[ProcedureResponse]:
        """Search procedures by trigger condition, title, or description matching."""
        sanitized = sanitize_fts5_query(query, match_mode="OR")
        if not sanitized or sanitized == '""':
            return []

        with self.engine.connection() as conn:
            rows = self.procedural_repo.search_fts(
                conn=conn,
                sanitized_query=sanitized,
                status=status.value if status else None,
                limit=limit,
            )
            return [_row_to_procedure_response(r) for r in rows]

    def get_execution_logs(
        self,
        procedure_id: str,
        limit: int = 50,
    ) -> list[ProcedureExecutionLogResponse]:
        """Fetch execution telemetry logs for a procedure."""
        with self.engine.connection() as conn:
            row = self.procedural_repo.get_by_id(conn, procedure_id)
            if not row:
                raise NotFoundError(f"Procedure with ID '{procedure_id}' not found.")
            rows = self.procedural_repo.get_execution_logs(conn, procedure_id, limit=limit)
            return [
                ProcedureExecutionLogResponse(
                    id=r["id"],
                    procedure_id=r["procedure_id"],
                    executed_at=r["executed_at"],
                    execution_status=r["execution_status"],
                    duration_seconds=r["duration_seconds"],
                    execution_actor=r["execution_actor"],
                    step_results=json.loads(r["step_results_json"]),
                    error_message=r["error_message"],
                    notes=r["notes"],
                )
                for r in rows
            ]

    def delete_procedure(self, procedure_id: str) -> dict:
        """Physically delete a procedure."""
        with self.engine.write_transaction() as conn:
            count = self.procedural_repo.delete(conn, procedure_id)
            if count == 0:
                raise NotFoundError(f"Procedure with ID '{procedure_id}' not found.")
        return {"id": procedure_id, "deleted": True}
