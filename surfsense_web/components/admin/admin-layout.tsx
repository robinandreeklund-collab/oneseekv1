"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { 
	Settings, 
	MessageSquare, 
	Database, 
	Wrench,
	ToggleLeft,
	ChevronRight 
} from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";

const ADMIN_NAV_ITEMS = [
	{
		title: "Agent Prompts",
		href: "/admin/prompts",
		icon: MessageSquare,
		description: "Konfigurera agent system prompts",
	},
	{
		title: "Tool Settings",
		href: "/admin/tools",
		icon: Wrench,
		description: "Hantera verktygsmetadata och inställningar",
	},
	{
		title: "Tool Lifecycle",
		href: "/admin/lifecycle",
		icon: ToggleLeft,
		description: "Hantera tool lifecycle och gating",
	},
	{
		title: "Cache Management",
		href: "/admin/cache",
		icon: Database,
		description: "Rensa och hantera cache",
	},
];

interface AdminLayoutProps {
	children: React.ReactNode;
}

export function AdminLayout({ children }: AdminLayoutProps) {
	const pathname = usePathname();

	return (
		<div className="flex min-h-screen">
			{/* Sidebar */}
			<div className="w-64 border-r bg-muted/40">
				<div className="flex h-full flex-col">
					{/* Header */}
					<div className="flex h-16 items-center border-b px-6">
						<Settings className="mr-2 h-5 w-5" />
						<h1 className="text-lg font-semibold">Admin</h1>
					</div>

					{/* Navigation */}
					<ScrollArea className="flex-1 px-3 py-4">
						<nav className="space-y-1">
							{ADMIN_NAV_ITEMS.map((item) => {
								const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
								const Icon = item.icon;
								
								return (
									<Link
										key={item.href}
										href={item.href}
										className={cn(
											"flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
											"hover:bg-accent hover:text-accent-foreground",
											isActive
												? "bg-accent text-accent-foreground font-medium"
												: "text-muted-foreground"
										)}
									>
										<Icon className="h-4 w-4" />
										<span className="flex-1">{item.title}</span>
										{isActive && <ChevronRight className="h-4 w-4" />}
									</Link>
								);
							})}
						</nav>

						<Separator className="my-4" />

						<div className="px-3 py-2">
							<p className="text-xs text-muted-foreground">
								Administratörsinställningar för OneSeek-instansen
							</p>
						</div>
					</ScrollArea>
				</div>
			</div>

			{/* Main content */}
			<div className="flex-1">
				<div className="container mx-auto p-6 max-w-7xl">
					{children}
				</div>
			</div>
		</div>
	);
}
