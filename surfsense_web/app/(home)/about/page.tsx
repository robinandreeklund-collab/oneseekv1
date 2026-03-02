export default function AboutPage() {
	return (
		<div className="min-h-screen relative pt-20">
			{/* Header */}
			<div className="border-b border-border/50">
				<div className="max-w-4xl mx-auto relative">
					<div className="p-6">
						<h1 className="text-4xl md:text-5xl font-bold tracking-tight bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-400 bg-clip-text text-transparent">
							Om OneSeek
						</h1>
						<p className="text-muted-foreground mt-3 text-lg">
							Varför vi finns och vad vi bygger
						</p>
					</div>
				</div>
			</div>

			{/* Content */}
			<div className="max-w-4xl mx-auto px-6 py-16">
				<div className="prose dark:prose-invert max-w-none prose-headings:font-semibold prose-headings:tracking-tight prose-p:tracking-tight prose-p:text-balance">
					<section className="space-y-6 mb-16">
						<h2 className="text-2xl font-semibold tracking-tight">
							Vår vision
						</h2>
						<p className="text-lg text-muted-foreground leading-relaxed">
							OneSeek är en AI-agentplattform byggd för realtidsanalys, verktygs&shy;orkestrering och transparent AI-beslutslogik.
							Vi tror att AI ska vara ett kraftfullt verktyg som är förståeligt, kontrollerbart och anpassningsbart
							efter dina behov.
						</p>
					</section>

					<section className="space-y-6 mb-16">
						<h2 className="text-2xl font-semibold tracking-tight">
							Varför OneSeek?
						</h2>
						<p className="text-lg text-muted-foreground leading-relaxed">
							I en värld med allt fler AI-verktyg saknas ofta transparens i hur beslut fattas och data hanteras.
							OneSeek är byggt från grunden med öppenhet som kärnprincip. Varje steg i AI-agentens
							resonemang är synligt och spårbart.
						</p>
						<div className="grid gap-8 md:grid-cols-2 mt-8">
							<div className="space-y-3 p-6 rounded-xl border bg-card">
								<h3 className="text-lg font-semibold">Transparent resonemang</h3>
								<p className="text-muted-foreground text-sm">
									Se exakt hur AI:n resonerar, vilka verktyg den använder och varför den fattar varje beslut.
								</p>
							</div>
							<div className="space-y-3 p-6 rounded-xl border bg-card">
								<h3 className="text-lg font-semibold">Realtidsanalys</h3>
								<p className="text-muted-foreground text-sm">
									Hämta och analysera data i realtid från hundratals källor med intelligent verktygs&shy;orkestrering.
								</p>
							</div>
							<div className="space-y-3 p-6 rounded-xl border bg-card">
								<h3 className="text-lg font-semibold">Anpassningsbar</h3>
								<p className="text-muted-foreground text-sm">
									Konfigurera agenter, verktyg och flöden efter dina specifika behov och arbetsflöden.
								</p>
							</div>
							<div className="space-y-3 p-6 rounded-xl border bg-card">
								<h3 className="text-lg font-semibold">Svensk innovation</h3>
								<p className="text-muted-foreground text-sm">
									Byggt i Sverige med fokus på kvalitet, säkerhet och användarvänlighet.
								</p>
							</div>
						</div>
					</section>

					<section className="space-y-6 mb-16">
						<h2 className="text-2xl font-semibold tracking-tight">
							Vad vi bygger
						</h2>
						<p className="text-lg text-muted-foreground leading-relaxed">
							OneSeek kombinerar avancerad AI-agentteknologi med en intuitiv användarupplevelse.
							Plattformen består av en kraftfull backend med LangGraph-baserad agentorkestrering,
							ett modernt webbgränssnitt och en webbläsartillägg för sömlös integration i ditt dagliga arbete.
						</p>
						<p className="text-lg text-muted-foreground leading-relaxed">
							Vi utvecklar kontinuerligt nya verktyg, integrationer och förbättringar.
							Följ vår <a href="/changelog" className="underline underline-offset-4 hover:text-foreground transition-colors">changelog</a> och <a href="/dev" className="underline underline-offset-4 hover:text-foreground transition-colors">dev-sida</a> för de senaste uppdateringarna.
						</p>
					</section>

					<section className="space-y-6">
						<h2 className="text-2xl font-semibold tracking-tight">
							Kontakt
						</h2>
						<p className="text-lg text-muted-foreground leading-relaxed">
							Har du frågor eller vill veta mer? Kontakta oss på{" "}
							<a href="mailto:Robin@oneseek.ai" className="underline underline-offset-4 hover:text-foreground transition-colors">
								Robin@oneseek.ai
							</a>{" "}
							eller besök vår <a href="/contact" className="underline underline-offset-4 hover:text-foreground transition-colors">kontaktsida</a>.
						</p>
					</section>
				</div>
			</div>
		</div>
	);
}
