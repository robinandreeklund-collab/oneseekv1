"use client";

import { useQuery } from "@tanstack/react-query";
import { diffLines } from "diff";
import { useAtomValue } from "jotai";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import type { AgentPromptItem } from "@/contracts/types/agent-prompts.types";
import { adminPromptsApiService } from "@/lib/apis/admin-prompts-api.service";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

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
	"synthesis",
	"smalltalk",
];

const AGENT_PROMPT_ORDER: Record<string, string[]> = {
	knowledge: ["system", "docs", "internal", "external"],
	action: ["system", "web", "media", "travel", "data"],
};

const SYSTEM_SECTION_ORDER = ["router", "supervisor", "worker", "compare", "other"];
const SYSTEM_SECTION_LABELS: Record<string, string> = {
	router: "Router",
	supervisor: "Supervisor",
	worker: "Workers",
	compare: "Compare",
	other: "Övrigt",
};

export function AdminPromptsPage() {
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const [overrides, setOverrides] = useState<Record<string, string>>({});
	const [isSaving, setIsSaving] = useState(false);
	const [viewMode, setViewMode] = useState<PromptViewMode>("all");
	const [selectedAgent, setSelectedAgent] = useState<string>("action");
	const [searchTerm, setSearchTerm] = useState("");

	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["admin-prompts"],
		queryFn: () => adminPromptsApiService.getAgentPrompts(),
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
			if (key.startsWith("compare.")) {
				return {
					item,
					group: "system" as const,
					section: "compare",
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

	const hasChanges = useMemo(() => {
		return items.some((item) => (overrides[item.key] ?? "") !== (item.override_prompt ?? ""));
	}, [items, overrides]);

	const renderPromptCard = (item: AgentPromptItem) => {
		const overrideValue = overrides[item.key] ?? "";
		const isActive = Boolean(item.override_prompt?.trim());
		const isDirty = overrideValue !== (item.override_prompt ?? "");

		return (
			<div key={item.key} className="rounded-lg border border-border/50 bg-card p-4 shadow-sm">
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
