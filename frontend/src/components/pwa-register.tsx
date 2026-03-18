"use client";

import { useEffect } from "react";

/**
 * Enregistre le service worker PWA au montage.
 * Composant client léger — ne rend rien, inclus dans le root layout.
 */
export function PwaRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;

    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Silencieux — le SW est une amélioration optionnelle, pas critique
      });
    });
  }, []);

  return null;
}
