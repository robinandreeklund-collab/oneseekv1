"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Package, ChevronDown, ChevronRight } from "lucide-react";

interface ToolGroupData {
	label: string;
	agent_id: string;
	tool_count: number;
	width: number;
	height: number;
	expanded: boolean;
}

function ToolGroupNodeComponent({ data }: NodeProps) {
	const d = data as unknown as ToolGroupData;
	return (
		<div
			className={`
				rounded-lg border-2 border-dashed transition-all cursor-pointer
				${d.expanded
					? "border-emerald-400/40 bg-emerald-500/5"
					: "border-muted-foreground/20 bg-muted/20 hover:border-muted-foreground/40 hover:bg-muted/30"
				}
			`}
			style={{ width: d.width, height: d.height, minWidth: 160 }}
		>
			<Handle type="target" position={Position.Left} className="!bg-transparent !border-0 !w-0 !h-0" />
			<div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-dashed border-muted-foreground/15">
				{d.expanded ? (
					<ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
				) : (
					<ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
				)}
				<Package className="h-3 w-3 text-muted-foreground shrink-0" />
				<span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide truncate">
					{d.label}
				</span>
				<span className="text-[10px] text-muted-foreground/60 ml-auto shrink-0">
					{d.tool_count}
				</span>
			</div>
			<Handle type="source" position={Position.Right} className="!bg-transparent !border-0 !w-0 !h-0" />
		</div>
	);
}

export const ToolGroupNode = memo(ToolGroupNodeComponent);
