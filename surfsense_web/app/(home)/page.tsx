import { AgentPipeline } from "@/components/homepage/agent-pipeline";
import { APIMarquee } from "@/components/homepage/api-marquee";
import { Capabilities } from "@/components/homepage/capabilities";
import { CTAHomepage } from "@/components/homepage/cta";
import { TimeCapsule, PodcastMode, TransparentReasoning } from "@/components/homepage/features-showcase";
import { HeroSection } from "@/components/homepage/hero-section";
import { LLMProviders } from "@/components/homepage/llm-providers";
import { StatsBar } from "@/components/homepage/stats-bar";

export default function HomePage() {
	return (
		<main className="min-h-screen bg-gradient-to-b from-gray-50 to-white text-gray-900 dark:from-neutral-950 dark:to-neutral-950 dark:text-white">
			<HeroSection />
			<StatsBar />
			<Capabilities />
			<APIMarquee />
			<AgentPipeline />
			<LLMProviders />
			<TransparentReasoning />
			<TimeCapsule />
			<PodcastMode />
			<CTAHomepage />
		</main>
	);
}
