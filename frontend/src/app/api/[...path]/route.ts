import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const COOKIE_ACCESS = "access_token";

const AUTH_PREFIXES = ["auth/login", "auth/me", "auth/logout", "auth/refresh"];

function isAuthPath(path: string[]) {
  const p = path.join("/");
  return AUTH_PREFIXES.some((prefix) => p === prefix || p.startsWith(prefix + "/"));
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  return proxy(request, path, "GET");
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  return proxy(request, path, "POST");
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  return proxy(request, path, "PUT");
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  return proxy(request, path, "PATCH");
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  return proxy(request, path, "DELETE");
}

async function proxy(
  request: NextRequest,
  path: string[],
  method: string
) {
  if (path.length === 0) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  const access = request.cookies.get(COOKIE_ACCESS)?.value;
  if (!access) {
    return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });
  }
  const pathStr = path.filter(Boolean).join("/");
  const url = new URL(request.url);
  const query = url.searchParams.toString();
  const basePath = pathStr ? `${pathStr}/` : "";
  const backendUrl = `${BACKEND_URL}/api/${basePath}${query ? `?${query}` : ""}`;
  const headers: Record<string, string> = {};
  if (access) headers.Authorization = `Bearer ${access}`;
  if (request.headers.get("content-type")) {
    headers["Content-Type"] = request.headers.get("content-type")!;
  }
  let body: string | undefined;
  try {
    body = await request.text();
  } catch {
    // no body
  }
  try {
    const backendRes = await fetch(backendUrl, {
      method,
      headers,
      body: body || undefined,
    });
    const contentType = backendRes.headers.get("content-type");
    const isJson = contentType?.includes("application/json");
    const data = isJson ? await backendRes.json().catch(() => ({})) : {};
    return NextResponse.json(data, { status: backendRes.status });
  } catch {
    return NextResponse.json(
      { detail: "Service backend indisponible." },
      { status: 503 }
    );
  }
}
