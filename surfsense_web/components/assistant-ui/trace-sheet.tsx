"use client";

import {
	Activity,
	AlertCircle,
	CheckCircle2,
	ChevronRight,
	CircleDot,
	Copy,
	Download,
} from "lucide-react";
import { type PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import YAML from "yaml";
import { Button } from "@/components/ui/button";
import {
	Drawer,
	DrawerContent,
	DrawerHandle,
	DrawerHeader,
	DrawerTitle,
} from "@/components/ui/drawer";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { TraceSpan } from "@/contracts/types/chat-trace.types";
import { useMediaQuery } from "@/hooks/use-media-query";
import { cn } from "@/lib/utils";

interface TraceSheetProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	messageId: string | null;
	sessionId: string | null;
	spans: TraceSpan[];
	variant?: "overlay" | "inline";
	dock?: "left" | "right";
	minWidth?: number;
	maxWidth?: number;
}

const MIN_WIDTH = 420;
const MAX_WIDTH = 980;

function formatDuration(durationMs?: number | null) {
	if (!durationMs || durationMs <= 0) return "...";
	const seconds = durationMs / 1000;
	return `${seconds.toFixed(seconds < 10 ? 2 : 1)}s`;
}

function formatPayload(payload: unknown, mode: "json" | "yaml" | "raw") {
	if (payload === null || payload === undefined) return "";
	try {
		if (mode === "raw") {
			if (typeof payload === "string") return payload;
			return JSON.stringify(payload, null, 2);
		}
		if (mode === "yaml") {
			return YAML.stringify(payload, { indent: 2 });
		}
		return JSON.stringify(payload, null, 2);
	} catch (_error) {
		return typeof payload === "string" ? payload : String(payload);
	}
}

function toSafeFilenameSegment(value: string | null | undefined) {
	if (!value) return "";
	return value
		.replace(/[^a-zA-Z0-9_-]+/g, "-")
		.replace(/-+/g, "-")
		.replace(/^-|-$/g, "")
		.slice(0, 48);
}

function extractAttribution(span: TraceSpan | null) {
	if (!span) return [];
	const meta = typeof span.meta === "object" && span.meta ? span.meta : {};
	const output = typeof span.output === "object" && span.output ? span.output : {};
	const attribution = (meta as Record<string, unknown>).attribution ?? output.attribution;
	const source = (meta as Record<string, unknown>).source ?? output.source;
	const url =
		(meta as Record<string, unknown>).source_url ??
		output.source_url ??
		(meta as Record<string, unknown>).url ??
		output.url;
	const entries: Array<{ label: string; value: string }> = [];
	if (attribution && typeof attribution === "string") {
		entries.push({ label: "Attribution", value: attribution });
	}
	if (source && typeof source === "string") {
		entries.push({ label: "Source", value: source });
	}
	if (url && typeof url === "string") {
		entries.push({ label: "URL", value: url });
	}
	return entries;
}

function getTokenInfo(span: TraceSpan | null) {
	if (!span || !span.meta || typeof span.meta !== "object") return null;
	const meta = span.meta as Record<string, unknown>;
	const inputTokens = Number(meta.input_tokens ?? 0);
	const outputTokens = Number(meta.output_tokens ?? 0);
	const totalTokens = Number(meta.total_tokens ?? 0);
	const resolvedTotal =
		Number.isFinite(totalTokens) && totalTokens > 0 ? totalTokens : inputTokens + outputTokens;
	if (!resolvedTotal) return null;
	return {
		total: resolvedTotal,
		input: Number.isFinite(inputTokens) ? inputTokens : 0,
		output: Number.isFinite(outputTokens) ? outputTokens : 0,
	};
}

