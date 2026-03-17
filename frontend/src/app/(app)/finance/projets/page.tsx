"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ChevronDown, ChevronRight, Plus, X } from "lucide-react";

interface DepotDepense {
  id: number;
  montant: string;
  description: string;
  date: string;
}

interface Projet {
  id: number;
  nom: string;
  description: string;
  budget_initial: string;
  total_depots: string;
  total_depenses: string;
  budget_restant: string;
  statut: string;
  statut_display: string;
  date_debut: string;
  date_fin: string | null;
  created_at: string;
  depenses: DepotDepense[];
  depots: DepotDepense[];
}

interface Paginated<T> { results: T[]; count?: number; }
function toList<T>(data: Paginated<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.results;
}

function StatutBadge({ statut, label }: { statut: string; label: string }) {
  const cls =
    statut === "actif" ? "bg-blue-100 text-blue-800" :
    statut === "suspendu" ? "bg-yellow-100 text-yellow-800" :
    statut === "termine" ? "bg-green-100 text-green-800" :
    statut === "annule" ? "bg-gray-100 text-gray-600" :
    "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

const STATUT_OPTIONS = [
  { value: "actif", label: "Actif" },
  { value: "suspendu", label: "Suspendu" },
  { value: "termine", label: "Terminé" },
  { value: "annule", label: "Annulé" },
];

const emptyProjetForm = {
  nom: "",
  description: "",
  budget_initial: "",
  date_debut: new Date().toISOString().slice(0, 10),
  date_fin: "",
};

const emptyMontantForm = {
  montant: "",
  description: "",
  date: new Date().toISOString().slice(0, 10),
};

type ActionType = "depense" | "depot" | "statut" | null;
interface ActiveAction {
  type: ActionType;
  projet: Projet;
}

export default function ProjetsPage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [projets, setProjets] = useState<Projet[]>([]);
  const [form, setForm] = useState(emptyProjetForm);
  const [showForm, setShowForm] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  const [activeAction, setActiveAction] = useState<ActiveAction | null>(null);
  const [actionForm, setActionForm] = useState(emptyMontantForm);
  const [newStatut, setNewStatut] = useState("actif");
  const [actionSubmitting, setActionSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiFetch<Paginated<Projet> | Projet[]>("/finance/projets/");
      setProjets(toList(res));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleChange =
    (field: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
      setError(null);
      setSuccess(null);
    };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.nom.trim() || !form.budget_initial || !form.date_debut) {
      setError("Nom, budget initial et date de début sont obligatoires.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const payload: Record<string, unknown> = {
        nom: form.nom,
        budget_initial: form.budget_initial,
        date_debut: form.date_debut,
      };
      if (form.description) payload.description = form.description;
      if (form.date_fin) payload.date_fin = form.date_fin;
      const created = await apiFetch<Projet>("/finance/projets/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setProjets((prev) => [created, ...prev]);
      setSuccess("Projet créé.");
      setForm(emptyProjetForm);
      setShowForm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la création.");
    } finally {
      setSubmitting(false);
    }
  };

  const openAction = (type: "depense" | "depot" | "statut", projet: Projet) => {
    setActiveAction({ type, projet });
    setActionForm(emptyMontantForm);
    setNewStatut(projet.statut);
    setActionError(null);
  };

  const handleAction = async () => {
    if (!activeAction) return;
    const { type, projet } = activeAction;

    if (type === "statut") {
      setActionSubmitting(true);
      setActionError(null);
      try {
        const updated = await apiFetch<Projet>(`/finance/projets/${projet.id}/changer_statut/`, {
          method: "PATCH",
          body: JSON.stringify({ statut: newStatut }),
        });
        setProjets((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
        setActiveAction(null);
        setSuccess("Statut mis à jour.");
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Erreur.");
      } finally {
        setActionSubmitting(false);
      }
      return;
    }

    if (!actionForm.montant || !actionForm.description.trim() || !actionForm.date) {
      setActionError("Montant, description et date sont obligatoires.");
      return;
    }
    setActionSubmitting(true);
    setActionError(null);
    try {
      const endpoint = type === "depense"
        ? `/finance/projets/${projet.id}/depense/`
        : `/finance/projets/${projet.id}/depot/`;
      const updated = await apiFetch<Projet>(endpoint, {
        method: "POST",
        body: JSON.stringify({
          montant: actionForm.montant,
          description: actionForm.description,
          date: actionForm.date,
        }),
      });
      setProjets((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setActiveAction(null);
      setSuccess(type === "depense" ? "Dépense ajoutée." : "Dépôt ajouté.");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Erreur.");
    } finally {
      setActionSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projets</h1>
          <p className="mt-1 text-sm text-muted-foreground">Suivi budgétaire des projets.</p>
        </div>
        <Button className="h-9 gap-1" onClick={() => setShowForm((v) => !v)}>
          <Plus className="h-4 w-4" />
          Nouveau projet
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>Nouveau projet</CardTitle>
            <CardDescription>Créer un projet avec budget initial.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label>Nom *</Label>
                <Input value={form.nom} onChange={handleChange("nom")} placeholder="Nom du projet" className="h-9" />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label>Description</Label>
                <Input value={form.description} onChange={handleChange("description")} placeholder="Description optionnelle" className="h-9" />
              </div>
              <div className="space-y-2">
                <Label>Budget initial *</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.budget_initial}
                  onChange={handleChange("budget_initial")}
                  className="h-9"
                />
              </div>
              <div className="space-y-2">
                <Label>Date de début *</Label>
                <Input type="date" value={form.date_debut} onChange={handleChange("date_debut")} className="h-9" />
              </div>
              <div className="space-y-2">
                <Label>Date de fin prévue</Label>
                <Input type="date" value={form.date_fin} onChange={handleChange("date_fin")} className="h-9" />
              </div>
              <div className="sm:col-span-2 flex flex-col gap-2">
                {error && <p className="text-sm text-destructive">{error}</p>}
                {success && <p className="text-sm text-emerald-600">{success}</p>}
                <div className="flex gap-2">
                  <Button type="submit" className="h-9" disabled={submitting || loading}>
                    {submitting ? "Création..." : "Créer"}
                  </Button>
                  <Button type="button" variant="outline" className="h-9" onClick={() => setShowForm(false)}>
                    Annuler
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {!showForm && success && <p className="text-sm text-emerald-600">{success}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Liste des projets</CardTitle>
          <CardDescription>{projets.length} projet(s).</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : projets.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun projet.</p>
          ) : (
            <div className="space-y-3">
              {projets.map((projet) => {
                const pct = Number(projet.budget_initial) > 0
                  ? Math.min(100, (Number(projet.total_depenses) / Number(projet.budget_initial)) * 100)
                  : 0;
                const overBudget = Number(projet.total_depenses) > Number(projet.budget_initial);
                return (
                  <div key={projet.id} className="border rounded-lg overflow-hidden">
                    <div
                      className="flex items-start justify-between gap-2 p-3 cursor-pointer hover:bg-muted/20"
                      onClick={() => setExpanded(expanded === projet.id ? null : projet.id)}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {expanded === projet.id
                          ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                          : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="font-medium text-sm">{projet.nom}</p>
                            <StatutBadge statut={projet.statut} label={projet.statut_display} />
                            {overBudget && (
                              <span className="inline-block rounded-full px-2 py-0.5 text-xs font-medium bg-red-100 text-red-800">
                                Dépassement
                              </span>
                            )}
                          </div>
                          {projet.description && (
                            <p className="text-xs text-muted-foreground truncate mt-0.5">{projet.description}</p>
                          )}
                          {/* Progress bar */}
                          <div className="mt-2 space-y-0.5">
                            <div className="flex justify-between text-xs text-muted-foreground">
                              <span>Dépenses: {fmt(projet.total_depenses)} FCFA</span>
                              <span>{pct.toFixed(0)}%</span>
                            </div>
                            <div className="w-full bg-muted rounded-full h-1.5">
                              <div
                                className={`h-1.5 rounded-full ${overBudget ? "bg-red-500" : "bg-blue-500"}`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="text-right shrink-0 space-y-0.5">
                        <p className="text-sm font-semibold">{fmt(projet.budget_restant)} FCFA</p>
                        <p className="text-xs text-muted-foreground">/ {fmt(projet.budget_initial)} FCFA budget</p>
                      </div>
                    </div>

                    {expanded === projet.id && (
                      <div className="border-t p-3 bg-muted/10 space-y-4">
                        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                          <span>Total dépôts: {fmt(projet.total_depots)} FCFA</span>
                          <span>Début: {projet.date_debut}</span>
                          {projet.date_fin && <span>Fin: {projet.date_fin}</span>}
                        </div>

                        {/* Dépôts */}
                        {projet.depots.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold mb-1 text-muted-foreground uppercase tracking-wide">Dépôts</p>
                            <div className="overflow-x-auto">
                              <table className="w-full min-w-[320px] text-xs">
                                <thead>
                                  <tr className="border-b bg-muted/30">
                                    <th className="text-left py-1.5 px-2">Date</th>
                                    <th className="text-right py-1.5 px-2">Montant</th>
                                    <th className="text-left py-1.5 px-2">Description</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {projet.depots.map((d) => (
                                    <tr key={d.id} className="border-b hover:bg-muted/20">
                                      <td className="py-1 px-2">{d.date}</td>
                                      <td className="py-1 px-2 text-right text-emerald-700">{fmt(d.montant)} FCFA</td>
                                      <td className="py-1 px-2 text-muted-foreground">{d.description}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {/* Dépenses */}
                        {projet.depenses.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold mb-1 text-muted-foreground uppercase tracking-wide">Dépenses</p>
                            <div className="overflow-x-auto">
                              <table className="w-full min-w-[320px] text-xs">
                                <thead>
                                  <tr className="border-b bg-muted/30">
                                    <th className="text-left py-1.5 px-2">Date</th>
                                    <th className="text-right py-1.5 px-2">Montant</th>
                                    <th className="text-left py-1.5 px-2">Description</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {projet.depenses.map((d) => (
                                    <tr key={d.id} className="border-b hover:bg-muted/20">
                                      <td className="py-1 px-2">{d.date}</td>
                                      <td className="py-1 px-2 text-right text-red-600">{fmt(d.montant)} FCFA</td>
                                      <td className="py-1 px-2 text-muted-foreground">{d.description}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        <div className="flex flex-wrap gap-2">
                          <Button size="sm" className="h-8 text-xs" onClick={() => openAction("depot", projet)}>
                            Ajouter dépôt
                          </Button>
                          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => openAction("depense", projet)}>
                            Ajouter dépense
                          </Button>
                          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => openAction("statut", projet)}>
                            Changer statut
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Action Modal */}
      {activeAction && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setActiveAction(null)}
        >
          <Card className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">
                {activeAction.type === "depense" && "Ajouter une dépense"}
                {activeAction.type === "depot" && "Ajouter un dépôt"}
                {activeAction.type === "statut" && "Changer le statut"}
                {" — "}{activeAction.projet.nom}
              </CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setActiveAction(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {actionError && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{actionError}</p>
              )}

              {activeAction.type === "statut" ? (
                <div className="space-y-1.5">
                  <Label>Nouveau statut</Label>
                  <select
                    value={newStatut}
                    onChange={(e) => setNewStatut(e.target.value)}
                    className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                  >
                    {STATUT_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <Label>Montant *</Label>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={actionForm.montant}
                      onChange={(e) => setActionForm((p) => ({ ...p, montant: e.target.value }))}
                      className="h-9"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Description *</Label>
                    <Input
                      value={actionForm.description}
                      onChange={(e) => setActionForm((p) => ({ ...p, description: e.target.value }))}
                      className="h-9"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Date *</Label>
                    <Input
                      type="date"
                      value={actionForm.date}
                      onChange={(e) => setActionForm((p) => ({ ...p, date: e.target.value }))}
                      className="h-9"
                    />
                  </div>
                </>
              )}

              <div className="flex gap-2 pt-1">
                <Button className="flex-1 h-9" onClick={handleAction} disabled={actionSubmitting}>
                  {actionSubmitting ? "Traitement..." : "Confirmer"}
                </Button>
                <Button variant="outline" className="h-9" onClick={() => setActiveAction(null)}>
                  Annuler
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
