"use client";

import { useEffect, useState } from "react";
import { nexusApiService, type CategoryMetadata } from "@/lib/apis/nexus-api.service";

/**
 * Hook that fetches category labels dynamically from the backend.
 * Returns a Record<string, string> mapping category_id → label.
 * Falls back to uppercased category_id if the API call fails.
 */
export function useCategoryLabels(): Record<string, string> {
	const [labels, setLabels] = useState<Record<string, string>>({});

	useEffect(() => {
		nexusApiService
			.getCategoryMetadata()
			.then(({ categories }) => {
				const map: Record<string, string> = { "": "Alla kategorier" };
				for (const c of categories) {
					map[c.category_id] = c.label;
				}
				setLabels(map);
			})
			.catch(() => {
				// Fallback: empty map — component will show raw category_id
				setLabels({ "": "Alla kategorier" });
			});
	}, []);

	return new Proxy(labels, {
		get(target, prop: string) {
			if (prop in target) return target[prop];
			// Fallback for unknown categories: capitalize
			if (typeof prop === "string" && prop !== "") {
				return prop.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
			}
			return undefined;
		},
	});
}
