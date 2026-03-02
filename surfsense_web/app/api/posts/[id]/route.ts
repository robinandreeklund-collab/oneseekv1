import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { eq } from "drizzle-orm";
import { db } from "@/app/db";
import { postsTable } from "@/app/db/schema";

const updatePostSchema = z.object({
	title: z.string().min(1).max(500).optional(),
	slug: z.string().min(1).max(500).optional(),
	content: z.string().min(1).optional(),
	excerpt: z.string().optional(),
	tags: z.string().optional(),
	imageUrl: z.string().optional(),
	published: z.boolean().optional(),
});

// GET /api/posts/[id]
export async function GET(
	_request: NextRequest,
	{ params }: { params: Promise<{ id: string }> }
) {
	try {
		const { id } = await params;
		const postId = parseInt(id, 10);
		if (isNaN(postId)) {
			return NextResponse.json(
				{ success: false, message: "Ogiltigt ID" },
				{ status: 400 }
			);
		}

		const posts = await db
			.select()
			.from(postsTable)
			.where(eq(postsTable.id, postId));

		if (posts.length === 0) {
			return NextResponse.json(
				{ success: false, message: "Post hittades inte" },
				{ status: 404 }
			);
		}

		return NextResponse.json({ success: true, data: posts[0] });
	} catch (error) {
		console.error("Error fetching post:", error);
		return NextResponse.json(
			{ success: false, message: "Kunde inte hämta post" },
			{ status: 500 }
		);
	}
}

// PUT /api/posts/[id]
export async function PUT(
	request: NextRequest,
	{ params }: { params: Promise<{ id: string }> }
) {
	try {
		const { id } = await params;
		const postId = parseInt(id, 10);
		if (isNaN(postId)) {
			return NextResponse.json(
				{ success: false, message: "Ogiltigt ID" },
				{ status: 400 }
			);
		}

		const body = await request.json();
		const validatedData = updatePostSchema.parse(body);

		const result = await db
			.update(postsTable)
			.set({
				...validatedData,
				updatedAt: new Date(),
			})
			.where(eq(postsTable.id, postId))
			.returning();

		if (result.length === 0) {
			return NextResponse.json(
				{ success: false, message: "Post hittades inte" },
				{ status: 404 }
			);
		}

		return NextResponse.json({
			success: true,
			data: result[0],
			message: "Post uppdaterad",
		});
	} catch (error) {
		if (error instanceof z.ZodError) {
			return NextResponse.json(
				{ success: false, message: "Valideringsfel", errors: error.issues },
				{ status: 400 }
			);
		}
		console.error("Error updating post:", error);
		return NextResponse.json(
			{ success: false, message: "Kunde inte uppdatera post" },
			{ status: 500 }
		);
	}
}

// DELETE /api/posts/[id]
export async function DELETE(
	_request: NextRequest,
	{ params }: { params: Promise<{ id: string }> }
) {
	try {
		const { id } = await params;
		const postId = parseInt(id, 10);
		if (isNaN(postId)) {
			return NextResponse.json(
				{ success: false, message: "Ogiltigt ID" },
				{ status: 400 }
			);
		}

		const result = await db
			.delete(postsTable)
			.where(eq(postsTable.id, postId))
			.returning();

		if (result.length === 0) {
			return NextResponse.json(
				{ success: false, message: "Post hittades inte" },
				{ status: 404 }
			);
		}

		return NextResponse.json({
			success: true,
			message: "Post borttagen",
		});
	} catch (error) {
		console.error("Error deleting post:", error);
		return NextResponse.json(
			{ success: false, message: "Kunde inte ta bort post" },
			{ status: 500 }
		);
	}
}
