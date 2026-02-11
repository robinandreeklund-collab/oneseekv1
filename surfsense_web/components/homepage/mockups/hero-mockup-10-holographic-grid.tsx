"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import { Sparkles, Zap } from "lucide-react";

export function HeroMockup10HolographicGrid() {
	const t = useTranslations("homepage");
	const gridRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		const grid = gridRef.current;
		if (!grid) return;

		const handleMouseMove = (e: MouseEvent) => {
			const rect = grid.getBoundingClientRect();
			const x = ((e.clientX - rect.left) / rect.width) * 100;
			const y = ((e.clientY - rect.top) / rect.height) * 100;
			
			grid.style.setProperty('--mouse-x', `${x}%`);
			grid.style.setProperty('--mouse-y', `${y}%`);
		};

		window.addEventListener('mousemove', handleMouseMove);
		return () => window.removeEventListener('mousemove', handleMouseMove);
	}, []);

	return (
		<section 
			ref={gridRef}
			className="relative min-h-screen w-full overflow-hidden bg-black"
			style={{
				'--mouse-x': '50%',
				'--mouse-y': '50%'
			} as React.CSSProperties}
		>
			{/* Holographic Grid Background */}
			<div className="absolute inset-0">
				{/* Main perspective grid */}
				<div 
					className="absolute inset-0 opacity-40"
					style={{
						background: `
							linear-gradient(to right, rgba(0, 255, 255, 0.3) 1px, transparent 1px),
							linear-gradient(to bottom, rgba(0, 255, 255, 0.3) 1px, transparent 1px)
						`,
						backgroundSize: '50px 50px',
						transform: 'perspective(500px) rotateX(60deg)',
						transformOrigin: 'center bottom'
					}}
				/>
				
				{/* Horizontal scan lines */}
				<div 
					className="absolute inset-0 opacity-20"
					style={{
						background: 'repeating-linear-gradient(0deg, rgba(0, 255, 255, 0.4) 0px, transparent 2px, transparent 4px)',
						animation: 'scan 4s linear infinite'
					}}
				/>

				{/* Glowing orb that follows mouse */}
				<div 
					className="absolute w-96 h-96 rounded-full transition-all duration-300 ease-out"
					style={{
						left: 'var(--mouse-x)',
						top: 'var(--mouse-y)',
						transform: 'translate(-50%, -50%)',
						background: 'radial-gradient(circle, rgba(0, 255, 255, 0.3), rgba(255, 0, 255, 0.2), transparent 70%)',
						filter: 'blur(60px)',
						pointerEvents: 'none'
					}}
				/>

				{/* Corner holograms */}
				{[
					{ top: '10%', left: '10%', delay: '0s' },
					{ top: '10%', right: '10%', delay: '0.5s' },
					{ bottom: '10%', left: '10%', delay: '1s' },
					{ bottom: '10%', right: '10%', delay: '1.5s' }
				].map((pos, index) => (
					<div
						key={index}
						className="absolute w-32 h-32"
						style={{
							...pos,
							animation: `hologram-pulse 3s ease-in-out infinite`,
							animationDelay: pos.delay
						}}
					>
						<div className="w-full h-full border-2 border-cyan-500/50 rounded-lg"
							style={{
								boxShadow: '0 0 20px rgba(0, 255, 255, 0.5), inset 0 0 20px rgba(0, 255, 255, 0.2)'
							}}
						/>
					</div>
				))}
			</div>

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-6xl w-full text-center">
					{/* Holographic Badge */}
					<div 
						className="inline-flex items-center gap-3 px-6 py-3 rounded-lg mb-8"
						style={{
							background: 'rgba(0, 255, 255, 0.1)',
							border: '2px solid rgba(0, 255, 255, 0.5)',
							boxShadow: '0 0 30px rgba(0, 255, 255, 0.3), inset 0 0 30px rgba(0, 255, 255, 0.1)',
							animation: 'hologram-flicker 2s infinite'
						}}
					>
						<Sparkles className="w-5 h-5 text-cyan-400" />
						<span className="text-sm font-black text-cyan-400 uppercase tracking-wider">
							Holographic AI Interface
						</span>
					</div>

					{/* Main Heading with Hologram Effect */}
					<h1 className="text-6xl md:text-8xl lg:text-9xl font-black mb-8 leading-none hologram-text">
						<span className="block mb-4 text-cyan-400" style={{
							textShadow: '0 0 20px rgba(0, 255, 255, 0.8), 0 0 40px rgba(0, 255, 255, 0.5)',
							filter: 'drop-shadow(0 0 30px rgba(0, 255, 255, 0.7))'
						}}>
							ONESEEK
						</span>
						<span className="block text-transparent bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text">
							Neural Interface
						</span>
					</h1>

					{/* Subtitle */}
					<p className="text-xl md:text-2xl text-cyan-300 mb-4 font-bold">
						INITIALIZING AI NETWORK...
					</p>
					<p className="text-lg md:text-xl text-gray-400 mb-12 max-w-3xl mx-auto">
						100+ Neural Nodes · 7 Swedish Data Streams · Full System Transparency
					</p>

					{/* Holographic CTA Buttons */}
					<div className="flex flex-col sm:flex-row gap-6 justify-center items-center mb-16">
						<Link
							href="/dashboard/public/new-chat"
							className="group relative px-12 py-6 font-black text-xl overflow-hidden transition-all duration-300"
							style={{
								background: 'linear-gradient(135deg, rgba(0, 255, 255, 0.2), rgba(255, 0, 255, 0.2))',
								border: '2px solid rgba(0, 255, 255, 0.5)',
								boxShadow: '0 0 30px rgba(0, 255, 255, 0.4), inset 0 0 30px rgba(0, 255, 255, 0.1)',
								color: '#00ffff',
								textShadow: '0 0 10px rgba(0, 255, 255, 0.8)'
							}}
							onMouseEnter={(e) => {
								e.currentTarget.style.boxShadow = '0 0 50px rgba(0, 255, 255, 0.6), inset 0 0 50px rgba(0, 255, 255, 0.2)';
								e.currentTarget.style.transform = 'scale(1.05)';
							}}
							onMouseLeave={(e) => {
								e.currentTarget.style.boxShadow = '0 0 30px rgba(0, 255, 255, 0.4), inset 0 0 30px rgba(0, 255, 255, 0.1)';
								e.currentTarget.style.transform = 'scale(1)';
							}}
						>
							<Zap className="inline w-6 h-6 mr-2" />
							ACTIVATE SYSTEM
						</Link>
						<Link
							href="/contact"
							className="px-12 py-6 font-black text-xl transition-all duration-300"
							style={{
								background: 'transparent',
								border: '2px solid rgba(255, 0, 255, 0.5)',
								boxShadow: '0 0 20px rgba(255, 0, 255, 0.3), inset 0 0 20px rgba(255, 0, 255, 0.1)',
								color: '#ff00ff',
								textShadow: '0 0 10px rgba(255, 0, 255, 0.8)'
							}}
							onMouseEnter={(e) => {
								e.currentTarget.style.boxShadow = '0 0 40px rgba(255, 0, 255, 0.5), inset 0 0 40px rgba(255, 0, 255, 0.2)';
								e.currentTarget.style.transform = 'scale(1.05)';
							}}
							onMouseLeave={(e) => {
								e.currentTarget.style.boxShadow = '0 0 20px rgba(255, 0, 255, 0.3), inset 0 0 20px rgba(255, 0, 255, 0.1)';
								e.currentTarget.style.transform = 'scale(1)';
							}}
						>
							REQUEST ACCESS
						</Link>
					</div>

					{/* System Status Display */}
					<div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
						{[
							{ 
								label: "AI NODES", 
								value: "100+", 
								status: "ONLINE",
								color: "cyan"
							},
							{ 
								label: "DATA STREAMS", 
								value: "7", 
								status: "ACTIVE",
								color: "purple"
							},
							{ 
								label: "TRANSPARENCY", 
								value: "100%", 
								status: "ENABLED",
								color: "pink"
							}
						].map((system, index) => (
							<div
								key={index}
								className="relative group"
							>
								<div 
									className="absolute inset-0 rounded-lg blur-md"
									style={{
										background: system.color === "cyan" ? 'rgba(0, 255, 255, 0.2)' :
												   system.color === "purple" ? 'rgba(168, 85, 247, 0.2)' :
												   'rgba(236, 72, 153, 0.2)',
										animation: 'hologram-pulse 2s ease-in-out infinite',
										animationDelay: `${index * 0.3}s`
									}}
								/>
								<div 
									className="relative p-8 rounded-lg"
									style={{
										background: 'rgba(0, 0, 0, 0.5)',
										border: `2px solid ${
											system.color === "cyan" ? 'rgba(0, 255, 255, 0.5)' :
											system.color === "purple" ? 'rgba(168, 85, 247, 0.5)' :
											'rgba(236, 72, 153, 0.5)'
										}`,
										boxShadow: `0 0 20px ${
											system.color === "cyan" ? 'rgba(0, 255, 255, 0.3)' :
											system.color === "purple" ? 'rgba(168, 85, 247, 0.3)' :
											'rgba(236, 72, 153, 0.3)'
										}, inset 0 0 20px ${
											system.color === "cyan" ? 'rgba(0, 255, 255, 0.1)' :
											system.color === "purple" ? 'rgba(168, 85, 247, 0.1)' :
											'rgba(236, 72, 153, 0.1)'
										}`
									}}
								>
									<div className="text-xs font-black mb-2 opacity-70"
										style={{
											color: system.color === "cyan" ? '#00ffff' :
												   system.color === "purple" ? '#a855f7' :
												   '#ec4899'
										}}
									>
										{system.label}
									</div>
									<div className="text-4xl md:text-5xl font-black mb-2"
										style={{
											color: system.color === "cyan" ? '#00ffff' :
												   system.color === "purple" ? '#a855f7' :
												   '#ec4899',
											textShadow: `0 0 20px ${
												system.color === "cyan" ? 'rgba(0, 255, 255, 0.8)' :
												system.color === "purple" ? 'rgba(168, 85, 247, 0.8)' :
												'rgba(236, 72, 153, 0.8)'
											}`
										}}
									>
										{system.value}
									</div>
									<div className="text-xs font-bold flex items-center justify-center gap-2"
										style={{
											color: system.color === "cyan" ? '#00ffff' :
												   system.color === "purple" ? '#a855f7' :
												   '#ec4899'
										}}
									>
										<span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
										{system.status}
									</div>
								</div>
							</div>
						))}
					</div>
				</div>
			</div>

			<style jsx>{`
				@keyframes scan {
					0% { transform: translateY(0); }
					100% { transform: translateY(4px); }
				}
				@keyframes hologram-pulse {
					0%, 100% { 
						opacity: 1;
						transform: scale(1);
					}
					50% { 
						opacity: 0.7;
						transform: scale(1.02);
					}
				}
				@keyframes hologram-flicker {
					0%, 100% { opacity: 1; }
					50% { opacity: 0.95; }
					75% { opacity: 0.98; }
				}
				.hologram-text {
					animation: hologram-flicker 3s infinite;
				}
			`}</style>
		</section>
	);
}
