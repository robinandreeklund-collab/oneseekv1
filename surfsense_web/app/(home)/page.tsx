import { CTAHomepage } from "@/components/homepage/cta";
import { FeaturesBentoGrid } from "@/components/homepage/features-bento-grid";
import { FeaturesCards } from "@/components/homepage/features-card";
import { HeroSection } from "@/components/homepage/hero-section";
// Integrations section removed per requirements
// import ExternalIntegrations from "@/components/homepage/integrations";

export default function HomePage() {
	return (
		<main className="min-h-screen bg-white dark:bg-neutral-950">
			<HeroSection />
			<FeaturesCards />
			<FeaturesBentoGrid />
			<CTAHomepage />
		</main>
	);
}
