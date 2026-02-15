"use client";

import { motion, useInView } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";
import Balancer from "react-wrap-balancer";
import { Logo } from "@/components/Logo";
import { cn } from "@/lib/utils";

// ==================== SHARED COMPONENTS ====================

const AnimatedSection = ({ children, className }: { children: React.ReactNode; className?: string }) => {
const ref = useRef(null);
const isInView = useInView(ref, { once: true, margin: "-100px" });

return (
<motion.section
ref={ref}
initial={{ opacity: 1, y: 0 }}
animate={isInView ? { opacity: 1, y: 0 } : { opacity: 1, y: 0 }}
transition={{ duration: 0.6, ease: "easeOut" }}
className={className}
>
{children}
</motion.section>
);
};

// ==================== TYPING ANIMATION ====================

const TypingAnimation = () => {
const queries = [
"Hur blir vädret i Stockholm imorgon?",
"Jämför alla AI-modeller om klimatpolitik",
"Visa SCB-statistik för befolkningsutveckling",
];

const [currentIndex, setCurrentIndex] = useState(0);
const [displayText, setDisplayText] = useState("");
const [isDeleting, setIsDeleting] = useState(false);

useEffect(() => {
const currentQuery = queries[currentIndex];
const fullText = currentQuery;

const timeout = setTimeout(
() => {
if (!isDeleting) {
if (displayText.length < fullText.length) {
setDisplayText(fullText.slice(0, displayText.length + 1));
} else {
setTimeout(() => setIsDeleting(true), 2000);
}
} else {
if (displayText.length > 0) {
setDisplayText(displayText.slice(0, -1));
} else {
setIsDeleting(false);
setCurrentIndex((currentIndex + 1) % queries.length);
}
}
},
isDeleting ? 30 : 50
);

return () => clearTimeout(timeout);
}, [displayText, isDeleting, currentIndex]);

return (
<div className="relative">
<span className="text-gray-600 dark:text-gray-400">{displayText}</span>
<span className="ml-1 inline-block h-5 w-0.5 animate-pulse bg-orange-500" />
</div>
);
};

// ==================== SECTION 1: HERO ====================

const HeroSection = () => {
return (
<section className="relative min-h-screen px-4 py-20 md:px-8">
<div className="mx-auto max-w-5xl">
<div className="flex flex-col items-center text-center">
<h1 className="mb-6 text-4xl font-bold tracking-tight md:text-6xl lg:text-7xl">
<Balancer>
En fråga.{" "}
<span className="bg-gradient-to-r from-orange-500 to-amber-500 bg-clip-text text-transparent">
Alla svar.
</span>{" "}
Verifierat.
</Balancer>
</h1>

<p className="mb-12 max-w-2xl text-lg text-gray-600 dark:text-gray-400">
Sveriges smartaste AI-plattform kombinerar 7 LLM-modeller och 20+ svenska datakällor för att ge dig
verifierade svar.
</p>

<div className="mb-16 w-full max-w-3xl">
<div className="rounded-lg border border-gray-200 bg-white p-6 shadow-lg dark:border-gray-700 dark:bg-gray-800">
<TypingAnimation />
</div>
</div>

<div className="w-full max-w-5xl">
<div className="overflow-hidden rounded-lg border border-gray-200 shadow-xl dark:border-gray-700">
<Image
src="/homepage/main_demo.webp"
alt="OneSeek Demo"
width={1920}
height={1080}
className="w-full"
priority
/>
</div>
</div>
</div>
</div>
</section>
);
};

// ==================== SECTION 2: COMPARE MODE ====================

