"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import {
	AlertCircleIcon,
	CloudIcon,
	CloudLightningIcon,
	CloudMoonIcon,
	CloudRainIcon,
	CloudSnowIcon,
	CloudSunIcon,
	MoonIcon,
	SunIcon,
} from "lucide-react";
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

const SmhiWeatherTimeseriesSchema = z
	.object({
		valid_time: z.string().nullish(),
		parameters: z.record(z.any()).nullish(),
	})
	.partial();

const SmhiWeatherResultSchema = z
	.object({
		status: z.string().nullish(),
		error: z.string().nullish(),
		attribution: z.string().nullish(),
		location: WeatherLocationSchema.nullish(),
		current: WeatherCurrentSchema.nullish(),
		timeseries: z.array(SmhiWeatherTimeseriesSchema).nullish(),
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
		<div className="my-4 overflow-hidden rounded-xl border border-destructive/20 bg-destructive/5 p-4 w-full">
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
		<Card className="my-4 w-full animate-pulse">
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
	if (symbol <= 10) return "rain";
	if (symbol === 11) return "thunder";
	if (symbol <= 14) return "rain";
	if (symbol <= 17) return "snow";
	if (symbol >= 18) return "thunder";
	return "cloudy";
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

type DayPhase = "night" | "dawn" | "day" | "dusk";

function resolveDayPhase(value: string | undefined): DayPhase {
	if (!value) return "day";
	const dt = new Date(value);
	if (Number.isNaN(dt.getTime())) return "day";
	const hours = dt.getHours();
	if (hours < 6 || hours >= 21) return "night";
	if (hours < 9) return "dawn";
	if (hours < 17) return "day";
	return "dusk";
}

function isDaytimeFromIso(value: string | undefined): boolean {
	if (!value) return true;
	const dt = new Date(value);
	if (Number.isNaN(dt.getTime())) return true;
	const hours = dt.getHours();
	return hours >= 6 && hours < 19;
}

function resolveSceneClasses(condition: WeatherCondition, phase: DayPhase): string {
	const isNight = phase === "night";
	const isDawn = phase === "dawn";
	const isDusk = phase === "dusk";
	if (isNight) {
		if (condition === "thunder") {
			return "from-slate-900 via-indigo-950 to-slate-950";
		}
		return "from-slate-900 via-indigo-900 to-slate-800";
	}
	if (isDawn || isDusk) {
		if (condition === "rain" || condition === "snow") {
			return "from-indigo-700 via-purple-600 to-slate-500";
		}
		return "from-fuchsia-500 via-orange-400 to-amber-300";
	}
	if (condition === "clear") {
		return "from-sky-300 via-sky-200 to-amber-200";
	}
	if (condition === "partly_cloudy") {
		return "from-sky-300 via-blue-200 to-slate-200";
	}
	if (condition === "cloudy") {
		return "from-slate-300 via-slate-200 to-slate-100";
	}
	if (condition === "fog") {
		return "from-slate-300 via-slate-200 to-slate-100";
	}
	if (condition === "snow") {
		return "from-sky-200 via-slate-200 to-white";
	}
	if (condition === "thunder") {
		return "from-slate-800 via-slate-900 to-indigo-950";
	}
	return "from-sky-300 via-blue-200 to-slate-200";
}

function WeatherScene({
	condition,
	phase,
}: {
	condition: WeatherCondition;
	phase: DayPhase;
}) {
	const isNight = phase === "night";
	const showRain = condition === "rain" || condition === "thunder";
	const showSnow = condition === "snow";
	const showClouds = condition !== "clear" || isNight;
	const showStars = isNight;
	const showLightning = condition === "thunder";
	const showFog = condition === "fog";
	const sunClass =
		isNight ? "bg-slate-200 shadow-slate-200/40" : "bg-amber-300 shadow-amber-200/60";
	const gradient = resolveSceneClasses(condition, phase);
	const rainDrops = Array.from({ length: 18 });
	const snowFlakes = Array.from({ length: 12 });
	const stars = Array.from({ length: 12 });

	return (
		<div className={`relative h-28 w-full overflow-hidden rounded-xl bg-gradient-to-br ${gradient}`}>
			<div className={`absolute right-6 top-4 size-12 rounded-full shadow-xl ${sunClass} weather-float`} />

			{showStars && (
				<div className="absolute inset-0">
					{stars.map((_, idx) => (
						<span
							key={`star-${idx}`}
							className="weather-star"
							style={{
								left: `${6 + (idx * 7) % 80}%`,
								top: `${6 + (idx * 11) % 40}%`,
								animationDelay: `${idx * 0.3}s`,
							}}
						/>
					))}
				</div>
			)}

			{showClouds && (
				<>
					<div className="absolute left-4 top-10 h-10 w-20 rounded-full bg-white/70 blur-sm weather-drift" />
					<div className="absolute left-16 top-6 h-8 w-14 rounded-full bg-white/60 blur-sm weather-drift-alt" />
					<div className="absolute right-16 top-14 h-8 w-16 rounded-full bg-white/50 blur-sm weather-drift-slow" />
				</>
			)}

			{showRain && (
				<div className="absolute inset-0">
					{rainDrops.map((_, idx) => (
						<span
							key={`rain-${idx}`}
							className="weather-rain"
							style={{
								left: `${6 + (idx * 6) % 90}%`,
								animationDelay: `${idx * 0.1}s`,
								animationDuration: `${1.1 + (idx % 5) * 0.15}s`,
							}}
						/>
					))}
				</div>
			)}

			{showSnow && (
				<div className="absolute inset-0">
					{snowFlakes.map((_, idx) => (
						<span
							key={`snow-${idx}`}
							className="weather-snow"
							style={{
								left: `${8 + (idx * 8) % 90}%`,
								animationDelay: `${idx * 0.2}s`,
								animationDuration: `${2.4 + (idx % 4) * 0.3}s`,
							}}
						/>
					))}
				</div>
			)}

			{showFog && <div className="absolute inset-0 bg-white/30 backdrop-blur-sm" />}

			{showLightning && <div className="absolute inset-0 weather-flash" />}

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
				.weather-drift-slow {
					animation: drift 12s ease-in-out infinite;
					animation-delay: 1.2s;
				}
				.weather-star {
					position: absolute;
					width: 2px;
					height: 2px;
					border-radius: 9999px;
					background: rgba(255, 255, 255, 0.8);
					animation: twinkle 3s ease-in-out infinite;
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
				.weather-flash {
					background: rgba(255, 255, 255, 0.6);
					animation: flash 3.2s ease-in-out infinite;
					opacity: 0;
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
				@keyframes twinkle {
					0%,
					100% {
						opacity: 0.5;
						transform: scale(1);
					}
					50% {
						opacity: 1;
						transform: scale(1.4);
					}
				}
				@keyframes rain {
					0% {
						transform: translateY(0);
						opacity: 0.6;
					}
					100% {
						transform: translateY(30px);
						opacity: 0;
					}
				}
				@keyframes snow {
					0% {
						transform: translate(0, 0);
						opacity: 0.8;
					}
					50% {
						opacity: 0.5;
						transform: translate(6px, 10px);
					}
					100% {
						transform: translate(-4px, 24px);
						opacity: 0;
					}
				}
				@keyframes flash {
					0%,
					85%,
					100% {
						opacity: 0;
					}
					88% {
						opacity: 0.7;
					}
					90% {
						opacity: 0.2;
					}
					92% {
						opacity: 0.6;
					}
				}
			`}</style>
		</div>
	);
}

function formatHour(value: string): string {
	const dt = new Date(value);
	if (Number.isNaN(dt.getTime())) return "";
	return new Intl.DateTimeFormat(undefined, {
		hour: "2-digit",
		minute: "2-digit",
	}).format(dt);
}

function formatWeekday(value: string): string {
	const dt = new Date(value);
	if (Number.isNaN(dt.getTime())) return "";
	return new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(dt);
}

function extractSymbol(parameters: Record<string, unknown>): number | undefined {
	const value = parameters.Wsymb2;
	return typeof value === "number" ? value : undefined;
}

function extractTemp(parameters: Record<string, unknown>): number | undefined {
	const value = parameters.t;
	return typeof value === "number" ? value : undefined;
}

function buildHourlyForecast(entries: { valid_time?: string | null; parameters?: Record<string, unknown> | null }[]) {
	const now = Date.now();
	const sorted = entries
		.filter((entry) => entry.valid_time && entry.parameters)
		.sort((a, b) => {
			const aTime = a.valid_time ? new Date(a.valid_time).getTime() : 0;
			const bTime = b.valid_time ? new Date(b.valid_time).getTime() : 0;
			return aTime - bTime;
		});
	const upcoming = sorted.filter((entry) => {
		const t = entry.valid_time ? new Date(entry.valid_time).getTime() : 0;
		return t >= now - 60 * 60 * 1000;
	});
	const pick = (upcoming.length ? upcoming : sorted).slice(0, 6);
	return pick.map((entry) => {
		const time = entry.valid_time || "";
		const parameters = entry.parameters || {};
		const symbol = extractSymbol(parameters);
		const temp = extractTemp(parameters);
		return { time, symbol, temp };
	});
}

function buildDailyForecast(entries: { valid_time?: string | null; parameters?: Record<string, unknown> | null }[]) {
	const grouped = new Map<string, { time: string; temps: number[]; symbols: number[] }>();
	for (const entry of entries) {
		if (!entry.valid_time || !entry.parameters) continue;
		const dateKey = entry.valid_time.slice(0, 10);
		const bucket = grouped.get(dateKey) || { time: entry.valid_time, temps: [], symbols: [] };
		const temp = extractTemp(entry.parameters);
		if (typeof temp === "number") bucket.temps.push(temp);
		const symbol = extractSymbol(entry.parameters);
		if (typeof symbol === "number") bucket.symbols.push(symbol);
		if (entry.valid_time > bucket.time) {
			bucket.time = entry.valid_time;
		}
		grouped.set(dateKey, bucket);
	}

	return Array.from(grouped.entries())
		.sort(([a], [b]) => a.localeCompare(b))
		.slice(0, 5)
		.map(([dateKey, bucket]) => {
			const temps = bucket.temps;
			const minTemp = temps.length ? Math.min(...temps) : undefined;
			const maxTemp = temps.length ? Math.max(...temps) : undefined;
			const symbol = bucket.symbols.length ? bucket.symbols[Math.floor(bucket.symbols.length / 2)] : undefined;
			return {
				date: dateKey,
				time: bucket.time,
				minTemp,
				maxTemp,
				symbol,
			};
		});
}

function ConditionIcon({
	condition,
	isDaytime,
}: {
	condition: WeatherCondition;
	isDaytime: boolean;
}) {
	const iconProps = { className: "size-5 text-white drop-shadow" };
	if (condition === "clear") {
		return isDaytime ? <SunIcon {...iconProps} /> : <MoonIcon {...iconProps} />;
	}
	if (condition === "partly_cloudy") {
		return isDaytime ? <CloudSunIcon {...iconProps} /> : <CloudMoonIcon {...iconProps} />;
	}
	if (condition === "rain") {
		return <CloudRainIcon {...iconProps} />;
	}
	if (condition === "snow") {
		return <CloudSnowIcon {...iconProps} />;
	}
	if (condition === "thunder") {
		return <CloudLightningIcon {...iconProps} />;
	}
	return <CloudIcon {...iconProps} />;
}

// ============================================================================
// Tool UI
// ============================================================================

function renderSmhiWeatherUI({
	args,
	result,
	status,
}: {
	args: SmhiWeatherArgs;
	result: SmhiWeatherResult | undefined;
	status: any;
}) {
	if (status.type === "running" || status.type === "requires-action") {
		return <WeatherLoading />;
	}

	if (status.type === "incomplete") {
		if (status.reason === "cancelled") {
			return (
				<div className="my-4 rounded-xl border border-muted p-4 text-muted-foreground w-full">
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
	const phase = resolveDayPhase(result.current?.valid_time || undefined);
	const timeseries = Array.isArray(result.timeseries) ? result.timeseries : [];
	const hourlyForecast = buildHourlyForecast(timeseries);
	const dailyForecast = buildDailyForecast(timeseries);
	const condition = resolveWeatherCondition(symbol);
	const conditionLabel = resolveConditionLabel(condition, isDaytime);
	const updatedAt = result.current?.valid_time;

	return (
		<Card className="my-4 w-full">
			<CardContent className="p-4">
				<div className="mb-4">
					<WeatherScene condition={condition} phase={phase} />
				</div>
				<div className="flex items-start justify-between gap-4">
					<div>
						<div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
							<span className="inline-flex items-center gap-2 rounded-full bg-slate-900/70 px-2 py-1 text-xs text-white">
								<ConditionIcon condition={condition} isDaytime={isDaytime} />
								<span>{conditionLabel}</span>
							</span>
							<span className="text-xs">SMHI weather</span>
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

				{hourlyForecast.length > 0 && (
					<div className="mt-4 rounded-lg border border-border/60 bg-background/60 p-3">
						<p className="text-xs font-semibold text-muted-foreground">Next hours</p>
						<div className="mt-2 flex flex-wrap gap-3">
							{hourlyForecast.map((entry) => {
								const entryCondition = resolveWeatherCondition(entry.symbol);
								const entryIsDay = isDaytimeFromIso(entry.time);
								return (
									<div
										key={`hour-${entry.time}`}
										className="flex min-w-[72px] flex-col items-center gap-1 text-xs text-muted-foreground"
									>
										<span>{formatHour(entry.time)}</span>
										<div className="rounded-full bg-slate-900/70 p-1.5">
											<ConditionIcon condition={entryCondition} isDaytime={entryIsDay} />
										</div>
										<span className="text-foreground">
											{entry.temp !== undefined ? `${entry.temp}°C` : "--"}
										</span>
									</div>
								);
							})}
						</div>
					</div>
				)}

				{dailyForecast.length > 1 && (
					<div className="mt-3 rounded-lg border border-border/60 bg-background/60 p-3">
						<p className="text-xs font-semibold text-muted-foreground">Next days</p>
						<div className="mt-2 flex flex-wrap gap-3">
							{dailyForecast.map((entry) => {
								const entryCondition = resolveWeatherCondition(entry.symbol);
								const entryIsDay = isDaytimeFromIso(entry.time);
								return (
									<div
										key={`day-${entry.date}`}
										className="flex min-w-[80px] flex-col items-center gap-1 text-xs text-muted-foreground"
									>
										<span>{formatWeekday(entry.time)}</span>
										<div className="rounded-full bg-slate-900/70 p-1.5">
											<ConditionIcon condition={entryCondition} isDaytime={entryIsDay} />
										</div>
										<span className="text-foreground">
											{entry.minTemp !== undefined && entry.maxTemp !== undefined
												? `${entry.minTemp}°C / ${entry.maxTemp}°C`
												: "--"}
										</span>
									</div>
								);
							})}
						</div>
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
}

export const SmhiWeatherToolUI = makeAssistantToolUI<SmhiWeatherArgs, SmhiWeatherResult>({
	toolName: "smhi_weather",
	render: renderSmhiWeatherUI,
});

export const SmhiMetfcstToolUI = makeAssistantToolUI<SmhiWeatherArgs, SmhiWeatherResult>({
	toolName: "smhi_vaderprognoser_metfcst",
	render: renderSmhiWeatherUI,
});
