"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Bot, Database, Sparkles, Zap } from "lucide-react";

export function HeroMockup8FloatingIslands() {
	const t = useTranslations("homepage");

	return (
		<section className="relative min-h-screen w-full overflow-hidden bg-gradient-to-b from-sky-100 via-blue-50 to-purple-100 dark:from-sky-950 dark:via-blue-950 dark:to-purple-950">
			{/* Cloud-like background */}
			<div className="absolute inset-0">
				<div className="absolute top-10 left-10 w-96 h-96 bg-white/40 dark:bg-white/10 rounded-full blur-3xl" />
				<div className="absolute top-40 right-20 w-80 h-80 bg-blue-300/30 dark:bg-blue-600/20 rounded-full blur-3xl" />
				<div className="absolute bottom-20 left-1/3 w-72 h-72 bg-purple-300/30 dark:bg-purple-600/20 rounded-full blur-3xl" />
			</div>

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-7xl w-full">
					{/* Main Title Area */}
					<div className="text-center mb-16">
						<div className="inline-flex items-center gap-2 px-5 py-2 rounded-full bg-white/60 dark:bg-white/10 backdrop-blur-sm border border-white/80 dark:border-white/20 mb-8 shadow-lg">
							<Sparkles className="w-4 h-4 text-blue-600 dark:text-blue-400" />
							<span className="text-sm font-bold text-gray-900 dark:text-white">
								Nästa generations AI-plattform
							</span>
						</div>

						<h1 className="text-5xl md:text-7xl lg:text-8xl font-black mb-6 leading-tight">
							<span className="block text-gray-900 dark:text-white mb-2">
								Svavar på
							</span>
							<span className="block bg-gradient-to-r from-blue-600 via-purple-600 to-pink-600 bg-clip-text text-transparent">
								molnens vingar
							</span>
						</h1>

						<p className="text-xl md:text-2xl text-gray-700 dark:text-gray-300 mb-10 max-w-3xl mx-auto">
							En ekosystem av sammankopplade AI-agenter som levererar insikter från 100+ modeller
						</p>

						<div className="flex flex-col sm:flex-row gap-4 justify-center">
							<Link
								href="/dashboard/public/new-chat"
								className="px-10 py-5 bg-gradient-to-r from-blue-600 to-purple-600 text-white font-bold text-xl rounded-2xl shadow-xl hover:shadow-2xl hover:scale-105 transition-all duration-300"
							>
								Flyg med oss
							</Link>
							<Link
								href="/contact"
								className="px-10 py-5 bg-white/80 dark:bg-white/10 backdrop-blur-sm border-2 border-white dark:border-white/30 text-gray-900 dark:text-white font-bold text-xl rounded-2xl hover:bg-white dark:hover:bg-white/20 transition-all duration-300 hover:scale-105 shadow-lg"
							>
								Upptäck mer
							</Link>
						</div>
					</div>

					{/* Floating Island Cards */}
					<div className="relative h-96 md:h-[500px]">
						{/* Island 1 - Top Left */}
						<div 
							className="absolute top-0 left-10 lg:left-20 w-64 md:w-80 animate-float"
							style={{ animationDelay: '0s' }}
						>
							<div className="bg-white/80 dark:bg-white/10 backdrop-blur-xl rounded-3xl p-8 shadow-2xl border border-white/50 dark:border-white/20 hover:scale-105 transition-transform duration-500">
								<div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-2xl flex items-center justify-center mb-4 shadow-lg">
									<Bot className="w-8 h-8 text-white" />
								</div>
								<h3 className="text-2xl font-black text-gray-900 dark:text-white mb-2">
									100+ AI-modeller
								</h3>
								<p className="text-sm text-gray-600 dark:text-gray-400">
									Jämför svar från världens främsta AI-system
								</p>
							</div>
						</div>

						{/* Island 2 - Top Right */}
						<div 
							className="absolute top-10 right-10 lg:right-20 w-64 md:w-80 animate-float"
							style={{ animationDelay: '1s' }}
						>
							<div className="bg-white/80 dark:bg-white/10 backdrop-blur-xl rounded-3xl p-8 shadow-2xl border border-white/50 dark:border-white/20 hover:scale-105 transition-transform duration-500">
								<div className="w-16 h-16 bg-gradient-to-br from-purple-500 to-pink-500 rounded-2xl flex items-center justify-center mb-4 shadow-lg">
									<Zap className="w-8 h-8 text-white" />
								</div>
								<h3 className="text-2xl font-black text-gray-900 dark:text-white mb-2">
									AI Debattläge
								</h3>
								<p className="text-sm text-gray-600 dark:text-gray-400">
									Låt modeller debattera för djupare insikter
								</p>
							</div>
						</div>

						{/* Island 3 - Middle Center */}
						<div 
							className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-72 md:w-96 animate-float z-10"
							style={{ animationDelay: '2s' }}
						>
							<div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-3xl p-10 shadow-2xl hover:scale-105 transition-transform duration-500">
								<div className="w-20 h-20 bg-white/20 backdrop-blur-sm rounded-2xl flex items-center justify-center mb-6 mx-auto shadow-lg">
									<Sparkles className="w-10 h-10 text-white" />
								</div>
								<h3 className="text-3xl font-black text-white mb-3 text-center">
									Full Transparens
								</h3>
								<p className="text-white/90 text-center">
									Se hela LangGraph-flödet från fråga till svar
								</p>
							</div>
						</div>

						{/* Island 4 - Bottom Left */}
						<div 
							className="absolute bottom-0 left-1/4 -translate-x-1/2 w-64 md:w-80 animate-float"
							style={{ animationDelay: '1.5s' }}
						>
							<div className="bg-white/80 dark:bg-white/10 backdrop-blur-xl rounded-3xl p-8 shadow-2xl border border-white/50 dark:border-white/20 hover:scale-105 transition-transform duration-500">
								<div className="w-16 h-16 bg-gradient-to-br from-green-500 to-emerald-500 rounded-2xl flex items-center justify-center mb-4 shadow-lg">
									<Database className="w-8 h-8 text-white" />
								</div>
								<h3 className="text-2xl font-black text-gray-900 dark:text-white mb-2">
									Svenska API:er
								</h3>
								<p className="text-sm text-gray-600 dark:text-gray-400">
									Realtidsdata från SCB, SMHI, Trafiklab m.fl.
								</p>
							</div>
						</div>

						{/* Island 5 - Bottom Right */}
						<div 
							className="absolute bottom-10 right-1/4 translate-x-1/2 w-56 md:w-72 animate-float"
							style={{ animationDelay: '0.5s' }}
						>
							<div className="bg-white/80 dark:bg-white/10 backdrop-blur-xl rounded-3xl p-6 shadow-2xl border border-white/50 dark:border-white/20 hover:scale-105 transition-transform duration-500">
								<h3 className="text-xl font-black text-gray-900 dark:text-white mb-2">
									Realtidsdata
								</h3>
								<p className="text-xs text-gray-600 dark:text-gray-400">
									Alltid uppdaterad information från svenska källor
								</p>
							</div>
						</div>
					</div>
				</div>
			</div>

			<style jsx>{`
				@keyframes float {
					0%, 100% { transform: translateY(0px); }
					50% { transform: translateY(-20px); }
				}
				.animate-float {
					animation: float 6s ease-in-out infinite;
				}
			`}</style>
		</section>
	);
}
