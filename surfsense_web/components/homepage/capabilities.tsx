"use client";

import { motion, useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { useRef } from "react";
import { cn } from "@/lib/utils";

const CAPABILITY_ICONS = {
	compare: (
		<svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
			<path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
		</svg>
	),
	debate: (
		<svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
			<path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
		</svg>
	),
	transparency: (
		<svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
			<path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
			<path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
		</svg>
	),
	realtime: (
		<svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
			<path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
		</svg>
	),
};

const CAPABILITY_COLORS = {
	compare: {
		icon: "text-purple-600 dark:text-purple-400",
		bg: "bg-purple-500/10 dark:bg-purple-500/20",
		border: "group-hover:border-purple-300 dark:group-hover:border-purple-500/40",
	},
	debate: {
		icon: "text-blue-600 dark:text-blue-400",
		bg: "bg-blue-500/10 dark:bg-blue-500/20",
		border: "group-hover:border-blue-300 dark:group-hover:border-blue-500/40",
	},
	transparency: {
		icon: "text-amber-600 dark:text-amber-400",
		bg: "bg-amber-500/10 dark:bg-amber-500/20",
		border: "group-hover:border-amber-300 dark:group-hover:border-amber-500/40",
	},
	realtime: {
		icon: "text-emerald-600 dark:text-emerald-400",
		bg: "bg-emerald-500/10 dark:bg-emerald-500/20",
		border: "group-hover:border-emerald-300 dark:group-hover:border-emerald-500/40",
	},
};

type CapabilityKey = keyof typeof CAPABILITY_ICONS;

export function Capabilities() {
	const t = useTranslations("homepage");
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.2 });

	const capabilities: { key: CapabilityKey; titleKey: string; descKey: string }[] = [
		{ key: "compare", titleKey: "cap_compare_title", descKey: "cap_compare_desc" },
		{ key: "debate", titleKey: "cap_debate_title", descKey: "cap_debate_desc" },
		{ key: "transparency", titleKey: "cap_transparency_title", descKey: "cap_transparency_desc" },
		{ key: "realtime", titleKey: "cap_realtime_title", descKey: "cap_realtime_desc" },
	];

	return (
		<section
			ref={ref}
			className="relative py-20 md:py-28 border-t border-neutral-100 dark:border-neutral-800/50"
		>
			<div className="mx-auto max-w-7xl px-6">
				<motion.div
					className="text-center mb-12"
					initial={{ opacity: 0, y: 20 }}
					animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
					transition={{ duration: 0.6 }}
				>
					<h2 className="text-3xl md:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white">
						{t("capabilities_title")}
					</h2>
					<p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400 max-w-2xl mx-auto">
						{t("capabilities_subtitle")}
					</p>
				</motion.div>

				<div className="grid grid-cols-1 md:grid-cols-2 gap-5 max-w-4xl mx-auto">
					{capabilities.map((cap, i) => {
						const colors = CAPABILITY_COLORS[cap.key];
						return (
							<motion.div
								key={cap.key}
								className={cn(
									"group relative rounded-xl border border-neutral-200/50 dark:border-neutral-800/50 bg-white/60 dark:bg-neutral-900/40 backdrop-blur-sm p-6 transition-all duration-300 hover:shadow-lg",
									colors.border
								)}
								initial={{ opacity: 0, y: 20 }}
								animate={
									isInView
										? { opacity: 1, y: 0 }
										: { opacity: 0, y: 20 }
								}
								transition={{ duration: 0.4, delay: i * 0.1 }}
							>
								<div
									className={cn(
										"w-11 h-11 rounded-xl flex items-center justify-center mb-4",
										colors.bg
									)}
								>
									<div className={colors.icon}>
										{CAPABILITY_ICONS[cap.key]}
									</div>
								</div>
								<h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-2">
									{t(cap.titleKey)}
								</h3>
								<p className="text-sm text-neutral-500 dark:text-neutral-400 leading-relaxed">
									{t(cap.descKey)}
								</p>
							</motion.div>
						);
					})}
				</div>
			</div>
		</section>
	);
}
