import { useAssistantState, useThreadViewport } from "@assistant-ui/react";
import { ChevronDownIcon } from "lucide-react";
import type { FC } from "react";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { TextShimmerLoader } from "@/components/prompt-kit/loader";
import type { ThinkingStep } from "@/components/tool-ui/deepagent-thinking";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Timeline — ordered list of reasoning chunks interleaved with tool steps
// ---------------------------------------------------------------------------

/** A single entry in the chronological fade-layer timeline. */
export type TimelineEntry =
	| { kind: "reasoning"; text: string }
	| { kind: "step"; stepId: string };

// Context to pass thinking steps to AssistantMessage
export const ThinkingStepsContext = createContext<Map<string, ThinkingStep[]>>(new Map());

// Context to pass live reasoning text (from <think> tags / reasoning-delta events) to AssistantMessage
export const ReasoningContext = createContext<Map<string, string>>(new Map());

// Context for the interleaved timeline (reasoning chunks + step markers, in arrival order)
export const TimelineContext = createContext<Map<string, TimelineEntry[]>>(new Map());

// ---------------------------------------------------------------------------
// CSS for hiding the scrollbar (WebKit + Firefox + IE)
// ---------------------------------------------------------------------------
const HIDE_SCROLLBAR_CLASS = "fade-layer-scroll";
const hideScrollbarStyle = `
.${HIDE_SCROLLBAR_CLASS}::-webkit-scrollbar { display: none; }
.${HIDE_SCROLLBAR_CLASS} { scrollbar-width: none; -ms-overflow-style: none; }
`;

// ---------------------------------------------------------------------------
// FadeLayer — unified rolling reasoning + thinking-steps component
// ---------------------------------------------------------------------------

/**
 * Renders tool-call steps as compact inline badges within the fade layer.
 */
const InlineToolStep: FC<{ step: ThinkingStep }> = ({ step }) => (
	<div className="my-0.5 inline-flex items-center gap-1.5 rounded border border-border/60 bg-muted/60 px-2 py-0.5 text-[0.7rem] text-muted-foreground">
		<span className="opacity-70">&#9728;</span>
		<span>{step.title}</span>
		{step.items?.[0] && (
			<span className="ml-1 text-[0.6rem] opacity-50">{step.items[0]}</span>
		)}
	</div>
);

/**
 * Renders a reasoning text chunk, splitting by --- Title --- headers.
 */
const ReasoningChunk: FC<{ text: string; keyPrefix: string }> = ({ text, keyPrefix }) => {
	const segments = text.split(/^(---\s+.+?\s+---)\s*$/m).filter(Boolean);
	return (
		<>
			{segments.map((segment, i) => {
				const isHeader = /^---\s+.+?\s+---$/.test(segment);
				if (isHeader) {
					const title = segment.replace(/^---\s+/, "").replace(/\s+---$/, "");
					return (
						<div key={`${keyPrefix}-${i}`} className="flex items-center gap-2 pt-1.5 pb-0.5">
							<span className="text-[0.68rem] font-semibold text-primary/80">
								{title}
							</span>
							<span className="h-px flex-1 bg-primary/10" />
						</div>
					);
				}
				const trimmed = segment.trim();
				if (!trimmed) return null;
				return (
					<div
						key={`${keyPrefix}-${i}`}
						className="text-[0.76rem] leading-relaxed text-muted-foreground whitespace-pre-wrap"
					>
						{trimmed}
					</div>
				);
			})}
		</>
	);
};

/** Max collapsed height in px (≈ 11rem) */
const MAX_COLLAPSED_HEIGHT = 176;

/**
 * FadeLayer – unified component that merges the reasoning stream
 * (from <think> / reasoning-delta events) with structured thinking
 * steps (tool calls etc.) into a single rolling container.
 *
 * Uses the timeline (ordered list of reasoning chunks + step markers)
 * to render entries in the correct chronological order.
 *
 * Design:
 * - Max-height with top gradient fade-out (content dissolves upward)
 * - No visible scrollbar; auto-scrolls to bottom during streaming
 * - Dims to low opacity when streaming finishes; hover reveals
 * - Clean expand toggle ("▾ N steg · Xs")
 */
