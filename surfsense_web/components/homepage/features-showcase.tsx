"use client";

import { motion, useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { cn } from "@/lib/utils";

/* ════════════════════════════════════════════════════════════════
   1. TIME CAPSULE
   ════════════════════════════════════════════════════════════════ */

const TIMELINE_EVENTS = [
	{ date: "2025-01-15", label: "tc_event_1", drift: 0 },
	{ date: "2025-03-22", label: "tc_event_2", drift: 12 },
	{ date: "2025-06-08", label: "tc_event_3", drift: 28 },
	{ date: "2025-09-14", label: "tc_event_4", drift: 45 },
	{ date: "2025-12-01", label: "tc_event_5", drift: 67 },
	{ date: "2026-02-20", label: "tc_event_6", drift: 91 },
];

function DriftMeter({ value, active }: { value: number; active: boolean }) {
	const color = value < 20 ? "bg-emerald-500" : value < 50 ? "bg-amber-500" : "bg-rose-500";
	return (
		<div className="flex items-center gap-2">
			<div className="w-16 h-1.5 rounded-full bg-neutral-200 dark:bg-neutral-800/50 overflow-hidden">
				<motion.div
					className={cn("h-full rounded-full", color)}
					initial={{ width: 0 }}
					animate={active ? { width: `${value}%` } : { width: 0 }}
					transition={{ duration: 0.8, ease: "easeOut" }}
				/>
			</div>
			<span
				className={cn(
					"text-[10px] font-mono tabular-nums",
					value < 20
						? "text-emerald-600 dark:text-emerald-400"
						: value < 50
							? "text-amber-600 dark:text-amber-400"
							: "text-rose-600 dark:text-rose-400"
				)}
			>
				{active ? `${value}%` : "—"}
			</span>
		</div>
	);
}

export function TimeCapsule() {
	const t = useTranslations("homepage");
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.15 });
	const [activeEvent, setActiveEvent] = useState(-1);

	useEffect(() => {
		if (!isInView) return;
		let step = 0;
		const interval = setInterval(() => {
			if (step < TIMELINE_EVENTS.length) {
				setActiveEvent(step);
				step++;
			} else {
				clearInterval(interval);
			}
		}, 400);
		return () => clearInterval(interval);
	}, [isInView]);

	return (
		<section
			ref={ref}
			className="relative py-20 md:py-28 overflow-hidden border-t border-neutral-100 dark:border-neutral-800/50"
		>
			{/* Background */}
			<div className="absolute inset-0 -z-10">
				<div className="absolute top-1/3 left-1/4 w-[500px] h-[400px] bg-[radial-gradient(circle,rgba(59,130,246,0.06),transparent_60%)] dark:bg-[radial-gradient(circle,rgba(59,130,246,0.1),transparent_60%)]" />
				<div className="absolute bottom-1/4 right-1/4 w-[400px] h-[300px] bg-[radial-gradient(circle,rgba(139,92,246,0.04),transparent_60%)] dark:bg-[radial-gradient(circle,rgba(139,92,246,0.08),transparent_60%)]" />
			</div>

			<div className="mx-auto max-w-6xl px-6">
				<div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
					{/* Left — text content */}
					<motion.div
						initial={{ opacity: 0, x: -30 }}
						animate={isInView ? { opacity: 1, x: 0 } : {}}
						transition={{ duration: 0.6 }}
					>
						<span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-xs font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider mb-5">
							<svg
								className="w-3.5 h-3.5"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								strokeWidth={2}
							>
								<path
									strokeLinecap="round"
									strokeLinejoin="round"
									d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"
								/>
							</svg>
							Time Capsule
						</span>
						<h2 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white leading-[1.1] mb-6">
							{t("tc_title")}
						</h2>
						<p className="text-base md:text-lg text-neutral-500 dark:text-neutral-400 leading-relaxed mb-8">
							{t("tc_description")}
						</p>

						{/* Key points */}
						<div className="space-y-4">
							{(["tc_point_1", "tc_point_2", "tc_point_3"] as const).map((key, i) => (
								<motion.div
									key={key}
									className="flex items-start gap-3"
									initial={{ opacity: 0, x: -10 }}
									animate={isInView ? { opacity: 1, x: 0 } : {}}
									transition={{ delay: 0.3 + i * 0.1, duration: 0.4 }}
								>
									<div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
									<span className="text-sm text-neutral-600 dark:text-neutral-300">{t(key)}</span>
								</motion.div>
							))}
						</div>
					</motion.div>

					{/* Right — interactive timeline visualization */}
					<motion.div
						initial={{ opacity: 0, x: 30 }}
						animate={isInView ? { opacity: 1, x: 0 } : {}}
						transition={{ duration: 0.6, delay: 0.2 }}
						className="relative"
					>
						<div className="rounded-2xl border border-neutral-200/60 dark:border-neutral-800/60 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-sm p-6 overflow-hidden shadow-lg shadow-neutral-200/50 dark:shadow-none">
							{/* Header */}
							<div className="flex items-center justify-between mb-5">
								<span className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
									{t("tc_timeline_header")}
								</span>
								<span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-600">
									{t("tc_drift_label")}
								</span>
							</div>

							{/* Timeline */}
							<div className="relative">
								{/* Vertical line */}
								<div className="absolute left-[7px] top-2 bottom-2 w-px bg-neutral-200 dark:bg-neutral-800" />

								<div className="space-y-5">
									{TIMELINE_EVENTS.map((event, i) => {
										const isActive = i <= activeEvent;
										const isCurrent = i === activeEvent;
										return (
											<motion.div
												key={event.date}
												className="relative flex items-start gap-4 pl-6"
												initial={{ opacity: 0.2 }}
												animate={isActive ? { opacity: 1 } : { opacity: 0.2 }}
												transition={{ duration: 0.3 }}
											>
												{/* Dot on timeline */}
												<div className="absolute left-0 top-1.5">
													<motion.div
														className="w-[15px] h-[15px] rounded-full border-2 flex items-center justify-center"
														style={{
															borderColor: isActive ? "#3b82f6" : "var(--dot-inactive, #d4d4d4)",
															background: isCurrent ? "#3b82f6" : "transparent",
														}}
														animate={
															isCurrent
																? {
																		boxShadow: [
																			"0 0 0px rgba(59,130,246,0)",
																			"0 0 10px rgba(59,130,246,0.4)",
																			"0 0 0px rgba(59,130,246,0)",
																		],
																	}
																: { boxShadow: "none" }
														}
														transition={
															isCurrent ? { duration: 1.5, repeat: Number.POSITIVE_INFINITY } : {}
														}
													>
														{isCurrent && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
													</motion.div>
												</div>

												<div className="flex-1 min-w-0">
													<div className="flex items-center justify-between gap-3">
														<div>
															<span className="text-[11px] font-mono text-neutral-400 dark:text-neutral-500 block">
																{event.date}
															</span>
															<span
																className={cn(
																	"text-xs font-medium",
																	isActive
																		? "text-neutral-800 dark:text-neutral-200"
																		: "text-neutral-400 dark:text-neutral-600"
																)}
															>
																{t(event.label)}
															</span>
														</div>
														<DriftMeter value={event.drift} active={isActive} />
													</div>
												</div>
											</motion.div>
										);
									})}
								</div>
							</div>

							{/* Alert bar */}
							<motion.div
								className="mt-5 rounded-lg bg-rose-500/10 border border-rose-500/20 px-3 py-2 flex items-center gap-2"
								initial={{ opacity: 0, y: 5 }}
								animate={
									activeEvent >= TIMELINE_EVENTS.length - 1
										? { opacity: 1, y: 0 }
										: { opacity: 0, y: 5 }
								}
								transition={{ duration: 0.4 }}
							>
								<svg
									className="w-3.5 h-3.5 text-rose-500 dark:text-rose-400 shrink-0"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									strokeWidth={2}
								>
									<path
										strokeLinecap="round"
										strokeLinejoin="round"
										d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
									/>
								</svg>
								<span className="text-[11px] text-rose-600 dark:text-rose-300 font-medium">
									{t("tc_alert")}
								</span>
							</motion.div>
						</div>
					</motion.div>
				</div>
			</div>
		</section>
	);
}

