"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";

export function HeroMockup5ParticleNetwork() {
	const t = useTranslations("homepage");
	const canvasRef = useRef<HTMLCanvasElement>(null);

	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;

		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		canvas.width = window.innerWidth;
		canvas.height = window.innerHeight;

		const particles: Array<{
			x: number;
			y: number;
			vx: number;
			vy: number;
			radius: number;
		}> = [];

		// Create particles
		for (let i = 0; i < 100; i++) {
			particles.push({
				x: Math.random() * canvas.width,
				y: Math.random() * canvas.height,
				vx: (Math.random() - 0.5) * 0.5,
				vy: (Math.random() - 0.5) * 0.5,
				radius: Math.random() * 2 + 1
			});
		}

		function animate() {
			if (!ctx || !canvas) return;
			
			ctx.clearRect(0, 0, canvas.width, canvas.height);

			// Update and draw particles
			particles.forEach((particle, i) => {
				particle.x += particle.vx;
				particle.y += particle.vy;

				// Bounce off edges
				if (particle.x < 0 || particle.x > canvas.width) particle.vx *= -1;
				if (particle.y < 0 || particle.y > canvas.height) particle.vy *= -1;

				// Draw particle
				ctx.beginPath();
				ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
				ctx.fillStyle = "rgba(99, 102, 241, 0.8)";
				ctx.fill();

				// Draw connections
				particles.slice(i + 1).forEach((otherParticle) => {
					const dx = particle.x - otherParticle.x;
					const dy = particle.y - otherParticle.y;
					const distance = Math.sqrt(dx * dx + dy * dy);

					if (distance < 150) {
						ctx.beginPath();
						ctx.moveTo(particle.x, particle.y);
						ctx.lineTo(otherParticle.x, otherParticle.y);
						ctx.strokeStyle = `rgba(99, 102, 241, ${1 - distance / 150})`;
						ctx.lineWidth = 0.5;
						ctx.stroke();
					}
				});
			});

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
		<section className="relative min-h-screen w-full overflow-hidden bg-gradient-to-br from-gray-900 via-indigo-950 to-purple-950">
			{/* Particle Canvas */}
			<canvas
				ref={canvasRef}
				className="absolute inset-0 w-full h-full"
			/>

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-6xl w-full text-center">
					{/* Animated Badge */}
					<div className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-indigo-500/20 backdrop-blur-sm border border-indigo-500/50 mb-8">
						<div className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
						<span className="text-sm font-bold text-indigo-300">
							Connected Neural Network
						</span>
					</div>

					{/* Main Heading */}
					<h1 className="text-6xl md:text-8xl lg:text-9xl font-black mb-6 leading-none">
						<span className="block text-white mb-4">
							Den intelligenta
						</span>
						<span className="block bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
							agent-nätverket
						</span>
					</h1>

					{/* Subtitle */}
					<p className="text-xl md:text-2xl text-indigo-200 mb-12 max-w-3xl mx-auto leading-relaxed">
						100+ sammankopplade AI-modeller arbetar tillsammans för att ge dig de bästa svaren
					</p>

					{/* CTA Buttons */}
					<div className="flex flex-col sm:flex-row gap-6 justify-center items-center mb-16">
						<Link
							href="/dashboard/public/new-chat"
							className="group relative px-10 py-5 bg-gradient-to-r from-indigo-500 to-purple-500 text-white font-bold text-xl rounded-xl overflow-hidden shadow-2xl hover:shadow-indigo-500/50 transition-all duration-300 hover:scale-105"
						>
							<span className="relative z-10">Anslut nu</span>
							<div className="absolute inset-0 bg-gradient-to-r from-purple-500 to-pink-500 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
						</Link>
						<Link
							href="/contact"
							className="px-10 py-5 bg-white/10 backdrop-blur-sm border-2 border-white/30 text-white font-bold text-xl rounded-xl hover:bg-white/20 transition-all duration-300 hover:scale-105"
						>
							Läs mer
						</Link>
					</div>

					{/* Network Stats */}
					<div className="grid grid-cols-3 gap-8 max-w-3xl mx-auto">
						{[
							{ value: "100+", label: "AI-noder", sublabel: "Sammankopplade modeller" },
							{ value: "7", label: "Data-källor", sublabel: "Svenska API:er" },
							{ value: "∞", label: "Förbindelser", sublabel: "Dynamiskt nätverk" }
						].map((stat, index) => (
							<div key={index} className="relative group">
								<div className="absolute inset-0 bg-indigo-500/20 rounded-2xl blur-xl group-hover:bg-indigo-500/30 transition-all duration-300" />
								<div className="relative bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 hover:border-indigo-500/50 transition-all duration-300">
									<div className="text-4xl md:text-5xl font-black text-indigo-400 mb-2">
										{stat.value}
									</div>
									<div className="text-sm font-bold text-white mb-1">
										{stat.label}
									</div>
									<div className="text-xs text-indigo-300">
										{stat.sublabel}
									</div>
								</div>
							</div>
						))}
					</div>
				</div>
			</div>
		</section>
	);
}
