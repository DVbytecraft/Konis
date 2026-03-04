"use client";

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { apiFetch, apiUrl } from "@/lib/api";
import { userSchema, type User } from "@/types/user";

// Re-export pour compatibilité ascendante (imports existants depuis @/contexts/auth-context)
export type { User };

// ── Utilitaires module-level (purs, sans closure React) ───────────────────────

/**
 * Fetch avec timeout via AbortController.
 * Annule vraiment la requête réseau — pas de requête fantôme en arrière-plan.
 * Lance une Error avec name="AbortError" si le timeout est dépassé.
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = 10_000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(`Timeout — le serveur ne répond pas après ${timeoutMs / 1000}s`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Parse et valide les données utilisateur via le schéma Zod.
 * Lève une erreur explicite si la structure est invalide — interdit les casts silencieux.
 */
function parseUserData(data: unknown): User {
  const result = userSchema.safeParse(data);
  if (!result.success) {
    console.error(
      "[Auth] Données utilisateur invalides reçues du serveur",
      result.error.flatten()
    );
    throw new Error(
      "Réponse serveur invalide : structure utilisateur incorrecte. L'API a peut-être changé."
    );
  }
  return result.data;
}

// ── Types du contexte ─────────────────────────────────────────────────────────

interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // useRef (vs module-level) : se réinitialise proprement entre les mounts.
  // Évite les "sessions fantômes" lors des hot reloads en dev.
  // En React Strict Mode, le double-mount provoque deux fetches (inoffensif :
  // les deux réussissent et setUser est idempotent).
  const bootstrapDoneRef = useRef(false);
  const refreshAttempted = useRef(false);
  const refreshInFlight = useRef<Promise<void> | null>(null);

  const normalizeUser = useCallback((raw: User): User => {
    // Normalise le rôle "usine" → "factory" pour l'uniformité côté frontend.
    if (raw.role === "usine" && raw.role_normalized === "factory") {
      return { ...raw, role: "factory" };
    }
    return raw;
  }, []);

  const isAuthScreen = useCallback((): boolean => {
    if (typeof window === "undefined") return false;
    const path = window.location.pathname.toLowerCase();
    return path === "/login" || path.startsWith("/login/");
  }, []);

  /** Réinitialise l'état auth vers "non authentifié" et verrouille les tentatives futures. */
  const failAuth = useCallback(() => {
    setUser(null);
    setIsAuthenticated(false);
    refreshAttempted.current = true;
  }, []);

  const refreshUser = useCallback(async () => {
    if (refreshInFlight.current) {
      await refreshInFlight.current;
      return;
    }

    const run = async () => {
      if (refreshAttempted.current) return;

      try {
        if (isAuthScreen()) {
          failAuth();
          return;
        }

        // ── Tentative 1 : appel /auth/me ──────────────────────────────────
        // Raw fetch intentionnel : apiFetch déclencherait un auto-refresh
        // créant une boucle infinie avec le flux de refresh ci-dessous.
        const meRes = await fetchWithTimeout(apiUrl("/auth/me"), {
          method: "GET",
          credentials: "include",
        });

        if (meRes.ok) {
          const data = await meRes.json();
          setUser(normalizeUser(parseUserData(data)));
          setIsAuthenticated(true);
          refreshAttempted.current = false;
          return;
        }

        if (meRes.status !== 401) {
          // 5xx, 403, etc. — erreur serveur, pas de token manquant
          console.error(`[Auth] /auth/me a retourné ${meRes.status} — abandonne le bootstrap`);
          failAuth();
          return;
        }

        // ── 401 sur /me : tenter un refresh silencieux ────────────────────
        // Le refresh_token dure 7 jours. L'utilisateur ne doit pas être
        // redirigé vers /login simplement parce que les 10 min d'access_token sont écoulées.
        const refreshRes = await fetchWithTimeout(apiUrl("/auth/refresh"), {
          method: "POST",
          credentials: "include",
        });

        if (!refreshRes.ok) {
          // Le refresh a aussi échoué : session vraiment expirée → login.
          failAuth();
          return;
        }

        // ── Refresh réussi : relancer /me UNE SEULE FOIS ──────────────────
        // On ne relance PAS un second refresh si ce /me retourne 401.
        // Raison : éviter les boucles infinies. Si le token est révoqué côté
        // serveur immédiatement après avoir été émis (race condition, horloge
        // désynchronisée, révocation manuelle), un second refresh ne résoudrait
        // rien et aggraverait la situation (spam de tokens).
        const meRes2 = await fetchWithTimeout(apiUrl("/auth/me"), {
          method: "GET",
          credentials: "include",
        });

        if (meRes2.ok) {
          const data = await meRes2.json();
          setUser(normalizeUser(parseUserData(data)));
          setIsAuthenticated(true);
          refreshAttempted.current = false;
          return;
        }

        if (meRes2.status === 401) {
          // Cas spécifique : session expirée immédiatement après un refresh réussi.
          // Cause probable : révocation de token, désynchronisation d'horloge,
          // ou rotation de clé secrète côté serveur.
          console.error(
            "[Auth] Session expirée immédiatement après refresh — token révoqué ou horloge désynchronisée. Redirection vers login."
          );
        } else {
          console.error(
            `[Auth] Second appel /auth/me a retourné ${meRes2.status} après refresh réussi`
          );
        }
        failAuth();
      } catch (error) {
        if (error instanceof Error && error.message.startsWith("Timeout")) {
          console.error("[Auth] Bootstrap annulé — serveur trop lent :", error.message);
        } else {
          console.error("[Auth] Erreur réseau lors du bootstrap :", error);
        }
        failAuth();
      }
    };

    refreshInFlight.current = run();
    try {
      await refreshInFlight.current;
    } finally {
      refreshInFlight.current = null;
    }
  }, [isAuthScreen, normalizeUser, failAuth]);

  useEffect(() => {
    if (bootstrapDoneRef.current) {
      setLoading(false);
      return;
    }
    bootstrapDoneRef.current = true;
    refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  const login = async (username: string, password: string) => {
    const data = await apiFetch<{ user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setUser(normalizeUser(data.user));
    setIsAuthenticated(true);
    refreshAttempted.current = false;
  };

  const logout = async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // Ignore logout errors: local auth state is always cleared in finally.
    } finally {
      setUser(null);
      setIsAuthenticated(false);
      refreshAttempted.current = true;
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, isAuthenticated, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