/* ════════════════════════════════════════════════════════════════
   2. DEBATE SHOWCASE
   ════════════════════════════════════════════════════════════════ */

const DEBATE_PARTICIPANTS = [
	{ key: "grok", name: "Grok", color: "#1a1a2e", logo: "/model-logos/grok.png" },
	{ key: "claude", name: "Claude", color: "#d4a574", logo: "/model-logos/claude.png" },
	{ key: "gpt", name: "ChatGPT", color: "#10a37f", logo: "/model-logos/chatgpt.png" },
	{ key: "gemini", name: "Gemini", color: "#4285f4", logo: "/model-logos/gemini.png" },
	{ key: "deepseek", name: "DeepSeek", color: "#0066ff", logo: "/model-logos/deepseek.png" },
	{ key: "perplexity", name: "Perplexity", color: "#20b2aa", logo: "/model-logos/perplexity.png" },
	{ key: "qwen", name: "Qwen", color: "#7c3aed", logo: "/model-logos/qwen.png" },
	{ key: "oneseek", name: "OneSeek", color: "#6366f1", logo: null },
];

const DEBATE_ROUNDS = [
	{ num: 1, labelKey: "debate_round_1" },
	{ num: 2, labelKey: "debate_round_2" },
	{ num: 3, labelKey: "debate_round_3" },
	{ num: 4, labelKey: "debate_round_4" },
];

