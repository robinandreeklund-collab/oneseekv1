"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface PromptSuggestion {
	prompt_key: string;
	rationale: string;
	current_prompt: string;
	proposed_prompt: string;
	failed_test_ids: string[];
}

interface PromptSuggestionsCardProps {
	title: string;
	suggestions: PromptSuggestion[];
	selectedKeys: Set<string>;
	onToggle: (promptKey: string) => void;
	onSave: () => void;
	isSaving: boolean;
	extraActions?: React.ReactNode;
}

export function PromptSuggestionsCard({
	title,
	suggestions,
	selectedKeys,
	onToggle,
	onSave,
	isSaving,
	extraActions,
}: PromptSuggestionsCardProps) {
	const selectedCount = Array.from(selectedKeys).filter((key) =>
		suggestions.some((s) => s.prompt_key === key)
	).length;

	return (
		<Card>
			<CardHeader>
				<CardTitle>{title}</CardTitle>
			</CardHeader>
			<CardContent className="space-y-4">
				<div className="flex flex-wrap items-center gap-2">
					<Button onClick={onSave} disabled={!selectedCount || isSaving}>
						Spara valda promptförslag
					</Button>
					{extraActions}
					<Badge variant="outline">{selectedCount} valda</Badge>
				</div>
				{suggestions.length === 0 ? (
					<p className="text-sm text-muted-foreground">Inga promptförslag för denna run.</p>
				) : (
					<div className="space-y-3">
						{suggestions.map((suggestion) => (
							<div key={`prompt-${suggestion.prompt_key}`} className="rounded border p-3 space-y-2">
								<div className="flex items-center gap-2">
									<input
										type="checkbox"
										checked={selectedKeys.has(suggestion.prompt_key)}
										onChange={() => onToggle(suggestion.prompt_key)}
									/>
									<Badge variant="secondary">{suggestion.prompt_key}</Badge>
									<Badge variant="outline">{suggestion.failed_test_ids.length} fail-case(s)</Badge>
								</div>
								<p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
								<div className="grid gap-3 md:grid-cols-2">
									<div className="rounded bg-muted/50 p-2">
										<p className="text-xs font-medium mb-1">Nuvarande</p>
										<pre className="text-[11px] whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
											{suggestion.current_prompt}
										</pre>
									</div>
									<div className="rounded bg-muted/50 p-2">
										<p className="text-xs font-medium mb-1">Föreslagen</p>
										<pre className="text-[11px] whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
											{suggestion.proposed_prompt}
										</pre>
									</div>
								</div>
							</div>
						))}
					</div>
				)}
			</CardContent>
		</Card>
	);
}
