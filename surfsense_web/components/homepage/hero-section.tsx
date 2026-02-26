"use client";

import { AnimatePresence, motion, useInView } from "motion/react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { AUTH_TYPE, BACKEND_URL } from "@/lib/env-config";
import { trackLoginAttempt } from "@/lib/posthog/events";
import { cn } from "@/lib/utils";

const AI_MODELS = [
	{ name: "ChatGPT", color: "from-emerald-400 to-green-500", accent: "text-emerald-400" },
	{ name: "Claude", color: "from-orange-400 to-amber-500", accent: "text-orange-400" },
	{ name: "Gemini", color: "from-blue-400 to-cyan-500", accent: "text-blue-400" },
	{ name: "DeepSeek", color: "from-indigo-400 to-purple-500", accent: "text-indigo-400" },
];

const DEMO_QUESTION = "Hur många invånare har Stockholm och hur har det förändrats?";

const DEMO_RESPONSES = [
	"Stockholm har cirka 984 000 invånare (2024). Sedan 2010 har befolkningen ökat med ungefär 12%, driven av urbanisering och invandring...",
	"Stockholms befolkning uppgår till 984 748 personer enligt SCB:s senaste statistik. Tillväxten har legat stabilt kring 1.2% per år...",
	"Enligt aktuella uppgifter bor det runt 985 000 människor i Stockholms kommun. Trenden visar på fortsatt tillväxt drivet av arbetsmarknad...",
	"Stockholm har 984 748 invånare (SCB, december 2024). Under senaste fem åren har staden vuxit med 3,2% totalt, främst genom inflyttning...",
];

const SYNTHESIS_TEXT =
	"Stockholm har 984 748 invånare (SCB, 2024). Befolkningen har ökat 12% sedan 2010, drivet av urbanisering och invandring. Samtliga modeller överens om siffrorna — verifierat mot SCB:s officiella statistik. [1][2]";

const GoogleLogo = ({ className }: { className?: string }) => (
	<svg className={className} viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
		<path
			d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
			fill="#4285F4"
		/>
		<path
			d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
			fill="#34A853"
		/>
		<path
			d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
			fill="#FBBC05"
		/>
		<path
			d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
			fill="#EA4335"
		/>
	</svg>
);

function TypingText({
	text,
	speed = 30,
	onComplete,
	className,
}: {
	text: string;
	speed?: number;
	onComplete?: () => void;
	className?: string;
}) {
	const [displayed, setDisplayed] = useState("");
	const indexRef = useRef(0);

	useEffect(() => {
		indexRef.current = 0;
		setDisplayed("");
		const interval = setInterval(() => {
			if (indexRef.current < text.length) {
				setDisplayed(text.slice(0, indexRef.current + 1));
				indexRef.current++;
			} else {
				clearInterval(interval);
				onComplete?.();
			}
		}, speed);
		return () => clearInterval(interval);
	}, [text, speed, onComplete]);

	return (
		<span className={className}>
			{displayed}
			<span className="animate-pulse">|</span>
		</span>
	);
}

