"use client";

import { useEffect, useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon, XIcon } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Drawer, DrawerContent, DrawerHandle, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { useMediaQuery } from "@/hooks/use-media-query";
import { cn } from "@/lib/utils";
import type { CompareProvider } from "./compare-sources-bar";

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
// Types
// ============================================================================

export interface CompareDetailSheetProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	providers: CompareProvider[];
	selectedProviderKey: string | null;
	onSelectProvider: (providerKey: string) => void;
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatLatency(latencyMs?: number): string {
	if (typeof latencyMs !== "number" || Number.isNaN(latencyMs)) return "—";
	if (latencyMs >= 1000) return `${(latencyMs / 1000).toFixed(1)}s`;
	return `${Math.round(latencyMs)}ms`;
}

function formatTokens(tokens?: number): string {
	if (typeof tokens !== "number" || Number.isNaN(tokens)) return "—";
	if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`;
	return String(tokens);
}

function formatEstimate(value: number | undefined, unit: string): string {
	if (typeof value !== "number" || !Number.isFinite(value)) return "—";
	if (value === 0) return `0${unit}`;
	if (value < 0.01) return `${value.toFixed(3)}${unit}`;
	if (value < 1) return `${value.toFixed(2)}${unit}`;
	return `${value.toFixed(2)}${unit}`;
}

// ============================================================================
// Provider Detail Component
// ============================================================================

interface ProviderDetailProps {
	provider: CompareProvider;
	onNavigatePrev: () => void;
	onNavigateNext: () => void;
	canNavigatePrev: boolean;
	canNavigateNext: boolean;
	currentIndex: number;
	totalCount: number;
}

function ProviderDetail({
	provider,
	onNavigatePrev,
	onNavigateNext,
	canNavigatePrev,
	canNavigateNext,
	currentIndex,
	totalCount,
}: ProviderDetailProps) {
	const [hasError, setHasError] = useState(false);
	const [metadataOpen, setMetadataOpen] = useState(false);
	const logo = provider.toolName ? MODEL_LOGOS[provider.toolName] : null;

	return (
		<div className="flex h-full flex-col">
			<ScrollArea className="flex-1">
				<div className="space-y-4 p-4">
					{/* Provider header */}
					<div className="flex items-center gap-3">
						<div className="relative">
							{logo && !hasError ? (
								<img
									src={logo.src}
									alt={`${logo.alt} logo`}
									className="size-12 rounded-lg border border-border/60 bg-white object-contain p-1.5"
									loading="lazy"
									onError={() => setHasError(true)}
								/>
							) : (
								<div className="flex size-12 items-center justify-center rounded-lg border border-border/60 bg-muted text-sm font-semibold text-muted-foreground">
									{provider.displayName.charAt(0).toUpperCase()}
								</div>
							)}
							{/* Status indicator */}
							<div
								className={cn(
									"absolute -right-1 -top-1 size-4 rounded-full border-2 border-background",
									provider.status === "success" && "bg-emerald-500",
									provider.status === "error" && "bg-destructive"
								)}
							/>
						</div>
						<div className="flex-1">
							<h3 className="text-lg font-semibold text-foreground">
								{provider.displayName}
							</h3>
							<div className="flex flex-wrap items-center gap-2 mt-1">
								{provider.provider && (
									<Badge variant="secondary" className="text-xs">
										{provider.provider}
									</Badge>
								)}
								{provider.model && (
									<span className="text-xs text-muted-foreground">{provider.model}</span>
								)}
							</div>
						</div>
					</div>

					{/* Stats grid */}
					<div className="grid grid-cols-4 gap-2">
						<div className="rounded-lg border border-border/60 bg-muted/30 p-2">
							<div className="text-xs text-muted-foreground mb-1">Svarstid</div>
							<div className="text-sm font-semibold text-foreground">
								{formatLatency(provider.latencyMs)}
							</div>
						</div>
						<div className="rounded-lg border border-border/60 bg-muted/30 p-2">
							<div className="text-xs text-muted-foreground mb-1">Tokens</div>
							<div className="text-sm font-semibold text-foreground">
								{formatTokens(provider.tokens)}
							</div>
						</div>
						<div className="rounded-lg border border-border/60 bg-muted/30 p-2">
							<div className="text-xs text-muted-foreground mb-1">CO₂</div>
							<div className="text-sm font-semibold text-foreground">
								{formatEstimate(provider.co2g, "g")}
							</div>
						</div>
						<div className="rounded-lg border border-border/60 bg-muted/30 p-2">
							<div className="text-xs text-muted-foreground mb-1">Energi</div>
							<div className="text-sm font-semibold text-foreground">
								{formatEstimate(provider.energyWh, "Wh")}
							</div>
						</div>
					</div>

					{/* Full response */}
					{provider.status === "success" && provider.answer && (
						<div className="rounded-lg border border-border/60 bg-card/40 p-4">
							<div className="text-sm font-semibold text-foreground mb-3">Fullständigt svar</div>
							<div className="prose prose-sm dark:prose-invert max-w-none">
								<MarkdownText content={{ type: "text", text: provider.answer }} />
							</div>
						</div>
					)}

					{/* Error state */}
					{provider.status === "error" && (
						<div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4">
							<div className="text-sm font-semibold text-destructive mb-2">Fel uppstod</div>
							<p className="text-sm text-muted-foreground">
								{provider.error || "Ett okänt fel uppstod"}
							</p>
						</div>
					)}

					{/* Metadata section (collapsible) */}
					{(provider.modelString || provider.apiBase) && (
						<Collapsible open={metadataOpen} onOpenChange={setMetadataOpen}>
							<div className="border-t border-border/60 pt-3">
								<CollapsibleTrigger asChild>
									<Button
										variant="ghost"
										size="sm"
										className="w-full justify-between text-xs"
									>
										<span>Metadata</span>
										<ChevronRightIcon
											className={cn(
												"size-4 transition-transform",
												metadataOpen && "rotate-90"
											)}
										/>
									</Button>
								</CollapsibleTrigger>
								<CollapsibleContent>
									<div className="mt-2 space-y-2 text-xs">
										{provider.modelString && (
											<div className="flex justify-between gap-2">
												<span className="text-muted-foreground">Model string:</span>
												<span className="text-foreground font-mono">
													{provider.modelString}
												</span>
											</div>
										)}
										{provider.apiBase && (
											<div className="flex justify-between gap-2">
												<span className="text-muted-foreground">API base:</span>
												<span className="text-foreground font-mono break-all">
													{provider.apiBase}
												</span>
											</div>
										)}
									</div>
								</CollapsibleContent>
							</div>
						</Collapsible>
					)}
				</div>
			</ScrollArea>

			{/* Bottom navigation */}
			<div className="border-t border-border/60 p-4 bg-card/30">
				<div className="flex items-center justify-between gap-4">
					<Button
						variant="outline"
						size="sm"
						onClick={onNavigatePrev}
						disabled={!canNavigatePrev}
						className="gap-1"
					>
						<ChevronLeftIcon className="size-4" />
						Föregående
					</Button>

					{/* Dot indicators */}
					<div className="flex items-center gap-1.5">
						{Array.from({ length: totalCount }).map((_, i) => (
							<div
								key={i}
								className={cn(
									"size-1.5 rounded-full transition-colors",
									i === currentIndex ? "bg-primary" : "bg-muted-foreground/30"
								)}
							/>
						))}
					</div>

					<Button
						variant="outline"
						size="sm"
						onClick={onNavigateNext}
						disabled={!canNavigateNext}
						className="gap-1"
					>
						Nästa
						<ChevronRightIcon className="size-4" />
					</Button>
				</div>
			</div>
		</div>
	);
}

// ============================================================================
// Main Component
// ============================================================================

export function CompareDetailSheet({
	open,
	onOpenChange,
	providers,
	selectedProviderKey,
	onSelectProvider,
}: CompareDetailSheetProps) {
	const isMobile = useMediaQuery("(max-width: 767px)");

	const currentIndex = providers.findIndex((p) => p.key === selectedProviderKey);
	const selectedProvider = currentIndex >= 0 ? providers[currentIndex] : null;

	const handleNavigatePrev = () => {
		if (currentIndex > 0) {
			onSelectProvider(providers[currentIndex - 1].key);
		}
	};

	const handleNavigateNext = () => {
		if (currentIndex < providers.length - 1) {
			onSelectProvider(providers[currentIndex + 1].key);
		}
	};

	// Keyboard navigation
	useEffect(() => {
		if (!open) return;

		const handleKeyDown = (e: KeyboardEvent) => {
			if (e.key === "ArrowLeft" && currentIndex > 0) {
				handleNavigatePrev();
			} else if (e.key === "ArrowRight" && currentIndex < providers.length - 1) {
				handleNavigateNext();
			} else if (e.key === "Escape") {
				onOpenChange(false);
			}
		};

		window.addEventListener("keydown", handleKeyDown);
		return () => window.removeEventListener("keydown", handleKeyDown);
	}, [open, currentIndex, providers.length]);

	if (!selectedProvider) return null;

	const content = (
		<ProviderDetail
			provider={selectedProvider}
			onNavigatePrev={handleNavigatePrev}
			onNavigateNext={handleNavigateNext}
			canNavigatePrev={currentIndex > 0}
			canNavigateNext={currentIndex < providers.length - 1}
			currentIndex={currentIndex}
			totalCount={providers.length}
		/>
	);

	const title = (
		<div className="flex items-center gap-2">
			<span>Modelljämförelse</span>
			<Badge variant="secondary" className="text-xs">
				{currentIndex + 1} av {providers.length}
			</Badge>
		</div>
	);

	// Mobile: Drawer
	if (isMobile) {
		return (
			<Drawer open={open} onOpenChange={onOpenChange} shouldScaleBackground={false}>
				<DrawerContent className="h-[85vh] max-h-[85vh]">
					<DrawerHandle />
					<DrawerHeader className="border-b border-border/60">
						<DrawerTitle>{title}</DrawerTitle>
					</DrawerHeader>
					{content}
				</DrawerContent>
			</Drawer>
		);
	}

	// Desktop: Sheet
	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent
				side="right"
				className="flex h-full w-[480px] max-w-full flex-col gap-0 overflow-hidden p-0"
			>
				<SheetHeader className="border-b border-border/60 px-4 py-4">
					<SheetTitle>{title}</SheetTitle>
				</SheetHeader>
				{content}
			</SheetContent>
		</Sheet>
	);
}
