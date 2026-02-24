"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
	X,
	Zap,
	Bot,
	Wrench,
	Tag,
	FileText,
	Hash,
	Save,
	Trash2,
	Loader2,
	ChevronDown,
	ChevronRight,
	History,
	RotateCcw,
	MessageSquare,
	Link,
	FolderOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import type {
	FlowIntentNode,
	FlowAgentNode,
	FlowToolNode,
	PipelineNode,
} from "@/contracts/types/admin-flow-graph.types";
import type { AgentPromptItem, AgentPromptHistoryItem } from "@/contracts/types/agent-prompts.types";
import type { MetadataCatalogResponse, ToolMetadataItem } from "@/contracts/types/admin-tool-settings.types";
import { adminFlowGraphApiService } from "@/lib/apis/admin-flow-graph-api.service";
import { adminPromptsApiService } from "@/lib/apis/admin-prompts-api.service";
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";

const ALL_ROUTES = ["kunskap", "skapande", "jämförelse", "konversation"];

const DESCRIPTION_TEMPLATE_PLACEHOLDER =
	"[HUVUDIDENTIFIERARE] [KÄRNAKTIVITET]\n[STARKASTE KEYWORDS]\n[UNIK AVGRÄNSNING]\n[KOMMUN/SVERIGE]\n[EXEMPEL FRÅGOR]\n[EXKLUDERAR: ...]";

type SelectedNodeData =
	| { type: "intent"; data: FlowIntentNode }
	| { type: "agent"; data: FlowAgentNode }
	| { type: "tool"; data: FlowToolNode }
	| { type: "pipeline"; data: PipelineNode };

interface FlowDetailPanelProps {
	selectedNode: SelectedNodeData;
	connectionCounts: {
		agentsPerIntent: Record<string, number>;
		toolsPerAgent: Record<string, number>;
	};
	catalogData: MetadataCatalogResponse | null;
	agents: FlowAgentNode[];
	onClose: () => void;
	onDataChanged?: () => void;
}

// ── Shared prompt editor component ─────────────────────────────────

