"""
Tool Evaluation Service

This module provides a comprehensive evaluation system for testing the tool selection
pipeline without making real API calls. It evaluates four layers:
1. Route classification (dispatcher regex patterns)
2. Sub-route classification (knowledge_router/action_router patterns)
3. Agent selection (_smart_retrieve_agents)
4. Tool retrieval (smart_retrieve_tools with full scoring pipeline)

The evaluation uses the EXACT same scoring/embedding/reranking pipeline as production
so results are representative.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Literal
from pathlib import Path

from langchain_core.tools import tool, BaseTool

# Import tool retrieval components from bigtool_store
from app.agents.new_chat.bigtool_store import (
    ToolIndexEntry,
    build_tool_index,
    smart_retrieve_tools,
    get_tool_rerank_trace,
    _normalize_text,
    _tokenize,
    _score_entry,
    _cosine_similarity,
    _normalize_vector,
    TOOL_EMBEDDING_WEIGHT,
)

# Import routing patterns from dispatcher
from app.agents.new_chat.dispatcher import (
    _ACTION_PATTERNS,
    _KNOWLEDGE_PATTERNS,
    _STATISTICS_PATTERNS,
    _GREETING_REGEX,
    _URL_REGEX,
)

# Import sub-route patterns from routers
from app.agents.new_chat.knowledge_router import (
    _DOCS_PATTERNS,
    _EXTERNAL_PATTERNS,
)

from app.agents.new_chat.action_router import (
    _WEB_PATTERNS,
    _MEDIA_PATTERNS,
    _TRAVEL_PATTERNS,
    _DATA_PATTERNS,
)

# Import agent selection
from app.agents.new_chat.supervisor_agent import _smart_retrieve_agents, AgentDefinition

# Import tool definitions
from app.agents.new_chat.statistics_agent import SCB_TOOL_DEFINITIONS
from app.agents.new_chat.riksdagen_agent import RIKSDAGEN_TOOL_DEFINITIONS
from app.agents.new_chat.tools.bolagsverket import BOLAGSVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.tools.trafikverket import TRAFIKVERKET_TOOL_DEFINITIONS
from app.agents.new_chat.tools.geoapify_maps import GEOAPIFY_TOOL_DEFINITIONS
from app.agents.new_chat.tools.registry import BUILTIN_TOOLS

# Type aliases
Route = Literal["knowledge", "action", "statistics", "smalltalk", "compare"]
SubRoute = Literal["docs", "internal", "external", "web", "media", "travel", "data"]
MatchType = Literal["exact_match", "acceptable_match", "partial_match", "no_match"]


@dataclass
class TestCase:
    """A single test case for evaluation."""
    id: str
    query: str
    expected_route: Route | None = None
    expected_sub_route: SubRoute | None = None
    expected_agents: list[str] | None = None
    expected_tools: list[str] | None = None
    acceptable_tools: list[str] | None = None
    tags: list[str] = field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    language: Literal["sv", "en"] = "sv"


@dataclass
class CategorySuite:
    """A category of related test cases."""
    category_id: str
    category_name: str
    test_cases: list[TestCase]


@dataclass
class EvalConfig:
    """Configuration for evaluation run."""
    tool_retrieval: dict[str, Any] = field(default_factory=lambda: {
        "limit": 2,
        "use_reranker": True,
        "use_embeddings": True,
        "primary_namespaces": [["tools"]],
        "fallback_namespaces": [],
    })
    scoring: dict[str, float] = field(default_factory=lambda: {
        "route_correct_weight": 0.15,
        "sub_route_correct_weight": 0.10,
        "agent_correct_weight": 0.25,
        "exact_match_weight": 0.30,
        "acceptable_match_weight": 0.20,
    })
    test_routing: bool = True
    test_agents: bool = True


@dataclass
class EvalSuite:
    """Complete evaluation test suite."""
    name: str
    description: str
    config: EvalConfig
    categories: list[CategorySuite]


@dataclass
class ScoringDetail:
    """Detailed scoring information for a tool."""
    tool_id: str
    name: str
    namespace: tuple[str, ...]
    base_score: float
    semantic_score: float
    total_score: float
    keywords_matched: list[str]
    examples_matched: list[str]


@dataclass
class SingleResult:
    """Result of evaluating a single test case."""
    test_case_id: str
    query: str
    
    # Route evaluation
    predicted_route: Route | None = None
    route_correct: bool = False
    
    # Sub-route evaluation
    predicted_sub_route: SubRoute | None = None
    sub_route_correct: bool = False
    
    # Agent evaluation
    selected_agents: list[str] = field(default_factory=list)
    agent_overlap: float = 0.0  # Jaccard similarity
    agent_correct: bool = False
    
    # Tool evaluation
    selected_tools: list[str] = field(default_factory=list)
    tool_match_type: MatchType = "no_match"
    tool_scoring_details: list[ScoringDetail] = field(default_factory=list)
    
    # Composite scoring
    composite_score: float = 0.0
    
    # Diagnostics
    latency_ms: float = 0.0
    failure_reasons: list[str] = field(default_factory=list)
    rerank_trace: list[dict[str, Any]] | None = None


@dataclass
class CategoryResult:
    """Aggregated results for a category."""
    category_id: str
    category_name: str
    total_tests: int
    
    # Route metrics
    route_accuracy: float = 0.0
    sub_route_accuracy: float = 0.0
    
    # Agent metrics
    agent_exact_rate: float = 0.0
    agent_avg_overlap: float = 0.0
    
    # Tool metrics
    tool_exact_rate: float = 0.0
    tool_acceptable_rate: float = 0.0
    tool_partial_rate: float = 0.0
    
    # Composite metrics
    avg_composite_score: float = 0.0
    avg_latency_ms: float = 0.0
    
    # Failed tests
    failed_tests: list[SingleResult] = field(default_factory=list)


@dataclass
class EvalReport:
    """Complete evaluation report."""
    suite_name: str
    total_tests: int
    timestamp: str
    
    # Overall metrics
    overall_route_accuracy: float = 0.0
    overall_sub_route_accuracy: float = 0.0
    overall_agent_exact_rate: float = 0.0
    overall_agent_avg_overlap: float = 0.0
    overall_tool_exact_rate: float = 0.0
    overall_tool_acceptable_rate: float = 0.0
    overall_tool_partial_rate: float = 0.0
    overall_avg_composite_score: float = 0.0
    overall_avg_latency_ms: float = 0.0
    
    # By category
    category_results: list[CategoryResult] = field(default_factory=list)
    
    # By difficulty
    by_difficulty: dict[str, dict[str, float]] = field(default_factory=dict)
    
    # Confusion matrix for routes
    route_confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    
    # Failure patterns
    failure_patterns: dict[str, int] = field(default_factory=dict)
    
    # Recommendations
    recommendations: list[str] = field(default_factory=list)


def parse_eval_suite(raw: dict[str, Any]) -> EvalSuite:
    """Parse uploaded JSON into typed EvalSuite."""
    config_data = raw.get("config", {})
    config = EvalConfig(
        tool_retrieval=config_data.get("tool_retrieval", {}),
        scoring=config_data.get("scoring", {}),
        test_routing=config_data.get("test_routing", True),
        test_agents=config_data.get("test_agents", True),
    )
    
    categories = []
    for cat_data in raw.get("categories", []):
        test_cases = []
        for tc_data in cat_data.get("test_cases", []):
            test_case = TestCase(
                id=tc_data["id"],
                query=tc_data["query"],
                expected_route=tc_data.get("expected_route"),
                expected_sub_route=tc_data.get("expected_sub_route"),
                expected_agents=tc_data.get("expected_agents"),
                expected_tools=tc_data.get("expected_tools"),
                acceptable_tools=tc_data.get("acceptable_tools"),
                tags=tc_data.get("tags", []),
                difficulty=tc_data.get("difficulty", "medium"),
                language=tc_data.get("language", "sv"),
            )
            test_cases.append(test_case)
        
        category = CategorySuite(
            category_id=cat_data["category_id"],
            category_name=cat_data["category_name"],
            test_cases=test_cases,
        )
        categories.append(category)
    
    return EvalSuite(
        name=raw.get("name", "Unnamed Suite"),
        description=raw.get("description", ""),
        config=config,
        categories=categories,
    )


def load_eval_suite_from_file(path: str | Path) -> EvalSuite:
    """Load evaluation suite from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return parse_eval_suite(raw)


