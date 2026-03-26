"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface TransfertRow {
  id: number;
  from_lieu_nom: string;
  to_lieu_nom: string;
  date: string;
  mouvements: { produit_nom: string; quantite: string }[];
}

interface ProduitOption {
  produit_id: number;
  produit_nom: string;
  produit_code: string;
  unite: string;
  quantite: string;
  quantite_kg: string;
  poids_par_sac: string | null;
}

interface LieuOption {
  id: number;
  nom: string;
  type_lieu: string;
}

interface LigneForme {
  produit_id: string;
  quantite: string;
  unite: string;
}

type ApiList<T> = T[] | { results?: T[] };
function toList<T>(r: ApiList<T>): T[] {
  if (Array.isArray(r)) return r;
  return r.results ?? [];
}

export default function MpslTransfertsPage() {
  const [tab, setTab] = useState<"creer" | "historique">("creer");

  const [produits, setProduits] = useState<ProduitOption[]>([]);
  const [destinations, setDestinations] = useState<LieuOption[]>([]);
  const [rows, setRows] = useState<TransfertRow[]>([]);

  const [toLieu, setToLieu] = useState("");
  const [lignes, setLignes] = useState<LigneForme[]>([{ produit_id: "", quantite: "", unite: "sacs" }]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const [stockData, usinesData, magasinsData, transfertsData] = await Promise.all([
      apiFetch("/mpsl/stock/"),
      apiFetch("/locations/by-type/?type=factory"),
      apiFetch("/locations/by-type/?type=shop"),
      apiFetch("/mpsl/transferts/"),
    ]);
    setProduits(toList(stockData as ApiList<ProduitOption>));
    const usines = toList(usinesData as ApiList<LieuOption>).map((l) => ({ ...l, type_lieu: "usine" }));
    const magasins = toList(magasinsData as ApiList<LieuOption>).map((l) => ({ ...l, type_lieu: "magasin" }));
    setDestinations([...usines, ...magasins]);
    setRows(toList(transfertsData as ApiList<TransfertRow>));
  };

  useEffect(() => { load().catch(() => {}); }, []);

  const addLigne = () => setLignes((l) => [...l, { produit_id: "", quantite: "", unite: "sacs" }]);
  const removeLigne = (i: number) => setLignes((l) => l.filter((_, idx) => idx !== i));
  const updateLigne = (i: number, field: keyof LigneForme, value: string) => {
    setLignes((l) => l.map((line, idx) => idx === i ? { ...line, [field]: value } : line));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (!toLieu) { setErr("Sélectionne la destination."); return; }
    const lignesValides = lignes.filter((l) => l.produit_id && Number(l.quantite) > 0);
    if (lignesValides.length === 0) { setErr("Au moins une ligne de produit requise."); return; }

    setLoading(true);
    try {
      await apiFetch("/mpsl/transferts/", {
        method: "POST",
        body: JSON.stringify({
          to_lieu: Number(toLieu),
          lignes: lignesValides.map((l) => ({
            produit_id: Number(l.produit_id),
            quantite: l.quantite,
            unite: l.unite,
          })),
        }),
      });
      setToLieu("");
      setLignes([{ produit_id: "", quantite: "", unite: "sacs" }]);
      setTab("historique");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur lors du transfert.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Transferts MPSL</h1>
        <p className="text-sm text-muted-foreground">
          Envoyer des produits du dépôt vers une usine ou un magasin.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b scrollbar-hidden overflow-x-auto">
        {(["creer", "historique"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap",
              tab === t
                ? "border-blue-500 text-blue-600 dark:text-blue-400"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {t === "creer" ? "Nouveau transfert" : "Historique"}
          </button>
        ))}
      </div>

      {/* Créer un transfert */}
      {tab === "creer" && (
        <form onSubmit={submit} className="space-y-4">
          <div className="flex flex-col gap-1 w-full sm:max-w-sm">
            <label className="text-xs font-medium text-muted-foreground">Destination (usine ou magasin)</label>
            <select
              className="h-10 rounded-md border border-input bg-background px-2 text-sm"
              value={toLieu}
              onChange={(e) => setToLieu(e.target.value)}
            >
              <option value="">Sélectionner...</option>
              {destinations.filter((d) => d.type_lieu === "usine").length > 0 && (
                <optgroup label="Usines">
                  {destinations.filter((d) => d.type_lieu === "usine").map((d) => (
                    <option key={d.id} value={d.id}>{d.nom}</option>
                  ))}
                </optgroup>
              )}
              {destinations.filter((d) => d.type_lieu === "magasin").length > 0 && (
                <optgroup label="Magasins">
                  {destinations.filter((d) => d.type_lieu === "magasin").map((d) => (
                    <option key={d.id} value={d.id}>{d.nom}</option>
                  ))}
                </optgroup>
              )}
            </select>
          </div>

          {/* Lignes de produits */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Produits à transférer</label>
              <button
                type="button"
                onClick={addLigne}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
              >
                + Ajouter une ligne
              </button>
            </div>

            {produits.length === 0 && (
              <p className="text-xs text-amber-700 dark:text-amber-400">
                Aucun produit en stock au dépôt MPSL.
              </p>
            )}

            <div className="space-y-2">
              {lignes.map((ligne, i) => {
                const stockItem = produits.find((p) => String(p.produit_id) === ligne.produit_id);
                const hasPds = stockItem?.poids_par_sac && parseFloat(stockItem.poids_par_sac) > 0;
                const sacs = stockItem ? parseFloat(stockItem.quantite) : 0;
                const kg = stockItem ? parseFloat(stockItem.quantite_kg ?? "0") : 0;
                const stockLabel = stockItem
                  ? hasPds
                    ? sacs > 0 && kg > 0 ? `${sacs} sacs + ${kg.toFixed(2)} kg dispo`
                      : sacs > 0 ? `${sacs} sacs dispo`
                      : `${kg.toFixed(2)} kg dispo`
                  : `${sacs} ${stockItem.unite} dispo`
                  : null;
                return (
                <div key={i} className="flex gap-2 items-start flex-col sm:flex-row sm:items-center">
                  <div className="flex-1 flex flex-col gap-0.5 w-full sm:w-auto">
                  <select
                    className="flex-1 h-10 rounded-md border border-input bg-background px-2 text-sm w-full"
                    value={ligne.produit_id}
                    onChange={(e) => updateLigne(i, "produit_id", e.target.value)}
                  >
                    <option value="">Produit...</option>
                    {produits.map((p) => (
                      <option key={p.produit_id} value={p.produit_id}>
                        {p.produit_nom}{p.produit_code ? ` (${p.produit_code})` : ""}
                      </option>
                    ))}
                  </select>
                  {stockLabel && (
                    <span className="text-xs text-emerald-700 dark:text-emerald-400 px-1">{stockLabel}</span>
                  )}
                  </div>
                  <Input
                    type="number"
                    min="0.01"
                    step="0.01"
                    placeholder="Quantité"
                    className="w-24 sm:w-32"
                    value={ligne.quantite}
                    onChange={(e) => updateLigne(i, "quantite", e.target.value)}
                  />
                  <select
                    className="h-10 rounded-md border border-input bg-background px-2 text-sm"
                    value={ligne.unite}
                    onChange={(e) => updateLigne(i, "unite", e.target.value)}
                  >
                    <option value="sacs">sacs</option>
                    <option value="kg">kg</option>
                    <option value="tonnes">tonnes</option>
                  </select>
                  {lignes.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeLigne(i)}
                      className="text-destructive text-sm hover:underline px-1"
                    >
                      ✕
                    </button>
                  )}
                </div>
                );
              })}
            </div>
          </div>

          {err && <p className="text-sm text-destructive">{err}</p>}

          <Button
            type="submit"
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 text-white"
          >
            {loading ? "Transfert en cours..." : "Confirmer le transfert"}
          </Button>
        </form>
      )}

      {/* Historique */}
      {tab === "historique" && (
        <div className="overflow-x-auto rounded-md border -mx-1 sm:mx-0">
          <table className="w-full text-xs sm:text-sm min-w-[560px]">
            <thead>
              <tr className="border-b bg-blue-50/50 dark:bg-blue-950/20">
                <th className="text-left py-2 px-3 text-blue-700 dark:text-blue-300">#</th>
                <th className="text-left py-2 px-3">Destination</th>
                <th className="text-left py-2 px-3">Produits</th>
                <th className="text-left py-2 px-3">Date</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-muted-foreground text-sm">
                    Aucun transfert.
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="border-b hover:bg-blue-50/30 dark:hover:bg-blue-950/10">
                  <td className="py-1.5 px-3 font-mono text-blue-700 dark:text-blue-300">#{r.id}</td>
                  <td className="py-1.5 px-3">{r.to_lieu_nom}</td>
                  <td className="py-1.5 px-3">
                    {(r.mouvements ?? []).map((m, i) => (
                      <span key={i} className="block text-xs">
                        {m.produit_nom} × {Number(m.quantite).toFixed(2)}
                      </span>
                    ))}
                  </td>
                  <td className="py-1.5 px-3 text-muted-foreground">
                    {new Date(r.date).toLocaleString("fr-FR")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
