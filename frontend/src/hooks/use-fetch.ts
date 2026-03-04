"use client";

/**
 * Hook générique de récupération de données via apiFetch.
 * Gère automatiquement les états loading / error / data et expose refetch()/cancel().
 *
 * Usage :
 *   const { data, loading, error, refetch, cancel } = useFetch<Ticket[]>("/boutique/ventes/");
 *
 * Passe `null` comme url pour désactiver le fetch (ex: chargement conditionnel).
 */

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

export interface UseFetchResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  cancel: () => void;
}

export function useFetch<T>(url: string | null): UseFetchResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(url));
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [controller, setController] = useState<AbortController | null>(null);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  const cancel = useCallback(() => {
    controller?.abort();
    setController(null);
    setLoading(false);
  }, [controller]);

  useEffect(() => {
    if (!url) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    const abortController = new AbortController();
    setController(abortController);
    setLoading(true);
    setError(null);

    apiFetch<T>(url, { signal: abortController.signal })
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (err instanceof DOMException && err.name === "AbortError") {
            setLoading(false);
            return;
          }
          setError(err instanceof Error ? err.message : "Erreur inconnue");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      abortController.abort();
      setController(null);
    };
  }, [url, tick]);

  return { data, loading, error, refetch, cancel };
}
