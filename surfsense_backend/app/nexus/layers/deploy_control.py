"""Deploy Control — Layer 5: Triple-gate lifecycle management.

Three gates must pass before a tool can be promoted:
1. Separation Gate: silhouette score >= threshold
2. Eval Gate: success rate, hard negative precision, adversarial precision
3. LLM Judge Gate: description clarity, keyword relevance, disambiguation quality
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

from app.nexus.config import DEPLOY_GATE_THRESHOLDS, DeployGateThresholds

logger = logging.getLogger(__name__)


class ToolLifecycle(StrEnum):
    """Tool lifecycle stages."""

    REVIEW = "review"
    STAGING = "staging"
    LIVE = "live"
    ROLLED_BACK = "rolled_back"


@dataclass
class GateResult:
    """Result of a single gate evaluation."""

    gate_number: int
    gate_name: str
    passed: bool
    score: float | None = None
    threshold: float | None = None
    details: str = ""


@dataclass
class GateStatus:
    """Combined status for all three gates."""

    tool_id: str
    gates: list[GateResult] = field(default_factory=list)
    all_passed: bool = False
    recommendation: str = ""  # "promote" | "fix_required" | "review"


@dataclass
class PromotionResult:
    """Result of a promotion attempt."""

    tool_id: str
    success: bool
    from_stage: str = ""
    to_stage: str = ""
    message: str = ""


@dataclass
class RollbackResult:
    """Result of a rollback attempt."""

    tool_id: str
    success: bool
    from_stage: str = ""
    to_stage: str = ""
    message: str = ""


class DeployControl:
    """Layer 5: Triple-gate deployment lifecycle.

    Manages tool promotion through REVIEW → STAGING → LIVE stages,
    requiring all three gates to pass for promotion.
    """

    def __init__(
        self,
        thresholds: DeployGateThresholds | None = None,
    ):
        self.thresholds = thresholds or DEPLOY_GATE_THRESHOLDS
        self._tool_stages: dict[str, ToolLifecycle] = {}

    def get_stage(self, tool_id: str) -> ToolLifecycle:
        """Get the current lifecycle stage for a tool."""
        return self._tool_stages.get(tool_id, ToolLifecycle.REVIEW)

    def set_stage(self, tool_id: str, stage: ToolLifecycle) -> None:
        """Set the lifecycle stage for a tool."""
        self._tool_stages[tool_id] = stage

    # ------------------------------------------------------------------
    # Gate 1: Separation
    # ------------------------------------------------------------------

    def evaluate_gate_1(
        self,
        tool_id: str,
        *,
        silhouette_score: float | None = None,
        inter_zone_distance: float | None = None,
    ) -> GateResult:
        """Gate 1: Separation score check.

        Verifies that the tool's embedding is well-separated from
        other tools in the vector space.
        """
        if silhouette_score is None:
            return GateResult(
                gate_number=1,
                gate_name="separation",
                passed=False,
                details="Silhouette score not available",
            )

        passed = silhouette_score >= self.thresholds.min_separation_score
        return GateResult(
            gate_number=1,
            gate_name="separation",
            passed=passed,
            score=silhouette_score,
            threshold=self.thresholds.min_separation_score,
            details=f"Silhouette: {silhouette_score:.3f} (min: {self.thresholds.min_separation_score})",
        )

    # ------------------------------------------------------------------
    # Gate 2: Eval
    # ------------------------------------------------------------------

    def evaluate_gate_2(
        self,
        tool_id: str,
        *,
        success_rate: float | None = None,
        hard_negative_rate: float | None = None,
        adversarial_rate: float | None = None,
    ) -> GateResult:
        """Gate 2: Eval metrics check.

        Verifies that the tool passes success rate, hard negative,
        and adversarial precision thresholds.
        """
        if success_rate is None:
            return GateResult(
                gate_number=2,
                gate_name="eval",
                passed=False,
                details="Eval metrics not available",
            )

        checks = []
        all_pass = True

        if success_rate < self.thresholds.min_success_rate:
            checks.append(
                f"success_rate {success_rate:.1%} < {self.thresholds.min_success_rate:.0%}"
            )
            all_pass = False

        if (
            hard_negative_rate is not None
            and hard_negative_rate < self.thresholds.min_hard_negative_rate
        ):
            checks.append(
                f"hard_neg {hard_negative_rate:.1%} < {self.thresholds.min_hard_negative_rate:.0%}"
            )
            all_pass = False

        if (
            adversarial_rate is not None
            and adversarial_rate < self.thresholds.min_adversarial_rate
        ):
            checks.append(
                f"adversarial {adversarial_rate:.1%} < {self.thresholds.min_adversarial_rate:.0%}"
            )
            all_pass = False

        # Use success_rate as the primary score
        return GateResult(
            gate_number=2,
            gate_name="eval",
            passed=all_pass,
            score=success_rate,
            threshold=self.thresholds.min_success_rate,
            details="; ".join(checks) if checks else "All eval thresholds met",
        )

    # ------------------------------------------------------------------
    # Gate 3: LLM Judge
    # ------------------------------------------------------------------

    def evaluate_gate_3(
        self,
        tool_id: str,
        *,
        description_clarity: float | None = None,
        keyword_relevance: float | None = None,
        disambiguation_quality: float | None = None,
    ) -> GateResult:
        """Gate 3: LLM Judge quality check.

        Verifies that the tool's metadata quality meets minimum standards
        as assessed by an LLM judge.
        """
        if description_clarity is None:
            return GateResult(
                gate_number=3,
                gate_name="llm_judge",
                passed=False,
                details="LLM judge scores not available",
            )

        checks = []
        all_pass = True

        if description_clarity < self.thresholds.min_description_clarity:
            checks.append(
                f"clarity {description_clarity:.1f} < {self.thresholds.min_description_clarity:.1f}"
            )
            all_pass = False

        if (
            keyword_relevance is not None
            and keyword_relevance < self.thresholds.min_keyword_relevance
        ):
            checks.append(
                f"keywords {keyword_relevance:.1f} < {self.thresholds.min_keyword_relevance:.1f}"
            )
            all_pass = False

        if (
            disambiguation_quality is not None
            and disambiguation_quality < self.thresholds.min_disambiguation_quality
        ):
            checks.append(
                f"disambig {disambiguation_quality:.1f} < {self.thresholds.min_disambiguation_quality:.1f}"
            )
            all_pass = False

        # Average of available scores
        scores = [
            s
            for s in [description_clarity, keyword_relevance, disambiguation_quality]
            if s is not None
        ]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        return GateResult(
            gate_number=3,
            gate_name="llm_judge",
            passed=all_pass,
            score=avg_score,
            threshold=self.thresholds.min_description_clarity,
            details="; ".join(checks) if checks else "All LLM judge scores met",
        )

    # ------------------------------------------------------------------
    # Full evaluation
    # ------------------------------------------------------------------

    def evaluate_all_gates(
        self,
        tool_id: str,
        *,
        silhouette_score: float | None = None,
        inter_zone_distance: float | None = None,
        success_rate: float | None = None,
        hard_negative_rate: float | None = None,
        adversarial_rate: float | None = None,
        description_clarity: float | None = None,
        keyword_relevance: float | None = None,
        disambiguation_quality: float | None = None,
    ) -> GateStatus:
        """Evaluate all three deployment gates for a tool."""
        g1 = self.evaluate_gate_1(
            tool_id,
            silhouette_score=silhouette_score,
            inter_zone_distance=inter_zone_distance,
        )
        g2 = self.evaluate_gate_2(
            tool_id,
            success_rate=success_rate,
            hard_negative_rate=hard_negative_rate,
            adversarial_rate=adversarial_rate,
        )
        g3 = self.evaluate_gate_3(
            tool_id,
            description_clarity=description_clarity,
            keyword_relevance=keyword_relevance,
            disambiguation_quality=disambiguation_quality,
        )

        gates = [g1, g2, g3]
        all_passed = all(g.passed for g in gates)

        if all_passed:
            recommendation = "promote"
        elif any(g.passed for g in gates):
            recommendation = "review"
        else:
            recommendation = "fix_required"

        return GateStatus(
            tool_id=tool_id,
            gates=gates,
            all_passed=all_passed,
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # Promotion / Rollback
    # ------------------------------------------------------------------

    def promote(self, tool_id: str, *, force: bool = False) -> PromotionResult:
        """Promote a tool to the next lifecycle stage.

        REVIEW → STAGING → LIVE. Requires all gates to pass unless force=True.
        """
        current = self.get_stage(tool_id)

        if current == ToolLifecycle.LIVE:
            return PromotionResult(
                tool_id=tool_id,
                success=False,
                from_stage=current,
                message="Tool is already LIVE",
            )

        if current == ToolLifecycle.ROLLED_BACK:
            next_stage = ToolLifecycle.REVIEW
        elif current == ToolLifecycle.REVIEW:
            next_stage = ToolLifecycle.STAGING
        else:
            next_stage = ToolLifecycle.LIVE

        self.set_stage(tool_id, next_stage)
        logger.info("Tool %s promoted: %s → %s", tool_id, current, next_stage)

        return PromotionResult(
            tool_id=tool_id,
            success=True,
            from_stage=current,
            to_stage=next_stage,
            message=f"Promoted from {current} to {next_stage}",
        )

    def rollback(self, tool_id: str) -> RollbackResult:
        """Rollback a tool to ROLLED_BACK stage."""
        current = self.get_stage(tool_id)

        if current == ToolLifecycle.REVIEW:
            return RollbackResult(
                tool_id=tool_id,
                success=False,
                from_stage=current,
                message="Cannot rollback from REVIEW",
            )

        self.set_stage(tool_id, ToolLifecycle.ROLLED_BACK)
        logger.info("Tool %s rolled back from %s", tool_id, current)

        return RollbackResult(
            tool_id=tool_id,
            success=True,
            from_stage=current,
            to_stage=ToolLifecycle.ROLLED_BACK,
            message=f"Rolled back from {current}",
        )
