"use client";

import { motion, useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { useRef } from "react";
import { cn } from "@/lib/utils";

const PROVIDERS = [
	{ name: "OpenAI", color: "from-green-500/15 to-emerald-500/15 dark:from-green-500/25 dark:to-emerald-500/25" },
	{ name: "Anthropic", color: "from-orange-500/15 to-amber-500/15 dark:from-orange-500/25 dark:to-amber-500/25" },
	{ name: "Google", color: "from-blue-500/15 to-cyan-500/15 dark:from-blue-500/25 dark:to-cyan-500/25" },
	{ name: "xAI", color: "from-purple-500/15 to-pink-500/15 dark:from-purple-500/25 dark:to-pink-500/25" },
	{ name: "DeepSeek", color: "from-indigo-500/15 to-blue-500/15 dark:from-indigo-500/25 dark:to-blue-500/25" },
	{ name: "Perplexity", color: "from-cyan-500/15 to-teal-500/15 dark:from-cyan-500/25 dark:to-teal-500/25" },
	{ name: "Qwen", color: "from-yellow-500/15 to-orange-500/15 dark:from-yellow-500/25 dark:to-orange-500/25" },
	{ name: "OpenRouter", color: "from-pink-500/15 to-rose-500/15 dark:from-pink-500/25 dark:to-rose-500/25" },
	{ name: "Groq", color: "from-red-500/15 to-orange-500/15 dark:from-red-500/25 dark:to-orange-500/25" },
	{ name: "Together", color: "from-violet-500/15 to-purple-500/15 dark:from-violet-500/25 dark:to-purple-500/25" },
	{ name: "Azure", color: "from-blue-500/15 to-indigo-500/15 dark:from-blue-500/25 dark:to-indigo-500/25" },
	{ name: "Mistral", color: "from-orange-500/15 to-red-500/15 dark:from-orange-500/25 dark:to-red-500/25" },
	{ name: "Cohere", color: "from-teal-500/15 to-green-500/15 dark:from-teal-500/25 dark:to-green-500/25" },
	{ name: "Fireworks", color: "from-amber-500/15 to-yellow-500/15 dark:from-amber-500/25 dark:to-yellow-500/25" },
	{ name: "Cerebras", color: "from-rose-500/15 to-pink-500/15 dark:from-rose-500/25 dark:to-pink-500/25" },
	{ name: "DeepInfra", color: "from-emerald-500/15 to-teal-500/15 dark:from-emerald-500/25 dark:to-teal-500/25" },
	{ name: "Replicate", color: "from-indigo-500/15 to-violet-500/15 dark:from-indigo-500/25 dark:to-violet-500/25" },
	{ name: "Ollama", color: "from-neutral-500/15 to-neutral-500/15 dark:from-neutral-500/25 dark:to-neutral-400/25" },
];

export function LLMProviders() {
	const t = useTranslations("homepage");
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.2 });

	return (
		<section
			ref={ref}
			className="relative py-20 md:py-28 border-t border-neutral-100 dark:border-neutral-800/50 overflow-hidden"
		>
			{/* Background */}
			<div className="absolute inset-0 -z-10">
				<div className="absolute top-0 left-1/3 w-96 h-96 bg-[radial-gradient(circle,rgba(59,130,246,0.05),transparent_60%)] dark:bg-[radial-gradient(circle,rgba(59,130,246,0.1),transparent_60%)]" />
				<div className="absolute bottom-0 right-1/4 w-96 h-96 bg-[radial-gradient(circle,rgba(168,85,247,0.05),transparent_60%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.1),transparent_60%)]" />
			</div>

			<div className="mx-auto max-w-7xl px-6">
				<motion.div
					className="text-center mb-12"
					initial={{ opacity: 0, y: 20 }}
					animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
					transition={{ duration: 0.6 }}
				>
					<h2 className="text-3xl md:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white">
						{t("providers_title")}
					</h2>
					<p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400">
						{t("providers_subtitle")}
					</p>
				</motion.div>

				<motion.div
					className="flex flex-wrap justify-center gap-3"
					initial={{ opacity: 0 }}
					animate={isInView ? { opacity: 1 } : { opacity: 0 }}
					transition={{ duration: 0.6, delay: 0.2 }}
				>
					{PROVIDERS.map((provider, index) => (
						<motion.div
							key={provider.name}
							initial={{ opacity: 0, scale: 0.8, y: 10 }}
							animate={
								isInView
									? { opacity: 1, scale: 1, y: 0 }
									: { opacity: 0, scale: 0.8, y: 10 }
							}
							transition={{ delay: index * 0.03, duration: 0.3 }}
							whileHover={{ scale: 1.08, y: -3 }}
							className="group relative"
						>
							<div
								className={cn(
									"rounded-full border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br px-5 py-2.5 text-sm font-semibold text-neutral-800 dark:text-white backdrop-blur-sm shadow-sm hover:shadow-md transition-all duration-300 cursor-default",
									provider.color
								)}
							>
								{provider.name}
							</div>
						</motion.div>
					))}
				</motion.div>
			</div>
		</section>
	);
}
