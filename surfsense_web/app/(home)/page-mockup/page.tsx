"use client";

import { motion, useInView } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";
import Balancer from "react-wrap-balancer";
import { Logo } from "@/components/Logo";
import { cn } from "@/lib/utils";

// ==================== SHARED COMPONENTS ====================

// Wrapper that fades in children on scroll
const AnimatedSection = ({ children, className }: { children: React.ReactNode; className?: string }) => {
	const ref = useRef(null);
	const isInView = useInView(ref, { once: true, margin: "-100px" });

	return (
		<motion.section
			ref={ref}
			initial={{ opacity: 1, y: 0 }}
			animate={isInView ? { opacity: 1, y: 0 } : { opacity: 1, y: 0 }}
			transition={{ duration: 0.6, ease: "easeOut" }}
			className={className}
		>
			{children}
		</motion.section>
	);
};

// Pill badge with border and backdrop blur
const SectionBadge = ({ children, className }: { children: React.ReactNode; className?: string }) => {
	return (
		<div
			className={cn(
				"mb-4 inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white/50 px-3 py-1.5 text-sm font-medium backdrop-blur-sm dark:border-gray-700 dark:bg-gray-800/50",
				className
			)}
		>
			{children}
		</div>
	);
};

// Animated counter that counts up from 0
const AnimatedCounter = ({ value, suffix = "" }: { value: string; suffix?: string }) => {
	const ref = useRef(null);
	const isInView = useInView(ref, { once: true });
	const [count, setCount] = useState(0);
	const target = parseInt(value);

	useEffect(() => {
		if (isInView && !isNaN(target)) {
			let current = 0;
			const increment = target / 30;
			const timer = setInterval(() => {
				current += increment;
				if (current >= target) {
					setCount(target);
					clearInterval(timer);
				} else {
					setCount(Math.floor(current));
				}
			}, 30);
			return () => clearInterval(timer);
		}
	}, [isInView, target]);

	return (
		<span ref={ref} className="font-bold">
			{count}
			{suffix}
		</span>
	);
};

// Typing animation component
const TypingAnimation = () => {
	const queries = [
		{ text: "Hur blir vädret i Stockholm imorgon?", badge: "WEATHER", color: "bg-blue-500" },
		{ text: "Jämför alla AI-modeller om klimatpolitik", badge: "COMPARE", color: "bg-purple-500" },
		{ text: "Visa SCB-statistik för befolkningsutveckling", badge: "STATISTICS", color: "bg-emerald-500" },
		{ text: "Vad säger riksdagen om energipolitik?", badge: "RIKSDAGEN", color: "bg-amber-500" },
		{ text: "Hitta information om Volvo AB", badge: "BOLAG", color: "bg-rose-500" },
	];

	const [currentIndex, setCurrentIndex] = useState(0);
	const [displayText, setDisplayText] = useState("");
	const [isDeleting, setIsDeleting] = useState(false);
	const [showCursor, setShowCursor] = useState(true);

	useEffect(() => {
		const currentQuery = queries[currentIndex];
		const fullText = currentQuery.text;

		const timeout = setTimeout(
			() => {
				if (!isDeleting) {
					if (displayText.length < fullText.length) {
						setDisplayText(fullText.slice(0, displayText.length + 1));
					} else {
						setTimeout(() => setIsDeleting(true), 2000);
					}
				} else {
					if (displayText.length > 0) {
						setDisplayText(displayText.slice(0, -1));
					} else {
						setIsDeleting(false);
						setCurrentIndex((currentIndex + 1) % queries.length);
					}
				}
			},
			isDeleting ? 30 : 50
		);

		return () => clearTimeout(timeout);
	}, [displayText, isDeleting, currentIndex]);

	useEffect(() => {
		const cursorInterval = setInterval(() => {
			setShowCursor((prev) => !prev);
		}, 530);
		return () => clearInterval(cursorInterval);
	}, []);

	const currentQuery = queries[currentIndex];

	return (
		<div className="relative">
			<div className="flex items-center gap-2">
				<span className={cn("rounded px-2 py-0.5 text-xs font-semibold text-white", currentQuery.color)}>
					{currentQuery.badge}
				</span>
				<span className="text-gray-700 dark:text-gray-300">{displayText}</span>
				<span className={cn("inline-block h-5 w-0.5 bg-orange-500", showCursor ? "opacity-100" : "opacity-0")} />
			</div>
		</div>
	);
};

