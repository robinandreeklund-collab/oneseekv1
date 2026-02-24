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
import { adminToolSettingsApiService } from "@/lib/apis/admin-tool-settings-api.service";
import type {
	FlowGraphResponse,
	FlowIntentNode,
	FlowAgentNode,
	FlowToolNode,
	PipelineNode as PipelineNodeData,
	PipelineEdge as PipelineEdgeData,
} from "@/contracts/types/admin-flow-graph.types";
import type { MetadataCatalogResponse } from "@/contracts/types/admin-tool-settings.types";
import { IntentGraphNode } from "./flow-nodes/intent-node";
import { AgentGraphNode } from "./flow-nodes/agent-node";
import { ToolGraphNode } from "./flow-nodes/tool-node";
import { ToolGroupNode } from "./flow-nodes/tool-group-node";
import { PipelineGraphNodeMemo } from "./flow-nodes/pipeline-node";
import { FlowDetailPanel } from "./flow-detail-panel";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";

type ViewMode = "pipeline" | "routing";

const nodeTypes: NodeTypes = {
	intentNode: IntentGraphNode,
	agentNode: AgentGraphNode,
	toolNode: ToolGraphNode,
	toolGroupNode: ToolGroupNode,
	pipelineNode: PipelineGraphNodeMemo,
};

// ── Routing graph layout ────────────────────────────────────────────

const INTENT_X = 50;
const AGENT_X = 450;
const TOOL_GROUP_X = 830;
const TOOL_X = 850;
const ROW_GAP = 100;
const INTENT_ROW_GAP = 120;
const TOOL_ROW_GAP = 44;
const TOOL_GROUP_PAD_TOP = 28;
const TOOL_GROUP_PAD_BOTTOM = 10;
const TOOL_GROUP_GAP = 16;
const TOOL_NODE_WIDTH = 180;
const COLLAPSED_GROUP_HEIGHT = 36;

// Map catalog tool categories to agents by heuristic
function _inferAgentForCatalogTool(
	category: string,
	agents: FlowAgentNode[],
): string {
	const cat = (category || "").toLowerCase();
	for (const a of agents) {
		if (cat.includes(a.agent_id)) return a.agent_id;
	}
	const categoryMap: Record<string, string> = {
		weather: "väder",
		smhi: "väder",
		maps: "kartor",
		statistics: "statistik",
		scb: "statistik",
		kolada: "statistik",
		traffic: "trafik",
		trafikverket: "trafik",
		media: "media",
		podcast: "media",
		code: "kod",
		sandbox: "kod",
		browser: "webb",
		web: "webb",
		company: "bolag",
		bolagsverket: "bolag",
		riksdag: "riksdagen",
		parliament: "riksdagen",
		marketplace: "marknad",
		blocket: "marknad",
		tradera: "marknad",
	};
	for (const [key, agentId] of Object.entries(categoryMap)) {
		if (cat.includes(key)) return agentId;
	}
	return "";
}

// ── Group tools by agent – shared helper ────────────────────────────

interface ToolGroupInfo {
	agentId: string;
	label: string;
	tools: FlowToolNode[];
}

function _groupToolsByAgent(
	data: FlowGraphResponse,
	catalog: MetadataCatalogResponse | null,
): { groups: ToolGroupInfo[]; allTools: FlowToolNode[] } {
	const flowToolIds = new Set(data.tools.map((t) => t.tool_id));
	const allTools: FlowToolNode[] = [...data.tools];

	if (catalog) {
		for (const cat of catalog.tool_categories) {
			for (const tool of cat.tools) {
				if (!flowToolIds.has(tool.tool_id)) {
					flowToolIds.add(tool.tool_id);
					const agentId = _inferAgentForCatalogTool(tool.category, data.agents);
					allTools.push({
						id: `tool:${tool.tool_id}`,
						type: "tool",
						tool_id: tool.tool_id,
						label: tool.name || tool.tool_id,
						agent_id: agentId,
					});
				}
			}
		}
	}

	const toolsByAgent: Record<string, FlowToolNode[]> = {};
	const unassignedTools: FlowToolNode[] = [];
	for (const tool of allTools) {
		const agentId = tool.agent_id;
		if (agentId && data.agents.some((a) => a.agent_id === agentId)) {
			if (!toolsByAgent[agentId]) toolsByAgent[agentId] = [];
			toolsByAgent[agentId].push(tool);
		} else {
			unassignedTools.push(tool);
		}
	}

	const groups: ToolGroupInfo[] = [];
	for (const agent of data.agents) {
		const agentTools = toolsByAgent[agent.agent_id] || [];
		if (agentTools.length === 0) continue;
		groups.push({ agentId: agent.agent_id, label: agent.label, tools: agentTools });
	}
	if (unassignedTools.length > 0) {
		groups.push({ agentId: "__unassigned", label: "Övriga", tools: unassignedTools });
	}

	return { groups, allTools };
}

