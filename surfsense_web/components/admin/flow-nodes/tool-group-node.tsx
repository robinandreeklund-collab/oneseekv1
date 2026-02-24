"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Package } from "lucide-react";

interface ToolGroupData {
	label: string;
	agent_id: string;
	tool_count: number;
	width: number;
	height: number;
}

function ToolGroupNodeComponent({ data, selected }: NodeProps) {
	const d = data as unknown as ToolGroupData;
	return (
		<div
			className={`
				rounded-lg border-2 border-dashed bg-muted/20 transition-all
				${selected ? "border-emerald-400 bg-emerald-500/5" : "border-muted-foreground/20"}
			`}
			style={{ width: d.width, height: d.height, minWidth: 160 }}
		>
			<Handle type="target" position={Position.Left} className="!bg-transparent !border-0 !w-0 !h-0" />
			<div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-dashed border-muted-foreground/15">
				<Package className="h-3 w-3 text-muted-foreground" />
				<span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
					{d.label}
				</span>
				<span className="text-[10px] text-muted-foreground/60 ml-auto">
					{d.tool_count}
				</span>
			</div>
			<Handle type="source" position={Position.Right} className="!bg-transparent !border-0 !w-0 !h-0" />
		</div>
	);
}

export const ToolGroupNode = memo(ToolGroupNodeComponent);
