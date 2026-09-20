"use client";

import { useState, useEffect, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { apiFetch, type TokenResponse } from "@/lib/api";
import { useAuth } from "@/context/auth-context";
import { useNotifications } from "@/hooks/useNotifications";
import { SESSION_EXPIRED_KEY } from "@/lib/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const { notifyDueToday } = useNotifications();
  const t = useTranslations("Auth");
  const tCommon = useTranslations("Common");
  // Starts null on server and client alike; the flags are read after mount so
  // the hydration render can't disagree with the server HTML.
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [smtpConfigured, setSmtpConfigured] = useState(false);

  useEffect(() => {
    // Two independent triggers for the session-expired banner: a client-side
    // 401 caught mid-session (flagged via sessionStorage, see
    // auth-context.tsx), or proxy.ts redirecting here server-side because the
    // cookie was already gone before the page ever loaded (flagged via query
    // param, since middleware can't touch sessionStorage).
    const hasQueryFlag =
      new URLSearchParams(window.location.search).get("session_expired") === "1";
    const hasStorageFlag = sessionStorage.getItem(SESSION_EXPIRED_KEY) !== null;
    if (hasQueryFlag || hasStorageFlag) {
      sessionStorage.removeItem(SESSION_EXPIRED_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-shot post-hydration read of browser-only flags; the value must also clear the flags, so it cannot be an external-store snapshot
      setError(t("sessionExpired"));
    }
  }, [t]);

  useEffect(() => {
    apiFetch<{ configured: boolean }>("/auth/smtp-status")
      .then((data) => setSmtpConfigured(data?.configured ?? false))
      .catch(() => setSmtpConfigured(false));
  }, []);

  // Strip ?session_expired so a manual refresh of this URL doesn't re-show the banner.
  useEffect(() => {
    if (window.location.search.includes("session_expired")) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const form = new FormData(e.currentTarget);
    const email = form.get("email") as string;
    const password = form.get("password") as string;

    try {
      await apiFetch<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      login();
      void notifyDueToday();
      router.push("/dashboard");
    } catch {
      setError(t("loginFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-900 px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-2">
          <Image src="/pt-logo.png" alt="Pay Tracker" width={80} height={80} className="rounded-2xl shadow-md" priority />
          <h1 className="text-2xl tracking-tight text-green-700 dark:text-green-500">
            <span className="font-normal">Pay</span><span className="font-bold">Tracker</span>
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {t("loginSubtitle")}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:bg-slate-800 dark:border-slate-700">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="email"
                className="text-sm font-medium text-slate-700 dark:text-slate-300"
              >
                {t("emailLabel")}
              </label>
              <Input
                id="email"
                name="email"
                type="email"
                required
                autoComplete="email"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="password"
                className="text-sm font-medium text-slate-700 dark:text-slate-300"
              >
                {t("passwordLabel")}
              </label>
              <Input
                id="password"
                name="password"
                type="password"
                required
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
                {error}
              </div>
            )}

            <Button type="submit" loading={loading} className="mt-1 w-full py-2.5">
              {loading ? t("signingIn") : t("signIn")}
            </Button>
          </form>

          <div className="mt-4 text-center text-sm">
            {smtpConfigured ? (
              <Link
                href="/forgot-password"
                className="text-slate-500 hover:text-green-700 dark:text-slate-400 dark:hover:text-green-500"
              >
                {t("forgotPassword")}
              </Link>
            ) : (
              <div>
                <span className="text-slate-400 dark:text-slate-500 cursor-default">
                  {t("forgotPassword")}
                </span>
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  {tCommon("smtpNotConfigured")}
                </p>
              </div>
            )}
          </div>
        </div>

        <p className="mt-5 text-center text-sm text-slate-500 dark:text-slate-400">
          {t("noAccount")}{" "}
          <Link
            href="/register"
            className="font-medium text-green-700 hover:text-green-800 dark:text-green-500"
          >
            {t("register")}
          </Link>
        </p>
      </div>
    </main>
  );
}
