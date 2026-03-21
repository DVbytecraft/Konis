"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { buildIdempotencyKey } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertCircle, CheckCircle2, RefreshCw, Package, ArrowRightLeft } from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface StockItem {
  id: number;
  produit: number;
  produit_nom: string;
  produit_code: string;
  produit_unite: string;
  poids_par_sac: string | null;
  lieu_nom: string;
  quantite: string;
  quantite_kg: string;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function BoutiqueStockPage() {
  const [stocks, setStocks] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Modal conversion
  const [convertTarget, setConvertTarget] = useState<StockItem | null>(null);
  const [nombreSacs, setNombreSacs] = useState("");
  const [converting, setConverting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const raw = await apiFetch<StockItem[] | { results?: StockItem[] }>("/boutique/stock/");
      setStocks(Array.isArray(raw) ? raw : (raw.results ?? []));
    } catch {
      setError("Impossible de charger le stock.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openConvert = (item: StockItem) => {
    setConvertTarget(item);
    setNombreSacs("");
    setSuccess(null);
    setError(null);
  };

  const closeConvert = () => {
    setConvertTarget(null);
    setNombreSacs("");
  };

  const handleConvert = async () => {
    if (!convertTarget) return;
    const n = parseInt(nombreSacs, 10);
    if (isNaN(n) || n <= 0) {
      setError("Nombre de sacs invalide.");
      return;
    }
    setConverting(true);
    setError(null);
    try {
      const res = await apiFetch<{ kg_generes: string; quantite_sacs: string; quantite_kg: string }>(
        `/boutique/stock/${convertTarget.produit}/convertir/`,
        {
          method: "POST",
          headers: { "Idempotency-Key": buildIdempotencyKey("conversion") },
          body: JSON.stringify({ nombre_sacs: n }),
        },
      );
      setSuccess(
        `${n} sac(s) converti(s) → ${res.kg_generes} kg générés. ` +
        `Stock restant : ${res.quantite_sacs} sacs + ${res.quantite_kg} kg.`,
      );
      closeConvert();
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Erreur lors de la conversion.";
      // Erreur STRICT_MODE : clé d'idempotency manquante (ne devrait pas arriver ici)
      if (msg.includes("Idempotency-Key")) {
        setError("Erreur technique : rechargez la page et réessayez.");
      } else {
        setError(msg);
      }
    } finally {
      setConverting(false);
    }
  };

  // Affichage quantite sacs + kg
  const afficherStock = (item: StockItem) => {
    const hasPds = item.poids_par_sac && parseFloat(item.poids_par_sac) > 0;
    const hasKg = parseFloat(item.quantite_kg) > 0;
    if (hasPds && hasKg) {
      return `${item.quantite} sacs + ${item.quantite_kg} kg`;
    }
    if (hasPds) {
      return `${item.quantite} sacs`;
    }
    return `${item.quantite} ${item.produit_unite}`;
  };

  // Peut-on convertir ? Oui si poids_par_sac défini et quantite > 0
  const peutConvertir = (item: StockItem) =>
    item.poids_par_sac !== null &&
    parseFloat(item.poids_par_sac) > 0 &&
    parseFloat(item.quantite) > 0;

  return (
    <div className="p-4 space-y-4 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Package className="h-6 w-6" /> Stock boutique
        </h1>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} />
          Actualiser
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3">
          <AlertCircle className="h-4 w-4 shrink-0" /> {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded p-3">
          <CheckCircle2 className="h-4 w-4 shrink-0" /> {success}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Produits en stock</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <p className="text-sm text-muted-foreground p-4">Chargement…</p>
          ) : stocks.length === 0 ? (
            <p className="text-sm text-muted-foreground p-4">Aucun stock enregistré.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium">Produit</th>
                    <th className="text-left px-4 py-2 font-medium">Code</th>
                    <th className="text-right px-4 py-2 font-medium">Quantité</th>
                    <th className="text-right px-4 py-2 font-medium">Poids/sac</th>
                    <th className="px-4 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {stocks.map((item) => (
                    <tr key={item.id} className="border-b last:border-0 hover:bg-muted/20">
                      <td className="px-4 py-3 font-medium">{item.produit_nom}</td>
                      <td className="px-4 py-3 text-muted-foreground">{item.produit_code || "—"}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{afficherStock(item)}</td>
                      <td className="px-4 py-3 text-right text-muted-foreground tabular-nums">
                        {item.poids_par_sac ? `${item.poids_par_sac} kg/sac` : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {peutConvertir(item) && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => openConvert(item)}
                            className="gap-1"
                          >
                            <ArrowRightLeft className="h-3 w-3" />
                            Convertir sacs → kg
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Modal conversion ─────────────────────────────────────────────── */}
      {convertTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-sm mx-4 p-6 space-y-4">
            <h2 className="text-lg font-semibold">
              Convertir sacs → kg
            </h2>
            <p className="text-sm text-muted-foreground">
              <span className="font-medium">{convertTarget.produit_nom}</span> —{" "}
              {convertTarget.quantite} sac(s) disponible(s)
              {convertTarget.poids_par_sac && (
                <> · {convertTarget.poids_par_sac} kg/sac</>
              )}
            </p>

            {convertTarget.poids_par_sac && (
              <p className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded p-2">
                {nombreSacs && !isNaN(parseInt(nombreSacs, 10)) && parseInt(nombreSacs, 10) > 0
                  ? `→ ${(parseInt(nombreSacs, 10) * parseFloat(convertTarget.poids_par_sac)).toFixed(3)} kg générés`
                  : "Entrez un nombre de sacs pour voir le calcul."}
              </p>
            )}

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium">
                  Nombre de sacs à convertir
                  <span className="text-muted-foreground font-normal ml-1">(max {parseInt(convertTarget.quantite)})</span>
                </label>
                <button
                  type="button"
                  onClick={() => setNombreSacs(convertTarget.quantite)}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Tout
                </button>
              </div>
              <Input
                type="number"
                min={1}
                max={parseInt(convertTarget.quantite)}
                value={nombreSacs}
                onChange={(e) => setNombreSacs(e.target.value)}
                placeholder={`1 – ${parseInt(convertTarget.quantite)}`}
                autoFocus
              />
            </div>

            <div className="flex gap-2 justify-end pt-1">
              <Button variant="outline" onClick={closeConvert} disabled={converting}>
                Annuler
              </Button>
              <Button onClick={handleConvert} disabled={converting || !nombreSacs}>
                {converting ? "Conversion…" : "Confirmer"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
