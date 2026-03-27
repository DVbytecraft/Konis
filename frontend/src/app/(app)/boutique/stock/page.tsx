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

  // Modal sac → kg
  const [convertTarget, setConvertTarget] = useState<StockItem | null>(null);
  const [nombreSacs, setNombreSacs] = useState("");
  const [poidsSaisi, setPoidsSaisi] = useState("");
  const [converting, setConverting] = useState(false);

  // Modal kg → sac
  const [kgSacTarget, setKgSacTarget] = useState<StockItem | null>(null);
  const [kgSacNombreSacs, setKgSacNombreSacs] = useState("");
  const [kgSacPoids, setKgSacPoids] = useState("");
  const [convertingKgSac, setConvertingKgSac] = useState(false);

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
    setPoidsSaisi("");
    setSuccess(null);
    setError(null);
  };

  const closeConvert = () => {
    setConvertTarget(null);
    setNombreSacs("");
    setPoidsSaisi("");
  };

  const openKgSac = (item: StockItem) => {
    setKgSacTarget(item);
    setKgSacNombreSacs("");
    setKgSacPoids(item.poids_par_sac ?? "");
    setSuccess(null);
    setError(null);
  };

  const closeKgSac = () => {
    setKgSacTarget(null);
    setKgSacNombreSacs("");
    setKgSacPoids("");
  };

  const handleKgToSac = async () => {
    if (!kgSacTarget) return;
    const n = parseInt(kgSacNombreSacs, 10);
    if (isNaN(n) || n <= 0) { setError("Nombre de sacs invalide."); return; }
    const pds = parseFloat(kgSacPoids);
    if (!kgSacPoids || isNaN(pds) || pds <= 0) { setError("Poids par sac obligatoire."); return; }
    const kgNecessaires = n * pds;
    const kgDispo = parseFloat(kgSacTarget.quantite_kg);
    if (kgNecessaires > kgDispo) {
      setError(`Stock insuffisant : ${kgDispo.toFixed(3)} kg disponible(s), conversion requiert ${kgNecessaires.toFixed(3)} kg.`);
      return;
    }
    setConvertingKgSac(true);
    setError(null);
    try {
      const res = await apiFetch<{ sacs_crees: number; kg_debites: string; quantite_sacs: string; quantite_kg: string }>(
        `/boutique/stock/${kgSacTarget.produit}/convertir-kg-en-sac/`,
        {
          method: "POST",
          headers: { "Idempotency-Key": buildIdempotencyKey("conversion-kg-sac") },
          body: JSON.stringify({ nombre_sacs: n, poids_par_sac: kgSacPoids }),
        },
      );
      setSuccess(
        `${res.sacs_crees} sac(s) créé(s) — ${res.kg_debites} kg débités. ` +
        `Stock restant : ${res.quantite_sacs} sacs + ${res.quantite_kg} kg.`,
      );
      closeKgSac();
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur lors de la conversion.");
    } finally {
      setConvertingKgSac(false);
    }
  };

  const handleConvert = async () => {
    if (!convertTarget) return;
    const n = parseInt(nombreSacs, 10);
    if (isNaN(n) || n <= 0) {
      setError("Nombre de sacs invalide.");
      return;
    }
    const needsPoids = !convertTarget.poids_par_sac || parseFloat(convertTarget.poids_par_sac) === 0;
    if (needsPoids && (!poidsSaisi || isNaN(parseFloat(poidsSaisi)) || parseFloat(poidsSaisi) <= 0)) {
      setError("Veuillez saisir le poids par sac en kg.");
      return;
    }
    setConverting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { nombre_sacs: n };
      if (needsPoids) body.poids_par_sac = parseFloat(poidsSaisi);
      const res = await apiFetch<{ kg_generes: string; quantite_sacs: string; quantite_kg: string }>(
        `/boutique/stock/${convertTarget.produit}/convertir/`,
        {
          method: "POST",
          headers: { "Idempotency-Key": buildIdempotencyKey("conversion") },
          body: JSON.stringify(body),
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
    const sacs = parseFloat(item.quantite);
    const kg = parseFloat(item.quantite_kg);
    if (sacs > 0 && kg > 0) return `${item.quantite} sacs + ${kg.toFixed(3)} kg`;
    if (sacs > 0) return `${item.quantite} sacs`;
    if (kg > 0) return `${kg.toFixed(3)} kg`;
    return `0 ${item.produit_unite}`;
  };

  // sac → kg : oui si quantite (sacs) > 0
  const peutConvertir = (item: StockItem) => parseFloat(item.quantite) > 0;
  // kg → sac : oui si quantite_kg > 0
  const peutConvertirKgEnSac = (item: StockItem) => parseFloat(item.quantite_kg) > 0;

  return (
    <div className="p-4 space-y-4 max-w-4xl mx-auto">
      <div className="flex items-center justify-between flex-wrap gap-2">
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
                        <div className="flex gap-1 justify-end flex-wrap">
                          {peutConvertir(item) && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openConvert(item)}
                              className="gap-1"
                            >
                              <ArrowRightLeft className="h-3 w-3" />
                              Sacs → kg
                            </Button>
                          )}
                          {peutConvertirKgEnSac(item) && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openKgSac(item)}
                              className="gap-1"
                            >
                              <ArrowRightLeft className="h-3 w-3" />
                              kg → Sacs
                            </Button>
                          )}
                        </div>
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
      {/* ── Modal kg → sacs ──────────────────────────────────────────────── */}
      {kgSacTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-sm mx-4 p-6 space-y-4">
            <h2 className="text-lg font-semibold">Convertir kg → sacs</h2>
            <p className="text-sm text-muted-foreground">
              <span className="font-medium">{kgSacTarget.produit_nom}</span> —{" "}
              {parseFloat(kgSacTarget.quantite_kg).toFixed(3)} kg disponibles
            </p>

            {/* poids_par_sac — obligatoire */}
            <div className="space-y-1">
              <label className="text-sm font-medium">
                Poids par sac (kg) <span className="text-red-500">*</span>
              </label>
              <Input
                type="number"
                min={0.001}
                step={0.001}
                value={kgSacPoids}
                onChange={(e) => setKgSacPoids(e.target.value)}
                placeholder="ex : 25.000"
                autoFocus={!kgSacTarget.poids_par_sac}
              />
              {kgSacTarget.poids_par_sac && parseFloat(kgSacTarget.poids_par_sac) > 0 && kgSacPoids !== kgSacTarget.poids_par_sac && (
                <p className="text-xs text-amber-600">
                  ⚠ Le produit est défini à {kgSacTarget.poids_par_sac} kg/sac. Toute valeur différente sera rejetée par le serveur.
                </p>
              )}
            </div>

            {/* nombre de sacs */}
            <div className="space-y-1">
              <label className="text-sm font-medium">Nombre de sacs à créer</label>
              <Input
                type="number"
                min={1}
                value={kgSacNombreSacs}
                onChange={(e) => setKgSacNombreSacs(e.target.value)}
                placeholder="ex : 4"
                autoFocus={!!kgSacTarget.poids_par_sac}
              />
            </div>

            {/* aperçu calcul */}
            {(() => {
              const n = parseInt(kgSacNombreSacs, 10);
              const pds = parseFloat(kgSacPoids);
              const kgDispo = parseFloat(kgSacTarget.quantite_kg);
              if (n > 0 && pds > 0) {
                const kgNec = n * pds;
                const ok = kgNec <= kgDispo;
                return (
                  <p className={`text-xs rounded p-2 border ${ok ? "text-blue-700 bg-blue-50 border-blue-200" : "text-red-700 bg-red-50 border-red-200"}`}>
                    {ok
                      ? `→ ${kgNec.toFixed(3)} kg débités · ${(kgDispo - kgNec).toFixed(3)} kg resteront`
                      : `✗ Insuffisant : ${kgNec.toFixed(3)} kg requis, ${kgDispo.toFixed(3)} kg disponibles`}
                  </p>
                );
              }
              return <p className="text-xs text-muted-foreground bg-muted/30 rounded p-2">Renseignez le nombre de sacs et le poids pour voir le calcul.</p>;
            })()}

            <div className="flex gap-2 justify-end pt-1">
              <Button variant="outline" onClick={closeKgSac} disabled={convertingKgSac}>Annuler</Button>
              <Button onClick={handleKgToSac} disabled={convertingKgSac || !kgSacNombreSacs || !kgSacPoids}>
                {convertingKgSac ? "Conversion…" : "Confirmer"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal sacs → kg ───────────────────────────────────────────────── */}
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

            {/* Champ poids si non prédéfini */}
            {(!convertTarget.poids_par_sac || parseFloat(convertTarget.poids_par_sac) === 0) && (
              <div className="space-y-1">
                <label className="text-sm font-medium">Poids par sac (kg) <span className="text-red-500">*</span></label>
                <Input
                  type="number"
                  min={0.001}
                  step={0.001}
                  value={poidsSaisi}
                  onChange={(e) => setPoidsSaisi(e.target.value)}
                  placeholder="ex : 50.000"
                  autoFocus
                />
              </div>
            )}

            {/* Aperçu kg */}
            {(() => {
              const pds = convertTarget.poids_par_sac ? parseFloat(convertTarget.poids_par_sac) : parseFloat(poidsSaisi);
              const n = parseInt(nombreSacs, 10);
              return pds > 0 && n > 0 ? (
                <p className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded p-2">
                  → {(n * pds).toFixed(3)} kg générés
                </p>
              ) : (
                <p className="text-xs text-muted-foreground bg-muted/30 rounded p-2">
                  Renseignez le nombre de sacs{(!convertTarget.poids_par_sac || parseFloat(convertTarget.poids_par_sac) === 0) ? " et le poids" : ""} pour voir le calcul.
                </p>
              );
            })()}

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
                autoFocus={!(!convertTarget.poids_par_sac || parseFloat(convertTarget.poids_par_sac) === 0)}
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
