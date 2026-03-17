"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Pencil, X } from "lucide-react";

interface Creancier {
  id: number;
  nom: string;
  type_creancier: string;
  contact: string;
  notes: string;
}

interface Paginated<T> { results: T[]; count?: number; }
function toList<T>(data: Paginated<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.results;
}

const TYPE_OPTIONS = [
  { value: "fournisseur", label: "Fournisseur" },
  { value: "banque", label: "Banque" },
  { value: "autre", label: "Autre" },
];

const emptyForm = { nom: "", type_creancier: "fournisseur", contact: "", notes: "" };

export default function CreanciersPage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [creanciers, setCreanciers] = useState<Creancier[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [editItem, setEditItem] = useState<Creancier | null>(null);
  const [editForm, setEditForm] = useState(emptyForm);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiFetch<Paginated<Creancier> | Creancier[]>("/finance/creanciers/");
      setCreanciers(toList(res));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleChange =
    (field: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
      setError(null);
      setSuccess(null);
    };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.nom.trim()) {
      setError("Le nom est obligatoire.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const created = await apiFetch<Creancier>("/finance/creanciers/", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setCreanciers((prev) => [created, ...prev]);
      setSuccess("Créancier ajouté.");
      setForm(emptyForm);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'enregistrement.");
    } finally {
      setSubmitting(false);
    }
  };

  const openEdit = (c: Creancier) => {
    setEditItem(c);
    setEditForm({ nom: c.nom, type_creancier: c.type_creancier, contact: c.contact || "", notes: c.notes || "" });
    setEditError(null);
  };

  const handleEditSubmit = async () => {
    if (!editItem) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      const updated = await apiFetch<Creancier>(`/finance/creanciers/${editItem.id}/`, {
        method: "PATCH",
        body: JSON.stringify(editForm),
      });
      setCreanciers((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      setEditItem(null);
      setSuccess("Créancier modifié.");
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Erreur lors de la modification.");
    } finally {
      setEditSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Créanciers</h1>
        <p className="mt-1 text-sm text-muted-foreground">Gérer les créanciers de l&apos;entreprise.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Nouveau créancier</CardTitle>
          <CardDescription>Ajouter un créancier (fournisseur, banque ou autre).</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Nom *</Label>
              <Input value={form.nom} onChange={handleChange("nom")} placeholder="Nom du créancier" className="h-9" />
            </div>
            <div className="space-y-2">
              <Label>Type</Label>
              <select
                value={form.type_creancier}
                onChange={handleChange("type_creancier")}
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              >
                {TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Contact</Label>
              <Input value={form.contact} onChange={handleChange("contact")} placeholder="Téléphone ou email" className="h-9" />
            </div>
            <div className="space-y-2">
              <Label>Notes</Label>
              <Input value={form.notes} onChange={handleChange("notes")} placeholder="Notes optionnelles" className="h-9" />
            </div>
            <div className="sm:col-span-2 flex flex-col gap-2">
              {error && <p className="text-sm text-destructive">{error}</p>}
              {success && <p className="text-sm text-emerald-600">{success}</p>}
              <Button type="submit" className="w-full sm:w-auto h-9" disabled={submitting || loading}>
                {submitting ? "Enregistrement..." : "Ajouter"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Liste des créanciers</CardTitle>
          <CardDescription>{creanciers.length} créancier(s) enregistré(s).</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : creanciers.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun créancier.</p>
          ) : (
            <div className="overflow-x-auto -mx-1">
              <table className="w-full min-w-[480px] text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left py-2 px-2">Nom</th>
                    <th className="text-left py-2 px-2">Type</th>
                    <th className="text-left py-2 px-2">Contact</th>
                    <th className="text-left py-2 px-2">Notes</th>
                    <th className="py-2 px-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {creanciers.map((c) => (
                    <tr key={c.id} className="border-b hover:bg-muted/20">
                      <td className="py-1.5 px-2 font-medium">{c.nom}</td>
                      <td className="py-1.5 px-2 capitalize text-muted-foreground">{c.type_creancier}</td>
                      <td className="py-1.5 px-2 text-muted-foreground">{c.contact || "—"}</td>
                      <td className="py-1.5 px-2 text-muted-foreground">{c.notes || "—"}</td>
                      <td className="py-1.5 px-2 text-center">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-foreground"
                          title="Modifier"
                          onClick={() => openEdit(c)}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {editItem && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setEditItem(null)}
        >
          <Card className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">Modifier créancier</CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditItem(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {editError && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{editError}</p>
              )}
              <div className="space-y-1.5">
                <Label>Nom *</Label>
                <Input
                  value={editForm.nom}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, nom: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Type</Label>
                <select
                  value={editForm.type_creancier}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, type_creancier: e.target.value }))}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  {TYPE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>Contact</Label>
                <Input
                  value={editForm.contact}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, contact: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Notes</Label>
                <Input
                  value={editForm.notes}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, notes: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <Button
                  className="flex-1 h-9"
                  onClick={handleEditSubmit}
                  disabled={editSubmitting}
                >
                  {editSubmitting ? "Enregistrement..." : "Enregistrer"}
                </Button>
                <Button variant="outline" className="h-9" onClick={() => setEditItem(null)}>
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
