"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RotateCcw, Save, X } from "lucide-react";
import { toast } from "sonner";

import {
	type AgentMetadataItem,
	type AgentMetadataUpdateItem,
	type IntentMetadataItem,
	type IntentMetadataUpdateItem,
	type MetadataCatalogAuditRunResponse,
	type MetadataCatalogAuditToolRankingItem,
	type MetadataCatalogAuditSuggestionResponse,
	type ToolMetadataItem,
	type ToolMetadataUpdateItem,
} from "@/contracts/types/admin-tool-settings.types";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

function normalizeKeywordList(values: string[]) {
	const seen = new Set<string>();
	const cleaned: string[] = [];
	for (const value of values) {
		const text = value.trim();
		if (!text) continue;
		const key = text.toLocaleLowerCase();
		if (seen.has(key)) continue;
		seen.add(key);
		cleaned.push(text);
	}
	return cleaned;
}

function isEqualStringArray(left: string[], right: string[]) {
	if (left.length !== right.length) return false;
	for (let i = 0; i < left.length; i += 1) {
		if (left[i] !== right[i]) return false;
	}
	return true;
}

function toToolUpdateItem(item: ToolMetadataItem | ToolMetadataUpdateItem): ToolMetadataUpdateItem {
	return {
		tool_id: item.tool_id,
		name: item.name,
		description: item.description,
		keywords: [...item.keywords],
		example_queries: [...item.example_queries],
		category: item.category,
		base_path: item.base_path ?? null,
	};
}

function toAgentUpdateItem(
	item: AgentMetadataItem | AgentMetadataUpdateItem
): AgentMetadataUpdateItem {
	return {
		agent_id: item.agent_id,
		label: item.label,
		description: item.description,
		keywords: [...item.keywords],
		prompt_key: item.prompt_key ?? null,
		namespace: [...(item.namespace ?? [])],
	};
}

function toIntentUpdateItem(
	item: IntentMetadataItem | IntentMetadataUpdateItem
): IntentMetadataUpdateItem {
	return {
		intent_id: item.intent_id,
		label: item.label,
		route: item.route,
		description: item.description,
		keywords: [...item.keywords],
		priority: item.priority ?? 500,
		enabled: item.enabled ?? true,
	};
}

function isEqualToolMetadata(left: ToolMetadataUpdateItem, right: ToolMetadataUpdateItem) {
	return (
		left.tool_id === right.tool_id &&
		left.name === right.name &&
		left.description === right.description &&
		left.category === right.category &&
		(left.base_path ?? null) === (right.base_path ?? null) &&
		isEqualStringArray(left.keywords, right.keywords) &&
		isEqualStringArray(left.example_queries, right.example_queries)
	);
}

function isEqualAgentMetadata(left: AgentMetadataUpdateItem, right: AgentMetadataUpdateItem) {
	return (
		left.agent_id === right.agent_id &&
		left.label === right.label &&
		left.description === right.description &&
		(left.prompt_key ?? null) === (right.prompt_key ?? null) &&
		isEqualStringArray(left.keywords, right.keywords) &&
		isEqualStringArray(left.namespace ?? [], right.namespace ?? [])
	);
}

function isEqualIntentMetadata(left: IntentMetadataUpdateItem, right: IntentMetadataUpdateItem) {
	return (
		left.intent_id === right.intent_id &&
		left.label === right.label &&
		left.route === right.route &&
		left.description === right.description &&
		(left.priority ?? 500) === (right.priority ?? 500) &&
		(left.enabled ?? true) === (right.enabled ?? true) &&
		isEqualStringArray(left.keywords, right.keywords)
	);
}

function KeywordEditor({
	entityId,
	keywords,
	onChange,
	placeholder = "Nytt keyword...",
}: {
	entityId: string;
	keywords: string[];
	onChange: (nextKeywords: string[]) => void;
	placeholder?: string;
}) {
	const [newKeyword, setNewKeyword] = useState("");

	const addKeyword = () => {
		if (!newKeyword.trim()) return;
		onChange(normalizeKeywordList([...keywords, newKeyword]));
		setNewKeyword("");
	};

	const removeKeyword = (index: number) => {
		onChange(keywords.filter((_, idx) => idx !== index));
	};

	return (
		<div className="space-y-2">
			<Label>Keywords</Label>
			<div className="flex flex-wrap gap-2">
				{keywords.map((keyword, index) => (
					<Badge key={`${entityId}-kw-${index}`} variant="secondary" className="gap-1">
						{keyword}
						<button
							type="button"
							className="ml-1 hover:text-destructive"
							onClick={() => removeKeyword(index)}
							aria-label={`Ta bort keyword ${keyword}`}
						>
							<X className="h-3 w-3" />
						</button>
					</Badge>
				))}
			</div>
			<div className="flex gap-2">
				<Input
					value={newKeyword}
					onChange={(event) => setNewKeyword(event.target.value)}
					placeholder={placeholder}
					onKeyDown={(event) => {
						if (event.key === "Enter") {
							event.preventDefault();
							addKeyword();
						}
					}}
				/>
				<Button type="button" size="sm" variant="outline" onClick={addKeyword}>
					<Plus className="h-4 w-4" />
				</Button>
			</div>
		</div>
	);
}

type AuditAnnotationDraft = {
	intent_is_correct: boolean;
	corrected_intent_id: string | null;
	agent_is_correct: boolean;
	corrected_agent_id: string | null;
	tool_is_correct: boolean;
	corrected_tool_id: string | null;
};

const AUDIT_SCOPE_OPTIONS: Array<{
	id: string;
	label: string;
	prefix?: string;
}> = [
	{ id: "smhi", label: "SMHI", prefix: "smhi_" },
	{ id: "trafikverket_weather", label: "Trafikverket-vader", prefix: "trafikverket_vader_" },
	{ id: "trafikverket", label: "Trafikverket (alla)", prefix: "trafikverket_" },
	{ id: "scb", label: "SCB", prefix: "scb_" },
	{ id: "kolada", label: "Kolada", prefix: "kolada_" },
	{ id: "riksdag", label: "Riksdag", prefix: "riksdag_" },
	{ id: "marketplace", label: "Marketplace", prefix: "marketplace_" },
	{ id: "bolagsverket", label: "Bolagsverket", prefix: "bolagsverket_" },
	{ id: "all", label: "Alla tools" },
];

function parseToolIdsInput(raw: string): string[] {
	const values = raw
		.split(/[\n,; ]+/)
		.map((value) => value.trim())
		.filter(Boolean);
	const seen = new Set<string>();
	const result: string[] = [];
	for (const value of values) {
		const key = value.toLocaleLowerCase();
		if (seen.has(key)) continue;
		seen.add(key);
		result.push(value);
	}
	return result;
}

const DEFAULT_AUDIT_LOW_MARGIN_THRESHOLD = 0.3;
const DEFAULT_AUTO_TARGET_TOOL = 80;
const DEFAULT_AUTO_TARGET_INTENT = 90;
const DEFAULT_AUTO_TARGET_AGENT = 85;
const DEFAULT_AUTO_TARGET_AGENT_GIVEN_INTENT = 90;
const DEFAULT_AUTO_TARGET_TOOL_GIVEN_INTENT_AGENT = 90;

type AutoAuditTargetMode = "tool_only" | "layered";

type AutoAuditRoundEntry = {
	round: number;
	intentAccuracy: number;
	agentAccuracy: number;
	toolAccuracy: number;
	agentGivenIntentAccuracy: number | null;
	toolGivenIntentAgentAccuracy: number | null;
	vectorRecallTop5: number | null;
	vectorTop1FromVector: number | null;
	vectorExpectedInTopK: number | null;
	totalProbes: number;
	toolRankingTopK: number;
	toolRankingRows: ToolRankingSnapshotItem[];
	monitorScore: number;
	step1TotalMs: number | null;
	step1PreparationMs: number | null;
	step1ProbeGenerationMs: number | null;
	step1EvaluationMs: number | null;
	step1IntentMs: number | null;
	step1AgentMs: number | null;
	step1ToolMs: number | null;
	step2TotalMs: number | null;
	step2PreparationMs: number | null;
	step2ToolMs: number | null;
	step2IntentMs: number | null;
	step2AgentMs: number | null;
	toolSuggestions: number;
	intentSuggestions: number;
	agentSuggestions: number;
	meetsTarget: boolean;
	note: string | null;
};

type AutoEvolutionRow = {
	key: string;
	metric: string;
	older: number | null;
	newer: number | null;
	deltaPp: number | null;
	comment: string;
};

type ToolRankingSnapshotItem = {
	toolId: string;
	probes: number;
	top1Rate: number;
	topKRate: number;
	avgExpectedRank: number | null;
	avgMargin: number | null;
};

type AutoToolRankingStabilityRow = {
	toolId: string;
	probesOlder: number;
	probesNewer: number;
	rankShift: number | null;
	marginOlder: number | null;
	marginNewer: number | null;
	top1Older: number | null;
	top1Newer: number | null;
	topKOlder: number | null;
	topKNewer: number | null;
	label: "stabilt" | "instabilt" | "overkansligt" | "omdistribuerat";
};

function normalizeRate(value: number | null | undefined): number | null {
	if (typeof value !== "number" || Number.isNaN(value)) return null;
	return Math.max(0, Math.min(1, value));
}

function formatRate(value: number | null): string {
	if (value == null) return "-";
	return `${(value * 100).toFixed(1)}%`;
}

function formatDeltaPp(deltaPp: number | null): string {
	if (deltaPp == null || Number.isNaN(deltaPp)) return "--";
	const arrow = deltaPp > 0.05 ? "↑" : deltaPp < -0.05 ? "↓" : "→";
	const sign = deltaPp > 0 ? "+" : "";
	return `${arrow} ${sign}${deltaPp.toFixed(1)} pp`;
}

function formatMs(value: number | null | undefined): string {
	if (typeof value !== "number" || Number.isNaN(value)) return "-";
	return `${value.toFixed(0)} ms`;
}

function formatSigned(value: number | null | undefined, digits = 2): string {
	if (typeof value !== "number" || Number.isNaN(value)) return "--";
	const sign = value > 0 ? "+" : "";
	return `${sign}${value.toFixed(digits)}`;
}

function toToolRankingSnapshotRows(
	rows: MetadataCatalogAuditToolRankingItem[] | undefined
): ToolRankingSnapshotItem[] {
	return (rows ?? []).map((row) => ({
		toolId: row.tool_id,
		probes: Math.max(0, Number(row.probes ?? 0)),
		top1Rate:
			typeof row.top1_rate === "number" && !Number.isNaN(row.top1_rate) ? row.top1_rate : 0,
		topKRate:
			typeof row.topk_rate === "number" && !Number.isNaN(row.topk_rate) ? row.topk_rate : 0,
		avgExpectedRank:
			typeof row.avg_expected_rank === "number" && !Number.isNaN(row.avg_expected_rank)
				? row.avg_expected_rank
				: null,
		avgMargin:
			typeof row.avg_margin_vs_best_other === "number" &&
			!Number.isNaN(row.avg_margin_vs_best_other)
				? row.avg_margin_vs_best_other
				: null,
	}));
}

function summarizeDeltaComment(
	metric: string,
	older: number | null,
	newer: number | null,
	deltaPp: number | null,
	baselineOnly: boolean
): string {
	if (baselineOnly) return "Baslinje - vantar pa nasta runda.";
	if (older == null || newer == null || deltaPp == null) return "Saknar jamforbar data.";
	if (metric === "Vector recall top-5" && newer >= 0.99 && Math.abs(deltaPp) < 0.5) {
		return "Top-5 recall ar stabilt hog.";
	}
	const abs = Math.abs(deltaPp);
	if (abs < 0.3) return "Stabilt mellan rundorna.";
	if (deltaPp >= 20) return "Stark forbattring.";
	if (deltaPp >= 8) return "Tydlig forbattring.";
	if (deltaPp > 0) return "Liten forbattring.";
	if (deltaPp <= -20) return "Kraftig tillbakagang - granska senaste forslag.";
	if (deltaPp <= -8) return "Markbar tillbakagang - kontrollera senaste patch.";
	return "Liten tillbakagang.";
}

function defaultAuditAnnotationForProbe(
	probe: MetadataCatalogAuditRunResponse["probes"][number]
): AuditAnnotationDraft {
	const intentExpected = probe.intent.expected_label ?? null;
	const agentExpected = probe.agent.expected_label ?? null;
	const toolExpected = probe.tool.expected_label ?? probe.target_tool_id ?? null;
	return {
		intent_is_correct: intentExpected ? probe.intent.predicted_label === intentExpected : true,
		corrected_intent_id: intentExpected,
		agent_is_correct: agentExpected ? probe.agent.predicted_label === agentExpected : true,
		corrected_agent_id: agentExpected,
		tool_is_correct: toolExpected ? probe.tool.predicted_label === toolExpected : true,
		corrected_tool_id: toolExpected,
	};
}

function isLowMargin(margin: number | null | undefined, threshold: number): boolean {
	if (typeof margin !== "number" || Number.isNaN(margin)) return false;
	return margin < threshold;
}

function clampPercentage(value: number, fallback: number): number {
	if (!Number.isFinite(value)) return fallback;
	return Math.max(0, Math.min(100, value));
}

function layeredMonitorScore(summary: MetadataCatalogAuditRunResponse["summary"]): number {
	const values = [summary.intent_accuracy, summary.agent_accuracy, summary.tool_accuracy];
	if (typeof summary.agent_accuracy_given_intent_correct === "number") {
		values.push(summary.agent_accuracy_given_intent_correct);
	}
	if (typeof summary.tool_accuracy_given_intent_agent_correct === "number") {
		values.push(summary.tool_accuracy_given_intent_agent_correct);
	}
	if (!values.length) return 0;
	return values.reduce((acc, value) => acc + value, 0) / values.length;
}

function monitorScoreForMode(
	summary: MetadataCatalogAuditRunResponse["summary"],
	mode: AutoAuditTargetMode
): number {
	if (mode === "tool_only") return summary.tool_accuracy;
	return layeredMonitorScore(summary);
}

