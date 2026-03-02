import type { ReactNode } from "react";

export default function Layout({ children }: { children: ReactNode }) {
	return (
		<div className="min-h-screen bg-white text-gray-900 dark:bg-neutral-950 dark:text-white">
			{children}
		</div>
	);
}
