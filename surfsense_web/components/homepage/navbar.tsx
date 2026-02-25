"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { SignInButton } from "@/components/auth/sign-in-button";
import { OneseekIcon, OneseekWordmark } from "@/components/Logo";
import { ThemeTogglerComponent } from "@/components/theme/theme-toggle";
import { cn } from "@/lib/utils";

export const Navbar = () => {
	const [isScrolled, setIsScrolled] = useState(false);
	const [sidebarOpen, setSidebarOpen] = useState(false);
	const t = useTranslations("navigation");

	const navItems = [
		{ name: t("contact"), link: "/contact" },
		{ name: t("changelog"), link: "/changelog" },
	];

	useEffect(() => {
		if (typeof window === "undefined") return;
		const handleScroll = () => setIsScrolled(window.scrollY > 20);
		handleScroll();
		window.addEventListener("scroll", handleScroll, { passive: true });
		return () => window.removeEventListener("scroll", handleScroll);
	}, []);

	// Lock body scroll when sidebar is open
	useEffect(() => {
		if (sidebarOpen) {
			document.body.style.overflow = "hidden";
		} else {
			document.body.style.overflow = "";
		}
		return () => {
			document.body.style.overflow = "";
		};
	}, [sidebarOpen]);

	const closeSidebar = useCallback(() => setSidebarOpen(false), []);

	return (
		<>
			{/* Top bar */}
			<header
				className={cn(
					"fixed top-0 left-0 right-0 z-50 transition-all duration-300",
					isScrolled
						? "bg-white/80 dark:bg-neutral-950/80 backdrop-blur-xl border-b border-neutral-200/50 dark:border-neutral-800/50 shadow-sm"
						: "bg-transparent border-b border-transparent"
				)}
			>
				<div className="mx-auto max-w-7xl flex items-center justify-between h-14 px-4 md:px-6">
					{/* Left: hamburger + logo */}
					<div className="flex items-center gap-3">
						{/* Hamburger — mobile only */}
						<button
							type="button"
							onClick={() => setSidebarOpen(true)}
							className="flex items-center justify-center w-8 h-8 -ml-1 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors lg:hidden"
							aria-label="Open menu"
						>
							<svg
								className="w-5 h-5 text-neutral-700 dark:text-neutral-300"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								strokeWidth={1.5}
							>
								<path
									strokeLinecap="round"
									strokeLinejoin="round"
									d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
								/>
							</svg>
						</button>

						{/* Logo — wordmark on desktop, icon-only on small mobile */}
						<Link href="/" className="flex items-center hover:opacity-80 transition-opacity">
							<span className="hidden sm:flex">
								<OneseekWordmark iconSize={26} />
							</span>
							<span className="flex sm:hidden">
								<OneseekIcon size={28} />
							</span>
						</Link>
					</div>

					{/* Center: nav links — desktop only */}
					<nav className="hidden lg:flex items-center gap-1">
						{navItems.map((item) => (
							<Link
								key={item.link}
								href={item.link}
								className="relative px-3 py-1.5 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800/60 transition-colors"
							>
								{item.name}
							</Link>
						))}
					</nav>

					{/* Right: theme toggle + sign in */}
					<div className="flex items-center gap-2">
						<ThemeTogglerComponent />
						<SignInButton variant="desktop" />
					</div>
				</div>
			</header>

			{/* Mobile sidebar */}
			<AnimatePresence>
				{sidebarOpen && (
					<>
						{/* Backdrop */}
						<motion.div
							initial={{ opacity: 0 }}
							animate={{ opacity: 1 }}
							exit={{ opacity: 0 }}
							transition={{ duration: 0.2 }}
							className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm lg:hidden"
							onClick={closeSidebar}
							aria-hidden
						/>

						{/* Sidebar panel — slides from left */}
						<motion.aside
							initial={{ x: "-100%" }}
							animate={{ x: 0 }}
							exit={{ x: "-100%" }}
							transition={{ type: "spring", damping: 30, stiffness: 300 }}
							className="fixed top-0 left-0 bottom-0 z-50 w-72 bg-white dark:bg-neutral-950 border-r border-neutral-200 dark:border-neutral-800 shadow-2xl flex flex-col lg:hidden"
						>
							{/* Sidebar header */}
							<div className="flex items-center justify-between h-14 px-4 border-b border-neutral-100 dark:border-neutral-800/50">
								<Link
									href="/"
									onClick={closeSidebar}
									className="hover:opacity-80 transition-opacity"
								>
									<OneseekWordmark iconSize={24} />
								</Link>
								<button
									type="button"
									onClick={closeSidebar}
									className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
									aria-label="Close menu"
								>
									<svg
										className="w-5 h-5 text-neutral-500"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										strokeWidth={1.5}
									>
										<path
											strokeLinecap="round"
											strokeLinejoin="round"
											d="M6 18L18 6M6 6l12 12"
										/>
									</svg>
								</button>
							</div>

							{/* Nav items */}
							<nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
								{navItems.map((item) => (
									<Link
										key={item.link}
										href={item.link}
										onClick={closeSidebar}
										className="flex items-center gap-3 px-3 py-2.5 text-sm font-medium text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800/60 transition-colors"
									>
										{item.name}
									</Link>
								))}
							</nav>

							{/* Sidebar footer */}
							<div className="p-4 border-t border-neutral-100 dark:border-neutral-800/50 space-y-3">
								<SignInButton variant="mobile" />
							</div>
						</motion.aside>
					</>
				)}
			</AnimatePresence>
		</>
	);
};
