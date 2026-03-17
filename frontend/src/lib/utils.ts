import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

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
