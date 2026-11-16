"""Health check and system inspection endpoints."""

from datetime import datetime, timezone
import sqlite3
from fastapi import APIRouter, Depends
from edith_brain.core.config import Settings, get_settings
from edith_brain.core.contracts import HealthResponse, SystemInfoResponse, MemoryCategory, PersonalSubcategory
from edith_brain.storage.db import SQLiteEngine
from edith_brain.api.deps import get_engine

router = APIRouter(prefix="", tags=["System & Health"])


@router.get("/health", response_model=HealthResponse)
def get_health(
    settings: Settings = Depends(get_settings),
    engine: SQLiteEngine = Depends(get_engine),
) -> HealthResponse:
    """Return runtime health, SQLite connection state, and PRAGMA status."""
    db_health = engine.check_health()
    return HealthResponse(
        status="healthy" if db_health["connected"] else "degraded",
        app_version=settings.app_version,
        environment=settings.environment,
        db_connected=db_health["connected"],
        wal_mode=db_health["wal_mode"],
        foreign_keys_on=db_health["foreign_keys_on"],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/system/info", response_model=SystemInfoResponse)
def get_system_info(
    settings: Settings = Depends(get_settings),
    engine: SQLiteEngine = Depends(get_engine),
) -> SystemInfoResponse:
    """Return core capabilities and supported memory categories."""
    db_health = engine.check_health()

    # Check FTS5 support natively
    fts5_ok = False
    try:
        with engine.connection() as conn:
            conn.execute("SELECT * FROM pragma_compile_options WHERE compile_options LIKE '%ENABLE_FTS5%';")
            fts5_ok = True
    except Exception:
        pass

    return SystemInfoResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        sqlite_version=db_health["sqlite_version"],
        fts5_supported=fts5_ok,
        supported_memory_categories=[c.value for c in MemoryCategory],
        supported_personal_subcategories=[s.value for s in PersonalSubcategory],
        max_file_size_bytes=settings.max_file_size_bytes,
    )
