"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { AlertCircleIcon } from "lucide-react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

// ============================================================================
// Zod Schemas
// ============================================================================

const StopGroupSchema = z
	.object({
		id: z.string().nullish(),
		name: z.string().nullish(),
		area_type: z.string().nullish(),
	})
	.partial();

const RouteSideSchema = z
	.object({
		id: z.string().nullish(),
		name: z.string().nullish(),
		stop_group: StopGroupSchema.nullish(),
	})
	.partial();

const TrafiklabRouteArgsSchema = z
	.object({
		origin: z.string().nullish(),
		destination: z.string().nullish(),
		time: z.string().nullish(),
		mode: z.string().nullish(),
	})
	.partial();

const TrafiklabRouteResultSchema = z
	.object({
		status: z.string().nullish(),
		error: z.string().nullish(),
		attribution: z.string().nullish(),
		board_type: z.string().nullish(),
		requested_time: z.string().nullish(),
		query_time: z.string().nullish(),
		origin: RouteSideSchema.nullish(),
		destination: RouteSideSchema.nullish(),
		entries: z.array(z.any()).nullish(),
		matching_entries: z.array(z.any()).nullish(),
	})
	.partial()
	.passthrough();

type TrafiklabRouteArgs = z.infer<typeof TrafiklabRouteArgsSchema>;
type TrafiklabRouteResult = z.infer<typeof TrafiklabRouteResultSchema>;

// ============================================================================
// UI Helpers
// ============================================================================

function RouteErrorState({ error }: { error: string }) {
	return (
		<div className="my-4 overflow-hidden rounded-xl border border-destructive/20 bg-destructive/5 p-4 w-full">
			<div className="flex items-center gap-4">
				<div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-destructive/10">
					<AlertCircleIcon className="size-6 text-destructive" />
				</div>
				<div className="flex-1 min-w-0">
					<p className="font-medium text-destructive text-sm">Failed to load departures</p>
					<p className="text-muted-foreground text-xs mt-1">{error}</p>
				</div>
			</div>
		</div>
	);
}

function RouteLoading() {
	return (
		<Card className="my-4 w-full animate-pulse">
			<CardContent className="p-4">
				<div className="h-4 w-1/2 rounded bg-muted" />
				<div className="mt-3 h-3 w-full rounded bg-muted" />
				<div className="mt-2 h-3 w-5/6 rounded bg-muted" />
			</CardContent>
		</Card>
	);
}

function formatTime(value: unknown): string {
	if (typeof value !== "string") return "";
	return value.replace("T", " ").slice(0, 16);
}

// ============================================================================
// Tool UI
// ============================================================================

export const TrafiklabRouteToolUI = makeAssistantToolUI<
	TrafiklabRouteArgs,
	TrafiklabRouteResult
>({
	toolName: "trafiklab_route",
	render: function TrafiklabRouteUI({ args, result, status }) {
		if (status.type === "running" || status.type === "requires-action") {
			return <RouteLoading />;
		}

		if (status.type === "incomplete") {
			if (status.reason === "cancelled") {
				return (
					<div className="my-4 rounded-xl border border-muted p-4 text-muted-foreground w-full">
						<p className="line-through">Route lookup cancelled</p>
					</div>
				);
			}
			if (status.reason === "error") {
				return (
					<RouteErrorState
						error={typeof status.error === "string" ? status.error : "An error occurred"}
					/>
				);
			}
		}

		if (!result) {
			return <RouteLoading />;
		}

		if (result.error || result.status === "error") {
			return <RouteErrorState error={result.error || "Route lookup failed"} />;
		}

		const originName =
			result.origin?.stop_group?.name || result.origin?.name || args.origin || "Origin";
		const destinationName =
			result.destination?.stop_group?.name ||
			result.destination?.name ||
			args.destination ||
			"Destination";
		const entries =
			(result.matching_entries && result.matching_entries.length > 0
				? result.matching_entries
				: result.entries) || [];
		const topEntries = entries.slice(0, 4);

		return (
			<Card className="my-4 w-full">
				<CardContent className="p-4">
					<div className="flex items-start justify-between gap-3">
						<div>
							<div className="text-sm text-muted-foreground">Trafiklab departures</div>
							<h3 className="mt-1 text-lg font-semibold">
								{originName} → {destinationName}
							</h3>
							{(result.requested_time || result.query_time) && (
								<p className="text-xs text-muted-foreground mt-1">
									Time: {formatTime(result.requested_time || result.query_time)}
								</p>
							)}
						</div>
						<span className="text-xs text-muted-foreground uppercase">{result.board_type}</span>
					</div>

					{topEntries.length === 0 ? (
						<p className="mt-4 text-sm text-muted-foreground">No matching departures found.</p>
					) : (
						<div className="mt-4 space-y-2">
							{topEntries.map((entry, index) => {
								const route = entry?.route || {};
								const departureTime = formatTime(entry?.realtime || entry?.scheduled);
								const line = route.designation || route.name || "Service";
								const direction =
									route.direction || route.destination?.name || "Unknown direction";
								const platform =
									entry?.realtime_platform?.designation ||
									entry?.scheduled_platform?.designation ||
									"--";
								const delay = typeof entry?.delay === "number" ? entry.delay : null;

								return (
									<div
										key={`${line}-${departureTime}-${index}`}
										className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-sm"
									>
										<div>
											<p className="font-medium">
												{line} · {direction}
											</p>
											<p className="text-xs text-muted-foreground">
												Platform {platform}
											</p>
										</div>
										<div className="text-right">
											<p className="font-semibold">{departureTime || "--"}</p>
											{delay !== null && delay > 0 && (
												<p className="text-xs text-amber-600">+{delay} min</p>
											)}
										</div>
									</div>
								);
							})}
							{entries.length > topEntries.length && (
								<p className="text-xs text-muted-foreground">
									+{entries.length - topEntries.length} more entries
								</p>
							)}
						</div>
					)}

					{result.attribution && (
						<Badge variant="secondary" className="mt-3 w-fit">
							{result.attribution}
						</Badge>
					)}
				</CardContent>
			</Card>
		);
	},
});
