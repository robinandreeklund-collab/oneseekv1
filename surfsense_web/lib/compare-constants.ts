/**
 * Shared constants and utilities for compare mode (Spotlight Arena).
 *
 * Used by both spotlight-arena.tsx and compare-model.tsx to avoid
 * duplicated definitions (KQ-02, KQ-03, KQ-04).
 */

// ── Energy / CO2 constants ──────────────────────────────────────────
export const ENERGY_WH_PER_1K_TOKENS = 0.2;
export const CO2G_PER_1K_TOKENS = 0.1;

// ── Model logos ─────────────────────────────────────────────────────
export const MODEL_LOGOS: Record<string, { src: string; alt: string }> = {
	call_grok: { src: "/model-logos/grok.png", alt: "Grok" },
	call_gpt: { src: "/model-logos/chatgpt.png", alt: "ChatGPT" },
	call_claude: { src: "/model-logos/claude.png", alt: "Claude" },
	call_gemini: { src: "/model-logos/gemini.png", alt: "Gemini" },
	call_deepseek: { src: "/model-logos/deepseek.png", alt: "DeepSeek" },
	call_perplexity: { src: "/model-logos/perplexity.png", alt: "Perplexity" },
	call_qwen: { src: "/model-logos/qwen.png", alt: "Qwen" },
	call_oneseek: { src: "/model-logos/oneseek.png", alt: "OneSeek" },
};

// ── Leaked JSON field names (KQ-01: shared source of truth) ────────
// Backend (_LEAKED_JSON_FIELDS in compare_executor.py) mirrors this list.
// Keep both in sync when adding new field names.
export const LEAKED_JSON_FIELDS = [
	"search_queries", "search_results", "winner_answer", "winner_rationale",
	"reasoning", "thinking", "arena_analysis", "consensus", "disagreements",
	"unique_contributions", "reliability_notes", "score",
] as const;

// ── Formatting helpers ──────────────────────────────────────────────

export function formatLatency(ms: number | null | undefined): string {
	if (ms === null || ms === undefined || Number.isNaN(ms)) return "";
	if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
	return `${Math.round(ms)}ms`;
}

/**
 * Rough token estimate based on ~4 chars per token (English average).
 * Swedish text may be 3–5 chars/token; CJK ~1–2.  The result is always
 * labelled as an estimate in the UI (prefixed with "~").
 */
export function estimateTokensFromText(text: string): number {
	if (!text) return 0;
	return Math.max(1, Math.round(text.length / 4));
}
