"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { useAtomValue } from "jotai";
import { currentUserAtom } from "@/atoms/user/user-query.atoms";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import { Separator } from "@/components/ui/separator";
import { AlertCircle, Save, RotateCcw, Plus, X } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface ToolMetadata {
	tool_id: string;
	name: string;
	description: string;
	keywords: string[];
	example_queries: string[];
	category: string;
}

interface ToolCategory {
	category_id: string;
	category_name: string;
	tools: ToolMetadata[];
}

// Mock data for now - will be replaced with API call
const MOCK_TOOL_CATEGORIES: ToolCategory[] = [
	{
		category_id: "riksdagen",
		category_name: "Riksdagen",
		tools: [
			{
				tool_id: "riksdag_dokument",
				name: "Riksdag Dokument - Alla typer",
				description: "Sök bland alla 70+ dokumenttyper från Riksdagen.",
				keywords: ["dokument", "riksdag", "riksdagen", "söka", "sök"],
				example_queries: [
					"Dokument om försvar 2024",
					"Riksdagsdokument från Finansutskottet",
				],
				category: "riksdagen_dokument",
			},
			{
				tool_id: "riksdag_dokument_proposition",
				name: "Riksdag Dokument - Proposition",
				description: "Sök propositioner (regeringens förslag till riksdagen).",
				keywords: ["proposition", "prop", "regeringen", "förslag"],
				example_queries: [
					"Propositioner om NATO 2024",
					"Senaste budgetpropositionen",
				],
				category: "riksdagen_dokument",
			},
		],
	},
	{
		category_id: "scb",
		category_name: "SCB Statistik",
		tools: [
			{
				tool_id: "scb_befolkning",
				name: "SCB Befolkning",
				description: "Befolkningsstatistik från SCB.",
				keywords: ["befolkning", "invånare", "demografisk"],
				example_queries: [
					"Befolkning per län 2024",
					"Befolkningsökning Sverige",
				],
				category: "statistics",
			},
		],
	},
];

function ToolEditor({
	tool,
	onSave,
	onReset,
}: {
	tool: ToolMetadata;
	onSave: (tool: ToolMetadata) => void;
	onReset: () => void;
}) {
	const [editedTool, setEditedTool] = useState<ToolMetadata>(tool);
	const [newKeyword, setNewKeyword] = useState("");
	const [newExample, setNewExample] = useState("");

	const hasChanges = JSON.stringify(editedTool) !== JSON.stringify(tool);

	const addKeyword = () => {
		if (newKeyword.trim()) {
			setEditedTool({
				...editedTool,
				keywords: [...editedTool.keywords, newKeyword.trim()],
			});
			setNewKeyword("");
		}
	};

	const removeKeyword = (index: number) => {
		setEditedTool({
			...editedTool,
			keywords: editedTool.keywords.filter((_, i) => i !== index),
		});
	};

	const addExample = () => {
		if (newExample.trim()) {
			setEditedTool({
				...editedTool,
				example_queries: [...editedTool.example_queries, newExample.trim()],
			});
			setNewExample("");
		}
	};

	const removeExample = (index: number) => {
		setEditedTool({
			...editedTool,
			example_queries: editedTool.example_queries.filter((_, i) => i !== index),
		});
	};

	return (
		<div className="space-y-4">
			<div className="space-y-2">
				<Label htmlFor={`name-${tool.tool_id}`}>Namn</Label>
				<Input
					id={`name-${tool.tool_id}`}
					value={editedTool.name}
					onChange={(e) =>
						setEditedTool({ ...editedTool, name: e.target.value })
					}
				/>
			</div>

			<div className="space-y-2">
				<Label htmlFor={`desc-${tool.tool_id}`}>Beskrivning</Label>
				<Textarea
					id={`desc-${tool.tool_id}`}
					value={editedTool.description}
					onChange={(e) =>
						setEditedTool({ ...editedTool, description: e.target.value })
					}
					rows={3}
				/>
			</div>

			<div className="space-y-2">
				<Label>Keywords</Label>
				<div className="flex flex-wrap gap-2 mb-2">
					{editedTool.keywords.map((keyword, index) => (
						<Badge key={index} variant="secondary" className="gap-1">
							{keyword}
							<button
								onClick={() => removeKeyword(index)}
								className="ml-1 hover:text-destructive"
							>
								<X className="h-3 w-3" />
							</button>
						</Badge>
					))}
				</div>
				<div className="flex gap-2">
					<Input
						placeholder="Nytt keyword..."
						value={newKeyword}
						onChange={(e) => setNewKeyword(e.target.value)}
						onKeyPress={(e) => e.key === "Enter" && addKeyword()}
					/>
					<Button onClick={addKeyword} size="sm" variant="outline">
						<Plus className="h-4 w-4" />
					</Button>
				</div>
			</div>

			<div className="space-y-2">
				<Label>Exempelfrågor</Label>
				<div className="space-y-2 mb-2">
					{editedTool.example_queries.map((example, index) => (
						<div key={index} className="flex items-center gap-2">
							<div className="flex-1 text-sm bg-muted p-2 rounded">
								{example}
							</div>
							<Button
								onClick={() => removeExample(index)}
								size="sm"
								variant="ghost"
							>
								<X className="h-4 w-4" />
							</Button>
						</div>
					))}
				</div>
				<div className="flex gap-2">
					<Input
						placeholder="Ny exempelfråga..."
						value={newExample}
						onChange={(e) => setNewExample(e.target.value)}
						onKeyPress={(e) => e.key === "Enter" && addExample()}
					/>
					<Button onClick={addExample} size="sm" variant="outline">
						<Plus className="h-4 w-4" />
					</Button>
				</div>
			</div>

			{hasChanges && (
				<div className="flex gap-2 pt-4">
					<Button onClick={() => onSave(editedTool)} className="gap-2">
						<Save className="h-4 w-4" />
						Spara ändringar
					</Button>
					<Button onClick={onReset} variant="outline" className="gap-2">
						<RotateCcw className="h-4 w-4" />
						Återställ
					</Button>
				</div>
			)}
		</div>
	);
}

