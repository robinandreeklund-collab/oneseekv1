"""Tests for NEXUS Auto Loop — Layer 3: Self-improving pipeline."""

from __future__ import annotations

import uuid

from app.nexus.layers.auto_loop import (
    AutoLoop,
    FailureCluster,
    LoopStatus,
)

# ---------------------------------------------------------------------------
# LoopStatus enum
# ---------------------------------------------------------------------------


class TestLoopStatus:
    def test_all_statuses(self):
        assert len(LoopStatus) == 9
        assert LoopStatus.PENDING == "pending"
        assert LoopStatus.DEPLOYED == "deployed"

    def test_is_str_enum(self):
        assert isinstance(LoopStatus.RUNNING, str)
        assert LoopStatus.RUNNING == "running"


# ---------------------------------------------------------------------------
# AutoLoop — start_run
# ---------------------------------------------------------------------------


class TestAutoLoopStartRun:
    def test_start_run_creates_run(self):
        loop = AutoLoop()
        run = loop.start_run()
        assert run.status == LoopStatus.RUNNING
        assert run.loop_number == 1
        assert run.started_at is not None

    def test_multiple_runs_increment(self):
        loop = AutoLoop()
        loop.start_run()
        loop.complete_run()
        r2 = loop.start_run()
        assert r2.loop_number == 2

    def test_current_run_set(self):
        loop = AutoLoop()
        run = loop.start_run()
        assert loop.current_run is run


# ---------------------------------------------------------------------------
# record_eval_results
# ---------------------------------------------------------------------------


class TestRecordEvalResults:
    def test_records_results(self):
        loop = AutoLoop()
        loop.start_run()
        loop.record_eval_results(100, 12, [])
        assert loop.current_run.total_tests == 100
        assert loop.current_run.failures == 12
        assert loop.current_run.status == LoopStatus.ANALYZING

    def test_no_current_run_noop(self):
        loop = AutoLoop()
        loop.record_eval_results(10, 5, [])  # Should not raise


# ---------------------------------------------------------------------------
# cluster_failures
# ---------------------------------------------------------------------------


class TestClusterFailures:
    def test_basic_clustering(self):
        loop = AutoLoop()
        loop.start_run()
        failed = [
            {"query": "Q1", "expected_tool": "smhi", "got_tool": "scb"},
            {"query": "Q2", "expected_tool": "smhi", "got_tool": "scb"},
            {"query": "Q3", "expected_tool": "kolada", "got_tool": "riksdag"},
        ]
        clusters = loop.cluster_failures(failed)
        assert len(clusters) == 2
        assert clusters[0].failure_count == 2
        assert clusters[1].failure_count == 1

    def test_sample_queries_limited(self):
        loop = AutoLoop()
        loop.start_run()
        failed = [
            {"query": f"Q{i}", "expected_tool": "a", "got_tool": "b"} for i in range(20)
        ]
        clusters = loop.cluster_failures(failed)
        assert len(clusters[0].sample_queries) <= 5

    def test_updates_status_to_proposing(self):
        loop = AutoLoop()
        loop.start_run()
        loop.cluster_failures([{"query": "Q", "expected_tool": "a", "got_tool": "b"}])
        assert loop.current_run.status == LoopStatus.PROPOSING

    def test_empty_failures(self):
        loop = AutoLoop()
        loop.start_run()
        clusters = loop.cluster_failures([])
        assert clusters == []


# ---------------------------------------------------------------------------
# create_proposals
# ---------------------------------------------------------------------------


