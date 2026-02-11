"use client";

import { useTranslations } from "next-intl";
import { ArrowRight, Database, Network, Search, Zap } from "lucide-react";

export function AgentFlow() {
	const t = useTranslations("homepage");

	return (
		<section className="w-full py-24 md:py-32 bg-white dark:bg-neutral-950">
			<div className="mx-auto max-w-7xl px-4 md:px-8">
				{/* Section Header */}
				<div className="text-center mb-16">
					<h2 className="text-4xl md:text-5xl lg:text-6xl font-bold text-black dark:text-white mb-4">
						{t("agent_flow_title")}
					</h2>
					<p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 max-w-3xl mx-auto">
						{t("agent_flow_subtitle")}
					</p>
				</div>

				{/* Flow Diagram */}
				<div className="relative">
					{/* Desktop Flow - Horizontal */}
					<div className="hidden md:flex flex-col gap-8">
						{/* Row 1: Query -> Dispatcher */}
						<div className="flex items-center justify-center gap-6">
							<FlowNode
								icon={<Search className="w-5 h-5" />}
								title={t("agent_flow_query")}
								description={t("agent_flow_query_desc")}
								color="blue"
							/>
							<ArrowRight className="w-6 h-6 text-gray-400 flex-shrink-0" />
							<FlowNode
								icon={<Zap className="w-5 h-5" />}
								title={t("agent_flow_dispatcher")}
								description={t("agent_flow_dispatcher_desc")}
								color="purple"
								large
							/>
						</div>

						{/* Row 2: Dispatcher branches */}
						<div className="grid grid-cols-4 gap-4">
							<FlowBranch
								icon={<Network className="w-5 h-5" />}
								title={t("agent_flow_compare")}
								items={[
									"ChatGPT",
									"Claude", 
									"Gemini",
									"DeepSeek",
									"Perplexity",
									"Qwen",
									"Oneseek"
								]}
								color="blue"
							/>
							<FlowBranch
								icon={<Search className="w-5 h-5" />}
								title={t("agent_flow_knowledge")}
								items={[
									t("agent_flow_tavily"),
									t("agent_flow_sweden_bias")
								]}
								color="green"
							/>
							<FlowBranch
								icon={<Database className="w-5 h-5" />}
								title={t("agent_flow_statistics")}
								items={[
									"SCB",
									"Bolagsverket",
									"SMHI",
									"Trafiklab"
								]}
								color="orange"
							/>
							<FlowBranch
								icon={<Database className="w-5 h-5" />}
								title={t("agent_flow_data")}
								items={[
									"Libris",
									"Arbetsförmedlingen"
								]}
								color="pink"
							/>
						</div>

						{/* Row 3: Synthesis */}
						<div className="flex items-center justify-center mt-4">
							<FlowNode
								icon={<Zap className="w-5 h-5" />}
								title={t("agent_flow_synthesis")}
								description={t("agent_flow_synthesis_desc")}
								color="purple"
								large
							/>
						</div>
					</div>

					{/* Mobile Flow - Vertical */}
					<div className="md:hidden flex flex-col gap-6">
						<FlowNode
							icon={<Search className="w-5 h-5" />}
							title={t("agent_flow_query")}
							description={t("agent_flow_query_desc")}
							color="blue"
						/>
						<div className="flex justify-center">
							<ArrowRight className="w-6 h-6 text-gray-400 rotate-90" />
						</div>
						<FlowNode
							icon={<Zap className="w-5 h-5" />}
							title={t("agent_flow_dispatcher")}
							description={t("agent_flow_dispatcher_desc")}
							color="purple"
						/>
						<div className="flex justify-center">
							<ArrowRight className="w-6 h-6 text-gray-400 rotate-90" />
						</div>
						<div className="space-y-4">
							<FlowBranch
								icon={<Network className="w-5 h-5" />}
								title={t("agent_flow_compare")}
								items={["ChatGPT", "Claude", "Gemini", "DeepSeek", "Perplexity", "Qwen", "Oneseek"]}
								color="blue"
							/>
							<FlowBranch
								icon={<Search className="w-5 h-5" />}
								title={t("agent_flow_knowledge")}
								items={[t("agent_flow_tavily"), t("agent_flow_sweden_bias")]}
								color="green"
							/>
							<FlowBranch
								icon={<Database className="w-5 h-5" />}
								title={t("agent_flow_statistics")}
								items={["SCB", "Bolagsverket", "SMHI", "Trafiklab"]}
								color="orange"
							/>
							<FlowBranch
								icon={<Database className="w-5 h-5" />}
								title={t("agent_flow_data")}
								items={["Libris", "Arbetsförmedlingen"]}
								color="pink"
							/>
						</div>
						<div className="flex justify-center">
							<ArrowRight className="w-6 h-6 text-gray-400 rotate-90" />
						</div>
						<FlowNode
							icon={<Zap className="w-5 h-5" />}
							title={t("agent_flow_synthesis")}
							description={t("agent_flow_synthesis_desc")}
							color="purple"
						/>
					</div>
				</div>
			</div>
		</section>
	);
}

