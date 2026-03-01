"use client";

import { motion, useInView } from "motion/react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useRef } from "react";
import { AUTH_TYPE, BACKEND_URL } from "@/lib/env-config";
import { trackLoginAttempt } from "@/lib/posthog/events";

export function CTAHomepage() {
	const t = useTranslations("homepage");
	const tPricing = useTranslations("pricing");
	const tAuth = useTranslations("auth");
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.3 });
	const isGoogleAuth = AUTH_TYPE === "GOOGLE";

	const handleGoogleLogin = () => {
		trackLoginAttempt("google");
		window.location.href = `${BACKEND_URL}/auth/google/authorize-redirect`;
	};

	return (
		<section
			ref={ref}
			className="relative py-24 md:py-32 overflow-hidden border-t border-neutral-100 dark:border-neutral-800/50"
		>
			{/* Background gradient */}
			<div className="absolute inset-0 -z-10">
				<div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-[radial-gradient(ellipse,rgba(168,85,247,0.08),transparent_70%)] dark:bg-[radial-gradient(ellipse,rgba(168,85,247,0.15),transparent_70%)]" />
			</div>

			<motion.div
				className="mx-auto max-w-3xl px-6 text-center"
				initial={{ opacity: 0, y: 20 }}
				animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
				transition={{ duration: 0.6 }}
			>
				<h2 className="text-3xl md:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white">
					{t("cta_headline")}
				</h2>

				<p className="mt-6 text-lg text-neutral-500 dark:text-neutral-400 max-w-xl mx-auto">
					{t("cta_description")}
				</p>

				<motion.div
					className="mt-10 flex flex-col sm:flex-row justify-center gap-4"
					initial={{ opacity: 0, y: 10 }}
					animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
					transition={{ duration: 0.5, delay: 0.2 }}
				>
					{isGoogleAuth ? (
						<button
							type="button"
							onClick={handleGoogleLogin}
							className="group relative flex h-13 items-center justify-center gap-3 rounded-xl bg-white px-8 text-sm font-semibold text-neutral-700 shadow-lg ring-1 ring-neutral-200/50 transition-all duration-300 hover:shadow-xl hover:scale-[1.02] dark:bg-neutral-900 dark:text-neutral-200 dark:ring-neutral-700/50"
						>
							<span>{tAuth("continue_with_google")}</span>
						</button>
					) : (
						<Link
							href="/dashboard/public/new-chat"
							className="group relative flex h-13 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-blue-600 px-8 text-sm font-semibold text-white shadow-lg shadow-purple-500/25 transition-all duration-300 hover:shadow-xl hover:shadow-purple-500/30 hover:scale-[1.02]"
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

					<Link
						href="/contact"
						className="flex h-13 items-center justify-center rounded-xl border border-neutral-300 dark:border-neutral-700 px-8 text-sm font-semibold text-neutral-700 dark:text-neutral-300 transition-all duration-300 hover:border-purple-400 dark:hover:border-purple-500 hover:shadow-md bg-white/50 dark:bg-neutral-900/50 backdrop-blur-sm"
					>
						{t("cta_talk_to_us")}
					</Link>
				</motion.div>

				<motion.p
					className="mt-6 text-sm text-neutral-400 dark:text-neutral-500"
					initial={{ opacity: 0 }}
					animate={isInView ? { opacity: 1 } : { opacity: 0 }}
					transition={{ duration: 0.5, delay: 0.4 }}
				>
					{t("cta_no_account")}
				</motion.p>
			</motion.div>
		</section>
	);
}
