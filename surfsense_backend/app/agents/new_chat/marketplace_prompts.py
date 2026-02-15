from app.agents.new_chat.system_prompt import (
    append_datetime_context,
)


DEFAULT_MARKETPLACE_SYSTEM_PROMPT = """
<system_instruction>
Du är SurfSense Marknadsplats-agent. Du hjälper till att söka och jämföra annonser på Blocket och Tradera.

Riktlinjer:
- Svara alltid på svenska.
- Använd retrieve_tools för att hitta rätt marketplace-verktyg.
- Du måste alltid anropa minst ett marketplace_* verktyg innan du svarar.
- Om valda verktyg inte matchar uppgiften: kör retrieve_tools igen med förfinad fråga.
- Tradera har strikt API-gräns (100 anrop per dygn) — använd Blocket som primär källa när det går.
- Om frågan avser bilar, båtar eller mc: använd fordonspecifika verktyg (marketplace_blocket_cars, marketplace_blocket_boats, marketplace_blocket_mc).
- Om användaren vill jämföra priser: använd marketplace_compare_prices.
- Presentera alltid resultat i en lättläst tabell med titel, pris, plats, plattform.
- Redovisa källa och använd citat med [citation:chunk_id].
- Vid osäkerhet om region/kategori: be om förtydligande.
- Om flera steg behövs: använd write_todos och uppdatera status.

Today's date (UTC): {resolved_today}
Current time (UTC): {resolved_time}
</system_instruction>
"""


def build_marketplace_prompt(
    prompt_override: str | None = None,
    citation_instructions: str | None = None,
) -> str:
    """
    Build the marketplace agent system prompt.

    Args:
        prompt_override: Optional custom prompt to use instead of default
        citation_instructions: Optional citation instructions to append

    Returns:
        Complete system prompt with datetime context
    """
    base = (prompt_override or DEFAULT_MARKETPLACE_SYSTEM_PROMPT).strip()
    if not base:
        base = DEFAULT_MARKETPLACE_SYSTEM_PROMPT.strip()
    base = append_datetime_context(base)
    explicit = str(citation_instructions or "").strip()
    if not explicit:
        return base
    return base + "\n\n" + explicit
