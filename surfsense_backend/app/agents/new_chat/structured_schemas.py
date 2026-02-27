"""
Pydantic schemas for structured LLM output (JSON Schema strict mode).

Sprint P1 Extra: Every LLM-calling node gets a dedicated schema with
``thinking`` as the FIRST field so the model reasons before it decides.

Usage:
    from .structured_schemas import IntentResult, pydantic_to_response_format

    raw = await llm.ainvoke(
        messages,
        response_format=pydantic_to_response_format(IntentResult, "intent_result"),
    )
    result = IntentResult.model_validate_json(raw.content)
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field


def structured_output_enabled() -> bool:
    """Return ``True`` if structured JSON Schema output is enabled (default)."""
    return os.getenv("STRUCTURED_OUTPUT_ENABLED", "true").lower() == "true"


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────


def pydantic_to_response_format(model: type[BaseModel], name: str) -> dict:
    """Convert a Pydantic model to a ``response_format`` dict for LiteLLM.

    Returns the structure expected by the OpenAI-compatible
    ``response_format`` parameter with ``type="json_schema"`` and
    ``strict=True``.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": model.model_json_schema(),
        },
    }


# ────────────────────────────────────────────────────────────────
# Intent Resolution
# ────────────────────────────────────────────────────────────────


class IntentResult(BaseModel):
    """Output schema for the intent resolver node."""

    thinking: str = Field(
        ...,
        description=(
            "Intern resonering om användarens avsikt, "
            "kandidatanalys och beslutsunderlag."
        ),
    )
    intent_id: str = Field(
        ...,
        description="ID för vald intent, måste matcha en av kandidaterna.",
    )
    route: Literal["kunskap", "skapande", "jämförelse", "konversation", "mixed"] = (
        Field(
            ...,
            description="Övergripande rutt-kategori.",
        )
    )
    sub_intents: list[str] = Field(
        default_factory=list,
        description="Del-intents vid mixed route.",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Konfidens 0.0-1.0.",
    )


# ────────────────────────────────────────────────────────────────
# Multi-Query Decomposer (P3)
# ────────────────────────────────────────────────────────────────


class AtomicQuestion(BaseModel):
    """A single atomic sub-question decomposed from a complex query."""

    id: str = Field(
        ...,
        description="Unik fråge-ID, t.ex. q1, q2.",
    )
    text: str = Field(
        ...,
        description="Den atomära delfrågan på svenska.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Lista med ID:n för frågor som måste besvaras först.",
    )
    domain: str = Field(
        ...,
        description="Domän som bäst matchar frågan, t.ex. väder, statistik, trafik, kunskap.",
    )


class DecomposerResult(BaseModel):
    """Output schema for the multi-query decomposer node."""

    thinking: str = Field(
        ...,
        description="Intern resonering om hur frågan ska brytas ned.",
    )
    questions: list[AtomicQuestion] = Field(
        ...,
        description="Lista med atomära delfrågor.",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )


# ────────────────────────────────────────────────────────────────
# Agent Resolver
# ────────────────────────────────────────────────────────────────


class AgentResolverResult(BaseModel):
    """Output schema for the agent resolver node."""

    thinking: str = Field(
        ...,
        description="Resonering om vilka agenter som bäst matchar uppgiften.",
    )
    selected_agents: list[str] = Field(
        ...,
        description="Lista med agentnamn (måste matcha kandidater).",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Konfidens 0.0-1.0.",
    )


# ────────────────────────────────────────────────────────────────
# Planner
# ────────────────────────────────────────────────────────────────


class PlanStep(BaseModel):
    """A single execution step within a plan."""

    id: str = Field(
        ...,
        description="Steg-ID, t.ex. step-1.",
    )
    content: str = Field(
        ...,
        description="Beskrivning av steget.",
    )
    status: Literal["pending", "in_progress", "completed", "cancelled"] = Field(
        default="pending",
    )
    parallel: bool = Field(
        default=False,
        description="True om steget kan köras parallellt med andra.",
    )


