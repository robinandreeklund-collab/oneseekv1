"use client";

import { motion, useInView } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";
import Balancer from "react-wrap-balancer";
import { cn } from "@/lib/utils";

// ==================== DESIGN TOKENS ====================
// Color gradients, spacing, typography, and animation timings
// Glassmorphism effects: backdrop-blur, semi-transparent backgrounds
// Animation library: Framer Motion with spring easing curves

const MODEL_LOGOS: Record<string, string> = {
gpt: "/llm-logos/openai.svg",
claude: "/llm-logos/anthropic.svg",
gemini: "/llm-logos/google.svg",
grok: "/llm-logos/xai.svg",
deepseek: "/llm-logos/deepseek.svg",
perplexity: "/llm-logos/perplexity.svg",
qwen: "/llm-logos/qwen.svg",
};

// ==================== SHARED MODEL DATA ====================
const MODEL_DATA = [
  { id: "gpt", name: "ChatGPT", provider: "OpenAI", latency: "0.9s", tokens: "~1.8k", performanceScore: 95, CO2Emission: "0.18g" },
  { id: "claude", name: "Claude", provider: "Anthropic", latency: "1.8s", tokens: "~2.1k", performanceScore: 85, CO2Emission: "0.24g" },
  { id: "gemini", name: "Gemini", provider: "Google", latency: "1.1s", tokens: "~2.4k", performanceScore: 88, CO2Emission: "0.22g" },
  { id: "deepseek", name: "DeepSeek", provider: "DeepSeek", latency: "1.4s", tokens: "~2.2k", performanceScore: 87, CO2Emission: "0.21g" },
  { id: "perplexity", name: "Perplexity", provider: "Perplexity", latency: "1.6s", tokens: "~2.0k", performanceScore: 82, CO2Emission: "0.25g" },
  { id: "qwen", name: "Qwen", provider: "Alibaba", latency: "1.5s", tokens: "~2.3k", performanceScore: 84, CO2Emission: "0.23g" },
  { id: "grok", name: "Grok", provider: "xAI", latency: "1.3s", tokens: "~1.9k", performanceScore: 90, CO2Emission: "0.20g" },
];




// ==================== SECTION 1: HERO WITH ENHANCED COMPARE PREVIEW ====================

