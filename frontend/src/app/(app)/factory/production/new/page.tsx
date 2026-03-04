"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/contexts/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type ProductOption = { id: number; name: string; code: string; unit: string };
type FactoryOption = { id: number; nom: string };

const UNITE_POIDS = [
  { value: "kg", label: "Kilogrammes" },
  { value: "tonnes", label: "Tonnes" },
];

export default function FactoryProductionNewPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [factories, setFactories] = useState<FactoryOption[]>([]);
  const [selectedFactory, setSelectedFactory] = useState("");
  const [nomLot, setNomLot] = useState("");
  const [productId, setProductId] = useState("");
  const [quantiteSacs, setQuantiteSacs] = useState("");
  const [poids, setPoids] = useState("");
  const [unitePoids, setUnitePoids] = useState("kg");
  const [newFinished, setNewFinished] = useState({ name: "", code: "", unit: "kg" });
  const [savingProduct, setSavingProduct] = useState(false);
  const [err, setErr] = useState("");

  const isAdmin = user?.role === "admin";

  const loadProducts = async () => {
    const res = await apiFetch("/factory/finished-products/catalog/");
    setProducts(res as ProductOption[]);
  };

  const loadFactories = async () => {
    try {
      const res = await apiFetch("/locations/by-type/?type=factory");
      setFactories(res as FactoryOption[]);
    } catch {
      setFactories([]);
    }
  };

  useEffect(() => {
    loadProducts().catch(() => setProducts([]));
    if (isAdmin) {
      loadFactories();
    }
  }, [isAdmin]);

  // Auto-selectionner l'usine de l'utilisateur si pas admin
  useEffect(() => {
    if (!isAdmin && user?.lieu?.id) {
      setSelectedFactory(String(user.lieu.id));
    }
  }, [isAdmin, user?.lieu?.id]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (!nomLot.trim()) {
      setErr("La référence du lot est obligatoire.");
      return;
    }
    if (!productId) {
      setErr("Sélectionne un produit fini.");
      return;
    }
    if (!quantiteSacs || Number(quantiteSacs) <= 0) {
      setErr("Le nombre de sacs doit être > 0.");
      return;
    }
    if (poids && Number(poids) > 0 && Number(quantiteSacs) > 0) {
      const poidsEnKg = unitePoids === "tonnes" ? Number(poids) * 1000 : Number(poids);
      const poidsParSac = poidsEnKg / Number(quantiteSacs);
      if (poidsParSac > 1000) {
        setErr(
          `Poids incohérent : ${poids} ${unitePoids} pour ${quantiteSacs} sacs = ${Math.round(poidsParSac)} kg/sac. ` +
          `Vérifiez l'unité (kg/tonnes) et la valeur saisie.`
        );
        return;
      }
    }
    const lieuId = isAdmin ? selectedFactory : (user as { lieu?: { id: number } } | null)?.lieu?.id;
    if (!lieuId) {
      setErr(isAdmin ? "Sélectionnez une usine." : "Lieu usine introuvable. Contactez un administrateur.");
      return;
    }
    try {
      await apiFetch("/usine/lots/", {
        method: "POST",
        body: JSON.stringify({
          lieu_usine: Number(lieuId),
          nom_lot: nomLot.trim(),
          produit_fini: Number(productId),
          quantite_sacs: quantiteSacs,
          poids: poids || "0",
          unite_poids: unitePoids,
        }),
      });
      router.push("/factory/production");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur");
    }
  };

  const addFinishedProduct = async () => {
    setErr("");
    if (!newFinished.name.trim()) {
      setErr("Le nom du produit fini est requis.");
      return;
    }
    try {
      setSavingProduct(true);
      const created = (await apiFetch("/factory/finished-products/catalog/", {
        method: "POST",
        body: JSON.stringify({
          name: newFinished.name.trim(),
          code: newFinished.code.trim(),
          unit: newFinished.unit.trim() || "kg",
        }),
      })) as ProductOption;
      setNewFinished({ name: "", code: "", unit: "kg" });
      await loadProducts();
      setProductId(String(created.id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur création produit fini");
    } finally {
      setSavingProduct(false);
    }
  };

  return (
    <div className="space-y-4 min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight">Nouveau lot de production</h1>

      <div className="rounded-md border p-3 space-y-2">
        <p className="text-sm font-medium">Ajouter un produit fini à la liste</p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Input
            placeholder="Nom produit fini"
            value={newFinished.name}
            onChange={(e) => setNewFinished((p) => ({ ...p, name: e.target.value }))}
          />
          <Input
            placeholder="Code (optionnel)"
            value={newFinished.code}
            onChange={(e) => setNewFinished((p) => ({ ...p, code: e.target.value }))}
          />
          <Input
            placeholder="Unité (kg)"
            value={newFinished.unit}
            onChange={(e) => setNewFinished((p) => ({ ...p, unit: e.target.value }))}
          />
          <Button
            type="button"
            variant="outline"
            className="w-full sm:w-auto"
            onClick={addFinishedProduct}
            disabled={savingProduct}
          >
            {savingProduct ? "Ajout…" : "Ajouter à la liste"}
          </Button>
        </div>
      </div>

      <form onSubmit={submit} className="space-y-3 w-full max-w-lg">
        {isAdmin && (
          <select
            className="h-10 w-full rounded-md border border-input bg-background px-2 text-sm"
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
        {isAdmin && factories.length === 0 && (
          <p className="text-xs text-amber-700">Aucune usine disponible. Créez d&apos;abord une usine.</p>
        )}
        <Input
          placeholder="Référence lot (ex: ANITCHE-2025-001)"
          value={nomLot}
          onChange={(e) => setNomLot(e.target.value)}
          required
        />
        <select
          className="h-10 w-full rounded-md border border-input bg-background px-2 text-sm"
          value={productId}
          onChange={(e) => setProductId(e.target.value)}
        >
          <option value="">Produit fini</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} {p.code ? `(${p.code})` : ""}
            </option>
          ))}
        </select>
        {products.length === 0 && (
          <p className="text-xs text-amber-700">
            Aucun produit fini dans la liste. Ajoute-en un juste au-dessus.
          </p>
        )}
        <div className="grid grid-cols-2 gap-2">
          <Input
            placeholder="Nombre de sacs"
            value={quantiteSacs}
            onChange={(e) => setQuantiteSacs(e.target.value)}
            required
          />
          <Input
            placeholder="Poids total (optionnel)"
            value={poids}
            onChange={(e) => setPoids(e.target.value)}
          />
        </div>
        <select
          className="h-10 w-full rounded-md border border-input bg-background px-2 text-sm"
          value={unitePoids}
          onChange={(e) => setUnitePoids(e.target.value)}
        >
          {UNITE_POIDS.map((u) => (
            <option key={u.value} value={u.value}>{u.label}</option>
          ))}
        </select>
        {err && <p className="text-sm text-destructive">{err}</p>}
        <Button type="submit" className="w-full sm:w-auto">Créer le lot</Button>
      </form>
    </div>
  );
}