function LiveDemo() {
	const t = useTranslations("homepage");
	const [phase, setPhase] = useState<"idle" | "typing" | "streaming" | "synthesis">("idle");
	const [visibleModels, setVisibleModels] = useState<number[]>([]);
	const [modelTexts, setModelTexts] = useState<string[]>(["", "", "", ""]);
	const [synthesisText, setSynthesisText] = useState("");
	const [hasPlayed, setHasPlayed] = useState(false);
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.3 });

	const streamText = useCallback(
		(text: string, modelIndex: number, delay: number) => {
			return new Promise<void>((resolve) => {
				setTimeout(() => {
					let charIndex = 0;
					const interval = setInterval(() => {
						if (charIndex < text.length) {
							setModelTexts((prev) => {
								const next = [...prev];
								next[modelIndex] = text.slice(0, charIndex + 1);
								return next;
							});
							charIndex++;
						} else {
							clearInterval(interval);
							resolve();
						}
					}, 12);
				}, delay);
			});
		},
		[]
	);

	useEffect(() => {
		if (!isInView || hasPlayed) return;
		setHasPlayed(true);

		const run = async () => {
			setPhase("typing");
			await new Promise((r) => setTimeout(r, DEMO_QUESTION.length * 30 + 600));
			setPhase("streaming");

			setVisibleModels([0]);
			await new Promise((r) => setTimeout(r, 150));
			setVisibleModels([0, 1]);
			await new Promise((r) => setTimeout(r, 150));
			setVisibleModels([0, 1, 2]);
			await new Promise((r) => setTimeout(r, 150));
			setVisibleModels([0, 1, 2, 3]);

			await Promise.all(DEMO_RESPONSES.map((text, i) => streamText(text, i, i * 250)));

			await new Promise((r) => setTimeout(r, 800));
			setPhase("synthesis");

			let charIndex = 0;
			await new Promise<void>((resolve) => {
				const interval = setInterval(() => {
					if (charIndex < SYNTHESIS_TEXT.length) {
						setSynthesisText(SYNTHESIS_TEXT.slice(0, charIndex + 1));
						charIndex++;
					} else {
						clearInterval(interval);
						resolve();
					}
				}, 10);
			});
		};

		run();
	}, [isInView, hasPlayed, streamText]);

	return (
		<div ref={ref} className="w-full max-w-5xl mx-auto mt-12 md:mt-16">
			<div className="relative rounded-2xl border border-neutral-200/50 dark:border-white/10 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-xl shadow-2xl shadow-purple-500/5 overflow-hidden">
				{/* Window chrome */}
				<div className="flex items-center gap-2 px-4 py-3 border-b border-neutral-100 dark:border-white/5">
					<div className="flex gap-1.5">
						<div className="w-3 h-3 rounded-full bg-red-400/80 dark:bg-red-500/80" />
						<div className="w-3 h-3 rounded-full bg-yellow-400/80 dark:bg-yellow-500/80" />
						<div className="w-3 h-3 rounded-full bg-green-400/80 dark:bg-green-500/80" />
					</div>
					<div className="flex-1 text-center">
						<span className="text-xs text-neutral-400 dark:text-neutral-500 font-mono">
							oneseek.se
						</span>
					</div>
				</div>

				{/* Question bar */}
				<div className="px-4 md:px-6 py-4 border-b border-neutral-100 dark:border-white/5">
					<div className="flex items-center gap-3 rounded-xl bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-200/50 dark:border-white/5 px-4 py-3">
						<svg
							className="w-5 h-5 text-neutral-400 dark:text-neutral-500 flex-shrink-0"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							strokeWidth={2}
						>
							<path
								strokeLinecap="round"
								strokeLinejoin="round"
								d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
							/>
						</svg>
						<div className="text-sm text-neutral-700 dark:text-neutral-300 font-mono">
							{phase === "idle" ? (
								<span className="text-neutral-400 dark:text-neutral-600">
									{t("demo_placeholder")}
								</span>
							) : (
								<TypingText text={DEMO_QUESTION} speed={30} />
							)}
						</div>
					</div>
				</div>

				{/* Model responses grid */}
				<AnimatePresence>
					{phase !== "idle" && phase !== "typing" && (
						<motion.div
							initial={{ height: 0, opacity: 0 }}
							animate={{ height: "auto", opacity: 1 }}
							transition={{ duration: 0.4 }}
							className="px-4 md:px-6 py-4"
						>
							<div className="grid grid-cols-1 md:grid-cols-2 gap-3">
								{AI_MODELS.map((model, i) => (
									<motion.div
										key={model.name}
										initial={{ opacity: 0, y: 10 }}
										animate={
											visibleModels.includes(i)
												? { opacity: 1, y: 0 }
												: { opacity: 0, y: 10 }
										}
										transition={{ duration: 0.3, delay: i * 0.08 }}
										className="rounded-xl bg-neutral-50 dark:bg-neutral-800/40 border border-neutral-200/30 dark:border-white/5 p-4"
									>
										<div className="flex items-center gap-2 mb-2">
											<div
												className={cn(
													"w-2 h-2 rounded-full bg-gradient-to-r",
													model.color
												)}
											/>
											<span
												className={cn(
													"text-xs font-semibold",
													model.accent
												)}
											>
												{model.name}
											</span>
										</div>
										<p className="text-xs text-neutral-500 dark:text-neutral-400 leading-relaxed min-h-[3rem]">
											{modelTexts[i] || (
												<span className="flex gap-1">
													<span className="w-1.5 h-1.5 rounded-full bg-neutral-300 dark:bg-neutral-600 animate-pulse" />
													<span
														className="w-1.5 h-1.5 rounded-full bg-neutral-300 dark:bg-neutral-600 animate-pulse"
														style={{ animationDelay: "0.2s" }}
													/>
													<span
														className="w-1.5 h-1.5 rounded-full bg-neutral-300 dark:bg-neutral-600 animate-pulse"
														style={{ animationDelay: "0.4s" }}
													/>
												</span>
											)}
										</p>
									</motion.div>
								))}
							</div>
						</motion.div>
					)}
				</AnimatePresence>

				{/* OneSeek Synthesis */}
				<AnimatePresence>
					{phase === "synthesis" && (
						<motion.div
							initial={{ opacity: 0, height: 0 }}
							animate={{ opacity: 1, height: "auto" }}
							transition={{ duration: 0.4 }}
							className="px-4 md:px-6 pb-4"
						>
							<div className="rounded-xl bg-gradient-to-br from-purple-50 via-blue-50 to-cyan-50 dark:from-purple-500/10 dark:via-blue-500/10 dark:to-cyan-500/10 border border-purple-200/50 dark:border-purple-500/20 p-4">
								<div className="flex items-center gap-2 mb-2">
									<div className="w-5 h-5 rounded-md bg-gradient-to-br from-purple-500 to-cyan-500 flex items-center justify-center">
										<svg
											className="w-3 h-3 text-white"
											fill="none"
											viewBox="0 0 24 24"
											stroke="currentColor"
											strokeWidth={2.5}
										>
											<path
												strokeLinecap="round"
												strokeLinejoin="round"
												d="M5 13l4 4L19 7"
											/>
										</svg>
									</div>
									<span className="text-xs font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-600 to-cyan-600 dark:from-purple-400 dark:to-cyan-400">
										OneSeek Syntes
									</span>
									<span className="text-[10px] text-neutral-400 dark:text-neutral-500 ml-auto">
										{t("demo_verified")}
									</span>
								</div>
								<p className="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">
									{synthesisText}
								</p>
							</div>
						</motion.div>
					)}
				</AnimatePresence>
			</div>
		</div>
	);
}

