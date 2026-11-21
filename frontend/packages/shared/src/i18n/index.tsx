import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  LOCALE_STORAGE_KEY,
  resolveInitialLocale,
  toHtmlLang,
  type StudioLocale,
} from "./locale.ts";

export * from "./locale.ts";

export interface StudioI18nContextValue {
  locale: StudioLocale;
  isZh: boolean;
  setLocale: (next: StudioLocale) => void;
  toggleLocale: () => void;
  t: <T = string>(en: T, zh: T) => T;
}

const defaultTranslate = <T = string>(en: T, _zh: T): T => en;

const StudioI18nContext = createContext<StudioI18nContextValue>({
  locale: "en",
  isZh: false,
  setLocale: () => undefined,
  toggleLocale: () => undefined,
  t: defaultTranslate,
});

function readStoredLocale(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(LOCALE_STORAGE_KEY);
  } catch {
    return null;
  }
}

function getInitialClientLocale(fallback?: StudioLocale): StudioLocale {
  if (typeof window === "undefined") return fallback ?? "en";
  return resolveInitialLocale({
    stored: readStoredLocale(),
    fallback,
    languages: typeof navigator !== "undefined" ? navigator.languages : undefined,
    language: typeof navigator !== "undefined" ? navigator.language : undefined,
  });
}

export function StudioI18nProvider({
  children,
  fallbackLocale,
}: {
  children: React.ReactNode;
  fallbackLocale?: StudioLocale;
}) {
  const [locale, setLocaleState] = useState<StudioLocale>(() => getInitialClientLocale(fallbackLocale));

  const setLocale = useCallback((next: StudioLocale) => {
    setLocaleState(next);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
      } catch {
        // ignore storage errors
      }
    }
  }, []);

  const toggleLocale = useCallback(() => {
    setLocale(locale === "zh" ? "en" : "zh");
  }, [locale, setLocale]);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = toHtmlLang(locale);
    }
  }, [locale]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onStorage = (event: StorageEvent) => {
      if (event.key !== LOCALE_STORAGE_KEY) return;
      if (event.newValue === "en" || event.newValue === "zh") {
        setLocaleState(event.newValue);
      } else if (event.newValue === null) {
        setLocaleState(getInitialClientLocale(fallbackLocale));
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [fallbackLocale]);

  const value = useMemo<StudioI18nContextValue>(
    () => ({
      locale,
      isZh: locale === "zh",
      setLocale,
      toggleLocale,
      t: <T = string>(en: T, zh: T): T => (locale === "zh" ? zh : en),
    }),
    [locale, setLocale, toggleLocale],
  );

  return <StudioI18nContext.Provider value={value}>{children}</StudioI18nContext.Provider>;
}

export function useStudioLocale(): StudioI18nContextValue {
  return useContext(StudioI18nContext);
}
