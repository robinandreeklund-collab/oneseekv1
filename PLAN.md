# Plan: Research Agent + Spotlight Arena UI

## Sammanfattning

Lägga till en **research-agent** ("call_oneseek") som körs parallellt med de externa modellerna i compare mode. Agenten har en egen mini-graph med Tavily-webbsökning och ger syntesizern faktaunderlag att bedöma modellernas svar mot. Frontenden uppdateras med **Spotlight Arena** — en dedikerad compare-resultatvy anpassad efter OneSeeks designsystem.

---

## Del 1: Backend — Research Agent

### Steg 1: Skapa research-agenten (`compare_research_agent.py`)

**Ny fil:** `surfsense_backend/app/agents/new_chat/compare_research_agent.py`

En mini-graph med 3 noder:
1. **`research_plan`** — LLM-anrop som tar användarfrågan och genererar 1-3 sökfrågor (query decomposition)
2. **`research_execute`** — Kör Tavily-sökning parallellt för varje sökfråga via `asyncio.gather()`
3. **`research_synthesize`** — Sammanfattar alla sökresultat till ett strukturerat faktaunderlag

Mini-graphen byggs med `StateGraph` internt i en `run_research_agent()` async-funktion. Den tar `connector_service`, `search_space_id`, `user_id` och `query` som argument.

**Returnerar:**
```python
{
    "status": "success",
    "source": "OneSeek Research",
    "queries_used": ["query1", "query2"],
    "web_sources": [{"title": "...", "url": "...", "snippet": "..."}],
    "synthesis": "Sammanfattat faktaunderlag...",
    "citation_chunk_ids": ["chunk_1", "chunk_2"],
    "latency_ms": 1234,
}
```

### Steg 2: Exponera som tool (`call_oneseek`)

**Modifiera:** `surfsense_backend/app/agents/new_chat/tools/external_models.py`

Lägg INTE till `call_oneseek` i `EXTERNAL_MODEL_SPECS` (det är inte en extern modell). Skapa istället en separat factory:

```python
def create_oneseek_research_tool(connector_service, search_space_id, user_id):
    @tool
    async def call_oneseek(query: str) -> str:
        result = await run_research_agent(
            connector_service=connector_service,
            search_space_id=search_space_id,
            user_id=user_id,
            query=query,
        )
        return json.dumps(result, ensure_ascii=False)
    return call_oneseek
```

### Steg 3: Uppdatera `compare_fan_out` för parallell exekvering

**Modifiera:** `surfsense_backend/app/agents/new_chat/compare_executor.py`

Ändra `compare_fan_out` så den startar research-agenten **parallellt** med de externa modellerna:

```python
async def compare_fan_out(state, *, connector_service=None, search_space_id=None, user_id=None):
    # ... befintlig logik för externa modeller ...

    # Lägg till research-agenten som en extra parallell task
    research_task = run_research_agent(
        connector_service=connector_service,
        search_space_id=search_space_id,
        user_id=user_id,
        query=user_query,
    )

    # Kör ALLT parallellt: 7 externa modeller + 1 research agent
    all_tasks = model_tasks + [research_task]
    results = await asyncio.gather(*all_tasks, return_exceptions=False)
```

Research-agentens resultat läggs till i `compare_outputs` med `tool_name: "call_oneseek"` och emitteras som en ToolMessage precis som de externa modellerna, så frontend-kortet renderas korrekt.

### Steg 4: Uppdatera `compare_synthesizer` prompt

**Modifiera:** `surfsense_backend/app/agents/new_chat/compare_prompts.py`

Lägg till `RESEARCH_AGENT_SECTION` i syntesprompt:
```
- Research-agentens svar (märkt som ONESEEK_RESEARCH) innehåller verifierad webb-information.
  Prioritera denna för faktapåståenden framför individuella modellsvar.
```

### Steg 5: Uppdatera `_build_synthesis_context`

**Modifiera:** `surfsense_backend/app/agents/new_chat/compare_executor.py`

Separat sektion för OneSeek Research i synteskontexten:
```
ONESEEK_RESEARCH (verifierad webb-data):
{synthesis}

Källor:
- {title} ({url})
```

### Steg 6: Wiring i supervisor_agent.py

**Modifiera:** `surfsense_backend/app/agents/new_chat/supervisor_agent.py` (rad ~6640-6668)

Skicka dependencies till `compare_fan_out` via `functools.partial`:
```python
compare_fan_out_with_deps = partial(
    compare_fan_out,
    connector_service=connector_service,
    search_space_id=search_space_id,
    user_id=user_id,
)
```

### Steg 7: Ta bort `compare_tavily` placeholder

**Modifiera:** `compare_executor.py` och `supervisor_agent.py`

`compare_tavily`-noden är nu onödig — Tavily-sökning sker inne i research-agenten. Ta bort noden och uppdatera grafen:

```
resolve_intent → compare_fan_out → compare_collect → compare_synthesizer → END
```

### Steg 8: SSE-streaming för research-agenten

**Modifiera:** `surfsense_backend/app/tasks/chat/stream_new_chat.py`

