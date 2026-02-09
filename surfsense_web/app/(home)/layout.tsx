"use client";

import { usePathname } from "next/navigation";
import { FooterNew } from "@/components/homepage/footer-new";
import { Navbar } from "@/components/homepage/navbar";

export default function HomePageLayout({ children }: { children: React.ReactNode }) {
	const pathname = usePathname();
	const isAuthPage = pathname === "/login" || pathname === "/register";

	return (
		<main className="min-h-screen bg-white dark:bg-neutral-950 overflow-x-hidden">
			<Navbar />
			{children}
			{!isAuthPage && <FooterNew />}
		</main>
	);
}
