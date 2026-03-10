"""SCB Region Registry — All 290 municipalities + 21 counties + Riket.

Provides O(1) lookup by code and by name, with diacritik normalization
so that "Goteborg" matches "Göteborg", "Jonkoping" matches "Jönköping", etc.

Used by:
- scb_validate / scb_fetch (fuzzy region matching)
- QUL entity → SCB code mapping
- scb_inspect_table (human-readable labels)
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScbRegion:
    code: str       # SCB code: "0180", "01", "00"
    name: str       # Canonical Swedish name: "Stockholm", "Stockholms län"
    type: str       # "municipality" | "county" | "country"


# ---------------------------------------------------------------------------
# Diacritik normalization
# ---------------------------------------------------------------------------

_DIACRITIK_TABLE = str.maketrans({
    "à": "a", "á": "a", "â": "a", "ã": "a",
    "ç": "c",
    "è": "e", "é": "e", "ê": "e", "ë": "e",
    "ì": "i", "í": "i", "î": "i", "ï": "i",
    "ð": "d", "ñ": "n",
    "ò": "o", "ó": "o", "ô": "o", "õ": "o", "ø": "o",
    "ù": "u", "ú": "u", "û": "u", "ü": "u",
    "ý": "y", "ÿ": "y",
    "þ": "b",
})


def normalize_diacritik(text: str) -> str:
    """Normalize Swedish diacritics for fuzzy matching.

    "Göteborg" → "goteborg", "Jönköping" → "jonkoping", etc.
    """
    lower = text.lower().strip()
    # Handle common Swedish characters explicitly
    result = lower.replace("å", "a").replace("ä", "a").replace("ö", "o")
    # Handle any remaining unicode diacritics
    result = result.translate(_DIACRITIK_TABLE)
    # Remove any remaining combining characters
    result = unicodedata.normalize("NFD", result)
    result = "".join(c for c in result if unicodedata.category(c) != "Mn")
    return result


# ---------------------------------------------------------------------------
# Complete registry: 00 (Riket) + 21 counties + 290 municipalities
# ---------------------------------------------------------------------------

# Country
_COUNTRY = [
    ScbRegion("00", "Riket", "country"),
]

# 21 Counties (län) — 2-digit codes
_COUNTIES = [
    ScbRegion("01", "Stockholms län", "county"),
    ScbRegion("03", "Uppsala län", "county"),
    ScbRegion("04", "Södermanlands län", "county"),
    ScbRegion("05", "Östergötlands län", "county"),
    ScbRegion("06", "Jönköpings län", "county"),
    ScbRegion("07", "Kronobergs län", "county"),
    ScbRegion("08", "Kalmar län", "county"),
    ScbRegion("09", "Gotlands län", "county"),
    ScbRegion("10", "Blekinge län", "county"),
    ScbRegion("12", "Skåne län", "county"),
    ScbRegion("13", "Hallands län", "county"),
    ScbRegion("14", "Västra Götalands län", "county"),
    ScbRegion("17", "Värmlands län", "county"),
    ScbRegion("18", "Örebro län", "county"),
    ScbRegion("19", "Västmanlands län", "county"),
    ScbRegion("20", "Dalarnas län", "county"),
    ScbRegion("21", "Gävleborgs län", "county"),
    ScbRegion("22", "Västernorrlands län", "county"),
    ScbRegion("23", "Jämtlands län", "county"),
    ScbRegion("24", "Västerbottens län", "county"),
    ScbRegion("25", "Norrbottens län", "county"),
]

# 290 Municipalities (kommuner) — 4-digit codes
# Sorted by code within each county
_MUNICIPALITIES = [
    # Stockholms län (01)
    ScbRegion("0114", "Upplands Väsby", "municipality"),
    ScbRegion("0115", "Vallentuna", "municipality"),
    ScbRegion("0117", "Österåker", "municipality"),
    ScbRegion("0120", "Värmdö", "municipality"),
    ScbRegion("0123", "Järfälla", "municipality"),
    ScbRegion("0125", "Ekerö", "municipality"),
    ScbRegion("0126", "Huddinge", "municipality"),
    ScbRegion("0127", "Botkyrka", "municipality"),
    ScbRegion("0128", "Salem", "municipality"),
    ScbRegion("0136", "Haninge", "municipality"),
    ScbRegion("0138", "Tyresö", "municipality"),
    ScbRegion("0139", "Upplands-Bro", "municipality"),
    ScbRegion("0140", "Nykvarn", "municipality"),
    ScbRegion("0160", "Täby", "municipality"),
    ScbRegion("0162", "Danderyd", "municipality"),
    ScbRegion("0163", "Sollentuna", "municipality"),
    ScbRegion("0180", "Stockholm", "municipality"),
    ScbRegion("0181", "Södertälje", "municipality"),
    ScbRegion("0182", "Nacka", "municipality"),
    ScbRegion("0183", "Sundbyberg", "municipality"),
    ScbRegion("0184", "Solna", "municipality"),
    ScbRegion("0186", "Lidingö", "municipality"),
    ScbRegion("0187", "Vaxholm", "municipality"),
    ScbRegion("0188", "Norrtälje", "municipality"),
    ScbRegion("0191", "Sigtuna", "municipality"),
    ScbRegion("0192", "Nynäshamn", "municipality"),
    # Uppsala län (03)
    ScbRegion("0305", "Håbo", "municipality"),
    ScbRegion("0319", "Älvkarleby", "municipality"),
    ScbRegion("0330", "Knivsta", "municipality"),
    ScbRegion("0331", "Heby", "municipality"),
    ScbRegion("0360", "Tierp", "municipality"),
    ScbRegion("0380", "Uppsala", "municipality"),
    ScbRegion("0381", "Enköping", "municipality"),
    ScbRegion("0382", "Östhammar", "municipality"),
    # Södermanlands län (04)
    ScbRegion("0428", "Vingåker", "municipality"),
    ScbRegion("0461", "Gnesta", "municipality"),
    ScbRegion("0480", "Nyköping", "municipality"),
    ScbRegion("0481", "Oxelösund", "municipality"),
    ScbRegion("0482", "Flen", "municipality"),
    ScbRegion("0483", "Katrineholm", "municipality"),
    ScbRegion("0484", "Eskilstuna", "municipality"),
    ScbRegion("0486", "Strängnäs", "municipality"),
    ScbRegion("0488", "Trosa", "municipality"),
    # Östergötlands län (05)
    ScbRegion("0509", "Ödeshög", "municipality"),
    ScbRegion("0512", "Ydre", "municipality"),
    ScbRegion("0513", "Kinda", "municipality"),
    ScbRegion("0560", "Boxholm", "municipality"),
    ScbRegion("0561", "Åtvidaberg", "municipality"),
    ScbRegion("0562", "Finspång", "municipality"),
    ScbRegion("0563", "Valdemarsvik", "municipality"),
    ScbRegion("0580", "Linköping", "municipality"),
    ScbRegion("0581", "Norrköping", "municipality"),
    ScbRegion("0582", "Söderköping", "municipality"),
    ScbRegion("0583", "Motala", "municipality"),
    ScbRegion("0584", "Vadstena", "municipality"),
    ScbRegion("0586", "Mjölby", "municipality"),
    # Jönköpings län (06)
    ScbRegion("0604", "Aneby", "municipality"),
    ScbRegion("0617", "Gnosjö", "municipality"),
    ScbRegion("0642", "Mullsjö", "municipality"),
    ScbRegion("0643", "Habo", "municipality"),
    ScbRegion("0662", "Gislaved", "municipality"),
    ScbRegion("0665", "Vaggeryd", "municipality"),
    ScbRegion("0680", "Jönköping", "municipality"),
    ScbRegion("0682", "Nässjö", "municipality"),
    ScbRegion("0683", "Värnamo", "municipality"),
    ScbRegion("0684", "Sävsjö", "municipality"),
    ScbRegion("0685", "Vetlanda", "municipality"),
    ScbRegion("0686", "Eksjö", "municipality"),
    ScbRegion("0687", "Tranås", "municipality"),
    # Kronobergs län (07)
    ScbRegion("0760", "Uppvidinge", "municipality"),
    ScbRegion("0761", "Lessebo", "municipality"),
    ScbRegion("0763", "Tingsryd", "municipality"),
    ScbRegion("0764", "Alvesta", "municipality"),
    ScbRegion("0765", "Älmhult", "municipality"),
    ScbRegion("0767", "Markaryd", "municipality"),
    ScbRegion("0780", "Växjö", "municipality"),
    ScbRegion("0781", "Ljungby", "municipality"),
    # Kalmar län (08)
    ScbRegion("0821", "Högsby", "municipality"),
    ScbRegion("0834", "Torsås", "municipality"),
    ScbRegion("0840", "Mörbylånga", "municipality"),
    ScbRegion("0860", "Hultsfred", "municipality"),
    ScbRegion("0861", "Mönsterås", "municipality"),
    ScbRegion("0862", "Emmaboda", "municipality"),
    ScbRegion("0880", "Kalmar", "municipality"),
    ScbRegion("0881", "Nybro", "municipality"),
    ScbRegion("0882", "Oskarshamn", "municipality"),
    ScbRegion("0883", "Västervik", "municipality"),
    ScbRegion("0884", "Vimmerby", "municipality"),
    ScbRegion("0885", "Borgholm", "municipality"),
    # Gotlands län (09)
    ScbRegion("0980", "Gotland", "municipality"),
    # Blekinge län (10)
    ScbRegion("1060", "Olofström", "municipality"),
    ScbRegion("1080", "Karlskrona", "municipality"),
    ScbRegion("1081", "Ronneby", "municipality"),
    ScbRegion("1082", "Karlshamn", "municipality"),
    ScbRegion("1083", "Sölvesborg", "municipality"),
    # Skåne län (12)
    ScbRegion("1214", "Svalöv", "municipality"),
    ScbRegion("1230", "Staffanstorp", "municipality"),
    ScbRegion("1231", "Burlöv", "municipality"),
    ScbRegion("1233", "Vellinge", "municipality"),
    ScbRegion("1256", "Östra Göinge", "municipality"),
    ScbRegion("1257", "Örkelljunga", "municipality"),
    ScbRegion("1260", "Bjuv", "municipality"),
    ScbRegion("1261", "Kävlinge", "municipality"),
    ScbRegion("1262", "Lomma", "municipality"),
    ScbRegion("1263", "Svedala", "municipality"),
    ScbRegion("1264", "Skurup", "municipality"),
    ScbRegion("1265", "Sjöbo", "municipality"),
    ScbRegion("1266", "Hörby", "municipality"),
    ScbRegion("1267", "Höör", "municipality"),
    ScbRegion("1270", "Tomelilla", "municipality"),
    ScbRegion("1272", "Bromölla", "municipality"),
    ScbRegion("1273", "Osby", "municipality"),
    ScbRegion("1275", "Perstorp", "municipality"),
    ScbRegion("1276", "Klippan", "municipality"),
    ScbRegion("1277", "Åstorp", "municipality"),
    ScbRegion("1278", "Båstad", "municipality"),
    ScbRegion("1280", "Malmö", "municipality"),
    ScbRegion("1281", "Lund", "municipality"),
    ScbRegion("1282", "Landskrona", "municipality"),
    ScbRegion("1283", "Helsingborg", "municipality"),
    ScbRegion("1284", "Höganäs", "municipality"),
    ScbRegion("1285", "Eslöv", "municipality"),
    ScbRegion("1286", "Ystad", "municipality"),
    ScbRegion("1287", "Trelleborg", "municipality"),
    ScbRegion("1290", "Kristianstad", "municipality"),
    ScbRegion("1291", "Simrishamn", "municipality"),
    ScbRegion("1292", "Ängelholm", "municipality"),
    ScbRegion("1293", "Hässleholm", "municipality"),
    # Hallands län (13)
    ScbRegion("1315", "Hylte", "municipality"),
    ScbRegion("1380", "Halmstad", "municipality"),
    ScbRegion("1381", "Laholm", "municipality"),
    ScbRegion("1382", "Falkenberg", "municipality"),
    ScbRegion("1383", "Varberg", "municipality"),
    ScbRegion("1384", "Kungsbacka", "municipality"),
    # Västra Götalands län (14)
    ScbRegion("1401", "Härryda", "municipality"),
    ScbRegion("1402", "Partille", "municipality"),
    ScbRegion("1407", "Öckerö", "municipality"),
    ScbRegion("1415", "Stenungsund", "municipality"),
    ScbRegion("1419", "Tjörn", "municipality"),
    ScbRegion("1421", "Orust", "municipality"),
    ScbRegion("1427", "Sotenäs", "municipality"),
    ScbRegion("1430", "Munkedal", "municipality"),
    ScbRegion("1435", "Tanum", "municipality"),
    ScbRegion("1438", "Dals-Ed", "municipality"),
    ScbRegion("1439", "Färgelanda", "municipality"),
    ScbRegion("1440", "Ale", "municipality"),
    ScbRegion("1441", "Lerum", "municipality"),
    ScbRegion("1442", "Vårgårda", "municipality"),
    ScbRegion("1443", "Bollebygd", "municipality"),
    ScbRegion("1444", "Grästorp", "municipality"),
    ScbRegion("1445", "Essunga", "municipality"),
    ScbRegion("1446", "Karlsborg", "municipality"),
    ScbRegion("1447", "Gullspång", "municipality"),
    ScbRegion("1452", "Tranemo", "municipality"),
    ScbRegion("1460", "Bengtsfors", "municipality"),
    ScbRegion("1461", "Mellerud", "municipality"),
    ScbRegion("1462", "Lilla Edet", "municipality"),
    ScbRegion("1463", "Mark", "municipality"),
    ScbRegion("1465", "Svenljunga", "municipality"),
    ScbRegion("1466", "Herrljunga", "municipality"),
    ScbRegion("1470", "Vara", "municipality"),
    ScbRegion("1471", "Götene", "municipality"),
    ScbRegion("1472", "Tibro", "municipality"),
    ScbRegion("1473", "Töreboda", "municipality"),
    ScbRegion("1480", "Göteborg", "municipality"),
    ScbRegion("1481", "Mölndal", "municipality"),
    ScbRegion("1482", "Kungälv", "municipality"),
    ScbRegion("1484", "Lysekil", "municipality"),
    ScbRegion("1485", "Uddevalla", "municipality"),
    ScbRegion("1486", "Strömstad", "municipality"),
    ScbRegion("1487", "Vänersborg", "municipality"),
    ScbRegion("1488", "Trollhättan", "municipality"),
    ScbRegion("1489", "Alingsås", "municipality"),
    ScbRegion("1490", "Borås", "municipality"),
    ScbRegion("1491", "Ulricehamn", "municipality"),
    ScbRegion("1492", "Åmål", "municipality"),
    ScbRegion("1493", "Mariestad", "municipality"),
    ScbRegion("1494", "Lidköping", "municipality"),
    ScbRegion("1495", "Skara", "municipality"),
    ScbRegion("1496", "Skövde", "municipality"),
    ScbRegion("1497", "Hjo", "municipality"),
    ScbRegion("1498", "Tidaholm", "municipality"),
    ScbRegion("1499", "Falköping", "municipality"),
    # Värmlands län (17)
    ScbRegion("1715", "Kil", "municipality"),
    ScbRegion("1730", "Eda", "municipality"),
    ScbRegion("1737", "Torsby", "municipality"),
    ScbRegion("1760", "Storfors", "municipality"),
    ScbRegion("1761", "Hammarö", "municipality"),
    ScbRegion("1762", "Munkfors", "municipality"),
    ScbRegion("1763", "Forshaga", "municipality"),
    ScbRegion("1764", "Grums", "municipality"),
    ScbRegion("1765", "Årjäng", "municipality"),
    ScbRegion("1766", "Sunne", "municipality"),
    ScbRegion("1780", "Karlstad", "municipality"),
    ScbRegion("1781", "Kristinehamn", "municipality"),
    ScbRegion("1782", "Filipstad", "municipality"),
    ScbRegion("1783", "Hagfors", "municipality"),
    ScbRegion("1784", "Arvika", "municipality"),
    ScbRegion("1785", "Säffle", "municipality"),
    # Örebro län (18)
    ScbRegion("1814", "Lekeberg", "municipality"),
    ScbRegion("1860", "Laxå", "municipality"),
    ScbRegion("1861", "Hallsberg", "municipality"),
    ScbRegion("1862", "Degerfors", "municipality"),
    ScbRegion("1863", "Hällefors", "municipality"),
    ScbRegion("1864", "Ljusnarsberg", "municipality"),
    ScbRegion("1880", "Örebro", "municipality"),
    ScbRegion("1881", "Kumla", "municipality"),
    ScbRegion("1882", "Askersund", "municipality"),
    ScbRegion("1883", "Karlskoga", "municipality"),
    ScbRegion("1884", "Nora", "municipality"),
    ScbRegion("1885", "Lindesberg", "municipality"),
    # Västmanlands län (19)
    ScbRegion("1904", "Skinnskatteberg", "municipality"),
    ScbRegion("1907", "Surahammar", "municipality"),
    ScbRegion("1960", "Kungsör", "municipality"),
    ScbRegion("1961", "Hallstahammar", "municipality"),
    ScbRegion("1962", "Norberg", "municipality"),
    ScbRegion("1980", "Västerås", "municipality"),
    ScbRegion("1981", "Sala", "municipality"),
    ScbRegion("1982", "Fagersta", "municipality"),
    ScbRegion("1983", "Köping", "municipality"),
    ScbRegion("1984", "Arboga", "municipality"),
    # Dalarnas län (20)
    ScbRegion("2021", "Vansbro", "municipality"),
    ScbRegion("2023", "Malung-Sälen", "municipality"),
    ScbRegion("2026", "Gagnef", "municipality"),
    ScbRegion("2029", "Leksand", "municipality"),
    ScbRegion("2031", "Rättvik", "municipality"),
    ScbRegion("2034", "Orsa", "municipality"),
    ScbRegion("2039", "Älvdalen", "municipality"),
    ScbRegion("2061", "Smedjebacken", "municipality"),
    ScbRegion("2062", "Mora", "municipality"),
    ScbRegion("2080", "Falun", "municipality"),
    ScbRegion("2081", "Borlänge", "municipality"),
    ScbRegion("2082", "Säter", "municipality"),
    ScbRegion("2083", "Hedemora", "municipality"),
    ScbRegion("2084", "Avesta", "municipality"),
    ScbRegion("2085", "Ludvika", "municipality"),
    # Gävleborgs län (21)
    ScbRegion("2101", "Ockelbo", "municipality"),
    ScbRegion("2104", "Hofors", "municipality"),
    ScbRegion("2121", "Ovanåker", "municipality"),
    ScbRegion("2132", "Nordanstig", "municipality"),
    ScbRegion("2161", "Ljusdal", "municipality"),
    ScbRegion("2180", "Gävle", "municipality"),
    ScbRegion("2181", "Sandviken", "municipality"),
    ScbRegion("2182", "Söderhamn", "municipality"),
    ScbRegion("2183", "Bollnäs", "municipality"),
    ScbRegion("2184", "Hudiksvall", "municipality"),
    # Västernorrlands län (22)
    ScbRegion("2260", "Ånge", "municipality"),
    ScbRegion("2262", "Timrå", "municipality"),
    ScbRegion("2280", "Härnösand", "municipality"),
    ScbRegion("2281", "Sundsvall", "municipality"),
    ScbRegion("2282", "Kramfors", "municipality"),
    ScbRegion("2283", "Sollefteå", "municipality"),
    ScbRegion("2284", "Örnsköldsvik", "municipality"),
    # Jämtlands län (23)
    ScbRegion("2303", "Ragunda", "municipality"),
    ScbRegion("2305", "Bräcke", "municipality"),
    ScbRegion("2309", "Krokom", "municipality"),
    ScbRegion("2313", "Strömsund", "municipality"),
    ScbRegion("2321", "Åre", "municipality"),
    ScbRegion("2326", "Berg", "municipality"),
    ScbRegion("2361", "Härjedalen", "municipality"),
    ScbRegion("2380", "Östersund", "municipality"),
    # Västerbottens län (24)
    ScbRegion("2401", "Nordmaling", "municipality"),
    ScbRegion("2403", "Bjurholm", "municipality"),
    ScbRegion("2404", "Vindeln", "municipality"),
    ScbRegion("2409", "Robertsfors", "municipality"),
    ScbRegion("2417", "Norsjö", "municipality"),
    ScbRegion("2418", "Malå", "municipality"),
    ScbRegion("2421", "Storuman", "municipality"),
    ScbRegion("2422", "Sorsele", "municipality"),
    ScbRegion("2425", "Dorotea", "municipality"),
    ScbRegion("2460", "Vännäs", "municipality"),
    ScbRegion("2462", "Vilhelmina", "municipality"),
    ScbRegion("2463", "Åsele", "municipality"),
    ScbRegion("2480", "Umeå", "municipality"),
    ScbRegion("2481", "Lycksele", "municipality"),
    ScbRegion("2482", "Skellefteå", "municipality"),
    # Norrbottens län (25)
    ScbRegion("2505", "Arvidsjaur", "municipality"),
    ScbRegion("2506", "Arjeplog", "municipality"),
    ScbRegion("2510", "Jokkmokk", "municipality"),
    ScbRegion("2513", "Överkalix", "municipality"),
    ScbRegion("2514", "Kalix", "municipality"),
    ScbRegion("2518", "Övertorneå", "municipality"),
    ScbRegion("2521", "Pajala", "municipality"),
    ScbRegion("2523", "Gällivare", "municipality"),
    ScbRegion("2560", "Älvsbyn", "municipality"),
    ScbRegion("2580", "Luleå", "municipality"),
    ScbRegion("2581", "Piteå", "municipality"),
    ScbRegion("2582", "Boden", "municipality"),
    ScbRegion("2583", "Haparanda", "municipality"),
    ScbRegion("2584", "Kiruna", "municipality"),
]

# ---------------------------------------------------------------------------
# Combined registry
# ---------------------------------------------------------------------------

ALL_REGIONS: list[ScbRegion] = _COUNTRY + _COUNTIES + _MUNICIPALITIES

# O(1) lookup maps
_BY_CODE: dict[str, ScbRegion] = {r.code: r for r in ALL_REGIONS}
_BY_NAME: dict[str, ScbRegion] = {r.name.lower(): r for r in ALL_REGIONS}
_BY_NORMALIZED: dict[str, ScbRegion] = {
    normalize_diacritik(r.name): r for r in ALL_REGIONS
}

# Common aliases and abbreviations
_ALIASES: dict[str, str] = {
    "sthlm": "0180",
    "gbg": "1480",
    "nkpg": "0581",
    "lkpg": "0580",
    "cph": "",  # Not a Swedish region
    "tumba": "0127",  # Botkyrka
    "visby": "0980",  # Gotland
    "riket": "00",
    "sverige": "00",
    "hela landet": "00",
    "hela riket": "00",
    # County short names
    "skane": "12",
    "skåne": "12",
    "vastra gotaland": "14",
    "västra götaland": "14",
    "vg": "14",
    "norrbotten": "25",
    "vasterbotten": "24",
    "västerbotten": "24",
    "jamtland": "23",
    "jämtland": "23",
    "dalarna": "20",
    "gavleborg": "21",
    "gävleborg": "21",
    "vasternorrland": "22",
    "västernorrland": "22",
    "varmland": "17",
    "värmland": "17",
    "orebro": "18",
    "örebro": "18",
    "vastmanland": "19",
    "västmanland": "19",
    "sodermanland": "04",
    "södermanland": "04",
    "ostergotland": "05",
    "östergötland": "05",
    "jonkoping": "06",
    "jönköping": "06",
    "kronoberg": "07",
    "blekinge": "10",
    "halland": "13",
    "gotland": "09",
    "stockholm": "0180",
    "stockholms lan": "01",
    "stockholms län": "01",
    "uppsala lan": "03",
    "uppsala län": "03",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_region_by_code(code: str) -> ScbRegion | None:
    """O(1) lookup by SCB code."""
    return _BY_CODE.get(code.strip())


def find_region_by_name(name: str) -> ScbRegion | None:
    """Exact name lookup (case-insensitive)."""
    return _BY_NAME.get(name.lower().strip())


def find_region_fuzzy(query: str) -> list[ScbRegion]:
    """Fuzzy region search with diacritik normalization.

    Matches "Goteborg" → Göteborg, "Jonkoping" → Jönköping, etc.
    Returns matching regions sorted by specificity (municipalities first).
    """
    query_norm = normalize_diacritik(query)
    if not query_norm:
        return []

    # 1. Check aliases first
    alias_code = _ALIASES.get(query_norm)
    if alias_code:
        region = _BY_CODE.get(alias_code)
        if region:
            return [region]

    # 2. Exact normalized match
    region = _BY_NORMALIZED.get(query_norm)
    if region:
        return [region]

    # 3. Substring / prefix matching
    matches: list[ScbRegion] = []
    for norm_name, region in _BY_NORMALIZED.items():
        if query_norm in norm_name or norm_name.startswith(query_norm):
            matches.append(region)

    # Sort: municipalities first (more specific), then counties
    type_order = {"municipality": 0, "county": 1, "country": 2}
    matches.sort(key=lambda r: (type_order.get(r.type, 3), r.name))

    return matches[:10]


def resolve_region_codes(
    location_name: str,
    table_values: list[str] | None = None,
    table_value_texts: list[str] | None = None,
) -> list[str]:
    """Resolve a location name to SCB region codes.

    First tries the offline registry, then matches against table-specific
    value codes if provided. Returns list of matching codes.
    """
    candidates = find_region_fuzzy(location_name)
    if not candidates:
        return []

    if table_values is None:
        return [c.code for c in candidates[:3]]

    # Filter to codes that actually exist in this table
    table_set = set(table_values)
    result: list[str] = []
    for candidate in candidates:
        if candidate.code in table_set:
            result.append(candidate.code)

    # If no exact matches, try matching by name against value texts
    if not result and table_value_texts:
        query_norm = normalize_diacritik(location_name)
        for code, text in zip(table_values, table_value_texts, strict=False):
            text_norm = normalize_diacritik(text)
            if query_norm in text_norm or text_norm.startswith(query_norm):
                result.append(code)

    return result[:5]


def format_region_for_llm(region: ScbRegion) -> str:
    """Format a region for display to the LLM."""
    type_labels = {
        "country": "hela landet",
        "county": "län",
        "municipality": "kommun",
    }
    return f"{region.code}={region.name} ({type_labels.get(region.type, '')})"
