"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Zap, Code2, Sparkles } from "lucide-react";

export function HeroMockup4NeonCyberpunk() {
	const t = useTranslations("homepage");

	return (
		<section className="relative min-h-screen w-full overflow-hidden bg-black">
			{/* Scanlines Effect */}
			<div className="absolute inset-0 pointer-events-none opacity-10">
				<div className="absolute inset-0" style={{
					backgroundImage: 'repeating-linear-gradient(0deg, rgba(0,255,255,0.1) 0px, transparent 2px, transparent 4px)',
					animation: 'scanlines 8s linear infinite'
				}} />
			</div>

			{/* Neon Grid */}
			<div className="absolute inset-0 opacity-20">
				<div className="absolute inset-0" style={{
					backgroundImage: 'linear-gradient(rgba(0,255,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,0,255,0.3) 1px, transparent 1px)',
					backgroundSize: '50px 50px',
					transform: 'perspective(500px) rotateX(60deg)',
					transformOrigin: 'center center'
				}} />
			</div>

			{/* Glowing Orbs */}
			<div className="absolute inset-0">
				<div className="absolute top-1/4 left-1/4 w-64 h-64 bg-cyan-500 rounded-full blur-3xl opacity-30 animate-pulse" />
				<div className="absolute bottom-1/4 right-1/4 w-64 h-64 bg-pink-500 rounded-full blur-3xl opacity-30 animate-pulse animation-delay-1000" />
				<div className="absolute top-1/2 left-1/2 w-96 h-96 bg-purple-500 rounded-full blur-3xl opacity-20 animate-pulse animation-delay-2000" />
			</div>

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-6xl w-full text-center">
					{/* Neon Badge */}
					<div className="inline-flex items-center gap-3 px-6 py-3 rounded-full border-2 border-cyan-500 mb-8" style={{
						boxShadow: '0 0 20px rgba(0,255,255,0.5), inset 0 0 20px rgba(0,255,255,0.1)',
						animation: 'neon-pulse 2s ease-in-out infinite'
					}}>
						<Code2 className="w-5 h-5 text-cyan-400" style={{
							filter: 'drop-shadow(0 0 8px rgba(0,255,255,0.8))'
						}} />
						<span className="text-sm font-black text-cyan-400 uppercase tracking-wider" style={{
							textShadow: '0 0 10px rgba(0,255,255,0.8)'
						}}>
							Neural Network Powered
						</span>
					</div>

					{/* Glitch Effect Heading */}
					<h1 className="text-6xl md:text-8xl lg:text-9xl font-black mb-8 leading-none glitch-text" data-text="ONESEEK">
						<span className="text-transparent" style={{
							WebkitTextStroke: '2px #fff',
							textStroke: '2px #fff'
						}}>ONE</span>
						<span className="text-transparent bg-gradient-to-r from-cyan-400 via-pink-400 to-purple-400 bg-clip-text" style={{
							filter: 'drop-shadow(0 0 20px rgba(0,255,255,0.7))'
						}}>SEEK</span>
					</h1>

					{/* Neon Subtitle */}
					<p className="text-2xl md:text-3xl font-bold mb-4" style={{
						color: '#fff',
						textShadow: '0 0 10px rgba(255,255,255,0.5)'
					}}>
						<span className="text-cyan-400" style={{ textShadow: '0 0 20px rgba(0,255,255,0.8)' }}>
							AI-DRIVEN
						</span>
						{' · '}
						<span className="text-pink-400" style={{ textShadow: '0 0 20px rgba(255,0,255,0.8)' }}>
							REAL-TIME
						</span>
						{' · '}
						<span className="text-purple-400" style={{ textShadow: '0 0 20px rgba(168,85,247,0.8)' }}>
							TRANSPARENT
						</span>
					</p>

					<p className="text-lg md:text-xl text-gray-400 mb-12 max-w-3xl mx-auto">
						100+ AI-modeller · 7 Svenska API:er · Full LangGraph-transparens
					</p>

					{/* Neon CTA Buttons */}
					<div className="flex flex-col sm:flex-row gap-6 justify-center items-center mb-16">
						<Link
							href="/dashboard/public/new-chat"
							className="group relative px-10 py-5 bg-cyan-500 text-black font-black text-xl rounded-lg overflow-hidden transition-all duration-300 hover:scale-110"
							style={{
								boxShadow: '0 0 30px rgba(0,255,255,0.6), 0 0 60px rgba(0,255,255,0.4), inset 0 0 20px rgba(0,255,255,0.2)'
							}}
						>
							<span className="relative z-10 flex items-center gap-3">
								<Zap className="w-6 h-6" />
								STARTA DIREKT
							</span>
						</Link>
						<Link
							href="/contact"
							className="px-10 py-5 bg-transparent border-2 border-pink-500 text-pink-400 font-black text-xl rounded-lg transition-all duration-300 hover:scale-110 hover:bg-pink-500/10"
							style={{
								boxShadow: '0 0 20px rgba(255,0,255,0.5), inset 0 0 20px rgba(255,0,255,0.1)'
							}}
						>
							KONTAKT
						</Link>
					</div>

					{/* Neon Feature Tags */}
					<div className="flex flex-wrap justify-center gap-4">
						{[
							{ label: "MULTI-MODEL", color: "cyan" },
							{ label: "DEBATE MODE", color: "pink" },
							{ label: "SWEDISH DATA", color: "purple" },
							{ label: "TRANSPARENT", color: "green" }
						].map((feature, index) => (
							<div
								key={index}
								className={`px-6 py-2 border-2 rounded-lg font-black text-sm`}
								style={{
									borderColor: feature.color === "cyan" ? "#06b6d4" : 
												feature.color === "pink" ? "#ec4899" : 
												feature.color === "purple" ? "#a855f7" : "#10b981",
									color: feature.color === "cyan" ? "#06b6d4" : 
										   feature.color === "pink" ? "#ec4899" : 
										   feature.color === "purple" ? "#a855f7" : "#10b981",
									textShadow: `0 0 10px ${feature.color === "cyan" ? "rgba(6,182,212,0.8)" : 
															feature.color === "pink" ? "rgba(236,72,153,0.8)" : 
															feature.color === "purple" ? "rgba(168,85,247,0.8)" : "rgba(16,185,129,0.8)"}`,
									boxShadow: `0 0 15px ${feature.color === "cyan" ? "rgba(6,182,212,0.3)" : 
														   feature.color === "pink" ? "rgba(236,72,153,0.3)" : 
														   feature.color === "purple" ? "rgba(168,85,247,0.3)" : "rgba(16,185,129,0.3)"}`
								}}
							>
								{feature.label}
							</div>
						))}
					</div>
				</div>
			</div>

			<style jsx>{`
				@keyframes neon-pulse {
					0%, 100% { box-shadow: 0 0 20px rgba(0,255,255,0.5), inset 0 0 20px rgba(0,255,255,0.1); }
					50% { box-shadow: 0 0 40px rgba(0,255,255,0.8), inset 0 0 30px rgba(0,255,255,0.2); }
				}
				@keyframes scanlines {
					0% { transform: translateY(0); }
					100% { transform: translateY(4px); }
				}
				.animation-delay-1000 { animation-delay: 1s; }
				.animation-delay-2000 { animation-delay: 2s; }
				.glitch-text {
					position: relative;
				}
				.glitch-text::before,
				.glitch-text::after {
					content: attr(data-text);
					position: absolute;
					top: 0;
					left: 0;
					width: 100%;
					height: 100%;
				}
				.glitch-text::before {
					color: #0ff;
					animation: glitch-1 1.5s infinite;
					clip-path: polygon(0 0, 100% 0, 100% 45%, 0 45%);
				}
				.glitch-text::after {
					color: #f0f;
					animation: glitch-2 1.5s infinite;
					clip-path: polygon(0 80%, 100% 80%, 100% 100%, 0 100%);
				}
				@keyframes glitch-1 {
					0% { transform: translateX(0); }
					20% { transform: translateX(-2px); }
					40% { transform: translateX(2px); }
					60% { transform: translateX(-2px); }
					80% { transform: translateX(2px); }
					100% { transform: translateX(0); }
				}
				@keyframes glitch-2 {
					0% { transform: translateX(0); }
					20% { transform: translateX(2px); }
					40% { transform: translateX(-2px); }
					60% { transform: translateX(2px); }
					80% { transform: translateX(-2px); }
					100% { transform: translateX(0); }
				}
			`}</style>
		</section>
	);
}
