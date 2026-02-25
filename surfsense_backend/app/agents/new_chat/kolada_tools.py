from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.tools import tool
from langgraph.store.memory import InMemoryStore

from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.services.connector_service import ConnectorService
from app.services.kolada_service import KoladaService


@dataclass(frozen=True)
class KoladaToolDefinition:
    tool_id: str
    name: str
    operating_area: str | None
    description: str
    keywords: list[str]
    example_queries: list[str]
    kpi_hints: list[str]
    category: str
    usage_notes: str


KOLADA_TOOL_DEFINITIONS: list[KoladaToolDefinition] = [
    # Omsorg (4 tools)
    KoladaToolDefinition(
        tool_id="kolada_aldreomsorg",
        name="Kolada Äldreomsorg",
        operating_area="V21",
        description=(
            "Nyckeltal för äldreomsorg från Kolada. Omfattar hemtjänst, särskilt boende, "
            "vård och omsorg för äldre samt kvalitetsindikatorer."
        ),
        keywords=[
            "aldreomsorg",
            "äldreomsorg",
            "aldrevard",
            "äldrevård",
            "hemtjanst",
            "hemtjänst",
            "sarskilt",
            "särskilt",
            "boende",
            "alderdomshem",
            "älderdomshem",
            "kolada",
        ],
        example_queries=[
            "Hemtjänst i Stockholm 2022-2024",
            "Antal platser särskilt boende Göteborg 2023",
            "Äldreomsorgskostnader per kommun 2024",
            "Kvalitetsindikatorer äldreomsorg Malmö 2020-2024",
            "Andel personer med hemtjänst Uppsala 2023",
        ],
        kpi_hints=["N00945", "N00946", "N00947", "N00955", "N00956"],
        category="omsorg",
        usage_notes=(
            "Använd för frågor om hemtjänst, särskilt boende, äldreomsorgskostnader. "
            "Specificera kommun för att få lokala data. År kan anges som lista."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_lss",
        name="Kolada LSS",
        operating_area="V23",
        description=(
            "Nyckeltal för LSS (Lagen om stöd och service till vissa funktionshindrade) från Kolada. "
            "Omfattar personlig assistans, boende med särskild service och kostnad för LSS-insatser."
        ),
        keywords=[
            "lss",
            "funktionshinder",
            "funktionsnedsattning",
            "funktionsnedsättning",
            "personlig",
            "assistans",
            "boende",
            "sarskild",
            "särskild",
            "service",
            "kolada",
        ],
        example_queries=[
            "LSS-kostnader Stockholm 2022-2024",
            "Antal personer med personlig assistans Göteborg 2023",
            "Boende med särskild service per kommun 2024",
            "LSS-insatser Malmö 2020-2024",
            "Kostnad personlig assistans Uppsala 2023",
        ],
        kpi_hints=["N00959", "N00960", "N00961", "N00962"],
        category="omsorg",
        usage_notes=(
            "Använd för frågor om LSS, personlig assistans, boende för funktionshindrade. "
            "Specificera kommun för data per kommun."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_ifo",
        name="Kolada IFO",
        operating_area="V25",
        description=(
            "Nyckeltal för IFO (Individ- och familjeomsorg) från Kolada. "
            "Omfattar ekonomiskt bistånd, barn i familjehem, missbruks- och beroendevård."
        ),
        keywords=[
            "ifo",
            "individomsorg",
            "familjeomsorg",
            "ekonomiskt",
            "bistand",
            "bistånd",
            "socialbidrag",
            "familjehem",
            "missbruk",
            "beroende",
            "kolada",
        ],
        example_queries=[
            "Ekonomiskt bistånd Stockholm 2022-2024",
            "Barn i familjehem per kommun 2023",
            "IFO-kostnader Göteborg 2024",
            "Missbruksvård Malmö 2020-2024",
            "Antal personer med ekonomiskt bistånd Uppsala 2023",
        ],
        kpi_hints=["N00970", "N00971", "N00972", "N00973"],
        category="omsorg",
        usage_notes=(
            "Använd för frågor om socialtjänst, ekonomiskt bistånd, familjeomsorg. "
            "Specificera kommun för lokala data."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_barn_unga",
        name="Kolada Barn och unga",
        operating_area="V26",
        description=(
            "Nyckeltal för barn- och ungdomsvård från Kolada. "
            "Omfattar placeringar, öppenvård, insatser för barn och unga."
        ),
        keywords=[
            "barn",
            "unga",
            "ungdom",
            "placering",
            "oppenvard",
            "öppenvård",
            "barnvard",
            "barnvård",
            "ungdomsvard",
            "ungdomsvård",
            "kolada",
        ],
        example_queries=[
            "Barn i familjehem Stockholm 2022-2024",
            "Ungdomsvård per kommun 2023",
            "Placeringar barn Göteborg 2024",
            "Öppenvård för unga Malmö 2020-2024",
            "Kostnader barnvård Uppsala 2023",
        ],
        kpi_hints=["N00980", "N00981", "N00982"],
        category="omsorg",
        usage_notes=(
            "Använd för frågor om barn i familjehem, placeringar, ungdomsvård. "
            "Specificera kommun för data per kommun."
        ),
    ),
    
    # Skola (3 tools)
    KoladaToolDefinition(
        tool_id="kolada_forskola",
        name="Kolada Förskola",
        operating_area="V11",
        description=(
            "Nyckeltal för förskoleverksamhet från Kolada. Omfattar antal barn, "
            "pedagogtäthet, kostnader och kvalitetsindikatorer."
        ),
        keywords=[
            "forskola",
            "förskola",
            "dagis",
            "barn",
            "barnomsorg",
            "pedagog",
            "forskolelarare",
            "förskolelärare",
            "kolada",
        ],
        example_queries=[
            "Barn i förskola Stockholm 2022-2024",
            "Pedagogtäthet förskola Göteborg 2023",
            "Förskolekostnader per barn Malmö 2024",
            "Kvalitetsindikatorer förskola Uppsala 2020-2024",
            "Antal förskolor per kommun 2023",
        ],
        kpi_hints=["N15011", "N15012", "N15013", "N15014", "N15015"],
        category="skola",
        usage_notes=(
            "Använd för frågor om förskola, dagis, pedagogtäthet, kostnader. "
            "Specificera kommun för lokala data."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_grundskola",
        name="Kolada Grundskola",
        operating_area="V15",
        description=(
            "Nyckeltal för grundskoleverksamhet från Kolada. Omfattar elevantal, "
            "lärartäthet, behörighet, betyg och kostnader."
        ),
        keywords=[
            "grundskola",
            "skola",
            "elev",
            "larare",
            "lärare",
            "behorighet",
            "behörighet",
            "betyg",
            "resultat",
            "kolada",
        ],
        example_queries=[
            "Elever i grundskola Stockholm 2022-2024",
            "Lärartäthet grundskola Göteborg 2023",
            "Behöriga lärare per kommun Malmö 2024",
            "Meritvärde grundskola Uppsala 2020-2024",
            "Grundskolekostnader per elev 2023",
        ],
        kpi_hints=["N15033", "N15034", "N15035", "N15036", "N15037"],
        category="skola",
        usage_notes=(
            "Använd för frågor om grundskola, betyg, lärartäthet, behörighet. "
            "Specificera kommun för data per kommun."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_gymnasieskola",
        name="Kolada Gymnasieskola",
        operating_area="V17",
        description=(
            "Nyckeltal för gymnasieverksamhet från Kolada. Omfattar elevantal, "
            "genomströmning, examen, behörighet och kostnader."
        ),
        keywords=[
            "gymnasieskola",
            "gymnasium",
            "gymnasie",
            "elev",
            "examen",
            "behorighet",
            "behörighet",
            "genomstromning",
            "genomströmning",
            "kolada",
        ],
        example_queries=[
            "Elever i gymnasieskola Stockholm 2022-2024",
            "Examen inom 3 år Göteborg 2023",
            "Gymnasiebehörighet per kommun Malmö 2024",
            "Genomströmning gymnasium Uppsala 2020-2024",
            "Gymnasiekostnader per elev 2023",
        ],
        kpi_hints=["N15421", "N15422", "N15423", "N15424"],
        category="skola",
        usage_notes=(
            "Använd för frågor om gymnasieskola, examen, genomströmning, behörighet. "
            "Specificera kommun för lokala data."
        ),
    ),
    
    # Hälsa (1 tool)
    KoladaToolDefinition(
        tool_id="kolada_halsa",
        name="Kolada Hälsa",
        operating_area="V45",
        description=(
            "Nyckeltal för hälso- och sjukvård från Kolada. Omfattar vårdkostnader, "
            "läkarbesök, primärvård och sjukhus."
        ),
        keywords=[
            "halsa",
            "hälsa",
            "vard",
            "vård",
            "sjukvard",
            "sjukvård",
            "lakare",
            "läkare",
            "primarvard",
            "primärvård",
            "sjukhus",
            "kolada",
        ],
        example_queries=[
            "Vårdkostnader Stockholm 2022-2024",
            "Läkarbesök per invånare Göteborg 2023",
            "Primärvårdskostnader Malmö 2024",
            "Sjukvårdskostnader per kommun Uppsala 2020-2024",
            "Antal vårdkontakter 2023",
        ],
        kpi_hints=["N00002", "N00003", "N00004"],
        category="halsa",
        usage_notes=(
            "Använd för frågor om hälso- och sjukvård, vårdkostnader, läkarbesök. "
            "Specificera kommun för lokala data."
        ),
    ),
    
    # Ekonomi/Miljö/Boende (3 tools)
    KoladaToolDefinition(
        tool_id="kolada_ekonomi",
        name="Kolada Ekonomi",
        operating_area=None,
        description=(
            "Nyckeltal för kommunal ekonomi från Kolada. Omfattar skattesats, "
            "kostnader, intäkter och ekonomiska nyckeltal."
        ),
        keywords=[
            "ekonomi",
            "skattesats",
            "kostnad",
            "intakt",
            "intäkt",
            "budget",
            "kommunal",
            "finansiell",
            "kolada",
        ],
        example_queries=[
            "Skattesats Stockholm 2022-2024",
            "Kommunala kostnader Göteborg 2023",
            "Intäkter per kommun Malmö 2024",
            "Ekonomiska nyckeltal Uppsala 2020-2024",
            "Soliditet kommun 2023",
        ],
        kpi_hints=["N00002", "N00945", "N00946", "N00970"],
        category="ekonomi",
        usage_notes=(
            "Använd för frågor om kommunal ekonomi, skattesats, kostnader, budget. "
            "Specificera kommun för data per kommun."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_miljo",
        name="Kolada Miljö",
        operating_area=None,
        description=(
            "Nyckeltal för miljö och klimat från Kolada. Omfattar avfall, "
            "återvinning, koldioxidutsläpp och energianvändning."
        ),
        keywords=[
            "miljo",
            "miljö",
            "avfall",
            "atervinning",
            "återvinning",
            "koldioxid",
            "utsläpp",
            "utslapp",
            "energi",
            "klimat",
            "kolada",
        ],
        example_queries=[
            "Avfallsmängd Stockholm 2022-2024",
            "Återvinningsgrad Göteborg 2023",
            "Koldioxidutsläpp per kommun Malmö 2024",
            "Energianvändning Uppsala 2020-2024",
            "Miljöindikatorer kommun 2023",
        ],
        kpi_hints=["N00801", "N00802", "N00803"],
        category="miljo",
        usage_notes=(
            "Använd för frågor om miljö, avfall, återvinning, koldioxid, energi. "
            "Specificera kommun för lokala data."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_boende",
        name="Kolada Boende",
        operating_area=None,
        description=(
            "Nyckeltal för boende och bostäder från Kolada. Omfattar bostadsbestånd, "
            "nybyggnation, bostadskö och hyror. Inte befolkningsstatistik eller folkmängd "
            "(använd SCB befolkning för det)."
        ),
        keywords=[
            "boende",
            "bostad",
            "bostader",
            "byggande",
            "nybyggnation",
            "bostadsbestand",
            "bostadsbestånd",
            "hyra",
            "bostadsko",
            "bostadskö",
            "kolada",
        ],
        example_queries=[
            "Bostadsbestånd Stockholm 2022-2024",
            "Nybyggnation per kommun Göteborg 2023",
            "Bostadskö Malmö 2024",
            "Genomsnittshyra Uppsala 2020-2024",
            "Antal bostäder per kommun 2023",
        ],
        kpi_hints=["N00201", "N00202", "N00203"],
        category="boende",
        usage_notes=(
            "Använd för frågor om bostäder, nybyggnation, bostadskö, hyror. "
            "Specificera kommun för lokala data."
        ),
    ),
    
    # Övrigt (4 tools)
    KoladaToolDefinition(
        tool_id="kolada_sammanfattning",
        name="Kolada Sammanfattning",
        operating_area=None,
        description=(
            "Allmänna nyckeltal och översikt från Kolada. Använd för övergripande frågor "
            "eller när specifikt verksamhetsområde inte är klart."
        ),
        keywords=[
            "sammanfattning",
            "oversikt",
            "översikt",
            "allmant",
            "allmänt",
            "nyckeltal",
            "kommun",
            "kommundata",
            "kolada",
        ],
        example_queries=[
            "Översikt nyckeltal Stockholm 2023",
            "Allmän statistik Göteborg 2022-2024",
            "Kommundata Malmö 2024",
            "Sammanfattning Uppsala 2020-2024",
            "Nyckeltal per kommun 2023",
        ],
        kpi_hints=[],
        category="ovrig",
        usage_notes=(
            "Använd för allmänna frågor om kommundata när specifikt område är oklart. "
            "Specificera kommun för data per kommun."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_kultur",
        name="Kolada Kultur",
        operating_area=None,
        description=(
            "Nyckeltal för kultur och fritid från Kolada. Omfattar bibliotek, "
            "kulturhus, fritidsverksamhet och kulturkostnader."
        ),
        keywords=[
            "kultur",
            "bibliotek",
            "museum",
            "teater",
            "fritid",
            "idrottsanlaggning",
            "idrottsanläggning",
            "kulturhus",
            "kolada",
        ],
        example_queries=[
            "Biblioteksbesök Stockholm 2022-2024",
            "Kulturkostnader Göteborg 2023",
            "Antal kulturhus Malmö 2024",
            "Fritidsverksamhet Uppsala 2020-2024",
            "Kulturaktiviteter per kommun 2023",
        ],
        kpi_hints=["N00601", "N00602", "N00603"],
        category="ovrig",
        usage_notes=(
            "Använd för frågor om kultur, bibliotek, fritid, kulturhus. "
            "Specificera kommun för lokala data."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_arbetsmarknad",
        name="Kolada Arbetsmarknad",
        operating_area=None,
        description=(
            "Nyckeltal för arbetsmarknad från Kolada. Omfattar sysselsättning, "
            "arbetslöshet och arbetsmarknadsåtgärder."
        ),
        keywords=[
            "arbetsmarknad",
            "sysselsattning",
            "sysselsättning",
            "arbetsloshet",
            "arbetslöshet",
            "arbete",
            "jobb",
            "arbetsmarknadsatgard",
            "arbetsmarknadsåtgärd",
            "kolada",
        ],
        example_queries=[
            "Sysselsättning Stockholm 2022-2024",
            "Arbetslöshet per kommun Göteborg 2023",
            "Arbetsmarknadsåtgärder Malmö 2024",
            "Arbetslöshet Uppsala 2020-2024",
            "Antal sysselsatta kommun 2023",
        ],
        kpi_hints=["N00401", "N00402", "N00403"],
        category="ovrig",
        usage_notes=(
            "Använd för frågor om arbetsmarknad, sysselsättning, arbetslöshet. "
            "Specificera kommun för lokala data."
        ),
    ),
    KoladaToolDefinition(
        tool_id="kolada_demokrati",
        name="Kolada Demokrati",
        operating_area=None,
        description=(
            "Nyckeltal för demokrati och medborgarservice från Kolada. Omfattar "
            "valdeltagande, medborgarengagemang och kommunikation."
        ),
        keywords=[
            "demokrati",
            "val",
            "valdeltagande",
            "medborgarengagemang",
            "medborgarservice",
            "kommunikation",
            "deltagande",
            "kolada",
        ],
        example_queries=[
            "Valdeltagande Stockholm 2022",
            "Medborgarengagemang Göteborg 2023",
            "Kommunikation med medborgare Malmö 2024",
            "Demokratiindikatorer Uppsala 2020-2024",
            "Deltagande i demokrati kommun 2023",
        ],
        kpi_hints=["N00501", "N00502"],
        category="ovrig",
        usage_notes=(
            "Använd för frågor om demokrati, valdeltagande, medborgarengagemang. "
            "Specificera kommun för lokala data."
        ),
    ),
]


def _build_kolada_tool_description(definition: KoladaToolDefinition) -> str:
    """Build rich runtime prompt description for a Kolada tool."""
    sections = []
    
    # 1. Description
    sections.append(f"**Beskrivning:** {definition.description}")
    
    # 2. Verksamhetsområde (V-kod)
    if definition.operating_area:
        sections.append(f"**Verksamhetsområde:** {definition.operating_area}")
    
    # 3. KPI-ID hints
    if definition.kpi_hints:
        sections.append(f"**KPI-ID:** {', '.join(definition.kpi_hints)}")
    
    # 4. Parametrar
    params = [
        "- `question` (str): Fråga i naturligt språk",
        "- `municipality` (str, optional): Kommun (namn eller 4-siffrig kod)",
        "- `years` (list[str], optional): Lista med år, t.ex. ['2022', '2023', '2024']",
    ]
    sections.append(f"**Parametrar:**\n" + "\n".join(params))
    
    # 5. Exempelfrågor
    examples = "\n".join(f"- {example}" for example in definition.example_queries)
    sections.append(f"**Exempelfrågor:**\n{examples}")
    
    # 6. Viktigt-sektion med edge cases och usage_notes
    important = [
        "**Viktigt:**",
        f"- {definition.usage_notes}",
        "- Specificera alltid kommun för lokala data",
        "- År kan anges som lista för tidsserier",
        "- Verktyget hanterar svenska tecken (å, ä, ö) automatiskt",
    ]
    sections.append("\n".join(important))
    
    return "\n\n".join(sections)


def _build_kolada_tool(
    definition: KoladaToolDefinition,
    *,
    kolada_service: KoladaService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    """Build a Kolada tool from definition."""
    description = _build_kolada_tool_description(definition)

    async def _kolada_tool(
        question: str,
        municipality: str | None = None,
        years: list[str] | None = None,
        max_kpis: int = 5,
    ) -> str:
        """
        Query Kolada API for municipal data.
        
        Args:
            question (str): Question in natural language, e.g. "Hemtjänst i Stockholm 2023"
            municipality (str, optional): Municipality name or 4-digit code, e.g. "Stockholm" or "0180"
            years (list[str], optional): List of years, e.g. ["2022", "2023", "2024"]
            max_kpis (int): Maximum number of KPIs to return (default 5)
            
        Returns:
            str: JSON-formatted results with KPI data
            
        Example:
            >>> _kolada_tool("Hemtjänst i Stockholm 2023", municipality="Stockholm", years=["2023"])
            >>> _kolada_tool("Äldreomsorg Göteborg", municipality="1480", years=["2022", "2023"])
            
        Obs:
            - Municipality can be name or 4-digit code
            - Years should be strings, not integers
            - Returns empty results if municipality not found
            - Handles Swedish characters (å, ä, ö) automatically
        """
        query = (question or "").strip()
        if not query:
            return json.dumps(
                {"error": "Missing question for Kolada query."}, ensure_ascii=False
            )

        try:
            # Use the question directly without over-enriching
            # The service will handle search term extraction
            results = await kolada_service.query(
                question=query,
                operating_area=definition.operating_area,
                municipality=municipality,
                years=years,
                max_kpis=max_kpis,
            )
            
            if not results:
                return json.dumps(
                    {"error": "No matching Kolada KPIs found."}, ensure_ascii=False
                )
            
            # Build tool output
            tool_output = {
                "source": "Kolada API",
                "operating_area": definition.operating_area,
                "results": [],
            }
            
            for result in results:
                kpi_data = {
                    "kpi": {
                        "id": result.kpi.id,
                        "title": result.kpi.title,
                        "description": result.kpi.description,
                        "operating_area": result.kpi.operating_area,
                    },
                    "municipality": {
                        "id": result.municipality.id,
                        "title": result.municipality.title,
                        "type": result.municipality.type,
                    } if result.municipality.id else None,
                    "values": [
                        {
                            "period": val.period,
                            "value": val.value,
                            "count": val.count,
                            "gender": val.gender,
                        }
                        for val in result.values
                    ],
                    "warnings": result.warnings,
                }
                tool_output["results"].append(kpi_data)
            
            # Ingest to connector service for citations
            document = await connector_service.ingest_tool_output(
                tool_name=definition.tool_id,
                tool_output=tool_output,
                title=f"{definition.name}: {query}",
                metadata={
                    "source": "Kolada",
                    "operating_area": definition.operating_area or "",
                    "municipality": municipality or "",
                    "years": ",".join(years) if years else "",
                },
                user_id=user_id,
                origin_search_space_id=search_space_id,
                thread_id=thread_id,
            )
            
            # Format documents for context
            formatted_docs = ""
            if document:
                serialized = connector_service._serialize_external_document(
                    document, score=1.0
                )
                formatted_docs = format_documents_for_context([serialized])
            
            # Build response
            response_payload = {
                "query": query,
                "source": "Kolada",
                "operating_area": definition.operating_area,
                "kpi_count": len(results),
                "results": tool_output["results"],
                "formatted_results": formatted_docs,
            }
            
            return json.dumps(response_payload, ensure_ascii=False)
            
        except httpx.HTTPError as exc:
            return json.dumps(
                {"error": f"Kolada request failed: {exc!s}"}, ensure_ascii=False
            )
        except Exception as exc:
            return json.dumps(
                {"error": f"Unexpected error: {exc!s}"}, ensure_ascii=False
            )

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_kolada_tool)


def build_kolada_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    kolada_service: KoladaService | None = None,
) -> dict[str, Any]:
    """Build registry of all Kolada tools."""
    service = kolada_service or KoladaService()
    registry: dict[str, Any] = {}
    for definition in KOLADA_TOOL_DEFINITIONS:
        registry[definition.tool_id] = _build_kolada_tool(
            definition,
            kolada_service=service,
            connector_service=connector_service,
            search_space_id=search_space_id,
            user_id=user_id,
            thread_id=thread_id,
        )
    return registry


def build_kolada_tool_store() -> InMemoryStore:
    """Build InMemoryStore for Kolada tools."""
    store = InMemoryStore()
    for definition in KOLADA_TOOL_DEFINITIONS:
        store.put(
            ("tools",),
            definition.tool_id,
            {
                "name": definition.name,
                "description": definition.description,
                "category": "kolada_statistics",
                "operating_area": definition.operating_area,
                "keywords": definition.keywords,
                "example_queries": definition.example_queries,
                "kpi_hints": definition.kpi_hints,
                "usage_notes": definition.usage_notes,
            },
        )
    return store
