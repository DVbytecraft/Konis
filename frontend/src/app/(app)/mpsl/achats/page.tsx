"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface AchatRow {
  id: number;
  produit_nom: string;
  lieu_nom: string;
  quantite: string;
  unite: string;
  prix_unitaire: string;
  prix_total: string;
  notes: string;
  date: string;
}

type ApiList<T> = T[] | { results?: T[] };
function toList<T>(r: ApiList<T>): T[] {
  if (Array.isArray(r)) return r;
  return r.results ?? [];
}

const UNITES = ["sacs", "kg", "tonnes"] as const;

export default function MpslAchatsPage() {
  const [rows, setRows] = useState<AchatRow[]>([]);
  const [form, setForm] = useState({
    produit_nom: "",
    quantite: "",
    unite: "sacs",
    prix_unitaire: "",
    notes: "",
  });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const achats = await apiFetch("/mpsl/achats/");
    setRows(toList(achats as ApiList<AchatRow>));
  };

  useEffect(() => { load().catch(() => {}); }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (!form.produit_nom.trim()) { setErr("Nom du produit obligatoire."); return; }
    if (!form.quantite || Number(form.quantite) <= 0) { setErr("Quantité > 0 requise."); return; }
    setLoading(true);
    try {
      await apiFetch("/mpsl/achats/", {
        method: "POST",
        body: JSON.stringify({
          produit_nom: form.produit_nom.trim(),
          quantite: form.quantite,
          unite: form.unite,
          prix_unitaire: form.prix_unitaire || "0",
          notes: form.notes,
        }),
      });
      setForm({ produit_nom: "", quantite: "", unite: "sacs", prix_unitaire: "", notes: "" });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur lors de l'enregistrement.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Achats MPSL</h1>
        <p className="text-sm text-muted-foreground">
          Enregistrer les réceptions de produits au dépôt.
        </p>
      </div>

      <div className="rounded-lg border bg-card p-4">
        <h2 className="text-base font-medium mb-4">Nouvel achat</h2>
        <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Nom du produit</label>
            <Input
              placeholder="Ex : Maïs jaune, Son de blé..."
              value={form.produit_nom}
              onChange={(e) => setForm((f) => ({ ...f, produit_nom: e.target.value }))}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Quantité</label>
            <Input
              type="number"
              min="0.01"
              step="0.01"
              placeholder="Ex : 500"
              value={form.quantite}
              onChange={(e) => setForm((f) => ({ ...f, quantite: e.target.value }))}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Unité</label>
            <select
              className="h-10 rounded-md border border-input bg-background px-2 text-sm"
              value={form.unite}
              onChange={(e) => setForm((f) => ({ ...f, unite: e.target.value }))}
            >
              {UNITES.map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Prix unitaire (FCFA)</label>
            <Input
              type="number"
              min="0"
              step="1"
              placeholder="Ex : 120"
              value={form.prix_unitaire}
              onChange={(e) => setForm((f) => ({ ...f, prix_unitaire: e.target.value }))}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Notes (optionnel)</label>
            <Input
              placeholder="Fournisseur, référence..."
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </div>

          {err && (
            <p className="text-sm text-destructive sm:col-span-2 lg:col-span-3">{err}</p>
          )}
          {form.quantite && form.prix_unitaire && Number(form.prix_unitaire) > 0 && (
            <p className="text-sm text-orange-700 dark:text-orange-300 font-medium sm:col-span-2 lg:col-span-3">
              Total estimé : {(Number(form.quantite) * Number(form.prix_unitaire)).toLocaleString("fr-FR")} FCFA
            </p>
          )}

          <Button
            type="submit"
            disabled={loading}
            className="sm:col-span-2 lg:col-span-3 bg-orange-600 hover:bg-orange-700 text-white"
          >
            {loading ? "Enregistrement..." : "Enregistrer l'achat"}
          </Button>
        </form>
      </div>

      <div>
        <h2 className="text-base font-medium mb-3">Historique des achats</h2>
        <div className="overflow-x-auto rounded-md border -mx-1 sm:mx-0">
          <table className="w-full text-xs sm:text-sm min-w-[580px]">
            <thead>
              <tr className="border-b bg-orange-50/50 dark:bg-orange-950/20">
                <th className="text-left py-2 px-3 text-orange-700 dark:text-orange-300">Produit</th>
                <th className="text-right py-2 px-3">Quantité</th>
                <th className="text-left py-2 px-3">Unité</th>
                <th className="text-right py-2 px-3">Prix unit.</th>
                <th className="text-right py-2 px-3 text-orange-700 dark:text-orange-300">Total</th>
                <th className="text-left py-2 px-3">Date</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-muted-foreground text-sm">
                    Aucun achat enregistré.
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="border-b hover:bg-orange-50/30 dark:hover:bg-orange-950/10">
                  <td className="py-1.5 px-3 font-medium">{r.produit_nom}</td>
                  <td className="py-1.5 px-3 text-right font-mono">{Number(r.quantite).toFixed(2)}</td>
                  <td className="py-1.5 px-3 text-muted-foreground">{r.unite}</td>
                  <td className="py-1.5 px-3 text-right">{Number(r.prix_unitaire).toLocaleString("fr-FR")}</td>
                  <td className="py-1.5 px-3 text-right font-semibold text-orange-700 dark:text-orange-300">
                    {Number(r.prix_total).toLocaleString("fr-FR")}
                  </td>
                  <td className="py-1.5 px-3 text-muted-foreground">
                    {new Date(r.date).toLocaleString("fr-FR")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
