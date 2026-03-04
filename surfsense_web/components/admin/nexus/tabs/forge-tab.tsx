"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2, Sparkles, Play, CheckCircle2, XCircle, Trash2, Search } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
	nexusApiService,
	type SyntheticCaseResponse,
	type PlatformToolResponse,
} from "@/lib/apis/nexus-api.service";

const CATEGORY_LABELS: Record<string, string> = {
	"": "Alla kategorier",
	smhi: "SMHI (V\u00e4der)",
	scb: "SCB (Statistik)",
	kolada: "Kolada (Nyckeltal)",
	riksdagen: "Riksdagen",
	trafikverket: "Trafikverket",
	bolagsverket: "Bolagsverket",
	marketplace: "Marknadsplats",
	skolverket: "Skolverket",
	builtin: "Inbyggda verktyg",
	geoapify: "Kartor (Geoapify)",
};

export function ForgeTab() {
	const [cases, setCases] = useState<SyntheticCaseResponse[]>([]);
	const [platformTools, setPlatformTools] = useState<PlatformToolResponse[]>([]);
	const [categories, setCategories] = useState<string[]>([]);
	const [selectedCategory, setSelectedCategory] = useState<string>("");
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [generating, setGenerating] = useState(false);
	const [searchQuery, setSearchQuery] = useState<string>("");
	const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());

	const loadCases = () => {
		setLoading(true);
		nexusApiService
			.getForgeCases()
			.then(setCases)
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false));
	};

	const loadPlatformTools = () => {
		nexusApiService
			.getPlatformTools()
			.then((data) => {
				setPlatformTools(data.tools || []);
				setCategories(data.categories || []);
			})
			.catch(() => {
				/* non-critical */
			});
	};

	useEffect(() => {
		loadCases();
		loadPlatformTools();
	}, []);

	const handleGenerate = () => {
		setGenerating(true);
		const request = selectedCategory ? { category: selectedCategory } : {};
		nexusApiService
			.forgeGenerate(request)
			.then(() => {
				loadCases();
			})
			.catch((err) => setError(err.message))
			.finally(() => setGenerating(false));
	};

	const handleDelete = (caseId: string) => {
		setDeletingIds((prev) => new Set(prev).add(caseId));
		nexusApiService
			.deleteForgeCase(caseId)
			.then(() => {
				setCases((prev) => prev.filter((c) => c.id !== caseId));
			})
			.catch((err) => setError(err.message))
			.finally(() => {
				setDeletingIds((prev) => {
					const next = new Set(prev);
					next.delete(caseId);
					return next;
				});
			});
	};

	// Filter displayed cases by selected category
	const categoryFiltered = selectedCategory
		? cases.filter((c) => {
				const tool = platformTools.find((t) => t.tool_id === c.tool_id);
				return tool?.category === selectedCategory;
			})
		: cases;

	// Filter by search query (question or tool_id)
	const query = searchQuery.trim().toLowerCase();
	const filteredCases = query
		? categoryFiltered.filter(
				(c) =>
					c.question.toLowerCase().includes(query) ||
					c.tool_id.toLowerCase().includes(query),
			)
		: categoryFiltered;

	const toolCount = new Set(
		(selectedCategory ? filteredCases : cases).map((c) => c.tool_id),
	).size;
	const platformToolCount = selectedCategory
		? platformTools.filter((t) => t.category === selectedCategory).length
		: platformTools.length;

	if (loading) {
		return (
			<div className="flex items-center gap-2 text-muted-foreground p-4">
				<Loader2 className="h-4 w-4 animate-spin" />
				Laddar syntetiska testfall...
			</div>
		);
	}

	if (error) {
		return (
			<Alert variant="destructive">
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>{error}</AlertDescription>
			</Alert>
		);
	}

	return (
		<div className="space-y-6">
			{/* Header + Category Filter + Generate Button */}
			<div className="flex items-center justify-between">
				<div>
					<h3 className="text-lg font-semibold flex items-center gap-2">
						<Sparkles className="h-5 w-5" />
						Synth Forge — Testgenerering
					</h3>
					<p className="text-sm text-muted-foreground">
						LLM-genererade testfr&aring;gor vid 4 sv&aring;righetsgrader per verktyg
					</p>
				</div>
				<div className="flex items-center gap-3">
					<select
						value={selectedCategory}
						onChange={(e) => setSelectedCategory(e.target.value)}
						className="rounded-md border bg-background px-3 py-2 text-sm"
					>
						<option value="">Alla kategorier ({platformTools.length} verktyg)</option>
						{categories
							.filter((c) => c !== "external_model")
							.map((cat) => (
								<option key={cat} value={cat}>
									{CATEGORY_LABELS[cat] || cat} (
									{platformTools.filter((t) => t.category === cat).length})
								</option>
							))}
					</select>
					<Button onClick={handleGenerate} disabled={generating}>
						{generating ? (
							<Loader2 className="h-4 w-4 animate-spin mr-2" />
						) : (
							<Play className="h-4 w-4 mr-2" />
						)}
						{generating
							? "Genererar..."
							: selectedCategory
								? `Generera f\u00f6r ${CATEGORY_LABELS[selectedCategory] || selectedCategory}`
								: "Generera testfall"}
					</Button>
				</div>
			</div>

			{/* Search */}
			<div className="relative">
				<Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
				<Input
					placeholder="S\u00f6k p\u00e5 fr\u00e5ga eller verktygs-ID..."
					value={searchQuery}
					onChange={(e) => setSearchQuery(e.target.value)}
					className="pl-9"
				/>
			</div>

			{/* Stats */}
			<div className="grid grid-cols-1 md:grid-cols-4 gap-4">
				<StatCard label="Plattformsverktyg" value={String(platformToolCount)} />
				<StatCard label="Testfall genererade" value={String(filteredCases.length)} />
				<StatCard
					label="Verifierade"
					value={String(filteredCases.filter((c) => c.roundtrip_verified).length)}
				/>
				<StatCard label="Verktyg med testfall" value={String(toolCount)} />
			</div>

			{/* Cases grouped by tool, then by difficulty */}
			{filteredCases.length === 0 ? (
				<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
					{selectedCategory
						? `Inga testfall for ${CATEGORY_LABELS[selectedCategory] || selectedCategory}. Klicka "Generera" for att skapa.`
						: query
							? "Inga testfall matchar din sokning."
							: 'Inga syntetiska testfall genererade annu. Klicka "Generera testfall" for att borja.'}
				</div>
			) : (
				<ToolGroupedCases cases={filteredCases} deletingIds={deletingIds} onDelete={handleDelete} />
			)}
		</div>
	);
}