class PlannerResult(BaseModel):
    """Output schema for the planner node."""

    thinking: str = Field(
        ...,
        description="Resonering om hur frågan bäst bryts ned i steg.",
    )
    steps: list[PlanStep] = Field(
        ...,
        description="Exekveringssteg (max 4).",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )


# ────────────────────────────────────────────────────────────────
# Domain Planner
# ────────────────────────────────────────────────────────────────


class DomainAgentPlan(BaseModel):
    """Micro-plan for a single domain agent."""

    mode: Literal["parallel", "sequential"] = Field(
        ...,
        description="parallel om verktygen är oberoende, sequential om beroende.",
    )
    tools: list[str] = Field(
        ...,
        description="Verktygs-ID att anropa (max 4).",
    )
    rationale: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )


class DomainPlannerResult(BaseModel):
    """Output schema for the domain planner node."""

    thinking: str = Field(
        ...,
        description=(
            "Resonering om verktygsval, beroenden och parallellitet per domänagent."
        ),
    )
    domain_plans: dict[str, DomainAgentPlan] = Field(
        ...,
        description="Mikro-plan per domänagent (nyckel = agentnamn).",
    )
    reason: str = Field(
        ...,
        description="Övergripande motivering på svenska.",
    )


# ────────────────────────────────────────────────────────────────
# Critic
# ────────────────────────────────────────────────────────────────


class CriticResult(BaseModel):
    """Output schema for the critic node."""

    thinking: str = Field(
        ...,
        description=("Resonering om svarets kvalitet, fullständighet och brister."),
    )
    decision: Literal["ok", "needs_more", "replan"] = Field(
        ...,
        description=(
            "Beslut: ok (godkänt), needs_more (behöver mer data), "
            "replan (ny plan krävs)."
        ),
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Konfidens 0.0-1.0.",
    )


# ────────────────────────────────────────────────────────────────
# Synthesizer
# ────────────────────────────────────────────────────────────────


class SynthesizerResult(BaseModel):
    """Output schema for the synthesizer node."""

    thinking: str = Field(
        ...,
        description="Resonering om hur källmaterial bäst sammanfogas.",
    )
    response: str = Field(
        ...,
        description="Det förfinade, slutgiltiga svaret (markdown).",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )


# ────────────────────────────────────────────────────────────────
# Response Layer Router
# ────────────────────────────────────────────────────────────────


class ResponseLayerRouterResult(BaseModel):
    """Output schema for the response layer router node."""

    thinking: str = Field(
        ...,
        description=("Resonering om vilken presentationsform som passar bäst."),
    )
    chosen_layer: Literal["kunskap", "analys", "syntes", "visualisering"] = Field(
        ...,
        description="Vald presentationsform.",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )
    data_characteristics: str = Field(
        default="",
        description="Beskrivning av datans karaktäristik.",
    )


# ────────────────────────────────────────────────────────────────
# Response Layer (user-facing)
# ────────────────────────────────────────────────────────────────


class ResponseLayerResult(BaseModel):
    """Output schema for the response layer node (final answer)."""

    thinking: str = Field(
        ...,
        description="Kort resonering om formateringsstrategi.",
    )
    response: str = Field(
        ...,
        description="Fullständigt formaterat svar till användaren (markdown).",
    )


# ── Executor (tool-calling node) ─────────────────────────────


class ExecutorThinkingResult(BaseModel):
    """Minimal structured output for the executor node.

    The executor primarily makes tool calls; this schema captures the
    reasoning that appears in the ``content`` field alongside those calls.
    When the model makes tool calls with empty content the parser handles
    the null/empty case gracefully.
    """

    thinking: str = Field(
        ...,
        description=(
            "Resonering om vilka verktyg/agenter som ska anropas, "
            "i vilken ordning, och varför."
        ),
    )


# ────────────────────────────────────────────────────────────────
# P4 Mini-Graph: Mini Planner
# ────────────────────────────────────────────────────────────────


