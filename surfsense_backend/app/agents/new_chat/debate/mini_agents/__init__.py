"""Mini-agents for the OneSeek debate subagent P4 pipeline.

Each mini-agent runs in parallel and produces focused output:
- tavily_core: Primary web search for topic facts
- fresh_news: Latest news and developments
- counter_evidence: Weakness analysis of other arguments
- swedish_context: Sweden-specific data and sources
- fact_consolidation: Fact verification and organization
- clarity: Argumentation structure optimization
"""

from app.agents.new_chat.oneseek_debate_subagent import (
    _run_clarity_agent as run_clarity,
    _run_counter_evidence as run_counter_evidence,
    _run_fact_consolidation as run_fact_consolidation,
    _run_fresh_news as run_fresh_news,
    _run_swedish_context as run_swedish_context,
    _run_tavily_core as run_tavily_core,
)

__all__ = [
    "run_tavily_core",
    "run_fresh_news",
    "run_counter_evidence",
    "run_swedish_context",
    "run_fact_consolidation",
    "run_clarity",
]
