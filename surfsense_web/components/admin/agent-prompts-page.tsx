"use client";

import { useQuery } from "@tanstack/react-query";
import { diffLines } from "diff";
import { useAtomValue } from "jotai";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import type { AgentPromptItem } from "@/contracts/types/agent-prompts.types";
import { adminPromptsApiService } from "@/lib/apis/admin-prompts-api.service";
import { adminCacheApiService } from "@/lib/apis/admin-cache-api.service";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { ArrowRightIcon } from "lucide-react";

type PromptViewMode = "all" | "agent" | "system";

const AGENT_ORDER = [
	"knowledge",
	"action",
	"media",
	"browser",
	"code",
	"kartor",
	"statistics",
	"bolag",
	"trafik",
	"riksdagen",
	"synthesis",
	"smalltalk",
];

const AGENT_PROMPT_ORDER: Record<string, string[]> = {
	knowledge: ["system", "docs", "internal", "external"],
	action: ["system", "web", "media", "travel", "data"],
};

const SYSTEM_SECTION_ORDER = [
	"core",
	"router",
	"supervisor",
	"worker",
	"compare",
	"citations",
	"other",
];
const SYSTEM_SECTION_LABELS: Record<string, string> = {
	core: "Core",
	router: "Router",
	supervisor: "Supervisor",
	worker: "Workers",
	compare: "Compare",
	citations: "Citations",
	other: "Övrigt",
};

const ROUTER_NODES = [
	{ label: "Top-level router", key: "router.top_level" },
	{ label: "Knowledge router", key: "router.knowledge" },
	{ label: "Action router", key: "router.action" },
];

const SYSTEM_NODES = [
	{ label: "Core system prompt", key: "system.default.instructions" },
	{ label: "Supervisor", key: "agent.supervisor.system" },
	{ label: "Supervisor · Critic", key: "supervisor.critic.system" },
	{ label: "Supervisor · Loop guard", key: "supervisor.loop_guard.message" },
	{ label: "Supervisor · Tool-limit guard", key: "supervisor.tool_limit_guard.message" },
	{
		label: "Supervisor · Trafik enforcement",
		key: "supervisor.trafik.enforcement.message",
	},
	{ label: "Worker · Knowledge", key: "agent.worker.knowledge" },
	{ label: "Worker · Action", key: "agent.worker.action" },
	{ label: "Compare · Analysis", key: "compare.analysis.system" },
	{ label: "Compare · External", key: "compare.external.system" },
	{ label: "Citation instructions", key: "citation.instructions" },
];

const AGENT_NODES = [
	{
		label: "Knowledge",
		agent: "knowledge",
		keys: [
			"agent.knowledge.system",
			"agent.knowledge.docs",
			"agent.knowledge.internal",
			"agent.knowledge.external",
		],
	},
	{
		label: "Action",
		agent: "action",
		keys: [
			"agent.action.system",
			"agent.action.web",
			"agent.action.media",
			"agent.action.travel",
			"agent.action.data",
		],
	},
	{ label: "Media", agent: "media", keys: ["agent.media.system"] },
	{ label: "Browser", agent: "browser", keys: ["agent.browser.system"] },
	{ label: "Code", agent: "code", keys: ["agent.code.system"] },
	{ label: "Kartor", agent: "kartor", keys: ["agent.kartor.system"] },
	{ label: "Statistics", agent: "statistics", keys: ["agent.statistics.system"] },
	{ label: "Bolag", agent: "bolag", keys: ["agent.bolag.system"] },
	{ label: "Trafik", agent: "trafik", keys: ["agent.trafik.system"] },
	{ label: "Riksdagen", agent: "riksdagen", keys: ["agent.riksdagen.system"] },
	{ label: "Synthesis", agent: "synthesis", keys: ["agent.synthesis.system"] },
	{ label: "Smalltalk", agent: "smalltalk", keys: ["agent.smalltalk.system"] },
];

