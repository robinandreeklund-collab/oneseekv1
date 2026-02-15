"use client";

import { useState } from "react";
import { HeroMockup1Glassmorphism } from "./mockups/hero-mockup-1-glassmorphism";
import { HeroMockup2AnimatedGradient } from "./mockups/hero-mockup-2-animated-gradient";
import { HeroMockup3Isometric } from "./mockups/hero-mockup-3-isometric";
import { HeroMockup4NeonCyberpunk } from "./mockups/hero-mockup-4-neon-cyberpunk";
import { HeroMockup5ParticleNetwork } from "./mockups/hero-mockup-5-particle-network";
import { HeroMockup6Spotlight } from "./mockups/hero-mockup-6-spotlight";
import { HeroMockup7SplitScreen } from "./mockups/hero-mockup-7-split-screen";
import { HeroMockup8FloatingIslands } from "./mockups/hero-mockup-8-floating-islands";
import { HeroMockup9LiquidMorphing } from "./mockups/hero-mockup-9-liquid-morphing";
import { HeroMockup10HolographicGrid } from "./mockups/hero-mockup-10-holographic-grid";

const mockups = [
	{ id: 1, name: "Glassmorphism", component: HeroMockup1Glassmorphism, description: "Frosted glass with gradient meshes" },
	{ id: 2, name: "Animated Gradient", component: HeroMockup2AnimatedGradient, description: "Dynamic flowing colors" },
	{ id: 3, name: "3D Isometric", component: HeroMockup3Isometric, description: "Elevated cards with depth" },
	{ id: 4, name: "Neon Cyberpunk", component: HeroMockup4NeonCyberpunk, description: "Glowing futuristic theme" },
	{ id: 5, name: "Particle Network", component: HeroMockup5ParticleNetwork, description: "Connected particle system" },
	{ id: 6, name: "Spotlight", component: HeroMockup6Spotlight, description: "Mouse-follow lighting" },
	{ id: 7, name: "Split Screen", component: HeroMockup7SplitScreen, description: "Bold contrasting design" },
	{ id: 8, name: "Floating Islands", component: HeroMockup8FloatingIslands, description: "Floating card clusters" },
	{ id: 9, name: "Liquid Morphing", component: HeroMockup9LiquidMorphing, description: "Organic blob animations" },
	{ id: 10, name: "Holographic Grid", component: HeroMockup10HolographicGrid, description: "Sci-fi grid effects" }
];

export function MockupSelector() {
	const [selectedMockup, setSelectedMockup] = useState(1);
	
	const SelectedComponent = mockups.find(m => m.id === selectedMockup)?.component || HeroMockup1Glassmorphism;

	return (
		<div className="min-h-screen">
			{/* Mockup Selector Bar */}
			<div className="fixed top-0 left-0 right-0 z-50 bg-black/90 backdrop-blur-lg border-b border-white/10 p-4">
				<div className="max-w-7xl mx-auto">
					<h2 className="text-white font-bold mb-3 text-center">🎨 Select Design Mockup</h2>
					<div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-10 gap-2">
						{mockups.map((mockup) => (
							<button
								key={mockup.id}
								onClick={() => setSelectedMockup(mockup.id)}
								className={`
									px-3 py-2 rounded-lg text-xs font-medium transition-all
									${selectedMockup === mockup.id 
										? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-lg scale-105' 
										: 'bg-white/10 text-white/70 hover:bg-white/20'}
								`}
								title={mockup.description}
							>
								<div className="font-bold">{mockup.id}</div>
								<div className="truncate">{mockup.name}</div>
							</button>
						))}
					</div>
					<p className="text-white/60 text-xs text-center mt-2">
						{mockups.find(m => m.id === selectedMockup)?.description}
					</p>
				</div>
			</div>

			{/* Selected Mockup */}
			<div className="pt-32">
				<SelectedComponent />
			</div>
		</div>
	);
}
