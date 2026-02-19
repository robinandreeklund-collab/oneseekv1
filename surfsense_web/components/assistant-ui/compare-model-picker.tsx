"use client";

import { AnimatePresence, motion } from "motion/react";
import { Check, GitCompareArrows, Save } from "lucide-react";
import { type FC, useState } from "react";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// ============================================================================
// Model definitions (synced with backend ExternalModelSpec)
// ============================================================================

export interface CompareModelDef {
	key: string;
	display: string;
	toolName: string;
	logo: string;
	description: string;
}

export const ALL_COMPARE_MODELS: CompareModelDef[] = [
	{ key: "claude", display: "Claude", toolName: "call_claude", logo: "/model-logos/claude.png", description: "Anthropic Claude 3.5 Sonnet" },
	{ key: "gpt", display: "ChatGPT", toolName: "call_gpt", logo: "/model-logos/chatgpt.png", description: "OpenAI GPT-4o" },
	{ key: "gemini", display: "Gemini", toolName: "call_gemini", logo: "/model-logos/gemini.png", description: "Google Gemini 1.5 Pro" },
	{ key: "perplexity", display: "Perplexity", toolName: "call_perplexity", logo: "/model-logos/perplexity.png", description: "Perplexity Sonar Large" },
	{ key: "deepseek", display: "DeepSeek", toolName: "call_deepseek", logo: "/model-logos/deepseek.png", description: "DeepSeek V3" },
	{ key: "qwen", display: "Qwen", toolName: "call_qwen", logo: "/model-logos/qwen.png", description: "Alibaba Qwen 2.5" },
	{ key: "grok", display: "Grok", toolName: "call_grok", logo: "/model-logos/grok.png", description: "xAI Grok-2" },
];

// ============================================================================
// Presets
// ============================================================================

export const COMPARE_PRESETS = {
	quick: { label: "⚡ Snabb", models: ["claude", "gpt"], description: "2 modeller, ~2-3s" },
	standard: { label: "📊 Standard", models: ["claude", "gpt", "gemini", "perplexity"], description: "4 modeller, ~4-6s" },
	all: { label: "🌐 Alla", models: ALL_COMPARE_MODELS.map((m) => m.key), description: "Alla tillgängliga" },
	custom: { label: "✏️ Anpassad", models: [] as string[], description: "Ditt eget urval" },
} as const;

export type ComparePresetKey = keyof typeof COMPARE_PRESETS;

// ============================================================================
// Model chip sub-component
// ============================================================================

function ModelChip({
	model,
	isSelected,
	onToggle,
}: {
	model: CompareModelDef;
	isSelected: boolean;
	onToggle: () => void;
}) {
	const [imgError, setImgError] = useState(false);

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<button
				type="button"
				onClick={onToggle}
				className={cn(
					"flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs transition-all",
					"focus-visible:ring-2 focus-visible:ring-violet-500/50 focus-visible:outline-none",
					isSelected
						? "border-violet-500/40 bg-violet-500/10 text-violet-700 dark:text-violet-300"
						: "border-border/60 bg-background text-muted-foreground hover:border-muted-foreground/40 hover:text-foreground"
				)}
				>
					{!imgError ? (
						<img
							src={model.logo}
							alt={model.display}
							className="size-4 rounded-sm object-contain"
							loading="lazy"
							onError={() => setImgError(true)}
						/>
					) : (
						<span className="flex size-4 items-center justify-center rounded-sm bg-muted text-[8px] font-bold">
							{model.display.charAt(0)}
						</span>
						)}
					<span>{model.display}</span>
					{isSelected && <Check className="size-3 text-violet-500" />}
				</button>
				</TooltipTrigger>
				<TooltipContent side="bottom" className="text-xs">
					{model.description}
				</TooltipContent>
				</Tooltip>
		);
}

// ============================================================================
// Main CompareModelPicker
// ============================================================================

interface CompareModelPickerProps {
	selectedModels: Set<string>;
	onToggleModel: (key: string) => void;
	activePreset: ComparePresetKey;
	onPresetChange: (preset: ComparePresetKey) => void;
	onSaveDefaults: () => void;
	hasUnsavedChanges?: boolean;
}

export const CompareModelPicker: FC<CompareModelPickerProps> = ({
	selectedModels,
	onToggleModel,
	activePreset,
	onPresetChange,
	onSaveDefaults,
	hasUnsavedChanges = false,
}) => {
	return (
		<motion.div
			initial={{ height: 0, opacity: 0 }}
			animate={{ height: "auto", opacity: 1 }}
			exit={{ height: 0, opacity: 0 }}
			transition={{ duration: 0.2, ease: "easeOut" }}
			className="overflow-hidden"
		>
			<div className="border-b border-violet-500/15 bg-violet-500/[0.03] px-3 py-2.5">
				{/* Header with preset selector */}
				<div className="mb-2 flex items-center justify-between gap-2">
					<div className="flex items-center gap-1.5">
						<GitCompareArrows className="size-3.5 text-violet-500" />
						<span className="text-xs font-medium text-violet-600 dark:text-violet-400">
							Compare-läge
						</span>
					</div>

					<div className="flex items-center gap-2">
						<Select value={activePreset} onValueChange={(v) => onPresetChange(v as ComparePresetKey)}>
							<SelectTrigger className="h-6 w-auto gap-1 border-violet-500/20 bg-transparent px-2 text-[10px] text-violet-600 dark:text-violet-400">
								<SelectValue />
							</SelectTrigger>
							<SelectContent>
								{Object.entries(COMPARE_PRESETS).map(([key, preset]) => (
									<SelectItem key={key} value={key} className="text-xs">
										<span>{preset.label}</span>
										<span className="ml-2 text-muted-foreground">{preset.description}</span>
									</SelectItem>
								))}
							</SelectContent>
						</Select>

						{hasUnsavedChanges && (
							<Button
								variant="ghost"
								size="sm"
								onClick={onSaveDefaults}
								className="h-5 gap-1 px-1.5 text-[10px] text-violet-500 hover:text-violet-600"
							>
								<Save className="size-2.5" />
								Spara
							</Button>
						)}
					</div>
				</div>

				{/* Model chips */}
				<div className="flex flex-wrap gap-1.5">
					{ALL_COMPARE_MODELS.map((model) => (
						<ModelChip
							key={model.key}
							model={model}
							isSelected={selectedModels.has(model.key)}
							onToggle={() => onToggleModel(model.key)}
						/>
					))}
				</div>

				{/* Footer stats */}
				<div className="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground/70">
					<span>{selectedModels.size} modeller valda</span>
					<span>·</span>
					<span>Uppskattad tid: ~{Math.ceil(selectedModels.size * 1.5)}s</span>
					{selectedModels.size < 2 && (
						<span className="text-amber-500">Välj minst 2 modeller för att jämföra</span>
					)}
				</div>
				</div>
			</motion.div>
	);
};