const CompareModeSection = () => {
const models = [
{ name: "ChatGPT", provider: "OpenAI" },
{ name: "Claude", provider: "Anthropic" },
{ name: "Gemini", provider: "Google" },
{ name: "Grok", provider: "xAI" },
{ name: "DeepSeek", provider: "DeepSeek" },
{ name: "Perplexity", provider: "Perplexity" },
{ name: "Qwen", provider: "Alibaba" },
];

return (
<AnimatedSection className="border-t border-gray-200 px-4 py-20 dark:border-gray-800 md:px-8">
<div className="mx-auto max-w-5xl">
<h2 className="mb-4 text-center text-3xl font-bold md:text-4xl">7 AI-modeller samtidigt</h2>
<p className="mb-12 text-center text-gray-600 dark:text-gray-400">
Jämför och kombinera svar från världens ledande AI-modeller
</p>

<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
{models.map((model) => (
<div
key={model.name}
className="rounded-lg border border-gray-200 bg-white p-4 text-center dark:border-gray-700 dark:bg-gray-800"
>
<div className="text-sm font-semibold text-gray-900 dark:text-white">{model.name}</div>
<div className="text-xs text-gray-500 dark:text-gray-400">{model.provider}</div>
</div>
))}
</div>

<div className="mt-8 text-center">
<div className="inline-flex items-center gap-2 rounded-full border border-orange-500 bg-orange-50 px-4 py-2 text-sm font-medium text-orange-600 dark:bg-orange-950/20">
→ OneSeek syntetiserar och verifierar svaren
</div>
</div>
</div>
</AnimatedSection>
);
};

// ==================== SECTION 3: DEBATT-LÄGE ====================

const DebattSection = () => {
return (
<AnimatedSection className="border-t border-gray-200 px-4 py-20 dark:border-gray-800 md:px-8">
<div className="mx-auto max-w-5xl">
<h2 className="mb-4 text-center text-3xl font-bold md:text-4xl">Riksdagsdata i realtid</h2>
<p className="mb-12 text-center text-gray-600 dark:text-gray-400">
Analysera propositioner och motioner direkt från riksdagen
</p>

<div className="grid gap-6 md:grid-cols-2">
<div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
<div className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">Proposition 2024/25:142</div>
<div className="mb-4 text-sm text-gray-600 dark:text-gray-400">Förstärkt klimatlag</div>
<div className="space-y-2">
<div className="h-2 w-full rounded bg-gray-100 dark:bg-gray-700" />
<div className="h-2 w-4/5 rounded bg-gray-100 dark:bg-gray-700" />
<div className="h-2 w-3/5 rounded bg-gray-100 dark:bg-gray-700" />
</div>
</div>

<div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
<div className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">Motion 2024/25:3847</div>
<div className="mb-4 text-sm text-gray-600 dark:text-gray-400">Utökad skattereform</div>
<div className="space-y-2">
<div className="h-2 w-full rounded bg-gray-100 dark:bg-gray-700" />
<div className="h-2 w-4/5 rounded bg-gray-100 dark:bg-gray-700" />
<div className="h-2 w-3/5 rounded bg-gray-100 dark:bg-gray-700" />
</div>
</div>
</div>
</div>
</AnimatedSection>
);
};

// ==================== SECTION 4: INTEGRATIONER ====================

const IntegrationsSection = () => {
const integrations = {
"AI-modeller": ["OpenAI", "Anthropic", "Google", "xAI", "DeepSeek", "Perplexity", "Qwen"],
"Svenska myndigheter": ["SCB", "SMHI", "Trafikverket", "Bolagsverket", "Riksdagen", "Kolada"],
"Verktyg & Sökning": ["Tavily", "Geoapify"],
};

return (
<AnimatedSection className="border-t border-gray-200 px-4 py-20 dark:border-gray-800 md:px-8">
<div className="mx-auto max-w-5xl">
<h2 className="mb-4 text-center text-3xl font-bold md:text-4xl">Integrationer</h2>
<p className="mb-12 text-center text-gray-600 dark:text-gray-400">
Direkt kopplat till Sveriges viktigaste datakällor
</p>

<div className="grid gap-12 md:grid-cols-3">
{Object.entries(integrations).map(([category, items]) => (
<div key={category}>
<h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
{category}
</h3>
<ul className="space-y-2">
{items.map((item) => (
<li key={item} className="text-gray-900 dark:text-white">
{item}
</li>
))}
</ul>
</div>
))}
</div>
</div>
</AnimatedSection>
);
};

