"use client";

import { motion, useInView } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import React, { useCallback, useEffect, useRef, useState } from "react";
import Balancer from "react-wrap-balancer";
import { cn } from "@/lib/utils";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// ==================== DESIGN TOKENS ====================
// Color gradients, spacing, typography, and animation timings
// Glassmorphism effects: backdrop-blur, semi-transparent backgrounds
// Animation library: Framer Motion with spring easing curves

const MODEL_LOGOS: Record<string, string> = {
  gpt: "/model-logos/chatgpt.png",
  claude: "/model-logos/claude.png",
  gemini: "/model-logos/gemini.png",
  grok: "/model-logos/grok.png",
  deepseek: "/model-logos/deepseek.png",
  perplexity: "/model-logos/perplexity.png",
  qwen: "/model-logos/qwen.png",
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

// ==================== EVALUATION METRICS DATA ====================
const EVALUATION_METRICS = [
  {
    icon: "🇸🇪",
    category: "Språk & Svenska",
    description: "Flyt, naturlighet, fackspråk, idiom",
    importance: "OneSeek är svenskt – språket är kärnan",
    examples: "Skriv långa texter, använd facktermer, testa dialekter"
  },
  {
    icon: "📚",
    category: "Fakta & Kunskap",
    description: "Faktaexakthet, aktualitet, hallucinationer",
    importance: "Svenska API:er kräver korrekt information",
    examples: "Befolkning i Hjo 2025? Senaste elpris-beslut?"
  },
  {
    icon: "⚖️",
    category: "Bias & Neutralitet",
    description: "Politik, kultur, kön, opartiskhet",
    importance: "OneSeek ska vara trovärdig och neutral",
    examples: "Frågor om politik, migration, klimat, välfärd"
  },
  {
    icon: "📖",
    category: "Källor & Transparens",
    description: "Citations, källhänvisningar, osäkerhet",
    importance: "Citations är kritiskt för OneSeek",
    examples: "Visa källor, hur vet du det, vad är osäkert?"
  },
  {
    icon: "🧠",
    category: "Resonemang & Logik",
    description: "Steg-för-steg-tänkande, komplexa problem",
    importance: "Supervisor och planner kräver starkt resonemang",
    examples: "Hur lösa X? Jämför A och B. Risker med Y?"
  },
  {
    icon: "🔧",
    category: "Verktygsanvändning",
    description: "Tool-calling, multi-step, agent-beteende",
    importance: "LangGraph + bigtool är kritiskt",
    examples: "Hämta SCB-data, visa karta över vägarbeten"
  },
  {
    icon: "🛡️",
    category: "Säkerhet & Etik",
    description: "Vägrar farligt, hanterar jailbreaks",
    importance: "Viktigt för svensk produkt",
    examples: "Bygga bomb? Falsk nyhet om politiker?"
  },
  {
    icon: "⚡",
    category: "Hastighet & Kostnad",
    description: "TTFT, tokens per svar, kostnadseffektivitet",
    importance: "Påverkar användarupplevelse och drift",
    examples: "Mät TTFT och total tokens på samma frågor"
  },
  {
    icon: "💬",
    category: "Personlighet & Ton",
    description: "Mänsklig, trevlig, professionell",
    importance: "OneSeek ska kännas varm men seriös",
    examples: "Smalltalk, humor, empati, spydighet"
  },
  {
    icon: "🔄",
    category: "Långkonversation",
    description: "Minne, kontextbevarande över meddelanden",
    importance: "Supervisor och active_plan är centralt",
    examples: "15-20 meddelanden lång konversation"
  }
];

// ==================== DETAILED LANGGRAPH STEPS ====================
const DETAILED_LANGGRAPH_STEPS = [
  // System Initialization (1-5)
  { id: 1, name: "START", icon: "▶️", phase: "init", description: "Initialize execution" },
  { id: 2, name: "Load Configuration", icon: "⚙️", phase: "init", description: "Load system config" },
  { id: 3, name: "Initialize LangGraph", icon: "⚙️", phase: "init", description: "Setup state machine" },
  { id: 4, name: "Set Checkpointer", icon: "⚙️", phase: "init", description: "Enable state persistence" },
  { id: 5, name: "Prepare State", icon: "⚙️", phase: "init", description: "Initialize execution state" },
  
  // Intent Resolution (6-15)
  { id: 6, name: "Parse Query", icon: "💭", phase: "intent", description: "Extract query structure" },
  { id: 7, name: "Tokenize Input", icon: "💭", phase: "intent", description: "Break into tokens" },
  { id: 8, name: "Run Intent Classifier", icon: "💭", phase: "intent", description: "Determine query type" },
  { id: 9, name: "Intent: Statistics", icon: "✓", phase: "intent", description: "Detected: statistics query" },
  { id: 10, name: "Confidence: 0.94", icon: "✓", phase: "intent", description: "High confidence score" },
  { id: 11, name: "Extract Entities", icon: "💭", phase: "intent", description: "Find: Stockholm, population" },
  { id: 12, name: "Validate Intent", icon: "✓", phase: "intent", description: "Intent validated" },
  { id: 13, name: "Save Intent State", icon: "⚙️", phase: "intent", description: "Store intent data" },
  { id: 14, name: "Prepare Routing", icon: "💭", phase: "intent", description: "Setup for agent selection" },
  { id: 15, name: "Intent Complete", icon: "✓", phase: "intent", description: "Intent resolution done" },
  
  // Agent Selection (16-25)
  { id: 16, name: "Query Embeddings", icon: "🤖", phase: "planning", description: "Generate query vector" },
  { id: 17, name: "Retrieve Agents", icon: "🤖", phase: "planning", description: "Get top 5 candidates" },
  { id: 18, name: "Score: Statistics 0.92", icon: "✓", phase: "planning", description: "Best match found" },
  { id: 19, name: "Score: Action 0.31", icon: "💭", phase: "planning", description: "Lower score" },
  { id: 20, name: "Score: Knowledge 0.28", icon: "💭", phase: "planning", description: "Lower score" },
  { id: 21, name: "Select: Statistics", icon: "✓", phase: "planning", description: "Statistics agent chosen" },
  { id: 22, name: "Load Agent Config", icon: "⚙️", phase: "planning", description: "Load agent definition" },
  { id: 23, name: "Initialize Context", icon: "⚙️", phase: "planning", description: "Setup agent context" },
  { id: 24, name: "Validate Selection", icon: "✓", phase: "planning", description: "Agent validated" },
  { id: 25, name: "Agent Ready", icon: "✓", phase: "planning", description: "Agent selection complete" },
  
  // Planning (26-35)
  { id: 26, name: "Generate Plan", icon: "🤖", phase: "planning", description: "Model: Claude Sonnet 3.5" },
  { id: 27, name: "Plan Prompt", icon: "💭", phase: "planning", description: "312 tokens sent" },
  { id: 28, name: "LLM Response", icon: "🤖", phase: "planning", description: "Plan generated" },
  { id: 29, name: "Parse Plan Steps", icon: "💭", phase: "planning", description: "Extract action steps" },
  { id: 30, name: "Step 1: Query SCB", icon: "✓", phase: "planning", description: "For Stockholm population" },
  { id: 31, name: "Step 2: Validate", icon: "✓", phase: "planning", description: "Check data quality" },
  { id: 32, name: "Step 3: Format", icon: "✓", phase: "planning", description: "Prepare response" },
  { id: 33, name: "Validate Plan", icon: "✓", phase: "planning", description: "Plan structure OK" },
  { id: 34, name: "Save Plan", icon: "⚙️", phase: "planning", description: "Store in state" },
  { id: 35, name: "Planning Complete", icon: "✓", phase: "planning", description: "Ready for execution" },
  
  // Tool Resolution (36-45)
  { id: 36, name: "Map to Tools", icon: "🔧", phase: "execution", description: "Find matching tools" },
  { id: 37, name: "Tool: get_population", icon: "🔧", phase: "execution", description: "SCB tool identified" },
  { id: 38, name: "Load Definition", icon: "⚙️", phase: "execution", description: "Load tool schema" },
  { id: 39, name: "Validate Params", icon: "✓", phase: "execution", description: "Check parameters" },
  { id: 40, name: "Check Rate Limit", icon: "✓", phase: "execution", description: "SCB: 100/day available" },
  { id: 41, name: "Check Cache", icon: "💭", phase: "execution", description: "No cached result" },
  { id: 42, name: "Prepare Call", icon: "🔧", phase: "execution", description: "Build API request" },
  { id: 43, name: "Set Params", icon: "⚙️", phase: "execution", description: "municipality=Stockholm" },
  { id: 44, name: "Validate Tool", icon: "✓", phase: "execution", description: "Tool ready" },
  { id: 45, name: "Tool Resolution Done", icon: "✓", phase: "execution", description: "Ready to execute" },
  
  // Execution (46-50)
  { id: 46, name: "Generate Call", icon: "🤖", phase: "execution", description: "Model: GPT-4o" },
  { id: 47, name: "Function Call", icon: "🔧", phase: "execution", description: "get_population_statistics" },
  { id: 48, name: "Validate Call", icon: "✓", phase: "execution", description: "Call structure OK" },
  { id: 49, name: "Execute Tool", icon: "📡", phase: "execution", description: "Running external API" },
  { id: 50, name: "Execution Started", icon: "✓", phase: "execution", description: "API call in progress" },
  
  // API Call Detail (51-60)
  { id: 51, name: "Prepare HTTP", icon: "📡", phase: "api", description: "Build HTTP request" },
  { id: 52, name: "Set Headers", icon: "📡", phase: "api", description: "Authorization, Content-Type" },
  { id: 53, name: "POST to SCB", icon: "📡", phase: "api", description: "api.scb.se/OV0104" },
  { id: 54, name: "Wait Response", icon: "⏳", phase: "api", description: "Waiting... (1.2s)" },
  { id: 55, name: "Response: 200 OK", icon: "✓", phase: "api", description: "Success status" },
  { id: 56, name: "Parse JSON", icon: "💭", phase: "api", description: "Extract data structure" },
  { id: 57, name: "Extract Data", icon: "💭", phase: "api", description: "Get population values" },
  { id: 58, name: "Validate Data", icon: "✓", phase: "api", description: "Schema validation passed" },
  { id: 59, name: "Cache Response", icon: "⚙️", phase: "api", description: "Save for 1 hour" },
  { id: 60, name: "API Call Complete", icon: "✓", phase: "api", description: "Data retrieved" },
  
  // Post-Processing (61-65)
  { id: 61, name: "Extract Fields", icon: "💭", phase: "validation", description: "Get relevant fields" },
  { id: 62, name: "Transform Format", icon: "💭", phase: "validation", description: "Convert to standard format" },
  { id: 63, name: "Add Metadata", icon: "⚙️", phase: "validation", description: "Source, timestamp, version" },
  { id: 64, name: "Validate Schema", icon: "✓", phase: "validation", description: "Output schema OK" },
  { id: 65, name: "Post-Process Done", icon: "✓", phase: "validation", description: "Data ready for synthesis" },
  
  // Safety & Validation (66-70)
  { id: 66, name: "Orchestration Guard", icon: "🛡️", phase: "validation", description: "Run safety checks" },
  { id: 67, name: "Loop Count: 1/3", icon: "✓", phase: "validation", description: "Under limit" },
  { id: 68, name: "Validate Sources", icon: "✓", phase: "validation", description: "SCB is trusted" },
  { id: 69, name: "Run Critic", icon: "🤖", phase: "validation", description: "Model: Claude Sonnet" },
  { id: 70, name: "Critic: OK", icon: "✓", phase: "validation", description: "Quality approved" },
  
  // Synthesis (71-77)
  { id: 71, name: "Generate Response", icon: "🤖", phase: "output", description: "Model: GPT-4o" },
  { id: 72, name: "Synthesis Prompt", icon: "💭", phase: "output", description: "845 tokens sent" },
  { id: 73, name: "Response Generated", icon: "✓", phase: "output", description: "Answer created" },
  { id: 74, name: "Add Citations", icon: "📖", phase: "output", description: "Add [1] SCB reference" },
  { id: 75, name: "Format Markdown", icon: "💭", phase: "output", description: "Apply formatting" },
  { id: 76, name: "Validate Output", icon: "✓", phase: "output", description: "Response validated" },
  { id: 77, name: "Synthesis Complete", icon: "✓", phase: "output", description: "Ready to return" },
  
  // Finalization (78-80)
  { id: 78, name: "Save Checkpoint", icon: "⚙️", phase: "output", description: "Persist final state" },
  { id: 79, name: "Prepare Response", icon: "💭", phase: "output", description: "Package for return" },
  { id: 80, name: "END", icon: "⏹️", phase: "output", description: "Execution complete" }
];




// ==================== REAL-TIME TYPING DEMO DATA ====================
// Constants for truncation and timing
const MAX_RESPONSE_LENGTH = 200;
const MAX_SYNTHESIS_LENGTH = 350;
const QUESTION_ROTATION_INTERVAL = 45000; // 45 seconds

// Question data interface
interface QuestionData {
  id: string;
  question: string;
  models: Array<{
    name: string;
    response: string;
  }>;
  oneseek_response: string;
}

// Helper to extract response text from JSON string
const extractResponse = (jsonStr: string): string => {
  if (jsonStr === "Model unavailable") {
    return "Model currently unavailable";
  }
  try {
    const parsed = JSON.parse(jsonStr);
    if (parsed.status === "error") {
      return "Model currently unavailable";
    }
    return parsed.response || parsed.summary || "No response available";
  } catch (error) {
    console.warn("Failed to parse model response:", jsonStr.substring(0, 100), error);
    return jsonStr;
  }
};

// Map model names to MODEL_DATA
const getModelData = (modelName: string) => {
  const normalizedName = modelName.toLowerCase();
  const modelMap: Record<string, string> = {
    chatgpt: "gpt",
    gpt: "gpt",
    claude: "claude",
    gemini: "gemini",
    deepseek: "deepseek",
    perplexity: "perplexity",
    grok: "grok",
  };
  const mappedId = modelMap[normalizedName] || normalizedName;
  return MODEL_DATA.find((m) => m.id === mappedId) || MODEL_DATA[0];
};

// ==================== TYPING ANIMATION COMPONENT ====================
const TypingText = ({ text, speed = 30, onComplete }: { text: string; speed?: number; onComplete?: () => void }) => {
  const [displayedText, setDisplayedText] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showCursor, setShowCursor] = useState(true);

  // Reset when text changes
  useEffect(() => {
    setDisplayedText("");
    setCurrentIndex(0);
  }, [text]);

  useEffect(() => {
    if (currentIndex < text.length) {
      const timeout = setTimeout(() => {
        setDisplayedText(prev => prev + text[currentIndex]);
        setCurrentIndex(prev => prev + 1);
      }, speed);
      return () => clearTimeout(timeout);
    } else if (currentIndex === text.length && currentIndex > 0 && onComplete) {
      // Only call onComplete once when we reach the end
      onComplete();
    }
  }, [currentIndex, text, speed]); // text instead of text.length to properly track changes

  useEffect(() => {
    const cursorInterval = setInterval(() => {
      setShowCursor(prev => !prev);
    }, 530);
    return () => clearInterval(cursorInterval);
  }, []);

  return (
    <span className="inline">
      {displayedText}
      {currentIndex < text.length && (
        <span className={cn("inline-block w-0.5 h-4 ml-0.5 bg-orange-500 dark:bg-orange-400", showCursor ? "opacity-100" : "opacity-0")}>
          |
        </span>
      )}
    </span>
  );
};

