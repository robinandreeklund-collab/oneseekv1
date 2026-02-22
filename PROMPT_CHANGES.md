# Promptändringar för Multi-Domain Query Support

Detta dokument listar alla promptändringar som gjordes för att stödja mixade frågor (multi-domain queries) som "hur många bor i Göteborg och vad är det för väder?".

## Sammanfattning

Tre supervisor-prompter uppdaterades för att stödja `route="mixed"` med `sub_intents` array för att hantera frågor som berör flera domäner samtidigt.

---

## 1. DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT

**Fil:** `surfsense_backend/app/agents/new_chat/supervisor_pipeline_prompts.py`
**Rader:** 10-11, 18

### Tillagda rader:

```python
# Rad 10-11:
- For mixade fragor (t.ex. "hur manga bor i Goteborg och vad ar det for vader?"):
  satt route="mixed" och inkludera sub_intents array med alla deldomaner.
```

```python
# Rad 18 (i JSON-schemat):
  "sub_intents": ["intent1", "intent2"],
```

### Syfte:
- Instruerar LLM att identifiera när en fråga innehåller flera olika domäner
- Lägger till `route="mixed"` som ett nytt alternativ
- Introducerar `sub_intents` array för att lista alla identifierade deldomäner

---

## 2. DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT

**Fil:** `surfsense_backend/app/agents/new_chat/supervisor_pipeline_prompts.py`
**Rad:** 31

### Tillagd rad:

```python
# Rad 31:
- For mixade fragor (route="mixed" med sub_intents): valj N agenter, en per sub_intent.
```

### Syfte:
- Instruerar agentväljaren att välja flera agenter när `route="mixed"`
- En agent ska väljas per identifierad `sub_intent`
- Detta möjliggör parallell hantering av olika domäner i samma fråga

---

## 3. DEFAULT_SUPERVISOR_PLANNER_PROMPT

**Fil:** `surfsense_backend/app/agents/new_chat/supervisor_pipeline_prompts.py`
**Rad:** 57

### Tillagd rad:

```python
# Rad 57:
- For mixade fragor: skapa parallella steg, ett per sub_intent/agent.
```

### Syfte:
- Instruerar planeraren att skapa parallella exekveringssteg för mixade frågor
- Ett steg skapas per `sub_intent` och tilldelad agent
- Möjliggör samtidig bearbetning av olika domäner

---

## 4. DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT

**Fil:** `surfsense_backend/app/agents/new_chat/supervisor_pipeline_prompts.py`
**Rad:** 90

### Tillagd rad:

```python
# Rad 90:
- For mixade fragor: verifiera att alla sub_intents tackts innan "ok".
```

### Syfte:
- Instruerar kritikern att kontrollera att ALLA `sub_intents` har hanterats
- Förhindrar för tidigt avslut av mixade frågor
- Säkerställer att svaret täcker alla delar av frågan

---

## 5. DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT

**Fil:** `surfsense_backend/app/agents/new_chat/supervisor_pipeline_prompts.py`
**Rad:** 112

### Tillagd rad:

```python
# Rad 112:
- For mixade fragor: strukturera svaret i sektioner per deldoman.
```

### Syfte:
- Instruerar synthesizern att organisera slutsvaret i tydliga sektioner
- En sektion per deldomain för bättre läsbarhet
- Hjälper användaren att se svaren på olika delar av frågan

---

## Kodinställningar (ej prompter)

Förutom prompterna gjordes följande tekniska ändringar i `supervisor_agent.py`:

1. **Tog bort hårdkodad weather-routing** - Weather-frågor hanteras nu via LLM-klassificering istället för regex-overrides
2. **Tog bort limit=1 för weather** - Mixade frågor kan nu hämta flera agenter
3. **Lade till sub_intents i cache-nyckel** - För korrekt cachning av mixade frågor
4. **Tog bort weather-specifik cache-invalidering** - Cachningen fungerar nu för alla query-typer

---

## Hur du synkar ändringarna

Om du har lokala ändringar i dessa prompt-filer:

### Alternativ 1: Manuell merge
1. Öppna `surfsense_backend/app/agents/new_chat/supervisor_pipeline_prompts.py`
2. Lägg till raderna markerade ovan i respektive prompt
3. Se till att behålla dina egna lokala anpassningar

### Alternativ 2: Git merge
```bash
# Se vad som ändrats
git diff origin/claude/remove-hardcoded-weather-agent surfsense_backend/app/agents/new_chat/supervisor_pipeline_prompts.py

# Merge branch
git merge origin/claude/remove-hardcoded-weather-agent

# Lös eventuella konflikter
```

### Alternativ 3: Cherry-pick specifika ändringar
```bash
# Se commit-historiken
git log origin/claude/remove-hardcoded-weather-agent

# Cherry-pick specifik commit (om du hittar en som bara ändrar prompter)
git cherry-pick <commit-hash>
```

---

## Testning

Kör testerna för att verifiera att ändringarna fungerar:

```bash
cd surfsense_backend
python tests/test_mixed_domain_routing.py
```

Alla 4 tester ska passera:
- ✓ test_mixed_weather_statistics_does_not_lock_to_weather
- ✓ test_pure_weather_query_still_routes_to_action
- ✓ test_weather_agent_limit_not_forced_to_1
- ✓ test_weather_cache_not_invalidated_for_mixed_query

---

## Exempel på mixade frågor som nu fungerar

- "Hur många bor i Göteborg och vad är det för väder?"
- "Ge mig statistik om befolkning i Stockholm och aktuell trafikinfo"
- "Sök företag i Malmö och visa vädret där"

Systemet kommer nu:
1. Identifiera båda domänerna (route="mixed", sub_intents=["statistics", "weather"])
2. Välja flera agenter (en per domain)
3. Skapa parallella exekveringssteg
4. Verifiera att alla sub_intents tackts
5. Strukturera svaret i tydliga sektioner
