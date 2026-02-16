# Hybrid Supervisor v2 - phased rollout and manual verification

This document describes how to roll out the hybrid supervisor in safe phases and
how to manually verify each phase before continuing.

## Runtime flags

The streaming entrypoint accepts runtime flags in `runtime_hitl`:

```json
{
  "runtime_hitl": {
    "enabled": true,
    "hybrid_mode": true,
    "speculative_enabled": false
  }
}
```

- `hybrid_mode=false` keeps legacy behavior.
- `hybrid_mode=true` enables adaptive routing and smart critic behavior.
- `speculative_enabled=true` should only be enabled when speculative nodes are shipped.

---

## Phase 1 - hybrid core (implemented)

### Scope
- Add `hybrid_mode` and `speculative_enabled` graph flags.
- Add extended hybrid state fields (`graph_complexity`, `targeted_missing_info`, etc).
- Add graph complexity classification in `resolve_intent`.
- Add simple-path shortcut: `resolve_intent -> tool_resolver`.
- Add smart critic with mechanical checks and fallback to current critic.
- Add `targeted_missing_info` handoff from critic to tool resolver.

### Manual tests
1. **Baseline unchanged**
   - Set `hybrid_mode=false`.
   - Run a known query flow that previously worked.
   - Verify same node progression and similar final response quality.

2. **Simple path shortcut**
   - Set `hybrid_mode=true`, `speculative_enabled=false`.
   - Ask a focused single-domain query (example: weather in one city).
   - Verify thinking/trace shows `resolve_intent` and then tool resolution/execution without planner expansion.

3. **Targeted retry path**
   - Use a query that often returns partial data (missing key fields).
   - Verify critic sets `needs_more` and tool resolver receives targeted missing info.

4. **Supervisor trivial fast finalize (follow-up case)**
   - In an existing non-smalltalk thread, send a short greeting follow-up.
   - Verify supervisor can finalize quickly without full plan/execution loop.

5. **HITL safety**
   - Enable HITL runtime flags and run the same simple query.
   - Verify planner/execution/synthesis gates still trigger correctly.

Pass criteria for Phase 1:
- No regressions with `hybrid_mode=false`.
- No loop increase or crash with `hybrid_mode=true`.
- `needs_more` retries are targeted (not broad re-plans by default).

---

## Phase 2 - execution router and robust execution

### Scope
- Add deterministic execution router (`inline`, `parallel`, `subagent`).
- Add timeout enforcement for worker execution paths.
- Allow controlled parallel fan-out in normal mode.

### Manual tests
1. **Inline strategy**
   - Single-agent query.
   - Verify strategy=`inline` and normal latency.

2. **Parallel strategy**
   - Multi-agent compare-like query (not `/compare` command).
   - Verify fan-out runs in parallel and returns merged result.

3. **Timeout handling**
   - Simulate a slow/hanging tool.
   - Verify timeout is enforced and graceful fallback is returned.

4. **Concurrency stability**
   - Run several requests in parallel.
   - Verify no deadlocks and bounded worker usage.

---

## Phase 3 - episodic memory + retrieval feedback (process memory first)

### Scope
- Add process-level episodic memory with TTL/LRU.
- Add process-level retrieval feedback boosts/penalties.
- Keep persistence out of scope initially.

### Manual tests
1. **Episodic hit**
   - Ask same query twice within TTL.
   - Verify second run avoids duplicate API/tool call.

2. **Episodic expiry**
   - Repeat after TTL.
   - Verify data refreshes.

3. **Feedback influence**
   - Run repeated success/failure patterns.
   - Verify retrieval ranking shifts in expected direction.

4. **Isolation**
   - Test different users/search spaces.
   - Verify memory/feedback are scoped and not leaked.

---

## Phase 4 - speculative branch + progressive synthesis

### Scope
- Add speculative branch and merge rules.
- Add progressive draft synthesis (`data-synthesis-draft` SSE event).

### Manual tests
1. **Speculative hit**
   - Query where planner confirms predicted tool.
   - Verify no duplicate call and lower latency.

2. **Speculative miss**
   - Query where planner rejects candidate.
   - Verify discard behavior and normal execution fallback.

3. **Draft streaming**
   - Multi-result response.
   - Verify `data-synthesis-draft` appears before final polished response.

4. **Backward compatibility**
   - Older frontend/client should still render final response even if draft events are ignored.

---

## Rollout recommendation

1. Enable `hybrid_mode` for internal users only.
2. Monitor latency, retries, and loop guard activations.
3. Expand to broader traffic when regression delta is acceptable.
4. Enable `speculative_enabled` last, with strict quotas and timeout monitoring.
