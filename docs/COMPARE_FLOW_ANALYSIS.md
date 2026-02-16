# Compare Flow Analysis: How `/compare` Uses `compare.analysis.system` Prompt

## Overview

This document provides a comprehensive analysis of how the `/compare` command works in OneSeek and how it uses the `compare.analysis.system` prompt for synthesizing answers from multiple LLMs.

## Architecture

### Two Implementations

1. **Legacy Implementation** (`stream_compare_chat.py`)
   - DEPRECATED monolithic implementation
   - Runs outside supervisor entirely
   - Does its own async model calls, Tavily, synthesis
   - SSE streaming implementation
   - Non-deterministic LLM-based tool calling

2. **New Implementation** (supervisor + LangGraph)
   - Runs within supervisor as deterministic subgraph
   - Guarantees ALL external models called in parallel
   - Proper AIMessage/ToolMessage emission for frontend
   - Linear execution: fan_out → collect → tavily → synthesizer → END

## Prompt Resolution Flow

### 1. Prompt Registration

**File:** `surfsense_backend/app/agents/new_chat/prompt_registry.py` (lines 295-298)

```python
PromptDefinition(
    key="compare.analysis.system",
    label="Compare analysis prompt",
    description="System prompt for compare synthesis step.",
    default_prompt=DEFAULT_COMPARE_ANALYSIS_PROMPT,
)
```

The prompt is registered in the global `PROMPT_DEFINITIONS` list, making it:
- Available in admin UI at `/admin/prompts`
- Customizable by administrators
- Overridable via `global_agent_prompt` database table

### 2. Prompt Loading at Runtime

**File:** `surfsense_backend/app/tasks/chat/stream_compare_chat.py` (lines 573-578)

```python
prompt_overrides = await get_global_prompt_overrides(session)
analysis_system_prompt = resolve_prompt(
    prompt_overrides,
    "compare.analysis.system",  # ← Key for lookup
    DEFAULT_ANALYSIS_SYSTEM_PROMPT,  # ← Fallback default
)
analysis_system_prompt = append_datetime_context(analysis_system_prompt)
```

**Resolution Logic:**
1. Query `global_agent_prompt` table for overrides
2. If override exists for `compare.analysis.system`, use it
3. Otherwise, fall back to `DEFAULT_COMPARE_ANALYSIS_PROMPT`
4. Append current datetime context to prompt

### 3. Default Prompt Content

**File:** `surfsense_backend/app/agents/new_chat/compare_prompts.py` (lines 6-56)

The `DEFAULT_COMPARE_ANALYSIS_PROMPT` instructs the synthesis model to:

**Core Tasks:**
1. **Evaluate correctness:** Cross-check facts between all sources
2. **Resolve conflicts:** Prioritize Tavily for facts, then freshness, then model consensus
3. **Fill gaps:** Use general knowledge when needed (but be transparent)
4. **Create optimized answer:** Write coherent, correct, well-structured response

**Response Guidelines:**
- Respond in user's language
- Keep main answer short, factual, clear, engaging
- If uncertain: say so and explain why
- Priority: Tavily > freshness > model consensus > internal knowledge

**Citation Format:**
- Inline citations: `[citation:chunk_id]`
- Mention model names in text (e.g., "According to Model X...")
- No numbered brackets like [1]
- No separate reference list

**Follow-up Questions:**
- Generate 2-4 targeted follow-up questions
- Hide in HTML comment: `<!-- possible_next_steps: ... -->`
- NOT visible in rendered text

## Compare Flow Execution

### Step 1: Detection

**File:** `surfsense_backend/app/tasks/chat/stream_compare_chat.py` (lines 82, 99-105)

```python
COMPARE_PREFIX = "/compare"

def is_compare_request(user_query: str) -> bool:
    """Check if the user query activates compare mode."""
    return user_query.strip().lower().startswith(COMPARE_PREFIX)

def extract_compare_query(user_query: str) -> str | None:
    """Extract the actual question from /compare command."""
    # Removes "/compare" prefix and returns the question
```

### Step 2: Parallel External Model Calls

**External Models Called:**
- Grok (xAI)
- DeepSeek
- Gemini (Google)
- ChatGPT (OpenAI)
- Claude (Anthropic)
- Perplexity
- Qwen (Alibaba)

**Configuration:**
```python
COMPARE_TIMEOUT_SECONDS = 90
COMPARE_RAW_ANSWER_CHARS = 12000
```

Each model receives the `compare.external.system` prompt (separate from analysis prompt).

### Step 3: Tavily Web Search

**Configuration:**
```python
MAX_TAVILY_RESULTS = 3
TAVILY_RESULT_CHUNK_CHARS = 320
TAVILY_RESULT_MAX_CHUNKS = 1
```

Fetches up to 3 web sources, truncates to 320 chars per chunk for context.

### Step 4: Synthesis with `compare.analysis.system`

**Input Structure:**
- User query
- 7 external model answers (labeled with MODEL_ANSWER + model name)
- Tavily web snippets (in `<sources>` with `<chunk id='...'>` tags)
- Optional Tavily summary

**Processing:**
1. Load `compare.analysis.system` prompt (with admin overrides)
2. Create synthesis messages: SystemMessage + HumanMessage with all inputs
3. Stream LLM response using local model (not external)
4. Parse and format citations