// ==================== SECTION 5: LANGGRAPH PIPELINE ====================

const PipelineSection = () => {
const pipeline = [
{ label: "Din fråga" },
{ label: "Intent Router" },
{ label: "Agent Resolver" },
{ label: "Planner" },
{ label: "Executor" },
{ label: "Critic" },
{ label: "Svar" },
];

const agents = [
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
];

return (
<AnimatedSection className="border-t border-gray-200 px-4 py-20 dark:border-gray-800 md:px-8">
<div className="mx-auto max-w-5xl">
<h2 className="mb-4 text-center text-3xl font-bold md:text-4xl">Så fungerar OneSeek</h2>
<p className="mb-12 text-center text-gray-600 dark:text-gray-400">
Intelligent routing och specialiserade agenter för varje typ av fråga
</p>

{/* Pipeline flow */}
<div className="mb-12 flex flex-wrap items-center justify-center gap-2">
{pipeline.map((node, index) => (
<React.Fragment key={node.label}>
<div className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium dark:border-gray-700 dark:bg-gray-800">
{node.label}
</div>
{index < pipeline.length - 1 && <span className="text-gray-400">→</span>}
</React.Fragment>
))}
</div>

{/* Agents */}
<div>
<h3 className="mb-6 text-center text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
12 Specialiserade Agenter
</h3>
<div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
{agents.map((agent) => (
<div
key={agent}
className="rounded-lg border border-gray-200 bg-white p-3 text-center text-xs font-medium dark:border-gray-700 dark:bg-gray-800"
>
{agent}
</div>
))}
</div>
</div>
</div>
</AnimatedSection>
);
};

// ==================== SECTION 6: LLM PROVIDERS ====================

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
<AnimatedSection className="border-t border-gray-200 px-4 py-20 dark:border-gray-800 md:px-8">
<div className="mx-auto max-w-5xl">
<h2 className="mb-4 text-center text-3xl font-bold md:text-4xl">20+ LLM-providers</h2>
<p className="mb-12 text-center text-gray-600 dark:text-gray-400">
Flexibel arkitektur med stöd för alla större språkmodeller
</p>

<div className="flex flex-wrap justify-center gap-3">
{providers.map((provider) => (
<span
key={provider}
className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm font-medium dark:border-gray-700 dark:bg-gray-800"
>
{provider}
</span>
))}
</div>
</div>
</AnimatedSection>
);
};

// ==================== SECTION 7: CTA ====================

const CTASection = () => {
return (
<section className="border-t border-gray-200 bg-white px-4 py-20 dark:border-gray-800 dark:bg-gray-950 md:px-8">
<div className="mx-auto max-w-4xl text-center">
<h2 className="mb-6 text-3xl font-bold md:text-4xl">
Redo att{" "}
<span className="bg-gradient-to-r from-orange-500 to-amber-500 bg-clip-text text-transparent">
söka smartare?
</span>
</h2>

<p className="mb-8 text-lg text-gray-600 dark:text-gray-400">
Upplev Sveriges mest avancerade AI-sökplattform
</p>

<div className="flex flex-col justify-center gap-4 sm:flex-row">
<Link
href="/dashboard/public/new-chat"
className="rounded-lg bg-orange-500 px-8 py-3 font-semibold text-white shadow-lg transition-all hover:bg-orange-600 hover:shadow-xl"
>
Kom igång nu
</Link>
<Link
href="/contact"
className="rounded-lg border-2 border-gray-300 px-8 py-3 font-semibold text-gray-900 transition-colors hover:border-orange-500 hover:text-orange-500 dark:border-gray-700 dark:text-white dark:hover:border-orange-500"
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
<main className="min-h-screen bg-white text-gray-900 dark:bg-gray-950 dark:text-white">
<HeroSection />
<CompareModeSection />
<DebattSection />
<IntegrationsSection />
<PipelineSection />
<LLMProvidersSection />
<CTASection />
</main>
);
}
