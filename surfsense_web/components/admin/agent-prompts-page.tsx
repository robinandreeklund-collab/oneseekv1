"use client";

import { useQuery } from "@tanstack/react-query";
import { useAtomValue } from "jotai";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import type { AgentPromptItem } from "@/contracts/types/agent-prompts.types";
import { adminPromptsApiService } from "@/lib/apis/admin-prompts-api.service";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export function AdminPromptsPage() {
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const [overrides, setOverrides] = useState<Record<string, string>>({});
	const [isSaving, setIsSaving] = useState(false);

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
	const hasChanges = useMemo(() => {
		return items.some((item) => (overrides[item.key] ?? "") !== (item.override_prompt ?? ""));
	}, [items, overrides]);

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

			{isLoading && (
				<p className="mt-6 text-sm text-muted-foreground">Laddar promtar...</p>
			)}
			{error && (
				<p className="mt-6 text-sm text-destructive">
					Kunde inte ladda promtar. Kontrollera behörigheter.
				</p>
			)}

			<div className="mt-6 space-y-4">
				{items.map((item) => (
					<div
						key={item.key}
						className="rounded-lg border border-border/50 bg-card p-4 shadow-sm"
					>
						<div className="flex items-start justify-between gap-4">
							<div>
								<h3 className="text-sm font-semibold">{item.label}</h3>
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
								value={overrides[item.key] ?? ""}
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
				))}
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
					</div>
				))}
				{isSaving && <p>Historik uppdateras när du sparar.</p>}
			</div>
		</details>
	);
}
