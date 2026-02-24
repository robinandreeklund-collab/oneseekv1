import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Wrench, GripVertical } from "lucide-react";
import type { FlowToolNode } from "@/contracts/types/admin-flow-graph.types";

export const ToolGraphNode = memo(function ToolGraphNode({
	data,
	selected,
}: NodeProps) {
	const tool = data as unknown as FlowToolNode;
	return (
		<div
			className={`
				group relative rounded border bg-background px-3 py-1.5
				shadow-sm transition-all cursor-pointer min-w-[130px]
				hover:shadow-md
				${selected ? "border-emerald-500 shadow-emerald-500/20 shadow-md" : "border-emerald-300/40"}
			`}
		>
			<Handle type="target" position={Position.Left} className="!bg-emerald-500 !w-1.5 !h-1.5" />
			<div className="flex items-center gap-1.5">
				<GripVertical className="h-3 w-3 text-muted-foreground/30 group-hover:text-muted-foreground/60 shrink-0 cursor-grab active:cursor-grabbing" />
				<Wrench className="h-3 w-3 text-emerald-500 shrink-0" />
				<span className="text-[11px] font-medium leading-tight truncate">{tool.label}</span>
			</div>
		</div>
	);
});
