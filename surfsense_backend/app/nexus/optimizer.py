"""Metadata Optimizer — LLM-powered tool metadata optimization.

Uses a configured LLM (e.g. Claude Sonnet via config_id=-24) to generate
optimized metadata for tools within a namespace/category batch.
The LLM sees ALL tools in the batch to maximize embedding separation.

Flow:
  1. Load tools from platform_bridge (+ existing DB overrides)
  2. Build prompt with all tools in batch
  3. Call LLM → get structured JSON suggestions
  4. Return suggestions for admin review
  5. On approval → upsert via tool_metadata_service → NEXUS picks up changes
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import litellm
from sqlalchemy.ext.asyncio import AsyncSession

from app.nexus.platform_bridge import (
    PlatformTool,
    get_category_names,
    get_platform_tools,
    invalidate_cache,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ToolSuggestion:
    """A single tool's optimized metadata suggestion."""

    tool_id: str
    current: dict[str, Any]
    suggested: dict[str, Any]
    reasoning: str = ""
    fields_changed: list[str] = field(default_factory=list)


@dataclass
class OptimizerResult:
    """Result from an optimizer run."""

    category: str
    total_tools: int = 0
    suggestions: list[ToolSuggestion] = field(default_factory=list)
    model_used: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Du är en expert på information retrieval och embedding-optimering.
Din uppgift är att optimera metadata för verktyg (tools) i ett AI-system
som använder semantic embeddings för att matcha användarfrågor till rätt verktyg.

REGLER:
1. Varje verktygs description MÅSTE vara unik och tydligt separerad från andra verktyg
2. Keywords ska vara specifika och relevanta — inte generella
3. Example queries ska vara realistiska svenska frågor som EN VANLIG ANVÄNDARE ställer
4. Excludes ska lista verktyg/ämnen som INTE ska matcha detta verktyg
5. Geographic scope ska vara specifik (t.ex. "Sverige", "Norden", "Globalt")
6. Tänk på att descriptions används för cosine similarity — de måste vara semantiskt distinkta

VIKTIGT: Svara ENBART med valid JSON. Ingen markdown, inga kommentarer utanför JSON."""

_USER_PROMPT_TEMPLATE = """\
Här är {tool_count} verktyg i kategorin "{category}".
Optimera metadata för VARJE verktyg så att de blir maximalt separerade i embedding-rymden.

NUVARANDE VERKTYG:
{tools_json}

Svara med en JSON-array där varje element har denna struktur:
{{
  "tool_id": "...",
  "description": "optimerad description (max 300 tecken)",
  "keywords": ["lista", "av", "relevanta", "keywords"],
  "example_queries": ["realistisk fråga 1", "realistisk fråga 2", "realistisk fråga 3"],
  "excludes": ["verktyg/ämnen som INTE ska matcha"],
  "geographic_scope": "specifik scope",
  "reasoning": "kort motivering av ändringar"
}}

