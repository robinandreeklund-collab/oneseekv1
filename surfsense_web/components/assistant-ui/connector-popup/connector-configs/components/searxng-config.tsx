"use client";

import { Globe, KeyRound } from "lucide-react";
import type { FC } from "react";
import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { ConnectorConfigProps } from "../index";

export interface SearxngConfigProps extends ConnectorConfigProps {
	onNameChange?: (name: string) => void;
}

const arrayToString = (arr: unknown): string => {
	if (!arr) return "";
	if (Array.isArray(arr)) {
		return arr.join(", ");
	}
	return String(arr);
};

const stringToArray = (value: string): string[] | undefined => {
	if (!value) return undefined;
	const items = value
		.split(",")
		.map((item) => item.trim())
		.filter((item) => item.length > 0);
	return items.length > 0 ? items : undefined;
};

export const SearxngConfig: FC<SearxngConfigProps> = ({
	connector,
	onConfigChange,
	onNameChange,
}) => {
	const [host, setHost] = useState<string>((connector.config?.SEARXNG_HOST as string) || "");
	const [apiKey, setApiKey] = useState<string>((connector.config?.SEARXNG_API_KEY as string) || "");
	const [engines, setEngines] = useState<string>(arrayToString(connector.config?.SEARXNG_ENGINES));
	const [categories, setCategories] = useState<string>(
		arrayToString(connector.config?.SEARXNG_CATEGORIES)
	);
	const [language, setLanguage] = useState<string>(
		(connector.config?.SEARXNG_LANGUAGE as string) || ""
	);
	const [safesearch, setSafesearch] = useState<string>(
		connector.config?.SEARXNG_SAFESEARCH !== undefined
			? String(connector.config.SEARXNG_SAFESEARCH)
			: ""
	);
	const [verifySsl, setVerifySsl] = useState<boolean>(
		connector.config?.SEARXNG_VERIFY_SSL !== undefined
			? (connector.config.SEARXNG_VERIFY_SSL as boolean)
			: true
	);
	const [name, setName] = useState<string>(connector.name || "");

	// Update all fields when connector changes
	useEffect(() => {
		const hostValue = (connector.config?.SEARXNG_HOST as string) || "";
		const apiKeyValue = (connector.config?.SEARXNG_API_KEY as string) || "";
		const enginesValue = arrayToString(connector.config?.SEARXNG_ENGINES);
		const categoriesValue = arrayToString(connector.config?.SEARXNG_CATEGORIES);
		const languageValue = (connector.config?.SEARXNG_LANGUAGE as string) || "";
		const safesearchValue =
			connector.config?.SEARXNG_SAFESEARCH !== undefined
				? String(connector.config.SEARXNG_SAFESEARCH)
				: "";
		const verifySslValue =
			connector.config?.SEARXNG_VERIFY_SSL !== undefined
				? (connector.config.SEARXNG_VERIFY_SSL as boolean)
				: true;

		setHost(hostValue);
		setApiKey(apiKeyValue);
		setEngines(enginesValue);
		setCategories(categoriesValue);
		setLanguage(languageValue);
		setSafesearch(safesearchValue);
		setVerifySsl(verifySslValue);
		setName(connector.name || "");
	}, [connector.config, connector.name]);

	const updateConfig = (updates: Record<string, unknown>) => {
		if (onConfigChange) {
			onConfigChange({
				...connector.config,
				...updates,
			});
		}
	};

	const handleHostChange = (value: string) => {
		setHost(value);
		updateConfig({ SEARXNG_HOST: value });
	};

	const handleApiKeyChange = (value: string) => {
		setApiKey(value);
		if (value) {
			updateConfig({ SEARXNG_API_KEY: value });
		} else {
			const newConfig = { ...connector.config };
			delete newConfig.SEARXNG_API_KEY;
			if (onConfigChange) {
				onConfigChange(newConfig);
			}
		}
	};

	const handleEnginesChange = (value: string) => {
		setEngines(value);
		const enginesArray = stringToArray(value);
		if (enginesArray) {
			updateConfig({ SEARXNG_ENGINES: enginesArray });
		} else {
			const newConfig = { ...connector.config };
			delete newConfig.SEARXNG_ENGINES;
			if (onConfigChange) {
				onConfigChange(newConfig);
			}
		}
	};

	const handleCategoriesChange = (value: string) => {
		setCategories(value);
		const categoriesArray = stringToArray(value);
		if (categoriesArray) {
			updateConfig({ SEARXNG_CATEGORIES: categoriesArray });
		} else {
			const newConfig = { ...connector.config };
			delete newConfig.SEARXNG_CATEGORIES;
			if (onConfigChange) {
				onConfigChange(newConfig);
			}
		}
	};

	const handleLanguageChange = (value: string) => {
		setLanguage(value);
		if (value) {
			updateConfig({ SEARXNG_LANGUAGE: value });
		} else {
			const newConfig = { ...connector.config };
			delete newConfig.SEARXNG_LANGUAGE;
			if (onConfigChange) {
				onConfigChange(newConfig);
			}
		}
	};

	const handleSafesearchChange = (value: string) => {
		setSafesearch(value);
		if (value) {
			const parsed = Number(value);
			if (!Number.isNaN(parsed)) {
				updateConfig({ SEARXNG_SAFESEARCH: parsed });
			}
		} else {
			const newConfig = { ...connector.config };
			delete newConfig.SEARXNG_SAFESEARCH;
			if (onConfigChange) {
				onConfigChange(newConfig);
			}
		}
	};

	const handleVerifySslChange = (value: boolean) => {
		setVerifySsl(value);
		if (value === false) {
			updateConfig({ SEARXNG_VERIFY_SSL: false });
		} else {
			const newConfig = { ...connector.config };
			delete newConfig.SEARXNG_VERIFY_SSL;
			if (onConfigChange) {
				onConfigChange(newConfig);
			}
		}
	};

	const handleNameChange = (value: string) => {
		setName(value);
		if (onNameChange) {
			onNameChange(value);
		}
	};

	return (
		<div className="space-y-6">
			{/* Connector Name */}
			<div className="rounded-xl border border-border bg-slate-400/5 dark:bg-white/5 p-3 sm:p-6 space-y-3 sm:space-y-4">
				<div className="space-y-2">
					<Label className="text-xs sm:text-sm">Anslutningsnamn</Label>
					<Input
						value={name}
						onChange={(e) => handleNameChange(e.target.value)}
						placeholder="Min SearxNG-anslutning"
						className="border-slate-400/20 focus-visible:border-slate-400/40"
					/>
					<p className="text-[10px] sm:text-xs text-muted-foreground">
						Ett vänligt namn för att identifiera anslutningen.
					</p>
				</div>
			</div>

			{/* Configuration */}
			<div className="rounded-xl border border-border bg-slate-400/5 dark:bg-white/5 p-3 sm:p-6 space-y-3 sm:space-y-4">
				<div className="space-y-1 sm:space-y-2">
					<h3 className="font-medium text-sm sm:text-base">Konfiguration</h3>
				</div>

				<div className="space-y-4">
					<div className="space-y-2">
						<Label className="flex items-center gap-2 text-xs sm:text-sm">
							<Globe className="h-4 w-4" />
							SearxNG-värd
						</Label>
						<Input
							value={host}
							onChange={(e) => handleHostChange(e.target.value)}
							placeholder="https://searxng.example.org"
							className="border-slate-400/20 focus-visible:border-slate-400/40"
						/>
						<p className="text-[10px] sm:text-xs text-muted-foreground">
							Uppdatera SearxNG-värden vid behov.
						</p>
					</div>

					<div className="space-y-2">
						<Label className="flex items-center gap-2 text-xs sm:text-sm">
							<KeyRound className="h-4 w-4" />
							API-nyckel (valfritt)
						</Label>
						<Input
							type="password"
							value={apiKey}
							onChange={(e) => handleApiKeyChange(e.target.value)}
							placeholder="Ange API-nyckel om din instans kräver en"
							className="border-slate-400/20 focus-visible:border-slate-400/40"
						/>
						<p className="text-[10px] sm:text-xs text-muted-foreground">
							Lämna tomt om din SearxNG-instans inte kräver API-nycklar.
						</p>
					</div>

					<div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
						<div className="space-y-2">
							<Label className="text-xs sm:text-sm">Sökmotorer (valfritt)</Label>
							<Input
								value={engines}
								onChange={(e) => handleEnginesChange(e.target.value)}
								placeholder="google,bing,duckduckgo"
								className="border-slate-400/20 focus-visible:border-slate-400/40"
							/>
							<p className="text-[10px] sm:text-xs text-muted-foreground">
								Kommaseparerad lista för att rikta in sig på specifika motorer.
							</p>
						</div>

						<div className="space-y-2">
							<Label className="text-xs sm:text-sm">Kategorier (valfritt)</Label>
							<Input
								value={categories}
								onChange={(e) => handleCategoriesChange(e.target.value)}
								placeholder="general,it,science"
								className="border-slate-400/20 focus-visible:border-slate-400/40"
							/>
							<p className="text-[10px] sm:text-xs text-muted-foreground">
								Kommaseparerad lista över SearxNG-kategorier.
							</p>
						</div>
					</div>

					<div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
						<div className="space-y-2">
							<Label className="text-xs sm:text-sm">Föredraget språk (valfritt)</Label>
							<Input
								value={language}
								onChange={(e) => handleLanguageChange(e.target.value)}
								placeholder="en-US"
								className="border-slate-400/20 focus-visible:border-slate-400/40"
							/>
							<p className="text-[10px] sm:text-xs text-muted-foreground">
								IETF-språktagg (t.ex. en, en-US). Lämna tomt för att använda standardinställningar.
							</p>
						</div>

						<div className="space-y-2">
							<Label className="text-xs sm:text-sm">SafeSearch-nivå (valfritt)</Label>
							<Input
								value={safesearch}
								onChange={(e) => handleSafesearchChange(e.target.value)}
								placeholder="0 (av), 1 (måttlig), 2 (strikt)"
								className="border-slate-400/20 focus-visible:border-slate-400/40"
							/>
							<p className="text-[10px] sm:text-xs text-muted-foreground">
								Ange 0, 1 eller 2 för att justera SafeSearch-filtrering. Lämna tomt för att
								använda instansens standard.
							</p>
						</div>
					</div>

					<div className="flex items-center justify-between rounded-lg border border-slate-400/20 p-3 sm:p-4">
						<div>
							<Label className="text-xs sm:text-sm">Verifiera SSL-certifikat</Label>
							<p className="text-[10px] sm:text-xs text-muted-foreground">
								Inaktivera endast vid anslutning till instanser med självsignerade certifikat.
							</p>
						</div>
						<Switch checked={verifySsl} onCheckedChange={handleVerifySslChange} />
					</div>
				</div>
			</div>
		</div>
	);
};
