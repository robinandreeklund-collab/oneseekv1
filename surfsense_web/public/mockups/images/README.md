# Compare Mode Mockup Screenshots

This directory contains HTML files and screenshots that demonstrate the Progressive Disclosure Pattern for Compare Mode.

## 🎨 Production-Quality Screenshots

These screenshots match the actual application design system with proper styling, colors, and layout.

### 1. CompareSourcesBar Component (Production)
![CompareSourcesBar Production](https://github.com/user-attachments/assets/b8b8eb77-d99e-4b1f-a18f-150409d9fb00)

**File**: `screenshots/04-compare-sources-bar-production.png`

The collapsible summary bar showing all provider responses with:
- ✅ Provider avatars with real logos and status indicators (green checkmarks for success, red X for errors)
- ⏱️ Response time and token count for each provider
- 📊 Aggregate statistics footer (total tokens, CO₂ estimate, fastest model)
- 🎯 Clean, modern design matching the application's style system
- 🇸🇪 Swedish language labels ("Modellsvar", "Snabbast", etc.)

**Example data shown**:
- Claude: 1.8s, 1.2k tokens ✓
- GPT-4: 2.1s, 842 tokens ✓
- Gemini: 3.2s, 920 tokens ✓
- Perplexity: 1.4s, 650 tokens ✓
- DeepSeek: timeout ✗

### 2. CompareDetailSheet Component (Production)
![CompareDetailSheet Production](https://github.com/user-attachments/assets/da7f871a-f7b2-4689-b6a1-92dd89ec1041)

**File**: `screenshots/05-compare-detail-sheet-production.png`

The detailed side panel showing a single provider's full response:
- 🎨 Provider header with logo, name, and provider badge
- 📈 4-column stats grid with real metrics (Svarstid, Tokens, CO₂, Energi)
- 📝 Full markdown-rendered response with formatting
- 🔍 Collapsible metadata section with model details
- ⬅️➡️ Navigation controls with Previous/Next buttons and dot indicators
- 📱 Responsive: Sheet on desktop (right side), Drawer on mobile (bottom)

**Example**: Claude 3.5 Sonnet response with 1.8s latency, 1.2k tokens, detailed AI impact analysis

### 3. Composer with Compare Mode (Production)
![Composer Compare Production](https://github.com/user-attachments/assets/9e3ec64b-2e8e-4c82-973b-19f7a542da93)

**File**: `screenshots/06-composer-compare-production.png`

The message composer with compare mode activated:
- 🏷️ `/compare` badge prefix showing mode is active
- 💬 User's query displayed in composer field
- ℹ️ Helpful info banner explaining compare mode functionality
- 🎨 Clean integration with existing composer design
- 🇸🇪 Swedish UI text throughout

**Info message**: "Compare-läge aktiverat. Din fråga skickas till flera AI-modeller samtidigt (Claude, GPT-4, Gemini, Perplexity, DeepSeek). Du får sedan en sammanfattning av alla svar."

---

## 📦 Early Mockup Screenshots

These are the initial mockups created during development:

### CompareSourcesBar (Early)
![CompareSourcesBar](screenshots/01-compare-sources-bar.png)
Early mockup of CompareSourcesBar component.

### CompareDetailSheet (Early)
![CompareDetailSheet](screenshots/02-compare-detail-sheet.png)
Early mockup of CompareDetailSheet component.

### Full Mockup Layout (Early)
![Full Mockup](screenshots/03-full-mockup-light.png)
Early full-page mockup showing component integration.


## 🌐 Interactive HTML Files

### Production Mockups (Recommended)
These use the exact design system from the application (OKLCH colors, proper spacing):
- **production-compare-sources-bar.html** - CompareSourcesBar with real design system styling
- **production-compare-detail-sheet.html** - CompareDetailSheet with responsive layout
- **production-composer-compare.html** - Composer view with `/compare` prefix active

### CDN-Based Mockups (require internet)
- `screenshot-sources-bar-light.html` - CompareSourcesBar component with Tailwind CDN
- `screenshot-detail-sheet-light.html` - CompareDetailSheet component with Tailwind CDN

### Standalone Mockups (work offline)
- `screenshot-sources-bar-standalone.html` - Self-contained with inline CSS
- `screenshot-detail-sheet-standalone.html` - Self-contained with inline CSS

### Complete Mockup
- `../compare-mode-mockup.html` - Full page mockup showing both light and dark modes side-by-side

## 🎯 Design System

All production mockups use the actual application design system:

**Colors (OKLCH)**:
- Background: `oklch(1 0 0)` (white)
- Foreground: `oklch(0.145 0 0)` (near black)
- Muted: `oklch(0.97 0 0)` (light gray background)
- Muted Foreground: `oklch(0.556 0 0)` (medium gray text)
- Border: `oklch(0.922 0 0)` (subtle borders)
- Primary: `oklch(0.205 0 0)` (dark primary)
- Primary Accent: `oklch(0.488 0.243 264.376)` (blue/purple for compare badges)

**Border Radius**: `0.625rem` (10px base, scales with component)

**Typography**: 
- Font Family: Geist Sans (system font stack fallback)
- Base Size: 15px for body text
- Headings: 14px-18px with appropriate weights

**Spacing**: Consistent with Tailwind spacing scale (4px base unit)

## 📖 How to View

**HTML Mockups**: Open any HTML file directly in a browser, or run a local server:

```bash
# Navigate to the mockups directory
cd surfsense_web/public/mockups

# Start a simple HTTP server
python3 -m http.server 8000

# Open in browser:
# - Production mockups: http://localhost:8000/images/production-compare-sources-bar.html
# - Complete mockup: http://localhost:8000/compare-mode-mockup.html
```

**Screenshots**: View PNG files directly or use the GitHub asset URLs provided above.

## ✨ Components Demonstrated

### 1. CompareSourcesBar
- Collapsible header with "Modellsvar (X av Y)" and chevron icon
- Horizontal scrollable row of provider avatars
- Each avatar shows:
  - Provider logo (40×40 rounded circle)
  - Status dot (green=success, red=error, yellow=pending)
  - Provider name
  - Response time
  - Token count
- Aggregate statistics footer:
  - Total tokens across all providers
  - Estimated CO₂ emissions
  - Fastest model with latency
- CSS grid animation for smooth expand/collapse
- Staggered entrance animations using motion/react patterns

### 2. CompareDetailSheet
- **Desktop**: Sheet sliding from right side (480px width)
- **Mobile**: Drawer from bottom (85vh height)
- Provider header:
  - Logo (48×48)
  - Display name and subtitle
  - Close button
- 4-column stats grid:
  - Response Time (Svarstid)
  - Tokens
  - CO₂ emissions
  - Energy consumption (Wh)
- Full response content:
  - Markdown-rendered text
  - Proper formatting (headings, lists, bold)
  - Readable typography
- Metadata section (collapsible):
  - Model identifier
  - API base URL
  - Token breakdown
- Navigation footer:
  - Previous button with provider name
  - Dot indicators showing current position
  - Next button with provider name
  - Arrow key support

### 3. Composer with Compare Mode
- Input field with `/compare` badge prefix
- Visual indicator showing mode is active
- Info banner with helpful description
- Attachment button
- Send button
- Smooth integration with existing composer

## 🎨 Design Features

- **🇸🇪 Swedish UI**: All text in Swedish ("Modellsvar", "Svarstid", "Snabbast", etc.)
- **🌙 Dark Mode**: Full support with semantic colors (not yet shown in screenshots)
- **📱 Responsive**: Mobile (drawer) and desktop (sheet) layouts
- **♿ Accessible**: Keyboard navigation, semantic HTML, ARIA labels
- **✨ Animations**: Smooth transitions, CSS grid collapsing, staggered entrances
- **🎯 Progressive Disclosure**: Information revealed on demand, not overwhelming

## 📚 Implementation

See these files for detailed documentation:
- `COMPARE_MODE_IMPLEMENTATION.md` - Technical architecture and data flow
- `VISUAL_GUIDE.md` - Visual component guide with usage examples

## 🔄 Comparison: Before vs After

**Before** (Old Design):
- Each model response rendered as full `ModelCard` inline
- Massive vertical space consumption
- Disrupted chat flow
- Hard to compare models at a glance
- No aggregate statistics

**After** (New Progressive Disclosure):
- Single collapsible summary bar
- 5+ provider responses in compact horizontal row
- Aggregate stats visible immediately
- Individual responses on demand via detail sheet
- Clean chat flow maintained
- Easy model comparison

## 🚀 Key Benefits

1. **Reduced Visual Clutter**: Providers collapsed by default
2. **Better Comparison**: All providers visible at once in compact view
3. **On-Demand Details**: Full responses available with single click
4. **Responsive Design**: Works perfectly on mobile and desktop
5. **Keyboard Accessible**: Full keyboard navigation support
6. **Performance**: Lazy rendering of detail content
7. **Swedish UI**: Native Swedish language throughout
8. **Dark Mode Ready**: Semantic colors adapt to theme
