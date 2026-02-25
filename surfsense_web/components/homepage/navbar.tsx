"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { OneseekIcon, OneseekWordmark } from "@/components/Logo";
import { ThemeTogglerComponent } from "@/components/theme/theme-toggle";
import { getBearerToken } from "@/lib/auth-utils";
import { AUTH_TYPE, BACKEND_URL } from "@/lib/env-config";
import { trackLoginAttempt } from "@/lib/posthog/events";
import { cn } from "@/lib/utils";

export const Navbar = () => {
	const [isScrolled, setIsScrolled] = useState(false);
	const [menuOpen, setMenuOpen] = useState(false);
	const [isAuthenticated, setIsAuthenticated] = useState(false);
	const t = useTranslations("navigation");
	const tAuth = useTranslations("auth");
	const isGoogleAuth = AUTH_TYPE === "GOOGLE";

	const navItems = [
		{ name: t("docs"), link: "/docs" },
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

	useEffect(() => {
		const update = () => setIsAuthenticated(!!getBearerToken());
		update();
		const handler = () => update();
		window.addEventListener("storage", handler);
		return () => window.removeEventListener("storage", handler);
	}, []);

	// Lock body scroll when menu is open
	useEffect(() => {
		if (menuOpen) {
			document.body.style.overflow = "hidden";
		} else {
			document.body.style.overflow = "";
		}
		return () => {
			document.body.style.overflow = "";
		};
	}, [menuOpen]);

	const closeMenu = useCallback(() => setMenuOpen(false), []);

	const handleGoogleLogin = () => {
		trackLoginAttempt("google");
		window.location.href = `${BACKEND_URL}/auth/google/authorize-redirect`;
	};

	return (
		<>
			<header
				className={cn(
					"fixed top-0 left-0 right-0 z-50 transition-all duration-300",
					isScrolled
						? "bg-white/80 dark:bg-neutral-950/80 backdrop-blur-xl border-b border-neutral-200/50 dark:border-neutral-800/50"
						: "bg-transparent border-b border-transparent"
				)}
			>
				<div className="mx-auto max-w-7xl flex items-center justify-between h-[60px] px-4 md:px-6">
					{/* ── Left cluster: logo + nav links ── */}
					<div className="flex items-center gap-1">
						{/* Logo */}
						<Link href="/" className="flex items-center hover:opacity-80 transition-opacity mr-6">
							<span className="hidden sm:flex">
								<OneseekWordmark iconSize={26} />
							</span>
							<span className="flex sm:hidden">
								<OneseekIcon size={28} />
							</span>
						</Link>

						{/* Desktop nav links — immediately after logo */}
						<nav className="hidden md:flex items-center">
							{navItems.map((item) => (
								<Link
									key={item.link}
									href={item.link}
									className="px-3 py-1.5 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
								>
									{item.name}
								</Link>
							))}
						</nav>
					</div>

					{/* ── Right cluster: theme toggle + login + CTA ── */}
					<div className="flex items-center gap-3">
						<ThemeTogglerComponent />

						{isAuthenticated ? (
							<Link
								href="/dashboard"
								className="hidden md:inline-flex items-center px-5 py-2 text-sm font-medium rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-900 hover:opacity-90 transition-opacity"
							>
								Dashboard
							</Link>
						) : (
							<>
								{/* "Log in" text link — OpenAI style */}
								{isGoogleAuth ? (
									<button
										type="button"
										onClick={handleGoogleLogin}
										className="hidden md:inline-flex text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
									>
										{tAuth("sign_in")}
									</button>
								) : (
									<Link
										href="/login"
										className="hidden md:inline-flex text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
									>
										{tAuth("sign_in")}
									</Link>
								)}

								{/* Prominent CTA pill — "Try Oneseek →" */}
								<Link
									href={isAuthenticated ? "/dashboard" : "/login"}
									className="hidden md:inline-flex items-center gap-1.5 px-5 py-2 text-sm font-medium rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-900 hover:opacity-90 transition-opacity"
								>
									{t("try_oneseek")}
									<svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
										<path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
									</svg>
								</Link>
							</>
						)}

						{/* Hamburger — mobile only */}
						<button
							type="button"
							onClick={() => setMenuOpen(true)}
							className="flex items-center justify-center w-9 h-9 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors md:hidden"
							aria-label="Open menu"
						>
							<svg
								className="w-5 h-5 text-neutral-700 dark:text-neutral-300"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								strokeWidth={1.5}
							>
								<path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
							</svg>
						</button>
					</div>
				</div>
			</header>

			{/* ── Mobile menu overlay ── */}
			<AnimatePresence>
				{menuOpen && (
					<>
						{/* Backdrop */}
						<motion.div
							initial={{ opacity: 0 }}
							animate={{ opacity: 1 }}
							exit={{ opacity: 0 }}
							transition={{ duration: 0.2 }}
							className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm md:hidden"
							onClick={closeMenu}
							aria-hidden
						/>

						{/* Slide-in panel from left */}
						<motion.aside
							initial={{ x: "-100%" }}
							animate={{ x: 0 }}
							exit={{ x: "-100%" }}
							transition={{ type: "spring", damping: 30, stiffness: 300 }}
							className="fixed top-0 left-0 bottom-0 z-50 w-72 bg-white dark:bg-neutral-950 border-r border-neutral-200 dark:border-neutral-800 shadow-2xl flex flex-col md:hidden"
						>
							{/* Panel header */}
							<div className="flex items-center justify-between h-[60px] px-4 border-b border-neutral-100 dark:border-neutral-800/50">
								<Link href="/" onClick={closeMenu} className="hover:opacity-80 transition-opacity">
									<OneseekWordmark iconSize={24} />
								</Link>
								<button
									type="button"
									onClick={closeMenu}
									className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
									aria-label="Close menu"
								>
									<svg className="w-5 h-5 text-neutral-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
										<path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
									</svg>
								</button>
							</div>

							{/* Nav items */}
							<nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
								{navItems.map((item) => (
									<Link
										key={item.link}
										href={item.link}
										onClick={closeMenu}
										className="flex items-center gap-3 px-3 py-2.5 text-sm font-medium text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800/60 transition-colors"
									>
										{item.name}
									</Link>
								))}
							</nav>

							{/* Panel footer with auth buttons */}
							<div className="p-4 border-t border-neutral-100 dark:border-neutral-800/50 space-y-3">
								{isAuthenticated ? (
									<Link
										href="/dashboard"
										onClick={closeMenu}
										className="flex items-center justify-center w-full px-4 py-2.5 text-sm font-medium rounded-lg bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
									>
										Dashboard
									</Link>
								) : (
									<>
										{isGoogleAuth ? (
											<button
												type="button"
												onClick={() => {
													closeMenu();
													handleGoogleLogin();
												}}
												className="flex items-center justify-center w-full px-4 py-2.5 text-sm font-medium rounded-lg bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
											>
												{tAuth("sign_in")}
											</button>
										) : (
											<Link
												href="/login"
												onClick={closeMenu}
												className="flex items-center justify-center w-full px-4 py-2.5 text-sm font-medium rounded-lg bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
											>
												{t("try_oneseek")}
												<svg className="w-3.5 h-3.5 ml-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
													<path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
												</svg>
											</Link>
										)}
									</>
								)}
							</div>
						</motion.aside>
					</>
				)}
			</AnimatePresence>
		</>
	);
};
