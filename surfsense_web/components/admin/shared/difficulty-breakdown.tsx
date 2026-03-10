"use client";

import { Badge } from "@/components/ui/badge";

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

export interface DifficultyBreakdownItem {
	difficulty: string;
	total_tests: number;
	passed_tests: number;
	success_rate: number;
	gated_success_rate?: number | null;
}

interface DifficultyBreakdownProps {
	title: string;
	items: DifficultyBreakdownItem[];
}

export function DifficultyBreakdown({ title, items }: DifficultyBreakdownProps) {
	if (!items.length) return null;
	return (
		<div className="rounded border p-3 space-y-2">
			<p className="text-sm font-medium">{title}</p>
			<div className="flex flex-wrap gap-2">
				{items.map((item) => (
					<Badge key={`${title}-${item.difficulty}`} variant="outline">
						{formatDifficultyLabel(item.difficulty)}: {item.passed_tests}/{item.total_tests} (
						{(item.success_rate * 100).toFixed(1)}%)
						{item.gated_success_rate == null
							? ""
							: ` · gated ${(item.gated_success_rate * 100).toFixed(1)}%`}
					</Badge>
				))}
			</div>
		</div>
	);
}
