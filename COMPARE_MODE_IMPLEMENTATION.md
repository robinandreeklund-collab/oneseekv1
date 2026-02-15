# Compare Mode Progressive Disclosure Implementation

## Overview

This implementation introduces a **Progressive Disclosure Pattern** for the compare mode frontend, replacing the vertically-stacked `ModelCard` components with a cleaner, more efficient UI that:

1. Shows a collapsible summary bar with provider avatars
2. Opens individual provider responses in a side sheet/drawer on demand
3. Keeps the chat clean while preserving full access to all model responses

## Architecture

The implementation follows three existing patterns in the codebase:

1. **ThinkingSteps** (`thinking-steps.tsx`) – collapsible header with CSS grid animation
2. **TraceSheet** (`trace-sheet.tsx`) – resizable Sheet/Drawer for detailed views
3. **Source Detail Pattern** – modal overlay with markdown rendering

## Components Created

### 1. CompareSourcesBar (`components/tool-ui/compare-sources-bar.tsx`)

**Purpose**: Displays a collapsible summary of all compare providers after the synthesized answer.

**Features**:
- Collapsible header with "Modellsvar (X av Y)" label
- Horizontal scrollable row of clickable provider avatars
- Each avatar shows:
  - Model logo (10×10 rounded)
  - Status dot (green for success, red for error, yellow pulsing for pending)
  - Provider name
  - Latency (e.g., "1.8s")
  - Token count (e.g., "1.2k tok")
- Aggregate stats footer showing:
  - Total tokens across all providers
  - Total CO₂ estimate
  - Total energy consumption
  - Fastest model
  - Average latency
- CSS grid animation for smooth expand/collapse
- Motion/react animations with staggered avatar pop-in
- Streaming state with pulse animation for pending providers

**Key Implementation Details**:
```typescript
export interface CompareProvider {
  key: string;
  displayName: string;
  status: "success" | "error";
  answer?: string;
  error?: string;
  latencyMs?: number;
  tokens?: number;
  co2g?: number;
  energyWh?: number;
  isEstimated?: boolean;
  toolName?: string;
  model?: string;
  provider?: string;
  modelString?: string;
  apiBase?: string;
}
```

### 2. CompareDetailSheet (`components/tool-ui/compare-detail-sheet.tsx`)

**Purpose**: Shows full details of a selected provider in a side panel.

**Features**:
- Responsive design:
  - Desktop (≥768px): Sheet from right side, 480px width
  - Mobile (<768px): Drawer from bottom, 85vh height
- Provider header with logo, name, provider badge, and model name
- Stats grid (4-column) showing latency, tokens, CO₂, and energy
- Full response rendered with `MarkdownText` component
- Collapsible metadata section for model string and API base
- Bottom navigation with:
  - Previous/Next buttons
  - Dot indicators showing current position
  - Disabled state for first/last items
- Arrow key keyboard navigation (Left/Right keys)
- Escape key to close

**Key Implementation Details**:
- Uses `useMediaQuery("(max-width: 767px)")` for responsive switching
- Keyboard navigation via `useEffect` with event listeners
- Reuses existing UI components (Sheet, Drawer, ScrollArea, Badge, Button)

### 3. CompareContext (`components/assistant-ui/compare-context.tsx`)

**Purpose**: React contexts for passing compare data through the component tree.

**Features**:
- `CompareProvidersContext`: Maps message ID → array of CompareProvider data
- `CompareDetailContext`: Manages selected provider and sheet open state

## Integration Points

### 1. `new-chat-page.tsx` Changes

**State Added**:
```typescript
const [messageCompareProviders, setMessageCompareProviders] = useState<
  Map<string, CompareProvider[]>
>(new Map());
const [selectedCompareProviderKey, setSelectedCompareProviderKey] = useState<string | null>(null);
const [isCompareDetailSheetOpen, setIsCompareDetailSheetOpen] = useState(false);
```

**Logic Added**:
1. **Track compare tool calls**: Maintains a `compareToolCalls` Map during SSE streaming
2. **Build compare providers**: Extracts data from tool call results (status, latency, tokens, etc.)
3. **Estimate impact**: Calculates CO₂ and energy from token counts using standard multipliers
4. **Update state**: Updates `messageCompareProviders` when tool outputs arrive

**Context Wrappers**:
- Wrapped Thread component with `CompareProvidersContext.Provider`
- Wrapped Thread component with `CompareDetailContext.Provider`
- Rendered `CompareDetailSheet` as global overlay

### 2. `assistant-message.tsx` Changes

