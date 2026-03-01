"use client";

import { useCallback, useEffect, useState } from "react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import {
	CheckCircle2,
	Loader2,
	Mic,
	Save,
	Volume2,
	Hash,
} from "lucide-react";
import {
	adminDebateApiService,
	type DebateVoiceSettings,
} from "@/lib/apis/admin-debate-api.service";
import Image from "next/image";

// All 13 built-in voices for gpt-4o-mini-tts
const OPENAI_VOICES = [
	"alloy",
	"ash",
	"ballad",
	"coral",
	"echo",
	"fable",
	"nova",
	"onyx",
	"sage",
	"shimmer",
	"verse",
	"marin",
	"cedar",
] as const;

const PARTICIPANTS = [
	"Grok",
	"Claude",
	"ChatGPT",
	"Gemini",
	"DeepSeek",
	"Perplexity",
	"Qwen",
	"OneSeek",
] as const;

const PARTICIPANT_LOGOS: Record<string, string> = {
	Grok: "/model-logos/grok.png",
	Claude: "/model-logos/claude.png",
	ChatGPT: "/model-logos/chatgpt.png",
	Gemini: "/model-logos/gemini.png",
	DeepSeek: "/model-logos/deepseek.png",
	Perplexity: "/model-logos/perplexity.png",
	Qwen: "/model-logos/qwen.png",
};

const DEFAULT_VOICE_MAP: Record<string, string> = {
	Grok: "ash",
	Claude: "ballad",
	ChatGPT: "coral",
	Gemini: "sage",
	DeepSeek: "verse",
	Perplexity: "onyx",
	Qwen: "marin",
	OneSeek: "nova",
};

const DEFAULT_CARTESIA_VOICE_MAP: Record<string, string> = {
	Grok: "c961b81c-a935-4c17-bfb3-ba2239de8c2f",
	Claude: "6ccbfb76-1fc6-48f7-b71d-91ac6298247b",
	ChatGPT: "a167e0f3-df7e-4d52-a9c3-f949145efdab",
	Gemini: "e07c00bc-4134-4eae-9ea4-1a55fb45746b",
	DeepSeek: "694f9389-aac1-45b6-b726-9d9369183238",
	Perplexity: "a0e99841-438c-4a64-b679-ae501e7d6091",
	Qwen: "f786b574-daa5-4673-aa0c-cbe3e8534c02",
	OneSeek: "6ccbfb76-1fc6-48f7-b71d-91ac6298247b",
};

const TTS_PROVIDERS = [
	{ value: "cartesia", label: "Cartesia Sonic-3 (Recommended)" },
	{ value: "openai", label: "OpenAI TTS" },
] as const;

const TTS_MODELS = [
	{ value: "gpt-4o-mini-tts", label: "gpt-4o-mini-tts (Recommended)" },
	{ value: "tts-1", label: "TTS-1 (Standard)" },
	{ value: "tts-1-hd", label: "TTS-1-HD (High Quality)" },
] as const;

const DEFAULT_MAX_TOKENS = 500;
const MIN_TOKENS = 50;
const MAX_TOKENS = 4096;

const INSTRUCTION_HINT = `Instruktionerna styr hur rösten låter. Du kan ange:

• Accent — "Speak with a slight British accent"
• Emotional range — "Sound enthusiastic and passionate"
• Intonation — "Vary pitch to emphasize key points"
• Impressions — "Sound like a confident news anchor"
• Speed of speech — "Speak at a measured, deliberate pace"
• Tone — "Warm and friendly"
• Whispering — "Whisper softly"

Kombinera fritt, t.ex:
"Speak Swedish with a warm, confident tone. Vary pitch for emphasis. Sound like a knowledgeable professor."`;

