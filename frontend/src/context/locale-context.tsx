"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useSyncExternalStore,
  ReactNode,
} from "react";
import { NextIntlClientProvider } from "next-intl";
import { useAuth } from "@/context/auth-context";
import { fetchMe, updateMe } from "@/lib/user-api";
import enMessages from "../../messages/en.json";
import plMessages from "../../messages/pl.json";
import deMessages from "../../messages/de.json";

export type Locale = "en" | "pl" | "de";

const messagesMap: Record<Locale, typeof enMessages> = {
  en: enMessages,
  pl: plMessages,
  de: deMessages,
};

const VALID_LOCALES: Locale[] = ["en", "pl", "de"];

function detectBrowserLocale(): Locale {
  if (typeof navigator === "undefined") return "en";
  const lang = navigator.language;
  if (lang.startsWith("pl")) return "pl";
  if (lang.startsWith("de")) return "de";
  return "en";
}

function subscribeNever(): () => void {
  return () => {};
}

function getServerLocale(): Locale {
  return "en";
}

interface LocaleContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  // navigator.language is browser-only, so SSR and hydration always start at
  // "en" (getServerSnapshot); React re-reads the client value after hydration.
  // Account-level preference overrides it once the profile loads.
  const detectedLocale = useSyncExternalStore(
    subscribeNever,
    detectBrowserLocale,
    getServerLocale,
  );
  const [localeOverride, setLocaleOverride] = useState<Locale | null>(null);
  const locale = localeOverride ?? detectedLocale;

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    fetchMe()
      .then((profile) => {
        if (cancelled) return;
        if (
          profile.language_preference &&
          VALID_LOCALES.includes(profile.language_preference as Locale)
        ) {
          setLocaleOverride(profile.language_preference as Locale);
        } else if (!profile.language_preference) {
          // Persist the browser-detected locale so backend emails use the right language
          updateMe({ language_preference: detectBrowserLocale() }).catch(() => {});
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback(
    (l: Locale) => {
      setLocaleOverride(l);
      if (isAuthenticated) {
        updateMe({ language_preference: l }).catch(() => {
          // persist failure is non-fatal
        });
      }
    },
    [isAuthenticated],
  );

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      <NextIntlClientProvider locale={locale} messages={messagesMap[locale]}>
        {children}
      </NextIntlClientProvider>
    </LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return ctx;
}
