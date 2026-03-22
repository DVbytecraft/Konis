"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { Truck, RefreshCw, Plus, X, Banknote, AlertCircle, Calendar } from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Lieu {
  id: number;
  nom: string;
  type_lieu_raw?: string;
}

interface Collecte {
  id: number;
  lieu: number;
  lieu_nom: string;
  collecteur_nom?: string;
  date_collecte: string;
  montant_trouve: string;
  montant_pris: string;
  montant_laisse: string;
  notes: string;
  depot_banque?: { montant: string; description: string } | null;
  created_at: string;
}

interface Paginated<T> { results: T[]; count?: number; }
function toList<T>(d: Paginated<T> | T[]): T[] {
  return Array.isArray(d) ? d : d.results;
}

const EMPTY_FORM = {
  lieu_id:          "",
  date_collecte:    new Date().toISOString().slice(0, 10),
  montant_trouve:   "",
  montant_pris:     "",
  notes:            "",
  deposer_en_banque: false,
};

function genKey() {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

function monthBounds(offset = 0) {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth() + offset;
  const first = new Date(y, m, 1);
  const last  = new Date(y, m + 1, 0);
  return {
    debut: first.toISOString().slice(0, 10),
    fin:   last.toISOString().slice(0, 10),
  };
}

export default function CollectesPage() {
  const [collectes, setCollectes]   = useState<Collecte[]>([]);
  const [lieux, setLieux]           = useState<Lieu[]>([]);
  const [loading, setLoading]       = useState(true);
  const [erreur, setErreur]         = useState("");
  const [showForm, setShowForm]     = useState(false);
  const [form, setForm]             = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formErr, setFormErr]       = useState("");
  const [idemKey, setIdemKey]       = useState("");

  // Filtres date
  const [debut, setDebut] = useState(monthBounds().debut);
  const [fin,   setFin]   = useState(monthBounds().fin);

  const charger = useCallback(async () => {
    try {
      setLoading(true);
      setErreur("");
      const params = new URLSearchParams();
      if (debut) params.set("debut", debut);
      if (fin)   params.set("fin",   fin);
      const qs = params.toString() ? `?${params}` : "";
      const [collectesRes, lieuxRes] = await Promise.all([
        apiFetch<Paginated<Collecte> | Collecte[]>(`/finance/collectes/${qs}`),
        apiFetch<Paginated<Lieu> | Lieu[]>("/locations/by-type/?type=magasin"),
      ]);
      setCollectes(toList(collectesRes));
      setLieux(toList(lieuxRes));
    } catch {
      setErreur("Impossible de charger les données.");
    } finally {
      setLoading(false);
    }
  }, [debut, fin]);

  useEffect(() => { charger(); }, [charger]);

  // Calcul montant_laisse en temps réel
  const montantLaisse = (() => {
    const t = parseFloat(form.montant_trouve);
    const p = parseFloat(form.montant_pris);
    if (isNaN(t) || isNaN(p)) return null;
    return Math.max(0, t - p);
  })();

  const ouvrirForm = () => {
    setForm(EMPTY_FORM);
    setFormErr("");
    setIdemKey(genKey());
    setShowForm(true);
  };

  const soumettre = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormErr("");
    if (!form.lieu_id) { setFormErr("Sélectionnez une boutique."); return; }
    const trouve = parseFloat(form.montant_trouve);
    const pris   = parseFloat(form.montant_pris);
    if (isNaN(trouve) || trouve < 0) { setFormErr("Montant trouvé invalide."); return; }
    if (isNaN(pris) || pris < 0)     { setFormErr("Montant pris invalide."); return; }
    if (pris > trouve)               { setFormErr("Le montant pris ne peut pas dépasser le montant trouvé."); return; }
    setSubmitting(true);
    try {
      await apiFetch("/finance/collectes/", {
        method: "POST",
        headers: { "Idempotency-Key": idemKey },
        body: JSON.stringify({
          lieu_id:           parseInt(form.lieu_id),
          date_collecte:     form.date_collecte,
          montant_trouve:    form.montant_trouve,
          montant_pris:      form.montant_pris,
          notes:             form.notes,
          deposer_en_banque: form.deposer_en_banque,
        }),
      });
      setShowForm(false);
      charger();
    } catch (e) {
      setFormErr(e instanceof Error ? e.message : "Erreur d'enregistrement.");
    } finally {
      setSubmitting(false);
    }
  };

  const totalPris   = collectes.reduce((a, c) => a + parseFloat(c.montant_pris),   0);
  const totalTrouve = collectes.reduce((a, c) => a + parseFloat(c.montant_trouve), 0);
  const totalLaisse = collectes.reduce((a, c) => a + parseFloat(c.montant_laisse), 0);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Truck className="h-6 w-6 text-blue-500" />
            Collectes
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Passages du collectionneur — montant trouvé, prélevé et laissé en caisse
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={charger}>
            <RefreshCw className="h-4 w-4 mr-2" /> Actualiser
          </Button>
          <Button size="sm" onClick={ouvrirForm} className="bg-blue-600 hover:bg-blue-700 text-white">
            <Plus className="h-4 w-4 mr-2" /> Enregistrer collecte
          </Button>
        </div>
      </div>

      {/* Filtres date */}
      <div className="flex items-end gap-3 flex-wrap">
        <Calendar className="h-4 w-4 text-muted-foreground mb-2 shrink-0" />
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Du</label>
          <Input type="date" value={debut} onChange={(e) => setDebut(e.target.value)} className="h-8 text-sm w-36" />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Au</label>
          <Input type="date" value={fin} onChange={(e) => setFin(e.target.value)} className="h-8 text-sm w-36" />
        </div>
        <div className="flex gap-1 mb-0.5">
          <Button variant="outline" size="sm" className="h-8 text-xs"
            onClick={() => { setDebut(new Date().toISOString().slice(0,10)); setFin(new Date().toISOString().slice(0,10)); }}>
            Aujourd&apos;hui
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs"
            onClick={() => { const b = monthBounds(); setDebut(b.debut); setFin(b.fin); }}>
            Ce mois
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs"
            onClick={() => { setDebut(""); setFin(""); }}>
            Tout
          </Button>
        </div>
      </div>

      {/* KPI synthèse */}
      {collectes.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <Card className="border-l-4 border-l-blue-400">
            <CardContent className="pt-4 pb-4 px-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Trouvé (total)</p>
              <p className="text-xl font-bold text-blue-700 dark:text-blue-300">{fmt(totalTrouve)}</p>
              <p className="text-xs text-muted-foreground">FCFA</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-green-400">
            <CardContent className="pt-4 pb-4 px-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Collecté</p>
              <p className="text-xl font-bold text-green-700 dark:text-green-300">{fmt(totalPris)}</p>
              <p className="text-xs text-muted-foreground">FCFA emportés</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-amber-400">
            <CardContent className="pt-4 pb-4 px-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Laissé en caisse</p>
              <p className="text-xl font-bold text-amber-700 dark:text-amber-300">{fmt(totalLaisse)}</p>
              <p className="text-xs text-muted-foreground">FCFA restants</p>
            </CardContent>
          </Card>
        </div>
      )}

      {erreur && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{erreur}</p>
      )}

      {/* Liste */}
      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : collectes.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Truck className="h-8 w-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">Aucune collecte enregistrée.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm min-w-[700px]">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left py-2 px-3">Boutique</th>
                <th className="text-left py-2 px-3">Date</th>
                <th className="text-right py-2 px-3">Trouvé</th>
                <th className="text-right py-2 px-3">Collecté</th>
                <th className="text-right py-2 px-3">Laissé</th>
                <th className="text-left py-2 px-3">Banque</th>
                <th className="text-left py-2 px-3">Notes</th>
              </tr>
            </thead>
            <tbody>
              {collectes.map((c) => {
                const laisse = parseFloat(c.montant_laisse);
                return (
                  <tr key={c.id} className="border-b hover:bg-muted/20">
                    <td className="py-2 px-3 font-medium">{c.lieu_nom}</td>
                    <td className="py-2 px-3 text-muted-foreground">
                      {new Date(c.date_collecte).toLocaleDateString("fr-FR")}
                    </td>
                    <td className="py-2 px-3 text-right font-mono">
                      {fmt(parseFloat(c.montant_trouve))}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-green-600">
                      {fmt(parseFloat(c.montant_pris))}
                    </td>
                    <td className={cn(
                      "py-2 px-3 text-right font-mono font-semibold",
                      laisse > 0 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
                    )}>
                      {fmt(laisse)}
                    </td>
                    <td className="py-2 px-3">
                      {c.depot_banque ? (
                        <span className="flex items-center gap-1 text-xs text-green-600">
                          <Banknote className="h-3.5 w-3.5" />
                          Déposé
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-muted-foreground text-xs truncate max-w-[140px]">
                      {c.notes || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal formulaire */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <Card className="w-full max-w-md">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-base">Nouvelle collecte</CardTitle>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded p-1 hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <CardContent>
              <form onSubmit={soumettre} className="space-y-3">
                {formErr && (
                  <div className="flex items-center gap-2 bg-destructive/10 text-destructive text-sm px-3 py-2 rounded">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    {formErr}
                  </div>
                )}

                <div className="space-y-1">
                  <label className="text-xs font-medium">Boutique *</label>
                  <select
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                    value={form.lieu_id}
                    onChange={(e) => setForm((f) => ({ ...f, lieu_id: e.target.value }))}
                  >
                    <option value="">Sélectionner une boutique…</option>
                    {lieux.map((l) => (
                      <option key={l.id} value={l.id}>{l.nom}</option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-medium">Date *</label>
                  <Input
                    type="date"
                    value={form.date_collecte}
                    onChange={(e) => setForm((f) => ({ ...f, date_collecte: e.target.value }))}
                    className="h-9"
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="text-xs font-medium">Montant trouvé (FCFA) *</label>
                    <Input
                      type="number" min="0" step="1"
                      placeholder="Ex : 150 000"
                      value={form.montant_trouve}
                      onChange={(e) => setForm((f) => ({ ...f, montant_trouve: e.target.value }))}
                      className="h-9"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium">Montant collecté (FCFA) *</label>
                    <Input
                      type="number" min="0" step="1"
                      placeholder="Ex : 100 000"
                      value={form.montant_pris}
                      onChange={(e) => setForm((f) => ({ ...f, montant_pris: e.target.value }))}
                      className="h-9"
                    />
                  </div>
                </div>

                {/* Montant laissé — calculé automatiquement */}
                {montantLaisse !== null && (
                  <div className="flex items-center justify-between bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded px-3 py-2">
                    <span className="text-xs font-medium text-amber-700 dark:text-amber-300">
                      Montant laissé en caisse
                    </span>
                    <span className="text-sm font-bold text-amber-700 dark:text-amber-300">
                      {fmt(montantLaisse)} FCFA
                    </span>
                  </div>
                )}

                <div className="space-y-1">
                  <label className="text-xs font-medium">Notes (optionnel)</label>
                  <Input
                    placeholder="Observations…"
                    value={form.notes}
                    onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                    className="h-9"
                  />
                </div>

                {/* Dépôt en banque */}
                <label className="flex items-center gap-2.5 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={form.deposer_en_banque}
                    onChange={(e) => setForm((f) => ({ ...f, deposer_en_banque: e.target.checked }))}
                    className="h-4 w-4 rounded border-input"
                  />
                  <span className="text-sm">
                    Déposer le montant collecté en banque (caisse suprême)
                  </span>
                </label>

                <div className="flex gap-2 pt-1">
                  <Button
                    type="submit"
                    className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
                    disabled={submitting}
                  >
                    {submitting ? "Enregistrement…" : "Confirmer"}
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setShowForm(false)}>
                    Annuler
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
