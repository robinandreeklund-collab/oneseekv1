"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Sparkles } from "lucide-react";

export function HeroMockup1Glassmorphism() {
	const t = useTranslations("homepage");

	return (
		<section className="relative min-h-screen w-full overflow-hidden bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50 dark:from-purple-950/20 dark:via-blue-950/20 dark:to-pink-950/20">
			{/* Gradient Mesh Background */}
			<div className="absolute inset-0">
				<div className="absolute top-0 left-1/4 w-96 h-96 bg-gradient-to-br from-blue-400/30 to-purple-600/30 rounded-full blur-3xl animate-pulse" />
				<div className="absolute bottom-0 right-1/4 w-96 h-96 bg-gradient-to-br from-pink-400/30 to-orange-600/30 rounded-full blur-3xl animate-pulse delay-1000" />
				<div className="absolute top-1/2 left-1/2 w-96 h-96 bg-gradient-to-br from-cyan-400/20 to-blue-600/20 rounded-full blur-3xl animate-pulse delay-500" />
			</div>

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-6xl w-full">
					{/* Glass Card */}
					<div className="backdrop-blur-2xl bg-white/30 dark:bg-black/30 rounded-3xl border border-white/50 dark:border-white/10 shadow-2xl p-8 md:p-16">
						{/* Badge */}
						<div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-blue-500/20 to-purple-500/20 backdrop-blur-sm border border-white/50 dark:border-white/20 mb-8">
							<Sparkles className="w-4 h-4 text-blue-600 dark:text-blue-400" />
							<span className="text-sm font-semibold bg-gradient-to-r from-blue-600 to-purple-600 dark:from-blue-400 dark:to-purple-400 bg-clip-text text-transparent">
								{t("hero_title") || "AI-plattformen för Sverige"}
							</span>
						</div>

						{/* Main Heading */}
						<h1 className="text-5xl md:text-7xl lg:text-8xl font-black mb-6 leading-tight">
							<span className="bg-gradient-to-r from-gray-900 via-blue-900 to-purple-900 dark:from-white dark:via-blue-200 dark:to-purple-200 bg-clip-text text-transparent">
								Upptäck framtidens
							</span>
							<br />
							<span className="bg-gradient-to-r from-blue-600 via-purple-600 to-pink-600 dark:from-blue-400 dark:via-purple-400 dark:to-pink-400 bg-clip-text text-transparent">
								AI-sökning
							</span>
						</h1>

						{/* Subtitle */}
						<p className="text-xl md:text-2xl text-gray-700 dark:text-gray-300 mb-10 max-w-3xl leading-relaxed">
							{t("hero_subtitle") || "Jämför 100+ AI-modeller, få realtidsdata från svenska API:er, och se hela LangGraph-flödet i realtid"}
						</p>

						{/* CTA Buttons - Glassmorphic */}
						<div className="flex flex-col sm:flex-row gap-4">
							<Link
								href="/dashboard/public/new-chat"
								className="group relative px-8 py-4 bg-gradient-to-r from-blue-600 to-purple-600 text-white font-bold text-lg rounded-2xl overflow-hidden shadow-xl hover:shadow-2xl transition-all duration-300 hover:scale-105"
							>
								<span className="relative z-10">Börja utforska</span>
								<div className="absolute inset-0 bg-gradient-to-r from-purple-600 to-pink-600 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
							</Link>
							<Link
								href="/contact"
								className="px-8 py-4 backdrop-blur-xl bg-white/50 dark:bg-black/50 border-2 border-white/50 dark:border-white/20 text-gray-900 dark:text-white font-bold text-lg rounded-2xl hover:bg-white/70 dark:hover:bg-black/70 transition-all duration-300 hover:scale-105 shadow-lg"
							>
								Kontakta oss
							</Link>
						</div>
					</div>

					{/* Floating Stats Cards */}
					<div className="grid grid-cols-3 gap-4 mt-8">
						{[
							{ label: "AI-modeller", value: "100+" },
							{ label: "Svenska API:er", value: "7" },
							{ label: "Transparens", value: "100%" }
						].map((stat, index) => (
							<div
								key={index}
								className="backdrop-blur-xl bg-white/20 dark:bg-black/20 rounded-2xl border border-white/30 dark:border-white/10 p-6 text-center hover:scale-105 transition-transform duration-300"
							>
								<div className="text-3xl md:text-4xl font-black bg-gradient-to-r from-blue-600 to-purple-600 dark:from-blue-400 dark:to-purple-400 bg-clip-text text-transparent mb-2">
									{stat.value}
								</div>
								<div className="text-sm font-semibold text-gray-700 dark:text-gray-300">
									{stat.label}
								</div>
							</div>
						))}
					</div>
				</div>
			</div>
		</section>
	);
}
