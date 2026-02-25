from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agents.new_chat.routing import ExecutionMode

_INTENT_EMBED_CACHE: dict[str, list[float]] = {}
_INTENT_TOKEN_RE = re.compile(r"[a-z0-9åäö]{2,}", re.IGNORECASE)
logger = logging.getLogger(__name__)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _tokenize(value: str) -> list[str]:
    return [token.lower() for token in _INTENT_TOKEN_RE.findall(str(value or ""))]


def _normalize_vector(vector: Any) -> list[float] | None:
    if vector is None:
        return None
    try:
        return [float(value) for value in vector]
    except Exception:
        return None


def _cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    norm_left = 0.0
    norm_right = 0.0
    for a, b in zip(left, right):
        dot += a * b
        norm_left += a * a
        norm_right += b * b
    if norm_left <= 0.0 or norm_right <= 0.0:
        return 0.0
    return dot / ((norm_left**0.5) * (norm_right**0.5))


def _embed_text_cached(text: str) -> list[float] | None:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return None
    cache_key = hashlib.sha1(normalized_text.encode("utf-8")).hexdigest()
    if cache_key in _INTENT_EMBED_CACHE:
        return _INTENT_EMBED_CACHE.get(cache_key)
    try:
        from app.config import config

        embedded = _normalize_vector(config.embedding_model_instance.embed(normalized_text))
    except Exception:
        embedded = None
    if embedded is not None:
        _INTENT_EMBED_CACHE[cache_key] = embedded
    return embedded


def _rank_intent_candidates(
    *,
    query: str,
    candidates: list[dict[str, Any]],
    lexical_weight: float,
    embedding_weight: float,
) -> list[dict[str, Any]]:
    query_norm = _normalize_text(query)
    query_tokens = set(_tokenize(query_norm))
    query_embedding = _embed_text_cached(query)
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        intent_id = str(candidate.get("intent_id") or "").strip()
        route = str(candidate.get("route") or "").strip()
        description = str(candidate.get("description") or "").strip()
        keywords = [
            str(keyword).strip()
            for keyword in list(candidate.get("keywords") or [])
            if str(keyword).strip()
        ]
        candidate_text = " ".join(
            part for part in [intent_id, route, description, *keywords] if part
        )
        lexical_hits = 0
        if _normalize_text(intent_id) in query_norm:
            lexical_hits += 2
        if _normalize_text(route) in query_norm:
            lexical_hits += 2
        for keyword in keywords:
            if _normalize_text(keyword) in query_norm:
                lexical_hits += 1
        lexical_hits += len(query_tokens.intersection(set(_tokenize(candidate_text))))
        lexical_score = float(lexical_hits) * float(lexical_weight)
        candidate_embedding = _embed_text_cached(candidate_text)
        semantic_raw = _cosine_similarity(query_embedding, candidate_embedding)
        semantic_score = semantic_raw * float(embedding_weight)
        ranked.append(
            {
                "intent_id": intent_id,
                "route": route,
                "score": float(lexical_score + semantic_score),
                "lexical_score": float(lexical_score),
                "semantic_score_raw": float(semantic_raw),
                "semantic_score": float(semantic_score),
            }
        )
    ranked.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return ranked


_VALID_EXECUTION_MODES = {m.value for m in ExecutionMode}


