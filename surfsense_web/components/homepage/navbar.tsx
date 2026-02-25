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

/* ────────────────────────────────────────────────────────────
   Sidebar toggle icon (hamburger ↔ X with animation)
   ──────────────────────────────────────────────────────────── */
const ToggleIcon = ({ open, className }: { open: boolean; className?: string }) => (
	<svg
		className={cn("w-5 h-5", className)}
		fill="none"
		viewBox="0 0 24 24"
		stroke="currentColor"
		strokeWidth={1.5}
	>
		{open ? (
			<path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
		) : (
			<>
				<path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5" />
				<path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5" />
				<path strokeLinecap="round" strokeLinejoin="round" d="M3.75 17.25h16.5" />
			</>
		)}
	</svg>
);

/* ────────────────────────────────────────────────────────────
   Sidebar + Top-right login bar
   Layout: left sidebar (collapsible drawer) + floating top-right auth
   ──────────────────────────────────────────────────────────── */
export const Navbar = () => {
	const [sidebarOpen, setSidebarOpen] = useState(true);
	const [isMobile, setIsMobile] = useState(false);
	const [isAuthenticated, setIsAuthenticated] = useState(false);
	const t = useTranslations("navigation");
	const tAuth = useTranslations("auth");
	const isGoogleAuth = AUTH_TYPE === "GOOGLE";

	const navItems = [
		{
			name: t("home"),
			link: "/",
			icon: (
				<svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
					<path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955a1.126 1.126 0 011.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
				</svg>
			),
		},
		{
			name: t("docs"),
			link: "/docs",
			icon: (
				<svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
					<path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
				</svg>
			),
		},
		{
			name: t("contact"),
			link: "/contact",
			icon: (
				<svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
					<path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
				</svg>
			),
		},
		{
			name: t("changelog"),
			link: "/changelog",
			icon: (
				<svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
					<path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
			),
		},
	];

	// Detect mobile
	useEffect(() => {
		const check = () => {
			const mobile = window.innerWidth < 768;
			setIsMobile(mobile);
			if (mobile) setSidebarOpen(false);
		};
		check();
		window.addEventListener("resize", check);
		return () => window.removeEventListener("resize", check);
	}, []);

	// Auth state
	useEffect(() => {
		const update = () => setIsAuthenticated(!!getBearerToken());
		update();
		const handler = () => update();
		window.addEventListener("storage", handler);
		return () => window.removeEventListener("storage", handler);
	}, []);

	// Lock body scroll when mobile overlay is open
	useEffect(() => {
		if (isMobile && sidebarOpen) {
			document.body.style.overflow = "hidden";
		} else {
			document.body.style.overflow = "";
		}
		return () => {
			document.body.style.overflow = "";
		};
	}, [isMobile, sidebarOpen]);

	const closeSidebar = useCallback(() => setSidebarOpen(false), []);
	const toggleSidebar = useCallback(() => setSidebarOpen((p) => !p), []);

	const handleGoogleLogin = () => {
		trackLoginAttempt("google");
		window.location.href = `${BACKEND_URL}/auth/google/authorize-redirect`;
	};

	return (
		<>
			{/* ── Left sidebar ── */}
			{/* Desktop: permanent, collapsible between wide (240px) and narrow (64px) */}
			{/* Mobile: overlay drawer from left */}

			{/* Mobile backdrop */}
			<AnimatePresence>
				{isMobile && sidebarOpen && (
					<motion.div
						initial={{ opacity: 0 }}
						animate={{ opacity: 1 }}
						exit={{ opacity: 0 }}
						transition={{ duration: 0.2 }}
						className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
						onClick={closeSidebar}
						aria-hidden
					/>
				)}
			</AnimatePresence>

			{/* Sidebar */}
			<motion.aside
				initial={false}
				animate={{
					width: sidebarOpen ? 240 : (isMobile ? 0 : 64),
					x: isMobile && !sidebarOpen ? -240 : 0,
				}}
				transition={{ type: "spring", damping: 28, stiffness: 320 }}
				className={cn(
					"fixed top-0 left-0 bottom-0 z-50 flex flex-col",
					"bg-neutral-50 dark:bg-neutral-900/80",
					"border-r border-neutral-200/70 dark:border-neutral-800/70",
					isMobile ? "shadow-2xl" : "",
				)}
				style={{ overflow: "hidden" }}
			>
				{/* Sidebar header: logo + toggle */}
				<div className="flex items-center h-14 px-3 shrink-0">
					{sidebarOpen ? (
						<div className="flex items-center justify-between w-full">
							<Link href="/" className="flex items-center hover:opacity-80 transition-opacity pl-1">
								<OneseekWordmark iconSize={24} />
							</Link>
							<button
								type="button"
								onClick={toggleSidebar}
								className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-neutral-200/70 dark:hover:bg-neutral-700/50 transition-colors"
								aria-label="Collapse sidebar"
							>
								{/* Sidebar collapse icon */}
								<svg className="w-[18px] h-[18px] text-neutral-500 dark:text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
									<path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
								</svg>
							</button>
						</div>
					) : (
						<button
							type="button"
							onClick={toggleSidebar}
							className="flex items-center justify-center w-10 h-10 rounded-lg hover:bg-neutral-200/70 dark:hover:bg-neutral-700/50 transition-colors mx-auto"
							aria-label="Expand sidebar"
						>
							<OneseekIcon size={22} />
						</button>
					)}
				</div>

				{/* Navigation links */}
				<nav className="flex-1 px-2 py-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
					{navItems.map((item) => (
						<Link
							key={item.link}
							href={item.link}
							onClick={isMobile ? closeSidebar : undefined}
							className={cn(
								"flex items-center gap-3 rounded-lg transition-colors",
								"text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white",
								"hover:bg-neutral-200/60 dark:hover:bg-neutral-700/40",
								sidebarOpen ? "px-3 py-2.5" : "justify-center px-0 py-2.5",
							)}
							title={!sidebarOpen ? item.name : undefined}
						>
							<span className="shrink-0">{item.icon}</span>
							{sidebarOpen && (
								<span className="text-sm font-medium truncate">{item.name}</span>
							)}
						</Link>
					))}
				</nav>

				{/* Sidebar footer: theme toggle */}
				<div className={cn(
					"shrink-0 border-t border-neutral-200/70 dark:border-neutral-800/70 px-2 py-3",
					sidebarOpen ? "flex items-center justify-between" : "flex justify-center",
				)}>
					<ThemeTogglerComponent />
				</div>
			</motion.aside>

			{/* ── Top-right floating bar ── */}
			<div
				className={cn(
					"fixed top-0 right-0 z-40 flex items-center gap-3 h-14 px-4 md:px-6 transition-all duration-300",
				)}
			>
				{/* Mobile hamburger toggle */}
				<button
					type="button"
					onClick={toggleSidebar}
					className="flex items-center justify-center w-9 h-9 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors md:hidden"
					aria-label="Toggle menu"
				>
					<ToggleIcon open={sidebarOpen} className="text-neutral-700 dark:text-neutral-300" />
				</button>

				{/* Auth buttons */}
				{isAuthenticated ? (
					<Link
						href="/dashboard"
						className="inline-flex items-center px-4 py-1.5 text-sm font-medium rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-900 hover:opacity-90 transition-opacity"
					>
						Dashboard
					</Link>
				) : (
					<>
						{isGoogleAuth ? (
							<button
								type="button"
								onClick={handleGoogleLogin}
								className="text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
							>
								{tAuth("sign_in")}
							</button>
						) : (
							<Link
								href="/login"
								className="inline-flex items-center px-4 py-1.5 text-sm font-medium rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-900 hover:opacity-90 transition-opacity"
							>
								{tAuth("sign_in")}
							</Link>
						)}
					</>
				)}
			</div>
		</>
	);
};

/* ────────────────────────────────────────────────────────────
   Export sidebar width constants for layout offset
   ──────────────────────────────────────────────────────────── */
export const SIDEBAR_WIDTH_OPEN = 240;
export const SIDEBAR_WIDTH_COLLAPSED = 64;
