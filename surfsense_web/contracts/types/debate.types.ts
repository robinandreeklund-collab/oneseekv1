/**
 * TypeScript types for Debate Mode (Debattläge).
 *
 * These types map to the backend schemas in `app/schemas/debate.py`
 * and are used by the DebateArena frontend components.
 */

// ─── Core Types ──────────────────────────────────────────────────────

export interface DebateParticipant {
	key: string;
	display: string;
	toolName: string;
	configId: number;
	isOneseek: boolean;
	/** Accumulated across all rounds */
	totalWordCount: number;
	/** Per-round responses */
	responses: Record<number, DebateParticipantResponse>;
	/** Round 4 vote (if completed) */
	vote?: DebateVote;
}

export interface DebateParticipantResponse {
	round: number;
	position: number;
	text: string;
	wordCount: number;
	latencyMs: number;
	status: "waiting" | "speaking" | "complete" | "error";
}

export interface DebateVote {
	voter: string;
	voterKey: string;
	votedFor: string;
	shortMotivation: string;
	threeBullets: string[];
}

export interface DebateRoundInfo {
	round: number;
	type: "introduction" | "argument" | "deepening" | "voting";
	order: string[];
	status: "pending" | "active" | "complete";
}

export interface DebateResults {
	winner: string;
	voteCounts: Record<string, number>;
	wordCounts: Record<string, number>;
	tiebreakerUsed: boolean;
	totalVotes: number;
	selfVotesFiltered: number;
}

// ─── State ───────────────────────────────────────────────────────────

export interface DebateState {
	topic: string;
	participants: DebateParticipant[];
	rounds: DebateRoundInfo[];
	currentRound: number;
	totalRounds: number;
	status:
		| "initializing"
		| "round_1"
		| "round_2"
		| "round_3"
		| "voting"
		| "results"
		| "synthesis"
		| "complete";
	results?: DebateResults;
	votes: DebateVote[];
}

// ─── SSE Event Payloads ──────────────────────────────────────────────

export interface DebateInitEvent {
	participants: string[];
	topic: string;
	total_rounds: number;
	timestamp: number;
}

export interface DebateRoundStartEvent {
	round: number;
	type: string;
	order: string[] | "parallel";
	timestamp: number;
}

export interface DebateParticipantStartEvent {
	model: string;
	model_key: string;
	round: number;
	position: number;
	timestamp: number;
}

export interface DebateParticipantEndEvent {
	model: string;
	model_key: string;
	round: number;
	position: number;
	word_count: number;
	latency_ms: number;
	response_preview: string;
	timestamp: number;
}

export interface DebateRoundEndEvent {
	round: number;
	participant_count: number;
	timestamp: number;
}

export interface DebateVoteResultEvent {
	voter: string;
	voted_for: string;
	motivation: string;
	bullets: string[];
	timestamp: number;
}

export interface DebateResultsEvent {
	winner: string;
	vote_counts: Record<string, number>;
	tiebreaker_used: boolean;
	word_counts: Record<string, number>;
	total_votes: number;
	timestamp: number;
}

// ─── Arena Analysis (from synthesis JSON block) ──────────────────────

export interface DebateArenaAnalysis {
	topic: string;
	rounds: number;
	participants: string[];
	winner: string;
	votes: Record<string, number>;
	consensus: string[];
	disagreements: {
		topic: string;
		sides: Record<string, string>;
		verdict: string;
	}[];
	key_arguments: {
		model: string;
		round: number;
		argument: string;
	}[];
	winner_rationale: string;
}

// ─── Display Helpers ─────────────────────────────────────────────────

export const DEBATE_TOOL_NAMES = new Set([
	"call_grok",
	"call_claude",
	"call_gpt",
	"call_gemini",
	"call_deepseek",
	"call_perplexity",
	"call_qwen",
	"call_oneseek",
]);

export const DEBATE_MODEL_DISPLAY: Record<string, string> = {
	call_grok: "Grok",
	call_claude: "Claude",
	call_gpt: "ChatGPT",
	call_gemini: "Gemini",
	call_deepseek: "DeepSeek",
	call_perplexity: "Perplexity",
	call_qwen: "Qwen",
	call_oneseek: "OneSeek",
};

export const DEBATE_MODEL_COLORS: Record<string, string> = {
	grok: "#1a1a2e",
	claude: "#d4a574",
	gpt: "#10a37f",
	gemini: "#4285f4",
	deepseek: "#0066ff",
	perplexity: "#20b2aa",
	qwen: "#7c3aed",
	oneseek: "#6366f1",
};

export const ROUND_LABELS: Record<number, string> = {
	1: "Introduktion",
	2: "Argument",
	3: "Fördjupning",
	4: "Röstning",
};
