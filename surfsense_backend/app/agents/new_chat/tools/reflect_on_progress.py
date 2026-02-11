from langchain_core.tools import tool


def create_reflect_on_progress_tool():
    @tool
    def reflect_on_progress(thoughts: str) -> dict:
        """Log a brief reflection on progress, gaps, and next steps."""
        cleaned = (thoughts or "").strip()
        return {"status": "logged", "reflection": cleaned}

    return reflect_on_progress