export const FadeLayer: FC<{
	timeline: TimelineEntry[];
	stepsById: Map<string, ThinkingStep>;
	isStreaming: boolean;
}> = ({ timeline, stepsById, isStreaming }) => {
	const scrollRef = useRef<HTMLDivElement>(null);
	const [isExpanded, setIsExpanded] = useState(false);
	const [streamStartTime] = useState(() => Date.now());
	const [elapsedSeconds, setElapsedSeconds] = useState(0);

	// Track elapsed time during streaming
	useEffect(() => {
		if (!isStreaming) {
			setElapsedSeconds(Math.round((Date.now() - streamStartTime) / 1000));
			return;
		}
		const interval = setInterval(() => {
			setElapsedSeconds(Math.round((Date.now() - streamStartTime) / 1000));
		}, 1000);
		return () => clearInterval(interval);
	}, [isStreaming, streamStartTime]);

	// Auto-scroll to bottom during streaming
	useEffect(() => {
		if (isStreaming && scrollRef.current) {
			requestAnimationFrame(() => {
				scrollRef.current?.scrollTo({
					top: scrollRef.current.scrollHeight,
					behavior: "smooth",
				});
			});
		}
	}, [timeline, isStreaming]);

	if (timeline.length === 0) return null;

	const isDone = !isStreaming;
	const stepCount = timeline.filter((e) => e.kind === "step").length;

	return (
		<div className="mx-auto w-full max-w-(--thread-max-width) px-2 pb-1">
			{/* Inject scrollbar-hiding CSS once */}
			<style dangerouslySetInnerHTML={{ __html: hideScrollbarStyle }} />

			{/* Rolling container — inline maxHeight for guaranteed constraint */}
			<div
				ref={scrollRef}
				className={cn("fade-layer-scroll relative overflow-y-auto overscroll-contain")}
				style={{
					maxHeight: isExpanded ? "none" : `${MAX_COLLAPSED_HEIGHT}px`,
				}}
			>
				{/* Top gradient fade-out mask */}
				{!isExpanded && (
					<div
						className="pointer-events-none sticky top-0 left-0 right-0 z-10"
						style={{
							height: "2.5rem",
							background: "linear-gradient(to bottom, var(--background) 0%, transparent 100%)",
						}}
					/>
				)}

				{/* Content — interleaved reasoning + steps */}
				<div
					className="space-y-0.5 px-1 pb-1"
					style={{
						opacity: isDone && !isExpanded ? 0.35 : undefined,
						transition: "opacity 400ms",
					}}
					onMouseEnter={(e) => {
						if (isDone && !isExpanded) {
							e.currentTarget.style.opacity = "0.75";
						}
					}}
					onMouseLeave={(e) => {
						if (isDone && !isExpanded) {
							e.currentTarget.style.opacity = "0.35";
						}
					}}
				>
					{timeline.map((entry, i) => {
						if (entry.kind === "reasoning") {
							return (
								<ReasoningChunk
									key={`tl-${i}`}
									text={entry.text}
									keyPrefix={`tl-${i}`}
								/>
							);
						}
						// entry.kind === "step"
						const step = stepsById.get(entry.stepId);
						if (!step) return null;
						return <InlineToolStep key={`tl-s-${entry.stepId}`} step={step} />;
					})}

					{/* Streaming cursor */}
					{isStreaming && (
						<span className="inline-block h-3.5 w-0.5 animate-pulse bg-primary/70 align-text-bottom ml-0.5" />
					)}
				</div>
			</div>

			{/* Toggle button */}
			<button
				type="button"
				onClick={() => setIsExpanded(!isExpanded)}
				className="mt-0.5 flex items-center gap-1.5 text-[0.65rem] text-muted-foreground/60 transition-colors hover:text-muted-foreground"
			>
				<ChevronDownIcon
					className={cn(
						"size-3 transition-transform duration-200",
						isExpanded && "rotate-180",
					)}
				/>
				{isStreaming ? (
					<TextShimmerLoader text="Tänker..." size="sm" />
				) : (
					<span>
						{stepCount > 0 ? `${stepCount} steg` : "Tankar"}
						{elapsedSeconds > 0 ? ` \u00B7 ${elapsedSeconds}s` : ""}
					</span>
				)}
			</button>
		</div>
	);
};

/**
 * Component that handles auto-scroll when thinking steps update.
 * Uses useThreadViewport to scroll to bottom when thinking steps change,
 * ensuring the user always sees the latest content during streaming.
 */
export const ThinkingStepsScrollHandler: FC = () => {
	const thinkingStepsMap = useContext(ThinkingStepsContext);
	const viewport = useThreadViewport();
	const isRunning = useAssistantState(({ thread }) => thread.isRunning);
	// Track the serialized state to detect any changes
	const prevStateRef = useRef<string>("");

	useEffect(() => {
		// Only act during streaming
		if (!isRunning) {
			prevStateRef.current = "";
			return;
		}

		// Serialize the thinking steps state to detect any changes
		// This catches new steps, status changes, and item additions
		let stateString = "";
		thinkingStepsMap.forEach((steps, msgId) => {
			steps.forEach((step) => {
				stateString += `${msgId}:${step.id}:${step.status}:${step.items?.length || 0};`;
			});
		});

		// If state changed at all during streaming, scroll
		if (stateString !== prevStateRef.current && stateString !== "") {
			prevStateRef.current = stateString;

			// Multiple attempts to ensure scroll happens after DOM updates
			const scrollAttempt = () => {
				try {
					viewport.scrollToBottom();
				} catch {
					// Ignore errors - viewport might not be ready
				}
			};

			// Delayed attempts to handle async DOM updates
			requestAnimationFrame(scrollAttempt);
			setTimeout(scrollAttempt, 100);
		}
	}, [thinkingStepsMap, viewport, isRunning]);

	return null; // This component doesn't render anything
};
