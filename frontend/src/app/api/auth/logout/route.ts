import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const COOKIE_ACCESS = "access_token";
const COOKIE_REFRESH = "refresh_token";

export async function POST(request: NextRequest) {
  const access = request.cookies.get(COOKIE_ACCESS)?.value;
  const refresh = request.cookies.get(COOKIE_REFRESH)?.value;

  // Best effort: appeler le backend pour blacklister le refresh token.
  if (access && refresh) {
    try {
      await fetch(`${BACKEND_URL}/api/auth/logout/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${access}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ refresh }),
      });
    } catch {
      // L'utilisateur sera déconnecté côté frontend même en cas d'erreur backend.
    }
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE_ACCESS, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  res.cookies.set(COOKIE_REFRESH, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return res;
}
