import { NextRequest, NextResponse } from "next/server";

// Chemins publics : aucune vérification d'auth requise
const PUBLIC_PATHS = [
  "/login",
  "/api/auth/login",
  "/api/auth/logout",
  "/api/auth/refresh",
  "/api/auth/me",
];

function isPublic(pathname: string): boolean {
  // Fichiers statiques Next.js
  if (
    pathname.startsWith("/_next/") ||
    pathname === "/favicon.ico" ||
    pathname.startsWith("/favicon")
  ) {
    return true;
  }
  // Proxy API : les routes /api/[...path] gèrent elles-mêmes l'auth (Bearer token)
  if (pathname.startsWith("/api/")) {
    return true;
  }
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (isPublic(pathname)) {
    return NextResponse.next();
  }

  const accessToken  = request.cookies.get("access_token")?.value;
  const refreshToken = request.cookies.get("refresh_token")?.value;

  // Ni access ni refresh token → redirect immédiat vers /login
  // (le client-side auth-context gère le refresh si seul l'access est absent)
  if (!accessToken && !refreshToken) {
    const loginUrl = new URL("/login", request.url);
    // Conserver la destination pour rediriger après login
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Matcher : toutes les routes sauf fichiers statiques Next.js
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
