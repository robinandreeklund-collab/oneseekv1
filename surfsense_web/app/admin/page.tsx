"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminPage() {
	const router = useRouter();

	useEffect(() => {
		// Redirect to prompts page by default
		router.replace("/admin/prompts");
	}, [router]);

	return null;
}
