from __future__ import annotations

import json
from dataclasses import dataclass
import re
from typing import Any

import httpx
from langchain_core.tools import tool
from langgraph.store.memory import InMemoryStore
from langgraph.types import Checkpointer
from langgraph_bigtool import create_agent as create_bigtool_agent
from langgraph_bigtool.graph import ToolNode as BigtoolToolNode
from langgraph.prebuilt.tool_node import ToolRuntime

from app.agents.new_chat.tools.knowledge_base import format_documents_for_context
from app.services.connector_service import ConnectorService
from app.services.scb_service import SCB_BASE_URL, ScbService


@dataclass(frozen=True)
class ScbToolDefinition:
    tool_id: str
    name: str
    base_path: str
    description: str
    keywords: list[str]
    example_queries: list[str]
    table_codes: list[str]
    typical_filters: list[str]


SCB_TOOL_DEFINITIONS: list[ScbToolDefinition] = [
    ScbToolDefinition(
        tool_id="scb_arbetsmarknad",
        name="SCB Arbetsmarknad",
        base_path="AM/",
        description=(
            "Arbetsmarknadsstatistik fran SCB. Omfattar sysselsattning, "
            "arbetsloshet, arbetskraftsdeltagande och loner."
        ),
        keywords=[
            "arbetsmarknad",
            "arbetsloshet",
            "sysselsattning",
            "arbetstid",
            "lon",
        ],
        example_queries=[
            "Arbetsloshet Sverige 2018-2024",
            "Sysselsattning kvinnor 2023",
            "Arbetsloshet per lan 2024",
            "Arbetskraftsdeltagande 2015-2024",
            "Lonestatistik per sektor 2022",
        ],
        table_codes=["AM7001", "AM0211", "AM0301", "AM0401", "AM0403"],
        typical_filters=["tid", "region", "kon", "alder", "naring"],
    ),
    ScbToolDefinition(
        tool_id="scb_befolkning",
        name="SCB Befolkning",
        base_path="BE/",
        description=(
            "Befolkningsstatistik fran SCB. Omfattar folkmangd, flyttningar, "
            "fodelser, dodsfall, alder, kon och region."
        ),
        keywords=[
            "befolkning",
            "folkmangd",
            "flytt",
            "migration",
            "fodd",
            "dod",
            "alder",
            "kon",
        ],
        example_queries=[
            "Befolkning i Stockholms lan 2024",
            "Folkmangd Sverige 2015-2024",
            "Flyttnetto per lan 2020-2024",
            "Fodda och dodda i Skane 2015-2024",
            "Aldersfordelning i Goteborg 2023",
        ],
        table_codes=["BE0001", "BE0101", "BE0205", "BE0401", "BE0701"],
        typical_filters=["tid", "region", "kon", "alder", "civilstand"],
    ),
    ScbToolDefinition(
        tool_id="scb_boende_byggande",
        name="SCB Boende, byggande och bebyggelse",
        base_path="BO/",
        description=(
            "Statistik om boende, byggande och bostader fran SCB. "
            "Omfattar bostadsbestand, nybyggnation och bygglov."
        ),
        keywords=[
            "boende",
            "bostad",
            "byggande",
            "bygglov",
            "bostadsbestand",
        ],
        example_queries=[
            "Antal fardigstallda bostader 2015-2024",
            "Nybyggnation per lan 2020-2024",
            "Bygglov bostader 2018-2024",
            "Bostadsbestand per kommun 2024",
            "Antal bostader i Stockholm 2010-2024",
        ],
        table_codes=["BO0101", "BO0104", "BO0201", "BO0301", "BO0303"],
        typical_filters=["tid", "region", "bostadstyp", "upplatelseform"],
    ),
    ScbToolDefinition(
        tool_id="scb_demokrati",
        name="SCB Demokrati",
        base_path="ME/",
        description=(
            "Demokrati- och valdeltagandestatistik fran SCB. "
            "Omfattar val, deltagande och fortroendeindikatorer."
        ),
        keywords=[
            "demokrati",
            "val",
            "valdeltagande",
            "parti",
            "fortroende",
        ],
        example_queries=[
            "Valdeltagande i riksdagsval 2022",
            "Valresultat per lan 2022",
            "Partisympatier 2010-2024",
            "Fortroende for institutioner 2015-2024",
            "Politisk aktivitet per alder 2023",
        ],
        table_codes=["ME0001", "ME0002", "ME0104", "ME0105", "ME0107"],
        typical_filters=["tid", "region", "alder", "kon", "parti"],
    ),
    ScbToolDefinition(
        tool_id="scb_energi",
        name="SCB Energi",
        base_path="EN/",
        description=(
            "Energistatistik fran SCB. Omfattar energianvandning, produktion "
            "och branslen."
        ),
        keywords=[
            "energi",
            "el",
            "bransle",
            "produktion",
            "forbrukning",
        ],
        example_queries=[
            "Energianvandning per sektor 2015-2024",
            "Elproduktion Sverige 2010-2024",
            "Forbrukning av branslen per lan 2023",
            "Slutlig energianvandning per bransch 2022",
            "Fornybar energi andel 2010-2024",
        ],
        table_codes=["EN0105", "EN0106", "EN0107", "EN0108", "EN0109"],
        typical_filters=["tid", "region", "energislag", "sektor"],
    ),
    ScbToolDefinition(
        tool_id="scb_finansmarknad",
        name="SCB Finansmarknad",
        base_path="FM/",
        description=(
            "Finansmarknadsstatistik fran SCB. Omfattar rantor, "
            "utlaning, insattningar och finansiella tillgangar."
        ),
        keywords=[
            "finans",
            "ranta",
            "utlaning",
            "insattning",
            "bank",
        ],
        example_queries=[
            "Rantor pa bostadslan 2015-2024",
            "Utlanning till hushall per ar",
            "Insattningar hushall 2010-2024",
            "Finansiella tillgangar per sektor 2022",
            "Kreditvolymer 2018-2024",
        ],
        table_codes=["FM0001", "FM0002", "FM0103", "FM0105", "FM0201"],
        typical_filters=["tid", "sektor", "instrument", "region"],
    ),
    ScbToolDefinition(
        tool_id="scb_handel",
        name="SCB Handel med varor och tjanster",
        base_path="HA/",
        description=(
            "Handelsstatistik fran SCB. Omfattar import, export, handelsbalans "
            "och tjanstehandel."
        ),
        keywords=[
            "handel",
            "import",
            "export",
            "handelsbalans",
            "tjanster",
        ],
        example_queries=[
            "Export per varugrupp 2023",
            "Import per land 2018-2024",
            "Handelsbalans Sverige 2010-2024",
            "Tjanstehandel per land 2022",
            "Export av tjanster per sektor 2023",
        ],
        table_codes=["HA0101", "HA0103", "HA0104", "HA0201", "HA0202"],
        typical_filters=["tid", "land", "varugrupp", "tjanstekategori"],
    ),
    ScbToolDefinition(
        tool_id="scb_hushall",
        name="SCB Hushallens ekonomi",
        base_path="HE/",
        description=(
            "Statistik om hushallens ekonomi fran SCB. Omfattar inkomster, "
            "utgifter, konsumtion och sparande."
        ),
        keywords=[
            "hushall",
            "inkomst",
            "utgift",
            "konsumtion",
            "sparande",
        ],
        example_queries=[
            "Disponibel inkomst per hushall 2015-2024",
            "Hushallens skulder 2010-2024",
            "Sparande per hushallstyp 2023",
            "Konsumtionsutgifter per kategori 2022",
            "Inkomstmedian per lan 2024",
        ],
        table_codes=["HE0000", "HE0103", "HE0104", "HE0110", "HE0111"],
        typical_filters=["tid", "region", "hushallstyp", "inkomstslag"],
    ),
    ScbToolDefinition(
        tool_id="scb_halsa_sjukvard",
        name="SCB Halso- och sjukvard",
        base_path="HS/",
        description=(
            "Halso- och sjukvardsstatistik fran SCB. Omfattar patientstatistik, "
            "halsa och sjukvard."
        ),
        keywords=[
            "halsa",
            "sjukvard",
            "patient",
            "vard",
        ],
        example_queries=[
            "Patientstatistik per lan 2024",
            "Sjukhusvard per region 2022",
            "Varddagar per kon 2023",
            "Vardkontakter per alder 2024",
            "Diagnoser per ar 2015-2024",
        ],
        table_codes=["HS0301"],
        typical_filters=["tid", "region", "kon", "alder", "diagnos"],
    ),
    ScbToolDefinition(
        tool_id="scb_jordbruk",
        name="SCB Jord- och skogsbruk, fiske",
        base_path="JO/",
        description=(
            "Jordbruks-, skogsbruks- och fiskestatistik fran SCB. "
            "Omfattar arealer, produktion och lantbruk."
        ),
        keywords=[
            "jordbruk",
            "skogsbruk",
            "fiske",
            "lantbruk",
            "areal",
        ],
        example_queries=[
            "Areal jordbruksmark per lan 2023",
            "Antal jordbruksforetag 2010-2024",
            "Fiskefangster per art 2022",
            "Skogsareal per region 2024",
            "Antal djur pa lantbruk 2023",
        ],
        table_codes=["JO1104", "JO0106", "JO0103", "JO0204", "JO0202"],
        typical_filters=["tid", "region", "produktionstyp", "djur", "areal"],
    ),
    ScbToolDefinition(
        tool_id="scb_kultur",
        name="SCB Kultur och fritid",
        base_path="KU/",
        description=(
            "Kultur- och fritidsstatistik fran SCB. Omfattar bibliotek, museer, "
            "kulturvanor och fritidsdeltagande."
        ),
        keywords=[
            "kultur",
            "fritid",
            "bibliotek",
            "museer",
            "idrott",
        ],
        example_queries=[
            "Biblioteksbesok per lan 2015-2024",
            "Museibesok Sverige 2022",
            "Kulturvanor per alder 2023",
            "Idrottsdeltagande per region 2024",
            "Kulturella evenemang per kommun 2023",
        ],
        table_codes=["KU0401", "KU0402", "KU0105"],
        typical_filters=["tid", "region", "alder", "aktivitet"],
    ),
    ScbToolDefinition(
        tool_id="scb_levnadsforhallanden",
        name="SCB Levnadsforhallanden",
        base_path="LE/",
        description=(
            "Levnadsforhallanden och livsvillkor fran SCB. Omfattar trygghet, "
            "boendemiljo och vardagsvillkor."
        ),
        keywords=[
            "levnadsforhallanden",
            "livsvillkor",
            "trygghet",
            "boendemiljo",
            "livskvalitet",
        ],
        example_queries=[
            "Levnadsforhallanden per lan 2024",
            "Trygghet i bostadsomrade 2023",
            "Livskvalitet per alder 2022",
            "Tid for obetalt arbete 2018-2024",
            "Hinder i vardagen 2023",
        ],
        table_codes=["LE0101", "LE0102", "LE0105", "LE0106", "LE0108"],
        typical_filters=["tid", "region", "alder", "kon", "bakgrund"],
    ),
    ScbToolDefinition(
        tool_id="scb_miljo",
        name="SCB Miljo",
        base_path="MI/",
        description=(
            "Miljostatistik fran SCB. Omfattar utslapp, energi och miljopaverkan."
        ),
        keywords=[
            "miljo",
            "utslapp",
            "co2",
            "energi",
            "klimat",
        ],
        example_queries=[
            "CO2-utslapp Sverige 2010-2024",
            "Utslapp per sektor 2020-2024",
            "Energianvandning per sektor 2015-2024",
            "Fornybar energi andel 2010-2024",
            "Utslapp per lan 2023",
        ],
        table_codes=["MI0106", "MI0107", "MI0108", "MI0305", "MI0307"],
        typical_filters=["tid", "region", "sektor", "miljokategori"],
    ),
    ScbToolDefinition(
        tool_id="scb_nationalrakenskaper",
        name="SCB Nationalrakenskaper",
        base_path="NR/",
        description=(
            "Nationalrakenskaper fran SCB. Omfattar BNP, tillvaxt, "
            "offentliga finanser och makroekonomi."
        ),
        keywords=[
            "bnp",
            "tillvaxt",
            "nationalrakenskaper",
            "ekonomi",
            "makro",
        ],
        example_queries=[
            "BNP Sverige 2010-2024",
            "BNP per capita 2015-2024",
            "Tillvaxt per ar 2015-2024",
            "Offentlig konsumtion 2010-2024",
            "Fasta investeringar 2012-2024",
        ],
        table_codes=["NR0001", "NR0101", "NR0103", "NR0105", "NR0109"],
        typical_filters=["tid", "sektor", "transaktion"],
    ),
    ScbToolDefinition(
        tool_id="scb_naringsverksamhet",
        name="SCB Naringsverksamhet",
        base_path="NV/",
        description=(
            "Naringslivs- och foretagsstatistik fran SCB. Omfattar foretagsstruktur, "
            "branscher och omsattning."
        ),
        keywords=[
            "foretag",
            "naringsliv",
            "bransch",
            "omsattning",
            "foretagsstruktur",
        ],
        example_queries=[
            "Antal foretag per bransch 2023",
            "Foretagsstruktur i Sverige 2015-2024",
            "Omsattning i industrin 2018-2024",
            "Nyregistrerade foretag per lan 2024",
            "Foretag efter storleksklass 2020-2024",
        ],
        table_codes=["NV0006", "NV0101", "NV0103", "NV0109", "NV0116"],
        typical_filters=["tid", "region", "bransch", "storlek"],
    ),
    ScbToolDefinition(
        tool_id="scb_offentlig_ekonomi",
        name="SCB Offentlig ekonomi",
        base_path="OE/",
        description=(
            "Statistik om offentlig ekonomi fran SCB. Omfattar skatteintakter, "
            "kommunal ekonomi och offentliga utgifter."
        ),
        keywords=[
            "offentlig",
            "kommunal",
            "skatt",
            "utgift",
            "inkomst",
        ],
        example_queries=[
            "Kommunala kostnader per invanare 2023",
            "Skatteintakter per lan 2010-2024",
            "Offentliga utgifter per sektor 2022",
            "Kommunal ekonomi resultat 2024",
            "Statliga utgifter 2015-2024",
        ],
        table_codes=["OE0101", "OE0106", "OE0107", "OE0108", "OE0111"],
        typical_filters=["tid", "region", "sektor", "intaktstyp"],
    ),
    ScbToolDefinition(
        tool_id="scb_priser_konsumtion",
        name="SCB Priser och konsumtion",
        base_path="PR/",
        description=(
            "Pris- och konsumtionsstatistik fran SCB. Omfattar KPI, inflation "
            "och konsumtionsindex."
        ),
        keywords=[
            "kpi",
            "inflation",
            "priser",
            "konsumtion",
        ],
        example_queries=[
            "KPI Sverige 2010-2024",
            "Inflation 2021-2024",
            "KPI per manad senaste 24 manaderna",
            "Konsumentprisindex for boende 2018-2024",
            "Prisniva for livsmedel 2015-2024",
        ],
        table_codes=["PR0101", "PR0301", "PR0501", "PR0502"],
        typical_filters=["tid", "varukategori", "region"],
    ),
    ScbToolDefinition(
        tool_id="scb_socialtjanst",
        name="SCB Socialtjanst",
        base_path="SO/",
        description=(
            "Socialtjanststatistik fran SCB. Omfattar ekonomiskt bistand, "
            "insatser och social omsorg."
        ),
        keywords=[
            "socialtjanst",
            "ekonomiskt bistand",
            "forsorjningsstod",
            "omsorg",
            "insatser",
        ],
        example_queries=[
            "Ekonomiskt bistand per lan 2015-2024",
            "Socialtjanstinsatser for barn 2023",
            "Forsorjningsstod per kommun 2024",
            "Antal barn i familjehem 2010-2024",
            "Social omsorg per alder 2023",
        ],
        table_codes=["SO0203"],
        typical_filters=["tid", "region", "alder", "insatstyp"],
    ),
    ScbToolDefinition(
        tool_id="scb_transporter",
        name="SCB Transporter och kommunikationer",
        base_path="TK/",
        description=(
            "Transport- och kommunikationsstatistik fran SCB. "
            "Omfattar resor, trafik och gods."
        ),
        keywords=[
            "transport",
            "trafik",
            "resor",
            "gods",
            "kommunikation",
        ],
        example_queries=[
            "Resor med kollektivtrafik 2015-2024",
            "Godstransporter Sverige 2010-2024",
            "Persontransporter per trafikslag 2018-2024",
            "Transportarbete per region 2022-2024",
            "Antal registrerade bilar per lan 2024",
        ],
        table_codes=["TK1001", "TK1201"],
        typical_filters=["tid", "region", "trafikslag", "fordonstyp"],
    ),
    ScbToolDefinition(
        tool_id="scb_utbildning",
        name="SCB Utbildning och forskning",
        base_path="UF/",
        description=(
            "Utbildnings- och forskningsstatistik fran SCB. "
            "Omfattar skolresultat, examen, hogskola och forskning."
        ),
        keywords=[
            "utbildning",
            "skola",
            "examen",
            "hogskola",
            "forskning",
        ],
        example_queries=[
            "Gymnasieexamen per lan 2022",
            "Andel med eftergymnasial utbildning 2010-2024",
            "Hogskoleutbildade kvinnor vs man 2023",
            "Antal studenter i hogskolan 2015-2024",
            "Forskningsutgifter i Sverige 2018-2024",
        ],
        table_codes=["UF0104", "UF0117", "UF0202", "UF0205", "UF0301"],
        typical_filters=["tid", "region", "kon", "alder", "utbildningsniva"],
    ),
    ScbToolDefinition(
        tool_id="scb_amnesovergripande",
        name="SCB Amnesovergripande statistik",
        base_path="AA/",
        description=(
            "Amnesovergripande statistik och nyckeltal som korsar flera omraden, "
            "t.ex. kommun- och regionsammanstallningar."
        ),
        keywords=[
            "amnesovergripande",
            "nyckeltal",
            "indikator",
            "sammanstallning",
            "kommunfakta",
        ],
        example_queries=[
            "Nyckeltal for kommuner 2024",
            "Overgripande indikatorer Sverige 2010-2024",
            "Sammanstallning per lan 2023",
        ],
        table_codes=["AA0003"],
        typical_filters=["region", "tid", "kommun", "lan"],
    ),
    ScbToolDefinition(
        tool_id="scb_befolkning_folkmangd",
        name="SCB Befolkning - Folkmangd",
        base_path="BE/BE0101/BE0101A/",
        description="Folkmangd och befolkning per region, alder och kon.",
        keywords=["folkmangd", "befolkning", "alder", "kon", "region"],
        example_queries=[
            "Folkmangd Sverige 2010-2024",
            "Befolkning per lan 2024",
            "Aldersfordelning Goteborg 2023",
        ],
        table_codes=["BE0101A"],
        typical_filters=["tid", "region", "kon", "alder"],
    ),
    ScbToolDefinition(
        tool_id="scb_befolkning_forandringar",
        name="SCB Befolkning - Forandringar",
        base_path="BE/BE0101/BE0101G/",
        description="Befolkningsforandringar och flyttningar over tid.",
        keywords=["flytt", "migration", "forandring", "netto", "inrikes", "utrikes"],
        example_queries=[
            "Flyttnetto per lan 2020-2024",
            "Befolkningsforandringar Sverige 2015-2024",
            "Inflyttning och utflyttning per region 2023",
        ],
        table_codes=["BE0101G"],
        typical_filters=["tid", "region", "typ"],
    ),
    ScbToolDefinition(
        tool_id="scb_befolkning_fodda",
        name="SCB Befolkning - Fodda",
        base_path="BE/BE0101/BE0101H/",
        description="Fodda, barn och nativitet per region.",
        keywords=["fodda", "nativitet", "barn", "forlossning"],
        example_queries=[
            "Antal fodda per lan 2015-2024",
            "Fodda per alder 2023",
            "Fodda i Skane 2020-2024",
        ],
        table_codes=["BE0101H"],
        typical_filters=["tid", "region", "kon", "alder"],
    ),
    ScbToolDefinition(
        tool_id="scb_arbetsmarknad_arbetsloshet",
        name="SCB Arbetsmarknad - Arbetsloshet",
        base_path="AM/AM0401/",
        description="Arbetsloshet och arbetssokande over tid.",
        keywords=["arbetsloshet", "arbetslos", "arbetssokande"],
        example_queries=[
            "Arbetsloshet per lan 2018-2024",
            "Arbetsloshet kvinnor 2023",
            "Arbetsloshet Sverige 2010-2024",
        ],
        table_codes=["AM0401"],
        typical_filters=["tid", "region", "kon", "alder"],
    ),
    ScbToolDefinition(
        tool_id="scb_arbetsmarknad_sysselsattning",
        name="SCB Arbetsmarknad - Sysselsattning",
        base_path="AM/AM0301/",
        description="Sysselsattning och arbetskraft over tid.",
        keywords=["sysselsattning", "arbetskraft", "sysselsatta"],
        example_queries=[
            "Sysselsattning per lan 2015-2024",
            "Sysselsattning kvinnor 2023",
            "Sysselsattning per alder 2024",
        ],
        table_codes=["AM0301"],
        typical_filters=["tid", "region", "kon", "alder"],
    ),
    ScbToolDefinition(
        tool_id="scb_arbetsmarknad_lon",
        name="SCB Arbetsmarknad - Lon",
        base_path="AM/AM0403/",
        description="Loner och inkomstrelaterad arbetsmarknadsstatistik.",
        keywords=["lon", "inkomst", "medianlon", "timlon"],
        example_queries=[
            "Genomsnittlig lon per sektor 2022",
            "Lon per lan 2024",
            "Medianlon kvinnor 2023",
        ],
        table_codes=["AM0403"],
        typical_filters=["tid", "region", "kon", "sektor"],
    ),
    ScbToolDefinition(
        tool_id="scb_utbildning_gymnasie",
        name="SCB Utbildning - Gymnasie",
        base_path="UF/UF0104/",
        description="Gymnasieskola och gymnasieexamen.",
        keywords=["gymnasie", "examen", "betyg", "skolresultat"],
        example_queries=[
            "Gymnasieexamen per lan 2022",
            "Gymnasieexamen kvinnor 2023",
            "Gymnasieresultat per kommun 2024",
        ],
        table_codes=["UF0104"],
        typical_filters=["tid", "region", "kon", "program"],
    ),
    ScbToolDefinition(
        tool_id="scb_utbildning_hogskola",
        name="SCB Utbildning - Hogskola",
        base_path="UF/UF0202/",
        description="Hogskola och universitet, studenter och examina.",
        keywords=["hogskola", "universitet", "student", "examen"],
        example_queries=[
            "Antal studenter i hogskolan 2015-2024",
            "Hogskoleutbildade per lan 2023",
            "Examina per utbildningsomrade 2022",
        ],
        table_codes=["UF0202"],
        typical_filters=["tid", "region", "kon", "utbildningsniva"],
    ),
    ScbToolDefinition(
        tool_id="scb_utbildning_forskning",
        name="SCB Utbildning - Forskning",
        base_path="UF/UF0301/",
        description="Forskning, forskningsutgifter och FoU.",
        keywords=["forskning", "fou", "forskningsutgifter"],
        example_queries=[
            "Forskningsutgifter Sverige 2018-2024",
            "FoU per sektor 2022",
            "Forskning per lan 2023",
        ],
        table_codes=["UF0301"],
        typical_filters=["tid", "sektor", "region"],
    ),
    ScbToolDefinition(
        tool_id="scb_naringsliv_foretag",
        name="SCB Naringsliv - Foretag",
        base_path="NV/NV0101/",
        description="Foretag och foretagsbestand per bransch.",
        keywords=["foretag", "foretagsbestand", "bransch"],
        example_queries=[
            "Antal foretag per bransch 2023",
            "Foretagsbestand per lan 2024",
            "Foretag efter storleksklass 2022",
        ],
        table_codes=["NV0101"],
        typical_filters=["tid", "region", "bransch", "storlek"],
    ),
    ScbToolDefinition(
        tool_id="scb_naringsliv_omsattning",
        name="SCB Naringsliv - Omsattning",
        base_path="NV/NV0109/",
        description="Omsattning och ekonomisk statistik for naringslivet.",
        keywords=["omsattning", "intakt", "foretagsekonomi"],
        example_queries=[
            "Omsattning i industrin 2018-2024",
            "Omsattning per bransch 2023",
            "Omsattning per lan 2022",
        ],
        table_codes=["NV0109"],
        typical_filters=["tid", "region", "bransch"],
    ),
    ScbToolDefinition(
        tool_id="scb_naringsliv_nyforetagande",
        name="SCB Naringsliv - Nyforetagande",
        base_path="NV/NV0006/",
        description="Nyregistrerade foretag och nyforetagande.",
        keywords=["nyforetagande", "nyregistrerade", "starta foretag"],
        example_queries=[
            "Nyregistrerade foretag per lan 2024",
            "Nyforetagande per bransch 2023",
            "Startade foretag per kommun 2022",
        ],
        table_codes=["NV0006"],
        typical_filters=["tid", "region", "bransch"],
    ),
    ScbToolDefinition(
        tool_id="scb_miljo_utslapp",
        name="SCB Miljo - Utslapp",
        base_path="MI/MI0106/",
        description="Utslapp och klimatrelaterade indikatorer.",
        keywords=["utslapp", "co2", "klimat", "vaxthusgaser"],
        example_queries=[
            "CO2-utslapp Sverige 2010-2024",
            "Utslapp per sektor 2020-2024",
            "Utslapp per lan 2023",
        ],
        table_codes=["MI0106"],
        typical_filters=["tid", "region", "sektor"],
    ),
    ScbToolDefinition(
        tool_id="scb_miljo_energi",
        name="SCB Miljo - Energi",
        base_path="MI/MI0107/",
        description="Miljorelaterad energistatistik.",
        keywords=["energi", "forbrukning", "fornybar"],
        example_queries=[
            "Energianvandning per sektor 2015-2024",
            "Fornybar energi andel 2010-2024",
            "Energi per region 2023",
        ],
        table_codes=["MI0107"],
        typical_filters=["tid", "region", "energislag", "sektor"],
    ),
    ScbToolDefinition(
        tool_id="scb_priser_kpi",
        name="SCB Priser - KPI",
        base_path="PR/PR0101/",
        description="KPI och prisindex over tid.",
        keywords=["kpi", "konsumentprisindex", "inflation"],
        example_queries=[
            "KPI Sverige 2010-2024",
            "KPI per manad senaste 24 manaderna",
            "KPI per varugrupp 2023",
        ],
        table_codes=["PR0101"],
        typical_filters=["tid", "varukategori"],
    ),
    ScbToolDefinition(
        tool_id="scb_priser_inflation",
        name="SCB Priser - Inflation",
        base_path="PR/PR0301/",
        description="Inflation och prisforandringar.",
        keywords=["inflation", "prisforandring"],
        example_queries=[
            "Inflation 2021-2024",
            "Inflation per ar 2010-2024",
            "Prisforandring per varugrupp 2023",
        ],
        table_codes=["PR0301"],
        typical_filters=["tid", "varukategori"],
    ),
    ScbToolDefinition(
        tool_id="scb_transporter_person",
        name="SCB Transporter - Persontransporter",
        base_path="TK/TK1001/",
        description="Persontransporter och resor per trafikslag.",
        keywords=["persontransporter", "resor", "kollektivtrafik"],
        example_queries=[
            "Resor med kollektivtrafik 2015-2024",
            "Persontransporter per trafikslag 2018-2024",
            "Resor per region 2023",
        ],
        table_codes=["TK1001"],
        typical_filters=["tid", "region", "trafikslag"],
    ),
    ScbToolDefinition(
        tool_id="scb_transporter_gods",
        name="SCB Transporter - Godstransporter",
        base_path="TK/TK1201/",
        description="Godstransporter och transportarbete.",
        keywords=["gods", "godstransporter", "transportarbete"],
        example_queries=[
            "Godstransporter Sverige 2010-2024",
            "Transportarbete per region 2022-2024",
            "Gods per trafikslag 2023",
        ],
        table_codes=["TK1201"],
        typical_filters=["tid", "region", "trafikslag"],
    ),
    ScbToolDefinition(
        tool_id="scb_boende_bygglov",
        name="SCB Boende - Bygglov",
        base_path="BO/BO0301/",
        description="Bygglov och byggstarter for bostader.",
        keywords=["bygglov", "byggstarter", "bostad"],
        example_queries=[
            "Bygglov bostader 2018-2024",
            "Byggstarter per lan 2022",
            "Bygglov per kommun 2023",
        ],
        table_codes=["BO0301"],
        typical_filters=["tid", "region", "bostadstyp"],
    ),
    ScbToolDefinition(
        tool_id="scb_boende_nybyggnation",
        name="SCB Boende - Nybyggnation",
        base_path="BO/BO0101/",
        description="Nybyggnation och fardigstallda bostader.",
        keywords=["nybyggnation", "fardigstallda", "bostader"],
        example_queries=[
            "Antal fardigstallda bostader 2015-2024",
            "Nybyggnation per lan 2020-2024",
            "Bostader per upplatelseform 2023",
        ],
        table_codes=["BO0101"],
        typical_filters=["tid", "region", "bostadstyp", "upplatelseform"],
    ),
    ScbToolDefinition(
        tool_id="scb_boende_bestand",
        name="SCB Boende - Bostadsbestand",
        base_path="BO/BO0201/",
        description="Bostadsbestand och bestandsstatistik.",
        keywords=["bostadsbestand", "bestand", "bostader"],
        example_queries=[
            "Bostadsbestand per kommun 2024",
            "Antal bostader i Stockholm 2010-2024",
            "Bostadsbestand per lan 2023",
        ],
        table_codes=["BO0201"],
        typical_filters=["tid", "region", "bostadstyp"],
    ),
]


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    cleaned = (
        lowered.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
    )
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def _score_tool(definition: ScbToolDefinition, query_norm: str, tokens: set[str]) -> int:
    score = 0
    name_norm = _normalize_text(definition.name)
    desc_norm = _normalize_text(definition.description)
    if name_norm and name_norm in query_norm:
        score += 5
    for keyword in definition.keywords:
        if _normalize_text(keyword) in query_norm:
            score += 3
    for code in definition.table_codes:
        if _normalize_text(code) in query_norm:
            score += 6
    for token in tokens:
        if token and token in desc_norm:
            score += 1
    return score


