import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Zap } from "lucide-react";
import type { FlowIntentNode } from "@/contracts/types/admin-flow-graph.types";

export const IntentGraphNode = memo(function IntentGraphNode({
	data,
	selected,
}: NodeProps) {
	const intent = data as unknown as FlowIntentNode;
	return (
		<div
			className={`
				group relative rounded-lg border-2 bg-background px-4 py-2.5
				shadow-sm transition-all cursor-pointer min-w-[160px]
				hover:shadow-md
				${selected ? "border-violet-500 shadow-violet-500/20 shadow-md" : "border-violet-300/50"}
				${!intent.enabled ? "opacity-50" : ""}
			`}
		>
			<Handle type="source" position={Position.Right} className="!bg-violet-500 !w-2 !h-2" />
			<div className="flex items-center gap-2">
				<div className="flex items-center justify-center h-6 w-6 rounded bg-violet-500/10">
					<Zap className="h-3.5 w-3.5 text-violet-500" />
				</div>
				<div className="flex flex-col">
					<span className="text-xs font-semibold leading-tight">{intent.label}</span>
					<span className="text-[10px] text-muted-foreground leading-tight">
						route: {intent.route}
					</span>
				</div>
			</div>
			<div className="absolute -top-1.5 -right-1.5 h-3 w-3 rounded-full bg-violet-500 border-2 border-background" />
		</div>
	);
});
