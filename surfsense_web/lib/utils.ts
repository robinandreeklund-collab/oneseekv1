import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

const DEFAULT_LOCALE = "sv";
const LOCALE_DATE_MAP: Record<string, string> = {
	sv: "sv-SE",
	en: "en-US",
	zh: "zh-CN",
};

export const formatDate = (date: Date, locale = DEFAULT_LOCALE): string => {
	const resolvedLocale = LOCALE_DATE_MAP[locale] ?? locale;
	return date.toLocaleDateString(resolvedLocale, {
		year: "numeric",
		month: "long",
		day: "numeric",
	});
};
