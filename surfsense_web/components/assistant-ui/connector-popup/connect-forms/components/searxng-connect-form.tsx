"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Info } from "lucide-react";
import type { FC } from "react";
import { useRef } from "react";
import { useForm } from "react-hook-form";
import * as z from "zod";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
	Form,
	FormControl,
	FormDescription,
	FormField,
	FormItem,
	FormLabel,
	FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { EnumConnectorName } from "@/contracts/enums/connector";
import { getConnectorBenefits } from "../connector-benefits";
import type { ConnectFormProps } from "../index";

const searxngFormSchema = z.object({
	name: z.string().min(3, {
		message: "Anslutningsnamn måste vara minst 3 tecken.",
	}),
	host: z
		.string()
		.min(1, { message: "Värd krävs." })
		.url({ message: "Ange en giltig SearxNG-värd-URL (t.ex. https://searxng.example.org)." }),
	api_key: z.string().optional(),
	engines: z.string().optional(),
	categories: z.string().optional(),
	language: z.string().optional(),
	safesearch: z
		.string()
		.regex(/^[0-2]?$/, { message: "SafeSearch måste vara 0, 1 eller 2." })
		.optional(),
	verify_ssl: z.boolean(),
});

type SearxngFormValues = z.infer<typeof searxngFormSchema>;

const parseCommaSeparated = (value?: string | null) => {
	if (!value) return undefined;
	const items = value
		.split(",")
		.map((item) => item.trim())
		.filter((item) => item.length > 0);
	return items.length > 0 ? items : undefined;
};

