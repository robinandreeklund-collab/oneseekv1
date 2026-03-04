"""Synth Forge — Layer 2: LLM-generated test questions.

Generates test questions at 4 difficulty levels per tool using LiteLLM.
Each question undergoes roundtrip verification: query → retrieve → check
if expected tool appears in top-k results.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field

from app.nexus.config import (
    SYNTH_DIFFICULTIES,
    SYNTH_QUESTIONS_PER_DIFFICULTY,
    SYNTH_ROUNDTRIP_TOP_K,
)

logger = logging.getLogger(__name__)

# Prompt template for synthetic question generation
SYNTH_PROMPT = """Du är en expert på att testa AI-system för verktygsval.

Verktyg: {tool_name}
Beskrivning: {description}
Namespace: {namespace}
Nyckelord: {keywords}
Exkluderar: {excludes}
Geografisk räckvidd: {geographic_scope}

Generera exakt {questions_per_difficulty} frågor per kategori:
1. EASY — frågor som tydligt mappar till detta verktyg
2. MEDIUM — frågor där verktyget behövs men inte nämns explicit
3. HARD — frågor som testar disambiguation mot liknande verktyg
4. ADVERSARIAL — frågor som INTE ska välja detta verktyg (för negativ träning)

Svara ENBART med JSON-array:
[
  {{
    "difficulty": "easy|medium|hard|adversarial",
    "question": "frågetexten",
    "expected_tool": "verktygets_id eller null för adversarial",
    "expected_reason": "kort motivering"
  }}
]
"""


@dataclass
class GeneratedCase:
    """A single generated test case."""

    tool_id: str
    namespace: str
    question: str
    difficulty: str
    expected_tool: str | None = None
    expected_reason: str = ""
    roundtrip_verified: bool = False
    quality_score: float | None = None


@dataclass
class ForgeRunResult:
    """Result of a Synth Forge generation run."""

    run_id: uuid.UUID
    total_generated: int = 0
    total_verified: int = 0
    by_difficulty: dict[str, int] = field(default_factory=dict)
    cases: list[GeneratedCase] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class SynthForge:
    """Layer 2: Auto-generate test questions per tool.

    Uses LiteLLM to generate questions at 4 difficulty levels,
    then verifies each through a roundtrip retrieval check.
    """

    def __init__(
        self,
        difficulties: list[str] | None = None,
        questions_per_difficulty: int = SYNTH_QUESTIONS_PER_DIFFICULTY,
        roundtrip_top_k: int = SYNTH_ROUNDTRIP_TOP_K,
    ):
        self.difficulties = difficulties or SYNTH_DIFFICULTIES
        self.questions_per_difficulty = questions_per_difficulty
        self.roundtrip_top_k = roundtrip_top_k

    def build_prompt(self, tool_metadata: dict) -> str:
        """Build the generation prompt from tool metadata."""
        return SYNTH_PROMPT.format(
            tool_name=tool_metadata.get("name", ""),
            description=tool_metadata.get("description", ""),
            namespace=tool_metadata.get("namespace", ""),
            keywords=", ".join(tool_metadata.get("keywords", [])),
            excludes=", ".join(tool_metadata.get("excludes", [])),
            geographic_scope=tool_metadata.get("geographic_scope", ""),
            questions_per_difficulty=self.questions_per_difficulty,
        )

    def parse_llm_response(
        self, response_text: str, tool_id: str, namespace: str
    ) -> list[GeneratedCase]:
        """Parse LLM JSON response into GeneratedCase objects."""
        cases: list[GeneratedCase] = []

        try:
            # Try to extract JSON array from response
            text = response_text.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            items = json.loads(text)
            if not isinstance(items, list):
                items = [items]

            for item in items:
                difficulty = str(item.get("difficulty", "")).lower()
                if difficulty not in self.difficulties:
                    continue

                # For non-adversarial cases the expected tool is always the
                # tool we generated for.  The LLM sometimes returns a
                # namespace prefix (e.g. "tools/trafik") instead of the real
                # tool_id — force the known value to avoid wrong proposals.
                expected = None if difficulty == "adversarial" else tool_id

                cases.append(
                    GeneratedCase(
                        tool_id=tool_id,
                        namespace=namespace,
                        question=str(item.get("question", "")),
                        difficulty=difficulty,
                        expected_tool=expected,
                        expected_reason=str(item.get("expected_reason", "")),
                    )
                )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse LLM response for %s: %s", tool_id, e)

        return cases

    async def generate_for_tool(
        self,
        tool_metadata: dict,
        *,
        llm_call: object | None = None,
    ) -> list[GeneratedCase]:
        """Generate test cases for a single tool.

        Args:
            tool_metadata: Dict with name, description, namespace, keywords, etc.
            llm_call: Async callable(prompt) → str. If None, returns empty.

        Returns:
            List of generated cases.
        """
        if llm_call is None:
            logger.info(
                "No LLM callable provided, skipping generation for %s",
                tool_metadata.get("tool_id", ""),
            )
            return []

        tool_id = tool_metadata.get("tool_id", "")
        namespace = tool_metadata.get("namespace", "")
        prompt = self.build_prompt(tool_metadata)

        try:
            response = await llm_call(prompt)
            cases = self.parse_llm_response(response, tool_id, namespace)
            logger.info("Generated %d cases for %s", len(cases), tool_id)
            return cases
        except Exception as e:
            logger.error("LLM generation failed for %s: %s", tool_id, e)
            return []

    def verify_roundtrip(
        self,
        case: GeneratedCase,
        retrieve_fn: object | None = None,
    ) -> bool:
        """Verify a case through roundtrip retrieval.

        Args:
            case: The generated case.
            retrieve_fn: Callable(query) → list[str] (tool_ids). If None, skip.

        Returns:
            True if the expected tool appears in top-k results.
        """
        if retrieve_fn is None or case.expected_tool is None:
            return False

        try:
            results = retrieve_fn(case.question)
            top_k = results[: self.roundtrip_top_k]
            return case.expected_tool in top_k
        except Exception as e:
            logger.warning("Roundtrip verification failed: %s", e)
            return False

    async def run(
        self,
        tools: list[dict],
        *,
        llm_call: object | None = None,
        retrieve_fn: object | None = None,
        tool_ids: list[str] | None = None,
    ) -> ForgeRunResult:
        """Run the full Synth Forge pipeline.

        Args:
            tools: List of tool metadata dicts.
            llm_call: Async callable(prompt) → str.
            retrieve_fn: Callable(query) → list[str].
            tool_ids: Subset of tool IDs to generate for. None = all.

        Returns:
            ForgeRunResult with all generated cases.
        """
        run_id = uuid.uuid4()
        result = ForgeRunResult(run_id=run_id)

        for tool in tools:
            tid = tool.get("tool_id", "")
            if tool_ids and tid not in tool_ids:
                continue

            cases = await self.generate_for_tool(tool, llm_call=llm_call)

            for case in cases:
                case.roundtrip_verified = self.verify_roundtrip(case, retrieve_fn)
                if case.roundtrip_verified:
                    result.total_verified += 1

                result.cases.append(case)
                result.total_generated += 1
                result.by_difficulty[case.difficulty] = (
                    result.by_difficulty.get(case.difficulty, 0) + 1
                )

        logger.info(
            "Forge run %s: %d generated, %d verified",
            run_id,
            result.total_generated,
            result.total_verified,
        )
        return result