function InlinePromptEditor({
	promptKey,
	onSaved,
}: {
	promptKey: string;
	onSaved?: () => void;
}) {
	const [loading, setLoading] = useState(true);
	const [promptItem, setPromptItem] = useState<AgentPromptItem | null>(null);
	const [overrideValue, setOverrideValue] = useState("");
	const [saving, setSaving] = useState(false);
	const [showDefault, setShowDefault] = useState(false);
	const [showHistory, setShowHistory] = useState(false);
	const [history, setHistory] = useState<AgentPromptHistoryItem[]>([]);
	const [historyLoading, setHistoryLoading] = useState(false);

	useEffect(() => {
		let cancelled = false;
		setLoading(true);
		adminPromptsApiService.getAgentPrompts().then((data) => {
			if (cancelled) return;
			const item = data.items.find((i) => i.key === promptKey);
			setPromptItem(item ?? null);
			setOverrideValue(item?.override_prompt ?? "");
			setLoading(false);
		}).catch(() => {
			if (!cancelled) setLoading(false);
		});
		return () => { cancelled = true; };
	}, [promptKey]);

	const loadHistory = useCallback(async () => {
		if (history.length > 0) {
			setShowHistory(!showHistory);
			return;
		}
		setHistoryLoading(true);
		try {
			const data = await adminPromptsApiService.getAgentPromptHistory(promptKey);
			setHistory(data.items);
			setShowHistory(true);
		} catch {
			toast.error("Kunde inte ladda historik");
		} finally {
			setHistoryLoading(false);
		}
	}, [promptKey, history.length, showHistory]);

	const handleSave = useCallback(async () => {
		if (!promptItem) return;
		setSaving(true);
		try {
			await adminPromptsApiService.updateAgentPrompts({
				items: [{ key: promptKey, override_prompt: overrideValue.trim() || null }],
			});
			toast.success("Prompt sparad");
			onSaved?.();
		} catch {
			toast.error("Kunde inte spara prompt");
		} finally {
			setSaving(false);
		}
	}, [promptKey, overrideValue, promptItem, onSaved]);

	const handleReset = useCallback(() => {
		setOverrideValue("");
	}, []);

	if (loading) {
		return (
			<div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
				<Loader2 className="h-3 w-3 animate-spin" /> Laddar prompt...
			</div>
		);
	}

	if (!promptItem) {
		return (
			<p className="text-xs text-muted-foreground py-2">
				Ingen prompt hittad för nyckel: <span className="font-mono">{promptKey}</span>
			</p>
		);
	}

	const isDirty = overrideValue !== (promptItem.override_prompt ?? "");
	const isActive = Boolean(promptItem.override_prompt?.trim());

	return (
		<div className="space-y-3">
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-2">
					<Label className="text-xs font-semibold">Prompt</Label>
					{isActive && (
						<Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-emerald-500/15 text-emerald-700">
							Override aktiv
						</Badge>
					)}
					{isDirty && (
						<Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-amber-500/15 text-amber-700">
							Osparad
						</Badge>
					)}
				</div>
			</div>

			<p className="text-[11px] text-muted-foreground font-mono">{promptKey}</p>

			<Textarea
				value={overrideValue}
				onChange={(e) => setOverrideValue(e.target.value)}
				placeholder="Skriv override-prompt här (tomt = standard)..."
				className="text-xs min-h-[120px] leading-5 font-mono"
			/>

			<div className="flex items-center gap-2">
				<Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving || !isDirty}>
					{saving ? <Loader2 className="h-3 w-3 mr-1.5 animate-spin" /> : <Save className="h-3 w-3 mr-1.5" />}
					Spara
				</Button>
				<Button variant="ghost" size="sm" className="h-7 text-xs" onClick={handleReset} disabled={saving}>
					<RotateCcw className="h-3 w-3 mr-1.5" /> Återställ
				</Button>
			</div>

			{/* Default prompt */}
			<button
				type="button"
				className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
				onClick={() => setShowDefault(!showDefault)}
			>
				{showDefault ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
				Visa standardprompt
			</button>
			{showDefault && (
				<pre className="whitespace-pre-wrap rounded-md border bg-muted/40 p-2 text-[11px] text-muted-foreground max-h-[200px] overflow-y-auto">
					{promptItem.default_prompt}
				</pre>
			)}

			{/* History */}
			<button
				type="button"
				className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
				onClick={loadHistory}
			>
				{historyLoading ? (
					<Loader2 className="h-3 w-3 animate-spin" />
				) : showHistory ? (
					<ChevronDown className="h-3 w-3" />
				) : (
					<History className="h-3 w-3" />
				)}
				Versionshistorik
			</button>
			{showHistory && history.length > 0 && (
				<div className="space-y-2 max-h-[300px] overflow-y-auto">
					{history.map((entry, i) => (
						<div key={`${entry.updated_at}-${i}`} className="rounded-md border bg-muted/30 p-2 text-[11px]">
							<p className="text-muted-foreground">
								{new Date(entry.updated_at).toLocaleString("sv-SE")}
							</p>
							{entry.previous_prompt && (
								<div className="mt-1">
									<span className="text-muted-foreground">Före: </span>
									<span className="text-rose-600 line-through">{entry.previous_prompt?.substring(0, 80)}...</span>
								</div>
							)}
							<div className="mt-1">
								<span className="text-muted-foreground">Efter: </span>
								<span className="text-emerald-600">{(entry.new_prompt || "(tömd)").substring(0, 80)}...</span>
							</div>
						</div>
					))}
				</div>
			)}
			{showHistory && history.length === 0 && (
				<p className="text-[11px] text-muted-foreground">Ingen historik ännu.</p>
			)}
		</div>
	);
}

// ── Intent Detail ──────────────────────────────────────────────────

