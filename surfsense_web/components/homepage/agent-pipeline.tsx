"use client";

import {
	ReactFlow,
	Background,
	type Node,
	type Edge,
	MarkerType,
	Position,
	Handle,
	type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { motion, useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/* ────────────────────────────────────────────────────────────
   Phase color definitions
   ──────────────────────────────────────────────────────────── */
type Phase = "intent" | "memory" | "planning" | "resolution" | "execution" | "validation" | "synthesis" | "response";

const PHASE_HUE: Record<Phase, { bg: string; border: string; text: string; handle: string; stroke: string }> = {
	intent: { bg: "bg-violet-500/10", border: "border-violet-500/40", text: "text-violet-400", handle: "#8b5cf6", stroke: "hsl(263 70% 55%)" },
	memory: { bg: "bg-blue-500/10", border: "border-blue-500/40", text: "text-blue-400", handle: "#3b82f6", stroke: "hsl(217 91% 60%)" },
	planning: { bg: "bg-teal-500/10", border: "border-teal-500/40", text: "text-teal-400", handle: "#14b8a6", stroke: "hsl(173 80% 40%)" },
	resolution: { bg: "bg-amber-500/10", border: "border-amber-500/40", text: "text-amber-400", handle: "#f59e0b", stroke: "hsl(38 92% 50%)" },
	execution: { bg: "bg-orange-500/10", border: "border-orange-500/40", text: "text-orange-400", handle: "#f97316", stroke: "hsl(25 95% 53%)" },
	validation: { bg: "bg-rose-500/10", border: "border-rose-500/40", text: "text-rose-400", handle: "#f43f5e", stroke: "hsl(350 89% 60%)" },
	synthesis: { bg: "bg-fuchsia-500/10", border: "border-fuchsia-500/40", text: "text-fuchsia-400", handle: "#d946ef", stroke: "hsl(292 84% 61%)" },
	response: { bg: "bg-pink-500/10", border: "border-pink-500/40", text: "text-pink-400", handle: "#ec4899", stroke: "hsl(330 81% 60%)" },
};

const PHASE_LABELS: Record<Phase, string> = {
	intent: "Intent",
	memory: "Minne",
	planning: "Planering",
	resolution: "Upplösning",
	execution: "Exekvering",
	validation: "Validering",
	synthesis: "Syntes",
	response: "Svar",
};

/* ────────────────────────────────────────────────────────────
   Pipeline node component
   ──────────────────────────────────────────────────────────── */
interface PipelineNodeData {
	label: string;
	description: string;
	phase: Phase;
	nodeType: "process" | "decision" | "hitl" | "terminal" | "branch";
	active?: boolean;
}

const PipelineNode = memo(function PipelineNode({ data }: NodeProps) {
	const d = data as unknown as PipelineNodeData;
	const colors = PHASE_HUE[d.phase];

	return (
		<>
			<Handle type="target" position={Position.Left} className="!w-2 !h-2" style={{ background: colors.handle }} />
			<div
				className={cn(
					"relative rounded-lg border px-3 py-2 shadow-sm min-w-[130px] max-w-[170px] transition-all duration-500",
					d.active ? colors.bg : "bg-neutral-900/40",
					d.active ? colors.border : "border-neutral-800/40",
					d.nodeType === "hitl" && "rounded-full border-dashed",
					d.nodeType === "decision" && "border-dashed",
					d.nodeType === "terminal" && "rounded-full",
					d.active && "shadow-lg",
				)}
				style={d.active ? { boxShadow: `0 0 20px ${colors.handle}20` } : undefined}
			>
				<div className={cn("absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full border-2 border-neutral-950 transition-colors duration-500")} style={{ background: d.active ? colors.handle : "#333" }} />
				<div className={cn("text-xs font-semibold leading-tight transition-colors duration-500", d.active ? colors.text : "text-neutral-600")}>
					{d.label}
				</div>
				{d.nodeType === "hitl" && (
					<span className={cn("text-[8px] font-bold uppercase tracking-wider", d.active ? "text-amber-400/80" : "text-neutral-700")}>HITL</span>
				)}
				{d.description && (
					<div className={cn("mt-0.5 text-[9px] leading-tight line-clamp-2 transition-colors duration-500", d.active ? "text-neutral-400" : "text-neutral-700")}>
						{d.description}
					</div>
				)}
			</div>
			<Handle type="source" position={Position.Right} className="!w-2 !h-2" style={{ background: colors.handle }} />
		</>
	);
});

const nodeTypes = { pipeline: PipelineNode };

/* ────────────────────────────────────────────────────────────
   Node definitions with positions
   ──────────────────────────────────────────────────────────── */
interface NodeDef {
	id: string;
	labelKey: string;
	descKey: string;
	phase: Phase;
	type: "process" | "decision" | "hitl" | "terminal" | "branch";
	x: number;
	y: number;
}

const NODE_DEFS: NodeDef[] = [
	// Row 1 — Intent & Memory
	{ id: "resolve_intent", labelKey: "gn_resolve_intent", descKey: "gn_resolve_intent_d", phase: "intent", type: "process", x: 0, y: 200 },
	{ id: "memory_context", labelKey: "gn_memory_context", descKey: "gn_memory_context_d", phase: "memory", type: "process", x: 240, y: 200 },
	// Branching from memory
	{ id: "smalltalk", labelKey: "gn_smalltalk", descKey: "gn_smalltalk_d", phase: "memory", type: "terminal", x: 480, y: 20 },
	{ id: "speculative", labelKey: "gn_speculative", descKey: "gn_speculative_d", phase: "memory", type: "branch", x: 480, y: 110 },
	// Planning
	{ id: "agent_resolver", labelKey: "gn_agent_resolver", descKey: "gn_agent_resolver_d", phase: "planning", type: "process", x: 480, y: 280 },
	{ id: "planner", labelKey: "gn_planner", descKey: "gn_planner_d", phase: "planning", type: "process", x: 700, y: 280 },
	{ id: "planner_hitl", labelKey: "gn_planner_hitl", descKey: "gn_planner_hitl_d", phase: "planning", type: "hitl", x: 910, y: 280 },
	// Tool Resolution
	{ id: "tool_resolver", labelKey: "gn_tool_resolver", descKey: "gn_tool_resolver_d", phase: "resolution", type: "process", x: 1120, y: 280 },
	{ id: "speculative_merge", labelKey: "gn_speculative_merge", descKey: "gn_speculative_merge_d", phase: "resolution", type: "branch", x: 1120, y: 150 },
	{ id: "execution_router", labelKey: "gn_execution_router", descKey: "gn_execution_router_d", phase: "resolution", type: "decision", x: 1340, y: 280 },
	// Execution
	{ id: "domain_planner", labelKey: "gn_domain_planner", descKey: "gn_domain_planner_d", phase: "execution", type: "process", x: 1560, y: 200 },
	{ id: "execution_hitl", labelKey: "gn_execution_hitl", descKey: "gn_execution_hitl_d", phase: "execution", type: "hitl", x: 1560, y: 320 },
	{ id: "executor", labelKey: "gn_executor", descKey: "gn_executor_d", phase: "execution", type: "process", x: 1780, y: 260 },
	{ id: "tools", labelKey: "gn_tools", descKey: "gn_tools_d", phase: "execution", type: "process", x: 2000, y: 200 },
	{ id: "post_tools", labelKey: "gn_post_tools", descKey: "gn_post_tools_d", phase: "execution", type: "process", x: 2000, y: 320 },
	{ id: "artifact_indexer", labelKey: "gn_artifact_indexer", descKey: "gn_artifact_indexer_d", phase: "execution", type: "process", x: 2220, y: 320 },
	// Validation
	{ id: "context_compactor", labelKey: "gn_context_compactor", descKey: "gn_context_compactor_d", phase: "validation", type: "process", x: 2220, y: 440 },
	{ id: "orchestration_guard", labelKey: "gn_orch_guard", descKey: "gn_orch_guard_d", phase: "validation", type: "process", x: 2000, y: 440 },
	{ id: "critic", labelKey: "gn_critic", descKey: "gn_critic_d", phase: "validation", type: "decision", x: 1780, y: 440 },
	// Synthesis
	{ id: "synthesis_hitl", labelKey: "gn_synthesis_hitl", descKey: "gn_synthesis_hitl_d", phase: "synthesis", type: "hitl", x: 1560, y: 520 },
	{ id: "progressive_synth", labelKey: "gn_progressive_synth", descKey: "gn_progressive_synth_d", phase: "synthesis", type: "process", x: 1340, y: 520 },
	{ id: "synthesizer", labelKey: "gn_synthesizer", descKey: "gn_synthesizer_d", phase: "synthesis", type: "process", x: 1120, y: 520 },
	// Response
	{ id: "response_layer", labelKey: "gn_response_layer", descKey: "gn_response_layer_d", phase: "response", type: "process", x: 910, y: 520 },
];

const EDGE_DEFS: { source: string; target: string; conditional?: boolean; label?: string }[] = [
	{ source: "resolve_intent", target: "memory_context" },
	{ source: "memory_context", target: "smalltalk", conditional: true },
	{ source: "memory_context", target: "speculative", conditional: true },
	{ source: "memory_context", target: "agent_resolver", conditional: true },
	{ source: "speculative", target: "agent_resolver" },
	{ source: "agent_resolver", target: "planner" },
	{ source: "planner", target: "planner_hitl" },
	{ source: "planner_hitl", target: "tool_resolver" },
	{ source: "tool_resolver", target: "speculative_merge" },
	{ source: "tool_resolver", target: "execution_router" },
	{ source: "speculative_merge", target: "execution_router" },
	{ source: "execution_router", target: "domain_planner" },
	{ source: "domain_planner", target: "execution_hitl" },
	{ source: "execution_hitl", target: "executor" },
	{ source: "executor", target: "tools" },
	{ source: "executor", target: "critic", conditional: true },
	{ source: "tools", target: "post_tools" },
	{ source: "post_tools", target: "artifact_indexer" },
	{ source: "artifact_indexer", target: "context_compactor" },
	{ source: "context_compactor", target: "orchestration_guard" },
	{ source: "orchestration_guard", target: "critic" },
	{ source: "critic", target: "synthesis_hitl", label: "ok" },
	{ source: "critic", target: "tool_resolver", conditional: true, label: "needs_more" },
	{ source: "critic", target: "planner", conditional: true, label: "replan" },
	{ source: "synthesis_hitl", target: "progressive_synth" },
	{ source: "synthesis_hitl", target: "synthesizer", conditional: true },
	{ source: "progressive_synth", target: "synthesizer" },
	{ source: "synthesizer", target: "response_layer" },
];

/* ────────────────────────────────────────────────────────────
   Main component
   ──────────────────────────────────────────────────────────── */
export function AgentPipeline() {
	const t = useTranslations("homepage");
	const containerRef = useRef<HTMLDivElement>(null);
	const isInView = useInView(containerRef, { once: true, amount: 0.1 });
	const [activeIdx, setActiveIdx] = useState(-1);
	const hasAnimated = useRef(false);

	useEffect(() => {
		if (!isInView || hasAnimated.current) return;
		hasAnimated.current = true;
		let step = 0;
		const interval = setInterval(() => {
			if (step < NODE_DEFS.length) {
				setActiveIdx(step);
				step++;
			} else {
				clearInterval(interval);
			}
		}, 120);
		return () => clearInterval(interval);
	}, [isInView]);

	const nodes: Node[] = useMemo(() =>
		NODE_DEFS.map((def, idx) => ({
			id: def.id,
			type: "pipeline",
			position: { x: def.x, y: def.y },
			data: {
				label: t(def.labelKey),
				description: t(def.descKey),
				phase: def.phase,
				nodeType: def.type,
				active: idx <= activeIdx,
			} satisfies PipelineNodeData,
			draggable: false,
			selectable: false,
		})),
		[t, activeIdx],
	);

	const edges: Edge[] = useMemo(() =>
		EDGE_DEFS.map((def, idx) => {
			const sourceNode = NODE_DEFS.find((n) => n.id === def.source);
			const phase = sourceNode?.phase ?? "intent";
			const color = PHASE_HUE[phase].stroke;
			const sourceActive = NODE_DEFS.findIndex((n) => n.id === def.source) <= activeIdx;
			const targetActive = NODE_DEFS.findIndex((n) => n.id === def.target) <= activeIdx;
			const edgeActive = sourceActive && targetActive;

			return {
				id: `e-${idx}`,
				source: def.source,
				target: def.target,
				type: "smoothstep",
				animated: edgeActive,
				label: def.label,
				labelStyle: { fontSize: 9, fill: "rgba(255,255,255,0.5)", fontWeight: 600 },
				labelBgStyle: { fill: "rgb(10,10,10)", fillOpacity: 0.9 },
				style: {
					stroke: color,
					strokeWidth: def.conditional ? 1 : 1.5,
					strokeDasharray: def.conditional ? "5 3" : undefined,
					opacity: edgeActive ? 0.8 : 0.12,
					transition: "opacity 0.5s ease",
				},
				markerEnd: {
					type: MarkerType.ArrowClosed,
					color,
					width: 12,
					height: 12,
				},
			};
		}),
		[activeIdx],
	);

	return (
		<section ref={containerRef} className="relative py-16 md:py-24 overflow-hidden">
			<div className="absolute inset-0 -z-10 bg-neutral-950">
				<div
					className="absolute inset-0 opacity-[0.03]"
					style={{
						backgroundImage: "linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px)",
						backgroundSize: "40px 40px",
					}}
				/>
				<div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[600px] bg-[radial-gradient(circle,rgba(139,92,246,0.08),transparent_60%)]" />
			</div>

			<div className="mx-auto max-w-7xl px-4 md:px-6">
				<motion.div
					className="text-center mb-8 md:mb-10"
					initial={{ opacity: 0, y: 20 }}
					animate={isInView ? { opacity: 1, y: 0 } : {}}
					transition={{ duration: 0.6 }}
				>
					<span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/20 text-xs font-semibold text-violet-400 uppercase tracking-wider mb-4">
						<span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
						{t("pipeline_badge")}
					</span>
					<h2 className="text-3xl md:text-5xl font-bold tracking-tight text-white">
						{t("pipeline_title")}
					</h2>
					<p className="mt-4 text-base md:text-lg text-neutral-400 max-w-2xl mx-auto">
						{t("pipeline_subtitle")}
					</p>
				</motion.div>

				{/* React Flow canvas */}
				<motion.div
					className="rounded-2xl border border-neutral-800/60 overflow-hidden"
					style={{ height: 560 }}
					initial={{ opacity: 0, scale: 0.98 }}
					animate={isInView ? { opacity: 1, scale: 1 } : {}}
					transition={{ duration: 0.6, delay: 0.2 }}
				>
					<ReactFlow
						nodes={nodes}
						edges={edges}
						nodeTypes={nodeTypes}
						fitView
						fitViewOptions={{ padding: 0.12, maxZoom: 0.65 }}
						panOnDrag
						zoomOnScroll={false}
						zoomOnPinch
						preventScrolling={false}
						nodesDraggable={false}
						nodesConnectable={false}
						elementsSelectable={false}
						proOptions={{ hideAttribution: true }}
						className="!bg-neutral-950"
					>
						<Background gap={20} size={1} color="rgba(255,255,255,0.03)" />
					</ReactFlow>
				</motion.div>

				{/* Phase legend */}
				<motion.div
					className="flex flex-wrap justify-center gap-3 mt-8"
					initial={{ opacity: 0 }}
					animate={isInView ? { opacity: 1 } : {}}
					transition={{ delay: 1.2 }}
				>
					{(Object.entries(PHASE_LABELS) as [Phase, string][]).map(([phase, label]) => (
						<div key={phase} className="flex items-center gap-1.5">
							<span className="w-2 h-2 rounded-full" style={{ background: PHASE_HUE[phase].handle }} />
							<span className="text-[10px] text-neutral-500 font-medium">{label}</span>
						</div>
					))}
				</motion.div>

				{/* Routing cards */}
				<motion.div
					className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4 max-w-3xl mx-auto"
					initial={{ opacity: 0, y: 10 }}
					animate={isInView ? { opacity: 1, y: 0 } : {}}
					transition={{ delay: 1.5, duration: 0.5 }}
				>
					{[
						{ label: "ok", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20", descKey: "routing_ok" },
						{ label: "needs_more", color: "text-amber-400", bg: "bg-amber-500/10 border-amber-500/20", descKey: "routing_needs_more" },
						{ label: "replan", color: "text-rose-400", bg: "bg-rose-500/10 border-rose-500/20", descKey: "routing_replan" },
					].map((route) => (
						<div key={route.label} className={cn("rounded-xl border p-3 text-center", route.bg)}>
							<code className={cn("text-sm font-bold", route.color)}>{route.label}</code>
							<p className="text-[11px] text-neutral-400 mt-1">{t(route.descKey)}</p>
						</div>
					))}
				</motion.div>

				<motion.p
					className="text-center mt-6 text-xs text-neutral-600"
					initial={{ opacity: 0 }}
					animate={isInView ? { opacity: 1 } : {}}
					transition={{ delay: 2 }}
				>
					{t("pipeline_node_count", { count: NODE_DEFS.length })}
				</motion.p>
			</div>
		</section>
	);
}
