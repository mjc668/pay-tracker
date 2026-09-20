"use client";

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useRef,
  useSyncExternalStore,
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

// Auth state is an external store backed by the presence cookie. Server and
// hydration renders report "logged out" via getAuthServerSnapshot; once
// hydrated, React re-reads the client snapshot, and login/logout emit changes.
// This keeps SSR HTML and the hydration render identical (no React #418).
const authListeners = new Set<() => void>();

function subscribeAuth(onChange: () => void): () => void {
  authListeners.add(onChange);
  return () => {
    authListeners.delete(onChange);
  };
}

function emitAuthChanged(): void {
  authListeners.forEach((listener) => listener());
}

function getAuthSnapshot(): boolean {
  return getAuthToken() !== null;
}

function getAuthServerSnapshot(): boolean {
  return false;
}

function subscribeNever(): () => void {
  return () => {};
}

function getMountedSnapshot(): boolean {
  return true;
}

function getMountedServerSnapshot(): boolean {
  return false;
}

interface AuthContextValue {
  isAuthenticated: boolean;
  // False until the post-hydration cookie read has run. Consumers that render
  // auth-dependent markup must wait for this so the first client render
  // matches the server HTML.
  isReady: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // isReady flips true after hydration so the dashboard redirect guard never
  // runs against the placeholder "logged out" value.
  const isReady = useSyncExternalStore(
    subscribeNever,
    getMountedSnapshot,
    getMountedServerSnapshot,
  );
  const isAuthenticated = useSyncExternalStore(
    subscribeAuth,
    getAuthSnapshot,
    getAuthServerSnapshot,
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
    // The /auth/login response already set the cookies; notify the store.
    emitAuthChanged();
    router.refresh();
  }, [router]);

  const logout = useCallback(async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // Proceed with client-side logout even if the request fails.
    }
    emitAuthChanged();
    router.refresh();
    router.push("/login");
  }, [router]);

  useEffect(() => {
    setSessionExpiredHandler(async () => {
      if (loggingOutRef.current) return;
      loggingOutRef.current = true;
      sessionStorage.setItem(SESSION_EXPIRED_KEY, "1");
      // The token has been rejected by the backend (expired, revoked, or a
      // pre-claims-enforcement cookie). Clear the HttpOnly cookie server-side
      // first so the proxy stops bouncing /login → /dashboard; then hard-
      // navigate so the fresh request goes out with the cookies already gone.
      try {
        await apiFetch("/auth/logout", { method: "POST" });
      } catch {
        // Even a failed logout must not block the redirect.
      }
      emitAuthChanged();
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
    <AuthContext.Provider value={{ isAuthenticated, isReady, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
