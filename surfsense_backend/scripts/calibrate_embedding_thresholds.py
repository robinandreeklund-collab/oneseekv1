#!/usr/bin/env python
"""
Calibrate retrieval-tuning thresholds after an embedding model change.

This script builds the full tool index with the currently configured
embedding model, runs a set of representative Swedish probe queries,
and reports the resulting score distributions.  The output tells you
whether the existing thresholds (tool_auto_score_threshold,
agent_auto_margin_threshold, etc.) still make sense with the new model.

Usage
-----
    cd surfsense_backend
    python scripts/calibrate_embedding_thresholds.py

    # Only probe a specific scope (e.g. weather tools)
    python scripts/calibrate_embedding_thresholds.py --scope weather

    # Write a JSON report to disk
    python scripts/calibrate_embedding_thresholds.py --output report.json

    # Use custom queries from a file (one query per line)
    python scripts/calibrate_embedding_thresholds.py --queries-file my_queries.txt
"""

import argparse
import json
import logging
import math
import statistics
import sys
import time
from pathlib import Path

# Ensure app modules are importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("calibrate_thresholds")

# ---------------------------------------------------------------------------
# Representative probe queries grouped by expected domain.
# These cover all major tool namespaces so we can measure cross-domain
# similarity distributions.
# ---------------------------------------------------------------------------
PROBE_QUERIES: dict[str, list[str]] = {
    "weather": [
        "Hur blir vädret i Stockholm imorgon?",
        "Vad är temperaturen i Göteborg just nu?",
        "Kommer det regna i Malmö på fredag?",
        "Visa väderprognos för Uppsala kommande vecka",
        "Blåser det mycket i Visby idag?",
        "Snöprognos för Kiruna",
        "UV-index i Lund idag",
        "Pollenprognos Stockholm",
    ],
    "traffic": [
        "Finns det trafikstörningar på E4 just nu?",
        "Vilka vägarbeten pågår i Stockholms län?",
        "Hur ser trafikläget ut på Öresundsbron?",
        "Visa aktuella tågförseningar till Göteborg",
        "Är det halka på vägarna i Norrbotten?",
        "Trafikolyckor i Skåne idag",
    ],
    "statistics": [
        "Hur många invånare har Stockholms kommun?",
        "Visa befolkningsstatistik för Malmö",
        "Vad är medelinkomsten i Göteborg?",
        "Hur stor är arbetslösheten i Sverige?",
        "SCB statistik om bostadsbyggande",
        "Hur många födda barn 2024 i Uppsala?",
        "BNP-tillväxt senaste kvartalet",
        "Hushållens skuldsättning enligt SCB",
    ],
    "kolada": [
        "Kolada nyckeltal för hemtjänst i Linköpings kommun",
        "Hur stor andel elever når gymnasiebehörighet i Malmö?",
        "Jämför äldreomsorg mellan Stockholm och Göteborg",
        "Kostnad per elev i grundskolan i Umeå",
        "Kommunens skattesats i Luleå",
    ],
    "riksdagen": [
        "Senaste riksdagsbesluten om migration",
        "Visa motioner om klimatpolitik",
        "Vilka propositioner har lagts fram i år?",
        "Voteringsresultat om skatteförslag",
        "Interpellationer till finansministern",
    ],
    "maps": [
        "Visa karta över restauranger nära Stureplan",
        "Hitta närmaste apotek i Lund",
        "Var ligger Liseberg på kartan?",
    ],
    "marketplace": [
        "Sök begagnade cyklar på Blocket i Stockholm",
        "Visa billigaste bilar på Blocket under 50000 kr",
        "Tradera auktioner för samlarfrimärken",
        "Jämför priser på iPhone 15",
    ],
    "bolagsverket": [
        "Visa information om företaget Volvo AB",
        "Sök bolagsregistret efter restauranger i Malmö",
        "Vilka styrelseledamöter har Ericsson?",
    ],
    "general": [
        "Berätta om de senaste nyheterna",
        "Sammanfatta den här webbsidan",
        "Spara detta som en anteckning",
        "Sök i min kunskapsbas efter projektplaner",
        "Vad heter Sveriges statsminister?",
        "Hjälp mig skriva ett mejl",
        "Generera en podcast om AI",
    ],
}


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    norm_left = 0.0
    norm_right = 0.0
    for a, b in zip(left, right, strict=False):
        dot += a * b
        norm_left += a * a
        norm_right += b * b
    if norm_left <= 0.0 or norm_right <= 0.0:
        return 0.0
    return dot / ((norm_left**0.5) * (norm_right**0.5))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (pct / 100.0)
    floor_k = int(math.floor(k))
    ceil_k = min(int(math.ceil(k)), len(sorted_values) - 1)
    if floor_k == ceil_k:
        return sorted_values[floor_k]
    d = k - floor_k
    return sorted_values[floor_k] * (1 - d) + sorted_values[ceil_k] * d


