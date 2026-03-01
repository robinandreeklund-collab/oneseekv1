"use client";

import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/utils";

/**
 * Compact "O" icon mark — used when space is tight (sidebar collapsed, favicon, mobile).
 * A geometric "O" with a subtle "seek" notch cut into the bottom-right,
 * suggesting a magnifying glass / search lens.
 */
export const OneseekIcon = ({ className, size = 32 }: { className?: string; size?: number }) => (
	<svg
		width={size}
		height={size}
		viewBox="0 0 32 32"
		fill="none"
		xmlns="http://www.w3.org/2000/svg"
		className={className}
		aria-label="Oneseek icon"
	>
		{/* Gradient definitions */}
		<defs>
			<linearGradient id="icon-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
				<stop offset="0%" stopColor="#8B5CF6" />
				<stop offset="100%" stopColor="#3B82F6" />
			</linearGradient>
		</defs>
		{/* Outer ring — thick geometric O */}
		<path
			d="M16 2C8.268 2 2 8.268 2 16s6.268 14 14 14c3.866 0 7.39-1.568 9.932-4.104l-3.536-3.536A8.96 8.96 0 0116 25c-4.97 0-9-4.03-9-9s4.03-9 9-9 9 4.03 9 9a8.96 8.96 0 01-1.36 4.396l3.536 3.536A13.934 13.934 0 0030 16C30 8.268 23.732 2 16 2z"
			fill="url(#icon-grad)"
		/>
		{/* Inner seek dot — the "lens" */}
		<circle cx="16" cy="16" r="3.5" fill="url(#icon-grad)" />
		{/* Search handle — diagonal line extending from the ring gap */}
		<rect
			x="24.5"
			y="22.4"
			width="5.5"
			height="3"
			rx="1.5"
			transform="rotate(45 24.5 22.4)"
			fill="url(#icon-grad)"
		/>
	</svg>
);

/**
 * Full wordmark: icon + "Oneseek" text.
 * Used in navbar, footer, and marketing materials.
 */
export const OneseekWordmark = ({
	className,
	iconSize = 28,
	textClassName,
}: {
	className?: string;
	iconSize?: number;
	textClassName?: string;
}) => (
	<div className={cn("flex items-center gap-2", className)}>
		<OneseekIcon size={iconSize} />
		<span
			className={cn(
				"text-lg font-bold tracking-tight text-neutral-900 dark:text-white",
				textClassName
			)}
		>
			Oneseek
		</span>
	</div>
);

/**
 * Legacy Logo component — wraps the old icon-128.svg.
 * Kept for backwards compatibility with other pages that may still use it.
 */
export const Logo = ({ className }: { className?: string }) => {
	return (
		<Link href="/">
			<Image
				src="/icon-128.svg"
				className={cn("dark:invert", className)}
				alt="logo"
				width={128}
				height={128}
			/>
		</Link>
	);
};