def _matches_any(patterns: list[str], text: str) -> bool:
    """Check if text matches any of the regex patterns."""
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _eval_route(query: str) -> Route | None:
    """
    Evaluate route classification using regex patterns ONLY (no LLM fallback).
    This tests the regex patterns from dispatcher.py.
    """
    text = (query or "").strip()
    if not text:
        return "smalltalk"
    
    if text.lower().startswith("/compare"):
        return "compare"
    
    if _GREETING_REGEX.match(text) and len(text) <= 20:
        return "smalltalk"
    
    if _URL_REGEX.search(text) or _matches_any(_ACTION_PATTERNS, text):
        return "action"
    
    if _matches_any(_STATISTICS_PATTERNS, text):
        return "statistics"
    
    if _matches_any(_KNOWLEDGE_PATTERNS, text):
        return "knowledge"
    
    # If no pattern matches, default to knowledge (no LLM fallback in evaluation)
    return "knowledge"


def _eval_sub_route(query: str, predicted_route: Route | None) -> SubRoute | None:
    """
    Evaluate sub-route classification using regex patterns ONLY.
    This tests the patterns from knowledge_router.py and action_router.py.
    """
    text = (query or "").strip().lower()
    
    if predicted_route == "knowledge":
        # Knowledge sub-routes
        if _matches_any(_DOCS_PATTERNS, text):
            return "docs"
        if _matches_any(_EXTERNAL_PATTERNS, text):
            return "external"
        return "internal"  # default for knowledge
    
    elif predicted_route == "action":
        # Action sub-routes
        if _matches_any(_WEB_PATTERNS, text):
            return "web"
        if _matches_any(_MEDIA_PATTERNS, text):
            return "media"
        if _matches_any(_TRAVEL_PATTERNS, text):
            return "travel"
        if _matches_any(_DATA_PATTERNS, text):
            return "data"
        return "web"  # default for action
    
    return None


