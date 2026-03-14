"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Pencil, Trash2, X } from "lucide-react";

interface Depense {
  id: number;
  lieu: number;
  lieu_nom: string;
  categorie: number;
  categorie_nom: string;
  production_order?: number | null;
  production_order_nom?: string | null;
  montant: string;
  date: string;
  libelle: string;
  created_at: string;
}

interface Categorie {
  id: number;
  nom: string;
}

interface LieuOption {
  id: number;
  nom: string;
  type_lieu_raw?: string;
}

interface Paginated<T> {
  results: T[];
  count?: number;
}

interface LocationItem {
  id: number;
  nom?: string;
  name?: string;
  type_lieu_raw?: string;
}

function toList<T>(data: Paginated<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.results;
}

function toLocationList(data: Paginated<LocationItem> | LocationItem[]): LieuOption[] {
  return toList(data).map((item) => ({
    id: item.id,
    nom: item.nom ?? item.name ?? `Lieu #${item.id}`,
    type_lieu_raw: item.type_lieu_raw,
  }));
}

export default function ComptableDepensesPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [depenses, setDepenses] = useState<Depense[]>([]);
  const [categories, setCategories] = useState<Categorie[]>([]);
  const [lieux, setLieux] = useState<LieuOption[]>([]);

  const [filters, setFilters] = useState({
    lieuId: "",
    categorieId: "",
    debut: "",
    fin: "",
  });

  const [form, setForm] = useState({
    lieuId: "",
    categorieId: "",
    montant: "",
    date: new Date().toISOString().slice(0, 10),
    libelle: "",
  });

  const [editDepense, setEditDepense] = useState<Depense | null>(null);
  const [editForm, setEditForm] = useState({
    lieuId: "",
    categorieId: "",
    montant: "",
    date: "",
    libelle: "",
  });
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const buildQuery = useCallback((p: typeof filters) => {
    const params = new URLSearchParams();
    if (p.lieuId) params.set("lieu", p.lieuId);
    if (p.categorieId) params.set("categorie", p.categorieId);
    if (p.debut) params.set("debut", p.debut);
    if (p.fin) params.set("fin", p.fin);
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  }, []);

  const loadDepenses = useCallback(
    async (p: typeof filters) => {
      const depensesRes = await apiFetch<Paginated<Depense> | Depense[]>(
        `/comptable/depenses/${buildQuery(p)}`
      );
      setDepenses(toList(depensesRes));
    },
    [buildQuery]
  );

  useEffect(() => {
    const charger = async () => {
      try {
        setLoading(true);
        const [shopsRes, factoriesRes, categoriesRes, depensesRes] = await Promise.all([
          apiFetch<Paginated<LocationItem> | LocationItem[]>("/locations/by-type/?type=shop"),
          apiFetch<Paginated<LocationItem> | LocationItem[]>("/locations/by-type/?type=factory"),
          apiFetch<Paginated<Categorie> | Categorie[]>("/comptable/categories-depense/"),
          apiFetch<Paginated<Depense> | Depense[]>("/comptable/depenses/"),
        ]);
        const lieuxList = [...toLocationList(shopsRes), ...toLocationList(factoriesRes)];
        setLieux(lieuxList);
        setCategories(toList(categoriesRes));
        setDepenses(toList(depensesRes));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur de chargement");
      } finally {
        setLoading(false);
      }
    };
    charger();
  }, []);

  const montantFmt = useMemo(
    () =>
      new Intl.NumberFormat("fr-FR", {
        style: "currency",
        currency: "XOF",
        maximumFractionDigits: 0,
      }),
    []
  );

  const handleChange =
    (field: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
      setError(null);
      setSuccess(null);
    };

  const handleFilterChange =
    (field: keyof typeof filters) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setFilters((prev) => ({ ...prev, [field]: e.target.value }));
    };

  const applyFilters = async () => {
    setError(null);
    try {
      setLoading(true);
      await loadDepenses(filters);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  };

  const resetFilters = async () => {
    const empty = { lieuId: "", categorieId: "", debut: "", fin: "" };
    setFilters(empty);
    try {
      setLoading(true);
      await loadDepenses(empty);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  };

  const openEdit = (d: Depense) => {
    setEditDepense(d);
    setEditForm({
      lieuId: String(d.lieu),
      categorieId: String(d.categorie),
      montant: String(d.montant ?? ""),
      date: d.date,
      libelle: d.libelle || "",
    });
    setEditError(null);
  };

  const handleEditSubmit = async () => {
    if (!editDepense) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      const payload = {
        lieu: Number(editForm.lieuId),
        categorie: Number(editForm.categorieId),
        montant: editForm.montant,
        date: editForm.date,
        libelle: editForm.libelle || "",
      };
      const updated = await apiFetch<Depense>(`/comptable/depenses/${editDepense.id}/`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      setDepenses((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setEditDepense(null);
      setSuccess("DÃ©pense modifiÃ©e.");
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Erreur lors de la modification.");
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleDelete = async (d: Depense) => {
    if (!window.confirm(`Supprimer la dÃ©pense de ${montantFmt.format(Number(d.montant || 0))} ?`)) return;
    try {
      await apiFetch(`/comptable/depenses/${d.id}/`, { method: "DELETE" });
      setDepenses((prev) => prev.filter((x) => x.id !== d.id));
      setSuccess("DÃ©pense supprimÃ©e.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la suppression.");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!form.lieuId || !form.categorieId || !form.montant || !form.date) {
      setError("Lieu, catégorie, montant et date sont obligatoires.");
      return;
    }

    try {
      setSubmitting(true);
      const payload = {
        lieu: Number(form.lieuId),
        categorie: Number(form.categorieId),
        montant: form.montant,
        date: form.date,
        libelle: form.libelle || "",
      };
      const created = await apiFetch<Depense>("/comptable/depenses/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setDepenses((prev) => [created, ...prev]);
      setSuccess("Dépense enregistrée.");
      setForm((prev) => ({ ...prev, montant: "", libelle: "" }));
      await loadDepenses(filters);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'enregistrement.");
    } finally {
      setSubmitting(false);
    }
  };

  if (user?.role !== "comptable" && user?.role !== "admin") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Dépenses</h1>
        <p className="text-sm text-muted-foreground">
          Accès réservé aux comptables et administrateurs.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dépenses</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Enregistrer et consulter les dépenses par lieu.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Nouvelle dépense</CardTitle>
          <CardDescription>
            Saisir une dépense et la rattacher à un lieu et une catégorie.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Lieu</Label>
              <select
                value={form.lieuId}
                onChange={handleChange("lieuId")}
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              >
                <option value="">Sélectionner...</option>
                {lieux.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.nom} {l.type_lieu_raw ? `(${l.type_lieu_raw})` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Catégorie</Label>
              <select
                value={form.categorieId}
                onChange={handleChange("categorieId")}
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              >
                <option value="">Sélectionner...</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.nom}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Montant (FCFA)</Label>
              <Input
                value={form.montant}
                onChange={handleChange("montant")}
                type="number"
                min="0"
                step="1"
                className="h-9"
              />
            </div>
            <div className="space-y-2">
              <Label>Date</Label>
              <Input
                value={form.date}
                onChange={handleChange("date")}
                type="date"
                className="h-9"
              />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label>Libellé</Label>
              <Input
                value={form.libelle}
                onChange={handleChange("libelle")}
                placeholder="Ex: achat fournitures"
                className="h-9"
              />
            </div>
            <div className="sm:col-span-2 flex flex-col gap-2">
              {error && <p className="text-sm text-destructive">{error}</p>}
              {success && <p className="text-sm text-emerald-600">{success}</p>}
              <Button type="submit" className="w-full sm:w-auto h-9" disabled={submitting || loading}>
                {submitting ? "Enregistrement..." : "Enregistrer"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Filtres</CardTitle>
          <CardDescription>Filtrer par date, lieu ou catÃ©gorie.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <Label>Date dÃ©but</Label>
              <Input type="date" value={filters.debut} onChange={handleFilterChange("debut")} className="h-9" />
            </div>
            <div className="space-y-2">
              <Label>Date fin</Label>
              <Input type="date" value={filters.fin} onChange={handleFilterChange("fin")} className="h-9" />
            </div>
            <div className="space-y-2">
              <Label>Lieu</Label>
              <select
                value={filters.lieuId}
                onChange={handleFilterChange("lieuId")}
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              >
                <option value="">Tous</option>
                {lieux.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.nom} {l.type_lieu_raw ? `(${l.type_lieu_raw})` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>CatÃ©gorie</Label>
              <select
                value={filters.categorieId}
                onChange={handleFilterChange("categorieId")}
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              >
                <option value="">Toutes</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.nom}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="button" className="h-9" onClick={applyFilters} disabled={loading}>
              Appliquer
            </Button>
            <Button type="button" variant="outline" className="h-9" onClick={resetFilters} disabled={loading}>
              RÃ©initialiser
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Dépenses enregistrées</CardTitle>
          <CardDescription>Liste des dernières dépenses.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : depenses.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune dépense.</p>
          ) : (
            <div className="overflow-x-auto -mx-1 min-w-0">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left py-2 px-1">Date</th>
                    <th className="text-left py-2 px-1">Lieu</th>
                    <th className="text-left py-2 px-1">Catégorie</th>
                    <th className="text-right py-2 px-1">Montant</th>
                    <th className="text-left py-2 px-1">Libellé</th>
                    <th className="py-2 px-1">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {depenses.map((d) => (
                    <tr key={d.id} className="border-b hover:bg-muted/20">
                      <td className="py-1.5 px-1">{d.date}</td>
                      <td className="py-1.5 px-1">{d.lieu_nom}</td>
                      <td className="py-1.5 px-1">{d.categorie_nom}</td>
                      <td className="py-1.5 px-1 text-right">{montantFmt.format(Number(d.montant || 0))}</td>
                      <td className="py-1.5 px-1 text-muted-foreground">{d.libelle || "—"}</td>
                      <td className="py-1.5 px-1">
                        <div className="flex items-center justify-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-foreground"
                            title="Modifier"
                            onClick={() => openEdit(d)}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="Supprimer"
                            onClick={() => handleDelete(d)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {editDepense && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setEditDepense(null)}>
          <Card className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">Modifier dÃ©pense</CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditDepense(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {editError && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{editError}</p>
              )}
              <div className="space-y-1.5">
                <Label>Lieu</Label>
                <select
                  value={editForm.lieuId}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, lieuId: e.target.value }))}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="">SÃ©lectionner...</option>
                  {lieux.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.nom} {l.type_lieu_raw ? `(${l.type_lieu_raw})` : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>CatÃ©gorie</Label>
                <select
                  value={editForm.categorieId}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, categorieId: e.target.value }))}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="">SÃ©lectionner...</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.nom}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>Montant (FCFA)</Label>
                <Input
                  type="number"
                  min="0"
                  step="1"
                  value={editForm.montant}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, montant: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Date</Label>
                <Input
                  type="date"
                  value={editForm.date}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, date: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>LibellÃ©</Label>
                <Input
                  value={editForm.libelle}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, libelle: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <Button className="flex-1 bg-green-600 hover:bg-green-700 text-white h-9" onClick={handleEditSubmit} disabled={editSubmitting}>
                  {editSubmitting ? "Enregistrementâ€¦" : "Enregistrer"}
                </Button>
                <Button variant="outline" className="h-9" onClick={() => setEditDepense(null)}>
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
