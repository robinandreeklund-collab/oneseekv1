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


DEFAULT_SUPERVISOR_CODE_READ_FILE_ENFORCEMENT_MESSAGE = (
    "Du maste anvanda sandbox_read_file for att lasa filinnehall innan du sammanfattar resultatet."
)


DEFAULT_SUPERVISOR_SCOPED_TOOL_PROMPT_TEMPLATE = (
    "[SCOPED TOOL PROMPT]\n"
    "Fokusera pa dessa mest relevanta verktyg/kategorier for uppgiften:\n"
    "{tool_lines}\n"
    "Anvand i forsta hand ett av ovanstaende verktyg och hall argumenten strikt till valt verktygs schema.\n"
    "Om inget av dessa verktyg passar uppgiften: kor retrieve_tools igen med forfinad intent innan fortsattning."
)


DEFAULT_SUPERVISOR_TOOL_DEFAULT_PROMPT_TEMPLATE = (
    "[TOOL-SPECIFIC PROMPT: {tool_id}]\n"
    "Kategori: {category}\n"
    "Beskrivning: {description}\n"
    "Nyckelord: {keywords}\n"
    "Anvand endast detta verktyg om uppgiften matchar dess doman.\n"
    "Matcha argument strikt mot verktygets schema och undvik overflodiga falt.\n"
    "Vid saknade kravfalt: stall en kort, exakt forfragan om komplettering.\n"
    "Om uppgiften byter amne eller inte matchar domanen: gor ny retrieve_tools innan nasta verktygsval."
)


DEFAULT_SUPERVISOR_SUBAGENT_CONTEXT_TEMPLATE = (
    "<subagent_context>\n{subagent_context_lines}\n</subagent_context>\n\n{task}"
)
