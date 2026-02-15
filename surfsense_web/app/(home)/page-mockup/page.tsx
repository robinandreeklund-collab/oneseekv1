"use client";

import { motion, useInView } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";
import Balancer from "react-wrap-balancer";
import { cn } from "@/lib/utils";

// ==================== DESIGN TOKENS ====================
// Based on Pixel-Perfect Design System YAML

const MODEL_LOGOS: Record<string, string> = {
gpt: "/llm-logos/openai.svg",
claude: "/llm-logos/anthropic.svg",
gemini: "/llm-logos/google.svg",
grok: "/llm-logos/xai.svg",
deepseek: "/llm-logos/deepseek.svg",
perplexity: "/llm-logos/perplexity.svg",
qwen: "/llm-logos/qwen.svg",
};

// ==================== SECTION 1: HERO WITH COMPARE PREVIEW ====================

const HeroSection = () => {
const models = [
{ id: "gpt", name: "GPT", provider: "OpenAI", latency: "0.9s" },
{ id: "claude", name: "Claude", provider: "Anthropic", latency: "1.2s" },
{ id: "gemini", name: "Gemini", provider: "Google", latency: "1.1s" },
{ id: "deepseek", name: "DeepSeek", provider: "DeepSeek", latency: "1.4s" },
{ id: "perplexity", name: "Perplexity", provider: "Perplexity", latency: "1.6s" },
{ id: "qwen", name: "Qwen", provider: "Alibaba", latency: "1.5s" },
{ id: "grok", name: "Grok", provider: "xAI", latency: "1.3s" },
];

return (
<section className="py-24 md:py-40 px-4 md:px-8">
<div className="mx-auto max-w-7xl">
{/* Heading */}
<div className="mx-auto max-w-4xl text-center">
<h1 className="text-4xl md:text-7xl font-bold tracking-tight text-black dark:text-white leading-[1.1]">
<Balancer>
En fråga.{" "}
<span className="text-neutral-500">Alla AI-modeller.</span>{" "}
<span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-purple-600">
Jämför.
</span>
</Balancer>
</h1>

<p className="mt-6 text-lg md:text-xl text-neutral-500 dark:text-neutral-400 max-w-2xl mx-auto leading-relaxed">
Ställ en fråga och se hur 7+ AI-modeller svarar samtidigt. Med latency, token-användning och
verifierade källor.
</p>

<div className="mt-10 flex gap-4 justify-center">
<Link
href="/dashboard/public/new-chat"
className="h-12 px-8 rounded-xl bg-black dark:bg-white text-white dark:text-black text-sm font-semibold transition-transform hover:scale-105"
>
Börja söka
</Link>
<Link
href="#compare"
className="h-12 px-8 rounded-xl ring-1 ring-neutral-200 dark:ring-neutral-800 text-sm font-semibold transition-transform hover:scale-105"
>
Se demo
</Link>
</div>
</div>

{/* Compare Preview */}
<div className="mt-16 md:mt-24 mx-auto max-w-5xl">
<div className="rounded-2xl border border-neutral-200/60 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900/50 p-1.5">
<div className="rounded-xl bg-white dark:bg-neutral-950 p-6">
<p className="text-sm text-neutral-500 mb-4">Vad är Sveriges BNP 2025?</p>

{/* Model Grid */}
<div className="grid grid-cols-4 md:grid-cols-7 gap-3">
{models.map((model, index) => (
<motion.div
key={model.id}
initial={{ opacity: 0, scale: 0.9 }}
animate={{ opacity: 1, scale: 1 }}
transition={{ duration: 0.3, delay: index * 0.08 }}
className="flex flex-col items-center gap-2 px-3 py-2 rounded-lg bg-neutral-50 dark:bg-neutral-900 border border-neutral-100 dark:border-neutral-800"
>
<div className="size-6 rounded-md border border-border/60 bg-white flex items-center justify-center p-0.5">
<span className="text-xs font-bold">{model.name[0]}</span>
</div>
<span className="text-xs font-medium text-center">{model.name}</span>
<span className="text-[10px] text-emerald-600">{model.latency}</span>
</motion.div>
))}
</div>

{/* Sources Bar */}
<div className="mt-4 rounded-lg bg-neutral-50 dark:bg-neutral-900/50 border border-neutral-100 dark:border-neutral-800 px-4 py-3 flex items-center justify-between">
<span className="text-xs text-neutral-500">Modellsvar (7 av 7)</span>
<span className="text-xs text-neutral-500">Σ 12.4k tokens · ⚡ DeepSeek</span>
</div>
</div>
</div>
</div>
</div>
</section>
);
};

// ==================== SECTION 2: API MARQUEE ====================

