"use client";

import { useTranslations } from "next-intl";
import Image from "next/image";

export function SwedishAPIs() {
	const t = useTranslations("homepage");

	const apis = [
		{
			name: "SCB",
			fullName: "Statistiska centralbyrån",
			description: t("api_scb_desc"),
			logo: "/api-logos/scb.svg",
			color: "blue"
		},
		{
			name: "Bolagsverket",
			fullName: "Bolagsverket",
			description: t("api_bolagsverket_desc"),
			logo: "/api-logos/bolagsverket.svg",
			color: "green"
		},
		{
			name: "SMHI",
			fullName: "SMHI",
			description: t("api_smhi_desc"),
			logo: "/api-logos/smhi.svg",
			color: "orange"
		},
		{
			name: "Trafiklab",
			fullName: "Trafiklab",
			description: t("api_trafiklab_desc"),
			logo: "/api-logos/trafiklab.svg",
			color: "purple"
		},
		{
			name: "Libris",
			fullName: "Kungliga Biblioteket",
			description: t("api_libris_desc"),
			logo: "/api-logos/libris.svg",
			color: "pink"
		},
		{
			name: "Arbetsförmedlingen",
			fullName: "Arbetsförmedlingen",
			description: t("api_arbetsformedlingen_desc"),
			logo: "/api-logos/arbetsformedlingen.svg",
			color: "red"
		},
		{
			name: "Tavily",
			fullName: "Tavily Search",
			description: t("api_tavily_desc"),
			logo: "/api-logos/tavily.svg",
			color: "indigo"
		}
	];

	return (
		<section className="w-full py-24 md:py-32 bg-gray-50 dark:bg-neutral-900">
			<div className="mx-auto max-w-7xl px-4 md:px-8">
				{/* Section Header */}
				<div className="text-center mb-16">
					<h2 className="text-4xl md:text-5xl lg:text-6xl font-bold text-black dark:text-white mb-4">
						{t("swedish_apis_title")}
					</h2>
					<p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 max-w-3xl mx-auto">
						{t("swedish_apis_subtitle")}
					</p>
				</div>

				{/* API Grid */}
				<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
					{apis.map((api) => (
						<APICard key={api.name} {...api} />
					))}
				</div>
			</div>
		</section>
	);
}

interface APICardProps {
	name: string;
	fullName: string;
	description: string;
	logo: string;
	color: string;
}

function APICard({ name, fullName, description, logo, color }: APICardProps) {
	const colorClasses: Record<string, string> = {
		blue: "hover:border-blue-400 hover:shadow-blue-200/50 dark:hover:border-blue-600 dark:hover:shadow-blue-900/30",
		green: "hover:border-green-400 hover:shadow-green-200/50 dark:hover:border-green-600 dark:hover:shadow-green-900/30",
		orange: "hover:border-orange-400 hover:shadow-orange-200/50 dark:hover:border-orange-600 dark:hover:shadow-orange-900/30",
		purple: "hover:border-purple-400 hover:shadow-purple-200/50 dark:hover:border-purple-600 dark:hover:shadow-purple-900/30",
		pink: "hover:border-pink-400 hover:shadow-pink-200/50 dark:hover:border-pink-600 dark:hover:shadow-pink-900/30",
		red: "hover:border-red-400 hover:shadow-red-200/50 dark:hover:border-red-600 dark:hover:shadow-red-900/30",
		indigo: "hover:border-indigo-400 hover:shadow-indigo-200/50 dark:hover:border-indigo-600 dark:hover:shadow-indigo-900/30"
	};

	return (
		<div
			className={`
				bg-white dark:bg-neutral-800
				border-2 border-gray-200 dark:border-neutral-700
				rounded-xl p-6
				transition-all duration-300
				hover:scale-105 hover:shadow-xl
				${colorClasses[color] || colorClasses.blue}
				group
			`}
		>
			{/* Logo */}
			<div className="flex items-center justify-center mb-4 h-16">
				<Image
					src={logo}
					alt={fullName}
					width={80}
					height={80}
					className="max-h-16 w-auto object-contain group-hover:scale-110 transition-transform duration-300"
				/>
			</div>

			{/* Content */}
			<div className="text-center">
				<h3 className="font-bold text-lg text-gray-900 dark:text-white mb-1">
					{name}
				</h3>
				<p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
					{fullName}
				</p>
				<p className="text-xs text-gray-500 dark:text-gray-500 leading-relaxed">
					{description}
				</p>
			</div>
		</div>
	);
}
