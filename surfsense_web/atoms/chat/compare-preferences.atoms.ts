"use client";

import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

// ============================================================================
// Compare Mode Preferences — persisted in localStorage
// ============================================================================

export type ComparePresetKey = "quick" | "standard" | "all" | "custom";

export interface ComparePreferences {
	/** Which preset is active */
	activePreset: ComparePresetKey;
	/** Custom model selection (used when preset === "custom") */
	customModels: string[];
	/** Default models for "standard" preset */
	defaultModels: string[];
}

const DEFAULT_PREFERENCES: ComparePreferences = {
	activePreset: "standard",
	customModels: [],
	defaultModels: ["claude", "gpt", "gemini", "perplexity"],
};

/**
 * Persisted compare preferences — survives page reloads.
 * Stored in localStorage under "oneseek:compare-preferences".
 */
export const comparePreferencesAtom = atomWithStorage<ComparePreferences>(
	"oneseek:compare-preferences",
	DEFAULT_PREFERENCES,
);

// ============================================================================
// Compare Mode UI State — ephemeral (resets on navigation)
// ============================================================================

export interface CompareUIState {
	/** Whether compare mode is currently active in the composer */
	isCompareActive: boolean;
	/** Whether the model picker panel is expanded */
	isPickerExpanded: boolean;
	/** Set of currently selected model keys for this compare request */
	selectedModels: Set<string>;
}

const DEFAULT_UI_STATE: CompareUIState = {
	isCompareActive: false,
	isPickerExpanded: false,
	selectedModels: new Set(["claude", "gpt", "gemini", "perplexity"]),
};

/** Ephemeral compare UI state — resets when navigating away */
export const compareUIStateAtom = atom<CompareUIState>(DEFAULT_UI_STATE);

// ============================================================================
// Derived atoms
// ============================================================================

/** Whether compare mode is toggled on */
export const isCompareActiveAtom = atom(
	(get) => get(compareUIStateAtom).isCompareActive,
	(get, set, active: boolean) => {
		const current = get(compareUIStateAtom);
		set(compareUIStateAtom, { ...current, isCompareActive: active });
	},
);

/** Whether the picker panel is expanded */
export const isPickerExpandedAtom = atom(
	(get) => get(compareUIStateAtom).isPickerExpanded,
	(get, set, expanded: boolean) => {
		const current = get(compareUIStateAtom);
		set(compareUIStateAtom, { ...current, isPickerExpanded: expanded });
	},
);

/** The set of selected models */
export const selectedCompareModelsAtom = atom(
	(get) => get(compareUIStateAtom).selectedModels,
	(get, set, models: Set<string>) => {
		const current = get(compareUIStateAtom);
		set(compareUIStateAtom, { ...current, selectedModels: models });
	},
);

/** Toggle a single model in/out of the selection */
export const toggleCompareModelAtom = atom(null, (get, set, modelKey: string) => {
	const current = get(compareUIStateAtom);
	const newModels = new Set(current.selectedModels);
	if (newModels.has(modelKey)) {
		newModels.delete(modelKey);
	} else {
		newModels.add(modelKey);
	}
	set(compareUIStateAtom, {
		...current,
		selectedModels: newModels,
		isCompareActive: newModels.size >= 2 ? current.isCompareActive : false,
	});
});

/** Apply a preset — updates both UI state and persisted preferences */
export const applyComparePresetAtom = atom(null, (get, set, preset: ComparePresetKey) => {
	const PRESET_MODELS: Record<ComparePresetKey, string[]> = {
		quick: ["claude", "gpt"],
		standard: ["claude", "gpt", "gemini", "perplexity"],
		all: ["claude", "gpt", "gemini", "perplexity", "deepseek", "qwen", "grok"],
		custom: Array.from(get(compareUIStateAtom).selectedModels),
	};

	const models = PRESET_MODELS[preset];
	const current = get(compareUIStateAtom);

	set(compareUIStateAtom, {
		...current,
		selectedModels: new Set(models),
	});

	// Persist preference
	set(comparePreferencesAtom, {
		...get(comparePreferencesAtom),
		activePreset: preset,
		...(preset === "custom" ? { customModels: models } : {}),
	});
});

/** Save current selection as the user's defaults */
export const saveCompareDefaultsAtom = atom(null, (get, set) => {
	const models = Array.from(get(compareUIStateAtom).selectedModels);
	set(comparePreferencesAtom, {
		...get(comparePreferencesAtom),
		activePreset: "custom",
		customModels: models,
		defaultModels: models,
	});
});

/** Reset compare UI state (call on chat navigation) */
export const resetCompareUIAtom = atom(null, (get, set) => {
	const prefs = get(comparePreferencesAtom);
	set(compareUIStateAtom, {
		isCompareActive: false,
		isPickerExpanded: false,
		selectedModels: new Set(prefs.defaultModels),
	});
});