/** @type {import('next').NextConfig} */
const nextConfig = {
  // ── Préfixe de base (optionnel) ───────────────────────────────────────────
  // Par défaut vide → Next.js sert depuis "/".
  // Si NEXT_PUBLIC_BASE_PATH est défini (ex: "/konis2"), Next.js préfixe toutes
  // ses routes. Doit correspondre au préfixe d'ingress DigitalOcean.
  // Architecture cible DO : / → frontend, /api/ → backend → NEXT_PUBLIC_BASE_PATH = ""
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",

  // ── Headers de sécurité et de cache ──────────────────────────────────────
  // Appliqués sur toutes les routes Next.js (pages, layouts, assets).
  // Note : les headers Cache-Control sur les routes /api/* sont déjà gérés
  // côté Django par SecurityHeadersMiddleware (no-store). Ces headers
  // couvrent le frontend lui-même (pages HTML, assets Next.js).
  async headers() {
    return [
      {
        // Pages de l'application : pas de mise en cache HTML
        // → assure que le navigateur recharge toujours la page après login/logout/reset
        source: "/((?!_next/static|_next/image|favicon.ico).*)",
        headers: [
          // Anti-clickjacking
          { key: "X-Frame-Options", value: "DENY" },
          // Anti-MIME-sniffing
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Réduction des fuites de Referer
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Désactiver la géolocalisation, caméra, micro
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          // HSTS : force HTTPS pendant 1 an (inclut sous-domaines).
          // N'a d'effet qu'en production HTTPS — ignoré en HTTP local.
          //
          // ⚠️  FLAG "preload" DÉLIBÉRÉMENT ABSENT :
          // Le preload soumet le domaine à la liste HSTS des navigateurs (Chrome, Firefox…).
          // C'est quasi-irréversible (délai de retrait : 6–12 mois) et bloque tout accès HTTP
          // au domaine et à TOUS ses sous-domaines, pour toujours.
          // À n'activer qu'après validation de l'infrastructure complète et décision explicite.
          // Ref : https://hstspreload.org/
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          // CSP : restreint les sources autorisées pour limiter l'impact d'une XSS.
          // unsafe-inline + unsafe-eval requis par Next.js (scripts hydration) et Tailwind (styles).
          // connect-src 'self' : interdit les appels réseau vers des domaines tiers
          // → même si du code malveillant s'exécutait, il ne pourrait pas exfiltrer de données.
          { key: "Content-Security-Policy", value: [
            "default-src 'self'",
            "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self'",
            "connect-src 'self'",
            "frame-src 'self' blob: https://*.ondigitalocean.app",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
          ].join("; ") },
          // Pages HTML : revalider à chaque navigation (pas de stale)
          // public + must-revalidate : le navigateur vérifie toujours la fraîcheur
          { key: "Cache-Control", value: "no-cache, must-revalidate" },
        ],
      },
      {
        // Assets statiques Next.js : peuvent être cachés longtemps (hash dans le nom)
        source: "/_next/static/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
    ];
  },
};

export default nextConfig;