// ==================== STREAMING MARKDOWN COMPONENT ====================
const StreamingMarkdown = ({ 
  content, 
  chunkSize = 150, 
  chunkDelay = 80,
  onComplete 
}: { 
  content: string; 
  chunkSize?: number; 
  chunkDelay?: number;
  onComplete?: () => void;
}) => {
  const [displayedContent, setDisplayedContent] = useState("");
  const [currentChunk, setCurrentChunk] = useState(0);
  const [isComplete, setIsComplete] = useState(false);

  // Reset when content changes
  useEffect(() => {
    setDisplayedContent("");
    setCurrentChunk(0);
    setIsComplete(false);
  }, [content]);

  // Stream chunks
  useEffect(() => {
    if (currentChunk * chunkSize < content.length && !isComplete) {
      const timeout = setTimeout(() => {
        const nextChunk = content.slice(0, (currentChunk + 1) * chunkSize);
        setDisplayedContent(nextChunk);
        setCurrentChunk(prev => prev + 1);
        
        // Check if complete
        if (nextChunk.length >= content.length) {
          setDisplayedContent(content);
          setIsComplete(true);
          if (onComplete) {
            onComplete();
          }
        }
      }, chunkDelay);
      
      return () => clearTimeout(timeout);
    }
  }, [currentChunk, content, chunkSize, chunkDelay, isComplete, onComplete]);

  return (
    <div className="prose prose-sm dark:prose-invert max-w-none">
      <ReactMarkdown 
        remarkPlugins={[remarkGfm]}
        components={{
          h3: ({node, ...props}) => <h3 className="text-base font-bold mt-4 mb-2 text-neutral-900 dark:text-neutral-100" {...props} />,
          p: ({node, ...props}) => <p className="my-2 text-sm text-neutral-700 dark:text-neutral-300" {...props} />,
          ul: ({node, ...props}) => <ul className="my-2 ml-4 list-disc text-sm text-neutral-700 dark:text-neutral-300" {...props} />,
          ol: ({node, ...props}) => <ol className="my-2 ml-4 list-decimal text-sm text-neutral-700 dark:text-neutral-300" {...props} />,
          li: ({node, ...props}) => <li className="my-1" {...props} />,
          strong: ({node, ...props}) => <strong className="font-semibold text-neutral-900 dark:text-neutral-100" {...props} />,
          em: ({node, ...props}) => <em className="italic" {...props} />,
          blockquote: ({node, ...props}) => <blockquote className="border-l-4 border-orange-500 pl-4 my-2 italic text-neutral-600 dark:text-neutral-400" {...props} />,
          table: ({node, ...props}) => (
            <div className="overflow-x-auto my-4">
              <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700 text-xs" {...props} />
            </div>
          ),
          thead: ({node, ...props}) => <thead className="bg-neutral-50 dark:bg-neutral-800" {...props} />,
          tbody: ({node, ...props}) => <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700" {...props} />,
          tr: ({node, ...props}) => <tr {...props} />,
          th: ({node, ...props}) => <th className="px-3 py-2 text-left text-xs font-semibold text-neutral-900 dark:text-neutral-100" {...props} />,
          td: ({node, ...props}) => <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300" {...props} />,
          code: ({node, inline, ...props}) => 
            inline ? (
              <code className="px-1 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-xs font-mono text-orange-600 dark:text-orange-400" {...props} />
            ) : (
              <code className="block p-2 rounded bg-neutral-100 dark:bg-neutral-800 text-xs font-mono overflow-x-auto" {...props} />
            ),
        }}
      >
        {displayedContent}
      </ReactMarkdown>
      {!isComplete && (
        <motion.span 
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1, repeat: Infinity }}
          className="inline-block w-1 h-4 ml-1 bg-orange-500 dark:bg-orange-400"
        />
      )}
    </div>
  );
};

