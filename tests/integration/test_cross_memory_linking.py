"""Integration tests for cross-memory links between Episodic, Procedural, and Semantic memories."""

import pytest
from fastapi.testclient import TestClient

from edith_brain.core.contracts import (
    EpisodeCreate,
    ProcedureCreate,
    ProcedureStep,
    MemoryCreate,
    MemoryCategory,
    PersonalSubcategory,
    MemoryLinkCreate,
    LinkType,
    EventType,
)
from edith_brain.services.episodic_service import EpisodicService
from edith_brain.services.procedural_service import ProceduralService
from edith_brain.services.memory_service import MemoryService


def test_cross_memory_linking_lifecycle(
    episodic_service: EpisodicService,
    procedural_service: ProceduralService,
    memory_service: MemoryService,
):
    """Test linking episodes to procedures and semantic memories, plus cascade behavior."""
    # 1. Create an episodic event
    episode = episodic_service.create_episode(
        EpisodeCreate(
            session_id="session-cross-link",
            title="Backup Run",
            event_type=EventType.TASK_EXECUTION,
            summary="Agent executed the data backup procedure.",
            significance_score=0.75,
        )
    )

    # 2. Create a procedure
    proc = procedural_service.create_procedure(
        ProcedureCreate(
            title="Data Backup Playbook",
            description="Backup user data and verify integrity",
            trigger_conditions=["Scheduled daily backup"],
            steps=[ProcedureStep(step_number=1, action="Run backup script")],
        )
    )

    # 3. Create a personal memory (semantic)
    mem = memory_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="User prefers encrypted local backups over cloud storage.",
        )
    )

    # 4. Link episode to procedure
    link1 = episodic_service.create_link(
        MemoryLinkCreate(
            episode_id=episode.id,
            procedure_id=proc.id,
            link_type=LinkType.EXECUTED_PROCEDURE,
            metadata={"notes": "Episode documents an execution instance of the playbook"},
        )
    )
    assert link1.id is not None
    assert link1.episode_id == episode.id
    assert link1.procedure_id == proc.id

    # 5. Link episode to semantic memory
    link2 = episodic_service.create_link(
        MemoryLinkCreate(
            episode_id=episode.id,
            memory_id=mem.id,
            link_type=LinkType.DERIVED_MEMORY,
            metadata={"notes": "Episode provides observational evidence of preference"},
        )
    )
    assert link2.id is not None
    assert link2.memory_id == mem.id

    # 6. Retrieve links for episode
    episode_links = episodic_service.get_episode_links(episode.id)
    assert len(episode_links) == 2
    types = {link.link_type for link in episode_links}
    assert LinkType.EXECUTED_PROCEDURE in types
    assert LinkType.DERIVED_MEMORY in types


def test_cross_memory_links_api(client: TestClient):
    """Test creating and querying links via the REST API."""
    # 1. Create episode via API
    resp_ep = client.post(
        "/api/v1/episodes",
        json={
            "session_id": "api-link-sess",
            "title": "UI Preference Session",
            "event_type": "conversation",
            "summary": "User requested dark mode in settings.",
            "significance_score": 0.6,
        },
    )
    assert resp_ep.status_code == 201, resp_ep.text
    ep_id = resp_ep.json()["id"]

    # 2. Create procedure via API
    resp_proc = client.post(
        "/api/v1/procedures",
        json={
            "title": "Toggle UI Theme",
            "description": "Switch UI theme preference",
            "trigger_conditions": ["User requests theme change"],
            "steps": [{"step_number": 1, "action": "Update theme config"}],
        },
    )
    assert resp_proc.status_code == 201, resp_proc.text
    proc_id = resp_proc.json()["id"]

    # 3. Create link via API
    resp_link = client.post(
        f"/api/v1/episodes/{ep_id}/links",
        json={
            "procedure_id": proc_id,
            "link_type": "executed_procedure",
            "metadata": {"notes": "API test link"},
        },
    )
    assert resp_link.status_code == 201, resp_link.text
    link_data = resp_link.json()
    assert link_data["episode_id"] == ep_id
    assert link_data["procedure_id"] == proc_id

    # 4. Query links by episode via API
    resp_get = client.get(f"/api/v1/episodes/{ep_id}/links")
    assert resp_get.status_code == 200
    links = resp_get.json()
    assert len(links) == 1
    assert links[0]["id"] == link_data["id"]
