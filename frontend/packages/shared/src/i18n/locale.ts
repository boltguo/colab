export type StudioLocale = "en" | "zh";

export const LOCALE_STORAGE_KEY = "colab_studio_locale";

export function parseLocaleTag(tag?: string | null): StudioLocale | null {
  if (!tag) return null;
  const normalized = tag.trim().toLowerCase();
  if (!normalized) return null;
  if (normalized.startsWith("zh")) return "zh";
  if (normalized.startsWith("en")) return "en";
  return null;
}

export function detectBrowserLocale(
  languages?: readonly string[] | null,
  fallbackLanguage?: string | null,
): StudioLocale {
  const candidates: string[] = [];
  if (Array.isArray(languages)) {
    candidates.push(...languages);
  }
  if (fallbackLanguage) {
    candidates.push(fallbackLanguage);
  }
  for (const tag of candidates) {
    const parsed = parseLocaleTag(tag);
    if (parsed) return parsed;
  }
  return "en";
}

export function resolveInitialLocale(options?: {
  stored?: string | null;
  languages?: readonly string[] | null;
  language?: string | null;
}): StudioLocale {
  if (options?.stored === "en" || options?.stored === "zh") {
    return options.stored;
  }
  return detectBrowserLocale(options?.languages, options?.language);
}

export function toM3ELocale(locale: StudioLocale): "en-US" | "zh-CN" {
  return locale === "zh" ? "zh-CN" : "en-US";
}

export function toHtmlLang(locale: StudioLocale): "en" | "zh-CN" {
  return locale === "zh" ? "zh-CN" : "en";
}
