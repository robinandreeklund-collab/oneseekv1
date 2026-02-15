# OneSeek Landing Page Mockup

This document describes the new landing page mockup for OneSeek (`app/(home)/page-mockup.tsx`). The design is purpose-built for OneSeek, showcasing all key features with a modern, premium aesthetic that sets it apart from generic landing pages.

## Design Philosophy

The new landing page embodies OneSeek's core promise: **"En fråga. Alla svar. Verifierat."** Every section demonstrates how OneSeek delivers comprehensive, verified answers by combining multiple AI models, Swedish data sources, and intelligent routing into a single, seamless experience.

The design uses:
- **Orange/amber** as the primary brand accent, representing intelligence and energy
- **Blue, purple, emerald, rose** as secondary colors for different features
- **Dark/light mode** support throughout with Tailwind's `dark:` classes
- **Scroll-triggered animations** to reveal content progressively
- **Swedish-first content** reflecting OneSeek's focus on Swedish users and data

---

## Section 1: Hero

**Purpose:** Make an immediate, powerful first impression that captures OneSeek's unique value proposition.

### Visual Elements

**Animated Typing Search Bar**
- Cycles through 5 real-world Swedish query examples, each with a colored route badge:
  - "Hur blir vädret i Stockholm imorgon?" → `WEATHER` (blue)
  - "Jämför alla AI-modeller om klimatpolitik" → `COMPARE` (purple)
  - "Visa SCB-statistik för befolkningsutveckling" → `STATISTICS` (emerald)
  - "Vad säger riksdagen om energipolitik?" → `RIKSDAGEN` (amber)
  - "Hitta information om Volvo AB" → `BOLAG` (rose)
- Typing animation (50ms per character) followed by deletion (30ms per character)
- Blinking orange cursor that pulses every 530ms
- White card with shadow and subtle glow effect underneath

**Gradient Background Orbs**
- Three large, blurred circular gradients (orange, blue, purple) positioned strategically
- Creates depth and visual interest without overwhelming the content
- Subtle 20% opacity for a soft, atmospheric effect

**Grid Pattern Overlay**
- Subtle 24px × 24px grid in semi-transparent gray
- Adds technical sophistication and structure to the background

**Floating Animated Particles**
- 20 small orange dots that float up and down continuously
- Random positioning, timing, and delays for organic movement
- Creates a sense of activity and intelligent processing

**Animated Counters**
- Three key metrics count up from 0 when scrolled into view:
  - "12+ AI-agenter"
  - "7 LLM-modeller"
  - "20+ API-integrationer"
- Smooth 30-frame animation over ~900ms
- Demonstrates OneSeek's comprehensive capabilities at a glance

**Section Badge**
- "Sveriges smartaste AI-plattform" with a green pulsing dot
- Establishes authority and Swedish focus immediately

**Main Heading**
- "En fråga." → "Alla svar." (with orange gradient) → "Verifierat."
- Uses Balancer for optimal line breaks
- Large, bold typography (4xl → 6xl → 7xl responsive)

**Demo Preview**
- Full-width screenshot of OneSeek in action (`/homepage/main_demo.webp`)
- Rounded corners with border for polish
- Blue glow effect underneath creates elevation
- Priority loading for fast initial render

### User Experience

The hero immediately communicates what OneSeek does through the typing animation—users see real examples of queries OneSeek can handle. The animated counters build credibility, while the demo preview shows the actual product. The overall effect is energetic, intelligent, and distinctly Swedish.

### Interactive Elements

- Typing animation cycles indefinitely
- Particles float continuously
- Counters animate once when scrolled into view
- Demo image loads with priority for performance

---

## Section 2: Compare Mode

**Purpose:** Showcase OneSeek's unique ability to query 7 AI models simultaneously and synthesize their responses into a single, verified answer.

### Visual Elements

**Section Badge**
- ⚡ lightning bolt icon emphasizing speed and power
- "Compare Mode" label

