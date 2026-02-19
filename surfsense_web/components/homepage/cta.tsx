"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";

export function CTAHomepage() {
	const t = useTranslations("homepage");

	return (
		<section className="w-full py-24 md:py-32 bg-white dark:bg-neutral-950">
			<div className="mx-auto max-w-4xl px-4 md:px-8 text-center">
				{/* Heading */}
				<h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-black dark:text-white mb-6">
					{t("cta_ready_title")}
				</h2>

				{/* CTA Button */}
				<Link
					href="/dashboard/public/new-chat"
					className="inline-block px-8 py-3 text-base font-semibold bg-black text-white rounded-lg hover:bg-gray-800 transition-colors dark:bg-white dark:text-black dark:hover:bg-gray-200"
				>
					{t("cta_ready_button")}
				</Link>
			</div>
		</section>
	);
}