export function ToolSettingsPage() {
	const { data: currentUser } = useAtomValue(currentUserAtom);
	const [searchTerm, setSearchTerm] = useState("");

	// TODO: Replace with actual API call
	const categories = MOCK_TOOL_CATEGORIES;

	const handleSave = (tool: ToolMetadata) => {
		// TODO: Implement save to backend
		toast.success(`Sparade ändringar för ${tool.name}`);
		console.log("Saving tool:", tool);
	};

	const handleReset = () => {
		toast.info("Återställde till ursprungsvärden");
	};

	const filteredCategories = categories
		.map((category) => ({
			...category,
			tools: category.tools.filter(
				(tool) =>
					tool.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
					tool.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
					tool.tool_id.toLowerCase().includes(searchTerm.toLowerCase())
			),
		}))
		.filter((category) => category.tools.length > 0);

	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold">Tool Settings</h1>
				<p className="text-muted-foreground mt-2">
					Konfigurera metadata och inställningar för varje verktyg och
					sub-tool.
				</p>
			</div>

			<Alert>
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>
					Ändringar här påverkar hur LLM:en hittar och använder verktygen.
					Uppdatera keywords och exempelfrågor för bättre precision.
				</AlertDescription>
			</Alert>

			<div className="flex items-center gap-4">
				<Input
					placeholder="Sök verktyg..."
					value={searchTerm}
					onChange={(e) => setSearchTerm(e.target.value)}
					className="max-w-md"
				/>
				<div className="text-sm text-muted-foreground">
					{filteredCategories.reduce((acc, cat) => acc + cat.tools.length, 0)}{" "}
					verktyg
				</div>
			</div>

			<Accordion type="single" collapsible className="space-y-4">
				{filteredCategories.map((category) => (
					<Card key={category.category_id}>
						<AccordionItem value={category.category_id} className="border-0">
							<CardHeader>
								<AccordionTrigger className="hover:no-underline">
									<div className="flex items-center gap-3">
										<CardTitle>{category.category_name}</CardTitle>
										<Badge variant="outline">{category.tools.length} verktyg</Badge>
									</div>
								</AccordionTrigger>
							</CardHeader>
							<AccordionContent>
								<CardContent>
									<div className="space-y-6">
										{category.tools.map((tool, index) => (
											<div key={tool.tool_id}>
												{index > 0 && <Separator className="my-6" />}
												<div className="space-y-4">
													<div>
														<div className="flex items-center gap-2 mb-1">
															<h3 className="font-semibold">{tool.name}</h3>
															<Badge variant="secondary" className="text-xs">
																{tool.tool_id}
															</Badge>
														</div>
														<p className="text-sm text-muted-foreground">
															Kategori: {tool.category}
														</p>
													</div>
													<ToolEditor
														tool={tool}
														onSave={handleSave}
														onReset={handleReset}
													/>
												</div>
											</div>
										))}
									</div>
								</CardContent>
							</AccordionContent>
						</AccordionItem>
					</Card>
				))}
			</Accordion>

			{filteredCategories.length === 0 && (
				<Card>
					<CardContent className="py-12 text-center">
						<p className="text-muted-foreground">
							Inga verktyg matchade sökningen &quot;{searchTerm}&quot;
						</p>
					</CardContent>
				</Card>
			)}
		</div>
	);
}
