"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ChevronDown, ChevronRight, Plus, X } from "lucide-react";

interface Paiement {
  id: number;
  montant: string;
  date: string;
  mode_paiement_display: string;
}

interface JournalCreance {
  id: number;
  client: number;
  client_nom: string;
  reference: string;
  description: string;
  montant_initial: string;
  montant_paye: string;
  montant_restant: string;
  statut: string;
  statut_display: string;
  date_echeance: string | null;
  notes: string;
  created_at: string;
  locked_at: string | null;
  paiements: Paiement[];
}

interface ClientFinance { id: number; nom: string; }

interface Paginated<T> { results: T[]; count?: number; }
function toList<T>(data: Paginated<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.results;
}

function StatutBadge({ statut, label }: { statut: string; label: string }) {
  const cls =
    statut === "ouvert" ? "bg-yellow-100 text-yellow-800" :
    statut === "solde" ? "bg-green-100 text-green-800" :
    statut === "en_retard" ? "bg-red-100 text-red-800" :
    "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

const MODE_OPTIONS = ["virement", "especes", "cheque", "mobile_money", "autre"];
const emptyJournalForm = {
  client_id: "",
  description: "",
  montant_initial: "",
  reference: "",
  date_echeance: "",
  notes: "",
};
const emptyPaiementForm = {
  montant: "",
  date: new Date().toISOString().slice(0, 10),
  mode_paiement: "virement",
  reference: "",
  notes: "",
};

export default function JournauxCreancesPage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [journaux, setJournaux] = useState<JournalCreance[]>([]);
  const [clients, setClients] = useState<ClientFinance[]>([]);
  const [form, setForm] = useState(emptyJournalForm);
  const [showForm, setShowForm] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  const [paiementJournal, setPaiementJournal] = useState<JournalCreance | null>(null);
  const [paiementForm, setPaiementForm] = useState(emptyPaiementForm);
  const [paiementSubmitting, setPaiementSubmitting] = useState(false);
  const [paiementError, setPaiementError] = useState<string | null>(null);

  const [solderJournal, setSolderJournal] = useState<JournalCreance | null>(null);
  const [solderSubmitting, setSolderSubmitting] = useState(false);
  const [solderError, setSolderError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [journauxRes, clientsRes] = await Promise.all([
        apiFetch<Paginated<JournalCreance> | JournalCreance[]>("/finance/journaux-creances/"),
        apiFetch<Paginated<ClientFinance> | ClientFinance[]>("/finance/clients/"),
      ]);
      setJournaux(toList(journauxRes));
      setClients(toList(clientsRes));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleChange =
    (field: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
      setError(null);
      setSuccess(null);
    };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.client_id || !form.description.trim() || !form.montant_initial) {
      setError("Client, description et montant sont obligatoires.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const payload: Record<string, unknown> = {
        client_id: Number(form.client_id),
        description: form.description,
        montant_initial: form.montant_initial,
      };
      if (form.reference) payload.reference = form.reference;
      if (form.date_echeance) payload.date_echeance = form.date_echeance;
      if (form.notes) payload.notes = form.notes;
      const created = await apiFetch<JournalCreance>("/finance/journaux-creances/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setJournaux((prev) => [created, ...prev]);
      setSuccess("Journal créé.");
      setForm(emptyJournalForm);
      setShowForm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la création.");
    } finally {
      setSubmitting(false);
    }
  };

  const handlePaiement = async () => {
    if (!paiementJournal) return;
    if (!paiementForm.montant || !paiementForm.date) {
      setPaiementError("Montant et date sont obligatoires.");
      return;
    }
    setPaiementSubmitting(true);
    setPaiementError(null);
    try {
      const payload: Record<string, unknown> = {
        montant: paiementForm.montant,
        date: paiementForm.date,
        mode_paiement: paiementForm.mode_paiement,
      };
      if (paiementForm.reference) payload.reference = paiementForm.reference;
      if (paiementForm.notes) payload.notes = paiementForm.notes;
      const updated = await apiFetch<JournalCreance>(
        `/finance/journaux-creances/${paiementJournal.id}/paiement/`,
        { method: "POST", body: JSON.stringify(payload) }
      );
      setJournaux((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));
      setPaiementJournal(null);
      setSuccess("Encaissement enregistré.");
    } catch (e) {
      setPaiementError(e instanceof Error ? e.message : "Erreur lors de l'encaissement.");
    } finally {
      setPaiementSubmitting(false);
    }
  };

  const handleSolder = async () => {
    if (!solderJournal) return;
    setSolderSubmitting(true);
    setSolderError(null);
    try {
      const updated = await apiFetch<JournalCreance>(
        `/finance/journaux-creances/${solderJournal.id}/solder/`,
        { method: "POST", body: JSON.stringify({}) }
      );
      setJournaux((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));
      setSolderJournal(null);
      setSuccess("Journal soldé.");
    } catch (e) {
      setSolderError(e instanceof Error ? e.message : "Erreur lors du solde.");
    } finally {
      setSolderSubmitting(false);
    }
  };

  const openPaiement = (j: JournalCreance) => {
    setPaiementJournal(j);
    setPaiementForm(emptyPaiementForm);
    setPaiementError(null);
  };

  return (
    <div className="space-y-8 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Journaux créances</h1>
          <p className="mt-1 text-sm text-muted-foreground">Montants dus par les clients.</p>
        </div>
        <Button className="h-9 gap-1" onClick={() => setShowForm((v) => !v)}>
          <Plus className="h-4 w-4" />
          Nouveau journal
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>Nouveau journal créance</CardTitle>
            <CardDescription>Enregistrer une nouvelle créance client.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Client *</Label>
                <select
                  value={form.client_id}
                  onChange={handleChange("client_id")}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="">Sélectionner...</option>
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>{c.nom}</option>
                  ))}
                </select>
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
              <div className="space-y-2 sm:col-span-2">
                <Label>Description *</Label>
                <Input value={form.description} onChange={handleChange("description")} placeholder="Description de la créance" className="h-9" />
              </div>
              <div className="space-y-2">
                <Label>Référence</Label>
                <Input value={form.reference} onChange={handleChange("reference")} placeholder="Ex: FACT-001" className="h-9" />
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
          <CardTitle>Liste des journaux</CardTitle>
          <CardDescription>{journaux.length} journal(ux) enregistré(s).</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : journaux.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun journal créance.</p>
          ) : (
            <div className="space-y-3">
              {journaux.map((j) => (
                <div key={j.id} className="border rounded-lg overflow-hidden">
                  <div
                    className="flex items-start justify-between gap-2 p-3 cursor-pointer hover:bg-muted/20"
                    onClick={() => setExpanded(expanded === j.id ? null : j.id)}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {expanded === j.id
                        ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                        : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
                      <div className="min-w-0">
                        <p className="font-medium text-sm truncate">{j.client_nom}</p>
                        <p className="text-xs text-muted-foreground truncate">{j.description}</p>
                        {j.reference && <p className="text-xs text-muted-foreground">Réf: {j.reference}</p>}
                      </div>
                    </div>
                    <div className="text-right shrink-0 space-y-1">
                      <StatutBadge statut={j.statut} label={j.statut_display} />
                      <p className="text-sm font-semibold text-emerald-700">{fmt(j.montant_restant)} FCFA restants</p>
                      <p className="text-xs text-muted-foreground">/ {fmt(j.montant_initial)} FCFA</p>
                    </div>
                  </div>

                  {expanded === j.id && (
                    <div className="border-t p-3 bg-muted/10 space-y-3">
                      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>Encaissé: {fmt(j.montant_paye)} FCFA</span>
                        {j.date_echeance && <span>Échéance: {j.date_echeance}</span>}
                        {j.notes && <span>Notes: {j.notes}</span>}
                      </div>

                      {j.paiements.length > 0 && (
                        <div className="overflow-x-auto">
                          <table className="w-full min-w-[360px] text-xs">
                            <thead>
                              <tr className="border-b bg-muted/30">
                                <th className="text-left py-1.5 px-2">Date</th>
                                <th className="text-right py-1.5 px-2">Montant</th>
                                <th className="text-left py-1.5 px-2">Mode</th>
                              </tr>
                            </thead>
                            <tbody>
                              {j.paiements.map((p) => (
                                <tr key={p.id} className="border-b hover:bg-muted/20">
                                  <td className="py-1 px-2">{p.date}</td>
                                  <td className="py-1 px-2 text-right">{fmt(p.montant)} FCFA</td>
                                  <td className="py-1 px-2 text-muted-foreground">{p.mode_paiement_display}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {j.statut === "ouvert" && (
                        <div className="flex flex-wrap gap-2">
                          <Button size="sm" className="h-8 text-xs" onClick={() => openPaiement(j)}>
                            Enregistrer un encaissement
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-8 text-xs"
                            onClick={() => { setSolderJournal(j); setSolderError(null); }}
                          >
                            Solder
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Modal encaissement */}
      {paiementJournal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setPaiementJournal(null)}
        >
          <Card className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">Encaissement — {paiementJournal.client_nom}</CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setPaiementJournal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {paiementError && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{paiementError}</p>
              )}
              <div className="space-y-1.5">
                <Label>Montant *</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={paiementForm.montant}
                  onChange={(e) => setPaiementForm((p) => ({ ...p, montant: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Date *</Label>
                <Input
                  type="date"
                  value={paiementForm.date}
                  onChange={(e) => setPaiementForm((p) => ({ ...p, date: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Mode de paiement</Label>
                <select
                  value={paiementForm.mode_paiement}
                  onChange={(e) => setPaiementForm((p) => ({ ...p, mode_paiement: e.target.value }))}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  {MODE_OPTIONS.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>Référence</Label>
                <Input
                  value={paiementForm.reference}
                  onChange={(e) => setPaiementForm((p) => ({ ...p, reference: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Notes</Label>
                <Input
                  value={paiementForm.notes}
                  onChange={(e) => setPaiementForm((p) => ({ ...p, notes: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <Button className="flex-1 h-9" onClick={handlePaiement} disabled={paiementSubmitting}>
                  {paiementSubmitting ? "Enregistrement..." : "Confirmer"}
                </Button>
                <Button variant="outline" className="h-9" onClick={() => setPaiementJournal(null)}>
                  Annuler
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Modal solder */}
      {solderJournal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setSolderJournal(null)}
        >
          <Card className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">Solder la créance</CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setSolderJournal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm">
                Confirmer le solde de la créance <strong>{solderJournal.client_nom}</strong> —{" "}
                {fmt(solderJournal.montant_restant)} FCFA restants ?
              </p>
              {solderError && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{solderError}</p>
              )}
              <div className="flex gap-2">
                <Button className="flex-1 h-9" onClick={handleSolder} disabled={solderSubmitting}>
                  {solderSubmitting ? "Traitement..." : "Confirmer"}
                </Button>
                <Button variant="outline" className="h-9" onClick={() => setSolderJournal(null)}>
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
