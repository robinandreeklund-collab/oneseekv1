"use client";

import { Database, Eye, GitCompare, MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";

export function FeaturesCards() {
	const t = useTranslations("homepage");

	const features = [
		{
			icon: <GitCompare className="w-6 h-6" />,
			title: t("capability_compare_title"),
			description: t("capability_compare_desc"),
			color: "blue"
		},
		{
			icon: <MessageSquare className="w-6 h-6" />,
			title: t("capability_debate_title"),
			description: t("capability_debate_desc"),
			color: "purple"
		},
		{
			icon: <Eye className="w-6 h-6" />,
			title: t("capability_transparency_title"),
			description: t("capability_transparency_desc"),
			color: "green"
		},
		{
			icon: <Database className="w-6 h-6" />,
			title: t("capability_realtime_title"),
			description: t("capability_realtime_desc"),
			color: "orange"
		}
	];

	return (
		<section className="w-full py-24 md:py-32 bg-gray-50 dark:bg-neutral-900">
			<div className="mx-auto max-w-7xl px-4 md:px-8">
				{/* Section Header */}
				<div className="text-center mb-16">
					<h2 className="text-4xl md:text-5xl lg:text-6xl font-bold text-black dark:text-white mb-4">
						{t("capabilities_title")}
					</h2>
					<p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 max-w-3xl mx-auto">
						{t("capabilities_subtitle")}
					</p>
				</div>

				{/* Features Grid */}
				<div className="grid grid-cols-1 md:grid-cols-2 gap-6 lg:gap-8">
					{features.map((feature, index) => (
						<FeatureCard key={index} {...feature} />
					))}
				</div>
			</div>
		</section>
	);
}

interface FeatureCardProps {
	icon: React.ReactNode;
	title: string;
	description: string;
	color: "blue" | "purple" | "green" | "orange";
}

function FeatureCard({ icon, title, description, color }: FeatureCardProps) {
	const colorClasses = {
		blue: "bg-blue-50 border-blue-200 text-blue-600 dark:bg-blue-950/30 dark:border-blue-800 dark:text-blue-400",
		purple: "bg-purple-50 border-purple-200 text-purple-600 dark:bg-purple-950/30 dark:border-purple-800 dark:text-purple-400",
		green: "bg-green-50 border-green-200 text-green-600 dark:bg-green-950/30 dark:border-green-800 dark:text-green-400",
		orange: "bg-orange-50 border-orange-200 text-orange-600 dark:bg-orange-950/30 dark:border-orange-800 dark:text-orange-400"
	};

	return (
		<div className="bg-white dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-2xl p-8 hover:shadow-xl transition-all duration-300 group">
			{/* Icon */}
			<div className={`inline-flex items-center justify-center w-12 h-12 rounded-xl border-2 mb-6 ${colorClasses[color]} group-hover:scale-110 transition-transform duration-300`}>
				{icon}
			</div>

			{/* Content */}
			<h3 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white mb-3">
				{title}
			</h3>
			<p className="text-base text-gray-600 dark:text-gray-400 leading-relaxed">
				{description}
			</p>
		</div>
	);
}
