"use client";

import { AnimatePresence, motion } from "motion/react";
import {
	CheckCircle2Icon,
	ChevronDownIcon,
	ClockIcon,
	CrownIcon,
	LoaderCircleIcon,
	MessageSquareIcon,
	MicIcon,
	TrophyIcon,
	VoteIcon,
} from "lucide-react";
import {
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
} from "@/contracts/types/debate.types";
import {
	DEBATE_MODEL_COLORS,
	DEBATE_MODEL_DISPLAY,
	ROUND_LABELS,
} from "@/contracts/types/debate.types";

// ============================================================================
// Context — other tool UIs check this to hide when debate arena is active
// ============================================================================

export const DebateArenaActiveContext = createContext(false);

/** Context to pass live debate state from the SSE handler down to the arena. */
export const LiveDebateStateContext = createContext<DebateState | null>(null);

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

	// Only show participants that have a response (speaking or complete) for the
	// active round — cards appear progressively as SSE events arrive.
	// For historic rounds (user clicked a tab), show all that responded.
	const visibleParticipants = useMemo(() => {
		return debateState.participants.filter((p) => {
			const resp = p.responses[activeRound];
			return resp !== undefined;
		});
	}, [debateState.participants, activeRound]);

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
						<MessageSquareIcon className="h-5 w-5 text-primary" />
					</div>
					<div>
						<h2 className="text-base font-bold text-foreground">Debattarena</h2>
						<p className="text-xs text-muted-foreground">
							{debateState.participants.length} deltagare · {debateState.totalRounds} rundor
						</p>
					</div>
				</div>
				<div className="flex items-center gap-2">
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
						// Auto-expand: the currently speaking card is always expanded.
						// Completed cards auto-collapse when someone else starts speaking.
						const autoExpanded = isSpeaking || (
							roundResponse?.status === "complete" && currentSpeaker === null
							&& index === visibleParticipants.length - 1
						);

						return (
							<ParticipantCard
								key={`${participant.key}-r${activeRound}`}
								participant={participant}
								roundResponse={roundResponse}
								round={activeRound}
								index={index}
								autoExpanded={autoExpanded}
								isMostRecent={index === visibleParticipants.length - 1 && currentSpeaker === null}
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
}

const ParticipantCard: FC<ParticipantCardProps> = ({
	participant,
	roundResponse,
	round,
	index,
	autoExpanded,
	isMostRecent,
}) => {
	const [manualToggle, setManualToggle] = useState<boolean | null>(null);
	const prevAutoRef = useRef(autoExpanded);

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
					isSpeaking && "border-primary/50 shadow-lg shadow-primary/5",
				)}
			>
				<Collapsible open={isExpanded} onOpenChange={(open) => setManualToggle(open)}>
					<div className="flex items-center justify-between px-4 py-3">
						<div className="flex items-center gap-3">
							<div
								className="flex h-9 w-9 items-center justify-center rounded-lg text-sm font-bold text-white"
								style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
							>
								{initials}
							</div>
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
										{roundResponse.wordCount > 0 && (
											<span>{roundResponse.wordCount} ord</span>
										)}
										{roundResponse.latencyMs > 0 && (
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
							{isSpeaking && (
								<Badge variant="outline" className="animate-pulse border-primary/30 text-primary text-[10px]">
									<MicIcon className="mr-1 h-3 w-3" />
									Talar
								</Badge>
							)}
							{isDone && (
								<Badge variant="outline" className="border-green-500/30 text-green-500 text-[10px]">
									<CheckCircle2Icon className="mr-1 h-3 w-3" />
									Klar
								</Badge>
							)}
							{roundResponse?.text && (
								<CollapsibleTrigger asChild>
									<Button variant="ghost" size="sm" className="h-7 w-7 p-0">
										<ChevronDownIcon
											className={cn(
												"h-4 w-4 transition-transform",
												isExpanded && "rotate-180",
											)}
										/>
									</Button>
								</CollapsibleTrigger>
							)}
						</div>
					</div>

					{/* Preview text (collapsed view) — 2-line clamp */}
					{roundResponse?.text && !isExpanded && (
						<div className="px-4 pb-3">
							<p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
								{roundResponse.text}
							</p>
						</div>
					)}

					{/* Full text (expanded view) — shows full response with typing feel */}
					<CollapsibleContent>
						{roundResponse?.text && (
							<CardContent className="border-t border-border px-4 py-3">
								<p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
									{roundResponse.text}
								</p>
							</CardContent>
						)}
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

export default DebateArenaLayout;
