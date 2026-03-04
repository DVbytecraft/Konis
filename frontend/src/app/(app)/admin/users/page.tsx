"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
import { Pencil, Trash2, X } from "lucide-react";

type Role = "admin" | "comptable" | "usine" | "boutique";

interface Entreprise {
  id: number;
  nom: string;
}

interface Lieu {
  id: number;
  nom: string;
  type_lieu: string;
  entreprise: number;
}

interface User {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  role: Role;
  role_display: string;
  entreprise: number | null;
  lieu: { id: number; nom: string; type_lieu: string } | null;
  is_active: boolean;
}

interface FormState {
  username: string;
  password: string;
  first_name: string;
  last_name: string;
  email: string;
  role: Role;
  entrepriseId: number | "";
  lieuId: number | "";
}

interface EditForm {
  password: string;
  role: Role;
  lieuId: number | "";
}

export default function AdminUsersPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [entreprises, setEntreprises] = useState<Entreprise[]>([]);
  const [lieux, setLieux] = useState<Lieu[]>([]);
  const [lieuxFiltres, setLieuxFiltres] = useState<Lieu[]>([]);
  const [users, setUsers] = useState<User[]>([]);

  // Edit modal state
  const [editUser, setEditUser] = useState<User | null>(null);
  const [editForm, setEditForm] = useState<EditForm>({ password: "", role: "boutique", lieuId: "" });
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editLieux, setEditLieux] = useState<Lieu[]>([]);

  const [form, setForm] = useState<FormState>({
    username: "",
    password: "",
    first_name: "",
    last_name: "",
    email: "",
    role: "boutique",
    entrepriseId: "",
    lieuId: "",
  });

  const lieuxForSelectedEntreprise = useMemo(() => {
    if (!form.entrepriseId) return lieuxFiltres;
    return lieuxFiltres.filter((l) => l.entreprise === form.entrepriseId);
  }, [lieuxFiltres, form.entrepriseId]);

  useEffect(() => {
    const charger = async () => {
      try {
        setLoading(true);
        const [ents, lieuxRes, usersRes] = await Promise.all([
          apiFetch("/admin/entreprises/"),
          apiFetch("/admin/lieux/"),
          apiFetch("/admin/users/"),
        ]);
        const entsList: Entreprise[] = ents.results ?? ents;
        const lieuxList: Lieu[] = (lieuxRes.results ?? lieuxRes).map((l: { id: number; nom: string; type_lieu: string; entreprise: number }) => ({
          id: l.id,
          nom: l.nom,
          type_lieu: l.type_lieu,
          entreprise: l.entreprise,
        }));
        const usersList: User[] = usersRes.results ?? usersRes;

        setEntreprises(entsList);
        setLieux(lieuxList);
        setLieuxFiltres(lieuxList);
        setUsers(usersList);

        if (!form.entrepriseId && entsList.length > 0) {
          setForm((prev) => ({ ...prev, entrepriseId: entsList[0].id }));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur de chargement");
      } finally {
        setLoading(false);
      }
    };
    charger();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const chargerLieuxFiltres = async () => {
      if (!form.entrepriseId) {
        setLieuxFiltres(lieux);
        return;
      }
      if (form.role === "boutique" || form.role === "usine") {
        const type = form.role === "boutique" ? "shop" : "factory";
        const res = await apiFetch(`/locations/by-type/?type=${type}&entreprise=${form.entrepriseId}`);
        const list: Lieu[] = res.results ?? res;
        setLieuxFiltres(list);
        return;
      }
      setLieuxFiltres(lieux.filter((l) => l.entreprise === form.entrepriseId));
    };
    chargerLieuxFiltres().catch(() => setLieuxFiltres([]));
  }, [form.entrepriseId, form.role, lieux]);

  const handleChange =
    (field: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value = e.target.value;
      setForm((prev) => ({
        ...prev,
        [field]:
          field === "entrepriseId" || field === "lieuId"
            ? ((value ? Number(value) : "") as never)
            : (value as never),
      }));
      setError(null);
      setSuccess(null);
    };

  const handleRoleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value as Role;
    setForm((prev) => ({
      ...prev,
      role: value,
      lieuId: value === "boutique" || value === "usine" ? prev.lieuId : "",
    }));
    setError(null);
    setSuccess(null);
  };

  const handleDelete = useCallback(async (u: User) => {
    if (!window.confirm(`Supprimer l'utilisateur "${u.username}" ? Cette action est irréversible.`)) return;
    try {
      await apiFetch(`/admin/users/${u.id}/`, { method: "DELETE" });
      setUsers((prev) => prev.filter((x) => x.id !== u.id));
      setSuccess(`Utilisateur "${u.username}" supprimé.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la suppression.");
    }
  }, []);

  const openEditModal = useCallback(async (u: User) => {
    setEditUser(u);
    setEditForm({ password: "", role: u.role, lieuId: u.lieu?.id ?? "" });
    setEditError(null);
    // Load lieux filtered by role + entreprise
    if (u.role === "boutique" || u.role === "usine") {
      try {
        const type = u.role === "boutique" ? "shop" : "factory";
        const ent = entreprises.find((e) => e.id);
        const res = await apiFetch(`/locations/by-type/?type=${type}${ent ? `&entreprise=${ent.id}` : ""}`);
        setEditLieux(res.results ?? res);
      } catch {
        setEditLieux(lieux);
      }
    } else {
      setEditLieux([]);
    }
  }, [entreprises, lieux]);

  const handleEditRoleChange = useCallback(async (role: Role) => {
    setEditForm((prev) => ({ ...prev, role, lieuId: "" }));
    if (role === "boutique" || role === "usine") {
      try {
        const type = role === "boutique" ? "shop" : "factory";
        const res = await apiFetch(`/locations/by-type/?type=${type}`);
        setEditLieux(res.results ?? res);
      } catch {
        setEditLieux(lieux);
      }
    } else {
      setEditLieux([]);
    }
  }, [lieux]);

  const handleEditSubmit = useCallback(async () => {
    if (!editUser) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      const payload: Record<string, unknown> = { role: editForm.role };
      if (editForm.password.trim()) payload.password = editForm.password.trim();
      if ((editForm.role === "boutique" || editForm.role === "usine") && editForm.lieuId) {
        payload.lieu = editForm.lieuId;
      } else if (editForm.role !== "boutique" && editForm.role !== "usine") {
        payload.lieu = null;
      }
      const updated = await apiFetch(`/admin/users/${editUser.id}/`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      setUsers((prev) => prev.map((u) => (u.id === editUser.id ? { ...u, ...updated } : u)));
      setEditUser(null);
      setSuccess(`Utilisateur "${editUser.username}" modifié.`);
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Erreur lors de la modification.");
    } finally {
      setEditSubmitting(false);
    }
  }, [editUser, editForm]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!form.username || !form.password) {
      setError("Identifiant et mot de passe sont obligatoires.");
      return;
    }
    if (!form.entrepriseId) {
      setError("Veuillez sélectionner une entreprise.");
      return;
    }
    if ((form.role === "boutique" || form.role === "usine") && !form.lieuId) {
      setError("Veuillez sélectionner un lieu pour ce rôle.");
      return;
    }

    try {
      setSubmitting(true);
      const payload: Record<string, unknown> = {
        username: form.username,
        password: form.password,
        first_name: form.first_name || "",
        last_name: form.last_name || "",
        email: form.email || "",
        role: form.role,
        entreprise: form.entrepriseId,
        is_active: true,
      };
      if ((form.role === "boutique" || form.role === "usine") && form.lieuId) {
        payload.lieu = form.lieuId;
      }

      const created = await apiFetch("/admin/users/", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setUsers((prev) => [created, ...prev]);
      setSuccess("Utilisateur créé avec succès.");
      setForm((prev) => ({
        ...prev,
        username: "",
        password: "",
        first_name: "",
        last_name: "",
        email: "",
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la création.");
    } finally {
      setSubmitting(false);
    }
  };

  if (user?.role !== "admin") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Utilisateurs</h1>
        <p className="text-sm text-muted-foreground">
          Seuls les administrateurs peuvent gérer les utilisateurs.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Utilisateurs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Création et gestion des comptes (admin, comptable, usine, boutiques).
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Créer un utilisateur</CardTitle>
          <CardDescription>
            Pour un compte boutique/usine, rattacher l&apos;utilisateur à un lieu du bon type.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="username">Identifiant</Label>
              <Input id="username" value={form.username} onChange={handleChange("username")} required className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Mot de passe</Label>
              <Input id="password" type="password" value={form.password} onChange={handleChange("password")} required className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="first_name">Prénom</Label>
              <Input id="first_name" value={form.first_name} onChange={handleChange("first_name")} className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="last_name">Nom</Label>
              <Input id="last_name" value={form.last_name} onChange={handleChange("last_name")} className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={form.email} onChange={handleChange("email")} className="h-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">Rôle</Label>
              <select id="role" value={form.role} onChange={handleRoleChange} className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm">
                <option value="admin">Admin</option>
                <option value="comptable">Comptable</option>
                <option value="usine">Usine</option>
                <option value="boutique">Boutique</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="entreprise">Entreprise</Label>
              <select id="entreprise" value={form.entrepriseId || ""} onChange={handleChange("entrepriseId")} className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm">
                <option value="">Sélectionner…</option>
                {entreprises.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.nom}
                  </option>
                ))}
              </select>
            </div>
            {(form.role === "boutique" || form.role === "usine") && (
              <div className="space-y-2">
                <Label htmlFor="lieu">{form.role === "boutique" ? "Boutique" : "Usine"}</Label>
                <select id="lieu" value={form.lieuId || ""} onChange={handleChange("lieuId")} className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm">
                  <option value="">Sélectionner…</option>
                  {lieuxForSelectedEntreprise.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.nom}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="sm:col-span-2 flex flex-col gap-2">
              {error && <p className="text-sm text-destructive">{error}</p>}
              {success && <p className="text-sm text-emerald-600">{success}</p>}
              <Button type="submit" className="w-full sm:w-auto h-9" disabled={submitting || loading}>
                {submitting ? "Création..." : "Créer l'utilisateur"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Utilisateurs existants</CardTitle>
          <CardDescription>Aperçu des comptes existants.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : users.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun utilisateur.</p>
          ) : (
            <div className="overflow-x-auto -mx-1 min-w-0">
              <table className="w-full min-w-[320px] text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left py-2 px-1">Identifiant</th>
                    <th className="text-left py-2 px-1">Nom</th>
                    <th className="text-left py-2 px-1">Rôle</th>
                    <th className="text-left py-2 px-1">Lieu</th>
                    <th className="text-left py-2 px-1">Active</th>
                    <th className="py-2 px-1">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-b hover:bg-muted/20">
                      <td className="py-1.5 px-1 font-mono">{u.username}</td>
                      <td className="py-1.5 px-1">
                        {u.first_name} {u.last_name}
                      </td>
                      <td className="py-1.5 px-1">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          u.role === "admin"
                            ? "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300"
                            : u.role === "comptable"
                            ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
                            : u.role === "usine"
                            ? "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300"
                            : "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
                        }`}>
                          {u.role_display}
                        </span>
                      </td>
                      <td className="py-1.5 px-1 text-muted-foreground">{u.lieu ? u.lieu.nom : "—"}</td>
                      <td className="py-1.5 px-1">
                        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${u.is_active ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300" : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"}`}>
                          {u.is_active ? "Actif" : "Inactif"}
                        </span>
                      </td>
                      <td className="py-1.5 px-1">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-foreground"
                            title="Modifier"
                            onClick={() => openEditModal(u)}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          {u.id !== user?.id && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-destructive hover:text-destructive"
                              title="Supprimer"
                              onClick={() => handleDelete(u)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
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

      {/* Modal modification utilisateur */}
      {editUser && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setEditUser(null)}
        >
          <Card className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">Modifier — {editUser.username}</CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditUser(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {editError && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">
                  {editError}
                </p>
              )}
              <div className="space-y-1.5">
                <Label>Nouveau mot de passe</Label>
                <Input
                  type="password"
                  placeholder="Laisser vide pour ne pas changer"
                  value={editForm.password}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, password: e.target.value }))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Rôle</Label>
                <select
                  value={editForm.role}
                  onChange={(e) => handleEditRoleChange(e.target.value as Role)}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="admin">Admin</option>
                  <option value="comptable">Comptable</option>
                  <option value="usine">Usine</option>
                  <option value="boutique">Boutique</option>
                </select>
              </div>
              {(editForm.role === "boutique" || editForm.role === "usine") && (
                <div className="space-y-1.5">
                  <Label>{editForm.role === "boutique" ? "Boutique" : "Usine"}</Label>
                  <select
                    value={editForm.lieuId}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, lieuId: e.target.value ? Number(e.target.value) : "" }))}
                    className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                  >
                    <option value="">Sélectionner…</option>
                    {editLieux.map((l) => (
                      <option key={l.id} value={l.id}>{l.nom}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="flex gap-2 pt-1">
                <Button
                  className="flex-1 bg-green-600 hover:bg-green-700 text-white h-9"
                  onClick={handleEditSubmit}
                  disabled={editSubmitting}
                >
                  {editSubmitting ? "Enregistrement…" : "Enregistrer"}
                </Button>
                <Button variant="outline" className="h-9" onClick={() => setEditUser(null)}>
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
