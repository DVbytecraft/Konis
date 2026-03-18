"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface CategorieDepense {
  id: number;
  nom: string;
  created_at: string;
}

export default function AdminCategoriesDepensePage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [categories, setCategories] = useState<CategorieDepense[]>([]);
  const [nom, setNom] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    const charger = async () => {
      try {
        setLoading(true);
        const data = await apiFetch<CategorieDepense[] | { results: CategorieDepense[] }>(
          "/admin/categories-depense/"
        );
        setCategories(Array.isArray(data) ? data : data.results);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur de chargement");
      } finally {
        setLoading(false);
      }
    };
    charger();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (!nom.trim()) {
      setError("Le nom de la catégorie est obligatoire.");
      return;
    }
    try {
      setSubmitting(true);
      const created = await apiFetch<CategorieDepense>("/admin/categories-depense/", {
        method: "POST",
        body: JSON.stringify({ nom: nom.trim() }),
      });
      setCategories((prev) => [created, ...prev]);
      setSuccess(`Catégorie "${created.nom}" créée.`);
      setNom("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la création.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (cat: CategorieDepense) => {
    if (!window.confirm(`Supprimer la catégorie "${cat.nom}" ?`)) return;
    try {
      setDeletingId(cat.id);
      setError(null);
      await apiFetch(`/admin/categories-depense/${cat.id}/`, { method: "DELETE" });
      setCategories((prev) => prev.filter((c) => c.id !== cat.id));
      setSuccess(`Catégorie "${cat.nom}" supprimée.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la suppression.");
    } finally {
      setDeletingId(null);
    }
  };

  if (user?.role !== "admin" && user?.role !== "supreme_admin") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Catégories de dépense</h1>
        <p className="text-sm text-muted-foreground">
          Seuls les administrateurs peuvent gérer les catégories.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Catégories de dépense</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Gérer les catégories utilisées pour classer les dépenses.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Nouvelle catégorie</CardTitle>
          <CardDescription>
            Saisir le nom de la catégorie (ex: Carburant, Salaires, Matières premières).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex gap-3 items-end">
            <div className="space-y-2 flex-1">
              <Label htmlFor="nom">Nom</Label>
              <Input
                id="nom"
                value={nom}
                onChange={(e) => { setNom(e.target.value); setError(null); setSuccess(null); }}
                placeholder="ex: Carburant"
                required
                className="h-9"
              />
            </div>
            <Button type="submit" className="h-9" disabled={submitting || loading}>
              {submitting ? "Création…" : "Créer"}
            </Button>
          </form>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
          {success && <p className="mt-2 text-sm text-emerald-600">{success}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Catégories existantes ({categories.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement…</p>
          ) : categories.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune catégorie. Créez-en une ci-dessus.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 px-1">Nom</th>
                  <th className="py-2 px-1 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((cat) => (
                  <tr key={cat.id} className="border-b hover:bg-muted/40">
                    <td className="py-2 px-1 font-medium">{cat.nom}</td>
                    <td className="py-2 px-1 text-right">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                        disabled={deletingId === cat.id}
                        onClick={() => handleDelete(cat)}
                      >
                        {deletingId === cat.id ? "…" : "Supprimer"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