const DEBATE_DIALOGUE = [
	{ speaker: 2, key: "debate_line_1" },
	{ speaker: 1, key: "debate_line_2" },
	{ speaker: 4, key: "debate_line_3" },
	{ speaker: 0, key: "debate_line_4" },
	{ speaker: 7, key: "debate_line_5" },
];

const VOTE_RESULTS = [
	{ participant: 1, votes: 5 },
	{ participant: 2, votes: 1 },
	{ participant: 4, votes: 1 },
	{ participant: 7, votes: 1 },
];

function WaveformBar({ active, color, delay }: { active: boolean; color: string; delay: number }) {
	return (
		<motion.div
			className="w-[3px] rounded-full"
			style={{ background: color }}
			animate={
				active
					? {
							height: [4, 16, 8, 20, 6, 14, 4],
						}
					: { height: 4 }
			}
			transition={
				active
					? {
							duration: 1.2,
							delay,
							repeat: Number.POSITIVE_INFINITY,
							ease: "easeInOut",
						}
					: { duration: 0.3 }
			}
		/>
	);
}

export function DebateShowcase() {
	const t = useTranslations("homepage");
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.15 });
	const [activeRound, setActiveRound] = useState(-1);
	const [activeLine, setActiveLine] = useState(-1);
	const [showVotes, setShowVotes] = useState(false);
	const [showWinner, setShowWinner] = useState(false);
	const [isVoiceActive, setIsVoiceActive] = useState(false);

	useEffect(() => {
		if (!isInView) return;
		const startDelay = setTimeout(() => {
			let round = 0;
			const roundInterval = setInterval(() => {
				if (round < 4) {
					setActiveRound(round);
					round++;
				} else {
					clearInterval(roundInterval);
				}
			}, 800);

			setTimeout(() => {
				setIsVoiceActive(true);
				let line = 0;
				const lineInterval = setInterval(() => {
					if (line < DEBATE_DIALOGUE.length) {
						setActiveLine(line);
						line++;
					} else {
						clearInterval(lineInterval);
						setTimeout(() => {
							setShowVotes(true);
							setTimeout(() => setShowWinner(true), 600);
						}, 500);
					}
				}, 900);
			}, 2400);
		}, 400);
		return () => clearTimeout(startDelay);
	}, [isInView]);

	const winner = DEBATE_PARTICIPANTS[1];

	return (
		<section
			ref={ref}
			className="relative py-20 md:py-28 overflow-hidden border-t border-neutral-100 dark:border-neutral-800/50"
		>
			{/* Background */}
			<div className="absolute inset-0 -z-10">
				<div className="absolute top-0 right-1/4 w-[500px] h-[400px] bg-[radial-gradient(circle,rgba(99,102,241,0.06),transparent_60%)] dark:bg-[radial-gradient(circle,rgba(99,102,241,0.12),transparent_60%)]" />
				<div className="absolute bottom-0 left-1/3 w-[400px] h-[300px] bg-[radial-gradient(circle,rgba(212,165,116,0.06),transparent_60%)] dark:bg-[radial-gradient(circle,rgba(212,165,116,0.1),transparent_60%)]" />
			</div>

			<div className="mx-auto max-w-6xl px-6">
				<div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
					{/* Left — debate arena visualization */}
					<motion.div
						initial={{ opacity: 0, x: -30 }}
						animate={isInView ? { opacity: 1, x: 0 } : {}}
						transition={{ duration: 0.6, delay: 0.2 }}
						className="order-2 md:order-1"
					>
						<div className="rounded-2xl border border-neutral-200/50 dark:border-neutral-800/60 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-sm overflow-hidden shadow-lg shadow-neutral-200/50 dark:shadow-none">
							{/* Header with topic + voice toggle */}
							<div className="px-5 py-4 border-b border-neutral-100 dark:border-neutral-800/50">
								<div className="flex items-center justify-between mb-3">
									<div>
										<p className="text-xs font-semibold text-neutral-800 dark:text-neutral-200">
											{t("debate_topic")}
										</p>
										<p className="text-[10px] text-neutral-500 dark:text-neutral-400 mt-0.5">
											8 {t("debate_voices_label")} · 4 {t("debate_rounds_label")}
										</p>
									</div>
									<motion.div
										className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20"
										animate={
											isVoiceActive
												? {
														borderColor: [
															"rgba(99,102,241,0.2)",
															"rgba(99,102,241,0.5)",
															"rgba(99,102,241,0.2)",
														],
													}
												: {}
										}
										transition={
											isVoiceActive ? { duration: 2, repeat: Number.POSITIVE_INFINITY } : {}
										}
									>
										<svg
											className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400"
											fill="none"
											viewBox="0 0 24 24"
											stroke="currentColor"
											strokeWidth={2}
										>
											<title>Voice mode</title>
											<path
												strokeLinecap="round"
												strokeLinejoin="round"
												d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z"
											/>
										</svg>
										<span className="text-[10px] font-semibold text-indigo-600 dark:text-indigo-400">
											{t("debate_voice_label")}
										</span>
									</motion.div>
								</div>

								{/* Round tabs */}
								<div className="flex gap-1">
									{DEBATE_ROUNDS.map((round, i) => {
										const isActive = i <= activeRound;
										const isCurrent = i === activeRound;
										return (
											<motion.div
												key={round.num}
												className={cn(
													"flex-1 py-1.5 px-2 rounded-md text-center text-[10px] font-semibold transition-all duration-300 border",
													isCurrent
														? "bg-indigo-500/15 border-indigo-500/30 text-indigo-600 dark:text-indigo-400"
														: isActive
															? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400"
															: "bg-neutral-50 dark:bg-neutral-800/40 border-neutral-200/30 dark:border-neutral-700/30 text-neutral-400 dark:text-neutral-600"
												)}
												initial={{ opacity: 0.4 }}
												animate={isActive ? { opacity: 1 } : { opacity: 0.4 }}
												transition={{ duration: 0.3 }}
											>
												<span className="hidden sm:inline">{t(round.labelKey)}</span>
												<span className="sm:hidden">R{round.num}</span>
												{isActive && !isCurrent && <span className="ml-1 inline-block">✓</span>}
											</motion.div>
										);
									})}
								</div>
							</div>

							{/* 8 participants grid */}
							<div className="px-5 pt-3 pb-2">
								<div className="grid grid-cols-4 gap-2">
									{DEBATE_PARTICIPANTS.map((p, i) => (
										<motion.div
											key={p.key}
											className="flex flex-col items-center gap-1"
											initial={{ opacity: 0, scale: 0.8 }}
											animate={isInView ? { opacity: 1, scale: 1 } : {}}
											transition={{ delay: 0.3 + i * 0.06, duration: 0.3 }}
										>
											<div
												className="w-8 h-8 rounded-full overflow-hidden bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center ring-2 ring-offset-1 ring-offset-white dark:ring-offset-neutral-900 transition-all duration-300"
												style={{ borderColor: p.color, boxShadow: `0 0 0 2px ${p.color}30` }}
											>
												{p.logo ? (
													<Image
														src={p.logo}
														alt={p.name}
														width={32}
														height={32}
														className="object-contain w-full h-full"
													/>
												) : (
													<div
														className="w-full h-full flex items-center justify-center text-[9px] font-bold text-white"
														style={{
															background: `linear-gradient(135deg, ${p.color}, ${p.color}cc)`,
														}}
													>
														OS
													</div>
												)}
											</div>
											<span className="text-[9px] font-medium text-neutral-500 dark:text-neutral-400 truncate max-w-full">
												{p.name}
											</span>
										</motion.div>
									))}
								</div>
							</div>

							{/* Dialogue lines */}
							<div className="px-5 py-3 space-y-2.5 min-h-[180px]">
								{DEBATE_DIALOGUE.map((line, i) => {
									const speaker = DEBATE_PARTICIPANTS[line.speaker];
									const isActive = i <= activeLine;
									return (
										<motion.div
											key={line.key}
											className="flex items-start gap-2.5"
											initial={{ opacity: 0, y: 8 }}
											animate={isActive ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
											transition={{ duration: 0.3 }}
										>
											<div className="w-5 h-5 rounded-full overflow-hidden shrink-0 mt-0.5 bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
												{speaker.logo ? (
													<Image
														src={speaker.logo}
														alt={speaker.name}
														width={20}
														height={20}
														className="object-contain w-full h-full"
													/>
												) : (
													<div
														className="w-full h-full flex items-center justify-center text-[7px] font-bold text-white"
														style={{ background: speaker.color }}
													>
														OS
													</div>
												)}
											</div>
											<div className="min-w-0 flex-1">
												<span
													className="text-[10px] font-semibold"
													style={{ color: speaker.color }}
												>
													{speaker.name}
												</span>
												<p className="text-[11px] text-neutral-600 dark:text-neutral-300 leading-relaxed">
													{t(line.key)}
												</p>
											</div>
										</motion.div>
									);
								})}
							</div>

							{/* Vote result + winner */}
							<motion.div
								className="px-5 pb-4"
								initial={{ opacity: 0, height: 0 }}
								animate={showVotes ? { opacity: 1, height: "auto" } : { opacity: 0, height: 0 }}
								transition={{ duration: 0.4 }}
							>
								<div className="rounded-lg bg-neutral-50 dark:bg-neutral-800/40 border border-neutral-200/30 dark:border-neutral-700/30 p-3 mb-2">
									<div className="flex items-center gap-2 mb-2">
										<span className="text-[10px] font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
											{t("debate_votes_label")}
										</span>
									</div>
									<div className="flex gap-1 h-3 rounded-full overflow-hidden bg-neutral-200/50 dark:bg-neutral-700/30">
										{VOTE_RESULTS.map((v) => {
											const p = DEBATE_PARTICIPANTS[v.participant];
											return (
												<motion.div
													key={p.key}
													className="h-full rounded-full"
													style={{ background: p.color }}
													initial={{ width: 0 }}
													animate={showVotes ? { width: `${(v.votes / 8) * 100}%` } : { width: 0 }}
													transition={{ duration: 0.6, delay: 0.2 }}
												/>
											);
										})}
									</div>
									<div className="flex gap-3 mt-1.5">
										{VOTE_RESULTS.map((v) => {
											const p = DEBATE_PARTICIPANTS[v.participant];
											return (
												<span
													key={p.key}
													className="text-[9px] text-neutral-500 dark:text-neutral-400"
												>
													<span style={{ color: p.color }} className="font-semibold">
														{p.name}
													</span>{" "}
													{v.votes}
												</span>
											);
										})}
									</div>
								</div>

								{/* Winner banner */}
								<motion.div
									className="rounded-lg bg-gradient-to-r from-amber-500/10 via-yellow-500/10 to-amber-500/10 border border-amber-500/20 px-3 py-2.5 flex items-center gap-2.5"
									initial={{ opacity: 0, scale: 0.95 }}
									animate={showWinner ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.95 }}
									transition={{ duration: 0.4, type: "spring" }}
								>
									<span className="text-base">🏆</span>
									<div>
										<span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-wider block">
											{t("debate_winner_label")}
										</span>
										<span className="text-xs font-bold" style={{ color: winner.color }}>
											{winner.name}
										</span>
										<span className="text-[10px] text-neutral-500 dark:text-neutral-400 ml-1.5">
											5/8 {t("debate_votes_label").toLowerCase()}
										</span>
									</div>
								</motion.div>
							</motion.div>

							{/* Voice waveform bar */}
							<motion.div
								className="px-5 pb-4"
								initial={{ opacity: 0 }}
								animate={isVoiceActive ? { opacity: 1 } : { opacity: 0 }}
								transition={{ duration: 0.3 }}
							>
								<div className="flex items-center gap-3 rounded-lg bg-indigo-500/5 border border-indigo-500/15 px-3 py-2">
									<motion.div
										className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-md shadow-indigo-500/20 shrink-0"
										animate={isVoiceActive ? { scale: [1, 1.08, 1] } : {}}
										transition={
											isVoiceActive ? { duration: 2, repeat: Number.POSITIVE_INFINITY } : {}
										}
									>
										<div className="flex items-center gap-0.5">
											<div className="w-[2px] h-2 bg-white rounded-full" />
											<div className="w-[2px] h-2 bg-white rounded-full" />
										</div>
									</motion.div>
									<div className="flex items-end gap-[2px] h-4 flex-1">
										{Array.from({ length: 32 }).map((_, i) => {
											const p = DEBATE_PARTICIPANTS[i % DEBATE_PARTICIPANTS.length];
											return (
												<WaveformBar
													key={`wave-${i}`}
													active={isVoiceActive}
													color={p.color}
													delay={i * 0.04}
												/>
											);
										})}
									</div>
									<span className="text-[9px] text-indigo-500 dark:text-indigo-400 font-mono shrink-0">
										MP3
									</span>
								</div>
							</motion.div>
						</div>
					</motion.div>

					{/* Right — text content */}
					<motion.div
						className="order-1 md:order-2"
						initial={{ opacity: 0, x: 30 }}
						animate={isInView ? { opacity: 1, x: 0 } : {}}
						transition={{ duration: 0.6 }}
					>
						<span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-xs font-semibold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider mb-5">
							<svg
								className="w-3.5 h-3.5"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								strokeWidth={2}
							>
								<title>Debate</title>
								<path
									strokeLinecap="round"
									strokeLinejoin="round"
									d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155"
								/>
							</svg>
							{t("debate_badge")}
						</span>
						<h2 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white leading-[1.1] mb-6">
							{t("debate_title")}
						</h2>
						<p className="text-base md:text-lg text-neutral-500 dark:text-neutral-400 leading-relaxed mb-8">
							{t("debate_description")}
						</p>

						{/* Key points */}
						<div className="space-y-4">
							{(
								["debate_point_1", "debate_point_2", "debate_point_3", "debate_point_4"] as const
							).map((key, i) => (
								<motion.div
									key={key}
									className="flex items-start gap-3"
									initial={{ opacity: 0, x: 10 }}
									animate={isInView ? { opacity: 1, x: 0 } : {}}
									transition={{ delay: 0.3 + i * 0.1, duration: 0.4 }}
								>
									<div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-indigo-500 shrink-0" />
									<span className="text-sm text-neutral-600 dark:text-neutral-300">{t(key)}</span>
								</motion.div>
							))}
						</div>
					</motion.div>
				</div>
			</div>
		</section>
	);
}