// ==================== SIDE-BY-SIDE COMPARISON COMPONENT ====================
const SideBySideComparison = () => {
  const [questions, setQuestions] = useState<QuestionData[]>([]);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [typingComplete, setTypingComplete] = useState<boolean[]>([false, false, false, false, false, false]);
  const [showSynthesis, setShowSynthesis] = useState(false);
  const [synthesisComplete, setSynthesisComplete] = useState(false);
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  // Load questions from JSON
  useEffect(() => {
    fetch("/compare_questions.json")
      .then((res) => res.json())
      .then((data: QuestionData[]) => {
        setQuestions(data);
      })
      .catch((err) => console.error("Failed to load questions:", err));
  }, []);

  // Show synthesis after all 6 models complete
  useEffect(() => {
    if (typingComplete.every((c) => c) && !showSynthesis) {
      const timeout = setTimeout(() => {
        setShowSynthesis(true);
      }, 800);
      return () => clearTimeout(timeout);
    }
  }, [typingComplete, showSynthesis]);

  // Rotate to next question after synthesis completes (45s total cycle)
  useEffect(() => {
    if (synthesisComplete && questions.length > 0) {
      const timeout = setTimeout(() => {
        setCurrentQuestionIndex((prev) => (prev + 1) % questions.length);
        setTypingComplete([false, false, false, false, false, false]);
        setShowSynthesis(false);
        setSynthesisComplete(false);
      }, QUESTION_ROTATION_INTERVAL);
      return () => clearTimeout(timeout);
    }
  }, [synthesisComplete, questions.length]);

  const currentQuestion = questions[currentQuestionIndex];

  // Memoize callbacks to prevent infinite loops
  const handleModelComplete = useCallback((index: number) => {
    setTypingComplete(prev => {
      const updated = [...prev];
      updated[index] = true;
      return updated;
    });
  }, []);

  const handleSynthesisComplete = useCallback(() => {
    setSynthesisComplete(true);
  }, []);

  if (!currentQuestion) {
    return (
      <div ref={ref} className="relative">
        <div className="text-center text-neutral-500" role="status" aria-live="polite">
          Loading questions...
        </div>
      </div>
    );
  }

  return (
    <div ref={ref} className="relative">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="relative rounded-3xl border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br from-neutral-50/80 to-neutral-100/80 dark:from-neutral-900/50 dark:to-neutral-900/30 p-2 backdrop-blur-xl shadow-2xl"
      >
        {/* Glow effect */}
        <div className="absolute -inset-0.5 bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-blue-500/10 rounded-3xl blur-xl" />
        
        <div className="relative rounded-2xl bg-white/90 dark:bg-neutral-950/90 p-6 md:p-8 backdrop-blur-sm">
          {/* Question indicator dots */}
          <div className="mb-4 flex items-center justify-center gap-2">
            {questions.map((_, index) => (
              <div
                key={index}
                className={cn(
                  "h-2 w-2 rounded-full transition-all duration-300",
                  index === currentQuestionIndex ? "bg-blue-500 scale-125" : "bg-neutral-300 dark:bg-neutral-700"
                )}
              />
            ))}
          </div>

          {/* Question */}
          <div className="mb-6 pb-4 border-b border-neutral-200 dark:border-neutral-800">
            <p className="text-sm font-medium text-neutral-500 dark:text-neutral-400 mb-2">FRÅGA</p>
            <p className="text-base md:text-lg font-semibold text-neutral-900 dark:text-white">
              {currentQuestion.question}
            </p>
          </div>

          {/* 6 models in grid: 3 cols on desktop, 2 on tablet, 1 on mobile */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {currentQuestion.models.map((model, index) => {
              const modelData = getModelData(model.name);
              const modelLogoKey = model.name.toLowerCase() === "chatgpt" ? "gpt" : model.name.toLowerCase();
              const responseText = extractResponse(model.response);
              
              return (
                <motion.div
                  key={`${currentQuestion.id}-${model.name}-${index}`}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: index * 0.1 }}
                  className="group relative"
                >
                  <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 hover:border-blue-200 dark:hover:border-blue-900 transition-colors duration-300 h-full flex flex-col">
                    {/* Model Header */}
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div className="relative size-10 flex-shrink-0">
                          {MODEL_LOGOS[modelLogoKey] ? (
                            <Image
                              src={MODEL_LOGOS[modelLogoKey]}
                              alt={`${modelData.name} logo`}
                              width={40}
                              height={40}
                              className="object-contain"
                            />
                          ) : (
                            <div className="size-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white font-bold shadow-lg">
                              {modelData.name[0]}
                            </div>
                          )}
                        </div>
                        <div>
                          <h3 className="text-xs font-bold text-neutral-900 dark:text-white">{modelData.name}</h3>
                          <p className="text-[10px] text-neutral-500 dark:text-neutral-400">{modelData.provider}</p>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-0.5">
                        <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400 px-1.5 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/50">
                          {modelData.latency}
                        </span>
                        <span className="text-[9px] text-neutral-400">{modelData.tokens}</span>
                      </div>
                    </div>

                    {/* Response with typing animation */}
                    <div className="flex-1 text-xs leading-relaxed text-neutral-700 dark:text-neutral-300 line-clamp-6">
                      <TypingText 
                        text={responseText.slice(0, MAX_RESPONSE_LENGTH)} 
                        speed={20}
                        onComplete={() => handleModelComplete(index)}
                      />
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>

          {/* OneSeek Synthesis Phase */}
          {showSynthesis && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className="mt-6"
            >
              <div className="relative rounded-2xl bg-gradient-to-br from-orange-500/10 via-amber-500/10 to-orange-500/10 dark:from-orange-500/20 dark:via-amber-500/20 dark:to-orange-500/20 border border-orange-200/50 dark:border-orange-800/50 p-6 backdrop-blur-sm">
                {/* Sparkle animation */}
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 flex items-center gap-2 bg-gradient-to-r from-orange-500 to-amber-500 text-white px-4 py-1.5 rounded-full text-xs font-bold shadow-lg">
                  <span className="animate-pulse">✨</span>
                  <span>OneSeek Syntes</span>
                </div>

                {/* Synthesis header */}
                <div className="flex items-center gap-3 mb-4 mt-2">
                  <div className="relative size-12 flex-shrink-0">
                    <Image
                      src="/model-logos/chatgpt.png"
                      alt="OneSeek logo"
                      width={48}
                      height={48}
                      className="object-contain"
                    />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-neutral-900 dark:text-white">OneSeek Sammanfattning</h3>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400">Verifierad • Med källor</p>
                  </div>
                </div>

                {/* Synthesized response */}
                <div className="text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
                  <TypingText 
                    text={currentQuestion.oneseek_response.slice(0, MAX_SYNTHESIS_LENGTH)}
                    speed={25}
                    onComplete={handleSynthesisComplete}
                  />
                </div>

                {/* Citation badges */}
                {synthesisComplete && (
                  <motion.div 
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4 }}
                    className="mt-4 flex flex-wrap items-center gap-2"
                  >
                    <span className="text-xs text-neutral-500 dark:text-neutral-400">Källor:</span>
                    <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                      [1] SCB
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-purple-50 dark:bg-purple-950/30 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
                      [2] Tavily
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 ml-auto">
                      <svg className="size-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                      Verifierat
                    </span>
                  </motion.div>
                )}
              </div>
            </motion.div>
          )}
        </div>
      </motion.div>
    </div>
  );
};

// ==================== SECTION 1: HERO WITH SIDE-BY-SIDE TYPING DEMO ====================

const HeroSection = () => {
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
Se AI-modeller svara i realtid, side by side. Jämför latency, kvalitet och precision.
</motion.p>

<motion.div 
className="mt-12 flex gap-4 justify-center flex-wrap"
transition={{ duration: 0.6, delay: 0.4, ease: [0.16, 1, 0.3, 1] }}
>
<Link
href="/dashboard/public/new-chat"
className="group relative h-14 px-10 rounded-2xl bg-black dark:bg-white text-white dark:text-black text-base font-semibold transition-all duration-300 hover:scale-105 hover:shadow-2xl hover:shadow-black/20 dark:hover:shadow-white/20 flex items-center justify-center overflow-hidden"
>
<span className="relative z-10">Skapa konto</span>
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

{/* Side-by-side typing demo */}
<motion.div 
className="mt-20 md:mt-32 mx-auto max-w-6xl"
transition={{ duration: 0.8, delay: 0.6, ease: [0.16, 1, 0.3, 1] }}
>
<SideBySideComparison />
</motion.div>
</div>
</section>
);
};

// ==================== SECTION 2: INTERACTIVE API SKILL TREE + CHAT DEMO ====================

interface APITool {
  id: string;
  name: string;
  category: string;
  logo: string;
  description: string;
}