export function HeroSection() {
	const t = useTranslations("homepage");
	const isGoogleAuth = AUTH_TYPE === "GOOGLE";
	const tAuth = useTranslations("auth");
	const tPricing = useTranslations("pricing");

	const handleGoogleLogin = () => {
		trackLoginAttempt("google");
		window.location.href = `${BACKEND_URL}/auth/google/authorize-redirect`;
	};

	return (
		<section className="relative overflow-hidden px-4 pt-16 pb-16 md:pt-20 md:pb-24">
			{/* Background */}
			<div className="absolute inset-0 -z-10">
				<div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_-20%,rgba(120,80,255,0.08),transparent)] dark:bg-[radial-gradient(ellipse_80%_60%_at_50%_-20%,rgba(120,80,255,0.25),transparent)]" />
				<div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_40%_at_80%_50%,rgba(56,189,248,0.05),transparent)] dark:bg-[radial-gradient(ellipse_60%_40%_at_80%_50%,rgba(56,189,248,0.12),transparent)]" />
				<div
					className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[600px] rounded-full opacity-30 dark:opacity-50 animate-pulse-glow pointer-events-none"
					style={{
						background:
							"radial-gradient(circle, rgba(139,92,246,0.1) 0%, rgba(56,189,248,0.05) 40%, transparent 70%)",
					}}
				/>
			</div>

			{/* Headline — fixed position, never moves */}
			<motion.div
				className="relative z-10 text-center max-w-4xl mx-auto"
				initial={{ opacity: 0, y: 20 }}
				animate={{ opacity: 1, y: 0 }}
				transition={{ duration: 0.6 }}
			>
				<h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight text-neutral-900 dark:text-white leading-[1.1]">
					{t("hero_headline")}
				</h1>
				<p className="mt-6 text-lg md:text-xl text-neutral-500 dark:text-neutral-400 max-w-2xl mx-auto leading-relaxed">
					{t("hero_subheadline")}
				</p>
			</motion.div>

			{/* CTA */}
			<motion.div
				className="relative z-10 mt-8 flex flex-col sm:flex-row items-center gap-4 justify-center"
				initial={{ opacity: 0, y: 10 }}
				animate={{ opacity: 1, y: 0 }}
				transition={{ duration: 0.6, delay: 0.2 }}
			>
				{isGoogleAuth ? (
					<button
						type="button"
						onClick={handleGoogleLogin}
						className="group relative flex h-12 items-center justify-center gap-3 rounded-xl bg-white px-6 text-sm font-semibold text-neutral-700 shadow-lg ring-1 ring-neutral-200/50 transition-all duration-300 hover:shadow-xl hover:scale-[1.02] dark:bg-neutral-900 dark:text-neutral-200 dark:ring-neutral-700/50"
					>
						<GoogleLogo className="h-5 w-5" />
						<span>{tAuth("continue_with_google")}</span>
					</button>
				) : (
					<Link
						href="/dashboard/public/new-chat"
						className="group relative flex h-12 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-blue-600 px-8 text-sm font-semibold text-white shadow-lg shadow-purple-500/25 transition-all duration-300 hover:shadow-xl hover:shadow-purple-500/30 hover:scale-[1.02]"
					>
						{tPricing("get_started")}
						<svg
							className="w-4 h-4 transition-transform group-hover:translate-x-0.5"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							strokeWidth={2}
						>
							<path
								strokeLinecap="round"
								strokeLinejoin="round"
								d="M13 7l5 5m0 0l-5 5m5-5H6"
							/>
						</svg>
					</Link>
				)}
			</motion.div>

			{/* Live Demo — grows downward, heading above stays pinned */}
			<motion.div
				className="relative z-10 w-full"
				initial={{ opacity: 0, y: 30 }}
				animate={{ opacity: 1, y: 0 }}
				transition={{ duration: 0.8, delay: 0.4 }}
			>
				<LiveDemo />
			</motion.div>
		</section>
	);
}
