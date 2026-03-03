"""SCB tool definitions — extracted from statistics_agent.py (KQ-3).

Contains all ScbToolDefinition instances including broad categories (21)
and specific sub-tools (26, was 21 + 5 new in #17).

New tools added in #17:
- scb_befolkning_dodsfall (BE/BE0101/BE0101I/)
- scb_befolkning_invandring (BE/BE0101/BE0101E/)
- scb_arbetsmarknad_lonestruktur (AM/AM0110/)
- scb_handel_detaljhandel (HA/HA0103/)
- scb_nationalrakenskaper_bnp_kvartal (NR/NR0103/)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.text import normalize_text as _normalize_text


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
    # -----------------------------------------------------------------------
    # Broad categories (21)
    # -----------------------------------------------------------------------
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
    # -----------------------------------------------------------------------
    # Specific sub-tools (26)
    # -----------------------------------------------------------------------
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
    # -- NEW #17: Dödsfall ---
    ScbToolDefinition(
        tool_id="scb_befolkning_dodsfall",
        name="SCB Befolkning - Dodsfall",
        base_path="BE/BE0101/BE0101I/",
        description=(
            "Dodsfallsstatistik fran SCB. Antal doda per region, alder, "
            "kon och dodsorsak."
        ),
        keywords=["dodsfall", "dod", "doda", "mortalitet", "livslangd", "dodsorsak"],
        example_queries=[
            "Antal doda Sverige 2015-2024",
            "Dodsfall per alder 2023",
            "Doda per lan 2020-2024",
            "Mortalitet per kon 2022",
        ],
        table_codes=["BE0101I"],
        typical_filters=["tid", "region", "kon", "alder"],
    ),
    # -- NEW #17: Invandring/utvandring ---
    ScbToolDefinition(
        tool_id="scb_befolkning_invandring",
        name="SCB Befolkning - Invandring och utvandring",
        base_path="BE/BE0101/BE0101E/",
        description=(
            "In- och utvandringsstatistik fran SCB. Antal invandrare och "
            "utvandrare per land, region och ar."
        ),
        keywords=[
            "invandring", "utvandring", "immigration", "emigration",
            "invandrare", "utvandrare", "asyl", "uppehallstillstand",
        ],
        example_queries=[
            "Invandring till Sverige 2015-2024",
            "Utvandring per lan 2020-2024",
            "Invandring per fodelseland 2023",
            "Nettoinvandring Sverige 2010-2024",
        ],
        table_codes=["BE0101E"],
        typical_filters=["tid", "region", "fodelseland", "kon"],
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
    # -- NEW #17: Lönestruktur (SLS) ---
    ScbToolDefinition(
        tool_id="scb_arbetsmarknad_lonestruktur",
        name="SCB Arbetsmarknad - Lonestruktur",
        base_path="AM/AM0110/",
        description=(
            "Lonestrukturstatistik (SLS) fran SCB. Detaljerad lonestatistik "
            "per yrke, sektor, utbildningsniva och region."
        ),
        keywords=[
            "lonestruktur", "sls", "yrke", "yrkeslon",
            "loneskillnad", "lonefordelning",
        ],
        example_queries=[
            "Medianlon per yrke 2023",
            "Loneskillnad man kvinnor 2022",
            "Lon per utbildningsniva 2024",
            "Loneutveckling per sektor 2015-2024",
        ],
        table_codes=["AM0110"],
        typical_filters=["tid", "yrke", "sektor", "kon", "utbildningsniva"],
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
    # -- NEW #17: Detaljhandel ---
    ScbToolDefinition(
        tool_id="scb_handel_detaljhandel",
        name="SCB Handel - Detaljhandel",
        base_path="HA/HA0103/",
        description=(
            "Omsattningsstatistik for detaljhandeln fran SCB. Omfattar "
            "detaljhandelsindex, omsattning per bransch och region."
        ),
        keywords=[
            "detaljhandel", "detaljhandelsindex", "butik",
            "dagligvaruhandel", "sallankopshandel", "e-handel",
        ],
        example_queries=[
            "Detaljhandelsindex 2018-2024",
            "Detaljhandel per bransch 2023",
            "Omsattning dagligvaruhandel 2020-2024",
            "E-handel omsattning 2022-2024",
        ],
        table_codes=["HA0103"],
        typical_filters=["tid", "bransch", "region"],
    ),
    # -- NEW #17: BNP per kvartal ---
    ScbToolDefinition(
        tool_id="scb_nationalrakenskaper_bnp_kvartal",
        name="SCB Nationalrakenskaper - BNP kvartal",
        base_path="NR/NR0103/",
        description=(
            "BNP per kvartal fran SCB. Kvartalsvis nationalrakenskaper med "
            "BNP-tillvaxt, saasongsrensad och kalenderkorrigerad."
        ),
        keywords=[
            "bnp", "kvartal", "kvartalsvis", "tillvaxt",
            "sasongsrensad", "kalenderkorrigerad", "gdp",
        ],
        example_queries=[
            "BNP per kvartal 2020-2024",
            "BNP-tillvaxt kvartalsvis 2023",
            "Sasongsrensad BNP 2022-2024",
            "Kvartals-BNP Sverige 2015-2024",
        ],
        table_codes=["NR0103"],
        typical_filters=["tid", "transaktion", "pristyp"],
    ),
]


# ---------------------------------------------------------------------------
# Pre-computed normalized keyword index for fast retrieval (OPT-7)
# ---------------------------------------------------------------------------

def _build_keyword_index() -> dict[str, list[str]]:
    """Pre-compute normalized keywords for each tool definition.

    Returns a dict mapping tool_id -> list of normalized keyword strings.
    Called once at module load time to avoid repeated normalization.
    """
    index: dict[str, list[str]] = {}
    for definition in SCB_TOOL_DEFINITIONS:
        normalized = [_normalize_text(kw) for kw in definition.keywords]
        index[definition.tool_id] = normalized
    return index


# Module-level pre-computed index
SCB_KEYWORD_INDEX: dict[str, list[str]] = _build_keyword_index()

# Pre-computed normalized names and descriptions
SCB_NORMALIZED_NAMES: dict[str, str] = {
    d.tool_id: _normalize_text(d.name) for d in SCB_TOOL_DEFINITIONS
}
SCB_NORMALIZED_DESCRIPTIONS: dict[str, str] = {
    d.tool_id: _normalize_text(d.description) for d in SCB_TOOL_DEFINITIONS
}
SCB_NORMALIZED_TABLE_CODES: dict[str, list[str]] = {
    d.tool_id: [_normalize_text(c) for c in d.table_codes]
    for d in SCB_TOOL_DEFINITIONS
}


# ---------------------------------------------------------------------------
# Tool scoring and retrieval (moved here to avoid heavy import chains)
# ---------------------------------------------------------------------------


def _score_tool(definition: ScbToolDefinition, query_norm: str, tokens: set[str]) -> int:
    """Score a tool definition against a query using pre-computed indices."""
    score = 0
    tool_id = definition.tool_id

    name_norm = SCB_NORMALIZED_NAMES.get(tool_id, "")
    desc_norm = SCB_NORMALIZED_DESCRIPTIONS.get(tool_id, "")

    if name_norm and name_norm in query_norm:
        score += 5

    for kw_norm in SCB_KEYWORD_INDEX.get(tool_id, []):
        if kw_norm in query_norm:
            score += 3

    for code_norm in SCB_NORMALIZED_TABLE_CODES.get(tool_id, []):
        if code_norm in query_norm:
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
