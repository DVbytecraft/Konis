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
import { Wheat } from "lucide-react";

interface Lieu {
  id: number;
  nom: string;
  code: string;
  type_lieu: string;
  type_lieu_display: string;
  entreprise: number;
  entreprise_nom: string;
  created_at: string;
  is_active?: boolean;
  mouture_enabled?: boolean;
}

interface FormState {
  nom: string;
  code: string;
  type_lieu: "magasin" | "usine" | "mpsl";
}

type ValidationErrorResponse = Record<string, unknown>;

/** Réponse paginée DRF standard. */
interface Paginated<T> {
  results: T[];
  count?: number;
}

/** Normalise une réponse DRF en tableau — supporte paginé ou tableau direct. */
function toList<T>(data: Paginated<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.results;
}

export default function AdminMagasinsPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [lieux, setLieux] = useState<Lieu[]>([]);

  const [form, setForm] = useState<FormState>({
    nom: "",
    code: "",
    type_lieu: "magasin",
  });

  useEffect(() => {
    const charger = async () => {
      try {
        setLoading(true);
        const lieuxRes = await apiFetch<Paginated<Lieu> | Lieu[]>("/admin/lieux/");
        setLieux(toList(lieuxRes));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur de chargement");
      } finally {
        setLoading(false);
      }
    };
    charger();
  }, []);

  const handleChange =
    (field: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value = e.target.value;
      setForm((prev) => ({
        ...prev,
        [field]: value,
      }));
      setError(null);
      setSuccess(null);
    };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!form.nom.trim()) {
      setError("Le nom du lieu est obligatoire.");
      return;
    }

    try {
      setSubmitting(true);
      const payload = {
        nom: form.nom.trim(),
        code: (form.code || "").trim(),
        type_lieu: form.type_lieu,
      };

      const created = await apiFetch<Lieu>("/admin/lieux/", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setLieux((prev) => [created, ...prev]);
      setSuccess(
        `${form.type_lieu === "magasin" ? "Magasin" : form.type_lieu === "mpsl" ? "Dépôt MPSL" : "Usine"} créé avec succès.`
      );
      setForm((prev) => ({
        ...prev,
        nom: "",
        code: "",
        type_lieu: "magasin",
      }));
    } catch (e) {
      let errorMessage = "Erreur lors de la création.";
      if (e instanceof Error) {
        errorMessage = e.message;
        // Essayer d'extraire plus de détails si disponible
        try {
          const errorData = JSON.parse(e.message);
          if (errorData.detail) {
            errorMessage = errorData.detail;
          } else if (typeof errorData === "object") {
            // Si c'est un objet de validation Django
            const firstError = Object.values(errorData as ValidationErrorResponse)[0];
            if (Array.isArray(firstError)) {
              errorMessage = String(firstError[0]);
            } else if (typeof firstError === "string") {
              errorMessage = firstError;
            }
          }
        } catch {
          // Si ce n'est pas du JSON, utiliser le message tel quel
        }
      }
      setError(errorMessage);
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleLieu = async (lieu: Lieu) => {
    const isActive = lieu.is_active !== false;
    const action = isActive ? "désactiver" : "réactiver";
    if (!window.confirm(`Voulez-vous ${action} le lieu "${lieu.nom}" ?`)) return;
    try {
      setError(null);
      const updated = await apiFetch<Lieu>(`/admin/lieux/${lieu.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !isActive }),
      });
      setLieux((prev) => prev.map((l) => (l.id === lieu.id ? { ...l, ...updated } : l)));
      setSuccess(`Lieu "${lieu.nom}" ${isActive ? "désactivé" : "réactivé"}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la mise à jour.");
    }
  };

  const handleToggleMouture = async (lieu: Lieu) => {
    const moutureActif = lieu.mouture_enabled !== false;
    const action = moutureActif ? "désactiver la mouture pour" : "activer la mouture pour";
    if (!window.confirm(`Voulez-vous ${action} "${lieu.nom}" ?`)) return;
    try {
      setError(null);
      const updated = await apiFetch<Lieu>(`/admin/lieux/${lieu.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ mouture_enabled: !moutureActif }),
      });
      setLieux((prev) => prev.map((l) => (l.id === lieu.id ? { ...l, ...updated } : l)));
      setSuccess(`Mouture ${moutureActif ? "désactivée" : "activée"} pour "${lieu.nom}".`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la mise à jour.");
    }
  };

  if (user?.role !== "admin") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Magasins</h1>
        <p className="text-sm text-muted-foreground">
          Seuls les administrateurs peuvent gérer les magasins.
        </p>
      </div>
    );
  }

  const magasins = lieux.filter((l) => l.type_lieu === "magasin");
  const usines = lieux.filter((l) => l.type_lieu === "usine");
  const mpslDepots = lieux.filter((l) => l.type_lieu === "mpsl");

  return (
    <div className="space-y-8 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Lieux</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Création et gestion des lieux (magasins, usines, dépôts MPSL).
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Créer un lieu</CardTitle>
          <CardDescription>
            Saisir les informations du lieu. Le code est optionnel et sert pour
            les numéros de tickets (ex: KARA, CENTRE).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="nom">Nom</Label>
              <Input
                id="nom"
                value={form.nom}
                onChange={handleChange("nom")}
                placeholder="ex: Magasin Centre"
                required
                className="h-9"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="code">Code (optionnel)</Label>
              <Input
                id="code"
                value={form.code}
                onChange={handleChange("code")}
                placeholder="ex: CENTRE"
                maxLength={20}
                className="h-9"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="type_lieu">Type</Label>
              <select
                id="type_lieu"
                value={form.type_lieu}
                onChange={handleChange("type_lieu")}
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              >
                <option value="magasin">Magasin</option>
                <option value="usine">Usine</option>
                <option value="mpsl">Dépôt MPSL</option>
              </select>
            </div>
            <div className="sm:col-span-2 flex flex-col gap-2">
              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}
              {success && (
                <p className="text-sm text-emerald-600">{success}</p>
              )}
              <Button
                type="submit"
                className="w-full sm:w-auto h-9"
                disabled={submitting || loading}
              >
                {submitting ? "Création…" : "Créer le lieu"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-6 sm:grid-cols-2">
        <Card className="border-t-2 border-t-green-500">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-green-700 dark:text-green-300">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500"></span>
              Magasins
            </CardTitle>
            <CardDescription>
              Liste des magasins existants ({magasins.length}).
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Chargement…</p>
            ) : magasins.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucun magasin.</p>
            ) : (
              <div className="overflow-x-auto -mx-1 min-w-0">
                <table className="w-full min-w-[320px] text-sm">
                  <thead>
                    <tr className="border-b bg-green-50/40 dark:bg-green-950/20">
                      <th className="text-left py-2 px-1">Nom</th>
                      <th className="text-left py-2 px-1">Code</th>
                      <th className="text-left py-2 px-1">Entreprise</th>
                      <th className="text-left py-2 px-1">Statut</th>
                      <th className="text-left py-2 px-1">Mouture</th>
                      <th className="py-2 px-1">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {magasins.map((l) => {
                      const actif = l.is_active !== false;
                      const mouture = l.mouture_enabled !== false;
                      return (
                        <tr key={l.id} className={`border-b hover:bg-green-50/30 dark:hover:bg-green-950/10 ${!actif ? "opacity-60" : ""}`}>
                          <td className="py-1.5 px-1 font-medium">{l.nom}</td>
                          <td className="py-1.5 px-1 font-mono text-muted-foreground">
                            {l.code ? (
                              <span className="bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 px-1.5 py-0.5 rounded text-xs">
                                {l.code}
                              </span>
                            ) : "—"}
                          </td>
                          <td className="py-1.5 px-1 text-muted-foreground">{l.entreprise_nom}</td>
                          <td className="py-1.5 px-1">
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${actif ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300" : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"}`}>
                              {actif ? "Actif" : "Inactif"}
                            </span>
                          </td>
                          <td className="py-1.5 px-1">
                            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${mouture ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300" : "bg-muted text-muted-foreground"}`}>
                              <Wheat className="h-3 w-3" />
                              {mouture ? "Activée" : "Désactivée"}
                            </span>
                          </td>
                          <td className="py-1.5 px-1">
                            <div className="flex items-center gap-1">
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-6 text-xs"
                                onClick={() => handleToggleLieu(l)}
                              >
                                {actif ? "Désactiver" : "Réactiver"}
                              </Button>
                              <Button
                                type="button"
                                variant={mouture ? "outline" : "default"}
                                size="sm"
                                className={`h-6 text-xs gap-1 ${mouture ? "" : "bg-green-600 hover:bg-green-700 text-white"}`}
                                onClick={() => handleToggleMouture(l)}
                              >
                                <Wheat className="h-3 w-3" />
                                {mouture ? "Mouture OFF" : "Mouture ON"}
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-t-2 border-t-orange-500">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-orange-700 dark:text-orange-300">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-orange-500"></span>
              Usines
            </CardTitle>
            <CardDescription>
              Liste des usines existantes ({usines.length}).
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Chargement…</p>
            ) : usines.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune usine.</p>
            ) : (
              <div className="overflow-x-auto -mx-1 min-w-0">
                <table className="w-full min-w-[320px] text-sm">
                  <thead>
                    <tr className="border-b bg-orange-50/40 dark:bg-orange-950/20">
                      <th className="text-left py-2 px-1">Nom</th>
                      <th className="text-left py-2 px-1">Code</th>
                      <th className="text-left py-2 px-1">Entreprise</th>
                      <th className="text-left py-2 px-1">Statut</th>
                      <th className="text-left py-2 px-1">Mouture</th>
                      <th className="py-2 px-1">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usines.map((l) => {
                      const actif = l.is_active !== false;
                      const mouture = l.mouture_enabled !== false;
                      return (
                        <tr key={l.id} className={`border-b hover:bg-orange-50/30 dark:hover:bg-orange-950/10 ${!actif ? "opacity-60" : ""}`}>
                          <td className="py-1.5 px-1 font-medium">{l.nom}</td>
                          <td className="py-1.5 px-1 font-mono text-muted-foreground">
                            {l.code ? (
                              <span className="bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300 px-1.5 py-0.5 rounded text-xs">
                                {l.code}
                              </span>
                            ) : "—"}
                          </td>
                          <td className="py-1.5 px-1 text-muted-foreground">{l.entreprise_nom}</td>
                          <td className="py-1.5 px-1">
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${actif ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300" : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"}`}>
                              {actif ? "Actif" : "Inactif"}
                            </span>
                          </td>
                          <td className="py-1.5 px-1">
                            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${mouture ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300" : "bg-muted text-muted-foreground"}`}>
                              <Wheat className="h-3 w-3" />
                              {mouture ? "Activée" : "Désactivée"}
                            </span>
                          </td>
                          <td className="py-1.5 px-1">
                            <div className="flex items-center gap-1">
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-6 text-xs"
                                onClick={() => handleToggleLieu(l)}
                              >
                                {actif ? "Désactiver" : "Réactiver"}
                              </Button>
                              <Button
                                type="button"
                                variant={mouture ? "outline" : "default"}
                                size="sm"
                                className={`h-6 text-xs gap-1 ${mouture ? "" : "bg-green-600 hover:bg-green-700 text-white"}`}
                                onClick={() => handleToggleMouture(l)}
                              >
                                <Wheat className="h-3 w-3" />
                                {mouture ? "Mouture OFF" : "Mouture ON"}
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Dépôts MPSL */}
      <Card className="border-t-2 border-t-cyan-500">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-cyan-700 dark:text-cyan-300">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-cyan-500"></span>
            Dépôts MPSL
          </CardTitle>
          <CardDescription>
            Centres logistiques d&apos;approvisionnement ({mpslDepots.length}).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement…</p>
          ) : mpslDepots.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun dépôt MPSL. Créez-en un via le formulaire ci-dessus.</p>
          ) : (
            <div className="overflow-x-auto -mx-1 min-w-0">
              <table className="w-full min-w-[320px] text-sm">
                <thead>
                  <tr className="border-b bg-cyan-50/40 dark:bg-cyan-950/20">
                    <th className="text-left py-2 px-1">Nom</th>
                    <th className="text-left py-2 px-1">Code</th>
                    <th className="text-left py-2 px-1">Entreprise</th>
                    <th className="text-left py-2 px-1">Statut</th>
                    <th className="py-2 px-1">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {mpslDepots.map((l) => {
                    const actif = l.is_active !== false;
                    return (
                      <tr key={l.id} className={`border-b hover:bg-cyan-50/30 dark:hover:bg-cyan-950/10 ${!actif ? "opacity-60" : ""}`}>
                        <td className="py-1.5 px-1 font-medium">{l.nom}</td>
                        <td className="py-1.5 px-1 font-mono text-muted-foreground">
                          {l.code ? (
                            <span className="bg-cyan-100 text-cyan-800 dark:bg-cyan-900/40 dark:text-cyan-300 px-1.5 py-0.5 rounded text-xs">
                              {l.code}
                            </span>
                          ) : "—"}
                        </td>
                        <td className="py-1.5 px-1 text-muted-foreground">{l.entreprise_nom}</td>
                        <td className="py-1.5 px-1">
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${actif ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300" : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"}`}>
                            {actif ? "Actif" : "Inactif"}
                          </span>
                        </td>
                        <td className="py-1.5 px-1">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-6 text-xs"
                            onClick={() => handleToggleLieu(l)}
                          >
                            {actif ? "Désactiver" : "Réactiver"}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