function buildGraphEdges(agents: Array<{ agent: string }>) {
	const edges: Array<{ from: string; to: string }> = [];
	for (const node of ROUTER_NODES) {
		edges.push({
			from: `prompt:${node.key}`,
			to: "prompt:agent.supervisor.system",
		});
	}
	for (const agent of agents) {
		edges.push({
			from: "prompt:agent.supervisor.system",
			to: `agent:${agent.agent}`,
		});
		for (const systemNode of SYSTEM_NODES) {
			edges.push({
				from: `agent:${agent.agent}`,
				to: `prompt:${systemNode.key}`,
			});
		}
	}
	return edges;
}

export function AdminPromptsPage() {
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const [overrides, setOverrides] = useState<Record<string, string>>({});
	const [isSaving, setIsSaving] = useState(false);
	const [isUpdatingCache, setIsUpdatingCache] = useState(false);
	const [isClearingCache, setIsClearingCache] = useState(false);
	const [viewMode, setViewMode] = useState<PromptViewMode>("all");
	const [selectedAgent, setSelectedAgent] = useState<string>("action");
	const [searchTerm, setSearchTerm] = useState("");
	const [pendingScrollKey, setPendingScrollKey] = useState<string | null>(null);
	const [highlightKey, setHighlightKey] = useState<string | null>(null);
	const promptRefs = useMemo(() => new Map<string, HTMLDivElement>(), []);
	const graphRef = useRef<HTMLDivElement | null>(null);
	const nodeRefs = useRef(new Map<string, HTMLButtonElement>());
	const [graphLines, setGraphLines] = useState<
		Array<{ x1: number; y1: number; x2: number; y2: number }>
	>([]);

	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["admin-prompts"],
		queryFn: () => adminPromptsApiService.getAgentPrompts(),
		enabled: !!currentUser,
	});

	const {
		data: cacheState,
		isLoading: cacheLoading,
		refetch: refetchCacheState,
	} = useQuery({
		queryKey: ["admin-cache"],
		queryFn: () => adminCacheApiService.getCacheState(),
		enabled: !!currentUser,
	});

	useEffect(() => {
		if (!data?.items) return;
		const next: Record<string, string> = {};
		for (const item of data.items) {
			next[item.key] = item.override_prompt ?? "";
		}
		setOverrides(next);
	}, [data?.items]);

	const items = data?.items ?? [];
	const promptMeta = useMemo(() => {
		return items.map((item) => {
			const key = item.key;
			if (key.startsWith("agent.worker.")) {
				return {
					item,
					group: "system" as const,
					section: "worker",
				};
			}
			if (key.startsWith("agent.supervisor.")) {
				return {
					item,
					group: "system" as const,
					section: "supervisor",
				};
			}
			if (key.startsWith("router.")) {
				return {
					item,
					group: "system" as const,
					section: "router",
				};
			}
			if (key.startsWith("system.")) {
				return {
					item,
					group: "system" as const,
					section: "core",
				};
			}
			if (key.startsWith("supervisor.")) {
				return {
					item,
					group: "system" as const,
					section: "supervisor",
				};
			}
			if (key.startsWith("compare.")) {
				return {
					item,
					group: "system" as const,
					section: "compare",
				};
			}
			if (key.startsWith("citation.")) {
				return {
					item,
					group: "system" as const,
					section: "citations",
				};
			}
			if (key.startsWith("agent.")) {
				const parts = key.split(".");
				const agent = parts[1] ?? "unknown";
				const variant = parts[2] ?? "";
				return {
					item,
					group: "agent" as const,
					agent,
					variant,
				};
			}
			return { item, group: "system" as const, section: "other" };
		});
	}, [items]);

	const availableAgents = useMemo(() => {
		const discovered = new Set<string>();
		promptMeta.forEach((meta) => {
			if (meta.group === "agent" && meta.agent) {
				discovered.add(meta.agent);
			}
		});
		const ordered = AGENT_ORDER.filter((agent) => discovered.has(agent));
		const remaining = Array.from(discovered).filter((agent) => !ordered.includes(agent));
		return [...ordered, ...remaining.sort()];
	}, [promptMeta]);

	useEffect(() => {
		if (!availableAgents.length) return;
		if (!availableAgents.includes(selectedAgent)) {
			setSelectedAgent(availableAgents[0]);
		}
	}, [availableAgents, selectedAgent]);

	const filteredMeta = useMemo(() => {
		const normalizedSearch = searchTerm.trim().toLowerCase();
		const applySearch = (item: AgentPromptItem) => {
			if (!normalizedSearch) return true;
			return (
				item.label.toLowerCase().includes(normalizedSearch) ||
				item.description.toLowerCase().includes(normalizedSearch) ||
				item.key.toLowerCase().includes(normalizedSearch)
			);
		};

		let results = promptMeta.filter(({ item, group, agent }) => {
			if (!applySearch(item)) return false;
			if (viewMode === "agent") {
				return group === "agent" && agent === selectedAgent;
			}
			if (viewMode === "system") {
				return group === "system";
			}
			return true;
		});

		if (viewMode === "agent") {
			const order = AGENT_PROMPT_ORDER[selectedAgent] ?? [];
			results = results.sort((a, b) => {
				const aVariant = a.variant ?? "";
				const bVariant = b.variant ?? "";
				const aRank = order.includes(aVariant) ? order.indexOf(aVariant) : 99;
				const bRank = order.includes(bVariant) ? order.indexOf(bVariant) : 99;
				if (aRank !== bRank) return aRank - bRank;
				return a.item.label.localeCompare(b.item.label);
			});
		}

		if (viewMode === "system") {
			results = results.sort((a, b) => {
				const aSection = (a.section ?? "other") as string;
				const bSection = (b.section ?? "other") as string;
				const aRank = SYSTEM_SECTION_ORDER.indexOf(aSection);
				const bRank = SYSTEM_SECTION_ORDER.indexOf(bSection);
				if (aRank !== bRank) return aRank - bRank;
				return a.item.label.localeCompare(b.item.label);
			});
		}

		return results;
	}, [promptMeta, viewMode, selectedAgent, searchTerm]);

	const filteredItems = useMemo(
		() => filteredMeta.map((meta) => meta.item),
		[filteredMeta]
	);

	const systemSections = useMemo(() => {
		if (viewMode !== "system") return [];
		return SYSTEM_SECTION_ORDER.map((section) => {
			const sectionItems = filteredMeta
				.filter((meta) => meta.group === "system" && meta.section === section)
				.map((meta) => meta.item);
			return {
				section,
				label: SYSTEM_SECTION_LABELS[section] ?? section,
				items: sectionItems,
			};
		}).filter((group) => group.items.length > 0);
	}, [filteredMeta, viewMode]);

	useEffect(() => {
		if (!pendingScrollKey) return;
		const node = promptRefs.get(pendingScrollKey);
		if (!node) return;
		node.scrollIntoView({ behavior: "smooth", block: "start" });
		setHighlightKey(pendingScrollKey);
		setPendingScrollKey(null);
		const timer = window.setTimeout(() => setHighlightKey(null), 1800);
		return () => window.clearTimeout(timer);
	}, [pendingScrollKey, promptRefs, filteredItems, viewMode]);

	const hasChanges = useMemo(() => {
		return items.some((item) => (overrides[item.key] ?? "") !== (item.override_prompt ?? ""));
	}, [items, overrides]);

	const activeKeys = useMemo(() => {
		const active = new Set<string>();
		for (const item of items) {
			if (item.override_prompt?.trim()) {
				active.add(item.key);
			}
		}
		return active;
	}, [items]);

	const isNodeActive = (keys: string[]) => keys.some((key) => activeKeys.has(key));

	const handleNodeClick = (target: {
		mode: PromptViewMode;
		key?: string;
		agent?: string;
	}) => {
		setSearchTerm("");
		if (target.mode === "agent" && target.agent) {
			setViewMode("agent");
			setSelectedAgent(target.agent);
			setPendingScrollKey(target.key ?? null);
			return;
		}
		setViewMode("system");
		setPendingScrollKey(target.key ?? null);
	};

	const registerNode = (id: string) => (node: HTMLButtonElement | null) => {
		if (node) {
			nodeRefs.current.set(id, node);
		} else {
			nodeRefs.current.delete(id);
		}
	};

	const renderPromptCard = (item: AgentPromptItem) => {
		const overrideValue = overrides[item.key] ?? "";
		const isActive = Boolean(item.override_prompt?.trim());
		const isDirty = overrideValue !== (item.override_prompt ?? "");

		return (
			<div
				key={item.key}
				ref={(node) => {
					if (node) promptRefs.set(item.key, node);
				}}
				className={cn(
					"rounded-lg border border-border/50 bg-card p-4 shadow-sm scroll-mt-24",
					highlightKey === item.key && "ring-2 ring-primary/40"
				)}
			>
				<div className="flex items-start justify-between gap-4">
					<div>
						<div className="flex flex-wrap items-center gap-2">
							<h3 className="text-sm font-semibold">{item.label}</h3>
							{isActive && (
								<Badge
									variant="secondary"
									className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-200"
								>
									Aktiv
								</Badge>
							)}
							{isDirty && (
								<Badge
									variant="secondary"
									className="bg-amber-500/15 text-amber-700 dark:text-amber-200"
								>
									Osparad ändring
								</Badge>
							)}
						</div>
						<p className="text-xs text-muted-foreground">{item.description}</p>
						<p className="mt-1 text-[11px] text-muted-foreground">
							Nyckel: <span className="font-mono">{item.key}</span>
						</p>
					</div>
					<Button
						variant="ghost"
						size="sm"
						onClick={() => handleReset(item)}
						disabled={isSaving}
					>
						Återställ
					</Button>
				</div>

				<div className="mt-3">
					<Textarea
						value={overrideValue}
						onChange={(event) =>
							setOverrides((prev) => ({ ...prev, [item.key]: event.target.value }))
						}
						placeholder="Skriv override‑prompt här..."
						className={cn("min-h-[140px] text-xs leading-5")}
					/>
				</div>

				<details className="mt-3">
					<summary className="cursor-pointer text-xs text-muted-foreground">
						Visa standardprompt
					</summary>
					<pre className="mt-2 whitespace-pre-wrap rounded-md border border-border/50 bg-muted/40 p-3 text-xs text-muted-foreground">
						{item.default_prompt}
					</pre>
				</details>
				<PromptHistory promptKey={item.key} isSaving={isSaving} />
			</div>
		);
	};

	const visibleAgentNodes = useMemo(
		() => AGENT_NODES.filter((node) => availableAgents.includes(node.agent)),
		[availableAgents]
	);

	useEffect(() => {
		const updateLines = () => {
			const container = graphRef.current;
			if (!container) return;
			const containerRect = container.getBoundingClientRect();
			const edges = buildGraphEdges(visibleAgentNodes);
			const next: Array<{ x1: number; y1: number; x2: number; y2: number }> = [];
			for (const edge of edges) {
				const fromNode = nodeRefs.current.get(edge.from);
				const toNode = nodeRefs.current.get(edge.to);
				if (!fromNode || !toNode) continue;
				const fromRect = fromNode.getBoundingClientRect();
				const toRect = toNode.getBoundingClientRect();
				next.push({
					x1: fromRect.right - containerRect.left,
					y1: fromRect.top - containerRect.top + fromRect.height / 2,
					x2: toRect.left - containerRect.left,
					y2: toRect.top - containerRect.top + toRect.height / 2,
				});
			}
			setGraphLines(next);
		};

		const handleResize = () => {
			window.requestAnimationFrame(updateLines);
		};

		window.requestAnimationFrame(updateLines);
		window.addEventListener("resize", handleResize);
		const observer =
			graphRef.current && typeof ResizeObserver !== "undefined"
				? new ResizeObserver(handleResize)
				: null;
		if (graphRef.current && observer) {
			observer.observe(graphRef.current);
		}
		return () => {
			window.removeEventListener("resize", handleResize);
			if (observer && graphRef.current) {
				observer.unobserve(graphRef.current);
			}
		};
	}, [visibleAgentNodes]);

	const handleSave = async () => {
		setIsSaving(true);
		try {
			const payload = {
				items: items.map((item) => ({
					key: item.key,
					override_prompt: (overrides[item.key] ?? "").trim() || null,
				})),
			};
			await adminPromptsApiService.updateAgentPrompts(payload);
			toast.success("Promtar uppdaterade");
			await refetch();
		} catch (err) {
			console.error("Failed to update agent prompts", err);
			toast.error("Kunde inte spara promtarna");
		} finally {
			setIsSaving(false);
		}
	};

	const handleReset = (item: AgentPromptItem) => {
		setOverrides((prev) => ({ ...prev, [item.key]: "" }));
	};

	const handleResetAll = () => {
		const next: Record<string, string> = {};
		for (const item of items) {
			next[item.key] = "";
		}
		setOverrides(next);
	};

	const cacheDisabled = cacheState?.disabled ?? false;

	const handleCacheToggle = async (disabled: boolean) => {
		setIsUpdatingCache(true);
		try {
			await adminCacheApiService.updateCacheState({ disabled });
			toast.success(disabled ? "Cache inaktiverad" : "Cache aktiverad");
			await refetchCacheState();
		} catch (err) {
			toast.error("Kunde inte uppdatera cache‑status");
		} finally {
			setIsUpdatingCache(false);
		}
	};

	const handleClearCache = async () => {
		setIsClearingCache(true);
		try {
			await adminCacheApiService.clearCaches();
			toast.success("Cache tömd");
		} catch (err) {
			toast.error("Kunde inte tömma cache");
		} finally {
			setIsClearingCache(false);
		}
	};

	const handleDevMode = async () => {
		setIsUpdatingCache(true);
		setIsClearingCache(true);
		try {
			await adminCacheApiService.updateCacheState({ disabled: true });
			await adminCacheApiService.clearCaches();
			toast.success("Dev‑läge aktivt: cache avstängd och tömd");
			await refetchCacheState();
		} catch (err) {
			toast.error("Kunde inte aktivera dev‑läge");
		} finally {
			setIsUpdatingCache(false);
			setIsClearingCache(false);
		}
	};

	if (!currentUser && !isLoading) {
		return (
			<div className="mx-auto w-full max-w-3xl px-4 py-10">
				<h1 className="text-xl font-semibold">Admin</h1>
				<p className="mt-2 text-sm text-muted-foreground">
					Logga in för att hantera admin‑inställningar.
				</p>
			</div>
		);
	}

	return (
		<div className="mx-auto w-full max-w-4xl px-4 py-10">
			<div className="flex flex-col gap-2">
				<h1 className="text-2xl font-semibold">Admin</h1>
				<p className="text-sm text-muted-foreground">
					Redigera globala agent‑promtar. Tomt fält betyder att standardprompten används.
				</p>
			</div>

			<Card className="mt-6">
				<CardHeader>
					<CardTitle>Cache</CardTitle>
					<CardDescription>
						Slå av cache för testning eller töm cached data vid behov.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="flex flex-wrap items-center gap-3">
						<div className="flex items-center gap-2">
							<Switch
								checked={cacheDisabled}
								onCheckedChange={(checked) => handleCacheToggle(checked)}
								disabled={isUpdatingCache || cacheLoading}
							/>
							<span className="text-sm">Inaktivera cache (dev)</span>
						</div>
						<Button
							variant="outline"
							onClick={handleClearCache}
							disabled={isClearingCache}
						>
							{isClearingCache ? "Tömmer cache..." : "Töm cache"}
						</Button>
						<Button
							variant="secondary"
							onClick={handleDevMode}
							disabled={isUpdatingCache || isClearingCache}
						>
							Aktivera dev‑läge
						</Button>
					</div>
					<p className="mt-2 text-xs text-muted-foreground">
						Cache‑läge: {cacheDisabled ? "Avstängd" : "Aktiv"}
					</p>
				</CardContent>
			</Card>

			<div className="mt-8 flex items-center justify-between gap-4">
				<h2 className="text-lg font-semibold">Agent Promtar</h2>
				<div className="flex gap-2">
					<Button variant="outline" onClick={handleResetAll} disabled={isSaving}>
						Återställ alla
					</Button>
					<Button onClick={handleSave} disabled={!hasChanges || isSaving}>
						{isSaving ? "Sparar..." : "Spara ändringar"}
					</Button>
				</div>
			</div>

			<div className="mt-4 flex flex-col gap-3 rounded-lg border border-border/40 bg-card/60 p-4">
				<div className="flex flex-wrap items-center gap-3">
					<Tabs value={viewMode} onValueChange={(value) => setViewMode(value as PromptViewMode)}>
						<TabsList>
							<TabsTrigger value="all">Alla</TabsTrigger>
							<TabsTrigger value="agent">Agent</TabsTrigger>
							<TabsTrigger value="system">System</TabsTrigger>
						</TabsList>
					</Tabs>

					{viewMode === "agent" && (
						<Select value={selectedAgent} onValueChange={setSelectedAgent}>
							<SelectTrigger className="min-w-[180px]">
								<SelectValue placeholder="Välj agent" />
							</SelectTrigger>
							<SelectContent>
								{availableAgents.map((agent) => (
									<SelectItem key={agent} value={agent}>
										{agent}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					)}

					<div className="flex-1 min-w-[220px]">
						<Input
							value={searchTerm}
							onChange={(event) => setSearchTerm(event.target.value)}
							placeholder="Sök prompt, nyckel eller beskrivning..."
						/>
					</div>
				</div>
				<p className="text-xs text-muted-foreground">
					Visar {filteredItems.length} av {items.length} promtar
				</p>
			</div>

			<div
				ref={graphRef}
				className="mt-6 rounded-xl border border-border/40 bg-muted/20 p-4 relative overflow-hidden"
			>
				<svg className="pointer-events-none absolute inset-0 h-full w-full z-0">
					{graphLines.map((line, index) => (
						<line
							key={`line-${index}`}
							x1={line.x1}
							y1={line.y1}
							x2={line.x2}
							y2={line.y2}
							stroke="hsl(var(--border))"
							strokeWidth="1"
							opacity="0.6"
						/>
					))}
				</svg>
				<div className="relative z-10 flex flex-wrap items-center justify-between gap-2">
					<div>
						<h3 className="text-sm font-semibold">Prompt-översikt</h3>
						<p className="text-xs text-muted-foreground">
							Klicka på en nod för att öppna och redigera prompten.
						</p>
					</div>
					<Badge variant="secondary" className="text-[11px]">
						Visar kopplingar mellan router, supervisor, agenter och systempromtar
					</Badge>
				</div>

				<div className="relative z-10 mt-4 grid items-start gap-4 lg:grid-cols-[1fr_auto_1fr_auto_2fr_auto_1fr]">
					<div className="space-y-2 relative">
						<p className="text-xs font-semibold uppercase text-muted-foreground">Router</p>
						{ROUTER_NODES.map((node) => (
							<button
								key={node.key}
								type="button"
								onClick={() =>
									handleNodeClick({ mode: "system", key: node.key })
								}
								ref={registerNode(`prompt:${node.key}`)}
								className={cn(
									"w-full rounded-lg border border-border/60 bg-background px-3 py-2 text-left text-xs transition hover:border-primary/40 hover:bg-background/90"
								)}
							>
								<div className="flex items-center justify-between gap-2">
									<span>{node.label}</span>
									{isNodeActive([node.key]) && (
										<span className="h-2 w-2 rounded-full bg-emerald-500" />
									)}
								</div>
							</button>
						))}
					</div>

					<div className="hidden h-full items-center justify-center text-muted-foreground lg:flex">
						<ArrowRightIcon className="size-4" />
					</div>

					<div className="space-y-2 relative">
						<p className="text-xs font-semibold uppercase text-muted-foreground">Supervisor</p>
						<button
							type="button"
							onClick={() =>
								handleNodeClick({ mode: "system", key: "agent.supervisor.system" })
							}
							ref={registerNode("prompt:agent.supervisor.system")}
							className={cn(
								"w-full rounded-lg border border-border/60 bg-background px-3 py-2 text-left text-xs transition hover:border-primary/40 hover:bg-background/90"
							)}
						>
							<div className="flex items-center justify-between gap-2">
								<span>Supervisor</span>
								{isNodeActive(["agent.supervisor.system"]) && (
									<span className="h-2 w-2 rounded-full bg-emerald-500" />
								)}
							</div>
						</button>
					</div>

					<div className="hidden h-full items-center justify-center text-muted-foreground lg:flex">
						<ArrowRightIcon className="size-4" />
					</div>

					<div className="space-y-2 relative">
						<p className="text-xs font-semibold uppercase text-muted-foreground">Agenter</p>
						<div className="grid gap-2 sm:grid-cols-2">
							{visibleAgentNodes.map((node) => (
								<button
									key={node.agent}
									type="button"
									onClick={() =>
										handleNodeClick({
											mode: "agent",
											agent: node.agent,
											key: node.keys[0],
										})
									}
									ref={registerNode(`agent:${node.agent}`)}
									className={cn(
										"rounded-lg border border-border/60 bg-background px-3 py-2 text-left text-xs transition hover:border-primary/40 hover:bg-background/90"
									)}
								>
									<div className="flex items-center justify-between gap-2">
										<span>{node.label}</span>
										{isNodeActive(node.keys) && (
											<span className="h-2 w-2 rounded-full bg-emerald-500" />
										)}
									</div>
								</button>
							))}
						</div>
					</div>

					<div className="hidden h-full items-center justify-center text-muted-foreground lg:flex">
						<ArrowRightIcon className="size-4" />
					</div>

					<div className="space-y-2 relative">
						<p className="text-xs font-semibold uppercase text-muted-foreground">System</p>
						{SYSTEM_NODES.map((node) => (
							<button
								key={node.key}
								type="button"
								onClick={() =>
									handleNodeClick({ mode: "system", key: node.key })
								}
								ref={registerNode(`prompt:${node.key}`)}
								className={cn(
									"w-full rounded-lg border border-border/60 bg-background px-3 py-2 text-left text-xs transition hover:border-primary/40 hover:bg-background/90"
								)}
							>
								<div className="flex items-center justify-between gap-2">
									<span>{node.label}</span>
									{isNodeActive([node.key]) && (
										<span className="h-2 w-2 rounded-full bg-emerald-500" />
									)}
								</div>
							</button>
						))}
					</div>
				</div>
			</div>

			{isLoading && (
				<p className="mt-6 text-sm text-muted-foreground">Laddar promtar...</p>
			)}
			{error && (
				<p className="mt-6 text-sm text-destructive">
					Kunde inte ladda promtar. Kontrollera behörigheter.
				</p>
			)}

			<div className="mt-6 space-y-6">
				{viewMode === "system" ? (
					systemSections.map((group) => (
						<div key={group.section} className="space-y-4">
							<div className="flex items-center justify-between">
								<h3 className="text-xs font-semibold uppercase text-muted-foreground">
									{group.label}
								</h3>
								<span className="text-[11px] text-muted-foreground">
									{group.items.length} promtar
								</span>
							</div>
							{group.items.map(renderPromptCard)}
						</div>
					))
				) : (
					<div className="space-y-4">{filteredItems.map(renderPromptCard)}</div>
				)}
			</div>
		</div>
	);
}

function PromptHistory({ promptKey, isSaving }: { promptKey: string; isSaving: boolean }) {
	const [isOpen, setIsOpen] = useState(false);
	const { data, isLoading } = useQuery({
		queryKey: ["admin-prompts-history", promptKey],
		queryFn: () => adminPromptsApiService.getAgentPromptHistory(promptKey),
		enabled: isOpen,
	});

	const items = data?.items ?? [];

	return (
		<details
			className="mt-3"
			open={isOpen}
			onToggle={(event) => setIsOpen((event.target as HTMLDetailsElement).open)}
		>
			<summary className="cursor-pointer text-xs text-muted-foreground">
				Visa versionshistorik
			</summary>
			<div className="mt-2 space-y-3 text-xs text-muted-foreground">
				{isLoading && <p>Laddar historik...</p>}
				{!isLoading && items.length === 0 && <p>Ingen historik ännu.</p>}
				{items.map((entry) => (
					<div
						key={`${entry.updated_at}-${entry.updated_by_id ?? "unknown"}`}
						className="rounded-md border border-border/40 bg-muted/30 p-3"
					>
						<p className="text-[11px] text-muted-foreground">
							{new Date(entry.updated_at).toLocaleString("sv-SE")}
							{entry.updated_by_id ? ` · ${entry.updated_by_id}` : ""}
						</p>
						{entry.previous_prompt ? (
							<>
								<p className="mt-2 text-[11px] uppercase text-muted-foreground">
									Föregående
								</p>
								<pre className="mt-1 whitespace-pre-wrap rounded bg-background/70 p-2 text-[11px] text-foreground/80">
									{entry.previous_prompt}
								</pre>
							</>
						) : null}
						<p className="mt-2 text-[11px] uppercase text-muted-foreground">Ny</p>
						<pre className="mt-1 whitespace-pre-wrap rounded bg-background/70 p-2 text-[11px] text-foreground/80">
							{entry.new_prompt || "(tömd)"}
						</pre>
						<details className="mt-3">
							<summary className="cursor-pointer text-[11px] text-muted-foreground">
								Visa diff
							</summary>
							<DiffBlock
								previousPrompt={entry.previous_prompt}
								newPrompt={entry.new_prompt}
							/>
						</details>
					</div>
				))}
				{isSaving && <p>Historik uppdateras när du sparar.</p>}
			</div>
		</details>
	);
}

function DiffBlock({
	previousPrompt,
	newPrompt,
}: {
	previousPrompt?: string | null;
	newPrompt?: string | null;
}) {
	const diff = diffLines(previousPrompt ?? "", newPrompt ?? "", {
		newlineIsToken: true,
	});

	return (
		<pre className="mt-2 whitespace-pre-wrap rounded bg-background/70 p-2 text-[11px]">
			{diff.map((part, index) => (
				<span
					key={`${part.added ? "add" : part.removed ? "del" : "same"}-${index}`}
					className={cn(
						"block px-1",
						part.added &&
							"bg-emerald-500/20 text-emerald-800 dark:text-emerald-200",
						part.removed &&
							"bg-rose-500/20 text-rose-800 line-through dark:text-rose-200",
						!part.added && !part.removed && "text-muted-foreground"
					)}
				>
					{part.value}
				</span>
			))}
		</pre>
	);
}