const APIMarquee = () => {
const apis = [
"SCB",
"SMHI",
"Bolagsverket",
"Trafikverket",
"Riksdagen",
"Kolada",
"Tavily",
"Geoapify",
];

return (
<section className="py-16 md:py-24 bg-white dark:bg-neutral-950 border-y border-neutral-100 dark:border-neutral-800/50">
<p className="text-center text-sm tracking-widest uppercase text-neutral-400 font-medium mb-8" style={{ letterSpacing: '0.1em' }}>
Ansluten till Sveriges officiella datakällor
</p>

<div className="overflow-hidden relative">
<div className="flex gap-6 animate-marquee">
{[...apis, ...apis].map((api, index) => (
<div key={index} className="flex items-center gap-3 px-6 py-3 whitespace-nowrap">
<span className="text-sm text-neutral-400 font-medium">{api}</span>
</div>
))}
</div>
</div>

<style jsx>{`
@keyframes marquee {
0% {
transform: translateX(0);
}
100% {
transform: translateX(-50%);
}
}
.animate-marquee {
animation: marquee 30s linear infinite;
}
.animate-marquee:hover {
animation-play-state: paused;
}
`}</style>
</section>
);
};

// ==================== SECTION 3: COMPARE SHOWCASE ====================

const CompareShowcase = () => {
const models = [
{ id: "claude", name: "Claude", provider: "Anthropic", latency: "1.8s", tokens: "~2.1k" },
{ id: "gpt", name: "ChatGPT", provider: "OpenAI", latency: "0.9s", tokens: "~1.8k" },
{ id: "gemini", name: "Gemini", provider: "Google", latency: "1.1s", tokens: "~2.4k" },
{ id: "grok", name: "Grok", provider: "xAI", latency: "1.3s", tokens: "~1.9k" },
{ id: "deepseek", name: "DeepSeek", provider: "DeepSeek", latency: "1.4s", tokens: "~2.2k" },
{ id: "perplexity", name: "Perplexity", provider: "Perplexity", latency: "1.6s", tokens: "~2.0k" },
{ id: "qwen", name: "Qwen", provider: "Alibaba", latency: "1.5s", tokens: "~2.3k" },
];

return (
<section id="compare" className="py-24 md:py-32">
<div className="mx-auto max-w-7xl px-6 lg:px-8">
{/* Header */}
<div className="text-center mb-16">
<span className="text-sm font-semibold text-blue-600 uppercase tracking-wider">COMPARE MODE</span>
<h2 className="mt-2 text-3xl md:text-5xl font-bold tracking-tight text-black dark:text-white">
Jämför AI-modeller — side by side
</h2>
<p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400 max-w-2xl mx-auto">
Ställ en fråga och se hur 7+ modeller svarar, med latency, token-användning och CO₂-estimat
</p>
</div>

{/* Model Cards Grid */}
<div className="grid lg:grid-cols-7 gap-4 max-w-5xl mx-auto">
{models.map((model, index) => (
<div
key={model.id}
className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 group hover:shadow-lg hover:border-blue-200 dark:hover:border-blue-800 transition-all duration-300"
>
<div className="size-8 rounded-md mx-auto border border-border/60 bg-white flex items-center justify-center p-1">
<span className="text-xs font-bold">{model.name[0]}</span>
</div>

<h4 className="mt-3 text-sm font-semibold text-center">{model.name}</h4>

<div className="mt-2 flex flex-col gap-1">
<div className="flex items-center justify-between text-[10px] text-muted-foreground">
<span>Latency</span>
<span>{model.latency}</span>
</div>
<div className="flex items-center justify-between text-[10px] text-muted-foreground">
<span>Tokens</span>
<span>{model.tokens}</span>
</div>
</div>

<div className="mt-2 flex gap-1.5 justify-center">
<span className="text-[10px] px-2 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800">
CO₂e ≈0.2g
</span>
<span className="text-[10px] px-2 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800">
⚡ 0.4Wh
</span>
</div>

<p className="mt-3 text-xs text-muted-foreground line-clamp-3 leading-relaxed">
Sveriges BNP uppgick till cirka 6 500 miljarder kronor...
</p>
</div>
))}
</div>

{/* Synthesis Bar */}
<div className="mt-8 max-w-5xl mx-auto rounded-xl bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-950/20 dark:to-purple-950/20 border border-blue-100 dark:border-blue-900/30 p-6">
<div className="flex items-start gap-3">
<div className="size-8 rounded-full bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center">
<span className="text-lg">✨</span>
</div>
<div>
<p className="text-sm font-semibold text-blue-900 dark:text-blue-200">OneSeek Synthesis</p>
<p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">
Baserat på alla 7 modellsvar: Sveriges BNP 2025 beräknas uppgå till cirka 6 500 miljarder
kronor enligt SCB:s preliminära data...
</p>
</div>
</div>
</div>
</div>
</section>
);
};

