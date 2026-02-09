"use client";

import { usePathname } from "next/navigation";
import { FooterNew } from "@/components/homepage/footer-new";
import { RightSidebar } from "@/components/homepage/right-sidebar";

export default function HomePageLayout({ children }: { children: React.ReactNode }) {
	const pathname = usePathname();
	const isAuthPage = pathname === "/login" || pathname === "/register";

	return (
		<div className="min-h-screen bg-white dark:bg-neutral-950 overflow-x-hidden">
			<div className="flex">
				<main className="flex-1">
					{children}
					{!isAuthPage && <FooterNew />}
				</main>
				<RightSidebar />
			</div>
		</div>
	);
}
