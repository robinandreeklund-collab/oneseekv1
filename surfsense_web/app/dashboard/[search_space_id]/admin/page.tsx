"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { AdminPromptsPage } from "@/components/admin/agent-prompts-page";

export default function AdminPromptsRedirectPage() {
	const router = useRouter();

	useEffect(() => {
		router.replace("/admin");
	}, [router]);

	return <AdminPromptsPage />;
}
