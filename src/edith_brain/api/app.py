"""FastAPI application factory, lifespan management, and global exception handlers."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from edith_brain.core.config import get_settings
from edith_brain.core.exceptions import (
    BrainCoreException,
    NotFoundError,
    ConflictError,
    ValidationError,
    SecurityError,
    StorageError,
    MigrationError,
)
from edith_brain.storage.db import SQLiteEngine
from edith_brain.storage.migrations import MigrationRunner
from edith_brain.api.v1.router import api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    settings.ensure_directories()

    # Run database schema migrations idempotently on startup
    engine = SQLiteEngine(db_path=settings.database_path, busy_timeout_ms=settings.sqlite_busy_timeout_ms)
    runner = MigrationRunner(engine=engine)
    runner.run_migrations()

    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="E.D.I.T.H. Brain Core - Independent Knowledge and Memory Foundation",
        lifespan=lifespan,
    )

    # Global Exception Handlers
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "type": "urn:edith:error:not-found",
                "title": "Resource Not Found",
                "status": 404,
                "detail": exc.message,
                "instance": str(request.url.path),
            },
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "type": "urn:edith:error:conflict",
                "title": "Resource Conflict",
                "status": 409,
                "detail": exc.message,
                "instance": str(request.url.path),
            },
        )

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "type": "urn:edith:error:validation",
                "title": "Domain Validation Error",
                "status": 422,
                "detail": exc.message,
                "instance": str(request.url.path),
            },
        )

    @app.exception_handler(SecurityError)
    async def security_handler(request: Request, exc: SecurityError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "type": "urn:edith:error:security",
                "title": "Security Invariant Violation",
                "status": 403,
                "detail": exc.message,
                "instance": str(request.url.path),
            },
        )

    @app.exception_handler(StorageError)
    async def storage_handler(request: Request, exc: StorageError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "urn:edith:error:storage",
                "title": "Storage Engine Error",
                "status": 500,
                "detail": exc.message,
                "instance": str(request.url.path),
            },
        )

    @app.exception_handler(BrainCoreException)
    async def generic_brain_core_handler(request: Request, exc: BrainCoreException):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "urn:edith:error:general",
                "title": "Brain Core Domain Error",
                "status": 500,
                "detail": exc.message,
                "instance": str(request.url.path),
            },
        )

    app.include_router(api_v1_router)

    return app