function buildRoutingNodes(
	data: FlowGraphResponse,
	catalog: MetadataCatalogResponse | null,
	expandedGroups: Set<string>,
): Node[] {
	const nodes: Node[] = [];

	// ── Intent nodes ──
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

	// ── Agent nodes ──
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

	// ── Build tool groups ──
	const { groups } = _groupToolsByAgent(data, catalog);

	let currentY = 20;

	for (const group of groups) {
		const isExpanded = expandedGroups.has(group.agentId);
		const groupHeight = isExpanded
			? TOOL_GROUP_PAD_TOP + group.tools.length * TOOL_ROW_GAP + TOOL_GROUP_PAD_BOTTOM
			: COLLAPSED_GROUP_HEIGHT;

		nodes.push({
			id: `toolgroup:${group.agentId}`,
			type: "toolGroupNode",
			position: { x: TOOL_GROUP_X, y: currentY },
			data: {
				label: group.label,
				agent_id: group.agentId,
				tool_count: group.tools.length,
				width: TOOL_NODE_WIDTH + 40,
				height: groupHeight,
				expanded: isExpanded,
			},
			draggable: false,
			selectable: false,
		});

		if (isExpanded) {
			for (let j = 0; j < group.tools.length; j++) {
				const tool = group.tools[j];
				nodes.push({
					id: tool.id,
					type: "toolNode",
					position: {
						x: TOOL_X,
						y: currentY + TOOL_GROUP_PAD_TOP + j * TOOL_ROW_GAP,
					},
					data: { ...tool },
					sourcePosition: Position.Right,
					targetPosition: Position.Left,
					draggable: true,
				});
			}
		}

		currentY += groupHeight + TOOL_GROUP_GAP;
	}

	return nodes;
}