function IntentDetail({
	intent,
	agentCount,
	onDataChanged,
}: {
	intent: FlowIntentNode;
	agentCount: number;
	onDataChanged?: () => void;
}) {
	const [editing, setEditing] = useState(false);
	const [label, setLabel] = useState(intent.label);
	const [description, setDescription] = useState(intent.description);
	const [keywords, setKeywords] = useState(intent.keywords.join(", "));
	const [priority, setPriority] = useState(String(intent.priority));
	const [enabled, setEnabled] = useState(intent.enabled);
	const [saving, setSaving] = useState(false);
	const [deleting, setDeleting] = useState(false);
	const [confirmDelete, setConfirmDelete] = useState(false);

	const handleSave = useCallback(async () => {
		setSaving(true);
		try {
			await adminFlowGraphApiService.upsertIntent({
				intent_id: intent.intent_id,
				label,
				description,
				keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
				priority: parseInt(priority, 10) || 500,
				enabled,
			});
			toast.success("Intent sparad");
			setEditing(false);
			onDataChanged?.();
		} catch {
			toast.error("Kunde inte spara intent");
		} finally {
			setSaving(false);
		}
	}, [intent.intent_id, label, description, keywords, priority, enabled, onDataChanged]);

	const handleDelete = useCallback(async () => {
		setDeleting(true);
		try {
			await adminFlowGraphApiService.deleteIntent(intent.intent_id);
			toast.success("Intent borttagen");
			onDataChanged?.();
		} catch {
			toast.error("Kunde inte ta bort intent");
		} finally {
			setDeleting(false);
			setConfirmDelete(false);
		}
	}, [intent.intent_id, onDataChanged]);

	return (
		<div className="space-y-4">
			{/* Header */}
			<div className="flex items-center gap-3">
				<div className="flex items-center justify-center h-10 w-10 rounded-lg bg-violet-500/10">
					<Zap className="h-5 w-5 text-violet-500" />
				</div>
				<div className="flex-1 min-w-0">
					<h3 className="text-base font-semibold truncate">{intent.label}</h3>
					<p className="text-xs text-muted-foreground">Intent</p>
				</div>
			</div>

			<Separator />

			{/* Properties */}
			<div className="space-y-3">
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Intent ID</span>
					<span className="text-xs font-mono">{intent.intent_id}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Route</span>
					<Badge variant="secondary" className="text-xs">{intent.route}</Badge>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Kopplade agenter</span>
					<span className="text-xs font-mono">{agentCount}</span>
				</div>
			</div>

			<Separator />

			{/* Edit mode toggle */}
			<div className="flex items-center justify-between">
				<Label className="text-xs font-semibold">Redigera intent</Label>
				<Button
					variant="ghost"
					size="sm"
					className="h-6 text-xs px-2"
					onClick={() => {
						if (editing) {
							setLabel(intent.label);
							setDescription(intent.description);
							setKeywords(intent.keywords.join(", "));
							setPriority(String(intent.priority));
							setEnabled(intent.enabled);
						}
						setEditing(!editing);
					}}
				>
					{editing ? "Avbryt" : "Redigera"}
				</Button>
			</div>

			{editing ? (
				<div className="space-y-3">
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground">Label</Label>
						<Input value={label} onChange={(e) => setLabel(e.target.value)} className="text-xs h-8" />
					</div>
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground">Beskrivning</Label>
						<Textarea
							value={description}
							onChange={(e) => setDescription(e.target.value)}
							className="text-xs min-h-[80px] font-mono leading-5"
							placeholder={DESCRIPTION_TEMPLATE_PLACEHOLDER}
						/>
						<p className="text-[10px] text-muted-foreground">
							Använd mallen: HUVUDIDENTIFIERARE, KÄRNAKTIVITET, KEYWORDS, AVGRÄNSNING, EXEMPEL
						</p>
					</div>
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground">Nyckelord (komma-separerade)</Label>
						<Textarea
							value={keywords}
							onChange={(e) => setKeywords(e.target.value)}
							className="text-xs min-h-[60px]"
						/>
					</div>
					<div className="grid grid-cols-2 gap-2">
						<div className="space-y-1">
							<Label className="text-[11px] text-muted-foreground">Prioritet</Label>
							<Input
								type="number"
								value={priority}
								onChange={(e) => setPriority(e.target.value)}
								className="text-xs h-8"
							/>
						</div>
						<div className="space-y-1">
							<Label className="text-[11px] text-muted-foreground">Status</Label>
							<div className="flex items-center gap-2 h-8">
								<Switch checked={enabled} onCheckedChange={setEnabled} />
								<span className="text-xs">{enabled ? "Aktiv" : "Inaktiv"}</span>
							</div>
						</div>
					</div>
					<Button size="sm" className="h-7 text-xs w-full" onClick={handleSave} disabled={saving}>
						{saving ? <Loader2 className="h-3 w-3 mr-1.5 animate-spin" /> : <Save className="h-3 w-3 mr-1.5" />}
						Spara intent
					</Button>
				</div>
			) : (
				<div className="space-y-2">
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
							<FileText className="h-3 w-3" /> Beskrivning
						</Label>
						<p className="text-xs text-muted-foreground whitespace-pre-wrap">{intent.description || "Ingen beskrivning"}</p>
					</div>
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
							<Tag className="h-3 w-3" /> Nyckelord
						</Label>
						<div className="flex flex-wrap gap-1">
							{intent.keywords.map((kw) => (
								<Badge key={kw} variant="outline" className="text-[10px] px-1.5 py-0">{kw}</Badge>
							))}
						</div>
					</div>
					<div className="flex items-center justify-between">
						<span className="text-xs text-muted-foreground">Prioritet</span>
						<span className="text-xs font-mono">{intent.priority}</span>
					</div>
					<div className="flex items-center justify-between">
						<span className="text-xs text-muted-foreground">Status</span>
						<Badge variant={intent.enabled ? "default" : "destructive"} className="text-xs">
							{intent.enabled ? "Aktiv" : "Inaktiv"}
						</Badge>
					</div>
				</div>
			)}

			<Separator />

			{/* Delete */}
			{!confirmDelete ? (
				<Button
					variant="ghost"
					size="sm"
					className="h-7 text-xs text-destructive hover:text-destructive w-full"
					onClick={() => setConfirmDelete(true)}
				>
					<Trash2 className="h-3 w-3 mr-1.5" /> Ta bort intent
				</Button>
			) : (
				<div className="space-y-2 rounded-md border border-destructive/30 bg-destructive/5 p-2">
					<p className="text-xs text-destructive">
						Bekräfta borttagning av <strong>{intent.label}</strong>?
					</p>
					<div className="flex gap-2">
						<Button
							variant="destructive"
							size="sm"
							className="h-7 text-xs flex-1"
							onClick={handleDelete}
							disabled={deleting}
						>
							{deleting ? <Loader2 className="h-3 w-3 mr-1.5 animate-spin" /> : <Trash2 className="h-3 w-3 mr-1.5" />}
							Ja, ta bort
						</Button>
						<Button
							variant="ghost"
							size="sm"
							className="h-7 text-xs"
							onClick={() => setConfirmDelete(false)}
						>
							Avbryt
						</Button>
					</div>
				</div>
			)}
		</div>
	);
}

