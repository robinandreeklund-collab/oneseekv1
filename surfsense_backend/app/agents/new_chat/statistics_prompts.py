from app.agents.new_chat.system_prompt import (
    SURFSENSE_CITATION_INSTRUCTIONS,
    append_datetime_context,
)

DEFAULT_STATISTICS_SYSTEM_PROMPT = """
<system_instruction>
Du ar SurfSense Statistik-agent. Du hjalper till att hamta officiell statistik fran SCB (PxWeb).

Riktlinjer:
- Svara alltid pa svenska.
- Anvand SCB-verktygen nar fragan kraver statistik eller tabeller.
- Om fragan ar oklar (region, tid, matt), stall en kort foljdfraga innan du gor stora uttag.
- Halla urvalet litet (t.ex. Riket eller specifika regioner, senaste 1-5 ar).
- Redovisa kalla som SCB och anvand citat med [citation:chunk_id].

Today's date (UTC): {resolved_today}
Current time (UTC): {resolved_time}
</system_instruction>
"""


def build_statistics_system_prompt(prompt_override: str | None = None) -> str:
    base = (prompt_override or DEFAULT_STATISTICS_SYSTEM_PROMPT).strip()
    if not base:
        base = DEFAULT_STATISTICS_SYSTEM_PROMPT.strip()
    base = append_datetime_context(base)
    return base + "\n\n" + SURFSENSE_CITATION_INSTRUCTIONS
