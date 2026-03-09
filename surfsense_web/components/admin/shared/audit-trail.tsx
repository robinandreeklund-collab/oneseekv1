"use client";

/**
 * Audit trail component — shows lifecycle change history.
 * Used in the Överblick tab to display who changed what and when.
 */

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export interface AuditTrailEntry {
	id: number;
	tool_id: string;
	old_status: string | null;
	new_status: string;
	success_rate: number | null;
	trigger: string;
	reason: string | null;
	changed_by_email: string | null;
	created_at: string;
}

interface AuditTrailProps {
	entries: AuditTrailEntry[];
	isLoading?: boolean;
}

function triggerLabel(trigger: string): string {
	switch (trigger) {
		case "manual":
			return "Manuell";
		case "eval_sync":
			return "Eval-synk";
		case "rollback":
			return "Rollback";
		case "bulk_promote":
			return "Bulk-befordran";
		default:
			return trigger;
	}
}

function triggerVariant(trigger: string): "default" | "secondary" | "destructive" | "outline" {
	switch (trigger) {
		case "rollback":
			return "destructive";
		case "eval_sync":
			return "secondary";
		case "bulk_promote":
			return "default";
		default:
			return "outline";
	}
}

function statusArrow(oldStatus: string | null, newStatus: string): string {
	if (!oldStatus) return `→ ${newStatus}`;
	return `${oldStatus} → ${newStatus}`;
}

export function AuditTrail({ entries, isLoading }: AuditTrailProps) {
	if (isLoading) {
		return (
			<Card>
				<CardHeader>
					<CardTitle>Audit Trail</CardTitle>
					<CardDescription>Laddar historik...</CardDescription>
				</CardHeader>
			</Card>
		);
	}

	return (
		<Card>
			<CardHeader>
				<CardTitle>Audit Trail</CardTitle>
				<CardDescription>Historik över lifecycle-ändringar — vem, vad, när.</CardDescription>
			</CardHeader>
			<CardContent>
				{entries.length === 0 ? (
					<p className="text-sm text-muted-foreground">
						Ingen historik ännu. Ändringar loggas automatiskt.
					</p>
				) : (
					<div className="space-y-2 max-h-96 overflow-auto">
						{entries.map((entry) => (
							<div key={entry.id} className="flex items-start gap-3 rounded border p-3 text-sm">
								<div className="flex-1 min-w-0 space-y-1">
									<div className="flex items-center gap-2 flex-wrap">
										<span className="font-mono text-xs truncate max-w-[200px]">
											{entry.tool_id}
										</span>
										<Badge variant={triggerVariant(entry.trigger)} className="text-xs">
											{triggerLabel(entry.trigger)}
										</Badge>
										<span className="text-xs text-muted-foreground">
											{statusArrow(entry.old_status, entry.new_status)}
										</span>
										{entry.success_rate !== null && (
											<span className="text-xs text-muted-foreground">
												({(entry.success_rate * 100).toFixed(1)}%)
											</span>
										)}
									</div>
									{entry.reason && (
										<p className="text-xs text-muted-foreground truncate">{entry.reason}</p>
									)}
								</div>
								<div className="text-right shrink-0 space-y-1">
									<p className="text-xs text-muted-foreground">
										{new Date(entry.created_at).toLocaleString("sv-SE")}
									</p>
									{entry.changed_by_email && (
										<p className="text-xs text-muted-foreground">{entry.changed_by_email}</p>
									)}
								</div>
							</div>
						))}
					</div>
				)}
			</CardContent>
		</Card>
	);
}
