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
import {
	CheckCircle2,
	Loader2,
	Mic,
	Save,
	Volume2,
} from "lucide-react";
import {
	adminDebateApiService,
	type DebateVoiceSettings,
} from "@/lib/apis/admin-debate-api.service";

const OPENAI_VOICES = [
	"alloy",
	"echo",
	"fable",
	"nova",
	"onyx",
	"shimmer",
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

const TTS_MODELS = [
	{ value: "tts-1", label: "TTS-1 (Standard)" },
	{ value: "tts-1-hd", label: "TTS-1-HD (High Quality)" },
] as const;

export function DebateSettingsPage() {
	const [settings, setSettings] = useState<DebateVoiceSettings>({
		api_key: "",
		api_base: "https://api.openai.com/v1",
		model: "tts-1",
		speed: 1.0,
		voice_map: {
			Grok: "fable",
			Claude: "nova",
			ChatGPT: "echo",
			Gemini: "shimmer",
			DeepSeek: "alloy",
			Perplexity: "onyx",
			Qwen: "fable",
			OneSeek: "nova",
		},
	});

	const [isLoading, setIsLoading] = useState(true);
	const [isSaving, setIsSaving] = useState(false);
	const [saved, setSaved] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// Load settings on mount
	useEffect(() => {
		(async () => {
			try {
				const resp = await adminDebateApiService.getVoiceSettings();
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

	if (isLoading) {
		return (
			<div className="flex items-center justify-center p-12">
				<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold">Debatt</h1>
				<p className="text-muted-foreground mt-2">
					Konfigurera debattl&auml;ge och r&ouml;stdebatt (Live Voice Debate Mode)
				</p>
			</div>

			{/* TTS API Configuration */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Volume2 className="h-5 w-5" />
						TTS-konfiguration
					</CardTitle>
					<CardDescription>
						OpenAI TTS API-inst&auml;llningar f&ouml;r r&ouml;stdebatt (/dvoice)
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="grid gap-4 sm:grid-cols-2">
						<div className="space-y-2">
							<Label htmlFor="api-key">API-nyckel</Label>
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

					<div className="grid gap-4 sm:grid-cols-2">
						<div className="space-y-2">
							<Label htmlFor="tts-model">TTS-modell</Label>
							<Select
								value={settings.model}
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
						<div className="space-y-2">
							<Label>Hastighet: {settings.speed.toFixed(2)}x</Label>
							<Slider
								min={0.25}
								max={4.0}
								step={0.05}
								value={[settings.speed]}
								onValueChange={([v]) =>
									setSettings((prev) => ({ ...prev, speed: v }))
								}
							/>
						</div>
					</div>
				</CardContent>
			</Card>

			{/* Voice Map */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Mic className="h-5 w-5" />
						R&ouml;stkarta (DEBATE_VOICE_MAP)
					</CardTitle>
					<CardDescription>
						Tilldela en unik r&ouml;st till varje debattdeltagare
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
						{PARTICIPANTS.map((name) => (
							<div
								key={name}
								className="flex items-center gap-3 rounded-lg border border-border p-3"
							>
								<div className="min-w-0 flex-1">
									<div className="text-sm font-medium">{name}</div>
									<Select
										value={settings.voice_map[name] ?? "alloy"}
										onValueChange={(v) => updateVoice(name, v)}
									>
										<SelectTrigger className="mt-1 h-8 text-xs">
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
								</div>
							</div>
						))}
					</div>
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
