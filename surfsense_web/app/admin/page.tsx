"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function AdminPage() {
	const router = useRouter();

	useEffect(() => {
		// Redirect to prompts page by default
		router.replace("/admin/flow");
	}, [router]);

	return null;
}
