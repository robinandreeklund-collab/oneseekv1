"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Bot, Sparkles, Zap, Database } from "lucide-react";

export function HeroMockup3Isometric() {
	const t = useTranslations("homepage");

	return (
		<section className="relative min-h-screen w-full overflow-hidden bg-gradient-to-br from-indigo-50 via-white to-purple-50 dark:from-indigo-950 dark:via-gray-950 dark:to-purple-950">
			{/* Isometric Grid Background */}
			<div className="absolute inset-0 opacity-30">
				<div className="absolute inset-0" style={{
					backgroundImage: `linear-gradient(30deg, #6366f1 12%, transparent 12.5%, transparent 87%, #6366f1 87.5%, #6366f1),
					linear-gradient(150deg, #6366f1 12%, transparent 12.5%, transparent 87%, #6366f1 87.5%, #6366f1),
					linear-gradient(30deg, #6366f1 12%, transparent 12.5%, transparent 87%, #6366f1 87.5%, #6366f1),
					linear-gradient(150deg, #6366f1 12%, transparent 12.5%, transparent 87%, #6366f1 87.5%, #6366f1)`,
					backgroundSize: '80px 140px',
					backgroundPosition: '0 0, 0 0, 40px 70px, 40px 70px'
				}} />
			</div>

			{/* Content */}
			<div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-20">
				<div className="max-w-7xl w-full">
					<div className="grid lg:grid-cols-2 gap-12 items-center">
						{/* Left: Text Content */}
						<div>
							<h1 className="text-6xl md:text-7xl lg:text-8xl font-black mb-6 leading-tight">
								<span className="text-gray-900 dark:text-white">Bygg med</span>
								<br />
								<span className="bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 bg-clip-text text-transparent">
									AI-agenter
								</span>
							</h1>

							<p className="text-xl md:text-2xl text-gray-700 dark:text-gray-300 mb-10 leading-relaxed">
								OneSeek kombinerar 100+ AI-modeller med svenska datakällor i en transparent agent-pipeline
							</p>

							<div className="flex flex-col sm:flex-row gap-4 mb-12">
								<Link
									href="/dashboard/public/new-chat"
									className="px-8 py-4 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-bold text-lg rounded-xl shadow-[8px_8px_0px_0px_rgba(99,102,241,0.3)] hover:shadow-[12px_12px_0px_0px_rgba(99,102,241,0.3)] hover:translate-x-[-4px] hover:translate-y-[-4px] transition-all duration-200"
								>
									Testa gratis
								</Link>
								<Link
									href="/contact"
									className="px-8 py-4 bg-white dark:bg-gray-900 text-gray-900 dark:text-white font-bold text-lg rounded-xl border-4 border-gray-900 dark:border-white shadow-[8px_8px_0px_0px_rgba(0,0,0,0.2)] hover:shadow-[12px_12px_0px_0px_rgba(0,0,0,0.2)] hover:translate-x-[-4px] hover:translate-y-[-4px] transition-all duration-200"
								>
									Läs mer
								</Link>
							</div>

							{/* Stats */}
							<div className="grid grid-cols-3 gap-4">
								{[
									{ value: "100+", label: "Modeller" },
									{ value: "7", label: "API:er" },
									{ value: "∞", label: "Möjligheter" }
								].map((stat, index) => (
									<div key={index} className="text-center">
										<div className="text-3xl md:text-4xl font-black text-indigo-600 dark:text-indigo-400 mb-1">
											{stat.value}
										</div>
										<div className="text-sm font-semibold text-gray-600 dark:text-gray-400">
											{stat.label}
										</div>
									</div>
								))}
							</div>
						</div>

						{/* Right: Isometric Cards */}
						<div className="relative h-[600px]">
							{/* Card 1 - Top */}
							<div 
								className="absolute top-0 left-1/2 -translate-x-1/2 w-64 h-64 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-2xl shadow-2xl transform -rotate-12 hover:rotate-0 transition-all duration-500 hover:scale-110 cursor-pointer"
								style={{ transform: 'perspective(1000px) rotateX(20deg) rotateY(-15deg)' }}
							>
								<div className="p-6 text-white">
									<Bot className="w-12 h-12 mb-4" />
									<h3 className="text-2xl font-black mb-2">Compare</h3>
									<p className="text-sm opacity-90">Jämför 100+ AI-modeller</p>
								</div>
							</div>

							{/* Card 2 - Middle Left */}
							<div 
								className="absolute top-1/2 left-1/4 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-gradient-to-br from-purple-500 to-pink-500 rounded-2xl shadow-2xl transform rotate-6 hover:rotate-0 transition-all duration-500 hover:scale-110 cursor-pointer"
								style={{ transform: 'perspective(1000px) rotateX(20deg) rotateY(15deg)' }}
							>
								<div className="p-6 text-white">
									<Zap className="w-12 h-12 mb-4" />
									<h3 className="text-2xl font-black mb-2">Debate</h3>
									<p className="text-sm opacity-90">AI-modeller debatterar</p>
								</div>
							</div>

							{/* Card 3 - Middle Right */}
							<div 
								className="absolute top-1/2 right-1/4 translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-gradient-to-br from-green-500 to-emerald-500 rounded-2xl shadow-2xl transform -rotate-6 hover:rotate-0 transition-all duration-500 hover:scale-110 cursor-pointer"
								style={{ transform: 'perspective(1000px) rotateX(20deg) rotateY(-20deg)' }}
							>
								<div className="p-6 text-white">
									<Sparkles className="w-12 h-12 mb-4" />
									<h3 className="text-2xl font-black mb-2">Transparent</h3>
									<p className="text-sm opacity-90">Se hela flödet</p>
								</div>
							</div>

							{/* Card 4 - Bottom */}
							<div 
								className="absolute bottom-0 left-1/2 -translate-x-1/2 w-64 h-64 bg-gradient-to-br from-orange-500 to-red-500 rounded-2xl shadow-2xl transform rotate-12 hover:rotate-0 transition-all duration-500 hover:scale-110 cursor-pointer"
								style={{ transform: 'perspective(1000px) rotateX(20deg) rotateY(10deg)' }}
							>
								<div className="p-6 text-white">
									<Database className="w-12 h-12 mb-4" />
									<h3 className="text-2xl font-black mb-2">Swedish APIs</h3>
									<p className="text-sm opacity-90">7 svenska datakällor</p>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</section>
	);
}
