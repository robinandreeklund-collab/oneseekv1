"use client";

import { motion, useInView } from "motion/react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useRef } from "react";

interface SwedishAPI {
	name: string;
	desc: string;
	color: string;
	logo?: string;
}

const SWEDISH_APIS: SwedishAPI[] = [
	{ name: "SCB", desc: "Statistiska Centralbyrån", color: "from-blue-500 to-blue-600", logo: "/api-logos/scb-logo.png" },
	{ name: "SMHI", desc: "Klimat & Väderdata", color: "from-cyan-500 to-teal-600", logo: "/api-logos/smhi-logo.png" },
	{ name: "Bolagsverket", desc: "Företagsregister", color: "from-amber-500 to-orange-600", logo: "/api-logos/bolagsverket-logo.png" },
	{ name: "Trafikverket", desc: "Infrastruktur & Trafik", color: "from-emerald-500 to-green-600", logo: "/api-logos/trafiklab.png" },
	{ name: "Riksdagen", desc: "Lagstiftning & Politik", color: "from-red-500 to-rose-600", logo: "/api-logos/riksdagen-logo.png" },
	{ name: "Nord Pool", desc: "Energipriser & Elmarknad", color: "from-indigo-500 to-blue-600", logo: "/api-logos/Nord_Pool_Logo.png" },
	{ name: "Kolada", desc: "Kommunal Statistik", color: "from-purple-500 to-violet-600" },
	{ name: "Tavily", desc: "Webbsökning", color: "from-indigo-500 to-blue-600" },
	{ name: "Skatteverket", desc: "Skatt & Folkbokföring", color: "from-yellow-500 to-amber-600" },
	{ name: "Skolverket", desc: "Utbildningsstatistik", color: "from-teal-500 to-cyan-600" },
	{ name: "Jordbruksverket", desc: "Jordbruk & Livsmedel", color: "from-lime-500 to-green-600" },
	{ name: "Valmyndigheten", desc: "Valstatistik", color: "from-violet-500 to-purple-600" },
	{ name: "Naturvårdsverket", desc: "Miljödata", color: "from-green-500 to-emerald-600" },
];

function MarqueeRow({ items, reverse = false }: { items: SwedishAPI[]; reverse?: boolean }) {
	const duplicated = [...items, ...items];

	return (
		<div className="flex overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
			<div
				className={`flex gap-5 py-2 ${reverse ? "[animation-direction:reverse]" : ""} animate-marquee`}
			>
				{duplicated.map((api, i) => (
					<div
						key={`${api.name}-${i}`}
						className="group flex-shrink-0 flex flex-col items-center gap-2.5 rounded-2xl border border-neutral-200/50 dark:border-white/10 bg-white/60 dark:bg-neutral-900/40 backdrop-blur-sm px-6 py-5 transition-all duration-300 hover:border-purple-300 dark:hover:border-purple-500/30 hover:shadow-lg hover:shadow-purple-500/5 min-w-[120px]"
					>
						{/* Logo — big and prominent */}
						{api.logo ? (
							<div className="w-14 h-14 rounded-xl overflow-hidden flex items-center justify-center flex-shrink-0 bg-white dark:bg-neutral-800 p-1.5">
								<Image
									src={api.logo}
									alt={api.name}
									width={56}
									height={56}
									className="object-contain w-full h-full"
								/>
							</div>
						) : (
							<div
								className={`w-14 h-14 rounded-xl bg-gradient-to-br ${api.color} flex items-center justify-center flex-shrink-0`}
							>
								<span className="text-white text-base font-bold leading-none">
									{api.name.slice(0, 2).toUpperCase()}
								</span>
							</div>
						)}
						{/* Name + desc below the logo */}
						<div className="flex flex-col items-center text-center">
							<span className="text-xs font-semibold text-neutral-800 dark:text-white whitespace-nowrap">
								{api.name}
							</span>
							<span className="text-[10px] text-neutral-500 dark:text-neutral-400 whitespace-nowrap">
								{api.desc}
							</span>
						</div>
					</div>
				))}
			</div>
		</div>
	);
}

export function APIMarquee() {
	const t = useTranslations("homepage");
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.2 });

	const firstRow = SWEDISH_APIS.slice(0, 7);
	const secondRow = SWEDISH_APIS.slice(7);

	return (
		<section
			ref={ref}
			className="relative py-20 md:py-28 overflow-hidden border-t border-neutral-100 dark:border-neutral-800/50"
		>
			{/* Background */}
			<div className="absolute inset-0 -z-10">
				<div className="absolute top-0 left-1/3 w-96 h-96 bg-[radial-gradient(circle,rgba(56,189,248,0.06),transparent_70%)] dark:bg-[radial-gradient(circle,rgba(56,189,248,0.1),transparent_70%)]" />
				<div className="absolute bottom-0 right-1/4 w-96 h-96 bg-[radial-gradient(circle,rgba(168,85,247,0.06),transparent_70%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.1),transparent_70%)]" />
			</div>

			<div className="mx-auto max-w-7xl px-6">
				<motion.div
					className="text-center mb-12"
					initial={{ opacity: 0, y: 20 }}
					animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
					transition={{ duration: 0.6 }}
				>
					<span className="text-sm font-semibold text-purple-600 dark:text-purple-400 uppercase tracking-wider">
						{t("api_section_badge")}
					</span>
					<h2 className="mt-2 text-3xl md:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white">
						{t("api_section_title")}
					</h2>
					<p className="mt-4 text-lg text-neutral-500 dark:text-neutral-400 max-w-2xl mx-auto">
						{t("api_section_subtitle")}
					</p>
				</motion.div>

				<motion.div
					className="space-y-4"
					initial={{ opacity: 0 }}
					animate={isInView ? { opacity: 1 } : { opacity: 0 }}
					transition={{ duration: 0.6, delay: 0.2 }}
				>
					<MarqueeRow items={firstRow} />
					<MarqueeRow items={secondRow} reverse />
				</motion.div>
			</div>
		</section>
	);
}