/* ════════════════════════════════════════════════════════════════
   3. TRANSPARENT REASONING
   ════════════════════════════════════════════════════════════════ */

const REASONING_STEPS = [
	{ key: "tr_step_1", type: "question", icon: "?" },
	{ key: "tr_step_2", type: "api", icon: "→" },
	{ key: "tr_step_3", type: "data", icon: "◆" },
	{ key: "tr_step_4", type: "analysis", icon: "⟐" },
	{ key: "tr_step_5", type: "verify", icon: "✓" },
	{ key: "tr_step_6", type: "answer", icon: "★" },
];

const STEP_COLORS: Record<
	string,
	{ bg: string; border: string; text: string; textLight: string; dot: string }
> = {
	question: {
		bg: "bg-violet-500/8",
		border: "border-violet-500/30",
		text: "text-violet-400",
		textLight: "text-violet-600",
		dot: "bg-violet-500",
	},
	api: {
		bg: "bg-blue-500/8",
		border: "border-blue-500/30",
		text: "text-blue-400",
		textLight: "text-blue-600",
		dot: "bg-blue-500",
	},
	data: {
		bg: "bg-cyan-500/8",
		border: "border-cyan-500/30",
		text: "text-cyan-400",
		textLight: "text-cyan-600",
		dot: "bg-cyan-500",
	},
	analysis: {
		bg: "bg-amber-500/8",
		border: "border-amber-500/30",
		text: "text-amber-400",
		textLight: "text-amber-600",
		dot: "bg-amber-500",
	},
	verify: {
		bg: "bg-emerald-500/8",
		border: "border-emerald-500/30",
		text: "text-emerald-400",
		textLight: "text-emerald-600",
		dot: "bg-emerald-500",
	},
	answer: {
		bg: "bg-pink-500/8",
		border: "border-pink-500/30",
		text: "text-pink-400",
		textLight: "text-pink-600",
		dot: "bg-pink-500",
	},
};

