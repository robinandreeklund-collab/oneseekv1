"use client";

import { IconMenu2, IconX } from "@tabler/icons-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Logo } from "@/components/Logo";
import { SignInButton } from "@/components/auth/sign-in-button";
import { ThemeTogglerComponent } from "@/components/theme/theme-toggle";

export function LeftSidebar() {
	const [isOpen, setIsOpen] = useState(false);
	const t = useTranslations("navigation");

	return (
		<>
			{/* Hamburger button - fixed top left */}
			<button
				type="button"
				onClick={() => setIsOpen(!isOpen)}
				className="fixed top-4 left-4 z-50 flex items-center justify-center w-10 h-10 rounded-lg bg-white border border-gray-200 hover:bg-gray-50 transition-colors dark:bg-neutral-900 dark:border-neutral-800 dark:hover:bg-neutral-800"
				aria-label={isOpen ? "Close menu" : "Open menu"}
			>
				{isOpen ? (
					<IconX className="h-5 w-5 text-gray-700 dark:text-gray-300" />
				) : (
					<IconMenu2 className="h-5 w-5 text-gray-700 dark:text-gray-300" />
				)}
			</button>

			{/* Overlay */}
			{isOpen && (
				<div
					className="fixed inset-0 bg-black/50 z-40 lg:hidden"
					onClick={() => setIsOpen(false)}
					aria-hidden="true"
				/>
			)}

			{/* Sidebar */}
			<aside
				className={`fixed top-0 left-0 z-40 h-screen w-64 bg-white border-r border-gray-200 transition-transform duration-300 dark:bg-neutral-950 dark:border-neutral-800 ${
					isOpen ? "translate-x-0" : "-translate-x-full"
				}`}
				aria-label="Main navigation sidebar"
			>
				<div className="flex flex-col h-full">
					{/* Logo at top */}
					<div className="p-6 border-b border-gray-200 dark:border-neutral-800">
						<Link href="/" className="flex items-center gap-2" onClick={() => setIsOpen(false)}>
							<Logo className="h-8 w-8 rounded-md" />
							<span className="text-lg font-bold text-gray-800 dark:text-white">Oneseek</span>
						</Link>
					</div>

					{/* Navigation */}
					<nav className="flex-1 p-6" aria-label="Primary navigation">
						<ul className="space-y-2">
							<li>
								<Link
									href="/contact"
									onClick={() => setIsOpen(false)}
									className="block px-3 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-50 rounded-md transition-colors dark:text-gray-400 dark:hover:text-white dark:hover:bg-neutral-800"
								>
									{t("contact")}
								</Link>
							</li>
							<li>
								<Link
									href="/changelog"
									onClick={() => setIsOpen(false)}
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
				</div>
			</aside>
		</>
	);
}