// ==================== SECTION 4: AGENT FLOW ====================

const AgentFlowSection = () => {
return (
<section className="py-24 md:py-32 bg-neutral-50 dark:bg-neutral-900/30">
<div className="mx-auto max-w-7xl px-6 lg:px-8">
<div className="text-center mb-16">
<span className="text-sm font-semibold text-purple-600 uppercase tracking-wider">ARKITEKTUR</span>
<h2 className="mt-2 text-3xl md:text-5xl font-bold tracking-tight text-black dark:text-white">
Se hela flödet — från fråga till svar
</h2>
<p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400">
Fullständig transparens i varje steg
</p>
</div>

{/* Simplified Flow */}
<div className="max-w-4xl mx-auto">
<div className="flex flex-wrap items-center justify-center gap-3">
{[
"Din fråga",
"→",
"Dispatcher",
"→",
"Agent Resolver",
"→",
"Executor",
"→",
"Synthesis",
"→",
"Svar",
].map((step, index) => (
<div
key={index}
className={cn(
step === "→" ? "text-neutral-400" : "rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-4 py-2 text-sm font-medium"
)}
>
{step}
</div>
))}
</div>

{/* Agent Grid */}
<div className="mt-12 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6">
<h3 className="text-center text-sm font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400 mb-6">
12 Specialiserade Agenter
</h3>
<div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
{[
"Knowledge",
"Weather",
"Trafik",
"Statistics",
"Kartor",
"Bolag",
"Riksdagen",
"Browser",
"Media",
"Code",
"Action",
"Synthesis",
].map((agent) => (
<div
key={agent}
className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-3 text-center text-xs font-medium"
>
{agent}
</div>
))}
</div>
</div>
</div>
</div>
</section>
);
};

// ==================== SECTION 5: LLM PROVIDERS ====================

const LLMProvidersSection = () => {
const providers = [
"OpenAI",
"Anthropic",
"Google",
"xAI",
"DeepSeek",
"Perplexity",
"Qwen",
"OpenRouter",
"Groq",
"Together",
"Azure",
"Mistral",
"Cohere",
"Fireworks",
"Cerebras",
"DeepInfra",
"Replicate",
"Ollama",
];

return (
<section className="py-24 md:py-32 border-t border-neutral-100 dark:border-neutral-800">
<div className="mx-auto max-w-7xl px-6 lg:px-8">
<div className="text-center mb-16">
<h2 className="text-3xl md:text-5xl font-bold tracking-tight text-black dark:text-white">
20+ LLM-providers
</h2>
<p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400">
Flexibel arkitektur med stöd för alla större språkmodeller
</p>
</div>

<div className="flex flex-wrap justify-center gap-3">
{providers.map((provider) => (
<span
key={provider}
className="rounded-full border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-4 py-2 text-sm font-medium hover:border-blue-200 dark:hover:border-blue-800 transition-colors"
>
{provider}
</span>
))}
</div>
</div>
</section>
);
};

// ==================== SECTION 6: CTA ====================

const CTASection = () => {
return (
<section className="py-24 md:py-32 border-t border-neutral-100 dark:border-neutral-800">
<div className="mx-auto max-w-4xl px-6 text-center">
<h2 className="text-3xl md:text-5xl font-bold tracking-tight text-black dark:text-white">
Redo att{" "}
<span className="bg-clip-text text-transparent bg-gradient-to-r from-orange-500 to-amber-500">
söka smartare?
</span>
</h2>

<p className="mt-6 text-lg text-neutral-500 dark:text-neutral-400">
Upplev Sveriges mest avancerade AI-sökplattform
</p>

<div className="mt-10 flex flex-col sm:flex-row justify-center gap-4">
<Link
href="/dashboard/public/new-chat"
className="h-12 px-8 rounded-xl bg-orange-500 text-white font-semibold shadow-lg transition-all hover:bg-orange-600 hover:shadow-xl flex items-center justify-center"
>
Kom igång nu
</Link>
<Link
href="/contact"
className="h-12 px-8 rounded-xl border-2 border-neutral-300 dark:border-neutral-700 font-semibold transition-colors hover:border-orange-500 hover:text-orange-500 dark:hover:border-orange-500 flex items-center justify-center"
>
Kontakta oss
</Link>
</div>
</div>
</section>
);
};

// ==================== MAIN PAGE COMPONENT ====================

export default function LandingPageMockup() {
return (
<main className="min-h-screen bg-white dark:bg-neutral-950 text-gray-900 dark:text-white">
<HeroSection />
<APIMarquee />
<CompareShowcase />
<AgentFlowSection />
<LLMProvidersSection />
<CTASection />
</main>
);
}
