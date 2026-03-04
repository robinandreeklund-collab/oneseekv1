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

			{/* Cases by difficulty */}
			{filteredCases.length === 0 ? (
				<div className="rounded-lg border bg-card p-6 text-center text-muted-foreground">
					{selectedCategory
						? `Inga testfall f\u00f6r ${CATEGORY_LABELS[selectedCategory] || selectedCategory}. Klicka "Generera" f\u00f6r att skapa.`
						: query
							? "Inga testfall matchar din s\u00f6kning."
							: 'Inga syntetiska testfall genererade \u00e4nnu. Klicka "Generera testfall" f\u00f6r att b\u00f6rja.'}
				</div>
			) : (
				<div className="rounded-lg border bg-card">
					<div className="p-4 border-b">
						<h4 className="font-semibold">Testfall ({filteredCases.length})</h4>
					</div>
					<div className="divide-y max-h-96 overflow-y-auto">
						{filteredCases.map((c) => (
							<div key={c.id} className="flex items-start justify-between p-4 gap-4">
								<div className="flex-1 min-w-0">
									<p className="text-sm font-medium truncate">{c.question}</p>
									<p className="text-xs text-muted-foreground mt-1">
										{c.tool_id} &middot; {c.namespace}
									</p>
								</div>
								<div className="flex items-center gap-2 shrink-0">
									<Badge variant="outline" className="text-xs font-mono">
										{c.quality_score != null
											? c.quality_score.toFixed(1)
											: "\u2014"}
									</Badge>
									<DifficultyBadge difficulty={c.difficulty} />
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
										onClick={() => handleDelete(c.id)}
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
