import { NextResponse } from "next/server";

/**
 * GET /api/healthz
 * Health check pour DigitalOcean App Platform.
 * DO envoie une requête GET sur ce chemin toutes les 30s pour vérifier
 * que le conteneur Next.js est vivant. Doit répondre 200 rapidement.
 *
 * Avec basePath="/konis2" (si défini), la route est accessible à :
 *   /konis2/api/healthz  (préfixé automatiquement par Next.js)
 * Sans basePath (architecture /api→Django, /→Next.js) :
 *   /api/healthz
 *   → Attention : DO route /api/* vers Django dans cette architecture.
 *   → Utiliser http_path: / dans app.yaml pour le health check frontend.
 */
export async function GET() {
  return NextResponse.json({ status: "ok" }, { status: 200 });
}
