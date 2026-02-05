"use client";

import type React from "react";
import { createContext, useContext, useEffect, useState } from "react";
import enMessages from "../messages/en.json";
import svMessages from "../messages/sv.json";
import zhMessages from "../messages/zh.json";
import { DEFAULT_LOCALE, type LocaleCode } from "@/lib/locale";

type Locale = LocaleCode;

interface LocaleContextType {
	locale: Locale;
	messages: typeof enMessages;
	setLocale: (locale: Locale) => void;
}

const LocaleContext = createContext<LocaleContextType | undefined>(undefined);

const LOCALE_STORAGE_KEY = "surfsense-locale";
const LOCALE_MESSAGES: Record<Locale, typeof enMessages> = {
	sv: svMessages,
	en: enMessages,
	zh: zhMessages,
};

export function LocaleProvider({ children }: { children: React.ReactNode }) {
	// Always start with 'sv' to avoid hydration mismatch
	// Then sync with localStorage after mount
	const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);
	const [mounted, setMounted] = useState(false);

	// Get messages based on current locale
	const messages = LOCALE_MESSAGES[locale] ?? LOCALE_MESSAGES[DEFAULT_LOCALE];

	// Load locale from localStorage after component mounts (client-side only)
	useEffect(() => {
		setMounted(true);
		if (typeof window !== "undefined") {
			const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
			if (stored && stored in LOCALE_MESSAGES) {
				setLocaleState(stored as Locale);
			}
		}
	}, []);

	// Update locale and persist to localStorage
	const setLocale = (newLocale: Locale) => {
		setLocaleState(newLocale);
		if (typeof window !== "undefined") {
			localStorage.setItem(LOCALE_STORAGE_KEY, newLocale);
			// Update HTML lang attribute
			document.documentElement.lang = newLocale;
		}
	};

	// Set HTML lang attribute when locale changes
	useEffect(() => {
		if (typeof window !== "undefined" && mounted) {
			document.documentElement.lang = locale;
		}
	}, [locale, mounted]);

	return (
		<LocaleContext.Provider value={{ locale, messages, setLocale }}>
			{children}
		</LocaleContext.Provider>
	);
}

export function useLocaleContext() {
	const context = useContext(LocaleContext);
	if (context === undefined) {
		throw new Error("useLocaleContext must be used within a LocaleProvider");
	}
	return context;
}
