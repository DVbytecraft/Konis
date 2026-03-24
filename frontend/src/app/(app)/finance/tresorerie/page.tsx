"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { buildIdempotencyKey, fmt } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Banknote, Plus, X } from "lucide-react";

interface Transaction {
  id: number;
  type_transaction: string;
  type_display: string;
  montant: string;
  description: string;
  reference: string;
  date: string;
  created_by_nom: string;
  created_at: string;
}

interface CaisseResponse {
  count?: number;
  results?: Transaction[];
  solde_courant?: string;
}

interface Paginated<T> { results: T[]; count?: number; }
function toList<T>(data: Paginated<T> | T[]): T[] {
  return Array.isArray(data) ? data : (data.results ?? []);
}

const emptyForm = {
  type_transaction: "depot" as "depot" | "retrait",
  montant: "",
  description: "",
  date: new Date().toISOString().slice(0, 10),
  reference: "",
};

export default function TresoreriePage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [solde, setSolde] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiFetch<CaisseResponse | Transaction[]>("/finance/caisse/");
      if (Array.isArray(res)) {
        setTransactions(res);
      } else {
        setTransactions(toList(res as Paginated<Transaction>));
        if (res.solde_courant !== undefined) {
          setSolde(res.solde_courant);
        }
      }
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
    if (!form.montant || !form.description.trim() || !form.date) {
      setError("Type, montant, description et date sont obligatoires.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const payload: Record<string, unknown> = {
        type_transaction: form.type_transaction,
        montant: form.montant,
        description: form.description,
        date: form.date,
      };
      if (form.reference) payload.reference = form.reference;
      const created = await apiFetch<Transaction>("/finance/caisse/", {
        method: "POST",
        headers: { "Idempotency-Key": buildIdempotencyKey("caisse-tx") },
        body: JSON.stringify(payload),
      });
      setTransactions((prev) => [created, ...prev]);
      // Recalculate solde locally
      setSolde((prev) => {
        const current = Number(prev ?? 0);
        const delta = Number(form.montant);
        return String(form.type_transaction === "depot" ? current + delta : current - delta);
      });
      setSuccess("Transaction enregistrée.");
      setForm(emptyForm);
      setShowForm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'enregistrement.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Trésorerie</h1>
          <p className="mt-1 text-sm text-muted-foreground">Caisse Suprême — dépôts et retraits.</p>
        </div>
        <Button className="h-9 gap-1" onClick={() => setShowForm((v) => !v)}>
          <Plus className="h-4 w-4" />
          Nouvelle transaction
        </Button>
      </div>

      {/* Solde courant */}
      {solde !== null && (
        <Card className="border-emerald-200">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Solde courant</CardTitle>
            <Banknote className="h-5 w-5 text-emerald-600" />
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-emerald-700">{fmt(solde)} FCFA</p>
          </CardContent>
        </Card>
      )}

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>Nouvelle transaction</CardTitle>
            <CardDescription>Enregistrer un dépôt ou un retrait de caisse.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Type *</Label>
                <select
                  value={form.type_transaction}
                  onChange={handleChange("type_transaction")}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="depot">Dépôt</option>
                  <option value="retrait">Retrait</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>Montant *</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.montant}
                  onChange={handleChange("montant")}
                  className="h-9"
                />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label>Description *</Label>
                <Input value={form.description} onChange={handleChange("description")} placeholder="Motif de la transaction" className="h-9" />
              </div>
              <div className="space-y-2">
                <Label>Date *</Label>
                <Input type="date" value={form.date} onChange={handleChange("date")} className="h-9" />
              </div>
              <div className="space-y-2">
                <Label>Référence</Label>
                <Input value={form.reference} onChange={handleChange("reference")} placeholder="Optionnel" className="h-9" />
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
          <CardTitle>Historique des transactions</CardTitle>
          <CardDescription>{transactions.length} transaction(s).</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : transactions.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune transaction.</p>
          ) : (
            <div className="overflow-x-auto -mx-1">
              <table className="w-full min-w-[520px] text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left py-2 px-2">Date</th>
                    <th className="text-left py-2 px-2">Type</th>
                    <th className="text-right py-2 px-2">Montant</th>
                    <th className="text-left py-2 px-2">Description</th>
                    <th className="text-left py-2 px-2">Référence</th>
                    <th className="text-left py-2 px-2">Par</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((t) => (
                    <tr key={t.id} className="border-b hover:bg-muted/20">
                      <td className="py-1.5 px-2 text-muted-foreground">{t.date}</td>
                      <td className="py-1.5 px-2">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                          t.type_transaction === "depot"
                            ? "bg-green-100 text-green-800"
                            : "bg-red-100 text-red-700"
                        }`}>
                          {t.type_display}
                        </span>
                      </td>
                      <td className={`py-1.5 px-2 text-right font-medium ${
                        t.type_transaction === "depot" ? "text-emerald-700" : "text-red-600"
                      }`}>
                        {t.type_transaction === "retrait" ? "−" : "+"}{fmt(t.montant)} FCFA
                      </td>
                      <td className="py-1.5 px-2">{t.description}</td>
                      <td className="py-1.5 px-2 text-muted-foreground">{t.reference || "—"}</td>
                      <td className="py-1.5 px-2 text-muted-foreground">{t.created_by_nom || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Fallback modal-free close button for form */}
      {showForm && (
        <Button
          variant="ghost"
          size="icon"
          className="fixed top-4 right-4 z-50 hidden"
          onClick={() => setShowForm(false)}
        >
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