class TestCreateProposals:
    def test_creates_proposals(self):
        loop = AutoLoop()
        loop.start_run()
        clusters = [
            FailureCluster(cluster_id=0, tool_ids=["smhi", "scb"], failure_count=5),
        ]
        proposals = loop.create_proposals(
            clusters, root_causes=["Liknande beskrivningar"]
        )
        assert len(proposals) == 1
        assert proposals[0].tool_id == "smhi"
        assert proposals[0].reason == "Liknande beskrivningar"

    def test_no_root_causes(self):
        loop = AutoLoop()
        loop.start_run()
        clusters = [
            FailureCluster(cluster_id=0, tool_ids=["a", "b"], failure_count=3),
        ]
        proposals = loop.create_proposals(clusters)
        assert len(proposals) == 1
        assert "b" in proposals[0].reason

    def test_sets_status_to_review(self):
        loop = AutoLoop()
        loop.start_run()
        clusters = [FailureCluster(cluster_id=0, tool_ids=["x", "y"])]
        loop.create_proposals(clusters)
        assert loop.current_run.status == LoopStatus.REVIEW


# ---------------------------------------------------------------------------
# approve / reject
# ---------------------------------------------------------------------------


class TestApproveReject:
    def test_approve_proposal(self):
        loop = AutoLoop()
        loop.start_run()
        clusters = [FailureCluster(cluster_id=0, tool_ids=["a", "b"])]
        loop.create_proposals(clusters)
        assert loop.approve_proposal("a")
        assert loop.current_run.approved_proposals == 1

    def test_reject_proposal(self):
        loop = AutoLoop()
        loop.start_run()
        clusters = [FailureCluster(cluster_id=0, tool_ids=["a", "b"])]
        loop.create_proposals(clusters)
        assert loop.reject_proposal("a")
        assert loop.current_run.proposals[0].approved is False

    def test_double_approve_fails(self):
        loop = AutoLoop()
        loop.start_run()
        clusters = [FailureCluster(cluster_id=0, tool_ids=["a", "b"])]
        loop.create_proposals(clusters)
        loop.approve_proposal("a")
        assert not loop.approve_proposal("a")  # Already approved

    def test_no_current_run(self):
        loop = AutoLoop()
        assert not loop.approve_proposal("a")
        assert not loop.reject_proposal("a")


# ---------------------------------------------------------------------------
# complete_run
# ---------------------------------------------------------------------------


class TestCompleteRun:
    def test_completes_run(self):
        loop = AutoLoop()
        loop.start_run()
        run = loop.complete_run()
        assert run is not None
        assert run.completed_at is not None
        assert loop.current_run is None

    def test_approved_status_when_proposals_approved(self):
        loop = AutoLoop()
        loop.start_run()
        clusters = [FailureCluster(cluster_id=0, tool_ids=["a", "b"])]
        loop.create_proposals(clusters)
        loop.approve_proposal("a")
        run = loop.complete_run()
        assert run.status == LoopStatus.APPROVED

    def test_rejected_status_when_all_rejected(self):
        loop = AutoLoop()
        loop.start_run()
        clusters = [FailureCluster(cluster_id=0, tool_ids=["a", "b"])]
        loop.create_proposals(clusters)
        loop.reject_proposal("a")
        run = loop.complete_run()
        assert run.status == LoopStatus.REJECTED

    def test_run_added_to_history(self):
        loop = AutoLoop()
        loop.start_run()
        loop.complete_run()
        assert loop.run_count == 1

    def test_no_current_run_returns_none(self):
        loop = AutoLoop()
        assert loop.complete_run() is None


# ---------------------------------------------------------------------------
# get_run / get_run_history
# ---------------------------------------------------------------------------


class TestRunHistory:
    def test_get_run_by_id(self):
        loop = AutoLoop()
        run = loop.start_run()
        run_id = run.id
        loop.complete_run()
        found = loop.get_run(run_id)
        assert found is not None
        assert found.id == run_id

    def test_get_current_run_by_id(self):
        loop = AutoLoop()
        run = loop.start_run()
        found = loop.get_run(run.id)
        assert found is run

    def test_get_nonexistent_run(self):
        loop = AutoLoop()
        assert loop.get_run(uuid.uuid4()) is None

    def test_run_history(self):
        loop = AutoLoop()
        loop.start_run()
        loop.complete_run()
        loop.start_run()
        loop.complete_run()
        assert len(loop.get_run_history()) == 2
