"""API router for episodic events, conversation history, and timeline querying."""

from fastapi import APIRouter, Depends, Query, status

from edith_brain.core.contracts import (
    EpisodeCreate,
    EpisodeResponse,
    EpisodeTimelineRequest,
    EpisodeLinkCreate,
    MemoryLinkCreate,
    MemoryLinkResponse,
    ActorRole,
)
from edith_brain.services.episodic_service import EpisodicService
from edith_brain.api.deps import get_episodic_service, get_current_actor

router = APIRouter(prefix="/episodes", tags=["Episodic Memory"])


@router.post("/timeline", response_model=list[EpisodeResponse])
def get_timeline(
    payload: EpisodeTimelineRequest,
    service: EpisodicService = Depends(get_episodic_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[EpisodeResponse]:
    """Query chronological or significance-filtered episodes timeline."""
    return service.get_timeline(payload)


@router.get("/sessions", response_model=list[dict])
def list_sessions(
    limit: int = Query(default=50, ge=1, le=500),
    service: EpisodicService = Depends(get_episodic_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[dict]:
    """List aggregated sessions with start time, activity, and event counts."""
    return service.list_sessions(limit=limit)


@router.post("", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
def create_episode(
    payload: EpisodeCreate,
    service: EpisodicService = Depends(get_episodic_service),
    actor: ActorRole = Depends(get_current_actor),
) -> EpisodeResponse:
    """Record a discrete episodic event, conversation, or task session."""
    return service.create_episode(payload)


@router.get("/{episode_id}", response_model=EpisodeResponse)
def get_episode(
    episode_id: str,
    service: EpisodicService = Depends(get_episodic_service),
    actor: ActorRole = Depends(get_current_actor),
) -> EpisodeResponse:
    """Retrieve an episodic event by ID."""
    return service.get_episode(episode_id)


@router.delete("/{episode_id}", response_model=dict)
def delete_episode(
    episode_id: str,
    service: EpisodicService = Depends(get_episodic_service),
    actor: ActorRole = Depends(get_current_actor),
) -> dict:
    """Delete an episodic event."""
    return service.delete_episode(episode_id)


@router.post("/{episode_id}/links", response_model=MemoryLinkResponse, status_code=status.HTTP_201_CREATED)
def link_episode(
    episode_id: str,
    payload: EpisodeLinkCreate,
    service: EpisodicService = Depends(get_episodic_service),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryLinkResponse:
    """Create a link between this episode and a procedure or personal memory."""
    full_link = MemoryLinkCreate(
        episode_id=episode_id,
        procedure_id=payload.procedure_id,
        memory_id=payload.memory_id,
        link_type=payload.link_type,
        metadata=payload.metadata,
    )
    return service.create_link(full_link)


@router.get("/{episode_id}/links", response_model=list[MemoryLinkResponse])
def get_episode_links(
    episode_id: str,
    service: EpisodicService = Depends(get_episodic_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[MemoryLinkResponse]:
    """Retrieve all cross-domain memory links for this episode."""
    return service.get_episode_links(episode_id)