**Heading**
- "7 AI-modeller. Ett optimerat svar."
- Purple-to-blue gradient on "Ett optimerat svar"
- Emphasizes the convergence of multiple models into one answer

**7 AI Model Cards**
- Grid layout (responsive: 1 → 2 → 3 → 4 columns)
- Each card features:
  - **Colored icon box** with model's first letter (brand colors)
  - **Model name** and **provider**
  - **Animated loading bar** that fills from 0% to 100%
  - **Latency time** (e.g., "0.9s")
- Models included:
  1. Grok (xAI, black)
  2. Claude (Anthropic, amber)
  3. ChatGPT (OpenAI, emerald)
  4. Gemini (Google, blue)
  5. DeepSeek (DeepSeek, indigo)
  6. Perplexity (Perplexity, teal)
  7. Qwen (Alibaba, violet)
- Staggered animation delays (100ms apart) for sequential reveal
- Hover effects: scale up 5%, lift 5px

**Convergence Visualization**
- **Vertical gradient line** (purple → blue) flowing downward
- **OneSeek Synthesis pill badge** with lightning icon
- **Second gradient line** (blue → emerald) flowing downward
- **Verification text**: "Verifierat med Tavily • Citations [1-7] • Faktakontrollerat"

### User Experience

Users immediately understand that OneSeek doesn't just use one AI—it queries seven simultaneously. The loading bars create anticipation, while the convergence visualization shows how these diverse responses are synthesized into a single, verified answer. This is OneSeek's killer feature, and this section makes it crystal clear.

### Interactive Elements

- Cards fade in and scale up on scroll
- Loading bars animate from 0% to 100% when visible
- Hover effects on cards (scale + lift)

---

## Section 3: Debatt-läge (Riksdagen)

**Purpose:** Highlight OneSeek's unique access to Swedish parliamentary data, showcasing real-time propositions and motions.

### Visual Elements

**Section Badge**
- 🏛️ classical building emoji representing parliament
- "Debatt-läge" label

**Heading**
- "Riksdagsdata i realtid"
- Amber-to-orange gradient emphasizing the Swedish government theme

**Amber-Tinted Background**
- Gradient from amber-50 to orange-50 (light mode)
- Creates a warm, official atmosphere

**Proposition Card (Blue Theme)**
- 📄 document icon in blue background
- "Proposition 2024/25:142"
- "Förstärkt klimatlag" (example climate law)
- Skeleton content lines (simulating text)
- Voting badges: "JA: 215" (green) and "NEJ: 134" (red)
- Animates in from the left

**Motion Card (Rose Theme)**
- ✏️ edit icon in rose background
- "Motion 2024/25:3847"
- "Utökad skattereform" (example tax reform)
- Skeleton content lines
- Info badges: "Utskott: FiU" (committee) and "8 ledamöter" (members)
- Animates in from the right

**VS Badge**
- Centered between the cards
- Circular badge with amber border
- "VS" text in bold amber
- Spring animation: scales from 0 to 1 with bounce effect

### User Experience

This section demonstrates OneSeek's deep integration with Swedish government data—something no other AI platform offers. Users see actual parliamentary documents with real voting data, making it tangible and credible. The "VS" badge creates a natural comparison frame, showing how OneSeek can analyze debates from multiple perspectives.

### Interactive Elements

- Cards slide in from opposite directions on scroll
- VS badge scales up with spring animation
- Section fades in as a whole unit

---

## Section 4: Sverige-specifika Integrationer

**Purpose:** Demonstrate OneSeek's comprehensive coverage of Swedish data sources, from weather to statistics to government databases.

### Visual Elements

**Section Badge**
- 🇸🇪 Swedish flag emoji
- "Svenska Integrationer" label

**Heading**
- "Direkt kopplat till Sveriges datakällor"
- Blue-to-yellow gradient (Swedish flag colors!)

**12 Integration Logos (Grid Layout)**
- Responsive grid: 3 → 4 → 6 columns
- Each integration:
  - 64×64 rounded square container
  - Emoji icon (3xl size)
  - Name label below
