"use client";

import { motion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import React, { useEffect, useState } from "react";
import Balancer from "react-wrap-balancer";
import { Logo } from "@/components/Logo";
import { cn } from "@/lib/utils";

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

// ==================== HERO SECTION ====================

const HeroSection = () => {
return (
<section className="relative min-h-screen px-4 py-20 md:px-8">
<div className="mx-auto max-w-5xl">
<div className="flex flex-col items-center text-center">
{/* Main heading */}
<h1 className="mb-6 text-4xl font-bold tracking-tight md:text-6xl lg:text-7xl">
<Balancer>
En fråga.{" "}
<span className="bg-gradient-to-r from-orange-500 to-amber-500 bg-clip-text text-transparent">
Alla svar.
</span>{" "}
Verifierat.
</Balancer>
</h1>

{/* Subtitle */}
<p className="mb-12 max-w-2xl text-lg text-gray-600 dark:text-gray-400">
Sveriges smartaste AI-plattform kombinerar 7 LLM-modeller och 20+ svenska datakällor för att ge dig
verifierade svar.
</p>

{/* Search bar with typing animation */}
<div className="mb-16 w-full max-w-3xl">
<div className="rounded-lg border border-gray-200 bg-white p-6 shadow-lg dark:border-gray-700 dark:bg-gray-800">
<TypingAnimation />
</div>
</div>

{/* Demo preview */}
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

// ==================== FEATURES SECTION ====================

const FeaturesSection = () => {
const features = [
{
title: "7 AI-modeller",
description: "Kombinerar svar från ChatGPT, Claude, Gemini, Grok, DeepSeek, Perplexity och Qwen",
},
{
title: "Svenska datakällor",
description: "Direkt integrerat med SCB, SMHI, Trafikverket, Bolagsverket, Riksdagen och Kolada",
},
{
title: "Verifierade svar",
description: "Alla svar faktakontrolleras och citeras med ursprungskällor från Tavily",
},
];

return (
<section className="px-4 py-20 md:px-8">
<div className="mx-auto max-w-5xl">
<div className="grid gap-12 md:grid-cols-3">
{features.map((feature, index) => (
<div key={index} className="text-center">
<h3 className="mb-3 text-xl font-semibold">{feature.title}</h3>
<p className="text-gray-600 dark:text-gray-400">{feature.description}</p>
</div>
))}
</div>
</div>
</section>
);
};

// ==================== INTEGRATIONS SECTION ====================

const IntegrationsSection = () => {
const integrations = {
"AI-modeller": ["OpenAI", "Anthropic", "Google", "xAI", "DeepSeek", "Perplexity", "Qwen"],
"Svenska myndigheter": ["SCB", "SMHI", "Trafikverket", "Bolagsverket", "Riksdagen", "Kolada"],
"Verktyg & Sökning": ["Tavily", "Geoapify"],
};

return (
<section className="border-t border-gray-200 px-4 py-20 dark:border-gray-800 md:px-8">
<div className="mx-auto max-w-5xl">
<h2 className="mb-12 text-center text-3xl font-bold md:text-4xl">Integrationer</h2>

<div className="grid gap-12 md:grid-cols-3">
{Object.entries(integrations).map(([category, items]) => (
<div key={category}>
<h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">{category}</h3>
<ul className="space-y-2">
{items.map((item) => (
<li key={item} className="text-gray-600 dark:text-gray-400">
{item}
</li>
))}
</ul>
</div>
))}
</div>
</div>
</section>
);
};

// ==================== CTA SECTION ====================

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
<FeaturesSection />
<IntegrationsSection />
<CTASection />
</main>
);
}