// ==================== SECTION 1: HERO ====================

const HeroSection = () => {
	return (
		<section className="relative min-h-screen overflow-hidden px-4 py-20 md:px-8">
			{/* Gradient background orbs */}
			<div className="pointer-events-none absolute inset-0">
				<div className="absolute left-1/4 top-1/4 h-96 w-96 rounded-full bg-orange-500/20 blur-3xl" />
				<div className="absolute right-1/4 top-1/3 h-96 w-96 rounded-full bg-blue-500/20 blur-3xl" />
				<div className="absolute bottom-1/4 left-1/3 h-96 w-96 rounded-full bg-purple-500/20 blur-3xl" />
			</div>

			{/* Grid pattern overlay */}
			<div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]" />

			{/* Floating particles */}
			<div className="pointer-events-none absolute inset-0">
				{Array.from({ length: 20 }).map((_, i) => (
					<motion.div
						key={i}
						className="absolute h-1 w-1 rounded-full bg-orange-500/30"
						style={{
							left: `${Math.random() * 100}%`,
							top: `${Math.random() * 100}%`,
						}}
						animate={{
							y: [0, -30, 0],
							opacity: [0.3, 0.6, 0.3],
						}}
						transition={{
							duration: 3 + Math.random() * 2,
							repeat: Infinity,
							delay: Math.random() * 2,
						}}
					/>
				))}
			</div>

			<div className="relative z-10 mx-auto max-w-6xl">
				<div className="flex flex-col items-center text-center">
					{/* Section badge */}
					<SectionBadge>
						<div className="h-2 w-2 animate-pulse rounded-full bg-green-500" />
						<span>Sveriges smartaste AI-plattform</span>
					</SectionBadge>

					{/* Main heading */}
					<h1 className="mb-6 text-4xl font-bold tracking-tight md:text-6xl lg:text-7xl">
						<Balancer>
							En fråga.{" "}
							<span className="bg-gradient-to-r from-orange-500 to-amber-500 bg-clip-text text-transparent">
								Alla svar.
							</span>{" "}
							Verifierat.
						</Balancer>
					</h1>

					{/* Animated counters */}
					<div className="mb-8 flex flex-wrap justify-center gap-6 text-sm md:gap-8 md:text-base">
						<div className="text-gray-600 dark:text-gray-400">
							<AnimatedCounter value="12" suffix="+ AI-agenter" />
						</div>
						<div className="text-gray-600 dark:text-gray-400">
							<AnimatedCounter value="7" suffix=" LLM-modeller" />
						</div>
						<div className="text-gray-600 dark:text-gray-400">
							<AnimatedCounter value="20" suffix="+ API-integrationer" />
						</div>
					</div>

					{/* Search bar with typing animation */}
					<div className="relative mb-12 w-full max-w-2xl">
						<div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-2xl dark:border-gray-700 dark:bg-gray-800">
							<TypingAnimation />
						</div>
						{/* Glow effect */}
						<div className="absolute -bottom-4 left-1/2 h-20 w-3/4 -translate-x-1/2 rounded-full bg-orange-500/30 blur-3xl" />
					</div>

					{/* Demo preview */}
					<div className="relative w-full max-w-5xl">
						<div className="overflow-hidden rounded-2xl border border-gray-200 shadow-2xl dark:border-gray-700">
							<Image
								src="/homepage/main_demo.webp"
								alt="OneSeek Demo"
								width={1920}
								height={1080}
								className="w-full"
								priority
							/>
						</div>
						{/* Glow effect under image */}
						<div className="absolute -bottom-8 left-1/2 h-32 w-3/4 -translate-x-1/2 rounded-full bg-blue-500/20 blur-3xl" />
					</div>
				</div>
			</div>
		</section>
	);
};

// ==================== SECTION 2: COMPARE MODE ====================

