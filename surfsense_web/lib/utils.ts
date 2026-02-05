import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { DEFAULT_LOCALE, LOCALE_MAP } from "@/lib/locale";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

export const formatDate = (date: Date, locale = DEFAULT_LOCALE): string => {
	const resolvedLocale = LOCALE_MAP[locale as keyof typeof LOCALE_MAP] ?? locale;
	return date.toLocaleDateString(resolvedLocale, {
		year: "numeric",
		month: "long",
		day: "numeric",
	});
};
