"use client";
import { IconMessageCircleQuestion } from "@tabler/icons-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

export function CTAHomepage() {
	const t = useTranslations("homepage");

	return (
		<section className="w-full py-20 md:py-32 bg-gray-50 dark:bg-neutral-900">
			<div className="max-w-7xl mx-auto px-4">
				<div className="max-w-4xl mx-auto text-center">
					<h2 className="text-3xl md:text-5xl font-bold text-gray-900 dark:text-white mb-6">
						{t("cta_transform")}{" "}
						<span className="text-black dark:text-white">{t("cta_transform_bold")}</span>
					</h2>
					<p className="text-lg md:text-xl text-gray-600 dark:text-gray-300 mb-10">
						{t("cta_unite_start")} <span className="font-semibold text-blue-600 dark:text-blue-400">{t("cta_unite_knowledge")}</span>{" "}
						{t("cta_unite_middle")} <span className="font-semibold text-indigo-600 dark:text-indigo-400">{t("cta_unite_search")}</span>.
					</p>

					<Link href="/contact">
						<button
							type="button"
							className="inline-flex items-center gap-2 px-6 py-3 text-base font-medium text-white bg-black rounded-lg hover:bg-gray-800 transition-colors dark:bg-white dark:text-black dark:hover:bg-gray-100"
						>
							<span>{t("cta_talk_to_us")}</span>
							<IconMessageCircleQuestion className="h-5 w-5" />
						</button>
					</Link>
				</div>
			</div>
		</section>
	);
}

const GridLineHorizontal = ({ className, offset }: { className?: string; offset?: string }) => {
	return (
		<div
			style={
				{
					"--background": "#ffffff",
					"--color": "rgba(0, 0, 0, 0.2)",
					"--height": "1px",
					"--width": "5px",
					"--fade-stop": "90%",
					"--offset": offset || "200px", //-100px if you want to keep the line inside
					"--color-dark": "rgba(255, 255, 255, 0.2)",
					maskComposite: "exclude",
				} as React.CSSProperties
			}
			className={cn(
				"absolute w-[calc(100%+var(--offset))] h-[var(--height)] left-[calc(var(--offset)/2*-1)]",
				"bg-[linear-gradient(to_right,var(--color),var(--color)_50%,transparent_0,transparent)]",
				"[background-size:var(--width)_var(--height)]",
				"[mask:linear-gradient(to_left,var(--background)_var(--fade-stop),transparent),_linear-gradient(to_right,var(--background)_var(--fade-stop),transparent),_linear-gradient(black,black)]",
				"[mask-composite:exclude]",
				"z-30",
				"dark:bg-[linear-gradient(to_right,var(--color-dark),var(--color-dark)_50%,transparent_0,transparent)]",
				className
			)}
		></div>
	);
};

const GridLineVertical = ({ className, offset }: { className?: string; offset?: string }) => {
	return (
		<div
			style={
				{
					"--background": "#ffffff",
					"--color": "rgba(0, 0, 0, 0.2)",
					"--height": "5px",
					"--width": "1px",
					"--fade-stop": "90%",
					"--offset": offset || "150px", //-100px if you want to keep the line inside
					"--color-dark": "rgba(255, 255, 255, 0.2)",
					maskComposite: "exclude",
				} as React.CSSProperties
			}
			className={cn(
				"absolute h-[calc(100%+var(--offset))] w-[var(--width)] top-[calc(var(--offset)/2*-1)]",
				"bg-[linear-gradient(to_bottom,var(--color),var(--color)_50%,transparent_0,transparent)]",
				"[background-size:var(--width)_var(--height)]",
				"[mask:linear-gradient(to_top,var(--background)_var(--fade-stop),transparent),_linear-gradient(to_bottom,var(--background)_var(--fade-stop),transparent),_linear-gradient(black,black)]",
				"[mask-composite:exclude]",
				"z-30",
				"dark:bg-[linear-gradient(to_bottom,var(--color-dark),var(--color-dark)_50%,transparent_0,transparent)]",
				className
			)}
		></div>
	);
};