Returnera en JSON-array med exakt {tool_count} element — ett per verktyg."""


# ---------------------------------------------------------------------------
# MetadataOptimizer
# ---------------------------------------------------------------------------


class MetadataOptimizer:
    """LLM-powered tool metadata optimization per category/namespace batch."""

    async def generate_suggestions(
        self,
        session: AsyncSession,
        *,
        category: str | None = None,
        namespace: str | None = None,
        llm_config_id: int = -24,
    ) -> OptimizerResult:
        """Generate optimized metadata suggestions for tools in a batch.

        Args:
            session: DB session for loading overrides.
            category: Tool category to optimize (e.g. "smhi", "scb").
            namespace: Namespace prefix to filter (e.g. "tools/weather").
            llm_config_id: LLM config ID (default -24 = Claude Sonnet).

        Returns:
            OptimizerResult with suggestions per tool.
        """
        # 1. Load tools
        tools = self._get_tools(category=category, namespace=namespace)
        if not tools:
            label = category or namespace or "unknown"
            return OptimizerResult(
                category=label,
                error=f"No tools found for category={category}, namespace={namespace}",
            )

        label = category or namespace or tools[0].category

        # 2. Load existing overrides to show current state
        current_overrides = await self._load_overrides(session)

        # 3. Build current metadata map
        current_meta = self._build_current_metadata(tools, current_overrides)

        # 4. Build prompt
        prompt = self._build_prompt(label, current_meta)

        # 5. Call LLM
        try:
            model_string, response_text = await self._call_llm(
                prompt, llm_config_id
            )
        except Exception as e:
            logger.error("Optimizer LLM call failed: %s", e)
            return OptimizerResult(
                category=label,
                total_tools=len(tools),
                error=str(e),
            )

        # 6. Parse response into suggestions
        suggestions = self._parse_response(response_text, current_meta)

        return OptimizerResult(
            category=label,
            total_tools=len(tools),
            suggestions=suggestions,
            model_used=model_string,
        )

    async def apply_suggestions(
        self,
        session: AsyncSession,
        suggestions: list[dict[str, Any]],
        *,
        user_id: Any = None,
    ) -> dict[str, Any]:
        """Apply approved suggestions as DB overrides.

        Args:
            session: DB session.
            suggestions: List of {tool_id, description, keywords, ...} dicts.
            user_id: User who approved.

        Returns:
            Summary of applied changes.
        """
        from app.services.tool_metadata_service import (
            normalize_tool_metadata_payload,
            upsert_global_tool_metadata_overrides,
        )

        # Build update tuples: (tool_id, payload | None)
        updates: list[tuple[str, dict[str, Any] | None]] = []
        for suggestion in suggestions:
            tool_id = suggestion.get("tool_id", "")
            if not tool_id:
                continue

            # Build override payload from suggestion
            payload: dict[str, Any] = {}
            for field_name in (
                "name",
                "description",
                "keywords",
                "example_queries",
                "category",
                "base_path",
                "main_identifier",
                "core_activity",
                "unique_scope",
                "geographic_scope",
                "excludes",
            ):
                if field_name in suggestion:
                    payload[field_name] = suggestion[field_name]

            if payload:
                # Merge with existing tool defaults so we don't lose fields
                tool = self._get_tool_by_id(tool_id)
                if tool:
                    defaults = {
                        "name": tool.name,
                        "description": tool.description,
                        "keywords": tool.keywords,
                        "example_queries": tool.example_queries,
                        "category": tool.category,
                        "geographic_scope": tool.geographic_scope,
                        "excludes": list(tool.excludes),
                    }
                    for k, v in defaults.items():
                        if k not in payload:
                            payload[k] = v

                updates.append((tool_id, normalize_tool_metadata_payload(payload)))

        if not updates:
            return {"applied": 0, "skipped": len(suggestions)}

        await upsert_global_tool_metadata_overrides(
            session, updates, updated_by_id=user_id
        )
        await session.commit()

        # Invalidate caches so NEXUS picks up changes
        invalidate_cache()
        try:
            from app.agents.new_chat.bigtool_store import clear_tool_caches

            clear_tool_caches()
        except (ImportError, AttributeError):
            pass

        return {"applied": len(updates), "skipped": len(suggestions) - len(updates)}

    # ----- Internal methods -----

    def _get_tools(
        self,
        *,
        category: str | None = None,
        namespace: str | None = None,
    ) -> list[PlatformTool]:
        """Get tools filtered by category or namespace."""
        tools = get_platform_tools()
        if category:
            tools = [t for t in tools if t.category == category]
        if namespace:
            tools = [
                t
                for t in tools
                if "/".join(t.namespace).startswith(namespace)
            ]
        return tools

    def _get_tool_by_id(self, tool_id: str) -> PlatformTool | None:
        for t in get_platform_tools():
            if t.tool_id == tool_id:
                return t
        return None

    async def _load_overrides(
        self, session: AsyncSession
    ) -> dict[str, dict[str, Any]]:
        """Load existing metadata overrides from DB."""
        from app.services.tool_metadata_service import (
            get_global_tool_metadata_overrides,
        )

        return await get_global_tool_metadata_overrides(session)

    def _build_current_metadata(
        self,
        tools: list[PlatformTool],
        overrides: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build current metadata list, merging defaults + overrides."""
        result: list[dict[str, Any]] = []
        for tool in tools:
            meta: dict[str, Any] = {
                "tool_id": tool.tool_id,
                "name": tool.name,
                "description": tool.description,
                "keywords": tool.keywords[:20],
                "example_queries": tool.example_queries[:10],
                "geographic_scope": tool.geographic_scope,
                "excludes": list(tool.excludes)[:15],
                "category": tool.category,
                "zone": tool.zone,
            }

            # Apply overrides if they exist
            override = overrides.get(tool.tool_id)
            if override:
                for key in (
                    "description",
                    "keywords",
                    "example_queries",
                    "geographic_scope",
                    "excludes",
                ):
                    val = override.get(key)
                    if val:
                        meta[key] = val

            result.append(meta)
        return result

    def _build_prompt(
        self, category: str, tools_meta: list[dict[str, Any]]
    ) -> str:
        """Build the LLM prompt."""
        # Compact JSON representation of tools
        tools_json = json.dumps(tools_meta, ensure_ascii=False, indent=2)

        return _USER_PROMPT_TEMPLATE.format(
            tool_count=len(tools_meta),
            category=category,
            tools_json=tools_json,
        )

    async def _call_llm(
        self, prompt: str, config_id: int
    ) -> tuple[str, str]:
        """Call LLM and return (model_string, response_text)."""
        from app.agents.new_chat.llm_config import (
            PROVIDER_MAP,
            load_llm_config_from_yaml,
        )

        config = load_llm_config_from_yaml(llm_config_id=config_id)
        if not config:
            raise RuntimeError(
                f"LLM config id={config_id} not found in global_llm_config.yaml"
            )

        # Build model string
        if config.get("custom_provider"):
            model_string = f"{config['custom_provider']}/{config['model_name']}"
        else:
            provider = config.get("provider", "").upper()
            prefix = PROVIDER_MAP.get(provider, provider.lower())
            model_string = f"{prefix}/{config['model_name']}"

        kwargs: dict[str, Any] = {
            "model": model_string,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }

        api_key = config.get("api_key", "")
        api_base = config.get("api_base", "")
        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            kwargs["api_base"] = api_base

        # Add litellm_params
        for key, value in config.get("litellm_params", {}).items():
            if key not in ("api_base",):
                kwargs[key] = value

        # Override temperature for more creative suggestions
        kwargs["temperature"] = kwargs.get("temperature", 0.7)

        logger.info(
            "Optimizer LLM call: model=%s, prompt_len=%d",
            model_string,
            len(prompt),
        )

        response = await litellm.acompletion(**kwargs)

        # Handle response — content may be string or list of content blocks
        raw_content = response.choices[0].message.content
        if isinstance(raw_content, list):
            # Extract text from content blocks (skip thinking blocks)
            text_parts = []
            for block in raw_content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)
        else:
            content = raw_content or ""

        logger.info("Optimizer LLM response: len=%d", len(content))
        return model_string, content

    def _parse_response(
        self,
        response_text: str,
        current_meta: list[dict[str, Any]],
    ) -> list[ToolSuggestion]:
        """Parse LLM response JSON into ToolSuggestion list."""
        # Build lookup for current metadata
        current_by_id = {m["tool_id"]: m for m in current_meta}

        text = response_text.strip()

        # Strategy 1: Extract from ```json ... ``` or ``` ... ``` blocks
        json_match = re.search(
            r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL
        )
        if json_match:
            text = json_match.group(1).strip()

        # Strategy 2: Find the outermost JSON array [ ... ]
        parsed = None
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(text)

        if parsed is None:
            # Try to locate the first '[' and last ']'
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(text[start : end + 1])

        if parsed is None:
            # Strategy 3: Find the first '{' and last '}'
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(text[start : end + 1])

        if parsed is None:
            logger.warning(
                "Failed to parse LLM response as JSON. First 500 chars: %s",
                response_text[:500],
            )
            return []

        if not isinstance(parsed, list):
            parsed = [parsed]

        suggestions: list[ToolSuggestion] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue

            tool_id = item.get("tool_id", "")
            if not tool_id or tool_id not in current_by_id:
                continue

            current = current_by_id[tool_id]

            # Determine which fields changed
            suggested: dict[str, Any] = {}
            changed: list[str] = []

            for field_name in (
                "description",
                "keywords",
                "example_queries",
                "excludes",
                "geographic_scope",
            ):
                if field_name in item:
                    new_val = item[field_name]
                    old_val = current.get(field_name)
                    suggested[field_name] = new_val
                    if new_val != old_val:
                        changed.append(field_name)

            if changed:
                suggestions.append(
                    ToolSuggestion(
                        tool_id=tool_id,
                        current=current,
                        suggested=suggested,
                        reasoning=item.get("reasoning", ""),
                        fields_changed=changed,
                    )
                )

        return suggestions

    def get_available_categories(self) -> list[str]:
        """Return all available tool categories."""
        return get_category_names()
