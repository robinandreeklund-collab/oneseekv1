"""Eval Ledger — Layer 4: Pipeline-stage metrics tracking.

Tracks precision metrics at 5 pipeline stages:
1. Intent routing
2. Route selection
3. Bigtool retrieval
4. Reranker effect
5. End-to-end quality

Per-namespace breakdown, reranker pre/post delta, MRR@10, nDCG@5.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from app.nexus.config import PIPELINE_STAGES

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Metrics for a single pipeline stage evaluation."""

    stage: int
    stage_name: str
    namespace: str | None = None
    precision_at_1: float | None = None
    precision_at_5: float | None = None
    mrr_at_10: float | None = None
    ndcg_at_5: float | None = None
    hard_negative_precision: float | None = None
    reranker_delta: float | None = None


@dataclass
class EvalRun:
    """A complete evaluation run across all stages."""

    stages: list[StageResult] = field(default_factory=list)
    overall_e2e: StageResult | None = None
    total_queries: int = 0
    total_correct: int = 0


def compute_mrr(
    ranked_results: list[str],
    relevant: str,
    *,
    k: int = 10,
) -> float:
    """Compute Mean Reciprocal Rank for a single query.

    Args:
        ranked_results: Ordered list of tool IDs (top-1 first).
        relevant: The correct tool ID.
        k: Cutoff.

    Returns:
        1/rank if found in top-k, else 0.0.
    """
    for i, tool_id in enumerate(ranked_results[:k]):
        if tool_id == relevant:
            return 1.0 / (i + 1)
    return 0.0


def compute_ndcg(
    ranked_results: list[str],
    relevant: str,
    *,
    k: int = 5,
) -> float:
    """Compute nDCG@k for a single query (binary relevance).

    Args:
        ranked_results: Ordered list of tool IDs.
        relevant: The correct tool ID.
        k: Cutoff.

    Returns:
        nDCG score (0-1).
    """
    dcg = 0.0
    for i, tool_id in enumerate(ranked_results[:k]):
        if tool_id == relevant:
            dcg = 1.0 / math.log2(i + 2)  # log2(rank + 1), rank is 1-indexed
            break

    # Ideal DCG: relevant at position 1
    idcg = 1.0 / math.log2(2)  # = 1.0

    return dcg / idcg if idcg > 0 else 0.0


def compute_precision_at_k(
    ranked_results: list[str],
    relevant: str,
    *,
    k: int = 1,
) -> float:
    """Compute precision@k (binary: is relevant in top-k?)."""
    return 1.0 if relevant in ranked_results[:k] else 0.0


class EvalLedger:
    """Layer 4: Pipeline metrics tracking and evaluation.

    Evaluates each stage of the precision routing pipeline independently,
    allowing identification of bottlenecks.
    """

    def __init__(self):
        self.stages = PIPELINE_STAGES

    def evaluate_query(
        self,
        query: str,
        expected_tool: str,
        *,
        intent_results: list[str] | None = None,
        agent_results: list[str] | None = None,
        route_results: list[str] | None = None,
        bigtool_results: list[str] | None = None,
        rerank_results: list[str] | None = None,
        e2e_result: str | None = None,
        namespace: str | None = None,
    ) -> list[StageResult]:
        """Evaluate a single query across all pipeline stages.

        Args:
            query: The query text.
            expected_tool: The correct tool ID.
            intent_results: Ranked results from intent routing.
            agent_results: Ranked agent names from agent resolution.
            route_results: Ranked results from route selection.
            bigtool_results: Ranked results from bigtool retrieval.
            rerank_results: Ranked results from reranker.
            e2e_result: Final selected tool.
            namespace: Optional namespace for per-namespace tracking.

        Returns:
            List of StageResult for each stage that had data.
        """
        results: list[StageResult] = []

        stage_data = [
            (1, "intent", intent_results),
            (2, "agent", agent_results),
            (3, "route", route_results),
            (4, "bigtool", bigtool_results),
            (5, "rerank", rerank_results),
        ]

        for stage_num, stage_name, ranked in stage_data:
            if ranked is None:
                continue

            results.append(
                StageResult(
                    stage=stage_num,
                    stage_name=stage_name,
                    namespace=namespace,
                    precision_at_1=compute_precision_at_k(ranked, expected_tool, k=1),
                    precision_at_5=compute_precision_at_k(ranked, expected_tool, k=5),
                    mrr_at_10=compute_mrr(ranked, expected_tool, k=10),
                    ndcg_at_5=compute_ndcg(ranked, expected_tool, k=5),
                )
            )

        # Reranker delta (stage 5 vs stage 4)
        if bigtool_results and rerank_results:
            pre_mrr = compute_mrr(bigtool_results, expected_tool, k=10)
            post_mrr = compute_mrr(rerank_results, expected_tool, k=10)
            delta = post_mrr - pre_mrr

            # Update the rerank stage result with delta
            for r in results:
                if r.stage_name == "rerank":
                    r.reranker_delta = delta

        # E2E stage
        if e2e_result is not None:
            results.append(
                StageResult(
                    stage=6,
                    stage_name="e2e",
                    namespace=namespace,
                    precision_at_1=1.0 if e2e_result == expected_tool else 0.0,
                )
            )

        return results

    def aggregate_results(
        self, all_results: list[list[StageResult]]
    ) -> dict[str, StageResult]:
        """Aggregate per-query results into summary metrics.

        Args:
            all_results: List of per-query StageResult lists.

        Returns:
            Dict of stage_name → aggregated StageResult.
        """
        by_stage: dict[str, list[StageResult]] = {}
        for query_results in all_results:
            for sr in query_results:
                by_stage.setdefault(sr.stage_name, []).append(sr)

        aggregated: dict[str, StageResult] = {}
        for stage_name, stage_results in by_stage.items():
            n = len(stage_results)
            if n == 0:
                continue

            def _mean(vals: list[float | None]) -> float | None:
                filtered = [v for v in vals if v is not None]
                return sum(filtered) / len(filtered) if filtered else None

            aggregated[stage_name] = StageResult(
                stage=stage_results[0].stage,
                stage_name=stage_name,
                precision_at_1=_mean([r.precision_at_1 for r in stage_results]),
                precision_at_5=_mean([r.precision_at_5 for r in stage_results]),
                mrr_at_10=_mean([r.mrr_at_10 for r in stage_results]),
                ndcg_at_5=_mean([r.ndcg_at_5 for r in stage_results]),
                hard_negative_precision=_mean(
                    [r.hard_negative_precision for r in stage_results]
                ),
                reranker_delta=_mean([r.reranker_delta for r in stage_results]),
            )

        return aggregated

    def aggregate_by_namespace(
        self, all_results: list[list[StageResult]]
    ) -> dict[str, dict[str, StageResult]]:
        """Aggregate results grouped by namespace.

        Returns:
            Dict of namespace → (stage_name → aggregated StageResult).
        """
        by_ns: dict[str, list[list[StageResult]]] = {}
        for query_results in all_results:
            for sr in query_results:
                ns = sr.namespace or "_global"
                by_ns.setdefault(ns, [])
                # Group by query (approximate: each query's results go together)
                if not by_ns[ns] or by_ns[ns][-1][0].stage >= sr.stage:
                    by_ns[ns].append([sr])
                else:
                    by_ns[ns][-1].append(sr)

        return {ns: self.aggregate_results(results) for ns, results in by_ns.items()}
