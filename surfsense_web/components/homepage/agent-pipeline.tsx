"use client";

import { motion, useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/* ────────────────────────────────────────────────────────────
   Phase definitions with gradient colors
   ──────────────────────────────────────────────────────────── */
type Phase = "intent" | "memory" | "planning" | "resolution" | "execution" | "validation" | "synthesis" | "response";

const PHASE_STYLES: Record<Phase, { gradient: string; glow: string; dot: string; label: string; border: string }> = {
	intent: {
		gradient: "from-violet-500 to-purple-600",
		glow: "shadow-violet-500/40",
		dot: "bg-violet-400",
		label: "Fas 1 — Intent",
		border: "border-violet-500/40",
	},
	memory: {
		gradient: "from-blue-500 to-cyan-500",
		glow: "shadow-blue-500/40",
		dot: "bg-blue-400",
		label: "Fas 1.5 — Minne",
		border: "border-blue-500/40",
	},
	planning: {
		gradient: "from-teal-400 to-emerald-500",
		glow: "shadow-teal-500/40",
		dot: "bg-teal-400",
		label: "Fas 2 — Planering",
		border: "border-teal-500/40",
	},
	resolution: {
		gradient: "from-amber-400 to-yellow-500",
		glow: "shadow-amber-500/40",
		dot: "bg-amber-400",
		label: "Fas 2.5 — Upplösning",
		border: "border-amber-500/40",
	},
	execution: {
		gradient: "from-orange-400 to-red-500",
		glow: "shadow-orange-500/40",
		dot: "bg-orange-400",
		label: "Fas 3–4 — Exekvering",
		border: "border-orange-500/40",
	},
	validation: {
		gradient: "from-rose-500 to-pink-600",
		glow: "shadow-rose-500/40",
		dot: "bg-rose-400",
		label: "Fas 5 — Validering",
		border: "border-rose-500/40",
	},
	synthesis: {
		gradient: "from-fuchsia-500 to-pink-500",
		glow: "shadow-fuchsia-500/40",
		dot: "bg-fuchsia-400",
		label: "Fas 6 — Syntes",
		border: "border-fuchsia-500/40",
	},
	response: {
		gradient: "from-pink-500 to-rose-400",
		glow: "shadow-pink-500/40",
		dot: "bg-pink-400",
		label: "Svarslager",
		border: "border-pink-500/40",
	},
};

/* ────────────────────────────────────────────────────────────
   Node definitions — accurate to the actual LangGraph flow
   ──────────────────────────────────────────────────────────── */
interface GraphNode {
	id: string;
	labelKey: string;
	descKey: string;
	phase: Phase;
	type: "process" | "decision" | "hitl" | "terminal" | "branch";
}

const GRAPH_NODES: GraphNode[] = [
	// Phase 1: Intent
	{ id: "resolve_intent", labelKey: "gn_resolve_intent", descKey: "gn_resolve_intent_d", phase: "intent", type: "process" },
	// Phase 1.5: Memory & routing
	{ id: "memory_context", labelKey: "gn_memory_context", descKey: "gn_memory_context_d", phase: "memory", type: "process" },
	{ id: "smalltalk", labelKey: "gn_smalltalk", descKey: "gn_smalltalk_d", phase: "memory", type: "terminal" },
	{ id: "speculative", labelKey: "gn_speculative", descKey: "gn_speculative_d", phase: "memory", type: "branch" },
	// Phase 2: Planning
	{ id: "agent_resolver", labelKey: "gn_agent_resolver", descKey: "gn_agent_resolver_d", phase: "planning", type: "process" },
	{ id: "planner", labelKey: "gn_planner", descKey: "gn_planner_d", phase: "planning", type: "process" },
	{ id: "planner_hitl", labelKey: "gn_planner_hitl", descKey: "gn_planner_hitl_d", phase: "planning", type: "hitl" },
	// Phase 2.5: Tool resolution
	{ id: "tool_resolver", labelKey: "gn_tool_resolver", descKey: "gn_tool_resolver_d", phase: "resolution", type: "process" },
	{ id: "speculative_merge", labelKey: "gn_speculative_merge", descKey: "gn_speculative_merge_d", phase: "resolution", type: "branch" },
	{ id: "execution_router", labelKey: "gn_execution_router", descKey: "gn_execution_router_d", phase: "resolution", type: "decision" },
	// Phase 3: Domain planning + execution
	{ id: "domain_planner", labelKey: "gn_domain_planner", descKey: "gn_domain_planner_d", phase: "execution", type: "process" },
	{ id: "execution_hitl", labelKey: "gn_execution_hitl", descKey: "gn_execution_hitl_d", phase: "execution", type: "hitl" },
	{ id: "executor", labelKey: "gn_executor", descKey: "gn_executor_d", phase: "execution", type: "process" },
	{ id: "tools", labelKey: "gn_tools", descKey: "gn_tools_d", phase: "execution", type: "process" },
	{ id: "post_tools", labelKey: "gn_post_tools", descKey: "gn_post_tools_d", phase: "execution", type: "process" },
	{ id: "artifact_indexer", labelKey: "gn_artifact_indexer", descKey: "gn_artifact_indexer_d", phase: "execution", type: "process" },
	// Phase 4: Validation
	{ id: "context_compactor", labelKey: "gn_context_compactor", descKey: "gn_context_compactor_d", phase: "validation", type: "process" },
	{ id: "orchestration_guard", labelKey: "gn_orch_guard", descKey: "gn_orch_guard_d", phase: "validation", type: "process" },
	{ id: "critic", labelKey: "gn_critic", descKey: "gn_critic_d", phase: "validation", type: "decision" },
	// Phase 5: Synthesis
	{ id: "synthesis_hitl", labelKey: "gn_synthesis_hitl", descKey: "gn_synthesis_hitl_d", phase: "synthesis", type: "hitl" },
	{ id: "progressive_synth", labelKey: "gn_progressive_synth", descKey: "gn_progressive_synth_d", phase: "synthesis", type: "process" },
	{ id: "synthesizer", labelKey: "gn_synthesizer", descKey: "gn_synthesizer_d", phase: "synthesis", type: "process" },
	// Response layer
	{ id: "response_layer", labelKey: "gn_response_layer", descKey: "gn_response_layer_d", phase: "response", type: "process" },
];

/* ────────────────────────────────────────────────────────────
   Row layout for the graph (how nodes are arranged visually)
   ──────────────────────────────────────────────────────────── */
const NODE_ROWS: string[][] = [
	["resolve_intent", "memory_context"],
	["smalltalk", "speculative", "agent_resolver"],
	["planner", "planner_hitl", "tool_resolver"],
	["speculative_merge", "execution_router", "domain_planner"],
	["execution_hitl", "executor", "tools"],
	["post_tools", "artifact_indexer", "context_compactor"],
	["orchestration_guard", "critic", "synthesis_hitl"],
	["progressive_synth", "synthesizer", "response_layer"],
];

/* ────────────────────────────────────────────────────────────
   Edges (connections between nodes)
   ──────────────────────────────────────────────────────────── */
const EDGES: [string, string][] = [
	["resolve_intent", "memory_context"],
	["memory_context", "smalltalk"],
	["memory_context", "speculative"],
	["memory_context", "agent_resolver"],
	["speculative", "agent_resolver"],
	["agent_resolver", "planner"],
	["planner", "planner_hitl"],
	["planner_hitl", "tool_resolver"],
	["tool_resolver", "speculative_merge"],
	["speculative_merge", "execution_router"],
	["execution_router", "domain_planner"],
	["domain_planner", "execution_hitl"],
	["execution_hitl", "executor"],
	["executor", "tools"],
	["executor", "critic"],
	["tools", "post_tools"],
	["post_tools", "artifact_indexer"],
	["artifact_indexer", "context_compactor"],
	["context_compactor", "orchestration_guard"],
	["orchestration_guard", "critic"],
	["critic", "synthesis_hitl"],
	["critic", "tool_resolver"],
	["critic", "planner"],
	["synthesis_hitl", "progressive_synth"],
	["synthesis_hitl", "synthesizer"],
	["progressive_synth", "synthesizer"],
	["synthesizer", "response_layer"],
];

/* ────────────────────────────────────────────────────────────
   Animated flowing particle on SVG path
   ──────────────────────────────────────────────────────────── */
const FlowParticle = ({ pathId, color, delay }: { pathId: string; color: string; delay: number }) => (
	<circle r="2.5" fill={color} opacity="0.9">
		<animateMotion dur="3s" repeatCount="indefinite" begin={`${delay}s`}>
			<mpath href={`#${pathId}`} />
		</animateMotion>
	</circle>
);

/* ────────────────────────────────────────────────────────────
   Main component
   ──────────────────────────────────────────────────────────── */
export function AgentPipeline() {
	const t = useTranslations("homepage");
	const containerRef = useRef<HTMLDivElement>(null);
	const graphRef = useRef<HTMLDivElement>(null);
	const isInView = useInView(containerRef, { once: true, amount: 0.15 });
	const [activeStep, setActiveStep] = useState(-1);
	const [hoveredNode, setHoveredNode] = useState<string | null>(null);
	const hasAnimated = useRef(false);

	// Flatten rows into activation order
	const activationOrder = useMemo(() => NODE_ROWS.flat(), []);

	// Sequential activation on scroll
	useEffect(() => {
		if (!isInView || hasAnimated.current) return;
		hasAnimated.current = true;

		let step = 0;
		const interval = setInterval(() => {
			if (step < activationOrder.length) {
				setActiveStep(step);
				step++;
			} else {
				clearInterval(interval);
			}
		}, 180);

		return () => clearInterval(interval);
	}, [isInView, activationOrder]);

	const getNodeState = (nodeId: string): "active" | "past" | "future" => {
		const idx = activationOrder.indexOf(nodeId);
		if (idx === activeStep) return "active";
		if (idx < activeStep) return "past";
		return "future";
	};

	const isEdgeActive = (from: string, to: string): boolean => {
		const fromState = getNodeState(from);
		const toState = getNodeState(to);
		return fromState !== "future" && toState !== "future";
	};

	return (
		<section
			ref={containerRef}
			className="relative py-20 md:py-28 overflow-hidden"
		>
			{/* Dark background with grid pattern */}
			<div className="absolute inset-0 -z-10 bg-neutral-950">
				<div
					className="absolute inset-0 opacity-[0.03]"
					style={{
						backgroundImage: `linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px)`,
						backgroundSize: "40px 40px",
					}}
				/>
				<div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[600px] bg-[radial-gradient(circle,rgba(139,92,246,0.08),transparent_60%)]" />
				<div className="absolute top-0 left-1/4 w-[500px] h-[400px] bg-[radial-gradient(circle,rgba(59,130,246,0.06),transparent_60%)]" />
				<div className="absolute bottom-0 right-1/4 w-[500px] h-[400px] bg-[radial-gradient(circle,rgba(236,72,153,0.06),transparent_60%)]" />
			</div>

			<div className="mx-auto max-w-7xl px-4 md:px-6">
				{/* Header */}
				<motion.div
					className="text-center mb-12 md:mb-16"
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

				{/* Graph visualization */}
				<div ref={graphRef} className="relative max-w-6xl mx-auto">
					{/* Node rows */}
					<div className="space-y-3 md:space-y-4">
						{NODE_ROWS.map((row, rowIdx) => (
							<motion.div
								key={rowIdx}
								className="flex flex-wrap justify-center gap-3 md:gap-4"
								initial={{ opacity: 0, y: 15 }}
								animate={isInView ? { opacity: 1, y: 0 } : {}}
								transition={{ duration: 0.4, delay: rowIdx * 0.08 }}
							>
								{row.map((nodeId) => {
									const node = GRAPH_NODES.find((n) => n.id === nodeId);
									if (!node) return null;
									const phase = PHASE_STYLES[node.phase];
									const state = getNodeState(nodeId);
									const isHovered = hoveredNode === nodeId;

									return (
										<motion.div
											key={nodeId}
											className="relative group"
											onMouseEnter={() => setHoveredNode(nodeId)}
											onMouseLeave={() => setHoveredNode(null)}
											animate={{
												scale: state === "active" ? 1.05 : isHovered ? 1.03 : 1,
											}}
											transition={{ type: "spring", stiffness: 400, damping: 25 }}
										>
											{/* Glow effect behind */}
											<div
												className={cn(
													"absolute -inset-1 rounded-xl blur-md transition-opacity duration-500",
													state === "active"
														? `bg-gradient-to-r ${phase.gradient} opacity-40`
														: state === "past"
															? `bg-gradient-to-r ${phase.gradient} opacity-10`
															: "opacity-0",
												)}
											/>

											{/* Node card */}
											<div
												className={cn(
													"relative flex items-center gap-2.5 px-4 py-2.5 rounded-xl border backdrop-blur-sm transition-all duration-300 cursor-default",
													// Shape modifiers
													node.type === "hitl" && "rounded-full",
													node.type === "decision" && "rounded-2xl border-dashed",
													node.type === "terminal" && "rounded-full",
													node.type === "branch" && "rounded-xl border-dotted",
													// State colors
													state === "active"
														? `bg-gradient-to-r ${phase.gradient} border-transparent text-white shadow-lg ${phase.glow}`
														: state === "past"
															? `bg-neutral-900/80 ${phase.border} text-neutral-200`
															: "bg-neutral-900/40 border-neutral-800/50 text-neutral-600",
												)}
											>
												{/* Type indicator dot */}
												<span
													className={cn(
														"w-2 h-2 rounded-full shrink-0 transition-colors duration-300",
														state === "active" ? "bg-white" : state === "past" ? phase.dot : "bg-neutral-700",
													)}
												/>

												{/* Label */}
												<span className={cn(
													"text-xs md:text-sm font-medium whitespace-nowrap",
													state === "active" && "font-semibold",
												)}>
													{t(node.labelKey)}
												</span>

												{/* HITL badge */}
												{node.type === "hitl" && (
													<span className={cn(
														"text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full",
														state === "active"
															? "bg-white/20 text-white"
															: state === "past"
																? "bg-amber-500/20 text-amber-400"
																: "bg-neutral-800 text-neutral-600",
													)}>
														HITL
													</span>
												)}

												{/* Scanning shine on active */}
												{state === "active" && (
													<motion.div
														className="absolute inset-0 rounded-xl overflow-hidden pointer-events-none"
														initial={false}
													>
														<motion.div
															className="absolute inset-y-0 w-[60%] bg-gradient-to-r from-transparent via-white/15 to-transparent"
															animate={{ x: ["-100%", "250%"] }}
															transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
														/>
													</motion.div>
												)}
											</div>

											{/* Tooltip */}
											<div
												className={cn(
													"absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-3 w-64 px-4 py-3 rounded-xl",
													"bg-neutral-900 border border-neutral-700 shadow-2xl",
													"text-xs text-neutral-300 leading-relaxed",
													"transition-all duration-200 pointer-events-none",
													isHovered ? "opacity-100 translate-y-0" : "opacity-0 translate-y-1",
												)}
											>
												<div className="font-semibold text-white mb-1 text-sm">
													{t(node.labelKey)}
												</div>
												<div className="text-neutral-400 text-[10px] font-medium uppercase tracking-wider mb-1.5">
													{PHASE_STYLES[node.phase].label}
												</div>
												{t(node.descKey)}
												<div className="absolute left-1/2 -translate-x-1/2 top-full w-2.5 h-2.5 rotate-45 bg-neutral-900 border-r border-b border-neutral-700" />
											</div>
										</motion.div>
									);
								})}
							</motion.div>
						))}
					</div>

					{/* Connection lines overlay (desktop only) */}
					<div className="hidden md:block absolute inset-0 pointer-events-none -z-[1]">
						{/* Vertical flow indicators between rows */}
						{NODE_ROWS.slice(0, -1).map((_, rowIdx) => (
							<div
								key={`flow-${rowIdx}`}
								className="flex justify-center"
								style={{
									position: "absolute",
									top: `${((rowIdx + 1) / NODE_ROWS.length) * 100}%`,
									left: "50%",
									transform: "translate(-50%, -50%)",
								}}
							>
								<motion.div
									className="w-px h-3"
									animate={{
										backgroundColor: rowIdx < Math.floor(activeStep / 3)
											? "rgba(139, 92, 246, 0.4)"
											: "rgba(100, 100, 100, 0.15)",
									}}
									transition={{ duration: 0.5 }}
								/>
							</div>
						))}
					</div>

					{/* Phase legend */}
					<motion.div
						className="flex flex-wrap justify-center gap-3 mt-10 md:mt-14"
						initial={{ opacity: 0 }}
						animate={isInView ? { opacity: 1 } : {}}
						transition={{ delay: 1.2 }}
					>
						{(Object.entries(PHASE_STYLES) as [Phase, typeof PHASE_STYLES[Phase]][]).map(([phase, style]) => (
							<div key={phase} className="flex items-center gap-1.5">
								<span className={cn("w-2 h-2 rounded-full", style.dot)} />
								<span className="text-[10px] text-neutral-500 font-medium">{style.label}</span>
							</div>
						))}
					</motion.div>

					{/* Routing explanation */}
					<motion.div
						className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-4 max-w-3xl mx-auto"
						initial={{ opacity: 0, y: 10 }}
						animate={isInView ? { opacity: 1, y: 0 } : {}}
						transition={{ delay: 1.5, duration: 0.5 }}
					>
						{[
							{ label: "ok", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20", descKey: "routing_ok" },
							{ label: "needs_more", color: "text-amber-400", bg: "bg-amber-500/10 border-amber-500/20", descKey: "routing_needs_more" },
							{ label: "replan", color: "text-rose-400", bg: "bg-rose-500/10 border-rose-500/20", descKey: "routing_replan" },
						].map((route) => (
							<div
								key={route.label}
								className={cn("rounded-xl border p-3 text-center", route.bg)}
							>
								<code className={cn("text-sm font-bold", route.color)}>{route.label}</code>
								<p className="text-[11px] text-neutral-400 mt-1">{t(route.descKey)}</p>
							</div>
						))}
					</motion.div>

					{/* Node count badge */}
					<motion.p
						className="text-center mt-8 text-xs text-neutral-600"
						initial={{ opacity: 0 }}
						animate={isInView ? { opacity: 1 } : {}}
						transition={{ delay: 2 }}
					>
						{t("pipeline_node_count", { count: GRAPH_NODES.length })}
					</motion.p>
				</div>
			</div>
		</section>
	);
}
