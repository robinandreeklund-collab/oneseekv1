"use client";

import { motion, useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

function AnimatedCounter({
	target,
	suffix = "",
	prefix = "",
	duration = 2000,
	delay = 0,
}: {
	target: number;
	suffix?: string;
	prefix?: string;
	duration?: number;
	delay?: number;
}) {
	const [count, setCount] = useState(0);
	const ref = useRef<HTMLSpanElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.5 });
	const hasStarted = useRef(false);

	useEffect(() => {
		if (!isInView || hasStarted.current) return;
		hasStarted.current = true;

		const startTime = Date.now() + delay;
		const animate = () => {
			const now = Date.now();
			if (now < startTime) {
				requestAnimationFrame(animate);
				return;
			}
			const elapsed = now - startTime;
			const progress = Math.min(elapsed / duration, 1);
			const eased = 1 - Math.pow(1 - progress, 3);
			setCount(Math.floor(eased * target));
			if (progress < 1) {
				requestAnimationFrame(animate);
			}
		};
		requestAnimationFrame(animate);
	}, [isInView, target, duration, delay]);

	return (
		<span ref={ref}>
			{prefix}
			{count}
			{suffix}
		</span>
	);
}

export function StatsBar() {
	const t = useTranslations("homepage");
	const ref = useRef<HTMLDivElement>(null);
	const isInView = useInView(ref, { once: true, amount: 0.3 });

	const stats = [
		{
			value: 7,
			suffix: "",
			label: t("stats_ai_models"),
		},
		{
			value: 13,
			suffix: "",
			label: t("stats_swedish_apis"),
		},
		{
			value: 23,
			suffix: "",
			label: t("stats_pipeline_nodes"),
		},
	];

	return (
		<section ref={ref} className="relative py-16 md:py-20">
			<div className="mx-auto max-w-5xl px-6">
				<motion.div
					className="grid grid-cols-3 gap-8 md:gap-16 max-w-3xl mx-auto"
					initial={{ opacity: 0, y: 20 }}
					animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
					transition={{ duration: 0.6 }}
				>
					{stats.map((stat, i) => (
						<motion.div
							key={stat.label}
							className="text-center"
							initial={{ opacity: 0, y: 10 }}
							animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
							transition={{ duration: 0.4, delay: i * 0.1 }}
						>
							<div className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-br from-purple-600 to-blue-600 dark:from-purple-400 dark:to-blue-400">
								<AnimatedCounter
									target={stat.value}
									suffix={stat.suffix}
									duration={1500}
									delay={i * 100}
								/>
							</div>
							<div className="mt-2 text-sm text-neutral-500 dark:text-neutral-400 font-medium">
								{stat.label}
							</div>
						</motion.div>
					))}
				</motion.div>
			</div>
		</section>
	);
}
