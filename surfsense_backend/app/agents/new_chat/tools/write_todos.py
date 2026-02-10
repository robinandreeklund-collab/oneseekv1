from typing import Any

from langchain_core.tools import tool


def create_write_todos_tool():
    @tool
    def write_todos(todos: list[dict[str, Any]]) -> dict[str, Any]:
        """Create or update a short todo list for multi-step work."""
        safe_todos: list[dict[str, Any]] = []
        for todo in todos or []:
            if not isinstance(todo, dict):
                continue
            content = str(todo.get("content") or "").strip()
            status = str(todo.get("status") or "pending").strip().lower()
            if not content:
                continue
            safe_todos.append({"content": content, "status": status})
        return {"todos": safe_todos}

    return write_todos
