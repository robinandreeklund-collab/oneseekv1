"use client";

import { usePathname } from "next/navigation";
import { FooterNew } from "@/components/homepage/footer-new";
import { Navbar } from "@/components/homepage/navbar";
import { LeftSidebar } from "@/components/homepage/left-sidebar";

export default function HomePageLayout({ children }: { children: React.ReactNode }) {
	const pathname = usePathname();
	const isAuthPage = pathname === "/login" || pathname === "/register";

	return (
		<div className="min-h-screen bg-white dark:bg-neutral-950 overflow-x-hidden">
			<LeftSidebar />
			<Navbar />
			<main className="min-h-screen">
				{children}
				{!isAuthPage && <FooterNew />}
			</main>
		</div>
	);
}