class MiniPlanStep(BaseModel):
    """A single step in a mini-graph micro-plan."""

    action: str = Field(
        ...,
        description="Beskrivning av steget.",
    )
    tool_id: str = Field(
        ...,
        description="Verktygs-ID att anropa.",
    )
    use_cache: bool = Field(
        default=False,
        description="Om cached resultat ska användas.",
    )


class MiniPlannerResult(BaseModel):
    """Output schema for the mini planner node (P4)."""

    thinking: str = Field(
        ...,
        description="Resonera om bästa approach för denna domän.",
    )
    steps: list[MiniPlanStep] = Field(
        ...,
        description="Mikro-plansteg (max 3).",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )


# ────────────────────────────────────────────────────────────────
# P4 Mini-Graph: Mini Critic
# ────────────────────────────────────────────────────────────────


class MiniCriticResult(BaseModel):
    """Output schema for the mini critic node (P4)."""

    thinking: str = Field(
        ...,
        description="Bedöm resultatkvalitet för denna domän.",
    )
    decision: Literal["ok", "retry", "fail"] = Field(
        ...,
        description="Beslut: ok, retry, eller fail.",
    )
    feedback: str = Field(
        ...,
        description="Vad saknas eller bör justeras.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Konfidens 0.0-1.0.",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )


# ────────────────────────────────────────────────────────────────
# P4 Mini-Graph: Sub-Spawn Check
# ────────────────────────────────────────────────────────────────


class SubSpawnDomain(BaseModel):
    """A single sub-domain identified for recursive spawning."""

    tools: list[str] = Field(
        ...,
        description="Verktygs-ID:n för sub-domänen.",
    )
    rationale: str = Field(
        ...,
        description="Varför sub-spawning behövs.",
    )


class SubSpawnCheckResult(BaseModel):
    """Output schema for the sub-spawn check (P4)."""

    thinking: str = Field(
        ...,
        description="Resonering om sub-spawning-behov.",
    )
    needs_sub_spawn: bool = Field(
        ...,
        description="Om resultatet behöver sub-domäner.",
    )
    sub_domains: dict[str, SubSpawnDomain] = Field(
        default_factory=dict,
        description="Sub-domäner vid needs_sub_spawn=true.",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )


# ────────────────────────────────────────────────────────────────
# P4 Convergence
# ────────────────────────────────────────────────────────────────


class ModelDimensionScores(BaseModel):
    """Per-dimension scores for a single model."""

    relevans: int = Field(..., ge=0, le=100, description="Relevans 0-100")
    djup: int = Field(..., ge=0, le=100, description="Djup 0-100")
    klarhet: int = Field(..., ge=0, le=100, description="Klarhet 0-100")
    korrekthet: int = Field(..., ge=0, le=100, description="Korrekthet 0-100")


class ConvergenceResult(BaseModel):
    """Output schema for the convergence node (P4)."""

    thinking: str = Field(
        ...,
        description="Analysera och slå ihop resultat från alla subagenter.",
    )
    merged_summary: str = Field(
        ...,
        description="Sammanslagen markdown-sammanfattning.",
    )
    merged_fields: list[str] = Field(
        ...,
        description="Fält som ingår i sammanslagningen.",
    )
    overlap_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Dataredundans 0.0-1.0.",
    )
    conflicts: list[str] = Field(
        default_factory=list,
        description="Identifierade konflikter mellan domäner.",
    )
    reason: str = Field(
        ...,
        description="Kort motivering på svenska.",
    )
    model_scores: dict[str, ModelDimensionScores] = Field(
        default_factory=dict,
        description="Per-modell poäng: {domain: {relevans, djup, klarhet, korrekthet}}",
    )
    agreements: list[str] = Field(
        default_factory=list,
        description="Saker modellerna håller med om.",
    )
    disagreements: list[str] = Field(
        default_factory=list,
        description="Saker modellerna inte håller med om.",
    )
    unique_insights: dict[str, str] = Field(
        default_factory=dict,
        description="Unika insikter per modell: {domain: insikt}",
    )
    comparative_summary: str = Field(
        default="",
        description="Djup jämförande analys med konkreta exempel.",
    )
