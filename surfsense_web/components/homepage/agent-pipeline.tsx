"use client";

import { motion, useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/* ────────────────────────────────────────────────────────────
   Phase definitions — the 8 stages of the pipeline
   ──────────────────────────────────────────────────────────── */
interface Phase {
	id: string;
	labelKey: string;
	color: string;
	glowColor: string;
	nodes: { labelKey: string; descKey: string; isDecision?: boolean; isHitl?: boolean }[];
}

const PHASES: Phase[] = [
	{
		id: "intent",
		labelKey: "phase_intent",
		color: "#8b5cf6",
		glowColor: "rgba(139,92,246,0.3)",
		nodes: [
			{ labelKey: "gn_resolve_intent", descKey: "gn_resolve_intent_d" },
		],
	},
	{
		id: "memory",
		labelKey: "phase_memory",
		color: "#3b82f6",
		glowColor: "rgba(59,130,246,0.3)",
		nodes: [
			{ labelKey: "gn_memory_context", descKey: "gn_memory_context_d" },
			{ labelKey: "gn_smalltalk", descKey: "gn_smalltalk_d" },
			{ labelKey: "gn_speculative", descKey: "gn_speculative_d" },
		],
	},
	{
		id: "planning",
		labelKey: "phase_planning",
		color: "#14b8a6",
		glowColor: "rgba(20,184,166,0.3)",
		nodes: [
			{ labelKey: "gn_agent_resolver", descKey: "gn_agent_resolver_d" },
			{ labelKey: "gn_planner", descKey: "gn_planner_d" },
			{ labelKey: "gn_planner_hitl", descKey: "gn_planner_hitl_d", isHitl: true },
		],
	},
	{
		id: "resolution",
		labelKey: "phase_resolution",
		color: "#f59e0b",
		glowColor: "rgba(245,158,11,0.3)",
		nodes: [
			{ labelKey: "gn_tool_resolver", descKey: "gn_tool_resolver_d" },
			{ labelKey: "gn_speculative_merge", descKey: "gn_speculative_merge_d" },
			{ labelKey: "gn_execution_router", descKey: "gn_execution_router_d", isDecision: true },
		],
	},
	{
		id: "execution",
		labelKey: "phase_execution",
		color: "#f97316",
		glowColor: "rgba(249,115,22,0.3)",
		nodes: [
			{ labelKey: "gn_domain_planner", descKey: "gn_domain_planner_d" },
			{ labelKey: "gn_execution_hitl", descKey: "gn_execution_hitl_d", isHitl: true },
			{ labelKey: "gn_executor", descKey: "gn_executor_d" },
			{ labelKey: "gn_tools", descKey: "gn_tools_d" },
			{ labelKey: "gn_post_tools", descKey: "gn_post_tools_d" },
			{ labelKey: "gn_artifact_indexer", descKey: "gn_artifact_indexer_d" },
		],
	},
	{
		id: "validation",
		labelKey: "phase_validation",
		color: "#f43f5e",
		glowColor: "rgba(244,63,94,0.3)",
		nodes: [
			{ labelKey: "gn_context_compactor", descKey: "gn_context_compactor_d" },
			{ labelKey: "gn_orch_guard", descKey: "gn_orch_guard_d" },
			{ labelKey: "gn_critic", descKey: "gn_critic_d", isDecision: true },
		],
	},
	{
		id: "synthesis",
		labelKey: "phase_synthesis",
		color: "#d946ef",
		glowColor: "rgba(217,70,239,0.3)",
		nodes: [
			{ labelKey: "gn_synthesis_hitl", descKey: "gn_synthesis_hitl_d", isHitl: true },
			{ labelKey: "gn_progressive_synth", descKey: "gn_progressive_synth_d" },
			{ labelKey: "gn_synthesizer", descKey: "gn_synthesizer_d" },
		],
	},
	{
		id: "response",
		labelKey: "phase_response",
		color: "#ec4899",
		glowColor: "rgba(236,72,153,0.3)",
		nodes: [
			{ labelKey: "gn_response_layer", descKey: "gn_response_layer_d" },
		],
	},
];

/* ────────────────────────────────────────────────────────────
   Phase row component
   ──────────────────────────────────────────────────────────── */
function PhaseRow({
	phase,
	index,
	activePhase,
	expandedNode,
	onNodeClick,
	t,
}: {
	phase: Phase;
	index: number;
	activePhase: number;
	expandedNode: string | null;
	onNodeClick: (key: string) => void;
	t: ReturnType<typeof useTranslations>;
}) {
	const isActive = index <= activePhase;
	const isCurrent = index === activePhase;

	return (
		<motion.div
			className="relative"
			initial={{ opacity: 0, x: -30 }}
			animate={isActive ? { opacity: 1, x: 0 } : { opacity: 0.15, x: 0 }}
			transition={{ duration: 0.5, delay: index * 0.08 }}
		>
			{/* Connector line to next phase */}
			{index < PHASES.length - 1 && (
				<div className="absolute left-[19px] top-[40px] bottom-[-8px] w-px">
					<motion.div
						className="w-full h-full origin-top"
						style={{ background: `linear-gradient(to bottom, ${phase.color}40, transparent)` }}
						initial={{ scaleY: 0 }}
						animate={isActive ? { scaleY: 1 } : { scaleY: 0 }}
						transition={{ duration: 0.4, delay: index * 0.08 + 0.3 }}
					/>
				</div>
			)}

			<div className="flex items-start gap-4">
				{/* Phase indicator dot */}
				<div className="relative shrink-0 mt-1">
					<motion.div
						className="w-[10px] h-[10px] rounded-full border-[2.5px]"
						style={{
							borderColor: isActive ? phase.color : "#404040",
							background: isCurrent ? phase.color : "transparent",
						}}
						animate={
							isCurrent
								? { boxShadow: [`0 0 0px ${phase.color}00`, `0 0 12px ${phase.glowColor}`, `0 0 0px ${phase.color}00`] }
								: { boxShadow: "none" }
						}
						transition={isCurrent ? { duration: 2, repeat: Number.POSITIVE_INFINITY } : {}}
					/>
				</div>

				{/* Phase content */}
				<div className="flex-1 min-w-0 pb-8">
					{/* Phase label */}
					<div className="flex items-center gap-3 mb-3">
						<span
							className="text-[11px] font-bold uppercase tracking-[0.15em]"
							style={{ color: isActive ? phase.color : "#525252" }}
						>
							{t(phase.labelKey)}
						</span>
						<motion.div
							className="h-px flex-1"
							style={{ background: `linear-gradient(to right, ${phase.color}30, transparent)` }}
							initial={{ scaleX: 0, transformOrigin: "left" }}
							animate={isActive ? { scaleX: 1 } : { scaleX: 0 }}
							transition={{ duration: 0.6, delay: index * 0.08 + 0.2 }}
						/>
						{isCurrent && (
							<motion.span
								className="text-[9px] font-medium px-2 py-0.5 rounded-full"
								style={{ background: `${phase.color}15`, color: phase.color }}
								initial={{ opacity: 0, scale: 0.8 }}
								animate={{ opacity: 1, scale: 1 }}
								transition={{ delay: 0.3 }}
							>
								ACTIVE
							</motion.span>
						)}
					</div>

					{/* Node chips */}
					<div className="flex flex-wrap gap-2">
						{phase.nodes.map((node, ni) => {
							const nodeKey = `${phase.id}-${ni}`;
							const isExpanded = expandedNode === nodeKey;
							return (
								<motion.button
									type="button"
									key={nodeKey}
									onClick={() => onNodeClick(nodeKey)}
									className={cn(
										"relative text-left rounded-lg border transition-all duration-300",
										isActive
											? "border-neutral-700/60 hover:border-neutral-600 bg-neutral-900/80"
											: "border-neutral-800/40 bg-neutral-900/30",
										isExpanded && "ring-1",
										node.isHitl && "border-dashed",
									)}
									style={isExpanded ? { ringColor: phase.color, borderColor: `${phase.color}60` } : undefined}
									initial={{ opacity: 0, y: 8 }}
									animate={isActive ? { opacity: 1, y: 0 } : { opacity: 0.3, y: 0 }}
									transition={{ duration: 0.3, delay: index * 0.08 + ni * 0.05 + 0.15 }}
									whileHover={isActive ? { scale: 1.02 } : undefined}
								>
									<div className="px-3 py-2">
										<div className="flex items-center gap-2">
											{/* Status dot */}
											<span
												className="w-1.5 h-1.5 rounded-full shrink-0"
												style={{ background: isActive ? phase.color : "#404040" }}
											/>
											<span
												className={cn(
													"text-xs font-medium whitespace-nowrap",
													isActive ? "text-neutral-200" : "text-neutral-600",
												)}
											>
												{t(node.labelKey)}
											</span>
											{node.isDecision && (
												<span className="text-[8px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 font-bold uppercase">
													decision
												</span>
											)}
											{node.isHitl && (
												<span className="text-[8px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-500 font-bold uppercase">
													hitl
												</span>
											)}
											{/* Expand indicator */}
											<svg
												className={cn(
													"w-3 h-3 transition-transform duration-200 ml-auto shrink-0",
													isActive ? "text-neutral-500" : "text-neutral-700",
													isExpanded && "rotate-180",
												)}
												fill="none"
												viewBox="0 0 24 24"
												stroke="currentColor"
												strokeWidth={2}
											>
												<path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
											</svg>
										</div>
									</div>

									{/* Expanded description */}
									<motion.div
										initial={false}
										animate={{ height: isExpanded ? "auto" : 0, opacity: isExpanded ? 1 : 0 }}
										transition={{ duration: 0.2 }}
										className="overflow-hidden"
									>
										<div className="px-3 pb-2.5 pt-0.5">
											<p className="text-[11px] leading-relaxed text-neutral-400">
												{t(node.descKey)}
											</p>
										</div>
									</motion.div>
								</motion.button>
							);
						})}
					</div>
				</div>
			</div>
		</motion.div>
	);
}

/* ────────────────────────────────────────────────────────────
   Animated progress bar — shows the "signal" flowing through
   ──────────────────────────────────────────────────────────── */
function ProgressSignal({ activePhase, total }: { activePhase: number; total: number }) {
	const progress = total > 1 ? activePhase / (total - 1) : 0;

	return (
		<div className="relative h-1 rounded-full bg-neutral-800/60 overflow-hidden">
			<motion.div
				className="absolute inset-y-0 left-0 rounded-full"
				style={{
					background: "linear-gradient(90deg, #8b5cf6, #3b82f6, #14b8a6, #f59e0b, #f97316, #f43f5e, #d946ef, #ec4899)",
				}}
				initial={{ width: "0%" }}
				animate={{ width: `${progress * 100}%` }}
				transition={{ duration: 0.6, ease: "easeOut" }}
			/>
			{/* Glowing head */}
			<motion.div
				className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full"
				style={{
					background: PHASES[Math.min(activePhase, PHASES.length - 1)].color,
					boxShadow: `0 0 12px ${PHASES[Math.min(activePhase, PHASES.length - 1)].glowColor}`,
				}}
				initial={{ left: "0%" }}
				animate={{ left: `${progress * 100}%` }}
				transition={{ duration: 0.6, ease: "easeOut" }}
			/>
		</div>
	);
}

/* ────────────────────────────────────────────────────────────
   Main component
   ──────────────────────────────────────────────────────────── */
export function AgentPipeline() {
	const t = useTranslations("homepage");
	const containerRef = useRef<HTMLDivElement>(null);
	const isInView = useInView(containerRef, { once: true, amount: 0.1 });
	const [activePhase, setActivePhase] = useState(-1);
	const [expandedNode, setExpandedNode] = useState<string | null>(null);
	const hasAnimated = useRef(false);

	// Count total nodes
	const totalNodes = useMemo(() => PHASES.reduce((sum, p) => sum + p.nodes.length, 0), []);

	// Sequential phase activation on scroll
	useEffect(() => {
		if (!isInView || hasAnimated.current) return;
		hasAnimated.current = true;

		let step = 0;
		const interval = setInterval(() => {
			if (step < PHASES.length) {
				setActivePhase(step);
				step++;
			} else {
				clearInterval(interval);
			}
		}, 350);
		return () => clearInterval(interval);
	}, [isInView]);

	const handleNodeClick = (key: string) => {
		setExpandedNode((prev) => (prev === key ? null : key));
	};

	return (
		<section ref={containerRef} className="relative py-16 md:py-24 overflow-hidden">
			{/* Dark background */}
			<div className="absolute inset-0 -z-10 bg-neutral-950">
				<div
					className="absolute inset-0 opacity-[0.02]"
					style={{
						backgroundImage:
							"radial-gradient(circle, rgba(255,255,255,0.15) 1px, transparent 1px)",
						backgroundSize: "24px 24px",
					}}
				/>
				{/* Ambient glow */}
				<div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-[radial-gradient(circle,rgba(139,92,246,0.06),transparent_60%)]" />
				<div className="absolute bottom-1/4 left-1/3 w-[400px] h-[300px] bg-[radial-gradient(circle,rgba(236,72,153,0.04),transparent_60%)]" />
			</div>

			<div className="mx-auto max-w-4xl px-6">
				{/* Header */}
				<motion.div
					className="text-center mb-12"
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

				{/* Progress signal bar */}
				<motion.div
					className="mb-10"
					initial={{ opacity: 0 }}
					animate={isInView ? { opacity: 1 } : {}}
					transition={{ delay: 0.3 }}
				>
					<ProgressSignal activePhase={activePhase} total={PHASES.length} />
					{/* Phase markers */}
					<div className="flex justify-between mt-2">
						{PHASES.map((phase, i) => (
							<button
								type="button"
								key={phase.id}
								onClick={() => setActivePhase(i)}
								className={cn(
									"text-[9px] font-medium transition-colors duration-300 cursor-pointer hover:opacity-80",
									i <= activePhase ? "opacity-100" : "opacity-30",
								)}
								style={{ color: phase.color }}
							>
								{t(phase.labelKey)}
							</button>
						))}
					</div>
				</motion.div>

				{/* Phase timeline */}
				<div className="relative pl-2">
					{PHASES.map((phase, index) => (
						<PhaseRow
							key={phase.id}
							phase={phase}
							index={index}
							activePhase={activePhase}
							expandedNode={expandedNode}
							onNodeClick={handleNodeClick}
							t={t}
						/>
					))}
				</div>

				{/* Footer stat */}
				<motion.div
					className="mt-8 flex items-center justify-center gap-4"
					initial={{ opacity: 0 }}
					animate={isInView ? { opacity: 1 } : {}}
					transition={{ delay: 3 }}
				>
					<div className="h-px w-16 bg-gradient-to-r from-transparent to-neutral-700" />
					<span className="text-xs text-neutral-500 font-medium">
						{t("pipeline_node_count", { count: totalNodes })}
					</span>
					<div className="h-px w-16 bg-gradient-to-l from-transparent to-neutral-700" />
				</motion.div>
			</div>
		</section>
	);
}
