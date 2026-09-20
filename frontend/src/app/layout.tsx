import type { Metadata } from "next";
import { connection } from "next/server";
import { Geist, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/context/auth-context";
import { LocaleProvider } from "@/context/locale-context";
import PwaRegister from "@/components/pwa-register";
import AppFooter from "@/components/AppFooter";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Pay Tracker",
  description: "Household bill tracking made simple",
  themeColor: "#2563eb",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  await connection();
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <head>
        {/* Prevent flash of wrong theme */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var t=localStorage.getItem('theme');if(t==='dark')document.documentElement.classList.add('dark');})();`,
          }}
        />
        {(() => {
          // Injected at request time from the container's .env (API_URL) so
          // the same image works anywhere without being rebuilt. Falls back
          // to the build-time NEXT_PUBLIC_API_URL when not set.
          const apiBaseUrl = process.env.API_URL?.trim() ?? "";
          if (!apiBaseUrl) return null;
          return (
            <script
              dangerouslySetInnerHTML={{
                __html: `window.__PT_API_URL__=${JSON.stringify(apiBaseUrl)};`,
              }}
            />
          );
        })()}
      </head>
      <body className="min-h-full flex flex-col bg-slate-50 dark:bg-slate-900 antialiased">
        <PwaRegister />
        <AuthProvider>
          <LocaleProvider>{children}</LocaleProvider>
        </AuthProvider>
        <AppFooter />
      </body>
    </html>
  );
}
