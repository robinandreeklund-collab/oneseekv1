import { createContext } from "react";
import type { CompareProvider } from "@/components/tool-ui/compare-sources-bar";

/**
 * Context to pass compare providers data to AssistantMessage components.
 * Similar pattern to ThinkingStepsContext.
 * 
 * Maps message ID to array of CompareProvider data.
 */
export const CompareProvidersContext = createContext<Map<string, CompareProvider[]>>(new Map());

/**
 * Context for managing the selected provider in CompareDetailSheet.
 * Allows parent component to control which provider is selected.
 */
export interface CompareDetailState {
	selectedProviderKey: string | null;
	setSelectedProviderKey: (key: string | null) => void;
	isDetailSheetOpen: boolean;
	setIsDetailSheetOpen: (open: boolean) => void;
}

export const CompareDetailContext = createContext<CompareDetailState | null>(null);
