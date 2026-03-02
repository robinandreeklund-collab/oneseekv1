"use client";

import { PostsAdminPage } from "@/components/admin/posts-admin-page";

export default function AdminDevlogPage() {
	return <PostsAdminPage type="devlog" title="Dev" description="Hantera dev-inlägg som visas på /dev (tester, API, integration, precision)" />;
}