**Component Added**:
```typescript
const CompareProvidersPart: FC = () => {
  // Looks up compare providers for current message
  // Renders CompareSourcesBar if providers exist
  // Handles provider click to open detail sheet
}
```

**Integration**:
- `CompareProvidersPart` added after text content, before FollowUpSuggestions
- Uses `useContext` to access `CompareProvidersContext` and `CompareDetailContext`
- Checks if message is streaming to show appropriate state

## Data Flow

```
Backend SSE Stream
  ↓
new-chat-page.tsx (onNew handler)
  ↓ [tool-input-start event]
Track compare tool calls in compareToolCalls Map
  ↓ [tool-output-available event]
Build CompareProvider objects from tool results
  ↓
Update messageCompareProviders state
  ↓
CompareProvidersContext.Provider
  ↓
assistant-message.tsx (CompareProvidersPart)
  ↓
CompareSourcesBar (rendered after text content)
  ↓ [user clicks provider avatar]
CompareDetailSheet opens (via CompareDetailContext)
```

## Backward Compatibility

- Existing `compare-model.tsx` remains unchanged
- Individual model tool UIs (`call_claude`, `call_gpt`, etc.) still registered in TOOLS_WITH_UI
- Compare summary data event already captured by backend (line 1295 in old code)
- No backend changes required

## Visual Design

### Light Mode
```
┌─ ThinkingSteps ─────────────────────────────────────────┐
│  ▸ [Compare] Routing request ✓                           │
└──────────────────────────────────────────────────────────┘

  The synthesized answer rendered as normal markdown text...

┌─ CompareSourcesBar ──────────────────────────────────────┐
│  🔍 Modellsvar (4 av 5)                              ▸   │
│                                                           │
│  [Claude] [GPT]   [Gemini] [Perpl.]  [DeepSeek]         │
│  ● 1.8s   ● 2.1s  ● 3.2s   ● 1.4s   ✕ timeout          │
│  1.2k tok 842 tok 920 tok  650 tok                       │
│                                                           │
│  Σ 3.6k tokens · CO₂ ≈0.4g · ⚡ Snabbast: Perplexity    │
└───────────────────────────────────────────────────────────┘
```

### Dark Mode
Same layout with dark theme colors:
- Background: `bg-gray-800/50`
- Borders: `border-gray-700`
- Text: `text-gray-100` / `text-gray-400`

## HTML Mockup

A standalone HTML mockup is available at:
`surfsense_web/public/mockups/compare-mode-mockup.html`

This demonstrates both light and dark modes side-by-side, showing:
- Chat interface with collapsed ThinkingSteps
- Synthesized answer text
- Expanded CompareSourcesBar
- Simulated CompareDetailSheet

## Key Benefits

1. **Reduced Visual Clutter**: Providers collapsed by default, expanding on demand
2. **Better Comparison**: Side-by-side comparison enabled via detail sheet
3. **Responsive**: Works on mobile (drawer) and desktop (sheet)
4. **Accessible**: Keyboard navigation, focus management, semantic colors
5. **Progressive Enhancement**: Shows streaming state, graceful error handling
6. **Performance**: Lazy rendering, only active provider detail loaded

## Future Enhancements

Potential improvements not included in this PR:

1. Provider filtering/sorting in the bar
2. Diff view to compare responses side-by-side
3. Export all responses as JSON/CSV
4. Favoriting/bookmarking specific providers
5. Historical comparison tracking

## Testing Checklist

- [ ] Collapsible animation works smoothly
- [ ] Provider avatars display correctly with logos
- [ ] Status dots show correct colors
- [ ] Aggregate stats calculate correctly
- [ ] Detail sheet opens when clicking provider
- [ ] Keyboard navigation works (arrows, escape)
- [ ] Responsive behavior (desktop sheet, mobile drawer)
- [ ] Streaming state shows pulse animation
- [ ] Dark mode colors apply correctly
- [ ] Error states display properly
- [ ] Backward compatible with existing compare-model.tsx

## Files Modified/Created

**Created**:
1. `surfsense_web/components/tool-ui/compare-sources-bar.tsx` (290 lines)
2. `surfsense_web/components/tool-ui/compare-detail-sheet.tsx` (380 lines)
3. `surfsense_web/components/assistant-ui/compare-context.tsx` (22 lines)
4. `surfsense_web/public/mockups/compare-mode-mockup.html` (590 lines)

**Modified**:
1. `surfsense_web/app/dashboard/[search_space_id]/new-chat/new-chat-page.tsx` (~80 lines added)
2. `surfsense_web/components/assistant-ui/assistant-message.tsx` (~50 lines added)

**Total**: ~1,412 lines of new code, following existing patterns and conventions.
