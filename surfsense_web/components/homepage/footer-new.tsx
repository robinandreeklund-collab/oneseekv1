"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

export function FooterNew() {
	const tNav = useTranslations("navigation");
	const tAuth = useTranslations("auth");
	const tFooter = useTranslations("footer");

	return (
		<footer className="border-t border-neutral-200/60 dark:border-neutral-800/40 bg-white dark:bg-neutral-950">
			<div className="mx-auto max-w-7xl px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4">
				<p className="text-xs text-neutral-400 dark:text-neutral-500">
					{tFooter("rights_reserved", { year: new Date().getFullYear() })}
				</p>

				<nav className="flex items-center gap-6">
					<Link
						href="/docs"
						className="text-xs text-neutral-500 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
					>
						{tNav("docs")}
					</Link>
					<Link
						href="/contact"
						className="text-xs text-neutral-500 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
					>
						{tNav("contact")}
					</Link>
					<Link
						href="/login"
						className="text-xs text-neutral-500 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
					>
						{tAuth("sign_in")}
					</Link>
				</nav>
			</div>
		</footer>
	);
}
