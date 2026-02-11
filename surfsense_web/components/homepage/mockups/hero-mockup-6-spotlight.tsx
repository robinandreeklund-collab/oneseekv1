"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

export function HeroMockup6Spotlight() {
	const t = useTranslations("homepage");
	const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });

	useEffect(() => {
		const handleMouseMove = (e: MouseEvent) => {
			setMousePosition({ x: e.clientX, y: e.clientY });
		};

		window.addEventListener("mousemove", handleMouseMove);
		return () => window.removeEventListener("mousemove", handleMouseMove);
	}, []);

	return (
		<section className="relative min-h-screen w-full overflow-hidden bg-black">
			{/* Spotlight Effect */}
			<div 
				className="absolute inset-0 pointer-events-none transition-opacity duration-300"
				style={{
					background: `radial-gradient(circle 600px at ${mousePosition.x}px ${mousePosition.y}px, rgba(99, 102, 241, 0.15), transparent 80%)`
				}}
			/>
			<div 
				className="absolute inset-0 pointer-events-none"
				style={{
					background: `radial-gradient(circle 400px at ${mousePosition.x}px ${mousePosition.y}px, rgba(168, 85, 247, 0.1), transparent 80%)`
				}}
			/>

			{/* Dot Grid */}
			<div className="absolute inset-0 opacity-20" style={{
				backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.3) 1px, transparent 1px)',
				backgroundSize: '50px 50px'
			}} />

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-6xl w-full">
					{/* Top Badge */}
					<div className="flex justify-center mb-12">
						<div className="inline-flex items-center gap-3 px-6 py-3 rounded-full bg-white/5 backdrop-blur-sm border border-white/10">
							<Sparkles className="w-5 h-5 text-indigo-400" />
							<span className="text-sm font-bold text-white/90">
								Spotlight on Intelligence
							</span>
						</div>
					</div>

					{/* Main Content Card */}
					<div 
						className="relative mx-auto max-w-4xl p-12 md:p-16 rounded-3xl border border-white/10 transition-all duration-500"
						style={{
							background: 'rgba(0, 0, 0, 0.4)',
							backdropFilter: 'blur(20px)',
							boxShadow: `0 0 100px rgba(99, 102, 241, ${Math.abs(Math.sin(Date.now() / 1000)) * 0.3})`
						}}
					>
						{/* Heading */}
						<h1 className="text-5xl md:text-7xl lg:text-8xl font-black mb-6 text-center leading-tight">
							<span className="block text-white mb-2">
								Belyser vägen till
							</span>
							<span className="block bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
								AI-transparens
							</span>
						</h1>

						{/* Subtitle */}
						<p className="text-xl md:text-2xl text-gray-300 mb-10 text-center leading-relaxed">
							Se exakt hur OneSeek processerar din fråga genom 100+ AI-modeller och svenska datakällor
						</p>

						{/* CTA Buttons */}
						<div className="flex flex-col sm:flex-row gap-4 justify-center">
							<Link
								href="/dashboard/public/new-chat"
								className="group relative px-10 py-5 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-bold text-lg rounded-xl overflow-hidden transition-all duration-300 hover:scale-105"
								style={{
									boxShadow: '0 10px 40px rgba(99, 102, 241, 0.4)'
								}}
							>
								<span className="relative z-10">Utforska nu</span>
								<div className="absolute inset-0 bg-gradient-to-r from-purple-600 to-pink-600 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
							</Link>
							<Link
								href="/contact"
								className="px-10 py-5 bg-white/5 backdrop-blur-sm border-2 border-white/20 text-white font-bold text-lg rounded-xl hover:bg-white/10 hover:border-white/30 transition-all duration-300 hover:scale-105"
							>
								Boka demo
							</Link>
						</div>
					</div>

					{/* Bottom Features */}
					<div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6">
						{[
							{ 
								title: "Multi-Model Compare",
								desc: "Jämför svar från 100+ AI-modeller side-by-side",
								glow: "indigo"
							},
							{ 
								title: "Swedish Data Sources",
								desc: "Realtidsdata från SCB, SMHI, Trafiklab och fler",
								glow: "purple"
							},
							{ 
								title: "Full Transparency",
								desc: "Se hela LangGraph-flödet från fråga till svar",
								glow: "pink"
							}
						].map((feature, index) => (
							<div
								key={index}
								className="group relative p-6 rounded-2xl bg-white/5 backdrop-blur-sm border border-white/10 hover:border-white/30 transition-all duration-300 hover:scale-105"
								style={{
									boxShadow: `0 0 30px rgba(${
										feature.glow === "indigo" ? "99, 102, 241" :
										feature.glow === "purple" ? "168, 85, 247" :
										"236, 72, 153"
									}, 0.2)`
								}}
							>
								<h3 className="text-xl font-bold text-white mb-2">
									{feature.title}
								</h3>
								<p className="text-sm text-gray-400">
									{feature.desc}
								</p>
								<div 
									className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 rounded-2xl"
									style={{
										background: `radial-gradient(circle at 50% 50%, rgba(${
											feature.glow === "indigo" ? "99, 102, 241" :
											feature.glow === "purple" ? "168, 85, 247" :
											"236, 72, 153"
										}, 0.1), transparent 70%)`
									}}
								/>
							</div>
						))}
					</div>
				</div>
			</div>
		</section>
	);
}
