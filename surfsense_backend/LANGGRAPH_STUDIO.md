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

Från repo-roten:

```bash
langgraph dev --config langgraph.json --host 127.0.0.1 --port 8123
```

eller från backend-katalogen:

```bash
cd surfsense_backend
langgraph dev --config langgraph.json --host 127.0.0.1 --port 8123
```

Windows PowerShell (rekommenderat helper-script från repo-roten):

```powershell
.\scripts\run-langgraph-studio.ps1
```

Det scriptet:

- skapar `.venv` om den saknas
- installerar backend-dependencies + `langgraph-cli`
- startar Studio med rätt Python-miljö

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

Fler färdiga testfall finns i:

- `surfsense_backend/studio_input_examples.json`

Varje exempel innehåller:

- `input_state`: payload att köra i Studio
- `expected_signals`: vad du bör verifiera i traces
- `configurable_overrides` (valfritt): runtime-flaggor per scenario

Tips: börja med dessa tre för cross-workflow-debug:

1. `weather_hjo_direct`
2. `compare_followup_weather_shift`
3. `traffic_e4_goteborg_direct`

## Notes

- `STUDIO_CHECKPOINTER_MODE=memory` är enklast för snabb lokal debug.
- Sätt `STUDIO_CHECKPOINTER_MODE=postgres` om du vill debugga med samma checkpoint-beteende som produktion.
- Graph-fabriken bygger samma supervisor-graph som chatflödet använder (`build_complete_graph`), med prompt-overrides från databasen.

## Troubleshooting

### `ModuleNotFoundError: No module named 'sqlalchemy'`

Du kör `langgraph` i en Python-miljö utan backend-dependencies.

Lösning (Windows PowerShell):

```powershell
cd C:\Users\robin\Documents\GitHub\oneseekv1
.\scripts\run-langgraph-studio.ps1
```

Alternativ manuell setup:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip setuptools wheel
python -m pip install -e .\surfsense_backend
python -m pip install "langgraph-cli[inmem]"
langgraph dev --config langgraph.json --host 127.0.0.1 --port 8123
```

### `ModuleNotFoundError: No module named 'fcntl'` (Windows)

`fcntl` finns inte på Windows. Nyare kod använder en Windows-kompatibel fallback för sandbox state-locking.

Lösning:

1. `git pull` så att du har senaste ändringarna.
2. Kör scriptet igen:

```powershell
.\scripts\run-langgraph-studio.ps1
```

Om du fortfarande får samma fel kör du sannolikt mot en äldre checkout eller annan katalog.

### `RuntimeError: asyncio.run() cannot be called from a running event loop`

Detta händer när en äldre Studio-factory kör `asyncio.run(...)` inifrån LangGraphs egen event loop.

Lösning:

1. `git pull` till senaste branch.
2. Starta om Studio:

```powershell
.\scripts\run-langgraph-studio.ps1 -SkipInstall
```
