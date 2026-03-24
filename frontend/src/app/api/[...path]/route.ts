import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const COOKIE_ACCESS = "access_token";
const JSON_CT = "application/json; charset=utf-8";

const AUTH_PREFIXES = ["auth/login", "auth/me", "auth/logout", "auth/refresh"];

function isAuthPath(path: string[]) {
  const p = path.join("/");
  return AUTH_PREFIXES.some((prefix) => p === prefix || p.startsWith(prefix + "/"));
}

function jsonResponse(data: unknown, status: number) {
  return new NextResponse(JSON.stringify(data), {
    status,
    headers: { "Content-Type": JSON_CT },
  });
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) return jsonResponse({ detail: "Not found" }, 404);
  return proxy(request, path, "GET");
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) return jsonResponse({ detail: "Not found" }, 404);
  return proxy(request, path, "POST");
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) return jsonResponse({ detail: "Not found" }, 404);
  return proxy(request, path, "PUT");
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) return jsonResponse({ detail: "Not found" }, 404);
  return proxy(request, path, "PATCH");
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  if (isAuthPath(path)) return jsonResponse({ detail: "Not found" }, 404);
  return proxy(request, path, "DELETE");
}

async function proxy(
  request: NextRequest,
  path: string[],
  method: string
) {
  if (path.length === 0) return jsonResponse({ detail: "Not found" }, 404);

  const access = request.cookies.get(COOKIE_ACCESS)?.value;
  if (!access) return jsonResponse({ detail: "Non authentifié." }, 401);

  const pathStr = path.filter(Boolean).join("/");
  const url = new URL(request.url);
  const query = url.searchParams.toString();
  const basePath = pathStr ? `${pathStr}/` : "";
  const backendUrl = `${BACKEND_URL}/api/${basePath}${query ? `?${query}` : ""}`;

  // Whitelist explicite : seuls ces headers sont transmis au backend.
  // Aucun header client non listé ne passe (empêche l'injection de headers forgés).
  const headers: Record<string, string> = { Authorization: `Bearer ${access}` };
  const ct = request.headers.get("content-type");
  if (ct) headers["Content-Type"] = ct;
  const idempotencyKey = request.headers.get("idempotency-key");
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

  let body: string | undefined;
  try {
    body = await request.text();
  } catch {
    // no body
  }

  // Limite de taille : rejeter les payloads > 5 Mo avant de les envoyer au backend
  if (body && body.length > 5 * 1024 * 1024) {
    return jsonResponse({ detail: "Requête trop volumineuse (max 5 Mo)." }, 413);
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30_000);
  try {
    const backendRes = await fetch(backendUrl, {
      method,
      headers,
      body: body || undefined,
      signal: controller.signal,
    });
    const contentType = backendRes.headers.get("content-type") ?? "application/octet-stream";
    const isJson = contentType.includes("application/json");
    if (isJson) {
      const text = await backendRes.text();
      return new NextResponse(text, {
        status: backendRes.status,
        headers: { "Content-Type": JSON_CT },
      });
    }
    // Streamer le contenu brut (PDF, binaire, HTML…) avec le bon Content-Type
    const blob = await backendRes.arrayBuffer();
    return new NextResponse(blob, {
      status: backendRes.status,
      headers: { "Content-Type": contentType },
    });
  } catch (err) {
    const isTimeout = err instanceof Error && err.name === "AbortError";
    return jsonResponse(
      { detail: isTimeout ? "Délai d'attente dépassé." : "Service backend indisponible." },
      503,
    );
  } finally {
    clearTimeout(timeoutId);
  }
}
