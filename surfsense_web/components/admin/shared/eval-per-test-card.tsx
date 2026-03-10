"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatDifficultyLabel(value: string | null | undefined) {
	const normalized = String(value ?? "")
		.trim()
		.toLowerCase();
	if (!normalized) return "Okänd";
	if (normalized === "lätt" || normalized === "latt" || normalized === "easy") return "Lätt";
	if (normalized === "medel" || normalized === "medium") return "Medel";
	if (normalized === "svår" || normalized === "svar" || normalized === "hard") return "Svår";
	return value ?? "Okänd";
}

function buildFailureReasons(result: Record<string, unknown>): string[] {
	const reasons: string[] = [];
	if (result.passed_intent === false) reasons.push("Intent mismatch");
	if (result.passed_route === false) reasons.push("Route mismatch");
	if (result.passed_sub_route === false) reasons.push("Sub-route mismatch");
	if (result.passed_agent === false) reasons.push("Agent mismatch");
	if (result.passed_plan === false) reasons.push("Plankrav ej uppfyllda");
	if (result.passed_tool === false) reasons.push("Tool mismatch");
	if (result.passed_api_input === false) reasons.push("API-input mismatch");
	if (result.supervisor_review_passed === false) reasons.push("Supervisor-spår behöver förbättras");
	return reasons;
}

interface EvalCaseResult {
	test_id: string;
	question: string;
	difficulty?: string;
	passed: boolean;
	expected_tool?: string;
	selected_tool?: string;
	passed_intent?: boolean;
	passed_route?: boolean;
	passed_agent?: boolean;
	passed_tool?: boolean;
	passed_api_input?: boolean;
	supervisor_review_rationale?: string;
	retrieval_top_tools?: string[];
	proposed_arguments?: Record<string, unknown>;
	schema_valid?: boolean;
	missing_required_fields?: string[];
	unexpected_fields?: string[];
}

interface EvalPerTestCardProps {
	title: string;
	results: EvalCaseResult[];
	showApiInputFields?: boolean;
}

export function EvalPerTestCard({ title, results, showApiInputFields }: EvalPerTestCardProps) {
	return (
		<Card>
			<CardHeader>
				<CardTitle>{title}</CardTitle>
			</CardHeader>
			<CardContent className="space-y-3 max-h-[600px] overflow-auto">
				{results.map((result) => {
					const failureReasons = buildFailureReasons(result as unknown as Record<string, unknown>);
					return (
						<div key={result.test_id} className="rounded border p-3 space-y-2">
							<div className="flex items-center justify-between gap-2">
								<div className="flex items-center gap-2">
									<Badge variant="outline">{result.test_id}</Badge>
									{result.difficulty && (
										<Badge variant="secondary">{formatDifficultyLabel(result.difficulty)}</Badge>
									)}
									<Badge variant={result.passed ? "default" : "destructive"}>
										{result.passed ? "PASS" : "FAIL"}
									</Badge>
								</div>
								<div className="text-xs text-muted-foreground">
									{result.expected_tool || "-"} → {result.selected_tool || "-"}
								</div>
							</div>
							<p className="text-sm">{result.question}</p>
							<div className="flex flex-wrap gap-2">
								{result.passed_intent != null && (
									<Badge variant={result.passed_intent ? "outline" : "destructive"}>
										intent {result.passed_intent ? "OK" : "MISS"}
									</Badge>
								)}
								{result.passed_route != null && (
									<Badge variant={result.passed_route ? "outline" : "destructive"}>
										route {result.passed_route ? "OK" : "MISS"}
									</Badge>
								)}
								{result.passed_agent != null && (
									<Badge variant={result.passed_agent ? "outline" : "destructive"}>
										agent {result.passed_agent ? "OK" : "MISS"}
									</Badge>
								)}
								{result.passed_tool != null && (
									<Badge variant={result.passed_tool ? "outline" : "destructive"}>
										tool {result.passed_tool ? "OK" : "MISS"}
									</Badge>
								)}
								{result.passed_api_input != null && (
									<Badge variant={result.passed_api_input ? "outline" : "destructive"}>
										api-input {result.passed_api_input ? "OK" : "MISS"}
									</Badge>
								)}
							</div>
							{!result.passed && failureReasons.length > 0 && (
								<p className="text-xs text-red-400">Fail-orsak: {failureReasons.join(" · ")}</p>
							)}
							{result.supervisor_review_rationale && (
								<p className="text-xs text-muted-foreground">
									Supervisor: {result.supervisor_review_rationale}
								</p>
							)}
							{result.retrieval_top_tools && (
								<p className="text-xs text-muted-foreground">
									Retrieval: {result.retrieval_top_tools.join(", ") || "-"}
								</p>
							)}
							{showApiInputFields && (
								<div className="grid gap-3 md:grid-cols-2">
									<div className="rounded bg-muted/40 p-2 space-y-1">
										<p className="text-xs font-medium">Proposed arguments</p>
										<pre className="text-[11px] whitespace-pre-wrap break-all text-muted-foreground">
											{JSON.stringify(result.proposed_arguments ?? {}, null, 2)}
										</pre>
									</div>
									<div className="rounded bg-muted/40 p-2 space-y-1">
										<p className="text-xs font-medium">Validering</p>
										<p className="text-[11px] text-muted-foreground">
											Schema-valid:{" "}
											{result.schema_valid == null ? "-" : result.schema_valid ? "Ja" : "Nej"}
										</p>
										<p className="text-[11px] text-muted-foreground">
											Missing required: {(result.missing_required_fields ?? []).join(", ") || "-"}
										</p>
										<p className="text-[11px] text-muted-foreground">
											Unexpected: {(result.unexpected_fields ?? []).join(", ") || "-"}
										</p>
									</div>
								</div>
							)}
						</div>
					);
				})}
			</CardContent>
		</Card>
	);
}
