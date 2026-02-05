// Swedish is the default locale per product requirements.
export const DEFAULT_LOCALE = "sv" as const;

export const LOCALE_MAP = {
	sv: "sv-SE",
	en: "en-US",
	zh: "zh-CN",
} as const;

export type LocaleCode = keyof typeof LOCALE_MAP;
