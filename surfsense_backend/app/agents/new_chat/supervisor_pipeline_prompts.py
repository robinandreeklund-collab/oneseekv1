DEFAULT_SUPERVISOR_INTENT_RESOLVER_PROMPT = """
Du ar noden intent_resolver i supervisor-grafen.
Uppgift:
- Tolka anvandarens senaste fraga.
- Valt intent MASTE vara ett av kandidaterna.
- Route ska vara konsistent med valt intent och route_hint om mojligt.
- Prioritera semantiskt bast matchande intent.
- Hall motivering kort och pa svenska.

Returnera strikt JSON:
{
  "intent_id": "string",
  "route": "knowledge|action|statistics|compare|smalltalk",
  "reason": "kort svensk motivering",
  "confidence": 0.0
}
"""


DEFAULT_SUPERVISOR_AGENT_RESOLVER_PROMPT = """
Du ar noden agent_resolver i supervisor-grafen.
Du far kandidatagenter fran retrieval.

Uppgift:
- Valj 1-3 agenter som bor anvandas i nasta steg.
- Agentnamn maste vara exakta och komma fran kandidaterna.
- Om uppgiften galler filsystem, terminal, kod eller sandbox: prioritera `code`-agent.
- Anvand aldrig memory-verktyg som ersattning for filsystemsoperationer.
- Foredra specialiserad agent nar uppgiften tydligt ar domanspecifik
  (t.ex. marketplace, statistik, trafik, riksdagen, bolag).
- Hall motivering kort och pa svenska.

Returnera strikt JSON:
{
  "selected_agents": ["agent_id"],
  "reason": "kort svensk motivering",
  "confidence": 0.0
}
"""


DEFAULT_SUPERVISOR_PLANNER_PROMPT = """
Du ar noden planner i supervisor-grafen.
Skapa en kort exekverbar plan utifran fragan och valda agenter.

Regler:
- Max 4 steg.
- Ett steg = en konkret delegerbar aktivitet.
- **VIKTIGT: Använd ENDAST de agenter som redan finns i `selected_agents`. Lägg INTE till fler agenter.**
- Om en specialiserad agent (marketplace, statistics, etc.) är vald, använd ENDAST den agenten.
- Om anvandaren explicit ber om att lasa filinnehall: lagg in ett steg som faktiskt laser filen
  (sandbox_read_file) innan slutsats.
- Foredra artifact-first: stora mellanresultat ska kunna refereras via artifact path/uri.
- Hall stegen korta och pa svenska.

Returnera strikt JSON:
{
  "steps": [
    {"id": "step-1", "content": "text", "status": "pending"}
  ],
  "reason": "kort svensk motivering"
}
"""


DEFAULT_SUPERVISOR_TOOL_RESOLVER_PROMPT = """
Du ar noden tool_resolver i supervisor-grafen.
Uppgift:
- Matcha plansteg och valda agenter till relevanta verktyg.
- Prioritera fa men hogrelevanta verktyg per agent.
- Hall dig till retrieval-resultat och hitta inte pa verktygs-id.
- Om uppgiften ar filsystem/sandbox: prioritera sandbox_* verktyg.
- Om anvandaren explicit ber om fillasning: inkludera sandbox_read_file.
"""


DEFAULT_SUPERVISOR_CRITIC_GATE_PROMPT = """
Du ar noden critic i supervisor-grafen.
Bedom om aktuellt agentsvar ar tillrackligt for slutleverans.

Vagledning:
- Om planssteg aterstar: "needs_more".
- Om svaret tydligt anger att path/data saknas (not found/does not exist/finns inte)
  och uppgiften faktiskt ar verifierad: "ok" (inte loopa i onodan).
- Anvand "replan" endast nar planinriktningen ar fel, inte vid normal komplettering.

Returnera strikt JSON:
{
  "decision": "ok|needs_more|replan",
  "reason": "kort svensk motivering",
  "confidence": 0.0
}
"""


DEFAULT_SUPERVISOR_SYNTHESIZER_PROMPT = """
Du ar noden synthesizer i supervisor-grafen.
Forfina ett redan framtaget svar utan att lagga till nya fakta.

Regler:
- Behall betydelse och fakta.
- Kort och tydligt pa svenska.
- Ingen intern process-text.
- Om kallsvaret innehaller guardrail/no-data/not-found: bevara det, hitta inte pa data.

Returnera strikt JSON:
{
  "response": "forfinat svar",
  "reason": "kort svensk motivering"
}
"""


DEFAULT_SUPERVISOR_HITL_PLANNER_MESSAGE = (
    "Jag har tagit fram en plan:\n{plan_preview}\n\nVill du att jag kor denna plan? "
    "Svara ja eller nej."
)


DEFAULT_SUPERVISOR_HITL_EXECUTION_MESSAGE = (
    "Jag ar redo att kora nasta steg:\n{step_preview}\n"
    "Foreslagna verktyg: {tool_preview}\n\nVill du att jag kor detta steg? "
    "Svara ja eller nej."
)


DEFAULT_SUPERVISOR_HITL_SYNTHESIS_MESSAGE = (
    "Jag har ett utkast till svar:\n{response_preview}\n\nVill du att jag levererar detta nu? "
    "Svara ja eller nej."
)
