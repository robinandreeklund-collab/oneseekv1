"use client";

import { motion, useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { useRef } from "react";

const SWEDISH_APIS = [
	{ name: "SCB", desc: "Statistiska Centralbyrån", color: "from-blue-500 to-blue-600" },
	{ name: "SMHI", desc: "Klimat & Väderdata", color: "from-cyan-500 to-teal-600" },
	{ name: "Bolagsverket", desc: "Företagsregister", color: "from-amber-500 to-orange-600" },
	{ name: "Trafikverket", desc: "Infrastruktur & Trafik", color: "from-emerald-500 to-green-600" },
	{ name: "Riksdagen", desc: "Lagstiftning & Politik", color: "from-red-500 to-rose-600" },
	{ name: "Kolada", desc: "Kommunal Statistik", color: "from-purple-500 to-violet-600" },
	{ name: "Tavily", desc: "Webbsökning", color: "from-indigo-500 to-blue-600" },
	{ name: "Skatteverket", desc: "Skatt & Folkbokföring", color: "from-yellow-500 to-amber-600" },
	{ name: "Skolverket", desc: "Utbildningsstatistik", color: "from-teal-500 to-cyan-600" },
	{ name: "Jordbruksverket", desc: "Jordbruk & Livsmedel", color: "from-lime-500 to-green-600" },
	{ name: "SCB Befolkning", desc: "Befolkningsdata", color: "from-pink-500 to-rose-600" },
	{ name: "Valmyndigheten", desc: "Valstatistik", color: "from-violet-500 to-purple-600" },
	{ name: "Naturvårdsverket", desc: "Miljödata", color: "from-green-500 to-emerald-600" },
];

function MarqueeRow({ items, reverse = false }: { items: typeof SWEDISH_APIS; reverse?: boolean }) {
	const duplicated = [...items, ...items];

	return (
		<div className="flex overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
			<div
				className={`flex gap-4 py-2 ${reverse ? "[animation-direction:reverse]" : ""} animate-marquee`}
			>
				{duplicated.map((api, i) => (
					<div
						key={`${api.name}-${i}`}
						className="group flex-shrink-0 flex items-center gap-3 rounded-xl border border-neutral-200/50 dark:border-white/10 bg-white/60 dark:bg-neutral-900/40 backdrop-blur-sm px-5 py-3 transition-all duration-300 hover:border-purple-300 dark:hover:border-purple-500/30 hover:shadow-lg hover:shadow-purple-500/5"
					>
						<div
							className={`w-8 h-8 rounded-lg bg-gradient-to-br ${api.color} flex items-center justify-center flex-shrink-0`}
						>
							<span className="text-white text-[10px] font-bold leading-none">
								{api.name.slice(0, 2).toUpperCase()}
							</span>
						</div>
						<div className="flex flex-col">
							<span className="text-sm font-semibold text-neutral-800 dark:text-white whitespace-nowrap">
								{api.name}
							</span>
							<span className="text-[11px] text-neutral-500 dark:text-neutral-400 whitespace-nowrap">
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
