"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import { KeyRound, Trash2, X } from "lucide-react";

interface FactoryUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
}

interface Factory {
  id: number;
  name: string;
  address: string;
  is_active: boolean;
  user: FactoryUser | null;
}

interface FactoryForm {
  factory_name: string;
  factory_address: string;
  user_email: string;
  user_first_name: string;
  user_last_name: string;
  user_password: string;
  user_password_confirm: string;
}

const initialForm: FactoryForm = {
  factory_name: "",
  factory_address: "",
  user_email: "",
  user_first_name: "",
  user_last_name: "",
  user_password: "",
  user_password_confirm: "",
};

export default function AdminFactoriesPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [factories, setFactories] = useState<Factory[]>([]);
  const [form, setForm] = useState<FactoryForm>(initialForm);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Password change modal
  const [mdpFactory, setMdpFactory] = useState<Factory | null>(null);
  const [nouveauMdp, setNouveauMdp] = useState("");
  const [mdpSubmitting, setMdpSubmitting] = useState(false);
  const [mdpError, setMdpError] = useState<string | null>(null);

  const loadFactories = async () => {
    const data = await apiFetch<Factory[]>("/admin/factories/");
    setFactories(data);
  };

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        await loadFactories();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur de chargement");
      } finally {
        setLoading(false);
      }
    };
    load().catch(() => setLoading(false));
  }, []);

  const onChange =
    (field: keyof FactoryForm) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
      setError(null);
      setSuccess(null);
    };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (!form.factory_name.trim()) {
      setError("Le nom d'usine est obligatoire.");
      return;
    }
    if (form.user_password !== form.user_password_confirm) {
      setError("La confirmation du mot de passe ne correspond pas.");
      return;
    }
    try {
      setSubmitting(true);
      await apiFetch<Factory>("/admin/factories/", {
        method: "POST",
        body: JSON.stringify({
          factory_name: form.factory_name.trim(),
          factory_address: form.factory_address.trim(),
          user_email: form.user_email.trim(),
          user_first_name: form.user_first_name.trim(),
          user_last_name: form.user_last_name.trim(),
          user_password: form.user_password,
        }),
      });
      setForm(initialForm);
      setSuccess("Usine et compte utilisateur créés.");
      await loadFactories();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la création.");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleFactory = async (factory: Factory) => {
    try {
      setError(null);
      await apiFetch<Factory>(`/admin/factories/${factory.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !factory.is_active }),
      });
      await loadFactories();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la mise à jour.");
    }
  };

  const handleDelete = async (factory: Factory) => {
    if (!window.confirm(`Supprimer l'usine "${factory.name}" ? Cette action est irréversible.`)) return;
    try {
      setError(null);
      await apiFetch(`/admin/factories/${factory.id}/`, { method: "DELETE" });
      setFactories((prev) => prev.filter((f) => f.id !== factory.id));
      setSuccess(`Usine "${factory.name}" supprimée.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la suppression.");
    }
  };

  const handleMdpSubmit = async () => {
    if (!mdpFactory || !nouveauMdp.trim()) {
      setMdpError("Le mot de passe ne peut pas être vide.");
      return;
    }
    setMdpSubmitting(true);
    setMdpError(null);
    try {
      await apiFetch<Factory>(`/admin/factories/${mdpFactory.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ user_password: nouveauMdp.trim() }),
      });
      setMdpFactory(null);
      setNouveauMdp("");
      setSuccess(`Mot de passe de "${mdpFactory.name}" modifié.`);
    } catch (e) {
      setMdpError(e instanceof Error ? e.message : "Erreur lors du changement de mot de passe.");
    } finally {
      setMdpSubmitting(false);
    }
  };

  if (user?.role !== "admin" && user?.role !== "supreme_admin") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Usines</h1>
        <p className="text-sm text-muted-foreground">Seuls les administrateurs peuvent gérer les usines.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Usines</h1>
        <p className="mt-1 text-sm text-muted-foreground">Créer et administrer les usines et leurs comptes responsables.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Créer une usine</CardTitle>
          <CardDescription>Création de l&apos;usine et du compte utilisateur usine en une seule opération.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="factory_name">Nom usine</Label>
              <Input id="factory_name" value={form.factory_name} onChange={onChange("factory_name")} required className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="factory_address">Adresse</Label>
              <Input id="factory_address" value={form.factory_address} onChange={onChange("factory_address")} className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="user_email">Email responsable</Label>
              <Input id="user_email" type="email" value={form.user_email} onChange={onChange("user_email")} required className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="user_first_name">Prénom</Label>
              <Input id="user_first_name" value={form.user_first_name} onChange={onChange("user_first_name")} className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="user_last_name">Nom</Label>
              <Input id="user_last_name" value={form.user_last_name} onChange={onChange("user_last_name")} className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="user_password">Mot de passe</Label>
              <PasswordInput id="user_password" value={form.user_password} onChange={onChange("user_password")} required className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="user_password_confirm">Confirmer mot de passe</Label>
              <PasswordInput id="user_password_confirm" value={form.user_password_confirm} onChange={onChange("user_password_confirm")} required className="h-9" />
            </div>

            <div className="sm:col-span-2 flex flex-col gap-2">
              {error && <p className="text-sm text-destructive">{error}</p>}
              {success && <p className="text-sm text-emerald-600">{success}</p>}
              <Button type="submit" className="w-full sm:w-auto h-9" disabled={submitting || loading}>
                {submitting ? "Création..." : "Créer l'usine"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Usines existantes</CardTitle>
          <CardDescription>Vue d&apos;ensemble multi-usines.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : factories.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune usine.</p>
          ) : (
            <div className="overflow-x-auto -mx-1 sm:mx-0 min-w-0">
              <table className="w-full min-w-[540px] text-xs sm:text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2">Nom</th>
                    <th className="text-left py-2">Adresse</th>
                    <th className="text-left py-2">Responsable</th>
                    <th className="text-left py-2">Statut</th>
                    <th className="text-left py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {factories.map((f) => (
                    <tr key={f.id} className="border-b">
                      <td className="py-1.5">{f.name}</td>
                      <td className="py-1.5">{f.address || "—"}</td>
                      <td className="py-1.5">{f.user?.email || "—"}</td>
                      <td className="py-1.5">{f.is_active ? "Active" : "Inactive"}</td>
                      <td className="py-1.5">
                        <div className="flex items-center gap-1 flex-wrap">
                          <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => toggleFactory(f)}>
                            {f.is_active ? "Désactiver" : "Réactiver"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1"
                            onClick={() => { setMdpFactory(f); setNouveauMdp(""); setMdpError(null); }}
                          >
                            <KeyRound className="h-3 w-3" />
                            MDP
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="Supprimer"
                            onClick={() => handleDelete(f)}
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

      {/* Modal changement mot de passe usine */}
      {mdpFactory && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setMdpFactory(null)}
        >
          <Card className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">Modifier MDP — {mdpFactory.name}</CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setMdpFactory(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {mdpError && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{mdpError}</p>
              )}
              <div className="space-y-1.5">
                <Label>Nouveau mot de passe</Label>
                <PasswordInput
                  placeholder="Nouveau mot de passe"
                  value={nouveauMdp}
                  onChange={(e) => setNouveauMdp(e.target.value)}
                  className="h-9"
                  autoFocus
                />
              </div>
              <div className="flex gap-2 pt-1">
                <Button
                  className="flex-1 bg-green-600 hover:bg-green-700 text-white h-9"
                  onClick={handleMdpSubmit}
                  disabled={mdpSubmitting}
                >
                  {mdpSubmitting ? "Enregistrement…" : "Changer le mot de passe"}
                </Button>
                <Button variant="outline" className="h-9" onClick={() => setMdpFactory(null)}>
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
