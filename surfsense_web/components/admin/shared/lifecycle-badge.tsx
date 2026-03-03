"use client";

/**
 * v2 Lifecycle badge — shows Live/Review status with success rate.
 * Used across all admin/tools tabs.
 */

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type LifecycleStatus = "live" | "review";

interface LifecycleBadgeProps {
	status: LifecycleStatus;
	successRate?: number | null;
	requiredSuccessRate?: number;
	compact?: boolean;
	className?: string;
}

export function LifecycleBadge({
	status,
	successRate,
	requiredSuccessRate = 0.8,
	compact = false,
	className,
}: LifecycleBadgeProps) {
	const isLive = status === "live";
	const isReady = successRate != null && successRate >= requiredSuccessRate;

	const statusLabel = isLive ? "Live" : "Review";
	const rateLabel =
		successRate != null ? `${(successRate * 100).toFixed(1)}%` : null;

	return (
		<span className={cn("inline-flex items-center gap-1.5", className)}>
			<Badge
				variant={isLive ? "default" : "secondary"}
				className={cn(
					"text-xs font-medium",
					isLive && "bg-green-600 hover:bg-green-700",
					!isLive && isReady && "bg-amber-500 hover:bg-amber-600 text-white",
				)}
			>
				<span
					className={cn(
						"mr-1 inline-block h-1.5 w-1.5 rounded-full",
						isLive ? "bg-green-200" : isReady ? "bg-amber-200" : "bg-gray-400",
					)}
				/>
				{statusLabel}
			</Badge>
			{!compact && rateLabel && (
				<span className="text-xs text-muted-foreground tabular-nums">
					{rateLabel}
				</span>
			)}
		</span>
	);
}
