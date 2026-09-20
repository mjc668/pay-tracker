"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { Archive, Receipt, CreditCard, LogOut, Menu, X, Settings } from "lucide-react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/context/auth-context";
import { fetchMe } from "@/lib/user-api";
import ThemeToggle from "@/components/ThemeToggle";
import LanguageToggle from "@/components/LanguageToggle";

const NAV_ITEMS = [
  { href: "/dashboard/payments", labelKey: "payments" as const, icon: CreditCard, exact: false },
  { href: "/dashboard/bills", labelKey: "bills" as const, icon: Receipt, exact: true },
  { href: "/dashboard/bills/archived", labelKey: "archived" as const, icon: Archive, exact: false },
  { href: "/dashboard/settings", labelKey: "settings" as const, icon: Settings, exact: false },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isReady, logout } = useAuth();
  const t = useTranslations("DashboardLayout");
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const menuRef = useRef<HTMLElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Wait for the cookie sync before deciding: redirecting during the first
    // render would kick authenticated users out before their state is known.
    if (isReady && !isAuthenticated) router.replace("/login");
  }, [isReady, isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchMe().then((p) => setUserEmail(p.email)).catch(() => {});
    }
  }, [isAuthenticated]);

  // Close mobile menu on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  // Close user dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    if (userMenuOpen) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [userMenuOpen]);

  if (!isReady || !isAuthenticated) return null;

  const initials = userEmail ? userEmail[0].toUpperCase() : "?";

  return (
    <div className="flex min-h-screen flex-col">
      {/* Top nav */}
      <header ref={menuRef} className="relative sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-700 dark:bg-slate-800/80">
        <div className="mx-auto flex max-w-4xl items-center gap-4 px-4 py-3">
          {/* Brand */}
          <Link
            href="/dashboard"
            className="flex items-center gap-2 text-green-700 transition-opacity hover:opacity-80 dark:text-green-500"
          >
            <Image src="/pt-logo.png" alt="Pay Tracker" width={32} height={32} className="rounded-xl" />
            <span className="text-lg tracking-tight">
              <span className="font-normal">Pay</span><span className="font-bold">Tracker</span>
            </span>
          </Link>

          {/* Desktop nav links */}
          <nav className="hidden md:flex flex-1 items-center gap-1 ml-4">
            {NAV_ITEMS.map(({ href, labelKey, icon: Icon, exact }) => {
              const active = pathname === href || (!exact && pathname.startsWith(href + "/"));
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                    active
                      ? "border border-green-200 bg-green-50 text-green-800 shadow-sm dark:border-green-800 dark:bg-green-900/30 dark:text-green-300"
                      : "border border-transparent text-slate-600 hover:border-green-200 hover:bg-green-50 hover:text-green-700 dark:text-slate-400 dark:hover:border-emerald-800 dark:hover:bg-emerald-900/20 dark:hover:text-emerald-300"
                  }`}
                >
                  <Icon size={15} />
                  {t(labelKey)}
                </Link>
              );
            })}
          </nav>

          {/* Desktop right side */}
          <div className="hidden md:flex items-center gap-1 ml-auto">
            <LanguageToggle />
            <ThemeToggle />

            {/* Avatar + dropdown */}
            <div className="relative" ref={userMenuRef}>
              <button
                onClick={() => setUserMenuOpen((o) => !o)}
                aria-label={t("userMenu")}
                className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold text-white shadow-sm transition-all ${
                  userMenuOpen
                    ? "bg-green-800 dark:bg-green-500"
                    : "bg-green-700 hover:bg-green-800 dark:bg-green-600 dark:hover:bg-green-500"
                }`}
              >
                {initials}
              </button>

              {/* Dropdown */}
              {userMenuOpen && (
                <div className="absolute right-0 top-full mt-2 z-50 w-64 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-800">
                  <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-700">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                      {t("signedInAs")}
                    </p>
                    <p className="mt-0.5 truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                      {userEmail}
                    </p>
                  </div>
                  <div className="p-2">
                    <button
                      onClick={() => { setUserMenuOpen(false); logout(); }}
                      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-all hover:bg-red-50 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-900/20 dark:hover:text-red-400"
                    >
                      <LogOut size={14} />
                      {t("logOut")}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Mobile: utility icons + hamburger */}
          <div className="flex md:hidden items-center gap-1 ml-auto">
            <LanguageToggle />
            <button
              onClick={() => setMenuOpen((o) => !o)}
              aria-label="Toggle menu"
              aria-expanded={menuOpen}
              className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 transition-colors"
            >
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>

            {/* Mobile dropdown */}
            {menuOpen && (
              <div className="absolute top-full inset-x-0 border-b border-slate-200 bg-white shadow-md dark:border-slate-700 dark:bg-slate-800">
                <div className="mx-auto max-w-4xl px-4 py-3 flex flex-col gap-1">
                  {/* Signed-in email header */}
                  {userEmail && (
                    <div className="mb-2 flex items-center gap-2.5 rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-700/50">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-green-700 text-xs font-bold text-white dark:bg-green-600">
                        {initials}
                      </div>
                      <span className="truncate text-sm text-slate-600 dark:text-slate-300">{userEmail}</span>
                    </div>
                  )}

                  {NAV_ITEMS.map(({ href, labelKey, icon: Icon, exact }) => {
                    const active = pathname === href || (!exact && pathname.startsWith(href + "/"));
                    return (
                      <Link
                        key={href}
                        href={href}
                        onClick={() => setMenuOpen(false)}
                        className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                          active
                            ? "border border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/30 dark:text-green-300"
                            : "border border-transparent text-slate-600 hover:border-green-200 hover:bg-green-50 hover:text-green-700 dark:text-slate-400 dark:hover:border-emerald-800 dark:hover:bg-emerald-900/20 dark:hover:text-emerald-300"
                        }`}
                      >
                        <Icon size={16} />
                        {t(labelKey)}
                      </Link>
                    );
                  })}

                  <div className="flex items-center gap-2 pt-1 border-t border-slate-100 dark:border-slate-700 mt-1">
                    <ThemeToggle />
                    <button
                      onClick={() => { setMenuOpen(false); logout(); }}
                      className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-500 shadow-sm transition-all hover:border-red-300 hover:bg-red-50 hover:text-red-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-red-800 dark:hover:bg-red-900/20 dark:hover:text-red-400"
                    >
                      <LogOut size={15} />
                      {t("logOut")}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1">{children}</main>
    </div>
  );
}
