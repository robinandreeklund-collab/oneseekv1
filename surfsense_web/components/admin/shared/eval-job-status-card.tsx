"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, Download } from "lucide-react";

interface CaseStatus {
	test_id: string;
	status: string;
	question: string;
	passed?: boolean;
	error?: string;
	selected_route?: string;
	selected_sub_route?: string;
	selected_agent?: string;
	selected_tool?: string;
	expected_normalized?: boolean;
	consistency_warnings?: string[];
}

interface EvalJobStatusCardProps {
	title: string;
	jobId: string;
	status?: string;
	completedTests?: number;
	totalTests?: number;
	error?: string;
	caseStatuses?: CaseStatus[];
	onExportJson: () => void;
	onExportYaml: () => void;
	exportDisabled?: boolean;
}

function statusVariant(status: string | undefined) {
	if (status === "failed") return "destructive" as const;
	if (status === "completed") return "default" as const;
	return "secondary" as const;
}

function caseVariant(status: string) {
	if (status === "failed") return "destructive" as const;
	if (status === "completed") return "default" as const;
	if (status === "running") return "secondary" as const;
	return "outline" as const;
}

export function EvalJobStatusCard({
	title,
	jobId,
	status,
	completedTests = 0,
	totalTests = 0,
	error,
	caseStatuses = [],
	onExportJson,
	onExportYaml,
	exportDisabled,
}: EvalJobStatusCardProps) {
	return (
		<Card>
			<CardHeader>
				<CardTitle>{title}</CardTitle>
				<CardDescription>
					Jobb {jobId} · status {status ?? "pending"}
				</CardDescription>
			</CardHeader>
			<CardContent className="space-y-3">
				<div className="flex flex-wrap items-center justify-between gap-2 text-sm">
					<div className="flex flex-wrap items-center gap-2">
						<Badge variant={statusVariant(status)}>{status ?? "pending"}</Badge>
						<span>{completedTests}/{totalTests} frågor</span>
					</div>
					<div className="flex items-center gap-2">
						<Button variant="outline" size="sm" onClick={onExportJson} disabled={exportDisabled}>
							<Download className="h-4 w-4 mr-1" />JSON
						</Button>
						<Button variant="outline" size="sm" onClick={onExportYaml} disabled={exportDisabled}>
							<Download className="h-4 w-4 mr-1" />YAML
						</Button>
					</div>
				</div>
				{error && (
					<Alert variant="destructive">
						<AlertCircle className="h-4 w-4" />
						<AlertDescription>{error}</AlertDescription>
					</Alert>
				)}
				<div className="space-y-2 max-h-96 overflow-auto">
					{caseStatuses.map((cs) => (
						<div key={cs.test_id} className="rounded border p-2 text-xs space-y-1">
							<div className="flex items-center justify-between gap-2">
								<p className="font-medium">{cs.test_id}</p>
								<Badge variant={caseVariant(cs.status)}>{cs.status}</Badge>
							</div>
							<p className="text-muted-foreground">{cs.question}</p>
							{cs.selected_route && (
								<p className="text-muted-foreground">
									Route: {cs.selected_route}
									{cs.selected_sub_route ? ` / ${cs.selected_sub_route}` : ""}
								</p>
							)}
							{cs.selected_agent && (
								<p className="text-muted-foreground">Agent: {cs.selected_agent}</p>
							)}
							{cs.selected_tool && (
								<p className="text-muted-foreground">Verktyg: {cs.selected_tool}</p>
							)}
							{cs.expected_normalized && <Badge variant="secondary">Expected normaliserad</Badge>}
							{cs.consistency_warnings && cs.consistency_warnings.length > 0 && (
								<p className="text-amber-400">Varning: {cs.consistency_warnings.join(" · ")}</p>
							)}
							{typeof cs.passed === "boolean" && (
								<p className="text-muted-foreground">Resultat: {cs.passed ? "Rätt" : "Fel"}</p>
							)}
							{cs.error && <p className="text-red-500">{cs.error}</p>}
						</div>
					))}
				</div>
			</CardContent>
		</Card>
	);
}
