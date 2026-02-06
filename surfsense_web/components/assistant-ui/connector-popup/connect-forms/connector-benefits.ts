/**
 * Helper function to get connector-specific benefits list
 * Returns null if no benefits are defined for the connector
 */
export function getConnectorBenefits(connectorType: string): string[] | null {
	const benefits: Record<string, string[]> = {
		LINEAR_CONNECTOR: [
			"Sök i alla dina Linear-ärenden och kommentarer",
			"Få tillgång till ärendetitlar, beskrivningar och fullständiga diskussionstrådar",
			"Anslut teamets projektledning direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste Linear-innehållet",
			"Indexera dina Linear-ärenden för förbättrade sökmöjligheter",
		],
		ELASTICSEARCH_CONNECTOR: [
			"Sök i dina indexerade dokument och loggar",
			"Få tillgång till strukturerad och ostrukturerad data från ditt kluster",
			"Utnyttja befintliga Elasticsearch-index för förbättrad sökning",
			"Sökning i realtid med kraftfulla frågefunktioner",
			"Integration med din befintliga Elasticsearch-infrastruktur",
		],
		TAVILY_API: [
			"AI-drivna sökresultat anpassade efter dina frågor",
			"Information i realtid från webben",
			"Förbättrade sökmöjligheter för dina projekt",
		],
		SEARXNG_API: [
			"Integritetsfokuserad metasökning över flera sökmotorer",
			"Självhostad sökinstans för full kontroll",
			"Sökresultat i realtid från flera källor",
		],
		LINKUP_API: [
			"AI-drivna sökresultat anpassade efter dina frågor",
			"Information i realtid från webben",
			"Förbättrade sökmöjligheter för dina projekt",
		],
		BAIDU_SEARCH_API: [
			"Intelligent sökning anpassad för kinesiskt webbinnehåll",
			"Information i realtid från Baidus sökindex",
			"AI-driven sammanfattning med källreferenser",
		],
		SLACK_CONNECTOR: [
			"Sök i alla dina Slack-meddelanden och konversationer",
			"Få tillgång till meddelanden från offentliga och privata kanaler",
			"Anslut teamets kommunikation direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste Slack-innehållet",
			"Indexera dina Slack-konversationer för förbättrade sökmöjligheter",
		],
		DISCORD_CONNECTOR: [
			"Sök i alla dina Discord-meddelanden och konversationer",
			"Få tillgång till meddelanden från alla åtkomliga kanaler",
			"Anslut communityns kommunikation direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste Discord-innehållet",
			"Indexera dina Discord-konversationer för förbättrade sökmöjligheter",
		],
		NOTION_CONNECTOR: [
			"Sök i alla dina Notion-sidor och databaser",
			"Få tillgång till sidinnehåll, egenskaper och metadata",
			"Anslut din kunskapsbas direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste Notion-innehållet",
			"Indexera din Notion-arbetsyta för förbättrade sökmöjligheter",
		],
		CONFLUENCE_CONNECTOR: [
			"Sök i alla dina Confluence-sidor och utrymmen",
			"Få tillgång till sidinnehåll, kommentarer och bilagor",
			"Anslut teamets dokumentation direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste Confluence-innehållet",
			"Indexera din Confluence-arbetsyta för förbättrade sökmöjligheter",
		],
		BOOKSTACK_CONNECTOR: [
			"Sök i alla dina BookStack-sidor och böcker",
			"Få tillgång till sidinnehåll, kapitel och dokumentation",
			"Anslut din dokumentation direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste BookStack-innehållet",
			"Indexera din BookStack-instans för förbättrade sökmöjligheter",
		],
		GITHUB_CONNECTOR: [
			"Sök i kod, ärenden och dokumentation från GitHub-repositories",
			"Få tillgång till repository-innehåll, pull requests och diskussioner",
			"Anslut din kodbas direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste GitHub-innehållet",
			"Indexera dina GitHub-repositories för förbättrade sökmöjligheter",
		],
		JIRA_CONNECTOR: [
			"Sök i alla dina Jira-ärenden och biljetter",
			"Få tillgång till ärendebeskrivningar, kommentarer och projektdata",
			"Anslut din projektledning direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste Jira-innehållet",
			"Indexera dina Jira-projekt för förbättrade sökmöjligheter",
		],
		CLICKUP_CONNECTOR: [
			"Sök i alla dina ClickUp-uppgifter och projekt",
			"Få tillgång till uppgiftsbeskrivningar, kommentarer och projektdata",
			"Anslut din uppgiftshantering direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste ClickUp-innehållet",
			"Indexera din ClickUp-arbetsyta för förbättrade sökmöjligheter",
		],
		LUMA_CONNECTOR: [
			"Sök i alla dina Luma-evenemang",
			"Få tillgång till evenemangsdetaljer, beskrivningar och deltagarinformation",
			"Anslut dina evenemang direkt till ditt sökutrymme",
			"Håll dina sökresultat uppdaterade med det senaste Luma-innehållet",
			"Indexera dina Luma-evenemang för förbättrade sökmöjligheter",
		],
		CIRCLEBACK_CONNECTOR: [
			"Ta emot mötesanteckningar, transkriptioner och åtgärdspunkter automatiskt",
			"Få tillgång till mötesdetaljer, deltagare och insikter",
			"Sök i alla dina Circleback-mötesposter",
			"Uppdateringar i realtid via webhook-integration",
			"Ingen manuell indexering krävs - möten läggs till automatiskt",
		],
		OBSIDIAN_CONNECTOR: [
			"Sök i alla dina Obsidian-anteckningar och din kunskapsbas",
			"Få tillgång till anteckningsinnehåll med YAML-frontmatter-metadata bevarad",
			"Wiki-länkar ([[note]]) och #taggar indexeras",
			"Anslut din personliga kunskapsbas direkt till ditt sökutrymme",
			"Inkrementell synk - endast ändrade filer indexeras om",
			"Fullt stöd för ditt valvs mappstruktur",
		],
	};

	return benefits[connectorType] || null;
}
