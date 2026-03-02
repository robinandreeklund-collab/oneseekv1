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
	const [sidebarOpen, setSidebarOpen] = useState(false);
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
			name: "Om oss",
			link: "/about",
			icon: (
				<svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
					<path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
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
		{
			name: "Dev",
			link: "/dev",
			icon: (
				<svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
					<path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
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
					"bg-white dark:bg-neutral-950",
					"border-r border-neutral-200/50 dark:border-neutral-800/50",
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
								className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800/60 transition-colors"
								aria-label="Collapse sidebar"
							>
								<svg className="w-[18px] h-[18px] text-neutral-400 dark:text-neutral-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
									<path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
								</svg>
							</button>
						</div>
					) : (
						<button
							type="button"
							onClick={toggleSidebar}
							className="flex items-center justify-center w-10 h-10 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800/60 transition-colors mx-auto"
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
					"shrink-0 border-t border-neutral-200/50 dark:border-neutral-800/50 px-2 py-3",
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
						className="group relative inline-flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-xl bg-gradient-to-b from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:from-blue-600 hover:to-blue-700 transition-all duration-200"
					>
						<svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
							<path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
						</svg>
						Dashboard
						<svg className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
							<path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
						</svg>
					</Link>
				) : (
					<>
						{isGoogleAuth ? (
							<button
								type="button"
								onClick={handleGoogleLogin}
								className="group relative inline-flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-xl bg-gradient-to-b from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:from-blue-600 hover:to-blue-700 transition-all duration-200"
							>
								<svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
									<path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
								</svg>
								{tAuth("sign_in")}
							</button>
						) : (
							<Link
								href="/login"
								className="group relative inline-flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-xl bg-gradient-to-b from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:from-blue-600 hover:to-blue-700 transition-all duration-200"
							>
								<svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
									<path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
								</svg>
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
