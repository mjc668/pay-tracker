import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const publicRoutes = ["/login", "/register", "/forgot-password", "/reset-password"];

// Only page-navigation methods may be bounced to the GET-only /login page.
// Redirecting a POST/PUT/DELETE (e.g. Next's router or Server-Function calls)
// with a 307 preserves the method and produces a 405 on /login.
const NAVIGATION_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("access_token")?.value;
  const method = request.method;

  const isPublicRoute = publicRoutes.some(
    (route) => pathname === route || pathname.startsWith(route + "/"),
  );

  if (!token && !isPublicRoute) {
    if (!NAVIGATION_METHODS.has(method)) {
      // Not a navigation — fail it cleanly so it is never redirected onto
      // the login page. The router treats this as an auth failure and falls
      // back to a normal (GET) page navigation.
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    // Marks this as a session-expiry redirect (as opposed to a plain
    // unauthenticated visit) so the login page can show the "session
    // expired" banner even when no client-side 401 ever fired — this path
    // runs server-side, before React mounts, so it can't touch sessionStorage.
    const url = new URL("/login", request.url);
    url.searchParams.set("session_expired", "1");
    // 303 forces the follow-up request to be GET, guaranteeing the login
    // page is always reached by GET regardless of the original method.
    return NextResponse.redirect(url, 303);
  }

  if (token && isPublicRoute) {
    return NextResponse.redirect(new URL("/dashboard", request.url), 303);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|manifest\\.webmanifest$|sw\\.js$|icon-(?:192|512)\\.png$|pt-logo\\.png$).*)",
  ],
};
