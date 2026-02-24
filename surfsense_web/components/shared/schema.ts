/**
 * Shared schema types for tool UI components
 */

/**
 * Action item for response actions in UI components
 */
export interface Action {
	id: string;
	label: string;
	variant?: "default" | "secondary" | "destructive" | "outline" | "ghost";
	disabled?: boolean;
}

/**
 * Structured configuration for confirm/cancel actions
 */
export interface ActionsConfig {
	confirm?: Omit<Action, "id">;
	cancel?: Omit<Action, "id">;
}
