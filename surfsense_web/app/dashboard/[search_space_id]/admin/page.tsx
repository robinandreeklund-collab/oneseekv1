"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AdminPromptsPage } from "@/components/admin/agent-prompts-page";

export default function AdminPromptsRedirectPage() {
	const router = useRouter();

	useEffect(() => {
		router.replace("/admin");
	}, [router]);

	return <AdminPromptsPage />;
}
