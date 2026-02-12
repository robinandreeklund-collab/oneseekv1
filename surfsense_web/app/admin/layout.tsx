import { AdminLayout } from "@/components/admin/admin-layout";

export default function AdminLayoutPage({
	children,
}: {
	children: React.ReactNode;
}) {
	return <AdminLayout>{children}</AdminLayout>;
}
