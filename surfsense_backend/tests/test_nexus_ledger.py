"""Tests for NEXUS Eval Ledger — Layer 4: Pipeline metrics tracking."""

from __future__ import annotations

import math

from app.nexus.layers.eval_ledger import (
    EvalLedger,
    EvalRun,
    StageResult,
    compute_mrr,
    compute_ndcg,
    compute_precision_at_k,
)

# ---------------------------------------------------------------------------
# compute_mrr
# ---------------------------------------------------------------------------


class TestComputeMRR:
    def test_first_position(self):
        assert compute_mrr(["a", "b", "c"], "a") == 1.0

    def test_second_position(self):
        assert compute_mrr(["b", "a", "c"], "a") == 0.5

    def test_third_position(self):
        assert abs(compute_mrr(["b", "c", "a"], "a") - 1 / 3) < 1e-9

    def test_not_found(self):
        assert compute_mrr(["b", "c", "d"], "a") == 0.0

    def test_cutoff(self):
        results = ["b", "c", "d", "a"]
        assert compute_mrr(results, "a", k=3) == 0.0  # Outside top-3
        assert compute_mrr(results, "a", k=4) == 0.25  # Inside top-4

    def test_empty_results(self):
        assert compute_mrr([], "a") == 0.0


# ---------------------------------------------------------------------------
# compute_ndcg
# ---------------------------------------------------------------------------


class TestComputeNDCG:
    def test_first_position_perfect(self):
        assert compute_ndcg(["a", "b"], "a") == 1.0

    def test_second_position(self):
        expected = (1.0 / math.log2(3)) / (1.0 / math.log2(2))
        assert abs(compute_ndcg(["b", "a"], "a") - expected) < 1e-9

    def test_not_found(self):
        assert compute_ndcg(["b", "c"], "a") == 0.0

    def test_cutoff(self):
        results = ["b", "c", "d", "e", "f", "a"]
        assert compute_ndcg(results, "a", k=3) == 0.0  # Outside top-3


# ---------------------------------------------------------------------------
# compute_precision_at_k
# ---------------------------------------------------------------------------


class TestComputePrecisionAtK:
    def test_in_top_1(self):
        assert compute_precision_at_k(["a", "b"], "a", k=1) == 1.0

    def test_not_in_top_1(self):
        assert compute_precision_at_k(["b", "a"], "a", k=1) == 0.0

    def test_in_top_5(self):
        assert compute_precision_at_k(["b", "c", "d", "a"], "a", k=5) == 1.0

    def test_empty(self):
        assert compute_precision_at_k([], "a", k=1) == 0.0


# ---------------------------------------------------------------------------
# EvalLedger.evaluate_query
# ---------------------------------------------------------------------------


class TestEvaluateQuery:
    def test_all_stages(self):
        ledger = EvalLedger()
        results = ledger.evaluate_query(
            query="Vad kostar el?",
            expected_tool="elspot",
            intent_results=["elspot", "smhi"],
            route_results=["smhi", "elspot"],
            bigtool_results=["scb", "smhi", "elspot"],
            rerank_results=["elspot", "smhi", "scb"],
            e2e_result="elspot",
        )
        assert len(results) == 5  # 4 stages + e2e
        names = [r.stage_name for r in results]
        assert "intent" in names
        assert "route" in names
        assert "bigtool" in names
        assert "rerank" in names
        assert "e2e" in names

    def test_intent_only(self):
        ledger = EvalLedger()
        results = ledger.evaluate_query(
            query="Q?",
            expected_tool="t1",
            intent_results=["t1"],
        )
        assert len(results) == 1
        assert results[0].stage_name == "intent"
        assert results[0].precision_at_1 == 1.0

    def test_reranker_delta(self):
        ledger = EvalLedger()
        results = ledger.evaluate_query(
            query="Q?",
            expected_tool="t1",
            bigtool_results=["t2", "t3", "t1"],
            rerank_results=["t1", "t2", "t3"],
        )
        rerank = next(r for r in results if r.stage_name == "rerank")
        assert rerank.reranker_delta is not None
        assert rerank.reranker_delta > 0  # Improved from pos 3 to pos 1

    def test_e2e_correct(self):
        ledger = EvalLedger()
        results = ledger.evaluate_query(
            query="Q?",
            expected_tool="t1",
            e2e_result="t1",
        )
        assert len(results) == 1
        assert results[0].precision_at_1 == 1.0

    def test_e2e_incorrect(self):
        ledger = EvalLedger()
        results = ledger.evaluate_query(
            query="Q?",
            expected_tool="t1",
            e2e_result="t2",
        )
        assert results[0].precision_at_1 == 0.0

    def test_with_namespace(self):
        ledger = EvalLedger()
        results = ledger.evaluate_query(
            query="Q?",
            expected_tool="t1",
            intent_results=["t1"],
            namespace="tools/kunskap",
        )
        assert results[0].namespace == "tools/kunskap"

    def test_no_data_returns_empty(self):
        ledger = EvalLedger()
        results = ledger.evaluate_query(query="Q?", expected_tool="t1")
        assert results == []


# ---------------------------------------------------------------------------
# aggregate_results
# ---------------------------------------------------------------------------


class TestAggregateResults:
    def test_basic_aggregation(self):
        ledger = EvalLedger()
        r1 = ledger.evaluate_query("Q1", "t1", intent_results=["t1", "t2"])
        r2 = ledger.evaluate_query("Q2", "t2", intent_results=["t2", "t1"])
        agg = ledger.aggregate_results([r1, r2])
        assert "intent" in agg
        assert agg["intent"].precision_at_1 == 1.0  # Both correct at pos 1

    def test_mixed_results(self):
        ledger = EvalLedger()
        r1 = ledger.evaluate_query("Q1", "t1", intent_results=["t1"])
        r2 = ledger.evaluate_query("Q2", "t1", intent_results=["t2"])
        agg = ledger.aggregate_results([r1, r2])
        assert agg["intent"].precision_at_1 == 0.5  # 50% correct

    def test_empty_input(self):
        ledger = EvalLedger()
        agg = ledger.aggregate_results([])
        assert agg == {}


# ---------------------------------------------------------------------------
# aggregate_by_namespace
# ---------------------------------------------------------------------------


class TestAggregateByNamespace:
    def test_groups_by_namespace(self):
        ledger = EvalLedger()
        r1 = ledger.evaluate_query("Q1", "t1", intent_results=["t1"], namespace="ns_a")
        r2 = ledger.evaluate_query("Q2", "t2", intent_results=["t2"], namespace="ns_b")
        by_ns = ledger.aggregate_by_namespace([r1, r2])
        assert "ns_a" in by_ns
        assert "ns_b" in by_ns


# ---------------------------------------------------------------------------
# StageResult / EvalRun dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_stage_result_defaults(self):
        sr = StageResult(stage=1, stage_name="intent")
        assert sr.precision_at_1 is None
        assert sr.reranker_delta is None

    def test_eval_run_defaults(self):
        run = EvalRun()
        assert run.stages == []
        assert run.total_queries == 0
