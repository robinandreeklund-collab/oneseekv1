"use client";

import { useMessage, MessagePrimitive } from "@assistant-ui/react";
import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

// ============================================================================
// Spotlight Arena — wraps compare mode tool-call cards
// ============================================================================

/**
 * SpotlightArena renders a visual wrapper around compare-mode tool results.
 *
 * Layout:
 * 1. OneSeek Research card in "spotlight" position (centered, glow effect)
 * 2. External model cards in responsive grid below
 * 3. Convergence summary (overlap score, conflicts)
 *
 * The individual model cards (GrokToolUI, ClaudeToolUI, etc.) are still
 * rendered by @assistant-ui/react's makeAssistantToolUI system — this
 * component provides the container layout and convergence metadata.
 */

interface ConvergenceData {
	overlap_score?: number;
	conflicts?: Array<{
		domain_a: string;
		domain_b: string;
		field?: string;
		description?: string;
	}>;
	merged_summary?: string;
}

interface SpotlightArenaProps {
	convergence?: ConvergenceData | null;
	modelCount?: number;
	researchPresent?: boolean;
	children?: React.ReactNode;
}

export function SpotlightArena({
	convergence,
	modelCount = 0,
	researchPresent = false,
	children,
}: SpotlightArenaProps) {
	const overlapPercent = Math.round((convergence?.overlap_score ?? 0) * 100);
	const conflicts = convergence?.conflicts ?? [];
	const hasConvergence = convergence && (convergence.overlap_score != null || conflicts.length > 0);

	return (
		<div className="space-y-4">
			{/* Header */}
			<div className="flex items-center gap-3">
				<h3 className="text-sm font-semibold text-muted-foreground tracking-wide uppercase">
					Jämförelse
				</h3>
				{modelCount > 0 && (
					<Badge variant="secondary" className="text-[10px]">
						{modelCount} modeller{researchPresent ? " + research" : ""}
					</Badge>
				)}
			</div>

			{/* Model cards — rendered by @assistant-ui/react ToolUI system */}
			<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{children}
			</div>

			{/* Convergence summary */}
			{hasConvergence && (
				<Card className="border-border/40 bg-muted/30">
					<CardHeader className="pb-2">
						<CardTitle className="text-sm font-medium flex items-center gap-2">
							Convergence
							<Badge variant="outline" className="text-[10px]">
								{overlapPercent}% overlap
							</Badge>
						</CardTitle>
					</CardHeader>
					<CardContent className="space-y-3">
						<Progress value={overlapPercent} className="h-1.5" />

						{conflicts.length > 0 && (
							<div className="space-y-1">
								<p className="text-xs font-medium text-muted-foreground">
									Konflikter ({conflicts.length})
								</p>
								{conflicts.map((conflict, idx) => (
									<div
										key={`conflict-${conflict.domain_a}-${conflict.domain_b}-${idx}`}
										className="flex items-start gap-2 text-xs text-muted-foreground"
									>
										<span className="text-amber-500 mt-0.5">!</span>
										<span>
											<strong>{conflict.domain_a}</strong> vs{" "}
											<strong>{conflict.domain_b}</strong>
											{conflict.field && ` (${conflict.field})`}
											{conflict.description && `: ${conflict.description}`}
										</span>
									</div>
								))}
							</div>
						)}

						{convergence?.merged_summary && (
							<div className="text-xs text-muted-foreground leading-relaxed">
								{convergence.merged_summary}
							</div>
						)}
					</CardContent>
				</Card>
			)}
		</div>
	);
}

/**
 * Hook to detect if the current message is a compare-mode message.
 *
 * Checks for the presence of compare tool calls (call_grok, call_claude, etc.)
 * in the message's tool invocations.
 */
const COMPARE_TOOL_NAMES = new Set([
	"call_grok",
	"call_claude",
	"call_gpt",
	"call_gemini",
	"call_deepseek",
	"call_perplexity",
	"call_qwen",
	"call_oneseek",
]);

export function useIsCompareMessage(): boolean {
	const message = useMessage();
	return useMemo(() => {
		if (!message || message.message.role !== "assistant") return false;
		const content = message.message.content;
		if (!Array.isArray(content)) return false;
		return content.some(
			(part) =>
				part.type === "tool-call" && COMPARE_TOOL_NAMES.has(part.toolName),
		);
	}, [message]);
}
