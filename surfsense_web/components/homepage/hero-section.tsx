"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { AUTH_TYPE, BACKEND_URL } from "@/lib/env-config";
import { trackLoginAttempt } from "@/lib/posthog/events";

export function HeroSection() {
	const t = useTranslations("homepage");

	return (
		<section className="relative w-full py-32 md:py-48 bg-white dark:bg-neutral-950">
			<div className="mx-auto max-w-5xl px-4 md:px-8 text-center">
				{/* Main Heading */}
				<h1 className="text-5xl md:text-6xl lg:text-7xl font-bold text-black dark:text-white mb-6 tracking-tight">
					{t("hero_title")}
				</h1>

				{/* Subtitle */}
				<p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 max-w-3xl mx-auto mb-10">
					{t("hero_subtitle")}
				</p>

				{/* CTA Buttons */}
				<div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
					<GetStartedButton />
					<ContactButton />
				</div>
			</div>
		</section>
	);
}

function GetStartedButton() {
	const isGoogleAuth = AUTH_TYPE === "GOOGLE";
	const tAuth = useTranslations("auth");
	const tPricing = useTranslations("pricing");

	const handleGoogleLogin = () => {
		trackLoginAttempt("google");
		window.location.href = `${BACKEND_URL}/auth/google/authorize-redirect`;
	};

	if (isGoogleAuth) {
		return (
			<button
				type="button"
				onClick={handleGoogleLogin}
				className="px-8 py-3 text-base font-semibold bg-white text-black border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors dark:bg-neutral-900 dark:text-white dark:border-neutral-700 dark:hover:bg-neutral-800"
			>
				{tAuth("continue_with_google")}
			</button>
		);
	}

	return (
		<Link
			href="/dashboard/public/new-chat"
			className="px-8 py-3 text-base font-semibold bg-black text-white rounded-lg hover:bg-gray-800 transition-colors dark:bg-white dark:text-black dark:hover:bg-gray-200"
		>
			{tPricing("get_started")}
		</Link>
	);
}

function ContactButton() {
	const tPricing = useTranslations("pricing");
	return (
		<Link
			href="/contact"
			className="px-8 py-3 text-base font-semibold bg-white text-black border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors dark:bg-neutral-900 dark:text-white dark:border-neutral-700 dark:hover:bg-neutral-800"
		>
			{tPricing("contact_sales")}
		</Link>
	);
}
