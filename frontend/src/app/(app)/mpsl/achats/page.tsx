"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PlusIcon, Trash2Icon } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { buildIdempotencyKey, fmt } from "@/lib/utils";
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
  journal_montant_paye?: string | null;
}

interface Fournisseur {
  id: number;
  nom: string;
  contact?: string;
}

interface LigneProduit {
  produit_nom: string;
  quantite: string;
  unite: string;
  poids_par_sac: string;
  prix_unitaire: string;
  notes: string;
}

interface CatalogueProduit {
  id: number;
  nom: string;
  code: string;
  unite: string;
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

const LIGNE_VIDE: LigneProduit = {
  produit_nom: "",
  quantite: "",
  unite: "sacs",
  poids_par_sac: "",
  prix_unitaire: "",
  notes: "",
};

export default function MpslAchatsPage() {
  const [rows, setRows]               = useState<AchatRow[]>([]);
  const [loading, setLoading]         = useState(false);
  const [err, setErr]                 = useState("");

  // Catalogue produits pour autocomplete
  const [catalogue, setCatalogue]     = useState<CatalogueProduit[]>([]);
  const [acSuggestions, setAcSuggestions] = useState<Record<number, CatalogueProduit[]>>({});
  const [acVisible, setAcVisible]     = useState<Record<number, boolean>>({});

  // Paiement
  const [typePaiement, setTypePaiement] = useState<TypePaiement>("cash");
  const [acompte, setAcompte]           = useState("");

  // Lignes produits
  const [lignes, setLignes]             = useState<LigneProduit[]>([{ ...LIGNE_VIDE }]);

  // Fournisseur
  const [foSearch, setFoSearch]         = useState("");
  const [fournisseurs, setFournisseurs] = useState<Fournisseur[]>([]);
  const [foLoading, setFoLoading]       = useState(false);
  const [foSelected, setFoSelected]     = useState<Fournisseur | null>(null);
  const [foMode, setFoMode]             = useState<"search" | "nouveau">("search");
  const [foNouveauNom, setFoNouveauNom] = useState("");
  const [showFoList, setShowFoList]     = useState(false);
  const debounceRef                     = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    const achats = await apiFetch("/mpsl/achats/");
    setRows(toList(achats as ApiList<AchatRow>));
  }, []);

  useEffect(() => { load().catch(() => {}); }, [load]);

  // Charger le catalogue une seule fois
  useEffect(() => {
    apiFetch<CatalogueProduit[]>("/mpsl/catalogue/")
      .then((res) => setCatalogue(Array.isArray(res) ? res : []))
      .catch(() => {});
  }, []);

  const handleProduitNomChange = (i: number, val: string) => {
    setLigne(i, { produit_nom: val });
    if (!val.trim()) {
      setAcSuggestions((p) => ({ ...p, [i]: [] }));
      setAcVisible((p) => ({ ...p, [i]: false }));
      return;
    }
    const q = val.toLowerCase();
    const matches = catalogue.filter((c) => c.nom.toLowerCase().includes(q)).slice(0, 8);
    setAcSuggestions((p) => ({ ...p, [i]: matches }));
    setAcVisible((p) => ({ ...p, [i]: true }));
  };

  const selectSuggestion = (i: number, produit: CatalogueProduit) => {
    const patch: Partial<LigneProduit> = { produit_nom: produit.nom };
    if (produit.unite) patch.unite = produit.unite === "sac" ? "sacs" : produit.unite;
    setLigne(i, patch);
    setAcVisible((p) => ({ ...p, [i]: false }));
  };

  // Recherche fournisseur debounced
  useEffect(() => {
    if (typePaiement === "cash" || foMode === "nouveau") return;
    if (!foSearch.trim()) { setFournisseurs([]); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setFoLoading(true);
      try {
        const res = await apiFetch<Fournisseur[]>(
          `/mpsl/fournisseurs/?search=${encodeURIComponent(foSearch)}`
        );
        setFournisseurs(Array.isArray(res) ? res : []);
        setShowFoList(true);
      } catch { setFournisseurs([]); }
      finally { setFoLoading(false); }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [foSearch, typePaiement, foMode]);

  const totalGlobal = lignes.reduce((acc, l) => {
    const q = parseInt(l.quantite) || 0;
    const p = parseInt(l.prix_unitaire) || 0;
    return acc + q * p;
  }, 0);

  const resetFournisseur = () => {
    setFoSelected(null);
    setFoSearch("");
    setFournisseurs([]);
    setShowFoList(false);
    setFoNouveauNom("");
    setFoMode("search");
  };

  const resetForm = () => {
    setTypePaiement("cash");
    setAcompte("");
    setLignes([{ ...LIGNE_VIDE }]);
    resetFournisseur();
    setErr("");
  };

  const setLigne = (i: number, patch: Partial<LigneProduit>) =>
    setLignes((prev) => prev.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

  const addLigne    = () => setLignes((prev) => [...prev, { ...LIGNE_VIDE }]);
  const removeLigne = (i: number) => setLignes((prev) => prev.filter((_, idx) => idx !== i));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");

    // Validation lignes
    for (let i = 0; i < lignes.length; i++) {
      const l = lignes[i];
      if (!l.produit_nom.trim()) {
        setErr(`Ligne ${i + 1} : nom du produit obligatoire.`); return;
      }
      const q = parseInt(l.quantite);
      if (!l.quantite || isNaN(q) || q <= 0 || String(q) !== l.quantite.trim()) {
        setErr(`Ligne ${i + 1} : quantité doit être un entier ≥ 1.`); return;
      }
      if (l.prix_unitaire) {
        const p = parseInt(l.prix_unitaire);
        if (isNaN(p) || p < 0 || String(p) !== l.prix_unitaire.trim()) {
          setErr(`Ligne ${i + 1} : prix unitaire doit être un entier ≥ 0.`); return;
        }
      }
      // poids_par_sac est facultatif : le produit rejoint le catalogue sans poids.
    }

    // Validation fournisseur
    if (typePaiement !== "cash") {
      if (foMode === "search" && !foSelected) {
        setErr("Sélectionnez un fournisseur ou choisissez « Nouveau fournisseur »."); return;
      }
      if (foMode === "nouveau" && !foNouveauNom.trim()) {
        setErr("Saisissez le nom du nouveau fournisseur."); return;
      }
    }

    // Validation acompte
    if (typePaiement === "partiel") {
      const a = parseInt(acompte);
      if (!acompte || isNaN(a) || a < 0 || String(a) !== acompte.trim()) {
        setErr("L'acompte doit être un entier ≥ 0."); return;
      }
    }

    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        type_paiement: typePaiement,
        produits: lignes.map((l) => ({
          produit_nom:   l.produit_nom.trim(),
          quantite:      parseInt(l.quantite),
          unite:         l.unite,
          poids_par_sac: (l.unite === "sacs" && l.poids_par_sac && Number(l.poids_par_sac) > 0)
            ? Number(l.poids_par_sac)
            : null,
          prix_unitaire: l.prix_unitaire ? parseInt(l.prix_unitaire) : 0,
          notes:         l.notes,
        })),
      };
      if (typePaiement !== "cash") {
        if (foMode === "search" && foSelected) body.fournisseur_id  = foSelected.id;
        if (foMode === "nouveau")              body.fournisseur_nom = foNouveauNom.trim();
      }
      if (typePaiement === "partiel") body.acompte = parseInt(acompte);

      await apiFetch("/mpsl/achats/batch/", {
        method: "POST",
        headers: { "Idempotency-Key": buildIdempotencyKey("mpsl-batch") },
        body: JSON.stringify(body),
      });
      resetForm();
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
          Les achats à crédit ou partiels créent automatiquement une dette fournisseur.
        </p>
      </div>

      {/* ── Formulaire ──────────────────────────────────────────────────────── */}
      <form onSubmit={submit} className="rounded-lg border bg-card p-4 space-y-5">
        <h2 className="text-base font-medium">Nouvel achat</h2>

        {/* Mode de paiement */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Mode de paiement
          </label>
          <div className="grid grid-cols-3 gap-2">
            {(["cash", "credit", "partiel"] as TypePaiement[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => { setTypePaiement(t); setAcompte(""); resetFournisseur(); }}
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

        {/* Fournisseur */}
        {typePaiement !== "cash" && (
          <div className="space-y-2 p-3 rounded-md bg-muted/40 border">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Fournisseur *
              </label>
              <button
                type="button"
                className="text-xs text-primary underline"
                onClick={() => { resetFournisseur(); setFoMode(foMode === "search" ? "nouveau" : "search"); }}
              >
                {foMode === "search" ? "+ Nouveau fournisseur" : "← Fournisseur existant"}
              </button>
            </div>

            {foMode === "search" ? (
              <div className="relative">
                <Input
                  placeholder="Rechercher un fournisseur…"
                  value={foSearch}
                  onChange={(e) => { setFoSearch(e.target.value); setFoSelected(null); }}
                  onFocus={() => setShowFoList(true)}
                  onBlur={() => setTimeout(() => setShowFoList(false), 150)}
                />
                {foSelected && (
                  <p className="text-xs text-green-700 dark:text-green-300 mt-1 pl-0.5">
                    ✓ {foSelected.nom} — confirmé
                  </p>
                )}
                {!foSelected && foSearch.trim() && !foLoading && fournisseurs.length === 0 && (
                  <p className="text-xs text-muted-foreground mt-1 pl-0.5 italic">
                    Aucun résultat — utilisez « + Nouveau fournisseur » pour créer.
                  </p>
                )}
                {showFoList && !foSelected && fournisseurs.length > 0 && (
                  <ul className="absolute z-50 top-full left-0 right-0 mt-0.5 border rounded-md bg-popover shadow-md max-h-48 overflow-y-auto">
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
                          {f.contact && (
                            <span className="text-muted-foreground ml-2">{f.contact}</span>
                          )}
                        </li>
                      ))
                    )}
                  </ul>
                )}
              </div>
            ) : (
              <Input
                placeholder="Nom du nouveau fournisseur"
                value={foNouveauNom}
                onChange={(e) => setFoNouveauNom(e.target.value)}
                autoFocus
              />
            )}
          </div>
        )}

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
                  className="absolute top-2 right-2 text-muted-foreground hover:text-destructive transition-colors"
                  onClick={() => removeLigne(i)}
                  title="Supprimer cette ligne"
                >
                  <Trash2Icon className="h-4 w-4" />
                </button>
              )}
              <p className="text-xs font-medium text-muted-foreground pr-6">Produit {i + 1}</p>

              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {/* Nom produit */}
                <div className="relative flex flex-col gap-1 sm:col-span-2 lg:col-span-1">
                  <label className="text-xs text-muted-foreground">Nom du produit *</label>
                  <Input
                    placeholder="Ex : Maïs jaune, Son de blé…"
                    value={l.produit_nom}
                    onChange={(e) => handleProduitNomChange(i, e.target.value)}
                    onBlur={() => setTimeout(() => setAcVisible((p) => ({ ...p, [i]: false })), 150)}
                    onFocus={() => {
                      if ((acSuggestions[i] ?? []).length > 0)
                        setAcVisible((p) => ({ ...p, [i]: true }));
                    }}
                    autoComplete="off"
                  />
                  {acVisible[i] && (acSuggestions[i] ?? []).length > 0 && (
                    <ul className="absolute z-50 top-full left-0 right-0 mt-0.5 border rounded-md bg-popover shadow-md max-h-48 overflow-y-auto">
                      {(acSuggestions[i] ?? []).map((p) => (
                        <li
                          key={p.id}
                          className="px-3 py-1.5 text-xs hover:bg-muted cursor-pointer"
                          onMouseDown={(e) => { e.preventDefault(); selectSuggestion(i, p); }}
                        >
                          <span className="font-medium">{p.nom}</span>
                          {p.code && <span className="text-muted-foreground ml-2">{p.code}</span>}
                          <span className="text-muted-foreground ml-2">({p.unite})</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Quantité */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground">Quantité *</label>
                  <Input
                    type="number"
                    min="1"
                    step="1"
                    placeholder="Ex : 500"
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
                    onChange={(e) => setLigne(i, { unite: e.target.value, poids_par_sac: "" })}
                  >
                    {UNITES.map((u) => <option key={u} value={u}>{u}</option>)}
                  </select>
                </div>

                {/* Poids par sac */}
                {l.unite === "sacs" && (
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-muted-foreground">Poids par sac (kg) <span className="opacity-50">(optionnel)</span></label>
                    <Input
                      type="number"
                      min="0.001"
                      step="0.001"
                      placeholder="Ex : 50"
                      value={l.poids_par_sac}
                      onChange={(e) => setLigne(i, { poids_par_sac: e.target.value })}
                    />
                  </div>
                )}

                {/* Prix unitaire */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground">Prix unitaire (FCFA)</label>
                  <Input
                    type="number"
                    min="0"
                    step="1"
                    placeholder="Ex : 12000"
                    value={l.prix_unitaire}
                    onChange={(e) => setLigne(i, { prix_unitaire: e.target.value })}
                  />
                </div>

                {/* Notes */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground">Notes</label>
                  <Input
                    placeholder="Référence, batch…"
                    value={l.notes}
                    onChange={(e) => setLigne(i, { notes: e.target.value })}
                  />
                </div>
              </div>

              {/* Sous-total */}
              {parseInt(l.quantite) > 0 && parseInt(l.prix_unitaire) > 0 && (
                <p className="text-xs text-right text-orange-700 dark:text-orange-300 font-semibold">
                  Sous-total : {fmt(parseInt(l.quantite) * parseInt(l.prix_unitaire))} FCFA
                </p>
              )}
            </div>
          ))}

          <button
            type="button"
            onClick={addLigne}
            className="flex items-center gap-1.5 text-sm text-primary hover:underline"
          >
            <PlusIcon className="h-4 w-4" />
            Ajouter un produit
          </button>
        </div>

        {/* Acompte — si partiel */}
        {typePaiement === "partiel" && (
          <div className="flex flex-col gap-1 max-w-xs">
            <label className="text-xs font-medium text-muted-foreground">Acompte versé (FCFA) *</label>
            <Input
              type="number"
              min="0"
              step="1"
              placeholder={totalGlobal > 0 ? `Max : ${fmt(totalGlobal)} FCFA` : "Montant payé"}
              value={acompte}
              onChange={(e) => setAcompte(e.target.value)}
            />
          </div>
        )}

        {/* Total global */}
        {totalGlobal > 0 && (
          <div className="rounded-md bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-800 px-4 py-2 space-y-0.5">
            <p className="text-sm font-semibold text-orange-700 dark:text-orange-300">
              Total : {fmt(totalGlobal)} FCFA
              {lignes.length > 1 && (
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  ({lignes.length} produits)
                </span>
              )}
            </p>
            {typePaiement === "partiel" && acompte && parseInt(acompte) >= 0 && (
              <p className="text-xs text-red-500">
                Reste dû : {fmt(Math.max(0, totalGlobal - parseInt(acompte)))} FCFA — dette fournisseur créée
              </p>
            )}
            {typePaiement === "credit" && (
              <p className="text-xs text-red-500">Dette fournisseur intégrale créée automatiquement</p>
            )}
          </div>
        )}

        {err && <p className="text-sm text-destructive">{err}</p>}

        <Button
          type="submit"
          disabled={loading}
          className={cn(
            "w-full text-white",
            typePaiement === "cash"
              ? "bg-green-600 hover:bg-green-700"
              : typePaiement === "credit"
              ? "bg-red-500 hover:bg-red-600"
              : "bg-amber-500 hover:bg-amber-600"
          )}
        >
          {loading
            ? "Enregistrement…"
            : `Enregistrer ${lignes.length > 1 ? `${lignes.length} produits` : "l'achat"}`}
        </Button>
      </form>

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
                    <td className="py-1.5 px-3 text-muted-foreground">{r.fournisseur_nom || "—"}</td>
                    <td className="py-1.5 px-3 text-right font-mono">{parseInt(r.quantite)}</td>
                    <td className="py-1.5 px-3 text-muted-foreground">{r.unite}</td>
                    <td className="py-1.5 px-3 text-right font-semibold text-orange-700 dark:text-orange-300">
                      {fmt(Number(r.prix_total))}
                    </td>
                    <td className="py-1.5 px-3">
                      <span className={cn("inline-block rounded-full px-2 py-0.5 text-xs font-semibold", BADGE[tp])}>
                        {r.type_paiement_label || tp}
                      </span>
                      {tp === "partiel" && Number(r.journal_montant_paye ?? r.montant_paye_initial) > 0 && (
                        <span className="text-xs text-muted-foreground ml-1">
                          (versé : {fmt(Number(r.journal_montant_paye ?? r.montant_paye_initial))} F)
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
