"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
  ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { getAuthToken, SESSION_EXPIRED_KEY } from "@/lib/auth";
import { apiFetch, setSessionExpiredHandler } from "@/lib/api";
import { fetchMe } from "@/lib/user-api";

// How often to proactively check the session while a tab is authenticated
// and visible. This is what redirects an idle tab to /login on its own once
// the token expires, instead of waiting for the user to click something.
// Configurable because ACCESS_TOKEN_EXPIRE_MINUTES varies a lot between
// environments (minutes in dev/testing, hours in production).
const DEFAULT_SESSION_HEARTBEAT_SECONDS = 180;
const SESSION_HEARTBEAT_MS =
  (Number(process.env.NEXT_PUBLIC_SESSION_HEARTBEAT_SECONDS) ||
    DEFAULT_SESSION_HEARTBEAT_SECONDS) * 1000;

interface AuthContextValue {
  isAuthenticated: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Presence is detected from the non-HttpOnly auth_logged_in cookie.
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => getAuthToken() !== null,
  );
  const router = useRouter();
  // Guards against multiple parallel 401s all triggering the redirect.
  const loggingOutRef = useRef(false);

  // Backend sets both HttpOnly access_token and presence auth_logged_in cookies.
  // login() just syncs React state to reflect the new auth state.
  //
  // router.refresh() busts Next's client Router Cache, which can hold a
  // stale middleware redirect (see src/proxy.ts) captured for a nav link
  // that was prefetched while unauthenticated. Without this, a page whose
  // cache entry was poisoned during the logged-out window keeps bouncing
  // to /login after a fresh, valid re-login.
  const login = useCallback(() => {
    loggingOutRef.current = false;
    setIsAuthenticated(true);
    router.refresh();
  }, [router]);

  const logout = useCallback(async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // Proceed with client-side logout even if the request fails.
    }
    setIsAuthenticated(false);
    router.refresh();
    router.push("/login");
  }, [router]);

  useEffect(() => {
    setSessionExpiredHandler(async () => {
      if (loggingOutRef.current) return;
      loggingOutRef.current = true;
      sessionStorage.setItem(SESSION_EXPIRED_KEY, "1");
      setIsAuthenticated(false);
      // The token has been rejected by the backend (expired, revoked, or a
      // pre-claims-enforcement cookie). Clear the HttpOnly cookie server-side
      // first so the proxy stops bouncing /login → /dashboard; then hard-
      // navigate so the fresh request goes out with the cookies already gone.
      try {
        await apiFetch("/auth/logout", { method: "POST" });
      } catch {
        // Even a failed logout must not block the redirect.
      }
      window.location.assign("/login");
    });
    return () => setSessionExpiredHandler(null);
  }, []);

  // Proactive expiry check: a real 401 here is already handled globally by
  // apiFetch/sessionExpiredHandler above, so this effect only needs to make
  // the request — no new redirect logic. Any non-401 error (network blip
  // etc.) is swallowed so it can't itself trigger a logout.
  useEffect(() => {
    if (!isAuthenticated) return;

    const check = () => {
      if (document.visibilityState === "visible") fetchMe().catch(() => {});
    };

    const id = setInterval(check, SESSION_HEARTBEAT_MS);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check);
    };
  }, [isAuthenticated]);

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
