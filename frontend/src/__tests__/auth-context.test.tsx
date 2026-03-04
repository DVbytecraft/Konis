/**
 * Tests du flux bootstrap AuthProvider — Brigade FC COPS, dossier AUTH-001.
 *
 * Stratégie :
 * - On mock globalThis.fetch pour simuler les réponses réseau.
 * - On mock @/lib/api pour isoler apiUrl (retourne "/api<path>").
 * - On render un composant consommateur et on observe l'état via le DOM.
 * - On utilise waitFor pour laisser les effets async se résoudre.
 *
 * Scénarios couverts :
 *   1. /me 200 direct → auth réussie
 *   2. /me 401 → refresh 200 → /me 200 → auth réussie (refresh silencieux)
 *   3. /me 401 → refresh 401 → non authentifié
 *   4. /me 401 → refresh 200 → /me 401 → non authentifié (pas de second refresh)
 *   5. /me 500 → non authentifié (erreur serveur)
 *   6. fetch throw (erreur réseau) → non authentifié
 *   7. fetch AbortError (timeout) → non authentifié
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { AuthProvider, useAuth } from "@/contexts/auth-context";

// ── Mocks ─────────────────────────────────────────────────────────────────────

// Mock apiFetch (utilisé par login/logout, pas par le bootstrap)
vi.mock("@/lib/api", () => ({
  apiUrl: (path: string) => `/api${path}`,
  apiFetch: vi.fn(),
}));

// Données utilisateur valides (conformes au schéma Zod)
const VALID_USER = {
  id: 1,
  username: "testuser",
  first_name: "Test",
  last_name: "User",
  role: "admin",
  role_display: "Administrateur",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Construit une Response-like pour le mock fetch */
function makeResponse(status: number, body?: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body ?? {}),
  } as unknown as Response;
}

/**
 * Composant consommateur minimal.
 * Affiche l'état du contexte dans le DOM pour les assertions.
 */
function TestConsumer() {
  const { user, loading, isAuthenticated } = useAuth();
  if (loading) return <div data-testid="state">loading</div>;
  if (!user || !isAuthenticated) return <div data-testid="state">unauthenticated</div>;
  return <div data-testid="state">authenticated:{user.username}</div>;
}

function renderAuth() {
  return render(
    <AuthProvider>
      <TestConsumer />
    </AuthProvider>
  );
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.restoreAllMocks();
  // Réinitialiser window.location.pathname (jsdom par défaut = "/")
  Object.defineProperty(window, "location", {
    value: { pathname: "/" },
    writable: true,
  });
});

// ── Scénarios ─────────────────────────────────────────────────────────────────

describe("AuthProvider — flux bootstrap", () => {

  /**
   * Scénario 1 : /me répond 200 directement.
   * Cas nominal — token valide, bootstrap réussi au premier appel.
   */
  it("sc1: /me 200 → authentifie l'utilisateur directement", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      makeResponse(200, VALID_USER)
    );

    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe(
        "authenticated:testuser"
      )
    );
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/me",
      expect.objectContaining({ method: "GET" })
    );
  });

  /**
   * Scénario 2 : /me 401 → refresh 200 → /me 200.
   * Cas normal en prod : l'access_token de 10 min a expiré,
   * mais le refresh_token de 7 jours est encore valide.
   */
  it("sc2: /me 401 → refresh 200 → /me 200 → authentifie silencieusement", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(makeResponse(401))          // /me → 401
      .mockResolvedValueOnce(makeResponse(200, {}))       // /refresh → 200
      .mockResolvedValueOnce(makeResponse(200, VALID_USER)); // /me retry → 200

    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe(
        "authenticated:testuser"
      )
    );
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    // Vérifier l'ordre des appels
    expect(fetchSpy.mock.calls[0][0]).toContain("/auth/me");
    expect(fetchSpy.mock.calls[1][0]).toContain("/auth/refresh");
    expect(fetchSpy.mock.calls[2][0]).toContain("/auth/me");
  });

  /**
   * Scénario 3 : /me 401 → refresh 401.
   * Session vraiment expirée (refresh_token périmé ou révoqué).
   * → Non authentifié, prêt pour redirection login par le layout.
   */
  it("sc3: /me 401 → refresh 401 → non authentifié", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(makeResponse(401)) // /me → 401
      .mockResolvedValueOnce(makeResponse(401)); // /refresh → 401

    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("unauthenticated")
    );
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  /**
   * Scénario 4 : /me 401 → refresh 200 → /me 401 (cas rare).
   * Token révoqué ou désynchronisation d'horloge.
   * CRITIQUE : vérifier qu'on NE RELANCE PAS un second refresh (anti-boucle).
   */
  it("sc4: /me 401 → refresh 200 → /me 401 → non authentifié SANS second refresh", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(makeResponse(401))  // /me → 401
      .mockResolvedValueOnce(makeResponse(200))  // /refresh → 200
      .mockResolvedValueOnce(makeResponse(401)); // /me retry → 401

    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("unauthenticated")
    );

    // Exactement 3 appels — pas de 4ème appel (second refresh interdit)
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    const urls = fetchSpy.mock.calls.map((call) => call[0] as string);
    const refreshCount = urls.filter((u) => u.includes("/auth/refresh")).length;
    expect(refreshCount).toBe(1); // Un seul refresh, jamais deux
  });

  /**
   * Scénario 5 : /me retourne 500 (erreur serveur).
   * Pas un problème de token — serveur en erreur.
   * → Non authentifié sans tenter de refresh.
   */
  it("sc5: /me 500 → non authentifié sans tenter de refresh", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(makeResponse(500));

    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("unauthenticated")
    );
    // Un seul appel — pas de refresh tenté sur une 5xx
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  /**
   * Scénario 6 : fetch lance une exception (coupure réseau, DNS fail, etc.)
   * → Non authentifié, erreur capturée proprement.
   */
  it("sc6: erreur réseau (fetch throw) → non authentifié", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(
      new Error("Network error: connexion refusée")
    );

    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("unauthenticated")
    );
  });

  /**
   * Scénario 7 : timeout AbortController (serveur trop lent).
   * → Non authentifié, log explicite, aucune requête fantôme.
   */
  it("sc7: timeout (AbortError) → non authentifié", async () => {
    const abortError = Object.assign(new Error("The user aborted a request."), {
      name: "AbortError",
    });
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(abortError);

    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("unauthenticated")
    );
  });

  /**
   * Scénario bonus : données utilisateur corrompues (fail Zod).
   * Le backend renvoie un objet sans "role" → safeParse échoue → non authentifié.
   */
  it("sc8: /me 200 avec données invalides (Zod fail) → non authentifié", async () => {
    const corruptUser = { id: 1, username: "bad" }; // role, role_display manquants
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      makeResponse(200, corruptUser)
    );

    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("unauthenticated")
    );
  });

});
