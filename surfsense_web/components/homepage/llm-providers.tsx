"use client";

import { motion, useInView } from "motion/react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useRef } from "react";
import { cn } from "@/lib/utils";

/* ────────────────────────────────────────────────────────────
   Primary models — the 7 compare-mode models with real logos
   ──────────────────────────────────────────────────────────── */
const PRIMARY_MODELS = [
	{ name: "ChatGPT", logo: "/model-logos/chatgpt.png", accent: "from-emerald-500/20 to-green-500/20", border: "border-emerald-500/30", glow: "group-hover:shadow-emerald-500/20" },
	{ name: "Claude", logo: "/model-logos/claude.png", accent: "from-orange-500/20 to-amber-500/20", border: "border-orange-500/30", glow: "group-hover:shadow-orange-500/20" },
	{ name: "Gemini", logo: "/model-logos/gemini.png", accent: "from-blue-500/20 to-cyan-500/20", border: "border-blue-500/30", glow: "group-hover:shadow-blue-500/20" },
	{ name: "Grok", logo: "/model-logos/grok.png", accent: "from-neutral-500/20 to-neutral-400/20", border: "border-neutral-500/30", glow: "group-hover:shadow-neutral-500/20" },
	{ name: "DeepSeek", logo: "/model-logos/deepseek.png", accent: "from-indigo-500/20 to-blue-500/20", border: "border-indigo-500/30", glow: "group-hover:shadow-indigo-500/20" },
	{ name: "Perplexity", logo: "/model-logos/perplexity.png", accent: "from-cyan-500/20 to-teal-500/20", border: "border-cyan-500/30", glow: "group-hover:shadow-cyan-500/20" },
	{ name: "Qwen", logo: "/model-logos/qwen.png", accent: "from-violet-500/20 to-purple-500/20", border: "border-violet-500/30", glow: "group-hover:shadow-violet-500/20" },
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
				{/* Header */}
				<motion.div
					className="text-center mb-14"
					initial={{ opacity: 0, y: 20 }}
					animate={isInView ? { opacity: 1, y: 0 } : {}}
					transition={{ duration: 0.6 }}
				>
					<h2 className="text-3xl md:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white">
						{t("providers_title")}
					</h2>
					<p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400 max-w-2xl mx-auto">
						{t("providers_subtitle")}
					</p>
				</motion.div>

				{/* Primary models — logo cards */}
				<motion.div
					className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-4 max-w-5xl mx-auto mb-12"
					initial={{ opacity: 0 }}
					animate={isInView ? { opacity: 1 } : {}}
					transition={{ duration: 0.5, delay: 0.2 }}
				>
					{PRIMARY_MODELS.map((model, index) => (
						<motion.div
							key={model.name}
							initial={{ opacity: 0, y: 15, scale: 0.9 }}
							animate={isInView ? { opacity: 1, y: 0, scale: 1 } : {}}
							transition={{ delay: 0.15 + index * 0.06, duration: 0.4 }}
							whileHover={{ y: -6, scale: 1.04 }}
							className="group"
						>
							<div
								className={cn(
									"relative flex flex-col items-center gap-3 p-5 rounded-2xl border backdrop-blur-sm",
									"bg-gradient-to-b transition-all duration-300 cursor-default",
									"shadow-sm group-hover:shadow-xl",
									model.accent,
									model.border,
									model.glow,
								)}
							>
								{/* Logo */}
								<div className="relative w-12 h-12 flex items-center justify-center">
									<Image
										src={model.logo}
										alt={model.name}
										width={48}
										height={48}
										className="object-contain rounded-lg"
									/>
								</div>
								{/* Name */}
								<span className="text-sm font-semibold text-neutral-800 dark:text-white">
									{model.name}
								</span>
							</div>
						</motion.div>
					))}
				</motion.div>

				</div>
		</section>
	);
}
