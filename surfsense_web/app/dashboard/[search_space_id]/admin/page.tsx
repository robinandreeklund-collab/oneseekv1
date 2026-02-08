"use client";

import { useQuery } from "@tanstack/react-query";
import { useAtomValue } from "jotai";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import type { AgentPromptItem } from "@/contracts/types/agent-prompts.types";
import { adminPromptsApiService } from "@/lib/apis/admin-prompts-api.service";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export default function AdminPromptsPage() {
	const params = useParams();
	const searchSpaceId = Number(params.search_space_id);
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const [overrides, setOverrides] = useState<Record<string, string>>({});
	const [isSaving, setIsSaving] = useState(false);

	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["admin-prompts", searchSpaceId],
		queryFn: () => adminPromptsApiService.getAgentPrompts(searchSpaceId),
		enabled: Number.isFinite(searchSpaceId) && searchSpaceId > 0,
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
		if (!searchSpaceId) return;
		setIsSaving(true);
		try {
			const payload = {
				items: items.map((item) => ({
					key: item.key,
					override_prompt: (overrides[item.key] ?? "").trim() || null,
				})),
			};
			await adminPromptsApiService.updateAgentPrompts(searchSpaceId, payload);
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
					Redigera agent‑promtar för varje steg i kedjan. Tomt fält betyder att
					standardprompten används.
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
					</div>
				))}
			</div>
		</div>
	);
}