const AIModelCard = ({
	name,
	provider,
	color,
	icon,
	latency,
	delay = 0,
}: {
	name: string;
	provider: string;
	color: string;
	icon: string;
	latency: string;
	delay?: number;
}) => {
	const [progress, setProgress] = useState(0);
	const ref = useRef(null);
	const isInView = useInView(ref, { once: true });

	useEffect(() => {
		if (isInView) {
			setTimeout(() => {
				const interval = setInterval(() => {
					setProgress((prev) => {
						if (prev >= 100) {
							clearInterval(interval);
							return 100;
						}
						return prev + 2;
					});
				}, 20);
			}, delay);
		}
	}, [isInView, delay]);

	return (
		<motion.div
			ref={ref}
			initial={{ opacity: 1, scale: 1 }}
			animate={isInView ? { opacity: 1, scale: 1 } : { opacity: 1, scale: 1 }}
			transition={{ duration: 0.4, delay: delay / 1000 }}
			whileHover={{ scale: 1.05, y: -5 }}
			className="rounded-xl border border-gray-200 bg-white p-4 shadow-lg dark:border-gray-700 dark:bg-gray-800"
		>
			<div className="flex items-center gap-3">
				<div className={cn("flex h-12 w-12 items-center justify-center rounded-lg text-xl font-bold text-white", color)}>
					{icon}
				</div>
				<div className="flex-1">
					<h3 className="font-semibold text-gray-900 dark:text-white">{name}</h3>
					<p className="text-xs text-gray-500 dark:text-gray-400">{provider}</p>
				</div>
			</div>
			<div className="mt-3">
				<div className="mb-1 h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
					<div className={cn("h-full transition-all duration-300", color)} style={{ width: `${progress}%` }} />
				</div>
				<p className="text-xs text-gray-500 dark:text-gray-400">{latency}</p>
			</div>
		</motion.div>
	);
};

const CompareModeSection = () => {
	const models = [
		{ name: "Grok", provider: "xAI", color: "bg-black", icon: "G", latency: "1.2s" },
		{ name: "Claude", provider: "Anthropic", color: "bg-amber-600", icon: "C", latency: "0.9s" },
		{ name: "ChatGPT", provider: "OpenAI", color: "bg-emerald-600", icon: "G", latency: "1.1s" },
		{ name: "Gemini", provider: "Google", color: "bg-blue-600", icon: "G", latency: "1.0s" },
		{ name: "DeepSeek", provider: "DeepSeek", color: "bg-indigo-600", icon: "D", latency: "1.3s" },
		{ name: "Perplexity", provider: "Perplexity", color: "bg-teal-600", icon: "P", latency: "1.4s" },
		{ name: "Qwen", provider: "Alibaba", color: "bg-violet-600", icon: "Q", latency: "1.5s" },
	];

	return (
		<AnimatedSection className="px-4 py-20 md:px-8">
			<div className="mx-auto max-w-6xl">
				<div className="mb-12 text-center">
					<SectionBadge>
						<span>⚡</span>
						<span>Compare Mode</span>
					</SectionBadge>
					<h2 className="mb-4 text-3xl font-bold md:text-5xl">
						<Balancer>
							7 AI-modeller.{" "}
							<span className="bg-gradient-to-r from-purple-500 to-blue-500 bg-clip-text text-transparent">
								Ett optimerat svar.
							</span>
						</Balancer>
					</h2>
				</div>

				{/* Model cards grid */}
				<div className="mb-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
					{models.map((model, index) => (
						<AIModelCard key={model.name} {...model} delay={index * 100} />
					))}
				</div>

				{/* Convergence visualization */}
				<div className="flex flex-col items-center gap-4">
					<div className="h-16 w-1 bg-gradient-to-b from-purple-500 to-blue-500" />
					<div className="flex items-center gap-2 rounded-full border border-blue-500 bg-blue-500/10 px-4 py-2">
						<span className="text-2xl">⚡</span>
						<span className="font-semibold text-blue-600 dark:text-blue-400">OneSeek Synthesis</span>
					</div>
					<div className="h-16 w-1 bg-gradient-to-b from-blue-500 to-emerald-500" />
					<p className="text-center text-sm text-gray-600 dark:text-gray-400">
						Verifierat med Tavily • Citations [1-7] • Faktakontrollerat
					</p>
				</div>
			</div>
		</AnimatedSection>
	);
};