const APIReasoningDemo = () => {
  const [currentScenario, setCurrentScenario] = useState(0);
  const [chatMessages, setChatMessages] = useState<any[]>([]);
  const [activeAPIs, setActiveAPIs] = useState<string[]>([]);
  const sectionRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(sectionRef, { once: true, margin: "-100px" });

  // API Tools Tree
  const apiTools: APITool[] = [
    { id: 'scb', name: 'SCB', category: 'Statistik', logo: '/api-logos/scb-logo.png', description: 'Statistiska centralbyrån - Befolkning, ekonomi' },
    { id: 'kolada', name: 'Kolada', category: 'Statistik', logo: '/api-logos/kolada-logo.png', description: 'Kommun- och landstingsdata' },
    { id: 'smhi', name: 'SMHI', category: 'Väder', logo: '/api-logos/smhi-logo.png', description: 'Väderdata och prognoser' },
    { id: 'trafikverket', name: 'Trafikverket', category: 'Transport', logo: '/api-logos/trafikverket-logo.png', description: 'Trafikinfo och störningar' },
    { id: 'riksdagen', name: 'Riksdagen', category: 'Politik', logo: '/api-logos/riksdagen-logo.png', description: 'Propositioner och debatter' },
    { id: 'bolagsverket', name: 'Bolagsverket', category: 'Företag', logo: '/api-logos/bolagsverket-logo.png', description: 'Företagsinformation' },
    { id: 'blocket', name: 'Blocket', category: 'Marknad', logo: '/api-logos/blocket-logo.png', description: 'Köp och sälj annonser' },
    { id: 'tradera', name: 'Tradera', category: 'Marknad', logo: '/api-logos/tradera-logo.png', description: 'Auktioner och handel' },
    { id: 'arbetsformedlingen', name: 'Arbetsförmedlingen', category: 'Arbetsmarknad', logo: '/api-logos/arbetsformedlingen-logo.png', description: 'Lediga jobb och platsannonser' },
    { id: 'libris', name: 'Libris', category: 'Bibliotek', logo: '/api-logos/libris-logo.png', description: 'Svensk nationalbibliografi' },
    { id: 'skolverket', name: 'Skolverket', category: 'Utbildning', logo: '/api-logos/skolverket-logo.png', description: 'Skoldata och statistik' },
    { id: 'trafiklab', name: 'Trafiklab', category: 'Transport', logo: '/api-logos/trafiklab-logo.png', description: 'Kollektivtrafik och tidtabeller' },
    { id: 'tavily', name: 'Tavily', category: 'Verifiering', logo: '/api-logos/tavily-logo.png', description: 'Faktakontroll och källor' },
  ];

  const scenarios = [
    {
      question: "Hur många invånare har Stockholm?",
      activeTools: ['scb'],
      messages: [
        { type: 'user', text: 'Hur många invånare har Stockholm?' },
        { type: 'system', text: '🔍 Analyserar fråga: Befolkningsstatistik för Stockholm' },
        { type: 'system', text: '⚡ Väljer verktyg: SCB API' },
        { type: 'api', text: '📡 Anropar SCB: get_population_statistics(municipality="Stockholm")' },
        { type: 'assistant', text: 'Stockholm har cirka 975 000 invånare enligt den senaste befolkningsstatistiken från SCB (2023).' },
        { type: 'sources', sources: ['SCB'] }
      ]
    },
    {
      question: "Hur blir vädret i Göteborg imorgon?",
      activeTools: ['smhi'],
      messages: [
        { type: 'user', text: 'Hur blir vädret i Göteborg imorgon?' },
        { type: 'system', text: '🔍 Analyserar fråga: Väderprogos för Göteborg' },
        { type: 'system', text: '⚡ Väljer verktyg: SMHI API' },
        { type: 'api', text: '📡 Anropar SMHI: get_weather_forecast(city="Göteborg", date="tomorrow")' },
        { type: 'assistant', text: 'Imorgon blir det delvis molnigt i Göteborg med temperaturer runt 15°C och lätt vind från sydväst.' },
        { type: 'sources', sources: ['SMHI'] }
      ]
    },
    {
      question: "Är det störningar på E4 just nu?",
      activeTools: ['trafikverket'],
      messages: [
        { type: 'user', text: 'Är det störningar på E4 just nu?' },
        { type: 'system', text: '🔍 Analyserar fråga: Trafikläge på E4' },
        { type: 'system', text: '⚡ Väljer verktyg: Trafikverket API' },
        { type: 'api', text: '📡 Anropar Trafikverket: get_traffic_status(road="E4")' },
        { type: 'assistant', text: 'Inga större störningar rapporterade på E4 för tillfället. Normalt trafikflöde i båda riktningar.' },
        { type: 'sources', sources: ['Trafikverket'] }
      ]
    },
    {
      question: "Befolkningstillväxt i Stockholm och dagens väder?",
      activeTools: ['scb', 'smhi'],
      messages: [
        { type: 'user', text: 'Befolkningstillväxt i Stockholm och dagens väder?' },
        { type: 'system', text: '🔍 Analyserar fråga: Komplex fråga med två delar' },
        { type: 'system', text: '⚡ Väljer verktyg: SCB API + SMHI API' },
        { type: 'api', text: '📡 Anropar SCB: get_population_growth(municipality="Stockholm")' },
        { type: 'api', text: '📡 Anropar SMHI: get_current_weather(city="Stockholm")' },
        { type: 'assistant', text: 'Stockholm har vuxit med cirka 15 000 invånare det senaste året till 975 000. Vädret idag: Delvis molnigt, 12°C.' },
        { type: 'sources', sources: ['SCB', 'SMHI'] }
      ]
    }
  ];

  // Animation sequence
  useEffect(() => {
    if (!isInView) return;

    const sequence = async () => {
      const data = scenarios[currentScenario];
      setChatMessages([]);
      setActiveAPIs([]);

      // Add messages one by one
      for (let i = 0; i < data.messages.length; i++) {
        await new Promise(resolve => setTimeout(resolve, i === 0 ? 500 : 1500));
        
        const message = data.messages[i];
        setChatMessages(prev => [...prev, message]);

        // Activate APIs when api message appears
        if (message.type === 'api') {
          setActiveAPIs(data.activeTools);
        }

        // Chat container handles scroll automatically with overflow-y-auto
        // NO scrollIntoView to prevent page jumping
      }

      // Wait before next scenario
      await new Promise(resolve => setTimeout(resolve, 3000));
      setCurrentScenario((prev) => (prev + 1) % scenarios.length);
    };

    sequence();
  }, [currentScenario, isInView]);

  return (
    <section ref={sectionRef} className="relative py-24 md:py-32 bg-gradient-to-b from-white via-neutral-50/50 to-white dark:from-neutral-950 dark:via-neutral-900/50 dark:to-neutral-950 border-y border-neutral-100 dark:border-neutral-800/50 overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-gradient-to-r from-blue-500/5 via-purple-500/5 to-blue-500/5 dark:from-blue-500/10 dark:via-purple-500/10 dark:to-blue-500/10 rounded-full blur-3xl" />
      </div>

      <div className="mx-auto max-w-7xl px-6">
        {/* Header */}
        <motion.div 
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-2xl md:text-4xl font-bold tracking-tight text-neutral-900 dark:text-white mb-4">
            OneSeek Reasoning i Realtid
          </h2>
          <p className="text-base md:text-lg text-neutral-600 dark:text-neutral-400">
            Se hur OneSeek analyserar frågor och anropar svenska datakällor
          </p>
        </motion.div>

        {/* Two-Column Layout */}
        <div className="grid md:grid-cols-[400px_1fr] gap-8">
          
          {/* Left: API Skill Tree */}
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6 }}
            className="relative"
          >
            <div className="sticky top-24 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-md p-6 shadow-xl">
              <h3 className="text-lg font-bold text-neutral-900 dark:text-white mb-1">Svenska Datakällor</h3>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-6">13 API-integrationer</p>
              
              {/* API Tools List - Fixed max height to match chat */}
              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-neutral-300 dark:scrollbar-thumb-neutral-700 scrollbar-track-transparent">
                {apiTools.map((tool) => {
                  const isActive = activeAPIs.includes(tool.id);
                  return (
                    <motion.div
                      key={tool.id}
                      animate={{
                        scale: isActive ? 1.02 : 1,
                        borderColor: isActive ? 'rgb(34, 197, 94)' : 'rgb(229, 231, 235)'
                      }}
                      transition={{ duration: 0.3 }}
                      className={cn(
                        "relative p-3 rounded-xl border-2 transition-all duration-300",
                        isActive 
                          ? "bg-emerald-50/80 dark:bg-emerald-950/30 border-emerald-500 shadow-lg shadow-emerald-500/20" 
                          : "bg-neutral-50/50 dark:bg-neutral-800/50 border-neutral-200 dark:border-neutral-700"
                      )}
                    >
                      {isActive && (
                        <motion.div
                          className="absolute -inset-0.5 bg-gradient-to-r from-emerald-500/20 to-teal-500/20 rounded-xl blur-sm -z-10"
                          animate={{ opacity: [0.5, 1, 0.5] }}
                          transition={{ duration: 1.5, repeat: Infinity }}
                        />
                      )}
                      <div className="flex items-center gap-3">
                        <div className="relative">
                          <Image
                            src={tool.logo}
                            alt={tool.name}
                            width={32}
                            height={32}
                            className="object-contain"
                          />
                          {isActive && (
                            <motion.div
                              className="absolute -inset-1 bg-emerald-500/30 rounded-full blur"
                              animate={{ scale: [1, 1.2, 1], opacity: [0.5, 0.8, 0.5] }}
                              transition={{ duration: 1, repeat: Infinity }}
                            />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className={cn(
                              "text-sm font-semibold",
                              isActive ? "text-emerald-700 dark:text-emerald-300" : "text-neutral-900 dark:text-white"
                            )}>
                              {tool.name}
                            </p>
                            {isActive && (
                              <motion.span
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                className="flex items-center justify-center size-5 rounded-full bg-emerald-500 text-white text-xs font-bold"
                              >
                                ✓
                              </motion.span>
                            )}
                          </div>
                          <p className="text-xs text-neutral-500 dark:text-neutral-400 line-clamp-1">
                            {tool.description}
                          </p>
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          </motion.div>

          {/* Right: Chat View */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="relative"
          >
            <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-md shadow-xl overflow-hidden">
              {/* Chat Header */}
              <div className="border-b border-neutral-200 dark:border-neutral-800 p-4 bg-neutral-50/50 dark:bg-neutral-800/50">
                <div className="flex items-center gap-3">
                  <div className="size-2 rounded-full bg-emerald-500 animate-pulse" />
                  <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">OneSeek Agent Chat</h4>
                  <span className="ml-auto text-xs text-neutral-500 dark:text-neutral-400">Live</span>
                </div>
              </div>

              {/* Chat Messages */}
              <div className="h-[600px] overflow-y-auto p-6 space-y-4">
                {chatMessages.map((message, index) => {
                  if (message.type === 'user') {
                    return (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.3 }}
                        className="flex justify-end"
                      >
                        <div className="max-w-[80%] p-3 rounded-2xl rounded-tr-sm bg-blue-500 text-white text-sm">
                          {message.text}
                        </div>
                      </motion.div>
                    );
                  }

                  if (message.type === 'system') {
                    return (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.3 }}
                        className="flex justify-start"
                      >
                        <div className="max-w-[80%] p-3 rounded-2xl rounded-tl-sm bg-purple-50 dark:bg-purple-950/30 text-purple-700 dark:text-purple-300 text-sm border border-purple-200 dark:border-purple-800">
                          {message.text}
                        </div>
                      </motion.div>
                    );
                  }

                  if (message.type === 'api') {
                    return (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.3 }}
                        className="flex justify-center"
                      >
                        <div className="px-4 py-2 rounded-full bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 text-xs font-mono border border-emerald-200 dark:border-emerald-800">
                          {message.text}
                        </div>
                      </motion.div>
                    );
                  }

                  if (message.type === 'assistant') {
                    return (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.3 }}
                        className="flex justify-start"
                      >
                        <div className="max-w-[80%] p-4 rounded-2xl rounded-tl-sm bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm border border-neutral-200 dark:border-neutral-700 shadow-sm">
                          <TypingText text={message.text} speed={25} />
                        </div>
                      </motion.div>
                    );
                  }

                  if (message.type === 'sources') {
                    return (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.3 }}
                        className="flex justify-start ml-4"
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs text-neutral-500 dark:text-neutral-400">Källor:</span>
                          {message.sources.map((source: string, i: number) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-orange-50 dark:bg-orange-950/30 text-orange-700 dark:text-orange-300 border border-orange-200 dark:border-orange-800"
                            >
                              [{i + 1}] {source}
                            </span>
                          ))}
                        </div>
                      </motion.div>
                    );
                  }

                  return null;
                })}
                <div ref={chatEndRef} />
              </div>
            </div>
          </motion.div>

        </div>
      </div>
    </section>
  );
};

// ==================== SECTION 3: COMPARE SHOWCASE ====================