def _jaccard_similarity(set1: list[str], set2: list[str]) -> float:
    """Calculate Jaccard similarity between two lists."""
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    s1 = set(set1)
    s2 = set(set2)
    intersection = len(s1 & s2)
    union = len(s1 | s2)
    return intersection / union if union > 0 else 0.0


def _build_stub_tool_registry() -> dict[str, BaseTool]:
    """
    Build a stub tool registry with correct names/descriptions but NO real implementations.
    Uses the @tool decorator to create stub tools.
    """
    registry: dict[str, BaseTool] = {}
    
    # Helper to create a stub tool
    def make_stub(tool_id: str, description: str) -> BaseTool:
        @tool(name=tool_id, description=description)
        def stub_tool(query: str = "") -> str:
            """Stub tool that does nothing."""
            return f"[Stub] {tool_id}"
        return stub_tool
    
    # Add SCB tools
    for definition in SCB_TOOL_DEFINITIONS:
        registry[definition.tool_id] = make_stub(definition.tool_id, definition.description)
    
    # Add Riksdagen tools
    for definition in RIKSDAGEN_TOOL_DEFINITIONS:
        registry[definition.tool_id] = make_stub(definition.tool_id, definition.description)
    
    # Add Bolagsverket tools
    for definition in BOLAGSVERKET_TOOL_DEFINITIONS:
        registry[definition.tool_id] = make_stub(definition.tool_id, definition.description)
    
    # Add Trafikverket tools
    for definition in TRAFIKVERKET_TOOL_DEFINITIONS:
        registry[definition.tool_id] = make_stub(definition.tool_id, definition.description)
    
    # Add Geoapify tools
    for definition in GEOAPIFY_TOOL_DEFINITIONS:
        registry[definition.tool_id] = make_stub(definition.tool_id, definition.description)
    
    # Add builtin tools (these need special handling since they have factory functions)
    builtin_names = [
        "search_knowledge_base",
        "search_surfsense_docs",
        "search_tavily",
        "save_memory",
        "recall_memory",
        "generate_podcast",
        "scrape_webpage",
        "display_image",
        "link_preview",
        "geoapify_static_map",
        "smhi_weather",
        "trafiklab_route",
        "libris_search",
        "jobad_links_search",
        "write_todos",
        "reflect_on_progress",
        # Compare tools
        "call_grok",
        "call_gpt",
        "call_claude",
        "call_gemini",
        "call_deepseek",
        "call_perplexity",
        "call_qwen",
    ]
    
    for builtin_name in builtin_names:
        # Find the description from BUILTIN_TOOLS if available
        description = f"Built-in tool: {builtin_name}"
        for tool_def in BUILTIN_TOOLS:
            if tool_def.name == builtin_name:
                description = tool_def.description
                break
        registry[builtin_name] = make_stub(builtin_name, description)
    
    return registry


