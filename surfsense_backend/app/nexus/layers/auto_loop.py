"""Auto Loop — Layer 3: Self-improving pipeline.

7-step pipeline:
1. Generate test cases (Synth Forge)
2. Evaluate against current routing
3. Cluster failure modes (DBSCAN)
4. LLM root cause analysis per cluster
5. Test fix in isolation (embedding delta)
6. Queue for human review
7. If approved: deploy & reindex
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


class LoopStatus(StrEnum):
    """Status of an auto-loop run."""

    PENDING = "pending"
    RUNNING = "running"
    ANALYZING = "analyzing"
    PROPOSING = "proposing"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYED = "deployed"
    FAILED = "failed"


@dataclass
class FailureCluster:
    """A cluster of related routing failures."""

    cluster_id: int
    tool_ids: list[str] = field(default_factory=list)
    sample_queries: list[str] = field(default_factory=list)
    failure_count: int = 0
    root_cause: str = ""
    proposed_fix: str = ""
    embedding_delta: float = 0.0


@dataclass
class MetadataProposal:
    """A proposed metadata change from the auto-loop."""

    tool_id: str
    field_name: str
    current_value: str = ""
    proposed_value: str = ""
    reason: str = ""
    embedding_delta: float = 0.0
    approved: bool | None = None  # None = pending review


@dataclass
class LoopRun:
    """A complete auto-loop run."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    loop_number: int = 0
    status: LoopStatus = LoopStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_tests: int = 0
    failures: int = 0
    failure_clusters: list[FailureCluster] = field(default_factory=list)
    proposals: list[MetadataProposal] = field(default_factory=list)
    approved_proposals: int = 0
    embedding_delta: float = 0.0


class AutoLoop:
    """Layer 3: Self-improving evaluation and metadata optimization.

    Orchestrates the 7-step auto-improvement pipeline.
    Each step can be run independently for testing.
    """

    def __init__(self):
        self._current_run: LoopRun | None = None
        self._run_history: list[LoopRun] = []

    @property
    def current_run(self) -> LoopRun | None:
        return self._current_run

    @property
    def run_count(self) -> int:
        return len(self._run_history)

    def start_run(self) -> LoopRun:
        """Start a new auto-loop run."""
        run = LoopRun(
            loop_number=len(self._run_history) + 1,
            status=LoopStatus.RUNNING,
            started_at=datetime.now(tz=UTC),
        )
        self._current_run = run
        logger.info("Auto-loop run #%d started", run.loop_number)
        return run

    def record_eval_results(
        self,
        total_tests: int,
        failures: int,
        failed_queries: list[dict],
    ) -> None:
        """Record evaluation results (step 2).

        Args:
            total_tests: Total test cases run.
            failures: Number of failures.
            failed_queries: List of dicts with query, expected_tool, got_tool.
        """
        if not self._current_run:
            return

        self._current_run.total_tests = total_tests
        self._current_run.failures = failures
        self._current_run.status = LoopStatus.ANALYZING
        logger.info("Eval: %d/%d failures", failures, total_tests)

    def cluster_failures(self, failed_queries: list[dict]) -> list[FailureCluster]:
        """Cluster failure modes (step 3).

        Groups failures by the confused tool pair. In production, DBSCAN
        would cluster by query embedding similarity.

        Args:
            failed_queries: List of dicts with query, expected_tool, got_tool.

        Returns:
            List of failure clusters.
        """
        # Group by (expected_tool, got_tool) pair
        pair_groups: dict[tuple[str, str], list[dict]] = {}
        for fq in failed_queries:
            key = (fq.get("expected_tool", ""), fq.get("got_tool", ""))
            pair_groups.setdefault(key, []).append(fq)

        clusters: list[FailureCluster] = []
        for i, ((expected, got), queries) in enumerate(pair_groups.items()):
            clusters.append(
                FailureCluster(
                    cluster_id=i,
                    tool_ids=[expected, got],
                    sample_queries=[q.get("query", "") for q in queries[:5]],
                    failure_count=len(queries),
                )
            )

        if self._current_run:
            self._current_run.failure_clusters = clusters
            self._current_run.status = LoopStatus.PROPOSING

        return clusters

    def create_proposals(
        self,
        clusters: list[FailureCluster],
        root_causes: list[str] | None = None,
    ) -> list[MetadataProposal]:
        """Create metadata change proposals (steps 4-5).

        In production, each cluster would get LLM root-cause analysis
        and the proposed fix would be tested for embedding delta.

        Args:
            clusters: Failure clusters from step 3.
            root_causes: Optional LLM-generated root causes per cluster.

        Returns:
            List of metadata proposals.
        """
        proposals: list[MetadataProposal] = []

        for i, cluster in enumerate(clusters):
            if not cluster.tool_ids:
                continue

            root_cause = ""
            if root_causes and i < len(root_causes):
                root_cause = root_causes[i]

            cluster.root_cause = root_cause

            # Create a proposal for the primary tool in the confusion pair
            tool_id = cluster.tool_ids[0]
            proposals.append(
                MetadataProposal(
                    tool_id=tool_id,
                    field_name="description",
                    reason=root_cause
                    or f"Confusion with {cluster.tool_ids[1] if len(cluster.tool_ids) > 1 else 'unknown'}",
                    embedding_delta=cluster.embedding_delta,
                )
            )

        if self._current_run:
            self._current_run.proposals = proposals
            self._current_run.status = LoopStatus.REVIEW

        return proposals

    def approve_proposal(self, tool_id: str) -> bool:
        """Approve a metadata proposal for deployment.

        Returns True if found and approved.
        """
        if not self._current_run:
            return False

        for p in self._current_run.proposals:
            if p.tool_id == tool_id and p.approved is None:
                p.approved = True
                self._current_run.approved_proposals += 1
                return True
        return False

    def reject_proposal(self, tool_id: str) -> bool:
        """Reject a metadata proposal.

        Returns True if found and rejected.
        """
        if not self._current_run:
            return False

        for p in self._current_run.proposals:
            if p.tool_id == tool_id and p.approved is None:
                p.approved = False
                return True
        return False

    def complete_run(self) -> LoopRun | None:
        """Complete the current run and move to history."""
        if not self._current_run:
            return None

        self._current_run.completed_at = datetime.now(tz=UTC)
        if any(p.approved for p in self._current_run.proposals):
            self._current_run.status = LoopStatus.APPROVED
        elif all(
            p.approved is False
            for p in self._current_run.proposals
            if p.approved is not None
        ):
            self._current_run.status = LoopStatus.REJECTED
        else:
            self._current_run.status = LoopStatus.REVIEW

        run = self._current_run
        self._run_history.append(run)
        self._current_run = None

        logger.info(
            "Auto-loop run #%d completed: %d proposals, %d approved",
            run.loop_number,
            len(run.proposals),
            run.approved_proposals,
        )
        return run

    def get_run_history(self) -> list[LoopRun]:
        """Return all completed runs."""
        return list(self._run_history)

    def get_run(self, run_id: uuid.UUID) -> LoopRun | None:
        """Get a specific run by ID."""
        for run in self._run_history:
            if run.id == run_id:
                return run
        if self._current_run and self._current_run.id == run_id:
            return self._current_run
        return None
