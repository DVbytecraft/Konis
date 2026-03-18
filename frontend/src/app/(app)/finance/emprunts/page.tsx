"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ChevronDown, ChevronRight, Plus, X } from "lucide-react";

interface Remboursement {
  id: number;
  montant: string;
  date: string;
  reference: string;
}

interface Emprunt {
  id: number;
  nom: string;
  banque: string;
  montant_initial: string;
  montant_rembourse: string;
  montant_restant: string;
  taux_interet: string | null;
  date_debut: string;
  date_echeance: string | null;
  statut: string;
  statut_display: string;
  notes: string;
  created_at: string;
  locked_at: string | null;
  remboursements: Remboursement[];
}

interface Paginated<T> { results: T[]; count?: number; }
function toList<T>(data: Paginated<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.results;
}

function StatutBadge({ statut, label }: { statut: string; label: string }) {
  const cls =
    statut === "en_cours" ? "bg-blue-100 text-blue-800" :
    statut === "rembourse" ? "bg-green-100 text-green-800" :
    "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

const emptyEmpruntForm = {
  nom: "",
  banque: "",
  montant_initial: "",
  date_debut: new Date().toISOString().slice(0, 10),
  taux_interet: "",
  date_echeance: "",
  notes: "",
};
const emptyRemboursementForm = {
  montant: "",
  date: new Date().toISOString().slice(0, 10),
  reference: "",
  notes: "",
};

export default function EmpruntsPage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [emprunts, setEmprunts] = useState<Emprunt[]>([]);
  const [form, setForm] = useState(emptyEmpruntForm);
  const [showForm, setShowForm] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  const [rembJournal, setRembJournal] = useState<Emprunt | null>(null);
  const [rembForm, setRembForm] = useState(emptyRemboursementForm);
  const [rembSubmitting, setRembSubmitting] = useState(false);
  const [rembError, setRembError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiFetch<Paginated<Emprunt> | Emprunt[]>("/finance/emprunts/");
      setEmprunts(toList(res));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleChange =
    (field: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
      setError(null);
      setSuccess(null);
    };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.nom.trim() || !form.banque.trim() || !form.montant_initial || !form.date_debut) {
      setError("Nom, banque, montant et date de début sont obligatoires.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const payload: Record<string, unknown> = {
        nom: form.nom,
        banque: form.banque,
        montant_initial: form.montant_initial,
        date_debut: form.date_debut,
      };
      if (form.taux_interet) payload.taux_interet = form.taux_interet;
      if (form.date_echeance) payload.date_echeance = form.date_echeance;
      if (form.notes) payload.notes = form.notes;
      const created = await apiFetch<Emprunt>("/finance/emprunts/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setEmprunts((prev) => [created, ...prev]);
      setSuccess("Emprunt enregistré.");
      setForm(emptyEmpruntForm);
      setShowForm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'enregistrement.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemboursement = async () => {
    if (!rembJournal) return;
    if (!rembForm.montant || !rembForm.date) {
      setRembError("Montant et date sont obligatoires.");
      return;
    }
    setRembSubmitting(true);
    setRembError(null);
    try {
      const payload: Record<string, unknown> = {
        montant: rembForm.montant,
        date: rembForm.date,
      };
      if (rembForm.reference) payload.reference = rembForm.reference;
      if (rembForm.notes) payload.notes = rembForm.notes;
      const updated = await apiFetch<Emprunt>(
        `/finance/emprunts/${rembJournal.id}/remboursement/`,
        { method: "POST", body: JSON.stringify(payload) }
      );
      setEmprunts((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      setRembJournal(null);
      setSuccess("Remboursement enregistré.");
    } catch (e) {
      setRembError(e instanceof Error ? e.message : "Erreur lors du remboursement.");
    } finally {
      setRembSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Emprunts</h1>
          <p className="mt-1 text-sm text-muted-foreground">Suivi des emprunts bancaires et remboursements.</p>
        </div>
        <Button className="h-9 gap-1" onClick={() => setShowForm((v) => !v)}>
          <Plus className="h-4 w-4" />
          Nouvel emprunt
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>Nouvel emprunt</CardTitle>
            <CardDescription>Enregistrer un emprunt auprès d&apos;une banque.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Nom *</Label>
                <Input value={form.nom} onChange={handleChange("nom")} placeholder="Ex: Prêt équipement 2026" className="h-9" />
              </div>
              <div className="space-y-2">
                <Label>Banque *</Label>
                <Input value={form.banque} onChange={handleChange("banque")} placeholder="Nom de la banque" className="h-9" />
              </div>
              <div className="space-y-2">
                <Label>Montant initial *</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.montant_initial}
                  onChange={handleChange("montant_initial")}
                  className="h-9"
                />
              </div>
              <div className="space-y-2">
                <Label>Date de début *</Label>
                <Input type="date" value={form.date_debut} onChange={handleChange("date_debut")} className="h-9" />
              </div>
              <div className="space-y-2">
                <Label>Taux d&apos;intérêt (%)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.taux_interet}
                  onChange={handleChange("taux_interet")}
                  placeholder="Ex: 5.5"
                  className="h-9"
                />
              </div>
              <div className="space-y-2">
                <Label>Date d&apos;échéance</Label>
                <Input type="date" value={form.date_echeance} onChange={handleChange("date_echeance")} className="h-9" />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label>Notes</Label>
                <Input value={form.notes} onChange={handleChange("notes")} className="h-9" />
              </div>
              <div className="sm:col-span-2 flex flex-col gap-2">
                {error && <p className="text-sm text-destructive">{error}</p>}
                {success && <p className="text-sm text-emerald-600">{success}</p>}
                <div className="flex gap-2">
                  <Button type="submit" className="h-9" disabled={submitting || loading}>
                    {submitting ? "Enregistrement..." : "Enregistrer"}
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
          <CardTitle>Liste des emprunts</CardTitle>
          <CardDescription>{emprunts.length} emprunt(s) enregistré(s).</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : emprunts.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun emprunt.</p>
          ) : (
            <div className="space-y-3">
              {emprunts.map((emprunt) => (
                <div key={emprunt.id} className="border rounded-lg overflow-hidden">
                  <div
                    className="flex items-start justify-between gap-2 p-3 cursor-pointer hover:bg-muted/20"
                    onClick={() => setExpanded(expanded === emprunt.id ? null : emprunt.id)}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {expanded === emprunt.id
                        ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                        : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
                      <div className="min-w-0">
                        <p className="font-medium text-sm truncate">{emprunt.nom}</p>
                        <p className="text-xs text-muted-foreground truncate">{emprunt.banque}</p>
                        <p className="text-xs text-muted-foreground">Depuis le {emprunt.date_debut}</p>
                      </div>
                    </div>
                    <div className="text-right shrink-0 space-y-1">
                      <StatutBadge statut={emprunt.statut} label={emprunt.statut_display} />
                      <p className="text-sm font-semibold">{fmt(emprunt.montant_restant)} FCFA restants</p>
                      <p className="text-xs text-muted-foreground">/ {fmt(emprunt.montant_initial)} FCFA</p>
                    </div>
                  </div>

                  {expanded === emprunt.id && (
                    <div className="border-t p-3 bg-muted/10 space-y-3">
                      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                        <span>Remboursé: {fmt(emprunt.montant_rembourse)} FCFA</span>
                        {emprunt.taux_interet && <span>Taux: {emprunt.taux_interet}%</span>}
                        {emprunt.date_echeance && <span>Échéance: {emprunt.date_echeance}</span>}
                        {emprunt.notes && <span>Notes: {emprunt.notes}</span>}
                      </div>

                      {emprunt.remboursements.length > 0 && (
                        <div className="overflow-x-auto">
                          <table className="w-full min-w-[360px] text-xs">
                            <thead>
                              <tr className="border-b bg-muted/30">
                                <th className="text-left py-1.5 px-2">Date</th>
                                <th className="text-right py-1.5 px-2">Montant</th>
                                <th className="text-left py-1.5 px-2">Référence</th>
                              </tr>
                            </thead>
                            <tbody>
                              {emprunt.remboursements.map((r) => (
                                <tr key={r.id} className="border-b hover:bg-muted/20">
                                  <td className="py-1 px-2">{r.date}</td>
                                  <td className="py-1 px-2 text-right">{fmt(r.montant)} FCFA</td>
                                  <td className="py-1 px-2 text-muted-foreground">{r.reference || "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {emprunt.statut === "en_cours" && (
                        <Button
                          size="sm"
                          className="h-8 text-xs"
                          onClick={() => {
                            setRembJournal(emprunt);
                            setRembForm(emptyRemboursementForm);
                            setRembError(null);
                          }}
                        >
                          Enregistrer un remboursement
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Modal remboursement */}
      {rembJournal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setRembJournal(null)}
        >
          <Card className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">Remboursement — {rembJournal.nom}</CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setRembJournal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {rembError && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{rembError}</p>
              )}
              <div className="space-y-1.5">
                <Label>Montant *</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={rembForm.montant}
                  onChange={(e) => setRembForm((p) => ({ ...p, montant: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Date *</Label>
                <Input
                  type="date"
                  value={rembForm.date}
                  onChange={(e) => setRembForm((p) => ({ ...p, date: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Référence</Label>
                <Input
                  value={rembForm.reference}
                  onChange={(e) => setRembForm((p) => ({ ...p, reference: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Notes</Label>
                <Input
                  value={rembForm.notes}
                  onChange={(e) => setRembForm((p) => ({ ...p, notes: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <Button className="flex-1 h-9" onClick={handleRemboursement} disabled={rembSubmitting}>
                  {rembSubmitting ? "Enregistrement..." : "Confirmer"}
                </Button>
                <Button variant="outline" className="h-9" onClick={() => setRembJournal(null)}>
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
