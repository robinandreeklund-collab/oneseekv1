import { ChevronRightIcon } from "lucide-react";
import type { FC } from "react";
import { createContext, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type ContextStatsEntry = {
	phase?: string;
	label?: string;
	delta_chars?: number;
	delta_tokens?: number;
	total_chars?: number;
	total_tokens?: number;
	base_chars?: number;
	base_tokens?: number;
	context_chars?: number;
	context_tokens?: number;
	tool_chars?: number;
	tool_tokens?: number;
	breakdown?: {
		attachments_chars?: number;
		mentioned_docs_chars?: number;
		mentioned_surfsense_docs_chars?: number;
	};
	receivedAt?: number;
};

export const ContextStatsContext = createContext<Map<string, ContextStatsEntry[]>>(new Map());

const formatNumber = (value: number) => {
	return Number.isFinite(value) ? value.toLocaleString("sv-SE") : "0";
};

const safeNumber = (value?: number) => {
	return typeof value === "number" && Number.isFinite(value) ? value : 0;
};

export const ContextStatsDisplay: FC<{
	entries: ContextStatsEntry[];
	isThreadRunning?: boolean;
}> = ({ entries }) => {
	const [isOpen, setIsOpen] = useState(false);
	const latest = entries[entries.length - 1];

	const stats = useMemo(() => {
		return {
			totalTokens: safeNumber(latest?.total_tokens),
			totalChars: safeNumber(latest?.total_chars),
			baseTokens: safeNumber(latest?.base_tokens),
			contextTokens: safeNumber(latest?.context_tokens),
			toolTokens: safeNumber(latest?.tool_tokens),
			lastDeltaTokens: safeNumber(latest?.delta_tokens),
			lastLabel: latest?.label || latest?.phase || "Update",
		};
	}, [latest]);

	const history = useMemo(() => entries.slice(-6).reverse(), [entries]);

	if (!latest) return null;

	return (
		<div className="mx-auto w-full max-w-(--thread-max-width) px-2">
			<div className="rounded-lg border border-border/40 bg-muted/20 px-3 py-2">
				<button
					type="button"
					onClick={() => setIsOpen(!isOpen)}
					className={cn(
						"flex w-full items-center justify-between gap-2 text-left text-sm",
						"text-muted-foreground hover:text-foreground"
					)}
				>
					<span>
						Kontext (tokens): {formatNumber(stats.totalTokens)}
						{stats.totalChars > 0 ? ` · ${formatNumber(stats.totalChars)} tecken` : ""}
					</span>
					<ChevronRightIcon
						className={cn("size-4 transition-transform duration-200", isOpen && "rotate-90")}
					/>
				</button>

				<div
					className={cn(
						"grid transition-[grid-template-rows] duration-300 ease-out",
						isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
					)}
				>
					<div className="overflow-hidden">
						<div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
							{stats.baseTokens > 0 && (
								<Badge variant="secondary">Bas {formatNumber(stats.baseTokens)} tok</Badge>
							)}
							{stats.contextTokens > 0 && (
								<Badge variant="secondary">
									Kontext {formatNumber(stats.contextTokens)} tok
								</Badge>
							)}
							{stats.toolTokens > 0 && (
								<Badge variant="secondary">
									Verktyg {formatNumber(stats.toolTokens)} tok
								</Badge>
							)}
						</div>

						{stats.lastDeltaTokens > 0 && (
							<div className="mt-2 text-xs text-muted-foreground">
								Senaste: +{formatNumber(stats.lastDeltaTokens)} tok · {stats.lastLabel}
							</div>
						)}

						{history.length > 1 && (
							<div className="mt-2 space-y-1 text-xs text-muted-foreground">
								{history.map((entry, index) => (
									<div key={`${entry.label || entry.phase}-${index}`} className="flex gap-2">
										<span className="flex-1 truncate">
											{entry.label || entry.phase || "Update"}
										</span>
										<span className="text-foreground/80">
											+{formatNumber(safeNumber(entry.delta_tokens))} tok
										</span>
									</div>
								))}
							</div>
						)}
					</div>
				</div>
			</div>
		</div>
	);
};
