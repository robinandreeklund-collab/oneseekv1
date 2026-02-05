"use client";

import { useCallback, useState } from "react";
import type {
	GlobalNewLLMConfig,
	NewLLMConfigPublic,
} from "@/contracts/types/new-llm-config.types";
import { ModelConfigSidebar } from "./model-config-sidebar";
import { ModelSelector } from "./model-selector";

interface ChatHeaderProps {
	searchSpaceId: number;
	isPublicChat?: boolean;
}

export function ChatHeader({ searchSpaceId, isPublicChat = false }: ChatHeaderProps) {
	const [sidebarOpen, setSidebarOpen] = useState(false);
	const [selectedConfig, setSelectedConfig] = useState<
		NewLLMConfigPublic | GlobalNewLLMConfig | null
	>(null);
	const [isGlobal, setIsGlobal] = useState(false);
	const [sidebarMode, setSidebarMode] = useState<"create" | "edit" | "view">("view");

	if (isPublicChat) {
		return (
			<div className="flex items-center gap-2">
				<div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted px-3 py-1 text-sm text-muted-foreground">
					Global model (public)
				</div>
			</div>
		);
	}

	const handleEditConfig = useCallback(
		(config: NewLLMConfigPublic | GlobalNewLLMConfig, global: boolean) => {
			setSelectedConfig(config);
			setIsGlobal(global);
			setSidebarMode(global ? "view" : "edit");
			setSidebarOpen(true);
		},
		[]
	);

	const handleAddNew = useCallback(() => {
		setSelectedConfig(null);
		setIsGlobal(false);
		setSidebarMode("create");
		setSidebarOpen(true);
	}, []);

	const handleSidebarClose = useCallback((open: boolean) => {
		setSidebarOpen(open);
		if (!open) {
			// Reset state when closing
			setSelectedConfig(null);
		}
	}, []);

	return (
		<div className="flex items-center gap-2">
			<ModelSelector onEdit={handleEditConfig} onAddNew={handleAddNew} />
			<ModelConfigSidebar
				open={sidebarOpen}
				onOpenChange={handleSidebarClose}
				config={selectedConfig}
				isGlobal={isGlobal}
				searchSpaceId={searchSpaceId}
				mode={sidebarMode}
			/>
		</div>
	);
}
