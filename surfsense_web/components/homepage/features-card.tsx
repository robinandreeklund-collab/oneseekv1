"use client";

import { GitCompare, MessageSquare, Network, Eye } from "lucide-react";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export function FeaturesCards() {
	const t = useTranslations("homepage");

	return (
		<section className="py-16 md:py-24 bg-white dark:bg-neutral-950">
			<div className="@container mx-auto max-w-7xl px-4">
				<div className="text-center mb-16">
					<h2 className="text-balance text-3xl font-bold text-gray-900 lg:text-5xl dark:text-white">
						{t("features_title")}
					</h2>
					<p className="mt-6 text-lg text-gray-600 dark:text-gray-400 max-w-3xl mx-auto">
						{t("features_subtitle")}
					</p>
				</div>
				<div className="@min-4xl:max-w-full @min-4xl:grid-cols-4 mx-auto grid max-w-sm gap-6 md:gap-6">
					<Card className="group border-gray-200 bg-white dark:border-neutral-800 dark:bg-neutral-900 hover:shadow-lg transition-shadow">
						<CardHeader className="pb-4">
							<div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/20">
								<GitCompare className="h-6 w-6 text-blue-600 dark:text-blue-400" aria-hidden />
							</div>
							<h3 className="text-xl font-semibold text-gray-900 dark:text-white">{t("feature_model_compare_title")}</h3>
						</CardHeader>
						<CardContent>
							<p className="text-base text-gray-600 dark:text-gray-400">{t("feature_model_compare_desc")}</p>
						</CardContent>
					</Card>

					<Card className="group border-gray-200 bg-white dark:border-neutral-800 dark:bg-neutral-900 hover:shadow-lg transition-shadow">
						<CardHeader className="pb-4">
							<div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-purple-50 dark:bg-purple-900/20">
								<MessageSquare className="h-6 w-6 text-purple-600 dark:text-purple-400" aria-hidden />
							</div>
							<h3 className="text-xl font-semibold text-gray-900 dark:text-white">{t("feature_ai_debates_title")}</h3>
						</CardHeader>
						<CardContent>
							<p className="text-base text-gray-600 dark:text-gray-400">{t("feature_ai_debates_desc")}</p>
						</CardContent>
					</Card>

					<Card className="group border-gray-200 bg-white dark:border-neutral-800 dark:bg-neutral-900 hover:shadow-lg transition-shadow">
						<CardHeader className="pb-4">
							<div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-green-50 dark:bg-green-900/20">
								<Eye className="h-6 w-6 text-green-600 dark:text-green-400" aria-hidden />
							</div>
							<h3 className="text-xl font-semibold text-gray-900 dark:text-white">{t("feature_transparency_title")}</h3>
						</CardHeader>
						<CardContent>
							<p className="text-base text-gray-600 dark:text-gray-400">{t("feature_transparency_desc")}</p>
						</CardContent>
					</Card>

					<Card className="group border-gray-200 bg-white dark:border-neutral-800 dark:bg-neutral-900 hover:shadow-lg transition-shadow">
						<CardHeader className="pb-4">
							<div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-orange-50 dark:bg-orange-900/20">
								<Network className="h-6 w-6 text-orange-600 dark:text-orange-400" aria-hidden />
							</div>
							<h3 className="text-xl font-semibold text-gray-900 dark:text-white">{t("feature_swedish_apis_title")}</h3>
						</CardHeader>
						<CardContent>
							<p className="text-base text-gray-600 dark:text-gray-400">{t("feature_swedish_apis_desc")}</p>
						</CardContent>
					</Card>
				</div>
			</div>
		</section>
	);
}

const CardDecorator = ({ children }: { children: ReactNode }) => (
	<div
		aria-hidden
		className="relative mx-auto size-36 mask-[radial-gradient(ellipse_50%_50%_at_50%_50%,#000_70%,transparent_100%)]"
	>
		<div className="absolute inset-0 [--border:black] dark:[--border:white] bg-[linear-gradient(to_right,var(--border)_1px,transparent_1px),linear-gradient(to_bottom,var(--border)_1px,transparent_1px)] bg-size-[24px_24px] opacity-10" />
		<div className="bg-background absolute inset-0 m-auto flex size-12 items-center justify-center border-t border-l">
			{children}
		</div>
	</div>
);
