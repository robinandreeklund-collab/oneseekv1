"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { cn } from "@/lib/utils";

const STAGE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
	entry: { bg: "bg-violet-500/10", border: "border-violet-500/40", text: "text-violet-700 dark:text-violet-300" },
	fast_path: { bg: "bg-amber-500/10", border: "border-amber-500/40", text: "text-amber-700 dark:text-amber-300" },
	speculative: { bg: "bg-slate-500/10", border: "border-slate-500/40", text: "text-slate-700 dark:text-slate-300" },
	planning: { bg: "bg-blue-500/10", border: "border-blue-500/40", text: "text-blue-700 dark:text-blue-300" },
	tool_resolution: { bg: "bg-cyan-500/10", border: "border-cyan-500/40", text: "text-cyan-700 dark:text-cyan-300" },
	execution: { bg: "bg-emerald-500/10", border: "border-emerald-500/40", text: "text-emerald-700 dark:text-emerald-300" },
	post_processing: { bg: "bg-slate-500/10", border: "border-slate-400/40", text: "text-slate-600 dark:text-slate-300" },
	evaluation: { bg: "bg-orange-500/10", border: "border-orange-500/40", text: "text-orange-700 dark:text-orange-300" },
	synthesis: { bg: "bg-rose-500/10", border: "border-rose-500/40", text: "text-rose-700 dark:text-rose-300" },
};

const DEFAULT_COLOR = { bg: "bg-muted/20", border: "border-border/60", text: "text-foreground" };

function PipelineGraphNode({ data }: NodeProps) {
	const stage = String((data as Record<string, unknown>).stage ?? "");
	const label = String((data as Record<string, unknown>).label ?? "");
	const description = String((data as Record<string, unknown>).description ?? "");
	const colors = STAGE_COLORS[stage] ?? DEFAULT_COLOR;

	return (
		<>
			<Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-muted-foreground/40" />
			<div
				className={cn(
					"rounded-lg border px-3 py-2 shadow-sm min-w-[140px] max-w-[180px]",
					colors.bg,
					colors.border,
				)}
			>
				<div className={cn("text-xs font-semibold leading-tight", colors.text)}>
					{label}
				</div>
				{description && (
					<div className="mt-1 text-[10px] leading-tight text-muted-foreground line-clamp-2">
						{description}
					</div>
				)}
			</div>
			<Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-muted-foreground/40" />
		</>
	);
}

export const PipelineGraphNodeMemo = memo(PipelineGraphNode);
