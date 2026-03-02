import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { eq, desc } from "drizzle-orm";
import { db } from "@/app/db";
import { postsTable } from "@/app/db/schema";

const createPostSchema = z.object({
	type: z.enum(["changelog", "devlog"]),
	title: z.string().min(1, "Titel krävs").max(500),
	slug: z.string().min(1, "Slug krävs").max(500),
	content: z.string().min(1, "Innehåll krävs"),
	excerpt: z.string().optional().default(""),
	tags: z.string().optional().default(""),
	imageUrl: z.string().optional().default(""),
	published: z.boolean().optional().default(false),
});

// GET /api/posts?type=changelog|devlog&published=true
export async function GET(request: NextRequest) {
	try {
		const { searchParams } = new URL(request.url);
		const type = searchParams.get("type");
		const publishedOnly = searchParams.get("published") === "true";

		let query = db.select().from(postsTable).orderBy(desc(postsTable.createdAt)).$dynamic();

		if (type) {
			query = query.where(eq(postsTable.type, type));
		}

		const posts = await query;

		const filtered = publishedOnly ? posts.filter((p) => p.published) : posts;

		return NextResponse.json({ success: true, data: filtered });
	} catch (error) {
		console.error("Error fetching posts:", error);
		return NextResponse.json(
			{ success: false, message: "Failed to fetch posts" },
			{ status: 500 }
		);
	}
}

// POST /api/posts
export async function POST(request: NextRequest) {
	try {
		const body = await request.json();
		const validatedData = createPostSchema.parse(body);

		const result = await db
			.insert(postsTable)
			.values({
				type: validatedData.type,
				title: validatedData.title,
				slug: validatedData.slug,
				content: validatedData.content,
				excerpt: validatedData.excerpt,
				tags: validatedData.tags,
				imageUrl: validatedData.imageUrl,
				published: validatedData.published,
			})
			.returning();

		return NextResponse.json(
			{ success: true, data: result[0], message: "Post skapad" },
			{ status: 201 }
		);
	} catch (error) {
		if (error instanceof z.ZodError) {
			return NextResponse.json(
				{ success: false, message: "Valideringsfel", errors: error.issues },
				{ status: 400 }
			);
		}
		console.error("Error creating post:", error);
		return NextResponse.json(
			{ success: false, message: "Kunde inte skapa post" },
			{ status: 500 }
		);
	}
}
