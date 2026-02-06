"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as RadioGroup from "@radix-ui/react-radio-group";
import { Info } from "lucide-react";
import type { FC } from "react";
import { useId, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import * as z from "zod";
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { EnumConnectorName } from "@/contracts/enums/connector";
import { DateRangeSelector } from "../../components/date-range-selector";
import { getConnectorBenefits } from "../connector-benefits";
import type { ConnectFormProps } from "../index";

const elasticsearchConnectorFormSchema = z
	.object({
		name: z.string().min(3, {
			message: "Anslutningsnamn måste vara minst 3 tecken.",
		}),
		endpoint_url: z.string().url({ message: "Ange en giltig Elasticsearch endpoint-URL." }),
		auth_method: z.enum(["basic", "api_key"]),
		username: z.string().optional(),
		password: z.string().optional(),
		ELASTICSEARCH_API_KEY: z.string().optional(),
		indices: z.string().optional(),
		query: z.string(),
		search_fields: z.string().optional(),
		max_documents: z.number().min(1).max(10000).optional(),
	})
	.refine(
		(data) => {
			if (data.auth_method === "basic") {
				return Boolean(data.username?.trim() && data.password?.trim());
			}
			if (data.auth_method === "api_key") {
				return Boolean(data.ELASTICSEARCH_API_KEY?.trim());
			}
			return true;
		},
		{
			message: "Autentiseringsuppgifter krävs för vald metod.",
			path: ["auth_method"],
		}
	);

type ElasticsearchConnectorFormValues = z.infer<typeof elasticsearchConnectorFormSchema>;

export const ElasticsearchConnectForm: FC<ConnectFormProps> = ({ onSubmit, isSubmitting }) => {
	const isSubmittingRef = useRef(false);
	const authBasicId = useId();
	const authApiKeyId = useId();
	const [startDate, setStartDate] = useState<Date | undefined>(undefined);
	const [endDate, setEndDate] = useState<Date | undefined>(undefined);
	const [periodicEnabled, setPeriodicEnabled] = useState(false);
	const [frequencyMinutes, setFrequencyMinutes] = useState("1440");

	const form = useForm<ElasticsearchConnectorFormValues>({
		resolver: zodResolver(elasticsearchConnectorFormSchema),
		defaultValues: {
			name: "Elasticsearch-anslutning",
			endpoint_url: "",
			auth_method: "api_key",
			username: "",
			password: "",
			ELASTICSEARCH_API_KEY: "",
			indices: "",
			query: "*",
			search_fields: "",
			max_documents: undefined,
		},
	});

	const stringToArray = (str: string): string[] => {
		const items = str
			.split(",")
			.map((item) => item.trim())
			.filter((item) => item.length > 0);
		return Array.from(new Set(items));
	};

	const handleSubmit = async (values: ElasticsearchConnectorFormValues) => {
		// Prevent multiple submissions
		if (isSubmittingRef.current || isSubmitting) {
			return;
		}

		isSubmittingRef.current = true;
		try {
			// Send full URL to backend (backend expects ELASTICSEARCH_URL)
			const config: Record<string, string | number | boolean | string[]> = {
				ELASTICSEARCH_URL: values.endpoint_url,
				// default to verifying certs; expose fields for CA/verify if UI added later
				ELASTICSEARCH_VERIFY_CERTS: true,
			};

			if (values.auth_method === "basic") {
				if (values.username) config.ELASTICSEARCH_USERNAME = values.username;
				if (values.password) config.ELASTICSEARCH_PASSWORD = values.password;
			} else if (values.auth_method === "api_key") {
				if (values.ELASTICSEARCH_API_KEY)
					config.ELASTICSEARCH_API_KEY = values.ELASTICSEARCH_API_KEY;
			}

			const indicesInput = values.indices?.trim() ?? "";
			const indicesArr = stringToArray(indicesInput);
			config.ELASTICSEARCH_INDEX =
				indicesArr.length === 0 ? "*" : indicesArr.length === 1 ? indicesArr[0] : indicesArr;

			if (values.query && values.query !== "*") {
				config.ELASTICSEARCH_QUERY = values.query;
			}

			if (values.search_fields?.trim()) {
				const fields = stringToArray(values.search_fields);
				config.ELASTICSEARCH_FIELDS = fields;
				config.ELASTICSEARCH_CONTENT_FIELDS = fields;
				if (fields.includes("title")) {
					config.ELASTICSEARCH_TITLE_FIELD = "title";
				}
			}

			if (values.max_documents !== undefined && values.max_documents > 0) {
				config.ELASTICSEARCH_MAX_DOCUMENTS = values.max_documents;
			}

			await onSubmit({
				name: values.name,
				connector_type: EnumConnectorName.ELASTICSEARCH_CONNECTOR,
				config,
				is_indexable: true,
				last_indexed_at: null,
				periodic_indexing_enabled: periodicEnabled,
				indexing_frequency_minutes: periodicEnabled ? parseInt(frequencyMinutes, 10) : null,
				next_scheduled_at: null,
				startDate,
				endDate,
				periodicEnabled,
				frequencyMinutes,
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
					<AlertTitle className="text-xs sm:text-sm">Anslutningsuppgifter krävs</AlertTitle>
					<AlertDescription className="text-[10px] sm:text-xs !pl-0">
						Ange endpoint-URL för ditt Elasticsearch-kluster och autentiseringsuppgifter för att
						ansluta.
					</AlertDescription>
				</div>
			</Alert>

			<div className="rounded-xl border border-border bg-slate-400/5 dark:bg-white/5 p-3 sm:p-6 space-y-3 sm:space-y-4">
				<Form {...form}>
					<form
						id="elasticsearch-connect-form"
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
											placeholder="Min Elasticsearch-anslutning"
											className="h-8 sm:h-10 px-2 sm:px-3 text-xs sm:text-sm border-slate-400/20 focus-visible:border-slate-400/40"
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

						{/* Connection Details */}
						<div className="space-y-4">
							<h3 className="text-sm sm:text-base font-medium">Anslutningsdetaljer</h3>

							<FormField
								control={form.control}
								name="endpoint_url"
								render={({ field }) => (
									<FormItem>
									<FormLabel className="text-xs sm:text-sm">Elasticsearch endpoint-URL</FormLabel>
										<FormControl>
											<Input
												type="url"
												autoComplete="off"
												placeholder="https://your-cluster.es.region.aws.com:443"
												className="h-8 sm:h-10 px-2 sm:px-3 text-xs sm:text-sm border-slate-400/20 focus-visible:border-slate-400/40"
												disabled={isSubmitting}
												{...field}
											/>
										</FormControl>
										<FormDescription className="text-[10px] sm:text-xs">
										Ange den fullständiga endpoint-URL:en för Elasticsearch. Vi extraherar
										automatiskt värdnamn, port och SSL-inställningar.
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>

							{/* Show parsed URL details */}
							{form.watch("endpoint_url") && (
								<div className="rounded-lg border border-border bg-muted/50 p-3">
									<h4 className="text-[10px] sm:text-xs font-medium mb-2">
										Tolkade anslutningsdetaljer:
									</h4>
									<div className="text-[10px] sm:text-xs text-muted-foreground space-y-1">
										{(() => {
											try {
												const url = new URL(form.watch("endpoint_url"));
												return (
													<>
														<div>
															<strong>Värdnamn:</strong> {url.hostname}
														</div>
														<div>
															<strong>Port:</strong>{" "}
															{url.port || (url.protocol === "https:" ? "443" : "80")}
														</div>
														<div>
															<strong>SSL/TLS:</strong>{" "}
															{url.protocol === "https:" ? "Aktiverad" : "Inaktiverad"}
														</div>
													</>
												);
											} catch {
												return <div className="text-destructive">Ogiltigt URL-format</div>;
											}
										})()}
									</div>
								</div>
							)}
						</div>

						{/* Authentication */}
						<div className="space-y-4">
							<h3 className="text-sm sm:text-base font-medium">Autentisering</h3>

							<FormField
								control={form.control}
								name="auth_method"
								render={({ field }) => (
									<FormItem className="space-y-3">
										<FormControl>
											<RadioGroup.Root
												onValueChange={(value) => {
													field.onChange(value);
													// Clear auth fields when method changes
													if (value !== "basic") {
														form.setValue("username", "");
														form.setValue("password", "");
													}
													if (value !== "api_key") {
														form.setValue("ELASTICSEARCH_API_KEY", "");
													}
												}}
												value={field.value}
												className="flex flex-col space-y-2"
											>
												<div className="flex items-center space-x-2">
													<RadioGroup.Item
														value="api_key"
														id={authApiKeyId}
														className="aspect-square h-4 w-4 rounded-full border border-primary text-primary ring-offset-background focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground"
													>
														<RadioGroup.Indicator className="flex items-center justify-center">
															<div className="h-2.5 w-2.5 rounded-full bg-current" />
														</RadioGroup.Indicator>
													</RadioGroup.Item>
													<Label htmlFor={authApiKeyId} className="text-xs sm:text-sm">
														API-nyckel
													</Label>
												</div>

												<div className="flex items-center space-x-2">
													<RadioGroup.Item
														value="basic"
														id={authBasicId}
														className="aspect-square h-4 w-4 rounded-full border border-primary text-primary ring-offset-background focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground"
													>
														<RadioGroup.Indicator className="flex items-center justify-center">
															<div className="h-2.5 w-2.5 rounded-full bg-current" />
														</RadioGroup.Indicator>
													</RadioGroup.Item>
													<Label htmlFor={authBasicId} className="text-xs sm:text-sm">
														Användarnamn och lösenord
													</Label>
												</div>
											</RadioGroup.Root>
										</FormControl>
										<FormMessage />
									</FormItem>
								)}
							/>

							{/* Basic Auth Fields */}
							{form.watch("auth_method") === "basic" && (
								<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
									<FormField
										control={form.control}
										name="username"
										render={({ field }) => (
											<FormItem>
												<FormLabel className="text-xs sm:text-sm">Användarnamn</FormLabel>
												<FormControl>
													<Input
														placeholder="elastic"
														autoComplete="username"
														className="h-8 sm:h-10 px-2 sm:px-3 text-xs sm:text-sm border-slate-400/20 focus-visible:border-slate-400/40"
														disabled={isSubmitting}
														{...field}
													/>
												</FormControl>
												<FormMessage />
											</FormItem>
										)}
									/>

									<FormField
										control={form.control}
										name="password"
										render={({ field }) => (
											<FormItem>
												<FormLabel className="text-xs sm:text-sm">Lösenord</FormLabel>
												<FormControl>
													<Input
														type="password"
														placeholder="Lösenord"
														autoComplete="current-password"
														className="h-8 sm:h-10 px-2 sm:px-3 text-xs sm:text-sm border-slate-400/20 focus-visible:border-slate-400/40"
														disabled={isSubmitting}
														{...field}
													/>
												</FormControl>
												<FormMessage />
											</FormItem>
										)}
									/>
								</div>
							)}

							{/* API Key Field */}
							{form.watch("auth_method") === "api_key" && (
								<FormField
									control={form.control}
									name="ELASTICSEARCH_API_KEY"
									render={({ field }) => (
										<FormItem>
											<FormLabel className="text-xs sm:text-sm">API-nyckel</FormLabel>
											<FormControl>
												<Input
													type="password"
													placeholder="Din API-nyckel här"
													autoComplete="off"
													className="h-8 sm:h-10 px-2 sm:px-3 text-xs sm:text-sm border-slate-400/20 focus-visible:border-slate-400/40"
													disabled={isSubmitting}
													{...field}
												/>
											</FormControl>
											<FormDescription className="text-[10px] sm:text-xs">
												Ange din Elasticsearch API-nyckel (base64-kodad). Den lagras säkert.
											</FormDescription>
											<FormMessage />
										</FormItem>
									)}
								/>
							)}
						</div>

						{/* Index Selection */}
						<FormField
							control={form.control}
							name="indices"
							render={({ field }) => (
								<FormItem>
									<FormLabel className="text-xs sm:text-sm">Indexval</FormLabel>
									<FormControl>
										<Input
											placeholder="logs-*, documents-*, app-logs"
											className="h-8 sm:h-10 px-2 sm:px-3 text-xs sm:text-sm border-slate-400/20 focus-visible:border-slate-400/40"
											disabled={isSubmitting}
											{...field}
										/>
									</FormControl>
									<FormDescription className="text-[10px] sm:text-xs">
										Kommaseparerade index att söka i (t.ex. "logs-*, documents-*").
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>

						{/* Show parsed indices as badges */}
						{form.watch("indices")?.trim() && (
							<div className="rounded-lg border border-border bg-muted/50 p-3">
								<h4 className="text-[10px] sm:text-xs font-medium mb-2">Valda index:</h4>
								<div className="flex flex-wrap gap-2">
									{stringToArray(form.watch("indices") ?? "").map((index) => (
										<Badge key={index} variant="secondary" className="text-[10px]">
											{index}
										</Badge>
									))}
								</div>
							</div>
						)}

						<Alert className="bg-slate-400/5 dark:bg-white/5 border-slate-400/20">
							<Info className="h-3 w-3 sm:h-4 sm:w-4" />
							<AlertTitle className="text-[10px] sm:text-xs">Tips för indexval</AlertTitle>
							<AlertDescription className="text-[9px] sm:text-[10px] mt-2">
								<ul className="list-disc pl-4 space-y-1">
									<li>Använd jokertecken som "logs-*" för att matcha flera index</li>
									<li>Separera flera index med kommatecken</li>
									<li>Lämna tomt för att söka i alla åtkomliga index inklusive interna</li>
									<li>Att välja specifika index förbättrar sökprestanda</li>
								</ul>
							</AlertDescription>
						</Alert>

						{/* Advanced Configuration */}
						<Accordion type="single" collapsible className="w-full">
							<AccordionItem value="advanced">
								<AccordionTrigger className="text-xs sm:text-sm">
									Avancerad konfiguration
								</AccordionTrigger>
								<AccordionContent className="space-y-4">
									{/* Default Search Query */}
									<FormField
										control={form.control}
										name="query"
										render={({ field }) => (
											<FormItem>
												<FormLabel className="text-xs sm:text-sm">
													Standard sökfråga{" "}
													<span className="text-muted-foreground">(valfritt)</span>
												</FormLabel>
												<FormControl>
													<Input
														placeholder="*"
														className="h-8 sm:h-10 px-2 sm:px-3 text-xs sm:text-sm border-slate-400/20 focus-visible:border-slate-400/40"
														disabled={isSubmitting}
														{...field}
													/>
												</FormControl>
												<FormDescription className="text-[10px] sm:text-xs">
													Standardfråga i Elasticsearch att använda för sökningar. Använd "*" för
													att matcha alla dokument.
												</FormDescription>
												<FormMessage />
											</FormItem>
										)}
									/>

									{/* Form Fields */}
									<FormField
										control={form.control}
										name="search_fields"
										render={({ field }) => (
											<FormItem>
												<FormLabel className="text-xs sm:text-sm">
													Sökfält <span className="text-muted-foreground">(valfritt)</span>
												</FormLabel>
												<FormControl>
													<Input
														placeholder="title, content, description"
														className="h-8 sm:h-10 px-2 sm:px-3 text-xs sm:text-sm border-slate-400/20 focus-visible:border-slate-400/40"
														disabled={isSubmitting}
														{...field}
													/>
												</FormControl>
												<FormDescription className="text-[10px] sm:text-xs">
													Kommaseparerad lista över specifika fält att söka i (t.ex. "title, content,
													description"). Lämna tomt för att söka i alla fält.
												</FormDescription>
												<FormMessage />
											</FormItem>
										)}
									/>

									{/* Show parsed search fields as badges */}
									{form.watch("search_fields")?.trim() && (
										<div className="rounded-lg border border-border bg-muted/50 p-3">
											<h4 className="text-[10px] sm:text-xs font-medium mb-2">Sökfält:</h4>
											<div className="flex flex-wrap gap-2">
												{stringToArray(form.watch("search_fields") ?? "").map((field) => (
													<Badge key={field} variant="outline" className="text-[10px]">
														{field}
													</Badge>
												))}
											</div>
										</div>
									)}

									<FormField
										control={form.control}
										name="max_documents"
										render={({ field }) => (
											<FormItem>
												<FormLabel className="text-xs sm:text-sm">
													Maximalt antal dokument{" "}
													<span className="text-muted-foreground">(valfritt)</span>
												</FormLabel>
												<FormControl>
													<Input
														type="number"
														placeholder="1000"
														min="1"
														max="10000"
														className="h-8 sm:h-10 px-2 sm:px-3 text-xs sm:text-sm border-slate-400/20 focus-visible:border-slate-400/40"
														disabled={isSubmitting}
														{...field}
														onChange={(e) =>
															field.onChange(
																e.target.value === "" ? undefined : parseInt(e.target.value, 10)
															)
														}
													/>
												</FormControl>
												<FormDescription className="text-[10px] sm:text-xs">
													Maximalt antal dokument att hämta per sökning (1-10 000). Lämna tomt för
													att använda Elasticsearchs standardgräns.
												</FormDescription>
												<FormMessage />
											</FormItem>
										)}
									/>
								</AccordionContent>
							</AccordionItem>
						</Accordion>

						{/* Indexing Configuration */}
						<div className="space-y-4 pt-4 border-t border-slate-400/20">
							<h3 className="text-sm sm:text-base font-medium">Indexeringskonfiguration</h3>

							{/* Date Range Selector */}
							<DateRangeSelector
								startDate={startDate}
								endDate={endDate}
								onStartDateChange={setStartDate}
								onEndDateChange={setEndDate}
							/>

							{/* Periodic Sync Config */}
							<div className="rounded-xl bg-slate-400/5 dark:bg-white/5 p-3 sm:p-6">
								<div className="flex items-center justify-between">
									<div className="space-y-1">
										<h3 className="font-medium text-sm sm:text-base">Aktivera periodisk synk</h3>
										<p className="text-xs sm:text-sm text-muted-foreground">
											Indexera om automatiskt med regelbundna intervall
										</p>
									</div>
									<Switch
										checked={periodicEnabled}
										onCheckedChange={setPeriodicEnabled}
										disabled={isSubmitting}
									/>
								</div>

								{periodicEnabled && (
									<div className="mt-4 pt-4 border-t border-slate-400/20 space-y-3">
										<div className="space-y-2">
											<Label htmlFor="frequency" className="text-xs sm:text-sm">
												Synkfrekvens
											</Label>
											<Select
												value={frequencyMinutes}
												onValueChange={setFrequencyMinutes}
												disabled={isSubmitting}
											>
												<SelectTrigger
													id="frequency"
													className="w-full bg-slate-400/5 dark:bg-slate-400/5 border-slate-400/20 text-xs sm:text-sm"
												>
													<SelectValue placeholder="Välj frekvens" />
												</SelectTrigger>
												<SelectContent className="z-[100]">
													<SelectItem value="5" className="text-xs sm:text-sm">
														Var 5:e minut
													</SelectItem>
													<SelectItem value="15" className="text-xs sm:text-sm">
														Var 15:e minut
													</SelectItem>
													<SelectItem value="60" className="text-xs sm:text-sm">
														Varje timme
													</SelectItem>
													<SelectItem value="360" className="text-xs sm:text-sm">
														Var 6:e timme
													</SelectItem>
													<SelectItem value="720" className="text-xs sm:text-sm">
														Var 12:e timme
													</SelectItem>
													<SelectItem value="1440" className="text-xs sm:text-sm">
														Dagligen
													</SelectItem>
													<SelectItem value="10080" className="text-xs sm:text-sm">
														Veckovis
													</SelectItem>
												</SelectContent>
											</Select>
										</div>
									</div>
								)}
							</div>
						</div>
					</form>
				</Form>
			</div>

			{/* What you get section */}
			{getConnectorBenefits(EnumConnectorName.ELASTICSEARCH_CONNECTOR) && (
				<div className="rounded-xl border border-border bg-slate-400/5 dark:bg-white/5 px-3 sm:px-6 py-4 space-y-2">
					<h4 className="text-xs sm:text-sm font-medium">
						Det här får du med Elasticsearch-integrationen:
					</h4>
					<ul className="list-disc pl-5 text-[10px] sm:text-xs text-muted-foreground space-y-1">
						{getConnectorBenefits(EnumConnectorName.ELASTICSEARCH_CONNECTOR)?.map((benefit) => (
							<li key={benefit}>{benefit}</li>
						))}
					</ul>
				</div>
			)}

			{/* Documentation Section */}
			<Accordion
				type="single"
				collapsible
				className="w-full border border-border rounded-xl bg-slate-400/5 dark:bg-white/5"
			>
				<AccordionItem value="documentation" className="border-0">
					<AccordionTrigger className="text-sm sm:text-base font-medium px-3 sm:px-6 no-underline hover:no-underline">
						Dokumentation
					</AccordionTrigger>
					<AccordionContent className="px-3 sm:px-6 pb-3 sm:pb-6 space-y-6">
						<div>
							<h3 className="text-sm sm:text-base font-semibold mb-2">Så fungerar det</h3>
							<p className="text-[10px] sm:text-xs text-muted-foreground">
								Elasticsearch-anslutningen låter dig söka och hämta dokument från ditt
								Elasticsearch-kluster. Konfigurera anslutningsdetaljer, välj specifika index och
								ange sökparametrar för att göra din befintliga data sökbar i Oneseek.
							</p>
						</div>

						<div className="space-y-4">
							<div>
								<h3 className="text-sm sm:text-base font-semibold mb-2">Anslutningsinställning</h3>
								<div className="space-y-4 sm:space-y-6">
									<div>
										<h4 className="text-[10px] sm:text-xs font-medium mb-2">
											Steg 1: Hämta din Elasticsearch-endpoint
										</h4>
										<p className="text-[10px] sm:text-xs text-muted-foreground mb-3">
											Du behöver endpoint-URL:en för ditt Elasticsearch-kluster. Den ser vanligtvis
											ut så här:
										</p>
										<ul className="list-disc pl-5 space-y-1 text-[10px] sm:text-xs text-muted-foreground mb-4">
											<li>
												Moln:{" "}
												<code className="bg-muted px-1 py-0.5 rounded">
													https://your-cluster.es.region.aws.com:443
												</code>
											</li>
											<li>
												Självhostad:{" "}
												<code className="bg-muted px-1 py-0.5 rounded">
													https://elasticsearch.example.com:9200
												</code>
											</li>
										</ul>
									</div>

									<div>
										<h4 className="text-[10px] sm:text-xs font-medium mb-2">
											Steg 2: Konfigurera autentisering
										</h4>
										<p className="text-[10px] sm:text-xs text-muted-foreground mb-3">
											Elasticsearch kräver autentisering. Du kan använda:
										</p>
										<ul className="list-disc pl-5 space-y-2 text-[10px] sm:text-xs text-muted-foreground mb-4">
											<li>
												<strong>API-nyckel:</strong> En base64-kodad API-nyckel. Du kan skapa en i
												Elasticsearch genom att köra:
												<pre className="bg-muted p-2 rounded mt-1 text-[9px] overflow-x-auto">
													<code>POST /_security/api_key</code>
												</pre>
											</li>
											<li>
												<strong>Användarnamn och lösenord:</strong> Grundläggande autentisering med
												ditt Elasticsearch-användarnamn och lösenord.
											</li>
										</ul>
									</div>

									<div>
										<h4 className="text-[10px] sm:text-xs font-medium mb-2">
											Steg 3: Välj index
										</h4>
										<p className="text-[10px] sm:text-xs text-muted-foreground mb-3">
											Ange vilka index som ska sökas. Du kan:
										</p>
										<ul className="list-disc pl-5 space-y-1 text-[10px] sm:text-xs text-muted-foreground">
											<li>
												Använd jokertecken:{" "}
												<code className="bg-muted px-1 py-0.5 rounded">logs-*</code> för att matcha
												flera index
											</li>
											<li>
												Ange specifika index:{" "}
												<code className="bg-muted px-1 py-0.5 rounded">
													logs-2024, documents-2024
												</code>
											</li>
											<li>
												Lämna tomt för att söka i alla åtkomliga index (rekommenderas inte för
												prestanda)
											</li>
										</ul>
									</div>
								</div>
							</div>
						</div>

						<div className="space-y-4">
							<div>
								<h3 className="text-sm sm:text-base font-semibold mb-2">Avancerad konfiguration</h3>
								<div className="space-y-4">
									<div>
										<h4 className="text-[10px] sm:text-xs font-medium mb-2">Sökfråga</h4>
										<p className="text-[10px] sm:text-xs text-muted-foreground mb-2">
											Standardfrågan som används för sökningar. Använd{" "}
											<code className="bg-muted px-1 py-0.5 rounded">*</code> för att matcha alla
											dokument, eller ange en mer komplex Elasticsearch-fråga.
										</p>
									</div>

									<div>
										<h4 className="text-[10px] sm:text-xs font-medium mb-2">Sökfält</h4>
										<p className="text-[10px] sm:text-xs text-muted-foreground mb-2">
											Begränsa sökningar till specifika fält för bättre prestanda. Vanliga fält är:
										</p>
										<ul className="list-disc pl-5 space-y-1 text-[10px] sm:text-xs text-muted-foreground">
											<li>
												<code className="bg-muted px-1 py-0.5 rounded">title</code> - Dokumenttitlar
											</li>
											<li>
												<code className="bg-muted px-1 py-0.5 rounded">content</code> - Huvudinnehåll
											</li>
											<li>
												<code className="bg-muted px-1 py-0.5 rounded">description</code> -
												Beskrivningar
											</li>
										</ul>
										<p className="text-[10px] sm:text-xs text-muted-foreground mt-2">
											Lämna tomt för att söka i alla fält i dina dokument.
										</p>
									</div>

									<div>
										<h4 className="text-[10px] sm:text-xs font-medium mb-2">Maximalt antal dokument</h4>
										<p className="text-[10px] sm:text-xs text-muted-foreground">
											Sätt en gräns för antalet dokument som hämtas per sökning (1-10 000). Detta
											hjälper till att kontrollera svarstider och resursanvändning. Lämna tomt för
											att använda Elasticsearchs standardgräns.
										</p>
									</div>
								</div>
							</div>
						</div>

						<div className="space-y-4">
							<div>
								<h3 className="text-sm sm:text-base font-semibold mb-2">Felsökning</h3>
								<div className="space-y-4">
									<div>
										<h4 className="text-[10px] sm:text-xs font-medium mb-2">Anslutningsproblem</h4>
										<ul className="list-disc pl-5 space-y-2 text-[10px] sm:text-xs text-muted-foreground">
											<li>
												<strong>Ogiltig URL:</strong> Kontrollera att endpoint-URL:en inkluderar
												protokoll (https://) och portnummer om det krävs.
											</li>
											<li>
												<strong>SSL/TLS-fel:</strong> Kontrollera att ditt kluster använder HTTPS
												och att certifikatet är giltigt. Självsignerade certifikat kan kräva
												ytterligare konfiguration.
											</li>
											<li>
												<strong>Anslutningstimeout:</strong> Kontrollera nätverksanslutning och
												brandväggsinställningar. Se till att Elasticsearch-klustret är åtkomligt
												från Oneseek-servrar.
											</li>
										</ul>
									</div>

									<div>
										<h4 className="text-[10px] sm:text-xs font-medium mb-2">
											Autentiseringsproblem
										</h4>
										<ul className="list-disc pl-5 space-y-2 text-[10px] sm:text-xs text-muted-foreground">
											<li>
												<strong>Ogiltiga uppgifter:</strong> Kontrollera användarnamn/lösenord eller
												API-nyckel. API-nycklar måste vara base64-kodade.
											</li>
											<li>
												<strong>Åtkomst nekad:</strong> Se till att din API-nyckel eller ditt konto
												har läsbehörighet för indexen du vill söka i.
											</li>
											<li>
												<strong>API-nyckelns format:</strong> Elasticsearch API-nycklar är vanligtvis
												base64-kodade strängar. Se till att du använder hela nyckeln.
											</li>
										</ul>
									</div>

									<div>
										<h4 className="text-[10px] sm:text-xs font-medium mb-2">Sökproblem</h4>
										<ul className="list-disc pl-5 space-y-2 text-[10px] sm:text-xs text-muted-foreground">
											<li>
												<strong>Inga resultat:</strong> Kontrollera att ditt indexval matchar
												befintliga index. Använd jokertecken med försiktighet.
											</li>
											<li>
												<strong>Långsamma sökningar:</strong> Begränsa antalet index eller använd
												specifika indexnamn i stället för jokertecken. Minska gränsen för maximala
												antal dokument.
											</li>
											<li>
												<strong>Fält hittades inte:</strong> Se till att sökfälten du anger faktiskt
												finns i dina Elasticsearch-dokument.
											</li>
										</ul>
									</div>

									<Alert className="bg-slate-400/5 dark:bg-white/5 border-slate-400/20 mt-4">
										<Info className="h-3 w-3 sm:h-4 sm:w-4" />
										<AlertTitle className="text-[10px] sm:text-xs">Behöver du mer hjälp?</AlertTitle>
										<AlertDescription className="text-[9px] sm:text-[10px]">
											Om du fortsätter att ha problem, kontrollera loggarna för ditt
											Elasticsearch-kluster och att klusterversionen är kompatibel. För
											Elasticsearch Cloud-installationer, kontrollera åtkomstpolicyer och IP-listor.
										</AlertDescription>
									</Alert>
								</div>
							</div>
						</div>
					</AccordionContent>
				</AccordionItem>
			</Accordion>
		</div>
	);
};
