/**
 * KONIS Service Worker — cache-first statique, network-first dynamique.
 * Stratégie minimale : pas de cache sur /api/* ni sur les routes auth.
 */

const CACHE_NAME = "konis-v1";

// Assets statiques à précacher au install
const PRECACHE_URLS = [
  "/",
  "/login",
  "/offline",
];

// Patterns à NE JAMAIS cacher (données live + auth)
const NO_CACHE_PATTERNS = [
  /^\/api\//,
  /^\/auth\//,
  /\/_next\/webpack-hmr/,
];

function shouldSkipCache(url) {
  const path = new URL(url).pathname;
  return NO_CACHE_PATTERNS.some((p) => p.test(path));
}

// ── Install : précacher les ressources critiques ──────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS).catch(() => null))
      .then(() => self.skipWaiting())
  );
});

// ── Activate : supprimer les anciens caches ───────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

// ── Fetch : network-first pour l'API, cache-first pour les assets ─────────────
self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Ignorer les requêtes non-GET et les patterns exclus
  if (request.method !== "GET" || shouldSkipCache(request.url)) {
    return;
  }

  // Assets Next.js (_next/static) : cache-first longue durée
  if (request.url.includes("/_next/static/")) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((res) => {
            if (res.ok) {
              const clone = res.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
            }
            return res;
          })
      )
    );
    return;
  }

  // Pages de l'app : network-first, fallback cache, puis /offline
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return res;
      })
      .catch(() =>
        caches
          .match(request)
          .then((cached) => cached || caches.match("/offline"))
      )
  );
});
