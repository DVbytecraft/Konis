import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Génère une clé d'idempotency unique pour les requêtes critiques (ventes, conversions).
 * Utilise crypto.randomUUID() si disponible (navigateurs modernes), sinon fallback manuel.
 *
 * Format : {scope}-{uuid}
 * Exemples : "vente-550e8400-e29b-41d4-a716-446655440000"
 *            "conversion-3f6c1234-..."
 */
export function buildIdempotencyKey(scope: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${scope}-${crypto.randomUUID()}`;
  }
  // Fallback pour environnements sans crypto.randomUUID (rare en 2026)
  const rand = () => Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, "0");
  return `${scope}-${rand()}-${rand()}-${rand()}-${rand()}`;
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Convertit une valeur quelconque (string, number, null, undefined) en nombre
 * puis applique toFixed(decimals). Protège contre TypeError: x.toFixed is not a function
 * causée par les champs Decimal de DRF sérialisés en strings.
 */
export function fmt(value: unknown, decimals = 2): string {
  const num = typeof value === "number" ? value : Number(value ?? 0);
  if (!Number.isFinite(num)) return (0).toFixed(decimals);
  return num.toFixed(decimals);
}
