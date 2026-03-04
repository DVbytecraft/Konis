/**
 * Toutes les requêtes API passent par Next.js (même origine).
 * Auth : route handlers Next (cookies httpOnly).
 * Données : proxy Next → Django avec token depuis cookie.
 *
 * CSRF : pour les méthodes mutantes (POST/PUT/PATCH/DELETE), le token CSRF
 * est lu depuis le cookie `csrftoken` (non-httpOnly) et envoyé via l'en-tête
 * X-CSRFToken. Ceci est une défense en profondeur ; la protection principale
 * est SameSite=Strict sur les cookies JWT.
 */

function getApiBase(): string {
  if (typeof window !== "undefined") return "";
  // Côté serveur (SSR/Route handlers) : préférer BACKEND_URL (réseau Docker interne)
  // plutôt que NEXT_PUBLIC_API_URL qui pointe vers l'hôte public.
  return process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

export function apiUrl(path: string) {
  const base = getApiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}/api${p}`;
}

/**
 * URL vers les templates HTML Django (impression ticket/facture).
 * Ces endpoints renvoient du HTML (non JSON) et ne passent pas par le proxy /api/.
 * Côté navigateur : utilise NEXT_PUBLIC_API_URL (URL publique du backend).
 */
export function djangoUrl(path: string): string {
  const base =
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      : process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

const AUTH_PATH_PREFIXES = ["/auth/login", "/auth/me", "/auth/logout", "/auth/refresh"];
const CSRF_SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
let refreshInFlight: Promise<boolean> | null = null;
let refreshFailureUntil = 0;

function isAuthPath(path: string): boolean {
  const p = path.startsWith("/") ? path : `/${path}`;
  return AUTH_PATH_PREFIXES.some((prefix) => p === prefix || p.startsWith(`${prefix}/`));
}

/**
 * Lit le cookie `csrftoken` défini par Django (non-httpOnly).
 * Retourne null si le cookie n'est pas encore disponible (premier chargement).
 */
function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

async function refreshAccessToken(): Promise<boolean> {
  if (Date.now() < refreshFailureUntil) {
    return false;
  }
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(apiUrl("/auth/refresh"), {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        // Session absente/expiree : eviter de spammer /auth/refresh a chaque 401.
        refreshFailureUntil = Date.now() + 60_000;
      } else {
        refreshFailureUntil = 0;
      }
      return res.ok;
    } catch {
      refreshFailureUntil = Date.now() + 60_000;
      return false;
    }
  })();
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

export async function apiFetch<T = unknown>(path: string, options: RequestInit = {}, retryOn401 = true): Promise<T> {
  const url = apiUrl(path);
  const method = (options.method || "GET").toUpperCase();

  // Injecter le token CSRF pour les méthodes mutantes (défense en profondeur)
  const csrfHeaders: Record<string, string> = {};
  if (!CSRF_SAFE_METHODS.has(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      csrfHeaders["X-CSRFToken"] = csrfToken;
    }
  }

  const res = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...csrfHeaders,
      ...options.headers,
    },
  });

  if (res.ok && isAuthPath(path)) {
    // Login/refresh reussi : reautoriser les tentatives de refresh.
    refreshFailureUntil = 0;
  }

  if (res.status === 401 && retryOn401 && !isAuthPath(path)) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiFetch<T>(path, options, false);
    }
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }

  if (!res.ok) {
    let err: Record<string, unknown>;
    try {
      const parsed = (await res.json()) as unknown;
      if (typeof parsed === "object" && parsed !== null) {
        err = parsed as Record<string, unknown>;
      } else {
        err = { detail: String(parsed) };
      }
    } catch {
      err = { detail: res.statusText || `Erreur ${res.status}` };
    }

    // Gérer les erreurs de validation Django REST Framework
    if (typeof err === "object" && err !== null) {
      // Si c'est un objet de validation avec des champs
      const errorKeys = Object.keys(err);
      if (errorKeys.length > 0 && !("detail" in err) && !("message" in err)) {
        const firstKey = errorKeys[0];
        const firstError = err[firstKey];
        if (Array.isArray(firstError) && firstError.length > 0) {
          throw new Error(`${firstKey}: ${firstError[0]}`);
        } else if (typeof firstError === "string") {
          throw new Error(`${firstKey}: ${firstError}`);
        }
      }
    }

    const detail = typeof err.detail === "string" ? err.detail : undefined;
    const message = typeof err.message === "string" ? err.message : undefined;
    const error = typeof err.error === "string" ? err.error : undefined;
    throw new Error(detail || message || error || String(res.status));
  }
  return res.json() as Promise<T>;
}
