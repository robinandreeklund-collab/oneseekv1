"use client";

import { useAtomValue } from "jotai";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { searchSpacesAtom } from "@/atoms/search-spaces/search-space-query.atoms";

export default function AdminRedirectPage() {
	const router = useRouter();
	const { data, isLoading } = useAtomValue(searchSpacesAtom);

	useEffect(() => {
		if (isLoading) return;
		const firstSpace = data?.[0];
		if (firstSpace?.id) {
			router.replace(`/dashboard/${firstSpace.id}/admin`);
		}
	}, [data, isLoading, router]);

	return (
		<div className="mx-auto w-full max-w-2xl px-4 py-10">
			<h1 className="text-xl font-semibold">Admin</h1>
			<p className="mt-2 text-sm text-muted-foreground">
				{isLoading
					? "Laddar arbetsytor..."
					: "Ingen arbetsyta hittades för ditt konto."}
			</p>
		</div>
	);
}