def build_intent_resolver_node(
    *,
    llm: Any,
    route_to_intent_id: dict[str, str],
    intent_resolver_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    parse_hitl_confirmation_fn: Callable[[str], str | None],
    normalize_route_hint_fn: Callable[[Any], str],
    intent_from_route_fn: Callable[[str | None], dict[str, Any]],
    append_datetime_context_fn: Callable[[str], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
    coerce_confidence_fn: Callable[[Any, float], float],
    classify_execution_mode_fn: Callable[[dict[str, Any], str], str],
    build_speculative_candidates_fn: Callable[[dict[str, Any], str], list[dict[str, Any]]],
    build_trivial_response_fn: Callable[[str], str | None],
    route_default_agent_fn: Callable[..., str],
    coerce_resolved_intent_fn: Callable[
        [dict[str, Any], str, str | None], dict[str, Any]
    ]
    | None = None,
    live_routing_config: dict[str, Any] | None = None,
):
    def _latest_human_turn_id(messages: list[Any] | None) -> str:
        human_count = 0
        latest_human: Any | None = None
        for message in messages or []:
            if isinstance(message, HumanMessage):
                human_count += 1
                latest_human = message
            elif isinstance(message, dict) and str(message.get("type") or "").strip().lower() in {
                "human",
                "user",
            }:
                human_count += 1
                latest_human = message
        if human_count <= 0 or latest_human is None:
            return ""
        if isinstance(latest_human, dict):
            message_id = str(latest_human.get("id") or "").strip()
            content = latest_human.get("content")
        else:
            message_id = str(getattr(latest_human, "id", "") or "").strip()
            content = getattr(latest_human, "content", "")
        if isinstance(content, list):
            content_text = "".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict)
            ).strip()
        else:
            content_text = str(content or "").strip()
        if message_id:
            signature = message_id
        elif content_text:
            signature = hashlib.sha1(
                content_text.encode("utf-8", errors="ignore")
            ).hexdigest()[:16]
        else:
            signature = "empty"
        return f"implicit_turn:{human_count}:{signature}"

    async def resolve_intent_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        state_messages = list(state.get("messages") or [])
        incoming_turn_id = str(state.get("turn_id") or "").strip()
        if not incoming_turn_id:
            incoming_turn_id = _latest_human_turn_id(state_messages)
        active_turn_id = str(state.get("active_turn_id") or "").strip()
        new_user_turn = bool(incoming_turn_id and incoming_turn_id != active_turn_id)
        latest_user_query = latest_user_query_fn(state_messages)

        if new_user_turn and bool(state.get("awaiting_confirmation")):
            pending_stage = str(state.get("pending_hitl_stage") or "").strip().lower()
            decision = parse_hitl_confirmation_fn(latest_user_query)
            if decision is None:
                return {
                    "messages": [
                        AIMessage(
                            content="Svara med ja eller nej sa jag vet hur jag ska fortsatta."
                        )
                    ],
                    "awaiting_confirmation": True,
                    "pending_hitl_stage": pending_stage or None,
                    "active_turn_id": incoming_turn_id or active_turn_id or None,
                    "orchestration_phase": "awaiting_confirmation",
                }
            updates: dict[str, Any] = {
                "awaiting_confirmation": False,
                "pending_hitl_stage": None,
                "pending_hitl_payload": None,
                "user_feedback": {
                    "stage": pending_stage or None,
                    "decision": decision,
                    "message": latest_user_query,
                },
            }
            if incoming_turn_id:
                updates["active_turn_id"] = incoming_turn_id
            if decision == "approve":
                if pending_stage == "planner":
                    updates["orchestration_phase"] = "resolve_tools"
                elif pending_stage == "execution":
                    updates["orchestration_phase"] = "execute"
                elif pending_stage == "synthesis":
                    updates["orchestration_phase"] = "finalize"
                return updates
            # reject
            updates["replan_count"] = int(state.get("replan_count") or 0) + 1
            if pending_stage == "synthesis":
                updates["final_response"] = None
                updates["final_agent_response"] = None
            updates["critic_decision"] = "needs_more"
            updates["orchestration_phase"] = "plan"
            return updates

        if not new_user_turn and state.get("resolved_intent"):
            return {}

        route_hint = normalize_route_hint_fn(state.get("route_hint"))
        candidates: list[dict[str, Any]] = []
        for route_name, intent_id in route_to_intent_id.items():
            candidates.append({"intent_id": intent_id, "route": route_name})
        if route_hint:
            candidates.sort(key=lambda item: 0 if item.get("route") == route_hint else 1)
        live_cfg = dict(live_routing_config or {})
        live_enabled = bool(live_cfg.get("enabled", False))
        phase_index = int(live_cfg.get("phase_index") or 0)
        intent_top_k = max(2, min(int(live_cfg.get("intent_top_k") or 3), 8))
        use_intent_shortlist = bool(live_enabled and phase_index >= 4)
        intent_ranked = _rank_intent_candidates(
            query=latest_user_query,
            candidates=candidates,
            lexical_weight=float(live_cfg.get("intent_lexical_weight") or 1.0),
            embedding_weight=float(live_cfg.get("intent_embedding_weight") or 1.0),
        )
        candidate_by_intent: dict[str, dict[str, Any]] = {
            str(item.get("intent_id") or "").strip(): item
            for item in candidates
            if str(item.get("intent_id") or "").strip()
        }
        intent_shortlist: list[dict[str, Any]] = []
        for item in intent_ranked[:intent_top_k]:
            intent_id = str(item.get("intent_id") or "").strip()
            if intent_id in candidate_by_intent:
                intent_shortlist.append(dict(candidate_by_intent[intent_id]))
        llm_candidates = intent_shortlist if use_intent_shortlist else candidates
        candidate_ids = {
            str(item.get("intent_id") or "").strip()
            for item in llm_candidates
            if str(item.get("intent_id") or "").strip()
        }
        top1_row = intent_ranked[0] if intent_ranked else None
        top2_row = intent_ranked[1] if len(intent_ranked) > 1 else None
        intent_margin = (
            float(top1_row.get("score") or 0.0) - float(top2_row.get("score") or 0.0)
            if top1_row and top2_row
            else None
        )

        resolved = intent_from_route_fn(route_hint)
        should_resolve_with_llm = bool(latest_user_query)
        if route_hint and route_hint in route_to_intent_id:
            should_resolve_with_llm = False

        # ── LLM intent resolution (now also produces execution_mode + domain_hints) ──
        llm_execution_mode: str | None = None
        llm_domain_hints: list[str] = []
        if latest_user_query and should_resolve_with_llm:
            prompt = append_datetime_context_fn(intent_resolver_prompt_template)
            resolver_input = json.dumps(
                {
                    "query": latest_user_query,
                    "route_hint": route_hint,
                    "intent_candidates": llm_candidates,
                },
                ensure_ascii=True,
            )
            try:
                message = await llm.ainvoke(
                    [
                        SystemMessage(content=prompt),
                        HumanMessage(content=resolver_input),
                    ],
                    max_tokens=200,
                )
                parsed = extract_first_json_object_fn(
                    str(getattr(message, "content", "") or "")
                )
                selected_intent = str(parsed.get("intent_id") or "").strip()
                selected_route = normalize_route_hint_fn(parsed.get("route"))
                # Extract new fields: execution_mode and domain_hints
                raw_exec_mode = str(parsed.get("execution_mode") or "").strip().lower()
                if raw_exec_mode in _VALID_EXECUTION_MODES:
                    llm_execution_mode = raw_exec_mode
                raw_domain_hints = parsed.get("domain_hints")
                if isinstance(raw_domain_hints, list):
                    llm_domain_hints = [
                        str(h).strip().lower()
                        for h in raw_domain_hints
                        if str(h).strip()
                    ]
                if selected_intent and selected_intent in candidate_ids:
                    resolved = {
                        "intent_id": selected_intent,
                        "route": selected_route
                        or next(
                            (
                                str(item.get("route") or "")
                                for item in llm_candidates
                                if str(item.get("intent_id") or "").strip()
                                == selected_intent
                            ),
                            route_hint or "knowledge",
                        ),
                        "reason": str(parsed.get("reason") or "").strip()
                        or "LLM intent_resolver valde intent.",
                        "confidence": coerce_confidence_fn(
                            parsed.get("confidence"), 0.5
                        ),
                    }
                    # Attach execution_mode and domain_hints to resolved intent
                    if llm_execution_mode:
                        resolved["execution_mode"] = llm_execution_mode
                    if llm_domain_hints:
                        resolved["domain_hints"] = llm_domain_hints
                    # Attach sub_intents for multi_source
                    raw_sub_intents = parsed.get("sub_intents")
                    if isinstance(raw_sub_intents, list):
                        resolved["sub_intents"] = [
                            str(s).strip() for s in raw_sub_intents if str(s).strip()
                        ]
            except Exception:
                pass

        if coerce_resolved_intent_fn is not None:
            try:
                coerced_resolved = coerce_resolved_intent_fn(
                    resolved if isinstance(resolved, dict) else {},
                    latest_user_query,
                    route_hint or None,
                )
                if isinstance(coerced_resolved, dict) and coerced_resolved:
                    resolved = coerced_resolved
            except Exception:
                pass

        # ── Classify execution mode (Nivå 1 decision) ──
        execution_mode = str(
            classify_execution_mode_fn(resolved, latest_user_query)
        ).strip().lower()
        if execution_mode not in _VALID_EXECUTION_MODES:
            execution_mode = ExecutionMode.TOOL_REQUIRED.value

        # Derive backward-compat graph_complexity from execution_mode
        from app.agents.new_chat.hybrid_state import execution_mode_to_graph_complexity
        graph_complexity = execution_mode_to_graph_complexity(execution_mode)

        # Extract domain_hints (prefer LLM output, fallback to resolved intent)
        domain_hints: list[str] = llm_domain_hints
        if not domain_hints:
            resolved_hints = (resolved or {}).get("domain_hints")
            if isinstance(resolved_hints, list):
                domain_hints = [str(h).strip().lower() for h in resolved_hints if str(h).strip()]

        speculative_candidates = build_speculative_candidates_fn(
            resolved,
            latest_user_query,
        )
        if not isinstance(speculative_candidates, list):
            speculative_candidates = []
        speculative_candidates = [
            item for item in speculative_candidates[:3] if isinstance(item, dict)
        ]

        # Pre-select agents for tool_optional and tool_required (simple cases)
        selected_agents_for_simple: list[dict[str, Any]] = []
        if execution_mode in {
            ExecutionMode.TOOL_REQUIRED.value,
            ExecutionMode.TOOL_OPTIONAL.value,
        } and graph_complexity == "simple":
            try:
                default_agent_name = route_default_agent_fn(
                    resolved.get("route"),
                    latest_user_query,
                )
            except TypeError:
                default_agent_name = route_default_agent_fn(resolved.get("route"))
            if default_agent_name:
                selected_agents_for_simple = [
                    {
                        "name": str(default_agent_name),
                        "description": "Preselected from hybrid intent complexity.",
                    }
                ]

        trivial_response = (
            build_trivial_response_fn(latest_user_query)
            if execution_mode == ExecutionMode.TOOL_FORBIDDEN.value
            else None
        )

        sub_intents: list[str] = []
        raw_sub_intents = resolved.get("sub_intents") if isinstance(resolved, dict) else None
        if isinstance(raw_sub_intents, list):
            sub_intents = [
                str(item).strip()
                for item in raw_sub_intents
                if str(item).strip()
            ]

        updates: dict[str, Any] = {
            "resolved_intent": resolved,
            "route_hint": normalize_route_hint_fn(resolved.get("route")),
            "sub_intents": sub_intents,
            "execution_mode": execution_mode,
            "domain_hints": domain_hints,
            "graph_complexity": graph_complexity,
            "speculative_candidates": speculative_candidates,
            "speculative_results": {},
            "execution_strategy": None,
            "worker_results": [],
            "synthesis_drafts": [],
            "retrieval_feedback": {},
            "targeted_missing_info": [],
            "orchestration_phase": "select_agent",
            "live_routing_trace": {
                **dict(state.get("live_routing_trace") or {}),
                "intent": {
                    "mode": "llm_shortlist" if use_intent_shortlist else "llm_full",
                    "phase": str(live_cfg.get("phase") or "shadow"),
                    "top1": (top1_row or {}).get("intent_id"),
                    "top2": (top2_row or {}).get("intent_id"),
                    "margin": intent_margin,
                    "shortlist_size": len(llm_candidates),
                    "selected": str((resolved or {}).get("intent_id") or ""),
                    "execution_mode": execution_mode,
                    "domain_hints": domain_hints,
                },
            },
        }
        if new_user_turn:
            updates["active_plan"] = []
            updates["plan_step_index"] = 0
            updates["plan_complete"] = False
            updates["step_results"] = []
            updates["recent_agent_calls"] = []
            updates["compare_outputs"] = []
            updates["selected_agents"] = []
            updates["resolved_tools_by_agent"] = {}
            updates["final_agent_response"] = None
            updates["final_response"] = None
            updates["critic_decision"] = None
            updates["awaiting_confirmation"] = False
            updates["pending_hitl_stage"] = None
            updates["pending_hitl_payload"] = None
            updates["user_feedback"] = None
            updates["replan_count"] = 0
            updates["agent_hops"] = 0
            updates["no_progress_runs"] = 0
            updates["guard_parallel_preview"] = []
            updates["subagent_handoffs"] = []
            updates["execution_mode"] = execution_mode
            updates["domain_hints"] = domain_hints
            updates["graph_complexity"] = graph_complexity
            updates["speculative_candidates"] = speculative_candidates
            updates["speculative_results"] = {}
            updates["execution_strategy"] = None
            updates["worker_results"] = []
            updates["synthesis_drafts"] = []
            updates["retrieval_feedback"] = {}
            updates["live_routing_trace"] = {
                "intent": dict(
                    (updates.get("live_routing_trace") or {}).get("intent") or {}
                )
            }
            updates["targeted_missing_info"] = []
            if incoming_turn_id:
                updates["active_turn_id"] = incoming_turn_id
        elif incoming_turn_id and not active_turn_id:
            updates["active_turn_id"] = incoming_turn_id

        if selected_agents_for_simple:
            updates["selected_agents"] = selected_agents_for_simple

        if trivial_response:
            updates["final_agent_response"] = trivial_response
            updates["final_response"] = trivial_response
            updates["final_agent_name"] = "supervisor"
            updates["orchestration_phase"] = "finalize"
        if live_enabled:
            logger.info(
                "live-routing intent-selection phase=%s mode=%s top1=%s top2=%s margin=%s selected=%s exec_mode=%s",
                live_cfg.get("phase"),
                "llm_shortlist" if use_intent_shortlist else "llm_full",
                (top1_row or {}).get("intent_id"),
                (top2_row or {}).get("intent_id"),
                intent_margin,
                str((resolved or {}).get("intent_id") or ""),
                execution_mode,
            )
        return updates

    return resolve_intent_node
