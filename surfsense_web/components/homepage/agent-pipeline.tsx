"use client";

import { motion, useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface PipelineNode {
	id: string;
	labelKey: string;
	descKey: string;
	phase: "intent" | "planning" | "execution" | "validation" | "output";
	type: "process" | "decision" | "hitl" | "terminal";
}

const NODES: PipelineNode[] = [
	{ id: "start", labelKey: "node_start", descKey: "node_start_desc", phase: "intent", type: "terminal" },
	{ id: "intent", labelKey: "node_intent", descKey: "node_intent_desc", phase: "intent", type: "process" },
	{ id: "agent_resolver", labelKey: "node_agent_resolver", descKey: "node_agent_resolver_desc", phase: "planning", type: "process" },
	{ id: "planner", labelKey: "node_planner", descKey: "node_planner_desc", phase: "planning", type: "process" },
	{ id: "plan_approval", labelKey: "node_plan_approval", descKey: "node_plan_approval_desc", phase: "planning", type: "hitl" },
	{ id: "tool_resolver", labelKey: "node_tool_resolver", descKey: "node_tool_resolver_desc", phase: "execution", type: "process" },
	{ id: "executor", labelKey: "node_executor", descKey: "node_executor_desc", phase: "execution", type: "process" },
	{ id: "tools", labelKey: "node_tools", descKey: "node_tools_desc", phase: "execution", type: "process" },
	{ id: "post_tools", labelKey: "node_post_tools", descKey: "node_post_tools_desc", phase: "execution", type: "process" },
	{ id: "guard", labelKey: "node_guard", descKey: "node_guard_desc", phase: "validation", type: "process" },
	{ id: "critic", labelKey: "node_critic", descKey: "node_critic_desc", phase: "validation", type: "decision" },
	{ id: "synthesizer", labelKey: "node_synthesizer", descKey: "node_synthesizer_desc", phase: "output", type: "process" },
	{ id: "end", labelKey: "node_end", descKey: "node_end_desc", phase: "output", type: "terminal" },
];

const PHASE_COLORS: Record<string, { bg: string; text: string; border: string; glow: string }> = {
	intent: {
		bg: "bg-purple-500/10 dark:bg-purple-500/20",
		text: "text-purple-700 dark:text-purple-300",
		border: "border-purple-300 dark:border-purple-500/40",
		glow: "shadow-purple-500/20",
	},
	planning: {
		bg: "bg-blue-500/10 dark:bg-blue-500/20",
		text: "text-blue-700 dark:text-blue-300",
		border: "border-blue-300 dark:border-blue-500/40",
		glow: "shadow-blue-500/20",
	},
	execution: {
		bg: "bg-emerald-500/10 dark:bg-emerald-500/20",
		text: "text-emerald-700 dark:text-emerald-300",
		border: "border-emerald-300 dark:border-emerald-500/40",
		glow: "shadow-emerald-500/20",
	},
	validation: {
		bg: "bg-amber-500/10 dark:bg-amber-500/20",
		text: "text-amber-700 dark:text-amber-300",
		border: "border-amber-300 dark:border-amber-500/40",
		glow: "shadow-amber-500/20",
	},
	output: {
		bg: "bg-orange-500/10 dark:bg-orange-500/20",
		text: "text-orange-700 dark:text-orange-300",
		border: "border-orange-300 dark:border-orange-500/40",
		glow: "shadow-orange-500/20",
	},
};

const PHASE_ACTIVE_COLORS: Record<string, string> = {
	intent: "from-purple-500 to-pink-500",
	planning: "from-blue-500 to-cyan-500",
	execution: "from-emerald-500 to-teal-500",
	validation: "from-amber-500 to-orange-500",
	output: "from-orange-500 to-red-500",
};

export function AgentPipeline() {
	const t = useTranslations("homepage");
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.2 });
	const [activeStep, setActiveStep] = useState(-1);
	const hasAnimated = useRef(false);

	useEffect(() => {
		if (!isInView || hasAnimated.current) return;
		hasAnimated.current = true;

		let step = 0;
		const interval = setInterval(() => {
			if (step < NODES.length) {
				setActiveStep(step);
				step++;
			} else {
				clearInterval(interval);
			}
		}, 400);

		return () => clearInterval(interval);
	}, [isInView]);

	return (
		<section
			ref={ref}
			className="relative py-20 md:py-28 overflow-hidden border-t border-neutral-100 dark:border-neutral-800/50"
		>
			{/* Background */}
			<div className="absolute inset-0 -z-10">
				<div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-[radial-gradient(circle,rgba(168,85,247,0.06),transparent_60%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.12),transparent_60%)]" />
			</div>

			<div className="mx-auto max-w-7xl px-6">
				<motion.div
					className="text-center mb-16"
					initial={{ opacity: 0, y: 20 }}
					animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
					transition={{ duration: 0.6 }}
				>
					<span className="text-sm font-semibold text-purple-600 dark:text-purple-400 uppercase tracking-wider">
						{t("pipeline_badge")}
					</span>
					<h2 className="mt-2 text-3xl md:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white">
						{t("pipeline_title")}
					</h2>
					<p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400 max-w-2xl mx-auto">
						{t("pipeline_subtitle")}
					</p>
				</motion.div>

				{/* Pipeline visualization */}
				<div className="max-w-5xl mx-auto">
					{/* Phase groups */}
					<div className="space-y-4">
						{(["intent", "planning", "execution", "validation", "output"] as const).map(
							(phase) => {
								const phaseNodes = NODES.filter((n) => n.phase === phase);
								const phaseColors = PHASE_COLORS[phase];
								const isPhaseActive = phaseNodes.some(
									(_, i) =>
										NODES.indexOf(phaseNodes[i]) <= activeStep
								);

								return (
									<motion.div
										key={phase}
										initial={{ opacity: 0, x: -20 }}
										animate={
											isInView
												? { opacity: 1, x: 0 }
												: { opacity: 0, x: -20 }
										}
										transition={{
											duration: 0.4,
											delay:
												(["intent", "planning", "execution", "validation", "output"].indexOf(phase)) * 0.1,
										}}
										className={cn(
											"rounded-xl border p-4 md:p-5 transition-all duration-500",
											isPhaseActive
												? `${phaseColors.border} ${phaseColors.bg}`
												: "border-neutral-200/50 dark:border-neutral-800/50 bg-neutral-50/50 dark:bg-neutral-900/30"
										)}
									>
										{/* Phase header */}
										<div className="flex items-center gap-2 mb-3">
											<span
												className={cn(
													"text-[10px] font-bold uppercase tracking-widest transition-colors duration-300",
													isPhaseActive
														? phaseColors.text
														: "text-neutral-400 dark:text-neutral-600"
												)}
											>
												{t(`phase_${phase}`)}
											</span>
											<div
												className={cn(
													"flex-1 h-px transition-colors duration-300",
													isPhaseActive
														? phaseColors.border.replace("border-", "bg-")
														: "bg-neutral-200 dark:bg-neutral-800"
												)}
											/>
										</div>

										{/* Nodes in this phase */}
										<div className="flex flex-wrap gap-2 md:gap-3">
											{phaseNodes.map((node) => {
												const globalIdx = NODES.indexOf(node);
												const isActive = globalIdx === activeStep;
												const isPast = globalIdx < activeStep;

												return (
													<motion.div
														key={node.id}
														animate={{
															scale: isActive ? 1.05 : 1,
														}}
														transition={{ duration: 0.3 }}
														className="relative group"
													>
														<div
															className={cn(
																"relative px-4 py-2.5 rounded-lg border text-left transition-all duration-300 cursor-default",
																node.type === "decision" &&
																	"rounded-xl",
																node.type === "hitl" &&
																	"rounded-full",
																node.type === "terminal" &&
																	"rounded-2xl",
																isActive
																	? `bg-gradient-to-r ${PHASE_ACTIVE_COLORS[node.phase]} border-transparent shadow-lg ${phaseColors.glow} text-white`
																	: isPast
																		? `bg-white/60 dark:bg-neutral-800/60 ${phaseColors.border}`
																		: "bg-white/30 dark:bg-neutral-900/30 border-neutral-200/40 dark:border-neutral-800/40 opacity-50"
															)}
														>
															{/* Shine effect on active */}
															{isActive && (
																<motion.div
																	className="absolute inset-0 rounded-lg bg-gradient-to-r from-transparent via-white/20 to-transparent"
																	animate={{ x: ["-100%", "200%"] }}
																	transition={{
																		duration: 1.5,
																		repeat: Infinity,
																		ease: "linear",
																	}}
																/>
															)}
															<div className="relative z-10">
																<div
																	className={cn(
																		"text-sm font-semibold",
																		isActive
																			? "text-white"
																			: isPast
																				? "text-neutral-800 dark:text-neutral-200"
																				: "text-neutral-500 dark:text-neutral-500"
																	)}
																>
																	{t(node.labelKey)}
																</div>
															</div>

															{/* Tooltip */}
															<div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 rounded-lg bg-neutral-900 dark:bg-neutral-800 text-white text-xs shadow-xl border border-neutral-700 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none">
																{t(node.descKey)}
																<div className="absolute left-1/2 -translate-x-1/2 top-full w-2 h-2 rotate-45 bg-neutral-900 dark:bg-neutral-800" />
															</div>
														</div>

														{/* Connection dot */}
														{globalIdx < NODES.length - 1 &&
															NODES[globalIdx + 1]?.phase === node.phase && (
																<div
																	className={cn(
																		"hidden md:block absolute top-1/2 -right-2 w-1 h-1 rounded-full transition-colors duration-300",
																		isPast || isActive
																			? phaseColors.text.replace("text-", "bg-")
																			: "bg-neutral-300 dark:bg-neutral-700"
																	)}
																	style={{ transform: "translateY(-50%)" }}
																/>
															)}
													</motion.div>
												);
											})}
										</div>
									</motion.div>
								);
							}
						)}
					</div>

					{/* Routing explanation */}
					<motion.div
						className="mt-8 p-5 rounded-xl border border-amber-200/50 dark:border-amber-800/30 bg-amber-50/50 dark:bg-amber-950/20"
						initial={{ opacity: 0, y: 10 }}
						animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
						transition={{ duration: 0.5, delay: 0.8 }}
					>
						<div className="flex items-start gap-3">
							<div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center flex-shrink-0 text-white text-xs font-bold">
								?
							</div>
							<div>
								<h4 className="text-sm font-semibold text-neutral-800 dark:text-white mb-1">
									{t("routing_title")}
								</h4>
								<div className="text-xs text-neutral-600 dark:text-neutral-400 space-y-0.5">
									<div>
										<span className="font-semibold text-emerald-600 dark:text-emerald-400">
											ok
										</span>{" "}
										{t("routing_ok")}
									</div>
									<div>
										<span className="font-semibold text-amber-600 dark:text-amber-400">
											needs_more
										</span>{" "}
										{t("routing_needs_more")}
									</div>
									<div>
										<span className="font-semibold text-red-600 dark:text-red-400">
											replan
										</span>{" "}
										{t("routing_replan")}
									</div>
								</div>
							</div>
						</div>
					</motion.div>
				</div>
			</div>
		</section>
	);
}
