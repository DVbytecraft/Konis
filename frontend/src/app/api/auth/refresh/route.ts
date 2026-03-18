import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const COOKIE_ACCESS = "access_token";
const COOKIE_REFRESH = "refresh_token";
const MAX_AGE_ACCESS = 60 * 10; // 10 min (aligné sur ACCESS_TOKEN_LIFETIME backend)
const MAX_AGE_REFRESH = 60 * 60 * 24 * 7; // 7 jours

export async function POST(request: NextRequest) {
  const refresh = request.cookies.get(COOKIE_REFRESH)?.value;
  if (!refresh) {
    return NextResponse.json(
      { detail: "Refresh token manquant." },
      { status: 401 }
    );
  }
  try {
    const backendRes = await fetch(`${BACKEND_URL}/api/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!backendRes.ok) {
      return NextResponse.json(
        { detail: "Session expirée." },
        { status: 401 }
      );
    }
    const data = await backendRes.json().catch(() => ({}));
    const access = data.access;
    if (!access) {
      return NextResponse.json(
        { detail: "Réponse backend invalide." },
        { status: 502 }
      );
    }
    const res = NextResponse.json({ ok: true });
    res.cookies.set(COOKIE_ACCESS, access, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      maxAge: MAX_AGE_ACCESS,
    });
    if (data.refresh) {
      res.cookies.set(COOKIE_REFRESH, data.refresh, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "strict",
        path: "/",
        maxAge: MAX_AGE_REFRESH,
      });
    }
    return res;
  } catch {
    return NextResponse.json(
      { detail: "Erreur serveur." },
      { status: 500 }
    );
  }
}
