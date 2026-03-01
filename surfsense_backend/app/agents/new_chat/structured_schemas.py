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


# ────────────────────────────────────────────────────────────────
# Compare: Criterion Evaluator
# ────────────────────────────────────────────────────────────────


class CriterionEvalResult(BaseModel):
    """Output schema for a single criterion evaluator in compare mode."""

    thinking: str = Field(
        ...,
        description="Intern resonering om bedömningen av detta kriterium.",
    )
    score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Poäng 0-100 för detta kriterium.",
    )
    reasoning: str = Field(
        ...,
        description="En mening som motiverar poängen.",
    )


class CombinedCriterionEvalResult(BaseModel):
    """Output schema for evaluating all 4 criteria in a single LLM call.

    This reduces compare mode from 32 LLM calls (8 domains × 4 criteria)
    to 8 calls (1 per domain), improving speed and reliability.
    """

    thinking: str = Field(
        ...,
        description="Intern resonering om bedömningen av alla fyra kriterier.",
    )
    relevans_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Relevans-poäng 0-100.",
    )
    relevans_reasoning: str = Field(
        ...,
        description="En mening som motiverar relevans-poängen.",
    )
    djup_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Djup-poäng 0-100.",
    )
    djup_reasoning: str = Field(
        ...,
        description="En mening som motiverar djup-poängen.",
    )
    klarhet_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Klarhet-poäng 0-100.",
    )
    klarhet_reasoning: str = Field(
        ...,
        description="En mening som motiverar klarhet-poängen.",
    )
    korrekthet_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Korrekthet-poäng 0-100.",
    )
    korrekthet_reasoning: str = Field(
        ...,
        description="En mening som motiverar korrekthet-poängen.",
    )


# ────────────────────────────────────────────────────────────────
# Compare: Research Query Decomposer
# ────────────────────────────────────────────────────────────────


class ResearchDecomposeResult(BaseModel):
    """Output schema for compare research query decomposition."""

    thinking: str = Field(
        ...,
        description="Resonering om hur frågan bäst delas upp i sökfrågor.",
    )
    queries: list[str] = Field(
        ...,
        description="1-3 korta, specifika sökfrågor.",
    )


# ────────────────────────────────────────────────────────────────
# Compare: Arena Analysis (Synthesizer output)
# ────────────────────────────────────────────────────────────────


class ArenaDisagreement(BaseModel):
    """A single disagreement between models."""

    topic: str = Field(..., description="Kort ämne för meningsskiljaktigheten.")
    sides: dict[str, str] = Field(
        ..., description="Modellnamn → deras ståndpunkt."
    )
    verdict: str = Field(..., description="Research/faktabaserad bedömning.")


class ArenaUniqueContribution(BaseModel):
    """A unique insight from one model."""

    model: str = Field(..., description="Modellens namn.")
    insight: str = Field(..., description="Unik insikt från modellen.")


class ArenaAnalysisResult(BaseModel):
    """Output schema for compare synthesizer arena analysis."""

    thinking: str = Field(
        ...,
        description="Intern resonering om jämförelsen på svenska.",
    )
    consensus: list[str] = Field(
        default_factory=list,
        description="Saker alla/de flesta modeller håller med om.",
    )
    disagreements: list[ArenaDisagreement] = Field(
        default_factory=list,
        description="Meningsskiljaktigheter mellan modeller.",
    )
    unique_contributions: list[ArenaUniqueContribution] = Field(
        default_factory=list,
        description="Unika bidrag per modell.",
    )
    winner_rationale: str = Field(
        ...,
        description=(
            "Motivering av vinnaren — MÅSTE matcha den faktiska rankingen "
            "baserat på viktade poäng. Nämn #1 modellen först."
        ),
    )
    reliability_notes: str = Field(
        default="",
        description="Noteringar om tillförlitlighet och research-verifiering.",
    )


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


class CompareSynthesisResult(BaseModel):
    """Output schema for the compare synthesizer node.

    The ``thinking`` field captures internal reasoning (streamed to
    the think-box as reasoning-delta).  The ``response`` field is the
    final user-facing markdown text (streamed as text-delta).
    """

    thinking: str = Field(
        ...,
        description=(
            "Din interna resonemang på svenska.  Analysera konvergens-"
            "resultaten, identifiera huvudsakliga slutsatser, och "
            "planera hur du ska formulera det slutgiltiga svaret."
        ),
    )
    response: str = Field(
        ...,
        description=(
            "Det slutgiltiga svaret till användaren i markdown.  "
            "Innehåller en sammanfattande analys med fokus på "
            "faktasvar, modellernas styrkor/svagheter, och en "
            "tydlig slutsats.  Inkludera INTE spotlight-arena-data "
            "eller rå JSON — bara ren markdown-text."
        ),
    )