def _extract_scoring_details(
    query: str,
    tool_index: list[ToolIndexEntry],
    selected_tool_ids: list[str],
) -> list[ScoringDetail]:
    """Extract detailed scoring information for selected tools."""
    query_norm = _normalize_text(query)
    query_tokens = set(_tokenize(query_norm))
    
    # Get query embedding
    query_embedding: list[float] | None = None
    try:
        from app.config import config
        query_embedding = _normalize_vector(
            config.embedding_model_instance.embed(query)
        )
    except Exception:
        pass
    
    details: list[ScoringDetail] = []
    tool_index_map = {entry.tool_id: entry for entry in tool_index}
    
    for tool_id in selected_tool_ids:
        entry = tool_index_map.get(tool_id)
        if not entry:
            continue
        
        # Calculate base score
        base_score = float(_score_entry(entry, query_tokens, query_norm))
        
        # Calculate semantic score
        semantic_score = 0.0
        if query_embedding and entry.embedding:
            semantic_score = _cosine_similarity(query_embedding, entry.embedding)
        
        # Total score
        total_score = base_score + (semantic_score * TOOL_EMBEDDING_WEIGHT)
        
        # Find matched keywords
        keywords_matched = []
        for keyword in entry.keywords:
            if _normalize_text(keyword) in query_norm:
                keywords_matched.append(keyword)
        
        # Find matched examples
        examples_matched = []
        for example in entry.example_queries:
            if _normalize_text(example) in query_norm:
                examples_matched.append(example)
        
        details.append(ScoringDetail(
            tool_id=tool_id,
            name=entry.name,
            namespace=entry.namespace,
            base_score=base_score,
            semantic_score=semantic_score,
            total_score=total_score,
            keywords_matched=keywords_matched,
            examples_matched=examples_matched,
        ))
    
    return details


def evaluate_single(
    tc: TestCase,
    tool_index: list[ToolIndexEntry],
    config: EvalConfig,
    agent_definitions: list[AgentDefinition] | None = None,
) -> SingleResult:
    """
    Evaluate a single test case through all four layers.
    Returns detailed results including scoring and diagnostics.
    """
    start_time = time.time()
    result = SingleResult(
        test_case_id=tc.id,
        query=tc.query,
    )
    
    # Layer 1: Route classification
    if config.test_routing and tc.expected_route:
        result.predicted_route = _eval_route(tc.query)
        result.route_correct = (result.predicted_route == tc.expected_route)
    
    # Layer 2: Sub-route classification
    if config.test_routing and tc.expected_sub_route:
        result.predicted_sub_route = _eval_sub_route(tc.query, result.predicted_route)
        result.sub_route_correct = (result.predicted_sub_route == tc.expected_sub_route)
    
    # Layer 3: Agent selection
    if config.test_agents and tc.expected_agents and agent_definitions:
        try:
            selected = _smart_retrieve_agents(
                tc.query,
                agent_definitions=agent_definitions,
                recent_agents=None,
                limit=3,
            )
            result.selected_agents = [agent.name for agent in selected]
            result.agent_overlap = _jaccard_similarity(result.selected_agents, tc.expected_agents)
            result.agent_correct = (set(result.selected_agents) == set(tc.expected_agents))
        except Exception as e:
            result.failure_reasons.append(f"Agent selection failed: {str(e)}")
    
    # Layer 4: Tool retrieval
    if tc.expected_tools:
        try:
            tool_config = config.tool_retrieval
            primary_namespaces = [tuple(ns) for ns in tool_config.get("primary_namespaces", [["tools"]])]
            fallback_namespaces = [tuple(ns) for ns in tool_config.get("fallback_namespaces", [])]
            limit = tool_config.get("limit", 2)
            
            trace_key = f"eval_{tc.id}"
            result.selected_tools = smart_retrieve_tools(
                tc.query,
                tool_index=tool_index,
                primary_namespaces=primary_namespaces,
                fallback_namespaces=fallback_namespaces,
                limit=limit,
                trace_key=trace_key,
            )
            
            # Get rerank trace
            result.rerank_trace = get_tool_rerank_trace(trace_key, query=tc.query)
            
            # Get detailed scoring
            result.tool_scoring_details = _extract_scoring_details(
                tc.query,
                tool_index,
                result.selected_tools,
            )
            
            # Determine match type
            selected_set = set(result.selected_tools)
            expected_set = set(tc.expected_tools)
            acceptable_set = set(tc.acceptable_tools or []) | expected_set
            
            if selected_set == expected_set:
                result.tool_match_type = "exact_match"
            elif selected_set <= acceptable_set:
                result.tool_match_type = "acceptable_match"
            elif selected_set & expected_set:
                result.tool_match_type = "partial_match"
            else:
                result.tool_match_type = "no_match"
            
            # Add failure diagnostics
            if result.tool_match_type == "no_match":
                result.failure_reasons.append(
                    f"Selected {result.selected_tools} but expected {tc.expected_tools}"
                )
                if result.tool_scoring_details:
                    top_tool = result.tool_scoring_details[0]
                    result.failure_reasons.append(
                        f"Top tool {top_tool.tool_id} scored {top_tool.total_score:.2f} "
                        f"(base: {top_tool.base_score}, semantic: {top_tool.semantic_score:.2f})"
                    )
                    if top_tool.keywords_matched:
                        result.failure_reasons.append(
                            f"Matched keywords: {', '.join(top_tool.keywords_matched)}"
                        )
        
        except Exception as e:
            result.failure_reasons.append(f"Tool retrieval failed: {str(e)}")
    
    # Calculate composite score
    weights = config.scoring
    route_score = 1.0 if result.route_correct else 0.0
    sub_route_score = 1.0 if result.sub_route_correct else 0.0
    agent_score = result.agent_overlap
    
    tool_score = 0.0
    if result.tool_match_type == "exact_match":
        tool_score = 1.0
    elif result.tool_match_type == "acceptable_match":
        tool_score = 0.8
    elif result.tool_match_type == "partial_match":
        tool_score = 0.4
    
    result.composite_score = (
        route_score * weights.get("route_correct_weight", 0.15) +
        sub_route_score * weights.get("sub_route_correct_weight", 0.10) +
        agent_score * weights.get("agent_correct_weight", 0.25) +
        tool_score * weights.get("exact_match_weight", 0.30) +
        (tool_score if result.tool_match_type == "acceptable_match" else 0.0) * weights.get("acceptable_match_weight", 0.20)
    )
    
    # Track latency
    result.latency_ms = (time.time() - start_time) * 1000
    
    return result


