"use client";

import { AnimatePresence, motion } from "motion/react";
import {
	CheckCircle2Icon,
	ChevronDownIcon,
	ClockIcon,
	CrownIcon,
	DownloadIcon,
	LoaderCircleIcon,
	MessageSquareIcon,
	MicIcon,
	PauseIcon,
	PlayIcon,
	TrophyIcon,
	Volume2Icon,
	VolumeXIcon,
	VoteIcon,
} from "lucide-react";
import React, {
	type FC,
	createContext,
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type {
	DebateArenaAnalysis,
	DebateParticipant,
	DebateResults,
	DebateRoundInfo,
	DebateState,
	DebateVote,
	DebateVoiceState,
} from "@/contracts/types/debate.types";
import {
	DEBATE_MODEL_COLORS,
	DEBATE_MODEL_DISPLAY,
	ROUND_LABELS,
} from "@/contracts/types/debate.types";
import { Slider } from "@/components/ui/slider";
import { useSmoothTyping } from "@/hooks/use-smooth-typing";

// ============================================================================
// Context — other tool UIs check this to hide when debate arena is active
// ============================================================================

export const DebateArenaActiveContext = createContext(false);

/** Context to pass live debate state from the SSE handler down to the arena. */
export const LiveDebateStateContext = createContext<DebateState | null>(null);

/** Context to pass voice audio controls down to the arena. */
export const DebateVoiceContext = createContext<{
	voiceState: DebateVoiceState;
	togglePlayPause: () => void;
	setVolume: (v: number) => void;
	exportAudioBlob: () => Blob | null;
	resumeAudioContext: () => Promise<void>;
	lastError: string | null;
} | null>(null);

// ============================================================================
// Helper functions
// ============================================================================

function getModelColor(key: string): string {
	return DEBATE_MODEL_COLORS[key] ?? "#6366f1";
}

function getModelInitials(display: string): string {
	if (display === "OneSeek") return "OS";
	if (display === "ChatGPT") return "GP";
	if (display === "DeepSeek") return "DS";
	return display.slice(0, 2);
}

function getRoundTypeLabel(round: number): string {
	return ROUND_LABELS[round] ?? `Runda ${round}`;
}

/** Model logos from /public/model-logos/ — keys match backend spec.key */
const MODEL_LOGOS: Record<string, string> = {
	grok: "/model-logos/grok.png",
	claude: "/model-logos/claude.png",
	gpt: "/model-logos/chatgpt.png",
	gemini: "/model-logos/gemini.png",
	deepseek: "/model-logos/deepseek.png",
	perplexity: "/model-logos/perplexity.png",
	qwen: "/model-logos/qwen.png",
};

// ============================================================================
// Main Component
// ============================================================================

interface DebateArenaLayoutProps {
	debateState: DebateState;
	analysis?: DebateArenaAnalysis | null;
}

export const DebateArenaLayout: FC<DebateArenaLayoutProps> = ({
	debateState,
	analysis,
}) => {
	const [selectedRound, setSelectedRound] = useState<number | null>(null);
	const activeRound = selectedRound ?? debateState.currentRound;
	const voiceCtx = React.useContext(DebateVoiceContext);
	const isVoiceMode = debateState.voiceMode === true;

	const isComplete = debateState.status === "complete" || debateState.status === "synthesis";
	const isVoting = debateState.status === "voting";

	// Determine which participant is currently speaking in the active round
	const currentSpeaker = useMemo(() => {
		for (const p of debateState.participants) {
			if (p.responses[activeRound]?.status === "speaking") {
				return p.key;
			}
		}
		return null;
	}, [debateState.participants, activeRound]);

	// The participant currently being voiced (audio playing or chunks streaming)
	const voiceSpeaker = voiceCtx?.voiceState.currentSpeaker ?? null;

	// Only show participants that have a response for the active round.
	// In voice mode during live debate: show ONLY the current speaker so cards
	// appear one-at-a-time. Once the round finishes, show all completed cards.
	// In completed/voting state or non-voice mode: show all with responses.
	const visibleParticipants = useMemo(() => {
		return debateState.participants.filter((p) => {
			const resp = p.responses[activeRound];
			if (resp === undefined) return false;

			if (isVoiceMode && !isComplete && !isVoting) {
				// While someone is actively speaking, show only that participant
				if (currentSpeaker) {
					return p.key === currentSpeaker;
				}
				// Between speakers (no one "speaking"), show completed ones
				return resp.status === "complete";
			}

			return true;
		});
	}, [debateState.participants, activeRound, isVoiceMode, isComplete, isVoting, currentSpeaker]);

	return (
		<div className="mx-auto w-full max-w-4xl space-y-4 py-4">
			{/* Header */}
			<motion.div
				initial={{ opacity: 0, y: -10 }}
				animate={{ opacity: 1, y: 0 }}
				className="flex items-center justify-between rounded-xl border border-border bg-card/50 px-5 py-4 backdrop-blur-sm"
			>
				<div className="flex items-center gap-3">
					<div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
						{isVoiceMode ? (
							<MicIcon className="h-5 w-5 text-primary" />
						) : (
							<MessageSquareIcon className="h-5 w-5 text-primary" />
						)}
					</div>
					<div>
						<h2 className="text-base font-bold text-foreground">
							{isVoiceMode ? "Röstdebatt" : "Debattarena"}
						</h2>
						<p className="text-xs text-muted-foreground">
							{debateState.participants.length} deltagare · {debateState.totalRounds} rundor
							{isVoiceMode && " · Live Voice"}
						</p>
					</div>
				</div>
				<div className="flex items-center gap-2">
					{isVoiceMode && voiceCtx?.voiceState.playbackStatus === "playing" && (
						<Badge variant="outline" className="animate-pulse border-red-500/40 bg-red-500/5 text-red-500 text-[10px]">
							<span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-red-500" />
							LIVE
						</Badge>
					)}
					{isComplete ? (
						<Badge variant="outline" className="border-green-500/30 text-green-500">
							<CheckCircle2Icon className="mr-1 h-3 w-3" />
							Klar
						</Badge>
					) : isVoting ? (
						<Badge variant="outline" className="border-amber-500/30 text-amber-500">
							<VoteIcon className="mr-1 h-3 w-3" />
							Röstning
						</Badge>
					) : (
						<Badge variant="outline" className="animate-pulse border-primary/30 text-primary">
							<LoaderCircleIcon className="mr-1 h-3 w-3 animate-spin" />
							Runda {debateState.currentRound}
						</Badge>
					)}
				</div>
			</motion.div>

			{/* Voice Control Bar — only shown in voice mode */}
			{isVoiceMode && voiceCtx && (
				<VoiceControlBar voiceCtx={voiceCtx} isComplete={isComplete} />
			)}

			{/* Topic */}
			{debateState.topic && (
				<motion.div
					initial={{ opacity: 0 }}
					animate={{ opacity: 1 }}
					className="rounded-xl border border-border bg-card/30 px-5 py-3"
				>
					<p className="text-sm font-medium text-foreground">{debateState.topic}</p>
				</motion.div>
			)}

			{/* Round Tabs */}
			<div className="flex gap-1 rounded-xl border border-border bg-card/50 p-1">
				{[1, 2, 3, 4].map((round) => {
					const roundInfo = debateState.rounds.find((r) => r.round === round);
					const isActive = activeRound === round;
					const isDone = roundInfo?.status === "complete";

					return (
						<button
							key={round}
							onClick={() => setSelectedRound(round)}
							className={cn(
								"flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-xs font-medium transition-all",
								isActive
									? "bg-primary text-primary-foreground shadow-sm"
									: isDone
										? "text-green-500 hover:bg-accent"
										: "text-muted-foreground hover:bg-accent",
							)}
						>
							{isDone && !isActive && <CheckCircle2Icon className="h-3 w-3" />}
							{isActive && !isDone && round === debateState.currentRound && (
								<LoaderCircleIcon className="h-3 w-3 animate-spin" />
							)}
							<span>R{round} — {getRoundTypeLabel(round)}</span>
						</button>
					);
				})}
			</div>

			{/* Progress Bar */}
			<div className="h-1 overflow-hidden rounded-full bg-muted">
				<motion.div
					className="h-full bg-gradient-to-r from-primary to-cyan-500"
					initial={{ width: "0%" }}
					animate={{
						width: `${((debateState.currentRound - 1) / debateState.totalRounds) * 100}%`,
					}}
					transition={{ duration: 0.5 }}
				/>
			</div>

			{/* Participant Cards — shown progressively as they respond */}
			<div className="space-y-3">
				<AnimatePresence mode="popLayout">
					{visibleParticipants.map((participant, index) => {
						const roundResponse = participant.responses[activeRound];
						const isSpeaking = roundResponse?.status === "speaking";

						// In voice mode: only expand the card that is currently being voiced.
						// Completed-voice cards collapse. Text-generating cards show a "generating" state.
						const isBeingVoiced = isVoiceMode && voiceSpeaker === participant.display;
						const voiceTextDone = isVoiceMode && roundResponse?.status === "complete";

						const autoExpanded = isVoiceMode
							? (isBeingVoiced || (isSpeaking && !voiceSpeaker))
							: (isSpeaking || (
								roundResponse?.status === "complete" && currentSpeaker === null
								&& index === visibleParticipants.length - 1
							));

						return (
							<ParticipantCard
								key={`${participant.key}-r${activeRound}`}
								participant={participant}
								roundResponse={roundResponse}
								round={activeRound}
								index={index}
								autoExpanded={autoExpanded}
								isMostRecent={!isVoiceMode && index === visibleParticipants.length - 1 && currentSpeaker === null}
								isVoiceMode={isVoiceMode}
								isBeingVoiced={isBeingVoiced}
								voiceTextDone={voiceTextDone}
							/>
						);
					})}
				</AnimatePresence>
			</div>

			{/* Voting Results */}
			{(isVoting || isComplete) && debateState.votes.length > 0 && (
				<VotingSection votes={debateState.votes} results={debateState.results} />
			)}

			{/* Winner Banner */}
			{isComplete && debateState.results?.winner && (
				<WinnerBanner
					winner={debateState.results.winner}
					results={debateState.results}
					votes={debateState.votes}
				/>
			)}
		</div>
	);
};

// ============================================================================
// Participant Card
// ============================================================================

interface ParticipantCardProps {
	participant: DebateParticipant;
	roundResponse?: DebateParticipant["responses"][number];
	round: number;
	index: number;
	/** Whether this card should be auto-expanded (currently speaking). */
	autoExpanded: boolean;
	/** Whether this is the most recently completed card (last in list, no one speaking). */
	isMostRecent: boolean;
	/** Whether this card is in voice debate mode. */
	isVoiceMode?: boolean;
	/** Whether this participant's voice is currently playing. */
	isBeingVoiced?: boolean;
	/** Whether voice text reveal is complete for this participant. */
	voiceTextDone?: boolean;
}

const ParticipantCard: FC<ParticipantCardProps> = ({
	participant,
	roundResponse,
	round,
	index,
	autoExpanded,
	isMostRecent,
	isVoiceMode = false,
	isBeingVoiced = false,
	voiceTextDone = false,
}) => {
	const [manualToggle, setManualToggle] = useState<boolean | null>(null);
	const prevAutoRef = useRef(autoExpanded);
	const voiceCtx = React.useContext(DebateVoiceContext);

	// Reset manual override when auto-expanded state changes (new speaker starts)
	useEffect(() => {
		if (prevAutoRef.current !== autoExpanded) {
			setManualToggle(null);
			prevAutoRef.current = autoExpanded;
		}
	}, [autoExpanded]);

	const isExpanded = manualToggle ?? autoExpanded;

	const color = getModelColor(participant.key);
	const initials = getModelInitials(participant.display);
	const isSpeaking = roundResponse?.status === "speaking";
	const isDone = roundResponse?.status === "complete";
	const voiceActive = voiceCtx?.voiceState.currentSpeaker === participant.display
		&& voiceCtx?.voiceState.playbackStatus === "playing";

	// Text display — in voice mode, smooth character-by-character reveal.
	// Animation stays active even after status flips to "complete" so the
	// typing effect finishes naturally (the hook stops on its own).
	const fullText = roundResponse?.text ?? "";
	const delayPerWord = roundResponse?.delayPerWord;
	const hasTypingData = isVoiceMode && delayPerWord !== undefined && delayPerWord > 0 && fullText.length > 0;
	const displayText = useSmoothTyping(fullText, delayPerWord, hasTypingData);
	const isTextStreaming = hasTypingData && displayText.length < fullText.length;

	// In voice mode: expand cards that have text or are being voiced/animated
	const effectiveExpanded = isVoiceMode
		? (isBeingVoiced || isTextStreaming || (isSpeaking && fullText.length > 0) || (isDone && !voiceTextDone))
		: (manualToggle ?? autoExpanded);

	// Voice mode: generating text (before any chunks arrive)
	const isGeneratingText = isVoiceMode && isSpeaking && fullText.length === 0;

	return (
		<motion.div
			initial={{ opacity: 0, y: 16 }}
			animate={{ opacity: 1, y: 0 }}
			exit={{ opacity: 0, y: -8 }}
			transition={{ duration: 0.3, delay: index * 0.05 }}
			layout
		>
			<Card
				className={cn(
					"transition-all duration-300",
					!isVoiceMode && isSpeaking && "border-primary/50 shadow-lg shadow-primary/5",
					isBeingVoiced && "border-red-500/50 shadow-xl shadow-red-500/10 ring-2 ring-red-500/30",
					isVoiceMode && isTextStreaming && !isBeingVoiced && "border-primary/40 shadow-lg shadow-primary/5",
					isVoiceMode && voiceTextDone && !isBeingVoiced && "border-border opacity-80",
				)}
			>
				<Collapsible open={effectiveExpanded} onOpenChange={(open) => !isVoiceMode && setManualToggle(open)}>
					<div className="flex items-center justify-between px-4 py-3">
						<div className="flex items-center gap-3">
							{MODEL_LOGOS[participant.key] ? (
								<img
									src={MODEL_LOGOS[participant.key]}
									alt={participant.display}
									className={cn(
										"h-9 w-9 rounded-lg object-contain",
										isBeingVoiced && "ring-2 ring-red-500/50",
									)}
								/>
							) : (
								<div
									className={cn(
										"flex h-9 w-9 items-center justify-center rounded-lg text-sm font-bold text-white",
										isBeingVoiced && "ring-2 ring-red-500/50",
									)}
									style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
								>
									{initials}
								</div>
							)}
							<div>
								<div className="flex items-center gap-2">
									<span className="text-sm font-semibold">{participant.display}</span>
									{participant.isOneseek && (
										<Badge variant="outline" className="border-cyan-500/30 text-cyan-500 text-[10px]">
											Realtidsverktyg
										</Badge>
									)}
								</div>
								{roundResponse && (
									<div className="flex items-center gap-2 text-xs text-muted-foreground">
										<span>#{roundResponse.position}</span>
										{roundResponse.wordCount > 0 && !isVoiceMode && (
											<span>{roundResponse.wordCount} ord</span>
										)}
										{roundResponse.latencyMs > 0 && !isVoiceMode && (
											<span className="flex items-center gap-1">
												<ClockIcon className="h-3 w-3" />
												{(roundResponse.latencyMs / 1000).toFixed(1)}s
											</span>
										)}
									</div>
								)}
							</div>
						</div>
						<div className="flex items-center gap-2">
							{isGeneratingText && (
								<Badge variant="outline" className="animate-pulse border-amber-500/30 text-amber-500 text-[10px]">
									<LoaderCircleIcon className="mr-1 h-3 w-3 animate-spin" />
									Genererar...
								</Badge>
							)}
							{isBeingVoiced && (
								<Badge variant="outline" className="animate-pulse border-red-500/40 bg-red-500/5 text-red-500 text-[10px]">
									<span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-red-500" />
									LIVE
								</Badge>
							)}
							{!isVoiceMode && isSpeaking && (
								<Badge variant="outline" className="animate-pulse border-primary/30 text-primary text-[10px]">
									<MicIcon className="mr-1 h-3 w-3" />
									Talar
								</Badge>
							)}
							{isVoiceMode && voiceTextDone && (
								<Badge variant="outline" className="border-green-500/30 text-green-500 text-[10px]">
									<CheckCircle2Icon className="mr-1 h-3 w-3" />
									Klar
								</Badge>
							)}
							{!isVoiceMode && isDone && (
								<Badge variant="outline" className="border-green-500/30 text-green-500 text-[10px]">
									<CheckCircle2Icon className="mr-1 h-3 w-3" />
									Klar
								</Badge>
							)}
							{!isVoiceMode && roundResponse?.text && (
								<CollapsibleTrigger asChild>
									<Button variant="ghost" size="sm" className="h-7 w-7 p-0">
										<ChevronDownIcon
											className={cn(
												"h-4 w-4 transition-transform",
												effectiveExpanded && "rotate-180",
											)}
										/>
									</Button>
								</CollapsibleTrigger>
							)}
						</div>
					</div>

					{/* Preview text (collapsed view) — 2-line clamp (non-voice mode only) */}
					{!isVoiceMode && displayText && !effectiveExpanded && (
						<div className="px-4 pb-3">
							<p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
								{displayText}
							</p>
						</div>
					)}

					{/* Full text (expanded view) — progressive reveal during voice */}
					<CollapsibleContent>
						{displayText ? (
							<CardContent className="border-t border-border px-4 py-3">
								<p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
									{displayText}
									{isTextStreaming && <span className="animate-pulse text-primary text-base">▍</span>}
								</p>
							</CardContent>
						) : isGeneratingText ? (
							<CardContent className="border-t border-border px-4 py-3">
								<p className="text-xs text-muted-foreground italic">
									Hämtar svar...
								</p>
							</CardContent>
						) : null}
					</CollapsibleContent>
				</Collapsible>
			</Card>
		</motion.div>
	);
};

// ============================================================================
// Voting Section
// ============================================================================

interface VotingSectionProps {
	votes: DebateVote[];
	results?: DebateResults;
}

const VotingSection: FC<VotingSectionProps> = ({ votes, results }) => {
	return (
		<motion.div
			initial={{ opacity: 0, y: 10 }}
			animate={{ opacity: 1, y: 0 }}
			className="space-y-3"
		>
			<div className="flex items-center gap-2 text-sm font-semibold text-foreground">
				<VoteIcon className="h-4 w-4" />
				Röstresultat
			</div>

			{/* Vote count bars */}
			{results?.voteCounts && (
				<div className="space-y-2 rounded-xl border border-border bg-card/30 p-4">
					{Object.entries(results.voteCounts)
						.sort(([, a], [, b]) => b - a)
						.map(([model, count]) => {
							const maxVotes = Math.max(...Object.values(results.voteCounts));
							const isWinner = model === results.winner;
							return (
								<div key={model} className="flex items-center gap-3">
									<span className={cn("w-24 text-xs font-medium", isWinner && "text-amber-400")}>
										{isWinner && "👑 "}{model}
									</span>
									<div className="flex-1">
										<div className="h-2 overflow-hidden rounded-full bg-muted">
											<motion.div
												className={cn(
													"h-full rounded-full",
													isWinner
														? "bg-gradient-to-r from-amber-500 to-amber-400"
														: "bg-gradient-to-r from-primary to-cyan-500",
												)}
												initial={{ width: "0%" }}
												animate={{
													width: `${maxVotes > 0 ? (count / maxVotes) * 100 : 0}%`,
												}}
												transition={{ duration: 0.8, delay: 0.2 }}
											/>
										</div>
									</div>
									<span className="w-12 text-right text-xs font-bold tabular-nums">
										{count} röst{count !== 1 ? "er" : ""}
									</span>
								</div>
							);
						})}
				</div>
			)}

			{/* Individual votes */}
			<div className="grid gap-2 sm:grid-cols-2">
				{votes.map((vote) => (
					<Card key={vote.voter} className="bg-card/30">
						<CardContent className="px-3 py-2.5">
							<div className="mb-1.5 flex items-center justify-between text-xs">
								<span className="font-medium text-foreground">{vote.voter}</span>
								<span className="text-muted-foreground">→</span>
								<span className="font-medium text-primary">{vote.votedFor}</span>
							</div>
							<p className="text-[11px] italic text-muted-foreground">
								&ldquo;{vote.shortMotivation}&rdquo;
							</p>
						</CardContent>
					</Card>
				))}
			</div>
		</motion.div>
	);
};

// ============================================================================
// Winner Banner
// ============================================================================

interface WinnerBannerProps {
	winner: string;
	results: DebateResults;
	votes: DebateVote[];
}

const WinnerBanner: FC<WinnerBannerProps> = ({ winner, results, votes }) => {
	const winnerVotes = results.voteCounts[winner] ?? 0;
	const totalVotes = results.totalVotes;

	return (
		<motion.div
			initial={{ opacity: 0, scale: 0.95 }}
			animate={{ opacity: 1, scale: 1 }}
			className="rounded-xl border border-amber-500/20 bg-gradient-to-r from-amber-500/5 to-amber-500/[0.02] p-5"
		>
			<div className="flex items-center gap-4">
				<div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-500/10 text-3xl">
					👑
				</div>
				<div className="flex-1">
					<h3 className="text-lg font-bold text-amber-400">
						{winner} vann debatten!
					</h3>
					<p className="text-sm text-muted-foreground">
						{winnerVotes} av {totalVotes} röster
						{results.tiebreakerUsed && " (tiebreaker: ordräkning)"}
					</p>
				</div>
				<div className="text-center">
					<div className="text-3xl font-extrabold text-amber-400">
						{winnerVotes}/{totalVotes}
					</div>
					<div className="text-[10px] uppercase tracking-wider text-muted-foreground">
						röster
					</div>
				</div>
			</div>
		</motion.div>
	);
};

// ============================================================================
// Voice Control Bar
// ============================================================================

interface VoiceControlBarProps {
	voiceCtx: {
		voiceState: DebateVoiceState;
		togglePlayPause: () => void;
		setVolume: (v: number) => void;
		exportAudioBlob: () => Blob | null;
		resumeAudioContext: () => Promise<void>;
		lastError: string | null;
	};
	isComplete: boolean;
}

const VoiceControlBar: FC<VoiceControlBarProps> = ({ voiceCtx, isComplete }) => {
	const { voiceState, togglePlayPause, setVolume, exportAudioBlob, resumeAudioContext, lastError } = voiceCtx;
	const canvasRef = useRef<HTMLCanvasElement>(null);

	// Waveform visualization
	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas || !voiceState.waveformData) return;

		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		const w = canvas.width;
		const h = canvas.height;
		const data = voiceState.waveformData;
		const barCount = Math.min(data.length, 64);
		const barWidth = w / barCount;

		ctx.clearRect(0, 0, w, h);

		for (let i = 0; i < barCount; i++) {
			const val = data[i] / 255;
			const barHeight = val * h * 0.9;
			const x = i * barWidth;
			const y = (h - barHeight) / 2;

			const isPlaying = voiceState.playbackStatus === "playing";
			ctx.fillStyle = isPlaying
				? `rgba(239, 68, 68, ${0.4 + val * 0.6})`
				: `rgba(148, 163, 184, ${0.3 + val * 0.3})`;
			ctx.fillRect(x + 1, y, barWidth - 2, barHeight);
		}
	}, [voiceState.waveformData, voiceState.playbackStatus]);

	const handleDownload = useCallback(() => {
		const blob = exportAudioBlob();
		if (!blob) return;
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `debatt-${Date.now()}.wav`;
		a.click();
		URL.revokeObjectURL(url);
	}, [exportAudioBlob]);

	return (
		<motion.div
			initial={{ opacity: 0, height: 0 }}
			animate={{ opacity: 1, height: "auto" }}
			className="flex items-center gap-3 rounded-xl border border-border bg-card/50 px-4 py-3 backdrop-blur-sm"
		>
			{/* Play/Pause */}
			<Button
				variant="ghost"
				size="sm"
				className="h-8 w-8 p-0"
				onClick={togglePlayPause}
			>
				{voiceState.playbackStatus === "playing" ? (
					<PauseIcon className="h-4 w-4" />
				) : (
					<PlayIcon className="h-4 w-4" />
				)}
			</Button>

			{/* Speaker indicator */}
			<div className="flex min-w-0 flex-1 flex-col gap-1">
				<div className="flex items-center gap-2">
					{lastError ? (
						<span className="truncate text-xs font-medium text-red-400">
							{lastError}
						</span>
					) : voiceState.currentSpeaker ? (
						<span className="truncate text-xs font-medium text-foreground">
							{voiceState.currentSpeaker}
						</span>
					) : (
						<span className="text-xs text-muted-foreground">
							{voiceState.playbackStatus === "idle"
								? "Klicka ▶ för att aktivera ljud"
								: "Buffrar…"}
						</span>
					)}
					{voiceState.playbackStatus === "playing" && (
						<span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
					)}
				</div>
				{/* Waveform canvas */}
				<canvas
					ref={canvasRef}
					width={320}
					height={24}
					className="w-full rounded-sm"
				/>
			</div>

			{/* Volume */}
			<div className="flex items-center gap-2">
				<Button
					variant="ghost"
					size="sm"
					className="h-7 w-7 p-0"
					onClick={() => setVolume(voiceState.volume > 0 ? 0 : 0.85)}
				>
					{voiceState.volume > 0 ? (
						<Volume2Icon className="h-3.5 w-3.5" />
					) : (
						<VolumeXIcon className="h-3.5 w-3.5" />
					)}
				</Button>
				<Slider
					className="w-20"
					min={0}
					max={1}
					step={0.05}
					value={[voiceState.volume]}
					onValueChange={([v]) => setVolume(v)}
				/>
			</div>

			{/* Download (only after debate completes) */}
			{isComplete && (
				<Button
					variant="ghost"
					size="sm"
					className="h-8 w-8 p-0"
					onClick={handleDownload}
					title="Ladda ner debatt-ljud (WAV)"
				>
					<DownloadIcon className="h-4 w-4" />
				</Button>
			)}
		</motion.div>
	);
};

export default DebateArenaLayout;
