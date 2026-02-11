"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import { Waves } from "lucide-react";

export function HeroMockup9LiquidMorphing() {
	const t = useTranslations("homepage");
	const canvasRef = useRef<HTMLCanvasElement>(null);

	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;

		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		canvas.width = window.innerWidth;
		canvas.height = window.innerHeight;

		let time = 0;

		function drawBlob(x: number, y: number, radius: number, color: string, phase: number) {
			if (!ctx) return;
			
			ctx.beginPath();
			
			for (let angle = 0; angle < Math.PI * 2; angle += 0.1) {
				const r = radius + Math.sin(angle * 3 + phase) * 30 + Math.cos(angle * 5 + phase * 1.5) * 20;
				const px = x + Math.cos(angle) * r;
				const py = y + Math.sin(angle) * r;
				
				if (angle === 0) {
					ctx.moveTo(px, py);
				} else {
					ctx.lineTo(px, py);
				}
			}
			
			ctx.closePath();
			ctx.fillStyle = color;
			ctx.fill();
		}

		function animate() {
			if (!ctx || !canvas) return;
			
			ctx.clearRect(0, 0, canvas.width, canvas.height);
			
			time += 0.02;
			
			// Draw morphing blobs
			drawBlob(
				canvas.width * 0.3 + Math.cos(time * 0.5) * 100,
				canvas.height * 0.3 + Math.sin(time * 0.7) * 80,
				150,
				"rgba(99, 102, 241, 0.3)",
				time
			);
			
			drawBlob(
				canvas.width * 0.7 + Math.sin(time * 0.6) * 120,
				canvas.height * 0.4 + Math.cos(time * 0.8) * 90,
				180,
				"rgba(168, 85, 247, 0.3)",
				time + 1
			);
			
			drawBlob(
				canvas.width * 0.5 + Math.cos(time * 0.4) * 80,
				canvas.height * 0.7 + Math.sin(time * 0.5) * 100,
				160,
				"rgba(236, 72, 153, 0.3)",
				time + 2
			);
			
			requestAnimationFrame(animate);
		}

		animate();

		const handleResize = () => {
			canvas.width = window.innerWidth;
			canvas.height = window.innerHeight;
		};

		window.addEventListener("resize", handleResize);
		return () => window.removeEventListener("resize", handleResize);
	}, []);

	return (
		<section className="relative min-h-screen w-full overflow-hidden bg-gradient-to-br from-indigo-50 via-purple-50 to-pink-50 dark:from-indigo-950 dark:via-purple-950 dark:to-pink-950">
			{/* Liquid Morphing Canvas */}
			<canvas
				ref={canvasRef}
				className="absolute inset-0 w-full h-full"
				style={{ filter: 'blur(40px)' }}
			/>

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-6xl w-full text-center">
					{/* Animated Badge */}
					<div className="inline-flex items-center gap-3 px-6 py-3 rounded-full bg-white/40 dark:bg-white/10 backdrop-blur-xl border border-white/60 dark:border-white/20 mb-8 shadow-xl">
						<Waves className="w-5 h-5 text-purple-600 dark:text-purple-400 animate-pulse" />
						<span className="text-sm font-bold text-gray-900 dark:text-white">
							Flytande AI-intelligens
						</span>
					</div>

					{/* Main Heading */}
					<h1 className="text-6xl md:text-8xl lg:text-9xl font-black mb-6 leading-none">
						<span className="block mb-4">
							<span className="bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 dark:from-indigo-400 dark:via-purple-400 dark:to-pink-400 bg-clip-text text-transparent animate-gradient-x">
								Organisk
							</span>
						</span>
						<span className="block text-gray-900 dark:text-white">
							AI-evolution
						</span>
					</h1>

					{/* Subtitle */}
					<p className="text-xl md:text-2xl text-gray-700 dark:text-gray-300 mb-12 max-w-3xl mx-auto leading-relaxed">
						OneSeek anpassar sig dynamiskt till dina frågor och morfar mellan 100+ AI-modeller för optimala svar
					</p>

					{/* Liquid CTA Buttons */}
					<div className="flex flex-col sm:flex-row gap-6 justify-center items-center mb-16">
						<Link
							href="/dashboard/public/new-chat"
							className="group relative px-12 py-6 bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 text-white font-black text-xl rounded-full overflow-hidden shadow-2xl hover:shadow-3xl transition-all duration-500 hover:scale-110"
						>
							<span className="relative z-10">Börja utforska</span>
							<div className="absolute inset-0 bg-gradient-to-r from-pink-600 via-purple-600 to-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
							<div className="absolute inset-0 bg-gradient-to-tr from-indigo-400/50 to-pink-400/50 blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
						</Link>
						<Link
							href="/contact"
							className="px-12 py-6 bg-white/60 dark:bg-white/10 backdrop-blur-xl border-3 border-white/80 dark:border-white/30 text-gray-900 dark:text-white font-black text-xl rounded-full hover:bg-white/80 dark:hover:bg-white/20 transition-all duration-500 hover:scale-110 shadow-xl"
						>
							Se demo
						</Link>
					</div>

					{/* Flowing Feature Pills */}
					<div className="flex flex-wrap justify-center gap-4 max-w-4xl mx-auto">
						{[
							{ text: "Adaptiv AI", delay: "0s", color: "from-blue-500 to-cyan-500" },
							{ text: "100+ Modeller", delay: "0.2s", color: "from-purple-500 to-pink-500" },
							{ text: "Svenska Data", delay: "0.4s", color: "from-green-500 to-emerald-500" },
							{ text: "Transparens", delay: "0.6s", color: "from-orange-500 to-red-500" },
							{ text: "Realtid", delay: "0.8s", color: "from-indigo-500 to-purple-500" }
						].map((pill, index) => (
							<div
								key={index}
								className={`px-8 py-4 bg-gradient-to-r ${pill.color} text-white font-bold text-lg rounded-full shadow-xl hover:scale-110 transition-all duration-500 animate-float-pill`}
								style={{ animationDelay: pill.delay }}
							>
								{pill.text}
							</div>
						))}
					</div>

					{/* Liquid Stats */}
					<div className="mt-20 grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
						{[
							{ 
								value: "100+", 
								label: "AI-modeller", 
								sublabel: "Dynamisk växling",
								color: "from-blue-500 to-purple-500"
							},
							{ 
								value: "7", 
								label: "Svenska API:er", 
								sublabel: "Realtidsdata",
								color: "from-purple-500 to-pink-500"
							},
							{ 
								value: "∞", 
								label: "Möjligheter", 
								sublabel: "Organisk evolution",
								color: "from-pink-500 to-red-500"
							}
						].map((stat, index) => (
							<div
								key={index}
								className="relative group"
							>
								<div className={`absolute inset-0 bg-gradient-to-br ${stat.color} rounded-3xl blur-xl opacity-50 group-hover:opacity-70 transition-opacity duration-500`} />
								<div className="relative bg-white/60 dark:bg-white/10 backdrop-blur-xl rounded-3xl p-8 border border-white/60 dark:border-white/20 hover:scale-105 transition-all duration-500 shadow-xl">
									<div className={`text-5xl md:text-6xl font-black bg-gradient-to-r ${stat.color} bg-clip-text text-transparent mb-2`}>
										{stat.value}
									</div>
									<div className="text-lg font-bold text-gray-900 dark:text-white mb-1">
										{stat.label}
									</div>
									<div className="text-sm text-gray-600 dark:text-gray-400">
										{stat.sublabel}
									</div>
								</div>
							</div>
						))}
					</div>
				</div>
			</div>

			<style jsx>{`
				@keyframes gradient-x {
					0%, 100% { background-position: 0% 50%; }
					50% { background-position: 100% 50%; }
				}
				@keyframes float-pill {
					0%, 100% { transform: translateY(0px); }
					50% { transform: translateY(-10px); }
				}
				.animate-gradient-x {
					background-size: 200% auto;
					animation: gradient-x 3s ease infinite;
				}
				.animate-float-pill {
					animation: float-pill 3s ease-in-out infinite;
				}
			`}</style>
		</section>
	);
}
