"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  Truck, RefreshCw, Plus, X, Banknote, AlertCircle,
  CheckCircle2, Pencil, ChevronDown, ChevronUp,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Lieu { id: number; nom: string }

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
  depot_banque_id?: number | null;
  created_at: string;
}

interface Paginated<T> { results: T[]; count?: number }
function toList<T>(d: Paginated<T> | T[]): T[] {
  return Array.isArray(d) ? d : d.results;
}

// ─── Formulaire création ──────────────────────────────────────────────────────

const EMPTY_CREATE = {
  lieu_id: "", date_collecte: new Date().toISOString().slice(0, 10),
  montant_trouve: "", montant_pris: "", notes: "", deposer_en_banque: false,
};

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CollecteurPage() {
  const [collectes, setCollectes]   = useState<Collecte[]>([]);
  const [lieux, setLieux]           = useState<Lieu[]>([]);
  const [loading, setLoading]       = useState(true);
  const [erreur, setErreur]         = useState("");
  const [success, setSuccess]       = useState("");

  // Formulaire création
  const [showCreate, setShowCreate]     = useState(false);
  const [createForm, setCreateForm]     = useState(EMPTY_CREATE);
  const [createErr, setCreateErr]       = useState("");
  const [creating, setCreating]         = useState(false);

  // Formulaire correction
  const [editTarget, setEditTarget]     = useState<Collecte | null>(null);
  const [editForm, setEditForm]         = useState({ montant_trouve: "", montant_pris: "", notes: "" });
  const [editErr, setEditErr]           = useState("");
  const [editing, setEditing]           = useState(false);

  // Vue par boutique (toggle)
  const [viewByBoutique, setViewByBoutique] = useState(false);

  // ── Chargement ──────────────────────────────────────────────────────────────

  const charger = useCallback(async () => {
    try {
      setLoading(true);
      setErreur("");
      const [collectesRes, lieuxRes] = await Promise.all([
        apiFetch<Paginated<Collecte> | Collecte[]>("/finance/collectes/"),
        apiFetch<Paginated<Lieu> | Lieu[]>("/locations/by-type/?type=magasin"),
      ]);
      setCollectes(toList(collectesRes));
      setLieux(toList(lieuxRes));
    } catch {
      setErreur("Impossible de charger les données.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { charger(); }, [charger]);

  // ── Calculs ─────────────────────────────────────────────────────────────────

  const totalPris   = collectes.reduce((a, c) => a + parseFloat(c.montant_pris),   0);
  const totalTrouve = collectes.reduce((a, c) => a + parseFloat(c.montant_trouve), 0);
  const totalLaisse = collectes.reduce((a, c) => a + parseFloat(c.montant_laisse), 0);

  // Résumé groupé par boutique
  const resumeParBoutique = useMemo(() => {
    const map = new Map<number, { lieu_nom: string; trouve: number; pris: number; laisse: number; nb: number }>();
    for (const c of collectes) {
      const prev = map.get(c.lieu) ?? { lieu_nom: c.lieu_nom, trouve: 0, pris: 0, laisse: 0, nb: 0 };
      map.set(c.lieu, {
        lieu_nom: c.lieu_nom,
        trouve:   prev.trouve + parseFloat(c.montant_trouve),
        pris:     prev.pris   + parseFloat(c.montant_pris),
        laisse:   prev.laisse + parseFloat(c.montant_laisse),
        nb:       prev.nb + 1,
      });
    }
    return Array.from(map.values()).sort((a, b) => a.lieu_nom.localeCompare(b.lieu_nom));
  }, [collectes]);

  // Montant laissé en temps réel (formulaire création)
  const createLaisse = (() => {
    const t = parseFloat(createForm.montant_trouve);
    const p = parseFloat(createForm.montant_pris);
    if (isNaN(t) || isNaN(p)) return null;
    return Math.max(0, t - p);
  })();

  // Montant laissé en temps réel (formulaire correction)
  const editLaisse = editTarget ? (() => {
    const t = parseFloat(editForm.montant_trouve || editTarget.montant_trouve);
    const p = parseFloat(editForm.montant_pris   || editTarget.montant_pris);
    if (isNaN(t) || isNaN(p)) return null;
    return Math.max(0, t - p);
  })() : null;

  // ── Actions ─────────────────────────────────────────────────────────────────

  const flashSuccess = (msg: string) => {
    setSuccess(msg);
    setTimeout(() => setSuccess(""), 4000);
  };

  const soumettre = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateErr("");
    if (!createForm.lieu_id) { setCreateErr("Sélectionnez une boutique."); return; }
    const trouve = parseFloat(createForm.montant_trouve);
    const pris   = parseFloat(createForm.montant_pris);
    if (isNaN(trouve) || trouve < 0) { setCreateErr("Montant trouvé invalide."); return; }
    if (isNaN(pris)   || pris   < 0) { setCreateErr("Montant collecté invalide."); return; }
    if (pris > trouve)               { setCreateErr("Le montant collecté ne peut pas dépasser le montant trouvé."); return; }
    setCreating(true);
    try {
      await apiFetch("/finance/collectes/", {
        method: "POST",
        body: JSON.stringify({
          lieu_id:           parseInt(createForm.lieu_id),
          date_collecte:     createForm.date_collecte,
          montant_trouve:    createForm.montant_trouve,
          montant_pris:      createForm.montant_pris,
          notes:             createForm.notes,
          deposer_en_banque: createForm.deposer_en_banque,
        }),
      });
      setShowCreate(false);
      setCreateForm(EMPTY_CREATE);
      flashSuccess("Collecte enregistrée avec succès.");
      charger();
    } catch (err) {
      setCreateErr(err instanceof Error ? err.message : "Erreur d'enregistrement.");
    } finally {
      setCreating(false);
    }
  };

  const ouvrirCorrection = (c: Collecte) => {
    setEditTarget(c);
    setEditForm({ montant_trouve: c.montant_trouve, montant_pris: c.montant_pris, notes: c.notes });
    setEditErr("");
  };

  const soumettreCorrection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editTarget) return;
    setEditErr("");
    const payload: Record<string, string | number> = {};
    if (editForm.montant_trouve !== editTarget.montant_trouve) payload.montant_trouve = editForm.montant_trouve;
    if (editForm.montant_pris   !== editTarget.montant_pris)   payload.montant_pris   = editForm.montant_pris;
    if (editForm.notes          !== editTarget.notes)          payload.notes          = editForm.notes;
    if (Object.keys(payload).length === 0) { setEditTarget(null); return; }

    const trouve = parseFloat(editForm.montant_trouve);
    const pris   = parseFloat(editForm.montant_pris);
    if (!isNaN(trouve) && !isNaN(pris) && pris > trouve) {
      setEditErr("Le montant collecté ne peut pas dépasser le montant trouvé.");
      return;
    }
    setEditing(true);
    try {
      await apiFetch(`/finance/collectes/${editTarget.id}/`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      setEditTarget(null);
      flashSuccess("Correction enregistrée.");
      charger();
    } catch (err) {
      setEditErr(err instanceof Error ? err.message : "Erreur de correction.");
    } finally {
      setEditing(false);
    }
  };

  // ── Rendu ────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">

      {/* En-tête */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Truck className="h-6 w-6 text-blue-500" />
            Mes collectes
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Enregistrez vos passages en boutique et corrigez si nécessaire
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={charger} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4 mr-2", loading && "animate-spin")} />
            Actualiser
          </Button>
          <Button size="sm" onClick={() => { setCreateForm(EMPTY_CREATE); setCreateErr(""); setShowCreate(true); }}
            className="bg-blue-600 hover:bg-blue-700 text-white">
            <Plus className="h-4 w-4 mr-2" /> Nouvelle collecte
          </Button>
        </div>
      </div>

      {/* Feedback */}
      {success && (
        <div className="flex items-center gap-2 bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 text-sm px-4 py-2.5 rounded-lg">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          {success}
        </div>
      )}
      {erreur && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{erreur}</p>
      )}

      {/* KPIs */}
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

      {/* Toggle vue */}
      {collectes.length > 0 && (
        <button
          onClick={() => setViewByBoutique((v) => !v)}
          className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          {viewByBoutique ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          {viewByBoutique ? "Voir la liste chronologique" : "Voir le résumé par boutique"}
        </button>
      )}

      {/* Résumé par boutique */}
      {viewByBoutique && resumeParBoutique.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left py-2 px-3">Boutique</th>
                <th className="text-right py-2 px-3">Passages</th>
                <th className="text-right py-2 px-3">Trouvé</th>
                <th className="text-right py-2 px-3">Collecté</th>
                <th className="text-right py-2 px-3">Laissé</th>
              </tr>
            </thead>
            <tbody>
              {resumeParBoutique.map((row) => (
                <tr key={row.lieu_nom} className="border-b hover:bg-muted/20">
                  <td className="py-2 px-3 font-medium">{row.lieu_nom}</td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{row.nb}</td>
                  <td className="py-2 px-3 text-right font-mono">{fmt(row.trouve)}</td>
                  <td className="py-2 px-3 text-right font-mono text-blue-700 dark:text-blue-300 font-semibold">{fmt(row.pris)}</td>
                  <td className={cn(
                    "py-2 px-3 text-right font-mono font-semibold",
                    row.laisse > 0 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
                  )}>
                    {fmt(row.laisse)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Liste chronologique */}
      {!viewByBoutique && (
        loading ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : collectes.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <Truck className="h-10 w-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Aucune collecte enregistrée.</p>
            <p className="text-xs mt-1">Cliquez sur « Nouvelle collecte » pour commencer.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm min-w-[750px]">
              <thead>
                <tr className="border-b bg-muted/30">
                  <th className="text-left py-2 px-3">Boutique</th>
                  <th className="text-left py-2 px-3">Date</th>
                  <th className="text-right py-2 px-3">Trouvé</th>
                  <th className="text-right py-2 px-3">Collecté</th>
                  <th className="text-right py-2 px-3">Laissé</th>
                  <th className="text-left py-2 px-3">Banque</th>
                  <th className="text-left py-2 px-3">Notes</th>
                  <th className="text-center py-2 px-3">Action</th>
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
                      <td className="py-2 px-3 text-right font-mono">{fmt(parseFloat(c.montant_trouve))}</td>
                      <td className="py-2 px-3 text-right font-mono text-blue-700 dark:text-blue-300 font-semibold">
                        {fmt(parseFloat(c.montant_pris))}
                      </td>
                      <td className={cn(
                        "py-2 px-3 text-right font-mono font-semibold",
                        laisse > 0 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
                      )}>
                        {fmt(laisse)}
                      </td>
                      <td className="py-2 px-3">
                        {c.depot_banque_id ? (
                          <span className="flex items-center gap-1 text-xs text-green-600">
                            <Banknote className="h-3.5 w-3.5" />Déposé
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-2 px-3 text-muted-foreground text-xs truncate max-w-[120px]">
                        {c.notes || "—"}
                      </td>
                      <td className="py-2 px-3 text-center">
                        <button
                          onClick={() => ouvrirCorrection(c)}
                          className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
                          title="Corriger"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* ── Modal création ─────────────────────────────────────────────────── */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <Card className="w-full max-w-md">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Truck className="h-4 w-4 text-blue-500" />
                Nouvelle collecte
              </CardTitle>
              <button type="button" onClick={() => setShowCreate(false)} className="rounded p-1 hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <CardContent>
              <form onSubmit={soumettre} className="space-y-3">
                {createErr && (
                  <div className="flex items-center gap-2 bg-destructive/10 text-destructive text-sm px-3 py-2 rounded">
                    <AlertCircle className="h-4 w-4 shrink-0" />{createErr}
                  </div>
                )}

                <div className="space-y-1">
                  <label className="text-xs font-medium">Boutique *</label>
                  <select
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                    value={createForm.lieu_id}
                    onChange={(e) => setCreateForm((f) => ({ ...f, lieu_id: e.target.value }))}
                  >
                    <option value="">Sélectionner une boutique…</option>
                    {lieux.map((l) => <option key={l.id} value={l.id}>{l.nom}</option>)}
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-medium">Date *</label>
                  <Input type="date" value={createForm.date_collecte}
                    onChange={(e) => setCreateForm((f) => ({ ...f, date_collecte: e.target.value }))}
                    className="h-9" />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="text-xs font-medium">Montant trouvé (FCFA) *</label>
                    <Input type="number" min="0" step="1" placeholder="Ex : 150 000"
                      value={createForm.montant_trouve}
                      onChange={(e) => setCreateForm((f) => ({ ...f, montant_trouve: e.target.value }))}
                      className="h-9" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium">Montant collecté (FCFA) *</label>
                    <Input type="number" min="0" step="1" placeholder="Ex : 100 000"
                      value={createForm.montant_pris}
                      onChange={(e) => setCreateForm((f) => ({ ...f, montant_pris: e.target.value }))}
                      className="h-9" />
                  </div>
                </div>

                {createLaisse !== null && (
                  <div className="flex items-center justify-between bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded px-3 py-2">
                    <span className="text-xs font-medium text-amber-700 dark:text-amber-300">Laissé en caisse</span>
                    <span className="text-sm font-bold text-amber-700 dark:text-amber-300">{fmt(createLaisse)} FCFA</span>
                  </div>
                )}

                <div className="space-y-1">
                  <label className="text-xs font-medium">Notes (optionnel)</label>
                  <Input placeholder="Observations, signature…"
                    value={createForm.notes}
                    onChange={(e) => setCreateForm((f) => ({ ...f, notes: e.target.value }))}
                    className="h-9" />
                </div>

                <label className="flex items-center gap-2.5 cursor-pointer select-none">
                  <input type="checkbox" checked={createForm.deposer_en_banque}
                    onChange={(e) => setCreateForm((f) => ({ ...f, deposer_en_banque: e.target.checked }))}
                    className="h-4 w-4 rounded border-input" />
                  <span className="text-sm">Déposer le montant collecté en banque (caisse suprême)</span>
                </label>

                <div className="flex gap-2 pt-1">
                  <Button type="submit" className="flex-1 bg-blue-600 hover:bg-blue-700 text-white" disabled={creating}>
                    {creating ? "Enregistrement…" : "Confirmer la collecte"}
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setShowCreate(false)}>Annuler</Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Modal correction ────────────────────────────────────────────────── */}
      {editTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <Card className="w-full max-w-md">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Pencil className="h-4 w-4 text-orange-500" />
                Corriger la collecte
              </CardTitle>
              <button type="button" onClick={() => setEditTarget(null)} className="rounded p-1 hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-3">
                {editTarget.lieu_nom} — {new Date(editTarget.date_collecte).toLocaleDateString("fr-FR")}
              </p>

              {editTarget.depot_banque_id && (
                <div className="flex items-center gap-2 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 text-blue-700 dark:text-blue-300 text-xs px-3 py-2 rounded mb-3">
                  <Banknote className="h-3.5 w-3.5 shrink-0" />
                  Un dépôt banque est lié à cette collecte. Seules les notes peuvent être modifiées.
                </div>
              )}

              <form onSubmit={soumettreCorrection} className="space-y-3">
                {editErr && (
                  <div className="flex items-center gap-2 bg-destructive/10 text-destructive text-sm px-3 py-2 rounded">
                    <AlertCircle className="h-4 w-4 shrink-0" />{editErr}
                  </div>
                )}

                {!editTarget.depot_banque_id && (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium">Montant trouvé</label>
                      <Input type="number" min="0" step="1"
                        value={editForm.montant_trouve}
                        onChange={(e) => setEditForm((f) => ({ ...f, montant_trouve: e.target.value }))}
                        className="h-9" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium">Montant collecté</label>
                      <Input type="number" min="0" step="1"
                        value={editForm.montant_pris}
                        onChange={(e) => setEditForm((f) => ({ ...f, montant_pris: e.target.value }))}
                        className="h-9" />
                    </div>
                  </div>
                )}

                {!editTarget.depot_banque_id && editLaisse !== null && (
                  <div className="flex items-center justify-between bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded px-3 py-2">
                    <span className="text-xs font-medium text-amber-700 dark:text-amber-300">Laissé (recalculé)</span>
                    <span className="text-sm font-bold text-amber-700 dark:text-amber-300">{fmt(editLaisse)} FCFA</span>
                  </div>
                )}

                <div className="space-y-1">
                  <label className="text-xs font-medium">Notes</label>
                  <Input placeholder="Observations…"
                    value={editForm.notes}
                    onChange={(e) => setEditForm((f) => ({ ...f, notes: e.target.value }))}
                    className="h-9" />
                </div>

                <div className="flex gap-2 pt-1">
                  <Button type="submit" className="flex-1 bg-orange-500 hover:bg-orange-600 text-white" disabled={editing}>
                    {editing ? "Enregistrement…" : "Enregistrer la correction"}
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setEditTarget(null)}>Annuler</Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
