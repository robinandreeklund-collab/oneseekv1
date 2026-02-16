# New Tool Guide (SurfSense) - exakt integrationschecklista

Den här guiden beskriver **exakt vilka steg** som krävs för att lägga till nya tools så att de fungerar från start i:

- backend (tool execution),
- supervisor/bigtool retrieval,
- routing/agentval,
- frontend admin tool settings,
- eval-system.

Guiden är byggd efter den nuvarande implementationen i repo.

---

## 0) Välj integrationsspår

Det finns två vanliga sätt att lägga till tools:

1. **Spår A - Enstaka tool i befintlig `tools/`-modul**  
   Exempel: `smhi_weather`, `libris_search`, `link_preview`.

2. **Spår B - Ny provider/tool-pack med egna definitionslistor**  
   Exempel: `marketplace_tools.py`, `kolada_tools.py`, `riksdagen_agent.py`.

Om du bygger flera tools för samma API/provider, välj nästan alltid **Spår B**.

---

## 1) Implementera tool-logik

## Spår A (enstaka tool)

Skapa fil:

- `surfsense_backend/app/agents/new_chat/tools/<my_tool>.py`

Exempel-skelett:

```python
from langchain_core.tools import tool

def create_my_tool(...):
    @tool
    async def my_tool(question: str) -> dict:
        """Kort, tydlig description."""
        # 1) validera input
        # 2) anropa API/service
        # 3) returnera normaliserad payload
        return {"ok": True}
    return my_tool
```

### Viktigt för datakällor/citations

Om toolen hämtar extern data som ska kunna citeras i svar:

- använd `connector_service.ingest_tool_output(...)`
- formatera med `format_documents_for_context(...)`

Titta på mönster i:

- `surfsense_backend/app/agents/new_chat/marketplace_tools.py`
- `surfsense_backend/app/agents/new_chat/statistics_agent.py`

---

## Spår B (provider/tool-pack)

Skapa fil:

- `surfsense_backend/app/agents/new_chat/<provider>_tools.py`

Följ mönstret:

1. dataclass för definitioner (tool_id, category, description, keywords, example_queries)
2. `*_TOOL_DEFINITIONS` lista
3. `_build_<provider>_tool(...)`
4. `build_<provider>_tool_registry(...)`

Referens:

- `surfsense_backend/app/agents/new_chat/marketplace_tools.py`

---

## 2) Registrera tools i global registry

Fil:

- `surfsense_backend/app/agents/new_chat/tools/registry.py`

### Spår A

1. Importera factory:

```python
from .my_tool import create_my_tool
```

2. Lägg till `ToolDefinition(...)` i `BUILTIN_TOOLS`.
3. Sätt rätt `requires=[...]` för dependencies.
4. Välj `enabled_by_default=True/False`.

### Spår B

1. Importera `*_TOOL_DEFINITIONS` + `build_*_tool_registry`.
2. Lägg till tool-ids i `get_default_enabled_tools()` om de ska vara default.
3. Lägg till block i `build_tools_async(...)` som bygger registry och appendar tools.

---

## 3) Namespace + retrieval metadata (obligatoriskt)

Fil:

- `surfsense_backend/app/agents/new_chat/bigtool_store.py`

Du måste uppdatera:

1. `TOOL_NAMESPACE_OVERRIDES` (tool_id -> namespace)
2. `TOOL_KEYWORDS` (retrieval-signaler)
3. vid behov `namespace_for_tool(...)` med prefix-routing
4. `build_tool_index(...)` så category/description/keywords hämtas från dina definitioner

Om du missar detta får du ofta:

- fel tool retrieval,
- låg träff i eval,
- agent drift mot fel verktyg.

---

## 4) Route mapping (vilken top-level route får använda toolen)

Fil:

- `surfsense_backend/app/agents/new_chat/routing.py`

Lägg tool-id i rätt lista i `ROUTE_TOOL_SETS`:

- `Route.KNOWLEDGE`
- `Route.ACTION`
- `Route.STATISTICS`

Detta påverkar vilka tools som ens är tillgängliga i deep-agent fallback-flöden.

---

## 5) Intent + dispatch-signaler (rekommenderat för bra träff direkt)

För nya domäner/providers bör du lägga in tydliga signaler:

1. **Intent keywords**
   - Fil: `surfsense_backend/app/services/intent_definition_service.py`
   - uppdatera `keywords` och ev. `description`.

2. **Rule-based top-level route**
   - Fil: `surfsense_backend/app/agents/new_chat/dispatcher.py`
   - lägg regex + regel i `_infer_rule_based_route(...)` vid behov.

3. **Action sub-route (om route=action)**
   - Fil: `surfsense_backend/app/agents/new_chat/action_router.py`
   - lägg mönster i rätt bucket (`WEB` / `MEDIA` / `TRAVEL` / `DATA`).

---

## 6) Agent/prompt integration

### Om toolen tillhör befintlig agent

Exempel: marketplace tools tillhör `marketplace` agenten.

- säkerställ att agentens prompt innehåller tydlig tool-strategi
- promptnyckel ska finnas i `prompt_registry.py`

Filer:

- `surfsense_backend/app/agents/new_chat/prompt_registry.py`
- t.ex. `surfsense_backend/app/agents/new_chat/marketplace_prompts.py`

### Om du skapar en helt ny specialist-agent

Uppdatera i:

- `surfsense_backend/app/agents/new_chat/supervisor_agent.py`

Minst:

