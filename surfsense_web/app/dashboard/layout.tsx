"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useGlobalLoadingEffect } from "@/hooks/use-global-loading";
import { getBearerToken, redirectToLogin } from "@/lib/auth-utils";

interface DashboardLayoutProps {
	children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
	const [isCheckingAuth, setIsCheckingAuth] = useState(true);
	const pathname = usePathname();
	const isPublicChatRoute = pathname?.startsWith("/dashboard/public/new-chat");

	// Use the global loading screen - spinner animation won't reset
	useGlobalLoadingEffect(isCheckingAuth);

	useEffect(() => {
		// Check if user is authenticated
		const token = getBearerToken();
		if (!token && !isPublicChatRoute) {
			// Save current path and redirect to login
			redirectToLogin();
			return;
		}
		setIsCheckingAuth(false);
	}, [isPublicChatRoute]);

	// Return null while loading - the global provider handles the loading UI
	if (isCheckingAuth) {
		return null;
	}

	return (
		<div className="h-full flex flex-col ">
			<div className="flex-1 min-h-0">{children}</div>
		</div>
	);
}
