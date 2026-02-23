import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Bot } from "lucide-react";
import type { FlowAgentNode } from "@/contracts/types/admin-flow-graph.types";

export const AgentGraphNode = memo(function AgentGraphNode({
	data,
	selected,
}: NodeProps) {
	const agent = data as unknown as FlowAgentNode;
	return (
		<div
			className={`
				group relative rounded-lg border-2 bg-background px-4 py-2.5
				shadow-sm transition-all cursor-pointer min-w-[160px]
				hover:shadow-md
				${selected ? "border-blue-500 shadow-blue-500/20 shadow-md" : "border-blue-300/50"}
			`}
		>
			<Handle type="target" position={Position.Left} className="!bg-blue-500 !w-2 !h-2" />
			<Handle type="source" position={Position.Right} className="!bg-blue-500 !w-2 !h-2" />
			<div className="flex items-center gap-2">
				<div className="flex items-center justify-center h-6 w-6 rounded bg-blue-500/10">
					<Bot className="h-3.5 w-3.5 text-blue-500" />
				</div>
				<div className="flex flex-col">
					<span className="text-xs font-semibold leading-tight">{agent.label}</span>
					<span className="text-[10px] text-muted-foreground leading-tight truncate max-w-[120px]">
						{agent.description.slice(0, 40)}
						{agent.description.length > 40 ? "..." : ""}
					</span>
				</div>
			</div>
			<div className="absolute -top-1.5 -right-1.5 h-3 w-3 rounded-full bg-blue-500 border-2 border-background" />
		</div>
	);
});
