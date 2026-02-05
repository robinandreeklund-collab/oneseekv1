"use client";

import { useTranslations } from "next-intl";
import { Pricing } from "@/components/pricing";

function PricingBasic() {
	const t = useTranslations("pricing");
	const demoPlans = [
		{
			name: t("community_name"),
			price: "0",
			yearlyPrice: "0",
			period: t("forever"),
			features: [
				t("community_support"),
				t("feature_llms"),
				t("openai_litellm_support"),
				t("feature_ollama"),
				t("feature_embeddings"),
				t("feature_files"),
				t("feature_podcasts"),
				t("feature_sources"),
				t("feature_extension"),
				t("access_controls"),
				t("collaboration"),
			],
			description: t("community_desc"),
			buttonText: t("get_started"),
			href: "/docs",
			isPopular: false,
		},
		{
			name: t("cloud_name"),
			price: "0",
			yearlyPrice: "0",
			period: t("cloud_period"),
			features: [
				t("everything_community"),
				t("email_support"),
				t("get_started_seconds"),
				t("instant_access"),
				t("easy_access_anywhere"),
				t("remote_team_management"),
			],
			description: t("cloud_desc"),
			buttonText: t("get_started"),
			href: "/",
			isPopular: true,
		},
		{
			name: t("enterprise_name"),
			price: t("contact_us"),
			yearlyPrice: t("contact_us"),
			period: "",
			features: [
				t("everything_community"),
				t("priority_support"),
				t("white_glove_setup"),
				t("managed_updates"),
				t("on_prem_vpc"),
				t("audit_logs"),
				t("sso"),
				t("sla_guarantee"),
				t("uptime_guarantee"),
			],
			description: t("enterprise_desc"),
			buttonText: t("contact_sales"),
			href: "/contact",
			isPopular: false,
		},
	];

	return (
		<Pricing plans={demoPlans} title={t("title")} description={t("subtitle")} />
	);
}

export default PricingBasic;
