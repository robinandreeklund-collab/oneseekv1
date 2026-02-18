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

export function MetadataCatalogTab({ searchSpaceId }: { searchSpaceId?: number }) {
	const queryClient = useQueryClient();
	const [sectionTab, setSectionTab] = useState<"agents" | "intents" | "tools">("agents");
	const [searchTerm, setSearchTerm] = useState("");
	const [isSaving, setIsSaving] = useState(false);
	const [draftTools, setDraftTools] = useState<Record<string, ToolMetadataUpdateItem>>({});
	const [draftAgents, setDraftAgents] = useState<Record<string, AgentMetadataUpdateItem>>({});
	const [draftIntents, setDraftIntents] = useState<Record<string, IntentMetadataUpdateItem>>({});

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
