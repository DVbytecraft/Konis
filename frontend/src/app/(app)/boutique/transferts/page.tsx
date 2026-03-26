"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRightLeft, PlusIcon, Trash2Icon } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { buildIdempotencyKey } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface StockItem {
  produit_id: number;
  produit_nom: string;
  quantite: string;       // sacs
  quantite_kg: string;    // kg
  poids_par_sac: string | null;
  unite: string;
}

interface Destination {
  id: number;
  nom: string;
  type_label: string;
}

interface LigneTransfert {
  produit_id: number | null;
  produit_nom: string;
  quantite: string;
  unite: string;
  disponible: string;   // affiché pour info
}

interface HistoriqueTransfert {
  id: number;
  date: string;
  from_lieu: string;
  to_lieu: string;
  to_lieu_type: string;
  mouvements: { produit: string; quantite: string; unite: string }[];
}

const LIGNE_VIDE: LigneTransfert = {
  produit_id: null,
  produit_nom: "",
  quantite: "",
  unite: "sacs",
  disponible: "",
};

function afficherDispo(s: StockItem): string {
  const hasPds = s.poids_par_sac && parseFloat(s.poids_par_sac) > 0;
  const sacs = parseFloat(s.quantite);
  const kg = parseFloat(s.quantite_kg);
  if (hasPds) {
    if (sacs > 0 && kg > 0) return `${sacs} sacs + ${kg.toFixed(2)} kg`;
    if (sacs > 0) return `${sacs} sacs`;
    if (kg > 0) return `${kg.toFixed(2)} kg`;
    return "0";
  }
  if (kg > 0) return `${kg.toFixed(2)} kg`;
  if (sacs > 0) return `${sacs} ${s.unite}`;
  return "0";
}

