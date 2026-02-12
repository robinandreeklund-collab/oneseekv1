"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function ModernHeroSection() {
	const t = useTranslations("homepage");
	const canvasRef = useRef<HTMLCanvasElement>(null);
	const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });

	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;

		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		canvas.width = window.innerWidth;
		canvas.height = window.innerHeight;

		// Subtle grid animation
		let offset = 0;

		function animate() {
			if (!ctx || !canvas) return;

			ctx.clearRect(0, 0, canvas.width, canvas.height);

			// Draw perspective grid
			ctx.strokeStyle = "rgba(139, 92, 246, 0.1)"; // Subtle purple
			ctx.lineWidth = 1;

			const gridSize = 50;
			const perspective = 0.3;

			// Vertical lines
			for (let x = 0; x < canvas.width; x += gridSize) {
				ctx.beginPath();
				const topOffset = (x - canvas.width / 2) * perspective;
				ctx.moveTo(x + topOffset, 0);
				ctx.lineTo(x, canvas.height);
				ctx.stroke();
			}

			// Horizontal lines with animation
			for (let y = offset; y < canvas.height; y += gridSize) {
				ctx.beginPath();
				ctx.moveTo(0, y);
				ctx.lineTo(canvas.width, y);
				ctx.stroke();
			}

			offset = (offset + 0.5) % gridSize;
			requestAnimationFrame(animate);
		}

		animate();

		const handleResize = () => {
			canvas.width = window.innerWidth;
			canvas.height = window.innerHeight;
		};

		const handleMouseMove = (e: MouseEvent) => {
			setMousePosition({ x: e.clientX, y: e.clientY });
		};

		window.addEventListener("resize", handleResize);
		window.addEventListener("mousemove", handleMouseMove);

		return () => {
			window.removeEventListener("resize", handleResize);
			window.removeEventListener("mousemove", handleMouseMove);
		};
	}, []);

	return (
		<section className="relative min-h-screen w-full overflow-hidden bg-gradient-to-b from-black via-gray-900 to-black">
			{/* Animated Grid Canvas */}
			<canvas
				ref={canvasRef}
				className="absolute inset-0 opacity-40"
			/>

			{/* Gradient Orbs */}
			<div className="absolute inset-0 overflow-hidden">
				<div 
					className="absolute w-[600px] h-[600px] rounded-full opacity-20 blur-3xl transition-all duration-1000"
					style={{
						background: "radial-gradient(circle, rgba(139, 92, 246, 0.4), transparent 70%)",
						left: `${mousePosition.x - 300}px`,
						top: `${mousePosition.y - 300}px`,
					}}
				/>
				<div className="absolute top-1/4 right-1/4 w-[500px] h-[500px] bg-gradient-to-br from-pink-500/20 to-purple-500/20 rounded-full blur-3xl animate-pulse-slow" />
				<div className="absolute bottom-1/4 left-1/4 w-[400px] h-[400px] bg-gradient-to-tr from-cyan-500/20 to-blue-500/20 rounded-full blur-3xl animate-pulse-slow animation-delay-2000" />
			</div>

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-7xl w-full">
					<div className="text-center">
						{/* Badge */}
						<div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 backdrop-blur-xl border border-white/10 mb-8 group hover:border-purple-500/50 transition-all duration-300">
							<Sparkles className="w-4 h-4 text-purple-400 group-hover:rotate-12 transition-transform" />
							<span className="text-sm font-medium text-gray-300">
								Powered by LangGraph & 100+ AI Models
							</span>
						</div>

						{/* Main Heading */}
						<h1 className="text-5xl md:text-7xl lg:text-8xl font-black mb-8 leading-none">
							<span className="block text-white mb-2">
								Power <span className="bg-gradient-to-r from-purple-400 via-pink-400 to-purple-400 bg-clip-text text-transparent">Automotive</span> AI
							</span>
							<span className="block text-white">
								With Your <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">Data</span>
							</span>
						</h1>

						{/* Subtitle */}
						<p className="text-xl md:text-2xl text-gray-400 mb-12 max-w-3xl mx-auto leading-relaxed">
							{t("hero_subtitle") || "Jämför 100+ AI-modeller, få realtidsdata från svenska API:er, och se hela LangGraph-flödet med full transparens"}
						</p>

						{/* CTA Buttons */}
						<div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-16">
							<Link
								href="/dashboard/public/new-chat"
								className="group relative px-8 py-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-xl overflow-hidden transition-all duration-300 hover:shadow-2xl hover:shadow-purple-500/50 hover:scale-105"
							>
								<span className="relative z-10 flex items-center gap-2">
									Börja utforska
									<ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
								</span>
								<div className="absolute inset-0 bg-gradient-to-r from-pink-600 to-purple-600 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
							</Link>
							<Link
								href="/contact"
								className="px-8 py-4 bg-white/5 backdrop-blur-xl border border-white/10 text-white font-semibold rounded-xl hover:bg-white/10 hover:border-white/20 transition-all duration-300 hover:scale-105"
							>
								Kontakta oss
							</Link>
						</div>

						{/* 3D Visualization Container */}
						<div className="relative mx-auto max-w-5xl">
							{/* Glassmorphic Card */}
							<div className="relative bg-gradient-to-b from-white/10 to-white/5 backdrop-blur-2xl rounded-3xl border border-white/20 p-1 shadow-2xl">
								{/* Inner glow */}
								<div className="absolute inset-0 bg-gradient-to-b from-purple-500/20 via-transparent to-transparent rounded-3xl" />
								
								{/* Content */}
								<div className="relative bg-black/40 backdrop-blur-xl rounded-2xl p-8 md:p-12">
									{/* 3D Isometric Layout */}
									<div className="grid grid-cols-1 md:grid-cols-3 gap-6">
										{/* AI Models */}
										<div className="group relative">
											<div className="absolute inset-0 bg-gradient-to-br from-purple-500/20 to-transparent rounded-2xl blur-xl group-hover:blur-2xl transition-all" />
											<div className="relative bg-gradient-to-br from-purple-900/30 to-black/50 backdrop-blur-sm border border-purple-500/30 rounded-2xl p-6 hover:border-purple-500/50 transition-all duration-300 hover:transform hover:-translate-y-2">
												<div className="text-4xl font-black text-purple-400 mb-2">100+</div>
												<div className="text-sm font-semibold text-white mb-1">AI-modeller</div>
												<div className="text-xs text-gray-400">Jämför side-by-side</div>
											</div>
										</div>

										{/* Swedish APIs */}
										<div className="group relative">
											<div className="absolute inset-0 bg-gradient-to-br from-pink-500/20 to-transparent rounded-2xl blur-xl group-hover:blur-2xl transition-all" />
											<div className="relative bg-gradient-to-br from-pink-900/30 to-black/50 backdrop-blur-sm border border-pink-500/30 rounded-2xl p-6 hover:border-pink-500/50 transition-all duration-300 hover:transform hover:-translate-y-2">
												<div className="text-4xl font-black text-pink-400 mb-2">7</div>
												<div className="text-sm font-semibold text-white mb-1">Svenska API:er</div>
												<div className="text-xs text-gray-400">Realtidsdata</div>
											</div>
										</div>

										{/* Transparency */}
										<div className="group relative">
											<div className="absolute inset-0 bg-gradient-to-br from-cyan-500/20 to-transparent rounded-2xl blur-xl group-hover:blur-2xl transition-all" />
											<div className="relative bg-gradient-to-br from-cyan-900/30 to-black/50 backdrop-blur-sm border border-cyan-500/30 rounded-2xl p-6 hover:border-cyan-500/50 transition-all duration-300 hover:transform hover:-translate-y-2">
												<div className="text-4xl font-black text-cyan-400 mb-2">100%</div>
												<div className="text-sm font-semibold text-white mb-1">Transparens</div>
												<div className="text-xs text-gray-400">Full LangGraph</div>
											</div>
										</div>
									</div>

									{/* Feature Pills */}
									<div className="flex flex-wrap justify-center gap-3 mt-8">
										{[
											"Compare Models",
											"AI Debates",
											"Swedish Data",
											"Real-time",
											"Full Transparency"
										].map((feature, index) => (
											<div
												key={index}
												className="px-4 py-2 bg-white/5 backdrop-blur-sm border border-white/10 rounded-full text-xs font-medium text-gray-300 hover:bg-white/10 hover:border-white/20 transition-all duration-300"
											>
												{feature}
											</div>
										))}
									</div>
								</div>
							</div>

							{/* Decorative Elements */}
							<div className="absolute -top-4 -right-4 w-24 h-24 bg-gradient-to-br from-purple-500/30 to-pink-500/30 rounded-full blur-2xl" />
							<div className="absolute -bottom-4 -left-4 w-32 h-32 bg-gradient-to-tr from-cyan-500/30 to-blue-500/30 rounded-full blur-2xl" />
						</div>

						{/* Trust Indicators */}
						<div className="mt-16 text-center">
							<p className="text-sm text-gray-500 mb-4">Trusted by Swedish organizations</p>
							<div className="flex flex-wrap justify-center gap-8 opacity-50">
								{["SCB", "SMHI", "Trafiklab", "Bolagsverket"].map((org, index) => (
									<div key={index} className="text-gray-600 font-semibold">
										{org}
									</div>
								))}
							</div>
						</div>
					</div>
				</div>
			</div>

			<style jsx>{`
				@keyframes pulse-slow {
					0%, 100% { opacity: 0.15; transform: scale(1); }
					50% { opacity: 0.25; transform: scale(1.05); }
				}
				.animate-pulse-slow {
					animation: pulse-slow 6s ease-in-out infinite;
				}
				.animation-delay-2000 {
					animation-delay: 2s;
				}
			`}</style>
		</section>
	);
}
