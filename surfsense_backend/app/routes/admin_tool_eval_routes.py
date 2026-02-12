"""
Admin Tool Evaluation Routes

FastAPI routes for the tool evaluation system. Provides endpoints to:
- Upload and run full evaluation suites
- Test single queries with detailed scoring
- Clear cached tool index

All endpoints require admin authentication.
"""

import logging
from typing import Any, Annotated
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session, User
from app.users import current_active_user
from app.routes.admin_tool_settings_routes import _require_admin

from app.services.tool_eval_service import (
    parse_eval_suite,
    run_evaluation,
    evaluate_single,
    report_to_dict,
    TestCase,
    EvalConfig,
    _build_stub_tool_registry,
    _extract_scoring_details,
)

from app.services.tool_eval_live import (
    evaluate_single_live,
    live_eval_result_to_dict,
    LiveEvalResult,
)

from app.agents.new_chat.bigtool_store import (
    build_tool_index,
    smart_retrieve_tools,
    get_tool_rerank_trace,
    ToolIndexEntry,
)

from app.agents.new_chat.supervisor_agent import (
    AgentDefinition,
)

from app.agents.new_chat.llm_config import create_chat_litellm_from_config
from app.config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Module-level cache for tool index
_CACHED_TOOL_INDEX: list[ToolIndexEntry] | None = None


async def _get_eval_tool_index() -> list[ToolIndexEntry]:
    """
    Get or build the tool index for evaluation.
    Lazily builds and caches the index from stub registry.
    """
    global _CACHED_TOOL_INDEX
    
    if _CACHED_TOOL_INDEX is not None:
        return _CACHED_TOOL_INDEX
    
    # Build stub registry (no real API dependencies)
    stub_registry = _build_stub_tool_registry()
    
    # Build tool index from stubs
    tool_index = build_tool_index(stub_registry)
    
    _CACHED_TOOL_INDEX = tool_index
    logger.info(f"Built tool index with {len(tool_index)} tools for evaluation")
    
    return tool_index


def _invalidate_tool_index_cache() -> None:
    """Clear the cached tool index."""
    global _CACHED_TOOL_INDEX
    _CACHED_TOOL_INDEX = None
    logger.info("Tool index cache invalidated")


# Request/Response models

class SingleQueryRequest(BaseModel):
    """Request to test a single query."""
    query: str = Field(..., description="The query to test")
    expected_tools: list[str] | None = Field(None, description="Expected tool IDs")
    limit: int = Field(2, ge=1, le=10, description="Number of tools to retrieve")
    primary_namespaces: list[list[str]] | None = Field(
        None,
        description="Primary namespaces to search",
    )
    fallback_namespaces: list[list[str]] | None = Field(
        None,
        description="Fallback namespaces",
    )


class ScoringDetailResponse(BaseModel):
    """Scoring detail for a tool."""
    tool_id: str
    name: str
    namespace: list[str]  # Convert tuple to list for JSON
    base_score: float
    semantic_score: float
    total_score: float
    keywords_matched: list[str]
    examples_matched: list[str]


class SingleQueryResponse(BaseModel):
    """Response from testing a single query."""
    query: str
    selected_tools: list[str]
    scoring_details: list[ScoringDetailResponse]
    rerank_trace: list[dict[str, Any]] | None
    match_type: str | None = None
    latency_ms: float


class EvalRunResponse(BaseModel):
    """Response from running a full evaluation suite."""
    suite_name: str
    total_tests: int
    timestamp: str
    
    # Overall metrics
    overall_route_accuracy: float
    overall_sub_route_accuracy: float
    overall_agent_exact_rate: float
    overall_agent_avg_overlap: float
    overall_tool_exact_rate: float
    overall_tool_acceptable_rate: float
    overall_tool_partial_rate: float
    overall_avg_composite_score: float
    overall_avg_latency_ms: float
    
    # Detailed results
    category_results: list[dict[str, Any]]
    by_difficulty: dict[str, dict[str, float]]
    route_confusion_matrix: dict[str, dict[str, int]]
    failure_patterns: dict[str, int]
    recommendations: list[str]


class InvalidateCacheResponse(BaseModel):
    """Response from cache invalidation."""
    success: bool
    message: str


# Endpoints