export function TraceSheet({
	open,
	onOpenChange,
	messageId,
	sessionId,
	spans,
	variant = "overlay",
	dock = "right",
	minWidth = MIN_WIDTH,
	maxWidth = MAX_WIDTH,
}: TraceSheetProps) {
	const isMobile = useMediaQuery("(max-width: 767px)");
	const [panelWidth, setPanelWidth] = useState(720);
	const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
	const [followLive, setFollowLive] = useState(true);
	const [isJustExported, setIsJustExported] = useState(false);
	const [isDragging, setIsDragging] = useState(false);
	const startXRef = useRef(0);
	const startWidthRef = useRef(0);
	const exportFeedbackTimerRef = useRef<number | null>(null);
	const previousMessageIdRef = useRef<string | null>(null);

	const sortedSpans = useMemo(() => {
		const next = [...spans];
		next.sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
		return next;
	}, [spans]);

	const spanMap = useMemo(() => {
		return new Map(sortedSpans.map((span) => [span.id, span]));
	}, [sortedSpans]);

	const depthMap = useMemo(() => {
		const memo = new Map<string, number>();
		const getDepth = (span: TraceSpan): number => {
			if (memo.has(span.id)) return memo.get(span.id) ?? 0;
			if (!span.parent_id) {
				memo.set(span.id, 0);
				return 0;
			}
			const parent = spanMap.get(span.parent_id);
			const depth = parent ? getDepth(parent) + 1 : 0;
			memo.set(span.id, depth);
			return depth;
		};
		sortedSpans.forEach((span) => {
			getDepth(span);
		});
		return memo;
	}, [sortedSpans, spanMap]);

	const activeSpan = useMemo(() => {
		const running = sortedSpans.filter((span) => span.status === "running");
		if (running.length > 0) return running[running.length - 1];
		return sortedSpans[sortedSpans.length - 1] ?? null;
	}, [sortedSpans]);

	const selectedSpan = useMemo(() => {
		if (!selectedSpanId) return activeSpan;
		return spanMap.get(selectedSpanId) ?? activeSpan;
	}, [selectedSpanId, spanMap, activeSpan]);

	useEffect(() => {
		if (!open) return;
		if (followLive && activeSpan) {
			setSelectedSpanId(activeSpan.id);
		}
	}, [activeSpan, followLive, open]);

	useEffect(() => {
		if (open) return;
		setSelectedSpanId(null);
		setFollowLive(true);
		setIsJustExported(false);
	}, [open]);

	useEffect(() => {
		if (previousMessageIdRef.current === messageId) return;
		previousMessageIdRef.current = messageId;
		setSelectedSpanId(null);
		setFollowLive(true);
		setIsJustExported(false);
	}, [messageId]);

	useEffect(() => {
		return () => {
			if (exportFeedbackTimerRef.current) {
				window.clearTimeout(exportFeedbackTimerRef.current);
			}
		};
	}, []);

	useEffect(() => {
		if (!isDragging) return;
		const handlePointerMove = (event: globalThis.PointerEvent) => {
			const delta =
				dock === "right" ? startXRef.current - event.clientX : event.clientX - startXRef.current;
			const nextWidth = Math.min(maxWidth, Math.max(minWidth, startWidthRef.current + delta));
			setPanelWidth(nextWidth);
		};
		const handlePointerUp = () => {
			setIsDragging(false);
			document.body.style.cursor = "";
		};
		window.addEventListener("pointermove", handlePointerMove);
		window.addEventListener("pointerup", handlePointerUp);
		return () => {
			window.removeEventListener("pointermove", handlePointerMove);
			window.removeEventListener("pointerup", handlePointerUp);
		};
	}, [dock, isDragging, maxWidth, minWidth]);

	const handleResizeStart = (event: PointerEvent<HTMLDivElement>) => {
		event.preventDefault();
		setIsDragging(true);
		startXRef.current = event.clientX;
		startWidthRef.current = panelWidth;
		document.body.style.cursor = "col-resize";
	};

	const attributionEntries = extractAttribution(selectedSpan);
	const selectedTokenInfo = getTokenInfo(selectedSpan);
	const canExportTrace = sortedSpans.length > 0 || Boolean(sessionId);

	const handleExportJson = () => {
		if (!canExportTrace) return;
		const runningSpans = sortedSpans.filter((span) => span.status === "running").length;
		const errorSpans = sortedSpans.filter((span) => span.status === "error").length;
		const maxDepth = sortedSpans.reduce((currentMax, span) => {
			return Math.max(currentMax, depthMap.get(span.id) ?? 0);
		}, 0);
		const payload = {
			export_type: "oneseek-live-trace",
			export_version: 1,
			exported_at: new Date().toISOString(),
			message_id: messageId,
			session_id: sessionId,
			ui_state: {
				follow_live: followLive,
				active_span_id: activeSpan?.id ?? null,
				selected_span_id: selectedSpan?.id ?? null,
			},
			summary: {
				total_spans: sortedSpans.length,
				running_spans: runningSpans,
				error_spans: errorSpans,
				completed_spans: Math.max(0, sortedSpans.length - runningSpans - errorSpans),
				max_depth: maxDepth,
			},
			spans: sortedSpans.map((span) => ({
				...span,
				tree_depth: depthMap.get(span.id) ?? 0,
			})),
		};
		const json = JSON.stringify(payload, null, 2);
		const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
		const sessionSegment = toSafeFilenameSegment(sessionId);
		const messageSegment = toSafeFilenameSegment(messageId);
		const targetSegment = sessionSegment || messageSegment || "trace";
		const fileName = `oneseek-live-trace-${targetSegment}-${timestamp}.json`;
		const blob = new Blob([json], { type: "application/json;charset=utf-8" });
		const objectUrl = URL.createObjectURL(blob);
		const anchor = document.createElement("a");
		anchor.href = objectUrl;
		anchor.download = fileName;
		document.body.appendChild(anchor);
		anchor.click();
		anchor.remove();
		URL.revokeObjectURL(objectUrl);
		setIsJustExported(true);
		if (exportFeedbackTimerRef.current) {
			window.clearTimeout(exportFeedbackTimerRef.current);
		}
		exportFeedbackTimerRef.current = window.setTimeout(() => {
			setIsJustExported(false);
		}, 1500);
	};

	const headerContent = (
		<div className="flex items-center justify-between gap-3">
			<div className="flex items-center gap-2">
				<div className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
					<Activity className={cn("size-5", open && "animate-pulse")} />
				</div>
				<div>
					<div className="text-sm font-semibold">Live-spårning</div>
					<div className="text-xs text-muted-foreground">
						{sessionId ? `Session ${sessionId.slice(0, 8)}…` : "Ingen session ännu"}
					</div>
				</div>
			</div>
			<div className="flex items-center gap-2">
				<Button
					variant="ghost"
					size="sm"
					onClick={() => setFollowLive((prev) => !prev)}
					className={cn("text-xs", followLive && "text-primary")}
				>
					{followLive ? "Följer live" : "Pausa följning"}
				</Button>
				<Button
					variant="outline"
					size="sm"
					onClick={handleExportJson}
					disabled={!canExportTrace}
					className="gap-1.5 text-xs"
				>
					{isJustExported ? (
						<CheckCircle2 className="size-3.5 text-emerald-500" />
					) : (
						<Download className="size-3.5" />
					)}
					{isJustExported ? "Exporterad" : "Exportera JSON"}
				</Button>
			</div>
		</div>
	);

	const treeColumns = useMemo(() => {
		const childrenMap = new Map<string, TraceSpan[]>();
		sortedSpans.forEach((span) => {
			if (!span.parent_id) return;
			const list = childrenMap.get(span.parent_id) ?? [];
			list.push(span);
			childrenMap.set(span.parent_id, list);
		});
		const lastChildMap = new Map<string, string>();
		childrenMap.forEach((list, parentId) => {
			list.sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
			const lastChild = list[list.length - 1];
			if (lastChild) {
				lastChildMap.set(parentId, lastChild.id);
			}
		});
		const lineMap = new Map<string, boolean[]>();
		sortedSpans.forEach((span) => {
			const segments: boolean[] = [];
			const chain: Array<{ parent: TraceSpan; child: TraceSpan }> = [];
			let current: TraceSpan | undefined = span;
			while (current?.parent_id) {
				const parent = spanMap.get(current.parent_id);
				if (!parent) break;
				chain.push({ parent, child: current });
				current = parent;
			}
			chain.reverse().forEach(({ parent, child }) => {
				segments.push(lastChildMap.get(parent.id) !== child.id);
			});
			lineMap.set(span.id, segments);
		});
		return { lineMap, lastChildMap };
	}, [sortedSpans, spanMap]);

	const content = (
		<div className="relative flex h-full flex-col bg-gradient-to-b from-background via-background/95 to-background/90">
			<div
				onPointerDown={handleResizeStart}
				className={cn(
					"absolute top-0 h-full cursor-col-resize bg-border/50 hover:bg-primary/40 touch-none z-20",
					dock === "right" ? "-left-1 w-2" : "-right-1 w-2"
				)}
			/>
			<div className="flex h-full min-h-0 flex-1 overflow-hidden">
				<div className="flex w-1/2 min-h-0 flex-col border-r border-border/60 bg-card/40 backdrop-blur-xl">
					<div className="flex items-center justify-between border-b border-border/60 px-4 py-3 text-xs uppercase tracking-wide text-muted-foreground">
						<span>Waterfall</span>
						<span>{sortedSpans.length} steg</span>
					</div>
					<ScrollArea className="flex-1 min-h-0">
						<div className="space-y-2 px-3 pb-6">
							{sortedSpans.length === 0 && (
								<div className="rounded-lg border border-dashed border-border/60 p-4 text-sm text-muted-foreground">
									Inga spårningssteg ännu.
								</div>
							)}
							{sortedSpans.map((span) => {
								const depth = depthMap.get(span.id) ?? 0;
								const isActive = span.status === "running";
								const isSelected = selectedSpan?.id === span.id;
								const tokenInfo = getTokenInfo(span);
								const lineSegments = treeColumns.lineMap.get(span.id) ?? [];
								const isLastChild = span.parent_id
									? treeColumns.lastChildMap.get(span.parent_id) === span.id
									: true;
								const gutterWidth = 12;
								const columnCount = depth > 0 ? depth + 1 : 0;
								const paddingLeft = 10 + columnCount * gutterWidth;
								return (
									<button
										key={span.id}
										type="button"
										onClick={() => {
											setSelectedSpanId(span.id);
											setFollowLive(false);
										}}
										className={cn(
											"group relative flex w-full flex-col gap-1 rounded-lg border border-border/40 bg-card/50 px-3 py-2 text-left text-sm transition-all",
											"hover:border-primary/40 hover:bg-primary/5",
											isSelected && "border-primary/60 bg-primary/10 shadow-md",
											isActive &&
												"animate-pulse border-primary/80 shadow-[0_0_0_1px_rgba(59,130,246,0.4)]"
										)}
										style={{ paddingLeft }}
									>
										{columnCount > 0 && (
											<div className="absolute inset-y-0 left-0 flex">
												{lineSegments.map((hasLine, idx) => (
													<div
														key={`${span.id}-line-${idx}`}
														className="relative"
														style={{ width: gutterWidth }}
													>
														{hasLine && (
															<div className="absolute inset-y-0 left-1/2 w-px bg-border/60" />
														)}
													</div>
												))}
												{depth > 0 && (
													<div className="relative" style={{ width: gutterWidth }}>
														<div
															className={cn(
																"absolute left-1/2 w-px bg-border/60",
																isLastChild ? "top-0 h-1/2" : "top-0 h-full"
															)}
														/>
														<div className="absolute left-1/2 top-1/2 h-px w-full bg-border/60" />
													</div>
												)}
											</div>
										)}
										<div className="flex items-center justify-between gap-2">
											<div className="flex items-center gap-2">
												{isActive ? (
													<CircleDot className="size-4 text-primary" />
												) : span.status === "error" ? (
													<AlertCircle className="size-4 text-destructive" />
												) : (
													<CheckCircle2 className="size-4 text-emerald-500" />
												)}
												<span className="font-medium text-foreground">{span.name}</span>
											</div>
											<span className="flex items-center gap-2 text-xs text-muted-foreground">
												{tokenInfo && (
													<span className="rounded-full border border-border/60 px-2 py-0.5">
														{tokenInfo.total} tok
													</span>
												)}
												<span>{formatDuration(span.duration_ms)}</span>
											</span>
										</div>
										<div className="flex items-center gap-2 text-xs text-muted-foreground">
											{depth > 0 && <ChevronRight className="size-3 opacity-60" />}
											<span className="rounded-full border border-border/60 px-2 py-0.5">
												{span.kind}
											</span>
											{span.status === "running" && (
												<span className="rounded-full bg-primary/10 px-2 py-0.5 text-primary">
													kör
												</span>
											)}
										</div>
									</button>
								);
							})}
						</div>
					</ScrollArea>
				</div>

				<div className="flex w-1/2 min-h-0 flex-col bg-card/30 backdrop-blur-xl">
					<div className="flex items-center justify-between border-b border-border/60 px-4 py-3 text-xs uppercase tracking-wide text-muted-foreground">
						<span>Detaljer</span>
						{selectedSpan && (
							<span className="text-xs text-muted-foreground">
								{selectedSpan.status === "running" ? "Pågår" : "Avslutad"}
							</span>
						)}
					</div>
					<ScrollArea className="flex-1 min-h-0">
						<div className="space-y-4 px-4 pb-8">
							{!selectedSpan && (
								<div className="rounded-lg border border-dashed border-border/60 p-4 text-sm text-muted-foreground">
									Välj ett steg för att se detaljer.
								</div>
							)}
							{selectedSpan && (
								<>
									<div className="space-y-1">
										<div className="text-sm font-semibold text-foreground">{selectedSpan.name}</div>
										<div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
											<span className="rounded-full border border-border/60 px-2 py-0.5">
												{selectedSpan.kind}
											</span>
											<span className="rounded-full border border-border/60 px-2 py-0.5">
												{formatDuration(selectedSpan.duration_ms)}
											</span>
											{selectedTokenInfo && (
												<span className="rounded-full border border-border/60 px-2 py-0.5">
													{selectedTokenInfo.total} tok
												</span>
											)}
											{selectedSpan.status === "running" && (
												<span className="rounded-full bg-primary/10 px-2 py-0.5 text-primary">
													Live
												</span>
											)}
										</div>
									</div>
									{selectedTokenInfo && (
										<div className="rounded-lg border border-border/60 bg-card/40 px-3 py-2 text-xs text-muted-foreground">
											Tokens: input {selectedTokenInfo.input} · output {selectedTokenInfo.output}
										</div>
									)}

									{attributionEntries.length > 0 && (
										<div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs text-emerald-600 dark:text-emerald-300">
											{attributionEntries.map((entry) => (
												<div key={entry.label} className="flex flex-col gap-0.5">
													<span className="font-semibold">{entry.label}</span>
													<span className="break-all">{entry.value}</span>
												</div>
											))}
										</div>
									)}

									{selectedSpan.input !== undefined && (
										<TracePayloadSection title="Input" payload={selectedSpan.input} />
									)}
									{selectedSpan.output !== undefined && (
										<TracePayloadSection title="Output" payload={selectedSpan.output} />
									)}
									{selectedSpan.meta !== undefined && (
										<TracePayloadSection title="Metadata" payload={selectedSpan.meta} />
									)}
								</>
							)}
						</div>
					</ScrollArea>
				</div>
			</div>
		</div>
	);

	const panelBody = (
		<div className="flex h-full flex-col">
			<div className="border-b border-border/60 bg-gradient-to-r from-primary/10 via-transparent to-transparent px-4 py-4">
				{headerContent}
			</div>
			<div className="min-h-0 flex-1">{content}</div>
		</div>
	);

	if (variant === "inline") {
		if (!open) return null;
		return (
			<div
				className={cn(
					"h-full",
					dock === "left" ? "border-r border-border/60" : "border-l border-border/60"
				)}
				style={{ width: panelWidth, minWidth, maxWidth }}
			>
				{panelBody}
			</div>
		);
	}

	if (isMobile) {
		return (
			<Drawer open={open} onOpenChange={onOpenChange} shouldScaleBackground={false}>
				<DrawerContent className="h-[90vh] max-h-[90vh] z-80" overlayClassName="z-80">
					<DrawerHandle />
					<DrawerHeader className="px-4 pb-3 pt-2">
						<DrawerTitle>{headerContent}</DrawerTitle>
					</DrawerHeader>
					<div className="min-h-0 flex-1">{content}</div>
				</DrawerContent>
			</Drawer>
		);
	}

	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent
				side="right"
				className="flex h-full flex-col gap-0 overflow-hidden p-0 shadow-2xl"
				style={{ width: panelWidth, maxWidth: "100vw" }}
			>
				<SheetHeader className="border-b border-border/60 bg-gradient-to-r from-primary/10 via-transparent to-transparent px-4 py-4">
					<SheetTitle>{headerContent}</SheetTitle>
				</SheetHeader>
				<div className="min-h-0 flex-1">{content}</div>
			</SheetContent>
		</Sheet>
	);
}

