from __future__ import annotations

import inspect
import logging
from typing import Any, Awaitable, Callable
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


def _normalize_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"success", "partial", "blocked", "error"}:
        return status
    return "partial"


def _normalize_missing_info(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    output: list[str] = []
    for raw in values:
        item = str(raw or "").strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        output.append(item)
    return output


def _collect_recent_contracts(
    *,
    state: dict[str, Any],
    contract_from_payload_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    step_results = state.get("step_results") or []
    for item in reversed(step_results):
        if not isinstance(item, dict):
            continue
        contract = contract_from_payload_fn(item)
        if not isinstance(contract, dict) or not contract:
            continue
        contracts.append(contract)
        if len(contracts) >= max(1, int(limit)):
            break
    return contracts


def _latest_successful_step_payload(
    *,
    state: dict[str, Any],
    contract_from_payload_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
) -> tuple[str, str] | None:
    step_results = state.get("step_results") or []
    for item in reversed(step_results):
        if not isinstance(item, dict):
            continue
        contract = contract_from_payload_fn(item)
        if not isinstance(contract, dict) or not contract:
            continue
        status = _normalize_status(contract.get("status"))
        if status != "success":
            continue
        response_text = str(item.get("response") or "").strip()
        if not response_text:
            continue
        agent_name = str(item.get("agent") or contract.get("agent") or "agent").strip()
        return response_text, agent_name or "agent"
    return None


def build_smart_critic_node(
    *,
    fallback_critic_node: Callable[..., Awaitable[dict[str, Any]]],
    contract_from_payload_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
    latest_user_query_fn: Callable[[list[Any] | None], str],
    max_replan_attempts: int,
    min_mechanical_confidence: float = 0.7,
    record_retrieval_feedback_fn: Callable[[str, str, bool], Any] | None = None,
):
    async def smart_critic_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        latest_user_query = latest_user_query_fn(state.get("messages") or [])
        final_response = str(
            state.get("final_agent_response") or state.get("final_response") or ""
        ).strip()
        replan_count = int(state.get("replan_count") or 0)
        total_steps = int(state.get("total_steps") or 0)
        critic_history = list(state.get("critic_history") or [])

        # --- P1 guard_finalized: respect orchestration_guard decision ---
        if state.get("guard_finalized") and final_response:
            logger.info(
                "smart_critic: guard_finalized=True, accepting (total_steps=%d)",
                total_steps,
            )
            return {
                "critic_decision": "ok",
                "final_response": final_response,
                "orchestration_phase": "finalize",
                "critic_history": critic_history + [
                    {"decision": "ok", "reason": "guard_finalized", "step": total_steps}
                ],
            }

        contracts = _collect_recent_contracts(
            state=state,
            contract_from_payload_fn=contract_from_payload_fn,
            limit=3,
        )

        async def _record_feedback(success: bool) -> None:
            if record_retrieval_feedback_fn is None:
                return
            for item in contracts:
                used_tools = item.get("used_tools")
                if not isinstance(used_tools, list):
                    continue
                for tool_id in used_tools:
                    normalized_tool = str(tool_id or "").strip()
                    if not normalized_tool:
                        continue
                    try:
                        maybe_awaitable = record_retrieval_feedback_fn(
                            normalized_tool,
                            latest_user_query,
                            bool(success),
                        )
                        if inspect.isawaitable(maybe_awaitable):
                            await maybe_awaitable
                    except Exception:
                        continue

        if not contracts:
            # Delegate to fallback (base critic_node) which has its own
            # guard_finalized / total_steps / critic_history handling.
            return await fallback_critic_node(
                state,
                config=config,
                store=store,
                **kwargs,
            )

        statuses = [_normalize_status(item.get("status")) for item in contracts]
        confidences: list[float] = []
        for item in contracts:
            try:
                confidence = float(item.get("confidence"))
            except (TypeError, ValueError):
                confidence = 0.0
            confidences.append(max(0.0, min(1.0, confidence)))
        avg_confidence = (sum(confidences) / len(confidences)) if confidences else 0.0

        missing_info: list[str] = []
        missing_seen: set[str] = set()
        for item in contracts:
            for field_name in _normalize_missing_info(item.get("missing_fields")):
                lowered = field_name.lower()
                if lowered in missing_seen:
                    continue
                missing_seen.add(lowered)
                missing_info.append(field_name)

        all_failed = all(status in {"error", "blocked"} for status in statuses)
        has_success = any(status == "success" for status in statuses)

        # --- P1 adaptive: lower confidence threshold based on total_steps ---
        adaptive_confidence = float(min_mechanical_confidence)
        if total_steps >= 8:
            adaptive_confidence = max(0.4, adaptive_confidence - 0.15)
        elif total_steps >= 5:
            adaptive_confidence = max(0.5, adaptive_confidence - 0.1)

        # Only replan when all agents failed AND there is no existing final
        # response to fall back on.
        if all_failed and not final_response and replan_count < max_replan_attempts:
            await _record_feedback(False)
            return {
                "critic_decision": "replan",
                "final_agent_response": None,
                "final_response": None,
                "targeted_missing_info": [],
                "replan_count": replan_count + 1,
                "orchestration_phase": "plan",
                "critic_history": critic_history + [
                    {"decision": "replan", "reason": "all_failed", "step": total_steps}
                ],
            }

        if missing_info and replan_count < max_replan_attempts:
            # P1 adaptive: skip needs_more if we've already retried recently.
            recent_needs_more = sum(
                1 for h in critic_history[-3:]
                if h.get("decision") == "needs_more"
            )
            if recent_needs_more >= 2:
                logger.info(
                    "smart_critic: %d recent needs_more, forcing ok despite missing info",
                    recent_needs_more,
                )
            else:
                await _record_feedback(False)
                return {
                    "critic_decision": "needs_more",
                    "final_agent_response": None,
                    "final_response": None,
                    "targeted_missing_info": missing_info[:6],
                    "replan_count": replan_count + 1,
                    "orchestration_phase": "resolve_tools",
                    "critic_history": critic_history + [
                        {"decision": "needs_more", "reason": "missing_info", "step": total_steps}
                    ],
                }

        # P1: use adaptive_confidence instead of fixed min_mechanical_confidence
        if has_success and avg_confidence >= adaptive_confidence:
            resolved_response = final_response
            resolved_agent_name = str(state.get("final_agent_name") or "").strip()
            if not resolved_response:
                successful_payload = _latest_successful_step_payload(
                    state=state,
                    contract_from_payload_fn=contract_from_payload_fn,
                )
                if successful_payload:
                    resolved_response, resolved_agent_name = successful_payload
            if resolved_response:
                await _record_feedback(True)
                updates: dict[str, Any] = {
                    "critic_decision": "ok",
                    "targeted_missing_info": [],
                    "orchestration_phase": "finalize",
                    "critic_history": critic_history + [
                        {"decision": "ok", "reason": "success_confident", "step": total_steps}
                    ],
                }
                if not final_response:
                    updates["final_response"] = resolved_response
                    updates["final_agent_response"] = resolved_response
                    updates["final_agent_name"] = resolved_agent_name or "agent"
                return updates
            if replan_count < max_replan_attempts:
                await _record_feedback(False)
                return {
                    "critic_decision": "needs_more",
                    "targeted_missing_info": [],
                    "replan_count": replan_count + 1,
                    "orchestration_phase": "resolve_tools",
                    "critic_history": critic_history + [
                        {"decision": "needs_more", "reason": "no_resolved_response", "step": total_steps}
                    ],
                }

        fallback_updates = await fallback_critic_node(
            state,
            config=config,
            store=store,
            **kwargs,
        )
        normalized = dict(fallback_updates or {})
        decision = str(normalized.get("critic_decision") or "").strip().lower()
        if decision == "needs_more":
            if missing_info and not normalized.get("targeted_missing_info"):
                normalized["targeted_missing_info"] = missing_info[:6]
            normalized["orchestration_phase"] = "resolve_tools"
            await _record_feedback(False)
        elif decision in {"ok", "pass", "finalize"}:
            await _record_feedback(True)
        elif decision == "replan":
            await _record_feedback(False)
        return normalized

    return smart_critic_node
