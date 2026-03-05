"""Tests for NEXUS Deploy Control — Layer 5: Triple-gate lifecycle."""

from __future__ import annotations

from app.nexus.config import DEPLOY_GATE_THRESHOLDS, DeployGateThresholds
from app.nexus.layers.deploy_control import (
    DeployControl,
    GateResult,
    GateStatus,
    PromotionResult,
    RollbackResult,
    ToolLifecycle,
)

# ---------------------------------------------------------------------------
# ToolLifecycle enum
# ---------------------------------------------------------------------------


class TestToolLifecycle:
    def test_all_stages(self):
        assert len(ToolLifecycle) == 4
        assert ToolLifecycle.REVIEW == "review"
        assert ToolLifecycle.STAGING == "staging"
        assert ToolLifecycle.LIVE == "live"
        assert ToolLifecycle.ROLLED_BACK == "rolled_back"


# ---------------------------------------------------------------------------
# Gate 1: Separation
# ---------------------------------------------------------------------------


class TestGate1Separation:
    def test_passes_above_threshold(self):
        dc = DeployControl()
        result = dc.evaluate_gate_1("t1", silhouette_score=0.75)
        assert result.passed
        assert result.score == 0.75
        assert result.threshold == DEPLOY_GATE_THRESHOLDS.min_separation_score

    def test_fails_below_threshold(self):
        dc = DeployControl()
        result = dc.evaluate_gate_1("t1", silhouette_score=0.50)
        assert not result.passed

    def test_exact_threshold(self):
        dc = DeployControl()
        result = dc.evaluate_gate_1(
            "t1", silhouette_score=DEPLOY_GATE_THRESHOLDS.min_separation_score
        )
        assert result.passed

    def test_no_score(self):
        dc = DeployControl()
        result = dc.evaluate_gate_1("t1")
        assert not result.passed
        assert "not available" in result.details

    def test_custom_threshold(self):
        thresholds = DeployGateThresholds(min_separation_score=0.80)
        dc = DeployControl(thresholds=thresholds)
        result = dc.evaluate_gate_1("t1", silhouette_score=0.75)
        assert not result.passed


# ---------------------------------------------------------------------------
# Gate 2: Eval
# ---------------------------------------------------------------------------


class TestGate2Eval:
    def test_all_pass(self):
        dc = DeployControl()
        result = dc.evaluate_gate_2(
            "t1", success_rate=0.90, hard_negative_rate=0.90, adversarial_rate=0.85
        )
        assert result.passed

    def test_success_rate_too_low(self):
        dc = DeployControl()
        result = dc.evaluate_gate_2(
            "t1", success_rate=0.70, hard_negative_rate=0.90, adversarial_rate=0.85
        )
        assert not result.passed
        assert "success_rate" in result.details

    def test_hard_negative_too_low(self):
        dc = DeployControl()
        result = dc.evaluate_gate_2(
            "t1", success_rate=0.90, hard_negative_rate=0.70, adversarial_rate=0.85
        )
        assert not result.passed

    def test_adversarial_too_low(self):
        dc = DeployControl()
        result = dc.evaluate_gate_2(
            "t1", success_rate=0.90, hard_negative_rate=0.90, adversarial_rate=0.70
        )
        assert not result.passed

    def test_no_metrics(self):
        dc = DeployControl()
        result = dc.evaluate_gate_2("t1")
        assert not result.passed

    def test_only_success_rate(self):
        dc = DeployControl()
        result = dc.evaluate_gate_2("t1", success_rate=0.85)
        assert result.passed  # No hard_neg or adversarial to fail


# ---------------------------------------------------------------------------
# Gate 3: LLM Judge
# ---------------------------------------------------------------------------


