"""Unit tests for Phase B4 Procedural Memory contracts and validation."""

import pytest
from pydantic import ValidationError

from edith_brain.core.contracts import (
    ProcedureCreate,
    ProcedureResponse,
    ProcedureStep,
    ProcedureStatus,
    ProcedureExecutionLogCreate,
    ProcedureExecutionLogResponse,
)


def test_procedure_step_valid():
    """Verify standard ProcedureStep initialization."""
    step = ProcedureStep(
        step_number=1,
        action="Check disk space",
        expected_outcome="Free space > 10GB",
        fallback_action="Run disk cleanup utility",
    )
    assert step.step_number == 1
    assert step.action == "Check disk space"
    assert step.expected_outcome == "Free space > 10GB"
    assert step.fallback_action == "Run disk cleanup utility"


def test_procedure_step_number_must_be_positive():
    """Verify step_number must be >= 1."""
    with pytest.raises(ValidationError):
        ProcedureStep(
            step_number=0,
            action="Invalid step number",
        )


def test_procedure_create_valid():
    """Verify ProcedureCreate schema with valid ordered steps."""
    proc = ProcedureCreate(
        title="Deploy Brain Core Service",
        description="Standard deployment procedure for local instance",
        trigger_conditions=["User issues deploy command"],
        steps=[
            ProcedureStep(step_number=1, action="Verify python version"),
            ProcedureStep(step_number=2, action="Run database migrations"),
            ProcedureStep(step_number=3, action="Start uvicorn server"),
        ],
        version="1.0.0",
        metadata={"tags": ["deployment", "operations"]},
    )
    assert proc.title == "Deploy Brain Core Service"
    assert len(proc.steps) == 3
    assert proc.version == "1.0.0"


def test_procedure_steps_must_be_non_empty():
    """Verify procedure requires at least one step."""
    with pytest.raises(ValidationError):
        ProcedureCreate(
            title="Empty Procedure",
            description="Empty procedure",
            trigger_conditions=["When something happens"],
            steps=[],
        )


def test_procedure_steps_must_be_strictly_sequential():
    """Verify step numbers must start at 1 and be sequentially increasing."""
    # Starting at 2
    with pytest.raises(ValidationError) as exc:
        ProcedureCreate(
            title="Broken Step Sequence",
            description="Description",
            trigger_conditions=["Trigger"],
            steps=[
                ProcedureStep(step_number=2, action="First step says 2"),
            ],
        )
    assert "start at 1" in str(exc.value)

    # Missing step 2
    with pytest.raises(ValidationError) as exc:
        ProcedureCreate(
            title="Gapped Step Sequence",
            description="Description",
            trigger_conditions=["Trigger"],
            steps=[
                ProcedureStep(step_number=1, action="Step 1"),
                ProcedureStep(step_number=3, action="Step 3 directly"),
            ],
        )
    assert "strictly sequential" in str(exc.value)


def test_procedure_version_format():
    """Verify semantic version string validation."""
    with pytest.raises(ValidationError):
        ProcedureCreate(
            title="Bad Version Proc",
            description="Description",
            trigger_conditions=["Trigger"],
            steps=[ProcedureStep(step_number=1, action="Step 1")],
            version="v1-final",  # Non-semantic version
        )


def test_procedure_execution_log_contracts():
    """Verify ProcedureExecutionLogCreate validation."""
    log = ProcedureExecutionLogCreate(
        execution_status="success",
        duration_seconds=0.125,
        notes="All checks passed.",
    )
    assert log.execution_status == "success"
    assert log.duration_seconds == 0.125

    with pytest.raises(ValidationError):
        ProcedureExecutionLogCreate(
            execution_status="invalid_status",
            duration_seconds=1.0,
        )

    with pytest.raises(ValidationError):
        ProcedureExecutionLogCreate(
            execution_status="success",
            duration_seconds=-5.0,
        )
