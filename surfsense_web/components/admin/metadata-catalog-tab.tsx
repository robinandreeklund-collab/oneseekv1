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

function toolIdPrefixForScope(scope: string): string | undefined {
	switch (scope) {
		case "smhi":
			return "smhi_";
		case "trafikverket":
			return "trafikverket_";
		case "scb":
			return "scb_";
		case "kolada":
			return "kolada_";
		case "riksdag":
			return "riksdag_";
		case "marketplace":
			return "marketplace_";
		case "bolagsverket":
			return "bolagsverket_";
		default:
			return undefined;
	}
}

export function MetadataCatalogTab({ searchSpaceId }: { searchSpaceId?: number }) {
	const queryClient = useQueryClient();
	const [sectionTab, setSectionTab] = useState<"agents" | "intents" | "tools">("agents");
	const [searchTerm, setSearchTerm] = useState("");
	const [isSaving, setIsSaving] = useState(false);
	const [draftTools, setDraftTools] = useState<Record<string, ToolMetadataUpdateItem>>({});
	const [draftAgents, setDraftAgents] = useState<Record<string, AgentMetadataUpdateItem>>({});
	const [draftIntents, setDraftIntents] = useState<Record<string, IntentMetadataUpdateItem>>({});
	const [auditScope, setAuditScope] = useState("smhi");
	const [includeExistingExamples, setIncludeExistingExamples] = useState(true);
	const [includeLlmGenerated, setIncludeLlmGenerated] = useState(true);
	const [llmQueriesPerTool, setLlmQueriesPerTool] = useState(3);
	const [maxQueriesPerTool, setMaxQueriesPerTool] = useState(6);
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
	const allToolOptions = useMemo(() => {
		const options: string[] = [];
		for (const category of data?.tool_categories ?? []) {
			for (const tool of category.tools) {
				options.push(tool.tool_id);
			}
		}
		return options.sort((left, right) => left.localeCompare(right, "sv"));
	}, [data?.tool_categories]);
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
				tool_id_prefix: toolIdPrefixForScope(auditScope),
				include_existing_examples: includeExistingExamples,
				include_llm_generated: includeLlmGenerated,
				llm_queries_per_tool: llmQueriesPerTool,
				max_queries_per_tool: maxQueriesPerTool,
			});
			setAuditResult(result);
			const nextAnnotations: Record<string, AuditAnnotationDraft> = {};
			for (const probe of result.probes) {
				const intentExpected = probe.intent.expected_label ?? null;
				const agentExpected = probe.agent.expected_label ?? null;
				const toolExpected = probe.tool.expected_label ?? probe.target_tool_id;
				const intentCorrect = intentExpected
					? probe.intent.predicted_label === intentExpected
					: true;
				const agentCorrect = agentExpected
					? probe.agent.predicted_label === agentExpected
					: true;
				const toolCorrect = toolExpected
					? probe.tool.predicted_label === toolExpected
					: true;
				nextAnnotations[probe.probe_id] = {
					intent_is_correct: intentCorrect,
					corrected_intent_id: intentExpected,
					agent_is_correct: agentCorrect,
					corrected_agent_id: agentExpected,
					tool_is_correct: toolCorrect,
					corrected_tool_id: toolExpected,
				};
			}
			setAuditAnnotations(nextAnnotations);
			setAuditSuggestions(null);
			setSelectedAuditSuggestionToolIds(new Set());
			setSelectedAuditSuggestionIntentIds(new Set());
			setSelectedAuditSuggestionAgentIds(new Set());
			toast.success(
				`Audit klar. ${result.summary.total_probes} probes analyserade.`
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
			const draft = auditAnnotations[probe.probe_id] ?? {
				intent_is_correct: probe.intent.predicted_label === probe.intent.expected_label,
				corrected_intent_id: probe.intent.expected_label ?? null,
				agent_is_correct: probe.agent.predicted_label === probe.agent.expected_label,
				corrected_agent_id: probe.agent.expected_label ?? null,
				tool_is_correct: probe.tool.predicted_label === probe.tool.expected_label,
				corrected_tool_id: probe.tool.expected_label ?? probe.target_tool_id,
			};
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
		setIsGeneratingAuditSuggestions(true);
		try {
			const response = await adminToolSettingsApiService.generateMetadataCatalogAuditSuggestions({
				search_space_id: data.search_space_id,
				metadata_patch: metadataPatchForDraft,
				annotations,
				max_suggestions: 30,
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
				`Genererade ${response.tool_suggestions.length + response.intent_suggestions.length + response.agent_suggestions.length} metadataforslag.`
			);
		} catch (_error) {
			toast.error("Kunde inte generera metadataforslag.");
		} finally {
			setIsGeneratingAuditSuggestions(false);
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
					<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-6">
						<div className="space-y-1">
							<Label>Scope</Label>
							<select
								value={auditScope}
								onChange={(event) => setAuditScope(event.target.value)}
								className="h-9 rounded-md border bg-transparent px-3 text-sm w-full"
							>
								<option value="smhi">SMHI</option>
								<option value="trafikverket">Trafikverket</option>
								<option value="scb">SCB</option>
								<option value="kolada">Kolada</option>
								<option value="riksdag">Riksdag</option>
								<option value="marketplace">Marketplace</option>
								<option value="bolagsverket">Bolagsverket</option>
								<option value="all">Alla tools</option>
							</select>
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

					{auditResult ? (
						<div className="space-y-4">
							<div className="flex flex-wrap gap-2">
								<Badge variant="outline">Probes: {auditResult.summary.total_probes}</Badge>
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
								{auditResult.probes.map((probe) => {
									const annotation = auditAnnotations[probe.probe_id] ?? {
										intent_is_correct:
											probe.intent.predicted_label === probe.intent.expected_label,
										corrected_intent_id: probe.intent.expected_label ?? null,
										agent_is_correct:
											probe.agent.predicted_label === probe.agent.expected_label,
										corrected_agent_id: probe.agent.expected_label ?? null,
										tool_is_correct: probe.tool.predicted_label === probe.tool.expected_label,
										corrected_tool_id:
											probe.tool.expected_label ?? probe.target_tool_id ?? null,
									};
									return (
										<div key={probe.probe_id} className="rounded border p-3 space-y-2">
											<p className="text-sm font-medium">{probe.query}</p>
											<div className="flex flex-wrap gap-2 text-xs">
												<Badge variant="outline">Expected path: {probe.expected_path}</Badge>
												<Badge variant="outline">Predicted path: {probe.predicted_path}</Badge>
												<Badge variant="secondary">{probe.source}</Badge>
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