@router.post(
    "/tool-eval/single",
    response_model=SingleQueryResponse,
)
async def test_single_query(
    request: SingleQueryRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> SingleQueryResponse:
    """
    Test a single query through the tool retrieval pipeline.
    Returns selected tools with detailed scoring and reranking information.
    """
    await _require_admin(session, user)
    
    try:
        import time
        start_time = time.time()
        
        # Get tool index
        tool_index = await _get_eval_tool_index()
        
        # Prepare namespaces
        primary_namespaces = request.primary_namespaces or [["tools"]]
        primary_ns_tuples = [tuple(ns) for ns in primary_namespaces]
        
        fallback_namespaces = request.fallback_namespaces or []
        fallback_ns_tuples = [tuple(ns) for ns in fallback_namespaces]
        
        # Run tool retrieval
        trace_key = f"single_query_{user.id}"
        selected_tools = smart_retrieve_tools(
            request.query,
            tool_index=tool_index,
            primary_namespaces=primary_ns_tuples,
            fallback_namespaces=fallback_ns_tuples,
            limit=request.limit,
            trace_key=trace_key,
        )
        
        # Get rerank trace
        rerank_trace = get_tool_rerank_trace(trace_key, query=request.query)
        
        # Get detailed scoring
        from app.services.tool_eval_service import _extract_scoring_details
        scoring_details_raw = _extract_scoring_details(
            request.query,
            tool_index,
            selected_tools,
        )
        
        # Convert to response models
        scoring_details = [
            ScoringDetailResponse(
                tool_id=detail.tool_id,
                name=detail.name,
                namespace=list(detail.namespace),
                base_score=detail.base_score,
                semantic_score=detail.semantic_score,
                total_score=detail.total_score,
                keywords_matched=detail.keywords_matched,
                examples_matched=detail.examples_matched,
            )
            for detail in scoring_details_raw
        ]
        
        # Calculate match type if expected tools provided
        match_type = None
        if request.expected_tools:
            selected_set = set(selected_tools)
            expected_set = set(request.expected_tools)
            
            if selected_set == expected_set:
                match_type = "exact_match"
            elif selected_set & expected_set:
                match_type = "partial_match"
            else:
                match_type = "no_match"
        
        latency_ms = (time.time() - start_time) * 1000
        
        return SingleQueryResponse(
            query=request.query,
            selected_tools=selected_tools,
            scoring_details=scoring_details,
            rerank_trace=rerank_trace,
            match_type=match_type,
            latency_ms=latency_ms,
        )
    
    except Exception as e:
        logger.error(f"Error testing single query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/tool-eval/run",
    response_model=EvalRunResponse,
)
async def run_eval_suite(
    file: Annotated[UploadFile, File(description="JSON test suite file")],
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> EvalRunResponse:
    """
    Upload and run a full evaluation test suite.
    Returns comprehensive evaluation report with metrics, failures, and recommendations.
    """
    await _require_admin(session, user)
    
    try:
        # Read and parse uploaded file
        content = await file.read()
        import json
        suite_data = json.loads(content.decode("utf-8"))
        
        # Parse into EvalSuite
        suite = parse_eval_suite(suite_data)
        
        # Get tool index
        tool_index = await _get_eval_tool_index()
        
        # Get agent definitions (not available at module level, so agent evaluation is skipped)
        # Agent definitions are created dynamically in supervisor graph creation
        agent_definitions = None
        logger.info("Agent evaluation will be skipped (agent_definitions not available at module level)")
        
        # Run evaluation
        report = run_evaluation(suite, tool_index, agent_definitions)
        
        # Convert to dict for JSON serialization
        report_dict = report_to_dict(report)
        
        return EvalRunResponse(**report_dict)
    
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    except Exception as e:
        logger.error(f"Error running evaluation suite: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/tool-eval/invalidate-cache",
    response_model=InvalidateCacheResponse,
)
async def invalidate_cache(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> InvalidateCacheResponse:
    """
    Clear the cached tool index.
    Useful after editing tool metadata in /admin/tools.
    """
    await _require_admin(session, user)
    
    try:
        _invalidate_tool_index_cache()
        return InvalidateCacheResponse(
            success=True,
            message="Tool index cache cleared successfully",
        )
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Live evaluation models
class LiveQueryRequest(BaseModel):
    """Request for live pipeline evaluation of a single query."""
    query: str = Field(..., description="User query to evaluate")
    expected_tools: list[str] | None = Field(None, description="Expected tool IDs for comparison")
    expected_agents: list[str] | None = Field(None, description="Expected agent names for comparison")


class LiveQueryResponse(BaseModel):
    """Response from live pipeline evaluation."""
    query: str
    trace: list[dict[str, Any]]
    final_response: str
    total_steps: int
    total_time_ms: float
    agents_used: list[str]
    tools_used: list[str]
    expected_tools: list[str] | None = None
    matched_tools: list[str]
    match_type: str | None = None
    agent_selection_correct: bool | None = None
    tool_selection_correct: bool | None = None
    reasoning_quality: str | None = None


@router.post(
    "/tool-eval/single-live",
    response_model=LiveQueryResponse,
)
async def test_single_query_live(
    request: LiveQueryRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> LiveQueryResponse:
    """
    Run a single query through the FULL supervisor pipeline with stub tools.
    
    This provides complete trace of:
    - Model reasoning and planning at each step
    - Agent selection with actual scoring  
    - Tool retrieval with actual scoring
    - Execution flow with all intermediate steps
    
    Unlike /tool-eval/single (isolated testing), this runs through the real
    production pipeline to see how everything works together.
    
    NO REAL API CALLS ARE MADE - all external tools use stub implementations.
    """
    await _require_admin(session, user)
    
    try:
        # Get LLM configuration - use first global config (same as public chat)
        llm_config = None
        if config.GLOBAL_LLM_CONFIGS:
            for cfg in config.GLOBAL_LLM_CONFIGS:
                if isinstance(cfg, dict) and cfg.get("id") is not None:
                    llm_config = cfg
                    break
        
        if not llm_config:
            raise HTTPException(
                status_code=503,
                detail="LLM configuration not available for evaluation"
            )
        
        # Create LLM instance
        llm = create_chat_litellm_from_config(llm_config)
        if not llm:
            raise HTTPException(
                status_code=503,
                detail="Failed to create LLM instance for evaluation"
            )
        
        # Run live evaluation
        result = await evaluate_single_live(
            query=request.query,
            llm=llm,
            db=session,
            user_id=str(user.id),
            expected_tools=request.expected_tools,
            expected_agents=request.expected_agents,
        )
        
        # Convert to dict and return
        result_dict = live_eval_result_to_dict(result)
        
        return LiveQueryResponse(**result_dict)
    
    except Exception as e:
        logger.error(f"Error in live query evaluation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
