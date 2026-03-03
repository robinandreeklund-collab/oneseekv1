"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface IntentSuggestion {
	intent_id: string;
	rationale: string;
	current_definition: Record<string, unknown>;
	proposed_definition: Record<string, unknown>;
	failed_test_ids: string[];
}

interface IntentSuggestionsCardProps {
	title: string;
	suggestions: IntentSuggestion[];
}

export function IntentSuggestionsCard({ title, suggestions }: IntentSuggestionsCardProps) {
	return (
		<Card>
			<CardHeader>
				<CardTitle>{title}</CardTitle>
			</CardHeader>
			<CardContent className="space-y-3">
				{suggestions.length === 0 ? (
					<p className="text-sm text-muted-foreground">Inga intent-förslag för denna run.</p>
				) : (
					suggestions.map((suggestion) => (
						<div key={`intent-${suggestion.intent_id}`} className="rounded border p-3 space-y-2">
							<div className="flex items-center gap-2">
								<Badge variant="secondary">{suggestion.intent_id}</Badge>
								<Badge variant="outline">{suggestion.failed_test_ids.length} fail-case(s)</Badge>
							</div>
							<p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
							<div className="grid gap-3 md:grid-cols-2">
								<div className="rounded bg-muted/50 p-2">
									<p className="text-xs font-medium mb-1">Nuvarande</p>
									<pre className="text-[11px] whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
										{JSON.stringify(suggestion.current_definition, null, 2)}
									</pre>
								</div>
								<div className="rounded bg-muted/50 p-2">
									<p className="text-xs font-medium mb-1">Föreslagen</p>
									<pre className="text-[11px] whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
										{JSON.stringify(suggestion.proposed_definition, null, 2)}
									</pre>
								</div>
							</div>
						</div>
					))
				)}
			</CardContent>
		</Card>
	);
}
