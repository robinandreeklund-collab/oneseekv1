"use client";

import { motion, AnimatePresence } from "motion/react";
import { ChevronRightIcon } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// ============================================================================
// Types
// ============================================================================

export interface CompareProvider {
	key: string;
	displayName: string;
	status: "success" | "error";
	answer?: string;
	error?: string;
	latencyMs?: number;
	tokens?: number;
	co2g?: number;
	energyWh?: number;
	isEstimated?: boolean;
	toolName?: string;
	model?: string;
	provider?: string;
	modelString?: string;
	apiBase?: string;
}

export interface CompareSourcesBarProps {
	providers: CompareProvider[];
	onProviderClick: (providerKey: string) => void;
	isStreaming?: boolean;
}

// ============================================================================
// Constants
// ============================================================================

const MODEL_LOGOS: Record<string, { src: string; alt: string }> = {
	call_grok: { src: "/model-logos/grok.png", alt: "Grok" },
	call_gpt: { src: "/model-logos/chatgpt.png", alt: "ChatGPT" },
	call_claude: { src: "/model-logos/claude.png", alt: "Claude" },
	call_gemini: { src: "/model-logos/gemini.png", alt: "Gemini" },
	call_deepseek: { src: "/model-logos/deepseek.png", alt: "DeepSeek" },
	call_perplexity: { src: "/model-logos/perplexity.png", alt: "Perplexity" },
	call_qwen: { src: "/model-logos/qwen.png", alt: "Qwen" },
	call_oneseek: { src: "/model-logos/oneseek.png", alt: "Oneseek" },
};

// ============================================================================
// Helper Functions
// ============================================================================

function formatLatency(latencyMs?: number): string {
	if (typeof latencyMs !== "number" || Number.isNaN(latencyMs)) return "";
	if (latencyMs >= 1000) return `${(latencyMs / 1000).toFixed(1)}s`;
	return `${Math.round(latencyMs)}ms`;
}