**Output:**
- Synthesized answer with inline citations
- Follow-up questions hidden in HTML comments
- Thinking steps shown in frontend

### Step 5: Response Streaming

Uses Vercel Streaming Service (SSE format) to stream:
- Routing step (status: completed)
- External model thinking steps (one per model)
- Tavily search step
- Synthesis step
- Final answer with citations

## Admin Customization

### How to Customize the Prompt

1. **Navigate to Admin UI:** `/admin/prompts`
2. **Find prompt:** "Compare analysis prompt" (key: `compare.analysis.system`)
3. **Click Edit**
4. **Modify content:** Change instructions, citation format, etc.
5. **Save:** Persists to `global_agent_prompt` table
6. **Effect:** Immediate - next `/compare` uses new prompt

### Database Storage

**Table:** `global_agent_prompt`
**Columns:**
- `key`: "compare.analysis.system"
- `prompt`: Custom prompt text
- `is_active`: Boolean
- `created_at`, `updated_at`: Timestamps

### Fallback Behavior

If custom prompt is:
- Empty/whitespace → Falls back to default
- Not found in DB → Falls back to default
- Marked inactive → Falls back to default

## Integration with Tool Lifecycle System

### Lifecycle Filtering in Compare Mode

**Production Use:**
- `respect_lifecycle=True` (default)
- Only LIVE tools are available
- Ensures production stability

**Eval/Testing Use:**
- `respect_lifecycle=False`
- All tools (including REVIEW) available
- Allows testing new tools before promotion

**Code Reference:** `surfsense_backend/app/agents/new_chat/tools/registry.py` (lines 490-507)

```python
if respect_lifecycle:
    try:
        live_tool_ids = await get_live_tool_ids(session)
        if live_tool_ids is not None:
            # Filter to only LIVE tools
            enabled_tool_set = enabled_tool_set.intersection(live_tool_ids)
    except Exception as e:
        logging.warning(f"Lifecycle check failed: {e}, loading all tools")
```

## Key Configuration Values

```python
# Prefixes and timeouts
COMPARE_PREFIX = "/compare"
COMPARE_TIMEOUT_SECONDS = 90

# Answer length limits
COMPARE_RAW_ANSWER_CHARS = 12000
COMPARE_SUMMARY_ANSWER_CHARS = 600
COMPARE_SUMMARY_FINAL_CHARS = 700

# Tavily configuration
MAX_TAVILY_RESULTS = 3
TAVILY_RESULT_CHUNK_CHARS = 320
TAVILY_RESULT_MAX_CHUNKS = 1
```

## Example Flow

### User Input
```
/compare What are the latest developments in quantum computing?
```

### System Processing

1. **Detection:** Recognizes `/compare` prefix
2. **Extract:** Query = "What are the latest developments in quantum computing?"
3. **Parallel Calls:**
   - Grok: "Quantum computing breakthrough with 1000 qubits..."
   - Claude: "Recent advances include error correction..."
   - ChatGPT: "IBM announced new quantum processor..."
   - (+ 4 more models)
4. **Tavily Search:**
   - Source 1: Nature article on quantum supremacy
   - Source 2: MIT Tech Review on error correction
   - Source 3: IBM press release
5. **Synthesis:** Uses `compare.analysis.system` prompt to:
   - Compare all 7 model answers
   - Cross-reference with Tavily sources
   - Resolve any conflicts
   - Generate coherent answer with citations
6. **Output:**
   ```
   Recent quantum computing developments include [citation:ibm-press]:
   
   1. **Error Correction Breakthrough**: According to Claude and 
      confirmed by [citation:mit-article], researchers achieved...
   
   2. **1000-Qubit Processor**: As Grok and ChatGPT note, IBM's new
      processor [citation:ibm-press] represents...
   
   <!-- possible_next_steps:
   - Would you like a detailed comparison of error correction approaches?
   - Should I analyze the implications for cryptography?
   -->
   ```

## Files Referenced

### Core Implementation
- `app/tasks/chat/stream_compare_chat.py` - Legacy compare flow
- `app/agents/new_chat/supervisor_agent.py` - New LangGraph compare subgraph
- `app/agents/new_chat/compare_executor.py` - Compare execution nodes

### Prompts
- `app/agents/new_chat/compare_prompts.py` - Default prompt definitions
- `app/agents/new_chat/prompt_registry.py` - Prompt registration

### Services
- `app/services/agent_prompt_service.py` - Prompt override loading
- `app/services/new_streaming_service.py` - SSE streaming

### Tools
- `app/agents/new_chat/tools/external_models.py` - External model specs
- `app/agents/new_chat/tools/registry.py` - Tool lifecycle filtering

## Summary

The `/compare` flow demonstrates sophisticated prompt engineering and multi-LLM orchestration:

1. **Detection:** Simple prefix matching (`/compare`)
2. **Parallelization:** Calls 7 external LLMs simultaneously
3. **Web Search:** Adds factual grounding with Tavily
4. **Synthesis:** Uses customizable `compare.analysis.system` prompt
5. **Streaming:** Real-time progress via SSE
6. **Customization:** Admin can modify synthesis behavior
7. **Lifecycle:** Respects tool gating in production

The `compare.analysis.system` prompt is the critical component that transforms multiple model outputs and web sources into a coherent, citation-backed answer.