// ==================== SECTION 3: DEBATT-LÄGE ====================

const DebattSection = () => {
	const ref = useRef(null);
	const isInView = useInView(ref, { once: true });

	return (
		<AnimatedSection className="px-4 py-20 md:px-8">
			<div className="mx-auto max-w-6xl">
				<div className="mb-12 text-center">
					<SectionBadge>
						<span>🏛️</span>
						<span>Debatt-läge</span>
					</SectionBadge>
					<h2 className="mb-4 text-3xl font-bold md:text-5xl">
						<Balancer>
							<span className="bg-gradient-to-r from-amber-500 to-orange-500 bg-clip-text text-transparent">
								Riksdagsdata i realtid
							</span>
						</Balancer>
					</h2>
				</div>

				{/* Amber gradient background */}
				<div className="relative rounded-3xl bg-gradient-to-br from-amber-50 to-orange-50 p-8 dark:from-amber-950/20 dark:to-orange-950/20">
					<div ref={ref} className="flex flex-col items-center gap-8 lg:flex-row lg:items-center lg:justify-center">
						{/* Proposition card */}
						<motion.div
							initial={{ opacity: 1, x: 0 }}
							animate={isInView ? { opacity: 1, x: 0 } : { opacity: 1, x: 0 }}
							transition={{ duration: 0.6 }}
							className="w-full max-w-sm rounded-xl border border-blue-200 bg-white p-6 shadow-lg dark:border-blue-800 dark:bg-gray-800"
						>
							<div className="mb-4 flex items-center gap-3">
								<div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-900">
									<span className="text-xl">📄</span>
								</div>
								<div>
									<h3 className="font-semibold text-blue-900 dark:text-blue-300">Proposition 2024/25:142</h3>
									<p className="text-sm text-gray-600 dark:text-gray-400">Förstärkt klimatlag</p>
								</div>
							</div>
							<div className="mb-4 space-y-2">
								<div className="h-2 w-full rounded bg-gray-200 dark:bg-gray-700" />
								<div className="h-2 w-5/6 rounded bg-gray-200 dark:bg-gray-700" />
								<div className="h-2 w-4/6 rounded bg-gray-200 dark:bg-gray-700" />
							</div>
							<div className="flex gap-2">
								<span className="rounded-full bg-green-100 px-3 py-1 text-sm font-semibold text-green-700 dark:bg-green-900 dark:text-green-300">
									JA: 215
								</span>
								<span className="rounded-full bg-red-100 px-3 py-1 text-sm font-semibold text-red-700 dark:bg-red-900 dark:text-red-300">
									NEJ: 134
								</span>
							</div>
						</motion.div>

						{/* VS badge */}
						<motion.div
							initial={{ scale: 1 }}
							animate={isInView ? { scale: 1 } : { scale: 1 }}
							transition={{ type: "spring", delay: 0.3 }}
							className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-full border-4 border-amber-500 bg-white text-2xl font-bold text-amber-600 shadow-lg dark:bg-gray-800 dark:text-amber-400"
						>
							VS
						</motion.div>

						{/* Motion card */}
						<motion.div
							initial={{ opacity: 1, x: 0 }}
							animate={isInView ? { opacity: 1, x: 0 } : { opacity: 1, x: 0 }}
							transition={{ duration: 0.6 }}
							className="w-full max-w-sm rounded-xl border border-rose-200 bg-white p-6 shadow-lg dark:border-rose-800 dark:bg-gray-800"
						>
							<div className="mb-4 flex items-center gap-3">
								<div className="flex h-10 w-10 items-center justify-center rounded-lg bg-rose-100 dark:bg-rose-900">
									<span className="text-xl">✏️</span>
								</div>
								<div>
									<h3 className="font-semibold text-rose-900 dark:text-rose-300">Motion 2024/25:3847</h3>
									<p className="text-sm text-gray-600 dark:text-gray-400">Utökad skattereform</p>
								</div>
							</div>
							<div className="mb-4 space-y-2">
								<div className="h-2 w-full rounded bg-gray-200 dark:bg-gray-700" />
								<div className="h-2 w-5/6 rounded bg-gray-200 dark:bg-gray-700" />
								<div className="h-2 w-4/6 rounded bg-gray-200 dark:bg-gray-700" />
							</div>
							<div className="flex gap-2">
								<span className="rounded-full bg-blue-100 px-3 py-1 text-sm font-semibold text-blue-700 dark:bg-blue-900 dark:text-blue-300">
									Utskott: FiU
								</span>
								<span className="rounded-full bg-purple-100 px-3 py-1 text-sm font-semibold text-purple-700 dark:bg-purple-900 dark:text-purple-300">
									8 ledamöter
								</span>
							</div>
						</motion.div>
					</div>
				</div>
			</div>
		</AnimatedSection>
	);
};

