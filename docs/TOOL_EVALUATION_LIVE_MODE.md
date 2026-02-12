# Tool Evaluation System - Live Pipeline Mode

## Overview

The Tool Evaluation System now includes a **Live Pipeline Mode** that runs queries through the complete production supervisor pipeline while using stub tools (no real API calls). This provides full visibility into how the system works in production.

## Two Evaluation Modes

### 1. Isolerad (Isolated) Mode
- **Purpose**: Fast component testing
- **Speed**: ~100-200ms
- **What it tests**:
  - Route classification (regex patterns)
  - Sub-route classification
  - Tool scoring and selection
- **What it shows**:
  - Selected tools
  - Scoring details (base, semantic, total)
  - Keywords matched
  - Match type
- **Use when**: Iterating on tool metadata, testing scoring logic

### 2. Live Pipeline Mode (NEW)
- **Purpose**: Full production pipeline execution
- **Speed**: ~2-5 seconds (includes LLM calls)
- **What it tests**:
  - Complete supervisor graph execution
  - Model reasoning and planning
  - Agent selection in context
  - Tool retrieval in context
  - Full execution flow
- **What it shows**:
  - Complete execution trace (all steps)
  - Model reasoning at each step
  - Tool calls with arguments
  - Tool results
  - Timestamps for each step
  - Final response
- **Use when**: Understanding production behavior, debugging complex flows, validating end-to-end

## Architecture

### Backend Flow
```
/admin/tool-eval/single-live endpoint
    ↓
evaluate_single_live(query, db, user_id)
    ↓
Build stub_tool_registry from _build_stub_tool_registry()
    ↓
create_supervisor_agent(stub_tool_registry=stubs)
    ↓
graph.astream_events(state, version="v1")
    ↓
Parse events:
  - on_chat_model_start → Model input
  - on_tool_start → Tool call begins
  - on_tool_end → Tool result  
  - on_chat_model_end → Model response
    ↓
Build LiveEvalResult with complete trace
    ↓
Return trace to frontend
```

### Stub Tool Integration Chain
```
create_supervisor_agent(stub_tool_registry)
    ↓
LazyWorkerPool(stub_tool_registry)
    ↓
create_bigtool_worker(stub_tool_registry)
    ↓
Uses stubs instead of build_global_tool_registry()
```

### Event Streaming Pattern
```python
async for event in graph.astream_events(state, version="v1"):
    event_type = event.get("event")
    
    if event_type == "on_chat_model_start":
        # Capture model input
        messages = event.get("data", {}).get("input", {}).get("messages", [])
        
    elif event_type == "on_tool_start":
        # Capture tool invocation
        tool_name = event.get("name")
        tool_input = event.get("data", {}).get("input")
        
    elif event_type == "on_tool_end":
        # Capture tool result
        tool_output = event.get("data", {}).get("output")
        
    elif event_type == "on_chat_model_end":
        # Capture model response
        output = event.get("data", {}).get("output")
```

## Frontend UI

### Mode Selection
Two-button toggle at top of Single Query Tester:
- **Isolerad (Snabb)** - Quick component testing
- **Live Pipeline (Full Flöde)** - Complete pipeline execution

### Live Results Display

**Summary Section:**
- Match type badge (exact/acceptable/partial/no_match)
- Tools used (badges)
- Agents used (badges)
- Execution time

**Final Response:**
- Formatted display of complete model response

**Execution Trace (Accordion):**
- One item per step
- Step number and type (model/tool)
- Tool name (if applicable)
- Timestamp
- Expandable to show:
  - Content/input
  - Tool arguments (JSON formatted)
  - Tool results
  - Model reasoning

## Usage Examples

### Testing Trafikverket Query

**Isolerad Mode:**
```
Query: "Finns det några trafikstörningar på E4?"

Results:
✅ Selected: trafikverket_trafikinfo_storningar
📊 Scoring:
   - Base score: 8.0
   - Semantic: 0.92  
   - Total: 8.92
🏷️ Keywords: störningar, trafikinfo
⏱️ 150ms
```

