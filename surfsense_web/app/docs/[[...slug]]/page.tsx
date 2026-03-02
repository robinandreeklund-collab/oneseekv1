export default function DocsPage() {
	return (
		<div className="flex flex-col items-center justify-center min-h-screen px-6">
			<div className="max-w-lg text-center space-y-4">
				<h1 className="text-4xl font-bold tracking-tight bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-400 bg-clip-text text-transparent">
					Dokumentation
				</h1>
				<p className="text-muted-foreground text-lg">
					Dokumentationen är under uppbyggnad och kommer snart.
				</p>
				<a
					href="/"
					className="inline-flex items-center px-4 py-2 text-sm font-medium rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-900 hover:opacity-90 transition-opacity"
				>
					Tillbaka till startsidan
				</a>
			</div>
		</div>
	);
}