export function TransparentReasoning() {
	const t = useTranslations("homepage");
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.15 });
	const [activeStep, setActiveStep] = useState(-1);
	const [showHash, setShowHash] = useState(false);

	useEffect(() => {
		if (!isInView) return;
		let step = 0;
		const interval = setInterval(() => {
			if (step < REASONING_STEPS.length) {
				setActiveStep(step);
				step++;
			} else {
				clearInterval(interval);
				setTimeout(() => setShowHash(true), 400);
			}
		}, 500);
		return () => clearInterval(interval);
	}, [isInView]);

	return (
		<section
			ref={ref}
			className="relative py-20 md:py-28 overflow-hidden border-t border-neutral-100 dark:border-neutral-800/50"
		>
			{/* Background */}
			<div className="absolute inset-0 -z-10">
				<div className="absolute top-1/3 right-1/4 w-[500px] h-[400px] bg-[radial-gradient(circle,rgba(16,185,129,0.05),transparent_60%)] dark:bg-[radial-gradient(circle,rgba(16,185,129,0.08),transparent_60%)]" />
				<div className="absolute bottom-1/4 left-1/3 w-[400px] h-[300px] bg-[radial-gradient(circle,rgba(139,92,246,0.04),transparent_60%)] dark:bg-[radial-gradient(circle,rgba(139,92,246,0.06),transparent_60%)]" />
			</div>

			<div className="mx-auto max-w-6xl px-6">
				<div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
					{/* Left — text content */}
					<motion.div
						initial={{ opacity: 0, x: -30 }}
						animate={isInView ? { opacity: 1, x: 0 } : {}}
						transition={{ duration: 0.6 }}
					>
						<span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-5">
							<svg
								className="w-3.5 h-3.5"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								strokeWidth={2}
							>
								<path
									strokeLinecap="round"
									strokeLinejoin="round"
									d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"
								/>
							</svg>
							{t("tr_badge")}
						</span>
						<h2 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white leading-[1.1] mb-6">
							{t("tr_title")}
						</h2>
						<p className="text-base md:text-lg text-neutral-500 dark:text-neutral-400 leading-relaxed mb-8">
							{t("tr_description")}
						</p>

						{/* Key points */}
						<div className="space-y-4">
							{(["tr_point_1", "tr_point_2", "tr_point_3"] as const).map((key, i) => (
								<motion.div
									key={key}
									className="flex items-start gap-3"
									initial={{ opacity: 0, x: -10 }}
									animate={isInView ? { opacity: 1, x: 0 } : {}}
									transition={{ delay: 0.3 + i * 0.1, duration: 0.4 }}
								>
									<div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
									<span className="text-sm text-neutral-600 dark:text-neutral-300">{t(key)}</span>
								</motion.div>
							))}
						</div>
					</motion.div>

					{/* Right — reasoning tree visualization */}
					<motion.div
						initial={{ opacity: 0, x: 30 }}
						animate={isInView ? { opacity: 1, x: 0 } : {}}
						transition={{ duration: 0.6, delay: 0.2 }}
					>
						<div className="rounded-2xl border border-neutral-200/60 dark:border-neutral-800/60 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-sm p-6 shadow-lg shadow-neutral-200/50 dark:shadow-none">
							{/* Header */}
							<div className="flex items-center justify-between mb-5">
								<span className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
									{t("tr_chain_header")}
								</span>
								<div className="flex items-center gap-1.5">
									<span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
									<span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">
										{t("tr_verified")}
									</span>
								</div>
							</div>

							{/* Reasoning chain */}
							<div className="space-y-3">
								{REASONING_STEPS.map((step, i) => {
									const colors = STEP_COLORS[step.type];
									const isActive = i <= activeStep;
									const isCurrent = i === activeStep;

									return (
										<motion.div
											key={step.key}
											className={cn(
												"relative rounded-lg border px-4 py-3 transition-all duration-300",
												isActive ? colors.bg : "bg-neutral-50 dark:bg-neutral-900/30",
												isActive
													? colors.border
													: "border-neutral-200/60 dark:border-neutral-800/30"
											)}
											initial={{ opacity: 0.15, x: 10 }}
											animate={isActive ? { opacity: 1, x: 0 } : { opacity: 0.15, x: 10 }}
											transition={{ duration: 0.3, delay: i * 0.05 }}
										>
											{/* Connector line */}
											{i < REASONING_STEPS.length - 1 && (
												<div className="absolute left-7 -bottom-3 w-px h-3">
													<motion.div
														className={cn(
															"w-full h-full",
															isActive ? colors.dot : "bg-neutral-200 dark:bg-neutral-700"
														)}
														initial={{ scaleY: 0 }}
														animate={isActive ? { scaleY: 1 } : { scaleY: 0 }}
														transition={{ duration: 0.2, delay: 0.2 }}
													/>
												</div>
											)}

											<div className="flex items-center gap-3">
												{/* Step icon */}
												<div
													className={cn(
														"w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold shrink-0",
														isActive ? colors.bg : "bg-neutral-100 dark:bg-neutral-800/50",
														isActive
															? cn(colors.textLight, `dark:${colors.text}`)
															: "text-neutral-400 dark:text-neutral-600",
														isActive && "border",
														isActive && colors.border
													)}
												>
													{step.icon}
												</div>

												<div className="flex-1 min-w-0">
													<span
														className={cn(
															"text-xs font-medium",
															isActive
																? "text-neutral-800 dark:text-neutral-200"
																: "text-neutral-400 dark:text-neutral-600"
														)}
													>
														{t(step.key)}
													</span>
												</div>

												{/* Animated indicator */}
												{isCurrent && (
													<motion.div
														className={cn("w-1.5 h-1.5 rounded-full", colors.dot)}
														animate={{ opacity: [1, 0.3, 1] }}
														transition={{ duration: 1, repeat: Number.POSITIVE_INFINITY }}
													/>
												)}
												{isActive && !isCurrent && (
													<svg
														className="w-3.5 h-3.5 text-emerald-500"
														fill="none"
														viewBox="0 0 24 24"
														stroke="currentColor"
														strokeWidth={2.5}
													>
														<path
															strokeLinecap="round"
															strokeLinejoin="round"
															d="M4.5 12.75l6 6 9-13.5"
														/>
													</svg>
												)}
											</div>
										</motion.div>
									);
								})}
							</div>

							{/* Blockchain hash */}
							<motion.div
								className="mt-5 rounded-lg bg-emerald-500/5 border border-emerald-500/20 px-3 py-2.5"
								initial={{ opacity: 0, y: 5 }}
								animate={showHash ? { opacity: 1, y: 0 } : { opacity: 0, y: 5 }}
								transition={{ duration: 0.4 }}
							>
								<div className="flex items-center gap-2 mb-1">
									<svg
										className="w-3 h-3 text-emerald-600 dark:text-emerald-400"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										strokeWidth={2}
									>
										<path
											strokeLinecap="round"
											strokeLinejoin="round"
											d="M13.5 10.5V6.75a4.5 4.5 0 119 0v3.75M3.75 21.75h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H3.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
										/>
									</svg>
									<span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
										{t("tr_hash_label")}
									</span>
								</div>
								<code className="text-[10px] font-mono text-emerald-700/70 dark:text-emerald-300/70 break-all leading-relaxed">
									0x7f3a...e91b · sha256 · {t("tr_hash_status")}
								</code>
							</motion.div>
						</div>
					</motion.div>
				</div>
			</div>
		</section>
	);
}
