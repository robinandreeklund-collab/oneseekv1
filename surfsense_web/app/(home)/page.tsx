import { AgentFlow } from "@/components/homepage/agent-flow";
import { CTAHomepage } from "@/components/homepage/cta";
import { FeaturesCards } from "@/components/homepage/features-card";
import { HeroSection } from "@/components/homepage/hero-section";
import { ModelComparison } from "@/components/homepage/model-comparison";
import { SwedishAPIs } from "@/components/homepage/swedish-apis";

export default function HomePage() {
	return (
		<main className="min-h-screen bg-white dark:bg-neutral-950">
			<HeroSection />
			<AgentFlow />
			<SwedishAPIs />
			<ModelComparison />
			<FeaturesCards />
			<CTAHomepage />
		</main>
	);
}
