import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const COOKIE_ACCESS = "access_token";

export async function GET(request: NextRequest) {
  const access = request.cookies.get(COOKIE_ACCESS)?.value;
  if (!access) {
    return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });
  }
  try {
    const backendRes = await fetch(`${BACKEND_URL}/api/auth/me/`, {
      headers: {
        Authorization: `Bearer ${access}`,
      },
    });
    if (!backendRes.ok) {
      return NextResponse.json(
        { detail: "Session invalide." },
        { status: 401 }
      );
    }
    const user = await backendRes.json();
    return NextResponse.json(user);
  } catch {
    return NextResponse.json(
      { detail: "Backend indisponible. Vérifiez le service Django (port 8000)." },
      { status: 503 }
    );
  }
}
