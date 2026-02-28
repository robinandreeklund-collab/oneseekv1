from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_REGISTRY_PATH = PROJECT_ROOT / "app/agents/new_chat/prompt_registry.py"


def _extract_template_keys_from_registry() -> tuple[str, ...]:
    text = PROMPT_REGISTRY_PATH.read_text(encoding="utf-8")
    block_match = re.search(
        r"ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS\s*:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\((.*?)\)\n\n",
        text,
        flags=re.DOTALL,
    )
    if not block_match:
        raise AssertionError("Could not locate ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS block")
    block = block_match.group(1)
    return tuple(
        match.group(1)
        for match in re.finditer(r'"([^"]+)"', block)
        if str(match.group(1) or "").strip()
    )


def _extract_definition_map_keys_from_registry() -> set[str]:
    text = PROMPT_REGISTRY_PATH.read_text(encoding="utf-8")
    block_match = re.search(
        r"_PROMPT_DEFINITIONS_BY_KEY\s*:\s*dict\[str,\s*PromptDefinition\]\s*=\s*\{(.*?)\}\n\n",
        text,
        flags=re.DOTALL,
    )
    if not block_match:
        raise AssertionError("Could not locate _PROMPT_DEFINITIONS_BY_KEY block")
    block = block_match.group(1)
    return {
        match.group(1)
        for match in re.finditer(r'"([^"]+)"\s*:\s*PromptDefinition\(', block)
        if str(match.group(1) or "").strip()
    }


def _extract_resolve_prompt_keys(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    # Match: resolve_prompt(..., "prompt.key",
    pattern = re.compile(r'resolve_prompt\(\s*[^,]+,\s*"([^"]+)"', re.MULTILINE)
    return {match.group(1).strip() for match in pattern.finditer(text)}


def test_prompt_definitions_match_oneseek_template_exactly() -> None:
    template_keys = _extract_template_keys_from_registry()
    definition_map_keys = _extract_definition_map_keys_from_registry()
    assert len(template_keys) == 61
    assert len(set(template_keys)) == 61
    assert definition_map_keys == set(template_keys)


def test_runtime_resolve_prompt_keys_are_covered_by_template() -> None:
    runtime_files = [
        PROJECT_ROOT / "app/agents/new_chat/supervisor_agent.py",
        PROJECT_ROOT / "app/tasks/chat/stream_new_chat.py",
        PROJECT_ROOT / "app/langgraph_studio.py",
        PROJECT_ROOT / "app/tasks/chat/stream_compare_chat.py",
        PROJECT_ROOT / "app/routes/public_global_chat_routes.py",
    ]
    runtime_keys: set[str] = set()
    for file_path in runtime_files:
        runtime_keys |= _extract_resolve_prompt_keys(file_path)
    template_keys = set(_extract_template_keys_from_registry())
    assert runtime_keys <= template_keys


def test_legacy_prompt_keys_removed_from_template() -> None:
    template_keys = set(_extract_template_keys_from_registry())
    legacy_keys = {
        "router.knowledge",
        "router.action",
        "agent.knowledge.docs",
        "agent.knowledge.internal",
        "agent.knowledge.external",
        "agent.action.web",
        "agent.action.media",
        "agent.action.travel",
        "agent.action.data",
    }
    assert template_keys.isdisjoint(legacy_keys)

