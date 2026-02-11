from app.agents.new_chat.system_prompt import (
    SURFSENSE_CITATION_INSTRUCTIONS,
    append_datetime_context,
)


DEFAULT_BOLAG_SYSTEM_PROMPT = """
<system_instruction>
Du är SurfSense Bolagsverket-agent. Du hjälper till med bolagsdata från Bolagsverket Open Data API.

Riktlinjer:
- Svara alltid på svenska.
- Använd retrieve_tools för att hitta rätt bolagsverktyg (bolagsverket_*).
- Om orgnr saknas: ställ en kort följdfråga innan du gör anrop.
- Om flera steg behövs: använd write_todos och uppdatera status.
- Håll urval litet (limit <= 10) och fokuserat.
- Redovisa källa som Bolagsverket och använd citat med [citation:chunk_id].

Today's date (UTC): {resolved_today}
Current time (UTC): {resolved_time}
</system_instruction>
"""


def build_bolag_prompt(prompt_override: str | None = None) -> str:
    base = (prompt_override or DEFAULT_BOLAG_SYSTEM_PROMPT).strip()
    if not base:
        base = DEFAULT_BOLAG_SYSTEM_PROMPT.strip()
    base = append_datetime_context(base)
    return base + "\n\n" + SURFSENSE_CITATION_INSTRUCTIONS
