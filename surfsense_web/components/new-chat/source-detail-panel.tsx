"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, ChevronDown, ExternalLink, FileText, Hash, Sparkles, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useTranslations } from "next-intl";
import type React from "react";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { MarkdownViewer } from "@/components/markdown-viewer";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Spinner } from "@/components/ui/spinner";
import type {
	GetDocumentByChunkResponse,
	GetSurfsenseDocsByChunkResponse,
} from "@/contracts/types/document.types";
import { documentsApiService } from "@/lib/apis/documents-api.service";
import { cacheKeys } from "@/lib/query-client/cache-keys";
import { cn } from "@/lib/utils";

type DocumentData = GetDocumentByChunkResponse | GetSurfsenseDocsByChunkResponse;

interface SourceDetailPanelProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	chunkId: number;
	sourceType: string;
	title: string;
	description?: string;
	url?: string;
	children?: ReactNode;
	isDocsChunk?: boolean;
}

const formatDocumentType = (type: string) => {
	if (!type) return "";
	return type
		.split("_")
		.map((word) => word.charAt(0) + word.slice(1).toLowerCase())
		.join(" ");
};

export function SourceDetailPanel({
	open,
	onOpenChange,
	chunkId,
	sourceType,
	title,
	description,
	url,
	children,
	isDocsChunk = false,
}: SourceDetailPanelProps) {
	const t = useTranslations("dashboard");
	const scrollAreaRef = useRef<HTMLDivElement>(null);
	const hasScrolledRef = useRef(false); // Use ref to avoid stale closures
	const [summaryOpen, setSummaryOpen] = useState(false);
	const [mounted, setMounted] = useState(false);
	const [_hasScrolledToCited, setHasScrolledToCited] = useState(false);
	const shouldReduceMotion = useReducedMotion();

	useEffect(() => {
		setMounted(true);
	}, []);

	const {
		data: documentData,
		isLoading: isDocumentByChunkFetching,
		error: documentByChunkFetchingError,
	} = useQuery<DocumentData>({
		queryKey: isDocsChunk
			? cacheKeys.documents.byChunk(`doc-${chunkId}`)
			: cacheKeys.documents.byChunk(chunkId.toString()),
		queryFn: async () => {
			if (isDocsChunk) {
				return documentsApiService.getSurfsenseDocByChunk(chunkId);
			}
			return documentsApiService.getDocumentByChunk({ chunk_id: chunkId });
		},
		enabled: !!chunkId && open,
		staleTime: 5 * 60 * 1000,
	});

	const isDirectRenderSource =
		sourceType === "TAVILY_API" ||
		sourceType === "LINKUP_API" ||
		sourceType === "SEARXNG_API" ||
		sourceType === "BAIDU_SEARCH_API";

	// Find cited chunk index
	const citedChunkIndex = documentData?.chunks?.findIndex((chunk) => chunk.id === chunkId) ?? -1;

	// Simple scroll function that scrolls to a chunk by index
	const scrollToChunkByIndex = useCallback(
		(chunkIndex: number, smooth = true) => {
			const scrollContainer = scrollAreaRef.current;
			if (!scrollContainer) return;

			const viewport = scrollContainer.querySelector(
				"[data-radix-scroll-area-viewport]"
			) as HTMLElement | null;
			if (!viewport) return;

			const chunkElement = scrollContainer.querySelector(
				`[data-chunk-index="${chunkIndex}"]`
			) as HTMLElement | null;
			if (!chunkElement) return;

			// Get positions using getBoundingClientRect for accuracy
			const viewportRect = viewport.getBoundingClientRect();
			const chunkRect = chunkElement.getBoundingClientRect();

			// Calculate where to scroll to center the chunk
			const currentScrollTop = viewport.scrollTop;
			const chunkTopRelativeToViewport = chunkRect.top - viewportRect.top + currentScrollTop;
			const scrollTarget =
				chunkTopRelativeToViewport - viewportRect.height / 2 + chunkRect.height / 2;

			viewport.scrollTo({
				top: Math.max(0, scrollTarget),
				behavior: smooth && !shouldReduceMotion ? "smooth" : "auto",
			});

		},
		[shouldReduceMotion]
	);

	// Callback ref for the cited chunk - scrolls when the element mounts
	const citedChunkRefCallback = useCallback(
		(node: HTMLDivElement | null) => {
			if (node && !hasScrolledRef.current && open) {
				hasScrolledRef.current = true; // Mark immediately to prevent duplicate scrolls

				// Store the node reference for the delayed scroll
				const scrollToCitedChunk = () => {
					const scrollContainer = scrollAreaRef.current;
					if (!scrollContainer || !node.isConnected) return false;

					const viewport = scrollContainer.querySelector(
						"[data-radix-scroll-area-viewport]"
					) as HTMLElement | null;
					if (!viewport) return false;

					// Get positions
					const viewportRect = viewport.getBoundingClientRect();
					const chunkRect = node.getBoundingClientRect();

					// Calculate scroll position to center the chunk
					const currentScrollTop = viewport.scrollTop;
					const chunkTopRelativeToViewport = chunkRect.top - viewportRect.top + currentScrollTop;
					const scrollTarget =
						chunkTopRelativeToViewport - viewportRect.height / 2 + chunkRect.height / 2;

					viewport.scrollTo({
						top: Math.max(0, scrollTarget),
						behavior: "auto", // Instant scroll for initial positioning
					});

					return true;
				};

				// Scroll multiple times with delays to handle progressive content rendering
				// Each subsequent scroll will correct for any layout shifts
				const scrollAttempts = [50, 150, 300, 600, 1000];

				scrollAttempts.forEach((delay) => {
					setTimeout(() => {
						scrollToCitedChunk();
					}, delay);
				});

				// After final attempt, mark state as scrolled
				setTimeout(
					() => {
						setHasScrolledToCited(true);
					},
					scrollAttempts[scrollAttempts.length - 1] + 50
				);
			}
		},
		[open, citedChunkIndex]
	);

	// Reset scroll state when panel closes
	useEffect(() => {
		if (!open) {
			hasScrolledRef.current = false;
			setHasScrolledToCited(false);
		}
	}, [open]);

	// Handle escape key
	useEffect(() => {
		const handleEscape = (e: KeyboardEvent) => {
			if (e.key === "Escape" && open) {
				onOpenChange(false);
			}
		};
		window.addEventListener("keydown", handleEscape);
		return () => window.removeEventListener("keydown", handleEscape);
	}, [open, onOpenChange]);

	// Prevent body scroll when open
	useEffect(() => {
		if (open) {
			document.body.style.overflow = "hidden";
		} else {
			document.body.style.overflow = "";
		}
		return () => {
			document.body.style.overflow = "";
		};
	}, [open]);

	const handleUrlClick = (e: React.MouseEvent, clickUrl: string) => {
		e.preventDefault();
		e.stopPropagation();
		window.open(clickUrl, "_blank", "noopener,noreferrer");
	};

	const scrollToChunk = useCallback(
		(index: number) => {
			scrollToChunkByIndex(index, true);
		},
		[scrollToChunkByIndex]
	);

	const panelContent = (
		<AnimatePresence mode="wait">
			{open && (
				<>
					{/* Backdrop */}
					<motion.div
						key="backdrop"
						initial={{ opacity: 0 }}
						animate={{ opacity: 1 }}
						exit={{ opacity: 0 }}
						transition={{ duration: 0.2 }}
						className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
						onClick={() => onOpenChange(false)}
					/>

					{/* Panel */}
					<motion.div
						key="panel"
						initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.95, y: 20 }}
						animate={{ opacity: 1, scale: 1, y: 0 }}
						exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.95, y: 20 }}
						transition={{
							type: "spring",
							damping: 30,
							stiffness: 300,
						}}
						className="fixed inset-3 sm:inset-6 md:inset-10 lg:inset-16 z-50 flex flex-col bg-background rounded-3xl shadow-2xl border overflow-hidden"
					>
						{/* Header */}
						<motion.div
							initial={{ opacity: 0, y: -10 }}
							animate={{ opacity: 1, y: 0 }}
							transition={{ delay: 0.1 }}
							className="flex items-center justify-between px-6 py-5 border-b bg-linear-to-r from-muted/50 to-muted/30"
						>
							<div className="min-w-0 flex-1">
								<h2 className="text-xl font-semibold truncate">
									{documentData?.title || title || "Källdokument"}
								</h2>
								<p className="text-sm text-muted-foreground mt-0.5">
									{documentData && "document_type" in documentData
										? formatDocumentType(documentData.document_type)
										: sourceType && formatDocumentType(sourceType)}
									{documentData?.chunks && (
										<span className="ml-2">
											• {documentData.chunks.length} del
											{documentData.chunks.length !== 1 ? "ar" : ""}
										</span>
									)}
								</p>
							</div>
							<div className="flex items-center gap-3 shrink-0">
								{url && (
									<Button
										size="sm"
										variant="outline"
										onClick={(e) => handleUrlClick(e, url)}
										className="hidden sm:flex gap-2 rounded-xl"
									>
										<ExternalLink className="h-4 w-4" />
										Öppna källa
									</Button>
								)}
								<Button
									size="icon"
									variant="ghost"
									onClick={() => onOpenChange(false)}
									className="h-8 w-8 rounded-full"
								>
									<X className="h-4 w-4" />
									<span className="sr-only">Stäng</span>
								</Button>
							</div>
						</motion.div>

						{/* Loading State */}
						{!isDirectRenderSource && isDocumentByChunkFetching && (
							<div className="flex-1 flex items-center justify-center">
								<motion.div
									initial={{ opacity: 0, scale: 0.9 }}
									animate={{ opacity: 1, scale: 1 }}
									className="flex flex-col items-center gap-4"
								>
									<Spinner size="lg" />
									<p className="text-sm text-muted-foreground font-medium">
										{t("loading_document")}
									</p>
								</motion.div>
							</div>
						)}

						{/* Error State */}
						{!isDirectRenderSource && documentByChunkFetchingError && (
							<div className="flex-1 flex items-center justify-center">
								<motion.div
									initial={{ opacity: 0, scale: 0.9 }}
									animate={{ opacity: 1, scale: 1 }}
									className="flex flex-col items-center gap-4 text-center px-6"
								>
									<div className="w-20 h-20 rounded-full bg-destructive/10 flex items-center justify-center">
										<X className="h-10 w-10 text-destructive" />
									</div>
									<div>
										<p className="font-semibold text-destructive text-lg">
											Det gick inte att läsa in dokumentet
										</p>
										<p className="text-sm text-muted-foreground mt-2 max-w-md">
											{documentByChunkFetchingError.message ||
												"Ett oväntat fel uppstod. Försök igen."}
										</p>
									</div>
									<Button variant="outline" onClick={() => onOpenChange(false)} className="mt-2">
										Stäng panel
									</Button>
								</motion.div>
							</div>
						)}

						{/* Direct render for web search providers */}
						{isDirectRenderSource && (
							<ScrollArea className="flex-1">
								<div className="p-6 max-w-3xl mx-auto">
									{url && (
										<Button
											size="default"
											variant="outline"
											onClick={(e) => handleUrlClick(e, url)}
											className="w-full mb-6 sm:hidden rounded-xl"
										>
											<ExternalLink className="mr-2 h-4 w-4" />
											Öppna i webbläsaren
										</Button>
									)}
									<motion.div
										initial={{ opacity: 0, y: 10 }}
										animate={{ opacity: 1, y: 0 }}
										className="p-6 bg-muted/50 rounded-2xl border"
									>
										<h3 className="text-base font-semibold mb-4 flex items-center gap-2">
											<BookOpen className="h-4 w-4" />
											Källinformation
										</h3>
										<div className="text-sm text-muted-foreground mb-3 font-medium">
											{title || "Utan titel"}
										</div>
										<div className="text-sm text-foreground leading-relaxed">
											{description || "Inget innehåll tillgängligt"}
										</div>
									</motion.div>
								</div>
							</ScrollArea>
						)}

						{/* API-fetched document content */}
						{!isDirectRenderSource && documentData && (
							<div className="flex-1 flex overflow-hidden">
								{/* Main Content */}
								<ScrollArea className="flex-1" ref={scrollAreaRef}>
									<div className="p-6 lg:p-8 max-w-4xl mx-auto space-y-6">
										{/* Document Metadata */}
										{"document_metadata" in documentData &&
											documentData.document_metadata &&
											Object.keys(documentData.document_metadata).length > 0 && (
												<motion.div
													initial={{ opacity: 0, y: 10 }}
													animate={{ opacity: 1, y: 0 }}
													transition={{ delay: 0.1 }}
													className="p-5 bg-muted/30 rounded-2xl border"
												>
													<h3 className="text-sm font-semibold mb-4 text-muted-foreground uppercase tracking-wider flex items-center gap-2">
														<FileText className="h-4 w-4" />
														Dokumentinformation
													</h3>
													<dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
														{Object.entries(documentData.document_metadata).map(([key, value]) => (
															<div key={key} className="space-y-1">
																<dt className="font-medium text-muted-foreground capitalize text-xs">
																	{key.replace(/_/g, " ")}
																</dt>
																<dd className="text-foreground wrap-break-word">{String(value)}</dd>
															</div>
														))}
													</dl>
												</motion.div>
											)}

										{/* Summary Collapsible */}
										{documentData.content && (
											<motion.div
												initial={{ opacity: 0, y: 10 }}
												animate={{ opacity: 1, y: 0 }}
												transition={{ delay: 0.15 }}
											>
												<Collapsible open={summaryOpen} onOpenChange={setSummaryOpen}>
													<CollapsibleTrigger className="w-full flex items-center justify-between p-5 rounded-2xl bg-linear-to-r from-muted/50 to-muted/30 border hover:from-muted/70 hover:to-muted/50 transition-all duration-200">
														<span className="font-semibold flex items-center gap-2">
															<BookOpen className="h-4 w-4" />
															Dokumentsammanfattning
														</span>
														<motion.div
															animate={{ rotate: summaryOpen ? 180 : 0 }}
															transition={{ duration: 0.2 }}
														>
															<ChevronDown className="h-5 w-5 text-muted-foreground" />
														</motion.div>
													</CollapsibleTrigger>
													<CollapsibleContent>
														<motion.div
															initial={{ opacity: 0 }}
															animate={{ opacity: 1 }}
															className="mt-3 p-5 bg-muted/20 rounded-2xl border"
														>
															<MarkdownViewer content={documentData.content} />
														</motion.div>
													</CollapsibleContent>
												</Collapsible>
											</motion.div>
										)}

										<div className="rounded-2xl border bg-muted/10">
											<div className="flex items-center justify-between px-5 py-4 border-b border-border/50">
												<h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
													<Hash className="h-4 w-4" />
													Fulltext
												</h3>
												{citedChunkIndex !== -1 && (
													<Button
														variant="ghost"
														size="sm"
														onClick={() => scrollToChunk(citedChunkIndex)}
														className="gap-2 text-primary hover:text-primary"
													>
														<Sparkles className="h-3.5 w-3.5" />
														Hoppa till citerad del
													</Button>
												)}
											</div>
											<div className="p-5 space-y-4">
												{documentData.chunks.map((chunk, idx) => {
													const isCited = chunk.id === chunkId;
													return (
														<div
															key={chunk.id}
															ref={isCited ? citedChunkRefCallback : undefined}
															data-chunk-index={idx}
															className={cn(
																"rounded-xl border transition-colors",
																isCited
																	? "border-yellow-300/60 bg-yellow-100/70 shadow-md shadow-yellow-200/30 dark:bg-yellow-900/20 dark:border-yellow-700/40"
																	: "border-transparent"
															)}
														>
															{isCited && (
																<div className="flex items-center gap-2 px-4 pt-4 text-xs font-semibold text-yellow-900 dark:text-yellow-100">
																	<Sparkles className="h-3.5 w-3.5" />
																	Citerad del
																</div>
															)}
															<div className="px-4 pb-4 pt-3">
																<MarkdownViewer content={chunk.content} />
															</div>
														</div>
													);
												})}
											</div>
										</div>
									</div>
								</ScrollArea>
							</div>
						)}
					</motion.div>
				</>
			)}
		</AnimatePresence>
	);

	if (!mounted) return <>{children}</>;

	return (
		<>
			{children}
			{createPortal(panelContent, globalThis.document.body)}
		</>
	);
}