export const SearxngConnectForm: FC<ConnectFormProps> = ({ onSubmit, isSubmitting }) => {
	const isSubmittingRef = useRef(false);
	const form = useForm<SearxngFormValues>({
		resolver: zodResolver(searxngFormSchema),
		defaultValues: {
			name: "SearxNG-anslutning",
			host: "",
			api_key: "",
			engines: "",
			categories: "",
			language: "",
			safesearch: "",
			verify_ssl: true,
		},
	});

	const handleSubmit = async (values: SearxngFormValues) => {
		// Prevent multiple submissions
		if (isSubmittingRef.current || isSubmitting) {
			return;
		}

		isSubmittingRef.current = true;
		try {
			const config: Record<string, unknown> = {
				SEARXNG_HOST: values.host.trim(),
			};

			const apiKey = values.api_key?.trim();
			if (apiKey) config.SEARXNG_API_KEY = apiKey;

			const engines = parseCommaSeparated(values.engines);
			if (engines) config.SEARXNG_ENGINES = engines;

			const categories = parseCommaSeparated(values.categories);
			if (categories) config.SEARXNG_CATEGORIES = categories;

			const language = values.language?.trim();
			if (language) config.SEARXNG_LANGUAGE = language;

			const safesearch = values.safesearch?.trim();
			if (safesearch) {
				const parsed = Number(safesearch);
				if (!Number.isNaN(parsed)) {
					config.SEARXNG_SAFESEARCH = parsed;
				}
			}

			// Include verify flag only when disabled to keep config minimal
			if (values.verify_ssl === false) {
				config.SEARXNG_VERIFY_SSL = false;
			}

			await onSubmit({
				name: values.name,
				connector_type: EnumConnectorName.SEARXNG_API,
				config,
				is_indexable: false,
				last_indexed_at: null,
				periodic_indexing_enabled: false,
				indexing_frequency_minutes: null,
				next_scheduled_at: null,
			});
		} finally {
			isSubmittingRef.current = false;
		}
	};

	return (
		<div className="space-y-6 pb-6">
			<Alert className="bg-slate-400/5 dark:bg-white/5 border-slate-400/20 p-2 sm:p-3 flex items-center [&>svg]:relative [&>svg]:left-0 [&>svg]:top-0 [&>svg+div]:translate-y-0">
				<Info className="h-3 w-3 sm:h-4 sm:w-4 shrink-0 ml-1" />
				<div className="-ml-1">
					<AlertTitle className="text-xs sm:text-sm">SearxNG-instans krävs</AlertTitle>
					<AlertDescription className="text-[10px] sm:text-xs !pl-0">
						Du behöver åtkomst till en körande SearxNG-instans. Se{" "}
						<a
							href="https://docs.searxng.org/admin/installation-docker.html"
							target="_blank"
							rel="noopener noreferrer"
							className="font-medium underline underline-offset-4"
						>
							SearxNG installationsguide
						</a>{" "}
						för installationsinstruktioner. Om din instans kräver en API-nyckel, ange den nedan.
					</AlertDescription>
				</div>
			</Alert>

			<div className="rounded-xl border border-border bg-slate-400/5 dark:bg-white/5 p-3 sm:p-6 space-y-3 sm:space-y-4">
				<Form {...form}>
					<form
						id="searxng-connect-form"
						onSubmit={form.handleSubmit(handleSubmit)}
						className="space-y-4 sm:space-y-6"
					>
						<FormField
							control={form.control}
							name="name"
							render={({ field }) => (
								<FormItem>
									<FormLabel className="text-xs sm:text-sm">Anslutningsnamn</FormLabel>
									<FormControl>
										<Input
											placeholder="Min SearxNG-anslutning"
											className="border-slate-400/20 focus-visible:border-slate-400/40"
											disabled={isSubmitting}
											{...field}
										/>
									</FormControl>
									<FormDescription className="text-[10px] sm:text-xs">
										Ett vänligt namn för att identifiera anslutningen.
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>

						<FormField
							control={form.control}
							name="host"
							render={({ field }) => (
								<FormItem>
									<FormLabel className="text-xs sm:text-sm">SearxNG-värd</FormLabel>
									<FormControl>
										<Input
											placeholder="https://searxng.example.org"
											className="border-slate-400/20 focus-visible:border-slate-400/40"
											disabled={isSubmitting}
											{...field}
										/>
									</FormControl>
									<FormDescription className="text-[10px] sm:text-xs">
										Ange fullständig bas-URL till din SearxNG-instans. Inkludera protokoll
										(http/https).
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>

						<FormField
							control={form.control}
							name="api_key"
							render={({ field }) => (
								<FormItem>
									<FormLabel className="text-xs sm:text-sm">API-nyckel (valfritt)</FormLabel>
									<FormControl>
										<Input
											type="password"
											placeholder="Ange API-nyckel om din instans kräver en"
											className="border-slate-400/20 focus-visible:border-slate-400/40"
											disabled={isSubmitting}
											{...field}
										/>
									</FormControl>
									<FormDescription className="text-[10px] sm:text-xs">
										Lämna tomt om din SearxNG-instans inte kräver API-nycklar.
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>

						<div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
							<FormField
								control={form.control}
								name="engines"
								render={({ field }) => (
									<FormItem>
										<FormLabel className="text-xs sm:text-sm">Sökmotorer (valfritt)</FormLabel>
										<FormControl>
											<Input
												placeholder="google,bing,duckduckgo"
												className="border-slate-400/20 focus-visible:border-slate-400/40"
												disabled={isSubmitting}
												{...field}
											/>
										</FormControl>
										<FormDescription className="text-[10px] sm:text-xs">
											Kommaseparerad lista för att rikta in sig på specifika motorer.
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>

							<FormField
								control={form.control}
								name="categories"
								render={({ field }) => (
									<FormItem>
										<FormLabel className="text-xs sm:text-sm">Kategorier (valfritt)</FormLabel>
										<FormControl>
											<Input
												placeholder="general,it,science"
												className="border-slate-400/20 focus-visible:border-slate-400/40"
												disabled={isSubmitting}
												{...field}
											/>
										</FormControl>
										<FormDescription className="text-[10px] sm:text-xs">
											Kommaseparerad lista över SearxNG-kategorier.
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>
						</div>

						<div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
							<FormField
								control={form.control}
								name="language"
								render={({ field }) => (
									<FormItem>
										<FormLabel className="text-xs sm:text-sm">
											Föredraget språk (valfritt)
										</FormLabel>
										<FormControl>
											<Input
												placeholder="en-US"
												className="border-slate-400/20 focus-visible:border-slate-400/40"
												disabled={isSubmitting}
												{...field}
											/>
										</FormControl>
										<FormDescription className="text-[10px] sm:text-xs">
											IETF-språktagg (t.ex. en, en-US). Lämna tomt för att använda standardinställningar.
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>

							<FormField
								control={form.control}
								name="safesearch"
								render={({ field }) => (
									<FormItem>
										<FormLabel className="text-xs sm:text-sm">
											SafeSearch-nivå (valfritt)
										</FormLabel>
										<FormControl>
											<Input
												placeholder="0 (av), 1 (måttlig), 2 (strikt)"
												className="border-slate-400/20 focus-visible:border-slate-400/40"
												disabled={isSubmitting}
												{...field}
											/>
										</FormControl>
										<FormDescription className="text-[10px] sm:text-xs">
											Ange 0, 1 eller 2 för att justera SafeSearch-filtrering. Lämna tomt för att
											använda instansens standard.
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>
						</div>

						<FormField
							control={form.control}
							name="verify_ssl"
							render={({ field }) => (
								<FormItem className="flex items-center justify-between rounded-lg border border-slate-400/20 p-3 sm:p-4">
									<div>
										<FormLabel className="text-xs sm:text-sm">Verifiera SSL-certifikat</FormLabel>
										<FormDescription className="text-[10px] sm:text-xs">
											Inaktivera endast vid anslutning till instanser med självsignerade certifikat.
										</FormDescription>
									</div>
									<FormControl>
										<Switch
											checked={field.value}
											onCheckedChange={field.onChange}
											disabled={isSubmitting}
										/>
									</FormControl>
								</FormItem>
							)}
						/>
					</form>
				</Form>
			</div>

			{/* What you get section */}
			{getConnectorBenefits(EnumConnectorName.SEARXNG_API) && (
				<div className="rounded-xl border border-border bg-slate-400/5 dark:bg-white/5 px-3 sm:px-6 py-4 space-y-2">
					<h4 className="text-xs sm:text-sm font-medium">Det här får du med SearxNG:</h4>
					<ul className="list-disc pl-5 text-[10px] sm:text-xs text-muted-foreground space-y-1">
						{getConnectorBenefits(EnumConnectorName.SEARXNG_API)?.map((benefit) => (
							<li key={benefit}>{benefit}</li>
						))}
					</ul>
				</div>
			)}
		</div>
	);
};
