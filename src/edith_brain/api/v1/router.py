"""Aggregated API v1 router."""

from fastapi import APIRouter
from edith_brain.api.v1.health import router as health_router
from edith_brain.api.v1.memories import router as memories_router
from edith_brain.api.v1.documents import router as documents_router
from edith_brain.api.v1.retrieval import router as retrieval_router
from edith_brain.api.v1.episodes import router as episodes_router
from edith_brain.api.v1.procedures import router as procedures_router
from edith_brain.api.v1.intelligence import router as intelligence_router
from edith_brain.api.v1.evaluation import router as evaluation_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(memories_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(retrieval_router)
api_v1_router.include_router(episodes_router)
api_v1_router.include_router(procedures_router)
api_v1_router.include_router(intelligence_router)
api_v1_router.include_router(evaluation_router)
