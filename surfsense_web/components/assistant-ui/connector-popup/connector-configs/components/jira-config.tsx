"use client";

import { Info, KeyRound } from "lucide-react";
import type { FC } from "react";
import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ConnectorConfigProps } from "../index";

export interface JiraConfigProps extends ConnectorConfigProps {
	onNameChange?: (name: string) => void;
}

export const JiraConfig: FC<JiraConfigProps> = ({ connector, onConfigChange, onNameChange }) => {
	// Check if this is an OAuth connector (has access_token or _token_encrypted flag)
	const isOAuth = !!(connector.config?.access_token || connector.config?._token_encrypted);

	const [baseUrl, setBaseUrl] = useState<string>((connector.config?.JIRA_BASE_URL as string) || "");
	const [email, setEmail] = useState<string>((connector.config?.JIRA_EMAIL as string) || "");
	const [apiToken, setApiToken] = useState<string>(
		(connector.config?.JIRA_API_TOKEN as string) || ""
	);
	const [name, setName] = useState<string>(connector.name || "");

	// Update values when connector changes (only for legacy connectors)
	useEffect(() => {
		if (!isOAuth) {
			const url = (connector.config?.JIRA_BASE_URL as string) || "";
			const emailVal = (connector.config?.JIRA_EMAIL as string) || "";
			const token = (connector.config?.JIRA_API_TOKEN as string) || "";
			setBaseUrl(url);
			setEmail(emailVal);
			setApiToken(token);
		}
		setName(connector.name || "");
	}, [connector.config, connector.name, isOAuth]);

	const handleBaseUrlChange = (value: string) => {
		setBaseUrl(value);
		if (onConfigChange) {
			onConfigChange({
				...connector.config,
				JIRA_BASE_URL: value,
			});
		}
	};

	const handleEmailChange = (value: string) => {
		setEmail(value);
		if (onConfigChange) {
			onConfigChange({
				...connector.config,
				JIRA_EMAIL: value,
			});
		}
	};

	const handleApiTokenChange = (value: string) => {
		setApiToken(value);
		if (onConfigChange) {
			onConfigChange({
				...connector.config,
				JIRA_API_TOKEN: value,
			});
		}
	};

	const handleNameChange = (value: string) => {
		setName(value);
		if (onNameChange) {
			onNameChange(value);
		}
	};

	// For OAuth connectors, show simple info message
	if (isOAuth) {
		const baseUrl = (connector.config?.base_url as string) || "Okänd";
		return (
			<div className="space-y-6">
				{/* OAuth Info */}
				<div className="rounded-xl border border-border bg-primary/5 p-4 flex items-start gap-3">
					<div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 shrink-0 mt-0.5">
						<Info className="size-4" />
					</div>
					<div className="text-xs sm:text-sm">
						<p className="font-medium text-xs sm:text-sm">Ansluten via OAuth</p>
						<p className="text-muted-foreground mt-1 text-[10px] sm:text-sm">
							Den här anslutningen autentiseras med OAuth 2.0. Din Jira-instans är:
						</p>
						<p className="text-muted-foreground mt-1 text-[10px] sm:text-sm">
							<code className="bg-muted px-1 py-0.5 rounded text-inherit">{baseUrl}</code>
						</p>
						<p className="text-muted-foreground mt-1 text-[10px] sm:text-sm">
							För att uppdatera din anslutning, anslut om den här anslutningen.
						</p>
					</div>
				</div>
			</div>
		);
	}

	// For legacy API token connectors, show the form
	return (
		<div className="space-y-6">
			{/* Connector Name */}
			<div className="rounded-xl border border-border bg-slate-400/5 dark:bg-white/5 p-3 sm:p-6 space-y-3 sm:space-y-4">
				<div className="space-y-2">
					<Label className="text-xs sm:text-sm">Anslutningsnamn</Label>
					<Input
						value={name}
						onChange={(e) => handleNameChange(e.target.value)}
						placeholder="Min Jira-anslutning"
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
						<Label className="text-xs sm:text-sm">Jira-bas-URL</Label>
						<Input
							type="url"
							value={baseUrl}
							onChange={(e) => handleBaseUrlChange(e.target.value)}
							placeholder="https://your-domain.atlassian.net"
							className="border-slate-400/20 focus-visible:border-slate-400/40"
						/>
						<p className="text-[10px] sm:text-xs text-muted-foreground">
							Bas-URL:en för din Jira-instans.
						</p>
					</div>

					<div className="space-y-2">
						<Label className="text-xs sm:text-sm">E-postadress</Label>
						<Input
							type="email"
							value={email}
							onChange={(e) => handleEmailChange(e.target.value)}
							placeholder="din-epost@example.com"
							className="border-slate-400/20 focus-visible:border-slate-400/40"
						/>
						<p className="text-[10px] sm:text-xs text-muted-foreground">
							E-postadressen som är kopplad till ditt Atlassian-konto.
						</p>
					</div>

					<div className="space-y-2">
						<Label className="flex items-center gap-2 text-xs sm:text-sm">
							<KeyRound className="h-4 w-4" />
							API-token
						</Label>
						<Input
							type="password"
							value={apiToken}
							onChange={(e) => handleApiTokenChange(e.target.value)}
							placeholder="Din API-token"
							className="border-slate-400/20 focus-visible:border-slate-400/40"
						/>
						<p className="text-[10px] sm:text-xs text-muted-foreground">
							Uppdatera din Jira API-token vid behov.
						</p>
					</div>
				</div>
			</div>
		</div>
	);
};
