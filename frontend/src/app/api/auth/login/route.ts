import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const COOKIE_ACCESS = "access_token";
const COOKIE_REFRESH = "refresh_token";
const MAX_AGE_ACCESS = 60 * 10; // 10 min (aligné sur ACCESS_TOKEN_LIFETIME backend)
const MAX_AGE_REFRESH = 60 * 60 * 24 * 7; // 7j

function setTokenCookies(res: NextResponse, access: string, refresh: string) {
  res.cookies.set(COOKIE_ACCESS, access, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict", // "strict" : aucun envoi cross-site, aligné sur Django (CSRF_COOKIE_SAMESITE=Strict)
    path: "/",
    maxAge: MAX_AGE_ACCESS,
  });
  res.cookies.set(COOKIE_REFRESH, refresh, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: MAX_AGE_REFRESH,
  });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { username, password } = body;
    if (!username || !password) {
      return NextResponse.json(
        { detail: "Identifiant et mot de passe requis." },
        { status: 400 }
      );
    }
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15_000);
    let backendRes: Response;
    try {
      backendRes = await fetch(`${BACKEND_URL}/api/auth/login/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // Secret partagé Django↔Next.js — vérifié côté Django via INTERNAL_API_SECRET
          // Fail-fast si absent : une chaîne vide désactiverait silencieusement l'authentification proxy.
          "X-Proxy": process.env.INTERNAL_API_SECRET ?? (() => { throw new Error("INTERNAL_API_SECRET non configuré"); })(),
        },
        body: JSON.stringify({ username, password }),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeoutId);
    }
    const data = await backendRes.json().catch(() => ({}));
    if (!backendRes.ok) {
      return NextResponse.json(
        { detail: data.detail || "Identifiants incorrects." },
        { status: backendRes.status }
      );
    }
    if (!data.access || !data.refresh) {
      return NextResponse.json(
        { detail: "Réponse backend invalide." },
        { status: 502 }
      );
    }
    const res = NextResponse.json({ user: data.user });
    setTokenCookies(res, data.access, data.refresh);
    return res;
  } catch {
    return NextResponse.json(
      { detail: "Backend indisponible. Vérifiez le service Django (port 8000)." },
      { status: 503 }
    );
  }
}
