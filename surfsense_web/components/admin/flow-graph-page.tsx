"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
	ReactFlow,
	Background,
	Controls,
	MiniMap,
	useNodesState,
	useEdgesState,
	type Node,
	type Edge,
	type NodeTypes,
	Position,
	MarkerType,
	Panel,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { adminFlowGraphApiService } from "@/lib/apis/admin-flow-graph-api.service";
import type {
	FlowGraphResponse,
	FlowIntentNode,
	FlowAgentNode,
	FlowToolNode,
} from "@/contracts/types/admin-flow-graph.types";
import { IntentGraphNode } from "./flow-nodes/intent-node";
import { AgentGraphNode } from "./flow-nodes/agent-node";
import { ToolGraphNode } from "./flow-nodes/tool-node";
import { FlowDetailPanel } from "./flow-detail-panel";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

const nodeTypes: NodeTypes = {
	intentNode: IntentGraphNode,
	agentNode: AgentGraphNode,
	toolNode: ToolGraphNode,
};

const INTENT_X = 50;
const AGENT_X = 450;
const TOOL_X = 850;
const ROW_GAP = 100;
const INTENT_ROW_GAP = 120;
const TOOL_ROW_GAP = 56;

function buildNodes(data: FlowGraphResponse): Node[] {
	const nodes: Node[] = [];

	// Intent nodes - left column
	data.intents.forEach((intent, i) => {
		nodes.push({
			id: intent.id,
			type: "intentNode",
			position: { x: INTENT_X, y: 40 + i * INTENT_ROW_GAP },
			data: { ...intent },
			sourcePosition: Position.Right,
			targetPosition: Position.Left,
		});
	});

	// Agent nodes - middle column
	data.agents.forEach((agent, i) => {
		nodes.push({
			id: agent.id,
			type: "agentNode",
			position: { x: AGENT_X, y: 20 + i * ROW_GAP },
			data: { ...agent },
			sourcePosition: Position.Right,
			targetPosition: Position.Left,
		});
	});

	// Tool nodes - right column, grouped by agent
	const toolsByAgent: Record<string, typeof data.tools> = {};
	for (const tool of data.tools) {
		const agentId = tool.agent_id;
		if (!toolsByAgent[agentId]) toolsByAgent[agentId] = [];
		toolsByAgent[agentId].push(tool);
	}

	let toolIndex = 0;
	// Order tool groups by agent order
	for (const agent of data.agents) {
		const agentTools = toolsByAgent[agent.agent_id] || [];
		for (const tool of agentTools) {
			nodes.push({
				id: tool.id,
				type: "toolNode",
				position: { x: TOOL_X, y: 20 + toolIndex * TOOL_ROW_GAP },
				data: { ...tool },
				sourcePosition: Position.Right,
				targetPosition: Position.Left,
			});
			toolIndex++;
		}
	}

	return nodes;
}

function buildEdges(data: FlowGraphResponse): Edge[] {
	const edges: Edge[] = [];

	data.intent_agent_edges.forEach((edge, i) => {
		edges.push({
			id: `ia-${i}`,
			source: edge.source,
			target: edge.target,
			type: "smoothstep",
			animated: false,
			style: { stroke: "hsl(var(--primary))", strokeWidth: 1.5, opacity: 0.5 },
			markerEnd: {
				type: MarkerType.ArrowClosed,
				color: "hsl(var(--primary))",
				width: 14,
				height: 14,
			},
		});
	});

	data.agent_tool_edges.forEach((edge, i) => {
		edges.push({
			id: `at-${i}`,
			source: edge.source,
			target: edge.target,
			type: "smoothstep",
			animated: false,
			style: { stroke: "hsl(var(--muted-foreground))", strokeWidth: 1, opacity: 0.35 },
			markerEnd: {
				type: MarkerType.ArrowClosed,
				color: "hsl(var(--muted-foreground))",
				width: 10,
				height: 10,
			},
		});
	});

	return edges;
}

type SelectedNodeData =
	| { type: "intent"; data: FlowIntentNode }
	| { type: "agent"; data: FlowAgentNode }
	| { type: "tool"; data: FlowToolNode }
	| null;

