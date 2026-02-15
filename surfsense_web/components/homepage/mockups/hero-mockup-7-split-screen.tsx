"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, Zap, Brain, Network } from "lucide-react";

export function HeroMockup7SplitScreen() {
	const t = useTranslations("homepage");

	return (
		<section className="relative min-h-screen w-full overflow-hidden">
			<div className="grid lg:grid-cols-2 min-h-screen">
				{/* Left Side - Dark with Gradient */}
				<div className="relative bg-gradient-to-br from-indigo-950 via-purple-950 to-pink-950 flex items-center justify-center p-8 md:p-16">
					{/* Animated Background Pattern */}
					<div className="absolute inset-0 opacity-10">
						<div className="absolute inset-0" style={{
							backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'1\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")',
						}} />
					</div>

					<div className="relative z-10 max-w-2xl">
						<div className="inline-flex items-center gap-2 px-5 py-2 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 mb-8">
							<Brain className="w-4 h-4 text-purple-400" />
							<span className="text-sm font-bold text-white">AI-Powered Platform</span>
						</div>

						<h1 className="text-5xl md:text-6xl lg:text-7xl font-black text-white mb-6 leading-tight">
							Jämför.
							<br />
							Debattera.
							<br />
							<span className="text-purple-400">Förstå.</span>
						</h1>

						<p className="text-xl text-purple-200 mb-8 leading-relaxed">
							OneSeek kombinerar 100+ AI-modeller med svenska datakällor för att ge dig de mest insiktsfulla svaren
						</p>

						<div className="flex flex-col sm:flex-row gap-4">
							<Link
								href="/dashboard/public/new-chat"
								className="group inline-flex items-center justify-center gap-3 px-8 py-4 bg-white text-indigo-900 font-bold text-lg rounded-xl hover:bg-purple-100 transition-all duration-300 hover:scale-105 shadow-xl"
							>
								Kom igång
								<ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
							</Link>
							<Link
								href="/contact"
								className="inline-flex items-center justify-center px-8 py-4 bg-white/10 backdrop-blur-sm border-2 border-white/30 text-white font-bold text-lg rounded-xl hover:bg-white/20 transition-all duration-300 hover:scale-105"
							>
								Läs mer
							</Link>
						</div>

						{/* Stats */}
						<div className="mt-12 grid grid-cols-3 gap-6">
							{[
								{ value: "100+", label: "Modeller" },
								{ value: "7", label: "API:er" },
								{ value: "∞", label: "Insikter" }
							].map((stat, index) => (
								<div key={index}>
									<div className="text-3xl md:text-4xl font-black text-white mb-1">
										{stat.value}
									</div>
									<div className="text-sm text-purple-300">
										{stat.label}
									</div>
								</div>
							))}
						</div>
					</div>
				</div>

				{/* Right Side - Light with Visual Elements */}
				<div className="relative bg-gradient-to-br from-white via-purple-50 to-pink-50 dark:from-gray-100 dark:via-purple-100 dark:to-pink-100 flex items-center justify-center p-8 md:p-16">
					{/* Decorative Elements */}
					<div className="absolute inset-0 overflow-hidden">
						<div className="absolute top-1/4 right-1/4 w-64 h-64 bg-gradient-to-br from-indigo-300/30 to-purple-300/30 rounded-full blur-3xl" />
						<div className="absolute bottom-1/4 left-1/4 w-64 h-64 bg-gradient-to-br from-purple-300/30 to-pink-300/30 rounded-full blur-3xl" />
					</div>

					{/* Feature Cards */}
					<div className="relative z-10 max-w-xl space-y-6">
						{[
							{
								icon: <Zap className="w-8 h-8" />,
								title: "Compare 100+ Models",
								desc: "Se och jämför svar från ChatGPT, Claude, Gemini, DeepSeek och 95+ till",
								color: "from-blue-500 to-cyan-500"
							},
							{
								icon: <Network className="w-8 h-8" />,
								title: "Swedish API Integration",
								desc: "Realtidsdata från SCB, SMHI, Trafiklab, Bolagsverket och fler",
								color: "from-purple-500 to-pink-500"
							},
							{
								icon: <Brain className="w-8 h-8" />,
								title: "AI Debate Mode",
								desc: "Låt AI-modeller debattera i 3 omgångar för djupare insikter",
								color: "from-indigo-500 to-purple-500"
							}
						].map((feature, index) => (
							<div
								key={index}
								className="group relative bg-white dark:bg-white/90 rounded-2xl p-6 shadow-xl hover:shadow-2xl transition-all duration-300 hover:scale-105 hover:-translate-y-1"
							>
								<div className={`inline-flex items-center justify-center w-16 h-16 rounded-xl bg-gradient-to-br ${feature.color} text-white mb-4 group-hover:scale-110 transition-transform`}>
									{feature.icon}
								</div>
								<h3 className="text-xl font-bold text-gray-900 mb-2">
									{feature.title}
								</h3>
								<p className="text-gray-600 leading-relaxed">
									{feature.desc}
								</p>
							</div>
						))}
					</div>
				</div>
			</div>
		</section>
	);
}