const HeroSection = () => {
  // Map performanceScore to 'progress' for animation compatibility with Framer Motion
  const models = MODEL_DATA.map(m => ({ ...m, progress: m.performanceScore }));

return (
<section className="relative py-32 md:py-48 px-4 md:px-8">
<div className="mx-auto max-w-7xl">
{/* Heading - Enhanced */}
<motion.div 
className="mx-auto max-w-5xl text-center"
>
<motion.h1 
className="text-5xl md:text-8xl font-bold tracking-tight text-black dark:text-white leading-[1.05]"
transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
>
<Balancer>
En fråga.{" "}
<span className="relative inline-block">
<span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 via-purple-600 to-blue-600 bg-[length:200%_auto] animate-gradient">
Alla AI-modeller.
</span>
<motion.span 
className="absolute -inset-1 bg-gradient-to-r from-blue-600/20 via-purple-600/20 to-blue-600/20 blur-2xl"
animate={{ opacity: [0.5, 0.8, 0.5] }}
transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
/>
</span>{" "}
Jämför.
</Balancer>
</motion.h1>

<motion.p 
className="mt-8 text-xl md:text-2xl text-neutral-600 dark:text-neutral-300 max-w-3xl mx-auto leading-relaxed font-light"
transition={{ duration: 0.6, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
>
Ställ en fråga och se hur 7+ AI-modeller svarar samtidigt. Med latency, token-användning och
verifierade källor.
</motion.p>

<motion.div 
className="mt-12 flex gap-4 justify-center flex-wrap"
transition={{ duration: 0.6, delay: 0.4, ease: [0.16, 1, 0.3, 1] }}
>
<Link
href="/dashboard/public/new-chat"
className="group relative h-14 px-10 rounded-2xl bg-black dark:bg-white text-white dark:text-black text-base font-semibold transition-all duration-300 hover:scale-105 hover:shadow-2xl hover:shadow-black/20 dark:hover:shadow-white/20 flex items-center justify-center overflow-hidden"
>
<span className="relative z-10">Börja söka</span>
<motion.div 
className="absolute inset-0 bg-gradient-to-r from-black via-neutral-800 to-black dark:from-white dark:via-neutral-200 dark:to-white"
initial={{ x: "-100%" }}
whileHover={{ x: "100%" }}
transition={{ duration: 0.6, ease: "easeInOut" }}
/>
</Link>
<Link
href="#compare"
className="h-14 px-10 rounded-2xl ring-2 ring-neutral-200 dark:ring-neutral-700 text-base font-semibold transition-all duration-300 hover:scale-105 hover:ring-neutral-300 dark:hover:ring-neutral-600 hover:shadow-xl flex items-center justify-center backdrop-blur-sm bg-white/50 dark:bg-neutral-900/50"
>
Se demo
</Link>
</motion.div>
</motion.div>

{/* Enhanced Compare Preview with Glassmorphism */}
<motion.div 
className="mt-20 md:mt-32 mx-auto max-w-6xl"
transition={{ duration: 0.8, delay: 0.6, ease: [0.16, 1, 0.3, 1] }}
>
<div className="group relative rounded-3xl border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br from-neutral-50/80 to-neutral-100/80 dark:from-neutral-900/50 dark:to-neutral-900/30 p-2 backdrop-blur-xl shadow-2xl hover:shadow-3xl transition-all duration-500">
{/* Glow effect */}
<div className="absolute -inset-0.5 bg-gradient-to-r from-blue-500/20 via-purple-500/20 to-blue-500/20 rounded-3xl opacity-0 group-hover:opacity-100 blur-xl transition-opacity duration-500" />
<div className="relative rounded-2xl bg-white/90 dark:bg-neutral-950/90 p-8 backdrop-blur-sm">
<p className="text-sm text-neutral-600 dark:text-neutral-400 mb-6 font-medium">Vad är Sveriges BNP 2025?</p>

{/* Enhanced Model Grid */}
<div className="grid grid-cols-4 md:grid-cols-7 gap-4">
{models.map((model, index) => (
<motion.div
key={model.id}
whileHover={{ scale: 1.05, y: -4 }}
transition={{ 
duration: 0.3, 
delay: index * 0.06,
ease: [0.16, 1, 0.3, 1]
}}
className="group/card relative flex flex-col items-center gap-3 px-4 py-3 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200/80 dark:border-neutral-800/80 hover:border-blue-200 dark:hover:border-blue-900 hover:shadow-lg transition-all duration-300"
>
{/* Progress bar */}
<div className="absolute top-0 left-0 right-0 h-0.5 bg-neutral-100 dark:bg-neutral-800 rounded-t-xl overflow-hidden">
<motion.div
className="h-full bg-gradient-to-r from-blue-500 to-purple-500"
initial={{ width: 0 }}
animate={{ width: `${model.progress}%` }}
transition={{ duration: 1, delay: index * 0.1 + 0.5, ease: "easeOut" }}
/>
</div>

<div className="size-8 rounded-lg border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br from-white to-neutral-50 dark:from-neutral-900 dark:to-neutral-950 flex items-center justify-center p-1 shadow-sm">
<span className="text-sm font-bold bg-clip-text text-transparent bg-gradient-to-br from-neutral-900 to-neutral-600 dark:from-white dark:to-neutral-400">{model.name[0]}</span>
</div>
<span className="text-xs font-semibold text-center text-neutral-900 dark:text-white">{model.name}</span>
<span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400 px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/50">{model.latency}</span>
</motion.div>
))}
</div>

{/* Enhanced Sources Bar */}
<motion.div 
className="mt-6 rounded-xl bg-gradient-to-r from-neutral-50 to-neutral-100 dark:from-neutral-900/70 dark:to-neutral-900/50 border border-neutral-200/50 dark:border-neutral-800/50 px-6 py-4 flex items-center justify-between shadow-sm"
transition={{ delay: 1.2 }}
>
<span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Modellsvar (7 av 7)</span>
<span className="text-sm font-medium text-neutral-600 dark:text-neutral-400">Σ 12.4k tokens · ⚡ DeepSeek</span>
</motion.div>
</div>
</div>
</motion.div>
</div>
</section>
);
};

// ==================== SECTION 2: API MARQUEE ====================

const APIMarquee = () => {
  const apis = [
    { name: "SCB", logo: "/api-logos/scb-logo.png" },
    { name: "SMHI", logo: "/api-logos/smhi-logo.png" },
    { name: "Bolagsverket", logo: "/api-logos/bolagsverket-logo.png" },
    { name: "Trafikverket", logo: "/api-logos/trafikverket-logo.png" },
    { name: "Riksdagen", logo: "/api-logos/riksdagen-logo.png" },
    { name: "Kolada", logo: "/api-logos/kolada-logo.png" },
    { name: "Tavily", logo: "/api-logos/tavily-logo.png" },
  ];

  return (
    <section className="relative py-16 md:py-24 bg-white dark:bg-neutral-950 border-y border-neutral-100 dark:border-neutral-800/50 overflow-hidden">
      {/* Gradient Blur Background */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-32 bg-gradient-to-r from-blue-500/5 via-purple-500/5 to-blue-500/5 dark:from-blue-500/10 dark:via-purple-500/10 dark:to-blue-500/10 rounded-full blur-3xl" />
      </div>

      <p className="text-center text-sm tracking-widest uppercase text-neutral-400 font-medium mb-12" style={{ letterSpacing: '0.1em' }}>
        Ansluten till Sveriges officiella datakällor
      </p>

      <div className="overflow-hidden relative">
        {/* Gradient Masks */}
        <div className="absolute left-0 top-0 bottom-0 w-24 bg-gradient-to-r from-white dark:from-neutral-950 to-transparent z-10 pointer-events-none" />
        <div className="absolute right-0 top-0 bottom-0 w-24 bg-gradient-to-l from-white dark:from-neutral-950 to-transparent z-10 pointer-events-none" />

        <motion.div 
          className="flex gap-8 animate-marquee"
        >
          {[...apis, ...apis].map((api, index) => (
            <motion.div 
              key={index} 
              className="group flex items-center gap-3 px-6 py-3 whitespace-nowrap rounded-2xl border border-neutral-200/40 dark:border-neutral-800/40 bg-white/40 dark:bg-neutral-900/40 backdrop-blur-md hover:bg-white/60 dark:hover:bg-neutral-900/60 hover:shadow-lg dark:hover:shadow-lg/50 transition-all duration-300"
              whileHover={{ scale: 1.05, y: -2 }}
            >
              <div className="relative size-6 flex-shrink-0">
                <Image
                  src={api.logo}
                  alt={`${api.name} logo`}
                  width={24}
                  height={24}
                  className="object-contain"
                />
              </div>
              <span className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 group-hover:text-neutral-900 dark:group-hover:text-white transition-colors">{api.name}</span>
            </motion.div>
          ))}
        </motion.div>
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
          animation: marquee 40s linear infinite;
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
  // Map performanceScore to 'progress' for animation compatibility with Framer Motion
  const models = MODEL_DATA.map(m => ({ ...m, progress: m.performanceScore }));

  return (
    <section id="compare" className="py-24 md:py-32 relative overflow-hidden">
      {/* Background Gradient Elements */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-0 right-1/4 w-96 h-96 bg-gradient-to-br from-blue-500/5 to-purple-500/5 dark:from-blue-500/10 dark:to-purple-500/10 rounded-full blur-3xl" />
      </div>

      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        {/* Header */}
        <motion.div 
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <span className="text-sm font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider">COMPARE MODE</span>
          <h2 className="mt-2 text-3xl md:text-5xl font-bold tracking-tight text-black dark:text-white">
            Jämför AI-modeller — side by side
          </h2>
          <p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400 max-w-2xl mx-auto">
            Ställ en fråga och se hur 7+ modeller svarar, med latency, token-användning och CO₂-estimat
          </p>
        </motion.div>

        {/* Model Cards Grid */}
        <motion.div 
          className="grid lg:grid-cols-7 gap-4 max-w-5xl mx-auto mb-8"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, staggerChildren: 0.05 }}
        >
          {models.map((model, index) => (
            <motion.div
              key={model.id}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.05, duration: 0.4 }}
              whileHover={{ y: -6, scale: 1.02 }}
              className="group relative rounded-2xl border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br from-white/80 to-neutral-50/80 dark:from-neutral-900/60 dark:to-neutral-900/40 p-4 backdrop-blur-lg hover:border-blue-300/60 dark:hover:border-blue-700/60 hover:shadow-xl dark:hover:shadow-blue-900/20 transition-all duration-300 overflow-hidden"
            >
              {/* Glow effect */}
              <div className="absolute -inset-1 bg-gradient-to-r from-blue-500/0 via-purple-500/0 to-blue-500/0 group-hover:from-blue-500/20 group-hover:via-purple-500/20 group-hover:to-blue-500/20 rounded-2xl opacity-0 group-hover:opacity-100 blur-xl transition-all duration-500 -z-10" />

              <div className="size-8 rounded-md mx-auto border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br from-white to-neutral-50 dark:from-neutral-900 dark:to-neutral-950 flex items-center justify-center p-1 shadow-sm group-hover:shadow-md transition-shadow">
                <span className="text-xs font-bold bg-clip-text text-transparent bg-gradient-to-br from-blue-600 to-purple-600 dark:from-blue-400 dark:to-purple-400">{model.name[0]}</span>
              </div>

              <h4 className="mt-3 text-sm font-semibold text-center text-neutral-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">{model.name}</h4>
              <p className="text-[10px] text-neutral-500 dark:text-neutral-500 text-center">{model.provider}</p>

              <div className="mt-3 flex flex-col gap-2">
                <div className="flex items-center justify-between text-[10px] text-neutral-600 dark:text-neutral-400">
                  <span>Latency</span>
                  <span className="font-semibold text-neutral-900 dark:text-white">{model.latency}</span>
                </div>
                <div className="h-0.5 w-full bg-neutral-200 dark:bg-neutral-800 rounded-full overflow-hidden">
                  <motion.div 
                    className="h-full bg-gradient-to-r from-blue-500 to-purple-500"
                    initial={{ width: 0 }}
                    whileInView={{ width: `${model.progress}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 1, delay: index * 0.1 }}
                  />
                </div>
              </div>

              <div className="mt-3 flex flex-col gap-2">
                <div className="flex items-center justify-between text-[10px] text-neutral-600 dark:text-neutral-400">
                  <span>Tokens</span>
                  <span className="font-semibold text-neutral-900 dark:text-white">{model.tokens}</span>
                </div>
              </div>

              <div className="mt-3 flex gap-1.5 justify-center">
                <motion.span 
                  className="text-[10px] px-2 py-1 rounded-full bg-gradient-to-r from-emerald-100 to-teal-100 dark:from-emerald-950/50 dark:to-teal-950/50 text-emerald-700 dark:text-emerald-400 font-semibold"
                  whileHover={{ scale: 1.05 }}
                >
                  CO₂ ≈{model.CO2Emission}
                </motion.span>
              </div>

              <p className="mt-3 text-xs text-neutral-600 dark:text-neutral-400 line-clamp-3 leading-relaxed text-center group-hover:text-neutral-900 dark:group-hover:text-neutral-300 transition-colors">
                Sveriges BNP uppgick till cirka 6 500 miljarder kronor...
              </p>
            </motion.div>
          ))}
        </motion.div>

        {/* Synthesis Bar */}
        <motion.div 
          className="max-w-5xl mx-auto rounded-2xl bg-gradient-to-r from-blue-50/80 via-purple-50/80 to-blue-50/80 dark:from-blue-950/30 dark:via-purple-950/30 dark:to-blue-950/30 border border-blue-200/60 dark:border-blue-800/60 backdrop-blur-lg p-6 shadow-lg hover:shadow-xl dark:hover:shadow-blue-900/30 transition-all duration-300 overflow-hidden group relative"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.3, duration: 0.6 }}
        >
          {/* Glow effect */}
          <div className="absolute -inset-0.5 bg-gradient-to-r from-blue-500/20 via-purple-500/20 to-blue-500/20 rounded-2xl opacity-0 group-hover:opacity-100 blur-lg transition-opacity duration-500 -z-10" />

          <div className="relative flex items-start gap-4">
            <motion.div 
              className="size-8 rounded-full bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center flex-shrink-0 shadow-lg"
              whileHover={{ scale: 1.1, rotate: 360 }}
              transition={{ duration: 0.6 }}
            >
              <span className="text-lg">✨</span>
            </motion.div>
            <div>
              <p className="text-sm font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600 dark:from-blue-300 dark:to-purple-300">OneSeek Synthesis</p>
              <p className="mt-1 text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">
                Baserat på alla 7 modellsvar: Sveriges BNP 2025 beräknas uppgå till cirka 6 500 miljarder kronor enligt SCB:s preliminära data...
              </p>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

// ==================== SECTION 4: AGENT FLOW ====================

const AgentFlowSection = () => {
  const flowSteps = [
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
    <section className="py-24 md:py-32 bg-gradient-to-b from-transparent via-purple-500/5 to-transparent dark:via-purple-500/10 relative overflow-hidden">
      {/* Background Gradient Elements */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-gradient-to-br from-purple-500/5 via-pink-500/5 to-orange-500/5 dark:from-purple-500/10 dark:via-pink-500/10 dark:to-orange-500/10 rounded-full blur-3xl" />
      </div>

      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <motion.div 
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <span className="text-sm font-semibold text-purple-600 dark:text-purple-400 uppercase tracking-wider">ARKITEKTUR</span>
          <h2 className="mt-2 text-3xl md:text-5xl font-bold tracking-tight text-black dark:text-white">
            Se hela flödet — från fråga till svar
          </h2>
          <p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400">
            Fullständig transparens i varje steg
          </p>
        </motion.div>

        {/* Flow Diagram */}
        <motion.div 
          className="max-w-5xl mx-auto mb-16"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <div className="flex flex-wrap items-center justify-center gap-2 md:gap-3">
            {flowSteps.map((step, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.05, duration: 0.3 }}
                whileHover={step !== "→" ? { scale: 1.05, y: -2 } : {}}
                className={cn(
                  step === "→" 
                    ? "text-neutral-400 dark:text-neutral-600 text-lg font-semibold" 
                    : "rounded-xl border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br from-white/80 to-neutral-50/80 dark:from-neutral-900/60 dark:to-neutral-900/40 backdrop-blur-md px-4 py-2 text-sm font-semibold text-neutral-900 dark:text-white shadow-md hover:shadow-lg dark:hover:shadow-purple-900/20 hover:border-purple-300/60 dark:hover:border-purple-700/60 transition-all duration-300"
                )}
              >
                {step}
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Agent Grid */}
        <motion.div 
          className="rounded-2xl border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br from-white/50 to-neutral-50/50 dark:from-neutral-900/50 dark:to-neutral-900/30 backdrop-blur-lg p-8 shadow-xl hover:shadow-2xl dark:hover:shadow-purple-900/30 transition-all duration-300 group relative overflow-hidden"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2, duration: 0.6 }}
        >
          {/* Glow effect */}
          <div className="absolute -inset-1 bg-gradient-to-r from-purple-500/0 via-pink-500/0 to-purple-500/0 group-hover:from-purple-500/20 group-hover:via-pink-500/20 group-hover:to-purple-500/20 rounded-2xl opacity-0 group-hover:opacity-100 blur-xl transition-all duration-500 -z-10" />

          <h3 className="text-center text-sm font-bold uppercase tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-purple-600 to-pink-600 dark:from-purple-400 dark:to-pink-400 mb-8">
            12 Specialiserade Agenter
          </h3>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {agents.map((agent, index) => (
              <motion.div
                key={agent}
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.04, duration: 0.3 }}
                whileHover={{ scale: 1.06, y: -4 }}
                className="group/agent relative rounded-xl border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br from-white/70 to-neutral-50/70 dark:from-neutral-900/70 dark:to-neutral-900/50 backdrop-blur-sm p-4 text-center text-xs font-semibold text-neutral-900 dark:text-white shadow-md hover:shadow-lg dark:hover:shadow-purple-900/20 hover:border-purple-300/60 dark:hover:border-purple-700/60 transition-all duration-300 cursor-pointer overflow-hidden"
              >
                {/* Subtle glow on hover */}
                <div className="absolute inset-0 bg-gradient-to-br from-purple-500/0 to-pink-500/0 group-hover/agent:from-purple-500/10 group-hover/agent:to-pink-500/10 transition-all duration-300 rounded-xl" />
                <span className="relative z-10">{agent}</span>
              </motion.div>
            ))}
          </div>
        </motion.div>
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

  const providerColors = {
    "OpenAI": "from-green-500/20 to-emerald-500/20 dark:from-green-500/30 dark:to-emerald-500/30",
    "Anthropic": "from-orange-500/20 to-amber-500/20 dark:from-orange-500/30 dark:to-amber-500/30",
    "Google": "from-blue-500/20 to-cyan-500/20 dark:from-blue-500/30 dark:to-cyan-500/30",
    "xAI": "from-purple-500/20 to-pink-500/20 dark:from-purple-500/30 dark:to-pink-500/30",
    "DeepSeek": "from-indigo-500/20 to-blue-500/20 dark:from-indigo-500/30 dark:to-blue-500/30",
    "Perplexity": "from-red-500/20 to-orange-500/20 dark:from-red-500/30 dark:to-orange-500/30",
    "Qwen": "from-yellow-500/20 to-orange-500/20 dark:from-yellow-500/30 dark:to-orange-500/30",
    "OpenRouter": "from-pink-500/20 to-rose-500/20 dark:from-pink-500/30 dark:to-rose-500/30",
  };

  return (
    <section className="py-24 md:py-32 border-t border-neutral-100 dark:border-neutral-800/50 relative overflow-hidden">
      {/* Background Gradient */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-0 left-1/3 w-96 h-96 bg-gradient-to-br from-blue-500/5 to-cyan-500/5 dark:from-blue-500/10 dark:to-cyan-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-gradient-to-tl from-purple-500/5 to-pink-500/5 dark:from-purple-500/10 dark:to-pink-500/10 rounded-full blur-3xl" />
      </div>

      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <motion.div 
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-black dark:text-white">
            20+ LLM-providers
          </h2>
          <p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400">
            Flexibel arkitektur med stöd för alla större språkmodeller
          </p>
        </motion.div>

        <motion.div 
          className="flex flex-wrap justify-center gap-3"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, staggerChildren: 0.03 }}
        >
          {providers.map((provider, index) => (
            <motion.div
              key={provider}
              initial={{ opacity: 0, scale: 0.8, y: 10 }}
              whileInView={{ opacity: 1, scale: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.03, duration: 0.3 }}
              whileHover={{ scale: 1.1, y: -4 }}
              className="group relative"
            >
              <div 
                className={cn(
                  "rounded-full border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br px-5 py-2.5 text-sm font-semibold text-neutral-900 dark:text-white backdrop-blur-md shadow-md hover:shadow-xl dark:hover:shadow-blue-900/30 transition-all duration-300 cursor-pointer overflow-hidden relative",
                  providerColors[provider as keyof typeof providerColors] || "from-neutral-100/80 to-neutral-100/80 dark:from-neutral-800/60 dark:to-neutral-800/60"
                )}
              >
                {/* Glow effect */}
                <div className="absolute -inset-1 bg-gradient-to-r from-blue-500/0 to-purple-500/0 group-hover:from-blue-500/30 group-hover:to-purple-500/30 rounded-full opacity-0 group-hover:opacity-100 blur-lg transition-all duration-500 -z-10" />
                
                {/* Shine effect on hover */}
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white to-transparent opacity-0 group-hover:opacity-20 dark:group-hover:opacity-10 transform -skew-x-12 group-hover:translate-x-full transition-all duration-500 pointer-events-none" />
                
                <span className="relative z-10">{provider}</span>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
};

// ==================== SECTION 6: CTA ====================

const CTASection = () => {
  return (
    <section className="py-24 md:py-32 border-t border-neutral-100 dark:border-neutral-800 relative overflow-hidden">
      {/* Background Gradient Elements */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-gradient-to-br from-orange-500/5 via-amber-500/5 to-orange-500/5 dark:from-orange-500/10 dark:via-amber-500/10 dark:to-orange-500/10 rounded-full blur-3xl" />
      </div>

      <motion.div 
        className="mx-auto max-w-4xl px-6 text-center"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.6 }}
      >
        <motion.h2 
          className="text-3xl md:text-5xl font-bold tracking-tight text-black dark:text-white"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1, duration: 0.6 }}
        >
          Redo att{" "}
          <span className="relative inline-block">
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-orange-500 via-amber-500 to-orange-500 bg-[length:200%_auto] animate-gradient">
              söka smartare?
            </span>
            <motion.span 
              className="absolute -inset-1 bg-gradient-to-r from-orange-500/20 via-amber-500/20 to-orange-500/20 blur-2xl rounded-lg"
              animate={{ opacity: [0.5, 0.8, 0.5] }}
              transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            />
          </span>
        </motion.h2>

        <motion.p 
          className="mt-6 text-lg text-neutral-500 dark:text-neutral-400"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2, duration: 0.6 }}
        >
          Upplev Sveriges mest avancerade AI-sökplattform
        </motion.p>

        <motion.div 
          className="mt-10 flex flex-col sm:flex-row justify-center gap-4"
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.3, duration: 0.6 }}
        >
          {/* Primary CTA Button */}
          <Link
            href="/dashboard/public/new-chat"
            className="group relative h-14 px-8 rounded-2xl bg-gradient-to-r from-orange-500 to-amber-500 text-white font-semibold shadow-xl hover:shadow-2xl hover:shadow-orange-500/50 dark:hover:shadow-orange-500/30 transition-all duration-300 hover:scale-105 flex items-center justify-center overflow-hidden"
          >
            {/* Shine effect */}
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent opacity-0 group-hover:opacity-100 transform -skew-x-12 group-hover:translate-x-full transition-all duration-700 pointer-events-none" />
            
            {/* Glow effect */}
            <div className="absolute -inset-1 bg-gradient-to-r from-orange-500/20 to-amber-500/20 rounded-2xl opacity-0 group-hover:opacity-100 blur-xl transition-opacity duration-500 -z-10" />
            
            <span className="relative z-10 flex items-center gap-2">
              <span>Kom igång nu</span>
              <motion.span
                animate={{ x: [0, 4, 0] }}
                transition={{ duration: 2, repeat: Infinity }}
              >
                →
              </motion.span>
            </span>
          </Link>

          {/* Secondary CTA Button */}
          <Link
            href="/contact"
            className="group relative h-14 px-8 rounded-2xl border-2 border-neutral-300 dark:border-neutral-700 font-semibold transition-all duration-300 hover:scale-105 hover:border-orange-500 dark:hover:border-orange-500 hover:shadow-lg dark:hover:shadow-orange-500/20 flex items-center justify-center overflow-hidden bg-white/40 dark:bg-neutral-900/40 backdrop-blur-sm hover:bg-white/60 dark:hover:bg-neutral-900/60"
          >
            {/* Glow effect */}
            <div className="absolute -inset-1 bg-gradient-to-r from-orange-500/0 via-amber-500/0 to-orange-500/0 group-hover:from-orange-500/20 group-hover:via-amber-500/20 group-hover:to-orange-500/20 rounded-2xl opacity-0 group-hover:opacity-100 blur-xl transition-all duration-500 -z-10" />

            <span className="relative z-10 text-neutral-900 dark:text-white group-hover:text-orange-600 dark:group-hover:text-orange-400 transition-colors">
              Kontakta oss
            </span>
          </Link>
        </motion.div>

        {/* Floating Elements */}
        <motion.div 
          className="mt-16 relative h-20"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.5, duration: 0.6 }}
        >
          <motion.div 
            className="absolute left-1/4 top-0 size-3 rounded-full bg-gradient-to-br from-orange-400 to-amber-500 shadow-lg"
            animate={{ y: [0, -20, 0], opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 3, repeat: Infinity }}
          />
          <motion.div 
            className="absolute right-1/4 top-0 size-3 rounded-full bg-gradient-to-br from-blue-400 to-purple-500 shadow-lg"
            animate={{ y: [0, -20, 0], opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 3, repeat: Infinity, delay: 0.5 }}
          />
          <motion.div 
            className="absolute left-1/3 bottom-0 size-2 rounded-full bg-gradient-to-br from-purple-400 to-pink-500 shadow-lg"
            animate={{ y: [0, 20, 0], opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 3, repeat: Infinity, delay: 1 }}
          />
        </motion.div>
      </motion.div>
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
