"use client";

/**
 * v2 Suggestion diff view — shows metadata changes as +/- diff.
 * Used in Kalibrering tab to review LLM suggestions before applying.
 */

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

interface SuggestionField {
	field: string;
	added?: string[];
	removed?: string[];
	oldValue?: string;
	newValue?: string;
}

export interface SuggestionDiffItem {
	toolId: string;
	toolName?: string;
	fields: SuggestionField[];
	warnings?: string[];
	validationStatus: "ok" | "warning" | "error";
}

interface SuggestionDiffViewProps {
	suggestions: SuggestionDiffItem[];
	selectedIds: Set<string>;
	onToggle: (toolId: string) => void;
	onToggleAll: (selected: boolean) => void;
}

function DiffField({ field }: { field: SuggestionField }) {
	if (field.added?.length || field.removed?.length) {
		return (
			<div className="ml-4 text-sm font-mono">
				<span className="text-muted-foreground">{field.field}:</span>
				{field.removed?.map((item) => (
					<div key={`rm-${item}`} className="text-red-500 pl-2">
						- &quot;{item}&quot;
					</div>
				))}
				{field.added?.map((item) => (
					<div key={`add-${item}`} className="text-green-500 pl-2">
						+ &quot;{item}&quot;
					</div>
				))}
			</div>
		);
	}

	if (field.oldValue !== field.newValue) {
		return (
			<div className="ml-4 text-sm font-mono">
				<span className="text-muted-foreground">{field.field}:</span>
				{field.oldValue && (
					<div className="text-red-500 pl-2">
						- &quot;{field.oldValue}&quot;
					</div>
				)}
				{field.newValue && (
					<div className="text-green-500 pl-2">
						+ &quot;{field.newValue}&quot;
					</div>
				)}
			</div>
		);
	}

	return null;
}

export function SuggestionDiffView({
	suggestions,
	selectedIds,
	onToggle,
	onToggleAll,
}: SuggestionDiffViewProps) {
	const allSelected =
		suggestions.length > 0 && suggestions.every((s) => selectedIds.has(s.toolId));

	return (
		<div className="space-y-3">
			<div className="flex items-center gap-2 pb-2 border-b">
				<Checkbox
					checked={allSelected}
					onCheckedChange={(checked) => onToggleAll(!!checked)}
				/>
				<span className="text-sm font-medium">
					{suggestions.length} förslag ({selectedIds.size} valda)
				</span>
			</div>

			{suggestions.map((suggestion) => (
				<div
					key={suggestion.toolId}
					className={cn(
						"border rounded-lg p-3 space-y-2",
						suggestion.validationStatus === "error" && "border-red-300 bg-red-50/50",
						suggestion.validationStatus === "warning" &&
							"border-amber-300 bg-amber-50/50",
					)}
				>
					<div className="flex items-center gap-2">
						<Checkbox
							checked={selectedIds.has(suggestion.toolId)}
							onCheckedChange={() => onToggle(suggestion.toolId)}
						/>
						<span className="font-medium text-sm">
							{suggestion.toolName || suggestion.toolId}
						</span>
						{suggestion.validationStatus === "ok" && (
							<Badge variant="outline" className="text-xs text-green-600">
								OK
							</Badge>
						)}
						{suggestion.validationStatus === "warning" && (
							<Badge variant="outline" className="text-xs text-amber-600">
								Varning
							</Badge>
						)}
					</div>

					{suggestion.fields.map((field) => (
						<DiffField key={field.field} field={field} />
					))}

					{suggestion.warnings?.map((warning) => (
						<div
							key={warning}
							className="ml-4 text-xs text-amber-600 flex items-center gap-1"
						>
							<span>&#9888;</span> {warning}
						</div>
					))}
				</div>
			))}
		</div>
	);
}