def retrieve_scb_tools(query: str, limit: int = 2) -> list[str]:
    """Retrieve SCB tool IDs matching the query."""
    query_norm = _normalize_text(query)
    tokens = set(query_norm.split())
    scored = [
        (definition.tool_id, _score_tool(definition, query_norm, tokens))
        for definition in SCB_TOOL_DEFINITIONS
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    if scored and scored[0][1] == 0:
        return [definition.tool_id for definition in SCB_TOOL_DEFINITIONS[:limit]]
    return [tool_id for tool_id, _ in scored[:limit]]


async def aretrieve_scb_tools(query: str, limit: int = 2) -> list[str]:
    """Async wrapper for retrieving SCB tool IDs matching the query."""
    return retrieve_scb_tools(query, limit=limit)


def _build_tool_description(definition: ScbToolDefinition) -> str:
    examples = "\n".join(f"- {example}" for example in definition.example_queries)
    sections = [definition.description]
    if definition.table_codes:
        sections.append(f"Vanliga tabellkoder: {', '.join(definition.table_codes)}.")
    if definition.typical_filters:
        sections.append(
            f"Typiska filter: {', '.join(definition.typical_filters)}."
        )
    sections.append(f"Exempel:\n{examples}")
    return "\n\n".join(sections)


def _build_scb_tool(
    definition: ScbToolDefinition,
    *,
    scb_service: ScbService,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
):
    description = _build_tool_description(definition)

    async def _scb_tool(
        question: str,
        max_tables: int = 80,
        max_cells: int = 150_000,
        max_batches: int = 6,
    ) -> str:
        query = (question or "").strip()
        if not query:
            return json.dumps(
                {"error": "Missing question for SCB query."}, ensure_ascii=True
            )

        try:
            query_hint = " ".join(
                [
                    definition.name,
                    *definition.keywords,
                    *definition.table_codes,
                    *definition.typical_filters,
                ]
            ).strip()
            enriched_query = f"{query} {query_hint}".strip()
            table, candidates = await scb_service.find_best_table_candidates(
                definition.base_path,
                enriched_query,
                max_tables=max_tables,
            )
            if not table:
                return json.dumps(
                    {"error": "No matching SCB table found."}, ensure_ascii=True
                )
            metadata = await scb_service.get_table_metadata(table.path)
            payloads, selection_summary, warnings, batch_summaries = (
                scb_service.build_query_payloads(
                    metadata,
                    query,
                    max_cells=max_cells,
                    max_batches=max_batches,
                )
            )
            if not payloads:
                return json.dumps(
                    {"error": "No valid SCB query payloads could be built."},
                    ensure_ascii=True,
                )

            data_batches: list[dict[str, Any]] = []
            for index, payload in enumerate(payloads, start=1):
                data = await scb_service.query_table(table.path, payload)
                entry: dict[str, Any] = {"batch": index, "data": data}
                if index - 1 < len(batch_summaries):
                    entry["selection"] = batch_summaries[index - 1]
                data_batches.append(entry)
        except httpx.HTTPError as exc:
            return json.dumps(
                {"error": f"SCB request failed: {exc!s}"}, ensure_ascii=True
            )

        source_url = f"{scb_service.base_url}{table.path.lstrip('/')}"
        tool_output = {
            "source": "SCB PxWeb",
            "table": {
                "id": table.id,
                "title": table.title,
                "path": table.path,
                "updated": table.updated,
                "source_url": source_url,
            },
            "selection": selection_summary,
            "query": payloads,
            "data": data_batches,
            "warnings": warnings,
        }
        if candidates:
            tool_output["candidates"] = [
                {
                    "id": candidate.id,
                    "title": candidate.title,
                    "path": candidate.path,
                    "updated": candidate.updated,
                }
                for candidate in candidates
            ]

        document = await connector_service.ingest_tool_output(
            tool_name=definition.tool_id,
            tool_output=tool_output,
            title=f"{definition.name}: {table.title}",
            metadata={
                "source": "SCB",
                "scb_base_path": definition.base_path,
                "scb_table_path": table.path,
                "scb_table_id": table.id,
                "scb_table_title": table.title,
                "scb_source_url": source_url,
            },
            user_id=user_id,
            origin_search_space_id=search_space_id,
            thread_id=thread_id,
        )

        formatted_docs = ""
        if document:
            serialized = connector_service._serialize_external_document(
                document, score=1.0
            )
            formatted_docs = format_documents_for_context([serialized])

        response_payload = {
            "query": query,
            "table": tool_output["table"],
            "selection": selection_summary,
            "warnings": warnings,
            "results": formatted_docs,
            "batches": len(data_batches),
        }
        if candidates:
            response_payload["candidates"] = tool_output["candidates"]
        if not formatted_docs:
            response_payload["data"] = data_batches
        return json.dumps(response_payload, ensure_ascii=True)

    return tool(
        definition.tool_id,
        description=description,
        parse_docstring=False,
    )(_scb_tool)


def build_scb_tool_registry(
    *,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    scb_service: ScbService | None = None,
) -> dict[str, Any]:
    service = scb_service or ScbService()
    registry: dict[str, Any] = {}
    for definition in SCB_TOOL_DEFINITIONS:
        registry[definition.tool_id] = _build_scb_tool(
            definition,
            scb_service=service,
            connector_service=connector_service,
            search_space_id=search_space_id,
            user_id=user_id,
            thread_id=thread_id,
        )
    return registry


def build_scb_tool_store() -> InMemoryStore:
    store = InMemoryStore()
    for definition in SCB_TOOL_DEFINITIONS:
        store.put(
            ("tools",),
            definition.tool_id,
            {
                "name": definition.name,
                "description": definition.description,
                "category": "scb_statistics",
                "base_path": definition.base_path,
                "keywords": definition.keywords,
                "example_queries": definition.example_queries,
                "table_codes": definition.table_codes,
                "typical_filters": definition.typical_filters,
            },
        )
    return store


def create_statistics_agent(
    *,
    llm,
    connector_service: ConnectorService,
    search_space_id: int,
    user_id: str | None,
    thread_id: int | None,
    checkpointer: Checkpointer | None,
    scb_base_url: str | None = None,
):
    if not hasattr(BigtoolToolNode, "inject_tool_args") and hasattr(
        BigtoolToolNode, "_inject_tool_args"
    ):
        def _inject_tool_args_compat(self, tool_call, state, store):
            tool_call_id = None
            if isinstance(tool_call, dict):
                tool_call_id = tool_call.get("id")
            runtime = ToolRuntime(
                state,
                {},
                {},
                lambda _: None,
                tool_call_id,
                store,
            )
            return self._inject_tool_args(tool_call, runtime)

        BigtoolToolNode.inject_tool_args = _inject_tool_args_compat  # type: ignore[attr-defined]
    scb_service = ScbService(base_url=scb_base_url or SCB_BASE_URL)
    tool_registry = build_scb_tool_registry(
        connector_service=connector_service,
        search_space_id=search_space_id,
        user_id=user_id,
        thread_id=thread_id,
        scb_service=scb_service,
    )
    store = build_scb_tool_store()
    graph = create_bigtool_agent(
        llm,
        tool_registry,
        limit=2,
        retrieve_tools_function=retrieve_scb_tools,
        retrieve_tools_coroutine=aretrieve_scb_tools,
    )
    return graph.compile(
        checkpointer=checkpointer,
        store=store,
        name="statistics-agent",
    )