- Integrations included:
  1. 📊 SCB (Statistics Sweden)
  2. 🌤️ SMHI (Swedish weather)
  3. 🚗 Trafikverket (Swedish Transport)
  4. 🏢 Bolagsverket (Companies)
  5. 🏛️ Riksdagen (Parliament)
  6. 📈 Kolada (Municipal data)
  7. 🔍 Tavily (Search/verification)
  8. 🗺️ Geoapify (Maps)
  9. 🤖 OpenAI (AI provider)
  10. 🧠 Anthropic (AI provider)
  11. ✨ Google AI (AI provider)
  12. ⚡ xAI (AI provider)
- Staggered animation (50ms apart)
- Hover effect: scale up 10%

**3 Category Cards**
- Full-width responsive grid (1 → 3 columns)
- Each card:
  - Gradient background (matching theme)
  - Large emoji (4xl)
  - Category title
- Categories:
  1. **Kunskap & Sökning** (blue-purple gradient, 🔍)
  2. **Statistik & Data** (emerald-teal gradient, 📊)
  3. **Realtid & Väder** (amber-orange gradient, ⚡)

### User Experience

This section reinforces OneSeek's Swedish focus and comprehensive data access. Users see familiar Swedish authorities (SCB, SMHI, Trafikverket) alongside powerful AI providers, understanding that OneSeek bridges local and global intelligence. The category cards organize these integrations conceptually, making the breadth of capabilities clear.

### Interactive Elements

- Logo containers fade in and scale up sequentially
- Hover effects scale logos
- Category cards slide up on scroll

---

## Section 5: LangGraph Pipeline

**Purpose:** Demystify how OneSeek works by visualizing the intelligent routing and processing pipeline powered by LangGraph.

### Visual Elements

**Section Badge**
- 🧠 brain emoji representing intelligence
- "LangGraph Pipeline" label

**Heading**
- "Så fungerar OneSeek"
- Orange-to-rose gradient

**Visual Pipeline Flow**
- 7 nodes in a horizontal flow (wraps on mobile):
  1. 💬 **Din fråga** (Your question)
  2. 🔀 **Intent Router** (Determines query type)
  3. 🎯 **Agent Resolver** (Selects appropriate agents)
  4. 📋 **Planner** (Creates execution plan)
  5. ⚙️ **Executor** (Runs the plan)
  6. 🔍 **Critic** (Validates results)
  7. ✅ **Svar** (Answer)
- Each node:
  - Orange-to-rose gradient background
  - Emoji icon (3xl)
  - Label below
- Arrow connectors between nodes (hidden on mobile)
- Staggered animation (100ms apart)

**12 Agent Badges Grid**
- Contained in bordered card with title: "12 Specialiserade Agenter"
- Grid layout: 2 → 3 → 4 → 6 columns
- Each badge:
  - Emoji icon (2xl)
  - Agent name (xs)
  - Light gray background with border
- Agents:
  1. 📚 Knowledge
  2. 🌤️ Weather
  3. 🚦 Trafik
  4. 📊 Statistics
  5. 🗺️ Kartor
  6. 🏢 Bolag
  7. 🏛️ Riksdagen
  8. 🌐 Browser
  9. 🎙️ Media
  10. 💻 Code
  11. ⚡ Action
  12. 🧬 Synthesis
- Staggered animation (50ms apart)

### User Experience

This section educates users about OneSeek's sophisticated architecture without being technical. The pipeline flow shows a clear journey from question to answer, while the agent grid demonstrates the breadth of specialized capabilities. Users understand that OneSeek isn't just a chatbot—it's an intelligent system that routes queries to specialized agents.

### Interactive Elements

- Pipeline nodes fade in and scale up sequentially
- Agent badges animate in one by one
- Full section animates on scroll into view

---

## Section 6: LLM Providers

**Purpose:** Build trust by showing the extensive range of AI providers OneSeek supports, demonstrating flexibility and cutting-edge capabilities.