// ── Agent Detail ───────────────────────────────────────────────────

function AgentDetail({
	agent,
	toolCount,
	onDataChanged,
}: {
	agent: FlowAgentNode;
	toolCount: number;
	onDataChanged?: () => void;
}) {
	const [editingRoutes, setEditingRoutes] = useState(false);
	const [selectedRoutes, setSelectedRoutes] = useState<string[]>(agent.routes ?? []);
	const [savingRoutes, setSavingRoutes] = useState(false);
	const [editingDesc, setEditingDesc] = useState(false);
	const [description, setDescription] = useState(agent.description);

	const handleToggleRoute = useCallback((route: string, checked: boolean) => {
		setSelectedRoutes((prev) =>
			checked ? [...prev, route] : prev.filter((r) => r !== route)
		);
	}, []);

	const handleSaveRoutes = useCallback(async () => {
		setSavingRoutes(true);
		try {
			await adminFlowGraphApiService.updateAgentRoutes(agent.agent_id, selectedRoutes);
			toast.success("Routes sparade");
			setEditingRoutes(false);
			onDataChanged?.();
		} catch {
			toast.error("Kunde inte spara routes");
		} finally {
			setSavingRoutes(false);
		}
	}, [agent.agent_id, selectedRoutes, onDataChanged]);

	// Determine the prompt key for this agent
	const agentPromptKey = agent.prompt_key
		? `agent.${agent.prompt_key}.system`
		: null;

	return (
		<div className="space-y-4">
			{/* Header */}
			<div className="flex items-center gap-3">
				<div className="flex items-center justify-center h-10 w-10 rounded-lg bg-blue-500/10">
					<Bot className="h-5 w-5 text-blue-500" />
				</div>
				<div className="flex-1 min-w-0">
					<h3 className="text-base font-semibold truncate">{agent.label}</h3>
					<p className="text-xs text-muted-foreground">Agent</p>
				</div>
			</div>

			<Separator />

			{/* Properties */}
			<div className="space-y-3">
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Agent ID</span>
					<span className="text-xs font-mono">{agent.agent_id}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Namespace</span>
					<span className="text-xs font-mono">{agent.namespace.join("/")}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Kopplade verktyg</span>
					<span className="text-xs font-mono">{toolCount}</span>
				</div>
			</div>

			<Separator />

			{/* Routes (editable) */}
			<div className="space-y-2">
				<div className="flex items-center justify-between">
					<Label className="text-xs flex items-center gap-1.5">
						<Zap className="h-3 w-3" /> Tillhör intents
					</Label>
					<Button
						variant="ghost"
						size="sm"
						className="h-6 text-xs px-2"
						onClick={() => {
							if (editingRoutes) {
								setSelectedRoutes(agent.routes ?? []);
							}
							setEditingRoutes(!editingRoutes);
						}}
					>
						{editingRoutes ? "Avbryt" : "Redigera"}
					</Button>
				</div>
				{editingRoutes ? (
					<div className="space-y-2">
						{ALL_ROUTES.map((route) => (
							<div key={route} className="flex items-center gap-2">
								<Checkbox
									id={`route-${route}`}
									checked={selectedRoutes.includes(route)}
									onCheckedChange={(checked) =>
										handleToggleRoute(route, checked === true)
									}
								/>
								<label htmlFor={`route-${route}`} className="text-xs cursor-pointer">
									{route}
								</label>
							</div>
						))}
						<Button
							size="sm"
							className="h-7 text-xs"
							onClick={handleSaveRoutes}
							disabled={savingRoutes}
						>
							{savingRoutes ? (
								<Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
							) : (
								<Save className="h-3 w-3 mr-1.5" />
							)}
							Spara
						</Button>
					</div>
				) : (
					<div className="flex flex-wrap gap-1">
						{(agent.routes ?? []).length > 0 ? (
							(agent.routes ?? []).map((r) => (
								<Badge key={r} variant="secondary" className="text-[10px] px-1.5 py-0">{r}</Badge>
							))
						) : (
							<span className="text-xs text-muted-foreground">Inga intents</span>
						)}
					</div>
				)}
			</div>

			<Separator />

			{/* Description */}
			<div className="space-y-2">
				<div className="flex items-center justify-between">
					<Label className="text-xs flex items-center gap-1.5">
						<FileText className="h-3 w-3" /> Beskrivning
					</Label>
					<Button
						variant="ghost"
						size="sm"
						className="h-6 text-xs px-2"
						onClick={() => setEditingDesc(!editingDesc)}
					>
						{editingDesc ? "Stäng" : "Visa"}
					</Button>
				</div>
				{editingDesc ? (
					<p className="text-xs text-muted-foreground whitespace-pre-wrap rounded-md border bg-muted/40 p-2">
						{agent.description || "Ingen beskrivning"}
					</p>
				) : (
					<p className="text-xs text-muted-foreground line-clamp-2">{agent.description || "Ingen beskrivning"}</p>
				)}
			</div>

			{/* Keywords */}
			<div className="space-y-2">
				<Label className="text-xs flex items-center gap-1.5">
					<Tag className="h-3 w-3" /> Nyckelord
				</Label>
				<div className="flex flex-wrap gap-1">
					{agent.keywords.map((kw) => (
						<Badge key={kw} variant="outline" className="text-[10px] px-1.5 py-0">{kw}</Badge>
					))}
				</div>
			</div>

			{/* Agent Prompt */}
			{agentPromptKey && (
				<>
					<Separator />
					<InlinePromptEditor promptKey={agentPromptKey} onSaved={onDataChanged} />
				</>
			)}
		</div>
	);
}