// ==================== SECTION 4: SVERIGE-SPECIFIKA INTEGRATIONER ====================

const IntegrationLogo = ({ emoji, name, delay = 0 }: { emoji: string; name: string; delay?: number }) => {
	const ref = useRef(null);
	const isInView = useInView(ref, { once: true });

	return (
		<motion.div
			ref={ref}
			initial={{ opacity: 1, scale: 1 }}
			animate={isInView ? { opacity: 1, scale: 1 } : { opacity: 1, scale: 1 }}
			transition={{ duration: 0.4, delay: delay / 1000 }}
			whileHover={{ scale: 1.1 }}
			className="flex flex-col items-center gap-2"
		>
			<div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-gray-200 bg-white text-3xl shadow-md dark:border-gray-700 dark:bg-gray-800">
				{emoji}
			</div>
			<span className="text-sm font-medium text-gray-700 dark:text-gray-300">{name}</span>
		</motion.div>
	);
};

const IntegrationsSection = () => {
	const integrations = [
		{ emoji: "📊", name: "SCB" },
		{ emoji: "🌤️", name: "SMHI" },
		{ emoji: "🚗", name: "Trafikverket" },
		{ emoji: "🏢", name: "Bolagsverket" },
		{ emoji: "🏛️", name: "Riksdagen" },
		{ emoji: "📈", name: "Kolada" },
		{ emoji: "🔍", name: "Tavily" },
		{ emoji: "🗺️", name: "Geoapify" },
		{ emoji: "🤖", name: "OpenAI" },
		{ emoji: "🧠", name: "Anthropic" },
		{ emoji: "✨", name: "Google AI" },
		{ emoji: "⚡", name: "xAI" },
	];

	const categories = [
		{
			title: "Kunskap & Sökning",
			gradient: "from-blue-500 to-purple-500",
			emoji: "🔍",
		},
		{
			title: "Statistik & Data",
			gradient: "from-emerald-500 to-teal-500",
			emoji: "📊",
		},
		{
			title: "Realtid & Väder",
			gradient: "from-amber-500 to-orange-500",
			emoji: "⚡",
		},
	];

	return (
		<AnimatedSection className="px-4 py-20 md:px-8">
			<div className="mx-auto max-w-6xl">
				<div className="mb-12 text-center">
					<SectionBadge>
						<span>🇸🇪</span>
						<span>Svenska Integrationer</span>
					</SectionBadge>
					<h2 className="mb-4 text-3xl font-bold md:text-5xl">
						<Balancer>
							<span className="bg-gradient-to-r from-blue-500 to-yellow-500 bg-clip-text text-transparent">
								Direkt kopplat till Sveriges datakällor
							</span>
						</Balancer>
					</h2>
				</div>

				{/* Integration logos */}
				<div className="mb-12 grid grid-cols-3 gap-6 sm:grid-cols-4 md:grid-cols-6">
					{integrations.map((integration, index) => (
						<IntegrationLogo key={integration.name} {...integration} delay={index * 50} />
					))}
				</div>

				{/* Category cards */}
				<div className="grid gap-6 md:grid-cols-3">
					{categories.map((category, index) => (
						<motion.div
							key={category.title}
							initial={{ opacity: 1, y: 0 }}
							whileInView={{ opacity: 1, y: 0 }}
							viewport={{ once: true }}
							transition={{ duration: 0.5, delay: index * 0.1 }}
							className={cn(
								"rounded-2xl bg-gradient-to-br p-6 text-white shadow-xl",
								category.gradient
							)}
						>
							<div className="mb-4 text-4xl">{category.emoji}</div>
							<h3 className="text-xl font-bold">{category.title}</h3>
						</motion.div>
					))}
				</div>
			</div>
		</AnimatedSection>
	);
};

