import type { Metadata } from "next";
import "./globals.css";
import { RootProvider } from "fumadocs-ui/provider/next";
import { Roboto } from "next/font/google";
import { ElectricProvider } from "@/components/providers/ElectricProvider";
import { GlobalLoadingProvider } from "@/components/providers/GlobalLoadingProvider";
import { I18nProvider } from "@/components/providers/I18nProvider";
import { PostHogProvider } from "@/components/providers/PostHogProvider";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import { LocaleProvider } from "@/contexts/LocaleContext";
import { ReactQueryClientProvider } from "@/lib/query-client/query-client.provider";
import { cn } from "@/lib/utils";

const roboto = Roboto({
	subsets: ["latin"],
	weight: ["400", "500", "700"],
	display: "swap",
	variable: "--font-roboto",
});

export const metadata: Metadata = {
	title: "Oneseek – Anpassningsbar AI-assistent för forskning och kunskapshantering",
	description:
		"Oneseek är en AI-driven forskningsassistent som integrerar med verktyg som Notion, GitHub, Slack och mer för att hjälpa dig att effektivt hantera, söka och chatta med dina dokument. Skapa podcasts, utför hybridsökning och få insikter från din kunskapsbas.",
	keywords: [
		"Oneseek",
		"AI research assistant",
		"AI knowledge management",
		"AI document assistant",
		"customizable AI assistant",
		"notion integration",
		"slack integration",
		"github integration",
		"hybrid search",
		"vector search",
		"RAG",
		"LangChain",
		"FastAPI",
		"LLM apps",
		"AI document chat",
		"knowledge management AI",
		"AI-powered document search",
		"personal AI assistant",
		"AI research tools",
		"AI podcast generator",
		"AI knowledge base",
		"AI document assistant tools",
		"AI-powered search assistant",
	],
	openGraph: {
		title: "Oneseek – AI-assistent för forskning och kunskapshantering",
		description:
			"Anslut dina dokument och verktyg som Notion, Slack, GitHub med mera till din privata AI-assistent. Oneseek erbjuder kraftfull sökning, dokumentchatt, podcastgenerering och RAG-API:er för att förbättra ditt arbetsflöde.",
		url: "https://surfsense.com",
		siteName: "Oneseek",
		type: "website",
		images: [
			{
				url: "https://surfsense.com/og-image.png",
				width: 1200,
				height: 630,
				alt: "Oneseek AI-forskningsassistent",
			},
		],
		locale: "sv_SE",
	},
	twitter: {
		card: "summary_large_image",
		title: "Oneseek – AI-assistent för forskning och kunskapshantering",
		description:
			"Få ditt eget NotebookLM eller Perplexity, fast bättre. Oneseek kopplar in externa verktyg, låter dig chatta med dina dokument och skapar snabba, högkvalitativa podcasts.",
		creator: "https://surfsense.com",
		site: "https://surfsense.com",
		images: [
			{
				url: "https://surfsense.com/og-image-twitter.png",
				width: 1200,
				height: 630,
				alt: "Oneseek AI-assistentförhandsvisning",
			},
		],
	},
};

export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	// Using client-side i18n
	// Language can be switched dynamically through LanguageSwitcher component
	// Locale state is managed by LocaleContext and persisted in localStorage
	return (
		<html lang="sv" suppressHydrationWarning>
			<body className={cn(roboto.className, "bg-white dark:bg-black antialiased h-full w-full ")}>
				<PostHogProvider>
					<LocaleProvider>
						<I18nProvider>
							<ThemeProvider
								attribute="class"
								enableSystem
								disableTransitionOnChange
								defaultTheme="system"
							>
								<RootProvider>
									<ReactQueryClientProvider>
										<ElectricProvider>
											<GlobalLoadingProvider>{children}</GlobalLoadingProvider>
										</ElectricProvider>
									</ReactQueryClientProvider>
									<Toaster />
								</RootProvider>
							</ThemeProvider>
						</I18nProvider>
					</LocaleProvider>
				</PostHogProvider>
			</body>
		</html>
	);
}