function formatTokens(tokens?: number): string {
	if (typeof tokens !== "number" || Number.isNaN(tokens)) return "";
	if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`;
	return String(tokens);
}

function formatEstimate(value: number, unit: string): string {
	if (!Number.isFinite(value)) return "";
	if (value === 0) return `0${unit}`;
	if (value < 0.01) return `${value.toFixed(3)}${unit}`;
	if (value < 1) return `${value.toFixed(2)}${unit}`;
	return `${value.toFixed(2)}${unit}`;
}

// ============================================================================
// Provider Avatar Component
// ============================================================================

interface ProviderAvatarProps {
	provider: CompareProvider;
	onClick: () => void;
	index: number;
	isStreaming?: boolean;
}

function ProviderAvatar({ provider, onClick, index, isStreaming }: ProviderAvatarProps) {
	const [hasError, setHasError] = useState(false);
	const logo = provider.toolName ? MODEL_LOGOS[provider.toolName] : null;
	const latency = formatLatency(provider.latencyMs);
	const tokens = formatTokens(provider.tokens);
	const isPending = isStreaming && provider.status !== "success" && provider.status !== "error";

	return (
		<motion.button
			type="button"
			onClick={onClick}
			initial={{ opacity: 0, scale: 0.8 }}
			animate={{ opacity: 1, scale: 1 }}
			transition={{
				delay: index * 0.05,
				duration: 0.2,
				ease: "easeOut",
			}}
			className={cn(
				"flex flex-col items-center gap-1.5 rounded-lg p-2 transition-all",
				"hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
				isPending && "animate-pulse"
			)}
		>
			<div className="relative">
				{logo && !hasError ? (
					<img
						src={logo.src}
						alt={`${logo.alt} logo`}
						className="size-10 rounded-lg border border-border/60 bg-white object-contain p-1"
						loading="lazy"
						onError={() => setHasError(true)}
					/>
				) : (
					<div className="flex size-10 items-center justify-center rounded-lg border border-border/60 bg-muted text-xs font-semibold text-muted-foreground">
						{provider.displayName.charAt(0).toUpperCase()}
					</div>
				)}
				{/* Status dot */}
				<div
					className={cn(
						"absolute -right-0.5 -top-0.5 size-3 rounded-full border-2 border-background",
						provider.status === "success" && "bg-emerald-500",
						provider.status === "error" && "bg-destructive",
						isPending && "bg-yellow-500 animate-pulse"
					)}
				/>
			</div>
			<div className="flex flex-col items-center gap-0.5 text-xs">
				<span className="font-medium text-foreground">{provider.displayName}</span>
				{latency && <span className="text-muted-foreground">{latency}</span>}
				{tokens && <span className="text-muted-foreground">{tokens} tok</span>}
			</div>
		</motion.button>
	);
}

// ============================================================================
// Main Component
// ============================================================================

export function CompareSourcesBar({
	providers,
	onProviderClick,
	isStreaming = false,
}: CompareSourcesBarProps) {
	const [isOpen, setIsOpen] = useState(false);

	const successCount = providers.filter((p) => p.status === "success").length;
	const totalCount = providers.length;

	// Calculate aggregate stats
	const totalTokens = providers.reduce((sum, p) => sum + (p.tokens || 0), 0);
	const totalCO2 = providers.reduce((sum, p) => sum + (p.co2g || 0), 0);
	const totalEnergy = providers.reduce((sum, p) => sum + (p.energyWh || 0), 0);
	const fastestProvider = providers
		.filter((p) => p.status === "success" && typeof p.latencyMs === "number")
		.sort((a, b) => (a.latencyMs || 0) - (b.latencyMs || 0))[0];
	const avgLatency =
		providers
			.filter((p) => p.status === "success" && typeof p.latencyMs === "number")
			.reduce((sum, p) => sum + (p.latencyMs || 0), 0) /
		(successCount || 1);

	if (providers.length === 0) return null;

	return (
		<div className="my-3 mx-2">
			<div className="rounded-lg border border-border/60 bg-card/30 backdrop-blur-sm">
				{/* Header */}
				<button
					type="button"
					onClick={() => setIsOpen(!isOpen)}
					className={cn(
						"flex w-full items-center justify-between gap-2 px-4 py-3 text-left transition-colors",
						"hover:bg-muted/30"
					)}
				>
					<div className="flex items-center gap-2">
						<span className="text-sm font-medium text-foreground">
							🔍 Modellsvar {isStreaming ? `(${successCount}/${totalCount})` : `(${totalCount})`}
						</span>
						{isStreaming && (
							<Badge variant="secondary" className="text-[10px]">
								Hämtar svar...
							</Badge>
						)}
					</div>
					<ChevronRightIcon
						className={cn(
							"size-4 text-muted-foreground transition-transform duration-200",
							isOpen && "rotate-90"
						)}
					/>
				</button>

				{/* Collapsible content with CSS grid animation */}
				<div
					className={cn(
						"grid transition-[grid-template-rows] duration-300 ease-out",
						isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
					)}
				>
					<div className="overflow-hidden">
						<div className="border-t border-border/60 px-4 py-3">
							{/* Provider avatars row */}
							<ScrollArea className="w-full" orientation="horizontal">
								<div className="flex gap-3 pb-2">
									<AnimatePresence>
										{providers.map((provider, index) => (
											<ProviderAvatar
												key={provider.key}
												provider={provider}
												onClick={() => onProviderClick(provider.key)}
												index={index}
												isStreaming={isStreaming}
											/>
										))}
									</AnimatePresence>
								</div>
							</ScrollArea>

							{/* Aggregate stats footer */}
							{!isStreaming && successCount > 0 && (
								<div className="mt-3 flex flex-wrap items-center gap-3 border-t border-border/60 pt-3 text-xs text-muted-foreground">
									<Tooltip>
										<TooltipTrigger asChild>
											<span className="flex items-center gap-1">
												<span className="text-foreground font-medium">
													Σ {formatTokens(totalTokens)} tokens
												</span>
											</span>
										</TooltipTrigger>
										<TooltipContent>
											<p>Totalt antal tokens från alla modeller</p>
										</TooltipContent>
									</Tooltip>

									{totalCO2 > 0 && (
										<Tooltip>
											<TooltipTrigger asChild>
												<span className="flex items-center gap-1">
													🌱 {formatEstimate(totalCO2, "g")} CO₂
												</span>
											</TooltipTrigger>
											<TooltipContent>
												<p>Uppskattad koldioxidutsläpp</p>
											</TooltipContent>
										</Tooltip>
									)}

									{totalEnergy > 0 && (
										<Tooltip>
											<TooltipTrigger asChild>
												<span className="flex items-center gap-1">
													⚡ {formatEstimate(totalEnergy, "Wh")}
												</span>
											</TooltipTrigger>
											<TooltipContent>
												<p>Uppskattad energiförbrukning</p>
											</TooltipContent>
										</Tooltip>
									)}

									{fastestProvider && (
										<span className="flex items-center gap-1">
											<span>⚡ Snabbast:</span>
											<span className="text-foreground font-medium">
												{fastestProvider.displayName}
											</span>
										</span>
									)}

									<span className="flex items-center gap-1">
										<span>Medel:</span>
										<span className="text-foreground font-medium">
											{formatLatency(avgLatency)}
										</span>
									</span>
								</div>
							)}
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
