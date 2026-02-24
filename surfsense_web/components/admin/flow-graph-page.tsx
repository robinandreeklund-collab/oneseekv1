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
	PipelineNode as PipelineNodeData,
	PipelineEdge as PipelineEdgeData,
	PipelineStage,
} from "@/contracts/types/admin-flow-graph.types";
import { IntentGraphNode } from "./flow-nodes/intent-node";
import { AgentGraphNode } from "./flow-nodes/agent-node";
import { ToolGraphNode } from "./flow-nodes/tool-node";
import { PipelineGraphNodeMemo } from "./flow-nodes/pipeline-node";
import { FlowDetailPanel } from "./flow-detail-panel";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type ViewMode = "pipeline" | "routing";

const nodeTypes: NodeTypes = {
	intentNode: IntentGraphNode,
	agentNode: AgentGraphNode,
	toolNode: ToolGraphNode,
	pipelineNode: PipelineGraphNodeMemo,
};

// ── Routing graph layout ────────────────────────────────────────────

const INTENT_X = 50;
const AGENT_X = 450;
const TOOL_X = 850;
const ROW_GAP = 100;
const INTENT_ROW_GAP = 120;
const TOOL_ROW_GAP = 56;

function buildRoutingNodes(data: FlowGraphResponse): Node[] {
	const nodes: Node[] = [];

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

	const toolsByAgent: Record<string, typeof data.tools> = {};
	for (const tool of data.tools) {
		const agentId = tool.agent_id;
		if (!toolsByAgent[agentId]) toolsByAgent[agentId] = [];
		toolsByAgent[agentId].push(tool);
	}

	let toolIndex = 0;
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

function buildRoutingEdges(data: FlowGraphResponse): Edge[] {
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

// ── Pipeline graph layout ───────────────────────────────────────────

const STAGE_COLORS: Record<string, string> = {
	entry: "hsl(263 70% 55%)",       // violet
	fast_path: "hsl(38 92% 50%)",    // amber
	speculative: "hsl(215 14% 50%)", // slate
	planning: "hsl(217 91% 60%)",    // blue
	tool_resolution: "hsl(189 94% 43%)", // cyan
	execution: "hsl(160 84% 39%)",   // emerald
	post_processing: "hsl(215 14% 50%)", // slate
	evaluation: "hsl(25 95% 53%)",   // orange
	synthesis: "hsl(350 89% 60%)",   // rose
};

// Pipeline layout: group nodes by stage in columns
const STAGE_ORDER = [
	"entry",
	"fast_path",
	"speculative",
	"planning",
	"tool_resolution",
	"execution",
	"post_processing",
	"evaluation",
	"synthesis",
];

function buildPipelineNodes(
	pipelineNodes: PipelineNodeData[],
): Node[] {
	const nodes: Node[] = [];

	// Group nodes by stage
	const nodesByStage: Record<string, PipelineNodeData[]> = {};
	for (const node of pipelineNodes) {
		if (!nodesByStage[node.stage]) nodesByStage[node.stage] = [];
		nodesByStage[node.stage].push(node);
	}

	// Lay out in a roughly left-to-right flow
	// We use a custom layout for a nice pipeline look
	const nodePositions: Record<string, { x: number; y: number }> = {
		// Entry
		"node:resolve_intent": { x: 0, y: 200 },
		"node:memory_context": { x: 220, y: 200 },
		// Fast path
		"node:smalltalk": { x: 440, y: 0 },
		// Speculative
		"node:speculative": { x: 440, y: 100 },
		// Planning
		"node:agent_resolver": { x: 440, y: 220 },
		"node:planner": { x: 660, y: 220 },
		"node:planner_hitl_gate": { x: 880, y: 220 },
		// Tool resolution
		"node:tool_resolver": { x: 440, y: 360 },
		"node:speculative_merge": { x: 660, y: 360 },
		"node:execution_router": { x: 880, y: 360 },
		// Execution
		"node:execution_hitl_gate": { x: 1100, y: 280 },
		"node:executor": { x: 1320, y: 280 },
		"node:tools": { x: 1540, y: 200 },
		"node:post_tools": { x: 1540, y: 340 },
		// Post-processing
		"node:artifact_indexer": { x: 1760, y: 340 },
		"node:context_compactor": { x: 1760, y: 460 },
		"node:orchestration_guard": { x: 1540, y: 460 },
		// Evaluation
		"node:critic": { x: 1320, y: 460 },
		// Synthesis
		"node:synthesis_hitl": { x: 1100, y: 560 },
		"node:progressive_synthesizer": { x: 1320, y: 620 },
		"node:synthesizer": { x: 1540, y: 620 },
	};

	for (const node of pipelineNodes) {
		const pos = nodePositions[node.id] ?? { x: 0, y: 0 };
		nodes.push({
			id: node.id,
			type: "pipelineNode",
			position: pos,
			data: { ...node },
			sourcePosition: Position.Right,
			targetPosition: Position.Left,
		});
	}

	return nodes;
}

function buildPipelineEdges(
	pipelineEdges: PipelineEdgeData[],
	pipelineNodes: PipelineNodeData[],
): Edge[] {
	const nodeStageMap: Record<string, string> = {};
	for (const n of pipelineNodes) {
		nodeStageMap[n.id] = n.stage;
	}

	return pipelineEdges.map((edge, i) => {
		const isConditional = edge.type === "conditional";
		const sourceStage = nodeStageMap[edge.source] ?? "";
		const color = STAGE_COLORS[sourceStage] ?? "hsl(var(--muted-foreground))";

		return {
			id: `pe-${i}`,
			source: edge.source,
			target: edge.target,
			type: "smoothstep",
			animated: false,
			label: edge.label ?? undefined,
			labelStyle: { fontSize: 9, fill: "hsl(var(--muted-foreground))" },
			labelBgStyle: { fill: "hsl(var(--background))", fillOpacity: 0.8 },
			style: {
				stroke: color,
				strokeWidth: isConditional ? 1 : 1.5,
				strokeDasharray: isConditional ? "5 3" : undefined,
				opacity: isConditional ? 0.6 : 0.8,
			},
			markerEnd: {
				type: MarkerType.ArrowClosed,
				color,
				width: 12,
				height: 12,
			},
		};
	});
}

// ── Detail panel types ──────────────────────────────────────────────

type SelectedNodeData =
	| { type: "intent"; data: FlowIntentNode }
	| { type: "agent"; data: FlowAgentNode }
	| { type: "tool"; data: FlowToolNode }
	| { type: "pipeline"; data: PipelineNodeData }
	| null;

// ── Main component ──────────────────────────────────────────────────

export function FlowGraphPage() {
	const [graphData, setGraphData] = useState<FlowGraphResponse | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [viewMode, setViewMode] = useState<ViewMode>("pipeline");
	const [nodes, setNodes, onNodesChange] = useNodesState<Node>([] as Node[]);
	const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([] as Edge[]);
	const [selectedNode, setSelectedNode] = useState<SelectedNodeData>(null);

	const fetchData = useCallback(async () => {
		setLoading(true);
		setError(null);
		try {
			const data = await adminFlowGraphApiService.getFlowGraph();
			setGraphData(data);
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to load flow graph");
		} finally {
			setLoading(false);
		}
	}, []);

	// Rebuild nodes/edges when data or view changes
	useEffect(() => {
		if (!graphData) return;
		if (viewMode === "pipeline") {
			setNodes(buildPipelineNodes(graphData.pipeline_nodes));
			setEdges(buildPipelineEdges(graphData.pipeline_edges, graphData.pipeline_nodes));
		} else {
			setNodes(buildRoutingNodes(graphData));
			setEdges(buildRoutingEdges(graphData));
		}
		setSelectedNode(null);
	}, [graphData, viewMode, setNodes, setEdges]);

	useEffect(() => {
		fetchData();
	}, [fetchData]);

	const onNodeClick = useCallback(
		(_event: React.MouseEvent, node: Node) => {
			if (!graphData) return;

			const nodeId = node.id;

			if (viewMode === "pipeline") {
				const found = graphData.pipeline_nodes.find((n) => n.id === nodeId);
				if (found) setSelectedNode({ type: "pipeline", data: found });
			} else {
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
			}

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
		[graphData, viewMode, setEdges]
	);

	const onPaneClick = useCallback(() => {
		setSelectedNode(null);
		if (!graphData) return;
		if (viewMode === "pipeline") {
			setEdges(buildPipelineEdges(graphData.pipeline_edges, graphData.pipeline_nodes));
		} else {
			setEdges(buildRoutingEdges(graphData));
		}
	}, [graphData, viewMode, setEdges]);

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

	// Stage legend for pipeline view
	const stages = graphData?.pipeline_stages ?? [];

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
					minZoom={0.15}
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
						<div className="flex items-center gap-4 rounded-lg border bg-background/95 backdrop-blur px-4 py-2 shadow-sm">
							<Tabs value={viewMode} onValueChange={(v) => setViewMode(v as ViewMode)}>
								<TabsList className="h-8">
									<TabsTrigger value="pipeline" className="text-xs px-3 h-6">
										Pipeline
									</TabsTrigger>
									<TabsTrigger value="routing" className="text-xs px-3 h-6">
										Routing
									</TabsTrigger>
								</TabsList>
							</Tabs>

							{viewMode === "pipeline" ? (
								<div className="flex items-center gap-3 text-[10px] text-muted-foreground">
									{stages.map((s) => (
										<span key={s.id} className="flex items-center gap-1">
											<span
												className="h-2 w-2 rounded-full"
												style={{ backgroundColor: STAGE_COLORS[s.id] }}
											/>
											{s.label}
										</span>
									))}
								</div>
							) : (
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
							)}

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

			{selectedNode && (
				<FlowDetailPanel
					selectedNode={selectedNode}
					connectionCounts={connectionCounts}
					onClose={() => {
						setSelectedNode(null);
						if (!graphData) return;
						if (viewMode === "pipeline") {
							setEdges(buildPipelineEdges(graphData.pipeline_edges, graphData.pipeline_nodes));
						} else {
							setEdges(buildRoutingEdges(graphData));
						}
					}}
				/>
			)}
		</div>
	);
}