function TracePayloadSection({ title, payload }: { title: string; payload: unknown }) {
	const [mode, setMode] = useState<"json" | "yaml" | "raw">("json");
	const text = useMemo(() => formatPayload(payload, mode), [payload, mode]);
	const [copied, setCopied] = useState(false);

	return (
		<div className="rounded-lg border border-border/60 bg-card/40">
			<div className="flex items-center justify-between border-b border-border/60 px-3 py-2">
				<span className="text-xs font-semibold text-muted-foreground">{title}</span>
				<div className="flex items-center gap-2">
					<Tabs value={mode} onValueChange={(value) => setMode(value as typeof mode)}>
						<TabsList className="h-7">
							<TabsTrigger value="json" className="text-[10px]">
								JSON
							</TabsTrigger>
							<TabsTrigger value="yaml" className="text-[10px]">
								YAML
							</TabsTrigger>
							<TabsTrigger value="raw" className="text-[10px]">
								Raw
							</TabsTrigger>
						</TabsList>
					</Tabs>
					<Button
						variant="ghost"
						size="icon"
						className="h-7 w-7"
						onClick={() => {
							navigator.clipboard.writeText(text);
							setCopied(true);
							setTimeout(() => setCopied(false), 1200);
						}}
					>
						{copied ? (
							<CheckCircle2 className="size-4 text-emerald-500" />
						) : (
							<Copy className="size-4" />
						)}
					</Button>
				</div>
			</div>
			<pre className="max-h-[320px] overflow-auto whitespace-pre-wrap break-words px-3 py-2 text-xs text-foreground">
				{text || "—"}
			</pre>
		</div>
	);
}
