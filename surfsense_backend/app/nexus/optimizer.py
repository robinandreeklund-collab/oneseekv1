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
# Shared helper: resolve agent_id → domain_id
# ---------------------------------------------------------------------------


async def _build_agent_domain_map(session: Any) -> dict[str, str]:
    """Build a mapping from agent_id to domain_id.

    Checks three sources in order:
      1. DB agent_definitions table (highest priority)
      2. Effective agent metadata (registry or hardcoded)
      3. Seed defaults from agent_definitions.py
    """
    from app.seeds.agent_definitions import get_default_agent_definitions

    mapping: dict[str, str] = {}

    # 1. Seed defaults
    for agent_id, defn in get_default_agent_definitions().items():
        did = defn.get("domain_id", "")
        if did:
            mapping[agent_id] = did

    # 2. Effective agent metadata (includes registry + overrides)
    try:
        from app.services.agent_metadata_service import get_effective_agent_metadata

        for agent in await get_effective_agent_metadata(session):
            agent_id = agent.get("agent_id", "")
            if not agent_id:
                continue
            # Metadata format uses routes=[domain_id] from registry
            routes = agent.get("routes", [])
            did = routes[0] if routes else agent.get("domain_id", "")
            if did:
                mapping[agent_id] = did
    except Exception:
        pass

    # 3. DB agent_definitions (most authoritative)
    try:
        from sqlalchemy.future import select

        from app.db import DomainAgentDefinition

        result = await session.execute(select(DomainAgentDefinition))
        for row in result.scalars():
            if row.agent_id and row.domain_id:
                mapping[row.agent_id] = row.domain_id
    except Exception:
        pass

    return mapping


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
            model_string, response_text = await self._call_llm(prompt, llm_config_id)
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
            tools = [t for t in tools if "/".join(t.namespace).startswith(namespace)]
        return tools

    def _get_tool_by_id(self, tool_id: str) -> PlatformTool | None:
        for t in get_platform_tools():
            if t.tool_id == tool_id:
                return t
        return None

    async def _load_overrides(self, session: AsyncSession) -> dict[str, dict[str, Any]]:
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

    def _build_prompt(self, category: str, tools_meta: list[dict[str, Any]]) -> str:
        """Build the LLM prompt."""
        # Compact JSON representation of tools
        tools_json = json.dumps(tools_meta, ensure_ascii=False, indent=2)

        return _USER_PROMPT_TEMPLATE.format(
            tool_count=len(tools_meta),
            category=category,
            tools_json=tools_json,
        )

    async def _call_llm(self, prompt: str, config_id: int) -> tuple[str, str]:
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
            "max_tokens": 32768,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }

        api_key = config.get("api_key", "")
        api_base = config.get("api_base", "")
        provider = config.get("provider", "")
        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            from app.services.llm_service import _sanitize_api_base_for_provider

            sanitized = _sanitize_api_base_for_provider(api_base, provider)
            if sanitized:
                kwargs["api_base"] = sanitized

        # Add litellm_params (but never let global config override our max_tokens)
        for key, value in config.get("litellm_params", {}).items():
            if key not in ("api_base", "max_tokens"):
                kwargs[key] = value

        # Lower temperature for consistent, well-structured JSON output
        kwargs["temperature"] = 0.3

        # Reset global litellm.api_base to prevent cross-provider pollution
        # — ChatLiteLLM mutates it globally, so a previous provider's base
        # URL can leak into this direct acompletion call.
        litellm.api_base = None

        logger.info(
            "Optimizer LLM call: model=%s, prompt_len=%d",
            model_string,
            len(prompt),
        )

        response = await litellm.acompletion(**kwargs)

        finish_reason = getattr(response.choices[0], "finish_reason", None)
        if finish_reason and finish_reason != "stop":
            logger.warning(
                "Optimizer LLM response truncated (finish_reason=%s). "
                "Consider increasing max_tokens.",
                finish_reason,
            )

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

        # Strategy 1: Strip markdown code fences if present
        if text.startswith("```"):
            # Remove opening fence (```json or ```)
            first_nl = text.find("\n")
            if first_nl != -1:
                # Remove closing fence
                if text.endswith("```"):
                    text = text[first_nl + 1 : -3].strip()
                else:
                    text = text[first_nl + 1 :].strip()

        # Strategy 2: Try direct JSON parse
        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.debug(
                "Direct JSON parse failed: %s. Trying bracket extraction.", exc
            )

        # Strategy 3: Find the outermost JSON array [ ... ]
        if parsed is None:
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except json.JSONDecodeError as exc:
                    logger.debug("Array extraction failed: %s", exc)

        # Strategy 4: Find the first '{' and last '}'
        if parsed is None:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(text[start : end + 1])

        if parsed is None:
            logger.warning(
                "Failed to parse LLM response as JSON. Full response:\n%s",
                response_text,
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


# ---------------------------------------------------------------------------
# Intent Layer Optimizer
# ---------------------------------------------------------------------------

_INTENT_LAYER_SYSTEM_PROMPT = """\
Du är en expert på information retrieval, intent-klassificering och embedding-optimering.
Din uppgift är att optimera metadata för hela intent-lagret i ett AI-routing-system.

Intent-lagret består av:
1. DOMÄNER — 17 domäner som fångar olika ämnesområden (väder, trafik, ekonomi, etc.)
2. AGENTER — 13 agenter som äger specifika verktyg inom varje domän

REGLER FÖR DOMÄNER:
- Varje domäns keywords MÅSTE vara unika och tydligt skilja sig från andra domäners keywords
- Description ska vara specifik nog att skilja domänen från närliggande domäner
- Excludes ska lista domäner/termer som INTE ska matcha denna domän
- Keywords används för word-boundary matching i svenska frågor
- Undvik överlappande keywords mellan domäner (t.ex. "kommun" i bara EN domän)

REGLER FÖR AGENTER:
- Varje agents keywords MÅSTE vara unika inom sin domän och gentemot andra domäners agenter
- Description ska tydligt separera agenten från andra agenter i samma domän
- Excludes ska förhindra felrouting till denna agent
- main_identifier, core_activity och unique_scope bör vara maximalt distinkta

VIKTIGT:
- Tänk på att keywords matchas med \\b word-boundary regex
- Flerteckens-keywords (t.ex. "lediga jobb") matchas som substring
- Domänkeywords triggar zon-routing, agentkeywords triggar agent-routing inom zonen
- Svara ENBART med valid JSON. Ingen markdown utanför JSON."""

_INTENT_LAYER_USER_TEMPLATE = """\
Här är hela intent-lagret med {domain_count} domäner och {agent_count} agenter.
Optimera metadata så att varje domän och agent blir maximalt separerade.

DOMÄNER:
{domains_json}

AGENTER:
{agents_json}

Svara med en JSON-objekt med två nycklar:
{{
  "domains": [
    {{
      "domain_id": "...",
      "description": "optimerad description",
      "keywords": ["lista", "av", "keywords"],
      "excludes": ["termer som INTE ska matcha"],
      "main_identifier": "...",
      "core_activity": "...",
      "unique_scope": "...",
      "reasoning": "kort motivering"
    }}
  ],
  "agents": [
    {{
      "agent_id": "...",
      "description": "optimerad description",
      "keywords": ["lista", "av", "keywords"],
      "excludes": ["termer som INTE ska matcha"],
      "main_identifier": "...",
      "core_activity": "...",
      "unique_scope": "...",
      "reasoning": "kort motivering"
    }}
  ]
}}

Returnera exakt {domain_count} domäner och {agent_count} agenter."""


@dataclass
class IntentLayerSuggestion:
    """A single domain or agent suggestion."""

    item_id: str
    item_type: str  # "domain" | "agent"
    current: dict[str, Any]
    suggested: dict[str, Any]
    reasoning: str = ""
    fields_changed: list[str] = field(default_factory=list)


@dataclass
class IntentLayerResult:
    """Result from an intent layer optimizer run."""

    total_domains: int = 0
    total_agents: int = 0
    suggestions: list[IntentLayerSuggestion] = field(default_factory=list)
    model_used: str = ""
    error: str | None = None


class IntentLayerOptimizer:
    """LLM-powered optimizer for the entire intent layer (domains + agents)."""

    async def generate_suggestions(
        self,
        session: AsyncSession,
        *,
        llm_config_id: int = -24,
    ) -> IntentLayerResult:
        """Generate optimized metadata for all domains and agents."""
        from app.services.agent_metadata_service import get_effective_agent_metadata
        from app.services.intent_domain_service import get_effective_intent_domains

        # 1. Load current domains and agents
        domains = await get_effective_intent_domains(session)
        agents = await get_effective_agent_metadata(session)

        if not domains and not agents:
            return IntentLayerResult(error="No domains or agents found")

        # 2. Build current metadata summaries (stripped of non-optimizable fields)
        domain_meta = self._build_domain_meta(domains)
        agent_meta = self._build_agent_meta(agents)

        # 3. Build prompt
        prompt = _INTENT_LAYER_USER_TEMPLATE.format(
            domain_count=len(domain_meta),
            agent_count=len(agent_meta),
            domains_json=json.dumps(domain_meta, ensure_ascii=False, indent=2),
            agents_json=json.dumps(agent_meta, ensure_ascii=False, indent=2),
        )

        # 4. Call LLM with intent layer system prompt
        try:
            model_string, response_text = await self._call_llm_with_system(
                _INTENT_LAYER_SYSTEM_PROMPT, prompt, llm_config_id
            )
        except Exception as e:
            logger.error("Intent layer optimizer LLM call failed: %s", e)
            return IntentLayerResult(
                total_domains=len(domains),
                total_agents=len(agents),
                error=str(e),
            )

        # 5. Parse response
        suggestions = self._parse_response(response_text, domain_meta, agent_meta)

        return IntentLayerResult(
            total_domains=len(domains),
            total_agents=len(agents),
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
        """Apply approved intent layer suggestions to DB."""
        from app.services.agent_definition_service import upsert_agent
        from app.services.agent_metadata_service import (
            get_effective_agent_metadata,
            upsert_global_agent_metadata_overrides,
        )
        from app.services.intent_domain_service import upsert_intent_domain
        from app.services.registry_events import (
            bump_registry_version,
            notify_registry_changed,
        )

        # Pre-build agent→domain_id lookup so we can inject domain_id into
        # payloads that only carry the changed metadata fields.
        agent_domain_map = await _build_agent_domain_map(session)

        domain_count = 0
        agent_count = 0

        for item in suggestions:
            item_type = item.get("item_type", "")
            item_id = item.get("item_id", "")
            if not item_id:
                continue

            if item_type == "domain":
                await upsert_intent_domain(
                    session,
                    domain_id=item_id,
                    payload=item,
                    updated_by_id=user_id,
                )
                domain_count += 1

            elif item_type == "agent":
                # Ensure domain_id is present — the optimizer only sends
                # changed fields so it's typically missing.
                if not item.get("domain_id"):
                    resolved = agent_domain_map.get(item_id, "")
                    if not resolved:
                        logger.warning(
                            "Intent apply: skipping agent %s — cannot resolve domain_id",
                            item_id,
                        )
                        continue
                    item["domain_id"] = resolved

                await upsert_agent(
                    session,
                    agent_id=item_id,
                    payload=item,
                    updated_by_id=user_id,
                )
                await upsert_global_agent_metadata_overrides(
                    session,
                    [(item_id, item)],
                    updated_by_id=user_id,
                )
                agent_count += 1

        if domain_count or agent_count:
            new_version = await bump_registry_version(session)
            await session.commit()
            await notify_registry_changed(session, new_version)
            # Invalidate caches
            invalidate_cache()
            try:
                from app.agents.new_chat.bigtool_store import clear_tool_caches

                clear_tool_caches()
            except (ImportError, AttributeError):
                pass

        return {
            "applied_domains": domain_count,
            "applied_agents": agent_count,
            "skipped": len(suggestions) - domain_count - agent_count,
        }

    # ----- Internal methods -----

    def _build_domain_meta(self, domains: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for d in domains:
            result.append(
                {
                    "domain_id": d.get("domain_id", ""),
                    "label": d.get("label", ""),
                    "description": d.get("description", ""),
                    "keywords": d.get("keywords", [])[:30],
                    "excludes": d.get("excludes", [])[:15],
                    "main_identifier": d.get("main_identifier", ""),
                    "core_activity": d.get("core_activity", ""),
                    "unique_scope": d.get("unique_scope", ""),
                    "geographic_scope": d.get("geographic_scope", ""),
                }
            )
        return result

    def _build_agent_meta(self, agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for a in agents:
            routes = a.get("routes", [])
            result.append(
                {
                    "agent_id": a.get("agent_id", ""),
                    "label": a.get("label", ""),
                    "description": a.get("description", ""),
                    "domain_id": routes[0] if routes else "",
                    "keywords": a.get("keywords", [])[:30],
                    "excludes": a.get("excludes", [])[:15],
                    "main_identifier": a.get("main_identifier", ""),
                    "core_activity": a.get("core_activity", ""),
                    "unique_scope": a.get("unique_scope", ""),
                    "geographic_scope": a.get("geographic_scope", ""),
                }
            )
        return result

    async def _call_llm_with_system(
        self, system_prompt: str, user_prompt: str, config_id: int
    ) -> tuple[str, str]:
        """Call LLM with custom system prompt."""
        from app.agents.new_chat.llm_config import (
            PROVIDER_MAP,
            load_llm_config_from_yaml,
        )

        config = load_llm_config_from_yaml(llm_config_id=config_id)
        if not config:
            raise RuntimeError(
                f"LLM config id={config_id} not found in global_llm_config.yaml"
            )

        if config.get("custom_provider"):
            model_string = f"{config['custom_provider']}/{config['model_name']}"
        else:
            provider = config.get("provider", "").upper()
            prefix = PROVIDER_MAP.get(provider, provider.lower())
            model_string = f"{prefix}/{config['model_name']}"

        kwargs: dict[str, Any] = {
            "model": model_string,
            "max_tokens": 32768,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        api_key = config.get("api_key", "")
        api_base = config.get("api_base", "")
        provider = config.get("provider", "")
        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            from app.services.llm_service import _sanitize_api_base_for_provider

            sanitized = _sanitize_api_base_for_provider(api_base, provider)
            if sanitized:
                kwargs["api_base"] = sanitized

        for key, value in config.get("litellm_params", {}).items():
            if key not in ("api_base", "max_tokens"):
                kwargs[key] = value

        kwargs["temperature"] = 0.3

        # Reset global litellm.api_base to prevent cross-provider pollution
        litellm.api_base = None

        logger.info(
            "Intent layer optimizer LLM call: model=%s, prompt_len=%d",
            model_string,
            len(user_prompt),
        )

        response = await litellm.acompletion(**kwargs)

        raw_content = response.choices[0].message.content
        if isinstance(raw_content, list):
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

        return model_string, content

    def _parse_response(
        self,
        response_text: str,
        domain_meta: list[dict[str, Any]],
        agent_meta: list[dict[str, Any]],
    ) -> list[IntentLayerSuggestion]:
        """Parse LLM response into suggestions list."""
        domain_by_id = {d["domain_id"]: d for d in domain_meta}
        agent_by_id = {a["agent_id"]: a for a in agent_meta}

        text = response_text.strip()

        # Strip markdown fences
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl != -1:
                if text.endswith("```"):
                    text = text[first_nl + 1 : -3].strip()
                else:
                    text = text[first_nl + 1 :].strip()

        parsed = None
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(text)

        if parsed is None:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(text[start : end + 1])

        if parsed is None or not isinstance(parsed, dict):
            logger.warning("Failed to parse intent layer response as JSON")
            return []

        suggestions: list[IntentLayerSuggestion] = []

        # Parse domain suggestions
        for item in parsed.get("domains", []):
            if not isinstance(item, dict):
                continue
            domain_id = item.get("domain_id", "")
            if domain_id not in domain_by_id:
                continue
            current = domain_by_id[domain_id]
            suggested, changed = self._diff_fields(current, item)
            if changed:
                suggestions.append(
                    IntentLayerSuggestion(
                        item_id=domain_id,
                        item_type="domain",
                        current=current,
                        suggested=suggested,
                        reasoning=item.get("reasoning", ""),
                        fields_changed=changed,
                    )
                )

        # Parse agent suggestions
        for item in parsed.get("agents", []):
            if not isinstance(item, dict):
                continue
            agent_id = item.get("agent_id", "")
            if agent_id not in agent_by_id:
                continue
            current = agent_by_id[agent_id]
            suggested, changed = self._diff_fields(current, item)
            if changed:
                suggestions.append(
                    IntentLayerSuggestion(
                        item_id=agent_id,
                        item_type="agent",
                        current=current,
                        suggested=suggested,
                        reasoning=item.get("reasoning", ""),
                        fields_changed=changed,
                    )
                )

        return suggestions

    def _diff_fields(
        self, current: dict[str, Any], item: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        """Compare current and suggested metadata, return (suggested, changed_fields)."""
        suggested: dict[str, Any] = {}
        changed: list[str] = []
        for field_name in (
            "description",
            "keywords",
            "excludes",
            "main_identifier",
            "core_activity",
            "unique_scope",
        ):
            if field_name in item:
                new_val = item[field_name]
                old_val = current.get(field_name)
                suggested[field_name] = new_val
                if new_val != old_val:
                    changed.append(field_name)
        return suggested, changed


# ---------------------------------------------------------------------------
# Domain-Scoped Agent Optimizer
# ---------------------------------------------------------------------------

_DOMAIN_AGENT_SYSTEM_PROMPT = """\
Du är en expert på information retrieval, embedding-optimering och agent-routing.
Din uppgift är att optimera metadata för alla agenter inom EN specifik domän,
så att de skiljer sig maximalt från varandra i embedding-rymden.

KONTEXT:
Varje domän (t.ex. "Trafik & Transport") kan ha flera agenter som hanterar
olika delaspekter. När en fråga routas till domänen väljs EN agent baserat på
embedding-likhet mot agentens metadata. Om agenterna har överlappande keywords
eller liknande descriptions hamnar de för nära varandra → felrouting.

REGLER:
- Keywords MÅSTE vara unika per agent — ingen keyword får förekomma i flera agenter
- Description ska tydligt skilja agenterna: vad den gör OCH vad den INTE gör
- main_identifier ska vara en kort, unik etikett (t.ex. "Tågtrafik-agent")
- core_activity ska beskriva agentens HUVUDfunktion i en mening
- unique_scope ska förklara vad som skiljer just denna agent från de andra
- excludes ska lista termer/ämnen som INTE ska matcha denna agent
  (typiskt: termer som tillhör en systeragent)
- Tänk på svenska sammansatta ord: "tågförseningar" bör matcha tåg-agenten,
  "vägarbeten" bör matcha väg-agenten
- Keyword-matchning använder \\b word-boundary regex, men substringsmatchning
  finns också (≥4 tecken) — undvik korta generiska termer

STRATEGI:
1. Identifiera överlapp mellan agenterna
2. Flytta överlappande keywords till den mest lämpliga agenten
3. Lägg till excludes som pekar bort trafik från fel agent
4. Gör descriptions mer specifika — undvik vaga formuleringar
5. Kontrollera att main_identifier och core_activity är unika per agent

Svara ENBART med valid JSON. Ingen markdown utanför JSON."""

_DOMAIN_AGENT_USER_TEMPLATE = """\
Domän: {domain_label} (domain_id: {domain_id})
Beskrivning: {domain_description}

Denna domän har {agent_count} agenter som behöver optimeras:

{agents_json}

Optimera metadata för alla {agent_count} agenter så de skiljer sig maximalt.

Svara med en JSON-objekt:
{{
  "agents": [
    {{
      "agent_id": "...",
      "description": "optimerad description",
      "keywords": ["lista", "av", "keywords"],
      "excludes": ["termer som INTE ska matcha"],
      "main_identifier": "...",
      "core_activity": "...",
      "unique_scope": "...",
      "reasoning": "kort motivering av ändringar"
    }}
  ]
}}

Returnera exakt {agent_count} agenter."""


class DomainAgentOptimizer:
    """LLM-powered optimizer for agents within a single domain."""

    async def generate_suggestions(
        self,
        session: AsyncSession,
        domain_id: str,
        *,
        llm_config_id: int = -24,
    ) -> IntentLayerResult:
        """Generate optimized metadata for agents in a specific domain."""
        from app.services.agent_metadata_service import get_effective_agent_metadata
        from app.services.intent_domain_service import get_effective_intent_domains

        domains = await get_effective_intent_domains(session)
        agents = await get_effective_agent_metadata(session)

        # Find the target domain
        domain_meta = None
        for d in domains:
            if d.get("domain_id") == domain_id:
                domain_meta = d
                break

        if not domain_meta:
            return IntentLayerResult(error=f"Domän '{domain_id}' hittades inte")

        # Filter agents belonging to this domain
        domain_agents = [
            a
            for a in agents
            if domain_id in (a.get("routes") or [])
        ]

        if not domain_agents:
            return IntentLayerResult(
                error=f"Inga agenter hittade för domän '{domain_id}'"
            )

        # Build metadata for LLM
        agent_meta = self._build_agent_meta(domain_agents)

        # Build prompt
        prompt = _DOMAIN_AGENT_USER_TEMPLATE.format(
            domain_id=domain_id,
            domain_label=domain_meta.get("label", domain_id),
            domain_description=domain_meta.get("description", ""),
            agent_count=len(agent_meta),
            agents_json=json.dumps(agent_meta, ensure_ascii=False, indent=2),
        )

        # Call LLM
        try:
            model_string, response_text = await self._call_llm(
                _DOMAIN_AGENT_SYSTEM_PROMPT, prompt, llm_config_id
            )
        except Exception as e:
            logger.error("Domain agent optimizer LLM call failed: %s", e)
            return IntentLayerResult(
                total_agents=len(domain_agents),
                error=str(e),
            )

        # Parse response
        suggestions = self._parse_response(response_text, agent_meta)

        return IntentLayerResult(
            total_domains=1,
            total_agents=len(domain_agents),
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
        """Apply approved agent suggestions to DB."""
        from app.services.agent_definition_service import upsert_agent
        from app.services.agent_metadata_service import (
            upsert_global_agent_metadata_overrides,
        )
        from app.services.registry_events import (
            bump_registry_version,
            notify_registry_changed,
        )

        # Pre-build agent→domain_id lookup so we can inject domain_id into
        # payloads that only carry the changed metadata fields.
        agent_domain_map = await _build_agent_domain_map(session)

        agent_count = 0
        for item in suggestions:
            item_id = item.get("item_id", "")
            if not item_id:
                continue

            # Ensure domain_id is present — the optimizer only sends
            # changed fields so it's typically missing.
            if not item.get("domain_id"):
                resolved = agent_domain_map.get(item_id, "")
                if not resolved:
                    logger.warning(
                        "Domain agent apply: skipping agent %s — cannot resolve domain_id",
                        item_id,
                    )
                    continue
                item["domain_id"] = resolved

            await upsert_agent(
                session,
                agent_id=item_id,
                payload=item,
                updated_by_id=user_id,
            )
            await upsert_global_agent_metadata_overrides(
                session,
                [(item_id, item)],
                updated_by_id=user_id,
            )
            agent_count += 1

        if agent_count:
            new_version = await bump_registry_version(session)
            await session.commit()
            await notify_registry_changed(session, new_version)
            invalidate_cache()
            try:
                from app.agents.new_chat.bigtool_store import clear_tool_caches

                clear_tool_caches()
            except (ImportError, AttributeError):
                pass

        return {"applied_domains": 0, "applied_agents": agent_count, "skipped": 0}

    def _build_agent_meta(
        self, agents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        result = []
        for a in agents:
            result.append(
                {
                    "agent_id": a.get("agent_id", ""),
                    "label": a.get("label", ""),
                    "description": a.get("description", ""),
                    "keywords": a.get("keywords", [])[:40],
                    "excludes": a.get("excludes", [])[:15],
                    "main_identifier": a.get("main_identifier", ""),
                    "core_activity": a.get("core_activity", ""),
                    "unique_scope": a.get("unique_scope", ""),
                    "geographic_scope": a.get("geographic_scope", ""),
                }
            )
        return result

    async def _call_llm(
        self, system_prompt: str, user_prompt: str, config_id: int
    ) -> tuple[str, str]:
        """Call LLM — delegates to IntentLayerOptimizer's method."""
        optimizer = IntentLayerOptimizer()
        return await optimizer._call_llm_with_system(
            system_prompt, user_prompt, config_id
        )

    def _parse_response(
        self,
        response_text: str,
        agent_meta: list[dict[str, Any]],
    ) -> list[IntentLayerSuggestion]:
        """Parse LLM response into agent suggestions."""
        agent_by_id = {a["agent_id"]: a for a in agent_meta}

        text = response_text.strip()
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl != -1:
                text = (
                    text[first_nl + 1 : -3].strip()
                    if text.endswith("```")
                    else text[first_nl + 1 :].strip()
                )

        parsed = None
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(text)

        if parsed is None:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(text[start : end + 1])

        if parsed is None or not isinstance(parsed, dict):
            logger.warning("Failed to parse domain agent response as JSON")
            return []

        suggestions: list[IntentLayerSuggestion] = []
        for item in parsed.get("agents", []):
            if not isinstance(item, dict):
                continue
            agent_id = item.get("agent_id", "")
            if agent_id not in agent_by_id:
                continue
            current = agent_by_id[agent_id]
            suggested, changed = self._diff_fields(current, item)
            if changed:
                suggestions.append(
                    IntentLayerSuggestion(
                        item_id=agent_id,
                        item_type="agent",
                        current=current,
                        suggested=suggested,
                        reasoning=item.get("reasoning", ""),
                        fields_changed=changed,
                    )
                )

        return suggestions

    def _diff_fields(
        self, current: dict[str, Any], item: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        suggested: dict[str, Any] = {}
        changed: list[str] = []
        for field_name in (
            "description",
            "keywords",
            "excludes",
            "main_identifier",
            "core_activity",
            "unique_scope",
        ):
            if field_name in item:
                new_val = item[field_name]
                old_val = current.get(field_name)
                suggested[field_name] = new_val
                if new_val != old_val:
                    changed.append(field_name)
        return suggested, changed
