import { useQuery } from "@tanstack/react-query";
import { useAtomValue } from "jotai";
import { useMemo } from "react";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import type { ToolLifecycleStatusResponse } from "@/contracts/types/admin-tool-lifecycle.types";
import type { ToolMetadataItem } from "@/contracts/types/admin-tool-settings.types";
import { adminToolLifecycleApiService } from "@/lib/apis/admin-tool-lifecycle-api.service";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";

// ---------------------------------------------------------------------------
// Domain grouping
// ---------------------------------------------------------------------------

export interface DomainGroup {
	domain: string;
	label: string;
	tools: ToolWithLifecycle[];
	liveCount: number;
	reviewCount: number;
	avgSuccessRate: number | null;
}

export interface ToolWithLifecycle extends ToolMetadataItem {
	lifecycle: ToolLifecycleStatusResponse | null;
}

const DOMAIN_LABELS: Record<string, string> = {
	weather: "Väder",
	politik: "Politik & Riksdag",
	statistics: "Statistik",
	transport: "Transport & Trafik",
	marketplace: "Marknadsplats",
	education: "Utbildning",
	company: "Bolag & Företag",
	knowledge: "Kunskapsbas",
	web: "Webb & Sökning",
	media: "Media & Podcast",
	code: "Kod & Sandbox",
	compare: "Jämförelse",
	memory: "Minne",
	general: "Övrigt",
};

function categorizeTool(tool: ToolMetadataItem): string {
	const id = tool.tool_id.toLowerCase();
	const cat = (tool.category || "").toLowerCase();

	if (id.startsWith("smhi_") || cat.includes("weather") || cat.includes("väder")) return "weather";
	if (id.startsWith("riksdag_")) return "politik";
	if (id.startsWith("scb_") || id.startsWith("kolada_") || cat.includes("statist"))
		return "statistics";
	if (
		id.startsWith("trafikverket_") ||
		id.startsWith("trafiklab") ||
		cat.includes("trafik") ||
		cat.includes("transport")
	)
		return "transport";
	if (id.startsWith("marketplace_")) return "marketplace";
	if (id.startsWith("skolverket_") || cat.includes("utbild") || cat.includes("skol"))
		return "education";
	if (id.startsWith("bolagsverket_") || cat.includes("bolag")) return "company";
	if (id.includes("knowledge_base") || id.includes("surfsense_docs")) return "knowledge";
	if (
		id.includes("tavily") ||
		id.includes("scrape") ||
		id.includes("link_preview") ||
		id === "search_web"
	)
		return "web";
	if (id.includes("podcast") || id.includes("display_image") || id.includes("geoapify"))
		return "media";
	if (id.startsWith("sandbox_") || id === "list_directory") return "code";
	if (id.startsWith("call_") || cat.includes("compare") || cat.includes("jämför")) return "compare";
	if (id.includes("memory")) return "memory";
	return "general";
}

function buildDomainGroups(
	tools: ToolMetadataItem[],
	lifecycleMap: Record<string, ToolLifecycleStatusResponse>
): DomainGroup[] {
	const groups: Record<string, ToolWithLifecycle[]> = {};

	for (const tool of tools) {
		const domain = categorizeTool(tool);
		if (!groups[domain]) groups[domain] = [];
		groups[domain].push({
			...tool,
			lifecycle: lifecycleMap[tool.tool_id] ?? null,
		});
	}

	// Sort domains by predefined order
	const domainOrder = Object.keys(DOMAIN_LABELS);

	return domainOrder
		.filter((domain) => groups[domain]?.length)
		.map((domain) => {
			const domainTools = groups[domain];
			const liveCount = domainTools.filter((t) => t.lifecycle?.status === "live").length;
			const reviewCount = domainTools.length - liveCount;
			const rates = domainTools
				.map((t) => t.lifecycle?.success_rate)
				.filter((r): r is number => r != null);
			const avgSuccessRate =
				rates.length > 0 ? rates.reduce((a, b) => a + b, 0) / rates.length : null;

			return {
				domain,
				label: DOMAIN_LABELS[domain] ?? domain,
				tools: domainTools.sort((a, b) => a.tool_id.localeCompare(b.tool_id)),
				liveCount,
				reviewCount,
				avgSuccessRate,
			};
		});
}