def _build_stub_registry() -> dict:
    """Build a lightweight tool registry without DB or service dependencies.

    Creates ``StructuredTool`` stubs from all known ``*_TOOL_DEFINITIONS``
    lists and the ``BUILTIN_TOOLS`` registry so that ``build_tool_index``
    receives the same tool IDs it would at runtime.
    """
    from langchain_core.tools import StructuredTool

    from app.agents.new_chat.kolada_tools import KOLADA_TOOL_DEFINITIONS
    from app.agents.new_chat.marketplace_tools import MARKETPLACE_TOOL_DEFINITIONS
    from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
    from app.agents.new_chat.skolverket_tools import SKOLVERKET_TOOL_DEFINITIONS
    from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.geoapify_maps import GEOAPIFY_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.registry import BUILTIN_TOOLS
    from app.agents.new_chat.tools.smhi import SMHI_TOOL_DEFINITIONS
    from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS

    def _noop(**kwargs):  # noqa: ARG001
        return "stub"

    registry: dict[str, StructuredTool] = {}

    # Domain tool definitions (SCB, Kolada, SMHI, etc.)
    for definitions in [
        SCB_TOOL_DEFINITIONS,
        KOLADA_TOOL_DEFINITIONS,
        SKOLVERKET_TOOL_DEFINITIONS,
        BOLAGSVERKET_TOOL_DEFINITIONS,
        TRAFIKVERKET_TOOL_DEFINITIONS,
        SMHI_TOOL_DEFINITIONS,
        GEOAPIFY_TOOL_DEFINITIONS,
        RIKSDAGEN_TOOL_DEFINITIONS,
        MARKETPLACE_TOOL_DEFINITIONS,
    ]:
        for defn in definitions:
            tool_id = defn.tool_id
            registry[tool_id] = StructuredTool.from_function(
                func=_noop,
                name=getattr(defn, "name", tool_id),
                description=getattr(defn, "description", ""),
            )

    # Built-in tools from registry (knowledge_base, podcast, link_preview …)
    for tool_def in BUILTIN_TOOLS:
        if tool_def.name not in registry:
            registry[tool_def.name] = StructuredTool.from_function(
                func=_noop,
                name=tool_def.name,
                description=tool_def.description,
            )

    return registry