### Visual Elements

**Section Badge**
- 🔌 plug emoji representing connectivity
- "LLM Providers" label

**Heading**
- "Stöd för 20+ LLM-providers"
- Violet-to-fuchsia gradient

**18 Provider Name Badges**
- Flex-wrap layout (centers and wraps naturally)
- Each badge:
  - Rounded pill shape
  - White background with border
  - Hover: violet border and violet background tint
- Providers:
  1. OpenAI
  2. Anthropic
  3. Google
  4. xAI
  5. DeepSeek
  6. Perplexity
  7. Qwen
  8. OpenRouter
  9. Groq
  10. Together
  11. Azure
  12. Mistral
  13. Cohere
  14. Fireworks
  15. Cerebras
  16. DeepInfra
  17. Replicate
  18. Ollama
- Staggered animation (30ms apart)
- Hover effects: scale up 10%, lift 2px

### User Experience

This section demonstrates OneSeek's vendor-agnostic approach and future-proof architecture. Users see both major providers (OpenAI, Anthropic, Google) and emerging ones (DeepSeek, Cerebras, Qwen), understanding that OneSeek gives them access to the entire AI ecosystem, not just one company's models.

### Interactive Elements

- Badges fade in and scale up sequentially
- Hover effects: scale, lift, border/background color change

---

## Section 7: CTA (Call to Action)

**Purpose:** Convert visitors into users with a clear, compelling call to action in a premium, dark environment.

### Visual Elements

**Dark Gradient Background**
- Gradient from gray-900 to pure black
- Creates premium, focused atmosphere

**Background Orbs**
- Orange and blue blurred circles
- Positioned for visual interest
- Lower opacity than hero (20%)

**OneSeek Logo**
- Inverted for dark background (using Logo component with dark:invert)
- 64×64 size
- Centered above heading

**Heading**
- "Redo att söka smartare?"
- Orange gradient on "söka smartare"

**Subheading**
- "Upplev Sveriges mest avancerade AI-sökplattform. Få verifierade svar från 7 LLM-modeller och 20+ datakällor."
- Light gray (300) for readability on dark background

**Two Buttons**
- **Primary button**: "Kom igång nu"
  - White background, dark text
  - Links to `/dashboard/public/new-chat`
  - Solid, high-contrast for primary action
- **Secondary button**: "Kontakta oss"
  - White border, white text
  - Links to `/contact`
  - Outline style for secondary action
- Both buttons:
  - Rounded-full shape (pill)
  - Hover: scale up 5%, lift 2px
  - Tap: scale down 5%

### User Experience

The dark background creates a focused, premium environment that draws attention to the CTA. The orange gradient on "söka smartare" (search smarter) connects back to the hero's branding, while the two clear buttons give users an obvious next step. The copy reinforces OneSeek's value proposition one final time.

### Interactive Elements

- Buttons scale and lift on hover
- Buttons scale down on tap/click
- Section is always visible (no scroll animation)

---

## Technical Details

### Dependencies Used

All dependencies are existing in the project:
- `motion/react` (Framer Motion) - All animations
- `next/image` - Optimized demo image loading
- `next/link` - Navigation to dashboard and contact
- `react-wrap-balancer` - Optimal heading line breaks
- `@/components/Logo` - OneSeek logo in CTA
- `@/lib/utils` - `cn()` utility for class merging

No new dependencies added.

### Animation Approach

**Scroll-Triggered Animations**
- Uses `useInView` hook from `motion/react`
- Configuration: `{ once: true, margin: "-100px" }`
- Elements animate once when they come within 100px of viewport
- Prevents re-animation on scroll up (better performance)

**Animation Types**
1. **Fade + slide up**: Most sections (`opacity: 0, y: 50` → `opacity: 1, y: 0`)
2. **Scale animations**: Cards, badges, logos (`scale: 0.8` → `scale: 1`)
3. **Slide from sides**: Debatt-läge cards (`x: -50` or `x: 50` → `x: 0`)
4. **Spring animations**: VS badge in Debatt-läge (`type: "spring"`)
5. **Counter animations**: Hero counters use `setInterval` for smooth counting
6. **Typing animation**: State-based cycling through queries

