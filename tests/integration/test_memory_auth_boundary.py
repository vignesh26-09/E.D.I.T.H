"""Integration tests for local authentication trust boundary and actor enforcement."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from edith_brain.core.config import Settings
from edith_brain.core.security import get_or_create_local_token
from edith_brain.api.app import create_app
from edith_brain.storage.db import SQLiteEngine
from edith_brain.storage.migrations import MigrationRunner
from edith_brain.api.deps import get_settings, get_engine


@pytest.fixture
def auth_enabled_client(tmp_path: Path):
    """Test client with authentication explicitly enabled."""
    token_file = tmp_path / ".edith_token"
    settings = Settings(
        app_name="E.D.I.T.H. Brain Core [Auth Test]",
        environment="test",
        base_dir=tmp_path,
        database_path=tmp_path / "auth_test.db",
        storage_raw_dir=tmp_path / "raw",
        storage_extracted_dir=tmp_path / "extracted",
        local_token_path=token_file,
        auth_enabled=True,
    )
    settings.ensure_directories()
    engine = SQLiteEngine(db_path=settings.database_path)
    runner = MigrationRunner(engine=engine)
    runner.run_migrations()

    token = get_or_create_local_token(token_file)

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_engine] = lambda: engine

    with TestClient(app) as test_client:
        yield test_client, token


def test_auth_health_endpoint_exempt(auth_enabled_client):
    """Health check endpoint is exempt from authentication."""
    client, _ = auth_enabled_client
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_auth_missing_token_returns_401(auth_enabled_client):
    """Protected endpoints reject requests missing the bearer token with 401."""
    client, _ = auth_enabled_client
    resp = client.get("/api/v1/memories")
    assert resp.status_code == 401
    assert "bearer token required" in resp.json()["detail"]


def test_auth_invalid_token_returns_401(auth_enabled_client):
    """Protected endpoints reject invalid bearer tokens with 401."""
    client, _ = auth_enabled_client
    resp = client.get("/api/v1/memories", headers={"Authorization": "Bearer invalid_secret_token"})
    assert resp.status_code == 401
    assert "invalid authentication token" in resp.json()["detail"]


def test_auth_valid_token_allows_access(auth_enabled_client):
    """Valid bearer token grants access."""
    client, token = auth_enabled_client
    resp = client.get("/api/v1/memories", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_system_pipeline_header_forbidden(auth_enabled_client):
    """External requests attempting to claim SYSTEM_PIPELINE actor role receive 403."""
    client, token = auth_enabled_client
    resp = client.get(
        "/api/v1/memories",
        headers={"Authorization": f"Bearer {token}", "X-Edith-Actor": "SYSTEM_PIPELINE"},
    )
    assert resp.status_code == 403
    assert "SYSTEM_PIPELINE" in resp.json()["detail"]