class TestGate3LLMJudge:
    def test_all_pass(self):
        dc = DeployControl()
        result = dc.evaluate_gate_3(
            "t1",
            description_clarity=4.5,
            keyword_relevance=4.2,
            disambiguation_quality=4.1,
        )
        assert result.passed

    def test_clarity_too_low(self):
        dc = DeployControl()
        result = dc.evaluate_gate_3(
            "t1",
            description_clarity=3.5,
            keyword_relevance=4.2,
            disambiguation_quality=4.1,
        )
        assert not result.passed
        assert "clarity" in result.details

    def test_no_scores(self):
        dc = DeployControl()
        result = dc.evaluate_gate_3("t1")
        assert not result.passed

    def test_only_clarity(self):
        dc = DeployControl()
        result = dc.evaluate_gate_3("t1", description_clarity=4.5)
        assert result.passed


# ---------------------------------------------------------------------------
# evaluate_all_gates
# ---------------------------------------------------------------------------


class TestEvaluateAllGates:
    def test_all_pass(self):
        dc = DeployControl()
        status = dc.evaluate_all_gates(
            "t1",
            silhouette_score=0.75,
            success_rate=0.90,
            description_clarity=4.5,
        )
        assert status.all_passed
        assert status.recommendation == "promote"
        assert len(status.gates) == 3

    def test_none_pass(self):
        dc = DeployControl()
        status = dc.evaluate_all_gates("t1")
        assert not status.all_passed
        assert status.recommendation == "fix_required"

    def test_partial_pass(self):
        dc = DeployControl()
        status = dc.evaluate_all_gates(
            "t1",
            silhouette_score=0.75,  # Pass gate 1
            success_rate=0.50,  # Fail gate 2
        )
        assert not status.all_passed
        assert status.recommendation == "review"


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


class TestPromotion:
    def test_review_to_staging(self):
        dc = DeployControl()
        result = dc.promote("t1")
        assert result.success
        assert dc.get_stage("t1") == ToolLifecycle.STAGING

    def test_staging_to_live(self):
        dc = DeployControl()
        dc.set_stage("t1", ToolLifecycle.STAGING)
        result = dc.promote("t1")
        assert result.success
        assert dc.get_stage("t1") == ToolLifecycle.LIVE

    def test_live_cannot_promote(self):
        dc = DeployControl()
        dc.set_stage("t1", ToolLifecycle.LIVE)
        result = dc.promote("t1")
        assert not result.success
        assert "already LIVE" in result.message

    def test_rolled_back_to_review(self):
        dc = DeployControl()
        dc.set_stage("t1", ToolLifecycle.ROLLED_BACK)
        result = dc.promote("t1")
        assert result.success
        assert dc.get_stage("t1") == ToolLifecycle.REVIEW

    def test_default_stage_is_review(self):
        dc = DeployControl()
        assert dc.get_stage("unknown_tool") == ToolLifecycle.REVIEW


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


class TestRollback:
    def test_staging_rollback(self):
        dc = DeployControl()
        dc.set_stage("t1", ToolLifecycle.STAGING)
        result = dc.rollback("t1")
        assert result.success
        assert dc.get_stage("t1") == ToolLifecycle.ROLLED_BACK

    def test_live_rollback(self):
        dc = DeployControl()
        dc.set_stage("t1", ToolLifecycle.LIVE)
        result = dc.rollback("t1")
        assert result.success
        assert dc.get_stage("t1") == ToolLifecycle.ROLLED_BACK

    def test_review_cannot_rollback(self):
        dc = DeployControl()
        result = dc.rollback("t1")
        assert not result.success
        assert "Cannot rollback" in result.message


# ---------------------------------------------------------------------------
# GateResult / GateStatus dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_gate_result_defaults(self):
        gr = GateResult(gate_number=1, gate_name="test", passed=True)
        assert gr.score is None
        assert gr.details == ""

    def test_gate_status_defaults(self):
        gs = GateStatus(tool_id="t1")
        assert gs.gates == []
        assert not gs.all_passed

    def test_promotion_result(self):
        pr = PromotionResult(tool_id="t1", success=True)
        assert pr.message == ""

    def test_rollback_result(self):
        rr = RollbackResult(tool_id="t1", success=False, message="err")
        assert rr.message == "err"
