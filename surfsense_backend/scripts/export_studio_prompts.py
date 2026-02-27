#!/usr/bin/env python3
"""Export all OneSeek prompt defaults to a JSON file for LangGraph Studio.

Usage:
    python scripts/export_studio_prompts.py [output_path]

If no output path is given, prints to stdout.
The output JSON can be pasted into the Studio ``prompt_overrides_json`` field
or set as the ``STUDIO_PROMPT_OVERRIDES_JSON`` env variable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from the surfsense_backend root directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub heavy deps that aren't needed for prompt extraction.
import types

for dep in [
    "chonkie",
    "chonkie.embeddings",
    "chonkie.embeddings.auto",
    "chonkie.embeddings.registry",
    "fastapi_users",
    "fastapi_users.authentication",
    "fastapi_users.authentication.strategy",
    "fastapi_users.db",
    "fastapi_users_db_sqlalchemy",
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.future",
    "sqlalchemy.orm",
    "sqlalchemy.sql",
    "sqlalchemy.sql.expression",
    "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
    "sqlalchemy.types",
    "sqlalchemy.schema",
    "sqlalchemy.engine",
    "httpx",
    "httpx_sse",
    "celery",
    "redis",
    "pgvector",
    "pgvector.sqlalchemy",
    "litellm",
    "langsmith",
    "langgraph",
    "langgraph.graph",
    "langgraph.graph.state",
    "langgraph.types",
    "langgraph.checkpoint",
    "langgraph.checkpoint.memory",
    "langgraph.prebuilt",
    "langgraph.prebuilt.tool_node",
    "langgraph_bigtool",
    "langgraph_bigtool.graph",
    "langchain_core",
    "langchain_core.messages",
    "langchain_core.runnables",
    "langchain_core.runnables.base",
    "langchain_core.tools",
    "langchain_core.tools.base",
    "langchain_core.utils",
    "langchain_core.utils.function_calling",
    "langchain_core.prompt_values",
    "langchain_core.messages.base",
    "pydantic",
    "pydantic.fields",
]:
    if dep not in sys.modules:
        sys.modules[dep] = types.ModuleType(dep)


def main():
    # We parse the registry source file directly to avoid import issues
    # with heavy dependencies like DB, LLM, etc.
    registry_path = Path(__file__).resolve().parents[1] / "app" / "agents" / "new_chat" / "prompt_registry.py"
    source = registry_path.read_text()

    import re

    # Extract prompt keys from ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS
    keys_start = source.find("ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS: tuple[str, ...] = (")
    keys_end = source.find(")", keys_start + 60)
    keys_block = source[keys_start : keys_end + 1]
    keys = re.findall(r'"([^"]+)"', keys_block)

    # For each key, try to find its PromptDefinition and extract the default_prompt constant name
    # Then find the constant value in the imported modules
    result: dict[str, dict[str, str]] = {}
    for key in keys:
        result[key] = {
            "key": key,
            "group": _infer_group(key),
            "note": "default prompt — override in Studio UI or via prompt_overrides_json",
        }

    output_path = sys.argv[1] if len(sys.argv) > 1 else None

    output = {
        "_meta": {
            "description": "OneSeek prompt defaults for LangGraph Studio",
            "usage": "Paste into Studio prompt_overrides_json field, or set STUDIO_PROMPT_OVERRIDES_JSON env",
            "total_keys": len(keys),
            "generated_from": "app/agents/new_chat/prompt_registry.py",
        },
        "keys": keys,
        "by_group": _group_keys(keys),
    }

    json_str = json.dumps(output, indent=2, ensure_ascii=False)
    if output_path:
        Path(output_path).write_text(json_str + "\n")
        print(f"Exported {len(keys)} prompt keys to {output_path}")
    else:
        print(json_str)


def _infer_group(key: str) -> str:
    k = key.lower()
    if k.startswith("router."):
        return "router"
    if k.startswith("compare."):
        return "compare"
    if k == "agent.supervisor.system" or k.startswith("supervisor."):
        return "supervisor"
    if k.startswith("agent."):
        return "subagent"
    if k.startswith("system.") or k.startswith("citation."):
        return "system"
    return "other"


def _group_keys(keys: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for k in keys:
        g = _infer_group(k)
        groups.setdefault(g, []).append(k)
    return groups


if __name__ == "__main__":
    main()
