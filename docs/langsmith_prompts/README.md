# LangSmith Studio Prompts med Multi-Domain Support

Denna mapp innehåller de uppdaterade supervisor-promptarna med integrerat stöd för multi-domain query-hantering.

## Filen

- `updated_prompts_with_multidomain.json` - Dina anpassade LangSmith Studio-prompts med nya multi-domain funktioner inbakade

## Ändringar per Prompt

### 1. `supervisor.intent_resolver.system`

**Dina anpassningar som behållits:**
- ✅ Din svenska formulering och struktur
- ✅ Dina specifika regler för intent-analys

**Nya funktioner tillagda:**
- ✅ Rad 9-10: Weather-specifik routing till `action` route
- ✅ Rad 11-13: Stöd för `route="mixed"` vid mixade frågor med `sub_intents` array
- ✅ Rad 18: Uppdaterad route-lista inkl. `|mixed`
- ✅ Rad 19: Nytt fält `"sub_intents": ["intent1", "intent2"]` i JSON-output

**Exempel:**
```
Fråga: "hur många bor i Göteborg och vad är det för väder?"
Output: route="mixed", sub_intents=["statistics_intent", "weather_intent"]
```

---

### 2. `supervisor.agent_resolver.system`

**Dina anpassningar som behållits:**
- ✅ Din specifika formulering "Agent-ID/namn ska vara exakt samma som i kandidatlistan"
- ✅ Din regel om "Memory-verktyg FÅR ALDRIG användas som substitut"
- ✅ Din struktur med "Regler:" istället för "Uppgift:"
- ✅ Din formulering "Svara enbart med JSON i exakt detta format"

**Nya funktioner tillagda:**
- ✅ Rad 34: För mixade frågor (route="mixed" med sub_intents): välj N agenter, en per sub_intent
- ✅ Rad 39: Weather som specialiserad agent i exemplen

**Exempel:**
```
Vid route="mixed" med sub_intents=["statistics", "weather"]
→ Välj 2 agenter: ["statistics_agent", "action_agent"]
```

---

### 3. `supervisor.planner.system`

**Dina anpassningar som behållits:**
- ✅ Din detaljerade beskrivning av planering
- ✅ Ditt exempel med befolkningstillväxt
- ✅ Dina regler för steguppdelning

**Nya funktioner tillagda:**
- ✅ Rad 21: För mixade frågor: skapa parallella steg, ett per sub_intent/agent
- ✅ Rad 23-24: Explicit regel om sandbox_read_file

**Exempel:**
```
Mixad fråga: "statistik om Göteborg och väder"
Plan:
- Steg 1 (parallel): Hämta befolkningsstatistik för Göteborg
- Steg 2 (parallel): Hämta väderprogn för Göteborg
- Steg 3: Sammanställ båda svaren
```

---

### 4. `supervisor.critic_gate.system`

**Dina anpassningar som behållits:**
- ✅ Dina regler för beslut (ok/needs_more/replan)
- ✅ Din formulering om resurser som saknas

**Nya funktioner tillagda:**
- ✅ Rad 10: För mixade frågor: verifiera att alla sub_intents täckts innan "ok"

**Exempel:**
```
Vid route="mixed" med sub_intents=["statistics", "weather"]
→ Kräv att BÅDE statistik OCH väder-svaret finns innan decision="ok"
```

---

### 5. `supervisor.synthesizer.system`

**Dina anpassningar som behållits:**
- ✅ Dina regler för förfining av svar
- ✅ Din guideline om att inte uppfinna data

**Nya funktioner tillagda:**
- ✅ Rad 10: För mixade frågor: strukturera svaret i sektioner per deldomän

**Exempel:**
```
Mixad fråga ger strukturerat svar:

## Befolkningsstatistik Göteborg
[statistik-svaret här]

## Väderprogn Göteborg
[väder-svaret här]
```

---

## Hur du använder dessa prompts i LangSmith Studio

### Alternativ 1: Via Studio UI (Rekommenderat)

1. Öppna LangSmith Studio
2. Gå till **Manage Assistants** → din assistant
3. Kopiera varje prompt från `updated_prompts_with_multidomain.json`
4. Klistra in i motsvarande fält:
   - `prompt_supervisor_intent_resolver_system`
   - `prompt_supervisor_agent_resolver_system`
   - `prompt_supervisor_planner_system`
   - `prompt_supervisor_critic_gate_system`
   - `prompt_supervisor_synthesizer_system`

### Alternativ 2: Via `prompt_overrides_json`

Om du föredrar att använda JSON-override-fältet i Studio:

```json
{
  "supervisor.intent_resolver.system": "[hela prompt-texten här]",
  "supervisor.agent_resolver.system": "[hela prompt-texten här]",
  "supervisor.planner.system": "[hela prompt-texten här]",
  "supervisor.critic_gate.system": "[hela prompt-texten här]",
  "supervisor.synthesizer.system": "[hela prompt-texten här]"
}
```

### Alternativ 3: Via miljövariabel

Sätt `STUDIO_PROMPT_OVERRIDES_JSON` i din `.env`:

```bash
STUDIO_PROMPT_OVERRIDES_JSON='{"supervisor.intent_resolver.system": "...", ...}'
```

---

## Testning

Efter att du har uppdaterat promptarna i LangSmith Studio, testa med dessa frågor:

### Test 1: Mixad väder + statistik
```
Fråga: "hur många bor i Göteborg och vad är det för väder?"
Förväntat: route="mixed", sub_intents innehåller både statistik och väder
```

### Test 2: Ren väder-fråga
```
Fråga: "vad är det för väder i Stockholm?"
Förväntat: route="action" (inte mixed)
```

### Test 3: Ren statistik-fråga
```
Fråga: "hur många invånare har Malmö?"
Förväntat: route="statistics" (inte mixed)
```

### Test 4: Komplex mixad fråga
```
Fråga: "ge mig statistik om befolkning i Stockholm och aktuell trafikinfo"
Förväntat: route="mixed", väljer både statistics_agent och trafik_agent, parallella steg
```

---

## Sammanfattning av fördelar

Med dessa uppdaterade prompts får du:

1. ✅ **Multi-domain support** - Hanterar frågor som spänner över flera domäner
2. ✅ **Parallell exekvering** - Flera agenter kan köra samtidigt för mixade frågor
3. ✅ **Strukturerade svar** - Tydliga sektioner per deldomän i slutsvaret
4. ✅ **Weather inte längre hårdkodad** - Behandlas som vilken domän som helst
5. ✅ **Dina anpassningar bevarade** - All din customization är intakt

---

## Support

Om något inte fungerar som förväntat, kontrollera:

1. Att alla 5 promptar är uppdaterade i Studio
2. Att JSON-syntaxen är giltig i svaren
3. Att `sub_intents` array inkluderas när route="mixed"
4. Att planner skapar parallella steg för mixade frågor