Lägg till `"call_oneseek"` i `_EXTERNAL_MODEL_TOOL_NAMES` (eller skapa ny set `_RESEARCH_TOOL_NAMES`) så att tool-output-events strömmas korrekt till frontend. Research-agenten ska skicka:
- `tool-input-start` → visar laddningskortet
- `tool-input-available` → visar query-argumentet
- `tool-output-available` → visar resultatet

### Steg 9: Registrera i bigtool_store

**Modifiera:** `surfsense_backend/app/agents/new_chat/bigtool_store.py`

```python
TOOL_NAMESPACE_OVERRIDES["call_oneseek"] = ("tools", "compare", "research")
TOOL_KEYWORDS["call_oneseek"] = ["oneseek", "research", "fakta", "webb", "sök"]
```

---

## Del 2: Frontend — Spotlight Arena

### Steg 10: OneSeek Research ModelCard

**Modifiera:** `surfsense_web/components/tool-ui/compare-model.tsx`

Lägg till `OneseekToolUI` som använder `call_oneseek`. Anpassa ModelCard för research-resultatet:
- Visar OneSeek-loggan med "Research Agent" badge
- Visar använda sökfrågor som chips
- Visar webbkällor med titel + URL
- Visar syntesen (inte en modell-respons utan faktaunderlag)
- Latency + antal källor istället för token usage

### Steg 11: Spotlight Arena layout-komponent

**Ny fil:** `surfsense_web/components/tool-ui/spotlight-arena.tsx`

Spotlight Arena-vyn som renderas när compare-resultat finns:

**Layout:**
- OneSeek Research-kortet centrerat överst ("spotlight"-position) — detta är faktaunderlaget
- Externa modellkort i ett responsivt grid nedanför (2-3 kolumner)
- Varje kort visar: modelllogga, provider-badge, sammanfattning, latency, token usage
- Expand/collapse för fullständigt svar
- Visuella indikatorer om modellens svar överensstämmer med research-agentens fakta (grön/gul/röd)

**Design (OneSeek-anpassad):**
- Använder befintliga CSS-variabler (oklch) från globals.css
- shadcn/ui Card, Badge, Collapsible, Tooltip
- Subtil spotlight-glow-effekt runt research-kortet (CSS radial-gradient med `--primary`)
- Dark mode-stöd via befintliga CSS-variabler
- Animationer: fade-in för kort i ordningen de anländer, skeleton-shimmer under laddning

### Steg 12: Integrera Spotlight Arena i thread

**Modifiera:** `surfsense_web/components/assistant-ui/thread.tsx`

Detektera när ett meddelande innehåller compare tool-calls och rendera `<SpotlightArena>` istället för individuella tool-calls inline.

### Steg 13: Uppdatera TOOLS_WITH_UI

**Modifiera:** `surfsense_web/app/dashboard/[search_space_id]/new-chat/new-chat-page.tsx`

Se till att `"call_oneseek"` finns i `TOOLS_WITH_UI` set (det finns redan men behöver motsvarande rendering).

### Steg 14: Compare Summary rendering

**Modifiera:** `surfsense_web/lib/chat/message-utils.ts`

Sluta filtrera bort `compare-summary` — skicka den till Spotlight Arena som syntesens text.

---

## Flödesdiagram (efter implementation)

```
User Input (/compare query)
    ↓
resolve_intent
    ↓
compare_fan_out (asyncio.gather)
    ├─→ call_grok() ──────────────┐
    ├─→ call_deepseek() ──────────┤
    ├─→ call_gemini() ────────────┤
    ├─→ call_gpt() ──────────────┤    Alla parallellt
    ├─→ call_claude() ────────────┤
    ├─→ call_perplexity() ────────┤
    ├─→ call_qwen() ─────────────┤
    └─→ research_agent() ────────┤    ← NY
         ├─ research_plan         │
         ├─ research_execute      │    (Tavily × N)
         └─ research_synthesize   │
                                  ↓
compare_collect (validate)
    ↓
compare_synthesizer (LLM syntes med research-fakta som ankare)
    ↓
END → Stream Spotlight Arena till frontend
```

---

## Ordning och beroenden

1. Steg 1-2 (research agent + tool) → kan göras först
2. Steg 3-5 (fan_out + prompts + context) → beror på steg 1-2
3. Steg 6-9 (wiring + streaming + registration) → beror på steg 3
4. Steg 10-14 (frontend) → kan påbörjas parallellt med steg 6-9

## Filer som ändras

**Nya filer:**
- `surfsense_backend/app/agents/new_chat/compare_research_agent.py`
- `surfsense_web/components/tool-ui/spotlight-arena.tsx`

**Modifierade filer:**
- `surfsense_backend/app/agents/new_chat/compare_executor.py`
- `surfsense_backend/app/agents/new_chat/compare_prompts.py`
- `surfsense_backend/app/agents/new_chat/supervisor_agent.py`
- `surfsense_backend/app/agents/new_chat/bigtool_store.py`
- `surfsense_backend/app/tasks/chat/stream_new_chat.py`
- `surfsense_web/components/tool-ui/compare-model.tsx`
- `surfsense_web/components/assistant-ui/thread.tsx`
- `surfsense_web/app/dashboard/[search_space_id]/new-chat/new-chat-page.tsx`
- `surfsense_web/lib/chat/message-utils.ts`
