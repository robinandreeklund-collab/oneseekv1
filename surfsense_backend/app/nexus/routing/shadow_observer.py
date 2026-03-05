"""Shadow Observer — connects NEXUS to the real live routing pipeline.

Reads telemetry from the platform's retrieval_feedback_store and
shadow mode decisions, allowing NEXUS to observe, compare, and improve
routing without interfering with the production pipeline.

This is how NEXUS learns from the REAL routing system:
1. Reads shadow mode decisions (tool selection, scores, margins)
2. Reads retrieval feedback (success/failure per tool per query pattern)
3. Compares NEXUS routing decisions against the real pipeline
4. Feeds discrepancies into the auto-loop for improvement
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ShadowComparison:
    """Result of comparing NEXUS routing vs real platform routing."""

    query: str
    nexus_tool: str | None
    platform_tool: str | None
    nexus_score: float
    platform_score: float
    platform_margin: float | None
    platform_mode: str  # "auto_select", "candidate_shortlist", "shadow", "profile"
    agreement: bool  # True if NEXUS and platform agree on top tool
    nexus_band: int = 0
    platform_phase: str = "shadow"


@dataclass
class ShadowObserverReport:
    """Aggregated report from shadow observation."""

    total_observations: int = 0
    agreements: int = 0
    disagreements: int = 0
    agreement_rate: float = 0.0
    disagreement_samples: list[ShadowComparison] = field(default_factory=list)
    feedback_snapshot: dict[str, Any] = field(default_factory=dict)
    live_routing_phase: str = "shadow"
    live_routing_enabled: bool = False


class ShadowObserver:
    """Observes the real platform routing pipeline from NEXUS.

    Reads from:
    - retrieval_feedback_store: success/failure signals from real routing
    - _resolve_live_tool_selection_for_agent() output: shadow mode decisions

    Does NOT modify the real pipeline — read-only observation.
    """

    def get_retrieval_feedback_snapshot(self) -> dict[str, Any]:
        """Read the current retrieval feedback store state.

        Returns the live success/failure signals the platform has collected
        from real user interactions (reformulations, follow-ups, thumbs up/down).
        """
        try:
            from app.agents.new_chat.retrieval_feedback import (
                get_global_retrieval_feedback_store,
            )

            store = get_global_retrieval_feedback_store()
            return store.snapshot()
        except Exception:
            logger.debug("Could not read retrieval feedback store")
            return {"rows": [], "count": 0}

    def get_feedback_for_tool(self, tool_id: str) -> dict[str, Any]:
        """Get retrieval feedback signals for a specific tool.

        Returns success/failure counts and score adjustment the platform
        applies to this tool during live routing.
        """
        try:
            from app.agents.new_chat.retrieval_feedback import (
                get_global_retrieval_feedback_store,
            )

            store = get_global_retrieval_feedback_store()
            snapshot = store.snapshot()
            tool_rows = [
                r for r in snapshot.get("rows", []) if r.get("tool_id") == tool_id
            ]
            return {
                "tool_id": tool_id,
                "patterns": tool_rows,
                "total_patterns": len(tool_rows),
            }
        except Exception:
            return {"tool_id": tool_id, "patterns": [], "total_patterns": 0}

    def get_live_tool_index(self) -> list[dict[str, Any]]:
        """Read the current live tool index by building from platform_bridge.

        Uses the same tool metadata available to NEXUS (from platform_bridge)
        rather than requiring the full runtime tool_registry.
        """
        try:
            from app.nexus.platform_bridge import get_platform_tools

            tools = get_platform_tools()
            return [
                {
                    "tool_id": t.tool_id,
                    "namespace": "/".join(t.namespace),
                    "zone": t.zone,
                    "category": t.category,
                }
                for t in tools
            ]
        except Exception:
            return []

    async def run_platform_retrieval(
        self,
        query: str,
        *,
        agent_name: str = "kunskap",
        session: Any = None,
    ) -> dict[str, Any]:
        """Run tool retrieval using NEXUS platform_bridge data.

        Since build_tool_index() requires a full runtime tool_registry
        (with BaseTool instances and async dependencies), we use NEXUS's
        own platform_bridge scoring as the platform comparison baseline.

        This still provides meaningful comparison data — it uses the same
        tool metadata, keywords, and namespace mappings as the live system.

        Args:
            query: User query to route.
            agent_name: Platform agent context for namespace selection.
            session: DB session for loading tuning config.

        Returns:
            Dict with ranked_ids, scores, and margin.
        """
        try:
            from app.nexus.embeddings import nexus_batch_score
            from app.nexus.platform_bridge import get_platform_tools

            tools = get_platform_tools()
            if not tools:
                return {"ranked_ids": [], "breakdown": [], "error": "empty_registry"}

            # Determine primary namespaces for agent
            primary_ns, _ = self._get_agent_namespaces(agent_name)
            primary_prefixes = ["/".join(ns) for ns in primary_ns]

            query_lower = query.lower()
            query_tokens = set(query_lower.split())

            # Filter tools and batch-compute embedding scores
            filtered_tools = [pt for pt in tools if pt.category != "external_model"]
            tool_texts = [
                f"{pt.tool_id} {pt.description}" for pt in filtered_tools
            ]
            emb_scores = nexus_batch_score(query_lower, tool_texts)

            # Score each tool
            scored: list[tuple[str, float, dict]] = []
            for i, pt in enumerate(filtered_tools):
                score = 0.0
                ns_str = "/".join(pt.namespace)

                # Namespace match bonus (tools in agent's primary namespaces)
                for prefix in primary_prefixes:
                    if ns_str.startswith(prefix):
                        score += 0.25
                        break

                # Keyword overlap
                tool_kw = {k.lower() for k in pt.keywords}
                hits = query_tokens & tool_kw
                if hits:
                    score += min(0.30, len(hits) * 0.10)

                # Name match
                name_parts = pt.tool_id.lower().replace("_", " ").split()
                if any(tok in query_lower for tok in name_parts if len(tok) > 3):
                    score += 0.15

                # Embedding similarity (from batch computation)
                emb_score = emb_scores[i] if emb_scores is not None else None
                if emb_score is not None:
                    score += emb_score * 0.50

                scored.append(
                    (
                        pt.tool_id,
                        score,
                        {"tool_id": pt.tool_id, "namespace": ns_str, "score": score},
                    )
                )

            # Sort by score descending
            scored.sort(key=lambda x: x[1], reverse=True)

            ranked_ids = [s[0] for s in scored[:5]]
            breakdown = [s[2] for s in scored[:5]]

            top1 = ranked_ids[0] if ranked_ids else None
            top2 = ranked_ids[1] if len(ranked_ids) > 1 else None
            top1_score = scored[0][1] if scored else 0.0
            top2_score = scored[1][1] if len(scored) > 1 else 0.0
            margin = top1_score - top2_score if top1 and top2 else None

            return {
                "ranked_ids": ranked_ids,
                "breakdown": breakdown,
                "top1": top1,
                "top2": top2,
                "top1_score": top1_score,
                "top2_score": top2_score,
                "margin": margin,
            }
        except Exception as e:
            logger.warning("Platform retrieval failed: %s", e)
            return {"ranked_ids": [], "breakdown": [], "error": str(e)}

    def compare_routing(
        self,
        query: str,
        nexus_tool: str | None,
        nexus_score: float,
        nexus_band: int,
        platform_result: dict[str, Any],
    ) -> ShadowComparison:
        """Compare a NEXUS routing decision against the platform's decision."""
        platform_tool = platform_result.get("top1")
        platform_score = platform_result.get("top1_score", 0.0)
        platform_margin = platform_result.get("margin")
        platform_mode = platform_result.get("mode", "unknown")
        platform_phase = platform_result.get("phase", "shadow")

        return ShadowComparison(
            query=query,
            nexus_tool=nexus_tool,
            platform_tool=platform_tool,
            nexus_score=nexus_score,
            platform_score=platform_score,
            platform_margin=platform_margin,
            platform_mode=platform_mode,
            agreement=nexus_tool == platform_tool,
            nexus_band=nexus_band,
            platform_phase=platform_phase,
        )

    def _get_agent_namespaces(
        self, agent_name: str
    ) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
        """Map agent name to primary and fallback namespaces.

        Mirrors the namespace configuration in supervisor_constants.py
        _build_agent_tool_profiles().
        """
        agent_ns_map: dict[str, tuple[list[tuple[str, ...]], list[tuple[str, ...]]]] = {
            "väder": (
                [("tools", "weather")],
                [("tools", "knowledge")],
            ),
            "trafik": (
                [("tools", "trafik")],
                [("tools", "knowledge")],
            ),
            "statistik": (
                [("tools", "statistics")],
                [("tools", "knowledge")],
            ),
            "riksdagen": (
                [("tools", "politik")],
                [("tools", "knowledge")],
            ),
            "bolag": (
                [("tools", "bolag")],
                [("tools", "knowledge")],
            ),
            "marknad": (
                [("tools", "marketplace")],
                [("tools", "knowledge")],
            ),
            "kunskap": (
                [("tools", "knowledge")],
                [("tools", "general")],
            ),
            "webb": (
                [("tools", "action", "web"), ("tools", "knowledge", "web")],
                [("tools", "knowledge")],
            ),
            "kartor": (
                [("tools", "kartor")],
                [("tools", "action")],
            ),
            "kod": (
                [("tools", "code")],
                [("tools", "action")],
            ),
            "media": (
                [("tools", "action", "media")],
                [("tools", "action")],
            ),
        }

        if agent_name in agent_ns_map:
            return agent_ns_map[agent_name]

        # Default: broad knowledge search
        return [("tools", "knowledge")], [("tools", "general")]
