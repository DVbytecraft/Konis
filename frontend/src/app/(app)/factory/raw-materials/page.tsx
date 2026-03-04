"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/contexts/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface AchatRow {
  id: number;
  produit_nom: string;
  quantite: string | number;
  unite: string;
  prix_unitaire: string | number;
  prix_total: string | number;
  notes: string;
  date: string;
}

interface FactoryOption {
  id: number;
  nom: string;
}

const UNITE_CHOICES = [
  { value: "sacs", label: "Sacs" },
  { value: "kg", label: "Kilogrammes" },
  { value: "tonnes", label: "Tonnes" },
];

export default function FactoryAchatsPage() {
  const { user, loading, isAuthenticated } = useAuth();
  const [rows, setRows] = useState<AchatRow[]>([]);
  const [factories, setFactories] = useState<FactoryOption[]>([]);
  const [selectedFactory, setSelectedFactory] = useState("");
  const [form, setForm] = useState({
    produit_nom: "",
    quantite: "",
    unite: "sacs",
    prix_unitaire: "",
    notes: "",
  });
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  const isAdmin = user?.role === "admin";

  const loadFactories = async () => {
    try {
      const res = await apiFetch("/locations/by-type/?type=factory");
      setFactories(res as FactoryOption[]);
    } catch {
      setFactories([]);
    }
  };

  const load = () =>
    apiFetch("/usine/achats/")
      .then((res) => {
        const list = (res as { results?: AchatRow[] }).results ?? (res as AchatRow[]);
        setRows(list.slice(0, 50));
      })
      .catch(() => setRows([]));

  useEffect(() => {
    // Ne charger les données que si l'utilisateur est authentifié
    if (loading || !isAuthenticated) return;
    
    load();
    if (isAdmin) {
      loadFactories();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, loading, isAuthenticated]);

  // Auto-selectionner l'usine de l'utilisateur si pas admin
  useEffect(() => {
    if (!isAdmin && user?.lieu?.id) {
      setSelectedFactory(String(user.lieu.id));
    }
  }, [isAdmin, user?.lieu?.id]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (!form.produit_nom.trim()) {
      setErr("Le nom du produit est obligatoire.");
      return;
    }
    if (!form.quantite || Number(form.quantite) <= 0) {
      setErr("La quantité doit être > 0.");
      return;
    }
    if (form.prix_unitaire && Number(form.prix_unitaire) < 0) {
      setErr("Le prix unitaire doit être >= 0.");
      return;
    }
    const lieuId = isAdmin ? selectedFactory : (user as { lieu?: { id: number } } | null)?.lieu?.id;
    if (!lieuId) {
      setErr(isAdmin ? "Sélectionnez une usine." : "Lieu usine introuvable. Contactez un administrateur.");
      return;
    }
    try {
      setSaving(true);
      await apiFetch("/usine/achats/", {
        method: "POST",
        body: JSON.stringify({
          lieu: Number(lieuId),
          produit_nom: form.produit_nom.trim(),
          quantite: form.quantite,
          unite: form.unite,
          prix_unitaire: form.prix_unitaire || "0",
          notes: form.notes.trim(),
        }),
      });
      setForm({ produit_nom: "", quantite: "", unite: "sacs", prix_unitaire: "", notes: "" });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur");
    } finally {
      setSaving(false);
    }
  };

  // Afficher un message de chargement
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="h-8 w-8 animate-pulse rounded-full border-2 border-primary border-t-transparent"></div>
      </div>
    );
  }

  // Afficher un message si non authentifié
  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <p className="text-muted-foreground">Vous devez être connecté pour accéder à cette page.</p>
        <a href="/login" className="text-primary underline">Se connecter</a>
      </div>
    );
  }

  return (
    <div className="space-y-6 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded-full bg-orange-500"></span>
          Achats usine
        </h1>
        <p className="text-sm text-muted-foreground">
          Enregistrement des achats d&apos;intrants (enregistrement comptable uniquement).
        </p>
      </div>

      {isAdmin && factories.length === 0 && (
        <p className="text-sm text-amber-700">Aucune usine disponible. Créez d&apos;abord une usine.</p>
      )}

      <form onSubmit={submit} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
        {isAdmin && (
          <select
            className="h-10 rounded-md border border-input bg-background px-2 text-sm lg:col-span-2"
            value={selectedFactory}
            onChange={(e) => setSelectedFactory(e.target.value)}
            required
          >
            <option value="">Sélectionner une usine</option>
            {factories.map((f) => (
              <option key={f.id} value={f.id}>{f.nom}</option>
            ))}
          </select>
        )}
        <Input
          className={isAdmin ? "" : "lg:col-span-2"}
          placeholder="Produit acheté (ex: Maïs, Son de blé…)"
          value={form.produit_nom}
          onChange={(e) => setForm((f) => ({ ...f, produit_nom: e.target.value }))}
          required
        />
        <Input
          placeholder="Quantité"
          value={form.quantite}
          onChange={(e) => setForm((f) => ({ ...f, quantite: e.target.value }))}
          required
        />
        <select
          className="h-10 rounded-md border border-input bg-background px-2 text-sm"
          value={form.unite}
          onChange={(e) => setForm((f) => ({ ...f, unite: e.target.value }))}
        >
          {UNITE_CHOICES.map((u) => (
            <option key={u.value} value={u.value}>{u.label}</option>
          ))}
        </select>
        <Input
          placeholder="Prix unitaire (FCFA)"
          value={form.prix_unitaire}
          onChange={(e) => setForm((f) => ({ ...f, prix_unitaire: e.target.value }))}
        />
        <Button type="submit" className="w-full" disabled={saving}>
          {saving ? "Enregistrement…" : "Enregistrer"}
        </Button>
        <Input
          className="sm:col-span-2 lg:col-span-6"
          placeholder="Notes (optionnel)"
          value={form.notes}
          onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
        />
      </form>
      {err && <p className="text-sm text-destructive">{err}</p>}

      <div className="overflow-x-auto rounded-md border -mx-1 sm:mx-0">
        <p className="text-sm font-medium p-3 border-b flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-orange-500"></span>
          Historique des achats
        </p>
        <table className="w-full text-xs sm:text-sm min-w-[560px]">
          <thead>
            <tr className="border-b bg-orange-50/50 dark:bg-orange-950/20">
              <th className="text-left py-2 px-3">Produit</th>
              <th className="text-right py-2 px-3">Quantité</th>
              <th className="text-left py-2 px-3">Unité</th>
              <th className="text-right py-2 px-3">PU (FCFA)</th>
              <th className="text-right py-2 px-3 text-orange-700 dark:text-orange-300">Total (FCFA)</th>
              <th className="text-left py-2 px-3">Date</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="py-4 text-center text-muted-foreground text-sm">
                  Aucun achat enregistré.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-b hover:bg-orange-50/30 dark:hover:bg-orange-950/10">
                <td className="py-1.5 px-3 font-medium">{r.produit_nom}</td>
                <td className="py-1.5 px-3 text-right">{Number(r.quantite).toFixed(2)}</td>
                <td className="py-1.5 px-3 text-muted-foreground">{r.unite}</td>
                <td className="py-1.5 px-3 text-right">{Number(r.prix_unitaire).toFixed(2)}</td>
                <td className="py-1.5 px-3 text-right font-semibold text-orange-700 dark:text-orange-300">
                  {Number(r.prix_total).toFixed(2)}
                </td>
                <td className="py-1.5 px-3 text-muted-foreground">
                  {new Date(r.date).toLocaleString("fr-FR")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