def run_calibration(args: argparse.Namespace) -> dict:
    # Import order matters — load config and the tools registry first so that
    # the circular dependency chain (bigtool_store → kolada_tools → tools →
    # registry → kolada_tools) is resolved before we touch bigtool_store.
    from app.config import config  # noqa: E402
    import app.agents.new_chat.tools.registry  # noqa: E402, F401 — trigger module load
    from app.agents.new_chat.bigtool_store import (  # noqa: E402
        DEFAULT_TOOL_RETRIEVAL_TUNING,
        _normalize_vector,
        _score_entry_components,
        build_tool_index,
    )
    from app.utils.text import normalize_text, tokenize

    # -----------------------------------------------------------------------
    # 1. Model info
    # -----------------------------------------------------------------------
    model_name = config.EMBEDDING_MODEL or "unknown"
    dimension = getattr(config.embedding_model_instance, "dimension", "?")
    embed_fn = config.embedding_model_instance.embed

    logger.info("=" * 70)
    logger.info("  Embedding model  : %s", model_name)
    logger.info("  Dimension        : %s", dimension)
    logger.info("=" * 70)

    # Smoke test
    test_vec = embed_fn("test")
    logger.info("  Smoke test OK — %d-dim vector", len(test_vec))

    # -----------------------------------------------------------------------
    # 2. Build tool index (stub tools — no DB/services required)
    # -----------------------------------------------------------------------
    logger.info("Building tool index...")
    tool_registry = _build_stub_registry()
    tool_index = build_tool_index(tool_registry)
    logger.info("  %d tools in index", len(tool_index))

    if args.scope:
        scope = args.scope.lower()
        tool_index = [
            entry
            for entry in tool_index
            if scope in entry.category.lower()
            or scope in entry.tool_id.lower()
            or any(scope in ns for ns in entry.namespace)
        ]
        logger.info("  Filtered to %d tools (scope=%s)", len(tool_index), scope)

    # -----------------------------------------------------------------------
    # 3. Collect probes
    # -----------------------------------------------------------------------
    if args.queries_file:
        queries_path = Path(args.queries_file)
        queries = [
            line.strip()
            for line in queries_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        probe_queries = {"custom": queries}
    else:
        probe_queries = PROBE_QUERIES

    total_probes = sum(len(qs) for qs in probe_queries.values())
    logger.info("  %d probe queries across %d domains", total_probes, len(probe_queries))

    # -----------------------------------------------------------------------
    # 4. Run probes and collect scores
    # -----------------------------------------------------------------------
    tuning = DEFAULT_TOOL_RETRIEVAL_TUNING

    # Accumulators
    all_semantic_scores: list[float] = []
    all_structural_scores: list[float] = []
    all_pre_rerank_scores: list[float] = []
    all_top1_scores: list[float] = []
    all_top2_scores: list[float] = []
    all_margins: list[float] = []
    all_embedding_weighted: list[float] = []

    probe_results: list[dict] = []

    start_time = time.monotonic()

    for domain, queries in probe_queries.items():
        for query in queries:
            query_norm = normalize_text(query)
            query_tokens = set(tokenize(query_norm))

            # Embed the query
            try:
                query_embedding = _normalize_vector(embed_fn(query))
            except Exception:
                query_embedding = None

            scored: list[dict] = []

            for entry in tool_index:
                components = _score_entry_components(
                    entry, query_tokens, query_norm, tuning
                )

                semantic_score = 0.0
                structural_score = 0.0
                semantic_embedding = entry.semantic_embedding or entry.embedding
                structural_embedding = entry.structural_embedding

                if query_embedding and semantic_embedding:
                    semantic_score = _cosine_similarity(query_embedding, semantic_embedding)
                if query_embedding and structural_embedding:
                    structural_score = _cosine_similarity(query_embedding, structural_embedding)

                semantic_weighted = semantic_score * tuning.semantic_embedding_weight
                structural_weighted = structural_score * tuning.structural_embedding_weight
                embedding_weighted = semantic_weighted + structural_weighted

                pre_rerank_score = (
                    components["lexical_score"] + embedding_weighted
                )

                all_semantic_scores.append(semantic_score)
                all_structural_scores.append(structural_score)
                all_embedding_weighted.append(embedding_weighted)

                scored.append({
                    "tool_id": entry.tool_id,
                    "category": entry.category,
                    "semantic_raw": round(semantic_score, 4),
                    "structural_raw": round(structural_score, 4),
                    "semantic_weighted": round(semantic_weighted, 4),
                    "structural_weighted": round(structural_weighted, 4),
                    "embedding_weighted": round(embedding_weighted, 4),
                    "lexical_score": round(components["lexical_score"], 4),
                    "pre_rerank_score": round(pre_rerank_score, 4),
                })

            scored.sort(key=lambda x: x["pre_rerank_score"], reverse=True)

            top1 = scored[0] if scored else None
            top2 = scored[1] if len(scored) > 1 else None

            top1_score = top1["pre_rerank_score"] if top1 else 0.0
            top2_score = top2["pre_rerank_score"] if top2 else 0.0
            margin = top1_score - top2_score

            all_pre_rerank_scores.extend(item["pre_rerank_score"] for item in scored)
            all_top1_scores.append(top1_score)
            all_top2_scores.append(top2_score)
            all_margins.append(margin)

            # Check auto-select with current thresholds
            tool_auto = (
                top1_score >= tuning.tool_auto_score_threshold
                and margin >= tuning.tool_auto_margin_threshold
            )
            agent_auto = (
                top1_score >= tuning.agent_auto_score_threshold
                and margin >= tuning.agent_auto_margin_threshold
            )

            probe_results.append({
                "domain": domain,
                "query": query,
                "top1_tool": top1["tool_id"] if top1 else None,
                "top1_score": round(top1_score, 4),
                "top1_semantic_raw": top1["semantic_raw"] if top1 else 0,
                "top1_embedding_weighted": top1["embedding_weighted"] if top1 else 0,
                "top1_lexical": top1["lexical_score"] if top1 else 0,
                "top2_tool": top2["tool_id"] if top2 else None,
                "top2_score": round(top2_score, 4),
                "margin": round(margin, 4),
                "tool_auto_select": tool_auto,
                "agent_auto_select": agent_auto,
                "top5": [
                    {
                        "tool_id": item["tool_id"],
                        "score": item["pre_rerank_score"],
                        "sem": item["semantic_raw"],
                        "struct": item["structural_raw"],
                        "lex": item["lexical_score"],
                    }
                    for item in scored[:5]
                ],
            })

    elapsed = time.monotonic() - start_time

    # -----------------------------------------------------------------------
    # 5. Compute distribution statistics
    # -----------------------------------------------------------------------
    def dist_stats(values: list[float], label: str) -> dict:
        if not values:
            return {"label": label, "count": 0}
        return {
            "label": label,
            "count": len(values),
            "mean": round(statistics.mean(values), 4),
            "median": round(statistics.median(values), 4),
            "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "p10": round(_percentile(values, 10), 4),
            "p25": round(_percentile(values, 25), 4),
            "p75": round(_percentile(values, 75), 4),
            "p90": round(_percentile(values, 90), 4),
            "p95": round(_percentile(values, 95), 4),
        }

    distributions = {
        "semantic_raw": dist_stats(all_semantic_scores, "Semantic cosine (raw)"),
        "structural_raw": dist_stats(all_structural_scores, "Structural cosine (raw)"),
        "embedding_weighted": dist_stats(all_embedding_weighted, "Embedding weighted (sem*2.8 + struct*1.2)"),
        "pre_rerank_all": dist_stats(all_pre_rerank_scores, "Pre-rerank score (all tools)"),
        "top1_scores": dist_stats(all_top1_scores, "Top-1 pre-rerank score"),
        "top2_scores": dist_stats(all_top2_scores, "Top-2 pre-rerank score"),
        "margins": dist_stats(all_margins, "Margin (top1 - top2)"),
    }

    # -----------------------------------------------------------------------
    # 6. Threshold analysis
    # -----------------------------------------------------------------------
    current_thresholds = {
        "tool_auto_score_threshold": tuning.tool_auto_score_threshold,
        "tool_auto_margin_threshold": tuning.tool_auto_margin_threshold,
        "agent_auto_score_threshold": tuning.agent_auto_score_threshold,
        "agent_auto_margin_threshold": tuning.agent_auto_margin_threshold,
        "adaptive_threshold_delta": tuning.adaptive_threshold_delta,
        "semantic_embedding_weight": tuning.semantic_embedding_weight,
        "structural_embedding_weight": tuning.structural_embedding_weight,
        "intent_embedding_weight": tuning.intent_embedding_weight,
    }

    tool_auto_count = sum(1 for p in probe_results if p["tool_auto_select"])
    agent_auto_count = sum(1 for p in probe_results if p["agent_auto_select"])
    tool_auto_rate = tool_auto_count / len(probe_results) if probe_results else 0
    agent_auto_rate = agent_auto_count / len(probe_results) if probe_results else 0

    threshold_analysis = {
        "total_probes": len(probe_results),
        "tool_auto_select_count": tool_auto_count,
        "tool_auto_select_rate": round(tool_auto_rate, 3),
        "agent_auto_select_count": agent_auto_count,
        "agent_auto_select_rate": round(agent_auto_rate, 3),
    }

    # Suggested thresholds based on distribution
    # Target: ~30-40% auto-select rate for tool gate
    suggested = {}
    if all_top1_scores:
        suggested["tool_auto_score_threshold"] = round(
            _percentile(all_top1_scores, 60), 2
        )
        suggested["agent_auto_score_threshold"] = round(
            _percentile(all_top1_scores, 50), 2
        )
    if all_margins:
        suggested["tool_auto_margin_threshold"] = round(
            _percentile(all_margins, 40), 2
        )
        suggested["agent_auto_margin_threshold"] = round(
            _percentile(all_margins, 30), 2
        )

    # BSSS-relevant: similarity between tools in same namespace
    logger.info("Computing intra-namespace similarity matrix...")
    namespace_similarities: dict[str, list[float]] = {}
    for i, entry_a in enumerate(tool_index):
        ns_key = "/".join(entry_a.namespace[:2])
        if ns_key not in namespace_similarities:
            namespace_similarities[ns_key] = []
        for j, entry_b in enumerate(tool_index):
            if i >= j:
                continue
            if entry_a.namespace[:2] != entry_b.namespace[:2]:
                continue
            sem_a = entry_a.semantic_embedding or entry_a.embedding
            sem_b = entry_b.semantic_embedding or entry_b.embedding
            if sem_a and sem_b:
                sim = _cosine_similarity(sem_a, sem_b)
                namespace_similarities[ns_key].append(sim)

    intra_namespace_stats: dict[str, dict] = {}
    for ns, sims in namespace_similarities.items():
        if sims:
            intra_namespace_stats[ns] = {
                "pairs": len(sims),
                "mean": round(statistics.mean(sims), 4),
                "max": round(max(sims), 4),
                "min": round(min(sims), 4),
                "above_085": sum(1 for s in sims if s > 0.85),
                "above_090": sum(1 for s in sims if s > 0.90),
            }

    # -----------------------------------------------------------------------
    # 7. Build report
    # -----------------------------------------------------------------------
    report = {
        "model": {
            "name": model_name,
            "dimension": dimension,
        },
        "tool_count": len(tool_index),
        "probe_count": len(probe_results),
        "elapsed_seconds": round(elapsed, 1),
        "distributions": distributions,
        "current_thresholds": current_thresholds,
        "threshold_analysis": threshold_analysis,
        "suggested_thresholds": suggested,
        "intra_namespace_similarity": intra_namespace_stats,
        "bsss_global_similarity_threshold_assessment": {
            "current_threshold": 0.85,
            "namespaces_with_pairs_above_threshold": {
                ns: stats
                for ns, stats in intra_namespace_stats.items()
                if stats.get("above_085", 0) > 0
            },
            "recommendation": (
                "LOWER threshold"
                if sum(
                    stats.get("above_085", 0)
                    for stats in intra_namespace_stats.values()
                )
                > len(intra_namespace_stats) * 0.5
                else "KEEP threshold at 0.85"
            ),
        },
        "probes": probe_results,
    }

    return report


def print_report(report: dict) -> None:
    """Print a human-readable summary to stdout."""
    print()
    print("=" * 70)
    print(f"  CALIBRATION REPORT — {report['model']['name']}")
    print(f"  Dimension: {report['model']['dimension']}   "
          f"Tools: {report['tool_count']}   "
          f"Probes: {report['probe_count']}   "
          f"Time: {report['elapsed_seconds']}s")
    print("=" * 70)

    print()
    print("SCORE DISTRIBUTIONS")
    print("-" * 70)
    for key, dist in report["distributions"].items():
        if dist.get("count", 0) == 0:
            continue
        print(f"  {dist['label']}:")
        print(f"    mean={dist['mean']:.4f}  median={dist['median']:.4f}  "
              f"stdev={dist['stdev']:.4f}")
        print(f"    min={dist['min']:.4f}  p10={dist['p10']:.4f}  "
              f"p25={dist['p25']:.4f}  p75={dist['p75']:.4f}  "
              f"p90={dist['p90']:.4f}  max={dist['max']:.4f}")
        print()

    print("CURRENT vs SUGGESTED THRESHOLDS")
    print("-" * 70)
    current = report["current_thresholds"]
    suggested = report.get("suggested_thresholds", {})
    analysis = report["threshold_analysis"]

    print(f"  {'Parameter':<35} {'Current':>10} {'Suggested':>10} {'Delta':>10}")
    print(f"  {'─' * 35} {'─' * 10} {'─' * 10} {'─' * 10}")
    for key in ["tool_auto_score_threshold", "tool_auto_margin_threshold",
                "agent_auto_score_threshold", "agent_auto_margin_threshold"]:
        cur = current.get(key, 0)
        sug = suggested.get(key, cur)
        delta = sug - cur
        flag = " ◀" if abs(delta) > 0.05 else ""
        print(f"  {key:<35} {cur:>10.2f} {sug:>10.2f} {delta:>+10.2f}{flag}")

    print()
    print(f"  Tool auto-select rate:  {analysis['tool_auto_select_count']}"
          f"/{analysis['total_probes']}"
          f" ({analysis['tool_auto_select_rate']:.0%})")
    print(f"  Agent auto-select rate: {analysis['agent_auto_select_count']}"
          f"/{analysis['total_probes']}"
          f" ({analysis['agent_auto_select_rate']:.0%})")
    target = "30-50%"
    if analysis["tool_auto_select_rate"] < 0.1:
        print(f"  ⚠  Tool auto-select rate is very low — thresholds are too strict "
              f"for this model. Target: {target}")
    elif analysis["tool_auto_select_rate"] > 0.7:
        print(f"  ⚠  Tool auto-select rate is very high — thresholds may be too "
              f"lenient. Target: {target}")
    else:
        print(f"  ✓  Tool auto-select rate is within target range ({target})")

    print()
    print("INTRA-NAMESPACE SIMILARITY (BSSS relevance)")
    print("-" * 70)
    intra = report.get("intra_namespace_similarity", {})
    if intra:
        print(f"  {'Namespace':<25} {'Pairs':>6} {'Mean':>8} {'Max':>8} "
              f"{'>.85':>6} {'>.90':>6}")
        print(f"  {'─' * 25} {'─' * 6} {'─' * 8} {'─' * 8} {'─' * 6} {'─' * 6}")
        for ns, stats in sorted(intra.items()):
            print(f"  {ns:<25} {stats['pairs']:>6} {stats['mean']:>8.4f} "
                  f"{stats['max']:>8.4f} {stats['above_085']:>6} "
                  f"{stats['above_090']:>6}")
    else:
        print("  No intra-namespace pairs found.")

    bsss = report.get("bsss_global_similarity_threshold_assessment", {})
    if bsss.get("namespaces_with_pairs_above_threshold"):
        print()
        print(f"  ⚠  BSSS: {len(bsss['namespaces_with_pairs_above_threshold'])} "
              f"namespace(s) have tool pairs above 0.85 threshold")
        print(f"  Recommendation: {bsss['recommendation']}")
    else:
        print()
        print("  ✓  BSSS: No tool pairs exceed 0.85 threshold")

    print()
    print("PER-PROBE RESULTS (top 5 per query)")
    print("-" * 70)
    for probe in report["probes"]:
        auto_flag = ""
        if probe["tool_auto_select"]:
            auto_flag = " [TOOL-AUTO]"
        elif probe["agent_auto_select"]:
            auto_flag = " [AGENT-AUTO]"
        print(f"\n  [{probe['domain']}] {probe['query']}")
        print(f"    top1={probe['top1_tool']}  score={probe['top1_score']:.4f}  "
              f"margin={probe['margin']:.4f}{auto_flag}")
        for i, item in enumerate(probe["top5"], 1):
            print(f"      {i}. {item['tool_id']:<40} "
                  f"score={item['score']:.4f}  "
                  f"sem={item['sem']:.4f}  "
                  f"struct={item['struct']:.4f}  "
                  f"lex={item['lex']:.4f}")

    print()
    print("=" * 70)
    print("Done.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calibrate retrieval tuning thresholds for a new embedding model.",
    )
    parser.add_argument(
        "--scope",
        default=None,
        help="Filter tools to a specific scope/category (e.g. weather, statistics)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write full JSON report to this file",
    )
    parser.add_argument(
        "--queries-file",
        default=None,
        help="Path to a text file with custom probe queries (one per line)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = run_calibration(args)
    print_report(report)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Full JSON report written to %s", output_path)