export function FlowGraphPage() {
	const [graphData, setGraphData] = useState<FlowGraphResponse | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [nodes, setNodes, onNodesChange] = useNodesState<Node>([] as Node[]);
	const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([] as Edge[]);
	const [selectedNode, setSelectedNode] = useState<SelectedNodeData>(null);

	const fetchData = useCallback(async () => {
		setLoading(true);
		setError(null);
		try {
			const data = await adminFlowGraphApiService.getFlowGraph();
			setGraphData(data);
			setNodes(buildNodes(data));
			setEdges(buildEdges(data));
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to load flow graph");
		} finally {
			setLoading(false);
		}
	}, [setNodes, setEdges]);

	useEffect(() => {
		fetchData();
	}, [fetchData]);

	const onNodeClick = useCallback(
		(_event: React.MouseEvent, node: Node) => {
			if (!graphData) return;

			const nodeId = node.id;
			if (nodeId.startsWith("intent:")) {
				const found = graphData.intents.find((i) => i.id === nodeId);
				if (found) setSelectedNode({ type: "intent", data: found });
			} else if (nodeId.startsWith("agent:")) {
				const found = graphData.agents.find((a) => a.id === nodeId);
				if (found) setSelectedNode({ type: "agent", data: found });
			} else if (nodeId.startsWith("tool:")) {
				const found = graphData.tools.find((t) => t.id === nodeId);
				if (found) setSelectedNode({ type: "tool", data: found });
			}

			// Highlight connected edges
			setEdges((currentEdges) =>
				currentEdges.map((edge) => {
					const isConnected = edge.source === nodeId || edge.target === nodeId;
					return {
						...edge,
						animated: isConnected,
						style: {
							...edge.style,
							opacity: isConnected ? 1 : 0.15,
							strokeWidth: isConnected ? 2.5 : (edge.style?.strokeWidth ?? 1),
						},
					};
				})
			);
		},
		[graphData, setEdges]
	);

	const onPaneClick = useCallback(() => {
		setSelectedNode(null);
		if (graphData) {
			setEdges(buildEdges(graphData));
		}
	}, [graphData, setEdges]);

	// Count connections for detail panel
	const connectionCounts = useMemo(() => {
		if (!graphData) return { agentsPerIntent: {}, toolsPerAgent: {} };
		const agentsPerIntent: Record<string, number> = {};
		const toolsPerAgent: Record<string, number> = {};
		for (const e of graphData.intent_agent_edges) {
			agentsPerIntent[e.source] = (agentsPerIntent[e.source] || 0) + 1;
		}
		for (const e of graphData.agent_tool_edges) {
			toolsPerAgent[e.source] = (toolsPerAgent[e.source] || 0) + 1;
		}
		return { agentsPerIntent, toolsPerAgent };
	}, [graphData]);

	if (loading) {
		return (
			<div className="flex items-center justify-center h-[calc(100vh-8rem)]">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		);
	}

	if (error) {
		return (
			<div className="flex flex-col items-center justify-center h-[calc(100vh-8rem)] gap-4">
				<p className="text-sm text-destructive">{error}</p>
				<Button variant="outline" size="sm" onClick={fetchData}>
					<RefreshCw className="mr-2 h-4 w-4" /> Retry
				</Button>
			</div>
		);
	}

	return (
		<div className="flex h-[calc(100vh-8rem)]">
			{/* Graph area */}
			<div className="flex-1 relative">
				<ReactFlow
					nodes={nodes}
					edges={edges}
					onNodesChange={onNodesChange}
					onEdgesChange={onEdgesChange}
					onNodeClick={onNodeClick}
					onPaneClick={onPaneClick}
					nodeTypes={nodeTypes}
					fitView
					fitViewOptions={{ padding: 0.15 }}
					minZoom={0.2}
					maxZoom={2}
					proOptions={{ hideAttribution: true }}
				>
					<Background gap={20} size={1} />
					<Controls showInteractive={false} />
					<MiniMap
						nodeStrokeWidth={2}
						pannable
						zoomable
						style={{ height: 100, width: 160 }}
					/>
					<Panel position="top-left">
						<div className="flex items-center gap-6 rounded-lg border bg-background/95 backdrop-blur px-4 py-2 shadow-sm">
							<h2 className="text-sm font-semibold">Flow Overview</h2>
							<div className="flex items-center gap-4 text-xs text-muted-foreground">
								<span className="flex items-center gap-1.5">
									<span className="h-2.5 w-2.5 rounded-full bg-violet-500" />
									Intents ({graphData?.intents.length ?? 0})
								</span>
								<span className="flex items-center gap-1.5">
									<span className="h-2.5 w-2.5 rounded-full bg-blue-500" />
									Agenter ({graphData?.agents.length ?? 0})
								</span>
								<span className="flex items-center gap-1.5">
									<span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
									Verktyg ({graphData?.tools.length ?? 0})
								</span>
							</div>
							<Button
								variant="ghost"
								size="sm"
								className="h-7 px-2"
								onClick={fetchData}
							>
								<RefreshCw className="h-3.5 w-3.5" />
							</Button>
						</div>
					</Panel>
				</ReactFlow>
			</div>

			{/* Detail panel */}
			{selectedNode && (
				<FlowDetailPanel
					selectedNode={selectedNode}
					connectionCounts={connectionCounts}
					onClose={() => {
						setSelectedNode(null);
						if (graphData) setEdges(buildEdges(graphData));
					}}
				/>
			)}
		</div>
	);
}
