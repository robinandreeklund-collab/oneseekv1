"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { AlertCircleIcon } from "lucide-react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

// ============================================================================
// Zod Schemas
// ============================================================================

const WeatherLocationSchema = z
	.object({
		name: z.string().nullish(),
		display_name: z.string().nullish(),
		lat: z.number().nullish(),
		lon: z.number().nullish(),
		source: z.string().nullish(),
	})
	.partial();

const WeatherSummarySchema = z
	.object({
		temperature_c: z.number().nullish(),
		wind_speed_m_s: z.number().nullish(),
		wind_gust_m_s: z.number().nullish(),
		wind_direction_deg: z.number().nullish(),
		relative_humidity: z.number().nullish(),
		pressure_hpa: z.number().nullish(),
		cloud_cover: z.number().nullish(),
		weather_symbol: z.number().nullish(),
		precipitation_mean: z.number().nullish(),
	})
	.partial();

const WeatherCurrentSchema = z
	.object({
		valid_time: z.string().nullish(),
		parameters: z.record(z.any()).nullish(),
		summary: WeatherSummarySchema.nullish(),
	})
	.partial();

const SmhiWeatherArgsSchema = z
	.object({
		location: z.string().nullish(),
		lat: z.number().nullish(),
		lon: z.number().nullish(),
		max_hours: z.number().nullish(),
		include_raw: z.boolean().nullish(),
	})
	.partial();

const SmhiWeatherResultSchema = z
	.object({
		status: z.string().nullish(),
		error: z.string().nullish(),
		attribution: z.string().nullish(),
		location: WeatherLocationSchema.nullish(),
		current: WeatherCurrentSchema.nullish(),
	})
	.partial()
	.passthrough();

type SmhiWeatherArgs = z.infer<typeof SmhiWeatherArgsSchema>;
type SmhiWeatherResult = z.infer<typeof SmhiWeatherResultSchema>;

// ============================================================================
// UI Helpers
// ============================================================================

function WeatherErrorState({ error }: { error: string }) {
	return (
		<div className="my-4 overflow-hidden rounded-xl border border-destructive/20 bg-destructive/5 p-4 max-w-md">
			<div className="flex items-center gap-4">
				<div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-destructive/10">
					<AlertCircleIcon className="size-6 text-destructive" />
				</div>
				<div className="flex-1 min-w-0">
					<p className="font-medium text-destructive text-sm">Failed to fetch weather</p>
					<p className="text-muted-foreground text-xs mt-1">{error}</p>
				</div>
			</div>
		</div>
	);
}

function WeatherLoading() {
	return (
		<Card className="my-4 w-full max-w-md animate-pulse">
			<CardContent className="p-4">
				<div className="h-4 w-1/3 rounded bg-muted" />
				<div className="mt-3 h-8 w-1/2 rounded bg-muted" />
				<div className="mt-3 h-3 w-full rounded bg-muted" />
			</CardContent>
		</Card>
	);
}

function getValue(value: unknown): number | undefined {
	return typeof value === "number" ? value : undefined;
}

// ============================================================================
// Tool UI
// ============================================================================

export const SmhiWeatherToolUI = makeAssistantToolUI<SmhiWeatherArgs, SmhiWeatherResult>({
	toolName: "smhi_weather",
	render: function SmhiWeatherUI({ args, result, status }) {
		if (status.type === "running" || status.type === "requires-action") {
			return <WeatherLoading />;
		}

		if (status.type === "incomplete") {
			if (status.reason === "cancelled") {
				return (
					<div className="my-4 rounded-xl border border-muted p-4 text-muted-foreground max-w-md">
						<p className="line-through">Weather lookup cancelled</p>
					</div>
				);
			}
			if (status.reason === "error") {
				return (
					<WeatherErrorState
						error={typeof status.error === "string" ? status.error : "An error occurred"}
					/>
				);
			}
		}

		if (!result) {
			return <WeatherLoading />;
		}

		if (result.error || result.status === "error") {
			return <WeatherErrorState error={result.error || "Weather lookup failed"} />;
		}

		const locationName =
			result.location?.name ||
			result.location?.display_name ||
			args.location ||
			(result.location?.lat && result.location?.lon
				? `${result.location.lat}, ${result.location.lon}`
				: "Unknown location");
		const summary = result.current?.summary || {};
		const parameters = result.current?.parameters || {};
		const temperature =
			getValue(summary.temperature_c) ?? getValue(parameters.t as unknown);
		const windSpeed =
			getValue(summary.wind_speed_m_s) ?? getValue(parameters.ws as unknown);
		const humidity =
			getValue(summary.relative_humidity) ?? getValue(parameters.r as unknown);
		const pressure =
			getValue(summary.pressure_hpa) ?? getValue(parameters.msl as unknown);
		const updatedAt = result.current?.valid_time;

		return (
			<Card className="my-4 w-full max-w-md">
				<CardContent className="p-4">
					<div className="flex items-start justify-between gap-4">
						<div>
							<div className="text-sm text-muted-foreground">SMHI weather</div>
							<h3 className="mt-1 text-lg font-semibold">{locationName}</h3>
							{updatedAt && (
								<p className="text-xs text-muted-foreground mt-1">Updated: {updatedAt}</p>
							)}
						</div>
						<div className="text-right">
							<div className="text-3xl font-semibold">
								{temperature !== undefined ? `${temperature}°C` : "--"}
							</div>
							<div className="mt-1 text-xs text-muted-foreground">
								{windSpeed !== undefined ? `Wind ${windSpeed} m/s` : "Wind --"}
							</div>
						</div>
					</div>

					<div className="mt-3 grid grid-cols-2 gap-2 text-sm text-muted-foreground">
						<div>Humidity: {humidity !== undefined ? `${humidity}%` : "--"}</div>
						<div>Pressure: {pressure !== undefined ? `${pressure} hPa` : "--"}</div>
					</div>

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
