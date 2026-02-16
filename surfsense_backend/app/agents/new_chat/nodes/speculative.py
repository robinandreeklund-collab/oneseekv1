from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable
from langchain_core.runnables import RunnableConfig


def _safe_candidates(values: Any, *, max_candidates: int) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("tool_id") or "").strip()
        if not tool_id or tool_id in seen:
            continue
        seen.add(tool_id)
        cleaned.append({"tool_id": tool_id, "probability": item.get("probability")})
        if len(cleaned) >= max(1, int(max_candidates)):
            break
    return cleaned


def _is_successful_speculative_result(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    return status in {"ok", "success", "partial", "cached"}


def build_speculative_node(
    *,
    run_speculative_candidate_fn: Callable[..., Awaitable[dict[str, Any]]],
    max_candidates: int = 3,
):
    async def speculative_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        candidates = _safe_candidates(
            state.get("speculative_candidates"),
            max_candidates=max_candidates,
        )
        if not candidates:
            return {
                "speculative_results": {},
                "pending_hitl_payload": {
                    "speculative_candidates": [],
                    "speculative_executed": 0,
                },
            }

        async def _run_one(candidate: dict[str, Any]) -> tuple[str, dict[str, Any]]:
            tool_id = str(candidate.get("tool_id") or "").strip()
            if not tool_id:
                return "", {"status": "failed", "reason": "missing_tool_id"}
            try:
                result = await run_speculative_candidate_fn(
                    tool_id=tool_id,
                    candidate=candidate,
                    state=state,
                )
                if not isinstance(result, dict):
                    result = {
                        "status": "failed",
                        "reason": "invalid_result_contract",
                    }
                return tool_id, result
            except asyncio.TimeoutError:
                return tool_id, {"status": "failed", "reason": "timeout"}
            except Exception as exc:  # pragma: no cover - defensive guard
                return tool_id, {"status": "failed", "reason": str(exc)}

        results = await asyncio.gather(*[_run_one(item) for item in candidates])
        speculative_results: dict[str, dict[str, Any]] = {}
        successful = 0
        for tool_id, payload in results:
            if not tool_id:
                continue
            speculative_results[tool_id] = payload
            if _is_successful_speculative_result(payload):
                successful += 1

        return {
            "speculative_results": speculative_results,
            "pending_hitl_payload": {
                "speculative_candidates": candidates,
                "speculative_executed": len(results),
                "speculative_successes": successful,
            },
        }

    return speculative_node


def build_speculative_merge_node():
    async def speculative_merge_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        resolved = state.get("resolved_tools_by_agent")
        speculative_results = state.get("speculative_results")
        if not isinstance(resolved, dict) or not isinstance(speculative_results, dict):
            return {}

        planned_tools: set[str] = set()
        for tool_ids in resolved.values():
            if not isinstance(tool_ids, list):
                continue
            for tool_id in tool_ids:
                normalized = str(tool_id or "").strip()
                if normalized:
                    planned_tools.add(normalized)

        reused_tools: list[str] = []
        remaining_tools: list[str] = []
        for tool_id in sorted(planned_tools):
            payload = speculative_results.get(tool_id)
            if isinstance(payload, dict) and _is_successful_speculative_result(payload):
                reused_tools.append(tool_id)
            else:
                remaining_tools.append(tool_id)

        discarded_tools = [
            tool_id
            for tool_id in speculative_results.keys()
            if str(tool_id or "").strip() and str(tool_id or "").strip() not in planned_tools
        ]
        output: dict[str, Any] = {
            "pending_hitl_payload": {
                "speculative_reused_tools": reused_tools,
                "speculative_remaining_tools": remaining_tools,
                "speculative_discarded_tools": discarded_tools,
            }
        }
        if planned_tools and not remaining_tools:
            output["execution_strategy"] = "inline"
        return output

    return speculative_merge_node