// ── Tool Detail (Full editing) ─────────────────────────────────────

function ToolDetail({
	tool,
	catalogData,
	agents,
	onDataChanged,
}: {
	tool: FlowToolNode;
	catalogData: MetadataCatalogResponse | null;
	agents: FlowAgentNode[];
	onDataChanged?: () => void;
}) {
	// Find the full metadata from catalog
	const catalogTool = useMemo((): ToolMetadataItem | null => {
		if (!catalogData) return null;
		for (const cat of catalogData.tool_categories) {
			const found = cat.tools.find((t) => t.tool_id === tool.tool_id);
			if (found) return found;
		}
		return null;
	}, [catalogData, tool.tool_id]);

	const [editing, setEditing] = useState(false);
	const [name, setName] = useState(catalogTool?.name ?? tool.label);
	const [description, setDescription] = useState(catalogTool?.description ?? "");
	const [keywords, setKeywords] = useState((catalogTool?.keywords ?? []).join(", "));
	const [exampleQueries, setExampleQueries] = useState((catalogTool?.example_queries ?? []).join("\n"));
	const [category, setCategory] = useState(catalogTool?.category ?? tool.agent_id);
	const [basePath, setBasePath] = useState(catalogTool?.base_path ?? "");
	const [selectedAgentId, setSelectedAgentId] = useState(tool.agent_id);
	const [saving, setSaving] = useState(false);

	// Reset form when tool changes
	useEffect(() => {
		setName(catalogTool?.name ?? tool.label);
		setDescription(catalogTool?.description ?? "");
		setKeywords((catalogTool?.keywords ?? []).join(", "));
		setExampleQueries((catalogTool?.example_queries ?? []).join("\n"));
		setCategory(catalogTool?.category ?? tool.agent_id);
		setBasePath(catalogTool?.base_path ?? "");
		setSelectedAgentId(tool.agent_id);
		setEditing(false);
	}, [tool.tool_id, tool.label, tool.agent_id, catalogTool]);

	const handleSave = useCallback(async () => {
		setSaving(true);
		try {
			// Update metadata catalog
			if (catalogData) {
				await adminToolSettingsApiService.updateMetadataCatalog(
					{
						tools: [{
							tool_id: tool.tool_id,
							name: name.trim(),
							description: description.trim(),
							keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
							example_queries: exampleQueries.split("\n").map((q) => q.trim()).filter(Boolean),
							category: category.trim(),
							base_path: basePath.trim() || null,
						}],
					},
					catalogData.search_space_id,
				);
			}

			// If agent assignment changed, update flow graph
			if (selectedAgentId !== tool.agent_id) {
				// Remove from old agent
				if (tool.agent_id) {
					const sourceTools = (catalogData?.agents ?? [])
						.find((a) => a.agent_id === tool.agent_id)
						?.flow_tools?.filter((t) => t.tool_id !== tool.tool_id)
						.map((t) => ({ tool_id: t.tool_id, label: t.label })) ?? [];
					await adminFlowGraphApiService.updateAgentTools(tool.agent_id, sourceTools);
				}

				// Add to new agent
				if (selectedAgentId) {
					const targetFlowTools = (catalogData?.agents ?? [])
						.find((a) => a.agent_id === selectedAgentId)
						?.flow_tools?.map((t) => ({ tool_id: t.tool_id, label: t.label })) ?? [];
					targetFlowTools.push({ tool_id: tool.tool_id, label: name.trim() || tool.label });
					await adminFlowGraphApiService.updateAgentTools(selectedAgentId, targetFlowTools);
				}
			}

			toast.success("Verktyg uppdaterat");
			setEditing(false);
			onDataChanged?.();
		} catch {
			toast.error("Kunde inte spara verktyg");
		} finally {
			setSaving(false);
		}
	}, [
		tool.tool_id,
		tool.agent_id,
		tool.label,
		catalogData,
		name,
		description,
		keywords,
		exampleQueries,
		category,
		basePath,
		selectedAgentId,
		onDataChanged,
	]);

	const handleCancel = useCallback(() => {
		setName(catalogTool?.name ?? tool.label);
		setDescription(catalogTool?.description ?? "");
		setKeywords((catalogTool?.keywords ?? []).join(", "));
		setExampleQueries((catalogTool?.example_queries ?? []).join("\n"));
		setCategory(catalogTool?.category ?? tool.agent_id);
		setBasePath(catalogTool?.base_path ?? "");
		setSelectedAgentId(tool.agent_id);
		setEditing(false);
	}, [catalogTool, tool]);

	return (
		<div className="space-y-4">
			{/* Header */}
			<div className="flex items-center gap-3">
				<div className="flex items-center justify-center h-10 w-10 rounded-lg bg-emerald-500/10">
					<Wrench className="h-5 w-5 text-emerald-500" />
				</div>
				<div className="flex-1 min-w-0">
					<h3 className="text-base font-semibold truncate">{tool.label}</h3>
					<p className="text-xs text-muted-foreground">Verktyg</p>
				</div>
			</div>

			<Separator />

			{/* Always-visible properties */}
			<div className="space-y-3">
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Tool ID</span>
					<span className="text-xs font-mono truncate max-w-[180px]">{tool.tool_id}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Agent</span>
					<Badge variant="secondary" className="text-xs">{tool.agent_id || "Ej tilldelad"}</Badge>
				</div>
				{catalogTool?.category && (
					<div className="flex items-center justify-between">
						<span className="text-xs text-muted-foreground">Kategori</span>
						<Badge variant="outline" className="text-xs">{catalogTool.category}</Badge>
					</div>
				)}
				{catalogTool?.has_override && (
					<div className="flex items-center justify-between">
						<span className="text-xs text-muted-foreground">Override</span>
						<Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-amber-500/15 text-amber-700">
							Har override
						</Badge>
					</div>
				)}
			</div>

			<Separator />

			{/* Edit toggle */}
			<div className="flex items-center justify-between">
				<Label className="text-xs font-semibold">Redigera verktyg</Label>
				<Button
					variant="ghost"
					size="sm"
					className="h-6 text-xs px-2"
					onClick={() => {
						if (editing) {
							handleCancel();
						} else {
							setEditing(true);
						}
					}}
				>
					{editing ? "Avbryt" : "Redigera"}
				</Button>
			</div>

			{editing ? (
				<div className="space-y-3">
					{/* Name */}
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
							<Tag className="h-3 w-3" /> Namn
						</Label>
						<Input
							value={name}
							onChange={(e) => setName(e.target.value)}
							className="text-xs h-8"
						/>
					</div>

					{/* Description */}
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
							<FileText className="h-3 w-3" /> Beskrivning
						</Label>
						<Textarea
							value={description}
							onChange={(e) => setDescription(e.target.value)}
							className="text-xs min-h-[120px] font-mono leading-5"
							placeholder={DESCRIPTION_TEMPLATE_PLACEHOLDER}
						/>
						<p className="text-[10px] text-muted-foreground">
							Mall: [HUVUDIDENTIFIERARE] [KÄRNAKTIVITET] [STARKASTE KEYWORDS] [UNIK AVGRÄNSNING] [KOMMUN/SVERIGE] [EXEMPEL FRÅGOR] [EXKLUDERAR: ...]
						</p>
					</div>

					{/* Keywords */}
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
							<Tag className="h-3 w-3" /> Nyckelord (komma-separerade)
						</Label>
						<Textarea
							value={keywords}
							onChange={(e) => setKeywords(e.target.value)}
							className="text-xs min-h-[60px]"
							placeholder="väder, temperatur, prognos, SMHI"
						/>
					</div>

					{/* Example queries */}
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
							<MessageSquare className="h-3 w-3" /> Exempelfrågor (en per rad)
						</Label>
						<Textarea
							value={exampleQueries}
							onChange={(e) => setExampleQueries(e.target.value)}
							className="text-xs min-h-[80px]"
							placeholder={"Vad blir vädret imorgon i Stockholm?\nVisa temperatur för Göteborg\nRegnar det idag?"}
						/>
					</div>

					{/* Category */}
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
							<FolderOpen className="h-3 w-3" /> Kategori
						</Label>
						<Input
							value={category}
							onChange={(e) => setCategory(e.target.value)}
							className="text-xs h-8"
							placeholder="weather, maps, statistics..."
						/>
					</div>

					{/* Agent assignment */}
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
							<Bot className="h-3 w-3" /> Agent-tilldelning
						</Label>
						<select
							value={selectedAgentId}
							onChange={(e) => setSelectedAgentId(e.target.value)}
							className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
						>
							<option value="">Ej tilldelad</option>
							{agents.map((a) => (
								<option key={a.agent_id} value={a.agent_id}>
									{a.label} ({a.agent_id})
								</option>
							))}
						</select>
						{selectedAgentId !== tool.agent_id && (
							<p className="text-[10px] text-amber-600">
								Namespace ändras: {tool.agent_id || "(ingen)"} → {selectedAgentId || "(ingen)"}
							</p>
						)}
					</div>

					{/* Base path */}
					<div className="space-y-1">
						<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
							<Link className="h-3 w-3" /> Base path
						</Label>
						<Input
							value={basePath}
							onChange={(e) => setBasePath(e.target.value)}
							className="text-xs h-8 font-mono"
							placeholder="/api/v1/..."
						/>
					</div>

					{/* Save / Cancel buttons */}
					<div className="flex gap-2">
						<Button
							size="sm"
							className="h-7 text-xs flex-1"
							onClick={handleSave}
							disabled={saving}
						>
							{saving ? (
								<Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
							) : (
								<Save className="h-3 w-3 mr-1.5" />
							)}
							Spara ändringar
						</Button>
						<Button
							variant="ghost"
							size="sm"
							className="h-7 text-xs"
							onClick={handleCancel}
							disabled={saving}
						>
							Avbryt
						</Button>
					</div>
				</div>
			) : (
				/* Read-only view of all metadata */
				<div className="space-y-3">
					{catalogTool ? (
						<>
							{/* Name */}
							<div className="space-y-1">
								<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
									<Tag className="h-3 w-3" /> Namn
								</Label>
								<p className="text-xs">{catalogTool.name}</p>
							</div>

							{/* Description */}
							<div className="space-y-1">
								<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
									<FileText className="h-3 w-3" /> Beskrivning
								</Label>
								<p className="text-xs text-muted-foreground whitespace-pre-wrap rounded-md border bg-muted/40 p-2">
									{catalogTool.description || "Ingen beskrivning"}
								</p>
							</div>

							{/* Keywords */}
							<div className="space-y-1">
								<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
									<Tag className="h-3 w-3" /> Nyckelord
								</Label>
								<div className="flex flex-wrap gap-1">
									{catalogTool.keywords.length > 0 ? (
										catalogTool.keywords.map((kw) => (
											<Badge key={kw} variant="outline" className="text-[10px] px-1.5 py-0">
												{kw}
											</Badge>
										))
									) : (
										<span className="text-[10px] text-muted-foreground italic">Inga nyckelord</span>
									)}
								</div>
							</div>

							{/* Example queries */}
							<div className="space-y-1">
								<Label className="text-[11px] text-muted-foreground flex items-center gap-1">
									<MessageSquare className="h-3 w-3" /> Exempelfrågor
								</Label>
								{catalogTool.example_queries.length > 0 ? (
									<ul className="space-y-0.5">
										{catalogTool.example_queries.map((q, i) => (
											<li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
												<span className="text-muted-foreground/50 shrink-0">•</span>
												<span>{q}</span>
											</li>
										))}
									</ul>
								) : (
									<span className="text-[10px] text-muted-foreground italic">Inga exempelfrågor</span>
								)}
							</div>

							{/* Category */}
							<div className="flex items-center justify-between">
								<span className="text-xs text-muted-foreground flex items-center gap-1">
									<FolderOpen className="h-3 w-3" /> Kategori
								</span>
								<span className="text-xs font-mono">{catalogTool.category}</span>
							</div>

							{/* Base path */}
							{catalogTool.base_path && (
								<div className="flex items-center justify-between">
									<span className="text-xs text-muted-foreground flex items-center gap-1">
										<Link className="h-3 w-3" /> Base path
									</span>
									<span className="text-xs font-mono truncate max-w-[180px]">
										{catalogTool.base_path}
									</span>
								</div>
							)}
						</>
					) : (
						<p className="text-xs text-muted-foreground italic">
							Ingen metadata hittad i katalogen för detta verktyg.
							Klicka "Redigera" för att lägga till metadata.
						</p>
					)}
				</div>
			)}
		</div>
	);
}