function StatCard({ label, value }: { label: string; value: string }) {
	return (
		<div className="rounded-lg border bg-card p-4">
			<p className="text-sm text-muted-foreground">{label}</p>
			<p className="text-2xl font-bold mt-1">{value}</p>
		</div>
	);
}

const DIFFICULTY_ORDER = ["easy", "medium", "hard", "adversarial"];
const DIFFICULTY_LABELS: Record<string, string> = {
	easy: "LATT (direkta)",
	medium: "MEDEL (kontextuella)",
	hard: "SVAR (tvetydiga)",
	adversarial: "ADVERSARIAL (bor INTE valja detta verktyg)",
};

function ToolGroupedCases({
	cases,
	deletingIds,
	onDelete,
}: {
	cases: SyntheticCaseResponse[];
	deletingIds: Set<string>;
	onDelete: (id: string) => void;
}) {
	// Group by tool_id
	const byTool = new Map<string, SyntheticCaseResponse[]>();
	for (const c of cases) {
		const list = byTool.get(c.tool_id) || [];
		list.push(c);
		byTool.set(c.tool_id, list);
	}

	return (
		<div className="space-y-4">
			{Array.from(byTool.entries())
				.sort(([a], [b]) => a.localeCompare(b))
				.map(([toolId, toolCases]) => {
					const verified = toolCases.filter((c) => c.roundtrip_verified).length;
					const byDiff = new Map<string, SyntheticCaseResponse[]>();
					for (const c of toolCases) {
						const list = byDiff.get(c.difficulty) || [];
						list.push(c);
						byDiff.set(c.difficulty, list);
					}

					return (
						<div key={toolId} className="rounded-lg border bg-card">
							<div className="p-4 border-b flex items-center justify-between">
								<div>
									<h4 className="font-mono font-semibold text-sm">{toolId}</h4>
									<p className="text-xs text-muted-foreground">
										{toolCases[0]?.namespace} — {toolCases.length} testfall, {verified} verifierade
									</p>
								</div>
								<div className="flex gap-1.5">
									{DIFFICULTY_ORDER.map((d) => {
										const count = byDiff.get(d)?.length ?? 0;
										return (
											<span key={d} className="text-xs text-muted-foreground">
												<DifficultyBadge difficulty={d} /> {count}
											</span>
										);
									})}
								</div>
							</div>
							<div className="max-h-80 overflow-y-auto">
								{DIFFICULTY_ORDER.filter((d) => byDiff.has(d)).map((difficulty) => (
									<div key={difficulty}>
										<div className="px-4 py-1.5 bg-muted/30 text-xs font-medium text-muted-foreground">
											{DIFFICULTY_LABELS[difficulty] || difficulty}
										</div>
										<div className="divide-y">
											{(byDiff.get(difficulty) || []).map((c) => (
												<div key={c.id} className="flex items-start justify-between px-4 py-2.5 gap-4">
													<div className="flex-1 min-w-0">
														<p className="text-sm">{c.question}</p>
													</div>
													<div className="flex items-center gap-2 shrink-0">
														<Badge variant="outline" className="text-xs font-mono">
															{c.quality_score != null ? c.quality_score.toFixed(1) : "\u2014"}
														</Badge>
														{c.roundtrip_verified ? (
															<CheckCircle2 className="h-4 w-4 text-green-600" />
														) : (
															<XCircle className="h-4 w-4 text-muted-foreground" />
														)}
														<Button
															variant="ghost"
															size="icon"
															className="h-7 w-7 text-muted-foreground hover:text-destructive"
															disabled={deletingIds.has(c.id)}
															onClick={() => onDelete(c.id)}
															title="Ta bort testfall"
														>
															{deletingIds.has(c.id) ? (
																<Loader2 className="h-3.5 w-3.5 animate-spin" />
															) : (
																<Trash2 className="h-3.5 w-3.5" />
															)}
														</Button>
													</div>
												</div>
											))}
										</div>
									</div>
								))}
							</div>
						</div>
					);
				})}
		</div>
	);
}

function DifficultyBadge({ difficulty }: { difficulty: string }) {
	const colors: Record<string, string> = {
		easy: "bg-green-100 text-green-700",
		medium: "bg-blue-100 text-blue-700",
		hard: "bg-amber-100 text-amber-700",
		adversarial: "bg-red-100 text-red-700",
	};
	const color = colors[difficulty] || "bg-gray-100 text-gray-700";

	return (
		<span className={`text-xs px-2 py-0.5 rounded ${color}`}>{difficulty}</span>
	);
}
