"use client";
import { useFeatureFlagVariantKey } from "@posthog/react";
import Image from "next/image";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useRef } from "react";
import Balancer from "react-wrap-balancer";
import { AUTH_TYPE, BACKEND_URL } from "@/lib/env-config";
import { trackLoginAttempt } from "@/lib/posthog/events";

// Official Google "G" logo with brand colors
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

export function HeroSection() {
	const containerRef = useRef<HTMLDivElement>(null);
	const parentRef = useRef<HTMLDivElement>(null);
	const heroVariant = useFeatureFlagVariantKey("notebooklm_flag");
	const isNotebookLMVariant = heroVariant === "notebooklm";
	const t = useTranslations("homepage");

	return (
		<div
			ref={parentRef}
			className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-20 md:px-8 md:py-32"
		>
			{/* Simplified background - OpenAI style */}
			<div className="absolute inset-0 bg-gradient-to-b from-white via-gray-50 to-white dark:from-neutral-950 dark:via-neutral-900 dark:to-neutral-950" />
			
			{/* Subtle grid pattern */}
			<div className="absolute inset-0 bg-[linear-gradient(to_right,#8882_1px,transparent_1px),linear-gradient(to_bottom,#8882_1px,transparent_1px)] bg-[size:14px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_110%)] dark:bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)]" />

			<h1 className="relative z-50 mx-auto mb-6 mt-4 max-w-5xl text-balance text-center text-4xl font-bold tracking-tight text-gray-900 md:text-6xl lg:text-7xl dark:text-white">
				{isNotebookLMVariant ? (
					<Balancer>
						<span>{t("notebooklm_title")}</span>
					</Balancer>
				) : (
					<Balancer>
						<span>{t("hero_title_part1")}</span>
						{t("hero_title_part2") && <span> {t("hero_title_part2")}</span>}
					</Balancer>
				)}
			</h1>
			<p className="relative z-50 mx-auto mt-4 max-w-2xl px-4 text-center text-lg text-gray-600 md:text-xl dark:text-gray-300">
				{t("hero_description")}
			</p>
			<div className="mb-16 mt-10 flex w-full flex-col items-center justify-center gap-4 px-8 sm:flex-row md:mb-20">
				<GetStartedButton />
			</div>
			<div
				ref={containerRef}
				className="relative mx-auto max-w-7xl rounded-2xl border border-gray-200 bg-white p-2 shadow-2xl md:p-3 dark:border-neutral-800 dark:bg-neutral-900"
			>
				<div className="rounded-xl border border-gray-100 bg-white overflow-hidden dark:border-neutral-800 dark:bg-black">
					{/* Light mode image */}
					<Image
						src="/homepage/main_demo.webp"
						alt="OneSeek AI Workspace Demo"
						width={1920}
						height={1080}
						className="rounded-lg block dark:hidden"
						unoptimized
					/>
					{/* Dark mode image */}
					<Image
						src="/homepage/main_demo.webp"
						alt="OneSeek AI Workspace Demo"
						width={1920}
						height={1080}
						className="rounded-lg hidden dark:block"
						unoptimized
					/>
				</div>
			</div>
		</div>
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
				className="group relative z-20 flex h-12 w-full cursor-pointer items-center justify-center gap-3 overflow-hidden rounded-lg bg-white px-8 py-3 text-base font-medium text-gray-700 shadow-sm ring-1 ring-gray-300 transition-all duration-200 hover:bg-gray-50 hover:shadow-md sm:w-auto dark:bg-neutral-800 dark:text-neutral-200 dark:ring-neutral-700 dark:hover:bg-neutral-700"
			>
				<GoogleLogo className="h-5 w-5" />
				<span>{tAuth("continue_with_google")}</span>
			</button>
		);
	}

	return (
		<Link
			href="/dashboard/public/new-chat"
			className="group relative z-20 flex h-12 w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-black px-8 py-3 text-base font-medium text-white shadow-sm transition-all duration-200 hover:bg-gray-800 hover:shadow-md sm:w-auto dark:bg-white dark:text-black dark:hover:bg-gray-100"
		>
			{tPricing("get_started")}
			<svg
				className="h-4 w-4 transition-transform group-hover:translate-x-1"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
			</svg>
		</Link>
	);
}

function ContactSalesButton() {
	const tPricing = useTranslations("pricing");
	return (
		<Link
			href="/contact"
			rel="noopener noreferrer"
			className="group relative z-20 flex h-12 w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-white px-8 py-3 text-base font-medium text-gray-700 shadow-sm ring-1 ring-gray-300 transition-all duration-200 hover:bg-gray-50 hover:shadow-md sm:w-auto dark:bg-neutral-800 dark:text-neutral-200 dark:ring-neutral-700 dark:hover:bg-neutral-700"
		>
			{tPricing("contact_sales")}
		</Link>
	);
}
