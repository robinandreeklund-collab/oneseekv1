"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, Zap } from "lucide-react";

export function HeroMockup2AnimatedGradient() {
	const t = useTranslations("homepage");

	return (
		<section className="relative min-h-screen w-full overflow-hidden bg-black">
			{/* Animated Gradient Background */}
			<div className="absolute inset-0">
				<div className="absolute inset-0 bg-gradient-to-br from-blue-600 via-purple-600 to-pink-600 animate-gradient-xy" />
				<div className="absolute inset-0 bg-gradient-to-tr from-cyan-500 via-blue-500 to-purple-500 opacity-50 animate-gradient-xy animation-delay-2000" />
				<div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.1),transparent_50%)]" />
			</div>

			{/* Grid Overlay */}
			<div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:50px_50px]" />

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-6xl w-full text-center">
					{/* Animated Badge */}
					<div className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 mb-8 animate-pulse-slow">
						<Zap className="w-5 h-5 text-yellow-400" />
						<span className="text-sm font-bold text-white">
							Powered by LangGraph
						</span>
					</div>

					{/* Main Heading with Gradient Text */}
					<h1 className="text-6xl md:text-8xl lg:text-9xl font-black mb-8 leading-none">
						<span className="block bg-gradient-to-r from-white via-blue-100 to-purple-100 bg-clip-text text-transparent animate-gradient-x">
							OneSeek
						</span>
						<span className="block text-4xl md:text-6xl lg:text-7xl mt-4 bg-gradient-to-r from-yellow-200 via-pink-200 to-purple-200 bg-clip-text text-transparent">
							AI-sökning från framtiden
						</span>
					</h1>

					{/* Subtitle */}
					<p className="text-xl md:text-2xl text-white/80 mb-12 max-w-3xl mx-auto leading-relaxed">
						Jämför 100+ AI-modeller side-by-side. Realtidsdata från Sverige. Full transparens med LangGraph.
					</p>

					{/* CTA Buttons */}
					<div className="flex flex-col sm:flex-row gap-6 justify-center items-center mb-16">
						<Link
							href="/dashboard/public/new-chat"
							className="group relative px-10 py-5 bg-white text-black font-black text-xl rounded-full overflow-hidden shadow-2xl hover:shadow-white/50 transition-all duration-300 hover:scale-110"
						>
							<span className="relative z-10 flex items-center gap-3">
								Starta nu
								<ArrowRight className="w-6 h-6 group-hover:translate-x-2 transition-transform" />
							</span>
						</Link>
						<Link
							href="/contact"
							className="px-10 py-5 bg-white/10 backdrop-blur-sm border-2 border-white/30 text-white font-bold text-xl rounded-full hover:bg-white/20 transition-all duration-300 hover:scale-110"
						>
							Demo
						</Link>
					</div>

					{/* Feature Pills */}
					<div className="flex flex-wrap justify-center gap-4">
						{[
							"100+ AI-modeller",
							"Svenska API:er",
							"Debattläge",
							"Full transparens",
							"Realtidsdata"
						].map((feature, index) => (
							<div
								key={index}
								className="px-6 py-3 bg-white/10 backdrop-blur-sm border border-white/20 rounded-full text-white font-semibold hover:bg-white/20 transition-all duration-300 hover:scale-105"
							>
								{feature}
							</div>
						))}
					</div>
				</div>
			</div>

			<style jsx>{`
				@keyframes gradient-xy {
					0%, 100% { background-position: 0% 0%; }
					25% { background-position: 100% 0%; }
					50% { background-position: 100% 100%; }
					75% { background-position: 0% 100%; }
				}
				@keyframes gradient-x {
					0%, 100% { background-position: 0% 50%; }
					50% { background-position: 100% 50%; }
				}
				@keyframes pulse-slow {
					0%, 100% { opacity: 1; }
					50% { opacity: 0.7; }
				}
				.animate-gradient-xy {
					background-size: 400% 400%;
					animation: gradient-xy 15s ease infinite;
				}
				.animate-gradient-x {
					background-size: 200% auto;
					animation: gradient-x 3s linear infinite;
				}
				.animate-pulse-slow {
					animation: pulse-slow 3s ease-in-out infinite;
				}
				.animation-delay-2000 {
					animation-delay: 2s;
				}
			`}</style>
		</section>
	);
}
