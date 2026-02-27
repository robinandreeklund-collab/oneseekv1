"""P4.1: Convergence node — merges parallel subagent mini-graph results.

Takes ``subagent_summaries`` produced by the subagent_spawner and
creates a unified artifact with source attribution, overlap detection,
and conflict flagging.  The merged result is passed to the critic for
final quality evaluation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..structured_schemas import (
    pydantic_to_response_format,
    structured_output_enabled,
)

logger = logging.getLogger(__name__)


def build_convergence_node(
    *,
    llm: Any,
    convergence_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
):
    """Return an async node function for the convergence node.

    Reads ``subagent_summaries`` from state (list of per-domain
    summaries) and produces ``convergence_status`` with the merged
    artifact.
    """

    async def convergence_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        *,
        store=None,
        **kwargs,
    ) -> dict[str, Any]:
        summaries = state.get("subagent_summaries") or []
        if not summaries:
            logger.info("convergence_node: no subagent_summaries, skipping")
            return {
                "convergence_status": {
                    "merged_fields": [],
                    "overlap_score": 0.0,
                    "conflicts": [],
                    "source_domains": [],
                    "merged_summary": "",
                },
            }

        user_query = latest_user_query_fn(state.get("messages") or [])
        source_domains = [s.get("domain", "unknown") for s in summaries]

        # If only one domain, skip LLM merge and pass through.
        if len(summaries) == 1:
            single = summaries[0]
            return {
                "convergence_status": {
                    "merged_fields": list(single.keys()),
                    "overlap_score": 0.0,
                    "conflicts": [],
                    "source_domains": source_domains,
                    "merged_summary": single.get("summary", ""),
                },
                "total_steps": (state.get("total_steps") or 0) + 1,
            }

        # Multiple domains: use LLM to merge
        system_msg = SystemMessage(content=convergence_prompt_template)
        summaries_text = json.dumps(summaries, ensure_ascii=False, default=str)
        human_msg = HumanMessage(
            content=(
                f"Användarens fråga: {user_query}\n\n"
                f"Subagent-resultat ({len(summaries)} domäner):\n{summaries_text}"
            )
        )

        try:
            raw = await llm.ainvoke([system_msg, human_msg], max_tokens=800)
            raw_content = str(getattr(raw, "content", "") or "")
            parsed = extract_first_json_object_fn(raw_content)

            convergence_status = {
                "merged_fields": parsed.get("merged_fields", []),
                "overlap_score": float(parsed.get("overlap_score", 0.0)),
                "conflicts": parsed.get("conflicts", []),
                "source_domains": source_domains,
                "merged_summary": parsed.get("merged_summary", ""),
            }

            logger.info(
                "convergence_node: merged %d domains, overlap=%.2f, conflicts=%d",
                len(source_domains),
                convergence_status["overlap_score"],
                len(convergence_status["conflicts"]),
            )

        except Exception:
            logger.exception("convergence_node: LLM merge failed, using simple concat")
            # Fallback: concatenate summaries
            concat_parts = []
            for s in summaries:
                domain = s.get("domain", "unknown")
                summary = s.get("summary", "")
                concat_parts.append(f"## {domain}\n{summary}")
            convergence_status = {
                "merged_fields": source_domains,
                "overlap_score": 0.0,
                "conflicts": [],
                "source_domains": source_domains,
                "merged_summary": "\n\n".join(concat_parts),
            }

        return {
            "convergence_status": convergence_status,
            "total_steps": (state.get("total_steps") or 0) + 1,
        }

    return convergence_node
