# Agent Flow (Current Optimized Chain)

This document describes the current routed multi-agent flow and where tools live.

## 1) High-level system flow

```mermaid
flowchart TD
    U[User Query] --> R[Top-level Router]

    R -->|knowledge| K[Knowledge Agent (DeepAgent)]
    R -->|action| A[Action Agent (DeepAgent)]
    R -->|smalltalk| S[Smalltalk Agent]
    R -->|compare| C[Compare Pipeline]

    K --> KD[Knowledge Router]
    KD -->|docs| KDOCS[Docs Sub-Agent]
    KD -->|internal| KINT[Internal KB Sub-Agent]
    KD -->|external| KEXT[External Web Sub-Agent]

    A --> AR[Action Router]
    AR -->|web| AWEB[Web Sub-Agent]
    AR -->|media| AMEDIA[Media Sub-Agent]
    AR -->|travel| ATRAVEL[Travel Sub-Agent]
    AR -->|data| ADATA[Data Sub-Agent]

    C --> C1[External Models]
    C --> C2[Oneseek (Knowledge Sub-Agent)]
    C --> C3[Tavily]
    C --> C4[Synthesis LLM]
```

## 2) Tool placement (where each tool lives)

### Knowledge Agent (DeepAgent)
**Docs Sub-Agent**
- `search_surfsense_docs`

**Internal KB Sub-Agent**
- `search_knowledge_base`
- `save_memory`
- `recall_memory`

**External Web Sub-Agent**
- `search_knowledge_base` with `connectors_to_search=['TAVILY_API']` and `top_k=3`

---

### Action Agent (DeepAgent)
**Web Sub-Agent**
- `link_preview`
- `scrape_webpage`
- `display_image`

**Media Sub-Agent**
- `generate_podcast`
- `search_knowledge_base` (for source content)

**Travel Sub-Agent**
- `smhi_weather`
- `trafiklab_route`

**Data Sub-Agent**
- `libris_search`
- `jobad_links_search`

---

### Smalltalk Agent
No tools.

---

### Compare Pipeline
**External Models**
- Grok, Claude, GPT, Gemini, DeepSeek, Perplexity, Qwen

**Oneseek**
- Uses Knowledge Sub-Agent (docs or internal KB)

**Tavily**
- Max 3 results, Sweden bias (site:.se)
- LLM answer stored as a tool-output document

**Synthesis LLM**
- Builds final answer with citations

## 3) UI Step Labels (real-time)

All steps are labeled in the UI to show routing:
- `[Knowledge/Docs] ...`
- `[Knowledge/KB] ...`
- `[Knowledge/External] ...`
- `[Action/Web] ...`
- `[Action/Media] ...`
- `[Action/Travel] ...`
- `[Action/Data] ...`
- `[Smalltalk] ...`
- `[Compare] ...`
- `[Compare] Asking Oneseek · Knowledge/KB`
