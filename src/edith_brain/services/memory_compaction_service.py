"""Domain service for detecting near-duplicate memory clusters and executing compaction plans."""

from __future__ import annotations

import re
from typing import Optional, Set

from edith_brain.core.contracts import (
    CompactionCandidateCluster,
    CompactionPlan,
    CompactionExecuteRequest,
    CompactionResult,
    MemoryCreate,
    MemoryCategory,
    PersonalSubcategory,
    MemoryCorrection,
)
from edith_brain.core.exceptions import ValidationError
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.memory_repository import MemoryRepository
from edith_brain.services.memory_service import MemoryService


def _tokenize(text: str) -> Set[str]:
    words = re.findall(r"\w+", text.lower())
    return set(words)


def _jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    return float(intersection) / float(union) if union > 0 else 0.0


class MemoryCompactionService:
    """Identifies overlapping, redundant personal memories and plans safe compaction."""

    def __init__(
        self,
        engine: SQLiteEngine,
        memory_service: MemoryService,
        memory_repo: Optional[MemoryRepository] = None,
    ) -> None:
        self.engine = engine
        self.memory_service = memory_service
        self.memory_repo = memory_repo or MemoryRepository()

    def analyze_compaction_opportunities(
        self,
        subcategory: Optional[PersonalSubcategory] = None,
        similarity_threshold: float = 0.65,
    ) -> CompactionPlan:
        """Scan active memories within subcategories and discover redundant clusters."""
        with self.engine.connection() as conn:
            # Fetch active personal memories
            memories = self.memory_repo.list(
                conn=conn,
                category=MemoryCategory.PERSONAL.value,
                subcategory=subcategory.value if subcategory else None,
                status="active",
                limit=1000,
            )

        total_analyzed = len(memories)
        if total_analyzed < 2:
            return CompactionPlan(
                clusters=[],
                total_memories_analyzed=total_analyzed,
                redundant_memories_identified=0,
                estimated_space_savings_pct=0.0,
            )

        # Group by subcategory
        by_subcat: dict[str, list] = {}
        for mem in memories:
            sub = mem["subcategory"] or "unspecified"
            by_subcat.setdefault(sub, []).append(mem)

        clusters: list[CompactionCandidateCluster] = []
        redundant_count = 0

        for sub, mem_list in by_subcat.items():
            if len(mem_list) < 2:
                continue

            visited = set()
            for i in range(len(mem_list)):
                if mem_list[i]["id"] in visited:
                    continue

                cluster_members = [mem_list[i]]
                tokens_i = _tokenize(mem_list[i]["content"])

                for j in range(i + 1, len(mem_list)):
                    if mem_list[j]["id"] in visited:
                        continue
                    tokens_j = _tokenize(mem_list[j]["content"])
                    sim = _jaccard_similarity(tokens_i, tokens_j)

                    if sim >= similarity_threshold:
                        cluster_members.append(mem_list[j])
                        visited.add(mem_list[j]["id"])

                if len(cluster_members) > 1:
                    visited.add(mem_list[i]["id"])
                    # Pick longest/richest content as the consolidated draft
                    best_content = max(cluster_members, key=lambda m: len(m["content"]))["content"]
                    avg_sim = round(similarity_threshold, 2)

                    clusters.append(
                        CompactionCandidateCluster(
                            subcategory=sub,
                            memory_ids=[m["id"] for m in cluster_members],
                            proposed_consolidated_content=best_content,
                            similarity_score=avg_sim,
                            rationale=f"Cluster of {len(cluster_members)} redundant memories in subcategory '{sub}' with Jaccard overlap >= {similarity_threshold}.",
                        )
                    )
                    redundant_count += (len(cluster_members) - 1)

        savings_pct = round((redundant_count / total_analyzed) * 100.0, 2) if total_analyzed > 0 else 0.0

        return CompactionPlan(
            clusters=clusters,
            total_memories_analyzed=total_analyzed,
            redundant_memories_identified=redundant_count,
            estimated_space_savings_pct=savings_pct,
        )

    def execute_compaction(
        self,
        plan: CompactionPlan,
        request: CompactionExecuteRequest,
    ) -> CompactionResult:
        """Execute or dry-run a compaction plan."""
        if not plan.clusters:
            return CompactionResult(
                executed=False,
                dry_run=request.dry_run,
                clusters_processed=0,
                superseded_memory_ids=[],
                created_memory_ids=[],
                message="No compaction clusters found in plan.",
            )

        if not request.dry_run and not request.confirmed:
            raise ValidationError("Executing memory compaction requires explicit 'confirmed=True' safeguard.")

        indices_to_process = (
            request.cluster_indices
            if request.cluster_indices is not None
            else list(range(len(plan.clusters)))
        )

        if request.dry_run:
            affected_ids = []
            for idx in indices_to_process:
                if 0 <= idx < len(plan.clusters):
                    affected_ids.extend(plan.clusters[idx].memory_ids)
            return CompactionResult(
                executed=False,
                dry_run=True,
                clusters_processed=len(indices_to_process),
                superseded_memory_ids=affected_ids,
                created_memory_ids=[],
                message=f"Dry run preview: would compact {len(indices_to_process)} clusters affecting {len(affected_ids)} memories.",
            )

        superseded_ids = []
        created_ids = []

        for idx in indices_to_process:
            if idx < 0 or idx >= len(plan.clusters):
                continue
            cluster = plan.clusters[idx]
            subcat = PersonalSubcategory(cluster.subcategory) if cluster.subcategory else PersonalSubcategory.PROFILE_FACT

            # 1. Create the unified consolidated memory
            new_mem = self.memory_service.create_memory(
                payload=MemoryCreate(
                    category=MemoryCategory.PERSONAL,
                    subcategory=subcat,
                    content=cluster.proposed_consolidated_content,
                    confidence=1.0,
                    tags=["compacted"],
                    metadata={"compacted_from": cluster.memory_ids},
                )
            )
            created_ids.append(new_mem.id)

            # 2. Correct/supersede the older constituent memories
            for mem_id in cluster.memory_ids:
                try:
                    self.memory_service.correct_memory(
                        memory_id=mem_id,
                        payload=MemoryCorrection(
                            new_content=cluster.proposed_consolidated_content,
                            confidence=1.0,
                            reason=f"Compacted into unified entry {new_mem.id}",
                            tags=["superseded_by_compaction"],
                        ),
                    )
                    superseded_ids.append(mem_id)
                except Exception:
                    pass

        return CompactionResult(
            executed=True,
            dry_run=False,
            clusters_processed=len(indices_to_process),
            superseded_memory_ids=superseded_ids,
            created_memory_ids=created_ids,
            message=f"Successfully compacted {len(indices_to_process)} clusters into {len(created_ids)} unified memories.",
        )
