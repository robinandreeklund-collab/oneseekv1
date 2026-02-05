import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

const LOCALE_DATE_MAP: Record<string, string> = {
	sv: "sv-SE",
	en: "en-US",
	zh: "zh-CN",
};

export const formatDate = (date: Date, locale = "sv"): string => {
	const resolvedLocale = LOCALE_DATE_MAP[locale] ?? locale;
	return date.toLocaleDateString(resolvedLocale, {
		year: "numeric",
		month: "long",
		day: "numeric",
	});
};