function buildRoutingEdges(data: FlowGraphResponse, expandedGroups: Set<string>): Edge[] {
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

	// Only show agent→tool edges when the target tool's group is expanded
	const expandedToolIds = new Set<string>();
	for (const tool of data.tools) {
		if (expandedGroups.has(tool.agent_id)) {
			expandedToolIds.add(tool.id);
		}
	}

	data.agent_tool_edges.forEach((edge, i) => {
		if (!expandedToolIds.has(edge.target)) return;
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
	entry: "hsl(263 70% 55%)",
	fast_path: "hsl(38 92% 50%)",
	speculative: "hsl(215 14% 50%)",
	planning: "hsl(217 91% 60%)",
	tool_resolution: "hsl(189 94% 43%)",
	execution: "hsl(160 84% 39%)",
	post_processing: "hsl(215 14% 50%)",
	evaluation: "hsl(25 95% 53%)",
	synthesis: "hsl(350 89% 60%)",
};

function buildPipelineNodes(pipelineNodes: PipelineNodeData[]): Node[] {
	const nodePositions: Record<string, { x: number; y: number }> = {
		"node:resolve_intent": { x: 0, y: 200 },
		"node:memory_context": { x: 220, y: 200 },
		"node:smalltalk": { x: 440, y: 0 },
		"node:speculative": { x: 440, y: 100 },
		"node:agent_resolver": { x: 440, y: 220 },
		"node:planner": { x: 660, y: 220 },
		"node:planner_hitl_gate": { x: 880, y: 220 },
		"node:tool_resolver": { x: 440, y: 360 },
		"node:speculative_merge": { x: 660, y: 360 },
		"node:execution_router": { x: 880, y: 360 },
		"node:execution_hitl_gate": { x: 1100, y: 280 },
		"node:executor": { x: 1320, y: 280 },
		"node:tools": { x: 1540, y: 200 },
		"node:post_tools": { x: 1540, y: 340 },
		"node:artifact_indexer": { x: 1760, y: 340 },
		"node:context_compactor": { x: 1760, y: 460 },
		"node:orchestration_guard": { x: 1540, y: 460 },
		"node:critic": { x: 1320, y: 460 },
		"node:synthesis_hitl": { x: 1100, y: 560 },
		"node:progressive_synthesizer": { x: 1320, y: 620 },
		"node:synthesizer": { x: 1540, y: 620 },
	};

	return pipelineNodes.map((node) => ({
		id: node.id,
		type: "pipelineNode",
		position: nodePositions[node.id] ?? { x: 0, y: 0 },
		data: { ...node },
		sourcePosition: Position.Right,
		targetPosition: Position.Left,
	}));
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
	const [catalogData, setCatalogData] = useState<MetadataCatalogResponse | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [viewMode, setViewMode] = useState<ViewMode>("pipeline");
	const [nodes, setNodes, onNodesChange] = useNodesState<Node>([] as Node[]);
	const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([] as Edge[]);
	const [selectedNode, setSelectedNode] = useState<SelectedNodeData>(null);
	const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

	const fetchData = useCallback(async () => {
		setLoading(true);
		setError(null);
		try {
			const [flowData, catalog] = await Promise.all([
				adminFlowGraphApiService.getFlowGraph(),
				adminToolSettingsApiService.getMetadataCatalog().catch(() => null),
			]);
			setGraphData(flowData);
			setCatalogData(catalog);
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to load flow graph");
		} finally {
			setLoading(false);
		}
	}, []);

	const totalToolCount = useMemo(() => {
		if (!catalogData) return graphData?.tools.length ?? 0;
		let count = 0;
		for (const cat of catalogData.tool_categories) {
			count += cat.tools.length;
		}
		return count;
	}, [catalogData, graphData]);

	// Rebuild nodes/edges when data, view mode, or expanded groups change
	useEffect(() => {
		if (!graphData) return;
		if (viewMode === "pipeline") {
			setNodes(buildPipelineNodes(graphData.pipeline_nodes));
			setEdges(buildPipelineEdges(graphData.pipeline_edges, graphData.pipeline_nodes));
		} else {
			setNodes(buildRoutingNodes(graphData, catalogData, expandedGroups));
			setEdges(buildRoutingEdges(graphData, expandedGroups));
		}
	}, [graphData, catalogData, viewMode, expandedGroups, setNodes, setEdges]);

	// Close detail panel when data source or view mode changes (but NOT on expand/collapse)
	useEffect(() => {
		setSelectedNode(null);
	}, [graphData, viewMode]);

	useEffect(() => {
		fetchData();
	}, [fetchData]);

	const onNodeClick = useCallback(
		(_event: React.MouseEvent, node: Node) => {
			if (!graphData) return;

			const nodeId = node.id;

			// Toggle tool group expansion
			if (nodeId.startsWith("toolgroup:")) {
				const agentId = nodeId.replace("toolgroup:", "");
				setExpandedGroups((prev) => {
					const next = new Set(prev);
					if (next.has(agentId)) next.delete(agentId);
					else next.add(agentId);
					return next;
				});
				return;
			}

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
					let found = graphData.tools.find((t) => t.id === nodeId);
					if (!found) {
						const toolId = nodeId.replace("tool:", "");
						found = {
							id: nodeId,
							type: "tool",
							tool_id: toolId,
							label: (node.data as { label?: string })?.label ?? toolId,
							agent_id: (node.data as { agent_id?: string })?.agent_id ?? "",
						};
					}
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

	// ── Drag-and-drop between groups ────────────────────────────────
	const onNodeDragStop = useCallback(
		async (_event: React.MouseEvent, node: Node) => {
			if (!node.id.startsWith("tool:") || !graphData) return;

			const toolData = node.data as unknown as FlowToolNode;
			const currentAgentId = toolData.agent_id;

			// Find which group the tool was dropped into by checking Y overlap
			const groupNodes = nodes.filter((n) => n.id.startsWith("toolgroup:"));
			let targetAgentId = "";

			for (const gn of groupNodes) {
				const gd = gn.data as unknown as {
					agent_id: string;
					width: number;
					height: number;
					expanded: boolean;
				};
				const gy = gn.position.y;
				const gh = gd.height;

				// Check if the dropped node's Y center falls within this group's vertical bounds
				const nodeCenterY = node.position.y + 16; // approx half node height
				if (nodeCenterY >= gy && nodeCenterY <= gy + gh) {
					targetAgentId = gd.agent_id;
					break;
				}
			}

			// If dropped outside any group, or same group, snap back
			if (!targetAgentId || targetAgentId === currentAgentId) {
				setNodes(buildRoutingNodes(graphData, catalogData, expandedGroups));
				setEdges(buildRoutingEdges(graphData, expandedGroups));
				return;
			}

			// Don't allow dropping into the unassigned group
			if (targetAgentId === "__unassigned") {
				setNodes(buildRoutingNodes(graphData, catalogData, expandedGroups));
				setEdges(buildRoutingEdges(graphData, expandedGroups));
				toast.error("Kan inte flytta till 'Övriga' – tilldela en agent istället");
				return;
			}

			// Move tool to new agent via API
			try {
				const toolId = toolData.tool_id;
				const toolLabel = toolData.label;

				// Remove from source agent (if assigned to a real agent)
				if (currentAgentId && currentAgentId !== "__unassigned") {
					const sourceTools = graphData.tools
						.filter((t) => t.agent_id === currentAgentId && t.tool_id !== toolId)
						.map((t) => ({ tool_id: t.tool_id, label: t.label }));
					await adminFlowGraphApiService.updateAgentTools(currentAgentId, sourceTools);
				}

				// Add to target agent
				const existingTargetTools = graphData.tools
					.filter((t) => t.agent_id === targetAgentId)
					.map((t) => ({ tool_id: t.tool_id, label: t.label }));
				const targetTools = [
					...existingTargetTools,
					{ tool_id: toolId, label: toolLabel },
				];
				await adminFlowGraphApiService.updateAgentTools(targetAgentId, targetTools);

				// Find the target agent label for the toast
				const targetAgent = graphData.agents.find((a) => a.agent_id === targetAgentId);
				const targetLabel = targetAgent?.label ?? targetAgentId;
				toast.success(`"${toolLabel}" flyttat till ${targetLabel}`);

				// Expand the target group so the moved tool is visible
				setExpandedGroups((prev) => {
					const next = new Set(prev);
					next.add(targetAgentId);
					return next;
				});

				await fetchData();
			} catch {
				toast.error("Kunde inte flytta verktyg");
				setNodes(buildRoutingNodes(graphData, catalogData, expandedGroups));
				setEdges(buildRoutingEdges(graphData, expandedGroups));
			}
		},
		[graphData, catalogData, nodes, expandedGroups, fetchData, setNodes, setEdges],
	);

	const onPaneClick = useCallback(() => {
		setSelectedNode(null);
		if (!graphData) return;
		if (viewMode === "pipeline") {
			setEdges(buildPipelineEdges(graphData.pipeline_edges, graphData.pipeline_nodes));
		} else {
			setEdges(buildRoutingEdges(graphData, expandedGroups));
		}
	}, [graphData, viewMode, expandedGroups, setEdges]);

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

	const stages = graphData?.pipeline_stages ?? [];

	if (loading) {
		return (
			<div className="flex items-center justify-center h-screen">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		);
	}

	if (error) {
		return (
			<div className="flex flex-col items-center justify-center h-screen gap-4">
				<p className="text-sm text-destructive">{error}</p>
				<Button variant="outline" size="sm" onClick={fetchData}>
					<RefreshCw className="mr-2 h-4 w-4" /> Retry
				</Button>
			</div>
		);
	}

	return (
		<div className="flex h-screen">
			<div className="flex-1 relative min-w-0">
				<ReactFlow
					nodes={nodes}
					edges={edges}
					onNodesChange={onNodesChange}
					onEdgesChange={onEdgesChange}
					onNodeClick={onNodeClick}
					onNodeDragStop={onNodeDragStop}
					onPaneClick={onPaneClick}
					nodeTypes={nodeTypes}
					fitView
					fitViewOptions={{ padding: 0.15 }}
					minZoom={0.1}
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
										Verktyg ({totalToolCount})
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
					catalogData={catalogData}
					agents={graphData?.agents ?? []}
					onClose={() => {
						setSelectedNode(null);
						if (!graphData) return;
						if (viewMode === "pipeline") {
							setEdges(buildPipelineEdges(graphData.pipeline_edges, graphData.pipeline_nodes));
						} else {
							setEdges(buildRoutingEdges(graphData, expandedGroups));
						}
					}}
					onDataChanged={() => {
						setSelectedNode(null);
						fetchData();
					}}
				/>
			)}
		</div>
	);
}