// ── Pipeline Detail ────────────────────────────────────────────────

function PipelineDetail({
	node,
	onDataChanged,
}: {
	node: PipelineNode;
	onDataChanged?: () => void;
}) {
	return (
		<div className="space-y-4">
			<div className="flex items-center gap-3">
				<div className="flex items-center justify-center h-10 w-10 rounded-lg bg-primary/10">
					<Hash className="h-5 w-5 text-primary" />
				</div>
				<div className="flex-1 min-w-0">
					<h3 className="text-base font-semibold truncate">{node.label}</h3>
					<p className="text-xs text-muted-foreground">Pipeline-nod</p>
				</div>
			</div>

			<Separator />

			<div className="space-y-3">
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Nod-ID</span>
					<span className="text-xs font-mono">{node.id.replace("node:", "")}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Steg</span>
					<Badge variant="secondary" className="text-xs">{node.stage}</Badge>
				</div>
			</div>

			<Separator />

			<div className="space-y-2">
				<Label className="text-xs flex items-center gap-1.5">
					<FileText className="h-3 w-3" /> Beskrivning
				</Label>
				<p className="text-xs text-muted-foreground">{node.description || "Ingen beskrivning"}</p>
			</div>

			{/* Inline prompt editor */}
			{node.prompt_key && (
				<>
					<Separator />
					<InlinePromptEditor promptKey={node.prompt_key} onSaved={onDataChanged} />
				</>
			)}

			{!node.prompt_key && (
				<>
					<Separator />
					<p className="text-xs text-muted-foreground italic">Denna nod har ingen direkt kopplad prompt.</p>
				</>
			)}
		</div>
	);
}