// ==================== SECTION 5: LANGGRAPH PIPELINE ====================

const PipelineNode = ({ emoji, label, delay = 0 }: { emoji: string; label: string; delay?: number }) => {
	const ref = useRef(null);
	const isInView = useInView(ref, { once: true });

	return (
		<motion.div
			ref={ref}
			initial={{ opacity: 1, scale: 1 }}
			animate={isInView ? { opacity: 1, scale: 1 } : { opacity: 1, scale: 1 }}
			transition={{ duration: 0.4, delay: delay / 1000 }}
			className="flex flex-col items-center gap-2"
		>
			<div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-orange-500 to-rose-500 text-3xl shadow-lg">
				{emoji}
			</div>
			<span className="text-center text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
		</motion.div>
	);
};

const PipelineArrow = () => {
	return <div className="hidden h-1 w-8 bg-gray-300 dark:bg-gray-600 md:block" />;
};

const PipelineSection = () => {
	const pipeline = [
		{ emoji: "💬", label: "Din fråga" },
		{ emoji: "🔀", label: "Intent Router" },
		{ emoji: "🎯", label: "Agent Resolver" },
		{ emoji: "📋", label: "Planner" },
		{ emoji: "⚙️", label: "Executor" },
		{ emoji: "🔍", label: "Critic" },
		{ emoji: "✅", label: "Svar" },
	];

	const agents = [
		{ emoji: "📚", name: "Knowledge" },
		{ emoji: "🌤️", name: "Weather" },
		{ emoji: "🚦", name: "Trafik" },
		{ emoji: "📊", name: "Statistics" },
		{ emoji: "🗺️", name: "Kartor" },
		{ emoji: "🏢", name: "Bolag" },
		{ emoji: "🏛️", name: "Riksdagen" },
		{ emoji: "🌐", name: "Browser" },
		{ emoji: "🎙️", name: "Media" },
		{ emoji: "💻", name: "Code" },
		{ emoji: "⚡", name: "Action" },
		{ emoji: "🧬", name: "Synthesis" },
	];

	return (
		<AnimatedSection className="px-4 py-20 md:px-8">
			<div className="mx-auto max-w-6xl">
				<div className="mb-12 text-center">
					<SectionBadge>
						<span>🧠</span>
						<span>LangGraph Pipeline</span>
					</SectionBadge>
					<h2 className="mb-4 text-3xl font-bold md:text-5xl">
						<Balancer>
							<span className="bg-gradient-to-r from-orange-500 to-rose-500 bg-clip-text text-transparent">
								Så fungerar OneSeek
							</span>
						</Balancer>
					</h2>
				</div>

				{/* Pipeline flow */}
				<div className="mb-12 flex flex-wrap items-center justify-center gap-4">
					{pipeline.map((node, index) => (
						<React.Fragment key={node.label}>
							<PipelineNode {...node} delay={index * 100} />
							{index < pipeline.length - 1 && <PipelineArrow />}
						</React.Fragment>
					))}
				</div>

				{/* Agent badges */}
				<div className="rounded-2xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
					<h3 className="mb-6 text-center text-xl font-semibold">12 Specialiserade Agenter</h3>
					<div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
						{agents.map((agent, index) => (
							<motion.div
								key={agent.name}
								initial={{ opacity: 1, scale: 1 }}
								whileInView={{ opacity: 1, scale: 1 }}
								viewport={{ once: true }}
								transition={{ duration: 0.3, delay: index * 0.05 }}
								className="flex flex-col items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900"
							>
								<span className="text-2xl">{agent.emoji}</span>
								<span className="text-xs font-medium text-gray-700 dark:text-gray-300">{agent.name}</span>
							</motion.div>
						))}
					</div>
				</div>
			</div>
		</AnimatedSection>
	);
};

// ==================== SECTION 6: LLM PROVIDERS ====================