// ---------------------------------------------------------------------------
// Main hook
// ---------------------------------------------------------------------------

export function useToolCatalog(searchSpaceId?: number) {
	const { data: currentUser } = useAtomValue(currentUserAtom);

	const settingsQuery = useQuery({
		queryKey: ["admin-tool-settings", searchSpaceId],
		queryFn: () => adminToolSettingsApiService.getToolSettings(searchSpaceId),
		enabled: !!currentUser,
		staleTime: 30_000,
	});

	const lifecycleQuery = useQuery({
		queryKey: ["admin-tool-lifecycle"],
		queryFn: () => adminToolLifecycleApiService.getToolLifecycleList(),
		enabled: !!currentUser,
		staleTime: 30_000,
	});

	const catalogQuery = useQuery({
		queryKey: ["admin-metadata-catalog", searchSpaceId ?? settingsQuery.data?.search_space_id],
		queryFn: () =>
			adminToolSettingsApiService.getMetadataCatalog(
				searchSpaceId ?? settingsQuery.data?.search_space_id
			),
		enabled:
			!!currentUser &&
			(typeof searchSpaceId === "number" ||
				typeof settingsQuery.data?.search_space_id === "number"),
		staleTime: 30_000,
	});

	const lifecycleMap = useMemo(() => {
		const map: Record<string, ToolLifecycleStatusResponse> = {};
		if (lifecycleQuery.data?.tools) {
			for (const tool of lifecycleQuery.data.tools) {
				map[tool.tool_id] = tool;
			}
		}
		return map;
	}, [lifecycleQuery.data?.tools]);

	const allTools = useMemo(() => {
		const tools: ToolMetadataItem[] = [];
		for (const category of settingsQuery.data?.categories ?? []) {
			for (const tool of category.tools) {
				tools.push(tool);
			}
		}
		return tools;
	}, [settingsQuery.data?.categories]);

	const domainGroups = useMemo(
		() => buildDomainGroups(allTools, lifecycleMap),
		[allTools, lifecycleMap]
	);

	const retrievalTuning = settingsQuery.data?.retrieval_tuning ?? null;
	const effectiveSearchSpaceId = searchSpaceId ?? settingsQuery.data?.search_space_id;

	return {
		domainGroups,
		allTools,
		lifecycleMap,
		lifecycleData: lifecycleQuery.data,
		retrievalTuning,
		searchSpaceId: effectiveSearchSpaceId,
		catalogData: catalogQuery.data,
		metadataVersionHash: settingsQuery.data?.metadata_version_hash,
		latestEvaluation: settingsQuery.data?.latest_evaluation,
		isLoading: settingsQuery.isLoading || lifecycleQuery.isLoading,
		error: settingsQuery.error || lifecycleQuery.error,
		refetch: async () => {
			await Promise.all([
				settingsQuery.refetch(),
				lifecycleQuery.refetch(),
				catalogQuery.refetch(),
			]);
		},
	};
}

// ---------------------------------------------------------------------------
// Utility exports
// ---------------------------------------------------------------------------

export function formatPercent(value: number | null | undefined): string {
	if (value == null || Number.isNaN(value)) return "-";
	return `${(value * 100).toFixed(1)}%`;
}

export function formatSignedPercent(value: number | null | undefined): string {
	if (value == null || Number.isNaN(value)) return "-";
	const sign = value > 0 ? "+" : "";
	return `${sign}${(value * 100).toFixed(1)}%`;
}

export function arraysEqual(a: string[], b: string[]): boolean {
	if (a.length !== b.length) return false;
	for (let i = 0; i < a.length; i++) {
		if (a[i] !== b[i]) return false;
	}
	return true;
}
