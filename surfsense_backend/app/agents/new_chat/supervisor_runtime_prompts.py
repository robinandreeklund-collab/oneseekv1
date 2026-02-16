DEFAULT_SUPERVISOR_CRITIC_PROMPT = (
    "Du ar en kritisk granskare. Bedom om svaret ar komplett och korrekt. "
    'Svara kort i JSON med {"status": "ok"|"needs_more", "reason": "..."}.' 
)


DEFAULT_SUPERVISOR_LOOP_GUARD_MESSAGE = (
    "Jag fastnade i en planeringsloop och avbryter for att ge ett stabilt svar.\n"
    "{recent_preview}\n"
    "Skicka garna fragan igen sa kor jag en strikt enkel exekvering med fa agentsteg."
)


DEFAULT_SUPERVISOR_TOOL_LIMIT_GUARD_MESSAGE = (
    "Jag avbryter denna korning for att undvika for manga verktygssteg i rad.\n"
    "Skicka garna fragan igen med en kortare avgransning sa svarar jag direkt.\n"
    "{recent_preview}"
)


DEFAULT_SUPERVISOR_TRAFIK_ENFORCEMENT_MESSAGE = (
    "Du maste anvanda retrieve_tools och sedan minst ett trafikverket_* verktyg innan du svarar."
)


DEFAULT_SUPERVISOR_CODE_SANDBOX_ENFORCEMENT_MESSAGE = (
    "Du maste anvanda sandbox_* verktyg for filsystemsuppgifter innan du svarar. "
    "Verifiera resultat med ett efterfoljande read/list-steg nar det ar relevant."
)
