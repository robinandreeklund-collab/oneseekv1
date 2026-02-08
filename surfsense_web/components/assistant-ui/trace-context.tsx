"use client";

import { createContext } from "react";
import type { TraceSpan } from "@/contracts/types/chat-trace.types";

export type TracePanelContextValue = {
	messageTraceSessions: Map<string, string>;
	traceSpansBySession: Map<string, TraceSpan[]>;
	activeMessageId: string | null;
	isOpen: boolean;
	openTraceForMessage: (messageId: string) => void;
	setIsOpen: (open: boolean) => void;
};

export const TracePanelContext = createContext<TracePanelContextValue | null>(null);
