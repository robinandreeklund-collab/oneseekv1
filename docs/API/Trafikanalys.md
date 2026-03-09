# Trafikanalys API Integration

## Översikt

Integration med Trafikanalys (trafa.se) REST-API för svensk transportstatistik.

| Egenskap | Värde |
|----------|-------|
| **API** | Trafikanalys öppen data |
| **Bas-URL** | `https://api.trafa.se/api/` |
| **Dokumentation** | [trafa.se/sidor/oppen-data-api/](https://www.trafa.se/sidor/oppen-data-api/) |
| **API-beskrivning (PDF)** | [api-beskrivning.pdf](https://www.trafa.se/globalassets/ovriga-dokument/api-beskrivning.pdf) |

## Autentisering

**Ingen autentisering krävs.** API:t är helt öppet — ingen registrering, ingen API-nyckel, inget avtal.

| Egenskap | Värde |
|----------|-------|
| **API-nyckel** | Ej nödvändig |
| **Rate limits** | Ej formellt specificerade |
| **Rekommendation** | Implementera cache för att undvika onödig belastning |

## Endpoints

### Structure API

Hämtar metadata om produkter, dimensioner och mått.

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/structure` | GET | Lista alla tillgängliga statistikprodukter |
| `/api/structure?query={query}` | GET | Hämta dimensioner och mått för en produkt |

### Data API

Hämtar faktiska statistikobservationer.

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/data?query={query}` | GET | Hämta statistikdata för ett urval |

### Query-format

Queries byggs med **pipe-separator** (`|`):

```
query=PRODUKT|MÅTT|DIMENSION:filter1,filter2|DIMENSION2
```

**Exempel:**

| Query | Beskrivning |
|-------|-------------|
| `t10016` | Metadata för personbilar |
| `t10016\|itrfslut` | Antal personbilar i trafik (alla år) |
| `t10016\|itrfslut\|ar:2024` | Antal personbilar i trafik 2024 |
| `t10016\|itrfslut\|ar:2023,2024\|drivm` | Personbilar per drivmedel 2023–2024 |
| `t10016\|nyregunder\|ar:senaste` | Nyregistrerade personbilar, senaste året |

**Filter-syntax:**
- `dimension:värde` — ett specifikt värde
- `dimension:värde1,värde2` — flera värden (kommaseparerade)
- `dimension:senaste` — senaste tillgängliga år
- `dimension:forra` — föregående år

### Språkstöd

Parametern `lang` styr språk för etiketter:
- `lang=sv` (standard) — svenska
- `lang=en` — engelska

## Statistikprodukter

### Vägtrafik

| Produktkod | Namn | Beskrivning |
|-----------|------|-------------|
| `t10016` | Personbilar | Bestånd, registreringar, drivmedel, ägare |
| `t10013` | Lastbilar | Bestånd, registreringar |
| `t10011` | Bussar | Bestånd, registreringar |
| `t10014` | Motorcyklar | Bestånd, registreringar |
| `t10015` | Mopeder klass I | Bestånd |
| `t10017` | Släpvagnar | Bestånd |
| `t10018` | Traktorer | Bestånd |
| `t10019` | Terrängskotrar | Bestånd |
| `t10010` | Fordon på väg | Översikt alla fordonsslag |
| `t10030` | Nyregistreringar | Alla fordonsslag |
| `t10012` | Körkort | Innehavare per behörighet |
| `t0401` | Trafikarbete | Fordonskilometer |
| `t04021` | Transportarbete väg | Transportarbete på väg |
| `t1004` | Vägtrafikskador | Döda, skadade per trafikantgrupp |
| `t10061` | Lastbilstrafik (år) | Godstransporter med lastbil |
| `t10062` | Lastbilstrafik (kvartal) | Kvartalsdata |

### Sjöfart

| Produktkod | Namn | Beskrivning |
|-----------|------|-------------|
| `t0802` | Sjötrafik | Gods, passagerare, anlöp i hamnar |
| `t08021` | Sjötrafik (kvartal) | Kvartalsdata |
| `t0808` | Fartyg | Fartygsbestånd |
| `t08091` | Sjöfartsföretag | Företag |
| `t08092` | Sjöfartsföretag EU | EU-statistik |

### Luftfart

| Produktkod | Namn | Beskrivning |
|-----------|------|-------------|
| `t0501` | Luftfart | Passagerare, flygningar, gods |

### Järnväg

| Produktkod | Namn | Beskrivning |
|-----------|------|-------------|
| `t0603` | Järnvägstransporter | Person- och godstransporter |
| `t0602` | Bantrafikskador | Olyckor och tillbud |
| `t0604` | Punktlighet | Tågpunktlighet (STM) |
| `t0604_rt_ar` | Punktlighet (år) | Årspublicering |
| `t0604_rt_kv` | Punktlighet (kvartal) | Kvartalspublicering |

### Kollektivtrafik

| Produktkod | Namn | Beskrivning |
|-----------|------|-------------|
| `t1201` | Färdtjänst | Färdtjänst och riksfärdtjänst |
| `t1202` | Kommersiell linjetrafik | Linjetrafik på väg |
| `t1203` | Regional linjetrafik | Regional kollektivtrafik |
| `t1204` | Linjetrafik vatten | Kollektivtrafik på vatten |

### Övrigt

| Produktkod | Namn | Beskrivning |
|-----------|------|-------------|
| `t1101` | RVU | Resvaneundersökning |
| `t1102` | Varuflöden | Varuflödesundersökning |
| `t0301` | Utländska lastbilar | Utländska lastbilstransporter i Sverige |
| `t0701` | Postverksamhet | Poststatistik |
| `t0901` | Televerksamhet | Telestatistik |

## Vanliga dimensioner och mått

### Mått (Measures)

| Namn | Beskrivning |
|------|-------------|
| `itrfslut` | Antal i trafik |
| `avstslut` | Antal avställda |
| `nyregunder` | Antal nyregistreringar |
| `avregunder` | Antal avregistreringar |
| `fordonkm` | Fordonskilometer (miljoner km) |

### Dimensioner (Dimensions)

| Namn | Etikett | Används i |
|------|---------|-----------|
| `ar` | År | Alla produkter |
| `drivm` | Drivmedel | Fordonsprodukter |
| `agarkat` | Ägarkategori | Fordonsprodukter |
| `kon` | Kön | Fordon, körkort |
| `dimpo` | Direkt import | Fordonsprodukter |
| `leasing` | Leasing | Fordonsprodukter |
| `tjvikt` | Tjänstevikt | Fordonsprodukter |
| `arsmodel` | Fordonsålder | Fordonsprodukter |

### Dimensionsvärden (vanliga)

| Dimension | Filter | Beskrivning |
|-----------|--------|-------------|
| `ar` | `senaste` | Senaste tillgängliga år |
| `ar` | `forra` | Föregående år |
| `ar` | `2024` | Specifikt år |
| `ar` | `2020,2021,2022` | Flera år |

## Verktyg (12 st)

| Tool ID | Namn | Kategori | Beskrivning |
|---------|------|----------|-------------|
| `trafikanalys_fordon_personbilar` | Trafikanalys Personbilar | Vägtrafik | Antal, registreringar, drivmedel |
| `trafikanalys_fordon_lastbilar` | Trafikanalys Lastbilar | Vägtrafik | Antal, registreringar |
| `trafikanalys_fordon_bussar` | Trafikanalys Bussar | Vägtrafik | Antal, registreringar |
| `trafikanalys_fordon_motorcyklar` | Trafikanalys Motorcyklar | Vägtrafik | Antal, registreringar |
| `trafikanalys_fordon_oversikt` | Trafikanalys Fordonsöversikt | Vägtrafik | Alla fordonsslag |
| `trafikanalys_korkort` | Trafikanalys Körkort | Vägtrafik | Innehavare per behörighet |
| `trafikanalys_trafikarbete` | Trafikanalys Trafikarbete | Vägtrafik | Fordonskilometer |
| `trafikanalys_vagtrafik_skador` | Trafikanalys Vägtrafikskador | Vägtrafik | Döda, skadade |
| `trafikanalys_sjotrafik` | Trafikanalys Sjötrafik | Sjöfart | Gods, passagerare |
| `trafikanalys_luftfart` | Trafikanalys Luftfart | Luftfart | Passagerare, flygningar |
| `trafikanalys_jarnvag` | Trafikanalys Järnväg | Järnväg | Person- och godstransporter |
| `trafikanalys_kollektivtrafik` | Trafikanalys Kollektivtrafik | Kollektivtrafik | Regional linjetrafik |

## Verktygsparametrar

### trafikanalys_fordon_personbilar

| Parameter | Typ | Standard | Beskrivning |
|-----------|-----|---------|-------------|
| `measure` | str | `"itrfslut"` | Mått: `itrfslut`, `nyregunder`, `avregunder`, `avstslut` |
| `years` | str | `"senaste"` | År, kommaseparerade eller `"senaste"` |
| `breakdown` | str | `""` | Uppdelningsdimension: `drivm`, `agarkat`, `kon` |

### trafikanalys_fordon_lastbilar / bussar / motorcyklar

| Parameter | Typ | Standard | Beskrivning |
|-----------|-----|---------|-------------|
| `measure` | str | `"itrfslut"` | Mått: `itrfslut`, `nyregunder`, `avregunder`, `avstslut` |
| `years` | str | `"senaste"` | År, kommaseparerade eller `"senaste"` |

### trafikanalys_fordon_oversikt / trafikarbete / skador / sjö / luft / järnväg / kollektivtrafik

| Parameter | Typ | Standard | Beskrivning |
|-----------|-----|---------|-------------|
| `years` | str | `"senaste"` | År, kommaseparerade eller `"senaste"` |

### trafikanalys_korkort

| Parameter | Typ | Standard | Beskrivning |
|-----------|-----|---------|-------------|
| `years` | str | `"senaste"` | År, kommaseparerade eller `"senaste"` |
| `breakdown` | str | `""` | Uppdelningsdimension: `kon`, `alder` |

## Agent- och Domänkonfiguration

- **Agent:** `trafikanalys-transport` i domän `trafik-och-transport`
- **Primära namespaces:** `["tools", "trafikanalys", "transport"]`
- **Fallback namespaces:** `["tools", "trafikanalys"]`

## Dataformat

### Responsstruktur (Data API)

```json
{
  "Header": {
    "Column": [
      {"Name": "ar", "Value": "År", "Type": "D", "Unit": ""},
      {"Name": "itrfslut", "Value": "Antal i trafik", "Type": "M", "Unit": "st"}
    ]
  },
  "Rows": [
    {
      "Cell": [
        {"Column": "ar", "Value": "2024", "FormattedValue": "2024"},
        {"Column": "itrfslut", "Value": "4977791", "FormattedValue": "4 977 791"}
      ]
    }
  ],
  "Name": "Personbilar",
  "OriginalName": "T10016",
  "Errors": null,
  "Notes": {}
}
```

### Förenklad respons (efter _simplify_response)

Verktygens returvärde förenklar ovanstående till:

```json
{
  "status": "success",
  "tool": "trafikanalys_fordon_personbilar",
  "source": "Trafikanalys (api.trafa.se)",
  "cached": false,
  "data": {
    "product": "Personbilar",
    "product_code": "T10016",
    "columns": [
      {"name": "ar", "label": "År", "type": "D", "unit": ""},
      {"name": "itrfslut", "label": "Antal i trafik", "type": "M", "unit": "st"}
    ],
    "rows": [
      {"ar": "2024", "itrfslut": "4 977 791"}
    ],
    "row_count": 1
  }
}
```

### Responsstruktur (Structure API)

```json
{
  "DataCount": 0,
  "StructureItems": [
    {
      "Id": 1,
      "Name": "t10016",
      "Label": "Personbilar",
      "Type": "P",
      "Selected": false,
      "StructureItems": []
    }
  ],
  "ValidatedRequestType": "anonymous"
}
```

### Typkoder i Structure

| Typ | Beskrivning |
|-----|-------------|
| `P` | Produkt |
| `D` | Dimension (variabel) |
| `DV` | Dimensionsvärde |
| `M` | Mått (mätvärde) |
| `H` | Hierarki |
| `F` | Filter (t.ex. "senaste", "föregående") |

## Användningsvillkor

- Fritt att använda utan kostnad
- Öppna data — fritt för kommersiell och icke-kommersiell återanvändning
- **Krav:** Ange alltid "Källa: Trafikanalys (trafa.se)"

## Caching

Tjänsten använder TTL-baserad in-memory-cache:

| Cache | TTL | Max storlek | Användning |
|-------|-----|-------------|------------|
| **Data** | 3 600 s (1 h) | 500 poster | Statistikobservationer |
| **Metadata** | 86 400 s (24 h) | 200 poster | Produktlista, dimensioner |

Rekommendation från Trafikanalys: "Implementera cache-funktioner för att undvika onödig belastning."

## Filer

| Fil | Beskrivning |
|-----|-------------|
| `surfsense_backend/app/services/trafikanalys_service.py` | HTTP-klient med cache |
| `surfsense_backend/app/agents/new_chat/tools/trafikanalys.py` | Verktygsimplementationer (12 st) |
| `surfsense_backend/tests/test_trafikanalys_service.py` | Tester |

## Miljövariabler

| Variabel | Standard | Beskrivning |
|----------|---------|-------------|
| `TRAFIKANALYS_BASE_URL` | `https://api.trafa.se/api` | API bas-URL |
| `TRAFIKANALYS_TIMEOUT` | `20.0` | HTTP timeout (sekunder) |
| `TRAFIKANALYS_CACHE_TTL_DATA` | `3600` | Cache TTL data (sekunder) |
| `TRAFIKANALYS_CACHE_TTL_META` | `86400` | Cache TTL metadata (sekunder) |

## Exempel: API-anrop

### Lista alla produkter

```
GET https://api.trafa.se/api/structure
```

### Hämta dimensioner för personbilar

```
GET https://api.trafa.se/api/structure?query=t10016
```

### Hämta antal personbilar i trafik 2024

```
GET https://api.trafa.se/api/data?query=t10016|itrfslut|ar:2024
```

**Svar:**
```json
{
  "Rows": [{"Cell": [{"Column": "ar", "Value": "2024"}, {"Column": "itrfslut", "Value": "4977791"}]}],
  "Name": "Personbilar"
}
```

### Personbilar per drivmedel 2023–2024

```
GET https://api.trafa.se/api/data?query=t10016|itrfslut|ar:2023,2024|drivm
```

### Nyregistreringar senaste fem åren

```
GET https://api.trafa.se/api/data?query=t10016|nyregunder|ar:2020,2021,2022,2023,2024
```

### Trafikarbete (fordonskilometer)

```
GET https://api.trafa.se/api/data?query=t0401|fordonkm|ar:senaste
```
