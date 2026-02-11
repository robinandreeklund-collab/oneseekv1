"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { AlertCircleIcon, MapIcon } from "lucide-react";
import { z } from "zod";
import { Image, ImageErrorBoundary, ImageLoading } from "@/components/tool-ui/image";

// ============================================================================
// Zod Schemas
// ============================================================================

const GeoapifyMarkerSchema = z.object({
	lat: z.number(),
	lon: z.number(),
	color: z.string().nullish(),
	label: z.string().nullish(),
	size: z.string().nullish(),
});

const GeoapifyStaticMapArgsSchema = z.object({
	location: z.string().nullish(),
	center: z.string().nullish(),
	lat: z.number().nullish(),
	lon: z.number().nullish(),
	zoom: z.number().nullish(),
	width: z.number().nullish(),
	height: z.number().nullish(),
	markers: z.array(GeoapifyMarkerSchema).nullish(),
	style: z.string().nullish(),
	image_format: z.string().nullish(),
});

const GeoapifyStaticMapResultSchema = z.object({
	status: z.string().nullish(),
	image_url: z.string().nullish(),
	center: z
		.object({
			lat: z.number().nullish(),
			lon: z.number().nullish(),
			name: z.string().nullish(),
		})
		.nullish(),
	zoom: z.number().nullish(),
	size: z
		.object({
			width: z.number().nullish(),
			height: z.number().nullish(),
		})
		.nullish(),
	markers: z.array(GeoapifyMarkerSchema).nullish(),
	error: z.string().nullish(),
});

type GeoapifyStaticMapArgs = z.infer<typeof GeoapifyStaticMapArgsSchema>;
type GeoapifyStaticMapResult = z.infer<typeof GeoapifyStaticMapResultSchema>;

function MapErrorState({ message }: { message: string }) {
	return (
		<div className="my-4 overflow-hidden rounded-xl border border-destructive/20 bg-destructive/5 p-4 w-full">
			<div className="flex items-center gap-4">
				<div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-destructive/10">
					<AlertCircleIcon className="size-6 text-destructive" />
				</div>
				<div className="flex-1 min-w-0">
					<p className="font-medium text-destructive text-sm">Kartan kunde inte skapas</p>
					<p className="text-muted-foreground text-xs mt-1">{message}</p>
				</div>
			</div>
		</div>
	);
}

function MapEmptyState() {
	return (
		<div className="my-4 rounded-xl border border-muted p-4 text-muted-foreground w-full">
			<p className="flex items-center gap-2 text-sm">
				<MapIcon className="size-4" />
				<span>Ingen karta att visa.</span>
			</p>
		</div>
	);
}

export const GeoapifyStaticMapToolUI = makeAssistantToolUI<
	GeoapifyStaticMapArgs,
	GeoapifyStaticMapResult
>({
	toolName: "geoapify_static_map",
	render: function GeoapifyStaticMapUI({ result, status }) {
		if (status.type === "running" || status.type === "requires-action") {
			return (
				<div className="my-4">
					<ImageLoading title="Skapar karta..." />
				</div>
			);
		}

		if (status.type === "incomplete") {
			return <MapEmptyState />;
		}

		if (!result) {
			return <MapEmptyState />;
		}

		if (result.error) {
			return <MapErrorState message={result.error} />;
		}

		if (!result.image_url) {
			return <MapEmptyState />;
		}

		const title = result.center?.name
			? `Karta: ${result.center.name}`
			: "Karta";
		const description = "Data © OpenStreetMap contributors";

		const safeId = `geoapify-${encodeURIComponent(result.image_url)}`;

		return (
			<div className="my-4">
				<ImageErrorBoundary>
					<Image
						id={safeId}
						assetId={result.image_url}
						src={result.image_url}
						alt="Geoapify karta"
						title={title}
						description={description}
						maxWidth="100%"
						ratio="16:9"
					/>
				</ImageErrorBoundary>
			</div>
		);
	},
});

export {
	GeoapifyStaticMapArgsSchema,
	GeoapifyStaticMapResultSchema,
	type GeoapifyStaticMapArgs,
	type GeoapifyStaticMapResult,
};
