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

type WeatherCondition =
	| "clear"
	| "partly_cloudy"
	| "cloudy"
	| "fog"
	| "rain"
	| "snow"
	| "thunder";

function resolveWeatherCondition(symbol: number | undefined): WeatherCondition {
	if (symbol === undefined) return "cloudy";
	if (symbol <= 2) return "clear";
	if (symbol <= 4) return "partly_cloudy";
	if (symbol <= 6) return "cloudy";
	if (symbol === 7) return "fog";
	if (symbol <= 12) return "rain";
	if (symbol <= 19) return "snow";
	if (symbol <= 23) return "snow";
	return "thunder";
}

function resolveConditionLabel(condition: WeatherCondition, isDaytime: boolean): string {
	switch (condition) {
		case "clear":
			return isDaytime ? "Clear sky" : "Clear night";
		case "partly_cloudy":
			return "Partly cloudy";
		case "cloudy":
			return "Overcast";
		case "fog":
			return "Foggy";
		case "rain":
			return "Rain";
		case "snow":
			return "Snow";
		case "thunder":
			return "Thunder";
		default:
			return "Cloudy";
	}
}

function isDaytimeFromIso(value: string | undefined): boolean {
	if (!value) return true;
	const dt = new Date(value);
	if (Number.isNaN(dt.getTime())) return true;
	const hours = dt.getHours();
	return hours >= 6 && hours < 19;
}

function resolveSceneClasses(condition: WeatherCondition, isDaytime: boolean): string {
	if (condition === "clear") {
		return isDaytime
			? "from-sky-300 via-sky-200 to-amber-200"
			: "from-slate-900 via-indigo-900 to-slate-800";
	}
	if (condition === "partly_cloudy") {
		return isDaytime
			? "from-sky-300 via-blue-200 to-slate-200"
			: "from-slate-800 via-slate-900 to-indigo-900";
	}
	if (condition === "cloudy") {
		return isDaytime
			? "from-slate-300 via-slate-200 to-slate-100"
			: "from-slate-800 via-slate-900 to-slate-700";
	}
	if (condition === "fog") {
		return "from-slate-300 via-slate-200 to-slate-100";
	}
	if (condition === "snow") {
		return isDaytime ? "from-sky-200 via-slate-200 to-white" : "from-slate-900 via-slate-800 to-slate-700";
	}
	if (condition === "thunder") {
		return "from-slate-800 via-slate-900 to-indigo-950";
	}
	return isDaytime ? "from-sky-300 via-blue-200 to-slate-200" : "from-slate-900 via-slate-800 to-indigo-900";
}

function WeatherScene({
	condition,
	isDaytime,
}: {
	condition: WeatherCondition;
	isDaytime: boolean;
}) {
	const showRain = condition === "rain" || condition === "thunder";
	const showSnow = condition === "snow";
	const showClouds = condition !== "clear";
	const sunClass = isDaytime ? "bg-amber-300 shadow-amber-200/60" : "bg-slate-200 shadow-slate-200/50";
	const gradient = resolveSceneClasses(condition, isDaytime);

	return (
		<div className={`relative h-28 w-full overflow-hidden rounded-xl bg-gradient-to-br ${gradient}`}>
			<div className={`absolute right-6 top-4 size-12 rounded-full shadow-xl ${sunClass} weather-float`} />

			{showClouds && (
				<>
					<div className="absolute left-4 top-10 h-10 w-20 rounded-full bg-white/70 blur-sm weather-drift" />
					<div className="absolute left-16 top-6 h-8 w-14 rounded-full bg-white/60 blur-sm weather-drift-alt" />
				</>
			)}

			{showRain && (
				<div className="absolute inset-0">
					{Array.from({ length: 10 }).map((_, idx) => (
						<span
							key={`rain-${idx}`}
							className="weather-rain"
							style={{
								left: `${8 + idx * 8}%`,
								animationDelay: `${idx * 0.12}s`,
							}}
						/>
					))}
				</div>
			)}

			{showSnow && (
				<div className="absolute inset-0">
					{Array.from({ length: 8 }).map((_, idx) => (
						<span
							key={`snow-${idx}`}
							className="weather-snow"
							style={{
								left: `${12 + idx * 10}%`,
								animationDelay: `${idx * 0.25}s`,
							}}
						/>
					))}
				</div>
			)}

			<style jsx>{`
				.weather-float {
					animation: float 6s ease-in-out infinite;
				}
				.weather-drift {
					animation: drift 8s ease-in-out infinite;
				}
				.weather-drift-alt {
					animation: drift 9s ease-in-out infinite;
					animation-delay: 0.6s;
				}
				.weather-rain {
					position: absolute;
					top: 50%;
					width: 2px;
					height: 18px;
					background: rgba(255, 255, 255, 0.7);
					border-radius: 9999px;
					animation: rain 1.3s linear infinite;
				}
				.weather-snow {
					position: absolute;
					top: 50%;
					width: 6px;
					height: 6px;
					background: rgba(255, 255, 255, 0.9);
					border-radius: 9999px;
					animation: snow 2.8s ease-in-out infinite;
				}
				@keyframes float {
					0%,
					100% {
						transform: translateY(0);
					}
					50% {
						transform: translateY(-6px);
					}
				}
				@keyframes drift {
					0%,
					100% {
						transform: translateX(0);
					}
					50% {
						transform: translateX(12px);
					}
				}
				@keyframes rain {
					0% {
						transform: translateY(0);
						opacity: 0.6;
					}
					100% {
						transform: translateY(24px);
						opacity: 0;
					}
				}
				@keyframes snow {
					0% {
						transform: translateY(0);
						opacity: 0.8;
					}
					50% {
						opacity: 0.4;
					}
					100% {
						transform: translateY(20px);
						opacity: 0;
					}
				}
			`}</style>
		</div>
	);
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
		const symbol =
			getValue(summary.weather_symbol) ?? getValue(parameters.Wsymb2 as unknown);
		const isDaytime = isDaytimeFromIso(result.current?.valid_time || undefined);
		const condition = resolveWeatherCondition(symbol);
		const conditionLabel = resolveConditionLabel(condition, isDaytime);
		const updatedAt = result.current?.valid_time;

		return (
			<Card className="my-4 w-full max-w-md">
				<CardContent className="p-4">
					<div className="mb-4">
						<WeatherScene condition={condition} isDaytime={isDaytime} />
					</div>
					<div className="flex items-start justify-between gap-4">
						<div>
							<div className="text-sm text-muted-foreground">
								SMHI weather · {conditionLabel}
							</div>
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