export function MetadataCatalogTab({ searchSpaceId }: { searchSpaceId?: number }) {
	const queryClient = useQueryClient();
	const [sectionTab, setSectionTab] = useState<"agents" | "intents" | "tools">("agents");
	const [searchTerm, setSearchTerm] = useState("");
	const [isSaving, setIsSaving] = useState(false);
	const [draftTools, setDraftTools] = useState<Record<string, ToolMetadataUpdateItem>>({});
	const [draftAgents, setDraftAgents] = useState<Record<string, AgentMetadataUpdateItem>>({});
	const [draftIntents, setDraftIntents] = useState<Record<string, IntentMetadataUpdateItem>>({});
	const [selectedAuditScopes, setSelectedAuditScopes] = useState<string[]>(["smhi"]);
	const [customAuditToolIdsInput, setCustomAuditToolIdsInput] = useState("");
	const [includeExistingExamples, setIncludeExistingExamples] = useState(true);
	const [includeLlmGenerated, setIncludeLlmGenerated] = useState(true);
	const [llmQueriesPerTool, setLlmQueriesPerTool] = useState(3);
	const [maxQueriesPerTool, setMaxQueriesPerTool] = useState(6);
	const [hardNegativesPerTool, setHardNegativesPerTool] = useState(1);
	const [probeGenerationParallelism, setProbeGenerationParallelism] = useState(1);
	const [suggestionParallelism, setSuggestionParallelism] = useState(1);
	const [auditLowMarginThreshold, setAuditLowMarginThreshold] = useState(
		DEFAULT_AUDIT_LOW_MARGIN_THRESHOLD
	);
	const [showOnlyAuditIssues, setShowOnlyAuditIssues] = useState(false);
	const [showOnlyLowMargin, setShowOnlyLowMargin] = useState(false);
	const [sortAuditIssuesFirst, setSortAuditIssuesFirst] = useState(true);
	const [autoTargetMode, setAutoTargetMode] = useState<AutoAuditTargetMode>("layered");
	const [autoTargetToolPct, setAutoTargetToolPct] = useState(DEFAULT_AUTO_TARGET_TOOL);
	const [autoTargetIntentPct, setAutoTargetIntentPct] = useState(DEFAULT_AUTO_TARGET_INTENT);
	const [autoTargetAgentPct, setAutoTargetAgentPct] = useState(DEFAULT_AUTO_TARGET_AGENT);
	const [autoTargetAgentGivenIntentPct, setAutoTargetAgentGivenIntentPct] = useState(
		DEFAULT_AUTO_TARGET_AGENT_GIVEN_INTENT
	);
	const [autoTargetToolGivenIntentAgentPct, setAutoTargetToolGivenIntentAgentPct] = useState(
		DEFAULT_AUTO_TARGET_TOOL_GIVEN_INTENT_AGENT
	);
	const [autoMaxRounds, setAutoMaxRounds] = useState(6);
	const [autoPatienceRounds, setAutoPatienceRounds] = useState(2);
	const [autoAbortDropPp, setAutoAbortDropPp] = useState(8);
	const [autoExcludeProbeHistoryBetweenRounds, setAutoExcludeProbeHistoryBetweenRounds] =
		useState(true);
	const [isAutoRunning, setIsAutoRunning] = useState(false);
	const [autoRoundHistory, setAutoRoundHistory] = useState<AutoAuditRoundEntry[]>([]);
	const [autoRunStatusText, setAutoRunStatusText] = useState<string | null>(null);
	const [isRunningAudit, setIsRunningAudit] = useState(false);
	const [auditResult, setAuditResult] = useState<MetadataCatalogAuditRunResponse | null>(null);
	const [auditAnnotations, setAuditAnnotations] = useState<Record<string, AuditAnnotationDraft>>(
		{}
	);
	const [isGeneratingAuditSuggestions, setIsGeneratingAuditSuggestions] = useState(false);
	const [auditSuggestions, setAuditSuggestions] =
		useState<MetadataCatalogAuditSuggestionResponse | null>(null);
	const [selectedAuditSuggestionToolIds, setSelectedAuditSuggestionToolIds] = useState<
		Set<string>
	>(new Set());
	const [selectedAuditSuggestionIntentIds, setSelectedAuditSuggestionIntentIds] = useState<
		Set<string>
	>(new Set());
	const [selectedAuditSuggestionAgentIds, setSelectedAuditSuggestionAgentIds] = useState<
		Set<string>
	>(new Set());

	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["admin-tool-metadata-catalog", searchSpaceId],
		queryFn: () => adminToolSettingsApiService.getMetadataCatalog(searchSpaceId),
	});

	const originalToolsById = useMemo(() => {
		const byId: Record<string, ToolMetadataItem> = {};
		for (const category of data?.tool_categories ?? []) {
			for (const tool of category.tools) {
				byId[tool.tool_id] = tool;
			}
		}
		return byId;
	}, [data?.tool_categories]);

	const originalAgentsById = useMemo(() => {
		const byId: Record<string, AgentMetadataItem> = {};
		for (const item of data?.agents ?? []) {
			byId[item.agent_id] = item;
		}
		return byId;
	}, [data?.agents]);

	const originalIntentsById = useMemo(() => {
		const byId: Record<string, IntentMetadataItem> = {};
		for (const item of data?.intents ?? []) {
			byId[item.intent_id] = item;
		}
		return byId;
	}, [data?.intents]);

	useEffect(() => {
		if (!data) return;
		const nextTools: Record<string, ToolMetadataUpdateItem> = {};
		for (const category of data.tool_categories) {
			for (const tool of category.tools) {
				nextTools[tool.tool_id] = toToolUpdateItem(tool);
			}
		}
		setDraftTools(nextTools);

		const nextAgents: Record<string, AgentMetadataUpdateItem> = {};
		for (const item of data.agents) {
			nextAgents[item.agent_id] = toAgentUpdateItem(item);
		}
		setDraftAgents(nextAgents);

		const nextIntents: Record<string, IntentMetadataUpdateItem> = {};
		for (const item of data.intents) {
			nextIntents[item.intent_id] = toIntentUpdateItem(item);
		}
		setDraftIntents(nextIntents);
	}, [data]);

	const changedToolIds = useMemo(() => {
		return Object.keys(draftTools).filter((toolId) => {
			const original = originalToolsById[toolId];
			if (!original) return false;
			return !isEqualToolMetadata(draftTools[toolId], toToolUpdateItem(original));
		});
	}, [draftTools, originalToolsById]);

	const changedAgentIds = useMemo(() => {
		return Object.keys(draftAgents).filter((agentId) => {
			const original = originalAgentsById[agentId];
			if (!original) return false;
			return !isEqualAgentMetadata(draftAgents[agentId], toAgentUpdateItem(original));
		});
	}, [draftAgents, originalAgentsById]);

	const changedIntentIds = useMemo(() => {
		return Object.keys(draftIntents).filter((intentId) => {
			const original = originalIntentsById[intentId];
			if (!original) return false;
			return !isEqualIntentMetadata(draftIntents[intentId], toIntentUpdateItem(original));
		});
	}, [draftIntents, originalIntentsById]);

	const changedToolSet = useMemo(() => new Set(changedToolIds), [changedToolIds]);
	const changedAgentSet = useMemo(() => new Set(changedAgentIds), [changedAgentIds]);
	const changedIntentSet = useMemo(() => new Set(changedIntentIds), [changedIntentIds]);
	const metadataPatchForDraft = useMemo(() => {
		return changedToolIds.map((toolId) => draftTools[toolId]).filter(Boolean);
	}, [changedToolIds, draftTools]);
	const intentMetadataPatchForDraft = useMemo(() => {
		return changedIntentIds
			.map((intentId) => draftIntents[intentId])
			.filter((item): item is IntentMetadataUpdateItem => Boolean(item));
	}, [changedIntentIds, draftIntents]);
	const agentMetadataPatchForDraft = useMemo(() => {
		return changedAgentIds
			.map((agentId) => draftAgents[agentId])
			.filter((item): item is AgentMetadataUpdateItem => Boolean(item));
	}, [changedAgentIds, draftAgents]);
	const allToolOptions = useMemo(() => {
		const options: string[] = [];
		for (const category of data?.tool_categories ?? []) {
			for (const tool of category.tools) {
				options.push(tool.tool_id);
			}
		}
		return options.sort((left, right) => left.localeCompare(right, "sv"));
	}, [data?.tool_categories]);
	const customAuditToolIds = useMemo(
		() => parseToolIdsInput(customAuditToolIdsInput),
		[customAuditToolIdsInput]
	);
	const hasAllScopeSelected = useMemo(
		() => selectedAuditScopes.includes("all"),
		[selectedAuditScopes]
	);
	const scopeDerivedAuditToolIds = useMemo(() => {
		if (hasAllScopeSelected) return [];
		const scopePrefixes = AUDIT_SCOPE_OPTIONS.filter((option) =>
			selectedAuditScopes.includes(option.id)
		)
			.map((option) => option.prefix)
			.filter((value): value is string => typeof value === "string" && value.length > 0);
		if (!scopePrefixes.length) return [];
		return allToolOptions.filter((toolId) => {
			const normalizedToolId = toolId.toLocaleLowerCase();
			return scopePrefixes.some((prefix) => normalizedToolId.startsWith(prefix));
		});
	}, [hasAllScopeSelected, selectedAuditScopes, allToolOptions]);
	const requestedAuditToolIds = useMemo(() => {
		if (hasAllScopeSelected && customAuditToolIds.length === 0) return [];
		const ordered: string[] = [];
		const seen = new Set<string>();
		for (const toolId of [...scopeDerivedAuditToolIds, ...customAuditToolIds]) {
			const normalized = toolId.toLocaleLowerCase();
			if (seen.has(normalized)) continue;
			seen.add(normalized);
			ordered.push(toolId);
		}
		return ordered.sort((left, right) => left.localeCompare(right, "sv"));
	}, [hasAllScopeSelected, scopeDerivedAuditToolIds, customAuditToolIds]);
	const auditToolOptions = useMemo(
		() =>
			(auditResult?.available_tool_ids?.length
				? auditResult.available_tool_ids
				: allToolOptions
			).slice().sort((left, right) => left.localeCompare(right, "sv")),
		[auditResult?.available_tool_ids, allToolOptions]
	);
	const auditIntentOptions = useMemo(
		() =>
			(auditResult?.available_intent_ids?.length
				? auditResult.available_intent_ids
				: (data?.intents ?? []).map((item) => item.intent_id)
			).slice().sort((left, right) => left.localeCompare(right, "sv")),
		[auditResult?.available_intent_ids, data?.intents]
	);
	const auditAgentOptions = useMemo(
		() =>
			(auditResult?.available_agent_ids?.length
				? auditResult.available_agent_ids
				: (data?.agents ?? []).map((item) => item.agent_id)
			).slice().sort((left, right) => left.localeCompare(right, "sv")),
		[auditResult?.available_agent_ids, data?.agents]
	);
	const selectedToolSuggestions = useMemo(() => {
		const list = auditSuggestions?.tool_suggestions ?? [];
		return list.filter((item) => selectedAuditSuggestionToolIds.has(item.tool_id));
	}, [auditSuggestions?.tool_suggestions, selectedAuditSuggestionToolIds]);
	const selectedIntentSuggestions = useMemo(() => {
		const list = auditSuggestions?.intent_suggestions ?? [];
		return list.filter((item) => selectedAuditSuggestionIntentIds.has(item.intent_id));
	}, [auditSuggestions?.intent_suggestions, selectedAuditSuggestionIntentIds]);
	const selectedAgentSuggestions = useMemo(() => {
		const list = auditSuggestions?.agent_suggestions ?? [];
		return list.filter((item) => selectedAuditSuggestionAgentIds.has(item.agent_id));
	}, [auditSuggestions?.agent_suggestions, selectedAuditSuggestionAgentIds]);
	const auditProbeRows = useMemo(() => {
		if (!auditResult) return [];
		return auditResult.probes.map((probe) => {
			const annotation = auditAnnotations[probe.probe_id] ?? defaultAuditAnnotationForProbe(probe);
			const intentExpected = probe.intent.expected_label ?? null;
			const agentExpected = probe.agent.expected_label ?? null;
			const toolExpected = probe.tool.expected_label ?? probe.target_tool_id ?? null;
			const intentCorrect = intentExpected
				? probe.intent.predicted_label === intentExpected
				: true;
			const agentCorrect = agentExpected ? probe.agent.predicted_label === agentExpected : true;
			const toolCorrect = toolExpected ? probe.tool.predicted_label === toolExpected : true;
			const intentLowMargin = isLowMargin(probe.intent.margin, auditLowMarginThreshold);
			const agentLowMargin = isLowMargin(probe.agent.margin, auditLowMarginThreshold);
			const toolLowMargin = isLowMargin(probe.tool.margin, auditLowMarginThreshold);
			const hasAnyError = !intentCorrect || !agentCorrect || !toolCorrect;
			const hasAnyLowMargin = intentLowMargin || agentLowMargin || toolLowMargin;
			const severityScore =
				(toolCorrect ? 0 : 120) +
				(agentCorrect ? 0 : 80) +
				(intentCorrect ? 0 : 60) +
				(toolLowMargin ? 20 : 0) +
				(agentLowMargin ? 14 : 0) +
				(intentLowMargin ? 10 : 0);
			return {
				probe,
				annotation,
				intentCorrect,
				agentCorrect,
				toolCorrect,
				intentLowMargin,
				agentLowMargin,
				toolLowMargin,
				hasAnyError,
				hasAnyLowMargin,
				severityScore,
			};
		});
	}, [auditResult, auditAnnotations, auditLowMarginThreshold]);
	const auditIssueSummary = useMemo(() => {
		let intentErrors = 0;
		let agentErrors = 0;
		let toolErrors = 0;
		let intentLowMargins = 0;
		let agentLowMargins = 0;
		let toolLowMargins = 0;
		let probesWithAnyError = 0;
		for (const row of auditProbeRows) {
			if (!row.intentCorrect) intentErrors += 1;
			if (!row.agentCorrect) agentErrors += 1;
			if (!row.toolCorrect) toolErrors += 1;
			if (row.intentLowMargin) intentLowMargins += 1;
			if (row.agentLowMargin) agentLowMargins += 1;
			if (row.toolLowMargin) toolLowMargins += 1;
			if (row.hasAnyError) probesWithAnyError += 1;
		}
		return {
			totalProbes: auditProbeRows.length,
			probesWithAnyError,
			intentErrors,
			agentErrors,
			toolErrors,
			intentLowMargins,
			agentLowMargins,
			toolLowMargins,
		};
	}, [auditProbeRows]);
	const visibleAuditProbeRows = useMemo(() => {
		let rows = auditProbeRows;
		if (showOnlyAuditIssues) {
			rows = rows.filter((row) => row.hasAnyError);
		}
		if (showOnlyLowMargin) {
			rows = rows.filter((row) => row.hasAnyLowMargin);
		}
		const sorted = [...rows];
		if (sortAuditIssuesFirst) {
			sorted.sort((left, right) => {
				if (left.severityScore !== right.severityScore) {
					return right.severityScore - left.severityScore;
				}
				return left.probe.query.localeCompare(right.probe.query, "sv");
			});
		}
		return sorted;
	}, [auditProbeRows, showOnlyAuditIssues, showOnlyLowMargin, sortAuditIssuesFirst]);
	const autoTargets = useMemo(
		() => ({
			tool: clampPercentage(autoTargetToolPct, DEFAULT_AUTO_TARGET_TOOL) / 100,
			intent: clampPercentage(autoTargetIntentPct, DEFAULT_AUTO_TARGET_INTENT) / 100,
			agent: clampPercentage(autoTargetAgentPct, DEFAULT_AUTO_TARGET_AGENT) / 100,
			agentGivenIntent:
				clampPercentage(
					autoTargetAgentGivenIntentPct,
					DEFAULT_AUTO_TARGET_AGENT_GIVEN_INTENT
				) / 100,
			toolGivenIntentAgent:
				clampPercentage(
					autoTargetToolGivenIntentAgentPct,
					DEFAULT_AUTO_TARGET_TOOL_GIVEN_INTENT_AGENT
				) / 100,
		}),
		[
			autoTargetToolPct,
			autoTargetIntentPct,
			autoTargetAgentPct,
			autoTargetAgentGivenIntentPct,
			autoTargetToolGivenIntentAgentPct,
		]
	);
	const currentAutoMonitorScore = useMemo(() => {
		if (!auditResult) return 0;
		return monitorScoreForMode(auditResult.summary, autoTargetMode);
	}, [auditResult, autoTargetMode]);
	const autoEvolutionSummary = useMemo(() => {
		if (!autoRoundHistory.length) {
			return null;
		}
		const olderRound = autoRoundHistory[0];
		const newerRound = autoRoundHistory[autoRoundHistory.length - 1];
		const baselineOnly = olderRound.round === newerRound.round;
		const rowsSeed: Array<{
			key: string;
			metric: string;
			older: number | null | undefined;
			newer: number | null | undefined;
		}> = [
			{
				key: "intent",
				metric: "Intent accuracy",
				older: olderRound.intentAccuracy,
				newer: newerRound.intentAccuracy,
			},
			{
				key: "agent",
				metric: "Agent accuracy",
				older: olderRound.agentAccuracy,
				newer: newerRound.agentAccuracy,
			},
			{
				key: "tool",
				metric: "Tool accuracy",
				older: olderRound.toolAccuracy,
				newer: newerRound.toolAccuracy,
			},
			{
				key: "agent_given_intent",
				metric: "Agent | Intent OK",
				older: olderRound.agentGivenIntentAccuracy,
				newer: newerRound.agentGivenIntentAccuracy,
			},
			{
				key: "tool_given_intent_agent",
				metric: "Tool | Intent+Agent OK",
				older: olderRound.toolGivenIntentAgentAccuracy,
				newer: newerRound.toolGivenIntentAgentAccuracy,
			},
			{
				key: "vector_recall_top5",
				metric: "Vector recall top-5",
				older: olderRound.vectorRecallTop5,
				newer: newerRound.vectorRecallTop5,
			},
			{
				key: "vector_top1_from_vector",
				metric: "Top-1 fran vector",
				older: olderRound.vectorTop1FromVector,
				newer: newerRound.vectorTop1FromVector,
			},
			{
				key: "vector_expected_top_k",
				metric: "Expected i vector@K",
				older: olderRound.vectorExpectedInTopK,
				newer: newerRound.vectorExpectedInTopK,
			},
		];
		const rows: AutoEvolutionRow[] = rowsSeed.map((seed) => {
			const older = normalizeRate(seed.older);
			const newer = normalizeRate(seed.newer);
			const deltaPp =
				!baselineOnly && older != null && newer != null ? (newer - older) * 100 : null;
			return {
				key: seed.key,
				metric: seed.metric,
				older,
				newer,
				deltaPp,
				comment: summarizeDeltaComment(seed.metric, older, newer, deltaPp, baselineOnly),
			};
		});
		return {
			olderRound: olderRound.round,
			newerRound: newerRound.round,
			olderProbes: olderRound.totalProbes,
			newerProbes: newerRound.totalProbes,
			rows,
		};
	}, [autoRoundHistory]);
	const autoToolRankingStability = useMemo(() => {
		if (autoRoundHistory.length < 2) return null;
		const olderRound = autoRoundHistory[autoRoundHistory.length - 2];
		const newerRound = autoRoundHistory[autoRoundHistory.length - 1];
		const olderByTool = new Map(olderRound.toolRankingRows.map((item) => [item.toolId, item]));
		const newerByTool = new Map(newerRound.toolRankingRows.map((item) => [item.toolId, item]));
		const toolIds = new Set<string>([...olderByTool.keys(), ...newerByTool.keys()]);
		const rows: AutoToolRankingStabilityRow[] = [];
		for (const toolId of toolIds) {
			const older = olderByTool.get(toolId);
			const newer = newerByTool.get(toolId);
			const rankShift =
				older?.avgExpectedRank != null && newer?.avgExpectedRank != null
					? newer.avgExpectedRank - older.avgExpectedRank
					: null;
			const top1Older = older?.top1Rate ?? null;
			const top1Newer = newer?.top1Rate ?? null;
			const topKOlder = older?.topKRate ?? null;
			const topKNewer = newer?.topKRate ?? null;
			const top1Delta =
				top1Older != null && top1Newer != null ? top1Newer - top1Older : null;
			const topKDelta =
				topKOlder != null && topKNewer != null ? topKNewer - topKOlder : null;
			const absShift = rankShift != null ? Math.abs(rankShift) : 0;
			let label: AutoToolRankingStabilityRow["label"] = "stabilt";
			if (rankShift != null && absShift >= 1.25 && (newer?.avgMargin ?? 0) < 0.15) {
				label = "overkansligt";
			} else if (rankShift != null && absShift >= 0.75) {
				label = "instabilt";
			} else if (
				top1Delta != null &&
				topKDelta != null &&
				top1Delta < -0.08 &&
				topKDelta > -0.02
			) {
				label = "omdistribuerat";
			}
			rows.push({
				toolId,
				probesOlder: older?.probes ?? 0,
				probesNewer: newer?.probes ?? 0,
				rankShift,
				marginOlder: older?.avgMargin ?? null,
				marginNewer: newer?.avgMargin ?? null,
				top1Older,
				top1Newer,
				topKOlder,
				topKNewer,
				label,
			});
		}
		rows.sort((left, right) => {
			const shiftLeft = Math.abs(left.rankShift ?? 0);
			const shiftRight = Math.abs(right.rankShift ?? 0);
			if (shiftRight !== shiftLeft) return shiftRight - shiftLeft;
			return right.probesNewer - left.probesNewer;
		});
		return {
			olderRound: olderRound.round,
			newerRound: newerRound.round,
			topK: Math.max(olderRound.toolRankingTopK, newerRound.toolRankingTopK, 1),
			rows,
		};
	}, [autoRoundHistory]);

	const onToolChange = (toolId: string, updates: Partial<ToolMetadataUpdateItem>) => {
		setDraftTools((previous) => {
			const current = previous[toolId];
			if (!current) return previous;
			return {
				...previous,
				[toolId]: {
					...current,
					...updates,
				},
			};
		});
	};

	const onAgentChange = (agentId: string, updates: Partial<AgentMetadataUpdateItem>) => {
		setDraftAgents((previous) => {
			const current = previous[agentId];
			if (!current) return previous;
			return {
				...previous,
				[agentId]: {
					...current,
					...updates,
				},
			};
		});
	};

	const onIntentChange = (intentId: string, updates: Partial<IntentMetadataUpdateItem>) => {
		setDraftIntents((previous) => {
			const current = previous[intentId];
			if (!current) return previous;
			return {
				...previous,
				[intentId]: {
					...current,
					...updates,
				},
			};
		});
	};

	const toggleAuditScopeSelection = (scopeId: string, selected: boolean) => {
		setSelectedAuditScopes((previous) => {
			const next = new Set(previous);
			if (selected) {
				if (scopeId === "all") {
					return ["all"];
				}
				next.delete("all");
				next.add(scopeId);
				return Array.from(next);
			}
			next.delete(scopeId);
			if (next.size === 0) {
				return ["smhi"];
			}
			return Array.from(next);
		});
	};

	const resetDrafts = () => {
		void refetch();
	};

	const saveAllMetadata = async () => {
		if (!data?.search_space_id) return;
		const tools = changedToolIds.map((toolId) => draftTools[toolId]).filter(Boolean);
		const agents = changedAgentIds
			.map((agentId) => draftAgents[agentId])
			.filter(Boolean);
		const intents = changedIntentIds
			.map((intentId) => draftIntents[intentId])
			.filter(Boolean);
		if (!tools.length && !agents.length && !intents.length) {
			toast.message("Inga metadataandringar att spara.");
			return;
		}
		setIsSaving(true);
		try {
			await adminToolSettingsApiService.updateMetadataCatalog(
				{
					tools,
					agents,
					intents,
				},
				data.search_space_id
			);
			await queryClient.invalidateQueries({
				queryKey: ["admin-tool-metadata-catalog", searchSpaceId],
			});
			await queryClient.invalidateQueries({ queryKey: ["admin-tool-settings"] });
			await refetch();
			toast.success("Metadata sparat.");
		} catch (_error) {
			toast.error("Kunde inte spara metadata.");
		} finally {
			setIsSaving(false);
		}
	};

	const runAudit = async () => {
		if (!data?.search_space_id) return;
		setIsRunningAudit(true);
		try {
			const result = await adminToolSettingsApiService.runMetadataCatalogAudit({
				search_space_id: data.search_space_id,
				metadata_patch: metadataPatchForDraft,
				intent_metadata_patch: intentMetadataPatchForDraft,
				agent_metadata_patch: agentMetadataPatchForDraft,
				tool_ids: requestedAuditToolIds,
				include_existing_examples: includeExistingExamples,
				include_llm_generated: includeLlmGenerated,
				llm_queries_per_tool: llmQueriesPerTool,
				max_queries_per_tool: maxQueriesPerTool,
				hard_negatives_per_tool: hardNegativesPerTool,
				probe_generation_parallelism: probeGenerationParallelism,
			});
			setAuditResult(result);
			const nextAnnotations: Record<string, AuditAnnotationDraft> = {};
			for (const probe of result.probes) {
				nextAnnotations[probe.probe_id] = defaultAuditAnnotationForProbe(probe);
			}
			setAuditAnnotations(nextAnnotations);
			setAuditSuggestions(null);
			setSelectedAuditSuggestionToolIds(new Set());
			setSelectedAuditSuggestionIntentIds(new Set());
			setSelectedAuditSuggestionAgentIds(new Set());
			toast.success(
				`Audit klar. ${result.summary.total_probes} probes analyserade (${formatMs(result.diagnostics?.total_ms)}).`
			);
		} catch (_error) {
			toast.error("Kunde inte kora metadata-audit.");
		} finally {
			setIsRunningAudit(false);
		}
	};

	const updateAnnotationCorrectness = (
		probeId: string,
		layer: "intent" | "agent" | "tool",
		isCorrect: boolean
	) => {
		setAuditAnnotations((previous) => {
			const current = previous[probeId] ?? {
				intent_is_correct: true,
				corrected_intent_id: null,
				agent_is_correct: true,
				corrected_agent_id: null,
				tool_is_correct: true,
				corrected_tool_id: null,
			};
			const key =
				layer === "intent"
					? "intent_is_correct"
					: layer === "agent"
						? "agent_is_correct"
						: "tool_is_correct";
			return {
				...previous,
				[probeId]: {
					...current,
					[key]: isCorrect,
				},
			};
		});
	};

	const updateAnnotationCorrectedLabel = (
		probeId: string,
		layer: "intent" | "agent" | "tool",
		correctedLabel: string
	) => {
		setAuditAnnotations((previous) => {
			const current = previous[probeId] ?? {
				intent_is_correct: true,
				corrected_intent_id: null,
				agent_is_correct: true,
				corrected_agent_id: null,
				tool_is_correct: true,
				corrected_tool_id: null,
			};
			const key =
				layer === "intent"
					? "corrected_intent_id"
					: layer === "agent"
						? "corrected_agent_id"
						: "corrected_tool_id";
			return {
				...previous,
				[probeId]: {
					...current,
					[key]: correctedLabel || null,
				},
			};
		});
	};

	const generateAuditSuggestions = async () => {
		if (!data?.search_space_id || !auditResult) return;
		const annotations = auditResult.probes.map((probe) => {
			const draft = auditAnnotations[probe.probe_id] ?? defaultAuditAnnotationForProbe(probe);
			return {
				probe_id: probe.probe_id,
				query: probe.query,
				expected_intent_id: probe.intent.expected_label ?? null,
				expected_agent_id: probe.agent.expected_label ?? null,
				expected_tool_id: probe.tool.expected_label ?? probe.target_tool_id,
				predicted_intent_id: probe.intent.predicted_label ?? null,
				predicted_agent_id: probe.agent.predicted_label ?? null,
				predicted_tool_id: probe.tool.predicted_label ?? null,
				intent_is_correct: draft.intent_is_correct,
				corrected_intent_id: draft.intent_is_correct
					? null
					: (draft.corrected_intent_id ?? probe.intent.expected_label ?? null),
				agent_is_correct: draft.agent_is_correct,
				corrected_agent_id: draft.agent_is_correct
					? null
					: (draft.corrected_agent_id ?? probe.agent.expected_label ?? null),
				tool_is_correct: draft.tool_is_correct,
				corrected_tool_id: draft.tool_is_correct
					? null
					: (draft.corrected_tool_id ??
						probe.tool.expected_label ??
						probe.target_tool_id),
				intent_score_breakdown: probe.intent.score_breakdown ?? [],
				agent_score_breakdown: probe.agent.score_breakdown ?? [],
				tool_score_breakdown: probe.tool.score_breakdown ?? [],
				tool_vector_diagnostics: probe.tool_vector_diagnostics ?? null,
			};
		});
		const reviewedFailures = annotations.filter(
			(item) =>
				!item.intent_is_correct || !item.agent_is_correct || !item.tool_is_correct
		).length;
		if (!reviewedFailures) {
			toast.message("Markera minst en probe som fel innan du genererar forslag.");
			return;
		}
		const failingAnnotations = annotations.filter(
			(item) =>
				!item.intent_is_correct || !item.agent_is_correct || !item.tool_is_correct
		);
		setIsGeneratingAuditSuggestions(true);
		try {
			const response = await adminToolSettingsApiService.generateMetadataCatalogAuditSuggestions({
				search_space_id: data.search_space_id,
				metadata_patch: metadataPatchForDraft,
				intent_metadata_patch: intentMetadataPatchForDraft,
				agent_metadata_patch: agentMetadataPatchForDraft,
				annotations: failingAnnotations,
				max_suggestions: 30,
				llm_parallelism: suggestionParallelism,
			});
			setAuditSuggestions(response);
			setSelectedAuditSuggestionToolIds(
				new Set(response.tool_suggestions.map((item) => item.tool_id))
			);
			setSelectedAuditSuggestionIntentIds(
				new Set(response.intent_suggestions.map((item) => item.intent_id))
			);
			setSelectedAuditSuggestionAgentIds(
				new Set(response.agent_suggestions.map((item) => item.agent_id))
			);
			toast.success(
				`Genererade ${response.tool_suggestions.length + response.intent_suggestions.length + response.agent_suggestions.length} metadataforslag fran ${failingAnnotations.length} felprobes (${formatMs(response.diagnostics?.total_ms)}).`
			);
		} catch (_error) {
			toast.error("Kunde inte generera metadataforslag.");
		} finally {
			setIsGeneratingAuditSuggestions(false);
		}
	};

	const runAutoAuditLoop = async () => {
		if (!data?.search_space_id) return;
		setIsAutoRunning(true);
		setAutoRoundHistory([]);
		setAutoRunStatusText("Startar autonom metadata-loop...");
		setAuditSuggestions(null);
		setSelectedAuditSuggestionToolIds(new Set());
		setSelectedAuditSuggestionIntentIds(new Set());
		setSelectedAuditSuggestionAgentIds(new Set());
		const maxRounds = Math.max(1, Math.min(20, Number.parseInt(`${autoMaxRounds}`, 10) || 1));
		const patienceRounds = Math.max(
			0,
			Math.min(10, Number.parseInt(`${autoPatienceRounds}`, 10) || 0)
		);
		const dropThreshold = Math.max(0, Math.min(50, Number.parseFloat(`${autoAbortDropPp}`) || 0)) / 100;
		const targetMode: AutoAuditTargetMode = autoTargetMode;

		const summaryMeetsTargets = (summary: MetadataCatalogAuditRunResponse["summary"]) => {
			if (targetMode === "tool_only") {
				return summary.tool_accuracy >= autoTargets.tool;
			}
			const conditionalAgentOk =
				typeof summary.agent_accuracy_given_intent_correct === "number"
					? summary.agent_accuracy_given_intent_correct >= autoTargets.agentGivenIntent
					: true;
			const conditionalToolOk =
				typeof summary.tool_accuracy_given_intent_agent_correct === "number"
					? summary.tool_accuracy_given_intent_agent_correct >= autoTargets.toolGivenIntentAgent
					: true;
			return (
				summary.intent_accuracy >= autoTargets.intent &&
				summary.agent_accuracy >= autoTargets.agent &&
				summary.tool_accuracy >= autoTargets.tool &&
				conditionalAgentOk &&
				conditionalToolOk
			);
		};

		const cloneToolPatchMap = (source: Record<string, ToolMetadataUpdateItem>) => {
			const next: Record<string, ToolMetadataUpdateItem> = {};
			for (const [toolId, item] of Object.entries(source)) {
				next[toolId] = {
					...item,
					keywords: [...item.keywords],
					example_queries: [...item.example_queries],
				};
			}
			return next;
		};
		const cloneAgentPatchMap = (source: Record<string, AgentMetadataUpdateItem>) => {
			const next: Record<string, AgentMetadataUpdateItem> = {};
			for (const [agentId, item] of Object.entries(source)) {
				next[agentId] = {
					...item,
					keywords: [...item.keywords],
					namespace: [...(item.namespace ?? [])],
				};
			}
			return next;
		};
		const cloneIntentPatchMap = (source: Record<string, IntentMetadataUpdateItem>) => {
			const next: Record<string, IntentMetadataUpdateItem> = {};
			for (const [intentId, item] of Object.entries(source)) {
				next[intentId] = {
					...item,
					keywords: [...item.keywords],
				};
			}
			return next;
		};
		const buildDefaultAnnotations = (result: MetadataCatalogAuditRunResponse) => {
			const nextAnnotations: Record<string, AuditAnnotationDraft> = {};
			for (const probe of result.probes) {
				nextAnnotations[probe.probe_id] = defaultAuditAnnotationForProbe(probe);
			}
			return nextAnnotations;
		};
		const buildAutoSuggestionAnnotations = (result: MetadataCatalogAuditRunResponse) => {
			return result.probes.map((probe) => {
				const draft = defaultAuditAnnotationForProbe(probe);
				return {
					probe_id: probe.probe_id,
					query: probe.query,
					expected_intent_id: probe.intent.expected_label ?? null,
					expected_agent_id: probe.agent.expected_label ?? null,
					expected_tool_id: probe.tool.expected_label ?? probe.target_tool_id,
					predicted_intent_id: probe.intent.predicted_label ?? null,
					predicted_agent_id: probe.agent.predicted_label ?? null,
					predicted_tool_id: probe.tool.predicted_label ?? null,
					intent_is_correct: draft.intent_is_correct,
					corrected_intent_id: draft.intent_is_correct
						? null
						: (draft.corrected_intent_id ?? probe.intent.expected_label ?? null),
					agent_is_correct: draft.agent_is_correct,
					corrected_agent_id: draft.agent_is_correct
						? null
						: (draft.corrected_agent_id ?? probe.agent.expected_label ?? null),
					tool_is_correct: draft.tool_is_correct,
					corrected_tool_id: draft.tool_is_correct
						? null
						: (draft.corrected_tool_id ??
							probe.tool.expected_label ??
							probe.target_tool_id),
					intent_score_breakdown: probe.intent.score_breakdown ?? [],
					agent_score_breakdown: probe.agent.score_breakdown ?? [],
					tool_score_breakdown: probe.tool.score_breakdown ?? [],
					tool_vector_diagnostics: probe.tool_vector_diagnostics ?? null,
				};
			});
		};

		try {
			const usedProbeQueryKeys = new Set<string>();
			let toolPatchMap: Record<string, ToolMetadataUpdateItem> = Object.fromEntries(
				metadataPatchForDraft.map((item) => [item.tool_id, { ...item }])
			);
			let intentPatchMap: Record<string, IntentMetadataUpdateItem> = Object.fromEntries(
				intentMetadataPatchForDraft.map((item) => [item.intent_id, { ...item }])
			);
			let agentPatchMap: Record<string, AgentMetadataUpdateItem> = Object.fromEntries(
				agentMetadataPatchForDraft.map((item) => [item.agent_id, { ...item }])
			);

			let bestToolPatchMap = cloneToolPatchMap(toolPatchMap);
			let bestIntentPatchMap = cloneIntentPatchMap(intentPatchMap);
			let bestAgentPatchMap = cloneAgentPatchMap(agentPatchMap);
			let bestMonitor = -1;
			let previousMonitor: number | null = null;
			let roundsWithoutImprovement = 0;
			let bestAuditResult: MetadataCatalogAuditRunResponse | null = null;
			let bestAuditAnnotations: Record<string, AuditAnnotationDraft> = {};
			const roundEntries: AutoAuditRoundEntry[] = [];
			let stopReason = "Nådde max antal rundor.";

			for (let round = 1; round <= maxRounds; round += 1) {
				setAutoRunStatusText(`Autonom loop: kör runda ${round}/${maxRounds}...`);
				const excludedProbeQueries = autoExcludeProbeHistoryBetweenRounds
					? Array.from(usedProbeQueryKeys).slice(-2500)
					: [];
				const result = await adminToolSettingsApiService.runMetadataCatalogAudit({
					search_space_id: data.search_space_id,
					metadata_patch: Object.values(toolPatchMap),
					intent_metadata_patch: Object.values(intentPatchMap),
					agent_metadata_patch: Object.values(agentPatchMap),
					tool_ids: requestedAuditToolIds,
					include_existing_examples: includeExistingExamples,
					include_llm_generated: includeLlmGenerated,
					llm_queries_per_tool: llmQueriesPerTool,
					max_queries_per_tool: maxQueriesPerTool,
					hard_negatives_per_tool: hardNegativesPerTool,
					probe_generation_parallelism: probeGenerationParallelism,
					probe_round: round,
					exclude_probe_queries: excludedProbeQueries,
				});
				if (autoExcludeProbeHistoryBetweenRounds) {
					for (const probe of result.probes) {
						const key = String(probe.query ?? "").trim().toLocaleLowerCase();
						if (key) usedProbeQueryKeys.add(key);
					}
				}
				const currentAnnotations = buildDefaultAnnotations(result);
				setAuditResult(result);
				setAuditAnnotations(currentAnnotations);
				const monitorScore = monitorScoreForMode(result.summary, targetMode);
				const meetsTarget = summaryMeetsTargets(result.summary);
				const improved = monitorScore > bestMonitor + 0.0001;
				if (improved) {
					bestMonitor = monitorScore;
					roundsWithoutImprovement = 0;
					bestToolPatchMap = cloneToolPatchMap(toolPatchMap);
					bestIntentPatchMap = cloneIntentPatchMap(intentPatchMap);
					bestAgentPatchMap = cloneAgentPatchMap(agentPatchMap);
					bestAuditResult = result;
					bestAuditAnnotations = currentAnnotations;
				} else {
					roundsWithoutImprovement += 1;
				}
				const dropTriggered =
					previousMonitor != null && monitorScore < previousMonitor - dropThreshold;
				previousMonitor = monitorScore;
				const vectorSummary = result.summary.vector_recall_summary;
				const rankingSummary = result.summary.tool_ranking_summary;
				const step1Diagnostics = result.diagnostics ?? null;
				const totalProbes = Math.max(0, Number(result.summary.total_probes || 0));

				const baseEntry: AutoAuditRoundEntry = {
					round,
					intentAccuracy: result.summary.intent_accuracy,
					agentAccuracy: result.summary.agent_accuracy,
					toolAccuracy: result.summary.tool_accuracy,
					agentGivenIntentAccuracy: result.summary.agent_accuracy_given_intent_correct ?? null,
					toolGivenIntentAgentAccuracy:
						result.summary.tool_accuracy_given_intent_agent_correct ?? null,
					vectorRecallTop5:
						typeof vectorSummary?.share_probes_with_vector_candidates === "number"
							? vectorSummary.share_probes_with_vector_candidates
							: null,
					vectorTop1FromVector:
						typeof vectorSummary?.share_top1_from_vector === "number"
							? vectorSummary.share_top1_from_vector
							: null,
					vectorExpectedInTopK:
						typeof vectorSummary?.share_expected_tool_in_vector_top_k === "number"
							? vectorSummary.share_expected_tool_in_vector_top_k
							: null,
					totalProbes,
					toolRankingTopK: Math.max(1, Number(rankingSummary?.top_k ?? 5)),
					toolRankingRows: toToolRankingSnapshotRows(rankingSummary?.tools),
					monitorScore,
					step1TotalMs: step1Diagnostics?.total_ms ?? null,
					step1PreparationMs: step1Diagnostics?.preparation_ms ?? null,
					step1ProbeGenerationMs: step1Diagnostics?.probe_generation_ms ?? null,
					step1EvaluationMs: step1Diagnostics?.evaluation_ms ?? null,
					step1IntentMs: step1Diagnostics?.intent_layer_ms ?? null,
					step1AgentMs: step1Diagnostics?.agent_layer_ms ?? null,
					step1ToolMs: step1Diagnostics?.tool_layer_ms ?? null,
					step2TotalMs: null,
					step2PreparationMs: null,
					step2ToolMs: null,
					step2IntentMs: null,
					step2AgentMs: null,
					toolSuggestions: 0,
					intentSuggestions: 0,
					agentSuggestions: 0,
					meetsTarget,
					note: null,
				};

				if (meetsTarget) {
					stopReason = `Mål uppnått i runda ${round}.`;
					roundEntries.push({
						...baseEntry,
						note: "Mål uppnått",
					});
					setAutoRoundHistory([...roundEntries]);
					break;
				}
				if (dropTriggered) {
					stopReason = `Avbruten i runda ${round}: tappade mer än ${(
						dropThreshold * 100
					).toFixed(1)} pp mot föregående.`;
					roundEntries.push({
						...baseEntry,
						note: `Tapp > ${(dropThreshold * 100).toFixed(1)} pp`,
					});
					setAutoRoundHistory([...roundEntries]);
					break;
				}
				if (roundsWithoutImprovement > patienceRounds) {
					stopReason = `Avbruten i runda ${round}: ingen förbättring på ${patienceRounds} rundor.`;
					roundEntries.push({
						...baseEntry,
						note: "Ingen förbättring",
					});
					setAutoRoundHistory([...roundEntries]);
					break;
				}

				const annotations = buildAutoSuggestionAnnotations(result);
				const reviewedFailures = annotations.filter(
					(item) =>
						!item.intent_is_correct || !item.agent_is_correct || !item.tool_is_correct
				).length;
				if (!reviewedFailures) {
					stopReason = `Stopp i runda ${round}: inga fel kvar att optimera.`;
					roundEntries.push({
						...baseEntry,
						note: "Inga fel kvar",
					});
					setAutoRoundHistory([...roundEntries]);
					break;
				}
				const failingAnnotations = annotations.filter(
					(item) =>
						!item.intent_is_correct || !item.agent_is_correct || !item.tool_is_correct
				);

				setAutoRunStatusText(`Autonom loop: genererar metadataförslag för runda ${round}...`);
				const suggestions =
					await adminToolSettingsApiService.generateMetadataCatalogAuditSuggestions({
						search_space_id: data.search_space_id,
						metadata_patch: Object.values(toolPatchMap),
						intent_metadata_patch: Object.values(intentPatchMap),
						agent_metadata_patch: Object.values(agentPatchMap),
						annotations: failingAnnotations,
						max_suggestions: 30,
						llm_parallelism: suggestionParallelism,
					});
				const toolSuggestionCount = suggestions.tool_suggestions.length;
				const intentSuggestionCount = suggestions.intent_suggestions.length;
				const agentSuggestionCount = suggestions.agent_suggestions.length;
				const totalSuggestionCount =
					toolSuggestionCount + intentSuggestionCount + agentSuggestionCount;
				const step2Diagnostics = suggestions.diagnostics ?? null;
				roundEntries.push({
					...baseEntry,
					step2TotalMs: step2Diagnostics?.total_ms ?? null,
					step2PreparationMs: step2Diagnostics?.preparation_ms ?? null,
					step2ToolMs: step2Diagnostics?.tool_stage_ms ?? null,
					step2IntentMs: step2Diagnostics?.intent_stage_ms ?? null,
					step2AgentMs: step2Diagnostics?.agent_stage_ms ?? null,
					toolSuggestions: toolSuggestionCount,
					intentSuggestions: intentSuggestionCount,
					agentSuggestions: agentSuggestionCount,
					note:
						totalSuggestionCount === 0
							? "Inga fler förslag"
							: `${totalSuggestionCount} förslag applicerade`,
				});
				setAutoRoundHistory([...roundEntries]);

				if (totalSuggestionCount === 0) {
					stopReason = `Stopp i runda ${round}: modellen gav inga fler metadataförslag.`;
					break;
				}

				for (const suggestion of suggestions.tool_suggestions) {
					toolPatchMap[suggestion.tool_id] = {
						...suggestion.proposed_metadata,
					};
				}
				for (const suggestion of suggestions.intent_suggestions) {
					intentPatchMap[suggestion.intent_id] = {
						...suggestion.proposed_metadata,
					};
				}
				for (const suggestion of suggestions.agent_suggestions) {
					agentPatchMap[suggestion.agent_id] = {
						...suggestion.proposed_metadata,
					};
				}
				if (round === maxRounds) {
					stopReason = `Stopp efter ${maxRounds} rundor (max).`;
				}
			}

			setDraftTools((previous) => ({ ...previous, ...bestToolPatchMap }));
			setDraftIntents((previous) => ({ ...previous, ...bestIntentPatchMap }));
			setDraftAgents((previous) => ({ ...previous, ...bestAgentPatchMap }));
			if (bestAuditResult) {
				setAuditResult(bestAuditResult);
				setAuditAnnotations(bestAuditAnnotations);
			}
			setAutoRunStatusText(stopReason);
			toast.success(stopReason);
		} catch (_error) {
			setAutoRunStatusText("Autonom loop misslyckades.");
			toast.error("Kunde inte köra autonom metadata-loop.");
		} finally {
			setIsAutoRunning(false);
		}
	};

	const toggleAuditToolSuggestionSelection = (toolId: string, selected: boolean) => {
		setSelectedAuditSuggestionToolIds((previous) => {
			const next = new Set(previous);
			if (selected) {
				next.add(toolId);
			} else {
				next.delete(toolId);
			}
			return next;
		});
	};

	const toggleAuditIntentSuggestionSelection = (intentId: string, selected: boolean) => {
		setSelectedAuditSuggestionIntentIds((previous) => {
			const next = new Set(previous);
			if (selected) {
				next.add(intentId);
			} else {
				next.delete(intentId);
			}
			return next;
		});
	};

	const toggleAuditAgentSuggestionSelection = (agentId: string, selected: boolean) => {
		setSelectedAuditSuggestionAgentIds((previous) => {
			const next = new Set(previous);
			if (selected) {
				next.add(agentId);
			} else {
				next.delete(agentId);
			}
			return next;
		});
	};

	const applySelectedAuditSuggestionsToDraft = () => {
		if (
			!selectedToolSuggestions.length &&
			!selectedIntentSuggestions.length &&
			!selectedAgentSuggestions.length
		) {
			toast.message("Inga metadataforslag valda.");
			return;
		}
		setDraftTools((previous) => {
			const next = { ...previous };
			for (const suggestion of selectedToolSuggestions) {
				next[suggestion.tool_id] = {
					...suggestion.proposed_metadata,
				};
			}
			return next;
		});
		setDraftIntents((previous) => {
			const next = { ...previous };
			for (const suggestion of selectedIntentSuggestions) {
				next[suggestion.intent_id] = {
					...suggestion.proposed_metadata,
				};
			}
			return next;
		});
		setDraftAgents((previous) => {
			const next = { ...previous };
			for (const suggestion of selectedAgentSuggestions) {
				next[suggestion.agent_id] = {
					...suggestion.proposed_metadata,
				};
			}
			return next;
		});
		toast.success(
			`Lade ${selectedToolSuggestions.length + selectedIntentSuggestions.length + selectedAgentSuggestions.length} forslag i draft.`
		);
	};

	const term = searchTerm.trim().toLocaleLowerCase();
	const filteredAgents = useMemo(() => {
		const source = data?.agents ?? [];
		if (!term) return source;
		return source.filter((item) => {
			const draft = draftAgents[item.agent_id] ?? toAgentUpdateItem(item);
			return (
				draft.agent_id.toLocaleLowerCase().includes(term) ||
				draft.label.toLocaleLowerCase().includes(term) ||
				draft.description.toLocaleLowerCase().includes(term) ||
				draft.keywords.some((keyword) => keyword.toLocaleLowerCase().includes(term))
			);
		});
	}, [data?.agents, draftAgents, term]);

	const filteredIntents = useMemo(() => {
		const source = data?.intents ?? [];
		if (!term) return source;
		return source.filter((item) => {
			const draft = draftIntents[item.intent_id] ?? toIntentUpdateItem(item);
			return (
				draft.intent_id.toLocaleLowerCase().includes(term) ||
				draft.label.toLocaleLowerCase().includes(term) ||
				draft.route.toLocaleLowerCase().includes(term) ||
				draft.description.toLocaleLowerCase().includes(term) ||
				draft.keywords.some((keyword) => keyword.toLocaleLowerCase().includes(term))
			);
		});
	}, [data?.intents, draftIntents, term]);

	const filteredToolCategories = useMemo(() => {
		const source = data?.tool_categories ?? [];
		return source
			.map((category) => {
				const tools = category.tools.filter((tool) => {
					if (!term) return true;
					const draft = draftTools[tool.tool_id] ?? toToolUpdateItem(tool);
					return (
						draft.tool_id.toLocaleLowerCase().includes(term) ||
						draft.name.toLocaleLowerCase().includes(term) ||
						draft.description.toLocaleLowerCase().includes(term) ||
						draft.category.toLocaleLowerCase().includes(term) ||
						draft.keywords.some((keyword) => keyword.toLocaleLowerCase().includes(term))
					);
				});
				return {
					...category,
					tools,
				};
			})
			.filter((category) => category.tools.length > 0);
	}, [data?.tool_categories, draftTools, term]);

	if (isLoading) {
		return (
			<Card>
				<CardContent className="py-6 text-sm text-muted-foreground">
					Laddar metadata-katalog...
				</CardContent>
			</Card>
		);
	}

	if (error || !data) {
		return (
			<Card>
				<CardContent className="py-6 text-sm text-destructive">
					Kunde inte lasa metadata-katalogen.
				</CardContent>
			</Card>
		);
	}

	return (
		<div className="space-y-4">
			<Card>
				<CardHeader>
					<CardTitle>Metadata-katalog: Agents, Intents och Tools</CardTitle>
					<CardDescription>
						Redigera beskrivning, keywords och metadata i en samlad vy.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="flex flex-wrap items-center gap-3">
						<Input
							value={searchTerm}
							onChange={(event) => setSearchTerm(event.target.value)}
							placeholder="Sok agent, intent eller tool..."
							className="max-w-lg"
						/>
						<Badge variant="outline">
							Andringar: {changedAgentIds.length + changedIntentIds.length + changedToolIds.length}
						</Badge>
						<Badge variant="outline">Version: {data.metadata_version_hash}</Badge>
						<Button
							type="button"
							variant="outline"
							className="gap-2"
							onClick={resetDrafts}
							disabled={isSaving}
						>
							<RotateCcw className="h-4 w-4" />
							Ladda om
						</Button>
						<Button
							type="button"
							className="gap-2"
							onClick={saveAllMetadata}
							disabled={
								isSaving ||
								(!changedAgentIds.length &&
									!changedIntentIds.length &&
									!changedToolIds.length)
							}
						>
							<Save className="h-4 w-4" />
							{isSaving ? "Sparar..." : "Spara metadata"}
						</Button>
					</div>
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle>Metadata Audit (Steg A + Steg B)</CardTitle>
					<CardDescription>
						Kor produktionens retrieval-vikter mot probe-queries och markera snabbt vad som
						ar korrekt.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-7">
						<div className="space-y-1 lg:col-span-2">
							<Label>Scope (flera val)</Label>
							<div className="rounded border p-2 space-y-1 max-h-32 overflow-auto text-xs">
								{AUDIT_SCOPE_OPTIONS.map((scopeOption) => {
									const checked = selectedAuditScopes.includes(scopeOption.id);
									const disabled =
										selectedAuditScopes.includes("all") && scopeOption.id !== "all";
									return (
										<label
											key={`audit-scope-${scopeOption.id}`}
											className={`flex items-center gap-2 ${
												disabled ? "opacity-50" : ""
											}`}
										>
											<input
												type="checkbox"
												checked={checked}
												disabled={disabled}
												onChange={(event) =>
													toggleAuditScopeSelection(scopeOption.id, event.target.checked)
												}
											/>
											{scopeOption.label}
										</label>
									);
								})}
							</div>
						</div>
						<div className="space-y-1 lg:col-span-2">
							<Label htmlFor="audit-tool-ids-input">
								Extra tool IDs (komma eller radbrytning)
							</Label>
							<Textarea
								id="audit-tool-ids-input"
								rows={4}
								value={customAuditToolIdsInput}
								onChange={(event) => setCustomAuditToolIdsInput(event.target.value)}
								placeholder={"smhi_weather\ntrafikverket_vader_halka"}
							/>
						</div>
						<div className="space-y-1">
							<Label>LLM queries/tool</Label>
							<Input
								type="number"
								min={1}
								max={10}
								value={llmQueriesPerTool}
								onChange={(event) =>
									setLlmQueriesPerTool(
										Math.max(1, Math.min(10, Number.parseInt(event.target.value || "1", 10)))
									)
								}
							/>
						</div>
						<div className="space-y-1">
							<Label>Max queries/tool</Label>
							<Input
								type="number"
								min={1}
								max={20}
								value={maxQueriesPerTool}
								onChange={(event) =>
									setMaxQueriesPerTool(
										Math.max(1, Math.min(20, Number.parseInt(event.target.value || "1", 10)))
									)
								}
							/>
						</div>
						<div className="space-y-1">
							<Label>Hard negatives/tool</Label>
							<Input
								type="number"
								min={0}
								max={10}
								value={hardNegativesPerTool}
								onChange={(event) =>
									setHardNegativesPerTool(
										Math.max(0, Math.min(10, Number.parseInt(event.target.value || "0", 10)))
									)
								}
							/>
						</div>
						<div className="space-y-1">
							<Label>Steg A parallelism</Label>
							<Input
								type="number"
								min={1}
								max={32}
								value={probeGenerationParallelism}
								onChange={(event) =>
									setProbeGenerationParallelism(
										Math.max(1, Math.min(32, Number.parseInt(event.target.value || "1", 10)))
									)
								}
							/>
						</div>
						<div className="space-y-1">
							<Label>Steg B parallelism</Label>
							<Input
								type="number"
								min={1}
								max={32}
								value={suggestionParallelism}
								onChange={(event) =>
									setSuggestionParallelism(
										Math.max(1, Math.min(32, Number.parseInt(event.target.value || "1", 10)))
									)
								}
							/>
						</div>
						<div className="space-y-1 lg:col-span-2">
							<Label className="block">Kallor</Label>
							<label className="flex items-center gap-2 text-sm">
								<input
									type="checkbox"
									checked={includeExistingExamples}
									onChange={(event) => setIncludeExistingExamples(event.target.checked)}
								/>
								Existing examples
							</label>
							<label className="flex items-center gap-2 text-sm">
								<input
									type="checkbox"
									checked={includeLlmGenerated}
									onChange={(event) => setIncludeLlmGenerated(event.target.checked)}
								/>
								LLM generated
							</label>
							<div className="flex flex-wrap gap-2 pt-1">
								<Badge variant="outline">
									Scope-val: {selectedAuditScopes.length}
								</Badge>
								<Badge variant="outline">
									Valda tool IDs:{" "}
									{hasAllScopeSelected && customAuditToolIds.length === 0
										? "alla"
										: requestedAuditToolIds.length}
								</Badge>
								{customAuditToolIds.length > 0 ? (
									<Badge variant="outline">Extra manuella: {customAuditToolIds.length}</Badge>
								) : null}
								<Badge variant="outline">A parallel: {probeGenerationParallelism}</Badge>
								<Badge variant="outline">B parallel: {suggestionParallelism}</Badge>
							</div>
						</div>
						<div className="flex items-end">
							<Button
								type="button"
								onClick={runAudit}
								disabled={isRunningAudit}
								className="w-full"
							>
								{isRunningAudit ? "Korer..." : "Kor Steg A Audit"}
							</Button>
						</div>
						<div className="flex items-end">
							<Button
								type="button"
								variant="outline"
								onClick={generateAuditSuggestions}
								disabled={!auditResult || isGeneratingAuditSuggestions}
								className="w-full"
							>
								{isGeneratingAuditSuggestions
									? "Genererar..."
									: "Kor Steg B Forslag"}
							</Button>
						</div>
					</div>
					<div className="rounded border p-3 space-y-3">
						<div className="flex flex-wrap items-center gap-2">
							<p className="text-sm font-medium">Autonom optimering (målstyrd loop)</p>
							<Badge variant="outline">Nuvarande monitor: {(currentAutoMonitorScore * 100).toFixed(1)}%</Badge>
							{autoRunStatusText ? <Badge variant="secondary">{autoRunStatusText}</Badge> : null}
						</div>
						<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-6">
							<div className="space-y-1 lg:col-span-2">
								<Label>Mållägen</Label>
								<select
									value={autoTargetMode}
									onChange={(event) =>
										setAutoTargetMode(event.target.value as AutoAuditTargetMode)
									}
									className="h-9 rounded-md border bg-transparent px-3 text-sm w-full"
								>
									<option value="layered">Layer gates + total (rekommenderad)</option>
									<option value="tool_only">Bara tool-accuracy</option>
								</select>
							</div>
							<div className="space-y-1">
								<Label>Max rounds</Label>
								<Input
									type="number"
									min={1}
									max={20}
									value={autoMaxRounds}
									onChange={(event) =>
										setAutoMaxRounds(
											Math.max(1, Math.min(20, Number.parseInt(event.target.value || "1", 10)))
										)
									}
								/>
							</div>
							<div className="space-y-1">
								<Label>Patience</Label>
								<Input
									type="number"
									min={0}
									max={10}
									value={autoPatienceRounds}
									onChange={(event) =>
										setAutoPatienceRounds(
											Math.max(0, Math.min(10, Number.parseInt(event.target.value || "0", 10)))
										)
									}
								/>
							</div>
							<div className="space-y-1">
								<Label>Abort drop (pp)</Label>
								<Input
									type="number"
									step={0.5}
									min={0}
									max={50}
									value={autoAbortDropPp}
									onChange={(event) =>
										setAutoAbortDropPp(
											Math.max(0, Math.min(50, Number.parseFloat(event.target.value || "0")))
										)
									}
								/>
							</div>
							<div className="flex items-end">
								<Button
									type="button"
									onClick={runAutoAuditLoop}
									disabled={isAutoRunning || isRunningAudit || isGeneratingAuditSuggestions}
									className="w-full"
								>
									{isAutoRunning ? "Autoloop kör..." : "Kör autonom loop"}
								</Button>
							</div>
						</div>
						<div className="flex items-center gap-2">
							<input
								id="auto-exclude-history-between-rounds"
								type="checkbox"
								checked={autoExcludeProbeHistoryBetweenRounds}
								onChange={(event) =>
									setAutoExcludeProbeHistoryBetweenRounds(event.target.checked)
								}
							/>
							<Label htmlFor="auto-exclude-history-between-rounds" className="text-sm">
								Exkludera probe-historik mellan rundor
							</Label>
							<Badge variant="outline">
								{autoExcludeProbeHistoryBetweenRounds ? "På" : "Av"}
							</Badge>
						</div>
						<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
							<div className="space-y-1">
								<Label>Tool mål %</Label>
								<Input
									type="number"
									min={0}
									max={100}
									value={autoTargetToolPct}
									onChange={(event) =>
										setAutoTargetToolPct(
											clampPercentage(
												Number.parseFloat(event.target.value || `${DEFAULT_AUTO_TARGET_TOOL}`),
												DEFAULT_AUTO_TARGET_TOOL
											)
										)
									}
								/>
							</div>
							<div className="space-y-1">
								<Label>Intent mål %</Label>
								<Input
									type="number"
									min={0}
									max={100}
									value={autoTargetIntentPct}
									onChange={(event) =>
										setAutoTargetIntentPct(
											clampPercentage(
												Number.parseFloat(event.target.value || `${DEFAULT_AUTO_TARGET_INTENT}`),
												DEFAULT_AUTO_TARGET_INTENT
											)
										)
									}
									disabled={autoTargetMode !== "layered"}
								/>
							</div>
							<div className="space-y-1">
								<Label>Agent mål %</Label>
								<Input
									type="number"
									min={0}
									max={100}
									value={autoTargetAgentPct}
									onChange={(event) =>
										setAutoTargetAgentPct(
											clampPercentage(
												Number.parseFloat(event.target.value || `${DEFAULT_AUTO_TARGET_AGENT}`),
												DEFAULT_AUTO_TARGET_AGENT
											)
										)
									}
									disabled={autoTargetMode !== "layered"}
								/>
							</div>
							<div className="space-y-1">
								<Label>Agent | Intent OK mål %</Label>
								<Input
									type="number"
									min={0}
									max={100}
									value={autoTargetAgentGivenIntentPct}
									onChange={(event) =>
										setAutoTargetAgentGivenIntentPct(
											clampPercentage(
												Number.parseFloat(
													event.target.value ||
														`${DEFAULT_AUTO_TARGET_AGENT_GIVEN_INTENT}`
												),
												DEFAULT_AUTO_TARGET_AGENT_GIVEN_INTENT
											)
										)
									}
									disabled={autoTargetMode !== "layered"}
								/>
							</div>
							<div className="space-y-1">
								<Label>Tool | Intent+Agent OK mål %</Label>
								<Input
									type="number"
									min={0}
									max={100}
									value={autoTargetToolGivenIntentAgentPct}
									onChange={(event) =>
										setAutoTargetToolGivenIntentAgentPct(
											clampPercentage(
												Number.parseFloat(
													event.target.value ||
														`${DEFAULT_AUTO_TARGET_TOOL_GIVEN_INTENT_AGENT}`
												),
												DEFAULT_AUTO_TARGET_TOOL_GIVEN_INTENT_AGENT
											)
										)
									}
									disabled={autoTargetMode !== "layered"}
								/>
							</div>
						</div>
						{autoRoundHistory.length > 0 ? (
							<div className="max-h-44 overflow-auto rounded border p-2 text-xs space-y-1">
								{autoRoundHistory.map((item) => (
									<div
										key={`auto-round-${item.round}`}
										className="rounded bg-muted/40 px-2 py-1"
									>
										Runda {item.round}: I {(item.intentAccuracy * 100).toFixed(1)}% · A{" "}
										{(item.agentAccuracy * 100).toFixed(1)}% · T{" "}
										{(item.toolAccuracy * 100).toFixed(1)}% · Monitor{" "}
										{(item.monitorScore * 100).toFixed(1)}% · Förslag{" "}
										{item.toolSuggestions}/{item.intentSuggestions}/{item.agentSuggestions}
										{item.step1TotalMs != null
											? ` · Steg1 ${formatMs(item.step1TotalMs)} (Prep ${formatMs(
													item.step1PreparationMs
												)} | QGen ${formatMs(item.step1ProbeGenerationMs)} | Eval ${formatMs(
													item.step1EvaluationMs
												)} | I ${formatMs(item.step1IntentMs)} | A ${formatMs(
													item.step1AgentMs
												)} | T ${formatMs(item.step1ToolMs)})`
											: ""}
										{item.step2TotalMs != null
											? ` · Steg2 ${formatMs(item.step2TotalMs)} (T ${formatMs(
													item.step2ToolMs
												)} | I ${formatMs(item.step2IntentMs)} | A ${formatMs(
													item.step2AgentMs
												)} | Prep ${formatMs(item.step2PreparationMs)})`
											: ""}
										{item.note ? ` · ${item.note}` : ""}
									</div>
								))}
							</div>
						) : null}
						{autoEvolutionSummary ? (
							<div className="rounded border">
								<div className="border-b bg-muted/30 px-3 py-2">
									<p className="text-sm font-medium">Sammanfattning av utvecklingen</p>
									<p className="text-xs text-muted-foreground">
										Jämför runda {autoEvolutionSummary.olderRound} mot runda{" "}
										{autoEvolutionSummary.newerRound}. Uppdateras live under autoloop.
										{" "}Probes: {autoEvolutionSummary.olderProbes} →{" "}
										{autoEvolutionSummary.newerProbes}
									</p>
								</div>
								<div className="overflow-auto">
									<table className="w-full text-xs">
										<thead>
											<tr className="border-b bg-muted/20">
												<th className="px-3 py-2 text-left font-medium">Mått</th>
												<th className="px-3 py-2 text-left font-medium">
													Äldre audit (R{autoEvolutionSummary.olderRound})
												</th>
												<th className="px-3 py-2 text-left font-medium">
													Nyare audit (R{autoEvolutionSummary.newerRound})
												</th>
												<th className="px-3 py-2 text-left font-medium">Förändring</th>
												<th className="px-3 py-2 text-left font-medium">Kommentar</th>
											</tr>
										</thead>
										<tbody>
											{autoEvolutionSummary.rows.map((row) => (
												<tr key={`auto-evolution-${row.key}`} className="border-b last:border-b-0">
													<td className="px-3 py-2 font-medium">{row.metric}</td>
													<td className="px-3 py-2">{formatRate(row.older)}</td>
													<td className="px-3 py-2">{formatRate(row.newer)}</td>
													<td
														className={`px-3 py-2 ${
															row.deltaPp == null
																? "text-muted-foreground"
																: row.deltaPp > 0.05
																	? "text-emerald-700"
																	: row.deltaPp < -0.05
																		? "text-red-700"
																		: "text-amber-700"
														}`}
													>
														{formatDeltaPp(row.deltaPp)}
													</td>
													<td className="px-3 py-2 text-muted-foreground">{row.comment}</td>
												</tr>
											))}
										</tbody>
									</table>
								</div>
							</div>
						) : null}
						{autoToolRankingStability ? (
							<div className="rounded border">
								<div className="border-b bg-muted/30 px-3 py-2">
									<p className="text-sm font-medium">Ranking stability per tool</p>
									<p className="text-xs text-muted-foreground">
										Jämför runda {autoToolRankingStability.olderRound} mot{" "}
										{autoToolRankingStability.newerRound} (top-
										{autoToolRankingStability.topK}).
									</p>
								</div>
								<div className="overflow-x-auto">
									<table className="min-w-full text-xs">
										<thead className="bg-muted/20 text-left">
											<tr>
												<th className="px-3 py-2 font-medium">Tool</th>
												<th className="px-3 py-2 font-medium">Rank-shift</th>
												<th className="px-3 py-2 font-medium">Margin (old→new)</th>
												<th className="px-3 py-2 font-medium">Top-1 (old→new)</th>
												<th className="px-3 py-2 font-medium">Top-K (old→new)</th>
												<th className="px-3 py-2 font-medium">Status</th>
											</tr>
										</thead>
										<tbody>
											{autoToolRankingStability.rows.slice(0, 24).map((row) => (
												<tr key={`stability-${row.toolId}`} className="border-t">
													<td className="px-3 py-2 font-mono">{row.toolId}</td>
													<td className="px-3 py-2">
														{formatSigned(row.rankShift, 2)}
													</td>
													<td className="px-3 py-2">
														{formatSigned(row.marginOlder, 2)} →{" "}
														{formatSigned(row.marginNewer, 2)}
													</td>
													<td className="px-3 py-2">
														{formatRate(row.top1Older)} → {formatRate(row.top1Newer)}
													</td>
													<td className="px-3 py-2">
														{formatRate(row.topKOlder)} → {formatRate(row.topKNewer)}
													</td>
													<td className="px-3 py-2">
														<Badge
															variant={
																row.label === "stabilt"
																	? "outline"
																	: row.label === "omdistribuerat"
																		? "secondary"
																		: "destructive"
															}
														>
															{row.label}
														</Badge>
													</td>
												</tr>
											))}
										</tbody>
									</table>
								</div>
							</div>
						) : null}
					</div>

					{auditResult ? (
						<div className="space-y-4">
							<div className="flex flex-wrap gap-2">
								<Badge variant="outline">Probes: {auditResult.summary.total_probes}</Badge>
								<Badge variant="outline">
									Steg1 total: {formatMs(auditResult.diagnostics?.total_ms)}
								</Badge>
								<Badge variant="outline">
									Steg1 Prep/QGen/Eval:{" "}
									{formatMs(auditResult.diagnostics?.preparation_ms)}/
									{formatMs(auditResult.diagnostics?.probe_generation_ms)}/
									{formatMs(auditResult.diagnostics?.evaluation_ms)}
								</Badge>
								<Badge variant="outline">
									Steg1 I/A/T: {formatMs(auditResult.diagnostics?.intent_layer_ms)}/
									{formatMs(auditResult.diagnostics?.agent_layer_ms)}/
									{formatMs(auditResult.diagnostics?.tool_layer_ms)}
								</Badge>
								<Badge variant="outline">
									Q-kandidater (tot/ex/llm/refresh):{" "}
									{auditResult.diagnostics?.query_candidates_total ?? 0}/
									{auditResult.diagnostics?.existing_example_candidates ?? 0}/
									{auditResult.diagnostics?.llm_generated_candidates ?? 0}/
									{auditResult.diagnostics?.round_refresh_queries ?? 0}
								</Badge>
								<Badge variant="outline">
									Exkluderade (history/dupes):{" "}
									{auditResult.diagnostics?.excluded_query_history_count ?? 0}/
									{auditResult.diagnostics?.excluded_query_duplicate_count ?? 0}
								</Badge>
								<Badge variant="outline">
									Evals: {auditResult.diagnostics?.evaluated_queries ?? 0} · Verktyg:{" "}
									{auditResult.diagnostics?.selected_tools_count ?? 0} · Probe pool:{" "}
									{auditResult.diagnostics?.excluded_query_pool_size ?? 0}
								</Badge>
								<Badge variant="outline">
									Intent: {(auditResult.summary.intent_accuracy * 100).toFixed(1)}%
								</Badge>
								<Badge variant="outline">
									Agent: {(auditResult.summary.agent_accuracy * 100).toFixed(1)}%
								</Badge>
								<Badge variant="outline">
									Tool: {(auditResult.summary.tool_accuracy * 100).toFixed(1)}%
								</Badge>
								{auditResult.summary.agent_accuracy_given_intent_correct != null ? (
									<Badge variant="outline">
										Agent | Intent OK:{" "}
										{(auditResult.summary.agent_accuracy_given_intent_correct * 100).toFixed(1)}%
									</Badge>
								) : null}
								{auditResult.summary.tool_accuracy_given_intent_agent_correct != null ? (
									<Badge variant="outline">
										Tool | Intent+Agent OK:{" "}
										{(
											auditResult.summary.tool_accuracy_given_intent_agent_correct * 100
										).toFixed(1)}
										%
									</Badge>
								) : null}
								<Badge variant="outline">
									Vector candidates:{" "}
									{auditResult.summary.vector_recall_summary.probes_with_vector_candidates}/
									{auditResult.summary.total_probes} (
									{(
										auditResult.summary.vector_recall_summary
											.share_probes_with_vector_candidates * 100
									).toFixed(1)}
									%)
								</Badge>
								<Badge variant="outline">
									Top1 fran vector:{" "}
									{auditResult.summary.vector_recall_summary.probes_with_top1_from_vector}/
									{auditResult.summary.total_probes} (
									{(
										auditResult.summary.vector_recall_summary.share_top1_from_vector * 100
									).toFixed(1)}
									%)
								</Badge>
								<Badge variant="outline">
									Expected i vector@
									{auditResult.summary.vector_recall_summary.top_k}:{" "}
									{
										auditResult.summary.vector_recall_summary
											.probes_with_expected_tool_in_vector_top_k
									}
									/{auditResult.summary.total_probes} (
									{(
										auditResult.summary.vector_recall_summary
											.share_expected_tool_in_vector_top_k * 100
									).toFixed(1)}
									%)
								</Badge>
								<Badge
									variant={
										auditIssueSummary.probesWithAnyError > 0 ? "destructive" : "outline"
									}
								>
									Probes med fel: {auditIssueSummary.probesWithAnyError}/
									{auditIssueSummary.totalProbes}
								</Badge>
								<Badge variant="outline">
									Intent/Agent/Tool fel: {auditIssueSummary.intentErrors}/
									{auditIssueSummary.agentErrors}/{auditIssueSummary.toolErrors}
								</Badge>
								<Badge variant="outline">
									Lag marginal (I/A/T): {auditIssueSummary.intentLowMargins}/
									{auditIssueSummary.agentLowMargins}/{auditIssueSummary.toolLowMargins}
								</Badge>
								<Badge variant="outline">
									Visar: {visibleAuditProbeRows.length}/{auditIssueSummary.totalProbes}
								</Badge>
							</div>
							<div className="rounded border p-3 space-y-2">
								<p className="text-sm font-medium">Tool-aware embedding context</p>
								<p className="text-xs text-muted-foreground">
									{auditResult.summary.tool_embedding_context.description ??
										"Embeddings använder tool-aware kontext för bättre disambiguering."}
								</p>
								<div className="flex flex-wrap gap-2">
									<Badge variant="secondary">
										Vector recall top-k: {auditResult.summary.vector_recall_summary.top_k}
									</Badge>
									<Badge variant="secondary">
										Semantic/Structural vikt:{" "}
										{auditResult.summary.tool_embedding_context.semantic_weight?.toFixed(2) ??
											"--"}
										/
										{auditResult.summary.tool_embedding_context.structural_weight?.toFixed(
											2
										) ?? "--"}
									</Badge>
									{auditResult.summary.tool_embedding_context.context_fields.map((field) => (
										<Badge key={`embedding-context-${field}`} variant="outline">
											{field}
										</Badge>
									))}
								</div>
								<div className="flex flex-wrap gap-2">
									{auditResult.summary.tool_embedding_context.semantic_fields.map((field) => (
										<Badge key={`embedding-semantic-${field}`} variant="secondary">
											semantic:{field}
										</Badge>
									))}
									{auditResult.summary.tool_embedding_context.structural_fields.map((field) => (
										<Badge key={`embedding-structural-${field}`} variant="outline">
											structural:{field}
										</Badge>
									))}
								</div>
							</div>
							<div className="rounded border p-3 space-y-2">
								<p className="text-sm font-medium">Ranking stability (aktuell audit)</p>
								<p className="text-xs text-muted-foreground">
									Per tool: top-1/top-k träff, genomsnittlig expected-rank och margin mot
									närmaste konkurrent.
								</p>
								<div className="overflow-x-auto">
									<table className="min-w-full text-xs">
										<thead className="bg-muted/20 text-left">
											<tr>
												<th className="px-3 py-2 font-medium">Tool</th>
												<th className="px-3 py-2 font-medium">Probes</th>
												<th className="px-3 py-2 font-medium">Top-1</th>
												<th className="px-3 py-2 font-medium">
													Top-{auditResult.summary.tool_ranking_summary.top_k}
												</th>
												<th className="px-3 py-2 font-medium">Avg expected-rank</th>
												<th className="px-3 py-2 font-medium">Avg margin</th>
											</tr>
										</thead>
										<tbody>
											{auditResult.summary.tool_ranking_summary.tools
												.slice()
												.sort((left, right) => {
													const probesDiff = (right.probes ?? 0) - (left.probes ?? 0);
													if (probesDiff !== 0) return probesDiff;
													return left.tool_id.localeCompare(right.tool_id, "sv");
												})
												.slice(0, 32)
												.map((row) => (
													<tr key={`tool-ranking-${row.tool_id}`} className="border-t">
														<td className="px-3 py-2 font-mono">{row.tool_id}</td>
														<td className="px-3 py-2">{row.probes}</td>
														<td className="px-3 py-2">{formatRate(row.top1_rate ?? 0)}</td>
														<td className="px-3 py-2">{formatRate(row.topk_rate ?? 0)}</td>
														<td className="px-3 py-2">
															{row.avg_expected_rank != null
																? row.avg_expected_rank.toFixed(2)
																: "--"}
														</td>
														<td className="px-3 py-2">
															{row.avg_margin_vs_best_other != null
																? row.avg_margin_vs_best_other.toFixed(2)
																: "--"}
														</td>
													</tr>
												))}
										</tbody>
									</table>
								</div>
							</div>
							<div className="rounded border p-3 space-y-2">
								<p className="text-sm font-medium">Snabbfilter: hitta fel snabbt</p>
								<div className="flex flex-wrap items-center gap-3 text-xs">
									<label className="flex items-center gap-2">
										<input
											type="checkbox"
											checked={showOnlyAuditIssues}
											onChange={(event) => setShowOnlyAuditIssues(event.target.checked)}
										/>
										Visa bara probes med fel
									</label>
									<label className="flex items-center gap-2">
										<input
											type="checkbox"
											checked={showOnlyLowMargin}
											onChange={(event) => setShowOnlyLowMargin(event.target.checked)}
										/>
										Visa bara lag marginal
									</label>
									<label className="flex items-center gap-2">
										<input
											type="checkbox"
											checked={sortAuditIssuesFirst}
											onChange={(event) => setSortAuditIssuesFirst(event.target.checked)}
										/>
										Sortera riskfall forst
									</label>
									<div className="flex items-center gap-2">
										<span className="text-muted-foreground">Lag margin-tröskel</span>
										<Input
											type="number"
											step={0.05}
											min={0}
											max={5}
											value={auditLowMarginThreshold}
											onChange={(event) =>
												setAuditLowMarginThreshold(
													Math.max(
														0,
														Math.min(
															5,
															Number.parseFloat(
																event.target.value ||
																	`${DEFAULT_AUDIT_LOW_MARGIN_THRESHOLD}`
															)
														)
													)
												)
											}
											className="h-8 w-24"
										/>
									</div>
									<Button
										type="button"
										variant="outline"
										size="sm"
										onClick={() => {
											setShowOnlyAuditIssues(false);
											setShowOnlyLowMargin(false);
											setSortAuditIssuesFirst(true);
											setAuditLowMarginThreshold(DEFAULT_AUDIT_LOW_MARGIN_THRESHOLD);
										}}
									>
										Reset filter
									</Button>
								</div>
							</div>
							<div className="grid gap-3 lg:grid-cols-2">
								<div className="space-y-2">
									<p className="text-sm font-medium">Intent confusion matrix</p>
									<div className="max-h-44 overflow-auto rounded border p-2 space-y-1 text-xs">
										{auditResult.summary.intent_confusion_matrix.slice(0, 10).map((row) => (
											<div
												key={`intent-${row.expected_label}-${row.predicted_label}`}
												className="rounded bg-muted/40 px-2 py-1"
											>
												{row.expected_label} -&gt; {row.predicted_label} ({row.count})
											</div>
										))}
									</div>
								</div>
								<div className="space-y-2">
									<p className="text-sm font-medium">Agent confusion matrix</p>
									<div className="max-h-44 overflow-auto rounded border p-2 space-y-1 text-xs">
										{auditResult.summary.agent_confusion_matrix.slice(0, 10).map((row) => (
											<div
												key={`agent-${row.expected_label}-${row.predicted_label}`}
												className="rounded bg-muted/40 px-2 py-1"
											>
												{row.expected_label} -&gt; {row.predicted_label} ({row.count})
											</div>
										))}
									</div>
								</div>
								<div className="space-y-2">
									<p className="text-sm font-medium">Tool confusion matrix</p>
									<div className="max-h-44 overflow-auto rounded border p-2 space-y-1 text-xs">
										{auditResult.summary.tool_confusion_matrix.slice(0, 10).map((row) => (
											<div
												key={`tool-${row.expected_label}-${row.predicted_label}`}
												className="rounded bg-muted/40 px-2 py-1"
											>
												{row.expected_label} -&gt; {row.predicted_label} ({row.count})
											</div>
										))}
									</div>
								</div>
								<div className="space-y-2">
									<p className="text-sm font-medium">Path confusion matrix</p>
									<div className="max-h-44 overflow-auto rounded border p-2 space-y-1 text-xs">
										{auditResult.summary.path_confusion_matrix.slice(0, 10).map((row) => (
											<div
												key={`path-${row.expected_path}-${row.predicted_path}`}
												className="rounded bg-muted/40 px-2 py-1"
											>
												{row.expected_path} -&gt; {row.predicted_path} ({row.count})
											</div>
										))}
									</div>
								</div>
							</div>
							<div className="max-h-[28rem] overflow-auto space-y-2 rounded border p-3">
								{visibleAuditProbeRows.map((probeRow) => {
									const {
										probe,
										annotation,
										intentCorrect,
										agentCorrect,
										toolCorrect,
										intentLowMargin,
										agentLowMargin,
										toolLowMargin,
										hasAnyError,
										hasAnyLowMargin,
									} = probeRow;
									const vectorDiagnostics = probe.tool_vector_diagnostics;
									const cardClassName = hasAnyError
										? "rounded border border-destructive/60 bg-destructive/5 p-3 space-y-2"
										: hasAnyLowMargin
											? "rounded border border-amber-500/60 bg-amber-500/5 p-3 space-y-2"
											: "rounded border border-emerald-500/35 bg-emerald-500/5 p-3 space-y-2";
									return (
										<div key={probe.probe_id} className={cardClassName}>
											<p className="text-sm font-medium">{probe.query}</p>
											<div className="flex flex-wrap gap-2 text-xs">
												<Badge variant="outline">Expected path: {probe.expected_path}</Badge>
												<Badge variant="outline">Predicted path: {probe.predicted_path}</Badge>
												<Badge variant="secondary">{probe.source}</Badge>
												{hasAnyError ? (
													<Badge variant="destructive">Fel</Badge>
												) : (
													<Badge variant="secondary">OK</Badge>
												)}
												{!intentCorrect ? <Badge variant="destructive">Intent fel</Badge> : null}
												{!agentCorrect ? <Badge variant="destructive">Agent fel</Badge> : null}
												{!toolCorrect ? <Badge variant="destructive">Tool fel</Badge> : null}
												{intentLowMargin ? (
													<Badge variant="outline">Intent lag marginal</Badge>
												) : null}
												{agentLowMargin ? (
													<Badge variant="outline">Agent lag marginal</Badge>
												) : null}
												{toolLowMargin ? <Badge variant="outline">Tool lag marginal</Badge> : null}
											</div>
											<div className="grid gap-3 lg:grid-cols-3">
												<div className="rounded border p-2 space-y-2">
													<p className="text-xs font-medium">
														Intent: {probe.intent.top1 ?? "-"}{" "}
														{probe.intent.top2 ? `| ${probe.intent.top2}` : ""}
													</p>
													<p className="text-xs text-muted-foreground">
														expected {probe.intent.expected_label ?? "-"} · margin{" "}
														{probe.intent.margin != null
															? probe.intent.margin.toFixed(2)
															: "-"}
													</p>
													<label className="flex items-center gap-2 text-xs">
														<input
															type="checkbox"
															checked={annotation.intent_is_correct}
															onChange={(event) =>
																updateAnnotationCorrectness(
																	probe.probe_id,
																	"intent",
																	event.target.checked
																)
															}
														/>
														Intent korrekt
													</label>
													{!annotation.intent_is_correct ? (
														<select
															value={
																annotation.corrected_intent_id ??
																probe.intent.expected_label ??
																""
															}
															onChange={(event) =>
																updateAnnotationCorrectedLabel(
																	probe.probe_id,
																	"intent",
																	event.target.value
																)
															}
															className="h-8 rounded-md border bg-transparent px-2 text-xs w-full"
														>
															<option value="">Valj intent...</option>
															{auditIntentOptions.map((intentId) => (
																<option
																	key={`${probe.probe_id}-intent-${intentId}`}
																	value={intentId}
																>
																	{intentId}
																</option>
															))}
														</select>
													) : null}
												</div>
												<div className="rounded border p-2 space-y-2">
													<p className="text-xs font-medium">
														Agent: {probe.agent.top1 ?? "-"}{" "}
														{probe.agent.top2 ? `| ${probe.agent.top2}` : ""}
													</p>
													<p className="text-xs text-muted-foreground">
														expected {probe.agent.expected_label ?? "-"} · margin{" "}
														{probe.agent.margin != null
															? probe.agent.margin.toFixed(2)
															: "-"}
													</p>
													<label className="flex items-center gap-2 text-xs">
														<input
															type="checkbox"
															checked={annotation.agent_is_correct}
															onChange={(event) =>
																updateAnnotationCorrectness(
																	probe.probe_id,
																	"agent",
																	event.target.checked
																)
															}
														/>
														Agent korrekt
													</label>
													{!annotation.agent_is_correct ? (
														<select
															value={
																annotation.corrected_agent_id ??
																probe.agent.expected_label ??
																""
															}
															onChange={(event) =>
																updateAnnotationCorrectedLabel(
																	probe.probe_id,
																	"agent",
																	event.target.value
																)
															}
															className="h-8 rounded-md border bg-transparent px-2 text-xs w-full"
														>
															<option value="">Valj agent...</option>
															{auditAgentOptions.map((agentId) => (
																<option
																	key={`${probe.probe_id}-agent-${agentId}`}
																	value={agentId}
																>
																	{agentId}
																</option>
															))}
														</select>
													) : null}
												</div>
												<div className="rounded border p-2 space-y-2">
													<p className="text-xs font-medium">
														Tool: {probe.tool.top1 ?? "-"}{" "}
														{probe.tool.top2 ? `| ${probe.tool.top2}` : ""}
													</p>
													<p className="text-xs text-muted-foreground">
														expected {probe.tool.expected_label ?? probe.target_tool_id} · margin{" "}
														{probe.tool.margin != null
															? probe.tool.margin.toFixed(2)
															: "-"}
													</p>
													<p className="text-[11px] text-muted-foreground">
														Vector top-{vectorDiagnostics.vector_top_k}:{" "}
														{vectorDiagnostics.vector_selected_ids.length
															? vectorDiagnostics.vector_selected_ids.join(", ")
															: "-"}
													</p>
													<p className="text-[11px] text-muted-foreground">
														Top1 via vector:{" "}
														{vectorDiagnostics.predicted_tool_vector_selected
															? `ja (rank ${vectorDiagnostics.predicted_tool_vector_rank ?? "-"})`
															: "nej"}{" "}
														· expected i vector:{" "}
														{vectorDiagnostics.expected_tool_vector_selected
															? `ja (rank ${vectorDiagnostics.expected_tool_vector_rank ?? "-"})`
															: "nej"}
													</p>
													<label className="flex items-center gap-2 text-xs">
														<input
															type="checkbox"
															checked={annotation.tool_is_correct}
															onChange={(event) =>
																updateAnnotationCorrectness(
																	probe.probe_id,
																	"tool",
																	event.target.checked
																)
															}
														/>
														Tool korrekt
													</label>
													{!annotation.tool_is_correct ? (
														<select
															value={
																annotation.corrected_tool_id ??
																probe.tool.expected_label ??
																probe.target_tool_id ??
																""
															}
															onChange={(event) =>
																updateAnnotationCorrectedLabel(
																	probe.probe_id,
																	"tool",
																	event.target.value
																)
															}
															className="h-8 rounded-md border bg-transparent px-2 text-xs w-full"
														>
															<option value="">Valj tool...</option>
															{auditToolOptions.map((toolId) => (
																<option
																	key={`${probe.probe_id}-tool-${toolId}`}
																	value={toolId}
																>
																	{toolId}
																</option>
															))}
														</select>
													) : null}
												</div>
											</div>
										</div>
									);
								})}
								{visibleAuditProbeRows.length === 0 ? (
									<div className="rounded border border-dashed p-4 text-xs text-muted-foreground">
										Inga probes matchar valda filter.
									</div>
								) : null}
							</div>
						</div>
					) : null}

					{auditSuggestions ? (
						<div className="space-y-3">
							<div className="flex flex-wrap items-center gap-2">
								<Badge variant="outline">
									Tool-forslag: {auditSuggestions.tool_suggestions.length}
								</Badge>
								<Badge variant="outline">
									Intent-forslag: {auditSuggestions.intent_suggestions.length}
								</Badge>
								<Badge variant="outline">
									Agent-forslag: {auditSuggestions.agent_suggestions.length}
								</Badge>
								<Badge variant="outline">
									Valda:{" "}
									{selectedToolSuggestions.length +
										selectedIntentSuggestions.length +
										selectedAgentSuggestions.length}
								</Badge>
								<Badge variant="outline">
									Steg2 total: {formatMs(auditSuggestions.diagnostics?.total_ms)}
								</Badge>
								<Badge variant="outline">
									Prep: {formatMs(auditSuggestions.diagnostics?.preparation_ms)}
								</Badge>
								<Badge variant="outline">
									Tool: {formatMs(auditSuggestions.diagnostics?.tool_stage_ms)}
								</Badge>
								<Badge variant="outline">
									Intent: {formatMs(auditSuggestions.diagnostics?.intent_stage_ms)}
								</Badge>
								<Badge variant="outline">
									Agent: {formatMs(auditSuggestions.diagnostics?.agent_stage_ms)}
								</Badge>
								<Badge variant="outline">
									Payload:{" "}
									{Number(
										auditSuggestions.diagnostics?.annotations_payload_bytes ?? 0
									).toLocaleString("sv")} B
								</Badge>
								<Badge variant="outline">
									Fail-kandidater (T/I/A):{" "}
									{auditSuggestions.diagnostics?.tool_failure_candidates ?? 0}/
									{auditSuggestions.diagnostics?.intent_failure_candidates ?? 0}/
									{auditSuggestions.diagnostics?.agent_failure_candidates ?? 0}
								</Badge>
								<Badge variant="outline">
									LLM parallel (req/eff):{" "}
									{auditSuggestions.diagnostics?.llm_parallelism ?? 1}/
									{auditSuggestions.diagnostics?.llm_parallelism_effective ?? 1}
								</Badge>
								<Button
									type="button"
									variant="outline"
									onClick={applySelectedAuditSuggestionsToDraft}
								>
									Lagg valda i draft
								</Button>
							</div>
							<div className="grid gap-3 lg:grid-cols-3">
								<div className="space-y-2">
									<p className="text-sm font-medium">Tool suggestions</p>
									{auditSuggestions.tool_suggestions.map((suggestion) => {
										const checked = selectedAuditSuggestionToolIds.has(
											suggestion.tool_id
										);
										return (
											<div
												key={`audit-suggestion-tool-${suggestion.tool_id}`}
												className="rounded border p-3"
											>
												<div className="flex items-center gap-2 mb-2">
													<input
														type="checkbox"
														checked={checked}
														onChange={(event) =>
															toggleAuditToolSuggestionSelection(
																suggestion.tool_id,
																event.target.checked
															)
														}
													/>
													<p className="text-sm font-medium">{suggestion.tool_id}</p>
												</div>
												<p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
											</div>
										);
									})}
								</div>
								<div className="space-y-2">
									<p className="text-sm font-medium">Intent suggestions</p>
									{auditSuggestions.intent_suggestions.map((suggestion) => {
										const checked = selectedAuditSuggestionIntentIds.has(
											suggestion.intent_id
										);
										return (
											<div
												key={`audit-suggestion-intent-${suggestion.intent_id}`}
												className="rounded border p-3"
											>
												<div className="flex items-center gap-2 mb-2">
													<input
														type="checkbox"
														checked={checked}
														onChange={(event) =>
															toggleAuditIntentSuggestionSelection(
																suggestion.intent_id,
																event.target.checked
															)
														}
													/>
													<p className="text-sm font-medium">{suggestion.intent_id}</p>
												</div>
												<p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
											</div>
										);
									})}
								</div>
								<div className="space-y-2">
									<p className="text-sm font-medium">Agent suggestions</p>
									{auditSuggestions.agent_suggestions.map((suggestion) => {
										const checked = selectedAuditSuggestionAgentIds.has(
											suggestion.agent_id
										);
										return (
											<div
												key={`audit-suggestion-agent-${suggestion.agent_id}`}
												className="rounded border p-3"
											>
												<div className="flex items-center gap-2 mb-2">
													<input
														type="checkbox"
														checked={checked}
														onChange={(event) =>
															toggleAuditAgentSuggestionSelection(
																suggestion.agent_id,
																event.target.checked
															)
														}
													/>
													<p className="text-sm font-medium">{suggestion.agent_id}</p>
												</div>
												<p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
											</div>
										);
									})}
								</div>
							</div>
						</div>
					) : null}
				</CardContent>
			</Card>

			<Tabs
				value={sectionTab}
				onValueChange={(value) => setSectionTab(value as "agents" | "intents" | "tools")}
			>
				<TabsList>
					<TabsTrigger value="agents">Agents ({data.agents.length})</TabsTrigger>
					<TabsTrigger value="intents">Intents ({data.intents.length})</TabsTrigger>
					<TabsTrigger value="tools">
						Tools (
						{data.tool_categories.reduce((count, category) => count + category.tools.length, 0)})
					</TabsTrigger>
				</TabsList>

				<TabsContent value="agents" className="space-y-4 mt-4">
					{filteredAgents.map((item, index) => {
						const draft = draftAgents[item.agent_id] ?? toAgentUpdateItem(item);
						const changed = changedAgentSet.has(item.agent_id);
						return (
							<Card key={item.agent_id}>
								<CardContent className="space-y-4 pt-6">
									<div className="flex flex-wrap items-center gap-2">
										<h3 className="font-semibold">{draft.label}</h3>
										<Badge variant="secondary">{draft.agent_id}</Badge>
										{draft.prompt_key ? <Badge variant="outline">{draft.prompt_key}</Badge> : null}
										{(item.has_override || changed) && (
											<Badge variant="outline">override</Badge>
										)}
									</div>
									<div className="space-y-2">
										<Label htmlFor={`agent-label-${index}`}>Namn</Label>
										<Input
											id={`agent-label-${index}`}
											value={draft.label}
											onChange={(event) =>
												onAgentChange(item.agent_id, {
													label: event.target.value,
												})
											}
										/>
									</div>
									<div className="space-y-2">
										<Label htmlFor={`agent-description-${index}`}>Beskrivning</Label>
										<Textarea
											id={`agent-description-${index}`}
											rows={3}
											value={draft.description}
											onChange={(event) =>
												onAgentChange(item.agent_id, {
													description: event.target.value,
												})
											}
										/>
									</div>
									<KeywordEditor
										entityId={item.agent_id}
										keywords={draft.keywords}
										onChange={(keywords) =>
											onAgentChange(item.agent_id, {
												keywords,
											})
										}
									/>
								</CardContent>
							</Card>
						);
					})}
					{filteredAgents.length === 0 ? (
						<Card>
							<CardContent className="py-8 text-center text-sm text-muted-foreground">
								Inga agents matchade sokningen.
							</CardContent>
						</Card>
					) : null}
				</TabsContent>

				<TabsContent value="intents" className="space-y-4 mt-4">
					{filteredIntents.map((item, index) => {
						const draft = draftIntents[item.intent_id] ?? toIntentUpdateItem(item);
						const changed = changedIntentSet.has(item.intent_id);
						return (
							<Card key={item.intent_id}>
								<CardContent className="space-y-4 pt-6">
									<div className="flex flex-wrap items-center gap-2">
										<h3 className="font-semibold">{draft.label}</h3>
										<Badge variant="secondary">{draft.intent_id}</Badge>
										<Badge variant="outline">route:{draft.route}</Badge>
										<Badge variant="outline">priority:{draft.priority}</Badge>
										{draft.enabled ? (
											<Badge variant="outline">enabled</Badge>
										) : (
											<Badge variant="destructive">disabled</Badge>
										)}
										{(item.has_override || changed) && (
											<Badge variant="outline">override</Badge>
										)}
									</div>
									<div className="space-y-2">
										<Label htmlFor={`intent-label-${index}`}>Namn</Label>
										<Input
											id={`intent-label-${index}`}
											value={draft.label}
											onChange={(event) =>
												onIntentChange(item.intent_id, {
													label: event.target.value,
												})
											}
										/>
									</div>
									<div className="space-y-2">
										<Label htmlFor={`intent-description-${index}`}>Beskrivning</Label>
										<Textarea
											id={`intent-description-${index}`}
											rows={3}
											value={draft.description}
											onChange={(event) =>
												onIntentChange(item.intent_id, {
													description: event.target.value,
												})
											}
										/>
									</div>
									<KeywordEditor
										entityId={item.intent_id}
										keywords={draft.keywords}
										onChange={(keywords) =>
											onIntentChange(item.intent_id, {
												keywords,
											})
										}
									/>
								</CardContent>
							</Card>
						);
					})}
					{filteredIntents.length === 0 ? (
						<Card>
							<CardContent className="py-8 text-center text-sm text-muted-foreground">
								Inga intents matchade sokningen.
							</CardContent>
						</Card>
					) : null}
				</TabsContent>

				<TabsContent value="tools" className="space-y-4 mt-4">
					{filteredToolCategories.map((category) => (
						<Card key={category.category_id}>
							<CardHeader>
								<CardTitle>{category.category_name}</CardTitle>
								<CardDescription>{category.tools.length} tools</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								{category.tools.map((tool, index) => {
									const draft = draftTools[tool.tool_id] ?? toToolUpdateItem(tool);
									const changed = changedToolSet.has(tool.tool_id);
									return (
										<div key={tool.tool_id}>
											{index > 0 ? <Separator className="my-4" /> : null}
											<div className="space-y-4">
												<div className="flex flex-wrap items-center gap-2">
													<h3 className="font-semibold">{draft.name}</h3>
													<Badge variant="secondary">{draft.tool_id}</Badge>
													<Badge variant="outline">{draft.category}</Badge>
													{(tool.has_override || changed) && (
														<Badge variant="outline">override</Badge>
													)}
												</div>
												<div className="space-y-2">
													<Label htmlFor={`tool-name-${tool.tool_id}`}>Namn</Label>
													<Input
														id={`tool-name-${tool.tool_id}`}
														value={draft.name}
														onChange={(event) =>
															onToolChange(tool.tool_id, {
																name: event.target.value,
															})
														}
													/>
												</div>
												<div className="space-y-2">
													<Label htmlFor={`tool-description-${tool.tool_id}`}>
														Beskrivning
													</Label>
													<Textarea
														id={`tool-description-${tool.tool_id}`}
														rows={3}
														value={draft.description}
														onChange={(event) =>
															onToolChange(tool.tool_id, {
																description: event.target.value,
															})
														}
													/>
												</div>
												<KeywordEditor
													entityId={tool.tool_id}
													keywords={draft.keywords}
													onChange={(keywords) =>
														onToolChange(tool.tool_id, {
															keywords,
														})
													}
												/>
											</div>
										</div>
									);
								})}
							</CardContent>
						</Card>
					))}
					{filteredToolCategories.length === 0 ? (
						<Card>
							<CardContent className="py-8 text-center text-sm text-muted-foreground">
								Inga tools matchade sokningen.
							</CardContent>
						</Card>
					) : null}
				</TabsContent>
			</Tabs>
		</div>
	);
}
