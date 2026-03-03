# Admin Tools Dashboard – Full Review (v3 five-panel layout)

## System intent
- Admin Tools is the control plane for routing: defines/edits tool metadata, tunes retrieval weights, audits correctness, runs evals, and promotes tools (review→live) used by the Hybrid Supervisor (intent → agent → tool).
- Correctness requirements: deterministic lifecycle gating, reproducible eval results, transparent scoring and auditability, safe rollout phases for live routing.

## Method
- Read frontends (`pipeline-explorer-panel.tsx`, `tool-catalog-panel.tsx`, `tuning-panel.tsx`, `eval-panel.tsx`, `deploy-panel.tsx`).
- Read backing routes under `/api/v1/admin/tool-settings/*` (debug-retrieval, eval, auto-loop, metadata audit, retrieval tuning, lifecycle).
- Cross-check lifecycle, retrieval, and eval flows with supervisor registry and lifecycle services.

## Scope
- Components reviewed: `pipeline-explorer-panel.tsx`, `tool-catalog-panel.tsx`, `tuning-panel.tsx`, `eval-panel.tsx`, `deploy-panel.tsx`.
- Backing APIs: `/api/v1/admin/tool-settings/*` including `debug-retrieval`, eval/auto-loop, metadata audit, retrieval tuning.

## Data/state dependencies to keep in mind
- `search_space_id` must be set for most admin actions; UI sometimes allows null and silently no-ops.
- Lifecycle gating (`respect_lifecycle=True`) filters tools to LIVE only; debug endpoints bypass this today.
- Retrieval tuning object drives thresholds, rerank candidates, live routing phase, and adaptive feedback flags.
- Metadata catalog uses optimistic locking via `expected_version_hash`; missing hash yields 409.
- Audit/eval share tool registry and metadata overrides; stale caches can hide new tools until `clear_tool_caches()` or reload.

## Findings
1) **Pipeline Explorer**
   - Backend `debug_retrieval` only performs tool retrieval; intent/agent are inferred heuristically and ignore routing phases, memory, and live rules. Confidence numbers are static. No error surfacing for empty index. Timing included.
   - UI shows blank until response; lacks loading state for steps and misses namespace context.
2) **Tool Catalog**
   - Domain grouping relies on category strings; duplicate category IDs (e.g., `marketplace_vehicles`) create non-unique React keys and collision warnings. Keys should combine category + index/namespace.
   - Inline edits bypass optimistic-lock protection if version hash missing; server rejects silently.
3) **Tuning**
   - Live-routing phases now exposed, but no guardrails explaining rollout sequence or when to enable `live_routing_enabled`; feedback DB toggle lacks status indicator of backend availability.
4) **Eval & Audit**
   - Category selection was previously absent; now present but still allows empty search space, causing silent no-ops.
   - Batch eval parallelism drives sequential polling; long runs can block UI. No backoff/jitter.
   - Auto-loop lacks surfacing of applied suggestions or deltas; users cannot inspect per-iteration tuning changes.
   - Metadata Audit returns collisions but UI only shows summary; errors from backend bubble as toasts without detail.
5) **Deploy/Ops**
   - Lifecycle metrics depend on eval sync; if lifecycle table not initialized, panels appear empty until first load triggers init. No explicit “respect_lifecycle” indicator.

## Risks
- Tool retrieval debug gives false confidence: intent/agent resolution paths are skipped, so production behavior can differ from explorer results.
- Duplicate keys can omit categories, hiding tools from admins.
- Auto-loop can churn without visibility into parameter changes; risk of silent regressions.

## Recommendations (minimal changes)
1) Pipeline Explorer
   - Extend `debug_retrieval` to run intent + agent resolvers with current live routing config; include route_hint, graph complexity, and agent thresholds.
   - Add loading placeholders per step and explicit “no tools indexed” message.
2) Tool Catalog
   - Make category chip keys stable (category_id + index). Show collision count from metadata audit results.
   - Require `expected_version_hash` on save; surface 409 conflicts with retry prompt.
3) Tuning
   - Add helper text for rollout phases (shadow → tool_gate → agent_auto → adaptive → intent_finetune).
   - Read-only badge showing feedback DB status (enabled/disabled) from tuning payload.
4) Eval & Audit
   - Block generate/eval/auto-loop if `search_space_id` missing; show inline error.
   - For batch eval, add capped polling with exponential backoff; persist batch job IDs to allow refresh recovery.
   - Surface iteration deltas (old vs new thresholds/weights) and applied suggestions list in auto-loop.
   - Render audit collisions table (predicted vs expected) and highlight top offenders.
5) Deploy/Ops
   - Display current lifecycle mode (`respect_lifecycle` on/off) and counts (LIVE vs REVIEW).
   - Prompt to run bulk-promote when review_count > 0 and lifecycle recently initialized.

## Backend endpoints worth validating regularly
- Retrieval: `debug-retrieval`, `tool-settings` (effective metadata + tuning), `tool-settings/metadata-catalog`.
- Eval: `tool-settings/eval-library/*`, `tool-settings/eval-history`, `tool-settings/eval`, `tool-settings/api-input-eval`.
- Auto-loop: `tool-settings/auto-loop` (start/status) plus `_sync_eval_to_lifecycle` side effects.
- Lifecycle: `/admin/tool-lifecycle/*` (list/promote/bulk-promote) and `respect_lifecycle` flags in registries.
- Audit: `tool-settings/metadata-audit` (run/suggestion/reset/stability locks).

## Acceptance checks (manual)
- Run `debug-retrieval` on a known weather query; verify intent/agent/tool align with live routing and namespace path matches tool_id.
- In Catalog, edit metadata with a stale version hash to confirm 409 is surfaced; ensure duplicate categories still render uniquely.
- Switch tuning phase from shadow→tool_gate and verify thresholds are applied in subsequent retrieval calls.
- Start eval with category + difficulty; ensure batch mode completes >1 category and displays success rates; auto-loop iteration deltas visible.
- Lifecycle tab shows LIVE/REVIEW counts and offers bulk promote when review_count > 0.

## Next Steps
- Prioritize fixing `debug_retrieval` to reflect true pipeline decisions.
- Patch UI keys for duplicated categories and show audit collisions.
- Add minimal visibility for auto-loop applied changes and lifecycle mode.
