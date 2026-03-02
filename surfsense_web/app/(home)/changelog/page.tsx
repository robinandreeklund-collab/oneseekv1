import { db } from "@/app/db";
import { postsTable } from "@/app/db/schema";
import { eq, desc } from "drizzle-orm";
import { formatDate } from "@/lib/utils";
import { getLocale, getTranslations } from "next-intl/server";

export const dynamic = "force-dynamic";

export default async function ChangelogPage() {
	const locale = await getLocale();
	const t = await getTranslations("changelog");

	const posts = await db
		.select()
		.from(postsTable)
		.where(eq(postsTable.type, "changelog"))
		.orderBy(desc(postsTable.createdAt));

	const publishedPosts = posts.filter((p) => p.published);

	return (
		<div className="min-h-screen relative pt-20">
			{/* Header */}
			<div className="border-b border-border/50">
				<div className="max-w-5xl mx-auto relative">
					<div className="p-6 flex items-center justify-between">
						<div>
							<h1 className="text-4xl font-bold tracking-tight bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-400 bg-clip-text text-transparent">
								{t("title")}
							</h1>
							<p className="text-muted-foreground mt-2">
								{t("subtitle")}
							</p>
						</div>
					</div>
				</div>
			</div>

			{/* Timeline */}
			<div className="max-w-5xl mx-auto px-6 lg:px-10 pt-10 pb-20">
				{publishedPosts.length === 0 ? (
					<p className="text-center text-muted-foreground py-20">
						Inga changelog-inlägg publicerade ännu.
					</p>
				) : (
					<div className="relative">
						{publishedPosts.map((post) => {
							const date = new Date(post.createdAt);
							const formattedDate = formatDate(date, locale as "sv");
							const tags = post.tags ? post.tags.split(",").map((t) => t.trim()).filter(Boolean) : [];

							return (
								<div key={post.id} className="relative">
									<div className="flex flex-col md:flex-row gap-y-6">
										<div className="md:w-48 flex-shrink-0">
											<div className="md:sticky md:top-24 pb-10">
												<time className="text-sm font-medium text-muted-foreground block mb-3">
													{formattedDate}
												</time>
											</div>
										</div>

										{/* Right side - Content */}
										<div className="flex-1 md:pl-8 relative pb-10">
											{/* Vertical timeline line */}
											<div className="hidden md:block absolute top-2 left-0 w-px h-full bg-border">
												{/* Timeline dot */}
												<div className="hidden md:block absolute -translate-x-1/2 size-3 bg-primary rounded-full z-10" />
											</div>

											<div className="space-y-6">
												<div className="relative z-10 flex flex-col gap-2">
													<h2 className="text-2xl font-semibold tracking-tight text-balance">
														{post.title}
													</h2>

													{/* Tags */}
													{tags.length > 0 && (
														<div className="flex flex-wrap gap-2">
															{tags.map((tag) => (
																<span
																	key={tag}
																	className="h-6 w-fit px-2.5 text-xs font-medium bg-muted text-muted-foreground rounded-full border flex items-center justify-center"
																>
																	{tag}
																</span>
															))}
														</div>
													)}
												</div>

												{post.imageUrl && (
													<img
														src={post.imageUrl}
														alt={post.title}
														className="rounded-xl shadow-lg max-w-full"
													/>
												)}

												<div className="prose dark:prose-invert max-w-none prose-headings:scroll-mt-8 prose-headings:font-semibold prose-a:no-underline prose-headings:tracking-tight prose-headings:text-balance prose-p:tracking-tight prose-p:text-balance prose-img:rounded-xl prose-img:shadow-lg">
													<MarkdownContent content={post.content} />
												</div>
											</div>
										</div>
									</div>
								</div>
							);
						})}
					</div>
				)}
			</div>
		</div>
	);
}

function MarkdownContent({ content }: { content: string }) {
	// Simple markdown to HTML conversion for common patterns
	const html = content
		// Code blocks
		.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
		// Inline code
		.replace(/`([^`]+)`/g, "<code>$1</code>")
		// Images
		.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" />')
		// Links
		.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
		// Bold
		.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
		// Italic
		.replace(/\*([^*]+)\*/g, "<em>$1</em>")
		// H3
		.replace(/^### (.+)$/gm, "<h3>$1</h3>")
		// H2
		.replace(/^## (.+)$/gm, "<h2>$1</h2>")
		// H1
		.replace(/^# (.+)$/gm, "<h1>$1</h1>")
		// Unordered lists
		.replace(/^- (.+)$/gm, "<li>$1</li>")
		// Wrap consecutive li elements in ul
		.replace(/((<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>")
		// Paragraphs (lines not already wrapped)
		.replace(/^(?!<[hupol]|<li|<pre|<code|<img|<a|<strong|<em)(.+)$/gm, "<p>$1</p>")
		// Line breaks
		.replace(/\n\n/g, "");

	return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