const CompareShowcase = () => {
  // Map performanceScore to 'progress' for animation compatibility with Framer Motion
  const models = MODEL_DATA.map(m => ({ ...m, progress: m.performanceScore }));
  
  // State for metrics drawer
  const [drawerExpanded, setDrawerExpanded] = React.useState(false);
  
  // Auto-cycle through evaluation metrics every 3 seconds
  React.useEffect(() => {
    const interval = setInterval(() => {
      setCurrentMetric((prev) => (prev + 1) % EVALUATION_METRICS.length);
    }, 3000);
    
    return () => clearInterval(interval);
  }, []);

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

              <div className="size-10 rounded-md mx-auto border border-neutral-200/60 dark:border-neutral-800/60 bg-white dark:bg-neutral-900 flex items-center justify-center p-1.5 shadow-sm group-hover:shadow-md transition-shadow">
                <Image
                  src={MODEL_LOGOS[model.id]}
                  alt={model.name}
                  width={40}
                  height={40}
                  className="object-contain"
                />
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

        {/* Interactive Metrics Drawer */}
        <motion.div
          className="max-w-5xl mx-auto mb-12"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
        >
          {/* Drawer Toggle Button */}
          <motion.button
            onClick={() => setDrawerExpanded(!drawerExpanded)}
            className="w-full rounded-2xl border border-orange-200 dark:border-orange-800 bg-gradient-to-r from-orange-50/80 via-amber-50/80 to-orange-50/80 dark:from-orange-950/30 dark:via-amber-950/30 dark:to-orange-950/30 backdrop-blur-md shadow-lg hover:shadow-xl transition-all duration-300 p-6 cursor-pointer group relative overflow-hidden"
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
          >
            {/* Subtle pulse effect */}
            <motion.div 
              className="absolute inset-0 bg-gradient-to-r from-orange-500/10 via-amber-500/10 to-orange-500/10"
              animate={{ opacity: [0.5, 0.8, 0.5] }}
              transition={{ duration: 2, repeat: Infinity }}
            />

            <div className="relative flex items-center justify-between">
              <div className="flex items-center gap-4">
                <span className="text-3xl">📊</span>
                <div className="text-left">
                  <p className="text-sm font-semibold text-orange-600 dark:text-orange-400">VÅR UTVÄRDERING</p>
                  <h3 className="text-lg font-bold text-neutral-900 dark:text-white">
                    Se alla utvärderingsmetrics
                  </h3>
                  <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
                    {EVALUATION_METRICS.length} kategorier som utvärderar modellernas prestanda
                  </p>
                </div>
              </div>
              
              <motion.div
                animate={{ rotate: drawerExpanded ? 180 : 0 }}
                transition={{ duration: 0.3 }}
                className="text-2xl text-orange-600 dark:text-orange-400"
              >
                ↓
              </motion.div>
            </div>
          </motion.button>

          {/* Expandable Drawer Content */}
          <motion.div
            initial={false}
            animate={{
              height: drawerExpanded ? "auto" : 0,
              opacity: drawerExpanded ? 1 : 0
            }}
            transition={{
              height: { duration: 0.4, ease: [0.4, 0, 0.2, 1] },
              opacity: { duration: 0.3, delay: drawerExpanded ? 0.1 : 0 }
            }}
            className="overflow-hidden"
          >
            <div className="pt-6">
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                {EVALUATION_METRICS.map((metric, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, y: 20 }}
                    animate={drawerExpanded ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
                    transition={{ delay: index * 0.05, duration: 0.3 }}
                    whileHover={{ y: -4, scale: 1.02 }}
                    className="rounded-xl border border-neutral-200/60 dark:border-neutral-800/60 bg-gradient-to-br from-white/90 to-neutral-50/90 dark:from-neutral-900/60 dark:to-neutral-900/40 backdrop-blur-md p-4 shadow-sm hover:shadow-md hover:border-orange-300/60 dark:hover:border-orange-700/60 transition-all duration-300 group"
                  >
                    <div className="flex items-start gap-3 mb-3">
                      <span className="text-2xl flex-shrink-0">{metric.icon}</span>
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-bold text-neutral-900 dark:text-white group-hover:text-orange-600 dark:group-hover:text-orange-400 transition-colors">
                          {metric.category}
                        </h4>
                        <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1 leading-relaxed">
                          {metric.description}
                        </p>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-[10px] text-neutral-500 dark:text-neutral-500">
                        <span>Viktighet</span>
                        <span className="text-orange-600 dark:text-orange-400 font-semibold">Hög</span>
                      </div>
                      <div className="h-1 w-full bg-neutral-200 dark:bg-neutral-800 rounded-full overflow-hidden">
                        <motion.div
                          className="h-full bg-gradient-to-r from-orange-500 to-amber-500"
                          initial={{ width: 0 }}
                          animate={drawerExpanded ? { width: "90%" } : { width: 0 }}
                          transition={{ delay: index * 0.05 + 0.2, duration: 0.6 }}
                        />
                      </div>
                    </div>

                    <div className="mt-3 pt-3 border-t border-neutral-200/60 dark:border-neutral-800/60">
                      <p className="text-[10px] text-neutral-500 dark:text-neutral-500 font-medium mb-1">
                        Varför viktigt:
                      </p>
                      <p className="text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed line-clamp-2">
                        {metric.importance}
                      </p>
                    </div>
                  </motion.div>
                ))}
              </div>

              {/* Additional info when expanded */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={drawerExpanded ? { opacity: 1 } : { opacity: 0 }}
                transition={{ delay: 0.4 }}
                className="mt-6 p-4 rounded-xl bg-gradient-to-r from-blue-50/50 to-purple-50/50 dark:from-blue-950/20 dark:to-purple-950/20 border border-blue-200/60 dark:border-blue-800/60"
              >
                <p className="text-sm text-neutral-700 dark:text-neutral-300 text-center">
                  <span className="font-semibold text-blue-600 dark:text-blue-400">OneSeek utvärderar kontinuerligt</span> alla modeller mot dessa kriterier för att säkerställa bästa möjliga svar med svenska källor.
                </p>
              </motion.div>
            </div>
          </motion.div>
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

// ==================== SECTION 4: INTERACTIVE DEBATE DEMO ====================

interface DebateModel {
  id: string;
  name: string;
  logo: string;
  argument: string;
}

interface DebateRound {
  roundNumber: number;
  roundName: string;
  models: DebateModel[];
  color: string;
}

const DebateDemo = () => {
  const [currentRound, setCurrentRound] = useState(0);
  const [currentModel, setCurrentModel] = useState(0);
  const [phase, setPhase] = useState<'question' | 'round' | 'synthesis' | 'voting'>('question');
  const [modelComplete, setModelComplete] = useState(false);
  const sectionRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(sectionRef, { once: true, margin: "-100px" });

  const question = "Bör Sverige införa en 4-dagars arbetsvecka?";

  const rounds: DebateRound[] = [
    {
      roundNumber: 1,
      roundName: "Inledande Argument",
      color: "from-blue-500 to-cyan-500",
      models: [
        {
          id: "gemini",
          name: "Gemini",
          logo: MODEL_LOGOS.gemini,
          argument: "En 4-dagars arbetsvecka kan öka produktiviteten genom bättre work-life balance och minskad stress."
        },
        {
          id: "gpt",
          name: "ChatGPT",
          logo: MODEL_LOGOS.gpt,
          argument: "Studier visar att kortare arbetsveckor leder till högre medarbetarengagemang och bättre psykisk hälsa."
        },
        {
          id: "deepseek",
          name: "DeepSeek",
          logo: MODEL_LOGOS.deepseek,
          argument: "Vissa branscher kan få svårigheter med kontinuitet och kundservice vid kortare arbetsvecka."
        },
      ],
    },
    {
      roundNumber: 2,
      roundName: "Utveckling",
      color: "from-purple-500 to-pink-500",
      models: [
        {
          id: "claude",
          name: "Claude",
          logo: MODEL_LOGOS.claude,
          argument: "Ekonomisk analys visar blandade resultat - vissa företag ser ökad effektivitet, andra ökade kostnader."
        },
        {
          id: "grok",
          name: "Grok",
          logo: MODEL_LOGOS.grok,
          argument: "Vi måste beakta svenska arbetsmarknadsmodellen och kollektivavtal vid eventuella förändringar."
        },
        {
          id: "perplexity",
          name: "Perplexity",
          logo: MODEL_LOGOS.perplexity,
          argument: "Pilotprojekt från Island och Nya Zeeland visar lovande resultat med bibehållen eller ökad produktivitet."
        },
      ],
    },
    {
      roundNumber: 3,
      roundName: "Syntes",
      color: "from-orange-500 to-amber-500",
      models: [
        {
          id: "qwen",
          name: "Qwen",
          logo: MODEL_LOGOS.qwen,
          argument: "En gradvis övergång med branschspecifika lösningar verkar vara mest realistiskt för Sverige."
        },
        {
          id: "gemini",
          name: "Gemini",
          logo: MODEL_LOGOS.gemini,
          argument: "Viktigt att testa i pilotstudier innan nationell implementering för att identifiera utmaningar."
        },
        {
          id: "gpt",
          name: "ChatGPT (OneSeek)",
          logo: MODEL_LOGOS.gpt,
          argument: "SYNTES: 4-dagars arbetsvecka har potential men kräver noggrant övervägande. Rekommenderar pilotprogram i utvalda sektorer med tydliga KPI:er. Svenska arbetsmarknadsmodellen med stark facklig representation är en fördel för konstruktiv dialog. Fokusera på flexibilitet och medarbetarens behov."
        },
      ],
    },
  ];

  const votes = [
    { model: "Gemini", votes: 2, logo: MODEL_LOGOS.gemini },
    { model: "ChatGPT", votes: 3, logo: MODEL_LOGOS.gpt, winner: true },
    { model: "Claude", votes: 1, logo: MODEL_LOGOS.claude },
    { model: "Qwen", votes: 0, logo: MODEL_LOGOS.qwen },
  ];

  const handleModelComplete = useCallback(() => {
    setModelComplete(true);
  }, []);

  // Animation sequence
  useEffect(() => {
    if (!isInView) return;

    const sequence = async () => {
      // Question phase (2s)
      setPhase('question');
      setCurrentRound(0);
      setCurrentModel(0);
      setModelComplete(false);
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Round 1 (15s - 3 models * 5s each)
      setPhase('round');
      setCurrentRound(0);
      for (let i = 0; i < rounds[0].models.length; i++) {
        setCurrentModel(i);
        setModelComplete(false);
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
      await new Promise(resolve => setTimeout(resolve, 1000));

      // Round 2 (15s)
      setCurrentRound(1);
      for (let i = 0; i < rounds[1].models.length; i++) {
        setCurrentModel(i);
        setModelComplete(false);
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
      await new Promise(resolve => setTimeout(resolve, 1000));

      // Round 3 + Synthesis (18s)
      setCurrentRound(2);
      for (let i = 0; i < rounds[2].models.length; i++) {
        setCurrentModel(i);
        setModelComplete(false);
        if (i === rounds[2].models.length - 1) {
          // OneSeek synthesis - longer display
          await new Promise(resolve => setTimeout(resolve, 7000));
        } else {
          await new Promise(resolve => setTimeout(resolve, 5000));
        }
      }
      await new Promise(resolve => setTimeout(resolve, 1000));

      // Voting phase (8s)
      setPhase('voting');
      await new Promise(resolve => setTimeout(resolve, 8000));

      // Pause before loop (2s)
      await new Promise(resolve => setTimeout(resolve, 2000));
    };

    sequence();
  }, [isInView]);

  const currentRoundData = rounds[currentRound];

  return (
    <section 
      ref={sectionRef} 
      className="relative py-24 md:py-32 bg-gradient-to-b from-neutral-50 via-white to-neutral-50 dark:from-neutral-900 dark:via-neutral-950 dark:to-neutral-900 border-y border-neutral-100 dark:border-neutral-800/50 overflow-hidden"
    >
      {/* Background Effects */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-1/3 left-1/4 w-[500px] h-[500px] bg-gradient-to-r from-purple-500/5 via-pink-500/5 to-orange-500/5 dark:from-purple-500/10 dark:via-pink-500/10 dark:to-orange-500/10 rounded-full blur-3xl" />
      </div>

      <div className="mx-auto max-w-6xl px-6">
        {/* Header */}
        <motion.div 
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-purple-50 to-pink-50 dark:from-purple-950/30 dark:to-pink-950/30 border border-purple-100 dark:border-purple-800/50 mb-6">
            <span className="text-sm font-semibold text-transparent bg-clip-text bg-gradient-to-r from-purple-600 to-pink-600 dark:from-purple-400 dark:to-pink-400">
              🎭 DEBATT-LÄGE
            </span>
          </div>
          <h2 className="text-2xl md:text-4xl font-bold tracking-tight text-neutral-900 dark:text-white mb-4">
            AI-Modeller Diskuterar i 3 Rundor
          </h2>
          <p className="text-base md:text-lg text-neutral-600 dark:text-neutral-400">
            Se hur modeller utvecklar argument, bygger på varandras svar, och röstar på bästa argumentet
          </p>
        </motion.div>

        {/* Question Card */}
        <motion.div 
          className="mb-8 p-6 md:p-8 rounded-2xl border-2 border-purple-200 dark:border-purple-800/50 bg-gradient-to-br from-purple-50/80 to-pink-50/80 dark:from-purple-950/30 dark:to-pink-950/30 backdrop-blur-sm"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6 }}
        >
          <div className="flex items-center gap-4 mb-3">
            <div className="flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 text-white flex items-center justify-center font-bold text-lg">
              ?
            </div>
            <p className="text-xs font-semibold text-purple-600 dark:text-purple-400 uppercase tracking-wide">Debattfråga</p>
          </div>
          <p className="text-xl md:text-2xl font-semibold text-neutral-900 dark:text-white">{question}</p>
        </motion.div>

        {/* Round Header */}
        {phase === 'round' && (
          <motion.div 
            key={`round-${currentRound}`}
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mb-6 flex items-center justify-center gap-3"
          >
            <div className={cn(
              "px-6 py-3 rounded-full bg-gradient-to-r text-white font-bold shadow-lg",
              `${currentRoundData.color}`
            )}>
              Round {currentRoundData.roundNumber}: {currentRoundData.roundName}
            </div>
          </motion.div>
        )}

        {/* Model Cards */}
        {phase === 'round' && (
          <div className="space-y-4">
            {currentRoundData.models.map((model, idx) => (
              <motion.div
                key={`${currentRound}-${idx}`}
                initial={{ opacity: 0, x: -20 }}
                animate={{ 
                  opacity: idx <= currentModel ? 1 : 0.3,
                  x: 0 
                }}
                transition={{ duration: 0.5, delay: idx * 0.1 }}
                className={cn(
                  "p-6 rounded-2xl border backdrop-blur-md transition-all duration-500",
                  idx === currentModel 
                    ? "border-2 border-purple-400 dark:border-purple-600 bg-white dark:bg-neutral-900 shadow-lg shadow-purple-500/20"
                    : "border-neutral-200 dark:border-neutral-800 bg-white/60 dark:bg-neutral-900/60"
                )}
              >
                <div className="flex items-start gap-4">
                  <motion.div
                    animate={idx === currentModel ? { 
                      scale: [1, 1.05, 1],
                      rotate: [0, 5, -5, 0]
                    } : {}}
                    transition={{ duration: 2, repeat: Infinity }}
                  >
                    <Image
                      src={model.logo}
                      alt={model.name}
                      width={48}
                      height={48}
                      className="rounded-lg"
                    />
                  </motion.div>
                  <div className="flex-1">
                    <p className="text-sm font-bold text-neutral-900 dark:text-white mb-2">{model.name}</p>
                    <div className="text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
                      {idx === currentModel ? (
                        <TypingText 
                          text={model.argument}
                          speed={30}
                          onComplete={handleModelComplete}
                        />
                      ) : idx < currentModel ? (
                        model.argument
                      ) : (
                        <span className="text-neutral-400 dark:text-neutral-600">Väntar...</span>
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}

        {/* Voting Phase */}
        {phase === 'voting' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="space-y-6"
          >
            <div className="text-center mb-8">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-orange-50 to-amber-50 dark:from-orange-950/30 dark:to-amber-950/30 border border-orange-100 dark:border-orange-800/50 mb-4">
                <span className="text-sm font-semibold text-transparent bg-clip-text bg-gradient-to-r from-orange-600 to-amber-600 dark:from-orange-400 dark:to-amber-400">
                  🗳️ RÖSTNING
                </span>
              </div>
              <h3 className="text-xl md:text-2xl font-bold text-neutral-900 dark:text-white mb-2">
                Externa Modeller Röstar
              </h3>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                4 externa AI-modeller röstar på bästa argumentet från Round 3
              </p>
            </div>

            <div className="space-y-4">
              {votes.map((vote, idx) => (
                <motion.div
                  key={vote.model}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.5, delay: idx * 0.2 }}
                  className={cn(
                    "p-5 rounded-xl border-2 backdrop-blur-md",
                    vote.winner
                      ? "border-amber-400 dark:border-amber-600 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30"
                      : "border-neutral-200 dark:border-neutral-800 bg-white/80 dark:bg-neutral-900/80"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <Image
                        src={vote.logo}
                        alt={vote.model}
                        width={40}
                        height={40}
                        className="rounded-lg"
                      />
                      <div>
                        <p className="text-sm font-bold text-neutral-900 dark:text-white flex items-center gap-2">
                          {vote.model}
                          {vote.winner && <span className="text-lg">🏆</span>}
                        </p>
                        {vote.winner && (
                          <p className="text-xs text-amber-600 dark:text-amber-400 font-semibold">Vinnare</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <p className="text-2xl font-bold text-neutral-900 dark:text-white">{vote.votes}</p>
                        <p className="text-xs text-neutral-500 dark:text-neutral-400">röster</p>
                      </div>
                      <div className="w-24 h-3 bg-neutral-100 dark:bg-neutral-800 rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${(vote.votes / 6) * 100}%` }}
                          transition={{ duration: 1, delay: idx * 0.2 }}
                          className={cn(
                            "h-full rounded-full",
                            vote.winner
                              ? "bg-gradient-to-r from-amber-400 to-orange-500"
                              : "bg-neutral-300 dark:bg-neutral-700"
                          )}
                        />
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 1 }}
              className="mt-8 text-center p-4 rounded-xl bg-neutral-50 dark:bg-neutral-900/50 border border-neutral-200 dark:border-neutral-800"
            >
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                ✓ ChatGPT vinner med mest balanserad syntes och konkreta rekommendationer
              </p>
            </motion.div>
          </motion.div>
        )}
      </div>
    </section>
  );
};

// ==================== SECTION 5: DETAILED LANGGRAPH FLOW ====================

// Node data structure matching actual LangGraph implementation
interface FlowNode {
  id: string;
  label: string;
  description: string;
  detailedDesc: string;
  phase: "intent" | "planning" | "execution" | "validation" | "output";
  type: "process" | "decision" | "hitl" | "terminal";
  apiCalls?: string[];
}

// ==================== RADICAL TRANSPARENCY SECTION ====================
const RadicalTransparencySection = () => {
  const [currentScenario, setCurrentScenario] = useState(0);
  const [chatMessages, setChatMessages] = useState<Array<{
    type: 'user' | 'system' | 'api' | 'thinking' | 'assistant' | 'sources';
    text: string;
    sources?: string[];
  }>>([]);
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [langGraphData, setLangGraphData] = useState<any>(null);
  const sectionRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(sectionRef, { once: true, amount: 0.3 });

  // Load real LangGraph JSON from /public
  useEffect(() => {
    fetch('/langgraph-flow-msg-3727-1771204720984.json')
      .then(res => res.json())
      .then(data => {
        console.log('Loaded LangGraph data:', data.metadata);
        setLangGraphData(data);
      })
      .catch(err => console.error('Failed to load LangGraph data:', err));
  }, []);

  // Extract query and response from loaded JSON
  const realQuery = langGraphData?.spans?.[0]?.input?.query || "";
  const realResponse = (() => {
    if (!langGraphData) return "";
    // Find the final response from critic_node span
    for (let i = langGraphData.spans.length - 1; i >= 0; i--) {
      const span = langGraphData.spans[i];
      if (span.name === 'critic_node' && span.output?.final_response) {
        return span.output.final_response;
      }
    }
    return "";
  })();

  // REAL DATA from actual LangGraph execution (loaded dynamically from JSON file)
  const scenarios = langGraphData ? [
    {
      question: realQuery,
      messages: [
        { type: 'user' as const, text: realQuery },
        { type: 'system' as const, text: "🔍 Analyserar komplex policy-fråga..." },
        { type: 'system' as const, text: "⚡ Väljer Statistics Agent" },
        { type: 'system' as const, text: "📋 Skapar research plan med flera källor" },
        { type: 'api' as const, text: "📡 Anropar SCB: befolkningsdata, arbetsmarknad, integration" },
        { type: 'thinking' as const, text: `Bearbetar data från ${langGraphData.metadata.totalSpans} execution steg...` },
        { type: 'system' as const, text: "✅ Orchestration guard: kvalitetskontroller" },
        { type: 'system' as const, text: "🔄 Critic validerar sources och reasoning" },
        { type: 'assistant' as const, text: realResponse },
        { type: 'sources' as const, text: "", sources: ['SCB'] },
      ],
      steps: [0, 1, 2, 3, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    }
  ] : [];

  // JSON export data - use loaded LangGraph data
  const jsonData = langGraphData || {
    metadata: {
      exportedAt: "",
      messageId: "",
      sessionId: "",
      totalSpans: 0,
      completedSpans: 0,
      runningSpans: 0,
      errorSpans: 0
    },
    spans: []
  };

  // Animation sequence - now updates both chat and JSON
  useEffect(() => {
    if (!isInView || !langGraphData || scenarios.length === 0) return;

    const runSequence = async () => {
      const data = scenarios[currentScenario];
      setChatMessages([]);
      setActiveStep(null);

      // Add messages sequentially
      for (let i = 0; i < data.messages.length; i++) {
        await new Promise(resolve => setTimeout(resolve, 1500));
        setChatMessages(prev => [...prev, data.messages[i]]);
        setActiveStep(data.steps[i]);
      }

      // Pause before next scenario
      await new Promise(resolve => setTimeout(resolve, 3000));
      setCurrentScenario((prev) => (prev + 1) % scenarios.length);
    };

    runSequence();
  }, [currentScenario, isInView, langGraphData]);

  return (
    <section ref={sectionRef} className="relative py-24 md:py-32 bg-white dark:bg-neutral-950">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl md:text-5xl font-bold mb-4">
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-600 to-red-600">
              Radikal transparens
            </span>
            {" "}— Ner till sista punkten
          </h2>
          <p className="text-lg md:text-xl text-neutral-600 dark:text-neutral-400 max-w-3xl mx-auto">
            Se exakt hur OneSeek bearbetar din fråga genom hela LangGraph-pipelinen med full transparens.
          </p>
        </motion.div>

        {/* Two-column layout: Chat left, Pipeline right */}
        <div className="flex flex-col lg:flex-row gap-8 max-w-7xl mx-auto">
          {/* Left: Chat View */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="flex-1 lg:max-w-2xl"
          >
            <div className="bg-white/40 dark:bg-neutral-900/40 backdrop-blur-md rounded-2xl border border-neutral-200 dark:border-neutral-800 p-6 h-[700px] overflow-y-auto">
              {/* Chat header */}
              <div className="flex items-center gap-2 mb-6 pb-4 border-b border-neutral-200 dark:border-neutral-800">
                <div className="size-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
                  Live Execution Trace
                </span>
              </div>

              {/* Messages */}
              <div className="space-y-4">
                {chatMessages.map((message, idx) => (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                    className={cn(
                      "flex",
                      message.type === 'user' ? "justify-end" : "justify-start"
                    )}
                  >
                    {message.type === 'user' && (
                      <div className="max-w-[80%] bg-blue-500 text-white rounded-2xl rounded-tr-sm px-4 py-3">
                        <p className="text-sm">{message.text}</p>
                      </div>
                    )}
                    
                    {message.type === 'system' && (
                      <div className="max-w-[80%] bg-purple-500/10 border border-purple-500/20 rounded-2xl rounded-tl-sm px-4 py-3">
                        <p className="text-sm text-purple-700 dark:text-purple-300">{message.text}</p>
                      </div>
                    )}
                    
                    {message.type === 'api' && (
                      <div className="w-full flex justify-center">
                        <div className="bg-emerald-500/20 border border-emerald-500/40 rounded-lg px-4 py-2">
                          <p className="text-xs font-mono text-emerald-700 dark:text-emerald-300">{message.text}</p>
                        </div>
                      </div>
                    )}
                    
                    {message.type === 'thinking' && (
                      <div className="max-w-[80%] bg-neutral-100 dark:bg-neutral-800 rounded-2xl rounded-tl-sm px-4 py-3">
                        <p className="text-sm italic text-neutral-600 dark:text-neutral-400">{message.text}</p>
                      </div>
                    )}
                    
                    {message.type === 'assistant' && (
                      <div className="max-w-[80%] bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
                        <StreamingMarkdown 
                          content={message.text} 
                          chunkSize={150} 
                          chunkDelay={80} 
                        />
                      </div>
                    )}
                    
                    {message.type === 'sources' && message.sources && (
                      <div className="flex gap-2 mt-2">
                        {message.sources.map((source, i) => (
                          <span
                            key={i}
                            className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border border-orange-200 dark:border-orange-800"
                          >
                            [{i + 1}] {source}
                          </span>
                        ))}
                      </div>
                    )}
                  </motion.div>
                ))}
                <div ref={chatEndRef} />
              </div>
            </div>
          </motion.div>

          {/* Right: JSON Code Preview */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="lg:w-[500px]"
          >
            <div className="bg-neutral-900 rounded-2xl border border-neutral-800 overflow-hidden sticky top-24 max-h-[700px] flex flex-col">
              {/* Code header */}
              <div className="flex items-center justify-between px-4 py-3 bg-neutral-800/50 border-b border-neutral-700">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1.5">
                    <div className="size-3 rounded-full bg-red-500/80" />
                    <div className="size-3 rounded-full bg-yellow-500/80" />
                    <div className="size-3 rounded-full bg-emerald-500/80" />
                  </div>
                  <span className="text-xs font-mono text-neutral-400 ml-2">
                    langgraph-flow.json
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs text-emerald-400">
                  <div className="size-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span>Streaming</span>
                </div>
              </div>

              {/* JSON Content */}
              <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed">
                <pre className="text-neutral-300">
                  <span className="text-neutral-500">{'{'}</span>{'\n'}
                  <span className="text-neutral-500">  </span>
                  <span className="text-blue-400">"metadata"</span>
                  <span className="text-neutral-500">: {'{'}</span>{'\n'}
                  <span className="text-neutral-500">    </span>
                  <span className="text-blue-400">"exportedAt"</span>
                  <span className="text-neutral-500">: </span>
                  <span className="text-emerald-400">"{jsonData.metadata.exportedAt}"</span>
                  <span className="text-neutral-500">,</span>{'\n'}
                  <span className="text-neutral-500">    </span>
                  <span className="text-blue-400">"messageId"</span>
                  <span className="text-neutral-500">: </span>
                  <span className="text-emerald-400">"{jsonData.metadata.messageId}"</span>
                  <span className="text-neutral-500">,</span>{'\n'}
                  <span className="text-neutral-500">    </span>
                  <span className="text-blue-400">"sessionId"</span>
                  <span className="text-neutral-500">: </span>
                  <span className="text-emerald-400">"{jsonData.metadata.sessionId}"</span>
                  <span className="text-neutral-500">,</span>{'\n'}
                  <span className="text-neutral-500">    </span>
                  <span className="text-blue-400">"totalSpans"</span>
                  <span className="text-neutral-500">: </span>
                  <span className="text-purple-400">{jsonData.metadata.totalSpans}</span>
                  <span className="text-neutral-500">,</span>{'\n'}
                  <span className="text-neutral-500">    </span>
                  <span className="text-blue-400">"completedSpans"</span>
                  <span className="text-neutral-500">: </span>
                  <motion.span 
                    key={jsonData.metadata.completedSpans}
                    initial={{ color: '#10b981' }}
                    animate={{ color: '#a78bfa' }}
                    transition={{ duration: 0.3 }}
                    className="text-purple-400 font-bold"
                  >
                    {jsonData.metadata.completedSpans}
                  </motion.span>
                  <span className="text-neutral-500">,</span>{'\n'}
                  <span className="text-neutral-500">    </span>
                  <span className="text-blue-400">"runningSpans"</span>
                  <span className="text-neutral-500">: </span>
                  <span className="text-purple-400">{jsonData.metadata.runningSpans}</span>
                  <span className="text-neutral-500">,</span>{'\n'}
                  <span className="text-neutral-500">    </span>
                  <span className="text-blue-400">"errorSpans"</span>
                  <span className="text-neutral-500">: </span>
                  <span className="text-purple-400">{jsonData.metadata.errorSpans}</span>{'\n'}
                  <span className="text-neutral-500">  {'}'},</span>{'\n'}
                  <span className="text-neutral-500">  </span>
                  <span className="text-blue-400">"spans"</span>
                  <span className="text-neutral-500">: [</span>{'\n'}
                  
                  {/* Render spans */}
                  {jsonData.spans.map((span, idx) => (
                    <motion.div
                      key={span.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.3 }}
                    >
                      <span className="text-neutral-500">    {'{'}</span>{'\n'}
                      <span className="text-neutral-500">      </span>
                      <span className="text-blue-400">"id"</span>
                      <span className="text-neutral-500">: </span>
                      <span className="text-emerald-400">"{span.id}"</span>
                      <span className="text-neutral-500">,</span>{'\n'}
                      <span className="text-neutral-500">      </span>
                      <span className="text-blue-400">"parent_id"</span>
                      <span className="text-neutral-500">: </span>
                      {span.parent_id ? (
                        <span className="text-emerald-400">"{span.parent_id}"</span>
                      ) : (
                        <span className="text-orange-400">null</span>
                      )}
                      <span className="text-neutral-500">,</span>{'\n'}
                      <span className="text-neutral-500">      </span>
                      <span className="text-blue-400">"name"</span>
                      <span className="text-neutral-500">: </span>
                      <span className="text-emerald-400">"{span.name}"</span>
                      <span className="text-neutral-500">,</span>{'\n'}
                      <span className="text-neutral-500">      </span>
                      <span className="text-blue-400">"status"</span>
                      <span className="text-neutral-500">: </span>
                      <span className="text-emerald-400">"{span.status}"</span>
                      <span className="text-neutral-500">,</span>{'\n'}
                      <span className="text-neutral-500">      </span>
                      <span className="text-blue-400">"sequence"</span>
                      <span className="text-neutral-500">: </span>
                      <span className="text-purple-400">{span.sequence}</span>
                      <span className="text-neutral-500">,</span>{'\n'}
                      <span className="text-neutral-500">      </span>
                      <span className="text-blue-400">"duration_ms"</span>
                      <span className="text-neutral-500">: </span>
                      <span className="text-purple-400">{span.duration_ms}</span>
                      <span className="text-neutral-500">,</span>{'\n'}
                      <span className="text-neutral-500">      </span>
                      <span className="text-blue-400">"meta"</span>
                      <span className="text-neutral-500">: {'{'}</span>
                      {span.meta.tokens && (
                        <>
                          <span className="text-blue-400">"tokens"</span>
                          <span className="text-neutral-500">: </span>
                          <span className="text-purple-400">{span.meta.tokens}</span>
                        </>
                      )}
                      <span className="text-neutral-500">{'}'}</span>{'\n'}
                      <span className="text-neutral-500">    {'}'}</span>
                      {idx < jsonData.spans.length - 1 && <span className="text-neutral-500">,</span>}
                      {'\n'}
                    </motion.div>
                  ))}
                  
                  <span className="text-neutral-500">  ]</span>{'\n'}
                  <span className="text-neutral-500">{'}'}</span>
                </pre>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

const AgentFlowSection = () => {
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showTooltip, setShowTooltip] = useState<number | null>(null);
  const sectionRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(sectionRef, { once: true, amount: 0.3 });

  // 14 actual nodes from supervisor_agent.py
  const nodes: FlowNode[] = [
    {
      id: "start",
      label: "START",
      description: "Användaren ställer en fråga",
      detailedDesc: "Fråga: 'Hur många invånare har Stockholm?'",
      phase: "intent",
      type: "process",
    },
    {
      id: "resolve_intent",
      label: "Intent Router",
      description: "Analyserar frågetyp",
      detailedDesc: "Identifierar: Statistik-fråga → Behöver SCB-data",
      phase: "intent",
      type: "process",
    },
    {
      id: "agent_resolver",
      label: "Agent Resolver",
      description: "Väljer specialiserade agenter",
      detailedDesc: "Väljer: Statistics Agent, Knowledge Agent",
      phase: "planning",
      type: "process",
    },
    {
      id: "planner",
      label: "Planner",
      description: "Skapar execution plan",
      detailedDesc: "Plan: 1) Hämta SCB data 2) Verifiera med Tavily 3) Formatera svar",
      phase: "planning",
      type: "process",
    },
    {
      id: "planner_hitl",
      label: "Plan Approval",
      description: "Human-in-the-loop checkpoint",
      detailedDesc: "Kontrollerar om planen är rimlig innan körning",
      phase: "planning",
      type: "hitl",
    },
    {
      id: "tool_resolver",
      label: "Tool Resolver",
      description: "Mappar agenter till verktyg",
      detailedDesc: "Statistics Agent → get_population_data från SCB",
      phase: "execution",
      type: "process",
    },
    {
      id: "execution_hitl",
      label: "Execution Approval",
      description: "Godkänn verktygsanrop",
      detailedDesc: "Tillåt anrop till SCB API och Tavily",
      phase: "execution",
      type: "hitl",
    },
    {
      id: "executor",
      label: "Executor",
      description: "LLM genererar tool calls",
      detailedDesc: "Skapar strukturerade API-anrop med parametrar",
      phase: "execution",
      type: "process",
    },
    {
      id: "tools",
      label: "External APIs",
      description: "Kör verktyg och hämtar data",
      detailedDesc: "Aktiva anrop till externa tjänster",
      phase: "execution",
      type: "process",
      apiCalls: ["SCB Befolkningsdata", "Tavily Verifiering", "SMHI Väderdata"],
    },
    {
      id: "post_tools",
      label: "Post-Tools",
      description: "Bearbetar verktygsresultat",
      detailedDesc: "Formaterar JSON-svar från SCB till läsbar text",
      phase: "execution",
      type: "process",
    },
    {
      id: "orchestration_guard",
      label: "Safety Guard",
      description: "Säkerhetskontroller",
      detailedDesc: "Verifierar: Max 3 hopp ✓, Ingen loop ✓, Token limit OK ✓",
      phase: "validation",
      type: "process",
    },
    {
      id: "critic",
      label: "Critic",
      description: "Validerar svar kvalitet",
      detailedDesc: "Beslut: ok | needs_more | replan",
      phase: "validation",
      type: "decision",
    },
    {
      id: "synthesizer",
      label: "Synthesizer",
      description: "Förfinar svar med citeringar",
      detailedDesc: "Sammanställer data från alla källor med [1] [2] referenser",
      phase: "output",
      type: "process",
    },
    {
      id: "end",
      label: "END",
      description: "Returnerar verifierat svar",
      detailedDesc: "Svar: 'Stockholm har 975 551 invånare (SCB 2023) [1]'",
      phase: "output",
      type: "terminal",
    },
  ];

  // Auto-play logic
  useEffect(() => {
    if (isInView && !isPlaying) {
      setIsPlaying(true);
    }
  }, [isInView]);

  useEffect(() => {
    if (isPlaying && currentStep < nodes.length - 1) {
      const timer = setTimeout(() => {
        setCurrentStep(prev => prev + 1);
      }, 2000);
      return () => clearTimeout(timer);
    } else if (currentStep >= nodes.length - 1) {
      setIsPlaying(false);
    }
  }, [isPlaying, currentStep, nodes.length]);

  const getPhaseColor = (phase: string) => {
    switch (phase) {
      case "intent": return "from-purple-500 to-pink-500";
      case "planning": return "from-blue-500 to-cyan-500";
      case "execution": return "from-emerald-500 to-teal-500";
      case "validation": return "from-amber-500 to-orange-500";
      case "output": return "from-orange-500 to-red-500";
      default: return "from-neutral-500 to-neutral-600";
    }
  };

  const getNodeShape = (type: string) => {
    if (type === "decision") return "clip-path-diamond";
    if (type === "hitl") return "rounded-full";
    if (type === "terminal") return "rounded-2xl";
    return "rounded-xl";
  };

  return (
    <section 
      ref={sectionRef}
      className="py-24 md:py-32 bg-gradient-to-b from-transparent via-purple-500/5 to-transparent dark:via-purple-500/10 relative overflow-hidden"
    >
      {/* Background Gradient Elements */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-gradient-to-br from-purple-500/5 via-pink-500/5 to-orange-500/5 dark:from-purple-500/10 dark:via-pink-500/10 dark:to-orange-500/10 rounded-full blur-3xl" />
      </div>

      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <motion.div 
          className="text-center mb-16"
          initial={{ opacity: 1, y: 0 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <span className="text-sm font-semibold text-purple-600 dark:text-purple-400 uppercase tracking-wider">ARKITEKTUR</span>
          <h2 className="mt-2 text-3xl md:text-5xl font-bold tracking-tight text-black dark:text-white">
            14-Nods LangGraph Pipeline — Exakt som koden
          </h2>
          <p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400">
            Se hur varje fråga flödar genom systemet, med alla beslutspunkter och API-anrop
          </p>
        </motion.div>

        {/* Playback Controls */}
        <div className="max-w-4xl mx-auto mb-12 flex items-center justify-center gap-4">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="px-6 py-2 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 text-white font-semibold shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300"
          >
            {isPlaying ? "⏸ Pause" : "▶ Play"}
          </button>
          <button
            onClick={() => setCurrentStep(Math.max(0, currentStep - 1))}
            disabled={currentStep === 0}
            className="px-4 py-2 rounded-xl border border-neutral-300 dark:border-neutral-700 bg-white/50 dark:bg-neutral-900/50 backdrop-blur-md disabled:opacity-30 hover:bg-white/80 dark:hover:bg-neutral-900/80 transition-all"
          >
            ← Prev
          </button>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-neutral-600 dark:text-neutral-400">
              Step {currentStep + 1} / {nodes.length}
            </span>
          </div>
          <button
            onClick={() => setCurrentStep(Math.min(nodes.length - 1, currentStep + 1))}
            disabled={currentStep === nodes.length - 1}
            className="px-4 py-2 rounded-xl border border-neutral-300 dark:border-neutral-700 bg-white/50 dark:bg-neutral-900/50 backdrop-blur-md disabled:opacity-30 hover:bg-white/80 dark:hover:bg-neutral-900/80 transition-all"
          >
            Next →
          </button>
        </div>

        {/* Node Flow Visualization */}
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {nodes.map((node, index) => {
              const isActive = index === currentStep;
              const isPast = index < currentStep;
              const isFuture = index > currentStep;

              return (
                <motion.div
                  key={node.id}
                  initial={{ opacity: 1, scale: 1 }}
                  animate={{
                    opacity: isFuture ? 0.4 : 1,
                    scale: isActive ? 1.05 : 1,
                  }}
                  transition={{ duration: 0.3 }}
                  onMouseEnter={() => setShowTooltip(index)}
                  onMouseLeave={() => setShowTooltip(null)}
                  className="relative"
                >
                  <div
                    className={cn(
                      "relative p-4 border-2 backdrop-blur-lg transition-all duration-300 overflow-hidden cursor-pointer",
                      getNodeShape(node.type),
                      isActive
                        ? `border-transparent bg-gradient-to-br ${getPhaseColor(node.phase)} shadow-2xl`
                        : isPast
                        ? "border-neutral-300 dark:border-neutral-700 bg-white/60 dark:bg-neutral-900/60"
                        : "border-neutral-200 dark:border-neutral-800 bg-white/40 dark:bg-neutral-900/40"
                    )}
                  >
                    {/* Shine effect on active node */}
                    {isActive && (
                      <motion.div
                        className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent"
                        animate={{
                          x: ["-100%", "200%"],
                        }}
                        transition={{
                          duration: 2,
                          repeat: Infinity,
                          ease: "linear",
                        }}
                      />
                    )}

                    <div className="relative z-10">
                      <div className={cn(
                        "text-xs font-bold uppercase tracking-wider mb-1",
                        isActive ? "text-white" : "text-neutral-500 dark:text-neutral-400"
                      )}>
                        {node.phase}
                      </div>
                      <div className={cn(
                        "text-sm font-semibold mb-1",
                        isActive ? "text-white" : "text-neutral-900 dark:text-white"
                      )}>
                        {node.label}
                      </div>
                      <div className={cn(
                        "text-xs",
                        isActive ? "text-white/90" : "text-neutral-600 dark:text-neutral-400"
                      )}>
                        {node.description}
                      </div>
                    </div>

                    {/* Tooltip */}
                    {showTooltip === index && (
                      <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 px-4 py-3 rounded-xl bg-neutral-900 dark:bg-neutral-800 text-white text-xs font-medium shadow-2xl border border-neutral-700 whitespace-nowrap max-w-xs"
                      >
                        <div className="font-semibold mb-1">{node.label}</div>
                        <div className="text-neutral-300">{node.detailedDesc}</div>
                        {node.apiCalls && (
                          <div className="mt-2 pt-2 border-t border-neutral-700">
                            <div className="text-[10px] text-neutral-400 mb-1">API Calls:</div>
                            {node.apiCalls.map((api, i) => (
                              <div key={i} className="text-[10px] text-green-400">⏳ {api}</div>
                            ))}
                          </div>
                        )}
                      </motion.div>
                    )}
                  </div>

                  {/* Connection arrow */}
                  {index < nodes.length - 1 && index % 4 !== 3 && (
                    <div className="absolute top-1/2 -right-2 -translate-y-1/2 text-neutral-400 dark:text-neutral-600 text-lg z-20">
                      →
                    </div>
                  )}
                </motion.div>
              );
            })}
          </div>

          {/* Conditional Routing Explanation */}
          <motion.div
            className="mt-12 p-6 rounded-2xl border border-amber-200 dark:border-amber-800/50 bg-gradient-to-br from-amber-50/50 to-orange-50/50 dark:from-amber-950/30 dark:to-orange-950/30 backdrop-blur-md"
            initial={{ opacity: 1, y: 0 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <div className="flex items-start gap-3">
              <div className="size-8 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center flex-shrink-0 text-white font-bold">
                ◆
              </div>
              <div>
                <h4 className="font-semibold text-neutral-900 dark:text-white mb-2">Villkorlig Routing från Critic</h4>
                <div className="text-sm text-neutral-700 dark:text-neutral-300 space-y-1">
                  <div>✓ <span className="font-semibold">ok</span> → Går till Synthesizer (slutför)</div>
                  <div>⟲ <span className="font-semibold">needs_more</span> → Går tillbaka till Tool Resolver (hämta mer data)</div>
                  <div>↺ <span className="font-semibold">replan</span> → Går tillbaka till Planner (skapa ny plan)</div>
                </div>
              </div>
            </div>
          </motion.div>
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
              <span>Skapa konto</span>
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
<APIReasoningDemo />
<CompareShowcase />
<DebateDemo />
<RadicalTransparencySection />
<AgentFlowSection />
<LLMProvidersSection />
<CTASection />
</main>
);
}
