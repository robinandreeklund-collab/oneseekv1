# LangGraph/LangSmith Dev Studio (lokalt)

Denna repo innehåller nu en Studio-entrypoint för hela supervisor-flödet:

- Graph config: `surfsense_backend/langgraph.json`
- Graph factory: `app.langgraph_studio:make_studio_graph`

Det gör att du kan köra LangGraph Studio lokalt och se nod-för-nod vad som händer i flödet.

## 1) Installera LangGraph CLI lokalt

På din dator (inte i cloud-agenten), i valfri Python-miljö:

```bash
pip install -U "langgraph-cli[inmem]"
```

## 2) Sätt miljövariabler

Skapa/uppdatera `surfsense_backend/.env` med dina vanliga backend-variabler
(`DATABASE_URL`, API-nycklar, etc).

Rekommenderade Studio-variabler:

```bash
STUDIO_SEARCH_SPACE_ID=2
STUDIO_LLM_CONFIG_ID=-1
STUDIO_THREAD_ID=900000001
STUDIO_CHECKPOINTER_MODE=memory
STUDIO_COMPARE_MODE=false
STUDIO_RUNTIME_HITL_JSON={"enabled":true,"hybrid_mode":true,"speculative_enabled":true}
```

Valfritt (om du vill forcera användare):

```bash
STUDIO_USER_ID=<uuid>
```

## 3) Aktivera LangSmith live-tracing (valfritt men rekommenderat)

Lägg till:

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=oneseek-local-studio
LANGSMITH_API_KEY=<din_langsmith_api_key>
```

## 4) Starta Studio

```bash
cd surfsense_backend
langgraph dev --config langgraph.json --host 127.0.0.1 --port 8123
```

Öppna sedan URL:en som CLI visar (Studio UI).

## 5) Kör ett test i Studio

Exempel-input till grafen:

```json
{
  "messages": [
    { "role": "user", "content": "Kan du kolla hur vädret är i Hjo?" }
  ],
  "turn_id": "studio-turn-1",
  "route_hint": "action"
}
```

## Notes

- `STUDIO_CHECKPOINTER_MODE=memory` är enklast för snabb lokal debug.
- Sätt `STUDIO_CHECKPOINTER_MODE=postgres` om du vill debugga med samma checkpoint-beteende som produktion.
- Graph-fabriken bygger samma supervisor-graph som chatflödet använder (`build_complete_graph`), med prompt-overrides från databasen.