// ── Main panel ─────────────────────────────────────────────────────

export function FlowDetailPanel({
	selectedNode,
	connectionCounts,
	catalogData,
	agents,
	onClose,
	onDataChanged,
}: FlowDetailPanelProps) {
	return (
		<div className="w-96 border-l bg-background overflow-y-auto">
			<div className="p-4">
				<div className="flex items-center justify-between mb-4">
					<h3 className="text-sm font-semibold text-muted-foreground">Detaljer</h3>
					<Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={onClose}>
						<X className="h-4 w-4" />
					</Button>
				</div>

				{selectedNode.type === "intent" && (
					<IntentDetail
						intent={selectedNode.data}
						agentCount={connectionCounts.agentsPerIntent[selectedNode.data.id] ?? 0}
						onDataChanged={onDataChanged}
					/>
				)}
				{selectedNode.type === "agent" && (
					<AgentDetail
						agent={selectedNode.data}
						toolCount={connectionCounts.toolsPerAgent[selectedNode.data.id] ?? 0}
						onDataChanged={onDataChanged}
					/>
				)}
				{selectedNode.type === "tool" && (
					<ToolDetail
						tool={selectedNode.data}
						catalogData={catalogData}
						agents={agents}
						onDataChanged={onDataChanged}
					/>
				)}
				{selectedNode.type === "pipeline" && (
					<PipelineDetail node={selectedNode.data} onDataChanged={onDataChanged} />
				)}
			</div>
		</div>
	);
}
