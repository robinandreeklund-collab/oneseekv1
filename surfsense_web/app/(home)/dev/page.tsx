import { db } from "@/app/db";
import { postsTable } from "@/app/db/schema";
import { eq, desc } from "drizzle-orm";
import { formatDate } from "@/lib/utils";
import { getLocale } from "next-intl/server";

export const dynamic = "force-dynamic";

export default async function DevPage() {
	const locale = await getLocale();

	const posts = await db
		.select()
		.from(postsTable)
		.where(eq(postsTable.type, "devlog"))
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
								Dev
							</h1>
							<p className="text-muted-foreground mt-2">
								Tester, API-integration, precision och metadata
							</p>
						</div>
					</div>
				</div>
			</div>

			{/* Posts */}
			<div className="max-w-5xl mx-auto px-6 lg:px-10 pt-10 pb-20">
				{publishedPosts.length === 0 ? (
					<p className="text-center text-muted-foreground py-20">
						Inga dev-inlägg publicerade ännu.
					</p>
				) : (
					<div className="space-y-10">
						{publishedPosts.map((post) => {
							const date = new Date(post.createdAt);
							const formattedDate = formatDate(date, locale as "sv");
							const tags = post.tags ? post.tags.split(",").map((t) => t.trim()).filter(Boolean) : [];

							return (
								<article key={post.id} className="relative">
									<div className="space-y-4">
										<div className="flex items-center gap-3">
											<time className="text-sm font-medium text-muted-foreground">
												{formattedDate}
											</time>
											{tags.length > 0 && (
												<div className="flex flex-wrap gap-1.5">
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

										<h2 className="text-2xl font-semibold tracking-tight text-balance">
											{post.title}
										</h2>

										{post.excerpt && (
											<p className="text-muted-foreground text-balance">
												{post.excerpt}
											</p>
										)}

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

									<div className="mt-10 border-b border-border/50" />
								</article>
							);
						})}
					</div>
				)}
			</div>
		</div>
	);
}

function MarkdownContent({ content }: { content: string }) {
	const html = content
		.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
		.replace(/`([^`]+)`/g, "<code>$1</code>")
		.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" />')
		.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
		.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
		.replace(/\*([^*]+)\*/g, "<em>$1</em>")
		.replace(/^### (.+)$/gm, "<h3>$1</h3>")
		.replace(/^## (.+)$/gm, "<h2>$1</h2>")
		.replace(/^# (.+)$/gm, "<h1>$1</h1>")
		.replace(/^- (.+)$/gm, "<li>$1</li>")
		.replace(/((<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>")
		.replace(/^(?!<[hupol]|<li|<pre|<code|<img|<a|<strong|<em)(.+)$/gm, "<p>$1</p>")
		.replace(/\n\n/g, "");

	return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