**Staggered Delays**
- Model cards: 100ms apart
- Integration logos: 50ms apart
- Pipeline nodes: 100ms apart
- Agent badges: 50ms apart
- Provider badges: 30ms apart

### Responsive Design

**Mobile-First Approach**
- Base styles for mobile (320px+)
- `sm:` breakpoint for small tablets (640px+)
- `md:` breakpoint for tablets (768px+)
- `lg:` breakpoint for desktops (1024px+)
- `xl:` breakpoint for large desktops (1280px+)

**Key Responsive Changes**
- Text sizes: `text-3xl` → `md:text-5xl` → `lg:text-7xl`
- Grid columns: `grid-cols-1` → `md:grid-cols-3` → `lg:grid-cols-6`
- Padding: `px-4` → `md:px-8`
- Pipeline arrows: `hidden` → `md:block`
- Debatt-läge layout: `flex-col` → `lg:flex-row`

### Dark/Light Mode Implementation

**Approach**
- Uses Tailwind's `dark:` variant throughout
- Relies on `next-themes` (already in project)
- No manual theme detection needed

**Key Patterns**
- Background: `bg-white` → `dark:bg-gray-950`
- Text: `text-gray-900` → `dark:text-white`
- Borders: `border-gray-200` → `dark:border-gray-700`
- Cards: `bg-white` → `dark:bg-gray-800`
- Logo: Inverts in dark mode using `dark:invert` class

**Gradients**
- Gradient backgrounds work in both modes
- Adjusted opacity for dark mode (e.g., `from-amber-50` → `dark:from-amber-950/20`)

### How to Preview the Mockup

1. **Development Server**
   ```bash
   cd surfsense_web
   npm run dev
   ```

2. **Navigate to Mockup**
   - Open browser to `http://localhost:3000/(home)/page-mockup` or directly access the route
   - Note: This is a separate page from the current landing page at `http://localhost:3000/`

3. **Test Dark Mode**
   - Use your system theme toggle, or
   - Open browser dev tools and toggle the theme using the site's theme switcher (if available in layout)

4. **Test Responsive Design**
   - Open browser dev tools (F12)
   - Toggle device toolbar (Ctrl+Shift+M)
   - Test at different breakpoints:
     - Mobile: 375px
     - Tablet: 768px
     - Desktop: 1280px
     - Large Desktop: 1920px

5. **Test Animations**
   - Scroll slowly through each section
   - Hover over interactive elements (cards, buttons, badges)
   - Watch typing animation cycle through queries
   - Observe counter animations in hero

### Performance Notes

- Demo image uses `priority` prop for LCP optimization
- All animations use `once: true` to prevent re-rendering
- Scroll animations use `-100px` margin for earlier trigger
- Emoji icons reduce need for image assets
- No external API calls or data fetching

---

## Future Enhancements (Not in Current Mockup)

Potential additions for future iterations:
1. **Live data**: Connect to actual OneSeek API for real metrics
2. **Interactive demo**: Embed a working search box
3. **Video**: Replace demo image with screen recording
4. **Testimonials**: Add user quotes/reviews
5. **Analytics**: Track scroll depth and CTA clicks
6. **A/B testing**: Test different headlines and CTAs
7. **Internationalization**: Support English version
8. **Accessibility**: Enhanced keyboard navigation and screen reader support

---

## Maintenance

- **Content updates**: Search for section headings in code to locate and update text
- **Color updates**: Gradients are defined inline using Tailwind classes
- **Animation timing**: Adjust `duration` and `delay` props in motion components
- **New integrations**: Add to `integrations` array in IntegrationsSection
- **New providers**: Add to `providers` array in LLMProvidersSection

---

## Questions & Support

For questions about this mockup or suggestions for improvements, please contact the development team or open an issue in the repository.