const LLMProvidersSection = () => {
	const providers = [
		"OpenAI",
		"Anthropic",
		"Google",
		"xAI",
		"DeepSeek",
		"Perplexity",
		"Qwen",
		"OpenRouter",
		"Groq",
		"Together",
		"Azure",
		"Mistral",
		"Cohere",
		"Fireworks",
		"Cerebras",
		"DeepInfra",
		"Replicate",
		"Ollama",
	];

	return (
		<AnimatedSection className="px-4 py-20 md:px-8">
			<div className="mx-auto max-w-6xl">
				<div className="mb-12 text-center">
					<SectionBadge>
						<span>🔌</span>
						<span>LLM Providers</span>
					</SectionBadge>
					<h2 className="mb-4 text-3xl font-bold md:text-5xl">
						<Balancer>
							<span className="bg-gradient-to-r from-violet-500 to-fuchsia-500 bg-clip-text text-transparent">
								Stöd för 20+ LLM-providers
							</span>
						</Balancer>
					</h2>
				</div>

				<div className="flex flex-wrap justify-center gap-3">
					{providers.map((provider, index) => (
						<motion.span
							key={provider}
							initial={{ opacity: 1, scale: 1 }}
							whileInView={{ opacity: 1, scale: 1 }}
							viewport={{ once: true }}
							transition={{ duration: 0.3, delay: index * 0.03 }}
							whileHover={{ scale: 1.1, y: -2 }}
							className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-md transition-colors hover:border-violet-500 hover:bg-violet-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:border-violet-500 dark:hover:bg-violet-950"
						>
							{provider}
						</motion.span>
					))}
				</div>
			</div>
		</AnimatedSection>
	);
};

// ==================== SECTION 7: CTA ====================

const CTASection = () => {
	return (
		<section className="relative overflow-hidden bg-gradient-to-b from-gray-900 to-black px-4 py-20 text-white md:px-8">
			{/* Background orbs */}
			<div className="pointer-events-none absolute inset-0">
				<div className="absolute left-1/4 top-1/2 h-96 w-96 rounded-full bg-orange-500/20 blur-3xl" />
				<div className="absolute right-1/4 top-1/3 h-96 w-96 rounded-full bg-blue-500/20 blur-3xl" />
			</div>

			<div className="relative z-10 mx-auto max-w-4xl text-center">
				<div className="mb-8 flex justify-center">
					<Logo className="h-16 w-16" />
				</div>

				<h2 className="mb-6 text-3xl font-bold md:text-5xl">
					<Balancer>
						Redo att{" "}
						<span className="bg-gradient-to-r from-orange-500 to-amber-500 bg-clip-text text-transparent">
							söka smartare?
						</span>
					</Balancer>
				</h2>

				<p className="mb-8 text-lg text-gray-300">
					Upplev Sveriges mest avancerade AI-sökplattform. Få verifierade svar från 7 LLM-modeller och 20+ datakällor.
				</p>

				<div className="flex flex-col justify-center gap-4 sm:flex-row">
					<motion.div whileHover={{ scale: 1.05, y: -2 }} whileTap={{ scale: 0.95 }}>
						<Link
							href="/dashboard/public/new-chat"
							className="inline-block rounded-full bg-white px-8 py-3 font-semibold text-gray-900 shadow-lg transition-shadow hover:shadow-xl"
						>
							Kom igång nu
						</Link>
					</motion.div>
					<motion.div whileHover={{ scale: 1.05, y: -2 }} whileTap={{ scale: 0.95 }}>
						<Link
							href="/contact"
							className="inline-block rounded-full border-2 border-white px-8 py-3 font-semibold text-white transition-colors hover:bg-white hover:text-gray-900"
						>
							Kontakta oss
						</Link>
					</motion.div>
				</div>
			</div>
		</section>
	);
};

// ==================== MAIN PAGE COMPONENT ====================

export default function LandingPageMockup() {
	return (
		<main className="min-h-screen bg-white text-gray-900 dark:bg-gray-950 dark:text-white">
			<HeroSection />
			<CompareModeSection />
			<DebattSection />
			<IntegrationsSection />
			<PipelineSection />
			<LLMProvidersSection />
			<CTASection />
		</main>
	);
}
