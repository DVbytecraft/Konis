"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

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
  type_paiement: string;
  type_paiement_label: string;
  montant_paye_initial: string;
  fournisseur_nom?: string | null;
  journal_payable_id?: number | null;
}

interface Fournisseur {
  id: number;
  nom: string;
  contact?: string;
}

type ApiList<T> = T[] | { results?: T[] };
function toList<T>(r: ApiList<T>): T[] {
  if (Array.isArray(r)) return r;
  return r.results ?? [];
}

type TypePaiement = "cash" | "credit" | "partiel";
const UNITES = ["sacs", "kg", "tonnes"] as const;

const BADGE: Record<TypePaiement, string> = {
  cash:    "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  credit:  "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  partiel: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
};

const EMPTY = {
  produit_nom:   "",
  quantite:      "",
  unite:         "sacs" as string,
  poids_par_sac: "",
  prix_unitaire: "",
  notes:         "",
  type_paiement: "cash" as TypePaiement,
  montant_paye:  "",
};

export default function MpslAchatsPage() {
  const [rows, setRows]               = useState<AchatRow[]>([]);
  const [form, setForm]               = useState(EMPTY);
  const [err, setErr]                 = useState("");
  const [loading, setLoading]         = useState(false);

  // Fournisseur search
  const [foSearch, setFoSearch]       = useState("");
  const [fournisseurs, setFournisseurs] = useState<Fournisseur[]>([]);
  const [foLoading, setFoLoading]     = useState(false);
  const [foSelected, setFoSelected]   = useState<Fournisseur | null>(null);
  const [showFoList, setShowFoList]   = useState(false);
  const debounceRef                   = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    const achats = await apiFetch("/mpsl/achats/");
    setRows(toList(achats as ApiList<AchatRow>));
  }, []);

  useEffect(() => { load().catch(() => {}); }, [load]);

  // Debounced fournisseur search
  useEffect(() => {
    if (form.type_paiement === "cash") return;
    if (!foSearch.trim()) { setFournisseurs([]); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setFoLoading(true);
      try {
        const res = await apiFetch<Fournisseur[]>(`/mpsl/fournisseurs/?search=${encodeURIComponent(foSearch)}`);
        setFournisseurs(Array.isArray(res) ? res : []);
      } catch { setFournisseurs([]); }
      finally { setFoLoading(false); }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [foSearch, form.type_paiement]);

  const totalEstime = form.quantite && form.prix_unitaire
    ? Number(form.quantite) * Number(form.prix_unitaire)
    : null;

  const resetFournisseur = () => {
    setFoSelected(null);
    setFoSearch("");
    setFournisseurs([]);
    setShowFoList(false);
  };

  const resetForm = () => {
    setForm(EMPTY);
    resetFournisseur();
    setErr("");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (!form.produit_nom.trim()) { setErr("Nom du produit obligatoire."); return; }
    if (!form.quantite || Number(form.quantite) <= 0) { setErr("Quantité > 0 requise."); return; }
    if (form.unite === "sacs" && (!form.poids_par_sac || Number(form.poids_par_sac) <= 0)) {
      setErr("Poids par sac requis pour une unit?? en sacs.");
      return;
    }
    if ((form.type_paiement === "credit" || form.type_paiement === "partiel") && !foSelected) {
      setErr("Sélectionnez un fournisseur pour un achat à crédit ou partiel.");
      return;
    }
    if (form.type_paiement === "partiel" && (!form.montant_paye || Number(form.montant_paye) < 0)) {
      setErr("Saisissez l'acompte versé pour un achat partiel.");
      return;
    }
    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        produit_nom:   form.produit_nom.trim(),
        quantite:      form.quantite,
        unite:         form.unite,
        poids_par_sac: form.unite === "sacs" ? form.poids_par_sac : null,
        prix_unitaire: form.prix_unitaire || "0",
        notes:         form.notes,
        type_paiement: form.type_paiement,
      };
      if (foSelected) body.fournisseur_id = foSelected.id;
      if (form.type_paiement === "partiel") body.montant_paye_initial = form.montant_paye;
      await apiFetch("/mpsl/achats/", { method: "POST", body: JSON.stringify(body) });
      resetForm();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur lors de l'enregistrement.");
    } finally {
      setLoading(false);
    }
  };

  const typePaiement = form.type_paiement as TypePaiement;

  return (
    <div className="space-y-6 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Achats MPSL</h1>
        <p className="text-sm text-muted-foreground">
          Enregistrer les réceptions de produits au dépôt.
          Les achats à crédit ou partiels créent automatiquement une dette fournisseur.
        </p>
      </div>

      {/* ── Formulaire ──────────────────────────────────────────────────────── */}
      <div className="rounded-lg border bg-card p-4 space-y-4">
        <h2 className="text-base font-medium">Nouvel achat</h2>

        {/* Type de paiement */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Mode de paiement
          </label>
          <div className="grid grid-cols-3 gap-2">
            {(["cash", "credit", "partiel"] as TypePaiement[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => {
                  setForm((f) => ({ ...f, type_paiement: t, montant_paye: "" }));
                  resetFournisseur();
                }}
                className={cn(
                  "rounded border py-2 text-sm font-semibold transition-colors",
                  typePaiement === t
                    ? t === "cash"
                      ? "bg-green-600 text-white border-green-600"
                      : t === "credit"
                      ? "bg-red-500 text-white border-red-500"
                      : "bg-amber-500 text-white border-amber-500"
                    : "bg-background hover:bg-muted border-input"
                )}
              >
                {t === "cash" ? "Cash" : t === "credit" ? "Crédit" : "Partiel"}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {/* Produit */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Nom du produit *</label>
            <Input
              placeholder="Ex : Maïs jaune, Son de blé..."
              value={form.produit_nom}
              onChange={(e) => setForm((f) => ({ ...f, produit_nom: e.target.value }))}
            />
          </div>

          {/* Quantité */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Quantité *</label>
            <Input
              type="number" min="0.01" step="0.01" placeholder="Ex : 500"
              value={form.quantite}
              onChange={(e) => setForm((f) => ({ ...f, quantite: e.target.value }))}
            />
          </div>

          {/* Unité */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Unité</label>
            <select
              className="h-10 rounded-md border border-input bg-background px-2 text-sm"
              value={form.unite}
              onChange={(e) => setForm((f) => ({ ...f, unite: e.target.value }))}
            >
              {UNITES.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>

          {/* Poids par sac (si unit?? = sacs) */}
          {form.unite === "sacs" && (
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Poids par sac (kg)</label>
              <Input
                type="number" min="0.001" step="0.001" placeholder="Ex : 50"
                value={form.poids_par_sac}
                onChange={(e) => setForm((f) => ({ ...f, poids_par_sac: e.target.value }))}
              />
            </div>
          )}

          {/* Prix unitaire */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Prix unitaire (FCFA)</label>
            <Input
              type="number" min="0" step="1" placeholder="Ex : 120"
              value={form.prix_unitaire}
              onChange={(e) => setForm((f) => ({ ...f, prix_unitaire: e.target.value }))}
            />
          </div>

          {/* Notes */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Notes (optionnel)</label>
            <Input
              placeholder="Référence, batch..."
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </div>

          {/* Fournisseur — visible si crédit ou partiel */}
          {(typePaiement === "credit" || typePaiement === "partiel") && (
            <div className="flex flex-col gap-1 relative">
              <label className="text-xs font-medium text-muted-foreground">
                Fournisseur *
              </label>
              <Input
                placeholder="Rechercher un fournisseur…"
                value={foSearch}
                onChange={(e) => { setFoSearch(e.target.value); setFoSelected(null); setShowFoList(true); }}
                onFocus={() => setShowFoList(true)}
              />
              {foSelected && (
                <p className="text-xs text-green-700 dark:text-green-300 mt-0.5 pl-0.5">
                  ✓ {foSelected.nom}
                </p>
              )}
              {showFoList && !foSelected && fournisseurs.length > 0 && (
                <ul className="absolute z-50 top-full left-0 right-0 mt-0.5 border rounded-md bg-popover shadow-md max-h-40 overflow-y-auto">
                  {foLoading ? (
                    <li className="px-3 py-2 text-xs text-muted-foreground">Chargement…</li>
                  ) : (
                    fournisseurs.map((f) => (
                      <li
                        key={f.id}
                        className="px-3 py-1.5 text-xs hover:bg-muted cursor-pointer"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          setFoSelected(f);
                          setFoSearch(f.nom);
                          setShowFoList(false);
                        }}
                      >
                        <span className="font-medium">{f.nom}</span>
                        {f.contact && <span className="text-muted-foreground ml-2">{f.contact}</span>}
                      </li>
                    ))
                  )}
                </ul>
              )}
            </div>
          )}

          {/* Acompte — visible si partiel */}
          {typePaiement === "partiel" && (
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">
                Acompte versé (FCFA) *
              </label>
              <Input
                type="number" min="0" step="1"
                placeholder={totalEstime ? `Max : ${fmt(totalEstime)} FCFA` : "Montant payé"}
                value={form.montant_paye}
                onChange={(e) => setForm((f) => ({ ...f, montant_paye: e.target.value }))}
              />
            </div>
          )}

          {/* Total estimé */}
          {totalEstime !== null && totalEstime > 0 && (
            <p className="text-sm font-semibold text-orange-700 dark:text-orange-300 sm:col-span-2 lg:col-span-3">
              Total : {fmt(totalEstime)} FCFA
              {typePaiement === "partiel" && form.montant_paye && (
                <span className="ml-3 text-red-500">
                  Reste dû : {fmt(Math.max(0, totalEstime - Number(form.montant_paye)))} FCFA
                </span>
              )}
              {typePaiement === "credit" && (
                <span className="ml-3 text-red-500">— Dette fournisseur créée automatiquement</span>
              )}
            </p>
          )}

          {err && (
            <p className="text-sm text-destructive sm:col-span-2 lg:col-span-3">{err}</p>
          )}

          <Button
            type="submit"
            disabled={loading}
            className={cn(
              "sm:col-span-2 lg:col-span-3 text-white",
              typePaiement === "cash"
                ? "bg-green-600 hover:bg-green-700"
                : typePaiement === "credit"
                ? "bg-red-500 hover:bg-red-600"
                : "bg-amber-500 hover:bg-amber-600"
            )}
          >
            {loading ? "Enregistrement…" : "Enregistrer l'achat"}
          </Button>
        </form>
      </div>

      {/* ── Historique ──────────────────────────────────────────────────────── */}
      <div>
        <h2 className="text-base font-medium mb-3">Historique des achats</h2>
        <div className="overflow-x-auto rounded-md border -mx-1 sm:mx-0">
          <table className="w-full text-xs sm:text-sm min-w-[680px]">
            <thead>
              <tr className="border-b bg-orange-50/50 dark:bg-orange-950/20">
                <th className="text-left py-2 px-3 text-orange-700 dark:text-orange-300">Produit</th>
                <th className="text-left py-2 px-3">Fournisseur</th>
                <th className="text-right py-2 px-3">Quantité</th>
                <th className="text-left py-2 px-3">Unité</th>
                <th className="text-right py-2 px-3 text-orange-700 dark:text-orange-300">Total</th>
                <th className="text-left py-2 px-3">Paiement</th>
                <th className="text-left py-2 px-3">Date</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-muted-foreground text-sm">
                    Aucun achat enregistré.
                  </td>
                </tr>
              )}
              {rows.map((r) => {
                const tp = (r.type_paiement || "cash") as TypePaiement;
                return (
                  <tr key={r.id} className="border-b hover:bg-orange-50/30 dark:hover:bg-orange-950/10">
                    <td className="py-1.5 px-3 font-medium">{r.produit_nom}</td>
                    <td className="py-1.5 px-3 text-muted-foreground">
                      {r.fournisseur_nom || "—"}
                    </td>
                    <td className="py-1.5 px-3 text-right font-mono">{Number(r.quantite).toFixed(2)}</td>
                    <td className="py-1.5 px-3 text-muted-foreground">{r.unite}</td>
                    <td className="py-1.5 px-3 text-right font-semibold text-orange-700 dark:text-orange-300">
                      {fmt(Number(r.prix_total))}
                    </td>
                    <td className="py-1.5 px-3">
                      <span className={cn("inline-block rounded-full px-2 py-0.5 text-xs font-semibold", BADGE[tp])}>
                        {r.type_paiement_label || tp}
                      </span>
                      {tp === "partiel" && Number(r.montant_paye_initial) > 0 && (
                        <span className="text-xs text-muted-foreground ml-1">
                          (versé : {fmt(Number(r.montant_paye_initial))} F)
                        </span>
                      )}
                      {r.journal_payable_id && (
                        <span className="text-xs text-red-500 ml-1">↗ dette</span>
                      )}
                    </td>
                    <td className="py-1.5 px-3 text-muted-foreground">
                      {new Date(r.date).toLocaleString("fr-FR")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
