"use client";

import { useTranslations } from "next-intl";
import Image from "next/image";

export function ModelComparison() {
	const t = useTranslations("homepage");

	const models = [
		{ name: "ChatGPT", logo: "/model-logos/chatgpt.png" },
		{ name: "Claude", logo: "/model-logos/claude.png" },
		{ name: "Gemini", logo: "/model-logos/gemini.png" },
		{ name: "DeepSeek", logo: "/model-logos/deepseek.png" },
		{ name: "Perplexity", logo: "/model-logos/perplexity.png" },
		{ name: "Qwen", logo: "/model-logos/qwen.png" },
		{ name: "Grok", logo: "/model-logos/grok.png" }
	];

	return (
		<section className="w-full py-24 md:py-32 bg-white dark:bg-neutral-950">
			<div className="mx-auto max-w-7xl px-4 md:px-8">
				{/* Section Header */}
				<div className="text-center mb-16">
					<h2 className="text-4xl md:text-5xl lg:text-6xl font-bold text-black dark:text-white mb-4">
						{t("model_comparison_title")}
					</h2>
					<p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 max-w-3xl mx-auto">
						{t("model_comparison_subtitle")}
					</p>
				</div>

				{/* Model Logo Bar */}
				<div className="flex flex-wrap items-center justify-center gap-8 md:gap-12">
					{models.map((model) => (
						<div
							key={model.name}
							className="group flex flex-col items-center gap-3 transition-transform duration-300 hover:scale-110"
						>
							<div className="relative w-16 h-16 md:w-20 md:h-20 rounded-xl bg-white dark:bg-neutral-800 p-2 shadow-lg group-hover:shadow-xl transition-shadow duration-300 border border-gray-200 dark:border-neutral-700">
								<Image
									src={model.logo}
									alt={model.name}
									width={80}
									height={80}
									className="w-full h-full object-contain"
								/>
							</div>
							<span className="text-xs md:text-sm font-medium text-gray-600 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
								{model.name}
							</span>
						</div>
					))}
				</div>

				{/* Additional info */}
				<div className="mt-12 text-center">
					<p className="text-base md:text-lg text-gray-500 dark:text-gray-500">
						{t("model_comparison_plus")}
					</p>
				</div>
			</div>
		</section>
	);
}
