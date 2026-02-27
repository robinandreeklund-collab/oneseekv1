"""P4.1: Convergence node — merges parallel subagent mini-graph results.

Takes ``subagent_summaries`` produced by the subagent_spawner (which now
contain proper handoff contract fields: subagent_id, status, confidence,
summary, findings) and creates a unified artifact with source attribution,
overlap detection, and conflict flagging.

The merged result is passed to the critic for final quality evaluation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


def build_convergence_node(
    *,
    llm: Any,
    convergence_prompt_template: str,
    latest_user_query_fn: Callable[[list[Any] | None], str],
    extract_first_json_object_fn: Callable[[str], dict[str, Any]],
):
    """Return an async node function for the convergence node.

    Reads ``subagent_summaries`` from state (list of per-domain handoff
    dicts with subagent_id, status, confidence, summary, findings, etc.)
    and produces ``convergence_status`` with the merged artifact.
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
        source_domains = [
            s.get("domain", s.get("agent", "unknown")) for s in summaries
        ]

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
                    "subagent_ids": [single.get("subagent_id", "")],
                    "domain_statuses": {
                        source_domains[0]: single.get("status", "partial"),
                    },
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

        # Collect per-domain metadata from handoff contracts
        subagent_ids = [s.get("subagent_id", "") for s in summaries]
        domain_statuses = {
            s.get("domain", s.get("agent", f"domain_{i}")): s.get("status", "partial")
            for i, s in enumerate(summaries)
        }

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
                "subagent_ids": subagent_ids,
                "domain_statuses": domain_statuses,
            }

            logger.info(
                "convergence_node: merged %d domains, overlap=%.2f, conflicts=%d",
                len(source_domains),
                convergence_status["overlap_score"],
                len(convergence_status["conflicts"]),
            )

        except Exception:
            logger.exception("convergence_node: LLM merge failed, using simple concat")
            # Fallback: concatenate summaries with handoff metadata
            concat_parts = []
            for s in summaries:
                domain = s.get("domain", s.get("agent", "unknown"))
                summary = s.get("summary", "")
                status = s.get("status", "partial")
                findings = s.get("findings", [])
                findings_text = ""
                if findings:
                    findings_text = "\n".join(f"- {f}" for f in findings)
                    findings_text = f"\n{findings_text}"
                concat_parts.append(
                    f"## {domain} (status: {status})\n{summary}{findings_text}"
                )
            convergence_status = {
                "merged_fields": source_domains,
                "overlap_score": 0.0,
                "conflicts": [],
                "source_domains": source_domains,
                "merged_summary": "\n\n".join(concat_parts),
                "subagent_ids": subagent_ids,
                "domain_statuses": domain_statuses,
            }

        return {
            "convergence_status": convergence_status,
            "total_steps": (state.get("total_steps") or 0) + 1,
        }

    return convergence_node
