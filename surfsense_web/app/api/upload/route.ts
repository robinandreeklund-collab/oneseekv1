import { type NextRequest, NextResponse } from "next/server";
import { writeFile, mkdir } from "fs/promises";
import path from "path";

export async function POST(request: NextRequest) {
	try {
		const formData = await request.formData();
		const file = formData.get("file") as File | null;

		if (!file) {
			return NextResponse.json(
				{ success: false, message: "Ingen fil vald" },
				{ status: 400 }
			);
		}

		const allowedTypes = ["image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"];
		if (!allowedTypes.includes(file.type)) {
			return NextResponse.json(
				{ success: false, message: "Filtypen stöds inte. Tillåtna: JPG, PNG, GIF, WebP, SVG" },
				{ status: 400 }
			);
		}

		const maxSize = 10 * 1024 * 1024; // 10MB
		if (file.size > maxSize) {
			return NextResponse.json(
				{ success: false, message: "Filen är för stor. Max 10MB." },
				{ status: 400 }
			);
		}

		const bytes = await file.arrayBuffer();
		const buffer = Buffer.from(bytes);

		const timestamp = Date.now();
		const ext = path.extname(file.name) || ".png";
		const safeName = file.name
			.replace(ext, "")
			.replace(/[^a-zA-Z0-9-_]/g, "-")
			.substring(0, 50);
		const fileName = `${timestamp}-${safeName}${ext}`;

		const uploadDir = path.join(process.cwd(), "public", "uploads");
		await mkdir(uploadDir, { recursive: true });

		const filePath = path.join(uploadDir, fileName);
		await writeFile(filePath, buffer);

		const url = `/uploads/${fileName}`;

		return NextResponse.json({
			success: true,
			url,
			message: "Bild uppladdad",
		});
	} catch (error) {
		console.error("Error uploading file:", error);
		return NextResponse.json(
			{ success: false, message: "Kunde inte ladda upp filen" },
			{ status: 500 }
		);
	}
}