export default function BoutiqueTransfertsPage() {
  const [stocks, setStocks]           = useState<StockItem[]>([]);
  const [destinations, setDests]      = useState<Destination[]>([]);
  const [historique, setHistorique]   = useState<HistoriqueTransfert[]>([]);
  const [loading, setLoading]         = useState(true);
  const [submitting, setSubmitting]   = useState(false);
  const [err, setErr]                 = useState("");
  const [success, setSuccess]         = useState("");

  const [toPlieu, setToPlieu]         = useState<number | null>(null);
  const [lignes, setLignes]           = useState<LigneTransfert[]>([{ ...LIGNE_VIDE }]);

  // Autocomplete produit
  const [acVisible, setAcVisible]     = useState<Record<number, boolean>>({});
  const debounceRefs                  = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [st, dests, hist] = await Promise.all([
        apiFetch<StockItem[]>("/boutique/stock/"),
        apiFetch<Destination[]>("/boutique/transferts/destinations/"),
        apiFetch<HistoriqueTransfert[]>("/boutique/transferts/"),
      ]);
      setStocks(Array.isArray(st) ? st : []);
      setDests(Array.isArray(dests) ? dests : []);
      setHistorique(Array.isArray(hist) ? hist : []);
    } catch {
      setErr("Impossible de charger les données.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const setLigne = (i: number, patch: Partial<LigneTransfert>) =>
    setLignes((prev) => prev.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

  const addLigne = () => setLignes((prev) => [...prev, { ...LIGNE_VIDE }]);
  const removeLigne = (i: number) => setLignes((prev) => prev.filter((_, idx) => idx !== i));

  const selectProduit = (i: number, s: StockItem) => {
    // Déterminer l'unité par défaut selon le stock
    const hasPds = s.poids_par_sac && parseFloat(s.poids_par_sac) > 0;
    const unite = hasPds ? "sacs" : "kg";
    setLigne(i, {
      produit_id: s.produit_id,
      produit_nom: s.produit_nom,
      unite,
      disponible: afficherDispo(s),
    });
    setAcVisible((p) => ({ ...p, [i]: false }));
  };

  const handleNomChange = (i: number, val: string) => {
    setLigne(i, { produit_nom: val, produit_id: null, disponible: "" });
    if (debounceRefs.current[i]) clearTimeout(debounceRefs.current[i]);
    debounceRefs.current[i] = setTimeout(() => {
      setAcVisible((p) => ({ ...p, [i]: val.trim().length > 0 }));
    }, 100);
  };

  const filteredStocks = (i: number) => {
    const q = (lignes[i]?.produit_nom || "").toLowerCase();
    if (!q) return stocks;
    return stocks.filter((s) => s.produit_nom.toLowerCase().includes(q));
  };

  const reset = () => {
    setToPlieu(null);
    setLignes([{ ...LIGNE_VIDE }]);
    setErr("");
    setSuccess("");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setSuccess("");

    if (!toPlieu) { setErr("Sélectionnez une destination."); return; }

    for (let i = 0; i < lignes.length; i++) {
      const l = lignes[i];
      if (!l.produit_id) { setErr(`Ligne ${i + 1} : sélectionnez un produit depuis la liste.`); return; }
      const q = parseFloat(l.quantite);
      if (!l.quantite || isNaN(q) || q <= 0) {
        setErr(`Ligne ${i + 1} : quantité invalide.`); return;
      }
    }

    setSubmitting(true);
    try {
      await apiFetch("/boutique/transferts/", {
        method: "POST",
        headers: { "Idempotency-Key": buildIdempotencyKey("boutique-transfert") },
        body: JSON.stringify({
          to_lieu: toPlieu,
          lignes: lignes.map((l) => ({
            produit_id: l.produit_id,
            quantite: l.quantite,
            unite: l.unite,
          })),
        }),
      });
      setSuccess("Transfert effectué avec succès.");
      reset();
      await loadAll();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur lors du transfert.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground p-4">Chargement…</p>;
  }

  return (
    <div className="space-y-6 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <ArrowRightLeft className="h-6 w-6" /> Transferts
        </h1>
        <p className="text-sm text-muted-foreground">
          Transférer du stock vers une autre boutique, une usine ou le MPSL.
        </p>
      </div>

      {/* ── Formulaire ──────────────────────────────────────────────────────── */}
      <form onSubmit={submit} className="rounded-lg border bg-card p-4 space-y-5">
        <h2 className="text-base font-medium">Nouveau transfert</h2>

        {/* Destination */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Destination *
          </label>
          {destinations.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">Aucune destination disponible.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {destinations.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => setToPlieu(d.id)}
                  className={cn(
                    "rounded border py-2 px-3 text-sm text-left transition-colors",
                    toPlieu === d.id
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-background hover:bg-muted border-input"
                  )}
                >
                  <span className="font-medium">{d.nom}</span>
                  <span className="ml-2 text-xs opacity-70">({d.type_label})</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Lignes produits */}
        <div className="space-y-3">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Produits ({lignes.length})
          </label>

          {lignes.map((l, i) => (
            <div key={i} className="relative rounded-md border p-3 bg-background space-y-2">
              {lignes.length > 1 && (
                <button
                  type="button"
                  className="absolute top-2 right-2 text-muted-foreground hover:text-destructive"
                  onClick={() => removeLigne(i)}
                >
                  <Trash2Icon className="h-4 w-4" />
                </button>
              )}
              <p className="text-xs font-medium text-muted-foreground pr-6">Produit {i + 1}</p>

              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {/* Produit — autocomplete depuis stock */}
                <div className="relative flex flex-col gap-1 sm:col-span-1">
                  <label className="text-xs text-muted-foreground">Produit *</label>
                  <Input
                    placeholder="Rechercher dans le stock…"
                    value={l.produit_nom}
                    onChange={(e) => handleNomChange(i, e.target.value)}
                    onFocus={() => setAcVisible((p) => ({ ...p, [i]: true }))}
                    onBlur={() =>
                      setTimeout(() => setAcVisible((p) => ({ ...p, [i]: false })), 150)
                    }
                    autoComplete="off"
                    className={cn(!l.produit_id && l.produit_nom ? "border-amber-400" : "")}
                  />
                  {acVisible[i] && (
                    <ul className="absolute z-50 top-full left-0 right-0 mt-0.5 border rounded-md bg-popover shadow-md max-h-52 overflow-y-auto">
                      {filteredStocks(i).length === 0 ? (
                        <li className="px-3 py-2 text-xs text-muted-foreground italic">
                          Aucun produit en stock.
                        </li>
                      ) : (
                        filteredStocks(i).map((s) => (
                          <li
                            key={s.produit_id}
                            className="px-3 py-1.5 text-xs hover:bg-muted cursor-pointer flex justify-between"
                            onMouseDown={(e) => { e.preventDefault(); selectProduit(i, s); }}
                          >
                            <span className="font-medium">{s.produit_nom}</span>
                            <span className="text-muted-foreground">{afficherDispo(s)}</span>
                          </li>
                        ))
                      )}
                    </ul>
                  )}
                  {l.disponible && (
                    <p className="text-xs text-muted-foreground">Dispo : {l.disponible}</p>
                  )}
                </div>

                {/* Quantité */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground">Quantité *</label>
                  <Input
                    type="number"
                    min="0.001"
                    step="any"
                    placeholder="Ex : 10"
                    value={l.quantite}
                    onChange={(e) => setLigne(i, { quantite: e.target.value })}
                  />
                </div>

                {/* Unité */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground">Unité</label>
                  <select
                    className="h-10 rounded-md border border-input bg-background px-2 text-sm"
                    value={l.unite}
                    onChange={(e) => setLigne(i, { unite: e.target.value })}
                  >
                    <option value="sacs">sacs</option>
                    <option value="kg">kg</option>
                    <option value="tonnes">tonnes</option>
                  </select>
                </div>
              </div>
            </div>
          ))}

          <button
            type="button"
            onClick={addLigne}
            className="flex items-center gap-1.5 text-sm text-primary hover:underline"
          >
            <PlusIcon className="h-4 w-4" /> Ajouter un produit
          </button>
        </div>

        {err && <p className="text-sm text-destructive">{err}</p>}
        {success && <p className="text-sm text-green-600 dark:text-green-400">{success}</p>}

        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? "Transfert en cours…" : `Transférer ${lignes.length > 1 ? `${lignes.length} produits` : "le produit"}`}
        </Button>
      </form>

      {/* ── Historique ──────────────────────────────────────────────────────── */}
      <div>
        <h2 className="text-base font-medium mb-3">Historique des transferts</h2>
        {historique.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucun transfert effectué.</p>
        ) : (
          <div className="space-y-2">
            {historique.map((t) => (
              <div key={t.id} className="rounded-md border p-3 text-sm">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium">
                    #{t.id} → {t.to_lieu}{" "}
                    <span className="text-xs text-muted-foreground">({t.to_lieu_type})</span>
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(t.date).toLocaleString("fr-FR")}
                  </span>
                </div>
                <ul className="text-xs text-muted-foreground space-y-0.5">
                  {t.mouvements.map((m, idx) => (
                    <li key={idx}>
                      {m.produit} × {m.quantite} {m.unite}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