1. `worker_configs` - ny `WorkerConfig` med primary/fallback namespaces
2. `worker_prompts` - promptkoppling
3. `agent_definitions` - namn, beskrivning, keywords
4. `_SPECIALIZED_AGENTS` - så agenten inte route-överstyrs fel
5. `_AGENT_NAME_ALIAS_MAP` och alias-heuristik vid behov
6. ev. `_ROUTE_STRICT_AGENT_POLICIES` om route ska vara strikt

---

## 7) Frontend/admin tool settings integration

Fil:

- `surfsense_backend/app/routes/admin_tool_settings_routes.py`

För att tools ska visas korrekt i admin/eval UI:

1. Uppdatera `_provider_for_tool_id(...)` med ditt tool-prefix
2. Uppdatera `_provider_display_name(...)`
3. Vid provider med egna statiska definitionslistor:
   - lägg till i `_build_tool_api_categories_response(...)`
4. Säkerställ att `_infer_agent_for_tool(...)` mappas rätt för din domän
5. Säkerställ att `_infer_route_for_tool(...)` ger rätt route/sub_route

Annars kan UI/eval få fel provider, fel agent eller fel route.

---

## 8) Eval integration (obligatoriskt om ny domän/agent)

Fil:

- `surfsense_backend/app/services/tool_evaluation_service.py`

Kontrollera och uppdatera:

1. `_normalize_agent_name(...)` (alias)
2. `_agent_for_tool(...)`
3. `_route_sub_route_for_tool(...)`
4. `_candidate_agents_for_route(...)`
5. `_heuristic_agent_choice(...)`
6. ev. category-normalisering om ny category-format

Vid ny agent:

- lägg till agent i `_EVAL_AGENT_CHOICES`
- lägg beskrivning i `_EVAL_AGENT_DESCRIPTIONS`

---

## 9) Eval library (testfall från start)

Eval-filer ligger under:

- `eval/api/<provider>/<category>/*.json`

Skapa 3-10 testfall som minst täcker:

1. route
2. sub_route (om action)
3. agent
4. category
5. tool

Du kan också generera via admin-endpoints (`/admin/tool-settings/eval-library/...`), men ha gärna en handskriven basfil för regression.

---

## 10) Tester - minimum som ska finnas

Lägg tester i:

- `surfsense_backend/tests/`

Minst:

1. **Service/test av API-normalisering**  
   Exempel: `test_blocket_tradera_service.py`
2. **Namespace/keywords integration**  
   Exempel: `test_kolada_bigtool_integration.py`
3. **Eval-logik vid ny agent/route**  
   Exempel: `test_tool_evaluation_service.py`

---

## 11) Verifiering innan merge

Kör minst:

```bash
# syntax check
python3 -m compileall surfsense_backend/app

# relevanta tester
python3 -m pytest -q surfsense_backend/tests/test_tool_evaluation_service.py
python3 -m pytest -q surfsense_backend/tests/test_<din_service>.py
```

Sedan manuell smoke test i chat:

1. fråga som ska träffa din tool
2. kontrollera tracing:
   - route
   - selected agent
   - selected tool
3. verifiera att tool-resultatet faktiskt används i slutsvaret

---

## 12) Vanliga fel (och exakt var de fixas)

1. **Tool syns inte alls**
   - `tools/registry.py` (ej registrerad)
   - `get_default_enabled_tools()` (inte default-enabled)

2. **Tool väljs aldrig av retrieval**
   - `bigtool_store.py` (`TOOL_NAMESPACE_OVERRIDES`, `TOOL_KEYWORDS`)

3. **Fel route/sub-route**
   - `routing.py`
   - `dispatcher.py`
   - `action_router.py`

4. **Fel agent**
   - `supervisor_agent.py` (agent definitions/aliases/policies)
   - `admin_tool_settings_routes.py` (`_infer_agent_for_tool`)
   - `tool_evaluation_service.py` (`_agent_for_tool`)

5. **Frontend visar fel provider/kategori**
   - `admin_tool_settings_routes.py` (`_provider_for_tool_id`, `_provider_display_name`, `_build_tool_api_categories_response`)

6. **Eval säger FAIL trots att runtime ser okej ut**
   - `tool_evaluation_service.py` mappingar/normalisering
   - eval JSON (fel expected route/agent/tool/category)

---

## 13) Definition of Done (DoD)

En ny tool är "klar" först när allt nedan är sant:

- [ ] Tool implementation fungerar mot verkligt API/mock
- [ ] Tool registrerad i `tools/registry.py`
- [ ] Namespace + keywords + index metadata i `bigtool_store.py`
- [ ] Route mapping i `routing.py`
- [ ] Intent/dispatch-signaler uppdaterade (vid behov)
- [ ] Prompt/agent integration klar (vid behov)
- [ ] Admin provider mapping + kategorier fungerar
- [ ] Eval mappingar uppdaterade
- [ ] Minst 1 eval library-fil skapad/uppdaterad
- [ ] Minst 2-3 relevanta tester tillagda/uppdaterade
- [ ] Manuell tracing i chat visar korrekt route -> agent -> tool

---

## Snabb start (kortversion)

Om du vill ha en snabb "från noll till klart" checklista:

1. Implementera tool/service
2. Registrera i `tools/registry.py`
3. Lägg namespace + keywords i `bigtool_store.py`
4. Lägg tool i `routing.py`
5. Lägg intent/route-signaler (`intent_definition_service.py`, `dispatcher.py`, `action_router.py`)
6. Uppdatera admin/eval mapping (`admin_tool_settings_routes.py`, `tool_evaluation_service.py`)
7. Lägg tester + eval JSON
8. Verifiera via tracing i frontend

Följer du den ordningen minimerar du risken för "funkar i kod men inte i eval/frontend".