export function DebateSettingsPage() {
	const [settings, setSettings] = useState<DebateVoiceSettings>({
		tts_provider: "cartesia",
		api_key: "",
		cartesia_api_key: "",
		api_base: "https://api.openai.com/v1",
		model: "",
		speed: 1.0,
		voice_map: { ...DEFAULT_CARTESIA_VOICE_MAP },
		language: "sv",
		language_instructions: {},
		max_tokens: DEFAULT_MAX_TOKENS,
		max_tokens_map: {},
	});

	const [isLoading, setIsLoading] = useState(true);
	const [isSaving, setIsSaving] = useState(false);
	const [saved, setSaved] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [expandedParticipant, setExpandedParticipant] = useState<string | null>(null);

	// Load settings on mount
	useEffect(() => {
		(async () => {
			try {
				const resp = await adminDebateApiService.getVoiceSettings();
				// Handle backwards compat: old string → migrate to dict
				const rawLang = resp.settings.language_instructions;
				if (typeof rawLang === "string") {
					resp.settings.language_instructions = rawLang ? { __default__: rawLang } : {};
				}
				setSettings(resp.settings);
			} catch {
				// Defaults are fine
			} finally {
				setIsLoading(false);
			}
		})();
	}, []);

	const handleSave = useCallback(async () => {
		setIsSaving(true);
		setError(null);
		setSaved(false);
		try {
			await adminDebateApiService.updateVoiceSettings(settings);
			setSaved(true);
			setTimeout(() => setSaved(false), 3000);
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to save");
		} finally {
			setIsSaving(false);
		}
	}, [settings]);

	const updateVoice = useCallback(
		(participant: string, voice: string) => {
			setSettings((prev) => ({
				...prev,
				voice_map: { ...prev.voice_map, [participant]: voice },
			}));
		},
		[],
	);

	const updateLangInstruction = useCallback(
		(participant: string, value: string) => {
			setSettings((prev) => {
				const instructions = { ...(prev.language_instructions ?? {}) };
				if (value.trim()) {
					instructions[participant] = value;
				} else {
					delete instructions[participant];
				}
				return { ...prev, language_instructions: instructions };
			});
		},
		[],
	);

	const updateModelMaxTokens = useCallback(
		(participant: string, value: number | null) => {
			setSettings((prev) => {
				const map = { ...(prev.max_tokens_map ?? {}) };
				if (value === null) {
					delete map[participant];
				} else {
					map[participant] = value;
				}
				return { ...prev, max_tokens_map: map };
			});
		},
		[],
	);

	if (isLoading) {
		return (
			<div className="flex items-center justify-center p-12">
				<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	const langInstructions = settings.language_instructions ?? {};
	const maxTokensMap = settings.max_tokens_map ?? {};

	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold">Debatt</h1>
				<p className="text-muted-foreground mt-2">
					Konfigurera debattl&auml;ge och r&ouml;stdebatt (Live Voice Debate Mode)
				</p>
			</div>

			{/* TTS Provider & API Configuration */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Volume2 className="h-5 w-5" />
						TTS-konfiguration
					</CardTitle>
					<CardDescription>
						V&auml;lj TTS-leverant&ouml;r och konfigurera API-nycklar f&ouml;r r&ouml;stdebatt (/dvoice)
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					{/* Provider selector */}
					<div className="space-y-2">
						<Label htmlFor="tts-provider">TTS-leverant&ouml;r</Label>
						<Select
							value={settings.tts_provider ?? "cartesia"}
							onValueChange={(value) => {
								const newVoiceMap = value === "cartesia"
									? { ...DEFAULT_CARTESIA_VOICE_MAP }
									: { ...DEFAULT_VOICE_MAP };
								setSettings((prev) => ({
									...prev,
									tts_provider: value,
									voice_map: newVoiceMap,
								}));
							}}
						>
							<SelectTrigger id="tts-provider">
								<SelectValue />
							</SelectTrigger>
							<SelectContent>
								{TTS_PROVIDERS.map((p) => (
									<SelectItem key={p.value} value={p.value}>
										{p.label}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					</div>

					{/* Cartesia-specific settings */}
					{(settings.tts_provider ?? "cartesia") === "cartesia" && (
						<div className="grid gap-4 sm:grid-cols-2">
							<div className="space-y-2">
								<Label htmlFor="cartesia-api-key">Cartesia API-nyckel</Label>
								<Input
									id="cartesia-api-key"
									type="password"
									placeholder="sk_cart_..."
									value={settings.cartesia_api_key ?? ""}
									onChange={(e) =>
										setSettings((prev) => ({
											...prev,
											cartesia_api_key: e.target.value,
										}))
									}
								/>
								<p className="text-[10px] text-muted-foreground">
									Fr&aring;n{" "}
									<a href="https://play.cartesia.ai/" target="_blank" rel="noopener noreferrer" className="text-primary underline">
										play.cartesia.ai
									</a>
								</p>
							</div>
							<div className="space-y-2">
								<Label htmlFor="cartesia-language">Spr&aring;k</Label>
								<Input
									id="cartesia-language"
									placeholder="sv"
									value={settings.language ?? "sv"}
									onChange={(e) =>
										setSettings((prev) => ({
											...prev,
											language: e.target.value,
										}))
									}
								/>
								<p className="text-[10px] text-muted-foreground">
									Spr&aring;kkod: sv (svenska), en (engelska), de (tyska), etc.
								</p>
							</div>
						</div>
					)}

					{/* OpenAI-specific settings */}
					{(settings.tts_provider ?? "cartesia") === "openai" && (
						<>
							<div className="grid gap-4 sm:grid-cols-2">
								<div className="space-y-2">
									<Label htmlFor="api-key">OpenAI API-nyckel</Label>
									<Input
										id="api-key"
										type="password"
										placeholder="sk-..."
										value={settings.api_key}
										onChange={(e) =>
											setSettings((prev) => ({
												...prev,
												api_key: e.target.value,
											}))
										}
									/>
								</div>
								<div className="space-y-2">
									<Label htmlFor="api-base">API Base URL</Label>
									<Input
										id="api-base"
										placeholder="https://api.openai.com/v1"
										value={settings.api_base}
										onChange={(e) =>
											setSettings((prev) => ({
												...prev,
												api_base: e.target.value,
											}))
										}
									/>
								</div>
							</div>

							<div className="space-y-2">
								<Label htmlFor="tts-model">TTS-modell</Label>
								<Select
									value={settings.model || "gpt-4o-mini-tts"}
									onValueChange={(value) =>
										setSettings((prev) => ({ ...prev, model: value }))
									}
								>
									<SelectTrigger id="tts-model">
										<SelectValue />
									</SelectTrigger>
									<SelectContent>
										{TTS_MODELS.map((m) => (
											<SelectItem key={m.value} value={m.value}>
												{m.label}
											</SelectItem>
										))}
									</SelectContent>
								</Select>
							</div>
						</>
					)}

					{/* Speed (both providers) */}
					<div className="space-y-2">
						<Label>Hastighet: {settings.speed.toFixed(2)}x</Label>
						<Slider
							min={0.25}
							max={(settings.tts_provider ?? "cartesia") === "cartesia" ? 1.5 : 4.0}
							step={0.05}
							value={[settings.speed]}
							onValueChange={([v]) =>
								setSettings((prev) => ({ ...prev, speed: v }))
							}
						/>
						{(settings.tts_provider ?? "cartesia") === "cartesia" && (
							<p className="text-[10px] text-muted-foreground">
								Cartesia st&ouml;der 0.6x &ndash; 1.5x
							</p>
						)}
					</div>
				</CardContent>
			</Card>

			{/* Token Limits */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Hash className="h-5 w-5" />
						Token-begr&auml;nsning
					</CardTitle>
					<CardDescription>
						Max antal tokens per deltagare per runda. Begr&auml;nsar hur l&aring;nga svar varje modell f&aring;r generera.
						S&auml;tt per modell eller anv&auml;nd standard f&ouml;r alla.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					{/* Global default */}
					<div className="rounded-lg border border-dashed border-border p-3 space-y-2">
						<div className="flex items-center justify-between">
							<Label className="text-xs text-muted-foreground">
								Standard max tokens (alla deltagare)
							</Label>
							<span className="text-sm font-mono font-medium tabular-nums">
								{settings.max_tokens}
							</span>
						</div>
						<Slider
							min={MIN_TOKENS}
							max={MAX_TOKENS}
							step={50}
							value={[settings.max_tokens]}
							onValueChange={([v]) =>
								setSettings((prev) => ({ ...prev, max_tokens: v }))
							}
						/>
						<p className="text-[10px] text-muted-foreground">
							{MIN_TOKENS} &ndash; {MAX_TOKENS} tokens. Ca {Math.round(settings.max_tokens * 0.75)} ord per svar.
						</p>
					</div>

					{/* Per-model overrides */}
					<div className="grid gap-2 sm:grid-cols-2">
						{PARTICIPANTS.map((name) => {
							const hasOverride = name in maxTokensMap;
							const effectiveValue = hasOverride ? maxTokensMap[name] : settings.max_tokens;

							return (
								<div
									key={name}
									className="flex items-center gap-3 rounded-lg border border-border p-2.5"
								>
									<div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-muted">
										{PARTICIPANT_LOGOS[name] ? (
											<Image
												src={PARTICIPANT_LOGOS[name]}
												alt={name}
												width={20}
												height={20}
												className="rounded"
											/>
										) : (
											<span className="text-[10px] font-bold">{name.slice(0, 2)}</span>
										)}
									</div>
									<div className="min-w-0 flex-1">
										<div className="flex items-center justify-between mb-1">
											<span className="text-xs font-medium">{name}</span>
											<div className="flex items-center gap-1.5">
												<span className="text-xs font-mono tabular-nums">
													{effectiveValue}
												</span>
												{hasOverride ? (
													<button
														type="button"
														className="text-[9px] text-muted-foreground hover:text-destructive transition-colors"
														onClick={() => updateModelMaxTokens(name, null)}
														title="Återställ till standard"
													>
														&times;
													</button>
												) : (
													<span className="text-[9px] text-muted-foreground">std</span>
												)}
											</div>
										</div>
										<Slider
											min={MIN_TOKENS}
											max={MAX_TOKENS}
											step={50}
											value={[effectiveValue]}
											onValueChange={([v]) => updateModelMaxTokens(name, v)}
										/>
									</div>
								</div>
							);
						})}
					</div>
				</CardContent>
			</Card>

			{/* Voice Map + Per-Model Instructions */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Mic className="h-5 w-5" />
						R&ouml;st &amp; instruktioner per deltagare
					</CardTitle>
					<CardDescription>
						{(settings.tts_provider ?? "cartesia") === "cartesia"
							? "Ange Cartesia voice-ID (UUID) per deltagare. Bläddra röster på play.cartesia.ai"
							: "Välj röst (13 tillgängliga) och ange instruktioner för accent, ton, känsla m.m."}
						{" "}Klicka p&aring; en deltagare f&ouml;r att expandera instruktionsf&auml;ltet.
					</CardDescription>
				</CardHeader>
				<CardContent>
					{/* Default instruction */}
					<div className="mb-4 space-y-2 rounded-lg border border-dashed border-border p-3">
						<Label className="text-xs text-muted-foreground">
							Standard-instruktion (g&auml;ller alla utan egen)
						</Label>
						<Textarea
							placeholder="T.ex. 'Speak Swedish clearly with a warm, professional tone.'"
							value={langInstructions.__default__ ?? ""}
							onChange={(e) => updateLangInstruction("__default__", e.target.value)}
							rows={2}
							className="text-sm"
						/>
					</div>

					<div className="grid gap-3 sm:grid-cols-2">
						{PARTICIPANTS.map((name) => {
							const isExpanded = expandedParticipant === name;
							const hasInstruction = Boolean(langInstructions[name]?.trim());

							return (
								<div
									key={name}
									className="rounded-lg border border-border transition-all duration-200 hover:border-primary/30"
								>
									{/* Header row: logo + name + voice picker */}
									<div className="flex items-center gap-3 p-3">
										{/* Logo */}
										<div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted">
											{PARTICIPANT_LOGOS[name] ? (
												<Image
													src={PARTICIPANT_LOGOS[name]}
													alt={name}
													width={28}
													height={28}
													className="rounded"
												/>
											) : (
												<span className="text-xs font-bold">{name.slice(0, 2)}</span>
											)}
										</div>
										<div className="min-w-0 flex-1 space-y-1">
											<button
												type="button"
												className="flex w-full items-center gap-2 text-left"
												onClick={() => setExpandedParticipant(isExpanded ? null : name)}
											>
												<span className="text-sm font-medium">{name}</span>
												{hasInstruction && (
													<Badge variant="outline" className="border-primary/30 text-primary text-[9px] px-1.5 py-0">
														instruktion
													</Badge>
												)}
											</button>
											{(settings.tts_provider ?? "cartesia") === "cartesia" ? (
												<Input
													className="h-8 text-xs font-mono"
													placeholder="voice-uuid..."
													value={settings.voice_map[name] ?? ""}
													onChange={(e) => updateVoice(name, e.target.value)}
												/>
											) : (
												<Select
													value={settings.voice_map[name] ?? "alloy"}
													onValueChange={(v) => updateVoice(name, v)}
												>
													<SelectTrigger className="h-8 text-xs">
														<SelectValue />
													</SelectTrigger>
													<SelectContent>
														{OPENAI_VOICES.map((v) => (
															<SelectItem key={v} value={v}>
																{v}
															</SelectItem>
														))}
													</SelectContent>
												</Select>
											)}
										</div>
									</div>

									{/* Expanded: instruction textarea */}
									{isExpanded && (
										<div className="border-t border-border px-3 pb-3 pt-2 space-y-1.5">
											<Label className="text-[11px] text-muted-foreground">
												R&ouml;stinstruktion f&ouml;r {name}
											</Label>
											<Textarea
												placeholder={`Accent, ton, känsla, tempo...\nT.ex. "Speak with confidence and a slight Nordic accent. Sound enthusiastic about technology."`}
												value={langInstructions[name] ?? ""}
												onChange={(e) => updateLangInstruction(name, e.target.value)}
												rows={3}
												className="text-xs"
											/>
											<p className="text-[10px] text-muted-foreground leading-relaxed">
												Styr: accent, emotional range, intonation, impressions, speed, tone, whispering
											</p>
										</div>
									)}
								</div>
							);
						})}
					</div>
				</CardContent>
			</Card>

			{/* Instructions help */}
			<Card>
				<CardHeader>
					<CardTitle className="text-sm">Instruktionsguide</CardTitle>
				</CardHeader>
				<CardContent>
					<pre className="whitespace-pre-wrap text-xs text-muted-foreground leading-relaxed">
						{INSTRUCTION_HINT}
					</pre>
				</CardContent>
			</Card>

			{/* Save */}
			<div className="flex items-center gap-3">
				<Button onClick={handleSave} disabled={isSaving}>
					{isSaving ? (
						<Loader2 className="mr-2 h-4 w-4 animate-spin" />
					) : (
						<Save className="mr-2 h-4 w-4" />
					)}
					Spara inst&auml;llningar
				</Button>
				{saved && (
					<Badge variant="outline" className="border-green-500/30 text-green-500">
						<CheckCircle2 className="mr-1 h-3 w-3" />
						Sparat
					</Badge>
				)}
				{error && (
					<Badge variant="outline" className="border-red-500/30 text-red-500">
						{error}
					</Badge>
				)}
			</div>

			{/* Usage instructions */}
			<Card>
				<CardHeader>
					<CardTitle>Anv&auml;ndning</CardTitle>
				</CardHeader>
				<CardContent className="space-y-2 text-sm text-muted-foreground">
					<p>
						<code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">/debatt</code>{" "}
						&mdash; Textdebatt (8 AI-modeller, 4 rundor, r&ouml;stning)
					</p>
					<p>
						<code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">/dvoice</code>{" "}
						&mdash; R&ouml;stdebatt med live TTS (kr&auml;ver API-nyckel ovan)
					</p>
					<p>
						Exempel:{" "}
						<code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
							/dvoice B&ouml;r AI regleras?
						</code>
					</p>
				</CardContent>
			</Card>
		</div>
	);
}