def run_evaluation(
    suite: EvalSuite,
    tool_index: list[ToolIndexEntry],
    agent_definitions: list[AgentDefinition] | None = None,
) -> EvalReport:
    """
    Run full evaluation suite and aggregate results.
    """
    from datetime import datetime
    
    report = EvalReport(
        suite_name=suite.name,
        total_tests=0,
        timestamp=datetime.utcnow().isoformat(),
    )
    
    all_results: list[SingleResult] = []
    
    # Evaluate each category
    for category in suite.categories:
        cat_result = CategoryResult(
            category_id=category.category_id,
            category_name=category.category_name,
            total_tests=len(category.test_cases),
        )
        
        category_results: list[SingleResult] = []
        for tc in category.test_cases:
            result = evaluate_single(tc, tool_index, suite.config, agent_definitions)
            category_results.append(result)
            all_results.append(result)
        
        # Aggregate category metrics
        if category_results:
            cat_result.route_accuracy = sum(
                1 for r in category_results if r.route_correct
            ) / len(category_results)
            
            cat_result.sub_route_accuracy = sum(
                1 for r in category_results if r.sub_route_correct
            ) / len(category_results)
            
            cat_result.agent_exact_rate = sum(
                1 for r in category_results if r.agent_correct
            ) / len(category_results)
            
            cat_result.agent_avg_overlap = sum(
                r.agent_overlap for r in category_results
            ) / len(category_results)
            
            cat_result.tool_exact_rate = sum(
                1 for r in category_results if r.tool_match_type == "exact_match"
            ) / len(category_results)
            
            cat_result.tool_acceptable_rate = sum(
                1 for r in category_results if r.tool_match_type in ("exact_match", "acceptable_match")
            ) / len(category_results)
            
            cat_result.tool_partial_rate = sum(
                1 for r in category_results if r.tool_match_type == "partial_match"
            ) / len(category_results)
            
            cat_result.avg_composite_score = sum(
                r.composite_score for r in category_results
            ) / len(category_results)
            
            cat_result.avg_latency_ms = sum(
                r.latency_ms for r in category_results
            ) / len(category_results)
            
            # Track failed tests
            cat_result.failed_tests = [
                r for r in category_results if r.tool_match_type == "no_match"
            ]
        
        report.category_results.append(cat_result)
    
    # Aggregate overall metrics
    report.total_tests = len(all_results)
    if all_results:
        report.overall_route_accuracy = sum(
            1 for r in all_results if r.route_correct
        ) / len(all_results)
        
        report.overall_sub_route_accuracy = sum(
            1 for r in all_results if r.sub_route_correct
        ) / len(all_results)
        
        report.overall_agent_exact_rate = sum(
            1 for r in all_results if r.agent_correct
        ) / len(all_results)
        
        report.overall_agent_avg_overlap = sum(
            r.agent_overlap for r in all_results
        ) / len(all_results)
        
        report.overall_tool_exact_rate = sum(
            1 for r in all_results if r.tool_match_type == "exact_match"
        ) / len(all_results)
        
        report.overall_tool_acceptable_rate = sum(
            1 for r in all_results if r.tool_match_type in ("exact_match", "acceptable_match")
        ) / len(all_results)
        
        report.overall_tool_partial_rate = sum(
            1 for r in all_results if r.tool_match_type == "partial_match"
        ) / len(all_results)
        
        report.overall_avg_composite_score = sum(
            r.composite_score for r in all_results
        ) / len(all_results)
        
        report.overall_avg_latency_ms = sum(
            r.latency_ms for r in all_results
        ) / len(all_results)
    
    # Build route confusion matrix
    route_confusion: dict[str, dict[str, int]] = {}
    for result in all_results:
        # We need the test case to get expected_route
        # Find it from categories
        for category in suite.categories:
            for tc in category.test_cases:
                if tc.id == result.test_case_id:
                    if tc.expected_route and result.predicted_route:
                        expected = tc.expected_route
                        predicted = result.predicted_route
                        if expected not in route_confusion:
                            route_confusion[expected] = {}
                        route_confusion[expected][predicted] = route_confusion[expected].get(predicted, 0) + 1
                    break
    report.route_confusion_matrix = route_confusion
    
    # Failure pattern detection (by tags)
    failure_patterns: dict[str, int] = {}
    for category in suite.categories:
        for tc in category.test_cases:
            for result in all_results:
                if result.test_case_id == tc.id and result.tool_match_type == "no_match":
                    for tag in tc.tags:
                        failure_patterns[tag] = failure_patterns.get(tag, 0) + 1
    report.failure_patterns = failure_patterns
    
    # By-difficulty breakdown
    by_diff: dict[str, dict[str, float]] = {}
    for difficulty in ["easy", "medium", "hard"]:
        diff_results = []
        for category in suite.categories:
            for tc in category.test_cases:
                if tc.difficulty == difficulty:
                    for result in all_results:
                        if result.test_case_id == tc.id:
                            diff_results.append(result)
        
        if diff_results:
            by_diff[difficulty] = {
                "total": len(diff_results),
                "tool_exact_rate": sum(1 for r in diff_results if r.tool_match_type == "exact_match") / len(diff_results),
                "tool_acceptable_rate": sum(1 for r in diff_results if r.tool_match_type in ("exact_match", "acceptable_match")) / len(diff_results),
                "avg_composite_score": sum(r.composite_score for r in diff_results) / len(diff_results),
            }
    report.by_difficulty = by_diff
    
    # Generate recommendations
    recommendations = []
    if report.overall_tool_exact_rate < 0.7:
        recommendations.append(
            f"Tool exact match rate is {report.overall_tool_exact_rate:.1%}. Consider increasing TOOL_EMBEDDING_WEIGHT or improving keyword/example metadata."
        )
    
    if report.overall_route_accuracy < 0.8:
        recommendations.append(
            f"Route accuracy is {report.overall_route_accuracy:.1%}. Consider improving regex patterns in dispatcher.py."
        )
    
    if report.overall_agent_exact_rate < 0.6:
        recommendations.append(
            f"Agent exact match rate is {report.overall_agent_exact_rate:.1%}. Consider improving agent descriptions or keywords."
        )
    
    if failure_patterns:
        top_failures = sorted(failure_patterns.items(), key=lambda x: x[1], reverse=True)[:3]
        recommendations.append(
            f"Most common failure tags: {', '.join(f'{tag} ({count})' for tag, count in top_failures)}"
        )
    
    report.recommendations = recommendations
    
    return report


def report_to_dict(report: EvalReport) -> dict[str, Any]:
    """Convert EvalReport to JSON-serializable dict."""
    def serialize_dataclass(obj: Any) -> Any:
        if hasattr(obj, "__dataclass_fields__"):
            return {k: serialize_dataclass(v) for k, v in asdict(obj).items()}
        elif isinstance(obj, list):
            return [serialize_dataclass(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: serialize_dataclass(v) for k, v in obj.items()}
        elif isinstance(obj, tuple):
            return list(obj)  # Convert tuples to lists for JSON
        else:
            return obj
    
    return serialize_dataclass(report)
