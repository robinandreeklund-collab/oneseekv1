"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Logo } from "@/components/Logo";
import { SignInButton } from "@/components/auth/sign-in-button";
import { ThemeTogglerComponent } from "@/components/theme/theme-toggle";

export function RightSidebar() {
	const t = useTranslations("navigation");

	return (
		<aside className="hidden lg:flex lg:flex-col lg:w-80 border-l border-gray-200 dark:border-neutral-800 bg-white dark:bg-neutral-950 sticky top-0 h-screen overflow-y-auto">
			{/* Logo at top */}
			<div className="p-6 border-b border-gray-200 dark:border-neutral-800">
				<Link href="/" className="flex items-center gap-2">
					<Logo className="h-8 w-8 rounded-md" />
					<span className="text-lg font-bold text-gray-800 dark:text-white">Oneseek</span>
				</Link>
			</div>

			{/* Navigation */}
			<nav className="flex-1 p-6">
				<ul className="space-y-2">
					<li>
						<Link
							href="/contact"
							className="block px-3 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-50 rounded-md transition-colors dark:text-gray-400 dark:hover:text-white dark:hover:bg-neutral-800"
						>
							{t("contact")}
						</Link>
					</li>
					<li>
						<Link
							href="/changelog"
							className="block px-3 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-50 rounded-md transition-colors dark:text-gray-400 dark:hover:text-white dark:hover:bg-neutral-800"
						>
							{t("changelog")}
						</Link>
					</li>
				</ul>
			</nav>

			{/* Actions at bottom */}
			<div className="p-6 border-t border-gray-200 dark:border-neutral-800 space-y-3">
				<ThemeTogglerComponent />
				<SignInButton variant="desktop" />
			</div>
		</aside>
	);
}
