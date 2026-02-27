/**
 * StructuredStreamViewer — progressive JSON rendering for pipeline node output.
 *
 * Uses `partial-json` to parse incomplete JSON tokens as they arrive during
 * LLM streaming, showing structured field values (thinking, route, confidence,
 * etc.) in a compact, readable format within the FadeLayer.
 *
 * P1-Extra.5: Created per the development plan to provide real-time visibility
 * into structured output schemas during agent pipeline execution.
 */

import { parse as partialParse } from "partial-json";
import type { FC } from "react";
import { useMemo } from "react";

/** Props for the viewer: raw JSON buffer (possibly incomplete) and node label. */
interface StructuredStreamViewerProps {
	/** The raw JSON buffer accumulated so far (may be incomplete). */
	buffer: string;
	/** The pipeline node name (e.g. "intent_router", "critic"). */
	node: string;
	/** Whether the stream is still active. */
	isStreaming?: boolean;
}

/** Fields to surface as key-value badges (order matters for display). */
const DISPLAY_FIELDS = [
	"route",
	"intent_id",
	"confidence",
	"decision",
	"reason",
	"chosen_layer",
	"selected_agents",
] as const;

/**
 * Renders a compact view of a partially-parsed structured JSON output
 * from a pipeline node. Fields appear as they are parsed, giving the
 * user real-time visibility into the agent's decision process.
 */
export const StructuredStreamViewer: FC<StructuredStreamViewerProps> = ({
	buffer,
	node,
	isStreaming = false,
}) => {
	const parsed = useMemo(() => {
		if (!buffer.trim()) return null;
		try {
			const obj = partialParse(buffer);
			if (typeof obj === "object" && obj !== null && !Array.isArray(obj)) {
				return obj as Record<string, unknown>;
			}
		} catch {
			// Incomplete JSON — return null until parseable
		}
		return null;
	}, [buffer]);

	if (!parsed) return null;

	// Collect fields that have values
	const entries: { field: string; value: string }[] = [];
	for (const field of DISPLAY_FIELDS) {
		const val = parsed[field];
		if (val !== undefined && val !== null && val !== "") {
			entries.push({
				field,
				value: typeof val === "string" ? val : JSON.stringify(val),
			});
		}
	}

	if (entries.length === 0) return null;

	return (
		<div className="my-0.5 rounded border border-border/40 bg-muted/30 px-2 py-1">
			<div className="mb-0.5 text-[0.6rem] font-medium text-muted-foreground/50">
				{node}
				{isStreaming && <span className="ml-1 inline-block animate-pulse text-primary/40">●</span>}
			</div>
			<div className="flex flex-wrap gap-x-2 gap-y-0.5">
				{entries.map(({ field, value }) => (
					<span key={`${node}-${field}`} className="text-[0.65rem] text-muted-foreground">
						<span className="opacity-50">{field}</span>
						<span className="mx-0.5 opacity-30">→</span>
						<span className="font-medium text-primary/70">{value}</span>
					</span>
				))}
			</div>
		</div>
	);
};