**Live Mode:**
```
Query: "Finns det några trafikstörningar på E4?"

Trace (8 steps):
1. 🤖 Model - Receives user query (0ms)
2. 🔧 Tool: dispatch_route - Classifies as "action" (450ms)
3. 🤖 Model - Plans to use action router (500ms)
4. 🔧 Tool: retrieve_agents - Gets ["trafik", "action"] (1200ms)
5. 🔧 Tool: smart_retrieve_tools - Scores and selects tools (1800ms)
6. 🔧 Tool: call_agent_trafik - Executes with stub (2500ms)
7. 🤖 Model - Processes results (3200ms)
8. 🤖 Model - Generates final response (4100ms)

Final Response:
"Jag hittade information om trafikstörningar på E4. [stub data]"

✅ Tools used: trafikverket_trafikinfo_storningar
⏱️ 4100ms
```

## Implementation Details

### Backend Files Modified

1. **supervisor_agent.py** (line 587)
   - Added `stub_tool_registry: dict[str, Any] | None = None` parameter
   - Passes to LazyWorkerPool

2. **lazy_worker_pool.py** (line 31)
   - Stores `_stub_tool_registry`
   - Passes to create_bigtool_worker

3. **bigtool_workers.py** (line 33)
   - Accepts `stub_tool_registry` parameter
   - Uses stubs when provided, otherwise calls build_global_tool_registry

4. **tool_eval_live.py** (new file, 300 lines)
   - `LiveEvalTrace` dataclass - Single trace step
   - `LiveEvalResult` dataclass - Complete evaluation result
   - `evaluate_single_live()` - Main evaluation function
   - Event parsing and trace building logic

5. **admin_tool_eval_routes.py** (+67 lines)
   - `LiveQueryRequest`/`Response` models
   - `POST /admin/tool-eval/single-live` endpoint
   - Admin auth required

### Frontend Files Modified

1. **admin-tool-eval.types.ts** (+47 lines)
   - `liveQueryRequestSchema`
   - `liveTraceStepSchema`
   - `liveQueryResponseSchema`
   - TypeScript types

2. **admin-tool-eval-api.service.ts** (+14 lines)
   - `testSingleQueryLive()` method

3. **tool-eval-page.tsx** (+231 lines, 13 modified)
   - `evalMode` state ("isolated" | "live")
   - `liveResult` state
   - `testLiveMutation` mutation
   - Mode toggle buttons
   - Live results display component
   - Trace visualization accordion

## Key Features

### Safety
✅ No real API calls - all tools use stubs
✅ Safe to test any query
✅ No side effects
✅ Deterministic stub responses

### Visibility
✅ Complete execution trace
✅ Model reasoning visible
✅ Tool arguments visible
✅ Tool results visible
✅ Timing information

### Production Fidelity
✅ Same supervisor graph
✅ Same routing logic
✅ Same agent selection
✅ Same tool retrieval
✅ Real LLM reasoning (with stubs)

## Troubleshooting

### Issue: Live mode shows error
**Solution**: Check backend logs. Most common issue is missing dependencies or stub tools not created properly.

### Issue: Trace shows no steps
**Solution**: Event streaming might be failing. Check that `astream_events` is working and events are being parsed correctly.

### Issue: Takes too long
**Solution**: Live mode includes real LLM calls which take 2-5 seconds. This is expected. Use Isolerad mode for faster iteration.

### Issue: Wrong tools selected
**Solution**: This reveals actual production behavior! Check:
1. Model reasoning - why did it choose that path?
2. Agent selection - which agents were selected?
3. Tool scoring - what scores did tools get?
4. Update prompts, tool metadata, or routing logic based on findings

## Future Enhancements

Potential improvements:
- [ ] Side-by-side comparison (isolated vs live)
- [ ] Save and replay traces
- [ ] Trace visualization timeline
- [ ] Export traces for analysis
- [ ] Batch live evaluation of test suites
- [ ] Performance profiling per step
- [ ] Tool call cost estimation
- [ ] A/B testing different prompts

## Summary

Live Pipeline Mode provides complete visibility into production behavior while maintaining safety through stub tools. Use it to:
- Understand how queries flow through the system
- Debug unexpected tool selections
- Validate prompt changes
- Train new team members on system architecture
- Demonstrate system capabilities

Combined with Isolerad mode, you have comprehensive testing coverage from isolated components to full integration.
