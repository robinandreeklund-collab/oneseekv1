"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { ImageIcon } from "lucide-react";
import { z } from "zod";
import {
	Image,
	ImageErrorBoundary,
	ImageSkeleton,
	parseSerializableImage,
} from "@/components/tool-ui/image";

// ============================================================================
// Zod Schemas
// ============================================================================

const GalleryImageArgsSchema = z.object({
	src: z.string(),
	alt: z.string().nullish(),
	title: z.string().nullish(),
	description: z.string().nullish(),
	href: z.string().nullish(),
});

const GalleryImageResultSchema = z.object({
	id: z.string(),
	assetId: z.string(),
	src: z.string(),
	alt: z.string().nullish(),
	title: z.string().nullish(),
	description: z.string().nullish(),
	href: z.string().nullish(),
	domain: z.string().nullish(),
	ratio: z.string().nullish(),
});

const ImageGalleryArgsSchema = z.object({
	images: z.array(GalleryImageArgsSchema),
});

const ImageGalleryResultSchema = z.object({
	images: z.array(GalleryImageResultSchema),
});

type ImageGalleryArgs = z.infer<typeof ImageGalleryArgsSchema>;
type ImageGalleryResult = z.infer<typeof ImageGalleryResultSchema>;

function GalleryEmptyState() {
	return (
		<div className="my-4 rounded-xl border border-muted p-4 text-muted-foreground w-full">
			<p className="flex items-center gap-2 text-sm">
				<ImageIcon className="size-4" />
				<span>Inga bilder att visa.</span>
			</p>
		</div>
	);
}

function GalleryLoadingState({ count }: { count: number }) {
	const items = Array.from({ length: count }, (_, index) => `loading-${index}`);
	return (
		<div className="my-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{items.map((key) => (
				<ImageSkeleton key={key} />
			))}
		</div>
	);
}

export const DisplayImageGalleryToolUI = makeAssistantToolUI<
	ImageGalleryArgs,
	ImageGalleryResult
>({
	toolName: "display_image_gallery",
	render: function DisplayImageGalleryUI({ args, result, status }) {
		const fallbackImages = args?.images ?? [];

		if (status.type === "running" || status.type === "requires-action") {
			return <GalleryLoadingState count={Math.max(2, Math.min(fallbackImages.length, 6))} />;
		}

		if (status.type === "incomplete") {
			return <GalleryEmptyState />;
		}

		const images = result?.images ?? [];

		if (!images.length) {
			return <GalleryEmptyState />;
		}

		return (
			<div className="my-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
				{images.map((image, index) => {
					const parsed = parseSerializableImage(image);
					return (
						<ImageErrorBoundary key={parsed.id ?? `${parsed.src}-${index}`}>
							<Image {...parsed} maxWidth="100%" />
						</ImageErrorBoundary>
					);
				})}
			</div>
		);
	},
});

export {
	GalleryImageArgsSchema,
	GalleryImageResultSchema,
	ImageGalleryArgsSchema,
	ImageGalleryResultSchema,
	type ImageGalleryArgs,
	type ImageGalleryResult,
};