interface FlowNodeProps {
	icon: React.ReactNode;
	title: string;
	description?: string;
	color: "blue" | "purple" | "green" | "orange" | "pink";
	large?: boolean;
}

function FlowNode({ icon, title, description, color, large }: FlowNodeProps) {
	const colorClasses = {
		blue: "bg-blue-50 border-blue-200 dark:bg-blue-950/30 dark:border-blue-800",
		purple: "bg-purple-50 border-purple-200 dark:bg-purple-950/30 dark:border-purple-800",
		green: "bg-green-50 border-green-200 dark:bg-green-950/30 dark:border-green-800",
		orange: "bg-orange-50 border-orange-200 dark:bg-orange-950/30 dark:border-orange-800",
		pink: "bg-pink-50 border-pink-200 dark:bg-pink-950/30 dark:border-pink-800"
	};

	const iconColorClasses = {
		blue: "text-blue-600 dark:text-blue-400",
		purple: "text-purple-600 dark:text-purple-400",
		green: "text-green-600 dark:text-green-400",
		orange: "text-orange-600 dark:text-orange-400",
		pink: "text-pink-600 dark:text-pink-400"
	};

	return (
		<div
			className={`
				${colorClasses[color]}
				${large ? "px-8 py-6 min-w-[280px]" : "px-6 py-4 min-w-[200px]"}
				border-2 rounded-xl
				transition-all duration-200
				hover:shadow-lg hover:scale-105
			`}
		>
			<div className="flex items-center gap-3 mb-2">
				<div className={iconColorClasses[color]}>{icon}</div>
				<h3 className="font-semibold text-gray-900 dark:text-white">{title}</h3>
			</div>
			{description && (
				<p className="text-sm text-gray-600 dark:text-gray-400">{description}</p>
			)}
		</div>
	);
}

interface FlowBranchProps {
	icon: React.ReactNode;
	title: string;
	items: string[];
	color: "blue" | "purple" | "green" | "orange" | "pink";
}

function FlowBranch({ icon, title, items, color }: FlowBranchProps) {
	const colorClasses = {
		blue: "bg-blue-50 border-blue-200 dark:bg-blue-950/30 dark:border-blue-800",
		purple: "bg-purple-50 border-purple-200 dark:bg-purple-950/30 dark:border-purple-800",
		green: "bg-green-50 border-green-200 dark:bg-green-950/30 dark:border-green-800",
		orange: "bg-orange-50 border-orange-200 dark:bg-orange-950/30 dark:border-orange-800",
		pink: "bg-pink-50 border-pink-200 dark:bg-pink-950/30 dark:border-pink-800"
	};

	const iconColorClasses = {
		blue: "text-blue-600 dark:text-blue-400",
		purple: "text-purple-600 dark:text-purple-400",
		green: "text-green-600 dark:text-green-400",
		orange: "text-orange-600 dark:text-orange-400",
		pink: "text-pink-600 dark:text-pink-400"
	};

	return (
		<div
			className={`
				${colorClasses[color]}
				border-2 rounded-xl p-4
				transition-all duration-200
				hover:shadow-lg
			`}
		>
			<div className="flex items-center gap-2 mb-3">
				<div className={iconColorClasses[color]}>{icon}</div>
				<h4 className="font-semibold text-sm text-gray-900 dark:text-white">{title}</h4>
			</div>
			<ul className="space-y-1.5">
				{items.map((item, index) => (
					<li key={index} className="text-xs text-gray-600 dark:text-gray-400 flex items-center gap-1.5">
						<span className="w-1 h-1 rounded-full bg-gray-400 dark:bg-gray-600 flex-shrink-0" />
						{item}
					</li>
				))}
			</ul>
		</div>
	);
}
